#!/bin/zsh
# Build a self-contained macOS GUI app from this directory.
set -euo pipefail
cd "$(dirname "$0")"

# Keep PyInstaller metadata inside this project.  This avoids reading or
# clearing an inaccessible cache under ~/Library on locked-down build Macs.
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"

# A locked-down build account may have no writable user site-packages.  Do not
# invoke pip (which may still attempt a user-site write) when every build
# dependency is already importable.
if ! python3 -c 'import PyInstaller, cv2, serial, Vision'; then
  echo "Missing build dependencies; installing from requirements.txt..."
  python3 -m pip install -r requirements.txt pyinstaller
fi
python3 -m PyInstaller --noconfirm --clean --windowed \
  --name "Atlas Agent B518 ATE" \
  --add-data "templates:templates" \
  --collect-all serial \
  --collect-all cv2 \
  --collect-all Vision \
  atlas_agent.py

plutil -replace CFBundleShortVersionString -string "0.1.0" "dist/Atlas Agent B518 ATE.app/Contents/Info.plist"
# PyInstaller's generated plist has no CFBundleVersion, so this must insert
# rather than replace the key.
plutil -insert CFBundleVersion -string "0.1.0" "dist/Atlas Agent B518 ATE.app/Contents/Info.plist"

echo "Built: $(pwd)/dist/Atlas Agent B518 ATE.app"
