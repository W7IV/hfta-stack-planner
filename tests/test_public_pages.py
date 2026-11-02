"""Pages of a public copy: footer on every page, privacy note, operator settings, and no change on other copies.
Run: python tests/test_public_pages.py (no native core needed)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hfta-pages-"))
DATA = TMP / "data"
os.environ["PROJECTS_DIR"] = str(DATA / "projects"); os.environ["PUBLIC_MODE"] = "1"
for k in ("APP_PASSWORD", "RAILWAY_ENVIRONMENT", "HOSTED", "OPERATOR_NAME", "OPERATOR_CONTACT", "PRN_UPLOAD"):
    os.environ.pop(k, None)
os.environ.setdefault("HFTA_WORKERS", "1")
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
import app as APP

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

ORIGIN = {"Origin": "http://localhost"}
FOOTER = ["Public copy operated by Paul F. Merrill, W7IV.", "MIT licence", "https://github.com/W7IV/hfta-stack-planner",
          "Not affiliated with ARRL or the OpenHFTA authors", 'href="/privacy"', "/releases/latest",
          "download the free Windows or Docker version", "OpenStreetMap contributors", "/guide#safety-disclaimer"]

def visitor():
    c = APP.app.test_client(); assert c.post("/welcome", data={"next": "/"}, headers=ORIGIN).status_code == 302; return c
def text(r): return r.get_data(as_text=True)

class env:
    def __init__(self, **kw): self.kw, self.old = kw, {}
    def __enter__(self):
        for k, v in self.kw.items(): self.old[k] = os.environ.get(k); os.environ[k] = v
    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

@test
def every_page_has_the_footer():
    c = APP.app.test_client()
    for path in ("/welcome", "/guide", "/privacy"):                          # pages a new visitor can open
        r = c.get(path); assert r.status_code == 200, path
        for piece in FOOTER: assert piece in text(r), (path, piece)
    v = visitor()
    for path in ("/", "/classic"):                                            # pages that need a workspace
        r = v.get(path); assert r.status_code == 200, path
        for piece in FOOTER: assert piece in text(r), (path, piece)

@test
def the_privacy_page_needs_no_workspace_and_makes_none():
    before = sorted(p.name for p in (DATA / "public").iterdir()) if (DATA / "public").exists() else []
    c = APP.app.test_client(); assert c.get("/privacy").status_code == 200
    with c.session_transaction() as s: assert "ws" not in s
    after = sorted(p.name for p in (DATA / "public").iterdir()) if (DATA / "public").exists() else []
    assert before == after                                                    # reading the note makes no workspace

@test
def the_privacy_page_says_what_happens_to_data():
    t = text(APP.app.test_client().get("/privacy"))
    for piece in ("30 days", "cookie", "signed", "does not ask for or keep your name, e-mail address or password",
                  "Fetch terrain online", "USGS", "OpenStreetMap can see the area you view and your IP address",
                  "access log", "50 MB", "daily totals of use", "no personal data", "No outside analytics service",
                  "entitled to use"):
        assert piece in t, piece
    assert APP.USAGE_COUNTS is True and "does not run any analytics" not in t  # a public copy keeps usage counts and says so

@test
def the_privacy_page_follows_the_usage_counts_and_arrl_settings():
    APP.USAGE_COUNTS = False
    try: t = text(APP.app.test_client().get("/privacy"))
    finally: APP.USAGE_COUNTS = True
    assert "does not run any analytics" in t and "daily totals" not in t     # the text follows the setting
    with env(PRN_UPLOAD="off"):
        t = text(APP.app.test_client().get("/privacy"))
    assert "does not accept ARRL" in t and "entitled to use" not in t

@test
def operator_and_contact_come_from_settings_and_are_escaped():
    c = APP.app.test_client()
    with env(OPERATOR_NAME="Test Operator", OPERATOR_CONTACT="<b>info@example.invalid</b>"):
        t = text(c.get("/guide"))
        assert "Public copy operated by Test Operator (&lt;b&gt;info@example.invalid&lt;/b&gt;)." in t and "<b>info@" not in t
        assert "write to &lt;b&gt;info@example.invalid&lt;/b&gt;" in text(c.get("/privacy"))
    t = text(c.get("/privacy"))
    assert "write to" not in t                                                # without a contact the sentence is left out

@test
def the_map_credit_and_the_notices_are_in_the_page_script():
    assert "OpenStreetMap contributors" in (REPO / "static" / "site-map.js").read_text(encoding="utf-8")
    js = (REPO / "static" / "v2.js").read_text(encoding="utf-8")
    assert "This is a public copy" in js and "Upload only files you are entitled to use" in js

@test
def the_readme_describes_the_public_copy():
    md = (REPO / "README.md").read_text(encoding="utf-8")
    assert "## Public copy (`PUBLIC_MODE=1`)" in md and "`/privacy`" in md and "`OPERATOR_CONTACT`" in md
    assert "keep any password-protected hosted copy private" in md and "There is no automatic retention or deletion" not in md

@test
def another_copy_has_no_footer_and_no_privacy_page():
    code = ("import app; c = app.app.test_client()\n"
            "pages = [c.get(p).get_data(as_text=True) for p in ('/guide', '/classic', '/')]\n"
            "print(any('Public copy operated' in t for t in pages), c.get('/privacy').status_code, c.get('/welcome').status_code)")
    e = {k: v for k, v in os.environ.items() if k != "PUBLIC_MODE"}
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(REPO)],
                       check=False, capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False 404 302", r.stdout                       # /welcome only sends the visitor to /

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
    if APP.POOL is not None: APP.POOL.shutdown(wait=True, cancel_futures=True)
