"""
app.py - Flask web GUI for OpenHFTA terrain analysis, stack evaluation and height optimisation.

Run:  python app.py      (then open http://localhost:5000)
Env:  OPENHFTA_DIR  path to the OpenHFTA checkout (default ../openhfta)
      HFTA_WORKERS  number of calculation processes (default: CPU count)
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
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

WORKERS = int(os.environ.get("HFTA_WORKERS", os.cpu_count() or 1))
POOL = None
JOBS: dict = {}
JOBS_LOCK = threading.Lock()
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
    """Shared settings and paths. Raises ValueError with a user-readable message."""
    units = body.get("units", "ft")
    freq = float(body["freq"])
    ant = body.get("antenna_type", "3-Ele")
    if ant not in engine.ANTENNA_TYPES:
        raise ValueError(f"Unknown antenna type {ant}")
    soil = body.get("soil", "Average soil")
    if soil == "Custom":
        sigma, epsr = float(body["sigma"]), float(body["epsr"])
    else:
        sigma, epsr = engine.SOIL_PRESETS[soil]
    paths = []
    for p in body.get("paths", []):
        if not p.get("profile"):
            continue
        d, h = engine.parse_profile_text(p["profile"])
        aoa = engine.parse_aoa(p["aoa"], freq) if p.get("aoa") else {}
        paths.append({"name": p.get("name") or f"Path {len(paths) + 1}", "dist": d, "hgt": h,
                      "aoa": aoa, "weight": float(p.get("weight", 1.0))})
    if not paths:
        raise ValueError("Load at least one terrain profile")
    return {
        "units": units, "freq": freq, "ant_type": engine.ANTENNA_TYPES[ant], "sigma": sigma,
        "epsr": epsr, "diffraction": bool(body.get("diffraction", True)),
        "move_tower_ft": to_ft(body.get("move_tower", 0) or 0, units), "paths": paths,
    }


def task(c: dict, heights_ft, phases, want_pattern=False) -> dict:
    return {"heights_ft": list(heights_ft), "phases": list(phases), "ant_type": c["ant_type"],
            "freq": c["freq"], "sigma": c["sigma"], "epsr": c["epsr"], "diffraction": c["diffraction"],
            "move_tower_ft": c["move_tower_ft"],
            "paths": [{k: p[k] for k in ("dist", "hgt", "aoa", "weight")} for p in c["paths"]],
            "want_pattern": want_pattern}


def path_info(c: dict) -> list:
    out = []
    for p in c["paths"]:
        u = c["units"]
        out.append({"name": p["name"], "weight": p["weight"],
                    "dist": [from_ft(x, u) for x in p["dist"]], "hgt": [from_ft(x, u) for x in p["hgt"]],
                    "aoa": {str(k): round(v * 100, 2) for k, v in sorted(p["aoa"].items())},
                    "has_aoa": bool(p["aoa"])})
    return out


def err(msg, code=400):
    return jsonify({"error": msg}), code


# --- routes -----------------------------------------------------------------
@app.get("/")
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
    """Run one stack, and optionally every sub-combination of its antennas."""
    try:
        body = request.get_json()
        c = decode_common(body)
        ants = body["antennas"]  # [{height, phase}] bottom to top
        h_ft = [to_ft(a["height"], c["units"]) for a in ants]
        ph = [-1 if a.get("phase") == 180 else 1 for a in ants]
        combos = engine.subsets(len(ants)) if body.get("combinations") and len(ants) > 1 \
            else [tuple(range(len(ants)))]
    except (KeyError, ValueError, TypeError) as e:
        return err(str(e))

    futs = {pool().submit(engine.evaluate, task(c, [h_ft[i] for i in cb], [ph[i] for i in cb], True)): cb
            for cb in combos}
    rows = []
    for f in as_completed(futs):
        cb = futs[f]
        r = f.result()
        rows.append({"antennas": [i + 1 for i in cb],
                     "heights": [from_ft(h_ft[i], c["units"]) for i in cb],
                     "foms": r["foms"], "score": r["score"], "patterns": r["patterns"]})
    rows.sort(key=lambda r: (len(r["antennas"]), r["antennas"]))
    return jsonify({"angles": engine.ANGLES.tolist(), "rows": rows, "paths": path_info(c),
                    "warning": engine.frequency_warning(c["freq"]), "units": c["units"]})


@app.post("/api/optimise")
def optimise():
    try:
        body = request.get_json()
        c = decode_common(body)
        if not any(p["aoa"] for p in c["paths"]):
            raise ValueError("The optimiser needs arrival-angle data for at least one path")
        u = c["units"]
        specs = []
        for a in body["antennas"]:  # bottom to top
            if a.get("mode") == "fixed":
                specs.append({"fixed": to_ft(a["height"], u)})
            else:
                specs.append({"min": to_ft(a["min"], u), "max": to_ft(a["max"], u)})
        phases = [-1 if a.get("phase") == 180 else 1 for a in body["antennas"]]
        step = to_ft(body["step"], u)
        spacing = to_ft(body.get("min_spacing", 0) or 0, u)
        if step <= 0:
            raise ValueError("Step must be greater than zero")
        full = engine.height_grid(specs, step, spacing)
        if not full:
            raise ValueError("No height combination satisfies the ranges and minimum spacing")
    except (KeyError, ValueError, TypeError) as e:
        return err(str(e))

    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "state": "running", "phase": "", "done": 0, "total": 0, "started": time.time(),
           "result": None, "error": None, "cancel": False}
    with JOBS_LOCK:
        JOBS[jid] = job
    threading.Thread(target=run_search, args=(job, c, specs, phases, step, spacing, full),
                     daemon=True).start()
    return jsonify({"job": jid, "combinations": len(full)})


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


def run_search(job, c, specs, phases, step, spacing, full):
    try:
        results = {}
        if len(full) <= EVAL_BUDGET:
            for r in run_batch(job, c, full, phases, "Full search"):
                results[tuple(r["heights_ft"])] = r
            coarse_step = None
        else:
            coarse_step = step
            grid = full
            while len(grid) > EVAL_BUDGET:
                coarse_step *= 2
                grid = engine.height_grid(specs, coarse_step, spacing)
            for r in run_batch(job, c, grid, phases, f"Coarse search ({len(grid)} of {len(full)})"):
                results[tuple(r["heights_ft"])] = r
            best = sorted((r for r in results.values() if r["score"] is not None),
                          key=lambda r: -r["score"])[:5]
            fine = [g for g in engine.refine_grid([tuple(r["heights_ft"]) for r in best], specs,
                                                  coarse_step, step, spacing) if g not in results]
            for r in run_batch(job, c, fine, phases, f"Fine search ({len(fine)})"):
                results[tuple(r["heights_ft"])] = r

        ranked = sorted((r for r in results.values() if r["score"] is not None), key=lambda r: -r["score"])
        if not ranked:
            raise RuntimeError("No FOM could be computed (check arrival-angle data and frequency)")

        # best configuration: full pattern + each antenna alone, for the report
        best_h = ranked[0]["heights_ft"]
        detail = []
        for cb in engine.subsets(len(best_h)):
            r = engine.evaluate(task(c, [best_h[i] for i in cb], [phases[i] for i in cb], True))
            detail.append({"antennas": [i + 1 for i in cb], "heights": [from_ft(best_h[i], c["units"]) for i in cb],
                           "foms": r["foms"], "score": r["score"], "patterns": r["patterns"]})
        detail.sort(key=lambda r: (len(r["antennas"]), r["antennas"]))

        u = c["units"]
        top = [{"heights": [from_ft(h, u) for h in r["heights_ft"]], "foms": r["foms"], "score": r["score"]}
               for r in ranked[:15]]

        # map of score over the two varying heights (only when exactly two vary)
        var = [i for i, s in enumerate(specs) if "fixed" not in s]
        fmap = None
        if len(var) == 2:
            i, j = var
            fmap = {"x_label": f"Antenna {i + 1}", "y_label": f"Antenna {j + 1}",
                    "points": [[from_ft(r["heights_ft"][i], u), from_ft(r["heights_ft"][j], u), round(r["score"], 2)]
                               for r in ranked]}
        elif len(var) == 1:
            i = var[0]
            fmap = {"x_label": f"Antenna {i + 1}", "line": sorted(
                [[from_ft(r["heights_ft"][i], u), round(r["score"], 2)] for r in ranked])}

        # how flat the optimum is: range of heights within 0.5 dB of the best
        tol = [r for r in ranked if r["score"] >= ranked[0]["score"] - 0.5]
        flat = [{"antenna": k + 1, "min": from_ft(min(r["heights_ft"][k] for r in tol), u),
                 "max": from_ft(max(r["heights_ft"][k] for r in tol), u)} for k in range(len(specs))]

        job["result"] = {"top": top, "detail": detail, "map": fmap, "within_half_db": flat,
                         "evaluated": len(results), "full_grid": len(full),
                         "coarse_step": from_ft(coarse_step, u) if coarse_step else None,
                         "angles": engine.ANGLES.tolist(), "paths": path_info(c),
                         "warning": engine.frequency_warning(c["freq"]), "units": u,
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
