"""Clean-up of workspaces that are not used any more (public mode).
Run: python tests/test_cleanup.py (no native core needed)."""
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-clean-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
os.environ.pop("APP_PASSWORD", None); os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None)
os.environ.pop("WORKSPACE_EXPIRY_DAYS", None); os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
from core import workspaces as W

PASSED = []
def test(fn):
    shutil.rmtree(W.public_dir(), ignore_errors=True)                           # every test starts with no workspaces
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

DAY = 86400
NOW = time.time()
ORIGIN = {"Origin": "http://localhost"}

def made(days_ago, with_file=True):
    """A workspace last used days_ago days before NOW, with a project file in it."""
    wid = W.create(); d = W.workspace_dir(wid)
    if with_file:
        (W.root_for(wid) / "proj").mkdir(); (W.root_for(wid) / "proj" / "project.json").write_text("{}")
    t = NOW - days_ago * DAY
    os.utime(d / W.MARK, (t, t))
    return wid

@test
def the_default_is_thirty_days():
    assert W.expiry_days() == 30

@test
def only_expired_workspaces_are_deleted():
    old, edge_old, edge_new, new = made(40), made(30.1), made(29.9), made(0)
    # 30.1 days is just past the limit of 30 days; 29.9 days is just inside it
    (DATA / "projects").mkdir(parents=True, exist_ok=True); (DATA / "projects" / "base.txt").write_text("keep")
    stray_dir = W.public_dir() / "keep-me"; stray_dir.mkdir(); (stray_dir / "a.txt").write_text("keep")
    stray_file = W.public_dir() / "notes.txt"; stray_file.write_text("keep")
    lookalike = W.public_dir() / ("A" * 32); lookalike.mkdir()                   # upper case: not a workspace number
    removed = W.cleanup(now=NOW)
    assert sorted(removed) == sorted([old, edge_old])
    assert not W.workspace_dir(old).exists() and not W.workspace_dir(edge_old).exists()
    assert W.workspace_dir(edge_new).exists() and W.workspace_dir(new).exists()
    assert (W.root_for(new) / "proj" / "project.json").exists()                  # a kept workspace is untouched
    assert (DATA / "projects" / "base.txt").read_text() == "keep"                # nothing outside public/
    assert (stray_dir / "a.txt").exists() and stray_file.exists() and lookalike.exists()
    assert W.LAST["removed"] == 2 and W.LAST["kept"] == 0
    assert W.cleanup(now=NOW) == []                                              # nothing more to do

@test
def a_workspace_with_a_running_calculation_is_kept():
    busy, idle = made(60), made(60)
    removed = W.cleanup(running_owners=[str(W.root_for(busy))], now=NOW)
    assert removed == [idle] and W.workspace_dir(busy).exists()
    assert W.LAST["kept"] == 1
    assert W.cleanup(now=NOW) == [busy]                                          # deleted once the calculation is over

@test
def a_workspace_without_a_mark_uses_the_folder_time():
    wid = made(0)
    (W.workspace_dir(wid) / W.MARK).unlink()
    t = NOW - 50 * DAY; os.utime(W.workspace_dir(wid), (t, t))
    assert W.cleanup(now=NOW) == [wid]

@test
def a_visitor_who_returns_in_time_keeps_the_workspace():
    wid = made(40)
    real = W.last_used
    calls = []
    def returning(w):                                                            # the visitor comes back during the clean-up
        calls.append(w)
        return real(w) if calls.count(w) == 1 else NOW                           # first look: old; second look: just now
    W.last_used = returning
    try:
        assert W.cleanup(now=NOW) == [] and W.workspace_dir(wid).exists()
        assert calls == [wid, wid]
    finally:
        W.last_used = real
    assert W.cleanup(now=NOW) == [wid]                                           # without the visit it is deleted

@test
def the_expiry_follows_the_setting():
    wid = made(10)
    os.environ["WORKSPACE_EXPIRY_DAYS"] = "7"
    try:
        assert W.cleanup(now=NOW) == [wid]
    finally:
        os.environ.pop("WORKSPACE_EXPIRY_DAYS", None)

@test
def no_public_folder_is_not_an_error():
    assert not W.public_dir().exists()
    assert W.list_ids() == [] and W.cleanup(now=NOW) == []

@test
def the_daily_thread_runs_cleanup_and_stops():
    wid = made(40); seen = []; stop = threading.Event()
    t = W.start_cleanup(lambda: seen.append(1) or [], interval=0.2, first_delay=0.1, stop=stop)
    for _ in range(50):
        if not W.workspace_dir(wid).exists() and len(seen) >= 2: break              # at least two rounds
        time.sleep(0.1)
    stop.set(); t.join(5)
    assert not W.workspace_dir(wid).exists() and len(seen) >= 2 and not t.is_alive()

@test
def a_thread_survives_an_error():
    stop = threading.Event(); n = []
    def broken():
        n.append(1); raise RuntimeError("test error")
    t = W.start_cleanup(broken, interval=0.1, first_delay=0.05, stop=stop)
    for _ in range(50):
        if len(n) >= 3: break
        time.sleep(0.1)
    stop.set(); t.join(5)
    assert len(n) >= 3 and not t.is_alive()

@test
def a_visitor_with_a_deleted_workspace_starts_again():
    c = APP.app.test_client(); assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302
    with c.session_transaction() as s: wid = s["ws"]
    assert c.get("/api/v2/meta").status_code == 200
    t = NOW - 40 * DAY; os.utime(W.workspace_dir(wid) / W.MARK, (t, t))
    assert W.cleanup(now=NOW) == [wid]
    r = c.get("/"); assert r.status_code == 302 and r.headers["Location"].startswith("/welcome")
    assert c.get("/api/v2/meta").status_code == 401
    assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302
    with c.session_transaction() as s: assert s["ws"] != wid
    assert c.get("/api/v2/meta").status_code == 200

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
