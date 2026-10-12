"""
engine.py - calculation layer for the HFTA web GUI.

Wraps the OpenHFTA Fortran core (OpenYTWCore) without changing its numerics.
All lengths passed to the core are in FEET (core convention).

Functions here are pure and picklable so they can run in worker processes.
The Fortran core keeps state in COMMON blocks, so it is NOT thread-safe:
parallel work must use processes, never threads.
"""
from __future__ import annotations

import ctypes
import itertools
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# --- locate the OpenHFTA checkout (hfta.py + libopenytwcore.so) -------------
OPENHFTA_DIR = Path(os.environ.get("OPENHFTA_DIR", Path(__file__).resolve().parent.parent / "openhfta"))
if str(OPENHFTA_DIR) not in sys.path:
    sys.path.insert(0, str(OPENHFTA_DIR))

import hfta  # noqa: E402  (OpenHFTA module; used for loader, types, FOM, PRN parser)

M_TO_FT = 3.28084

ANTENNA_TYPES = {  # GUI label -> core pattern type
    "Dipole": 1, "2-Ele": 2, "3-Ele": 3, "4-Ele": 4,
    "5-Ele": 5, "6-Ele": 6, "8-Ele": 7,
}

SOIL_PRESETS = {  # name -> (sigma S/m, eps_r); values from original HFTA GUI
    "Very poor soil": (0.001, 5), "Sandy, dry soil": (0.002, 10),
    "Poor soil": (0.002, 13), "Average soil": (0.005, 13),
    "Good soil": (0.010, 14), "Very good soil": (0.030, 20),
    "Fresh water": (0.001, 81), "Salt water": (5.000, 80),
}

ANGLES = np.arange(0.25, 35.25, 0.25)  # 140 output angles of the core

_LIB = None

# Version of this wrapper's numerical handling (run inputs, invalid-output policy). Part of every run key, so a
# change here makes old stored patterns unusable instead of silently reused.
WRAPPER_NUMERIC_VERSION = "2"
_ENGINE = None


def engine_info() -> dict:
    """Identity of the calculation engine actually used: OpenHFTA commit (when the checkout has .git), the SHA-256 of
    the native library, and the wrapper version. Stored with results and exports. 'unknown' when not found."""
    global _ENGINE
    if _ENGINE is None:
        import hashlib, subprocess
        lib = os.environ.get("OPENHFTA_LIB") or (hfta.find_ytw_core_library() if hasattr(hfta, "find_ytw_core_library") else None)
        sha = "unknown"
        if lib and Path(lib).exists():
            sha = hashlib.sha256(Path(lib).read_bytes()).hexdigest()
        commit = os.environ.get("OPENHFTA_COMMIT") or "unknown"
        if commit == "unknown" and (OPENHFTA_DIR / ".git").exists():
            try:
                commit = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(OPENHFTA_DIR), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
            except Exception:  # noqa: BLE001
                pass
        _ENGINE = {"name": "OpenHFTA", "commit": commit, "library_sha256": sha, "wrapper": WRAPPER_NUMERIC_VERSION}
        _ENGINE["id"] = hashlib.sha256(f"{commit}|{sha}|{WRAPPER_NUMERIC_VERSION}".encode()).hexdigest()[:12]
    return _ENGINE


def _lib():
    """Load the core once per process."""
    global _LIB
    if _LIB is None:
        _LIB = hfta.load_ytw_core(os.environ.get("OPENHFTA_LIB"))
    return _LIB


# --- input parsing ----------------------------------------------------------
def parse_profile_text(text: str) -> Tuple[List[float], List[float]]:
    """Parse a legacy .PRO profile. Same rules as hfta.parse_profile. Returns feet."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("Empty profile file")
    first = lines[0].lower()
    if "meter" in first:
        f, body = M_TO_FT, lines[1:]
    elif "feet" in first or "foot" in first:
        f, body = 1.0, lines[1:]
    else:
        f, body = 1.0, lines
    d, h = [], []
    for ln in body:
        if ln.startswith("#"):
            continue
        p = ln.split()
        if len(p) >= 2:
            try:
                x, y = float(p[0]) * f, float(p[1]) * f   # both parsed before either is kept
            except ValueError:
                continue                                   # text line (e.g. a column heading), as in hfta.parse_profile
            if not (np.isfinite(x) and np.isfinite(y)):
                raise ValueError(f"Profile has a non-finite value: {ln[:40]}")
            if d and x <= d[-1]:
                raise ValueError(f"Profile distances must increase: {x / f:g} after {d[-1] / f:g}")
            d.append(x); h.append(y)
    if len(d) < 2:
        raise ValueError("Profile must contain at least 2 points")

    if len(d) > 148:
        raise ValueError(f"Profile has {len(d)} points; the core accepts at most 148")
    return d, h


def prn_bands(text: str) -> List[str]:
    """Band columns present in an ARRL .PRN angle-of-arrival file."""
    lines = text.strip().splitlines()
    if len(lines) < 2 or not lines[1].strip().startswith("Elev"):
        raise ValueError("Not an ARRL .PRN file: second line must start with 'Elev'")
    return lines[1].split()[1:]


def parse_aoa(text: str, freq_mhz: float) -> Dict[int, float]:
    band = hfta.frequency_to_band(freq_mhz)
    if band is None:
        return {}
    return hfta.parse_prn_multiband(text, band)


def frequency_warning(freq_mhz: float) -> Optional[str]:
    if hfta.frequency_to_band(freq_mhz) is None:
        return "Frequency is outside the amateur bands. No arrival-angle data, so no FOM."
    if freq_mhz < 7.0:
        return ("Below 7 MHz the diffraction method (UTD) is less reliable, mainly with low antennas "
                "and steep terrain near the tower. Compare with diffraction off.")
    if freq_mhz > 30.0:
        return ("Above 30 MHz the method is not validated. Terrain data must be fine enough "
                "to resolve features of about 1/8 wavelength.")
    return None


# --- core call --------------------------------------------------------------
def pattern(dist_ft: Sequence[float], hgt_ft: Sequence[float], freq_mhz: float,
            heights_ft: Sequence[float], phases: Sequence[int], ant_type: int,
            sigma: float = 0.005, epsr: float = 13.0, diffraction: bool = True,
            move_tower_ft: float = 0.0) -> np.ndarray:
    """Elevation pattern in dB at ANGLES. Mirrors hfta.analyze() exactly."""
    if not 1 <= len(heights_ft) <= 4:
        raise ValueError("1 to 4 antennas are supported")
    d = np.asarray(dist_ft, dtype=np.float32)
    h = np.asarray(hgt_ft, dtype=np.float32)
    if move_tower_ft > 0:
        d = np.concatenate([[0.0], d + move_tower_ft]).astype(np.float32)
        h = np.concatenate([[h[0]], h]).astype(np.float32)

    dg0 = np.zeros(151, dtype=np.float32)
    hg0 = np.zeros(151, dtype=np.float32)
    n = min(len(d), 148)
    dg0[1:n + 1] = d[:n]
    hg0[1:n + 1] = h[:n]
    hant = np.zeros(4, dtype=np.float32)
    hant[:len(heights_ft)] = heights_ft
    ph = np.ones(4, dtype=np.int16)
    ph[:len(phases)] = phases
    out = np.zeros(140, dtype=np.float32)
    R, I16 = hfta.FortranReal, hfta.FortranInt16
    _lib().ytwcore1_(
        dg0.ctypes.data_as(ctypes.POINTER(R)), hg0.ctypes.data_as(ctypes.POINTER(R)),
        hant.ctypes.data_as(ctypes.POINTER(R)),
        ctypes.byref(R(freq_mhz)), ctypes.byref(R(epsr)), ctypes.byref(R(sigma)),
        ctypes.byref(I16(ant_type)), ctypes.byref(I16(0 if diffraction else 1)),
        ctypes.byref(I16(0)), ctypes.byref(R(0.0)),
        out.ctypes.data_as(ctypes.POINTER(R)), ph.ctypes.data_as(ctypes.POINTER(I16)),
    )
    return out


def fom(pat_db: np.ndarray, aoa: Dict[int, float]) -> Optional[float]:
    if not aoa:
        return None
    v = hfta.compute_fom(pat_db, aoa)
    return None if not np.isfinite(v) else float(v)


# --- higher-level tasks (one worker call = one antenna set, all bands x paths) --
def evaluate(task: dict) -> dict:
    """
    task = {heights_ft, phases, sigma, epsr, diffraction, move_tower_ft,
            paths: [{dist, hgt, weight}],
            bands: [{freq, ant_type, weight, aoa: [dict per path]}],
            want_pattern: bool}
    Returns per band: per-path FOM and path-weighted band score; overall band-weighted score.
    """
    pw = [p["weight"] for p in task["paths"]]
    band_foms, band_scores, pats = [], [], []
    for b in task["bands"]:
        foms, bp = [], []
        for p, aoa in zip(task["paths"], b["aoa"]):
            pat = pattern(p["dist"], p["hgt"], b["freq"], task["heights_ft"], task["phases"],
                          b["ant_type"], task["sigma"], task["epsr"], task["diffraction"],
                          task.get("move_tower_ft", 0.0))
            foms.append(fom(pat, aoa))
            if task.get("want_pattern"):
                bp.append([round(float(x), 2) for x in pat])
        band_foms.append(foms)
        band_scores.append(weighted_score(foms, pw))
        pats.append(bp)
    score = weighted_score(band_scores, [b["weight"] for b in task["bands"]])
    r = {"heights_ft": list(task["heights_ft"]), "band_foms": band_foms,
         "band_scores": band_scores, "score": score}
    if task.get("want_pattern"):
        r["patterns"] = pats
    return r


def weighted_score(foms: List[Optional[float]], weights: List[float]) -> Optional[float]:
    pairs = [(f, w) for f, w in zip(foms, weights) if f is not None and w > 0]
    if not pairs:
        return None
    return sum(f * w for f, w in pairs) / sum(w for _, w in pairs)


def subsets(n: int) -> List[Tuple[int, ...]]:
    """All non-empty antenna combinations, singles first, full stack last."""
    return [c for k in range(1, n + 1) for c in itertools.combinations(range(n), k)]


# --- optimiser grid ---------------------------------------------------------
def height_grid(specs: List[dict], step_ft: float, min_spacing_ft: float,
                max_top_ft: Optional[float] = None) -> List[Tuple[float, ...]]:
    """
    specs: per antenna, bottom to top: {"fixed": h} or {"min": a, "max": b} (feet).
    Returns all height tuples with h[i+1] - h[i] >= min_spacing.
    """
    axes = []
    for s in specs:
        if "fixed" in s:
            axes.append([float(s["fixed"])])
        else:
            lo, hi = float(s["min"]), float(s["max"])
            if hi < lo:
                raise ValueError("Maximum height is below minimum height")
            n = int(np.floor((hi - lo) / step_ft + 1e-6))
            axes.append([round(lo + i * step_ft, 3) for i in range(n + 1)])
    n = 1
    for a in axes: n *= len(a)
    if n > 2_000_000:
        raise ValueError(f"{n:,} height combinations: too many. Use a larger step or narrower ranges.")
    out = []
    for combo in itertools.product(*axes):
        if max_top_ft is not None and combo[-1] > max_top_ft + 1e-6:
            continue
        if all(combo[i + 1] - combo[i] >= min_spacing_ft - 1e-6 for i in range(len(combo) - 1)):
            out.append(combo)
    return out


def _axis(lo: float, hi: float, step: float) -> List[float]:
    if hi < lo:
        raise ValueError("Maximum is below minimum")
    n = int(np.floor((hi - lo) / step + 1e-6))
    return [round(lo + i * step, 3) for i in range(n + 1)]


def equal_grid(n: int, bottom: Tuple[float, float], spacing: Tuple[float, float], step_ft: float,
               min_spacing_ft: float, max_top_ft: Optional[float] = None) -> List[Tuple[float, ...]]:
    """Equally spaced stacks: heights = b + i*s. Searches bottom height b and spacing s."""
    out = []
    s_axis = [0.0] if n == 1 else [s for s in _axis(*spacing, step_ft) if s >= min_spacing_ft - 1e-6]
    for b in _axis(*bottom, step_ft):
        for s in s_axis:
            hs = tuple(round(b + i * s, 3) for i in range(n))
            if max_top_ft is None or hs[-1] <= max_top_ft + 1e-6:
                out.append(hs)
    return out


def refine_grid(centres: List[Tuple[float, ...]], specs: List[dict], coarse: float,
                fine: float, min_spacing_ft: float, max_top_ft: Optional[float] = None) -> List[Tuple[float, ...]]:
    """Fine grid of +/- one coarse step around each centre, clipped to the user ranges."""
    seen = set()
    for c in centres:
        local = []
        for h, s in zip(c, specs):
            if "fixed" in s:
                local.append({"fixed": h})
            else:
                local.append({"min": max(s["min"], h - coarse), "max": min(s["max"], h + coarse)})
        for g in height_grid(local, fine, min_spacing_ft, max_top_ft):
            seen.add(g)
    return sorted(seen)


def refine_equal(centres: List[Tuple[float, ...]], bottom, spacing, coarse: float, fine: float,
                 min_spacing_ft: float, max_top_ft: Optional[float] = None) -> List[Tuple[float, ...]]:
    seen = set()
    for c in centres:
        b, s = c[0], (c[1] - c[0] if len(c) > 1 else 0.0)
        lb = (max(bottom[0], b - coarse), min(bottom[1], b + coarse))
        ls = (max(spacing[0], s - coarse), min(spacing[1], s + coarse))
        for g in equal_grid(len(c), lb, ls, fine, min_spacing_ft, max_top_ft):
            seen.add(g)
    return sorted(seen)


def wavelength_ft(freq_mhz: float) -> float:
    return 983.5712 / freq_mhz
