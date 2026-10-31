"""Regression: one configured tower, with one antenna, is a supported HFTA study."""
import io
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ["PROJECTS_DIR"] = str(Path(tempfile.mkdtemp()) / "projects")
os.environ.pop("APP_PASSWORD", None)
os.environ.pop("RAILWAY_ENVIRONMENT", None)
os.environ.pop("HOSTED", None)

import app
from core import project as P, evaluate as EV

client = app.app.test_client()
slug = client.post("/api/v2/projects", json={"name": "One Tower"}).get_json()["slug"]
proj = client.get(f"/api/v2/p/{slug}").get_json()["project"]
proj["sites"] = [{"id": "s1", "name": "Single site"}]
save = client.put(f"/api/v2/p/{slug}", json=proj)
assert save.status_code == 200, save.data

source = REPO / "tests" / "data" / "AZI-30.00.PRO"
files = {"files": [(io.BytesIO(source.read_bytes()), "AZI-30.00.PRO")]}
r = client.post(f"/api/v2/p/{slug}/sites/s1/import", data=files, content_type="multipart/form-data")
assert r.status_code == 200, r.data
prn = REPO / "samples" / "TEST-ONLY-synthetic.PRN"
r = client.post(f"/api/v2/p/{slug}/prn", data={"files": [(io.BytesIO(prn.read_bytes()), "SYN.PRN")]}, content_type="multipart/form-data")
assert r.status_code == 200, r.data

proj = client.get(f"/api/v2/p/{slug}").get_json()["project"]
proj["targets"] = [{"id": "t1", "name": "Target", "prn": "SYN.PRN", "heading": 30,
                    "offsets": [0], "weights": [1], "bands": ["20"]}]
proj["towers"] = [{"id": "w1", "name": "Only tower", "switching": "stackmatch",
                   "antennas": [{"h": 60, "el": {"20": 4}}]}]
r = client.put(f"/api/v2/p/{slug}", json=proj)
assert r.status_code == 200, r.data

cells, runs, _ = EV.plan(P.load(slug), slug)
assert len(cells) == 1 and len(runs) == 1, (cells, runs)
assert cells[0]["tower"] == "w1" and cells[0]["target"] == "t1"
assert not cells[0]["issues"], cells[0]
assert len(cells[0]["options"]) == 1, cells[0]
print("PASS: one tower with one antenna produces an evaluable HFTA run")
