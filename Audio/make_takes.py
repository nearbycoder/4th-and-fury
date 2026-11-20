"""Generate the dry performances in Audio/takes on Apple Silicon with mlx-audio installed.

The game and its normal audio build use the saved PCM takes. Run this script only to
replace performances. Pass asset names to generate individual replacements.
"""
from pathlib import Path
import sys
import zlib

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model
from fury.catalog import VO_LINES

MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16"
OUT = Path(__file__).parent / "takes"
FIELD = {**{f"SFX_Hut_{i}": line for i, line in enumerate(("Hut!", "Hup!"), 1)},
         **{f"SFX_Grunt_{i}": line for i, line in enumerate(("Ugh!", "Oof!", "Hngh!", "Argh!"), 1)}}


def main():
    OUT.mkdir(exist_ok=True)
    model = load_model(MODEL)
    for name, text in (FIELD | VO_LINES).items():
        if sys.argv[1:] and name not in sys.argv[1:]:
            continue
        mx.random.seed(zlib.crc32(name.encode()))
        if name.startswith("SFX_Hut"):
            direction = "American quarterback barking a single explosive snap count from his diaphragm. Short and sharp."
        elif name.startswith("SFX"):
            direction = "A short involuntary grunt of physical exertion during a football tackle. Breath pushed out."
        else:
            direction = "American football stadium announcer, resonant and upbeat. Project to the back row. Crisp, quick call."
        if name in {"VO_Title", "VO_BigGain_1", "VO_BigGain_2", "VO_Interception_2", "VO_Team_volcanoes", "VO_Punt"}:
            direction = "American football broadcaster. Speak clearly at a measured pace with precise consonants and warm, natural emphasis."
        if name == "VO_Team_volcanoes":
            text = "The Honolulu Volcanos!"
        take = next(model.generate_custom_voice(text, speaker="Ryan", language="English",
                                                instruct=direction, max_tokens=85))
        sf.write(OUT / (name + ".wav"), np.asarray(take.audio).squeeze(), take.sample_rate)
        print(name, flush=True)


if __name__ == "__main__":
    main()
