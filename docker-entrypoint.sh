#!/bin/sh
# Starts the planner as the unprivileged user "planner". The container starts as root only to make the data volume
# writable by that user (a mounted volume belongs to root), then drops root for good with setpriv.
set -e
DATA_DIR="${PROJECTS_DIR%/projects}"
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$PROJECTS_DIR"
    chown planner:planner "$DATA_DIR" "$PROJECTS_DIR" 2>/dev/null || true
    # Files written by earlier root-run versions: make them writable for the new user (one-time, fast on small sets).
    find "$DATA_DIR" ! -user planner -exec chown planner:planner {} + 2>/dev/null || true
    exec setpriv --reuid=planner --regid=planner --init-groups --inh-caps=-all "$@"
fi
exec "$@"
