"""
Elevation-angle (arrival-angle) tables from VOACAP, in the .PRN layout that HFTA and OpenHFTA read.

Method (after the way N6BV made the ARRL files, checked against them: see README, "VOACAP angle tables"):
for an origin and a set of receive points that stand for a target region, VOACAP (method 25, all modes) is run for
every month, every hour and three levels of solar activity, with isotropic antennas. Every propagation mode of every
hour contributes its take-off (elevation) angle, weighted by that mode's reliability (the probability that it gives the
required signal-to-noise ratio). The weighted counts at each whole degree, as percentages, are written per band.

Requires `voacapl` (public-domain VOACAP for Linux, github.com/jawatson/voacapl) and its data folder (`makeitshfbc`).
Set VOACAPL (path to the binary, default: found on PATH) and ITSHFBC (the data folder, default ~/itshfbc).

Every file written here says "VOACAP-generated" in its title. It is not an ARRL file.
"""
from __future__ import annotations
import os, re, shutil, subprocess, tempfile, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BAND_FREQ = {"80": 3.6, "40": 7.1, "30": 10.12, "20": 14.2, "17": 18.1, "15": 21.2, "12": 24.94, "10": 28.4}
BANDS = list(BAND_FREQ)
SSN_LEVELS = {"low": 10, "medium": 70, "high": 150}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Receive points that stand for a region (lat, lon): several per region, as in the ARRL method, so that the table
# covers the spread of distances inside the region. The point sets were chosen so that tables for the W1 (Boston)
# origin agree with the ARRL W1 files (README). Asia is India to China, as the planner's targets define it.
REGIONS = {
    "EU": {"name": "Europe", "points": [(51.5, -0.1), (48.9, 2.3), (52.5, 13.4), (41.9, 12.5), (40.4, -3.7), (59.3, 18.1),
                                        (52.2, 21.0), (50.1, 14.4), (47.5, 19.0), (55.7, 37.6)]},
    "JA": {"name": "Japan", "points": [(35.7, 139.7), (34.7, 135.5), (43.1, 141.3), (33.6, 130.4), (38.3, 140.9)]},
    "AS": {"name": "Asia", "points": [(28.6, 77.2), (39.9, 116.4), (13.8, 100.5), (31.2, 121.5), (22.3, 114.2), (1.3, 103.8)]},
    "AF": {"name": "southern Africa", "points": [(-26.2, 28.0), (-33.9, 18.4), (-17.8, 31.0), (-15.4, 28.3), (-22.6, 17.1)]},
    "OC": {"name": "Oceania", "points": [(-33.9, 151.2), (-37.8, 145.0), (-27.5, 153.0), (-31.9, 115.9), (-36.8, 174.8), (-41.3, 174.8)]},
    "SA": {"name": "South America", "points": [(-23.5, -46.6), (-34.6, -58.4), (-33.4, -70.7), (-12.0, -77.0), (4.7, -74.1), (-22.9, -43.2)]},
    "US": {"name": "USA", "points": [(38.9, -77.0), (40.4, -80.0), (41.5, -81.7), (42.3, -83.0), (41.9, -87.6), (35.8, -78.6), (33.7, -84.4),
                                     (28.5, -81.4), (36.2, -86.8), (38.6, -90.2), (44.9, -93.3), (39.1, -94.6), (32.8, -96.8), (29.8, -95.4),
                                     (39.7, -105.0), (33.4, -112.1), (34.1, -118.2), (37.8, -122.4), (47.6, -122.3), (45.5, -122.7), (40.8, -111.9)]},
}

def available() -> bool:
    try: _voacapl(); _itshfbc(); return True
    except RuntimeError: return False

def _voacapl() -> str:
    exe = os.environ.get("VOACAPL") or shutil.which("voacapl")
    if not exe: raise RuntimeError("voacapl not found. Install it (github.com/jawatson/voacapl) or set VOACAPL.")
    return exe

def _itshfbc() -> Path:
    d = Path(os.environ.get("ITSHFBC") or Path.home() / "itshfbc")
    if not (d / "run").is_dir(): raise RuntimeError(f"VOACAP data folder not found at {d}. Run makeitshfbc or set ITSHFBC.")
    return d

def _ll(v, pos, neg, w):
    """Fixed-column latitude/longitude as VOACAP reads it: number right-aligned in w columns, then N/S or E/W."""
    return f"{abs(v):{w}.2f}{pos if v >= 0 else neg}"

def deck(tx, rx, months, ssn, freqs, label="", power_kw=1.5, min_angle=0.5, req_snr=24.0, method=25) -> str:
    """One VOACAP input deck: one circuit, all given months (an EXECUTE per month). Fixed columns matter."""
    f = list(freqs)[:11] + [0.0] * (11 - len(list(freqs)[:11]))
    out = ["LINEMAX      55       number of lines-per-page", "COEFFS    CCIR", "TIME          1   24    1    1"]
    first = True
    for m in months:
        out.append(f"MONTH      2026{m:5.2f}")
        if first:
            out += [f"SUNSPOT   {ssn:4.0f}.", f"LABEL     {label[:20]:<20} {'':<20}",
                    f"CIRCUIT   {_ll(tx[0], 'N', 'S', 5)}{_ll(tx[1], 'E', 'W', 9)}{_ll(rx[0], 'N', 'S', 9)}{_ll(rx[1], 'E', 'W', 9)}  S     0",
                    f"SYSTEM       1. 150. {min_angle:4.2f}  90. {req_snr:4.1f} 3.00 0.10",
                    "FPROB      1.00 1.00 1.00 0.00",
                    f"ANTENNA       1    1    2   30     0.000[default/isotrope     ]  0.0 {power_kw * 1000:8.4f}",
                    "ANTENNA       2    2    2   30     0.000[default/isotrope     ]  0.0    0.0000",
                    "FREQUENCY " + "".join(f"{x:5.2f}" for x in f), f"METHOD     {method:4d}    0"]
            first = False
        out.append("EXECUTE")
    out.append("QUIT")
    return "\n".join(out) + "\n"

_SUM = re.compile(r"^\s*SUMMARY\s+(\d+) MODES\s+FREQ =\s*([\d.]+) MHZ\s+UT =\s*([\d.]+)")

def parse_method25(text: str):
    """Yield (hour, month, freq, [modes]) per hour and frequency. Each mode: {name, angle, sdbw, rel, prob, snr}.
    The last column of a method-25 summary ("Most REL") is the chosen mode again and is left out."""
    lines = text.splitlines(); month = None; i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^\s+([A-Z][a-z]{2})\s+\d{4}\s+SSN =", ln)
        if m: month = m.group(1)
        m = _SUM.match(ln)
        if m:
            n, fq, hour = int(m.group(1)), float(m.group(2)), float(m.group(3))
            rows = {}; j = i + 1
            while j < len(lines) and not _SUM.match(lines[j]) and not lines[j].startswith("     CCIR"):
                t = lines[j].rstrip()
                for key in ("ANGLE", "SIG. POW.", "RELIABIL", "MODE PROB", "SNR", "TRAN.LOSS"):
                    if t.lstrip().startswith(key + " "):
                        rows[key] = [float(x) for x in t.split()[len(key.split()):]]
                j += 1
            try:
                modes = []
                for k in range(n):
                    modes.append({"angle": rows["ANGLE"][k], "sdbw": rows["SIG. POW."][k], "rel": rows["RELIABIL"][k],
                                  "prob": rows["MODE PROB"][k], "snr": rows["SNR"][k]})
                yield hour, month, fq, modes
            except (KeyError, IndexError):
                pass
            i = j
        else:
            i += 1

_LOCAL = threading.local()

def _private_itshfbc() -> Path:
    """voacapl keeps scratch files with fixed names in <itshfbc>/run, so parallel runs need their own run folder.
    Each thread gets a private copy of the data folder made of links, with its own run folder."""
    d = getattr(_LOCAL, "its", None)
    if d is None or not d.exists():
        src = _itshfbc(); d = Path(tempfile.mkdtemp(prefix="itshfbc-")); _LOCAL.its = d
        def copy_tree(a: Path, b: Path):
            """Plain read/write copy (shutil's Windows copy needs an API that Wine lacks; the files are small)."""
            b.mkdir(parents=True, exist_ok=True)
            for x in a.iterdir():
                if x.is_dir(): copy_tree(x, b / x.name)
                elif x.is_file(): (b / x.name).write_bytes(x.read_bytes())
        for child in src.iterdir():
            if child.name == "run": continue
            if os.name == "nt":                                # Windows: copy (a few MB); the Fortran core does not follow links
                if child.is_dir(): copy_tree(child, d / child.name)
                else: (d / child.name).write_bytes(child.read_bytes())
            else:
                os.symlink(child, d / child.name)
        copy_tree(src / "run", d / "run")
    return d

def run_deck(text: str, tag: str) -> str:
    """Run one deck through voacapl; returns the output text."""
    its = _private_itshfbc(); name = f"aoa_{tag}_{uuid.uuid4().hex[:6]}"
    inp, out = its / "run" / f"{name}.dat", its / "run" / f"{name}.out"
    inp.write_text(text)
    try:
        r = subprocess.run([_voacapl(), str(its), inp.name, out.name], capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"voacapl failed ({r.returncode}): {(r.stdout + r.stderr)[-400:]}")
        return out.read_text(errors="ignore")
    finally:
        inp.unlink(missing_ok=True); out.unlink(missing_ok=True)

def histogram(origin, points, bands=BANDS, months=range(1, 13), ssns=tuple(SSN_LEVELS.values()), hours=None,
              workers=4, progress=None, cancel=None, **deck_kw) -> dict:
    """{band: {angle_deg: weighted count}} plus the total weight per band and 'meta'.
    months: 1..12; hours: UTC hours to keep (None = all); ssns: sunspot numbers to run (one run each)."""
    freqs = [BAND_FREQ[b] for b in bands]
    jobs = [(p, s) for p in points for s in ssns]
    counts = {b: {} for b in bands}; total = {b: 0.0 for b in bands}; done = [0]
    def one(job):
        p, s = job
        if cancel and cancel(): return []
        txt = run_deck(deck(origin, p, list(months), s, freqs, method=25, **deck_kw), f"{abs(p[0]):.0f}{abs(p[1]):.0f}{int(s)}")
        return list(parse_method25(txt))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for rows in ex.map(one, jobs):
            done[0] += 1
            if progress: progress(done[0], len(jobs))
            for hour, month, fq, modes in rows:
                if hours is not None and int(round(hour)) % 24 not in hours: continue
                b = next((b for b in bands if abs(BAND_FREQ[b] - fq) < 0.1), None)
                if b is None: continue
                for m in modes:
                    if m["rel"] <= 0: continue
                    a = max(1, int(round(m["angle"])))
                    counts[b][a] = counts[b].get(a, 0.0) + m["rel"]; total[b] += m["rel"]
    if cancel and cancel(): raise RuntimeError("Cancelled")
    return {"counts": counts, "weight_total": total,
            "meta": {"origin": list(origin), "points": [list(p) for p in points], "months": list(months), "ssn": list(ssns),
                     "hours": None if hours is None else sorted(hours), "weighting": "all modes, weight = reliability", **deck_kw}}

def to_prn(h: dict, title: str, bands=BANDS, max_angle=70) -> str:
    """ARRL .PRN layout: title line, 'Elev' header, one row per degree with the percentage per band."""
    out = [f"VOACAP-generated: {title}"[:78], "Elev   " + "".join(f"{b + 'm':>7}" for b in bands)]
    for a in range(1, max_angle + 1):
        row = []
        for b in bands:
            tot = h["weight_total"].get(b, 0.0)
            row.append(100.0 * h["counts"][b].get(a, 0.0) / tot if tot > 0 else 0.0)
        out.append(f"{a:2d}     " + "".join(f"{v:7.1f}" for v in row))
    return "\n".join(out) + "\n"

def describe(meta: dict) -> str:
    """Short text of what a table covers, for the title and the project notes."""
    m = meta.get("months") or list(range(1, 13)); h = meta.get("hours"); s = meta.get("ssn") or []
    mt = "all months" if len(m) == 12 else "months " + ",".join(MONTH_NAMES[x - 1] for x in m)
    ht = "all hours" if not h or len(h) == 24 else f"UTC hours {min(h):02d}-{max(h):02d}"
    st = "SSN " + "/".join(f"{x:g}" for x in s)
    return f"{mt}, {ht}, {st}"

def generate(origin, region, out_file: Path, title=None, **kw) -> dict:
    """Write a VOACAP-generated .PRN for an origin and a region: a key of REGIONS, or {'name':..., 'points': [...]}."""
    reg = REGIONS[region] if isinstance(region, str) else region
    h = histogram(origin, reg["points"], **kw)
    t = title or f"{origin[0]:.2f},{origin[1]:.2f} to {reg['name']}"
    Path(out_file).write_text(to_prn(h, f"{t} ({describe(h['meta'])})", kw.get("bands", BANDS)))
    return h
