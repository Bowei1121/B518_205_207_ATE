#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}"
cd "$ROOT"
[[ "$(uname -m)" == "x86_64" ]] || { print -u2 'Requires an Intel x86_64 builder.'; exit 1; }
[[ "$(sw_vers -productVersion)" == 10.15.* ]] || { print -u2 'Requires macOS 10.15.x Catalina VM.'; exit 1; }
PYTHON_BIN="${PYTHON_BIN:-/usr/local/bin/python3.12}"
[[ -x "$PYTHON_BIN" ]] || { print -u2 "Python 3.12 not found: $PYTHON_BIN"; exit 1; }
export MACOSX_DEPLOYMENT_TARGET=10.14 CMAKE_OSX_DEPLOYMENT_TARGET=10.14 CMAKE_OSX_ARCHITECTURES=x86_64
VENV=.venv-macos10.14-log-solution
[[ -d "$VENV" ]] || "$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements-macos10.14-common.txt
"$VENV/bin/python" -m unittest -v test_log_monitoring.py test_log_solution_ui.py
VERSION="$($VENV/bin/python - <<'PY'
from pathlib import Path
parts = [int(v) for v in Path('VERSION').read_text().strip().split('.')]
parts[-1] += 1
value = '.'.join(map(str, parts))
Path('VERSION').write_text(value + '\n')
print(value)
PY
)"
DIST=dist-macos10.14-common BUILD=build-macos10.14-common
rm -rf "$DIST" "$BUILD"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --windowed --target-architecture x86_64 --name 'B518 Log Solution' --osx-bundle-identifier com.b518.logsolution --distpath "$DIST" --workpath "$BUILD" b518_log_solution.py
APP="$DIST/B518 Log Solution.app"; PLIST="$APP/Contents/Info.plist"
for pair in "CFBundleShortVersionString $VERSION" "CFBundleVersion $VERSION" "LSMinimumSystemVersion 10.14"; do
  key=${pair%% *}; value=${pair#* }
  /usr/libexec/PlistBuddy -c "Set :$key $value" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :$key string $value" "$PLIST"
done
while IFS= read -r -d '' binary; do
  file "$binary" | grep -q 'Mach-O' || continue
  lipo -archs "$binary" | grep -qw x86_64 || { print -u2 "Not x86_64: $binary"; exit 1; }
done < <(find "$APP" -type f -print0)
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
ZIP="$DIST/B518-Log-Solution-V${VERSION}-macOS10.14-x86_64.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP" > "$ZIP.sha256"
print "Candidate built: $ZIP"
