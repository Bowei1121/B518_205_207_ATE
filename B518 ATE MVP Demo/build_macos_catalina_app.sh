#!/bin/zsh
# Build an Intel-only Atlas Agent bundle that runs on macOS Catalina 10.15.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(/usr/bin/sw_vers -productVersion)" != 10.15.* ]]; then
  echo "This script must run inside the macOS Catalina 10.15 Intel build VM."
  echo "Current system: $(/usr/bin/sw_vers -productVersion)"
  exit 2
fi
if [[ "$(/usr/bin/uname -m)" != "x86_64" ]]; then
  echo "This script requires an Intel (x86_64) Catalina VM."
  exit 2
fi
if ! /usr/bin/xcodebuild -version >/dev/null 2>&1; then
  echo "A full Xcode installation is required to build the Catalina PyObjC bridges."
  echo "Install Xcode 12.4 in /Applications, then run:"
  echo "  sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer"
  echo "  sudo xcodebuild -license accept"
  exit 2
fi

PYTHON="${PYTHON:-/usr/local/bin/python3.12}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python 3.12 was not found at $PYTHON. Set PYTHON=/path/to/python3.12 and try again."
  exit 2
fi
if ! "$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
  echo "This Catalina build requires Python 3.12: $PYTHON"
  exit 2
fi

VENV="$PWD/.venv-catalina"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi
PYTHON="$VENV/bin/python"

export MACOSX_DEPLOYMENT_TARGET=10.15
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-catalina"

APP_EXECUTABLE="$PWD/dist-catalina/Atlas Agent B518 ATE.app/Contents/MacOS/Atlas Agent B518 ATE"
if command -v pgrep >/dev/null && pgrep -f "$APP_EXECUTABLE" >/dev/null 2>/dev/null; then
  echo "The previous Catalina app is still running. Close it before building."
  exit 3
fi

# PyObjC 10.3.1's setup script still imports pkg_resources.  Newer setuptools
# no longer ships that compatibility module, so keep the build toolchain below
# its removal and avoid pip creating an isolated environment with a newer one.
"$PYTHON" -m pip install --upgrade pip "setuptools==80.9.0" wheel
"$PYTHON" -m pip install --no-build-isolation \
  --no-binary=pyobjc-core,pyobjc-framework-Cocoa,pyobjc-framework-Vision \
  -r requirements-catalina.txt "pyinstaller==6.16.0"
if ! "$PYTHON" -c 'import PyInstaller, cv2, serial, Vision, AppKit'; then
  echo "Catalina build dependencies could not be imported."
  exit 4
fi

BUILD_VERSION="$("$PYTHON" bump_build_version.py)"
echo "Building Catalina-compatible Atlas Agent B518 ATE V$BUILD_VERSION"
TEMPLATE_SOURCE="$PWD/templates"
if [[ ! -d "$TEMPLATE_SOURCE" ]]; then
  echo "Required template directory is missing: $TEMPLATE_SOURCE"
  exit 4
fi
# With --specpath, a relative add-data source would be looked up under
# build-catalina.  Use the project absolute path so templates are packaged.
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed \
  --name "Atlas Agent B518 ATE" \
  --distpath "$PWD/dist-catalina" \
  --workpath "$PWD/build-catalina" \
  --specpath "$PWD/build-catalina" \
  --add-data "$TEMPLATE_SOURCE:templates" \
  --collect-all serial \
  --collect-all cv2 \
  --collect-all Vision \
  atlas_agent.py

PLIST="$PWD/dist-catalina/Atlas Agent B518 ATE.app/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$BUILD_VERSION" "$PLIST"
plutil -insert CFBundleVersion -string "$BUILD_VERSION" "$PLIST"
"$PWD/verify_catalina_bundle.sh" "$PWD/dist-catalina/Atlas Agent B518 ATE.app"

echo "Built Catalina-compatible V$BUILD_VERSION: $PWD/dist-catalina/Atlas Agent B518 ATE.app"
