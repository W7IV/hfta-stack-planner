"""HFTA Stack Planner v2: five-step workflow (Sites, Targets, Towers, Compare, Report). Runs locally."""
from __future__ import annotations
import io, json, os, threading, time, uuid
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, render_template
import engine
from core import library as LB, antennas as A, project as P, terrain as TR, evaluate as EV, exports as EX, guys as G, report as RP, compromise as CM, spacing as SP, aoa_gen as AG

bp = Blueprint("v2", __name__)
CTX = {}   # set by app.py: pool(), JOBS

def err(msg, code=400): return jsonify({"error": msg}), code

@bp.errorhandler(ValueError)
def _bad_value(e):
    """Invalid ids, file names or numbers (checked in core/project.py) answer 400 with the reason."""
    return err(str(e))
def layers(proj): return {}   # no layers beyond HFTA in this version
def results_path(slug): return P.path(slug) / "results.json"

def new_job() -> tuple:
    """Register a background job. Finished jobs older than one hour are forgotten, so memory stays bounded."""
    now = time.time(); jobs = CTX["jobs"]
    for k in [k for k, j in list(jobs.items()) if j["state"] != "running" and now - j["started"] > 3600]: jobs.pop(k, None)
    if sum(1 for j in jobs.values() if j["state"] == "running") >= 4:
        raise ValueError("Four calculations are already running. Wait for one to finish.")
    jid = uuid.uuid4().hex[:8]
    job = {"state": "running", "phase": "Planning", "done": 0, "total": 0, "result": None, "error": None, "cancel": False, "started": now}
    jobs[jid] = job; return jid, job
def load_results(slug):
    p = results_path(slug); return json.loads(p.read_text()) if p.exists() else None

STARTED = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
_BUILD = None

def build_info() -> dict:
    """Version shown at the bottom of the page: planner commit (Railway gives RAILWAY_GIT_COMMIT_SHA; a local
    checkout asks git), when this server started, and the OpenHFTA engine."""
    global _BUILD
    if _BUILD is None:
        sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("SOURCE_COMMIT") or ""
        if not sha:
            try:
                import subprocess
                sha = subprocess.run(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
            except Exception:  # noqa: BLE001
                sha = ""
        e = engine.engine_info()
        _BUILD = {"planner": sha[:7] or "unknown", "started": STARTED,
                  "engine_commit": str(e.get("commit", "unknown"))[:7], "engine_lib": str(e.get("library_sha256", "unknown"))[:8]}
    return _BUILD

@bp.get("/")
def index():
    # Version stamp from the files' modification time, so browsers fetch new JS/CSS after an update.
    st = Path(__file__).parent / "static"
    v = int(max(p.stat().st_mtime for p in (st / "v2.js", st / "v2.css")))
    return render_template("v2.html", asset_v=v, build=build_info())

@bp.get("/api/v2/meta")
def meta():
    return jsonify({"elements": A.ELEMENTS, "types": {str(k): v for k, v in A.TYPE.items()}, "spacing_defaults": P.SPACING_DEFAULTS, "bands": A.BANDS, "band_freq": A.BAND_FREQ, "soils": P.SOILS,
                    "wires": {k: {"lb_ft": v[0], "dia_in": v[1], "tension": v[2]} for k, v in G.WIRES.items()},
                    "projects": P.list_projects(),
                    "voacap": AG.available(), "regions": {k: v["name"] for k, v in AG.REGIONS.items()}, "ssn_levels": list(AG.SSN_LEVELS.items())})

@bp.post("/api/v2/projects")
def create():
    name = (request.get_json() or {}).get("name", "").strip() or "New project"
    slug = P.slug(name); n = 2
    while P.path(slug).exists():
        slug = f"{P.slug(name)}-{n}"; n += 1
    P.path(slug).mkdir(parents=True)
    P.save(slug, P.default_project(name)); LB.prns_into_project(slug)   # the user's library .PRN files come with every new project
    return jsonify({"slug": slug})

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
    infos = {i.filename: i for i in z.infolist()}
    if len(infos) > 20000 or sum(i.file_size for i in infos.values()) > 500_000_000:
        return err("The zip is too large when unpacked")
    try:
        proj = P.validate(P.upgrade(json.loads(z.read(pj))))     # checked before anything is written
    except (ValueError, json.JSONDecodeError) as e:
        return err(f"project.json: {e}")
    site_ids = {s["id"] for s in proj.get("sites", [])}
    take = []
    for n_ in names:
        rel = n_[len(root):] if n_.startswith(root) else None
        if not rel: continue
        parts = rel.split("/")
        if infos[n_].file_size > 5_000_000: continue
        if len(parts) == 3 and parts[0] == "sites" and parts[1] in site_ids and re.fullmatch(r"[\w.\- ]+\.pro", parts[2], re.I) and ".." not in parts[2]:
            take.append((n_, ("sites", parts[1], parts[2])))
        elif len(parts) == 2 and parts[0] == "prn" and re.fullmatch(r"[\w.\- ]+\.prn", parts[1], re.I) and ".." not in parts[1]:
            take.append((n_, ("prn", parts[1])))
    base = P.slug(proj.get("name") or "Imported"); slug = base; n = 2
    while P.path(slug).exists(): slug = f"{base}-{n}"; n += 1
    P.path(slug).mkdir(parents=True)                               # reserves the name
    for n_, where in take:
        d = P.site_dir(slug, where[1]) if where[0] == "sites" else P.prn_dir(slug)
        d.mkdir(parents=True, exist_ok=True); (d / where[-1]).write_bytes(z.read(n_))
    P.save(slug, proj)
    return jsonify({"slug": slug})

def bundle(slug, include_prn: bool = True) -> bytes:
    """Project with its files. include_prn=True: for moving your own project between your computers (contains your
    .PRN files). False: shareable; the .PRN files are left out and listed in prn-files.txt with their SHA-256."""
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
            lst = []
            for f in sorted(P.prn_dir(slug).iterdir()):
                if not f.is_file(): continue
                if include_prn: z.write(f, f"prn/{f.name}")
                else: lst.append(f"{f.name}  sha256 {EX.sha256_file(f)}")
            if not include_prn:
                z.writestr("prn-files.txt", "Elevation-angle (.PRN) files used by this project, not included (copyright ARRL or the owner).\n"
                           "Add your own copies in step 2 (Targets) after opening the project.\n\n" + "\n".join(lst) + "\n")
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
    if not (P.path(slug) / "project.json").exists(): return err("Project not found", 404)
    proj = P.validate(P.upgrade(request.get_json()))
    P.save(slug, proj); return jsonify(state(slug))

# ------------------------------------------------------------ library shared by all projects
@bp.get("/api/v2/library")
def lib_list():
    return jsonify(LB.listing())

@bp.post("/api/v2/p/<slug>/towers/<tid>/to-library")
def lib_save_tower(slug, tid):
    b = request.get_json() or {}; proj = P.load(slug)
    t = next((x for x in proj["towers"] if x["id"] == tid), None)
    if not t: return err("Tower not found", 404)
    try: e = LB.save_tower(t, b.get("name") or t["name"], bool(b.get("replace")))
    except FileExistsError: return err("exists", 409)
    return jsonify(e)

@bp.post("/api/v2/p/<slug>/sites/<sid>/to-library")
def lib_save_site(slug, sid):
    b = request.get_json() or {}; proj = P.load(slug)
    s = next((x for x in proj["sites"] if x["id"] == sid), None)
    if not s: return err("Site not found", 404)
    try: e = LB.save_site(s, P.site_dir(slug, sid), b.get("name") or s["name"], bool(b.get("replace")))
    except FileExistsError: return err("exists", 409)
    return jsonify(e)

@bp.post("/api/v2/p/<slug>/library/towers/<lid>")
def lib_add_tower(slug, lid):
    proj = P.load(slug)
    try: t = LB.tower_for_project(lid)
    except (KeyError, ValueError): return err("Not in the library", 404)
    names = {x["name"] for x in proj["towers"]}; base = t["name"]; n = 2
    while t["name"] in names: t["name"] = f"{base} ({n})"; n += 1
    t["targets"] = [x["id"] for x in proj["targets"]]
    proj["towers"].append(t); P.save(slug, proj); return jsonify(state(slug))

@bp.post("/api/v2/p/<slug>/library/sites/<lid>")
def lib_add_site(slug, lid):
    proj = P.load(slug)
    try: s = LB.site_into_project(lid, slug)
    except (KeyError, ValueError): return err("Not in the library", 404)
    names = {x["name"] for x in proj["sites"]}; base = s["name"]; n = 2
    while s["name"] in names: s["name"] = f"{base} ({n})"; n += 1
    proj["sites"].append(s); P.save(slug, proj); return jsonify(state(slug))

@bp.post("/api/v2/p/<slug>/prn/to-library")
def lib_save_prns(slug):
    return jsonify({"saved": LB.prns_to_library(P.prn_dir(slug)), "library": LB.list_prns()})

@bp.post("/api/v2/p/<slug>/library/prn")
def lib_add_prns(slug):
    added = LB.prns_into_project(slug); out = state(slug); out["added"] = added; return jsonify(out)

@bp.delete("/api/v2/library/prn/<name>")
def lib_delete_prn(name):
    try: LB.delete_prn(name)
    except ValueError as e: return err(str(e))
    return jsonify(LB.listing())

@bp.delete("/api/v2/library/<kind>/<lid>")
def lib_delete(kind, lid):
    try: (LB.delete_tower if kind == "towers" else LB.delete_site)(lid)
    except ValueError: return err("Bad id")
    return jsonify(LB.listing())

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
    ext = Path(f.filename or "").suffix.lower()
    if ext not in (".tif", ".tiff", ".asc"): return err("Choose a GeoTIFF (.tif) or ESRI ASCII grid (.asc) file.")
    tmp = P.path(slug) / "dem"; tmp.mkdir(exist_ok=True); fp = tmp / f"upload-{uuid.uuid4().hex[:8]}{ext}"; f.save(fp)
    fm = request.form
    try:
        dem = TR.DEM(fp, crs=fm.get("crs") or None, z_units=fm.get("z_units", "m"))
        out = TR.generate_from_dem(dem, float(fm["lat"]), float(fm["lon"]), P.site_dir(slug, sid), P.slug(fm.get("prefix") or "SITE"),
                                   float(fm.get("az_step", 1)), float(fm.get("spacing_m", 30)), float(fm.get("length_m", 4410)))
    except Exception as e:  # noqa: BLE001
        return err(f"DEM: {e}")
    finally:
        fp.unlink(missing_ok=True)
    return jsonify(out)

@bp.post("/api/v2/p/<slug>/sites/<sid>/auto")
def site_auto(slug, sid):
    """Fetch a DEM patch from USGS 3DEP and generate terrain profiles. Body: {lat, lon, prefix?, az_step?, spacing_m?, length_m?}."""
    body = request.get_json() or {}
    lat, lon = body.get("lat"), body.get("lon")
    if lat is None or lon is None:
        return err("lat and lon are required.")
    try:
        out = TR.fetch_dem_and_generate(
            float(lat), float(lon),
            P.site_dir(slug, sid),
            P.slug(body.get("prefix") or "SITE"),
            float(body.get("az_step", 1)),
            float(body.get("spacing_m", 30)),
            float(body.get("length_m", 4410)),
        )
    except Exception as e:  # noqa: BLE001
        return err(f"Auto terrain: {e}")
    return jsonify(out)

@bp.get("/api/v2/p/<slug>/sites/<sid>/download")
def site_download(slug, sid):
    import zipfile
    d = P.site_dir(slug, sid)
    files = sorted(p for p in d.glob("*") if p.suffix.lower() == ".pro")
    if not files:
        return err("No terrain profiles for this site.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
    buf.seek(0)
    proj = P.load(slug)
    site = next((s for s in proj.get("sites", []) if s["id"] == sid), None)
    name = P.slug(site["name"] if site else sid)
    return send_file(buf, as_attachment=True, download_name=f"{name}-terrain.zip")

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
        P.prn_file(slug, Path(f.filename).name).write_bytes(data); out.append({"file": f.filename, "bands": bands})
    return jsonify(out)

@bp.get("/api/v2/p/<slug>/prn/<name>")
def prn_get(slug, name):
    f = P.prn_file(slug, name)
    if not f.exists(): return err("File not found", 404)
    txt = f.read_text(errors="ignore"); lines = txt.strip().splitlines()
    if len(lines) < 2: return err("Not an elevation-angle file")
    cols = lines[1].split(); rows = []
    for ln in lines[2:]:
        p = ln.split()
        if len(p) == len(cols):
            try: rows.append([float(x) for x in p])
            except ValueError: pass
    return jsonify({"title": lines[0].strip(), "columns": cols, "rows": rows})

# ------------------------------------------------------------ VOACAP-generated elevation-angle tables
def _run_prn_gen(job, slug, body):
    try:
        lat, lon = float(body["lat"]), float(body["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("Latitude must be -90..90 and longitude -180..180")
        region = body.get("region")
        if region in AG.REGIONS: reg = AG.REGIONS[region]
        else:
            pts = [(float(a), float(b)) for a, b in (body.get("points") or [])]
            if not pts: raise ValueError("Choose a region or give at least one receive point")
            if len(pts) > 40: raise ValueError("At most 40 receive points")
            reg = {"name": str(body.get("region_name") or "custom points")[:40], "points": pts}
        months = sorted({int(m) for m in (body.get("months") or range(1, 13))} & set(range(1, 13))) or list(range(1, 13))
        hours = body.get("hours"); hours = sorted({int(h) % 24 for h in hours}) if hours else None
        ssn = [float(x) for x in (body.get("ssn") or AG.SSN_LEVELS.values())]
        if not 1 <= len(ssn) <= 6 or any(not 0 <= x <= 300 for x in ssn): raise ValueError("Sunspot numbers: 1 to 6 values between 0 and 300")
        name = P.safe_file(str(body.get("name") or "").strip(), ".prn")
        title = str(body.get("title") or f"{body.get('origin_name') or f'{lat:.2f},{lon:.2f}'} to {reg['name']}")[:60]
        job.update(phase="VOACAP runs", done=0, total=len(reg["points"]) * len(ssn))
        def progress(d, n): job["done"] = d
        h = AG.generate((lat, lon), reg, P.prn_file(slug, name), title=title, months=months, hours=hours, ssns=ssn,
                        workers=min(4, int(os.environ.get("HFTA_WORKERS", os.cpu_count() or 1))), progress=progress, cancel=lambda: job["cancel"])
        bands = [b for b in AG.BANDS if h["weight_total"].get(b, 0) > 0]
        job["result"] = {"file": name, "bands": bands, "describe": AG.describe(h["meta"]), "empty_bands": [b for b in AG.BANDS if b not in bands]}
        job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/prn/generate")
def prn_generate(slug):
    """Make a .PRN elevation-angle table with VOACAP. Body: {lat, lon, region | points, name, months?, hours?, ssn?, title?}."""
    if not AG.available(): return err("VOACAP (voacapl) is not installed on this computer.")
    if not (P.path(slug) / "project.json").exists(): return err("Project not found", 404)
    jid, job = new_job(); threading.Thread(target=_run_prn_gen, args=(job, slug, request.get_json() or {}), daemon=True).start()
    return jsonify({"job": jid})

# ------------------------------------------------------------ evaluation
def _run_eval(job, slug):
    try:
        proj = P.load(slug); cells, runs, _ = EV.plan(proj, slug)
        old = load_results(slug) or {}; old_notes = old.get("run_notes", {})
        # Reuse only valid stored patterns. The run key includes terrain content and engine identity (core/evaluate.py).
        pats = {k: v for k, v in old.get("patterns", {}).items() if k in runs and v is not None and all(x == x for x in v)}
        notes = {k: old_notes[k] for k in pats if k in old_notes}
        todo = [(rid, spec, str(P.site_dir(slug, spec["site"]))) for rid, spec in runs.items() if rid not in pats]
        job.update(phase="HFTA runs", done=0, total=len(todo))
        for rid, pat, note in CTX["pool"]().map(EV.run_one, todo, chunksize=4):
            pats[rid] = pat; job["done"] += 1
            if note: notes[rid] = note
            if job["cancel"]: raise RuntimeError("Cancelled")
        fom_log = EV.finish(proj, slug, cells, runs, pats, notes)
        prns = sorted({t["prn"] for t in proj["targets"] if t.get("prn")})
        res = {"stamp": time.strftime("%Y-%m-%d %H:%M:%S"), "cells": cells, "runs": runs, "patterns": pats, "fom_log": fom_log,
               "run_notes": notes, "n_runs": len(runs), "reused": len(runs) - len(todo), "engine": engine.engine_info(),
               "prn_sha256": {f: EX.sha256_file(P.prn_file(slug, f)) for f in prns if P.prn_file(slug, f).exists()},
               "n_failed": sum(1 for v in pats.values() if v is None), "n_filled": sum(1 for v in notes.values() if v.get("filled_deg"))}
        P.write_atomic(results_path(slug), json.dumps(res))
        job["result"] = {"cells": len(cells), "runs": len(runs), "reused": res["reused"], "failed": res["n_failed"], "filled": res["n_filled"]}; job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/evaluate")
def evaluate(slug):
    jid, job = new_job(); threading.Thread(target=_run_eval, args=(job, slug), daemon=True).start()
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
                     "use": best["heights"] if best else None, "n_options": len(c["options"]), "issues": c["issues"], "notes": c.get("notes", [])})
    return jsonify({"stamp": res["stamp"], "cells": slim, "n_runs": res["n_runs"], "engine": res.get("engine"),
                    "n_failed": res.get("n_failed", 0), "n_filled": res.get("n_filled", 0)})

@bp.get("/api/v2/p/<slug>/cell/<int:i>")
def cell(slug, i):
    res = load_results(slug)
    if not res or not 0 <= i < len(res["cells"]): return err("Result not found. Run the evaluation again.", 404)
    c = res["cells"][i]; proj = P.load(slug)
    tg = next((t for t in proj["targets"] if t["id"] == c["target"]), None)
    aoa, why = (EV.aoa_status(proj, slug, tg, c["freq"], {}) if tg else (None, "The target no longer exists."))
    runs = {a["run"]: {**res["runs"][a["run"]], "fom": a.get("fom"), "note": (res.get("run_notes") or {}).get(a["run"])} for o in c["options"] for a in o["az"]}
    best = c["options"][c["best"]] if c.get("best") is not None else None
    pats = {}
    if best:
        for a in best["az"]:
            if res["patterns"].get(a["run"]) is not None: pats[a["run"]] = res["patterns"][a["run"]]
    return jsonify({"cell": c, "runs": runs, "patterns": pats, "aoa": aoa or {}, "aoa_note": why, "prn": tg["prn"] if tg else "",
                    "engine": res.get("engine"), "angles": [float(x) for x in engine.ANGLES]})

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
        aoa, why = EV.aoa_status(proj, slug, tg, freq, {})
        if why: raise ValueError(why)
        if not jobs: raise ValueError("No heights to scan")
        if len(jobs) > 20000: raise ValueError(f"{len(jobs)} runs: too many for one scan. Use a larger step or a smaller range.")
        job.update(phase="Height scan", done=0, total=len(jobs)); pats = {}; notes = {}
        for rid, pat, note in CTX["pool"]().map(EV.run_one, jobs, chunksize=4):
            pats[rid] = pat; job["done"] += 1
            if note: notes[rid] = note
            if job["cancel"]: raise RuntimeError("Cancelled")
        import numpy as np
        rows = []
        for h in hs:
            num = den = 0.0; ok = True; filled = 0
            for az, w in EV.target_azimuths(tg):
                pat = pats[f"{h}|{az}"]
                if pat is None: ok = False; break
                filled += len((notes.get(f"{h}|{az}") or {}).get("filled_deg", []))
                f = engine.fom(np.array(pat, dtype="float32"), aoa)
                if f is not None: num += w * f; den += w
            rows.append({"h": h, "fom": round(num / den, 2) if (ok and den) else None, "failed": not ok, "filled": filled})
        job["result"] = {"rows": rows, "type": t, "freq": freq}; job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/scan")
def scan(slug):
    jid, job = new_job(); threading.Thread(target=_run_scan, args=(job, slug, request.get_json()), daemon=True).start()
    return jsonify({"job": jid})

# ------------------------------------------------------------ one-tower compromise
def _run_comp(job, slug, body):
    try:
        proj = P.load(slug); r = CM.search(proj, slug, body, CTX["pool"](), job)
        r["request"] = body; r["stamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        r["engine"] = engine.engine_info()
        P.write_atomic(P.path(slug) / "compromise.json", json.dumps(r)); job["result"] = r; job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", str(e)

@bp.post("/api/v2/p/<slug>/compromise")
def compromise(slug):
    jid, job = new_job(); threading.Thread(target=_run_comp, args=(job, slug, request.get_json()), daemon=True).start()
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
    proj = P.load(slug); tw = next((t for t in proj["towers"] if t["id"] == tid), None)
    if not tw: return err("Tower not found", 404)
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
        private = request.args.get("prn") != "0"
        return send_file(io.BytesIO(bundle(slug, private)), as_attachment=True,
                         download_name=f"{base}.hfta-project{'' if private else '-shareable'}.zip")
    if not res: return err("Run the evaluation first (step 4).")
    gr = {t["name"]: guy_rows(proj, t) for t in proj["towers"] if (t.get("guys") or {}).get("levels")}
    if kind == "xlsx":
        return send_file(io.BytesIO(EX.workbook(proj, slug, res, on, gr)), as_attachment=True, download_name=f"{base}.xlsx")
    if kind == "csv":
        return send_file(io.BytesIO(EX.results_csv(proj, res, on).encode()), as_attachment=True, download_name=f"{base}-results.csv")
    if kind == "replay":
        private = request.args.get("prn") == "1"
        return send_file(io.BytesIO(EX.replay_pack(proj, slug, res, on, include_prn=private)), as_attachment=True,
                         download_name=f"{base}-HFTA-replay{'-PRIVATE' if private else ''}.zip")
    if kind == "html":
        return send_file(io.BytesIO(RP.html_report(proj, slug, res, on, gr).encode()), as_attachment=True, download_name=f"{base}-report.html")
    return err("Unknown export")
