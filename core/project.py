"""Project file: everything needed to repeat a study. Stored as projects/<slug>/project.json with the terrain
and PRN files beside it."""
from __future__ import annotations
import json, math, os, re, tempfile, threading, time, uuid
from pathlib import Path

import contextvars
BASE_ROOT = Path(os.environ.get("PROJECTS_DIR") or Path(__file__).resolve().parent.parent / "projects")
DATA_DIR = BASE_ROOT.parent          # users.json, users/<name>/projects, the secret key, the shared terrain cache
# The project store of the current request: the base store (one user, or the admin) or a user's own store.
_ROOT_VAR = contextvars.ContextVar("hfta_root", default=None)

def root() -> Path:
    return _ROOT_VAR.get() or BASE_ROOT

def set_root(p):
    """Choose the project store for this context (request or thread). None = the base store."""
    _ROOT_VAR.set(Path(p) if p else None)

def user_root(name: str) -> Path:
    return DATA_DIR / "users" / safe_id(name, "user name") / "projects"
SOILS = {"Very poor soil": (0.001, 5), "Sandy, dry soil": (0.002, 10), "Poor soil": (0.002, 13), "Average soil": (0.005, 13),
         "Good soil": (0.010, 14), "Very good soil": (0.030, 20), "Fresh water": (0.001, 81), "Salt water": (5.000, 80)}

# Spacing warnings (not part of HFTA; HFTA has no mutual coupling). See core/spacing.py.
SPACING_DEFAULTS = {"red_wl": 0.30, "amber_wl": 0.40, "gap_red_ft": 10.0, "gap_amber_ft": 15.0}

def slug(s): return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-")[:48] or "project"
def new_id(prefix): return f"{prefix}{uuid.uuid4().hex[:6]}"

def default_project(name: str) -> dict:
    return {"name": name, "version": 2, "created": time.strftime("%Y-%m-%d %H:%M"), "units": "ft",
            "settings": {"soil": "Average soil", "sigma": 0.005, "epsr": 13.0, "diffraction": True,
                         "band_freq": {}, "spacing": dict(SPACING_DEFAULTS)},
            "sites": [], "targets": [], "towers": []}

# ---------------- safe names: every id and file name that becomes part of a path is checked here
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
FILE_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\- ]{0,120}")

def safe_id(x, what="id") -> str:
    """Project slugs, site ids, tower ids, target ids: letters, digits, '_' and '-' only."""
    if not isinstance(x, str) or not ID_RE.fullmatch(x): raise ValueError(f"Invalid {what}: {str(x)[:40]!r}")
    return x

def safe_file(x, ext=None) -> str:
    """A plain file name: no folder part, no '..', no drive letter."""
    if not isinstance(x, str) or not FILE_RE.fullmatch(x) or ".." in x: raise ValueError(f"Invalid file name: {str(x)[:60]!r}")
    if ext and not x.lower().endswith(ext): raise ValueError(f"Not a {ext} file: {x}")
    return x

def write_atomic(f: Path, text: str):
    """Write to a temporary file in the same folder, then replace: a reader never sees a half-written file."""
    f = Path(f); f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=f.parent, prefix="." + f.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h: h.write(text)
        os.replace(tmp, f)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise

_LOCK = threading.Lock()

def path(pslug): return root() / safe_id(pslug, "project")
def load(pslug) -> dict: return upgrade(json.loads((path(pslug) / "project.json").read_text()))

def upgrade(p: dict) -> dict:
    """Bring older project files to the current form: generic antennas (band + elements), no layers."""
    from . import antennas as A
    st = p.setdefault("settings", {}); st.pop("layers", None)
    st["spacing"] = {**SPACING_DEFAULTS, **(st.get("spacing") or {})}
    hint = sorted({b for t in p.get("targets", []) for b in t.get("bands", [])}, key=A.BANDS.index) or None
    for t in p.get("towers", []):
        t["antennas"] = [A.upgrade(a, t.get("bands") or hint) for a in t.get("antennas", [])]
    cp = st.get("compromise")
    if cp:
        for g in cp.get("groups", []):
            if "model" in g:
                u = A.upgrade({"model": g.pop("model")}, hint); g["el"] = u["el"]
                g.setdefault("turning_radius", u.get("turning_radius")); g.setdefault("droop", u.get("droop"))
    return p
def save(pslug, p: dict, expect_rev=None):
    """Write the project. Every save increases 'rev'. With expect_rev, the save is refused (RevisionConflict, carrying the
    stored project) when the stored revision is different: another window saved in between."""
    with _LOCK:
        f = path(pslug) / "project.json"
        if expect_rev is not None and f.exists():
            cur = json.loads(f.read_text()).get("rev", 0)
            if int(expect_rev) != cur: raise RevisionConflict(cur)
        p["rev"] = int(p.get("rev") or 0) + 1 if expect_rev is None else int(expect_rev) + 1
        write_atomic(f, json.dumps(p, indent=1))
    return p["rev"]

class RevisionConflict(Exception):
    def __init__(self, stored_rev): super().__init__("The project was changed in another window"); self.stored_rev = stored_rev
def list_projects():
    r = root(); r.mkdir(parents=True, exist_ok=True)
    return sorted([d.name for d in r.iterdir() if (d / "project.json").exists()])
def site_dir(pslug, site_id): return path(pslug) / "sites" / safe_id(site_id, "site id")
def prn_dir(pslug): return path(pslug) / "prn"
def prn_file(pslug, name): return prn_dir(pslug) / safe_file(name, ".prn")

# ---------------- schema check for a project received from the browser or from an imported zip
def _num(v, what, lo=None, hi=None, none_ok=False):
    if v is None or v == "":
        if none_ok: return None
        raise ValueError(f"{what}: a number is required")
    if isinstance(v, bool): raise ValueError(f"{what}: not a number")
    try: x = float(v)
    except (TypeError, ValueError): raise ValueError(f"{what}: not a number ({str(v)[:20]!r})")
    if not math.isfinite(x): raise ValueError(f"{what}: not a finite number")
    if (lo is not None and x < lo) or (hi is not None and x > hi): raise ValueError(f"{what}: {x:g} is outside {lo}..{hi}")
    return x

def _txt(v, n=200): return str(v if v is not None else "")[:n]

def validate(p: dict) -> dict:
    """Check types and ranges, and that every id is safe. Numbers become numbers, names become strings.
    Raises ValueError with a readable message. Unknown keys are kept as they are (they are never used in a path)."""
    from . import antennas as A
    if not isinstance(p, dict): raise ValueError("Project must be a JSON object")
    p["name"] = _txt(p.get("name") or "Project", 80)
    st = p.setdefault("settings", {})
    if not isinstance(st, dict): raise ValueError("settings must be an object")
    st["epsr"] = _num(st.get("epsr", 13), "Dielectric constant", 1, 100)
    st["sigma"] = _num(st.get("sigma", 0.005), "Conductivity", 0, 10)
    st["diffraction"] = bool(st.get("diffraction", True)); st["soil"] = _txt(st.get("soil", "Average soil"), 40)
    st["band_freq"] = {b: _num(f, f"Frequency of {b} m", 1, 60) for b, f in (st.get("band_freq") or {}).items() if b in A.BANDS and f not in (None, "")}
    st["spacing"] = {k: _num((st.get("spacing") or {}).get(k, d), f"Spacing limit {k}", 0, 1000) for k, d in SPACING_DEFAULTS.items()}
    for key in ("sites", "targets", "towers"):
        if not isinstance(p.setdefault(key, []), list): raise ValueError(f"{key} must be a list")
    seen = set()
    def uid(x, what):
        safe_id(x, what)
        if x in seen: raise ValueError(f"Duplicate id {x}")
        seen.add(x); return x
    for s in p["sites"]:
        uid(s.setdefault("id", new_id("s")), "site id"); s["name"] = _txt(s.get("name") or "Site", 80); s["notes"] = _txt(s.get("notes"), 500)
        s["lat"] = _num(s.get("lat"), "Latitude", -90, 90, True); s["lon"] = _num(s.get("lon"), "Longitude", -180, 180, True)
        if s.get("terrain") is not None and not isinstance(s["terrain"], dict): s["terrain"] = {}
        if isinstance(s.get("terrain"), dict):
            t = s["terrain"]
            if "source" in t: t["source"] = _txt(t["source"], 120)
            for k in ("length_m", "spacing_m"):
                if k in t: t[k] = _num(t[k], f"{s['name']}: terrain {k}", 0, 100000, True)
            fh = t.get("far_horizon")
            if fh is not None:
                if not isinstance(fh, dict) or not isinstance(fh.get("deg"), list) or len(fh["deg"]) > 720: t["far_horizon"] = None
                else:
                    fh["deg"] = [(_num(v, "far horizon", -90, 90, True)) for v in fh["deg"]]
                    for k in ("step", "start_m", "end_m", "antenna_m", "max_deg", "max_az"):
                        if k in fh: fh[k] = _num(fh[k], f"far horizon {k}", -100000, 100000, True)
    for t in p["targets"]:
        uid(t.setdefault("id", new_id("t")), "target id"); t["name"] = _txt(t.get("name") or "Target", 80)
        if t.get("prn") not in (None, ""): safe_file(t["prn"], ".prn")
        else: t["prn"] = ""
        t["heading"] = _num(t.get("heading", 0), f"{t['name']}: heading", -360, 720)
        offs = t.get("offsets") or [0]; w = t.get("weights") or [1] * len(offs)
        if len(offs) != len(w): raise ValueError(f"{t['name']}: {len(offs)} headings but {len(w)} weights")
        t["offsets"] = [_num(o, f"{t['name']}: heading offset", -180, 180) for o in offs]
        t["weights"] = [_num(x, f"{t['name']}: heading weight", 0, 1e6) for x in w]
        if sum(t["weights"]) <= 0: raise ValueError(f"{t['name']}: the heading weights add up to zero")
        t["bands"] = [b for b in (t.get("bands") or []) if b in A.BANDS]
    tg_ids = {t["id"] for t in p["targets"]}
    for w in p["towers"]:
        uid(w.setdefault("id", new_id("w")), "tower id"); w["name"] = _txt(w.get("name") or "Tower", 80)
        if w.get("site") not in (None, ""): safe_id(w["site"], "site id")
        if w.get("targets") is not None:
            if not isinstance(w["targets"], list): raise ValueError(f"{w['name']}: targets must be a list")
            w["targets"] = [x for x in w["targets"] if x in tg_ids]
        w["height_ft"] = _num(w.get("height_ft"), f"{w['name']}: tower height", 0, 5000, True)
        if w.get("design") is not None: w["design"] = _txt(w["design"], 500)
        if not isinstance(w.setdefault("antennas", []), list): raise ValueError(f"{w['name']}: antennas must be a list")
        for a in w["antennas"]:
            a["h"] = _num(a.get("h"), f"{w['name']}: antenna height", 0, 2000)
            for k in ("turning_radius", "droop"):
                if k in a: a[k] = _num(a.get(k), f"{w['name']}: {k}", 0, 500, True)
            if not isinstance(a.get("el", {}), dict): raise ValueError(f"{w['name']}: antenna elements must be an object")
            if "el" in a: a["el"] = {b: int(_num(n, f"{w['name']}: elements on {b} m", 1, 20)) for b, n in a["el"].items() if b in A.BANDS and n not in (None, "", 0)}
        g = w.get("guys")
        if isinstance(g, dict):
            for k in ("ice_in", "margin_ft", "density"):
                if k in g: g[k] = _num(g[k], f"{w['name']}: guys {k}", 0, 1000)
            from .guys import WIRES
            for l in g.get("levels") or []:
                l["h"] = _num(l.get("h"), f"{w['name']}: guy height", 1, 5000)
                l["r"] = _num(l.get("r"), f"{w['name']}: guy anchor radius", 1, 5000)
                l["tension"] = _num(l.get("tension"), f"{w['name']}: guy tension", 1, 1e6, True)
                if l.get("wire") not in WIRES: raise ValueError(f"{w['name']}: unknown guy wire {str(l.get('wire'))[:40]!r}")
    return p
