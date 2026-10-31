"""Terrain fetch failures must be actionable without hiding bad coordinates or deleting valid profiles.

Run: python tests/test_terrain_fetch_errors.py
No external network calls: upstream failures are simulated.
"""
import io
import os
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(tempfile.mkdtemp(prefix="hfta-terrain-failure-"))
os.environ["PROJECTS_DIR"] = str(ROOT / "projects")
os.environ.pop("APP_PASSWORD", None)
os.environ.pop("HOSTED", None)
os.environ.pop("RAILWAY_ENVIRONMENT", None)

import app as APP
from core import terrain as TR, project as P

client = APP.app.test_client()
created = client.post("/api/v2/projects", json={"name": "Service failure test"})
assert created.status_code == 200, created.data
slug = created.get_json()["slug"]
site = "s1"
out = P.site_dir(slug, site)
out.mkdir(parents=True, exist_ok=True)
old = out / "EXISTING-AZI-0.00.PRO"
old.write_text("meters\n0 100\n30 110\n", encoding="utf-8")

request_body = {"lat": 43.67, "lon": -72.01, "source": "3dep", "az_step": 90}
def submit():
    return client.post(f"/api/v2/p/{slug}/sites/{site}/auto", json=request_body)

with patch.object(TR, "fetch_dem_and_generate", side_effect=TR.TerrainServiceTemporaryError("USGS 3DEP temporarily unavailable (HTTP 503).")):
    response = submit()
    assert response.status_code == 503, response.data
    error = response.get_json()
    assert error["retryable"] is True and "try again" in error["error"].lower(), error

with patch.object(TR, "fetch_dem_and_generate", side_effect=ValueError("USGS 3DEP has no data at the site.")):
    response = submit()
    assert response.status_code == 400, response.data
    assert "retryable" not in response.get_json(), response.get_json()

assert old.read_text(encoding="utf-8") == "meters\n0 100\n30 110\n"

def fake_http_error(code):
    return urllib.error.HTTPError("https://example.test", code, "simulated", {}, io.BytesIO(b""))

for code in (429, 500, 502, 503, 504):
    with patch.object(TR.urllib.request, "urlopen", side_effect=fake_http_error(code)):
        try:
            TR.fetch_terrain_response("https://example.test", "USGS 3DEP")
            raise AssertionError(f"HTTP {code} should have been retryable")
        except TR.TerrainServiceTemporaryError:
            pass

with patch.object(TR.urllib.request, "urlopen", side_effect=urllib.error.URLError("timed out")):
    try:
        TR.fetch_terrain_response("https://example.test", "USGS 3DEP")
        raise AssertionError("Network error should have been retryable")
    except TR.TerrainServiceTemporaryError:
        pass

# 404 is missing coverage/invalid URL, not a transient outage.
with patch.object(TR.urllib.request, "urlopen", side_effect=fake_http_error(404)):
    try:
        TR.fetch_terrain_response("https://example.test", "USGS 3DEP")
        raise AssertionError("HTTP 404 should not have been marked retryable")
    except ValueError:
        pass

# Preserve the existing Terrain Tiles semantics: 404 means no tile, not a retry notification.
with patch.object(TR.urllib.request, "urlopen", side_effect=fake_http_error(404)):
    assert TR.download_tile(43, -72, ROOT / "hgt") is None

class JsonError:
    headers = {"Content-Type": "application/json"}
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False
    def read(self): return b'{"error":{"code":503,"message":"Service temporarily unavailable"}}'

with patch.object(TR.urllib.request, "urlopen", return_value=JsonError()):
    try:
        TR.fetch_dem_and_generate(43.67, -72.01, out, "TEST")
        raise AssertionError("HTTP 200 with server busy JSON must be retryable")
    except TR.TerrainServiceTemporaryError:
        pass
assert old.exists() and old.read_text(encoding="utf-8").startswith("meters\n")
print("PASS: retryable upstream errors use 503; invalid input uses 400; existing profiles preserved")
