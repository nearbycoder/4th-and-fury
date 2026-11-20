#!/bin/sh
# Compile the game module, then (re)import art and audio when asked or when content is missing.
#
#   ./build.sh              compile only (imports everything once if Content/Fury is empty)
#   ./build.sh --assets     compile, then re-import every asset group
#   ./build.sh --assets characters anims     re-import just those groups
#
# Other Unreal projects on this machine share the same source-built engine. Whenever one of them
# rebuilds engine-side modules, the engine's build id changes and this project's module manifest
# goes stale ("module could not be found"). So the manifest is checked after every build and
# regenerated when it no longer matches.
set -e
ENGINE="${UE_ENGINE_DIR:-$HOME/UnrealEngine}"
DIR="$(cd "$(dirname "$0")" && pwd)"
UBT="$ENGINE/Engine/Build/BatchFiles/Mac/Build.sh"
EDITOR="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
MANIFEST="$DIR/Binaries/Mac/UnrealEditor.modules"

build_id() { sed -n 's/.*"BuildId": *"\([^"]*\)".*/\1/p' "$1" 2>/dev/null | head -1; }

compile() {
  "$UBT" FourthAndFuryEditor Mac Development -Project="$DIR/FourthAndFury.uproject" -WaitMutex
}

compile
if [ "$(build_id "$MANIFEST")" != "$(build_id "$ENGINE/Engine/Binaries/Mac/UnrealEditor.version")" ]; then
  echo "Module manifest is stale against the engine build id; regenerating."
  rm -f "$MANIFEST"
  compile
fi

if [ "$1" = "--assets" ] || [ ! -d "$DIR/Content/Fury" ]; then
  [ "$1" = "--assets" ] && shift
  "$EDITOR" "$DIR/FourthAndFury.uproject" -run=pythonscript -script="$DIR/Scripts/import_assets.py $*" \
    -unattended -nopause -nosplash -AllowCommandletRendering
fi
