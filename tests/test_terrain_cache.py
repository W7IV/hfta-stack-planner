"""Shared terrain-tile cache of a public copy: one cache for all visitors (public elevation data only), a size limit
that removes the tiles used longest ago, safe temporary files, and a limit on fetches that run at the same time.
Run: python tests/test_terrain_cache.py (no native core needed)."""
import gzip
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-tcache-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
os.environ.pop("APP_PASSWORD", None); os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None)
os.environ.pop("TERRAIN_CACHE_MB", None); os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
from core import limits as LM, terrain as TR, workspaces as W

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

ORIGIN = {"Origin": "http://localhost"}
LM.CFG["new_workspaces_per_day"] = 1000
CACHE = DATA / "_cache" / "hgt"

def visitor():
    c = APP.app.test_client(); assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302; return c
def new_project(c, name="P"): return c.post("/api/v2/projects", json={"name": name}, headers=ORIGIN).get_json()["slug"]

class FakeService:
    """Replaces the download from the tile service and counts the downloads."""
    def __init__(self, size=1000, barrier=None):
        self.count, self.size, self.barrier = 0, size, barrier
        self.real = TR.fetch_terrain_response
    def __enter__(self):
        def fetch(req, service, timeout=180):
            self.count += 1
            if self.barrier: self.barrier.wait(10)
            return "application/gzip", gzip.compress(b"x" * self.size)
        TR.fetch_terrain_response = fetch; return self
    def __exit__(self, *a): TR.fetch_terrain_response = self.real

class _env:
    """Set environment variables for a block and put the old values back afterwards."""
    def __init__(self, **kw): self.kw, self.old = kw, {}
    def __enter__(self):
        for k, v in self.kw.items(): self.old[k] = os.environ.get(k); os.environ[k] = v
    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

def py(code, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("PUBLIC_MODE", "TERRAIN_CACHE_MB")}; e.update(env)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(REPO)],
                       check=False, capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

@test
def the_cache_limit_has_defaults_and_a_setting():
    assert py("from core import terrain as T; print(T.cache_limit_bytes())", PUBLIC_MODE="1") == str(1000 * 1024 * 1024)
    assert py("from core import terrain as T; print(T.cache_limit_bytes())") == "None"                    # own computer: no limit
    assert py("from core import terrain as T; print(T.cache_limit_bytes())", PUBLIC_MODE="1", TERRAIN_CACHE_MB="5") == str(5 * 1024 * 1024)

@test
def trimming_removes_the_tiles_used_longest_ago():
    d = TMP / "trim"; d.mkdir(); now = time.time()
    for i in range(5):                                                        # tile0 is the oldest, tile4 the newest
        f = d / f"tile{i}.hgt"; f.write_bytes(b"x" * 1000); os.utime(f, (now - 100 + i, now - 100 + i))
    (d / "other.txt").write_text("keep")
    # 5 tiles of 1000 bytes + 1000 incoming = 6000. The limit is 3500: remove 3 tiles (6000 -> 3000), the oldest first.
    removed = TR.trim_cache(d, incoming=1000, limit=3500)
    assert removed == ["tile0.hgt", "tile1.hgt", "tile2.hgt"]
    assert sorted(p.name for p in d.glob("*.hgt")) == ["tile3.hgt", "tile4.hgt"] and (d / "other.txt").exists()
    assert TR.trim_cache(d, incoming=0, limit=10**9) == []                                                 # room: nothing removed

@test
def half_written_files_are_removed_when_old():
    d = TMP / "tmpfiles"; d.mkdir(); now = time.time()
    old, new = d / "a.1234.tmp", d / "b.5678.tmp"
    old.write_bytes(b"x"); new.write_bytes(b"x"); os.utime(old, (now - 7200, now - 7200))
    TR.trim_cache(d, limit=10**9)
    assert not old.exists() and new.exists()                                  # two hours old: removed; just made: kept

@test
def a_tile_is_downloaded_once_and_kept_in_use_order():
    d = TMP / "dl"
    with FakeService(size=600_000) as svc, _env(TERRAIN_CACHE_MB="1"):        # limit 1 MB = 1,048,576 bytes
        assert TR.download_tile(47, -123, d) == b"x" * 600_000 and svc.count == 1
        a = d / "N47W123.hgt"; os.utime(a, (time.time() - 500, time.time() - 500))
        TR.download_tile(47, -123, d); assert svc.count == 1                  # from the cache; and the tile is marked as used now
        assert time.time() - a.stat().st_mtime < 5
        os.utime(a, (time.time() - 500, time.time() - 500))
        TR.download_tile(48, -123, d); assert svc.count == 2                  # 0.6 MB + 0.6 MB is over 1 MB: the older tile goes
        assert not a.exists() and (d / "N48W123.hgt").exists()
        TR.download_tile(47, -123, d); assert svc.count == 3                  # downloaded again when needed
        assert not list(d.glob("*.tmp"))

@test
def two_requests_for_the_same_tile_do_not_collide():
    d = TMP / "race"; results, errors = [], []
    with FakeService(size=5000, barrier=threading.Barrier(6)) as svc:
        def go():
            try: results.append(TR.download_tile(10, 20, d))
            except Exception as e: errors.append(e)                           # noqa: BLE001
        ts = [threading.Thread(target=go) for _ in range(6)]
        [t.start() for t in ts]; [t.join(20) for t in ts]
    assert not errors and len(results) == 6 and all(r == b"x" * 5000 for r in results) and svc.count == 6, (errors, len(results), svc.count)
    assert (d / "N10E020.hgt").stat().st_size == 5000 and not list(d.glob("*.tmp"))

@test
def visitors_share_one_cache_outside_every_workspace():
    calls = []
    real = TR.fetch_tiles_and_generate
    def stub(lat, lon, out_dir, prefix, cache_dir, *opts):
        calls.append(cache_dir); TR.download_tile(int(lat), int(lon), cache_dir); return {"ok": True}
    TR.fetch_tiles_and_generate = stub
    try:
        with FakeService(size=2000) as svc:
            a, b = visitor(), visitor(); body = {"lat": 47.5, "lon": 8.5, "source": "tiles"}
            ra = a.post(f"/api/v2/p/{new_project(a)}/sites/s1/auto", json=body, headers=ORIGIN)
            rb = b.post(f"/api/v2/p/{new_project(b)}/sites/s1/auto", json=body, headers=ORIGIN)
            assert ra.status_code == 200 and rb.status_code == 200
            assert svc.count == 1                                             # B used the tile that A's request loaded
    finally: TR.fetch_tiles_and_generate = real
    assert calls == [CACHE, CACHE] and (CACHE / "N47E008.hgt").exists()
    inside = [p for p in (DATA / "public").rglob("*") if p.suffix in (".hgt", ".tmp")]
    assert inside == []                                                       # no tile inside any workspace
    removed = W.cleanup(now=time.time() + 40 * 86400)                         # all workspaces expire: the cache stays
    assert len(removed) >= 2 and (CACHE / "N47E008.hgt").exists()

@test
def only_a_few_online_fetches_run_at_once():
    started, release = threading.Event(), threading.Event(); real = TR.fetch_tiles_and_generate
    def stub(*a, **k):
        started.set(); release.wait(10); return {"ok": True}
    TR.fetch_tiles_and_generate = stub; out = {}
    try:
        old = LM.CFG["terrain_concurrent"]; LM.CFG["terrain_concurrent"] = 1
        a, b = visitor(), visitor(); sa, sb = new_project(a), new_project(b)
        body = {"lat": 47.5, "lon": 8.5, "source": "tiles"}
        t = threading.Thread(target=lambda: out.update(a=a.post(f"/api/v2/p/{sa}/sites/s1/auto", json=body, headers=ORIGIN)))
        t.start(); assert started.wait(10)
        r = b.post(f"/api/v2/p/{sb}/sites/s1/auto", json=body, headers=ORIGIN)             # the only place is taken
        assert r.status_code == 429 and "fetching terrain for other visitors" in r.get_json()["error"]
        release.set(); t.join(10)
        assert out["a"].status_code == 200
        assert b.post(f"/api/v2/p/{sb}/sites/s1/auto", json=body, headers=ORIGIN).status_code == 200   # free again
        assert LM._TERRAIN_BUSY == 0
    finally:
        TR.fetch_tiles_and_generate = real; LM.CFG["terrain_concurrent"] = old; release.set()

@test
def a_copy_that_is_not_public_has_no_terrain_limit():
    out = py("from core import limits as L; import contextlib\n"
             "with L.terrain_slot():\n"
             "    with L.terrain_slot():\n"
             "        print('no limit')")
    assert out == "no limit"

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
