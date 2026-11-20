"""Athlete animation toolkit for 4th & Fury (driven by ../build_anims.py).

    skel.py          the shared skeleton as plain maths: rest frames, forward kinematics, Pose
    controls.py      the control rig: semantic body / limb controls -> Pose (FK, two-bone IK,
                     planted feet, ball grips, ground contact)
    curves.py        keyed channels, easing and interpolation of controls
    clip.py          Clip (keys + procedural modifiers + events), sampling, diagnostics
    gait.py          stepping cycles built from foot paths (run, jog, backpedal, shuffle...)
    poses.py         anchor poses and building blocks shared by the clips
    clips_loco.py    tier 1: locomotion loops and stances
    clips_action.py  tier 2: the core football actions
    clips_fun.py     tier 3: celebrations, gestures and the silliest hits
    library.py       every clip, in export order
    bake.py          Pose samples -> Blender action; the manifest file
    dummy.py         preview stand-ins: mannequin (left limbs blue, right limbs orange), football, field
    preview.py       contact sheets, the overview sheet and the static pose sheets
    selftest.py      checks of the control rig's conventions (build_anims.py -- --selftest)

Conventions used throughout: metres, Z up, the character faces -Y and its left is +X; angles in
degrees; a clip of N frames is sampled on frames 0..N at 30 fps; the root bone never moves.
"""
