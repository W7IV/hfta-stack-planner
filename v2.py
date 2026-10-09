"""HFTA Stack Planner v2: five-step workflow (Sites, Targets, Towers, Compare, Report). Runs locally."""
from __future__ import annotations
import io, json, threading, time, uuid
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, render_template
import engine
from core import antennas as A, project as P, terrain as TR, evaluate as EV, exports as EX, guys as G, report as RP, compromise as CM, spacing as SP

bp = Blueprint("v2", __name__)
CTX = {}   # set by app.py: pool(), JOBS

def err(msg, code=400): return jsonify({"error": msg}), code
def layers(proj): return {}   # no layers beyond HFTA in this version
def results_path(slug): return P.path(slug) / "results.json"
def load_results(slug):
    p = results_path(slug); return json.loads(p.read_text()) if p.exists() else None

@bp.get("/")
def index():
    return render_template("v2.html")

@bp.get("/api/v2/meta")
def meta():
    return jsonify({"elements": A.ELEMENTS, "types": {str(k): v for k, v in A.TYPE.items()}, "spacing_defaults": P.SPACING_DEFAULTS, "bands": A.BANDS, "band_freq": A.BAND_FREQ, "soils": P.SOILS,
                    "wires": {k: {"lb_ft": v[0], "dia_in": v[1], "tension": v[2]} for k, v in G.WIRES.items()},
                    "projects": P.list_projects()})

@bp.post("/api/v2/projects")
def create():
    name = (request.get_json() or {}).get("name", "").strip() or "New project"
    slug = P.slug(name); n = 2
    while (P.path(slug) / "project.json").exists():
        slug = f"{P.slug(name)}-{n}"; n += 1
    P.save(slug, P.default_project(name)); return jsonify({"slug": slug})

# ------------------------------------------------------------ project with all its files (move between computers)
@bp.post("/api/v2/projects/import")
def import_project():
    """Zip made by export/bundle: project.json, sites/<site id>/*.PRO, prn/*.PRN (results are recomputed)."""
    import zipfile, re
    f = request.files.get("file")
    if not f: return err("No file")
    try: z = zipfile.ZipFile(f.stream)
    except zipfile.BadZipFile: return err("Not a zip file")
    names = [n for n in z.namelist() if not n.endswith("/")]
    pj = next((n for n in names if n.split("/")[-1] == "project.json"), None)
    if not pj: return err("project.json not found in the zip")
    root = pj[: -len("project.json")]
    proj = P.upgrade(json.loads(z.read(pj)))
    base = P.slug(proj.get("name") or "Imported"); slug = base; n = 2
    while (P.path(slug) / "project.json").exists(): slug = f"{base}-{n}"; n += 1
    site_ids = {s["id"] for s in proj.get("sites", [])}
    for n_ in names:
        rel = n_[len(root):] if n_.startswith(root) else None
        if not rel: continue
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "sites" and parts[1] in site_ids and re.fullmatch(r"[\w.\- ]+\.pro", parts[2], re.I):
            d = P.site_dir(slug, parts[1]); d.mkdir(parents=True, exist_ok=True); (d / parts[2]).write_bytes(z.read(n_))
        elif len(parts) == 2 and parts[0] == "prn" and re.fullmatch(r"[\w.\- ]+\.prn", parts[1], re.I):
            d = P.prn_dir(slug); d.mkdir(parents=True, exist_ok=True); (d / parts[1]).write_bytes(z.read(n_))
    P.save(slug, proj)
    return jsonify({"slug": slug})

def bundle(slug) -> bytes:
    import zipfile
    proj = P.load(slug); b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(proj, indent=1))
        for s in proj["sites"]:
            d = P.site_dir(slug, s["id"])
            if d.exists():
                for f in sorted(d.iterdir()):
                    if f.is_file(): z.write(f, f"sites/{s['id']}/{f.name}")
        if P.prn_dir(slug).exists():
            for f in sorted(P.prn_dir(slug).iterdir()):
                if f.is_file(): z.write(f, f"prn/{f.name}")
    return b.getvalue()

def state(slug):
    proj = P.load(slug)
    sites = {}
    for s in proj["sites"]:
        idx = TR.profile_index(P.site_dir(slug, s["id"]))
        sites[s["id"]] = {"n": len(idx), "step": _step(sorted(idx))}
    prns = sorted(p.name for p in P.prn_dir(slug).glob("*")) if P.prn_dir(slug).exists() else []
    res = load_results(slug)
    return {"slug": slug, "project": proj, "site_files": sites, "prns": prns, "has_results": res is not None,
            "results_stamp": res.get("stamp") if res else None}

def _step(azs):
    if len(azs) < 2: return None
    d = [round(b - a, 3) for a, b in zip(azs, azs[1:])]; return min(d)

@bp.get("/api/v2/p/<slug>")
def get_project(slug):
    if not (P.path(slug) / "project.json").exists(): return err("Project not found", 404)
    return jsonify(state(slug))

@bp.put("/api/v2/p/<slug>")
def put_project(slug):
    proj = request.get_json()
    for s in proj.get("sites", []): s.setdefault("id", P.new_id("s"))
    for t in proj.get("targets", []): t.setdefault("id", P.new_id("t"))
    for t in proj.get("towers", []): t.setdefault("id", P.new_id("w"))
    P.save(slug, P.upgrade(proj)); return jsonify(state(slug))

@bp.post("/api/v2/p/<slug>/sites/<sid>/import")
def site_import(slug, sid):
    files = [(f.filename, f.read()) for f in request.files.getlist("files")]
    r = TR.import_files(P.site_dir(slug, sid), files); return jsonify(r)

@bp.post("/api/v2/p/<slug>/sites/<sid>/flat")
def site_flat(slug, sid):
    TR.write_flat(P.site_dir(slug, sid)); return jsonify({"ok": True})

@bp.post("/api/v2/p/<slug>/sites/<sid>/dem")
def site_dem(slug, sid):
    f = request.files.get("dem")
    if not f: return err("Choose a DEM file (GeoTIFF .tif or ESRI ASCII grid .asc).")
    tmp = P.path(slug) / "dem"; tmp.mkdir(exist_ok=True); fp = tmp / Path(f.filename).name; f.save(fp)
    fm = request.form
    try:
        dem = TR.DEM(fp, crs=fm.get("crs") or None, z_units=fm.get("z_units", "m"))
        out = TR.generate_from_dem(dem, float(fm["lat"]), float(fm["lon"]), P.site_dir(slug, sid), P.slug(fm.get("prefix") or "SITE"),
                                   float(fm.get("az_step", 1)), float(fm.get("spacing_m", 30)), float(fm.get("length_m", 4410)))
    except Exception as e:  # noqa: BLE001
        return err(f"DEM: {e}")
    return jsonify(out)

@bp.delete("/api/v2/p/<slug>/sites/<sid>/files")
def site_clear(slug, sid):
    d = P.site_dir(slug, sid)
    for p in d.glob("*"):
        if p.suffix.lower() == ".pro": p.unlink()
    return jsonify({"ok": True})

@bp.get("/api/v2/p/<slug>/sites/<sid>/summary")
def site_summary(slug, sid):
    return jsonify(TR.summary(P.site_dir(slug, sid), int(request.args.get("step", 5))))

@bp.get("/api/v2/p/<slug>/sites/<sid>/profile")
def site_profile(slug, sid):
    idx = TR.profile_index(P.site_dir(slug, sid)); k, name = TR.nearest(idx, float(request.args.get("az", 0)))
    if not name: return err("No profiles")
    d, h = TR.load_profile(P.site_dir(slug, sid), name)
    return jsonify({"az": k, "file": name, "d_ft": d, "h_ft": h})

@bp.post("/api/v2/p/<slug>/prn")
def prn_upload(slug):
    out = []; P.prn_dir(slug).mkdir(parents=True, exist_ok=True)
    for f in request.files.getlist("files"):
        data = f.read(); txt = data.decode("latin-1")
        try:
            bands = engine.prn_bands(txt)
        except Exception as e:  # noqa: BLE001
            out.append({"file": f.filename, "error": str(e)}); continue
        (P.prn_dir(slug) / Path(f.filename).name).write_bytes(data); out.append({"file": f.filename, "bands": bands})
    return jsonify(out)

@bp.get("/api/v2/p/<slug>/prn/<name>")
def prn_get(slug, name):
    txt = (P.prn_dir(slug) / name).read_text(errors="ignore"); lines = txt.strip().splitlines()
    cols = lines[1].split(); rows = []
    for ln in lines[2:]:
        p = ln.split()
        if len(p) == len(cols):
            try: rows.append([float(x) for x in p])
            except ValueError: pass
    return jsonify({"title": lines[0].strip(), "columns": cols, "rows": rows})

# ------------------------------------------------------------ evaluation
def _run_eval(job, slug):
    try:
        proj = P.load(slug); cells, runs, _ = EV.plan(proj, slug)
        old = load_results(slug) or {}; pats = {k: v for k, v in old.get("patterns", {}).items() if k in runs and all(x == x for x in v)}
        todo = [(rid, spec, str(P.site_dir(slug, spec["site"]))) for rid, spec in runs.items() if rid not in pats]
        job.update(phase="HFTA runs", done=0, total=len(todo))
        for rid, pat in CTX["pool"]().map(EV.run_one, todo, chunksize=4):
            pats[rid] = pat; job["done"] += 1
            if job["cancel"]: raise RuntimeError("Cancelled")
        fom_log = EV.finish(proj, slug, cells, runs, pats)
        res = {"stamp": time.strftime("%Y-%m-%d %H:%M:%S"), "cells": cells, "runs": runs, "patterns": pats, "fom_log": fom_log,
               "n_runs": len(runs), "reused": len(runs) - len(todo)}
        results_path(slug).write_text(json.dumps(res))
        job["result"] = {"cells": len(cells), "runs": len(runs), "reused": res["reused"]}; job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/evaluate")
def evaluate(slug):
    jid = uuid.uuid4().hex[:8]
    job = {"state": "running", "phase": "Planning", "done": 0, "total": 0, "result": None, "error": None, "cancel": False, "started": time.time()}
    CTX["jobs"][jid] = job; threading.Thread(target=_run_eval, args=(job, slug), daemon=True).start()
    return jsonify({"job": jid})

@bp.get("/api/v2/p/<slug>/results")
def results(slug):
    res = load_results(slug)
    if not res: return jsonify({"cells": []})
    proj = P.load(slug); on = layers(proj)
    slim = []
    for i, c in enumerate(res["cells"]):
        best = c["options"][c["best"]] if c.get("best") is not None else None
        slim.append({"i": i, "site": c["site"], "tower": c["tower"], "target": c["target"], "band": c["band"], "freq": c["freq"],
                     "hfta": c.get("hfta_fom"), "spacing": SP.worst(c.get("spacing", [])), "spacing_text": [w["text"] for w in c.get("spacing", [])],
                     "use": best["heights"] if best else None, "n_options": len(c["options"]), "issues": c["issues"]})
    return jsonify({"stamp": res["stamp"], "cells": slim, "n_runs": res["n_runs"]})

@bp.get("/api/v2/p/<slug>/cell/<int:i>")
def cell(slug, i):
    res = load_results(slug); c = res["cells"][i]; proj = P.load(slug)
    tg = next(t for t in proj["targets"] if t["id"] == c["target"])
    aoa = engine.parse_aoa((P.prn_dir(slug) / tg["prn"]).read_text(errors="ignore"), c["freq"])
    runs = {a["run"]: {**res["runs"][a["run"]], "fom": a.get("fom")} for o in c["options"] for a in o["az"]}
    best = c["options"][c["best"]] if c.get("best") is not None else None
    pats = {}
    if best:
        for a in best["az"]: pats[a["run"]] = res["patterns"][a["run"]]
    return jsonify({"cell": c, "runs": runs, "patterns": pats, "aoa": aoa, "prn": tg["prn"], "angles": [float(x) for x in engine.ANGLES]})

# ------------------------------------------------------------ height scan (single antenna, HFTA runs)
def _run_scan(job, slug, body):
    try:
        proj = P.load(slug); s = proj["settings"]; site = body["site"]; tg = next(t for t in proj["targets"] if t["id"] == body["target"])
        band = body["band"]; freq = EV.band_freq(proj, band); t = A.hfta_type(int(body["elements"]))
        idx = TR.profile_index(P.site_dir(slug, site)); hs = [float(x) for x in range(int(body["lo"]), int(body["hi"]) + 1, int(body["step"]))]
        jobs = []
        for h in hs:
            for az, w in EV.target_azimuths(tg):
                k, f = TR.nearest(idx, az)
                spec = {"site": site, "file": f, "freq": freq, "hfta_type": t, "heights_ft": [h], "phases": [1], "epsr": s["epsr"], "sigma": s["sigma"], "diffraction": s["diffraction"]}
                jobs.append((f"{h}|{az}", spec, str(P.site_dir(slug, site))))
        job.update(phase="Height scan", done=0, total=len(jobs)); pats = {}
        for rid, pat in CTX["pool"]().map(EV.run_one, jobs, chunksize=4):
            pats[rid] = pat; job["done"] += 1
        aoa = engine.parse_aoa((P.prn_dir(slug) / tg["prn"]).read_text(errors="ignore"), freq)
        rows = []
        for h in hs:
            num = den = 0.0
            for az, w in EV.target_azimuths(tg):
                import numpy as np
                f = engine.fom(np.array(pats[f"{h}|{az}"], dtype="float32"), aoa)
                if f is not None: num += w * f; den += w
            rows.append({"h": h, "fom": round(num / den, 2) if den else None})
        job["result"] = {"rows": rows, "type": t, "freq": freq}; job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/scan")
def scan(slug):
    jid = uuid.uuid4().hex[:8]
    job = {"state": "running", "phase": "Planning", "done": 0, "total": 0, "result": None, "error": None, "cancel": False, "started": time.time()}
    CTX["jobs"][jid] = job; threading.Thread(target=_run_scan, args=(job, slug, request.get_json()), daemon=True).start()
    return jsonify({"job": jid})

# ------------------------------------------------------------ one-tower compromise
def _run_comp(job, slug, body):
    try:
        proj = P.load(slug); r = CM.search(proj, slug, body, CTX["pool"](), job)
        r["request"] = body; r["stamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        (P.path(slug) / "compromise.json").write_text(json.dumps(r)); job["result"] = r; job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/compromise")
def compromise(slug):
    jid = uuid.uuid4().hex[:8]
    job = {"state": "running", "phase": "Planning", "done": 0, "total": 0, "result": None, "error": None, "cancel": False, "started": time.time()}
    CTX["jobs"][jid] = job; threading.Thread(target=_run_comp, args=(job, slug, request.get_json()), daemon=True).start()
    return jsonify({"job": jid})

@bp.get("/api/v2/p/<slug>/compromise")
def compromise_last(slug):
    p = P.path(slug) / "compromise.json"
    return jsonify(json.loads(p.read_text()) if p.exists() else {})

# ------------------------------------------------------------ guys
def guy_rows(proj, tower):
    ants = []
    for a in tower["antennas"]:
        ants.append({"name": A.describe(a), "h": a["h"], "turning_radius": a.get("turning_radius") or None, "droop": a.get("droop") or 0.0})
    g = tower.get("guys") or {}
    return G.check(ants, g.get("levels", []), float(g.get("ice_in", 1.0)), float(g.get("margin_ft", 2.0)), float(g.get("density", 56)))

@bp.get("/api/v2/p/<slug>/guys/<tid>")
def guys(slug, tid):
    proj = P.load(slug); tw = next(t for t in proj["towers"] if t["id"] == tid)
    rows = guy_rows(proj, tw); bare = guy_rows(proj, {**tw, "guys": {**(tw.get("guys") or {}), "ice_in": 0}})
    for r, b in zip(rows, bare): r["clearance_bare"] = b["clearance"]
    return jsonify({"rows": rows})

# ------------------------------------------------------------ exports
@bp.get("/api/v2/p/<slug>/export/<kind>")
def export(slug, kind):
    proj = P.load(slug); res = load_results(slug); on = layers(proj); base = P.slug(proj["name"])
    if kind == "project":
        return send_file(io.BytesIO(json.dumps(proj, indent=1).encode()), as_attachment=True, download_name=f"{base}.hfta-project.json")
    if kind == "bundle":
        return send_file(io.BytesIO(bundle(slug)), as_attachment=True, download_name=f"{base}.hfta-project.zip")
    if not res: return err("Run the evaluation first (step 4).")
    gr = {t["name"]: guy_rows(proj, t) for t in proj["towers"] if (t.get("guys") or {}).get("levels")}
    if kind == "xlsx":
        return send_file(io.BytesIO(EX.workbook(proj, slug, res, on, gr)), as_attachment=True, download_name=f"{base}.xlsx")
    if kind == "csv":
        return send_file(io.BytesIO(EX.results_csv(proj, res, on).encode()), as_attachment=True, download_name=f"{base}-results.csv")
    if kind == "replay":
        return send_file(io.BytesIO(EX.replay_pack(proj, slug, res, on)), as_attachment=True, download_name=f"{base}-HFTA-replay.zip")
    if kind == "html":
        return send_file(io.BytesIO(RP.html_report(proj, slug, res, on, gr).encode()), as_attachment=True, download_name=f"{base}-report.html")
    return err("Unknown export")
