"""Public mode (PUBLIC_MODE=1): one private workspace per browser, no accounts.

A visitor accepts the notice once. The server makes a random workspace number and keeps it in a signed cookie.
The workspace is the folder <DATA_DIR>/public/<id>/ ; its projects are in <DATA_DIR>/public/<id>/projects.
Nobody can list workspaces. A workspace that is not used for WORKSPACE_EXPIRY_DAYS days (default 30) is deleted by
a clean-up that runs once a day (cleanup, start_cleanup). Only folders named with a workspace number are touched."""
from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path

from . import project as P

ID_RE = re.compile(r"[0-9a-f]{32}")
TOUCH_EVERY = 600          # seconds: the "last used" mark is renewed at most this often
MARK = ".last_used"


def public_dir() -> Path:
    return P.DATA_DIR / "public"


def valid_id(wid) -> bool:
    """True only for a number made by create(): 32 lower-case hexadecimal characters. Nothing else can reach the
    file system, so a damaged or forged cookie cannot point outside the public folder."""
    return isinstance(wid, str) and ID_RE.fullmatch(wid) is not None


def workspace_dir(wid: str) -> Path:
    if not valid_id(wid):
        raise ValueError("Not a workspace number")
    return public_dir() / wid


def root_for(wid: str) -> Path:
    """The project store of a workspace (the same role as users.root_for in password mode)."""
    return workspace_dir(wid) / "projects"


def exists(wid) -> bool:
    return valid_id(wid) and root_for(wid).is_dir()


def create() -> str:
    wid = secrets.token_hex(16)
    root_for(wid).mkdir(parents=True)
    touch(wid, force=True)
    return wid


def touch(wid: str, force: bool = False, now: float | None = None):
    """Record that the workspace was used. The mark is a file; its modification time is the last use."""
    mark = workspace_dir(wid) / MARK
    now = time.time() if now is None else now
    try:
        if force or not mark.exists() or now - mark.stat().st_mtime > TOUCH_EVERY:
            mark.touch()
            os.utime(mark, (now, now))
    except OSError:
        pass                # a failed mark must never stop a request


def last_used(wid: str) -> float:
    d = workspace_dir(wid)
    try:
        return (d / MARK).stat().st_mtime
    except OSError:
        return d.stat().st_mtime


# ---------------------------------------------------------------- clean-up of workspaces that are not used any more
LOG = logging.getLogger("hfta.workspaces")
LAST = {"time": None, "removed": 0, "kept": 0}      # result of the latest clean-up, for the statistics page


def expiry_days() -> int:
    return int(os.environ.get("WORKSPACE_EXPIRY_DAYS", "30"))


def list_ids() -> list:
    """Workspaces on the volume. Only folders whose name is a workspace number count; every other entry in the
    public folder (a file, a folder with another name, a link) is never listed, so it is never deleted."""
    base = public_dir()
    if not base.is_dir():
        return []
    return sorted(e.name for e in os.scandir(base)
                  if valid_id(e.name) and e.is_dir(follow_symlinks=False))


def expired_ids(now: float | None = None) -> list:
    cutoff = (time.time() if now is None else now) - expiry_days() * 86400
    out = []
    for wid in list_ids():
        try:
            if last_used(wid) < cutoff:
                out.append(wid)
        except OSError:
            pass
    return out


def cleanup(running_owners=(), now: float | None = None) -> list:
    """Delete every workspace not used for expiry_days() days, and return their numbers. A workspace with a
    running calculation is kept (running_owners: the project-store paths of the running jobs). The last-use time
    is read again just before deleting, so a visitor who returns during the clean-up keeps the workspace."""
    now = time.time() if now is None else now
    cutoff = now - expiry_days() * 86400
    owners = {str(o) for o in running_owners}
    base = public_dir().resolve()
    removed, kept = [], 0
    for wid in expired_ids(now):
        path = workspace_dir(wid)
        if str(root_for(wid)) in owners or path.resolve().parent != base or os.path.islink(path):
            kept += 1
            continue
        try:
            if last_used(wid) >= cutoff:
                kept += 1
                continue
            shutil.rmtree(path)
            removed.append(wid)
        except OSError as e:
            kept += 1
            LOG.warning("workspace %s not deleted: %s", wid, e)
    LAST.update(time=now, removed=len(removed), kept=kept)
    LOG.info("workspace clean-up: %d deleted, %d expired but kept", len(removed), kept)
    return removed


def start_cleanup(owners_fn, interval: float = 86400, first_delay: float = 120,
                  stop: threading.Event | None = None) -> threading.Thread:
    """Run cleanup() every interval seconds in a background thread (the first time after first_delay seconds).
    owners_fn returns the project-store paths of the running calculations."""
    stop = stop or threading.Event()

    def loop():
        wait = first_delay
        while not stop.wait(wait):
            try:
                cleanup(owners_fn())
            except Exception:  # the loop must survive any error and try again later
                LOG.exception("workspace clean-up failed")
            wait = interval

    t = threading.Thread(target=loop, daemon=True, name="workspace-cleanup")
    t.start()
    return t
