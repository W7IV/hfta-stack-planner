"""Limits of a public copy (PUBLIC_MODE=1). On your own computer, or on a password-protected copy, nothing here is
enforced: enabled() is False and the app behaves as before.

Every limit has a default for the public copy and an environment setting to change it:

  LIMIT_JOBS_PER_WORKSPACE      running calculations per workspace                   1
  LIMIT_JOBS_ON_SERVER          calculations that run at the same time on the server  2  (others wait in line)
  LIMIT_QUEUE_LENGTH            calculations that may wait in line                    10
  LIMIT_PROJECTS                projects per workspace                                5
  LIMIT_WORKSPACE_MB            disk space per workspace                              50
  LIMIT_VOACAP_PER_DAY          VOACAP tables (one region = one table) per workspace per day   7
  LIMIT_TERRAIN_PER_DAY         online terrain fetches per workspace per day          20
  LIMIT_NEW_WORKSPACES_PER_DAY  new workspaces per address per day                    10
  LIMIT_MEMORY_PERCENT          share of the memory limit above which no new calculation starts   80
  LIMIT_MEMORY_MB               memory limit in MB; 0 = read it from the container (cgroup) if there is one   0
  LIMIT_TERRAIN_CONCURRENT      online terrain fetches that may run at the same time on the server   2
  LIMIT_DESIGNER_RUNS           Designer searches per workspace, in total             2
  LIMIT_SCAN_RUNS               height scans per workspace, in total                  3
  LIMIT_VOACAP_TABLES           VOACAP tables per workspace, in total                 7

Both VOACAP values are 7 so that one workspace can make a table for each of the 7 regions once (3 until 3 Nov 2026:
a worldwide set was refused). The tables can then be saved to the library and used by every project.

The last three are the allowance of a workspace: the public copy is for trying the planner, and the free Windows or
Docker version is for real work. Only a calculation that finishes is counted; one that stops with an error or is
cancelled is not. The counts are kept in a file in the workspace, so a restart of the server does not reset them.
A negative value means no allowance for that kind (no limit).

Also for the public copy (read in core/compromise.py, core/terrain.py and app.py): STAGE_SECONDS (60),
SEARCH_SECONDS (600), MAX_GROUP_LAYOUTS (50000), MAX_UPLOAD_MB (25), HFTA_WORKERS (2), TERRAIN_CACHE_MB (1000).

PRN_UPLOAD decides about ARRL elevation-angle (.PRN) files, which are copyright ARRL:
  private (default)  a visitor may upload their own files into their own workspace only; they are never shared or
                     listed and are deleted with the workspace
  off                the public copy accepts no ARRL files; visitors make VOACAP tables instead

The daily counts are kept in memory and start again from zero after a restart of the server."""
from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path

PUBLIC_DEFAULTS = {
    "jobs_per_workspace": 1, "jobs_on_server": 2, "queue_length": 10, "projects": 5, "workspace_mb": 50,
    "voacap_per_day": 7, "terrain_per_day": 20, "new_workspaces_per_day": 10, "memory_percent": 80, "memory_mb": 0,
    "terrain_concurrent": 2, "designer_runs": 2, "scan_runs": 3, "voacap_tables": 7,
}
ENV_NAMES = {
    "jobs_per_workspace": "LIMIT_JOBS_PER_WORKSPACE", "jobs_on_server": "LIMIT_JOBS_ON_SERVER",
    "queue_length": "LIMIT_QUEUE_LENGTH", "projects": "LIMIT_PROJECTS", "workspace_mb": "LIMIT_WORKSPACE_MB",
    "voacap_per_day": "LIMIT_VOACAP_PER_DAY", "terrain_per_day": "LIMIT_TERRAIN_PER_DAY",
    "new_workspaces_per_day": "LIMIT_NEW_WORKSPACES_PER_DAY", "memory_percent": "LIMIT_MEMORY_PERCENT",
    "memory_mb": "LIMIT_MEMORY_MB", "terrain_concurrent": "LIMIT_TERRAIN_CONCURRENT",
    "designer_runs": "LIMIT_DESIGNER_RUNS", "scan_runs": "LIMIT_SCAN_RUNS", "voacap_tables": "LIMIT_VOACAP_TABLES",
}
CFG: dict = {}
PUBLIC = False


# Set by app.py so that the usage counts (core/stats.py) see each refusal and each wait in line.
HOOKS: dict = {"refused": None, "queued": None}


def _call_hook(name, *args):
    fn = HOOKS.get(name)
    if fn:
        try:
            fn(*args)
        except Exception:  # a counting error must never change what the visitor sees
            logging.getLogger("hfta.limits").exception("hook %s failed", name)


class LimitError(ValueError):
    """A limit of the public copy was reached. The text is shown to the user as it is. kind names the limit for the
    usage counts."""
    def __init__(self, message: str, status: int = 429, kind: str = "other"):
        super().__init__(message)
        self.status = status
        self.kind = kind
        _call_hook("refused", kind)


def load():
    """Read the settings from the environment. Called once at start-up; tests call it again after changing them."""
    global PUBLIC
    PUBLIC = os.environ.get("PUBLIC_MODE") == "1"
    CFG.clear()
    for key, default in PUBLIC_DEFAULTS.items():
        CFG[key] = int(os.environ.get(ENV_NAMES[key], default))


def enabled() -> bool:
    return PUBLIC


def workers() -> int:
    """Number of calculation processes. HFTA_WORKERS if set. Otherwise the CPU count, but at most 2 on a public copy
    and at most 4 on any other hosted copy: a host reports the CPUs of the whole machine (24 was seen on Railway),
    not the share this service can use."""
    value = os.environ.get("HFTA_WORKERS")
    if value:
        return max(1, int(value))
    cpus = os.cpu_count() or 1
    if PUBLIC:
        return min(cpus, 2)
    if os.environ.get("HOSTED") == "1" or os.environ.get("RAILWAY_ENVIRONMENT"):
        return min(cpus, 4)
    return cpus


def prn_upload_allowed() -> bool:
    return os.environ.get("PRN_UPLOAD", "private").strip().lower() != "off"


def unpacked_limit() -> int:
    """Largest size, in bytes, of a project zip after unpacking."""
    return CFG["workspace_mb"] * 1024 * 1024 if PUBLIC else 500_000_000


# ---------------------------------------------------------------- memory
CGROUP_FILES = [("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes")]


def _read_int(path):
    try:
        text = Path(path).read_text().strip()
        return int(text) if text.isdigit() else None        # the word "max" means no limit
    except (OSError, ValueError):
        return None


def memory_fraction():
    """Memory in use as a share of the limit (0 to 1), or None when it cannot be known (no container limit)."""
    for used_file, limit_file in CGROUP_FILES:
        used = _read_int(used_file)
        if used is None:
            continue
        limit = CFG["memory_mb"] * 1024 * 1024 if CFG["memory_mb"] > 0 else _read_int(limit_file)
        if limit and limit < (1 << 60):
            return used / limit
    return None


def memory_busy() -> bool:
    f = memory_fraction()
    return f is not None and f * 100 >= CFG["memory_percent"]


# ---------------------------------------------------------------- disk
def workspace_bytes(folder: Path) -> int:
    total = 0
    stack = [str(folder)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    else:
                        try:
                            total += e.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
        except OSError:
            pass
    return total


def check_disk(workspace_dir: Path, extra: int = 0):
    limit = CFG["workspace_mb"] * 1024 * 1024
    used = workspace_bytes(workspace_dir)
    if used + (extra or 0) > limit:
        raise LimitError(f"Your workspace is full ({used / 1048576:.0f} MB used of {CFG['workspace_mb']} MB). "
                         "Export a project and delete it, or use the free Windows or Docker version for larger work.", 413,
                         kind="disk")


# ---------------------------------------------------------------- daily counts
_LOCK = threading.Lock()
_DAY = {"date": None, "counts": {}}


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def spend(kind: str, key: str, n: int, limit: int, message: str):
    """Add n to today's count of (kind, key), or refuse with message if that would pass the limit."""
    with _LOCK:
        today = _today()
        if _DAY["date"] != today:
            _DAY["date"], _DAY["counts"] = today, {}
        used = _DAY["counts"].get((kind, key), 0)
        if used + n > limit:
            raise LimitError(message, kind=f"{kind}_per_day")
        _DAY["counts"][(kind, key)] = used + n


_TERRAIN_BUSY = 0


@contextlib.contextmanager
def terrain_slot():
    """Online terrain fetches hold large tiles in memory, so only a few may run at once on a public copy. A fetch
    that finds no free place is refused at once (not queued): the visitor can try again in a minute."""
    global _TERRAIN_BUSY
    if not PUBLIC:
        yield
        return
    with _LOCK:
        if _TERRAIN_BUSY >= CFG["terrain_concurrent"]:
            raise LimitError("The public server is fetching terrain for other visitors. Try again in a minute.",
                             kind="terrain_busy")
        _TERRAIN_BUSY += 1
    try:
        yield
    finally:
        with _LOCK:
            _TERRAIN_BUSY -= 1


# ---------------------------------------------------------------- calculations: one at a time, a line for the rest
class Gate:
    """At most jobs_on_server calculations run at once. The others wait in the order they came. A waiting job can be
    cancelled. When memory is high, the next job waits as long as another job is running (it will free memory);
    with nothing running it starts anyway, so the line can never stand still."""

    def __init__(self):
        self.cv = threading.Condition()
        self.running = 0
        self.waiting: list = []

    def full(self) -> bool:
        with self.cv:
            return len(self.waiting) >= CFG["queue_length"]

    def run(self, job: dict, fn):
        waited = False
        with self.cv:
            self.waiting.append(job)
            while True:
                if job.get("cancel"):
                    self.waiting.remove(job)
                    job["state"], job["error"] = "error", "Cancelled"
                    self.cv.notify_all()
                    return
                first = self.waiting[0] is job
                if first and self.running < CFG["jobs_on_server"] and not (self.running and memory_busy()):
                    self.waiting.pop(0)
                    self.running += 1
                    break
                job["phase"] = f"Waiting in line: position {self.waiting.index(job) + 1} of {len(self.waiting)}"
                if not waited:
                    waited = True
                    _call_hook("queued")
                self.cv.wait(timeout=0.5)
        try:
            fn()
        finally:
            with self.cv:
                self.running -= 1
                self.cv.notify_all()


GATE = Gate()


def check_new_job(owner: str, jobs: dict, workspace_dir: Path):
    """Called before a calculation is registered. Raises LimitError with a plain message."""
    mine = sum(1 for j in jobs.values() if j.get("state") == "running" and j.get("owner") == owner)
    if mine >= CFG["jobs_per_workspace"]:
        raise LimitError("The public server allows one calculation at a time for each workspace. Wait for the running "
                         "one to finish, or cancel it. For larger studies, use the free Windows or Docker version.",
                         kind="one_job_per_workspace")
    if GATE.full():
        raise LimitError("The calculation line on the public server is full. Try again in a few minutes.", kind="queue_full")
    if GATE.running and memory_busy():
        raise LimitError("The public server is using most of its memory. Try again in a few minutes.", kind="memory")
    check_disk(workspace_dir)


# ---------------------------------------------------------------- allowance of a workspace (in total, not per day)
ALLOWANCE = {"designer": ("designer_runs", "Designer searches"), "scan": ("scan_runs", "height scans"),
             "voacap": ("voacap_tables", "VOACAP tables")}
ALLOWANCE_FILE = ".allowance.json"      # in the workspace folder, beside projects/ (never inside a project)


def _allowance_path(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / ALLOWANCE_FILE


def allowance_used(workspace_dir: Path) -> dict:
    """{kind: count} of the calculations this workspace has finished. A missing or damaged file counts as none."""
    try:
        data = json.loads(_allowance_path(workspace_dir).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in ALLOWANCE and isinstance(v, int) and v >= 0}


def allowance(workspace_dir: Path) -> dict:
    """{kind: {"limit", "used", "left", "name"}} for the page. Kinds with no limit (negative setting) are left out."""
    used = allowance_used(workspace_dir)
    out = {}
    for kind, (key, name) in ALLOWANCE.items():
        limit = CFG[key]
        if limit < 0:
            continue
        u = used.get(kind, 0)
        out[kind] = {"limit": limit, "used": u, "left": max(0, limit - u), "name": name}
    return out


def check_allowance(kind: str, n: int, workspace_dir: Path):
    """Refuse a calculation when the workspace has used its allowance of this kind. Called before the job starts."""
    if kind not in ALLOWANCE:
        return
    key, name = ALLOWANCE[kind]
    limit = CFG[key]
    if limit < 0:
        return
    used = allowance_used(workspace_dir).get(kind, 0)
    if used + n > limit:
        left = max(0, limit - used)
        more = f" {left} left; this one needs {n}." if left else ""
        raise LimitError(f"This public copy allows {limit} {name} for each workspace, for trying the planner.{more} "
                         "For more, download the free planner (Windows or Docker) and run it on your own computer. "
                         "Your work comes with you: export the project here (zip) and import it there.",
                         kind=f"allowance_{kind}")


def use_allowance(kind: str, n: int, workspace_dir: Path):
    """Count n finished calculations of this kind. A counting error is logged and never reaches the visitor."""
    if kind not in ALLOWANCE:
        return
    try:
        with _LOCK:
            used = allowance_used(workspace_dir)
            used[kind] = used.get(kind, 0) + n
            path = _allowance_path(workspace_dir)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(used))
            os.replace(tmp, path)
    except Exception:  # a counting error must never change what the visitor sees
        logging.getLogger("hfta.limits").exception("allowance count failed")


def voacap_tables(body: dict) -> int:
    """Number of VOACAP tables a request makes: one per region, or one for a single region or custom points."""
    regions = body.get("regions") if isinstance(body, dict) else None
    return len(regions) if isinstance(regions, list) and regions else 1


# ---------------------------------------------------------------- checks on a request (before the route runs)
def guard_request(req, workspace_id: str, workspace_dir: Path, project_count):
    """Limits that depend on the kind of request: number of projects, size of an upload, terrain fetches, VOACAP tables.
    Only POST requests of a visitor with a workspace come here. project_count is a function: projects now."""
    path = req.path
    if path in ("/api/v2/projects", "/api/v2/projects/import") and project_count() >= CFG["projects"]:
        raise LimitError(f"A workspace holds at most {CFG['projects']} projects. Export a project and delete it "
                         "before you make a new one.", kind="projects")
    if (not prn_upload_allowed() and path.startswith("/api/v2/p/")
            and path.endswith(("/prn", "/library/prn"))):
        raise LimitError("This public server does not accept ARRL elevation-angle (.PRN) files. Make a VOACAP table "
                         "instead (Targets page), or use the free Windows or Docker version.", 403, kind="prn_off")
    if (req.content_type or "").startswith("multipart/") or path == "/api/v2/projects/import":
        check_disk(workspace_dir, req.content_length or 0)
    if path.startswith("/api/v2/p/") and path.endswith("/auto") and "/sites/" in path:
        check_disk(workspace_dir)
        spend("terrain", workspace_id, 1, CFG["terrain_per_day"],
              f"The public server allows {CFG['terrain_per_day']} online terrain fetches a day for each workspace. "
              "Try again tomorrow, or upload your own terrain files.")
    if path.startswith("/api/v2/p/") and path.endswith("/prn/generate"):
        spend("voacap", workspace_id, voacap_tables(req.get_json(silent=True) or {}), CFG["voacap_per_day"],
              f"The public server allows {CFG['voacap_per_day']} VOACAP tables a day for each workspace "
              "(one region is one table). Try again tomorrow, or use the free Windows or Docker version.")


load()
