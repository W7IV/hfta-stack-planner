"""
app.py - Flask web GUI for OpenHFTA terrain analysis, stack evaluation and height optimisation.

Run:  python app.py      (then open http://localhost:5000)
Env:  OPENHFTA_DIR  path to the OpenHFTA checkout (default ../openhfta)
      HFTA_WORKERS  number of calculation processes (default: CPU count)
      PROJECTS_DIR  where projects are stored (default ./projects; on a host, a persistent volume)
      APP_PASSWORD  if set, the browser asks for it (any user name). Use it when the app is on the internet.
      PUBLIC_MODE   1 = public copy: no accounts, one private workspace per browser (not together with APP_PASSWORD)
      MAX_UPLOAD_MB largest upload in megabytes (default 512)
      TRUSTED_PROXY_HOPS  proxies in front of the app that add to X-Forwarded-For (default 1 when hosted, else 0)

Model of a request
  bands : one or more bands analysed with the SAME physical heights (single-band or tribander).
          Each band has its own frequency, element count (antenna type), boom length and weight.
  paths : one or more azimuths. Each path = terrain profile + ARRL .PRN file (all bands) + weight.
  Score : FOM per band = path-weighted mean; overall = band-weighted mean of band FOMs.
"""
from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from urllib.parse import quote

from flask import Flask, jsonify, render_template, request

import engine

app = Flask(__name__)
# One upload limit for the whole app. DEM files can be large and a copy on your own computer needs them, so the
# default is 512 MB. A hosted copy that many people use can set a lower value.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25" if os.environ.get("PUBLIC_MODE") == "1" else "512"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# Public mode: no accounts; every browser gets its own private workspace (core/workspaces.py). Off by default.
PUBLIC_MODE = os.environ.get("PUBLIC_MODE") == "1"
if PUBLIC_MODE and APP_PASSWORD:
    raise SystemExit("PUBLIC_MODE=1 and APP_PASSWORD are both set. A copy is either public or password-protected: "
                     "unset one of them and start again.")

# A hosted copy must have a password, unless it is a public copy. Railway sets RAILWAY_ENVIRONMENT; HOSTED=1 marks
# any other server.
if (os.environ.get("HOSTED") == "1" or os.environ.get("RAILWAY_ENVIRONMENT")) and not APP_PASSWORD and not PUBLIC_MODE:
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


# ---------------------------------------------------------------- accounts (hosted copy)
from flask import session, redirect, g, abort  # noqa: E402
from core import limits as LM, project as P, stats as ST, users as U, workspaces as W  # noqa: E402

if PUBLIC_MODE:
    # Anonymous daily usage counts (core/stats.py): every refusal of a limit and every wait in line is counted.
    ST.ENABLED = True
    LM.HOOKS.update(refused=ST.refused, queued=ST.queued)

if APP_PASSWORD or PUBLIC_MODE:
    app.secret_key = U.secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("HOSTED") == "1"),
                      PERMANENT_SESSION_LIFETIME=30 * 24 * 3600)


@app.before_request
def _login():
    """Hosted copy (APP_PASSWORD set): every page needs a login. 'admin' with APP_PASSWORD, or a user made by the
    admin. Each user works in their own project store. Basic authentication with APP_PASSWORD still works for the
    admin (scripts). Without APP_PASSWORD (own computer) there is no login and one store."""
    P.set_root(None); g.user = None
    if PUBLIC_MODE:
        return _public_gate()
    if not APP_PASSWORD or request.path == "/healthz" or request.path.startswith("/static/"):
        return None
    if request.path in ("/login", "/logout", "/guide"):
        return None
    import hmac
    a = request.authorization
    if a and a.password and a.type == "basic" and hmac.compare_digest(a.password, APP_PASSWORD):
        g.user = U.ADMIN; return None
    user = session.get("user")
    if user == U.ADMIN or (user and user in {u["name"] for u in U.listing()}):
        g.user = user; P.set_root(U.root_for(user)); return None
    session.clear()
    if request.path.startswith("/api/"):
        return jsonify({"error": "Please log in", "login": True}), 401
    return redirect("/login?next=" + request.path)


# Number of proxies in front of the app that each add an address to X-Forwarded-For. Railway: 1. On your own computer: 0.
PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS",
                                "1" if (os.environ.get("HOSTED") == "1" or os.environ.get("RAILWAY_ENVIRONMENT")) else "0"))


def client_key() -> str:
    """Address used for the login lock-out. A client can write anything into X-Forwarded-For, so only the address
    added by our own proxy is trusted: the PROXY_HOPS-th value from the right. With no proxy, the direct address."""
    parts = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    if PROXY_HOPS > 0 and len(parts) >= PROXY_HOPS:
        return parts[-PROXY_HOPS]
    return request.remote_addr or "?"


@app.before_request
def _limits():
    """Public copy: limits that depend on the request (projects, uploads, terrain fetches, VOACAP tables). Registered
    after _login, so the workspace is already chosen. Calculations are limited where they are registered."""
    if not LM.enabled() or request.method != "POST" or not hasattr(g, "workspace"):
        return None
    try:
        LM.guard_request(request, g.workspace, W.workspace_dir(g.workspace), lambda: len(P.list_projects()))
    except LM.LimitError as e:
        return jsonify({"error": str(e)}), e.status
    return None


@app.errorhandler(LM.LimitError)
def _limit_reached(e):
    return jsonify({"error": str(e)}), e.status


def _safe_next(nxt) -> str:
    """Only a path on this server: starts with one slash, not two."""
    return nxt if isinstance(nxt, str) and nxt.startswith("/") and not nxt.startswith("//") else "/"


def _public_gate():
    """Public copy: a visitor needs a workspace. Without a valid one, pages go to the notice page and API calls get
    the same 401 answer as a login (the page script then opens the notice page). The base project store is never
    used in public mode."""
    if request.path == "/admin" or request.path.startswith("/admin/"):
        abort(404)                            # there is no administrator page, whoever asks
    if request.path == "/healthz" or request.path.startswith("/static/") or request.path in ("/welcome", "/guide", "/privacy", "/stats"):
        return None
    wid = session.get("ws")
    if W.exists(wid):
        P.set_root(W.root_for(wid)); g.workspace = wid; W.touch(wid); ST.active(wid)
        return None
    session.pop("ws", None)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Please accept the notice first", "login": True}), 401
    return redirect("/welcome?next=" + quote(request.path))


REPO_URL = "https://github.com/W7IV/hfta-stack-planner"
USAGE_COUNTS = PUBLIC_MODE   # a public copy keeps anonymous daily usage counts (core/stats.py); the privacy page says so


@app.context_processor
def _public_context():
    """Texts of a public copy for the page templates (footer, privacy page). None on any other copy: no footer."""
    if not PUBLIC_MODE:
        return {"public": None}
    return {"public": {"operator": os.environ.get("OPERATOR_NAME", "Paul F. Merrill, W7IV").strip(),
                       "contact": os.environ.get("OPERATOR_CONTACT", "").strip(),
                       "expiry_days": W.expiry_days(), "workspace_mb": LM.CFG["workspace_mb"],
                       "usage_counts": USAGE_COUNTS, "prn_upload": LM.prn_upload_allowed(),
                       "repo": REPO_URL, "releases": REPO_URL + "/releases/latest",
                       "allowance": [f"{LM.CFG[key]} {name}" for key, name in LM.ALLOWANCE.values() if LM.CFG[key] >= 0]}}


@app.get("/privacy")
def privacy_page():
    if not PUBLIC_MODE: abort(404)       # the privacy note describes a public copy
    return render_template("privacy.html")


STATS_JOBS = [("hfta", "HFTA runs"), ("designer", "Designer"), ("scan", "Height scans"), ("voacap", "VOACAP tables"),
              ("terrain", "Terrain fetches"), ("classic", "Classic optimiser")]


@app.get("/stats")
def stats_page():
    """Usage counts for the operator. Only on a public copy with STATS_PASSWORD set (any user name); otherwise 404.
    Shows totals only: the counts hold no address and no workspace number (core/stats.py)."""
    import hmac
    pw = os.environ.get("STATS_PASSWORD", "")
    if not PUBLIC_MODE or not pw:
        abort(404)
    key = "stats:" + client_key()
    if U.too_many_failures(key):
        return "Too many failed attempts. Wait five minutes.", 429
    a = request.authorization
    if not (a and a.type == "basic" and a.password and hmac.compare_digest(a.password, pw)):
        if a: U.note_failure(key)
        return "Password required.", 401, {"WWW-Authenticate": 'Basic realm="HFTA Stack Planner statistics"'}
    U.clear_failures(key)
    try:
        n_days = min(max(int(request.args.get("days", 30)), 1), ST.KEEP_DAYS)
    except ValueError:
        n_days = 30
    days = ST.days(n_days)
    base = W.public_dir()
    now = {"workspaces": len(W.list_ids()),
           "workspace_mb": round(LM.workspace_bytes(base) / 1048576, 1) if base.exists() else 0.0,
           "cache_mb": round(LM.workspace_bytes(P.DATA_DIR / "_cache") / 1048576, 1),
           "cleanup": dict(W.LAST), "running": sum(1 for j in JOBS.values() if j.get("state") == "running"),
           "waiting": len(LM.GATE.waiting), "memory": LM.memory_fraction()}
    if request.args.get("format") == "json":
        return jsonify({"days": [{"date": d, **c} for d, c in days], "now": now})
    if now["cleanup"].get("time"):
        now["cleanup"]["time"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now["cleanup"]["time"]))
    return render_template("stats.html", days=days, now=now, jobs=STATS_JOBS)


@app.get("/welcome")
def welcome_page():
    if not PUBLIC_MODE: return redirect("/")
    if W.exists(session.get("ws")): return redirect(_safe_next(request.args.get("next", "/")))
    return render_template("welcome.html", next=_safe_next(request.args.get("next", "/")), message=None)


@app.post("/welcome")
def welcome_post():
    if not PUBLIC_MODE: return redirect("/")
    wid = session.get("ws")
    if not W.exists(wid):
        try:
            LM.spend("new_workspaces", client_key(), 1, LM.CFG["new_workspaces_per_day"],
                     "Too many new workspaces were made from this address today. Try again tomorrow.")
        except LM.LimitError as e:
            return render_template("welcome.html", next=_safe_next(request.form.get("next", "/")), message=str(e)), e.status
        wid = W.create(); ST.new_workspace()
        session.clear(); session["ws"] = wid; session.permanent = True
    return redirect(_safe_next(request.form.get("next", "/")))


@app.get("/login")
def login_page():
    if PUBLIC_MODE: return redirect("/welcome?next=" + quote(_safe_next(request.args.get("next", "/"))))
    if not APP_PASSWORD: return redirect("/")
    return render_template("login.html", error=None, next=request.args.get("next", "/"))


@app.post("/login")
def login_post():
    if PUBLIC_MODE: return redirect("/welcome")
    if not APP_PASSWORD: return redirect("/")
    key = client_key()
    if U.too_many_failures(key):
        return render_template("login.html", error="Too many failed attempts. Wait five minutes.", next="/"), 429
    name = U.authenticate(request.form.get("user", ""), request.form.get("password", ""), APP_PASSWORD)
    if not name:
        U.note_failure(key); time.sleep(0.5)
        return render_template("login.html", error="Wrong user name or password.", next=request.form.get("next", "/")), 401
    U.clear_failures(key); session.clear(); session["user"] = name; session.permanent = True
    nxt = request.form.get("next") or "/"
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if PUBLIC_MODE: return redirect("/")      # no log-out: the workspace stays with the browser until it expires
    session.clear(); return redirect("/login" if APP_PASSWORD else "/")


@app.get("/api/whoami")
def whoami():
    out = {"user": g.user, "admin": g.user == U.ADMIN, "accounts": bool(APP_PASSWORD)}
    if PUBLIC_MODE: out["public"] = True      # the answer of a password or local copy is unchanged
    return jsonify(out)


def _admin_only():
    if PUBLIC_MODE: abort(404)                # no user list and no administrator page on a public copy
    if not APP_PASSWORD or g.user != U.ADMIN: abort(403)


@app.get("/admin")
def admin_page():
    _admin_only(); return render_template("admin.html", users=U.listing(), msg=request.args.get("msg", ""))


@app.post("/admin/users")
def admin_users():
    _admin_only(); f = request.form; act = f.get("action")
    try:
        if act == "create": U.create(f.get("name"), f.get("password")); msg = f"User {f.get('name', '').strip().lower()} created."
        elif act == "password": U.set_password(f.get("name"), f.get("password")); msg = f"Password of {f.get('name')} changed."
        elif act == "delete": U.delete(f.get("name")); msg = f"Login of {f.get('name')} removed. Their files stay on the server under users/{f.get('name')}."
        else: msg = "Unknown action."
    except (ValueError, KeyError) as e:
        msg = f"Not done: {e}"
    from urllib.parse import quote
    return redirect("/admin?msg=" + quote(msg))


@app.after_request
def _headers(resp):
    """Browser rules: scripts and styles only from this server (Plotly is served from /static), no framing by other
    sites, no content-type guessing. Inline styles are allowed (the pages set widths and colours inline)."""
    resp.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tile.openstreetmap.org; "
        "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


@app.get("/healthz")
def _healthz():
    return "ok"

WORKERS = LM.workers()
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


def new_search_job() -> tuple:
    """Register a job of the classic optimiser. It belongs to the project store of the request, like a Designer job,
    so another user cannot read or cancel it."""
    if LM.enabled():
        LM.check_new_job(str(P.root()), JOBS, P.root().parent)
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "state": "running", "phase": "", "done": 0, "total": 0, "started": time.time(),
           "result": None, "error": None, "cancel": False, "owner": str(P.root())}
    JOBS[jid] = job
    ST.job("classic")
    return jid, job


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
        for k, grid in grids.items():
            if not grid:
                raise ValueError(f"No height combination satisfies the {k} search ranges, minimum spacing "
                                 "and maximum tower height")
    except (KeyError, ValueError, TypeError) as e:
        return err(str(e))

    jid, job = new_search_job()
    args = dict(specs=specs, phases=phases, step=step, bottom=bottom, spacing=spacing)
    v2.start_thread(run_search, job, c, grids, args)      # in line with the Designer jobs on a public copy
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
    if job.get("owner") != str(P.root()):
        return err("Unknown job", 404)
    return jsonify({k: job[k] for k in ("state", "phase", "done", "total", "result", "error")})


@app.post("/api/job/<jid>/cancel")
def job_cancel(jid):
    job = JOBS.get(jid)
    if job and job.get("owner") == str(P.root()):
        job["cancel"] = True
    return jsonify({"ok": True})


import v2  # noqa: E402
v2.CTX.update(pool=pool, jobs=JOBS)
app.register_blueprint(v2.bp)

if PUBLIC_MODE:
    # Once a day, delete workspaces that were not used for WORKSPACE_EXPIRY_DAYS days (default 30), unless a
    # calculation of that workspace is still running.
    W.start_cleanup(lambda: [j.get("owner") for j in list(JOBS.values()) if j.get("state") == "running"])

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
