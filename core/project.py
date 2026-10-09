"""Project file: everything needed to repeat a study. Stored as projects/<slug>/project.json with the terrain
and PRN files beside it."""
from __future__ import annotations
import json, re, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "projects"
SOILS = {"Very poor soil": (0.001, 5), "Sandy, dry soil": (0.002, 10), "Poor soil": (0.002, 13), "Average soil": (0.005, 13),
         "Good soil": (0.010, 14), "Very good soil": (0.030, 20), "Fresh water": (0.001, 81), "Salt water": (5.000, 80)}

def slug(s): return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-")[:48] or "project"
def new_id(prefix): return f"{prefix}{uuid.uuid4().hex[:6]}"

def default_project(name: str) -> dict:
    return {"name": name, "version": 2, "created": time.strftime("%Y-%m-%d %H:%M"), "units": "ft",
            "settings": {"soil": "Average soil", "sigma": 0.005, "epsr": 13.0, "diffraction": True,
                         "band_freq": {}, "layers": {"jk_gain": False, "beam_loss": False}},
            "sites": [], "targets": [], "towers": []}

def path(pslug): return ROOT / pslug
def load(pslug) -> dict: return json.loads((path(pslug) / "project.json").read_text())
def save(pslug, p: dict):
    d = path(pslug); d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps(p, indent=1))
def list_projects():
    ROOT.mkdir(exist_ok=True)
    return sorted([d.name for d in ROOT.iterdir() if (d / "project.json").exists()])
def site_dir(pslug, site_id): return path(pslug) / "sites" / site_id
def prn_dir(pslug): return path(pslug) / "prn"
