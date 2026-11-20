# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1", "torch", "transformers"]
# ///
"""QC helper: a second machine "ear" -- zero-shot text/audio matching with LAION-CLAP.

For each WAV, scores how well it matches each of a list of text descriptions (soft-max over the
list), so a sound can be tested against what it is meant to be and against the things a bad
synthesis tends to sound like instead ("static", "a synthesizer", "water" ...).

    uv run Audio/qc/describe.py --prompts "a referee whistle|a bird|a synthesizer beep" FILE.wav ...
    uv run Audio/qc/describe.py FILE.wav ...          # uses a built-in prompt set chosen by file name

Downloads the model (~600 MB) from Hugging Face on first use. Not needed to build the audio.
"""
import argparse
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from fury.wavio import read_wav  # noqa: E402

BAD = ["static, white noise", "a synthesizer, electronic beep", "water flowing, rain"]
SETS = [
    ("AMB_CrowdLow", ["a stadium crowd murmuring and chattering", "a large crowd cheering and roaring in a stadium", "wind blowing"]),
    ("AMB_CrowdHigh", ["a large crowd cheering and roaring in a stadium", "a stadium crowd murmuring and chattering", "a siren"]),
    ("AMB_Cheer", ["a crowd erupting in cheers and applause", "a crowd booing", "a siren"]),
    ("AMB_Ooh", ["a crowd going ooh in surprise", "a crowd cheering", "a crowd booing", "a cow mooing"]),
    ("AMB_Boo", ["a crowd booing", "a crowd cheering", "a cow mooing", "a foghorn"]),
    ("AMB_Chant", ["a crowd stomping, clapping and chanting in rhythm", "a drum kit playing", "a crowd cheering"]),
    ("AMB_Night", ["quiet outdoor night ambience with an electrical hum", "a crowd", "wind blowing", "silence"]),
    ("SFX_Hit", ["a football tackle, bodies and pads colliding", "a punch", "a drum hit", "a gunshot"]),
    ("SFX_BigHit", ["a huge explosive impact", "a football tackle, bodies and pads colliding", "a drum hit", "thunder"]),
    ("SFX_Whistle", ["a referee blowing a whistle", "a bird singing", "a kettle whistling", "a flute"]),
    ("SFX_Fireworks", ["fireworks launching and exploding", "a gunshot", "thunder", "a drum hit"]),
    ("SFX_Cannon", ["a cannon firing, a big boom", "a drum hit", "thunder", "a door slamming"]),
    ("SFX_Horn", ["a stadium horn, a buzzer", "a car horn", "a trumpet", "a foghorn"]),
    ("SFX_Fury", ["fire igniting and roaring", "wind blowing", "an explosion", "a crackling fire"]),
    ("MUS_", ["energetic rock music with drums and electric guitar", "calm relaxed funk music", "tense suspenseful music",
              "a triumphant brass fanfare", "noise"]),
    ("VO_", ["a stadium announcer speaking over a loudspeaker", "a person speaking in a quiet room", "a robot voice", "music"]),
]


def prompts_for(name, override):
    if override:
        return override
    for prefix, ps in SETS:
        if name.startswith(prefix):
            return ps + BAD
    return ["a sound effect", "music", "speech"] + BAD


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--prompts", default=None, help="descriptions separated by |")
    a = ap.parse_args()
    import torch
    import transformers
    from transformers import ClapModel, ClapProcessor
    transformers.logging.set_verbosity_error()
    model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
    proc = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")
    override = a.prompts.split("|") if a.prompts else None
    cache = {}

    def feats(out):
        e = out.pooler_output if hasattr(out, "pooler_output") else out
        return e / e.norm(dim=-1, keepdim=True)

    for path in a.files:
        name = os.path.basename(path)[:-4]
        ps = prompts_for(name, override)
        x, sr = read_wav(path)
        m = (x if x.ndim == 1 else x.mean(axis=1)).astype(np.float32)
        m = m / max(float(np.max(np.abs(m))), 1e-9) * 0.5
        with torch.no_grad():
            key = tuple(ps)
            if key not in cache:
                cache[key] = feats(model.get_text_features(**proc(text=ps, return_tensors="pt", padding=True)))
            au = feats(model.get_audio_features(**proc(audio=[m], sampling_rate=sr, return_tensors="pt")))
            p = ((au @ cache[key].T)[0] * model.logit_scale_a.exp()).softmax(-1).numpy()
        order = np.argsort(-p)
        print(f"{name:<22s} " + "; ".join(f"{ps[i]} {p[i]:.2f}" for i in order[:4]))


if __name__ == "__main__":
    main()
