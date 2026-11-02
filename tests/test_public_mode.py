"""Public mode (PUBLIC_MODE=1): no accounts, one private workspace per browser, no administrator page.
Run: python tests/test_public_mode.py (no native core needed)."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-pub-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
os.environ.pop("APP_PASSWORD", None); os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None)
os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
from core import project as P, workspaces as W

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

ORIGIN = {"Origin": "http://localhost"}
def client(): return APP.app.test_client()
def accept(c, nxt="/"): return c.post("/welcome", data={"next": nxt}, headers=ORIGIN)
def workspace_of(c):
    with c.session_transaction() as s: return s.get("ws")

@test
def starts_without_a_password_and_is_in_public_mode():
    assert APP.PUBLIC_MODE is True and APP.APP_PASSWORD == ""
    assert client().get("/healthz").status_code == 200

@test
def public_mode_with_a_password_refuses_to_start():
    code = "import sys; sys.path.insert(0, sys.argv[1]); import app"
    env = dict(os.environ, APP_PASSWORD="x-secret-1234")
    r = subprocess.run([sys.executable, "-c", code, str(REPO)], check=False, capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode != 0 and "PUBLIC_MODE=1 and APP_PASSWORD" in (r.stdout + r.stderr), r.stderr

@test
def hosted_public_copy_starts_without_a_password():
    code = "import sys; sys.path.insert(0, sys.argv[1]); import app; print('started', app.PUBLIC_MODE)"
    env = dict(os.environ, HOSTED="1", RAILWAY_ENVIRONMENT="production")
    r = subprocess.run([sys.executable, "-c", code, str(REPO)], check=False, capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0 and "started True" in r.stdout, r.stdout + r.stderr

@test
def first_visit_goes_to_the_notice_page():
    c = client()
    r = c.get("/"); assert r.status_code == 302 and r.headers["Location"].startswith("/welcome")
    r = c.get("/api/v2/meta"); assert r.status_code == 401 and r.get_json()["login"] is True
    r = c.get("/classic"); assert r.status_code == 302 and r.headers["Location"].startswith("/welcome")
    r = c.get("/login"); assert r.status_code == 302 and r.headers["Location"].startswith("/welcome")
    r = c.get("/welcome"); assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "I understand" in text and "Planning estimates only" in text and "30 days" in text
    assert c.get("/guide").status_code == 200 and c.get("/static/v2.css").status_code == 200
    assert not (DATA / "public").exists() or not list((DATA / "public").iterdir())    # a visit alone makes no workspace

@test
def accepting_makes_a_workspace_and_a_signed_cookie():
    c = client()
    r = accept(c, "/"); assert r.status_code == 302 and r.headers["Location"] == "/"
    wid = workspace_of(c)
    assert W.valid_id(wid) and (DATA / "public" / wid / "projects").is_dir() and (DATA / "public" / wid / W.MARK).exists()
    assert c.get("/").status_code == 200 and c.get("/api/v2/meta").status_code == 200
    assert c.get("/welcome").status_code == 302                       # already has a workspace
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert c.get("/api/whoami").get_json() == {"user": None, "admin": False, "accounts": False, "public": True}
    assert accept(c).status_code == 302 and workspace_of(c) == wid    # accepting again keeps the same workspace

@test
def two_browsers_cannot_see_each_other():
    a, b = client(), client(); accept(a); accept(b)
    assert workspace_of(a) != workspace_of(b)
    slug = a.post("/api/v2/projects", json={"name": "Canaan"}, headers=ORIGIN).get_json()["slug"]
    assert (DATA / "public" / workspace_of(a) / "projects" / slug / "project.json").exists()
    assert a.get("/api/v2/meta").get_json()["projects"] == [slug]
    assert b.get("/api/v2/meta").get_json()["projects"] == []
    assert b.get(f"/api/v2/p/{slug}").status_code == 404
    # a job made by A is not visible to B
    with APP.app.test_request_context():
        P.set_root(W.root_for(workspace_of(a)))                       # a job started in A's workspace
        jid, job = APP.new_search_job()
    job["state"] = "done"
    assert a.get(f"/api/job/{jid}").status_code == 200 and b.get(f"/api/job/{jid}").status_code == 404
    b.post(f"/api/job/{jid}/cancel", headers=ORIGIN); assert job["cancel"] is False
    assert not (DATA / "projects" / slug).exists()                    # the base store is never used

@test
def there_is_no_administrator_page():
    c = client()
    for path in ("/admin", "/admin/users"):
        assert c.get(path).status_code == 404                         # without a workspace
    accept(c)
    for path in ("/admin", "/admin/users"):
        assert c.get(path).status_code == 404                         # with one
    assert c.post("/admin/users", data={"action": "create", "name": "x1", "password": "letmein-99"}, headers=ORIGIN).status_code == 404

@test
def a_damaged_or_expired_cookie_is_not_a_workspace():
    c = client(); accept(c); wid = workspace_of(c)
    with c.session_transaction() as s: s["ws"] = "../../projects"      # a signed cookie that points outside
    assert c.get("/api/v2/meta").status_code == 401
    with c.session_transaction() as s: s["ws"] = "0" * 32              # well formed, but no such workspace
    assert c.get("/api/v2/meta").status_code == 401
    r = c.get("/"); assert r.status_code == 302 and r.headers["Location"].startswith("/welcome")
    with c.session_transaction() as s: s["ws"] = wid
    assert c.get("/api/v2/meta").status_code == 200
    forged = client(); forged.set_cookie("session", "not-a-signed-value")
    assert forged.get("/api/v2/meta").status_code == 401

@test
def next_address_stays_on_this_server():
    c = client()
    assert accept(c, "//evil.example/x").headers["Location"] == "/"
    c2 = client(); assert accept(c2, "https://evil.example/").headers["Location"] == "/"
    c3 = client(); assert accept(c3, "/guide").headers["Location"] == "/guide"

@test
def notice_page_refuses_posts_from_other_sites():
    c = client()
    r = c.post("/welcome", data={}, headers={"Origin": "http://evil.example"}); assert r.status_code == 403

@test
def workspace_ids_and_the_last_used_mark():
    assert not W.valid_id("../x") and not W.valid_id("A" * 32) and not W.valid_id(None) and not W.valid_id("a" * 31)
    wid = W.create(); d = W.workspace_dir(wid)
    old = time.time() - 40 * 86400                                    # 40 days ago
    os.utime(d / W.MARK, (old, old)); assert abs(W.last_used(wid) - old) < 2
    W.touch(wid, now=old + 100); assert abs(W.last_used(wid) - old) < 2   # only 100 s after the mark: left alone (limit 600 s)
    W.touch(wid); assert time.time() - W.last_used(wid) < 5           # a mark 40 days old is renewed

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
