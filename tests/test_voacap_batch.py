"""VOACAP region batch tests with a stubbed engine (no costly external VOACAP runs)."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ["PROJECTS_DIR"] = tempfile.mkdtemp(prefix="hfta-voacap-batch-") + "/projects"
os.environ.pop("APP_PASSWORD", None)
os.environ.pop("RAILWAY_ENVIRONMENT", None)
os.environ.pop("HOSTED", None)
os.environ["HFTA_WORKERS"] = "2"

import app as APP
from core import project as P, aoa_gen as AG
import v2 as V

client = APP.app.test_client()
slug = client.post("/api/v2/projects", json={"name": "Batch"}).get_json()["slug"]
base = {"lat": 42.4, "lon": -71.1, "regions": ["EU", "JA", "US"], "prefix": "My station",
        "origin_name": "My station", "months": [1], "ssn": [70]}
output_dir = P.prn_dir(slug)
output_dir.mkdir(parents=True, exist_ok=True)
orig = output_dir / "My-station-EU-VOACAP.PRN"
orig.write_text("old European table", encoding="utf-8")

calls = []
def fake_generate(origin, reg, out_file, title=None, progress=None, cancel=None, **kw):
    calls.append((reg["name"], out_file.name, title))
    n = len(reg["points"]) * len(kw["ssns"])
    progress(n, n)
    out_file.write_text("VOACAP-generated: test\nElev    20m\n 1       100.0\n", encoding="utf-8")
    return {"weight_total": {"20": 1.0},
            "meta": {"months": kw["months"], "hours": kw["hours"], "ssn": kw["ssns"]}}

job = {"cancel": False, "state": "running", "done": 0, "total": 0, "phase": ""}
with patch.object(AG, "generate", side_effect=fake_generate):
    V._run_prn_batch(job, slug, base, 42.4, -71.1)
assert job["state"] == "done", job
assert job["total"] == 36 and job["done"] == 36, job
assert [item["region"] for item in job["result"]["files"]] == ["EU", "JA", "US"]
assert [item["file"] for item in job["result"]["files"]] == [
    "My-station-EU-VOACAP.PRN", "My-station-JA-VOACAP.PRN", "My-station-US-VOACAP.PRN"]
assert len(calls) == 3 and len(list(output_dir.glob("*.PRN"))) == 3
assert orig.read_text(encoding="utf-8").startswith("VOACAP-generated:")
assert [x["region_name"] for x in job["result"]["files"]] == ["Europe", "Japan", "USA"]

# Invalid selections never generate or overwrite files.
for values in ([], ["??"], ["EU", "EU"]):
    before = orig.read_bytes()
    try:
        V._run_prn_batch(dict(job, cancel=False), slug, dict(base, regions=values), 42.4, -71.1)
        raise AssertionError(f"Invalid region selection accepted: {values}")
    except ValueError:
        pass
    assert orig.read_bytes() == before

# Cancellation and engine failures preserve every preexisting file.
for failure in ("cancel", "engine"):
    old = {p.name: p.read_bytes() for p in output_dir.glob("*.PRN")}
    seen = []
    state = {"cancel": False, "done": 0, "total": 0}
    def fail_after_one(origin, reg, out_file, **kw):
        seen.append(out_file.name)
        if len(seen) == 2:
            if failure == "engine": raise RuntimeError("VOACAP stopped")
            state["cancel"] = True
        out_file.write_text("temporary", encoding="utf-8")
        kw["progress"](len(reg["points"]), len(reg["points"]))
        return {"weight_total": {"20": 1.0}, "meta": {"months": [1], "hours": None, "ssn": [70]}}
    try:
        with patch.object(AG, "generate", side_effect=fail_after_one):
            V._run_prn_batch(state, slug, base, 42.4, -71.1)
        raise AssertionError("Expected batch abort")
    except RuntimeError:
        pass
    assert {p.name: p.read_bytes() for p in output_dir.glob("*.PRN")} == old
    assert not any(p.name.startswith(".voacap-batch-") for p in output_dir.iterdir())

# Real API uses one background job and keeps the existing result shape for single-region callers.
with patch.object(AG, "available", return_value=True), patch.object(AG, "generate", side_effect=fake_generate):
    res = client.post(f"/api/v2/p/{slug}/prn/generate", json=base)
    assert res.status_code == 200, res.data
    jid = res.get_json()["job"]
    for _ in range(50):
        status = client.get(f"/api/job/{jid}").get_json()
        if status["state"] != "running": break
        time.sleep(0.1)
    assert status["state"] == "done" and status["result"]["count"] == 3, status
print("PASS: multiregion VOACAP batch, progress, results, invalid selections and all-or-nothing staging")
