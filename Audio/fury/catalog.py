"""The full list of audio files the game expects, with the brief's constraints.

Each entry: name, category, group, allowed duration range (s), loop flag, channel count
(1, 2 or None = either), optional spoken text and extra metadata (bpm, bars).
The generators produce exactly these names; verify_audio.py checks them and writes the manifest.
"""

TEAMS = [
    ("sasquatch", "The Portland Sasquatch!"),
    ("volcanoes", "The Honolulu Volcanoes!"),
    ("icebreakers", "The Anchorage Icebreakers!"),
    ("hellhounds", "The Memphis Hellhounds!"),
    ("twisters", "The Omaha Twisters!"),
    ("amps", "The Austin Amps!"),
    ("scorpions", "The Tucson Scorpions!"),
    ("gargoyles", "The Brooklyn Gargoyles!"),
]

# Spoken lines (all original). Key -> text as it should be heard.
VO_LINES = {
    "VO_Title": "Fourth and Fury!",
    "VO_Welcome_1": "Welcome, football fans, to Fourth and Fury!",
    "VO_Welcome_2": "It's game night under the lights!",
    **{f"VO_Team_{key}": text for key, text in TEAMS},
    "VO_Kickoff_1": "Get ready for the kickoff!",
    "VO_Kickoff_2": "The ball is on the tee. Here we go!",
    "VO_Touchdown_1": "Touchdown!",
    "VO_Touchdown_2": "He's in! Touchdown!",
    "VO_Touchdown_3": "Six points on the board!",
    "VO_Touchdown_4": "Into the end zone! Touchdown!",
    "VO_FirstDown_1": "First down!",
    "VO_FirstDown_2": "The chains are moving!",
    "VO_FirstDown_3": "That's a fresh set of downs!",
    "VO_Sack_1": "That's a sack!",
    "VO_Sack_2": "The quarterback goes down!",
    "VO_Sack_3": "Nowhere to hide! He's down!",
    "VO_Interception_1": "Intercepted!",
    "VO_Interception_2": "Picked off!",
    "VO_Interception_3": "Stolen out of the sky!",
    "VO_Fumble_1": "Fumble!",
    "VO_Fumble_2": "The football is loose!",
    "VO_BigHit_1": "What a hit!",
    "VO_BigHit_2": "He got flattened!",
    "VO_BigHit_3": "That hit shook the stadium!",
    "VO_BigHit_4": "Check the field for a crater!",
    "VO_Incomplete_1": "Incomplete!",
    "VO_Incomplete_2": "He couldn't hang on!",
    "VO_Incomplete_3": "Off the fingertips. Incomplete!",
    "VO_BigGain_1": "Big gain on the play!",
    "VO_BigGain_2": "He breaks loose!",
    "VO_BigGain_3": "That's a huge pickup!",
    "VO_Fury_1": "Fury mode!",
    "VO_Fury_2": "The fury is unleashed!",
    "VO_Fury_3": "They are unstoppable!",
    "VO_Turnover": "Turnover on downs!",
    "VO_Safety": "Safety! Two points!",
    "VO_FieldGoalGood": "The kick is good!",
    "VO_FieldGoalNoGood": "No good! The kick is wide!",
    "VO_ExtraPointGood": "The extra point is good!",
    "VO_TwoPointGood": "The two point try is good!",
    "VO_TwoPointNoGood": "Two point try, no good!",
    "VO_Punt": "They're punting it away!",
    "VO_Quarter2": "Second quarter!",
    "VO_Quarter3": "Third quarter!",
    "VO_Quarter4": "Fourth quarter! This is it!",
    "VO_Halftime": "That's the half!",
    "VO_TwoMinute": "The clock is running out! Now or never!",
    "VO_Overtime": "We're going to overtime!",
    "VO_Final_1": "That's the game!",
    "VO_Final_2": "Final whistle! It's all over!",
    "VO_Win_Home": "Victory for the home team!",
    "VO_Win_Away": "The visitors take the win!",
}

# Music timing (also used by make_music.py / make_crowd.py so the two can never disagree).
MUSIC = {
    "MUS_Menu": {"bpm": 125.0, "bars": 32},
    "MUS_PlaySelect": {"bpm": 120.0, "bars": 8},
    "MUS_Halftime": {"bpm": 96.0, "bars": 16},
}
CHANT = {"bpm": 112.0, "bars": 8}


def _bars_seconds(spec):
    return spec["bars"] * 4 * 60.0 / spec["bpm"]


def _e(name, category, group, dur, loop=False, channels=1, text=None, **meta):
    lo, hi = dur if isinstance(dur, tuple) else (dur * 0.93, dur * 1.07)
    return {"name": name, "category": category, "group": group, "min_s": round(lo, 4), "max_s": round(hi, 4),
            "loop": loop, "channels": channels, "text": text, "meta": meta}


def _var(base, count, *args, **kw):
    return [_e(f"{base}_{i}", *args, **kw) for i in range(1, count + 1)]


def entries():
    out = []
    fb, fury, ui, sting = "football", "fury", "interface", "stinger"
    out += _var("SFX_Hit", 4, "sfx", fb, (0.3, 0.5))
    out += _var("SFX_BigHit", 3, "sfx", fb, (0.7, 1.0))
    out += _var("SFX_Dive", 2, "sfx", fb, 0.4)
    out += _var("SFX_Throw", 2, "sfx", fb, 0.25)
    out += [_e("SFX_BallAir", "sfx", fb, 1.0, loop=True)]
    out += _var("SFX_Catch", 3, "sfx", fb, (0.15, 0.25))
    out += [_e("SFX_Drop", "sfx", fb, 0.3), _e("SFX_Bounce", "sfx", fb, 0.25)]
    out += _var("SFX_Kick", 2, "sfx", fb, 0.4)
    out += [_e("SFX_Snap", "sfx", fb, 0.12)]
    out += _var("SFX_Hut", 3, "sfx", fb, (0.12, 0.42))
    out += _var("SFX_Grunt", 4, "sfx", fb, (0.12, 0.48))
    out += _var("SFX_Cleat", 6, "sfx", fb, 0.16)
    out += [_e("SFX_Steps", "sfx", fb, 0.5, loop=True),
            _e("SFX_Whistle", "sfx", fb, 0.6), _e("SFX_WhistleLong", "sfx", fb, 1.2),
            _e("SFX_Spin", "sfx", fb, 0.3), _e("SFX_StiffArm", "sfx", fb, 0.25), _e("SFX_Juke", "sfx", fb, 0.2),
            _e("SFX_Fumble", "sfx", fb, 0.4), _e("SFX_Goalpost", "sfx", fb, 0.8)]
    out += [_e("SFX_FuryIgnite", "sfx", fury, 1.5), _e("SFX_FuryLoop", "sfx", fury, 2.0, loop=True),
            _e("SFX_FuryEnd", "sfx", fury, 0.8), _e("SFX_MeterTick", "sfx", fury, 0.1)]
    for n in ("UIMove", "UISelect", "UIBack", "UIJoin", "UIReady", "UIError", "UIPage",
              "PlayPicked", "Countdown", "CountdownGo"):
        out.append(_e("SFX_" + n, "sfx", ui, (0.05, 0.4)))
    out += [_e("SFX_Touchdown", "sfx", sting, 3.0, channels=None),
            _e("SFX_FirstDown", "sfx", sting, 0.8, channels=None),
            _e("SFX_Turnover", "sfx", sting, 1.2, channels=None),
            _e("SFX_Sack", "sfx", sting, 0.9, channels=None),
            _e("SFX_FieldGoalGood", "sfx", sting, 1.5, channels=None),
            _e("SFX_NoGood", "sfx", sting, 1.0, channels=None),
            _e("SFX_Horn", "sfx", sting, 2.0, channels=None)]
    out += _var("SFX_Fireworks", 3, "sfx", sting, (1.5, 2.5), channels=None)
    out += [_e("SFX_Cannon", "sfx", sting, 1.5, channels=None)]

    amb = "crowd"
    out += [_e("AMB_CrowdLow", "ambience", amb, (12.0, 16.0), loop=True, channels=2),
            _e("AMB_CrowdHigh", "ambience", amb, (12.0, 16.0), loop=True, channels=2)]
    out += _var("AMB_Cheer", 3, "ambience", amb, (4.0, 6.8), channels=2)
    out += _var("AMB_Ooh", 2, "ambience", amb, (1.5, 2.0), channels=2)
    out += [_e("AMB_Boo", "ambience", amb, 3.0, channels=2),
            _e("AMB_Chant", "ambience", amb, _bars_seconds(CHANT) * 1.0, loop=True, channels=2, **CHANT),
            _e("AMB_Night", "ambience", "bed", 10.0, loop=True, channels=2)]

    for name, spec in MUSIC.items():
        out.append(_e(name, "music", "loop", _bars_seconds(spec), loop=True, channels=2, **spec))
    out.append(_e("MUS_Victory", "music", "fanfare", (6.0, 8.0), channels=2))

    for key, text in VO_LINES.items():
        out.append(_e(key, "voice", "announcer", (0.4, 6.0), text=text))
    return out


def by_name():
    return {e["name"]: e for e in entries()}
