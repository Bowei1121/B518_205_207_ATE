#!/bin/zsh
# Build the lightweight HID calibration candidate for Mojave 10.14 and Catalina 10.15.
set -euo pipefail
cd "$(dirname "$0")"

TARGET="10.14"
EXPECTED_PYTHON="3.12.6"
VENV="$PWD/.venv-hid-macos10.14-common"
DIST="$PWD/dist-hid-macos10.14-common"
BUILD="$PWD/build-hid-macos10.14-common"
RELEASE="$PWD/release-hid-macos10.14-common"
APP="$DIST/Atlas HID Calibration B518.app"

set_plist_string() {
  local plist="$1" key="$2" value="$3"
  if /usr/libexec/PlistBuddy -c "Print :$key" "$plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$key $value" "$plist"
  else
    /usr/libexec/PlistBuddy -c "Add :$key string $value" "$plist"
  fi
}

[[ "$(/usr/bin/sw_vers -productVersion)" == 10.15.* ]] || {
  echo "Run this common candidate builder in the Catalina 10.15 Intel VM."; exit 2; }
[[ "$(/usr/bin/uname -m)" == x86_64 ]] || { echo "An x86_64 Intel VM is required."; exit 2; }

BASE_PYTHON="${PYTHON:-/usr/local/bin/python3.12}"
[[ -x "$BASE_PYTHON" ]] || { echo "Python not found: $BASE_PYTHON"; exit 2; }
/usr/bin/arch -x86_64 "$BASE_PYTHON" -c \
  "import sys; assert sys.version.split()[0] == '$EXPECTED_PYTHON'" || {
  echo "Python $EXPECTED_PYTHON x86_64 is required."; exit 2; }

export MACOSX_DEPLOYMENT_TARGET="$TARGET"
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-hid-macos10.14-common"
if [[ ! -x "$VENV/bin/python" ]]; then
  /usr/bin/arch -x86_64 "$BASE_PYTHON" -m venv "$VENV"
fi
PYTHON_BIN="$VENV/bin/python"
"$PYTHON_BIN" -m pip install --upgrade pip "setuptools==80.9.0" wheel
"$PYTHON_BIN" -m pip install -r requirements-hid-calibration.txt
"$PYTHON_BIN" -m pip check
"$PYTHON_BIN" -c 'import serial, PyInstaller; print("HID calibration build imports OK")'
"$PYTHON_BIN" -m unittest -v test_atlas_agent.py

VERSION="$("$PYTHON_BIN" bump_hid_calibration_version.py)"
echo "Building Atlas HID Calibration B518 V$VERSION"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --windowed --target-arch x86_64 \
  --name "Atlas HID Calibration B518" --distpath "$DIST" --workpath "$BUILD" \
  --specpath "$BUILD" --collect-all serial hid_calibration.py

PLIST="$APP/Contents/Info.plist"
set_plist_string "$PLIST" CFBundleShortVersionString "$VERSION"
set_plist_string "$PLIST" CFBundleVersion "$VERSION"
set_plist_string "$PLIST" LSMinimumSystemVersion "$TARGET"
/usr/bin/xattr -cr "$APP"
/usr/bin/codesign --force --deep --sign - "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
/usr/bin/file "$APP/Contents/MacOS/Atlas HID Calibration B518" | /usr/bin/grep -q x86_64

/bin/mkdir -p "$RELEASE"
ZIP="$RELEASE/Atlas-HID-Calibration-B518-V$VERSION-macos10.14-x86_64.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
/usr/bin/shasum -a 256 "$ZIP" > "$ZIP.sha256"
echo "Candidate built: $APP"
echo "Deliverable: $ZIP"
