#!/bin/zsh
# Build the standalone Arduino HID distance calibration utility.
set -euo pipefail
cd "$(dirname "$0")"
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"

if ! python3 -c 'import PyInstaller, serial'; then
  echo "Missing build dependencies; installing from requirements.txt..."
  python3 -m pip install -r requirements.txt pyinstaller
fi

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name "Atlas HID Calibration B518" \
  --collect-all serial \
  hid_calibration.py

plutil -replace CFBundleShortVersionString -string "0.1.0" "dist/Atlas HID Calibration B518.app/Contents/Info.plist"
plutil -insert CFBundleVersion -string "0.1.0" "dist/Atlas HID Calibration B518.app/Contents/Info.plist"
echo "Built: $(pwd)/dist/Atlas HID Calibration B518.app"
