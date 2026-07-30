#!/bin/zsh
# Build an Intel-only Atlas Agent bundle that runs on macOS Mojave 10.14.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(/usr/bin/sw_vers -productVersion)" != 10.14.* ]]; then
  echo "This script must run inside the macOS Mojave 10.14 Intel build VM."
  echo "Current system: $(/usr/bin/sw_vers -productVersion)"
  exit 2
fi
if [[ "$(/usr/bin/uname -m)" != "x86_64" ]]; then
  echo "This script requires an Intel (x86_64) Mojave VM."
  exit 2
fi
if ! /usr/bin/xcodebuild -version >/dev/null 2>&1; then
  echo "A full Xcode installation is required to compile Mojave-compatible OpenCV and PyObjC."
  echo "Install Xcode 10.3 in /Applications, then select it with xcode-select."
  exit 2
fi

PYTHON="${PYTHON:-/usr/local/bin/python3.12}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python 3.12 was not found at $PYTHON. Set PYTHON=/path/to/python3.12 and try again."
  exit 2
fi
if ! "$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
  echo "This Mojave build requires Python 3.12: $PYTHON"
  exit 2
fi

VENV="$PWD/.venv-mojave"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi
PYTHON="$VENV/bin/python"

export MACOSX_DEPLOYMENT_TARGET=10.14
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-mojave"

APP_EXECUTABLE="$PWD/dist-mojave/Atlas Agent B518 ATE.app/Contents/MacOS/Atlas Agent B518 ATE"
if command -v pgrep >/dev/null && pgrep -f "$APP_EXECUTABLE" >/dev/null 2>&1; then
  echo "The previous Mojave app is still running. Close it before building."
  exit 3
fi

# Build OpenCV from source in Mojave.  A Catalina/newer wheel embeds a higher
# LC_VERSION_MIN_MACOSX and is the cause of the template-maker launch failure.
"$PYTHON" -m pip install --upgrade pip "setuptools==80.9.0" wheel \
  "cmake==3.30.5" "ninja==1.11.1.1" "scikit-build==0.17.6"
"$PYTHON" -m pip install --no-build-isolation \
  --no-binary=opencv-python,pyobjc-core,pyobjc-framework-Cocoa \
  -r requirements-mojave.txt "pyinstaller==6.16.0"
if ! "$PYTHON" -c 'import PyInstaller, cv2, serial, AppKit'; then
  echo "Mojave build dependencies could not be imported."
  exit 4
fi

BUILD_VERSION="$("$PYTHON" bump_build_version.py)"
echo "Building Mojave-compatible Atlas Agent B518 ATE V$BUILD_VERSION"
TEMPLATE_SOURCE="$PWD/templates"
if [[ ! -d "$TEMPLATE_SOURCE" ]]; then
  echo "Required template directory is missing: $TEMPLATE_SOURCE"
  exit 4
fi
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed \
  --name "Atlas Agent B518 ATE" \
  --distpath "$PWD/dist-mojave" \
  --workpath "$PWD/build-mojave" \
  --specpath "$PWD/build-mojave" \
  --add-data="${TEMPLATE_SOURCE}:templates" \
  --collect-all serial \
  --collect-all cv2 \
  atlas_agent.py

PLIST="$PWD/dist-mojave/Atlas Agent B518 ATE.app/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$BUILD_VERSION" "$PLIST"
plutil -insert CFBundleVersion -string "$BUILD_VERSION" "$PLIST"
"$PWD/verify_mojave_bundle.sh" "$PWD/dist-mojave/Atlas Agent B518 ATE.app"

echo "Built Mojave-compatible V$BUILD_VERSION: $PWD/dist-mojave/Atlas Agent B518 ATE.app"
