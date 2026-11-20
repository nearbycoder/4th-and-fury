# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""4th & Fury -- measure every generated WAV, check it against the brief, write the manifest.

    uv run Audio/verify_audio.py [--quiet]

Checks (per file): present, 48 kHz / 16-bit PCM, channel count, duration in range, sample peak
<= -1 dBFS, no clipped samples, no DC offset, no dead air at the head, a faded tail (one-shots),
and for loops that the last samples flow into the first:
  * the step across the join is an ordinary sample-to-sample step,
  * a linear predictor trained on the file predicts the samples after the join as well as it
    predicts any others (a click is, by definition, unpredictable),
  * octave-band levels do not jump across the join more than they do inside the loop.
Writes FourthAndFury/AudioSource/audio_manifest.json and exits non-zero if anything fails.
"""
import json
import os
import sys
import wave

import numpy as np

from fury import catalog, measure
from fury.core import SR
from fury.wavio import OUT_DIR, read_wav

MANIFEST = os.path.join(OUT_DIR, "audio_manifest.json")
PEAK_LIMIT_DB = -1.0
HEAD_MAX_S = {"sfx": 0.03, "ambience": 0.12, "music": 0.06, "voice": 0.06}


def check(entry):
    """Returns (manifest_row or None, problems, figures)."""
    name = entry["name"]
    path = os.path.join(OUT_DIR, name + ".wav")
    problems = []
    if not os.path.exists(path):
        return None, ["missing"], {}
    with wave.open(path, "rb") as w:
        ch, width, sr, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = np.frombuffer(w.readframes(frames), dtype="<i2")
    if sr != SR:
        problems.append(f"sample rate {sr}")
    if width != 2:
        problems.append(f"{width * 8}-bit")
    if entry["channels"] is not None and ch != entry["channels"]:
        problems.append(f"{ch} channels (want {entry['channels']})")
    x, _ = read_wav(path)
    dur = frames / sr
    if not (entry["min_s"] - 1e-6 <= dur <= entry["max_s"] + 1e-6):
        problems.append(f"duration {dur:.3f}s outside {entry['min_s']}-{entry['max_s']}s")
    s = measure.summarize(x, loop=entry["loop"])
    if s["peak_dbfs"] > PEAK_LIMIT_DB + 1e-9:
        problems.append(f"peak {s['peak_dbfs']} dBFS")
    clipped = int(np.sum(np.abs(raw.astype(np.int32)) >= 32767))
    if clipped:
        problems.append(f"{clipped} clipped samples")
    if s["dc"] > 1e-3:
        problems.append(f"DC offset {s['dc']:.5f}")
    if s["head_silence_s"] > HEAD_MAX_S[entry["category"]] and not entry["loop"]:
        problems.append(f"{s['head_silence_s'] * 1000:.0f} ms of silence at the head")
    figures = dict(s)
    seam = None
    if entry["loop"]:
        seam = measure.seam_report(x)
        figures.update(seam)
        if seam["lpc_ratio"] > 2.0:
            problems.append(f"loop seam: prediction residual {seam['lpc_ratio']:.1f}x the 99.9th percentile (click)")
        if seam["step_ratio"] > 6.0:
            problems.append(f"loop seam: step {seam['step_ratio']:.1f}x RMS step")
        if seam["band_db"] > max(1.5 * seam["band_ref_db"], 4.0):
            problems.append(f"loop seam: band jump {seam['band_db']:.1f} dB (typical {seam['band_ref_db']:.1f})")
        if "bpm" in entry["meta"]:
            want = entry["meta"]["bars"] * 4 * 60.0 / entry["meta"]["bpm"]
            if abs(dur - want) > 0.002:
                problems.append(f"length {dur:.4f}s is not {entry['meta']['bars']} bars at {entry['meta']['bpm']} BPM ({want:.4f}s)")
    else:
        m = np.max(np.abs(x.reshape(len(x), -1)), axis=1)
        if m[0] > 4 / 32768 or m[-1] > 4 / 32768:
            problems.append("does not start/end at zero")
        k = int(0.002 * SR)
        if measure.db(np.sqrt(np.mean(m[-k:] ** 2))) > -45.0:
            problems.append("tail is cut off (last 2 ms above -45 dBFS)")
    row = {
        "name": name,
        "file": name + ".wav",
        "category": entry["category"],
        "group": entry["group"],
        "duration": round(dur, 4),
        "channels": ch,
        "loops": entry["loop"],
        "peak_dbfs": s["peak_dbfs"],
        "rms_dbfs": s["rms_dbfs"],
        "lufs": s["lufs"],
    }
    if entry["text"]:
        row["text"] = entry["text"]
    if entry["meta"]:
        row.update(entry["meta"])
    if seam:
        row["loop_seam"] = {"step_vs_rms_step": round(float(seam["step_ratio"]), 2),
                            "prediction_residual_vs_p99_9": round(float(seam["lpc_ratio"]), 2),
                            "band_jump_db": round(seam["band_db"], 1), "typical_band_jump_db": round(seam["band_ref_db"], 1)}
    return row, problems, figures


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    quiet = "--quiet" in args
    entries = catalog.entries()
    rows, failures = [], 0
    known = {e["name"] + ".wav" for e in entries}
    print(f"Verifying {len(entries)} files in {OUT_DIR}")
    if not quiet:
        print(f"{'file':<24s} {'sec':>6s} ch {'peak':>6s} {'rms':>6s} {'LUFS':>6s} {'head ms':>7s}  loop seam (step x, predict x, band dB / typ)")
    for e in entries:
        row, problems, f = check(e)
        if row:
            rows.append(row)
        if not quiet and row:
            seam = ""
            if e["loop"]:
                seam = f"  {f['step_ratio']:5.2f} {f['lpc_ratio']:5.2f}  {f['band_db']:4.1f} / {f['band_ref_db']:4.1f}"
            print(f"{e['name']:<24s} {row['duration']:6.2f} {row['channels']:>2d} {row['peak_dbfs']:6.1f} {row['rms_dbfs']:6.1f} "
                  f"{row['lufs']:6.1f} {f['head_silence_s'] * 1000:7.1f}{seam}")
        if problems:
            failures += 1
            print(f"  FAIL {e['name']}: " + "; ".join(problems))
    extra = sorted(f for f in os.listdir(OUT_DIR) if f.endswith(".wav") and f not in known)
    for f in extra:
        print(f"  note: {f} is not in the catalog")
    manifest = {
        "project": "4th & Fury",
        "generated_by": "Audio/make_audio.py",
        "sample_rate": SR,
        "bit_depth": 16,
        "count": len(rows),
        "notes": {
            "levels": "peak_dbfs and rms_dbfs are measured from the written 16-bit files; lufs is ITU-R BS.1770 integrated loudness",
            "voice": "Announcer and field vocals use saved Qwen3-TTS-12Hz-1.7B-CustomVoice performances (Ryan preset). See Audio/make_takes.py.",
            "crossfade": "AMB_CrowdLow and AMB_CrowdHigh are uncorrelated: use an equal-power cross-fade",
        },
        "files": rows,
    }
    with open(MANIFEST, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    total = sum(r["duration"] for r in rows)
    print(f"\n{len(rows)}/{len(entries)} files present, {total:.1f} s of audio, {failures} with problems. Manifest: {MANIFEST}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
