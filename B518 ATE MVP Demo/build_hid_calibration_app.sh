#!/bin/zsh
# Build the standalone Arduino HID distance calibration utility.
set -euo pipefail
cd "$(dirname "$0")"
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"

WORK_ROOT="$(/usr/bin/mktemp -d /private/tmp/atlas-hid-calibration.XXXXXX)"
trap '/bin/rm -rf "$WORK_ROOT"' EXIT
TEMP_DIST="$WORK_ROOT/dist"
TEMP_BUILD="$WORK_ROOT/build"
TEMP_SPEC="$WORK_ROOT/spec"
APP="$TEMP_DIST/Atlas HID Calibration B518.app"
RELEASE="$PWD/release-hid-calibration"

if ! python3 -c 'import PyInstaller, serial'; then
  echo "Missing lightweight HID build dependencies; installing them..."
  python3 -m pip install -r requirements-hid-calibration.txt
fi

VERSION="$(python3 bump_hid_calibration_version.py)"

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name "Atlas HID Calibration B518" \
  --distpath "$TEMP_DIST" --workpath "$TEMP_BUILD" --specpath "$TEMP_SPEC" \
  --collect-all serial \
  hid_calibration.py

PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST"
/usr/bin/xattr -cr "$APP"
/usr/bin/codesign --force --deep --sign - "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"

# File Provider folders may immediately add FinderInfo to an unpacked app and
# invalidate a strict signature. Sign in /private/tmp and publish the verified
# bundle as a ZIP instead.
/bin/mkdir -p "$RELEASE"
ZIP="$RELEASE/Atlas-HID-Calibration-B518-V$VERSION-host.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
/usr/bin/shasum -a 256 "$ZIP" > "$ZIP.sha256"
echo "Built and verified V$VERSION: $ZIP"
echo "Extract the ZIP before local testing; do not use the stale app under dist/."
