#!/bin/zsh
# Build a self-contained macOS GUI app from this directory.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing Python 3.12 development environment: $PYTHON"
  echo "Create it with: /usr/local/opt/python@3.12/bin/python3.12 -m venv .venv"
  exit 2
fi
if ! "$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
  echo "This build requires Python 3.12: $PYTHON"
  exit 2
fi

# Keep PyInstaller metadata inside this project.  This avoids reading or
# clearing an inaccessible cache under ~/Library on locked-down build Macs.
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"

# Do not replace an app bundle while this user's previous build is open.  That
# can leave the executable and Info.plist from different versions.  The check
# occurs before the version bump so only a real build increments the version.
APP_EXECUTABLE="$PWD/dist/Atlas Agent B518 ATE.app/Contents/MacOS/Atlas Agent B518 ATE"
if command -v pgrep >/dev/null && pgrep -f "$APP_EXECUTABLE" >/dev/null 2>/dev/null; then
  echo "Atlas Agent B518 ATE is still running. Close it before building."
  exit 3
fi

# A locked-down build account may have no writable user site-packages.  Do not
# invoke pip (which may still attempt a user-site write) when every build
# dependency is already importable.
if ! "$PYTHON" -c 'import PyInstaller, cv2, serial, AppKit'; then
  echo "Missing build dependencies; installing from requirements.txt..."
  "$PYTHON" -m pip install -r requirements.txt pyinstaller
fi
BUILD_VERSION="$("$PYTHON" bump_build_version.py)"
echo "Building Atlas Agent B518 ATE V$BUILD_VERSION"
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed \
  --name "Atlas Agent B518 ATE" \
  --add-data "templates:templates" \
  --collect-all serial \
  --collect-all cv2 \
  atlas_agent.py

plutil -replace CFBundleShortVersionString -string "$BUILD_VERSION" "dist/Atlas Agent B518 ATE.app/Contents/Info.plist"
# PyInstaller's generated plist has no CFBundleVersion, so this must insert
# rather than replace the key.
plutil -insert CFBundleVersion -string "$BUILD_VERSION" "dist/Atlas Agent B518 ATE.app/Contents/Info.plist"

echo "Built V$BUILD_VERSION: $(pwd)/dist/Atlas Agent B518 ATE.app"
