"""ARRL elevation-angle (.PRN) files on a public copy: a visitor's files stay in their own workspace, the notices are
shown, and PRN_UPLOAD=off refuses ARRL files. Run: python tests/test_arrl_files.py (no native core needed)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-arrl-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
os.environ.pop("APP_PASSWORD", None); os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None)
os.environ.pop("PRN_UPLOAD", None); os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
from core import limits as LM, project as P, workspaces as W

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

ORIGIN = {"Origin": "http://localhost"}
LM.CFG["new_workspaces_per_day"] = 1000
SAMPLE = (REPO / "samples" / "TEST-ONLY-synthetic.PRN").read_bytes()      # synthetic data: not an ARRL file
NAME = "TEST-ONLY-synthetic.PRN"

def visitor():
    c = APP.app.test_client(); assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302; return c
def workspace_of(c):
    with c.session_transaction() as s: return s["ws"]
def new_project(c, name="P"): return c.post("/api/v2/projects", json={"name": name}, headers=ORIGIN).get_json()["slug"]
def upload(c, slug): return c.post(f"/api/v2/p/{slug}/prn", data={"files": (io.BytesIO(SAMPLE), NAME)}, headers=ORIGIN)
def copies(): return [p for p in DATA.rglob(NAME)]
def make_zip(with_prn=True):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("project.json", json.dumps(P.default_project("Imported")))
        if with_prn: z.writestr(f"prn/{NAME}", SAMPLE)
    return b.getvalue()
def py(code):
    e = {k: v for k, v in os.environ.items() if k not in ("PUBLIC_MODE", "PRN_UPLOAD")}
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(REPO)],
                       check=False, capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

@test
def the_page_tells_the_visitor_what_happens_to_their_files():
    c = APP.app.test_client()
    assert "Upload only files you are entitled to use" in c.get("/welcome").get_data(as_text=True)
    js = (REPO / "static" / "v2.js").read_text(encoding="utf-8")
    assert "Upload only files you are entitled to use" in js and "are never shared or listed" in js
    c = visitor()
    pub = c.get("/api/v2/meta").get_json()["public"]
    assert {k: pub[k] for k in ("prn_upload", "expiry_days", "workspace_mb", "projects")} == {"prn_upload": True, "expiry_days": 30, "workspace_mb": 50, "projects": 5}, pub
    assert set(pub["allowance"]) == {"designer", "scan", "voacap"}, pub          # v1.1.1: the allowance (tests/test_allowance.py)

@test
def a_copy_that_is_not_public_answers_as_before():
    assert py("import app; c = app.app.test_client(); print('public' in c.get('/api/v2/meta').get_json())") == "False"

@test
def an_uploaded_file_stays_in_the_workspace_of_its_owner():
    a, b = visitor(), visitor(); sa, sb = new_project(a), new_project(b)
    r = upload(a, sa); assert r.status_code == 200 and r.get_json()[0]["file"] == NAME and "error" not in r.get_json()[0]
    where = copies(); assert len(where) == 1
    assert W.workspace_dir(workspace_of(a)) in where[0].parents                       # only in A's workspace folder
    assert a.get(f"/api/v2/p/{sa}/prn/{NAME}").status_code == 200
    assert b.get(f"/api/v2/p/{sb}/prn/{NAME}").status_code != 200                     # B cannot read it, even in a project of the same name
    assert b.get(f"/api/v2/p/{sa}/prn/{NAME}").status_code == 404
    assert NAME not in json.dumps(b.get("/api/v2/library").get_json())
    a.post(f"/api/v2/p/{sa}/prn/to-library", headers=ORIGIN)                          # A's library is A's own
    assert NAME in json.dumps(a.get("/api/v2/library").get_json()) and NAME not in json.dumps(b.get("/api/v2/library").get_json())
    assert all(W.workspace_dir(workspace_of(a)) in p.parents for p in copies())      # still nothing outside A's workspace

@test
def the_file_is_deleted_with_the_workspace():
    assert copies()
    removed = W.cleanup(now=time.time() + 40 * 86400)
    assert removed and copies() == []

@test
def a_public_copy_can_refuse_arrl_files():
    os.environ["PRN_UPLOAD"] = "off"
    try:
        c = visitor(); slug = new_project(c)
        assert c.get("/api/v2/meta").get_json()["public"]["prn_upload"] is False
        r = upload(c, slug)
        assert r.status_code == 403 and "does not accept ARRL" in r.get_json()["error"] and copies() == []
        assert c.post(f"/api/v2/p/{slug}/library/prn", headers=ORIGIN).status_code == 403
        # a project zip made elsewhere comes in without its .PRN files
        r = c.post("/api/v2/projects/import", data={"file": (io.BytesIO(make_zip()), "p.zip")}, headers=ORIGIN)
        assert r.status_code == 200 and copies() == []
    finally:
        os.environ.pop("PRN_UPLOAD", None)

@test
def with_the_default_a_project_zip_keeps_its_prn_files():
    c = visitor()
    r = c.post("/api/v2/projects/import", data={"file": (io.BytesIO(make_zip()), "p.zip")}, headers=ORIGIN)
    assert r.status_code == 200 and len(copies()) == 1
    assert W.workspace_dir(workspace_of(c)) in copies()[0].parents

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
