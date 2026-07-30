#!/bin/zsh
# Reject a bundle containing native code that requires newer than Mojave 10.14.
set -euo pipefail
cd "$(dirname "$0")"

APP_PATH="${1:-$PWD/dist-mojave/Atlas Agent B518 ATE.app}"
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH"
  exit 2
fi

version_is_newer_than_mojave() {
  awk -v candidate="$1" 'BEGIN {
    split(candidate, a, "."); split("10.14.0", b, ".");
    for (i = 1; i <= 3; i++) {
      av = (a[i] == "" ? 0 : a[i]) + 0; bv = b[i] + 0;
      if (av > bv) exit 0;
      if (av < bv) exit 1;
    }
    exit 1;
  }'
}

integer=0
violations=0
while IFS= read -r -d '' candidate; do
  /usr/bin/file -b "$candidate" 2>/dev/null | /usr/bin/grep -q 'Mach-O' || continue
  integer=$((integer + 1))
  minimum=$(/usr/bin/otool -l "$candidate" 2>/dev/null | /usr/bin/awk '
    $1 == "cmd" && ($2 == "LC_BUILD_VERSION" || $2 == "LC_VERSION_MIN_MACOSX") { watch = 1; next }
    watch && ($1 == "minos" || $1 == "version") { print $2; exit }
  ')
  [[ -n "$minimum" ]] || continue
  if version_is_newer_than_mojave "$minimum"; then
    echo "INCOMPATIBLE (requires macOS $minimum): $candidate"
    violations=$((violations + 1))
  fi
done < <(/usr/bin/find "$APP_PATH" -type f -print0)

if (( violations > 0 )); then
  echo "Mojave compatibility verification failed: $violations / $integer Mach-O files require newer macOS."
  exit 1
fi
echo "Mojave compatibility verified: $integer Mach-O files require macOS 10.14 or earlier."
