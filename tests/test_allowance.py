"""Public copy, v1.1.1: the allowance of a workspace (Designer searches, height scans, VOACAP tables, in total) and the
time budget of a whole Designer search. Run: python tests/test_allowance.py (no native core needed)."""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-allow-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
os.environ.pop("APP_PASSWORD", None); os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None)
os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
import v2 as V2
from core import compromise as CM, limits as LM, project as P, workspaces as W

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
def py(code, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("PUBLIC_MODE", "HFTA_WORKERS", "HOSTED", "RAILWAY_ENVIRONMENT")}
    e.update(env)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(REPO)],
                       check=False, capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

def run_job(wid, kind, outcome, n=1):
    """Start a job of this kind in workspace wid, as a route does, and wait until it has ended and been counted."""
    with APP.app.test_request_context():
        P.set_root(W.root_for(wid))
        _, job = V2.new_job(kind, n)
        def fn(job):
            if outcome == "cancel": job["cancel"] = True; job["state"], job["error"] = "error", "Cancelled"
            else: job["state"] = outcome
        V2.start_thread(fn, job)
    for _ in range(100):                          # the thread ends, then the count is written (or not)
        if job["state"] != "running" and LM.GATE.running == 0 and not LM.GATE.waiting: break
        time.sleep(0.05)
    time.sleep(0.1)
    return job

@test
def defaults_follow_the_plan():
    out = py("from core import compromise as C, limits as L; "
             "print(L.CFG['designer_runs'], L.CFG['scan_runs'], L.CFG['voacap_tables'], C.SEARCH_SECONDS)", PUBLIC_MODE="1")
    assert out == "2 3 3 600", out
    out = py("from core import compromise as C; print(C.SEARCH_SECONDS)")             # own computer: no time budget
    assert out == "0", out
    out = py("from core import limits as L; print(L.CFG['designer_runs'])", PUBLIC_MODE="1", LIMIT_DESIGNER_RUNS="5")
    assert out == "5", out

@test
def only_a_finished_calculation_is_counted():
    c = visitor(); wid = workspace_of(c); wdir = W.workspace_dir(wid); APP.JOBS.clear()
    run_job(wid, "designer", "error"); run_job(wid, "designer", "cancel")
    assert LM.allowance_used(wdir) == {}, LM.allowance_used(wdir)
    run_job(wid, "designer", "done"); run_job(wid, "hfta", "done")              # Evaluate is never counted
    assert LM.allowance_used(wdir) == {"designer": 1}, LM.allowance_used(wdir)
    assert (wdir / LM.ALLOWANCE_FILE).is_file() and not (W.root_for(wid) / LM.ALLOWANCE_FILE).exists()

@test
def a_used_allowance_refuses_with_the_way_forward():
    c = visitor(); wid = workspace_of(c); APP.JOBS.clear()
    run_job(wid, "designer", "done"); run_job(wid, "designer", "done")
    with APP.app.test_request_context():
        P.set_root(W.root_for(wid))
        try:
            V2.new_job("designer"); raise AssertionError("a third Designer search was accepted")
        except LM.LimitError as e:
            assert e.status == 429 and e.kind == "allowance_designer"
            assert "2 Designer searches" in str(e) and "free planner" in str(e) and "import it there" in str(e), str(e)
        V2.new_job("scan")                                                     # other kinds are still allowed
    other = workspace_of(visitor())                                            # another workspace has its own allowance
    with APP.app.test_request_context():
        P.set_root(W.root_for(other)); APP.JOBS.clear(); V2.new_job("designer")
    APP.JOBS.clear()

@test
def voacap_tables_count_one_per_region():
    c = visitor(); wid = workspace_of(c); APP.JOBS.clear()
    run_job(wid, "voacap", "done", n=2)
    with APP.app.test_request_context():
        P.set_root(W.root_for(wid))
        try:
            V2.new_job("voacap", 2); raise AssertionError("4 tables were accepted with an allowance of 3")
        except LM.LimitError as e:
            assert "1 left; this one needs 2" in str(e), str(e)
        V2.new_job("voacap", 1)
    APP.JOBS.clear()

@test
def the_count_is_kept_in_the_workspace_and_survives_a_restart():
    c = visitor(); wid = workspace_of(c); wdir = W.workspace_dir(wid); APP.JOBS.clear()
    run_job(wid, "scan", "done")
    out = py("from core import limits as L; from pathlib import Path; import sys; print(L.allowance(Path(sys.argv[2]))['scan']['left'])"
             .replace("sys.argv[2]", repr(str(wdir))), PUBLIC_MODE="1")
    assert out == "2", out                                                     # a new process (a restarted server) reads it
    (wdir / LM.ALLOWANCE_FILE).write_text("not json")                          # a damaged file counts as nothing used
    assert LM.allowance_used(wdir) == {}
    (wdir / LM.ALLOWANCE_FILE).write_text(json.dumps({"scan": -4, "other": 9, "designer": "x"}))
    assert LM.allowance_used(wdir) == {}

@test
def a_negative_setting_means_no_allowance():
    c = visitor(); wid = workspace_of(c); APP.JOBS.clear()
    with cfg(designer_runs=-1):
        for _ in range(3): run_job(wid, "designer", "done")
        assert "designer" not in LM.allowance(W.workspace_dir(wid))
        assert "designer" not in c.get("/api/v2/meta").get_json()["public"]["allowance"]
    APP.JOBS.clear()

@test
def page_and_notice_show_the_allowance():
    c = visitor(); wid = workspace_of(c); APP.JOBS.clear()
    run_job(wid, "designer", "done")
    a = c.get("/api/v2/meta").get_json()["public"]["allowance"]
    assert a["designer"] == {"limit": 2, "used": 1, "left": 1, "name": "Designer searches"}, a
    assert a["scan"]["left"] == 3 and a["voacap"]["left"] == 3, a
    page = APP.app.test_client().get("/welcome").get_data(as_text=True)
    assert "2 Designer searches, 3 height scans, 3 VOACAP tables" in page, page

# ---------------------------------------------------------------- time budget of a whole Designer search
class FakeScorer:
    """Stands in for the HFTA runs: every run 'costs' PER_RUN seconds; the score prefers a stack centred at 100 ft."""
    PER_RUN = 10.0
    def __init__(self, proj, slug, site, targets, pool, job):
        self.targets, self.idx, self.pat, self.stages = targets, {0.0: "f"}, {}, []
        self.n_fom = self.n_failed = self.n_filled = 0; self.workers = 1
    def calibrate(self, model, bands, c, mode): return self.PER_RUN
    def needed(self, model, bands, cands, mode): return [c for c in cands if c not in self.pat]
    def compute(self, keys, label):
        self.stages.append({"stage": label, "runs": len(keys)})
        for k in keys: self.pat[k] = 1
    def score(self, model, bands, c, mode):
        v = round(-abs(sum(c) / len(c) - 100) / 10, 3)
        return {t["id"]: {b: (v, list(c)) for b in bands if b in t["bands"]} for t in self.targets}

def fake_search(search_seconds, per_run):
    proj = P.validate(P.default_project("T")); proj["targets"] = [{"id": "t1", "name": "T", "bands": ["20"], "heading": 0}]
    body = {"site": "s1", "max_height": 200, "groups": [{"name": "Yagis", "el": {"20": 4}, "count": 3, "lo": 20, "hi": 200, "step": 5}]}
    old = (CM.Scorer, CM.aoa_status, CM.SEARCH_SECONDS, FakeScorer.PER_RUN)
    CM.Scorer, CM.aoa_status, CM.SEARCH_SECONDS, FakeScorer.PER_RUN = FakeScorer, (lambda *a: ({}, None)), search_seconds, per_run
    try: return CM.search(proj, "x", body, None, {})
    finally: CM.Scorer, CM.aoa_status, CM.SEARCH_SECONDS, FakeScorer.PER_RUN = old

@test
def without_a_time_budget_the_search_refines_as_before():
    r = fake_search(0, 10.0)
    # 37 heights (20..200 by 5) give C(37,3) = 7,770 layouts, more than the 1,500-run floor of a stage: coarse at 10 ft
    # first, then a fine stage at 5 ft around the 6 best.
    assert r["stats"]["time_cut"] == [] and r["stats"]["coarse_grid"], r["stats"]
    assert [s["stage"].split(",")[0] for s in r["stats"]["stages"]] == ["Yagis: coarse search", "Yagis: fine search at 5 ft"], r["stats"]["stages"]

@test
def a_time_budget_refines_fewer_layouts_or_stops():
    # The coarse stage has 455 layouts (10 ft grid). Refining at 5 ft needs 86 new runs around the 6 best layouts,
    # 41 around the 3 best and 11 around the best one (computed with group_candidates and refine). Budget 600 s.
    # 10 s a run: 860 s does not fit, 410 s does: the 3 best are refined.
    r = fake_search(600, 10.0)
    assert r["stats"]["time_cut"] == [{"group": "Yagis", "step": 5.0, "top": 3}], r["stats"]["time_cut"]
    assert r["stats"]["search_seconds"] == 600 and r["rows"], r["stats"]
    # 20 s a run: 1,720 s and 820 s do not fit, 220 s does: only the best one is refined.
    r = fake_search(600, 20.0)
    assert r["stats"]["time_cut"] == [{"group": "Yagis", "step": 5.0, "top": 1}], r["stats"]["time_cut"]
    # 100 s a run: even one layout (1,100 s) does not fit: the fine stage is skipped and the 10 ft result is kept.
    r = fake_search(600, 100.0)
    assert r["stats"]["time_cut"] == [{"group": "Yagis", "step": 10.0, "stopped": True}], r["stats"]["time_cut"]
    assert len(r["stats"]["stages"]) == 1 and r["rows"] and all(h % 10 == 0 for h in r["rows"][0]["layout"][0]), r["rows"][0]

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
