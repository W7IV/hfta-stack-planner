"""User accounts for a hosted copy. Stored in <DATA_DIR>/users.json: name, password hash (scrypt), created.
The administrator is the holder of APP_PASSWORD (user name "admin"); the admin's projects are the base store, every
other user has a store of their own under <DATA_DIR>/users/<name>/projects. Without APP_PASSWORD there are no
accounts: the app runs for one person on their own computer, as before."""
from __future__ import annotations
import hashlib, hmac, json, os, re, secrets, threading, time
from pathlib import Path
from . import project as P

ADMIN = "admin"
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,30}")
_LOCK = threading.Lock()

def users_file() -> Path: return P.DATA_DIR / "users.json"

def _load() -> dict:
    f = users_file()
    return json.loads(f.read_text()) if f.exists() else {}

def _save(d: dict):
    P.write_atomic(users_file(), json.dumps(d, indent=1))

def valid_name(name) -> str:
    n = str(name or "").strip().lower()
    if not NAME_RE.fullmatch(n): raise ValueError("User name: 2-31 characters, letters, digits, '-' or '_'")
    if n == ADMIN: raise ValueError("'admin' is the administrator")
    return n

def hash_password(pw: str, salt: bytes = None) -> str:
    if len(pw or "") < 8: raise ValueError("Password: at least 8 characters")
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"

def check_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        return hmac.compare_digest(hashlib.scrypt((pw or "").encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex(), h)
    except (ValueError, TypeError):
        return False

def listing() -> list:
    return sorted(({"name": k, "created": v.get("created", "")} for k, v in _load().items()), key=lambda u: u["name"])

def create(name: str, pw: str) -> dict:
    name = valid_name(name)
    with _LOCK:
        d = _load()
        if name in d: raise ValueError(f"User {name} exists")
        d[name] = {"hash": hash_password(pw), "created": time.strftime("%Y-%m-%d")}
        _save(d)
    P.user_root(name).mkdir(parents=True, exist_ok=True)
    return {"name": name}

def set_password(name: str, pw: str):
    name = valid_name(name)
    with _LOCK:
        d = _load()
        if name not in d: raise KeyError(name)
        d[name]["hash"] = hash_password(pw); _save(d)

def delete(name: str):
    """Removes the login only; the user's files stay under users/<name> until the administrator deletes them."""
    name = valid_name(name)
    with _LOCK:
        d = _load(); d.pop(name, None); _save(d)

def authenticate(name: str, pw: str, admin_password: str):
    """Returns the user name for a good login, else None. 'admin' is APP_PASSWORD."""
    name = str(name or "").strip().lower()
    if name == ADMIN:
        return ADMIN if admin_password and hmac.compare_digest(pw or "", admin_password) else None
    u = _load().get(name)
    return name if u and check_password(pw, u["hash"]) else None

def root_for(name: str) -> Path:
    return P.BASE_ROOT if name == ADMIN else P.user_root(name)

def secret_key() -> bytes:
    """Session signing key: SECRET_KEY from the environment, else a random key kept in the data folder so that
    logins survive a restart."""
    env = os.environ.get("SECRET_KEY")
    if env: return env.encode()
    f = P.DATA_DIR / "secret_key"
    if not f.exists():
        P.DATA_DIR.mkdir(parents=True, exist_ok=True); f.write_bytes(secrets.token_bytes(32))
        try: f.chmod(0o600)
        except OSError: pass
    return f.read_bytes()

# ---------------- login attempts: a short lock after repeated failures
_FAILS: dict = {}

def too_many_failures(key: str) -> bool:
    n, until = _FAILS.get(key, (0, 0))
    return n >= 8 and time.time() < until

def note_failure(key: str):
    n, _ = _FAILS.get(key, (0, 0)); _FAILS[key] = (n + 1, time.time() + 300)

def clear_failures(key: str):
    _FAILS.pop(key, None)
