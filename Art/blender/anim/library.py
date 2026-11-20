"""Every clip of the set, in export order."""
from . import clips_action, clips_fun, clips_loco

BUILDERS = [
    # Tier 1 -- locomotion and stances
    ("Idle", clips_loco.idle),
    ("Run", clips_loco.run),
    ("Jog", clips_loco.jog),
    ("RunBall", clips_loco.run_ball),
    ("JogBall", clips_loco.jog_ball),
    ("Backpedal", clips_loco.backpedal),
    ("ShuffleL", clips_loco.shuffle_l),
    ("ShuffleR", clips_loco.shuffle_r),
    ("Ready", clips_loco.ready),
    ("Stance3", clips_loco.stance3),
    ("StanceCenter", clips_loco.stance_center),
    ("StanceQB", clips_loco.stance_qb),
    ("QBSet", clips_loco.qb_set),
    ("QBDrop", clips_loco.qb_drop),
    ("BlockLoop", clips_loco.block_loop),
    ("DownBack", clips_loco.down_back),
    ("DownFront", clips_loco.down_front),
    # Tier 2 -- core football actions
    ("Snap", clips_action.snap),
    ("CatchSnap", clips_action.catch_snap),
    ("Throw", clips_action.throw),
    ("Handoff", clips_action.handoff),
    ("CatchChest", clips_action.catch_chest),
    ("CatchHigh", clips_action.catch_high),
    ("Swat", clips_action.swat),
    ("DiveTackle", clips_action.dive_tackle),
    ("TackleWrap", clips_action.tackle_wrap),
    ("BigHit", clips_action.big_hit),
    ("Shove", clips_action.shove),
    ("HitBack", clips_action.hit_back),
    ("HitFront", clips_action.hit_front),
    ("HitFlip", clips_action.hit_flip),
    ("GetUpBack", clips_action.get_up_back),
    ("GetUpFront", clips_action.get_up_front),
    ("Stumble", clips_action.stumble),
    ("StiffArm", clips_action.stiff_arm),
    ("Spin", clips_action.spin),
    ("JukeL", clips_action.juke_l),
    ("JukeR", clips_action.juke_r),
    ("Hurdle", clips_action.hurdle),
    ("DiveBall", clips_action.dive_ball),
    ("Kick", clips_action.kick),
    ("Punt", clips_action.punt),
    ("PickUp", clips_action.pick_up),
    # Tier 3 -- personality
    ("CelebSpike", clips_fun.celeb_spike),
    ("CelebDance", clips_fun.celeb_dance),
    ("CelebFlex", clips_fun.celeb_flex),
    ("Dejected", clips_fun.dejected),
    ("Signal1st", clips_fun.signal_1st),
    ("HitSpin", clips_fun.hit_spin),
    ("ElbowDrop", clips_fun.elbow_drop),
    ("GroundHitBack", clips_fun.ground_hit_back),
    ("GroundHitFront", clips_fun.ground_hit_front),
]


def build_all(rig):
    """Return the Clip objects in export order."""
    made = {}
    clips = []
    for name, builder in BUILDERS:
        clip = builder(rig, made)
        if clip.name != name:
            raise ValueError(f"builder for {name} returned {clip.name}")
        made[name] = clip
        clips.append(clip)
    return clips
