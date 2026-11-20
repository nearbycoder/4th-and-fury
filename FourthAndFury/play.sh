#!/bin/sh
# Launch 4th & Fury using the source-built UE 5.9 editor binary.
#   ./play.sh                      the game, in a 1920x1080 window
#   ./play.sh -fullscreen          full screen
#   ./play.sh -FuryViewer          animation viewer (left/right arrows step through clips)
ENGINE="${UE_ENGINE_DIR:-$HOME/UnrealEngine}"
DIR="$(cd "$(dirname "$0")" && pwd)"
case " $* " in
  *" -fullscreen "*) MODE="" ;;
  *) MODE="-windowed -ResX=1920 -ResY=1080" ;;
esac
open -n "$ENGINE/Engine/Binaries/Mac/UnrealEditor.app" --args "$DIR/FourthAndFury.uproject" -game $MODE "$@"
