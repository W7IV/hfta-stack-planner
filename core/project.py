"""Project file: everything needed to repeat a study. Stored as projects/<slug>/project.json with the terrain
and PRN files beside it."""
from __future__ import annotations
import json, re, time, uuid
from pathlib import Path

import os
ROOT = Path(os.environ.get("PROJECTS_DIR") or Path(__file__).resolve().parent.parent / "projects")
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

def path(pslug): return ROOT / pslug
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
def save(pslug, p: dict):
    d = path(pslug); d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps(p, indent=1))
def list_projects():
    ROOT.mkdir(parents=True, exist_ok=True)
    return sorted([d.name for d in ROOT.iterdir() if (d / "project.json").exists()])
def site_dir(pslug, site_id): return path(pslug) / "sites" / site_id
def prn_dir(pslug): return path(pslug) / "prn"
