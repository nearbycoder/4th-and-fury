#!/bin/sh
# Play a rendered eight-seat match. Windowed runs request native 1080p.
# FURY_FULLSCREEN=1 uses the display mode selected by macOS.
# FURY_SCALE=auto tests the saved preset. A percentage fixes the field scale (default 100).
# Usage: Scripts/benchmark.sh [seed] [seconds] [additional game options...]
set -eu
project=$(cd "$(dirname "$0")/.." && pwd)
app="${FURY_APP:-$project/Packaged/FourthAndFury.app}"
executable=$(/usr/libexec/PlistBuddy -c 'Print CFBundleExecutable' "$app/Contents/Info.plist")
bundle=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$app/Contents/Info.plist")
report="$HOME/Library/Containers/$bundle/Data/fury-benchmark-$(uuidgen).txt"
seed=${1:-7341}
duration=${2:-90}
if [ "$#" -gt 0 ]; then shift; fi
if [ "$#" -gt 0 ]; then shift; fi
case "$duration" in ''|*[!0-9]*) echo "Duration must be whole seconds" >&2; exit 2;; esac
[ "$duration" -ge 15 ] || { echo "Allow at least 15 seconds for warm-up and live play" >&2; exit 2; }
mode=-windowed
scale_option=
case "${FURY_SCALE:-100}" in
  auto) ;;
  *[!0-9]*) echo "Use auto or a whole-number percentage for FURY_SCALE." >&2; exit 2 ;;
  *) scale_option="-FuryScreenPct=${FURY_SCALE:-100}" ;;
esac
if [ "${FURY_FULLSCREEN:-0}" = 1 ]; then
  # macOS cannot finish a native fullscreen transition on a locked desktop.
  if ioreg -n Root -d1 | grep -q '"CGSSessionScreenIsLocked"=Yes'; then
    echo "Unlock the Mac display before starting a fullscreen benchmark." >&2
    exit 2
  fi
  mode=-fullscreen
fi
log=$(mktemp "${TMPDIR:-/tmp}/fury-benchmark.XXXXXXXX")
echo "Seed $seed, ${duration}s, log $log"
"$app/Contents/MacOS/$executable" "$mode" -ResX=1920 -ResY=1080 -ForceRes \
  -FuryMatch -FuryBots=8 -FuryHome=hellhounds -FuryAway=scorpions ${scale_option:+"$scale_option"} \
  "-FurySeed=$seed" "-FuryQuitAfter=$duration" "-FuryBenchReport=$report" -FuryBenchmark -unattended -nosplash -stdout -FullStdOutLogOutput "$@" >"$log" 2>&1
if [ -s "$report" ]; then
  cat "$report" | tee -a "$log"
  rm "$report"
else
  grep -E 'LogFury: (Window |Stadium: [0-9]|FURY_BENCH)' "$log"
fi
grep -q 'FURY_BENCH match ' "$log" && grep -q 'FURY_BENCH live ' "$log"
