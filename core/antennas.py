"""
Antennas, as HFTA sees them. HFTA knows only generic Yagis by element count (Dipole, 2-, 3-, 4-, 5-, 6- and 8-element).
An antenna here is a height plus, for each band it works on, the number of elements:
    {"h": 60, "el": {"20": 4, "15": 5, "10": 6}, "turning_radius": 25, "droop": 3}
A multiband antenna is entered in HFTA as the generic type for its element count on each band.
turning_radius and droop are used only by the guy and ice check, never by the HFTA numbers.
"""
from __future__ import annotations

BAND_FREQ = {"160": 1.83, "80": 3.6, "40": 7.1, "30": 10.12, "20": 14.2, "17": 18.1, "15": 21.2,
             "12": 24.94, "10": 28.4, "6": 50.1}
BANDS = list(BAND_FREQ)
ELEMENTS = [1, 2, 3, 4, 5, 6, 8]                       # the types HFTA offers
TYPE = {1: "Dipole", 2: "2-Ele", 3: "3-Ele", 4: "4-Ele", 5: "5-Ele", 6: "6-Ele", 8: "8-Ele"}
# Free-space gain (dBi) of each HFTA generic type, measured from the core (peak over flat ground minus 6.0 dB). Information only.
MODEL_GAIN_DBI = {"Dipole": 2.1, "2-Ele": 5.4, "3-Ele": 6.9, "4-Ele": 8.4, "5-Ele": 9.35, "6-Ele": 10.8, "8-Ele": 11.8}

def wavelength_ft(mhz): return 983.571 / mhz

def el_of(a) -> dict:
    return {b: int(n) for b, n in (a.get("el") or {}).items() if n}

def bands_of(a) -> list:
    return sorted(el_of(a), key=BANDS.index)

def hfta_type(a_or_n, band=None) -> str:
    n = a_or_n if isinstance(a_or_n, int) else el_of(a_or_n)[band]
    if n not in TYPE: raise ValueError(f"HFTA has no {n}-element type (use 1-6 or 8)")
    return TYPE[n]

def el_text(n): return "dipole" if n == 1 else f"{n}-el"

def describe(a) -> str:
    """e.g. '20/15/10 m 4-el' or '20 m 4-el, 15 m 5-el, 10 m 6-el'."""
    e = el_of(a); bs = bands_of(a)
    if not bs: return "no bands"
    if len({e[b] for b in bs}) == 1: return f"{'/'.join(bs)} m {el_text(e[bs[0]])}"
    return ", ".join(f"{b} m {el_text(e[b])}" for b in bs)

# ---- reading projects saved before generic antennas (brand models). Only used to convert old files.
_LEGACY = {
    "JK Big-Tri": ({"20": 4, "15": 5, "10": 6}, 25.4, 3.0), "JK Mid-Tri": ({"20": 3, "15": 4, "10": 5}, 22.0, 2.5),
    "JK MidTri-40": ({"40": 2, "20": 3, "15": 4, "10": 5}, 27.7, 4.0), "JK 404C": ({"40": 4}, 31.25, 5.0),
    "JK 404 Grande": ({"40": 4}, 43.0, 6.0), "JK 801-T rigid dipole": ({"80": 1}, None, 6.0),
}
_GENERIC = {"Generic Dipole": 1, "Generic 2-Ele": 2, "Generic 3-Ele": 3, "Generic 4-Ele": 4, "Generic 5-Ele": 5, "Generic 6-Ele": 6, "Generic 8-Ele": 8}

def upgrade(a: dict, bands_hint=None) -> dict:
    """Convert an old {'model': ...} entry to the generic form. Leaves new entries unchanged."""
    if "model" not in a: return a
    m = a["model"]; out = {k: v for k, v in a.items() if k != "model"}
    if m in _LEGACY:
        el, tr, dr = _LEGACY[m]; out["el"] = dict(el)
        out.setdefault("turning_radius", tr); out.setdefault("droop", dr)
    else:
        out["el"] = {b: _GENERIC.get(m, 3) for b in (bands_hint or ["20", "15", "10"])}
    return out
