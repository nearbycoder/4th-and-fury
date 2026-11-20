#!/bin/sh
# Developer tool: play N computer-vs-computer matches without rendering and print the statistics.
#   Scripts/simtest.sh [games] [extra args, e.g. -FurySkill=0.8 -FuryVerbose]
ENGINE="${UE_ENGINE_DIR:-$HOME/UnrealEngine}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
GAMES="${1:-40}"; [ $# -gt 0 ] && shift
"$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$DIR/FourthAndFury.uproject" -game -nullrhi -nosound -nosplash -unattended \
  -FurySimTest="$GAMES" "$@" > /dev/null 2>&1
grep -h "SIMTEST\|Play blown dead" "$HOME/Library/Logs/FourthAndFury/FourthAndFury.log" | sed 's/^.*LogFury: //'
