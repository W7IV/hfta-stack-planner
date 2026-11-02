"""Anonymous usage counts of a public copy and the operator's /stats page.
Run: python tests/test_stats.py (no native core needed)."""
import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-stats-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
for k in ("APP_PASSWORD", "RAILWAY_ENVIRONMENT", "HOSTED", "STATS_PASSWORD"):
    os.environ.pop(k, None)
os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
import v2 as V2
from core import limits as LM, project as P, stats as ST, users as U, workspaces as W

PASSED = []
def test(fn):
    ST.path().unlink(missing_ok=True); ST._SEEN.update(date=None, key=b"", tags=set()); LM._DAY["counts"].clear()
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

ORIGIN = {"Origin": "http://localhost"}
LM.CFG["new_workspaces_per_day"] = 1000

def visitor():
    c = APP.app.test_client(); assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302; return c
def workspace_of(c):
    with c.session_transaction() as s: return s["ws"]
def new_project(c, name="P"): return c.post("/api/v2/projects", json={"name": name}, headers=ORIGIN).get_json()["slug"]
def today(): d = ST.days(1); return d[0][1] if d else {}
def basic(pw): return {"Authorization": "Basic " + base64.b64encode(f"operator:{pw}".encode()).decode()}
def wait_jobs():
    for _ in range(100):
        if not any(j.get("state") == "running" for j in APP.JOBS.values()): return
        time.sleep(0.05)

@test
def counting_is_on_for_a_public_copy():
    assert ST.ENABLED is True and LM.HOOKS["refused"] is ST.refused and LM.HOOKS["queued"] is ST.queued

@test
def new_and_active_workspaces():
    a = visitor(); assert today().get("new_workspaces") == 1 and "active_workspaces" not in today()
    a.get("/api/v2/meta"); a.get("/api/v2/meta"); a.get("/")
    assert today()["active_workspaces"] == 1                                  # once per day, however many requests
    b = visitor(); b.get("/api/v2/meta")
    assert today()["new_workspaces"] == 2 and today()["active_workspaces"] == 2
    real = ST._today; ST._today = lambda: "2999-01-01"                        # the next day: counted again
    try:
        a.get("/api/v2/meta")
        assert ST._load()["2999-01-01"] == {"active_workspaces": 1}
    finally: ST._today = real

@test
def the_counts_hold_no_identifier():
    a, b = visitor(), visitor(); a.get("/"); b.get("/")
    raw = ST.path().read_text()
    for wid in (workspace_of(a), workspace_of(b)):
        assert wid not in raw
        assert hashlib.sha256(wid.encode()).digest()[:16] not in ST._SEEN["tags"]     # the memory set is keyed, not a plain hash
    assert "127.0.0.1" not in raw and "session" not in raw
    allowed = {"new_workspaces", "active_workspaces", "queue_waits", "jobs", "refused"}
    assert all(set(c) <= allowed for c in ST._load().values())
    assert not list(P.DATA_DIR.glob("stats/*key*"))                           # the daily key is never written

@test
def calculations_and_fetches_by_kind():
    APP.JOBS.clear()
    a = visitor(); slug = new_project(a)
    with APP.app.test_request_context():
        P.set_root(W.root_for(workspace_of(a))); _, job = APP.new_search_job(); job["state"] = "done"
    assert a.post(f"/api/v2/p/{slug}/evaluate", headers=ORIGIN).status_code == 200; wait_jobs()
    assert a.post(f"/api/v2/p/{slug}/scan", json={}, headers=ORIGIN).status_code == 200; wait_jobs()
    assert a.post(f"/api/v2/p/{slug}/compromise", json={}, headers=ORIGIN).status_code == 200; wait_jobs()
    a.post(f"/api/v2/p/{slug}/sites/s1/auto", json={}, headers=ORIGIN)       # reaches the route (400: no position)
    real_avail, real_run = V2.AG.available, V2._run_prn_gen
    V2.AG.available = lambda: True; V2._run_prn_gen = lambda job, slug, body: job.update(state="done")
    try:
        assert a.post(f"/api/v2/p/{slug}/prn/generate", json={"regions": ["EU", "AS"]}, headers=ORIGIN).status_code == 200
    finally: V2.AG.available, V2._run_prn_gen = real_avail, real_run
    wait_jobs()
    assert today()["jobs"] == {"classic": 1, "hfta": 1, "scan": 1, "designer": 1, "terrain": 1, "voacap": 2}   # two regions: two tables

@test
def refusals_and_waits_in_line():
    a = visitor()
    old = LM.CFG["projects"]; LM.CFG["projects"] = 1
    try:
        new_project(a, "one")
        assert a.post("/api/v2/projects", json={"name": "two"}, headers=ORIGIN).status_code == 429
    finally: LM.CFG["projects"] = old
    gate = LM.Gate(); release = threading.Event(); old_n = LM.CFG["jobs_on_server"]; LM.CFG["jobs_on_server"] = 1
    try:
        t1 = threading.Thread(target=lambda: gate.run({"cancel": False}, lambda: release.wait(10))); t1.start()
        while gate.running == 0: time.sleep(0.02)
        t2 = threading.Thread(target=lambda: gate.run({"cancel": False}, lambda: None)); t2.start(); time.sleep(0.3)
        release.set(); t1.join(5); t2.join(5)
    finally: LM.CFG["jobs_on_server"] = old_n
    assert today()["refused"] == {"projects": 1} and today()["queue_waits"] == 1

@test
def the_stats_page_needs_its_own_password():
    c = APP.app.test_client()
    assert c.get("/stats").status_code == 404                                 # no STATS_PASSWORD: no page
    visitor().get("/")
    os.environ["STATS_PASSWORD"] = "stats-pass-123"
    try:
        r = c.get("/stats"); assert r.status_code == 401 and "Basic" in r.headers["WWW-Authenticate"]
        assert c.get("/stats", headers=basic("wrong")).status_code == 401
        r = c.get("/stats", headers=basic("stats-pass-123")); t = r.get_data(as_text=True)
        assert r.status_code == 200 and "Usage of the public copy" in t and ST._today() in t and "Workspaces on the volume" in t
        j = c.get("/stats?format=json", headers=basic("stats-pass-123")).get_json()
        assert j["days"][0]["date"] == ST._today() and j["days"][0]["new_workspaces"] == 1 and j["now"]["workspaces"] >= 1
        assert c.get("/stats?days=abc", headers=basic("stats-pass-123")).status_code == 200
        with c.session_transaction() as s: assert "ws" not in s               # the operator needs no workspace
        x = APP.app.test_client()
        for _ in range(8): x.get("/stats", headers=basic("nope"))
        assert x.get("/stats", headers=basic("stats-pass-123")).status_code == 429   # locked after repeated failures
    finally:
        os.environ.pop("STATS_PASSWORD", None); U.clear_failures("stats:127.0.0.1")

@test
def old_days_are_dropped():
    ST._save({f"2020-{m:02d}-{d:02d}": {"new_workspaces": 1} for m in range(1, 13) for d in range(1, 29)})   # 336 days
    ST._save({**ST._load(), **{f"2021-{m:02d}-{d:02d}": {"new_workspaces": 1} for m in range(1, 4) for d in range(1, 29)}})  # +84 = 420
    ST.new_workspace()
    d = ST._load(); assert len(d) == ST.KEEP_DAYS == 400 and ST._today() in d and "2020-01-01" not in d

@test
def a_counting_failure_never_breaks_a_request():
    real = ST._save
    def broken(d): raise OSError("disk full")
    ST._save = broken
    try:
        c = visitor(); assert c.get("/api/v2/meta").status_code == 200
        ST.job("hfta")                                                        # no exception
    finally: ST._save = real

@test
def a_copy_that_is_not_public_counts_nothing():
    code = ("import app; from core import stats as S; c = app.app.test_client(); c.get('/'); c.get('/api/v2/meta')\n"
            "print(S.ENABLED, S.path().exists(), c.get('/stats').status_code)")
    e = {k: v for k, v in os.environ.items() if k != "PUBLIC_MODE"}
    e["PROJECTS_DIR"] = str(TMP / "other" / "projects"); e["STATS_PASSWORD"] = "x-12345678"
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(REPO)],
                       check=False, capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False False 404", r.stdout

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
