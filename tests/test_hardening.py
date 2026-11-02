"""Hardening of a hosted copy: classic-optimiser jobs belong to their owner, one upload limit, and a login lock-out
that a forged X-Forwarded-For header cannot avoid.
Run: python tests/test_hardening.py (no native core needed)."""
import os, sys, tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-hard-"))
os.environ["PROJECTS_DIR"] = str(TMP / "data" / "projects"); os.environ["APP_PASSWORD"] = "admin-secret-1"
os.environ.pop("RAILWAY_ENVIRONMENT", None); os.environ.pop("HOSTED", None); os.environ.pop("MAX_UPLOAD_MB", None)
os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP
from core import project as P, users as U

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

def client(): return APP.app.test_client()

def login(c, user, pw, headers=None):
    h = {"Origin": "http://localhost"}; h.update(headers or {})
    return c.post("/login", data={"user": user, "password": pw, "next": "/"}, headers=h)

U.create("dl1abc", "letmein-99")
ADMIN = client(); assert login(ADMIN, "admin", "admin-secret-1").status_code == 302
USER = client(); assert login(USER, "dl1abc", "letmein-99").status_code == 302

@test
def classic_job_has_an_owner_and_is_private():
    with APP.app.test_request_context():
        P.set_root(None)                                  # the admin store, as for a logged-in admin
        jid, job = APP.new_search_job()
    assert job["owner"] == str(P.BASE_ROOT)
    job["state"] = "done"
    assert ADMIN.get(f"/api/job/{jid}").status_code == 200
    assert USER.get(f"/api/job/{jid}").status_code == 404
    USER.post(f"/api/job/{jid}/cancel"); assert job["cancel"] is False   # another user cannot cancel it
    ADMIN.post(f"/api/job/{jid}/cancel"); assert job["cancel"] is True

@test
def job_without_owner_is_not_visible_to_anyone():
    APP.JOBS["legacy01"] = {"id": "legacy01", "state": "done", "phase": "", "done": 0, "total": 0,
                            "result": None, "error": None, "cancel": False}
    assert ADMIN.get("/api/job/legacy01").status_code == 404 and USER.get("/api/job/legacy01").status_code == 404
    ADMIN.post("/api/job/legacy01/cancel"); assert APP.JOBS["legacy01"]["cancel"] is False

@test
def one_upload_limit_and_it_is_enforced():
    assert APP.MAX_UPLOAD_MB == 512 and APP.app.config["MAX_CONTENT_LENGTH"] == 512 * 1024 * 1024
    old = APP.app.config["MAX_CONTENT_LENGTH"]
    try:
        APP.app.config["MAX_CONTENT_LENGTH"] = 1000       # a 2000-byte body is over this limit
        r = ADMIN.post("/api/prn-bands", data=b"x" * 2000, content_type="application/json",
                       headers={"Origin": "http://localhost"})
        # Flask refuses the body. This route reports the refusal as a 400 with the message, other routes as 413.
        assert r.status_code == 413 or "Request Entity Too Large" in r.get_data(as_text=True)
        assert r.status_code != 200
    finally:
        APP.app.config["MAX_CONTENT_LENGTH"] = old

@test
def upload_limit_follows_the_setting():
    import subprocess
    env = dict(os.environ, MAX_UPLOAD_MB="5")
    code = "import sys; sys.path.insert(0, sys.argv[1]); import app; print(app.app.config['MAX_CONTENT_LENGTH'])"
    out = subprocess.run([sys.executable, "-c", code, str(REPO)], check=False, capture_output=True, text=True, env=env, timeout=120)
    assert out.stdout.strip() == str(5 * 1024 * 1024), out.stdout + out.stderr

@test
def client_key_ignores_forged_addresses():
    hdr = lambda v: {"X-Forwarded-For": v}
    old = APP.PROXY_HOPS
    try:
        APP.PROXY_HOPS = 1                                # one proxy (Railway) adds the real address on the right
        with APP.app.test_request_context(headers=hdr("1.1.1.1, 7.7.7.7"), environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            assert APP.client_key() == "7.7.7.7"
        with APP.app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            assert APP.client_key() == "10.0.0.1"         # no header: the direct address
        APP.PROXY_HOPS = 0                                # own computer: the header is not trusted at all
        with APP.app.test_request_context(headers=hdr("1.1.1.1"), environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            assert APP.client_key() == "127.0.0.1"
    finally:
        APP.PROXY_HOPS = old

@test
def lockout_cannot_be_avoided_with_a_forged_header():
    old = APP.PROXY_HOPS
    try:
        APP.PROXY_HOPS = 1
        c = client()
        for i in range(8):                                # 8 failures, each with a different forged first address
            login(c, "admin", "nope", {"X-Forwarded-For": f"9.9.9.{i}, 7.7.7.7"})
        r = login(c, "admin", "admin-secret-1", {"X-Forwarded-For": "5.5.5.5, 7.7.7.7"})
        assert r.status_code == 429                       # locked: the trusted address is the same each time
    finally:
        APP.PROXY_HOPS = old; U.clear_failures("7.7.7.7")

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
