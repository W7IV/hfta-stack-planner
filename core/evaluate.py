"""
Evaluator. Every number it produces is built from OpenHFTA runs (the HFTA method), and every HFTA run is recorded with the exact inputs
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

def tower_serves(tower, target_id) -> bool:
    """targets missing or None = every target (older projects); a list = only those, so [] = none."""
    t = tower.get("targets")
    return t is None or target_id in t

def aoa_status(proj, pslug, target, freq, cache):
    """(arrival-angle data, None) or (None, reason). The reason says exactly what is missing."""
    prn = target.get("prn") or ""
    key = (prn, freq)
    if key not in cache:
        if not prn:
            cache[key] = (None, "No elevation-angle (.PRN) file chosen for this target. Not evaluated.")
        else:
            f = P.prn_file(pslug, prn)
            if not f.exists():
                cache[key] = (None, f"The elevation-angle file {prn} is not in the project. Not evaluated.")
            else:
                try:
                    aoa = engine.parse_aoa(f.read_text(errors="ignore"), freq)
                except Exception as e:  # noqa: BLE001
                    aoa, err = None, f"The elevation-angle file {prn} cannot be read ({e}). Not evaluated."
                else:
                    err = None
                    vals = list((aoa or {}).values())
                    if not vals or any((not np.isfinite(v)) or v < 0 for v in vals) or sum(vals) <= 0:
                        aoa, err = None, f"The elevation-angle file {prn} has no usable data for {freq:g} MHz. Not evaluated."
                cache[key] = (aoa, err)
    return cache[key]

def plan(proj, pslug):
    """Build the list of result cells and the unique HFTA runs they need. A run's key includes the terrain file's
    content and the engine identity, so a changed terrain file or a new engine never reuses an old pattern."""
    s = proj["settings"]; cells, runs = [], {}
    bands_all = sorted({b for t in proj["targets"] for b in t["bands"]}, key=lambda b: A.BANDS.index(b))
    site_ids = {x["id"] for x in proj["sites"]}
    eng = engine.engine_info()["id"]; aoa_cache = {}; digests = {}
    for site in proj["sites"]:
        sdir = P.site_dir(pslug, site["id"]); idx = TR.profile_index(sdir)
        if not idx: continue
        for tower in proj["towers"]:
            # A tower with a location is evaluated at that site only. No location (or a site that no longer
            # exists) means every site, for comparing sites.
            if tower.get("site") in site_ids and tower["site"] != site["id"]:
                continue
            warns = SP.check(tower["antennas"], lambda b: band_freq(proj, b), s["spacing"])
            for target in proj["targets"]:
                if not tower_serves(tower, target["id"]):
                    continue
                for band in target["bands"]:
                    st = stack_for_band(tower, band)
                    if not st: continue
                    try: types = {A.hfta_type(a, band) for a in st}
                    except ValueError as e: types = {str(e)}
                    hs_band = {a["h"] for a in st}
                    cell = {"site": site["id"], "tower": tower["id"], "target": target["id"], "band": band,
                            "freq": band_freq(proj, band), "antennas": [{"h": a["h"], "el": A.el_of(a)[band], "desc": A.describe(a)} for a in st],
                            "issues": [], "options": [], "best": None, "hfta_fom": None, "notes": [],
                            "spacing": [w for w in warns if (w["kind"] == "stack" and w["band"] == band) or (w["kind"] == "gap" and hs_band & set(w["heights"]))]}
                    if any(x not in A.TYPE.values() for x in types): cell["issues"].append("HFTA has no antenna type with that element count (use 1-6 or 8). Not evaluated.")
                    elif len(types) > 1: cell["issues"].append("Different antenna types on one band: HFTA needs one type per run. Not evaluated.")
                    if len(st) > 4: cell["issues"].append("More than 4 antennas on one band: HFTA allows at most 4. Not evaluated.")
                    _, why = aoa_status(proj, pslug, target, cell["freq"], aoa_cache)
                    if why: cell["issues"].append(why)
                    if cell["issues"]: cells.append(cell); continue
                    t = types.pop()
                    for opt in switch_options(len(st), tower.get("switching", "stackmatch")):
                        hs = [st[i]["h"] for i in opt]; o = {"use": list(opt), "heights": hs, "az": []}
                        for az, w in target_azimuths(target):
                            k, fname = TR.nearest(idx, az)
                            if (site["id"], fname) not in digests: digests[(site["id"], fname)] = TR.file_digest(sdir, fname)
                            spec = {"site": site["id"], "file": fname, "freq": cell["freq"], "hfta_type": t, "heights_ft": hs,
                                    "phases": [1] * len(hs), "epsr": s["epsr"], "sigma": s["sigma"], "diffraction": s["diffraction"],
                                    "terrain_sha256": digests[(site["id"], fname)], "engine": eng}
                            rid = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:10]
                            runs[rid] = spec
                            o["az"].append({"az": az, "file_az": k, "weight": w, "run": rid})
                        cell["options"].append(o)
                    cell["hfta_type"] = t
                    cells.append(cell)
    return cells, runs, bands_all

MAX_FILLED = 8   # at most 2 degrees of the 140 angles (0.25 deg steps) may be filled

def check_pattern(pat):
    """Policy for invalid values (NaN, infinite) returned by the calculation core.
    A known core fault returns a few NaN angles on some profiles (seen at 19.5-20.5 deg, 28 MHz, one antenna,
    diffraction on). Up to MAX_FILLED isolated angles inside the range are filled by straight-line interpolation
    from their neighbours, and the filled angles are reported with the run. More than that, or an invalid first or
    last angle, makes the run FAILED: it gets no FOM and is never ranked.
    Returns (pattern or None, note) where note is None, {"filled_deg": [...]} or {"failed": "..."}."""
    pat = np.asarray(pat, dtype=float); bad = ~np.isfinite(pat)
    if not bad.any():
        return pat, None
    n = int(bad.sum())
    if n > MAX_FILLED or bad[0] or bad[-1]:
        return None, {"failed": f"The calculation core returned {n} invalid values of {len(pat)} angles"}
    x = np.arange(len(pat)); pat = pat.copy(); pat[bad] = np.interp(x[bad], x[~bad], pat[~bad])
    return pat, {"filled_deg": [float(a) for a in engine.ANGLES[bad]]}

def run_one(args):
    """One HFTA run in a worker process. Returns (run id, pattern list or None, note)."""
    rid, spec, sdir = args
    try:
        d, h = TR.load_profile(Path(sdir), spec["file"])
        raw = engine.pattern(d, h, spec["freq"], spec["heights_ft"], spec["phases"], engine.ANTENNA_TYPES[spec["hfta_type"]],
                             spec["sigma"], spec["epsr"], spec["diffraction"])
    except Exception as e:  # noqa: BLE001
        return rid, None, {"failed": f"Run could not be calculated: {e}"}
    pat, note = check_pattern(raw)
    return rid, (None if pat is None else [round(float(x), 3) for x in pat]), note

def finish(proj, pslug, cells, runs, patterns, notes=None):
    """Compute FOMs from patterns and choose switch settings. A failed run (pattern None) gives no FOM; a switch
    setting with a failed run gets no score (a mean over fewer headings would not be the same quantity)."""
    targets = {t["id"]: t for t in proj["targets"]}
    notes = notes or {}; aoa_cache, fom_log = {}, {}
    for c in cells:
        if c["issues"]: continue
        tg = targets[c["target"]]
        aoa, why = aoa_status(proj, pslug, tg, c["freq"], aoa_cache)
        if why: c["issues"].append(why); c["best"] = None; c["hfta_fom"] = None; continue
        c_notes = set()
        for o in c["options"]:
            failed = False
            for a in o["az"]:
                pat = patterns.get(a["run"])
                nt = notes.get(a["run"]) or {}
                if pat is None:
                    a["fom"] = None; failed = True; c_notes.add(f"Run failed at {a['az']}°: {nt.get('failed', 'no pattern')}")
                    continue
                if nt.get("filled_deg"):
                    a["filled_deg"] = nt["filled_deg"]
                    c_notes.add(f"Run at {a['az']}° ({'/'.join(f'{h:g}' for h in o['heights'])} ft): {len(nt['filled_deg'])} invalid angle(s) "
                                f"from the core filled by interpolation ({nt['filled_deg'][0]:g}–{nt['filled_deg'][-1]:g}°)")
                f = engine.fom(np.array(pat, dtype=np.float32), aoa)
                a["fom"] = None if f is None else round(f, 2)
                fom_log.setdefault(a["run"], {})[f'{tg["prn"]}|{c["band"]}'] = a["fom"]
            good = [a for a in o["az"] if a["fom"] is not None]
            tot_w = sum(a["weight"] for a in good)
            o["score"] = round(sum(a["fom"] * a["weight"] for a in good) / tot_w, 2) if (good and not failed and len(good) == len(o["az"]) and tot_w > 0) else None
        best = max((o for o in c["options"] if o["score"] is not None), key=lambda o: o["score"], default=None)
        c["best"] = c["options"].index(best) if best else None
        c["hfta_fom"] = best["score"] if best else None
        c["notes"] = sorted(c_notes)
        if best is None: c["issues"].append("No result: " + ("; ".join(sorted(c_notes)) or "no switch setting could be scored"))
    return fom_log

def total(cell, layers_on=None):
    """The result of a cell: the HFTA FOM of its best switch setting. (Kept for old callers.)"""
    return cell.get("hfta_fom")
