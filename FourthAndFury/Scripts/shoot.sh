#!/bin/sh
# Capture original PNGs, small previews and the game mix for review.
# Usage: Scripts/shoot.sh <output directory> <seconds> <interval> [game options...]
# FURY_APP selects a packaged build. FURY_SOUND=1 plays audio through the speakers.
set -eu
if [ "$#" -lt 3 ]; then
  echo 'Usage: shoot.sh <output directory> <seconds> <interval> [game options...]' >&2
  exit 2
fi
out=$1
seconds=$2
interval=$3
shift 3
if ! awk -v seconds="$seconds" -v interval="$interval" 'BEGIN {
  decimal = "^([0-9]+([.][0-9]*)?|[.][0-9]+)$"
  exit !(seconds ~ decimal && interval ~ decimal && seconds + 0 > 0 && interval + 0 > 0)
}'; then
  echo 'Capture duration and interval must be positive numbers in seconds.' >&2
  exit 2
fi

if [ -n "${FURY_CAPTURE_FPS:-}" ]; then
  case "$FURY_CAPTURE_FPS" in ''|*[!0-9]*) echo 'FURY_CAPTURE_FPS must be a positive whole number.' >&2; exit 2;; esac
  [ "$FURY_CAPTURE_FPS" -gt 0 ] || { echo 'FURY_CAPTURE_FPS must be positive.' >&2; exit 2; }
  set -- -UseFixedTimeStep "-FuryCaptureFPS=$FURY_CAPTURE_FPS" "$@"
fi

project=$(cd "$(dirname "$0")/.." && pwd)
if [ -n "${FURY_APP:-}" ]; then
  plist="$FURY_APP/Contents/Info.plist"
  name=$(/usr/libexec/PlistBuddy -c 'Print CFBundleExecutable' "$plist")
  bundle=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$plist")
  executable="$FURY_APP/Contents/MacOS/$name"
  parent="$HOME/Library/Containers/$bundle/Data"
else
  executable="${UE_ENGINE_DIR:-$HOME/UnrealEngine}/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
  parent=/tmp
fi
[ -x "$executable" ] || { echo "Missing game executable: $executable" >&2; exit 1; }

mkdir -p "$out" "$parent"
out=$(cd "$out" && pwd)
lock="$out/.fury-shoot.lock"
mkdir "$lock" || { echo "A capture already owns $out" >&2; exit 1; }
trap 'rmdir "$lock"' EXIT
trap 'exit 1' HUP INT TERM
work=$(mktemp -d "$parent/fury-shoot.XXXXXXXX")
echo "Recording to $work"
if [ "${FURY_SOUND:-0}" != 1 ]; then
  set -- -NonRealtimeAudio "-FuryAudioOut=$work/mix.wav" "$@"
fi
set -- -windowed "-ResX=${FURY_RESX:-1600}" "-ResY=${FURY_RESY:-900}" "-FuryShots=$work" \
  "-FuryShotEvery=$interval" "-FuryQuitAfter=$seconds" "-abslog=$work/game.log" -nosplash -unattended "$@"
if [ -z "${FURY_APP:-}" ]; then set -- "$project/FourthAndFury.uproject" -game "$@"; fi
"$executable" "$@" > "$work/run.log" 2>&1 || { echo "Capture failed. See $work/run.log" >&2; exit 1; }

if [ "${FURY_SOUND:-0}" != 1 ] && [ ! -s "$work/mix.wav" ]; then
  echo "No audio written. See $work/run.log" >&2
  exit 1
fi
count=0
for shot in "$work"/shot_*.png; do
  [ -f "$shot" ] || { echo "No frames written. See $work/run.log" >&2; exit 1; }
  sips -Z "${FURY_VIEW:-1200}" "$shot" --out "${shot%.png}_s.png" > /dev/null
  count=$((count + 1))
done
# A shorter repeat replaces the old sequence. Leave all other files in the output directory alone.
for old in "$out"/shot_*.png; do
  [ -f "$old" ] || continue
  file=${old##*/}
  digits=${file#shot_}
  digits=${digits%.png}
  digits=${digits%_s}
  case "$digits" in ''|*[!0-9]*) continue;; esac
  [ -f "$work/$file" ] || rm "$old"
done
for file in mix.wav game.log; do
  [ -f "$work/$file" ] || rm -f "$out/$file"
done
for file in "$work"/shot_*.png "$work"/*.log "$work"/*.wav; do
  [ -f "$file" ] || continue
  mv -f "$file" "$out/${file##*/}"
done
rmdir "$work"
echo "$count screenshots in $out"
