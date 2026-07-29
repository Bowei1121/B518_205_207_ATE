#!/bin/zsh
# Reject a bundle containing Mach-O code that requires newer than Catalina.
set -euo pipefail
cd "$(dirname "$0")"

APP_PATH="${1:-$PWD/dist-catalina/Atlas Agent B518 ATE.app}"
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH"
  exit 2
fi

version_is_newer_than_catalina() {
  awk -v candidate="$1" 'BEGIN {
    split(candidate, a, "."); split("10.15.0", b, ".");
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
  if version_is_newer_than_catalina "$minimum"; then
    echo "INCOMPATIBLE (requires macOS $minimum): $candidate"
    violations=$((violations + 1))
  fi
done < <(/usr/bin/find "$APP_PATH" -type f -print0)

if (( violations > 0 )); then
  echo "Catalina compatibility verification failed: $violations / $integer Mach-O files require newer macOS."
  exit 1
fi
echo "Catalina compatibility verified: $integer Mach-O files require macOS 10.15 or earlier."
