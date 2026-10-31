#!/usr/bin/env bash
# Executed by tools/build_windows.sh on an isolated GitHub Actions/Wine runner.
# Exercises the real distributable native launcher with the bundled Python.
set -euo pipefail
PKG="$1"
WORK="$2"
LOG="$WORK/launcher-smoke.log"
PID=""

cleanup() {
  if [ -n "$PID" ]; then kill "$PID" 2>/dev/null || true; fi
  # This test runs on a dedicated CI Wine environment.
  wineserver -k >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting packaged Windows EXE under Wine (no batch file)"
(
  cd "$PKG"
  HFTA_NO_BROWSER=1 WINEDEBUG=-all wine "$PKG/Start HFTA Stack Planner.exe" >"$LOG" 2>&1
) &
PID=$!

for attempt in $(seq 1 120); do
  if curl --noproxy '*' --fail --silent --max-time 1 http://127.0.0.1:5055/healthz >/dev/null; then
    echo "PASS: native EXE launched bundled Python, Flask served /healthz on localhost:5055"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "FAIL: launcher process exited before Flask accepted connections"
    cat "$LOG"
    exit 1
  fi
  sleep 0.25
done

echo "FAIL: packaged launcher did not make /healthz available"
cat "$LOG"
exit 1
