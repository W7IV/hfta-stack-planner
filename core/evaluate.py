"""
Evaluator. Every number it produces is built from HFTA runs, and every HFTA run is recorded with the exact inputs
a user enters in the original HFTA (terrain file, elevation-angle file, frequency, antenna type, heights, ground,
diffraction). Combination steps are plain arithmetic and are recorded too:
  - azimuth averaging: weighted mean of FOM (dB) over the target's headings
  - stack switching: the best (highest) of the switch settings offered by the tower
  - bands, targets: shown separately; no hidden totals
Spacing warnings (core/spacing.py) are attached to each result; they never change a number.
The direction of every run is set by the terrain file, i.e. by the targets a tower is evaluated on.
"""
from __future__ import annotations
import hashlib, itertools, json
from pathlib import Path
import numpy as np
import engine
from . import antennas as A, terrain as TR, project as P, spacing as SP

def band_freq(proj, band): return float(proj["settings"].get("band_freq", {}).get(band) or A.BAND_FREQ[band])

def stack_for_band(tower, band):
    """Antennas of the tower that work on this band, lowest first."""
    rows = [a for a in tower["antennas"] if band in A.el_of(a)]
    return sorted(rows, key=lambda a: a["h"])

def switch_options(n, mode):
    """Switch settings offered by the tower. 'full': whole stack only (plain HFTA). 'stackmatch': whole stack,
    bottom pair, top pair, each antenna alone. 'all': every combination."""
    idx = tuple(range(n))
    if n == 0: return []
    if mode == "full" or n == 1: return [idx]
    if mode == "all": return [c for k in range(n, 0, -1) for c in itertools.combinations(idx, k)]
    pairs = {2: [], 3: [(0, 1), (1, 2)], 4: [(0, 1), (2, 3)]}[n]
    return [idx] + pairs + [(i,) for i in idx]

def target_azimuths(target):
    offs = target.get("offsets") or [0]; w = target.get("weights") or [1] * len(offs)
    return [((target["heading"] + o) % 360, float(wi)) for o, wi in zip(offs, w)]

def plan(proj, pslug):
    """Build the list of result cells and the unique HFTA runs they need."""
    s = proj["settings"]; cells, runs = [], {}
    bands_all = sorted({b for t in proj["targets"] for b in t["bands"]}, key=lambda b: A.BANDS.index(b))
    for site in proj["sites"]:
        sdir = P.site_dir(pslug, site["id"]); idx = TR.profile_index(sdir)
        if not idx: continue
        for tower in proj["towers"]:
            warns = SP.check(tower["antennas"], lambda b: band_freq(proj, b), s["spacing"])
            for target in proj["targets"]:
                if tower.get("targets") and target["id"] not in tower["targets"]:
                    continue
                for band in target["bands"]:
                    st = stack_for_band(tower, band)
                    if not st: continue
                    try: types = {A.hfta_type(a, band) for a in st}
                    except ValueError as e: types = {str(e)}
                    hs_band = {a["h"] for a in st}
                    cell = {"site": site["id"], "tower": tower["id"], "target": target["id"], "band": band,
                            "freq": band_freq(proj, band), "antennas": [{"h": a["h"], "el": A.el_of(a)[band], "desc": A.describe(a)} for a in st],
                            "issues": [], "options": [],
                            "spacing": [w for w in warns if (w["kind"] == "stack" and w["band"] == band) or (w["kind"] == "gap" and hs_band & set(w["heights"]))]}
                    if any(x not in A.TYPE.values() for x in types): cell["issues"].append("HFTA has no antenna type with that element count (use 1-6 or 8). Not evaluated.")
                    elif len(types) > 1: cell["issues"].append("Different antenna types on one band: HFTA needs one type per run. Not evaluated.")
                    if len(st) > 4: cell["issues"].append("More than 4 antennas on one band: HFTA allows at most 4. Not evaluated.")
                    if cell["issues"]: cells.append(cell); continue
                    t = types.pop()
                    for opt in switch_options(len(st), tower.get("switching", "stackmatch")):
                        hs = [st[i]["h"] for i in opt]; o = {"use": list(opt), "heights": hs, "az": []}
                        for az, w in target_azimuths(target):
                            k, fname = TR.nearest(idx, az)
                            spec = {"site": site["id"], "file": fname, "freq": cell["freq"], "hfta_type": t, "heights_ft": hs,
                                    "phases": [1] * len(hs), "epsr": s["epsr"], "sigma": s["sigma"], "diffraction": s["diffraction"]}
                            rid = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:10]
                            runs[rid] = spec
                            o["az"].append({"az": az, "file_az": k, "weight": w, "run": rid})
                        cell["options"].append(o)
                    cell["hfta_type"] = t
                    cells.append(cell)
    return cells, runs, bands_all

def run_one(args):
    rid, spec, sdir = args
    d, h = TR.load_profile(Path(sdir), spec["file"])
    pat = engine.pattern(d, h, spec["freq"], spec["heights_ft"], spec["phases"], engine.ANTENNA_TYPES[spec["hfta_type"]],
                         spec["sigma"], spec["epsr"], spec["diffraction"])
    pat = np.asarray(pat, dtype=float); bad = ~np.isfinite(pat)
    if bad.any() and (~bad).sum() >= 2:
        # Known fault in the calculation core: a few angles can come back as NaN on some profiles (seen at 19.5-20.5 deg,
        # 28 MHz, one antenna height, diffraction on; reported to OpenHFTA). Fill them by straight-line interpolation from the neighbouring angles.
        x = np.arange(len(pat)); pat[bad] = np.interp(x[bad], x[~bad], pat[~bad])
    return rid, [round(float(x), 3) for x in pat]

def finish(proj, pslug, cells, runs, patterns):
    """Compute FOMs from patterns and choose switch settings."""
    targets = {t["id"]: t for t in proj["targets"]}; towers = {t["id"]: t for t in proj["towers"]}
    prn_cache, fom_log = {}, {}
    for c in cells:
        if c["issues"]: continue
        tg = targets[c["target"]]; tw = towers[c["tower"]]
        key = (tg["prn"], c["freq"])
        if key not in prn_cache:
            prn_cache[key] = engine.parse_aoa((P.prn_dir(pslug) / tg["prn"]).read_text(errors="ignore"), c["freq"])
        aoa = prn_cache[key]
        for o in c["options"]:
            tot_w = sum(a["weight"] for a in o["az"])
            for a in o["az"]:
                f = engine.fom(np.array(patterns[a["run"]], dtype=np.float32), aoa)
                a["fom"] = None if f is None else round(f, 2)
                fom_log.setdefault(a["run"], {})[f'{tg["prn"]}|{c["band"]}'] = a["fom"]
            good = [a for a in o["az"] if a["fom"] is not None]
            o["score"] = round(sum(a["fom"] * a["weight"] for a in good) / sum(a["weight"] for a in good), 2) if good else None
        best = max((o for o in c["options"] if o["score"] is not None), key=lambda o: o["score"], default=None)
        c["best"] = c["options"].index(best) if best else None
        c["hfta_fom"] = best["score"] if best else None
    return fom_log

def total(cell, layers_on=None):
    """The result of a cell: the HFTA FOM of its best switch setting. (Kept for old callers.)"""
    return cell.get("hfta_fom")
