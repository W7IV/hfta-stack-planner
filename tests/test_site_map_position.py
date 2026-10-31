"""Site position updates invalidate old elevation profiles and calculation results.

Run: python tests/test_site_map_position.py
Does not contact a map tile or terrain service.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ["PROJECTS_DIR"] = str(Path(tempfile.mkdtemp(prefix="hfta-map-test-")) / "projects")
os.environ.pop("APP_PASSWORD", None)
os.environ.pop("RAILWAY_ENVIRONMENT", None)
os.environ.pop("HOSTED", None)

import app as APP
from core import project as P

client = APP.app.test_client()
created = client.post("/api/v2/projects", json={"name": "Map picker regression"})
assert created.status_code == 200, created.data
slug = created.get_json()["slug"]
project_url = f"/api/v2/p/{slug}"
position_url = f"{project_url}/sites/s1/position"
proj = client.get(project_url).get_json()["project"]
proj["sites"] = [
    {"id": "s1", "name": "Tower location", "lat": 41.43889, "lon": -73.40383,
     "terrain": {"source": "USGS 3DEP (online)"}},
    {"id": "s2", "name": "Other location", "lat": 42.0, "lon": -73.5},
]
saved = client.put(project_url, json=proj)
assert saved.status_code == 200, saved.data
revision = saved.get_json()["project"]["rev"]
first = P.site_dir(slug, "s1")
second = P.site_dir(slug, "s2")
first.mkdir(parents=True, exist_ok=True)
second.mkdir(parents=True, exist_ok=True)
first_profile = first / "LOCATION-AZI-0.00.PRO"
other_profile = second / "OTHER-AZI-0.00.PRO"
first_profile.write_text("meters\n0 100\n30 101\n")
other_profile.write_text("meters\n0 200\n30 201\n")
results = P.path(slug) / "results.json"
results.write_text(json.dumps({"stamp": "old comparison", "cells": []}))

# A failed/stale edit must never delete files.
invalid = client.post(position_url, json={"lat": 999, "lon": 0, "rev": revision})
assert invalid.status_code == 400, invalid.data
stale = client.post(position_url, json={"lat": 43, "lon": -72, "rev": revision - 1})
assert stale.status_code == 409, stale.data
assert first_profile.exists() and other_profile.exists() and results.exists()

# A map selection must change only that site's coordinates and old terrain.
response = client.post(position_url, json={"lat": 41.43891, "lon": -73.40385, "rev": revision})
assert response.status_code == 200, response.data
state = response.get_json()
assert state["removed_profiles"] == 1, state
assert state["site_files"]["s1"]["n"] == 0
assert state["site_files"]["s2"]["n"] == 1
assert not first_profile.exists() and other_profile.exists()
assert not results.exists() and state["has_results"] is False
site = next(s for s in state["project"]["sites"] if s["id"] == "s1")
assert (site["lat"], site["lon"]) == (41.43891, -73.40385)
assert site["terrain"]["source"] == ""
assert site["name"] == "Tower location"

# Selecting the same location again must not erase fresh profiles.
fresh = first / "NEW-AZI-0.00.PRO"
fresh.write_text("meters\n0 300\n30 310\n")
revision = state["project"]["rev"]
same = client.post(position_url, json={"lat": 41.43891, "lon": -73.40385, "rev": revision})
assert same.status_code == 200, same.data
assert same.get_json()["removed_profiles"] == 0
assert fresh.exists()

# Cross-origin site edits remain blocked.
blocked = client.post(position_url, json={"lat": 42, "lon": -72, "rev": revision},
                      headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"})
assert blocked.status_code == 403
assert fresh.exists()

# Tile source is restricted to one specific domain, not arbitrary remote scripts.
headers = client.get("/").headers
assert "https://tile.openstreetmap.org" in headers["Content-Security-Policy"]
assert "script-src 'self'" in headers["Content-Security-Policy"]
print("PASS: map saves coordinates, checks revision, clears only stale terrain and results, preserves other sites")
