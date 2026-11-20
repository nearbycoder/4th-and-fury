#!/usr/bin/env bash
# Rebuild everything in web/public/assets from the game's sources.
#
#   web/tools/build_assets.sh [step ...]      steps: venv textures gltf quantize crowd audio fonts check (check = gltf-transform validate + three.js binding test) (default: all)
#
# Tools: Blender 5.x (BLENDER), ffmpeg (FFMPEG), python3, npx (for @gltf-transform/cli).
# Scratch output goes to FURY_SCRATCH (default /private/tmp/fury_web), never into the repo.
# Reads Art/, FourthAndFury/AudioSource, FourthAndFury/Content/Fonts; never launches Unreal.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/web/public/assets"
BLENDER="${BLENDER:-/opt/homebrew/bin/blender}"
FFMPEG="${FFMPEG:-/opt/homebrew/bin/ffmpeg}"
export FURY_SCRATCH="${FURY_SCRATCH:-/private/tmp/fury_web}"
VENV="$FURY_SCRATCH/venv"
GLTF_TRANSFORM="@gltf-transform/cli@4.5.1"

steps=("$@")
[ ${#steps[@]} -eq 0 ] && steps=(venv textures gltf quantize crowd audio fonts check)
mkdir -p "$FURY_SCRATCH" "$OUT"

for step in "${steps[@]}"; do
  echo "=== $step"
  case "$step" in
    venv)
      [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
      "$VENV/bin/pip" -q install pillow numpy fonttools brotli
      ;;
    textures)
      "$VENV/bin/python" "$HERE/convert_textures.py" --out "$OUT/textures"
      ;;
    gltf)
      # needs $FURY_SCRATCH/ads_gltf.jpg from the textures step
      "$BLENDER" -b --factory-startup --python "$HERE/export_gltf.py" -- --out "$OUT" 2>&1 \
        | grep -E '^\[export_gltf\]|Error|Traceback|AssertionError' || true
      [ -s "$OUT/characters/anims.glb" ] && [ -s "$OUT/stadium/stadium.glb" ]
      ;;
    quantize)
      # The bowl is ~250k vertices: 16-bit positions (4 mm over 267 m) and 8-bit normals via
      # KHR_mesh_quantization, which three's GLTFLoader reads without a decoder. UVs stay float.
      cp "$OUT/stadium/stadium.glb" "$FURY_SCRATCH/stadium_raw.glb"
      npx -y "$GLTF_TRANSFORM" quantize "$FURY_SCRATCH/stadium_raw.glb" "$OUT/stadium/stadium.glb" \
        --quantize-position 16 --quantize-normal 8
      ;;
    crowd)
      python3 "$HERE/convert_crowd.py"
      ;;
    audio)
      python3 "$HERE/convert_audio.py" --ffmpeg "$FFMPEG"
      ;;
    fonts)
      "$VENV/bin/python" "$HERE/convert_fonts.py"
      ;;
    check)
      for f in "$OUT"/characters/*.glb "$OUT"/stadium/*.glb; do
        npx -y "$GLTF_TRANSFORM" validate "$f" > "$FURY_SCRATCH/validate_$(basename "$f").txt" 2>&1 \
          && echo "valid  $(basename "$f")" || { echo "INVALID $f"; cat "$FURY_SCRATCH/validate_$(basename "$f").txt"; }
      done
      python3 "$HERE/inspect_glb.py" "$OUT/characters/anims.glb" --anims | grep -c "anim " | xargs echo "animations:"
      node "$HERE/verify_three.mjs" | grep -v "^ok   clip "
      find "$OUT" -type f -size +10M -exec echo "OVER 10 MB: {}" \;
      du -sh "$OUT"
      ;;
    *) echo "unknown step $step"; exit 1 ;;
  esac
done
