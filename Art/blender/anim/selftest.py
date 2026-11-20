"""Checks of the control rig's conventions (run with build_anims.py -- --selftest)."""
import math

import bpy
from mathutils import Vector

from . import bake
from .controls import (DEFAULTS, ArmFK, ArmIK, LegFK, LegIK, Plant, mirror_controls)


def run(armature, rig):
    sk = rig.skel
    fails = []

    def check(name, ok, info=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {name} {info}")
        if not ok:
            fails.append(name)

    def solve(**kw):
        return rig.solve(dict(DEFAULTS, clamp=0.0, **kw))

    rest = {n: sk.head[n] for n in sk.names}

    # rest pose is reproduced by the default arms only if asked for; legs must match exactly
    p = solve(legL=Plant(0.105, 0.01, out=0.0), legR=Plant(-0.105, 0.01, out=0.0))
    err = max((p.head(n) - rest[n]).length for n in ("foot_l", "ball_l", "foot_r", "ball_r"))
    check("default Plant = rest feet", err < 2e-3, f"{err:.4f}")
    check("toe tip on ground", abs(p.tail("ball_l").z - sk.tail["ball_l"].z) < 1e-3)

    # pelvis
    p = solve(pitch=30.0)
    check("pitch + leans forward", p.head("head").y < -0.2)
    p = solve(yaw=90.0)
    nose = p.wrot("head") @ Vector((0, 0, 1))          # head local Z = front
    check("yaw + turns left (+X)", nose.x > 0.9, str(tuple(round(v, 2) for v in nose)))
    p = solve(roll=30.0)
    check("roll + leans left", p.head("head").x > 0.2)
    p = solve(pitch=-90.0, hip=(0, 0, 0.2))
    check("pitch -90 = on the back, head to the rear", p.head("head").y > 0.5 and (p.wrot("head") @ Vector((0, 0, 1))).z > 0.9)
    p = solve(pitch=90.0, spin=90.0, hip=(0, 0, 0.3))
    check("spin turns about the body axis", abs(p.head("head").y + 0.64) < 0.05)

    # spine / head
    p = solve(bend=40.0)
    check("bend + forward", p.head("head").y < -0.15)
    p = solve(twist=40.0)
    check("twist + turns chest left", p.head("upperarm_l").y > 0.05 and p.head("upperarm_r").y < -0.05)
    p = solve(side=30.0)
    check("side + leans left", p.head("head").x > 0.08)
    p = solve(turn=60.0)
    nose = p.wrot("head") @ Vector((0, 0, 1))
    check("turn + looks left", nose.x > 0.7)
    p = solve(nod=40.0)
    nose = p.wrot("head") @ Vector((0, 0, 1))
    check("nod + looks down", nose.z < -0.5)
    p = solve(tilt=30.0)
    check("tilt + ear to left shoulder", p.tail("head").x > 0.03)
    p = solve(pitch=40.0, twist=30.0, gaze=1.0)
    nose = p.wrot("head") @ Vector((0, 0, 1))
    check("gaze keeps the head level", nose.y < -0.98, str(tuple(round(v, 2) for v in nose)))

    # arms (FK)
    for side, s in (("L", 1.0), ("R", -1.0)):
        suf = "_l" if side == "L" else "_r"
        key = "arm" + side
        p = solve(**{key: ArmFK(fwd=0, out=0, elbow=0)})
        d = p.head("hand" + suf) - p.head("upperarm" + suf)
        check(f"{side} arm hangs down", d.normalized().z < -0.99)
        palm = p.wrot("hand" + suf) @ Vector((s, 0, 0))
        check(f"{side} palm faces the thigh", palm.x * s < -0.9, str(tuple(round(v, 2) for v in palm)))
        p = solve(**{key: ArmFK(fwd=90, out=0, elbow=0)})
        d = (p.head("hand" + suf) - p.head("upperarm" + suf)).normalized()
        check(f"{side} fwd=90 points ahead", d.y < -0.99)
        p = solve(**{key: ArmFK(fwd=0, out=90, elbow=0)})
        d = (p.head("hand" + suf) - p.head("upperarm" + suf)).normalized()
        check(f"{side} out=90 points sideways", d.x * s > 0.99)
        p = solve(**{key: ArmFK(fwd=0, out=0, elbow=90)})
        d = (p.head("hand" + suf) - p.head("lowerarm" + suf)).normalized()
        check(f"{side} elbow flexes forward", d.y < -0.99)
        thumb = p.wrot("hand" + suf) @ Vector((0, 0, 1))
        check(f"{side} thumb up when elbow is bent", thumb.z > 0.9)
        p = solve(**{key: ArmFK(fwd=0, out=0, elbow=90, twist=90)})
        d = (p.head("hand" + suf) - p.head("lowerarm" + suf)).normalized()
        check(f"{side} twist + brings forearm across", d.x * s < -0.99)
        p = solve(**{key: ArmFK(fwd=0, out=0, elbow=90, pron=90)})
        palm = p.wrot("hand" + suf) @ Vector((s, 0, 0))
        check(f"{side} pron + turns palm down", palm.z < -0.9, str(tuple(round(v, 2) for v in palm)))
        p0 = solve(**{key: ArmFK(fwd=0, out=0, elbow=0)})
        p = solve(**{key: ArmFK(fwd=0, out=0, elbow=0, flex=60)})
        move = p.tail("hand" + suf) - p0.tail("hand" + suf)
        palm = p0.wrot("hand" + suf) @ Vector((s, 0, 0))
        check(f"{side} wrist flex toward palm", move.normalized().dot(palm) > 0.7)
        p = solve(**{key: ArmFK(fwd=0, out=0, elbow=0, grip=1.0, thumb=1.0)})
        move = p.tail("fingers" + suf) - p0.tail("fingers" + suf)
        check(f"{side} grip curls toward palm", move.normalized().dot(palm) > 0.5)
        move = p.tail("thumb" + suf) - p0.tail("thumb" + suf)
        check(f"{side} thumb closes toward palm", move.normalized().dot(palm) > 0.5)
        # IK
        target = (0.25 * s, -0.35, 1.25)
        p = solve(**{key: ArmIK(pos=target)})
        check(f"{side} arm IK reaches", (p.head("hand" + suf) - Vector(target)).length < 1e-3)
        elbow = p.head("lowerarm" + suf)
        mid = (p.head("upperarm" + suf) + Vector(target)) * 0.5
        check(f"{side} elbow points down/out by default", (elbow - mid).z < 0 and (elbow - mid).x * s > 0)
        p = solve(**{key: ArmIK(pos=(0.2 * s, -0.33, 1.1), at="palm", palm=(0, 0, -1), fingers=(0, -1, 0))})
        palm = p.wrot("hand" + suf) @ Vector((s, 0, 0))
        grip = p.world("hand" + suf) @ rig.palm_point[side]
        check(f"{side} palm aim + palm point", palm.z < -0.99 and (grip - Vector((0.2 * s, -0.33, 1.1))).length < 1e-3,
              f"{palm.z:.2f} {(grip - Vector((0.2 * s, -0.33, 1.1))).length:.4f}")

        # legs
        key = "leg" + side
        p = solve(hip=(0, 0, 1.5), **{key: LegFK(fwd=90)})
        d = (p.head("calf" + suf) - p.head("thigh" + suf)).normalized()
        check(f"{side} hip fwd lifts the knee", d.y < -0.99)
        p = solve(hip=(0, 0, 1.5), **{key: LegFK(knee=90)})
        d = (p.head("foot" + suf) - p.head("calf" + suf)).normalized()
        check(f"{side} knee flexes back", d.y > 0.99)
        p = solve(hip=(0, 0, 1.5), **{key: LegFK(out=45)})
        d = (p.head("calf" + suf) - p.head("thigh" + suf)).normalized()
        check(f"{side} hip out", d.x * s > 0.69)
        p = solve(hip=(0, 0, 1.5), **{key: LegFK(twist=45)})
        toes = (p.tail("ball" + suf) - p.head("foot" + suf)).normalized()
        check(f"{side} hip twist + turns toes out", toes.x * s > 0.5)
        p = solve(hip=(0, 0, 1.5), **{key: LegFK(ankle=30)})
        check(f"{side} ankle + lifts toes", p.head("ball" + suf).z > sk.head["ball" + suf].z + 0.52 + 0.03)
        p = solve(hip=(0, 0, 0.80), **{key: Plant(0.2 * s, -0.1, roll=40.0)})
        check(f"{side} heel lift keeps the ball of the foot down",
              abs(p.head("ball" + suf).z - 0.025) < 1e-3 and p.head("foot" + suf).z > 0.15
              and abs(p.tail("ball" + suf).z - 0.025) < 2e-3)
        p = solve(hip=(0, 0, 0.80), **{key: Plant(0.2 * s, -0.1, roll=-25.0)})
        check(f"{side} toe lift raises the toes", p.tail("ball" + suf).z > 0.08)
        knee = p.head("calf" + suf)
        check(f"{side} knee points forward", knee.y < p.head("thigh" + suf).y - 0.1)
        p = solve(hip=(0, 0, 1.4), **{key: LegIK(pos=(0.1 * s, -0.3, 0.9), space="pelvis", ankle=0.0)})
        want = p.point("pelvis", (0.1 * s, -0.3, 0.9))
        check(f"{side} leg IK in pelvis space", (p.head("foot" + suf) - want).length < 1e-3)

    # ball hold: the socket lands where it was asked to
    spec = ArmIK(pos=(-0.05, -0.32, 1.30), space="chest", at="ball", fingers=(0.3, -0.9, 0.3), palm=(0.7, 0.2, -0.3),
                 hspace="chest")
    p = solve(armR=spec, bend=10.0)
    m = p.world("ball_hand_r")
    want = p.point("spine_03", (-0.05, -0.32, 1.30))
    axis = p.direction("spine_03", (0.3, -0.9, 0.3)).normalized()
    got_axis = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
    check("ball hold: centre", (m.translation - want).length < 2e-3, f"{(m.translation - want).length:.4f}")
    check("ball hold: axis", abs(got_axis.dot(axis)) > 0.999)
    palm_dir = (m.translation - p.world("hand_r") @ rig.palm_point["R"]).normalized()
    check("ball hold: palm side", palm_dir.dot(p.direction("spine_03", (0.7, 0.2, -0.3)).normalized()) > 0.5,
          f"{palm_dir.dot(p.direction('spine_03', (0.7, 0.2, -0.3)).normalized()):.2f}")

    # mirroring
    c = dict(DEFAULTS, clamp=0.0, yaw=20.0, twist=15.0, side=5.0, turn=20.0, hip=(0.05, -0.02, 0.9),
             armL=ArmFK(fwd=50, out=20, twist=30, elbow=70), armR=ArmIK(pos=(-0.2, -0.3, 1.2), space="chest"),
             legL=Plant(0.2, -0.2, yaw=10.0), legR=LegFK(fwd=40, knee=60, out=10))
    a, b = rig.solve(c), rig.solve(mirror_controls(c))
    err = 0.0
    for n in sk.names:
        if n in ("ball_hand_r", "ball_tuck_r", "towel"):  # equipment mounted on one side
            continue
        m = n[:-2] + ("_r" if n.endswith("_l") else "_l") if n[-2:] in ("_l", "_r") else n
        pa, pb = a.head(n), b.head(m)
        err = max(err, (Vector((-pa.x, pa.y, pa.z)) - pb).length)
    check("mirror", err < 1e-4, f"{err:.5f}")

    # hand2tuck slides the hand socket onto the tuck socket
    p = solve(hand2tuck=1.0, armR=ArmFK(fwd=20, elbow=80, twist=40))
    d = (p.head("ball_hand_r") - p.head("ball_tuck_r")).length
    check("hand2tuck", d < 1e-4, f"{d:.5f}")

    # our FK must agree with Blender's evaluation of the baked action
    poses = [rig.solve(dict(c, pitch=10.0 * i, bend=5.0 * i, hip=(0.1 * i, 0.0, 0.9 + 0.1 * i))) for i in range(3)]
    action = bake.make_action(armature, "A_SelfTest", poses)
    bake.assign(armature, action)
    err = 0.0
    for f, pose in enumerate(poses):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        for n in sk.names:
            got = armature.pose.bones[n].matrix
            want = pose.world(n)
            err = max(err, (got.translation - want.translation).length)
            err = max(err, got.to_quaternion().rotation_difference(want.to_quaternion()).angle * 0.2)
    check("FK agrees with Blender", err < 1e-4, f"{err:.6f}")
    bpy.data.actions.remove(action)

    print("SELFTEST", "FAILED: " + ", ".join(fails) if fails else "OK")
    return not fails
