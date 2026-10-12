"""
app.py - Flask web GUI for OpenHFTA terrain analysis, stack evaluation and height optimisation.

Run:  python app.py      (then open http://localhost:5000)
Env:  OPENHFTA_DIR  path to the OpenHFTA checkout (default ../openhfta)
      HFTA_WORKERS  number of calculation processes (default: CPU count)
      PROJECTS_DIR  where projects are stored (default ./projects; on a host, a persistent volume)
      APP_PASSWORD  if set, the browser asks for it (any user name). Use it when the app is on the internet.

Model of a request
  bands : one or more bands analysed with the SAME physical heights (single-band or tribander).
          Each band has its own frequency, element count (antenna type), boom length and weight.
  paths : one or more azimuths. Each path = terrain profile + ARRL .PRN file (all bands) + weight.
  Score : FOM per band = path-weighted mean; overall = band-weighted mean of band FOMs.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed

from flask import Flask, jsonify, render_template, request

import engine

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# A hosted copy must have a password. Railway sets RAILWAY_ENVIRONMENT; HOSTED=1 marks any other server.
if (os.environ.get("HOSTED") == "1" or os.environ.get("RAILWAY_ENVIRONMENT")) and not APP_PASSWORD:
    raise SystemExit("Hosted copy without APP_PASSWORD: set APP_PASSWORD (or unset HOSTED) and start again.")


@app.before_request
def _same_origin():
    """Refuse requests that change data when they come from another web site (a page open in the same browser).
    Browsers send Sec-Fetch-Site and Origin; tools such as curl send neither and are not affected."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return ("Request from another web site refused", 403)
    origin = request.headers.get("Origin")
    if origin and origin != "null":
        from urllib.parse import urlparse
        if urlparse(origin).netloc != request.host:
            return ("Request from another web site refused", 403)
    return None


@app.before_request
def _password():
    """Simple protection for a hosted copy: HTTP basic authentication, password from APP_PASSWORD."""
    if not APP_PASSWORD or request.path == "/healthz":
        return None
    import hmac
    a = request.authorization
    if a and a.password and hmac.compare_digest(a.password, APP_PASSWORD):
        return None
    return ("Password required", 401, {"WWW-Authenticate": 'Basic realm="HFTA Stack Planner"'})


@app.after_request
def _headers(resp):
    """Browser rules: scripts and styles only from this server (Plotly is served from /static), no framing by other
    sites, no content-type guessing. Inline styles are allowed (the pages set widths and colours inline)."""
    resp.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


@app.get("/healthz")
def _healthz():
    return "ok"

WORKERS = int(os.environ.get("HFTA_WORKERS", os.cpu_count() or 1))
POOL = None
JOBS: dict = {}
EVAL_BUDGET = 500  # max combinations in one search pass before coarse-to-fine is used


def pool() -> ProcessPoolExecutor:
    global POOL
    if POOL is None:
        POOL = ProcessPoolExecutor(max_workers=WORKERS)
    return POOL


# --- request decoding -------------------------------------------------------
def to_ft(v, units):
    return float(v) * (engine.M_TO_FT if units == "m" else 1.0)


def from_ft(v, units):
    return round(v / engine.M_TO_FT, 2) if units == "m" else round(v, 1)


def decode_common(body: dict) -> dict:
    """Shared settings, bands and paths. Raises ValueError with a user-readable message."""
    units = body.get("units", "ft")
    soil = body.get("soil", "Average soil")
    if soil == "Custom":
        sigma, epsr = float(body["sigma"]), float(body["epsr"])
    else:
        sigma, epsr = engine.SOIL_PRESETS[soil]

    raw_paths = [p for p in body.get("paths", []) if p.get("profile")]
    if not raw_paths:
        raise ValueError("Load at least one terrain profile")
    paths = []
    for i, p in enumerate(raw_paths):
        d, h = engine.parse_profile_text(p["profile"])
        paths.append({"name": p.get("name") or f"Path {i + 1}", "dist": d, "hgt": h,
                      "weight": float(p.get("weight", 1.0)), "aoa_text": p.get("aoa", "")})

    bands = []
    for b in body.get("bands", []):
        if not b.get("enabled", True):
            continue
        freq = float(b["freq"])
        ant = b.get("antenna_type", "3-Ele")
        if ant not in engine.ANTENNA_TYPES:
            raise ValueError(f"Unknown antenna type {ant}")
        aoa = [engine.parse_aoa(p["aoa_text"], freq) if p["aoa_text"] else {} for p in paths]
        bands.append({"name": b.get("name") or engine.hfta.frequency_to_band(freq) or f"{freq} MHz",
                      "freq": freq, "ant_type": engine.ANTENNA_TYPES[ant], "ant_label": ant,
                      "boom_ft": to_ft(b["boom"], units) if b.get("boom") else None,
                      "weight": float(b.get("weight", 1.0)), "aoa": aoa})
    if not bands:
        raise ValueError("Enable at least one band")

    lam_max = max(engine.wavelength_ft(b["freq"]) for b in bands)  # lowest band sets spacing rules
    min_sp_lambda = float(body.get("min_spacing_lambda", 0.5) or 0)
    return {
        "units": units, "sigma": sigma, "epsr": epsr,
        "diffraction": bool(body.get("diffraction", True)),
        "move_tower_ft": to_ft(body.get("move_tower", 0) or 0, units),
        "max_tower_ft": to_ft(body["max_tower"], units) if body.get("max_tower") else None,
        "min_spacing_lambda": min_sp_lambda, "min_spacing_ft": min_sp_lambda * lam_max,
        "paths": paths, "bands": bands,
    }


def task(c: dict, heights_ft, phases, want_pattern=False) -> dict:
    return {"heights_ft": list(heights_ft), "phases": list(phases),
            "sigma": c["sigma"], "epsr": c["epsr"], "diffraction": c["diffraction"],
            "move_tower_ft": c["move_tower_ft"],
            "paths": [{k: p[k] for k in ("dist", "hgt", "weight")} for p in c["paths"]],
            "bands": [{k: b[k] for k in ("freq", "ant_type", "weight", "aoa")} for b in c["bands"]],
            "want_pattern": want_pattern}


def meta(c: dict) -> dict:
    """Description of paths and bands for the browser."""
    u = c["units"]
    paths = [{"name": p["name"], "weight": p["weight"],
              "dist": [from_ft(x, u) for x in p["dist"]], "hgt": [from_ft(x, u) for x in p["hgt"]]}
             for p in c["paths"]]
    bands = []
    for b in c["bands"]:
        bands.append({"name": b["name"], "freq": b["freq"], "antenna": b["ant_label"], "weight": b["weight"],
                      "boom": from_ft(b["boom_ft"], u) if b["boom_ft"] else None,
                      "lambda": from_ft(engine.wavelength_ft(b["freq"]), u),
                      "aoa": [{str(k): round(v * 100, 2) for k, v in sorted(a.items())} for a in b["aoa"]],
                      "has_aoa": [bool(a) for a in b["aoa"]],
                      "warning": engine.frequency_warning(b["freq"])})
    return {"paths": paths, "bands": bands, "units": u, "angles": engine.ANGLES.tolist(),
            "min_spacing": from_ft(c["min_spacing_ft"], u), "min_spacing_lambda": c["min_spacing_lambda"],
            "max_tower": from_ft(c["max_tower_ft"], u) if c["max_tower_ft"] else None}


def geometry_warnings(c: dict, heights_ft) -> list:
    out, u = [], c["units"]
    lab = "m" if u == "m" else "ft"
    for i in range(len(heights_ft) - 1):
        sp = heights_ft[i + 1] - heights_ft[i]
        if sp < c["min_spacing_ft"] - 1e-6:
            out.append(f"Antennas {i + 1}-{i + 2}: spacing {from_ft(sp, u)} {lab} is below the minimum "
                       f"{from_ft(c['min_spacing_ft'], u)} {lab} ({c['min_spacing_lambda']} λ on the lowest band). "
                       "Coupling between antennas is not modelled.")
        if sp <= 0:
            out.append("Antenna heights must increase from antenna 1 (lowest) upward.")
    if c["max_tower_ft"] and heights_ft and max(heights_ft) > c["max_tower_ft"] + 1e-6:
        out.append(f"Top antenna is above the maximum tower height ({from_ft(c['max_tower_ft'], u)} {lab}).")
    return out


def detail_rows(c: dict, heights_ft, phases) -> list:
    """Every antenna sub-group of one stack, with patterns, for all bands and paths."""
    combos = engine.subsets(len(heights_ft))
    futs = {pool().submit(engine.evaluate, task(c, [heights_ft[i] for i in cb], [phases[i] for i in cb], True)): cb
            for cb in combos}
    rows = []
    for f in as_completed(futs):
        cb, r = futs[f], f.result()
        rows.append({"antennas": [i + 1 for i in cb], "heights": [from_ft(heights_ft[i], c["units"]) for i in cb],
                     "band_foms": r["band_foms"], "band_scores": r["band_scores"], "score": r["score"],
                     "patterns": r["patterns"]})
    rows.sort(key=lambda r: (len(r["antennas"]), r["antennas"]))
    return rows


def err(msg, code=400):
    return jsonify({"error": msg}), code


# --- routes -----------------------------------------------------------------
@app.get("/classic")
def index():
    return render_template("index.html", antenna_types=list(engine.ANTENNA_TYPES),
                           soils=list(engine.SOIL_PRESETS))


@app.post("/api/prn-bands")
def prn_bands():
    try:
        return jsonify({"bands": engine.prn_bands(request.get_json()["text"])})
    except Exception as e:  # noqa: BLE001
        return err(str(e))


@app.post("/api/analyse")
def analyse():
    """Run one stack and every sub-group of its antennas, on every band."""
    try:
        body = request.get_json()
        c = decode_common(body)
        ants = body["antennas"]  # bottom to top
        h_ft = [to_ft(a["height"], c["units"]) for a in ants]
        ph = [-1 if int(a.get("phase", 0)) == 180 else 1 for a in ants]
    except (KeyError, ValueError, TypeError) as e:
        return err(str(e))
    return jsonify({**meta(c), "rows": detail_rows(c, h_ft, ph),
                    "geometry": geometry_warnings(c, h_ft)})


@app.post("/api/optimise")
def optimise():
    try:
        body = request.get_json()
        c = decode_common(body)
        if not any(any(b["aoa"]) for b in c["bands"]):
            raise ValueError("The optimiser needs arrival-angle data for at least one band and path")
        u = c["units"]
        mode = body.get("mode", "free")  # free | equal | both
        ants = body["antennas"]
        phases = [-1 if int(a.get("phase", 0)) == 180 else 1 for a in ants]
        step = to_ft(body["step"], u)
        if step <= 0:
            raise ValueError("Step must be greater than zero")
        specs = [{"fixed": to_ft(a["height"], u)} if not a.get("vary") else
                 {"min": to_ft(a["min"], u), "max": to_ft(a["max"], u)} for a in ants]
        bottom = (to_ft(ants[0]["min"], u), to_ft(ants[0]["max"], u))
        spacing = (to_ft(body.get("spacing_min", 0) or 0, u), to_ft(body.get("spacing_max", 0) or 0, u))
        if mode in ("equal", "both") and len(ants) > 1 and spacing[1] <= 0:
            raise ValueError("Set the spacing range for the equal-spacing search")
        grids = {}
        if mode in ("free", "both"):
            grids["free"] = engine.height_grid(specs, step, c["min_spacing_ft"], c["max_tower_ft"])
        if mode in ("equal", "both"):
            grids["equal"] = engine.equal_grid(len(ants), bottom, spacing, step, c["min_spacing_ft"], c["max_tower_ft"])
        for k, g in grids.items():
            if not g:
                raise ValueError(f"No height combination satisfies the {k} search ranges, minimum spacing "
                                 "and maximum tower height")
    except (KeyError, ValueError, TypeError) as e:
        return err(str(e))

    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "state": "running", "phase": "", "done": 0, "total": 0, "started": time.time(),
           "result": None, "error": None, "cancel": False}
    JOBS[jid] = job
    args = dict(specs=specs, phases=phases, step=step, bottom=bottom, spacing=spacing)
    threading.Thread(target=run_search, args=(job, c, grids, args), daemon=True).start()
    return jsonify({"job": jid, "combinations": {k: len(v) for k, v in grids.items()}})


def run_batch(job, c, grid, phases, label):
    job.update(phase=label, done=0, total=len(grid))
    futs = [pool().submit(engine.evaluate, task(c, g, phases)) for g in grid]
    out = []
    for f in as_completed(futs):
        if job["cancel"]:
            for x in futs:
                x.cancel()
            raise RuntimeError("Cancelled")
        out.append(f.result())
        job["done"] += 1
    return out


def search(job, c, kind, full, a) -> dict:
    """One search (free or equal). Coarse-to-fine when the grid is larger than EVAL_BUDGET."""
    results, coarse = {}, None
    name = "Free spacing" if kind == "free" else "Equal spacing"
    if len(full) <= EVAL_BUDGET:
        grid = full
    else:
        coarse = a["step"]
        grid = full
        while len(grid) > EVAL_BUDGET:
            coarse *= 2
            grid = (engine.height_grid(a["specs"], coarse, c["min_spacing_ft"], c["max_tower_ft"]) if kind == "free"
                    else engine.equal_grid(len(a["phases"]), a["bottom"], a["spacing"], coarse,
                                           c["min_spacing_ft"], c["max_tower_ft"]))
    label = f"{name}: {'coarse ' if coarse else ''}search"
    for r in run_batch(job, c, grid, a["phases"], label):
        results[tuple(r["heights_ft"])] = r
    if coarse:
        best = sorted((r for r in results.values() if r["score"] is not None), key=lambda r: -r["score"])[:5]
        centres = [tuple(r["heights_ft"]) for r in best]
        fine = (engine.refine_grid(centres, a["specs"], coarse, a["step"], c["min_spacing_ft"], c["max_tower_ft"])
                if kind == "free" else
                engine.refine_equal(centres, a["bottom"], a["spacing"], coarse, a["step"],
                                    c["min_spacing_ft"], c["max_tower_ft"]))
        fine = [g for g in fine if g not in results]
        for r in run_batch(job, c, fine, a["phases"], f"{name}: fine search"):
            results[tuple(r["heights_ft"])] = r
    u = c["units"]
    rows = [{"h": [from_ft(x, u) for x in r["heights_ft"]],
             "b": [None if s is None else round(s, 3) for s in r["band_scores"]],
             "p": [[None if f is None else round(f, 3) for f in fl] for fl in r["band_foms"]]}
            for r in results.values() if r["score"] is not None]
    if not rows:
        raise RuntimeError("No FOM could be computed (check arrival-angle data and frequency)")
    return {"kind": kind, "rows": rows, "evaluated": len(results), "full_grid": len(full),
            "coarse_step": from_ft(coarse, u) if coarse else None}


def run_search(job, c, grids, a):
    try:
        searches = [search(job, c, k, g, a) for k, g in grids.items()]
        # detail (all sub-groups, all bands, patterns) for the best overall result at default weights
        bw = [b["weight"] for b in c["bands"]]
        allrows = [r for s in searches for r in s["rows"]]
        best = max(allrows, key=lambda r: engine.weighted_score(r["b"], bw) or -1e9)
        job.update(phase="Patterns for the best result", done=0, total=0)
        best_ft = [to_ft(h, c["units"]) for h in best["h"]]
        job["result"] = {**meta(c), "searches": searches, "phases": a["phases"],
                         "varying": [i for i, s in enumerate(a["specs"]) if "fixed" not in s],
                         "rows": detail_rows(c, best_ft, a["phases"]),
                         "geometry": geometry_warnings(c, best_ft),
                         "seconds": round(time.time() - job["started"], 1)}
        job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)


@app.get("/api/job/<jid>")
def job_status(jid):
    job = JOBS.get(jid)
    if not job:
        return err("Unknown job", 404)
    return jsonify({k: job[k] for k in ("state", "phase", "done", "total", "result", "error")})


@app.post("/api/job/<jid>/cancel")
def job_cancel(jid):
    job = JOBS.get(jid)
    if job:
        job["cancel"] = True
    return jsonify({"ok": True})


import v2  # noqa: E402
v2.CTX.update(pool=pool, jobs=JOBS)
app.register_blueprint(v2.bp)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024   # DEM files can be large; the app runs locally

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
