"""Anonymous daily usage counts of a public copy (PUBLIC_MODE=1), for the operator's /stats page.

Kept in <DATA_DIR>/stats/usage.json: one entry per day (UTC) with totals only, for example
    {"2026-11-02": {"new_workspaces": 4, "active_workspaces": 9, "queue_waits": 1,
                    "jobs": {"hfta": 6, "designer": 2}, "refused": {"voacap_per_day": 1}}}
The file holds no address, no workspace number, no cookie and no browser details.

Active workspaces are counted once per day. To know whether a workspace was already counted today, the server keeps,
in memory only, a keyed hash of the workspace number. The key is random, made new each day and never written to
disk, so the hashes of one day cannot be linked to another day or to a workspace. After a restart the same workspace
may be counted twice on that day. Nothing is counted on a copy that is not public (ENABLED is False)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time

from . import project as P

ENABLED = False              # set by app.py: True on a public copy
KEEP_DAYS = 400
LOG = logging.getLogger("hfta.stats")
_LOCK = threading.Lock()
_SEEN = {"date": None, "key": b"", "tags": set()}


def path():
    return P.DATA_DIR / "stats" / "usage.json"


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _load() -> dict:
    try:
        d = json.loads(path().read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict):
    path().parent.mkdir(parents=True, exist_ok=True)
    P.write_atomic(path(), json.dumps(d, indent=1, sort_keys=True))


def add(counter: str, n: int = 1, group: str | None = None):
    """Add n to today's counter (inside group, if given). A failure to count never stops the request."""
    if not ENABLED or n <= 0:
        return
    try:
        with _LOCK:
            d = _load()
            day = d.setdefault(_today(), {})
            where = day.setdefault(group, {}) if group else day
            where[counter] = where.get(counter, 0) + n
            for old in sorted(d)[:-KEEP_DAYS]:
                del d[old]
            _save(d)
    except Exception:  # counting must never break the app
        LOG.exception("usage count not saved")


def new_workspace():
    add("new_workspaces")


def active(wid: str):
    """Count a workspace once per day, without keeping its number (see the module text)."""
    if not ENABLED:
        return
    with _LOCK:
        today = _today()
        if _SEEN["date"] != today:
            _SEEN.update(date=today, key=secrets.token_bytes(32), tags=set())
        tag = hmac.new(_SEEN["key"], wid.encode(), hashlib.sha256).digest()[:16]
        if tag in _SEEN["tags"]:
            return
        _SEEN["tags"].add(tag)
    add("active_workspaces")


def job(kind: str, n: int = 1):
    add(kind, n, group="jobs")


def refused(kind: str):
    add(kind or "other", group="refused")


def queued():
    add("queue_waits")


def days(n: int = 30) -> list:
    """The latest n days that have counts, newest first: [(date, counts), ...]."""
    d = _load()
    return [(k, d[k]) for k in sorted(d, reverse=True)[:n]]
