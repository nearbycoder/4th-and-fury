# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1", "faster-whisper"]
# ///
"""QC helper: check that the announcer lines are intelligible.

Transcribes each VO_*.wav with a speech recogniser (Whisper small.en via faster-whisper) and
compares the result with the line it is supposed to say (fury/catalog.py). A processed
stadium-PA line that a recogniser still gets word-for-word is a line a player will understand.

    uv run Audio/qc/transcribe.py [FILE.wav ...]        # default: every VO_*.wav in AudioSource

Downloads the model (~250 MB) on first use. Not needed to build the audio.
"""
import difflib
import glob
import os
import re
import sys

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from fury import catalog  # noqa: E402
from fury.wavio import OUT_DIR, read_wav  # noqa: E402

NUMBERS = {"2": "two", "1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth", "6": "six", "turnover": "turn over"}


def words(text):
    text = text.lower().replace("-", " ")
    out = [NUMBERS.get(w, w) for w in re.sub(r"[^a-z0-9' ]", " ", text).split()]
    return out


def main():
    from faster_whisper import WhisperModel
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(OUT_DIR, "VO_*.wav")))
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    scores = []
    for path in files:
        name = os.path.basename(path)[:-4]
        x, sr = read_wav(path)
        m = x if x.ndim == 1 else x.mean(axis=1)
        audio = signal.resample_poly(m, 16000, sr).astype(np.float32)
        audio = np.concatenate([np.zeros(4000, np.float32), audio, np.zeros(8000, np.float32)])
        segs, _ = model.transcribe(audio, beam_size=5, language="en", condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs)
        want = catalog.VO_LINES.get(name.split("__")[0])
        if want is None:
            print(f"{name:<24s} heard: {heard}")
            continue
        ratio = difflib.SequenceMatcher(None, " ".join(words(want)).split(), " ".join(words(heard)).split()).ratio()
        scores.append(ratio)
        flag = "ok " if ratio >= 0.999 else ("~  " if ratio >= 0.7 else "BAD")
        print(f"{flag} {name:<24s} {ratio:4.2f}  want: {want:<44s} heard: {heard}")
    if scores:
        print(f"\n{sum(s >= 0.999 for s in scores)}/{len(scores)} lines recognised word-for-word; mean match {np.mean(scores):.3f}")


if __name__ == "__main__":
    main()
