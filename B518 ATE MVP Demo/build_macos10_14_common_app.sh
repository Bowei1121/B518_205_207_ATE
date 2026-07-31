#!/bin/zsh
# Build an Intel x86_64 macOS 10.14-compatible candidate on Catalina 10.15.
set -euo pipefail
cd "$(dirname "$0")"

TARGET="10.14"
EXPECTED_PYTHON="3.12.6"
VENV="$PWD/.venv-macos10.14-common"
WHEEL_DIR="$PWD/.wheels-macos10.14-common"
DIST="$PWD/dist-macos10.14-common"
BUILD="$PWD/build-macos10.14-common"
APP="$DIST/Atlas Agent B518 ATE.app"
RELEASE="$PWD/release-macos10.14-common"

set_plist_string() {
  local plist_path="$1"
  local plist_key="$2"
  local plist_value="$3"
  if /usr/libexec/PlistBuddy -c "Print :$plist_key" "$plist_path" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$plist_key $plist_value" "$plist_path"
  else
    /usr/libexec/PlistBuddy -c "Add :$plist_key string $plist_value" "$plist_path"
  fi
}

verify_plist_writer() {
  local test_directory
  local test_plist
  test_directory=$(/usr/bin/mktemp -d /tmp/atlas-agent-plist-test.XXXXXX)
  test_plist="$test_directory/Info.plist"
  /usr/libexec/PlistBuddy -c "Add :Existing string old" "$test_plist" >/dev/null
  set_plist_string "$test_plist" Existing replaced
  set_plist_string "$test_plist" Missing added
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :Existing' "$test_plist")" == replaced ]]
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :Missing' "$test_plist")" == added ]]
  /bin/rm "$test_plist"
  /bin/rmdir "$test_directory"
  echo "Info.plist add/set self-test passed."
}

if [[ "${1:-}" == "--self-test-plist" ]]; then
  verify_plist_writer
  exit 0
fi

[[ "$(/usr/bin/sw_vers -productVersion)" == 10.15.* ]] || {
  echo "This candidate builder must run in the macOS Catalina 10.15 Intel VM."
  echo "Current macOS: $(/usr/bin/sw_vers -productVersion)"; exit 2; }
[[ "$(/usr/bin/uname -m)" == x86_64 ]] || { echo "An x86_64 Intel VM is required."; exit 2; }
if ! /usr/bin/xcodebuild -version >/dev/null 2>&1; then
  echo "Full Xcode 12.4 is required; Command Line Tools alone cannot build OpenCV/PyObjC."
  echo "Run: sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer"
  exit 2
fi

BASE_PYTHON="${PYTHON:-/usr/local/bin/python3.12}"
[[ -x "$BASE_PYTHON" ]] || { echo "Python 3.12.6 not found: $BASE_PYTHON"; exit 2; }
if ! /usr/bin/arch -x86_64 "$BASE_PYTHON" -c "import sys; assert sys.version.split()[0] == '$EXPECTED_PYTHON'" 2>/dev/null; then
  echo "Use the python.org x86_64-capable Python $EXPECTED_PYTHON installer (set PYTHON=/path/to/python3.12)."
  exit 2
fi

export MACOSX_DEPLOYMENT_TARGET="$TARGET"
export CMAKE_OSX_DEPLOYMENT_TARGET="$TARGET"
export CMAKE_OSX_ARCHITECTURES=x86_64
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-macos10.14-common"
export CMAKE_ARGS="-DCMAKE_OSX_DEPLOYMENT_TARGET=$TARGET -DCMAKE_OSX_ARCHITECTURES=x86_64"
export ENABLE_HEADLESS=1

if [[ ! -x "$VENV/bin/python" ]]; then
  /usr/bin/arch -x86_64 "$BASE_PYTHON" -m venv "$VENV"
fi
PYTHON="$VENV/bin/python"

if command -v pgrep >/dev/null && [[ -x "$APP/Contents/MacOS/Atlas Agent B518 ATE" ]] && pgrep -f "$APP/Contents/MacOS/Atlas Agent B518 ATE" >/dev/null 2>&1; then
  echo "Close the previous candidate App before building."; exit 3
fi

"$PYTHON" -m pip install --upgrade pip "setuptools==80.9.0" wheel
# These build tools are installed before the source build so OpenCV does not
# pull a newer, platform-incompatible isolated toolchain.
# The old Ninja PyPI package does not publish a Catalina-compatible runtime.
# CMake falls back to Xcode/Unix Makefiles, which is sufficient for this
# one-time OpenCV source wheel and avoids a false platform failure after build.
"$PYTHON" -m pip uninstall -y ninja >/dev/null 2>&1 || true
"$PYTHON" -m pip install "cmake==3.30.5" "scikit-build==0.17.6"
"$PYTHON" -m pip install "numpy==1.26.4" "pyserial==3.5" \
  "pyobjc-core==10.3.1" "pyobjc-framework-Cocoa==10.3.1" "pyinstaller==6.16.0"

mkdir -p "$WHEEL_DIR"
"$PYTHON" -m pip wheel --no-deps --no-build-isolation --no-binary=opencv-python-headless \
  --wheel-dir "$WHEEL_DIR" "opencv-python-headless==4.10.0.84"
OPENCV_WHEEL=$(find "$WHEEL_DIR" -maxdepth 1 -name 'opencv_python_headless-4.10.0.84-*.whl' -print -quit)
[[ -n "$OPENCV_WHEEL" ]] || { echo "OpenCV source wheel was not produced."; exit 4; }
"$PYTHON" -m pip install --no-deps "$OPENCV_WHEEL"
"$PYTHON" -m pip check
"$PYTHON" -c 'import AppKit, PyInstaller, cv2, numpy, serial; print("runtime imports OK", cv2.__version__)'

"$PYTHON" -m unittest -v test_atlas_agent.py test_upper_computer_simulator.py
"$PWD/verify_macos10_14_bundle.sh" --self-test
verify_plist_writer

TEMPLATE_SOURCE="$PWD/templates"
[[ -d "$TEMPLATE_SOURCE" ]] || { echo "Template directory is missing: $TEMPLATE_SOURCE"; exit 4; }
BUILD_VERSION="$("$PYTHON" bump_build_version.py)"
echo "Building macOS $TARGET-compatible candidate V$BUILD_VERSION"
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed --target-arch x86_64 \
  --name "Atlas Agent B518 ATE" --distpath "$DIST" --workpath "$BUILD" --specpath "$BUILD" \
  --add-data "${TEMPLATE_SOURCE}:templates" --collect-all serial --collect-all cv2 --hidden-import AppKit atlas_agent.py

PLIST="$APP/Contents/Info.plist"
set_plist_string "$PLIST" CFBundleShortVersionString "$BUILD_VERSION"
set_plist_string "$PLIST" CFBundleVersion "$BUILD_VERSION"
set_plist_string "$PLIST" LSMinimumSystemVersion "$TARGET"
/usr/bin/codesign --force --deep --sign - "$APP"
"$PWD/verify_macos10_14_bundle.sh" "$APP"

mkdir -p "$RELEASE"
ZIP="$RELEASE/Atlas-Agent-B518-ATE-V$BUILD_VERSION-macos10.14-x86_64.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
/usr/bin/shasum -a 256 "$ZIP" > "$ZIP.sha256"
REPORT="$RELEASE/Atlas-Agent-B518-ATE-V$BUILD_VERSION-build-report.txt"
{
  echo "version=$BUILD_VERSION"; echo "target_macos=$TARGET"; echo "target_arch=x86_64"
  /usr/bin/sw_vers; /usr/bin/uname -a; /usr/bin/xcodebuild -version
  "$PYTHON" --version; "$PYTHON" -m pip show numpy opencv-python-headless pyserial pyobjc-core pyobjc-framework-Cocoa pyinstaller
  echo "app=$APP"; echo "zip=$ZIP"
} > "$REPORT"
echo "Candidate built: $APP"
echo "Deliver this ZIP for Mojave and Catalina acceptance: $ZIP"
