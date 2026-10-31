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
  # Wine's embedded Python needs a valid console/PTY for standard streams.
  HFTA_NO_BROWSER=1 WINEDEBUG=-all script -qec "wine \"$PKG/Start HFTA Stack Planner.exe\"" /dev/null >"$LOG" 2>&1
) &
PID=$!

for attempt in $(seq 1 120); do
  if curl --noproxy '*' --fail --silent --max-time 1 http://127.0.0.1:5055/healthz >/dev/null; then
    echo "PASS: native EXE launched bundled Python, Flask served /healthz on localhost:5055"
    # A second release must NOT open the already-running server as its own app.
    # HFTA_NO_BROWSER=1 prevents a console prompt in this automated negative test.
    DUPLICATE_LOG="$WORK/launcher-duplicate.log"
    if HFTA_NO_BROWSER=1 WINEDEBUG=-all script -qec "wine \"$PKG/Start HFTA Stack Planner.exe\"" /dev/null >"$DUPLICATE_LOG" 2>&1; then
      echo "FAIL: second launcher unexpectedly succeeded against occupied port 5055"
      cat "$DUPLICATE_LOG"
      exit 1
    fi
    if ! grep -q "Port 5055 is already in use" "$DUPLICATE_LOG"; then
      echo "FAIL: second launcher did not explain the occupied port"
      cat "$DUPLICATE_LOG"
      exit 1
    fi
    if ! curl --noproxy '*' --fail --silent --max-time 1 http://127.0.0.1:5055/healthz >/dev/null; then
      echo "FAIL: second launcher interfered with the first instance"
      exit 1
    fi
    echo "PASS: concurrent Windows launcher refuses occupied port without opening an older instance"
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
