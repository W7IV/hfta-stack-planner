"""Library shared by all projects: named towers (antennas, guys, switching) and named sites (position and terrain files).
Stored in <PROJECTS_DIR>/_library/: towers.json, sites.json, and sites/<id>/*.PRO.
Adding an item to a project copies it, so later changes in the project do not change the library, and the reverse."""
from __future__ import annotations
import json, re, shutil, time
from pathlib import Path
from . import project as P

def root() -> Path:
    d = P.ROOT / "_library"; (d / "sites").mkdir(parents=True, exist_ok=True); return d

def _load(name) -> list:
    f = root() / name
    return json.loads(f.read_text()) if f.exists() else []

def _save(name, items: list):
    (root() / name).write_text(json.dumps(items, indent=1))

def _clean_name(s) -> str:
    return (str(s or "").strip() or "Unnamed")[:80]

def _safe_id(i: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", i or ""): raise ValueError("Bad library id")
    return i

def listing() -> dict:
    sites = _load("sites.json")
    for s in sites:
        d = root() / "sites" / s["id"]
        s["n_profiles"] = len([p for p in d.glob("*") if p.suffix.lower() == ".pro"]) if d.exists() else 0
    return {"towers": _load("towers.json"), "sites": sites}

# ---------------- towers
TOWER_KEYS = ("antennas", "guys", "switching", "height_ft", "design")

def save_tower(tower: dict, name: str, replace: bool = False) -> dict:
    """Save a copy of a project tower. Same name + replace=True overwrites the library entry of that name."""
    items = _load("towers.json"); name = _clean_name(name)
    entry = {k: json.loads(json.dumps(tower.get(k))) for k in TOWER_KEYS}
    entry.update(name=name, saved=time.strftime("%Y-%m-%d %H:%M"))
    old = next((t for t in items if t["name"].lower() == name.lower()), None)
    if old and not replace: raise FileExistsError(name)
    if old: entry["id"] = old["id"]; items[items.index(old)] = entry
    else: entry["id"] = P.new_id("L"); items.append(entry)
    _save("towers.json", items); return entry

def tower_for_project(lib_id: str) -> dict:
    t = next((t for t in _load("towers.json") if t["id"] == _safe_id(lib_id)), None)
    if not t: raise KeyError(lib_id)
    out = {k: json.loads(json.dumps(t.get(k))) for k in TOWER_KEYS}
    out.update(id=P.new_id("w"), name=t["name"], site=None)
    return out

def delete_tower(lib_id: str):
    _save("towers.json", [t for t in _load("towers.json") if t["id"] != _safe_id(lib_id)])

# ---------------- sites (with terrain files)
SITE_KEYS = ("lat", "lon", "notes", "terrain")

def save_site(site: dict, src_dir: Path, name: str, replace: bool = False) -> dict:
    items = _load("sites.json"); name = _clean_name(name)
    old = next((s for s in items if s["name"].lower() == name.lower()), None)
    if old and not replace: raise FileExistsError(name)
    entry = {k: json.loads(json.dumps(site.get(k))) for k in SITE_KEYS}
    entry.update(name=name, saved=time.strftime("%Y-%m-%d %H:%M"), id=old["id"] if old else P.new_id("L"))
    dst = root() / "sites" / entry["id"]
    if dst.exists(): shutil.rmtree(dst)
    dst.mkdir(parents=True)
    if src_dir.exists():
        for f in src_dir.iterdir():
            if f.is_file() and f.suffix.lower() == ".pro": shutil.copy2(f, dst / f.name)
    if old: items[items.index(old)] = entry
    else: items.append(entry)
    _save("sites.json", items); return entry

def site_into_project(lib_id: str, pslug: str) -> dict:
    s = next((s for s in _load("sites.json") if s["id"] == _safe_id(lib_id)), None)
    if not s: raise KeyError(lib_id)
    out = {k: json.loads(json.dumps(s.get(k))) for k in SITE_KEYS}
    out.update(id=P.new_id("s"), name=s["name"])
    src, dst = root() / "sites" / s["id"], P.site_dir(pslug, out["id"])
    dst.mkdir(parents=True, exist_ok=True)
    if src.exists():
        for f in src.iterdir():
            if f.is_file(): shutil.copy2(f, dst / f.name)
    return out

def delete_site(lib_id: str):
    lib_id = _safe_id(lib_id)
    _save("sites.json", [s for s in _load("sites.json") if s["id"] != lib_id])
    d = root() / "sites" / lib_id
    if d.exists(): shutil.rmtree(d)
