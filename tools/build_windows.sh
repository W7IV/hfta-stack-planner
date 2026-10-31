#!/bin/bash
# Builds the Windows package of the HFTA Stack Planner on a Linux machine (no Windows needed):
#   runtime/   Python 3.12 for Windows (python-build-standalone) with the pinned wheels
#   app/       this repository (working tree, without .git)
#   openhfta/  hfta.py + OpenYTWCore.dll cross-compiled with MinGW gfortran from the pinned OpenHFTA commit
#   voacap/    voacapl.exe cross-compiled with MinGW + its data folder (coefficient binaries made by the Windows tools under Wine)
#   Start HFTA Stack Planner.exe (native launcher), README-Windows.txt
# Needs: gfortran-mingw-w64-x86-64, gcc-mingw-w64-x86-64, automake, autoconf, wine (the package that provides the `wine` command; wine64 alone does not), python3 + pip, curl, zip.
# Usage: tools/build_windows.sh [output dir]   -> HFTA-Stack-Planner-windows-<version>.zip
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd); OUT=${1:-"$REPO/dist"}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)   # absolute: the zip is written from another directory
WORK=${WORK:-/tmp/hfta-winbuild}; PKG="$WORK/HFTA-Stack-Planner"; rm -rf "$PKG"; mkdir -p "$WORK" "$PKG"
OPENHFTA_COMMIT=${OPENHFTA_COMMIT:-7d62e863f1d27372c97df3ac6ef53092fb58bd50}
VOACAPL_COMMIT=${VOACAPL_COMMIT:-c12a98b}
PBS_URL=${PBS_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20241219/cpython-3.12.8%2B20241219-x86_64-pc-windows-msvc-install_only.tar.gz}
VERSION=$(git -C "$REPO" describe --tags --always 2>/dev/null || echo dev)
export WINEDEBUG=-all
for t in x86_64-w64-mingw32-gfortran x86_64-w64-mingw32-gcc autoreconf wine winepath script curl pip zip; do
  command -v "$t" >/dev/null || { echo "missing tool: $t (on Ubuntu: apt-get install gfortran-mingw-w64-x86-64 gcc-mingw-w64-x86-64 automake autoconf wine zip python3-pip)"; exit 1; }
done
wineboot -u >/dev/null 2>&1 || true   # first run creates the Wine prefix; done here so its messages do not land in the build output
# Wine's Python needs a terminal for its standard streams; `script` provides one when the build runs unattended.
wpy() { script -qec "wine \"$PKG/runtime/python.exe\" $*" /dev/null | tr -d '\r'; }

echo "== Python runtime"
[ -f "$WORK/pbs.tgz" ] || curl -sSL -o "$WORK/pbs.tgz" "$PBS_URL"
tar xzf "$WORK/pbs.tgz" -C "$PKG" && mv "$PKG/python" "$PKG/runtime"
mkdir -p "$WORK/wheels"
pip download -q --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp -d "$WORK/wheels" -r "$REPO/tools/requirements-windows.txt"
wpy -m pip install -q --no-index --find-links "$WORK/wheels" --no-warn-script-location -r "$REPO/tools/requirements-windows.txt"
CHECK=$(wpy -m pip check); echo "$CHECK" | grep -q "No broken requirements" || { echo "$CHECK"; exit 1; }
rm -rf "$PKG"/runtime/Lib/site-packages/pip* "$PKG"/runtime/Scripts "$PKG"/runtime/include "$PKG"/runtime/libs \
      "$PKG"/runtime/Lib/test "$PKG"/runtime/Lib/idlelib "$PKG"/runtime/Lib/tkinter "$PKG"/runtime/Lib/turtledemo "$PKG"/runtime/tcl \
      "$PKG"/runtime/DLLs/_tkinter.pyd "$PKG"/runtime/DLLs/tcl86t.dll "$PKG"/runtime/DLLs/tk86t.dll
find "$PKG/runtime" -name "*.pdb" -delete; find "$PKG/runtime" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "== OpenHFTA core (DLL)"
[ -d "$WORK/openhfta" ] || git clone -q https://github.com/RioDXGroup/openhfta.git "$WORK/openhfta"
git -C "$WORK/openhfta" checkout -q "$OPENHFTA_COMMIT"
mkdir -p "$WORK/openhfta/build/win64" "$PKG/openhfta"
FF="-O0 -g -mfpmath=387 -fexcess-precision=fast -ffast-math -fno-associative-math -fno-reciprocal-math -fcheck=all -ffree-line-length-none"
for f in "$WORK"/openhfta/src/*.f90; do x86_64-w64-mingw32-gfortran $FF -c -o "$WORK/openhfta/build/win64/$(basename "${f%.f90}").o" "$f"; done
printf 'LIBRARY OpenYTWCore\nEXPORTS\n  YTWCore1=ytwcore1_\n  ytwcore1_=ytwcore1_\n' > "$WORK/OpenYTWCore.def"
x86_64-w64-mingw32-gfortran $FF -shared -o "$PKG/openhfta/OpenYTWCore.dll" "$WORK"/openhfta/build/win64/*.o -Wl,"$WORK/OpenYTWCore.def" -static -static-libgfortran -static-libgcc
cp "$WORK/openhfta/hfta.py" "$PKG/openhfta/"; cp "$WORK"/openhfta/LICENSE* "$PKG/openhfta/" 2>/dev/null || true
echo "$OPENHFTA_COMMIT" > "$PKG/openhfta/COMMIT"

echo "== VOACAP (voacapl.exe)"
rm -rf "$WORK/voacapl"; git clone -q https://github.com/jawatson/voacapl.git "$WORK/voacapl"; git -C "$WORK/voacapl" checkout -q "$VOACAPL_COMMIT"
( cd "$WORK/voacapl" && autoreconf -fi >/dev/null 2>&1 && ./configure --host=x86_64-w64-mingw32 --prefix="$WORK/vcwin" FC=x86_64-w64-mingw32-gfortran F77=x86_64-w64-mingw32-gfortran CC=x86_64-w64-mingw32-gcc FCFLAGS="-O2 -static" FFLAGS="-O2 -static" LDFLAGS="-static" >/dev/null && make -j4 >/dev/null && make install >/dev/null 2>&1 || true )
mkdir -p "$PKG/voacap/bin"; cp "$WORK/voacapl/src/voacapw/voacapl.exe" "$PKG/voacap/bin/"
cp -r "$WORK/vcwin/share/voacapl/itshfbc" "$PKG/voacap/itshfbc"
cp "$WORK/voacapl/COPYING" "$WORK/voacapl/AUTHORS" "$PKG/voacap/"
rm -f "$PKG"/voacap/itshfbc/coeffs/*.bin "$PKG"/voacap/itshfbc/coeffs/*.da "$PKG"/voacap/itshfbc/coeffs/*.daw
WPATH=$(winepath -w "$PKG/voacap/itshfbc/coeffs")
for x in coeffbin coefbinw fof2bin fof2binw; do wine "$WORK/vcwin/bin/$x.exe" "$WPATH" >/dev/null 2>&1; done
find "$PKG/voacap" \( -name "*.exe" -o -name "*.o" -o -name "Makefile*" -o -name "*.f" \) ! -path "*/bin/voacapl.exe" -delete
[ "$(ls "$PKG"/voacap/itshfbc/coeffs/*.bin | wc -l)" -ge 24 ] || { echo "coefficient binaries missing"; exit 1; }

echo "== app"
mkdir -p "$PKG/app" "$PKG/data/projects"
( cd "$REPO" && tar c --exclude=.git --exclude=__pycache__ --exclude=projects --exclude=COMMIT --exclude=dist --exclude=Dockerfile --exclude=docker-entrypoint.sh . ) | tar x -C "$PKG/app"
cp "$REPO/tools/windows/README-Windows.txt" "$PKG/"
echo "== native Windows launcher (no batch interpreter)"
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror -municode \
  "$REPO/tools/windows/launcher.c" -o "$PKG/Start HFTA Stack Planner.exe" \
  -lws2_32 -lshell32
test -s "$PKG/Start HFTA Stack Planner.exe"
echo "$VERSION" > "$PKG/VERSION"

echo "== check: the Windows build must still match the original HFTA (under Wine)"
# (script gives Wine a terminal; without one Python cannot open its standard streams)
( cd "$PKG" && OPENHFTA_DIR="$(winepath -w "$PKG/openhfta")" wpy app/tests/test_hfta_match.py | tee "$WORK/check.log" | tail -2 )
grep -q "PASS: matches the original HFTA" "$WORK/check.log"

echo "== launcher smoke test (native EXE -> bundled Python -> loopback HTTP)"
# This runs the distributed EXE, not the legacy batch script, and validates /healthz.
# No shell or browser is invoked by the program. Wine runs only in CI/build.
bash "$REPO/tools/windows/test_launcher.sh" "$PKG" "$WORK"

echo "== bundled Python license inventory"
mkdir -p "$PKG/licenses/runtime"
# Preserve original Python-build-standalone license metadata/files (and the CRT notice if present).
find "$PKG/runtime" -maxdepth 3 -type f \( -iname '*license*' -o -iname '*licence*' -o -iname '*copyright*' -o -name 'PYTHON.json' -o -iname '*notice*' \) -print > "$WORK/runtime-license-file-list.txt"
( cd "$PKG" && wpy app/tools/license_inventory.py licenses/runtime )
cp "$REPO/THIRD_PARTY_NOTICES.md" "$PKG/licenses/"
cp "$REPO/licenses/PLOTLY-MIT.txt" "$PKG/licenses/"
cp "$REPO/LICENSE" "$PKG/"
cp "$REPO/DISCLAIMER.md" "$PKG/"
if [ -f "$PKG/runtime/LICENSE" ]; then cp "$PKG/runtime/LICENSE" "$PKG/licenses/runtime/PYTHON-LICENSE.txt"; fi
if [ -f "$PKG/runtime/PC/crtlicense.txt" ]; then cp "$PKG/runtime/PC/crtlicense.txt" "$PKG/licenses/runtime/PYTHON-CRT-LICENSE.txt"; fi
test -s "$PKG/licenses/runtime/python-dependencies.json"
test -s "$PKG/licenses/runtime/PYTHON-DEPENDENCIES.md"
echo "== zip"
ZIP="$OUT/HFTA-Stack-Planner-windows-$VERSION.zip"; rm -f "$ZIP"
( cd "$WORK" && zip -qr "$ZIP" "HFTA-Stack-Planner" )
ls -la "$ZIP"
