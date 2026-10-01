#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
cd "$ROOT"

[[ "$(uname -m)" == "arm64" ]] || { print -u2 'Requires an Apple Silicon arm64 builder.'; exit 1; }
OS_VERSION="$(sw_vers -productVersion)"
OS_MAJOR="${OS_VERSION%%.*}"
[[ "$OS_MAJOR" -ge 15 ]] || {
  print -u2 'Requires macOS 15.0 or newer.'; exit 1;
}

PYTHON_BIN="${PYTHON_BIN:-/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12}"
[[ -x "$PYTHON_BIN" ]] || { print -u2 "Python 3.12 not found: $PYTHON_BIN (install Python.org 3.12.10 universal2 or set PYTHON_BIN)"; exit 1; }
"$PYTHON_BIN" scripts/check_macos_build_python.py

export MACOSX_DEPLOYMENT_TARGET=15.0 CMAKE_OSX_DEPLOYMENT_TARGET=15.0 CMAKE_OSX_ARCHITECTURES=arm64

VENV=.venv-macos15_0-arm64-log-solution
[[ -d "$VENV" ]] || "$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" scripts/check_macos_build_python.py
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements/requirements-macos15-arm64.txt
"$VENV/bin/python" scripts/run_tests.py

VERSION="$($VENV/bin/python - <<'PY'
from pathlib import Path
parts = [int(v) for v in Path('VERSION').read_text().strip().split('.')]
parts[-1] += 1
value = '.'.join(map(str, parts))
Path('VERSION').write_text(value + '\n')
print(value)
PY
)"

DIST=dist-macos15_0-arm64
BUILD=build-macos15_0-arm64
rm -rf "$DIST" "$BUILD"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --windowed --target-architecture arm64 \
  --name 'B518 Log Solution' --osx-bundle-identifier com.b518.logsolution \
  --distpath "$DIST" --workpath "$BUILD" --paths src --add-data "assets:assets" src/b518_log_solution.py

APP="$DIST/B518 Log Solution.app"
PLIST="$APP/Contents/Info.plist"
for pair in "CFBundleShortVersionString $VERSION" "CFBundleVersion $VERSION" "LSMinimumSystemVersion 15.0"; do
  key=${pair%% *}
  value=${pair#* }
  /usr/libexec/PlistBuddy -c "Set :$key $value" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :$key string $value" "$PLIST"
done

"$VENV/bin/python" scripts/verify_macos_bundle.py "$APP" --target 15.0

codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

ZIP="$DIST/B518-Log-Solution-V${VERSION}-macOS15.0-arm64.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP" > "$ZIP.sha256"
print "Candidate built: $ZIP"
