#!/usr/bin/env python3
"""FourthAndFury/AudioSource/*.wav -> web/public/assets/audio/*.mp3 + audio/manifest.json

    python3 web/tools/convert_audio.py [--ffmpeg /opt/homebrew/bin/ffmpeg]

Encoding (libmp3lame, CBR, 48 kHz kept):
    music              stereo 160 kbps
    ambience           stereo 128 kbps
    sfx group stinger  stereo 128 kbps (the 11 stereo stingers)
    sfx / voice        mono    96 kbps

The manifest carries what the game knows about each clip: category, group, loop flag, the bus it plays on
(UFuryAudio::ChannelFor), the volume the game passes at its call sites (FuryDirector*.cpp / FuryAudio.cpp),
duration and exact sample count of the source, and the announcer caption text.
"""
import argparse
import json
import os
import subprocess
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(REPO, "FourthAndFury", "AudioSource")
DST = os.path.join(REPO, "web", "public", "assets", "audio")

# Volume (and pitch) at the game's call sites, keyed by clip name or by the base name of a numbered set
# (PlayOneOf / SayOneOf pick <Base>_<1..Count> at random). First entry = the usual case.
CALLS = {
    "SFX_UIBack": [1.0], "SFX_UISelect": [1.0], "SFX_UIPage": [1.0], "SFX_UIJoin": [1.0], "SFX_UIReady": [1.0],
    "SFX_UIError": [1.0], "SFX_UIMove": [1.0, "0.7 (team carousel)", "0.7 at pitch 1.3"],
    "SFX_Kick": [1.0], "SFX_NoGood": [1.0], "SFX_Grunt": [0.5], "SFX_Turnover": [1.0, 0.8],
    "SFX_FieldGoalGood": [1.0, 0.6], "SFX_Countdown": [1.0, 0.8], "SFX_CountdownGo": [1.0], "SFX_Throw": [0.8],
    "SFX_Hut": [0.6], "SFX_Hit": [0.75, "0.55 + 0.45 * impact (0..1)", 0.45], "SFX_Fireworks": [0.55, "0.55, pitch 1 +- 0.1"],
    "SFX_Dive": [0.7], "SFX_Cleat": [0.4, "clamp(carrier speed cm/s / 1800, 0.2, 0.6), pitch 1 +- 0.1"],
    "SFX_Catch": [0.9, 0.8], "SFX_BigHit": [1.0, 0.85], "SFX_WhistleLong": [0.7], "SFX_Whistle": [0.7],
    "SFX_Touchdown": [1.0], "SFX_StiffArm": [0.9], "SFX_Spin": [0.7, "0.6 at pitch 1.25"], "SFX_Snap": [0.8],
    "SFX_Sack": [1.0], "SFX_PlayPicked": [0.7], "SFX_MeterTick": [0.9, "0.9 at pitch 1.25", "0.6 at pitch 0.8"],
    "SFX_Juke": [0.7], "SFX_Horn": [1.0], "SFX_Goalpost": [1.0], "SFX_FuryIgnite": [1.0], "SFX_FuryEnd": [0.8],
    "SFX_Fumble": [1.0], "SFX_FirstDown": [0.8], "SFX_Drop": [0.8], "SFX_Cannon": [0.8], "SFX_Bounce": [0.6],
    "SFX_FuryLoop": [0.45, "loop 0.45 while either team is in Fury (fade in 4/s, out 2.5/s)"],
    "SFX_BallAir": [0.3, "loop 0.18 + 0.27 * approach, pitch 0.94 + 0.28 * approach, while a pass is in the air"],
    "SFX_Steps": ["not played by the game"],
    "AMB_Cheer": [0.9, 0.8, 1.0, 0.7], "AMB_Ooh": [0.9, "0.7 heavy hit / 0.4 light"], "AMB_Boo": [0.7],
    "AMB_Chant": [0.42, "loop 0.42 on a big down (lineup / pre-snap)"],
    "AMB_CrowdLow": [1.0, "loop presence * (0.35 + 0.65 * cos(level * pi/2))"],
    "AMB_CrowdHigh": [0.9, "loop presence * 0.9 * sin(level * pi/2)"],
    "AMB_Night": [0.25, "loop 0.25 (constant)"],
    "MUS_Menu": [0.6, "0.4 on the final screen"], "MUS_PlaySelect": [0.32], "MUS_Halftime": [0.5], "MUS_Victory": [0.7],
}


def bus_for(name):
    if name.startswith("MUS_"):
        return "music"
    if name.startswith("VO_"):
        return "announcer"
    if name.startswith("AMB_"):
        return "ambience"
    if name.startswith("SFX_UI"):
        return "interface"
    return "field"


def calls_for(name):
    if name in CALLS:
        return CALLS[name]
    base = name.rsplit("_", 1)[0] if name.rsplit("_", 1)[-1].isdigit() else name
    if base in CALLS:
        return CALLS[base]
    if name.startswith("VO_"):
        return [1.0]
    return None


def encoding(entry):
    if entry["category"] == "music":
        return 2, "160k"
    if entry["category"] == "ambience":
        return 2, "128k"
    if entry["channels"] == 2:
        return 2, "128k"
    return 1, "96k"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    args = ap.parse_args()
    manifest = json.load(open(os.path.join(SRC, "audio_manifest.json")))
    os.makedirs(DST, exist_ok=True)
    entries = []
    total = 0
    for entry in manifest["files"]:
        name = entry["name"]
        wav_path = os.path.join(SRC, entry["file"])
        with wave.open(wav_path) as w:
            frames, rate, channels = w.getnframes(), w.getframerate(), w.getnchannels()
        out_channels, bitrate = encoding(entry)
        mp3 = name + ".mp3"
        subprocess.run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", wav_path,
                        "-ac", str(out_channels), "-ar", str(rate), "-codec:a", "libmp3lame", "-b:a", bitrate,
                        "-write_xing", "1", "-id3v2_version", "0", "-map_metadata", "-1",
                        os.path.join(DST, mp3)], check=True)
        size = os.path.getsize(os.path.join(DST, mp3))
        total += size
        calls = calls_for(name)
        numeric = [c for c in (calls or []) if isinstance(c, (int, float))]
        item = dict(
            name=name, file=mp3, category=entry["category"], group=entry["group"], bus=bus_for(name),
            loop=bool(entry["loops"]), volume=numeric[0] if numeric else (0.0 if name == "SFX_Steps" else 1.0),
            duration=round(frames / rate, 6), samples=frames, sample_rate=rate,
            channels=out_channels, source_channels=channels, bitrate=bitrate, lufs=entry.get("lufs"),
        )
        if calls and (len(calls) > 1 or not numeric):
            item["volume_notes"] = [str(c) for c in calls]
        for key in ("text", "bpm", "bars"):
            if key in entry:
                item[key] = entry[key]
        entries.append(item)
    out = dict(
        source="FourthAndFury/AudioSource/audio_manifest.json + call sites in FourthAndFury/Source (see web/tools/convert_audio.py)",
        format="mp3 (libmp3lame CBR, 48 kHz, LAME/Xing header with encoder delay + padding)",
        buses=dict(music="MUS_*", announcer="VO_*", ambience="AMB_*", interface="SFX_UI*", field="every other SFX_*"),
        notes=dict(
            volume="`volume` is the linear gain the game passes when it plays the clip (first call site); "
                   "`volume_notes` lists the other call sites or the formula for clips the game drives continuously. "
                   "The bus gain (options master * per-bus slider) multiplies on top.",
            loops="Loops: the decoded buffer should be exactly `samples` long. If a browser ignores the LAME gapless "
                  "header the buffer comes back longer; then set loopStart = 1105 / sample_rate (LAME's encoder delay), "
                  "loopEnd = loopStart + duration.",
            crossfade=manifest["notes"].get("crossfade"),
            voice=manifest["notes"].get("voice"),
        ),
        count=len(entries),
        files=entries,
    )
    with open(os.path.join(DST, "manifest.json"), "w") as handle:
        json.dump(out, handle, indent=1)
    print("audio: %d files, %.2f MB" % (len(entries), total / 1048576))


if __name__ == "__main__":
    main()
