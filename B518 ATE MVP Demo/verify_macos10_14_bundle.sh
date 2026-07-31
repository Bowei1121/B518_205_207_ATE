#!/bin/zsh
# Validate a Catalina-built candidate before it is copied to Mojave 10.14.
set -euo pipefail
cd "$(dirname "$0")"

version_is_newer_than_target() {
  /usr/bin/awk -v candidate="$1" -v target="10.14.0" 'BEGIN {
    split(candidate, a, "."); split(target, b, ".");
    for (i = 1; i <= 3; i++) {
      av = (a[i] == "" ? 0 : a[i]) + 0; bv = (b[i] == "" ? 0 : b[i]) + 0;
      if (av > bv) exit 0;
      if (av < bv) exit 1;
    }
    exit 1;
  }'
}

if [[ "${1:-}" == "--self-test" ]]; then
  version_is_newer_than_target 10.13.6 && exit 1
  version_is_newer_than_target 10.14.0 && exit 1
  version_is_newer_than_target 10.15.0 || exit 1
  echo "Verifier version comparison self-test passed."
  exit 0
fi

APP_PATH="${1:-$PWD/dist-macos10.14-common/Atlas Agent B518 ATE.app}"
[[ -d "$APP_PATH" ]] || { echo "App bundle not found: $APP_PATH"; exit 2; }
PLIST="$APP_PATH/Contents/Info.plist"
[[ -f "$PLIST" ]] || { echo "Info.plist is missing: $PLIST"; exit 2; }

minimum=$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$PLIST" 2>/dev/null || true)
[[ "$minimum" == "10.14" ]] || { echo "LSMinimumSystemVersion must be 10.14 (got ${minimum:-missing})"; exit 1; }

machines=0
violations=0
while IFS= read -r -d '' candidate; do
  /usr/bin/file -b "$candidate" 2>/dev/null | /usr/bin/grep -q 'Mach-O' || continue
  machines=$((machines + 1))
  architectures=$(/usr/bin/lipo -archs "$candidate" 2>/dev/null || true)
  if [[ " $architectures " != *" x86_64 "* ]]; then
    echo "ARCHITECTURE MISSING x86_64: $candidate ($architectures)"
    violations=$((violations + 1))
  fi
  binary_minimum=$(/usr/bin/otool -l "$candidate" 2>/dev/null | /usr/bin/awk '
    $1 == "cmd" && ($2 == "LC_BUILD_VERSION" || $2 == "LC_VERSION_MIN_MACOSX") { watch = 1; next }
    watch && ($1 == "minos" || $1 == "version") { print $2; exit }
  ')
  if [[ -n "$binary_minimum" ]] && version_is_newer_than_target "$binary_minimum"; then
    echo "MINIMUM OS TOO NEW ($binary_minimum): $candidate"
    violations=$((violations + 1))
  fi
  while IFS= read -r dependency; do
    [[ -z "$dependency" ]] && continue
    case "$dependency" in
      @rpath/*|@loader_path/*|@executable_path/*|/System/Library/*|/usr/lib/*) ;;
      *) echo "EXTERNAL THIRD-PARTY DYLIB: $candidate -> $dependency"; violations=$((violations + 1));;
    esac
  done < <(/usr/bin/otool -L "$candidate" 2>/dev/null | /usr/bin/awk 'NR > 1 {print $1}')
done < <(/usr/bin/find "$APP_PATH" -type f -print0)

for package in cv2 numpy serial AppKit; do
  if ! /usr/bin/find "$APP_PATH" -iname "*${package}*" -print -quit | /usr/bin/grep -q .; then
    echo "PACKAGED MODULE NOT FOUND: $package"
    violations=$((violations + 1))
  fi
done

if ! /usr/bin/codesign --verify --deep --strict "$APP_PATH"; then
  echo "Code signature validation failed."
  violations=$((violations + 1))
fi

if (( violations > 0 )); then
  echo "macOS 10.14 candidate verification failed: $violations violation(s) across $machines Mach-O file(s)."
  exit 1
fi
echo "macOS 10.14 candidate verification passed: $machines Mach-O file(s), x86_64, no external third-party dylibs."
