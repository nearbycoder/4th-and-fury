#!/bin/sh
# Build a standalone copy of the game for this Mac: compiles the game target, cooks the content,
# and leaves a double-clickable app in Packaged/.
#
#   ./package.sh              Development build (keeps the log and the -Fury* test switches)
#   ./package.sh Shipping     release build and a verified ZIP with the play guide
#
# The first run compiles the engine for the game target, which takes a while; later runs are quick.
# The app is ad-hoc signed and sandboxed (entitlements in Build/Mac/Resources). Console builds use
# the same project but require the platform SDK, Unreal platform support and device testing.
set -e
ENGINE="${UE_ENGINE_DIR:-$HOME/UnrealEngine}"
DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-Development}"
case "$CONFIG" in Development|Shipping) ;; *) echo "Use Development or Shipping" >&2; exit 2;; esac
"$ENGINE/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project="$DIR/FourthAndFury.uproject" -platform=Mac \
  -clientconfig="$CONFIG" -build -cook -stage -pak -nocompileeditor -nop4 -utf8output -unattended

# Staging assembles the complete bundle (program, engine data and cooked game data inside it).
PRODUCT=FourthAndFury
if [ "$CONFIG" = Shipping ]; then PRODUCT=FourthAndFury-Mac-Shipping; fi
STAGED="$DIR/Saved/StagedBuilds/Mac/$PRODUCT.app"
[ -d "$STAGED/Contents/UE" ] || { echo "Staged app is incomplete: $STAGED"; exit 1; }
mkdir -p "$DIR/Packaged"
set -- "$STAGED" "$DIR/Packaged/FourthAndFury.app"
if [ "$CONFIG" = Shipping ]; then set -- "$@" "$DIR/../Contest/Play.txt"; fi
python3 "$DIR/Scripts/install_mac_build.py" "$@"
echo "Packaged: $DIR/Packaged/FourthAndFury.app"
