# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""4th & Fury -- build ALL of the game's audio, then verify it and write the manifest.

    uv run Audio/make_audio.py                 # everything (about 3 minutes)
    uv run Audio/make_audio.py sfx music       # only some parts: sfx, crowd, music, voice
    uv run Audio/make_audio.py --no-verify

Output: FourthAndFury/AudioSource/*.wav (48 kHz, 16-bit PCM) and audio_manifest.json.
Everything is seeded, so re-running reproduces the same files. The voice build uses the saved dry takes.
"""
import sys
import time

import make_crowd
import make_music
import make_sfx
import make_voice
import verify_audio

PARTS = {"sfx": make_sfx.main, "crowd": make_crowd.main, "music": make_music.main, "voice": make_voice.main}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    unknown = [a for a in args if a not in PARTS]
    if unknown:
        sys.exit(f"unknown part(s) {unknown}; choose from {list(PARTS)}")
    t_all = time.time()
    for name, fn in PARTS.items():
        if args and name not in args:
            continue
        t0 = time.time()
        fn([])
        print(f"-- {name}: {time.time() - t0:.0f} s\n", flush=True)
    code = 0
    if "--no-verify" not in flags:
        code = verify_audio.main(["--quiet"] if "--quiet" in flags else [])
    print(f"Total {time.time() - t_all:.0f} s")
    sys.exit(code)


if __name__ == "__main__":
    main()
