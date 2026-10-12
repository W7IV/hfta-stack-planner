"""Accounts on a hosted copy: login, admin user management, one project store per user, jobs private to their owner.
Run: python tests/test_accounts.py (no native core needed)."""
import json, os, sys, tempfile, time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-acc-"))
os.environ["PROJECTS_DIR"] = str(TMP / "data" / "projects"); os.environ["APP_PASSWORD"] = "admin-secret-1"
os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None); os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
from core import project as P, users as U

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

def client(): return APP.app.test_client()

def login(c, user, pw):
    return c.post("/login", data={"user": user, "password": pw, "next": "/"}, headers={"Origin": "http://localhost"})

@test
def pages_need_login():
    c = client()
    r = c.get("/"); assert r.status_code == 302 and "/login" in r.headers["Location"]
    r = c.get("/api/v2/meta"); assert r.status_code == 401 and r.get_json()["login"]
    assert c.get("/healthz").status_code == 200 and c.get("/login").status_code == 200
    assert c.get("/static/v2.css").status_code == 200

@test
def admin_logs_in_and_manages_users():
    c = client()
    assert login(c, "admin", "wrong").status_code == 401
    r = login(c, "admin", "admin-secret-1"); assert r.status_code == 302 and r.headers["Location"].endswith("/")
    assert c.get("/").status_code == 200 and c.get("/api/whoami").get_json() == {"user": "admin", "admin": True, "accounts": True}
    assert c.get("/admin").status_code == 200
    r = c.post("/admin/users", data={"action": "create", "name": "DL1ABC", "password": "letmein-99"}); assert r.status_code == 302
    assert [u["name"] for u in U.listing()] == ["dl1abc"]
    r = c.post("/admin/users", data={"action": "create", "name": "x", "password": "short"}); assert "Not+done" in r.headers["Location"] or "Not%20done" in r.headers["Location"]
    r = c.post("/admin/users", data={"action": "create", "name": "admin", "password": "letmein-99"}); assert "administrator" in r.headers["Location"].replace("%20", " ").replace("+", " ")
    assert P.user_root("dl1abc").exists()

@test
def users_have_separate_stores():
    a = client(); login(a, "admin", "admin-secret-1")
    slug = a.post("/api/v2/projects", json={"name": "Canaan"}).get_json()["slug"]
    assert (P.BASE_ROOT / slug / "project.json").exists()
    u = client(); r = login(u, "dl1abc", "letmein-99"); assert r.status_code == 302
    assert u.get("/api/whoami").get_json()["admin"] is False and u.get("/admin").status_code == 403
    assert u.get("/api/v2/meta").get_json()["projects"] == []                  # cannot see the admin's project
    assert u.get(f"/api/v2/p/{slug}").status_code == 404
    s2 = u.post("/api/v2/projects", json={"name": "Duesseldorf"}).get_json()["slug"]
    assert (P.user_root("dl1abc") / s2 / "project.json").exists() and not (P.BASE_ROOT / s2).exists()
    assert a.get("/api/v2/meta").get_json()["projects"] == [slug]
    # library is per user too
    assert u.get("/api/v2/library").get_json()["prns"] == []
    # a project id that climbs out of the store is refused
    assert u.get("/api/v2/p/..%2F..%2F" + slug).status_code in (400, 404)

@test
def jobs_are_private():
    a = client(); login(a, "admin", "admin-secret-1")
    slug = a.get("/api/v2/meta").get_json()["projects"][0]
    proj = a.get(f"/api/v2/p/{slug}").get_json()["project"]; proj["sites"] = [{"id": "s1", "name": "S"}]
    assert a.put(f"/api/v2/p/{slug}", json=proj).status_code == 200
    a.post(f"/api/v2/p/{slug}/sites/s1/flat")
    jid = a.post(f"/api/v2/p/{slug}/evaluate").get_json()["job"]
    u = client(); login(u, "dl1abc", "letmein-99")
    assert u.get(f"/api/job/{jid}").status_code == 404 and a.get(f"/api/job/{jid}").status_code == 200
    for _ in range(50):
        if a.get(f"/api/job/{jid}").get_json()["state"] != "running": break
        time.sleep(0.2)

@test
def password_change_delete_and_lockout():
    a = client(); login(a, "admin", "admin-secret-1")
    a.post("/admin/users", data={"action": "password", "name": "dl1abc", "password": "new-pass-123"})
    u = client(); assert login(u, "dl1abc", "letmein-99").status_code == 401 and login(u, "dl1abc", "new-pass-123").status_code == 302
    assert u.get("/logout").status_code == 302 and u.get("/api/v2/meta").status_code == 401
    a.post("/admin/users", data={"action": "delete", "name": "dl1abc"})
    assert login(client(), "dl1abc", "new-pass-123").status_code == 401 and P.user_root("dl1abc").exists()
    x = client()
    for _ in range(8): login(x, "admin", "nope")
    assert login(x, "admin", "admin-secret-1").status_code == 429       # locked after repeated failures, even with the right password
    U.clear_failures("127.0.0.1")

@test
def basic_auth_still_works_for_admin():
    import base64
    c = client(); h = {"Authorization": "Basic " + base64.b64encode(b"any:admin-secret-1").decode()}
    assert c.get("/api/v2/meta", headers=h).status_code == 200 and c.get("/api/whoami", headers=h).get_json()["user"] == "admin"
    assert c.get("/api/v2/meta", headers={"Authorization": "Basic " + base64.b64encode(b"any:wrong").decode()}).status_code == 401

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
