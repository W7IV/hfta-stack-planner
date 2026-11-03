"""Limits of a public copy: one calculation per workspace, a line for the rest, a memory guard, disk, projects,
terrain fetches, VOACAP tables, new workspaces, and the defaults. A copy that is not public is not limited.
Run: python tests/test_limits.py (no native core needed)."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-lim-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
os.environ.pop("APP_PASSWORD", None); os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None)
os.environ.pop("MAX_UPLOAD_MB", None); os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
import v2 as V2
from core import limits as LM, project as P, workspaces as W

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

ORIGIN = {"Origin": "http://localhost"}
LM.CFG["new_workspaces_per_day"] = 1000         # the tests below make many workspaces from one address

@contextlib.contextmanager
def cfg(**kw):
    old = {k: LM.CFG[k] for k in kw}; LM.CFG.update(kw)
    try: yield
    finally: LM.CFG.update(old)

def visitor():
    c = APP.app.test_client(); assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302; return c
def workspace_of(c):
    with c.session_transaction() as s: return s["ws"]
def new_project(c, name="P"):
    r = c.post("/api/v2/projects", json={"name": name}, headers=ORIGIN); assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["slug"]
def reset_counts(): LM._DAY["counts"].clear()
def py(code, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("PUBLIC_MODE", "HFTA_WORKERS", "HOSTED", "RAILWAY_ENVIRONMENT", "MAX_UPLOAD_MB")}
    e.update(env)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(REPO)],
                       check=False, capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

@test
def public_defaults_follow_the_plan():
    out = py("import app; from core import compromise as C, limits as L; "
             "print(L.enabled(), L.CFG['jobs_per_workspace'], L.CFG['jobs_on_server'], L.CFG['projects'], L.CFG['workspace_mb'], "
             "L.CFG['voacap_per_day'], L.CFG['terrain_per_day'], L.CFG['new_workspaces_per_day'], C.STAGE_SECONDS, "
             "C.MAX_GROUP_LAYOUTS, app.MAX_UPLOAD_MB, L.unpacked_limit())", PUBLIC_MODE="1")
    assert out == "True 1 2 5 50 7 20 10 60 50000 25 52428800", out         # 50 MB = 50 * 1024 * 1024 = 52,428,800 bytes

@test
def a_copy_that_is_not_public_is_not_limited():
    out = py("import app; from core import compromise as C, limits as L; "
             "print(L.enabled(), C.STAGE_SECONDS, C.MAX_GROUP_LAYOUTS, app.MAX_UPLOAD_MB, L.unpacked_limit())")
    assert out == "False 240 200000 512 500000000", out

@test
def calculation_processes_have_a_safe_default():
    keep = {k: os.environ.pop(k, None) for k in ("HFTA_WORKERS", "HOSTED", "RAILWAY_ENVIRONMENT")}
    real = LM.os.cpu_count; LM.os.cpu_count = lambda: 24                      # what Railway reported
    try:
        assert LM.workers() == 2                                              # public copy
        LM.PUBLIC = False
        assert LM.workers() == 24                                             # own computer: all CPUs, as before
        os.environ["HOSTED"] = "1"; assert LM.workers() == 4                  # other hosted copy: at most 4
        os.environ["HFTA_WORKERS"] = "7"; assert LM.workers() == 7            # an explicit setting always wins
    finally:
        LM.os.cpu_count = real; LM.PUBLIC = True
        for k in ("HFTA_WORKERS", "HOSTED", "RAILWAY_ENVIRONMENT"): os.environ.pop(k, None)
        for k, v in keep.items():
            if v is not None: os.environ[k] = v

@test
def one_calculation_per_workspace():
    a, b = visitor(), visitor(); APP.JOBS.clear()
    with APP.app.test_request_context():
        P.set_root(W.root_for(workspace_of(a))); _, job_a = APP.new_search_job()
        try:
            APP.new_search_job(); raise AssertionError("a second job was accepted")
        except LM.LimitError as e:
            assert "one calculation at a time" in str(e) and e.status == 429
        P.set_root(W.root_for(workspace_of(b))); _, job_b = APP.new_search_job()   # another workspace is not blocked
    slug = new_project(a)
    r = a.post(f"/api/v2/p/{slug}/evaluate", headers=ORIGIN)                       # the same rule through a Designer route
    assert r.status_code == 429 and "one calculation at a time" in r.get_json()["error"]
    job_a["state"] = job_b["state"] = "done"; APP.JOBS.clear()

@test
def waiting_line_keeps_order_and_can_be_cancelled():
    gate = LM.Gate(); ran, release = [], threading.Event()
    def make(name, wait=False):
        job = {"cancel": False, "state": "running", "phase": ""}
        def fn():
            ran.append(name)
            if wait: release.wait(10)
        t = threading.Thread(target=lambda: gate.run(job, fn), daemon=True); return job, t
    with cfg(jobs_on_server=1):
        _, t1 = make("one", wait=True); t1.start()
        while "one" not in ran: time.sleep(0.05)
        j2, t2 = make("two"); t2.start(); time.sleep(0.2)
        j3, t3 = make("three"); t3.start(); j4, t4 = make("four"); t4.start(); time.sleep(0.7)
        assert gate.running == 1 and "Waiting in line: position 1 of 3" == j2["phase"] and "position 3 of 3" in j4["phase"]
        j3["cancel"] = True; t3.join(5)                                           # cancelled while waiting: never runs
        assert j3["state"] == "error" and j3["error"] == "Cancelled" and "three" not in ran
        release.set(); t2.join(10); t4.join(10)
        assert ran == ["one", "two", "four"] and gate.running == 0 and not gate.waiting

@test
def full_line_refuses_new_calculations():
    old = LM.GATE; LM.GATE = LM.Gate()
    try:
        with cfg(queue_length=2):
            LM.GATE.waiting.extend([{}, {}])
            try:
                LM.check_new_job("x", {}, TMP); raise AssertionError("accepted with a full line")
            except LM.LimitError as e:
                assert "line on the public server is full" in str(e)
            LM.GATE.waiting.pop()
            LM.check_new_job("x", {}, TMP)                                        # room again
    finally: LM.GATE = old

@test
def memory_guard_waits_but_never_stands_still():
    d = TMP / "cg"; d.mkdir(); used, limit = d / "memory.current", d / "memory.max"
    old_files, old_gate = LM.CGROUP_FILES, LM.GATE
    LM.CGROUP_FILES = [(str(used), str(limit))]; LM.GATE = LM.Gate()
    try:
        used.write_text("90"); limit.write_text("100")                           # 90 percent of 100 bytes; the limit is 80
        assert LM.memory_fraction() == 0.9 and LM.memory_busy()
        LM.check_new_job("x", {}, TMP)                                            # nothing running: allowed, or the line would stall
        LM.GATE.running = 1
        try:
            LM.check_new_job("x", {}, TMP); raise AssertionError("accepted while memory is high")
        except LM.LimitError as e:
            assert "most of its memory" in str(e)
        used.write_text("50"); LM.check_new_job("x", {}, TMP)                     # 50 percent: fine
        limit.write_text("max"); used.write_text("99"); assert LM.memory_fraction() is None and not LM.memory_busy()
        with cfg(memory_mb=1):                                                    # a limit given in the settings: 1 MB
            used.write_text(str(900_000)); assert LM.memory_busy()                # 900,000 of 1,048,576 bytes = 86 percent
        # with high memory and nothing running, the next job in the line starts at once
        LM.GATE.running = 0; used.write_text("90"); limit.write_text("100"); hit = []
        t = threading.Thread(target=lambda: LM.GATE.run({"cancel": False}, lambda: hit.append(1)), daemon=True); t.start(); t.join(5)
        assert hit == [1]
    finally: LM.CGROUP_FILES, LM.GATE = old_files, old_gate

@test
def start_thread_uses_the_line_on_a_public_copy():
    old = LM.GATE; LM.GATE = LM.Gate(); done = threading.Event(); seen = []
    try:
        V2.start_thread(lambda job, x: (seen.append((job["id"], x)), done.set()), {"id": "j1", "cancel": False}, 7)
        assert done.wait(5) and seen == [("j1", 7)]
        for _ in range(40):                                                       # the place is given back just after the job
            if LM.GATE.running == 0: break
            time.sleep(0.05)
        assert LM.GATE.running == 0
    finally: LM.GATE = old

@test
def full_workspace_refuses_work_and_uploads():
    c = visitor(); slug = new_project(c); wdir = W.workspace_dir(workspace_of(c))
    (wdir / "projects" / "filler.bin").write_bytes(b"x" * 600_000)                # 0.57 MB
    with cfg(workspace_mb=1):
        r = c.post(f"/api/v2/p/{slug}/sites/s1/dem", data={"dem": (io.BytesIO(b"y" * 600_000), "a.tif")}, headers=ORIGIN)
        assert r.status_code == 413 and "workspace is full" in r.get_json()["error"]      # 0.57 + 0.57 MB is over 1 MB
        (wdir / "projects" / "filler2.bin").write_bytes(b"x" * 600_000)                  # now over the limit by itself
        r = c.post(f"/api/v2/p/{slug}/evaluate", headers=ORIGIN)
        assert r.status_code == 413 and "workspace is full" in r.get_json()["error"]
        assert c.get("/api/v2/meta").status_code == 200                                   # reading still works
    assert LM.workspace_bytes(wdir) > 1_200_000

@test
def projects_per_workspace():
    c = visitor()
    with cfg(projects=2):
        new_project(c, "one"); new_project(c, "two")
        r = c.post("/api/v2/projects", json={"name": "three"}, headers=ORIGIN)
        assert r.status_code == 429 and "at most 2 projects" in r.get_json()["error"]
        r = c.post("/api/v2/projects/import", data={"file": (io.BytesIO(b"PK"), "p.zip")}, headers=ORIGIN)
        assert r.status_code == 429                                                       # an import is a new project too
        assert visitor().post("/api/v2/projects", json={"name": "other"}, headers=ORIGIN).status_code == 200

@test
def terrain_fetches_per_day():
    c, d = visitor(), visitor(); slug = new_project(c, "t"); reset_counts()
    url = f"/api/v2/p/{slug}/sites/s1/auto"
    with cfg(terrain_per_day=2):
        assert c.post(url, json={}, headers=ORIGIN).status_code == 400                    # reaches the route: lat and lon missing
        assert c.post(url, json={}, headers=ORIGIN).status_code == 400
        r = c.post(url, json={}, headers=ORIGIN)
        assert r.status_code == 429 and "2 online terrain fetches a day" in r.get_json()["error"]
        assert d.post(f"/api/v2/p/{new_project(d, 'u')}/sites/s1/auto", json={}, headers=ORIGIN).status_code == 400   # own count
        real = LM._today; LM._today = lambda: "2999-01-01"                                 # the next day
        try: assert c.post(url, json={}, headers=ORIGIN).status_code == 400
        finally: LM._today = real
    reset_counts()

@test
def voacap_tables_per_day():
    c = visitor(); slug = new_project(c, "v"); reset_counts()
    url = f"/api/v2/p/{slug}/prn/generate"
    with cfg(voacap_per_day=3):
        assert c.post(url, json={"regions": ["EU", "AS"]}, headers=ORIGIN).status_code != 429     # 2 tables of 3
        r = c.post(url, json={"regions": ["EU", "AS"]}, headers=ORIGIN)                           # 2 more would make 4
        assert r.status_code == 429 and "3 VOACAP tables a day" in r.get_json()["error"]
        assert c.post(url, json={"region": "EU"}, headers=ORIGIN).status_code != 429              # one table: the third
        assert c.post(url, json={"region": "EU"}, headers=ORIGIN).status_code == 429
    reset_counts()

@test
def new_workspaces_per_address():
    reset_counts()
    def arrive(addr):
        c = APP.app.test_client(); c.environ_base["REMOTE_ADDR"] = addr
        return c.post("/welcome", data={"next": "/"}, headers=ORIGIN)
    with cfg(new_workspaces_per_day=2):
        assert arrive("8.8.8.8").status_code == 302 and arrive("8.8.8.8").status_code == 302
        r = arrive("8.8.8.8")
        assert r.status_code == 429 and "Too many new workspaces" in r.get_data(as_text=True)
        assert arrive("9.9.9.9").status_code == 302                                           # another address is not affected
    reset_counts()

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
