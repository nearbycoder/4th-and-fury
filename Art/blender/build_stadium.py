"""Stadium, static props, crowd figures, metadata and previews for 4th & Fury.

    blender -b --factory-startup -P Art/blender/build_stadium.py

Writes
    Art/export/stadium/SM_Stadium.fbx            the arena, one mesh, 14 material slots
    Art/export/stadium/SM_<Prop>.fbx             goalpost, ball, tee, pylon, bench, cooler, sticks, camera
    Art/export/stadium/SM_Crowd{A,B,C}.fbx       low-poly spectators with a `Col` mask
    Art/export/stadium/stadium_meta.json         lights, screens, tunnel, benches, bounds, triangle counts
    Art/export/stadium/crowd.bin                 one record per seat
    Art/previews/stadium/*.png, report.json      renders and the validation report

Options (after `--`)
    --no-previews          geometry, exports and checks only (about 20 s)
    --no-export            skip the FBX files (iterating on looks)
    --only a,b,...         render only these preview groups or shot names
                           (groups: stadium, crowd, props, audit)
    --quick                fewer samples
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from furylib import export, render as frender  # noqa: E402
from stadium import bowl, checks, crowd, preview, props, shots, spec as S  # noqa: E402
from stadium.meshkit import mesh_triangle_count  # noqa: E402

ART = os.path.dirname(HERE)
OUT = os.path.join(ART, "export", "stadium")
PREVIEW = os.path.join(ART, "previews", "stadium")
SCRATCH = os.path.join(ART, "_scratch", "stadium")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = dict(previews=True, export=True, only=None, quick=False)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-previews":
            opts["previews"] = False
        elif a == "--no-export":
            opts["export"] = False
        elif a == "--quick":
            opts["quick"] = True
        elif a == "--only":
            i += 1
            opts["only"] = set(argv[i].split(","))
        else:
            raise SystemExit(f"unknown option {a}")
        i += 1
    return opts


def export_object(obj, path):
    """FBX through the project's exporter, triangulated so the count is exact."""
    mod = obj.modifiers.new("Triangulate", "TRIANGULATE")
    mod.quad_method = "SHORTEST_DIAGONAL"
    mod.ngon_method = "BEAUTY"
    mod.min_vertices = 4
    if hasattr(mod, "keep_custom_normals"):
        mod.keep_custom_normals = True
    export.export_static_mesh(path, [obj])
    obj.modifiers.remove(mod)


def verify_fbx(path):
    """Read the file back and describe what an importer will see."""
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.fbx_import(filepath=path)
    except Exception:
        bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    info = dict(objects=len(new))
    for o in new:
        if o.type != "MESH":
            continue
        me = o.data
        pts = [o.matrix_world @ v.co for v in me.vertices]
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        info.update(
            name=o.name,
            tris=sum(p.loop_total - 2 for p in me.polygons),
            only_triangles=all(p.loop_total == 3 for p in me.polygons),
            slots=[m.name.split(".")[0] if m else None for m in me.materials],
            uv_layers=len(me.uv_layers),
            color_attributes=[a.name for a in me.color_attributes],
            bounds=[[round(v, 4) for v in lo], [round(v, 4) for v in hi]],
            origin=[round(v, 5) for v in o.matrix_world.translation],
        )
    for o in new:
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
    for m in list(bpy.data.materials):
        if m.users == 0 and "." in m.name:
            bpy.data.materials.remove(m)
    return info


def main():
    opts = parse_args()
    t0 = time.time()
    for d in (OUT, PREVIEW, SCRATCH):
        os.makedirs(d, exist_ok=True)
    scene = frender.reset_scene()
    report = {}

    # ---- build ----------------------------------------------------------------------------------
    mats = preview.plain_materials()          # exported as-is; preview shaders replace them later
    c_stadium, c_props, c_figs = shots.coll("Stadium"), shots.coll("Props"), shots.coll("CrowdFigs")

    st = bowl.Stadium().build()
    shots.set_tunnel_views(st.tunnel_meta)
    stadium = st.mb.to_object("SM_Stadium", slots=bowl.SLOTS, materials=mats, collection=c_stadium)
    used = [m.name for m in stadium.data.materials]
    if used != bowl.SLOTS:
        raise SystemExit(f"stadium slots differ from the brief: {used}")

    objects = {"SM_Stadium": stadium}
    slots = {"SM_Stadium": used}
    for name, fn in props.ALL.items():
        mb, sl = fn()
        objects[name] = mb.to_object(name, slots=sl, materials=mats, collection=c_props,
                                     sharp_angle=24.0 if name == "SM_Football" else 35.0)
        slots[name] = [m.name for m in objects[name].data.materials]
        if slots[name] != sl:
            raise SystemExit(f"{name}: slots {slots[name]} != {sl}")
    for name, fn in crowd.FIGURES.items():
        mb = fn()
        # Alpha is the cheer motion mask. Chair, shoes and seated hips stay planted.
        base = 0.52 if name == "SM_CrowdA" else 0.10
        for i, face in enumerate(mb.faces):
            colors = mb.col[i] or [(0, 0, 0, 0)] * len(face)
            mb.col[i] = [(*c[:3], min(1.0, max(0.0, (mb.co[v][2] - base) / 0.8)))
                         for c, v in zip(colors, face)]
        objects[name] = mb.to_object(name, slots=["Crowd"], materials=mats, collection=c_figs, sharp_angle=180.0)
        slots[name] = ["Crowd"]
    print("BUILD %.1fs" % (time.time() - t0))

    # ---- seats ----------------------------------------------------------------------------------
    seats = st.seats()
    bin_path = os.path.join(OUT, "crowd.bin")
    crowd.write_bin(bin_path, seats)
    seats_disk = crowd.read_bin(bin_path)

    # ---- checks ---------------------------------------------------------------------------------
    report["camera_clear_volume"] = checks.camera_clear(st.mb)
    report["turf_rectangle"] = checks.turf_clear(st.mb)
    report["seats"] = checks.seats_general(seats_disk)
    report["seats_on_steps"] = checks.seats_on_steps(stadium, seats_disk, used)
    report["uv"] = checks.uv_conventions(st.mb)
    eyes = {k: shots.STADIUM_VIEWS[k][0] for k in shots.AUDIT_VIEWS}
    eyes.update({k: v[0] for k, v in shots.AUDIT_EXTRA.items()})
    rng = np.random.default_rng(11)
    for i in range(70):                                  # anywhere a game camera might fly
        eyes["air_%02d" % i] = (float(rng.uniform(-62, 62)), float(rng.uniform(-31, 31)), float(rng.uniform(0.4, 34)))
    for i in range(0, len(seats_disk), max(1, len(seats_disk) // 40)):   # and from the stands
        x, y, z = (float(v) for v in seats_disk[i][:3])
        eyes["seat_%05d" % i] = (x, y, z + 1.6)
    vb = checks.visible_backfaces(stadium, used, eyes)
    report["visible_backfaces"] = dict(
        ok=all(v["area"] < 0.02 for v in vb.values()), eyes=len(vb),
        worst_area_m2=max(v["area"] for v in vb.values()),
        offenders={k: v for k, v in vb.items() if v["count"]})
    report["dropped_faces"] = {n: int(o.get("dropped_faces", 0)) for n, o in objects.items()}
    report["tris_by_slot"] = dict(sorted(st.mb.tri_count_by_material().items(), key=lambda kv: -kv[1]))
    tris = {n + ".fbx": mesh_triangle_count(o) for n, o in objects.items()}
    report["tris"] = tris
    ok = all(v.get("ok", True) for v in (report["camera_clear_volume"], report["turf_rectangle"],
                                          report["seats"], report["seats_on_steps"]))
    ok = ok and all(v["ok"] for v in report["uv"].values()) and report["visible_backfaces"]["ok"]
    report["all_checks_pass"] = bool(ok)

    # ---- export ---------------------------------------------------------------------------------
    if opts["export"]:
        fbx = {}
        for name, obj in objects.items():
            path = os.path.join(OUT, name + ".fbx")
            export_object(obj, path)
            fbx[name + ".fbx"] = verify_fbx(path)
        report["fbx_readback"] = fbx
        for name, info in fbx.items():
            if info.get("tris") != tris[name]:
                print("WARNING: triangle count differs on read-back:", name, info.get("tris"), tris[name])
        print("EXPORT done %.1fs" % (time.time() - t0))

    # ---- metadata -------------------------------------------------------------------------------
    lo, hi = st.mb.bounds()
    r = lambda v: [round(float(c), 4) + 0.0 for c in v]         # "+ 0.0" turns -0.0 into 0.0
    dressing = shots.suggested_dressing()
    meta = {
        "units": "metres, Blender coordinates (Z up). Unreal = (100*x, -100*y, 100*z) cm.",
        "lights": [dict(pos=r(l["pos"]), aim=r(l["aim"])) for l in st.lights],
        "screen": dict(center=r(st.screen["center"]), width=st.screen["width"], height=st.screen["height"],
                       normal=r(st.screen["normal"])),
        "small_screens": [dict(center=r(s["center"]), width=s["width"], height=s["height"], normal=r(s["normal"]))
                          for s in st.small_screens],
        "tunnel": dict(mouth=r(st.tunnel_meta["mouth"]), dir=r(st.tunnel_meta["dir"]),
                       clear_width=round(st.tunnel_meta["width"], 3),
                       portal=r(st.tunnel_meta["portal"]), portal_width=st.tunnel_meta["portal_width"],
                       portal_height=st.tunnel_meta["portal_height"]),
        "benches": {
            "home": dict(side="+Y", area_center=[0.0, 30.2, 0.0], area_size=[33.0, 3.0], yaw=0.0,
                         benches=[b for b in dressing["SM_Bench"] if b["pos"][1] > 0]),
            "away": dict(side="-Y", area_center=[0.0, -30.2, 0.0], area_size=[33.0, 3.0], yaw=round(math.pi, 6),
                         benches=[b for b in dressing["SM_Bench"] if b["pos"][1] < 0]),
            "note": "yaw is radians about +Z in Blender; SM_Bench's sitting side faces -Y at yaw 0.",
        },
        "bounds": dict(min=r(lo), max=r(hi), size=r(hi - lo)),
        "tris": tris,
        "slots": slots,
        "seats": dict(file="crowd.bin", count=int(len(seats_disk)),
                      record="float32 x, y, z, yaw, section (little-endian), after an int32 count",
                      section_a=report["seats"]["section_a"], section_b=report["seats"]["section_b"]),
        "ad_boards": dict(wall_boards=st.notes["ad_boards"], wall_board_length=round(st.notes["ad_board_len"], 4),
                          wall_band_z=[S.AD_Z0 - 0.02, S.AD_Z1 + 0.02],
                          note="U advances 1.0 per board, left to right seen from the field. The same slot "
                               "also covers the LED ribbons on the upper-deck fascias."),
        "field_wall": dict(half_x=S.WALL_HX, half_y=S.WALL_HY, corner_radius=S.WALL_R, height=S.WALL_H),
        "camera_clear_volume": dict(abs_x_below=S.CLEAR_X, y=[S.CLEAR_Y0, S.CLEAR_Y1], z_above=S.CLEAR_Z,
                                    highest_geometry_under_it=report["camera_clear_volume"]["highest_vertex_under_it"]),
        "suggested_props": dressing,
    }
    with open(os.path.join(OUT, "stadium_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    # a partial run (--no-export, --no-previews, --only) keeps what the last full run recorded
    report_path = os.path.join(PREVIEW, "report.json")
    if os.path.exists(report_path):
        try:
            with open(report_path) as f:
                previous = json.load(f)
            for key in ("fbx_readback", "backface_fraction_by_view", "preview_crowd_instances"):
                if key not in report and key in previous:
                    report[key] = previous[key]
        except (OSError, ValueError):
            pass
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print("REPORT", json.dumps({k: v for k, v in report.items() if k not in ("fbx_readback",)}, indent=1))
    print("CHECKS", "PASS" if ok else "FAIL")

    # ---- previews -------------------------------------------------------------------------------
    if opts["previews"]:
        preview.stadium_materials()            # upgrade the slot materials in place for rendering
        preview.prop_materials()
        render_previews(scene, st, objects, seats_disk, opts, report)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
    print("STADIUM_OK %.1fs" % (time.time() - t0))


# ================================================================================================
STADIUM_SHOTS = ["broadcast_center", "broadcast_left", "broadcast_right", "overview", "overview_back", "exterior",
                 "plan", "field_north",
                 "field_south", "endzone_west", "endzone_east", "corner_ne", "tunnel_out", "tunnel_mouth",
                 "upper_deck", "sideline_props", "goal_east"]
CROWD_SHOTS = ["broadcast_center", "broadcast_left", "broadcast_right", "broadcast_tight", "field_north",
               "overview", "crowd_closeup", "crowd_rows", "crowd_upper"]


def render_previews(scene, st, objects, seats, opts, report):
    only = opts["only"]
    samples = 40 if opts["quick"] else 110

    def want(group, name=None):
        return only is None or group in only or (name is not None and name in only)

    prop_objs = {n: o for n, o in objects.items() if n in props.ALL}
    shots.build_stage(scene, st.lights, prop_objs)

    names = [n for n in STADIUM_SHOTS if want("stadium", n)]
    if names:
        shots.render_stadium(scene, names, PREVIEW, samples=samples)

    def crowd_file(n):
        return n if n.startswith("crowd_") else n + "_crowd"

    names = [n for n in CROWD_SHOTS if want("crowd", crowd_file(n))]
    if names:
        cm = crowd.crowd_material()
        meshes = []
        for n in ("SM_CrowdA", "SM_CrowdB", "SM_CrowdC"):
            me = objects[n].data.copy()
            me.materials.clear()
            me.materials.append(cm)
            meshes.append(me)
        c, count = crowd.instance_crowd(seats, meshes, preview.TEAM_A, preview.TEAM_B, collection=shots.coll("PV_Crowd"))
        report["preview_crowd_instances"] = count
        for n in names:
            suffix = "" if n.startswith("crowd_") else "_crowd"
            shots.render_stadium(scene, [n], PREVIEW, suffix=suffix, samples=samples, with_crowd=True)

    if want("props"):
        render_prop_previews(scene, objects, samples)

    if want("audit"):
        audit = shots.backface_audit(scene, os.path.join(SCRATCH, "audit"))
        report["backface_fraction_by_view"] = audit
        print("AUDIT", json.dumps(audit, indent=1))


def render_prop_previews(scene, objects, samples):
    P = lambda n: os.path.join(PREVIEW, n + ".png")
    views = {
        "SM_Goalpost": dict(az=-38, el=8, fov=30, fill=1.15),
        "SM_KickTee": dict(az=30, el=28, fov=26),
        "SM_Pylon": dict(az=32, el=14, fov=26, fill=1.4),
        "SM_Bench": dict(az=28, el=16, fov=28, fill=1.05),
        "SM_Cooler": dict(az=24, el=20, fov=28, fill=1.2),
        "SM_ChainPole": dict(az=20, el=6, fov=26, fill=1.2),
        "SM_DownBox": dict(az=28, el=6, fov=26, fill=1.2),
        "SM_Camera": dict(az=40, el=12, fov=28, fill=1.25),
    }
    sheet = []
    for name, kw in views.items():
        sub = shots.subject([objects[name]])
        sheet.append(shots.render_prop(scene, sub, P("prop_" + name[3:].lower()), samples=samples, res=(912, 912), **kw))
    # the ball: hero, laces from above, and teed up
    sub = shots.subject([objects["SM_Football"]])
    shots.render_prop(scene, sub, P("prop_football"), az=28, el=22, fov=24, fill=1.15, res=(1400, 900), samples=samples * 2)
    sheet.insert(1, shots.render_prop(scene, sub, P("prop_football_sq"), az=28, el=22, fov=24, fill=1.25, res=(912, 912),
                                      samples=samples))
    shots.render_prop(scene, sub, P("prop_football_top"), az=8, el=68, fov=24, fill=1.2, res=(1000, 750), samples=samples)
    shots.render_prop(scene, sub, P("prop_football_end"), az=74, el=10, fov=24, fill=1.5, res=(1000, 750), samples=samples)
    sub = shots.subject([objects["SM_KickTee"], (objects["SM_Football"], (0.012, 0, 0.165), (0, math.radians(-80), 0))])
    shots.render_prop(scene, sub, P("prop_football_teed"), az=35, el=12, fov=26, fill=1.3, res=(1000, 750), samples=samples)
    # detail shots
    sub = shots.subject([objects["SM_DownBox"], (objects["SM_ChainPole"], (0.7, 0, 0))])
    shots.render_prop(scene, sub, P("prop_sticks_heads"), az=22, el=4, fov=14, fill=0.42, res=(1000, 750), samples=samples,
                      target_shift=(0, 0, 0.42))
    sub = shots.subject([objects["SM_Goalpost"]])
    shots.render_prop(scene, sub, P("prop_goalpost_base"), az=-35, el=10, fov=24, fill=0.36, res=(1000, 750), samples=samples,
                      target_shift=(0.02, 0, -0.36))
    # the three spectators, in shirt colours and as the raw mask
    cm = crowd.crowd_material()
    figs = []
    for i, n in enumerate(("SM_CrowdA", "SM_CrowdB", "SM_CrowdC")):
        o = objects[n]
        o.color = (*[preview.TEAM_A, preview.TEAM_B, (0.8, 0.62, 0.1)][i], 1.0)
        figs.append((o, ((i - 1) * 0.95, 0, 0.44 if i == 0 else 0.0)))
    sub = shots.subject(figs)
    step = bpy.data.meshes.new("PV_Step")
    step.from_pydata([(-1.6, -0.32, 0.44), (1.6, -0.32, 0.44), (1.6, 0.5, 0.44), (-1.6, 0.5, 0.44),
                      (-1.6, -0.32, 0.0), (1.6, -0.32, 0.0)], [], [(0, 1, 2, 3), (4, 5, 1, 0)])
    step.materials.append(preview.principled("PV_StepMat", (0.3, 0.3, 0.32), 0.8))
    so = bpy.data.objects.new("PV_Step", step)
    shots.coll("PV_Subject").objects.link(so)
    for o in sub:
        o.data = o.data.copy()
        o.data.materials.clear()
        o.data.materials.append(cm)
    shots.render_prop(scene, sub, P("crowd_figures"), az=24, el=10, fov=28, fill=1.1, res=(1200, 800), samples=samples)
    mask = preview.vertex_color_material("PV_Mask")
    for o in sub:
        o.data.materials.clear()
        o.data.materials.append(mask)
    shots.render_prop(scene, sub, P("crowd_figures_mask"), az=24, el=10, fov=28, fill=1.1, res=(1200, 800), samples=samples)
    shots.render_prop(scene, sub, P("crowd_figures_back"), az=156, el=10, fov=28, fill=1.1, res=(1200, 800), samples=samples)
    # contact sheet from half-size tiles (3 x 456 px + gutters = 1392 px)
    tiles = []
    for p in sheet:
        img = bpy.data.images.load(p, check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        half = px.reshape(h // 2, 2, w // 2, 2, 4).mean(axis=(1, 3))
        out = bpy.data.images.new("PV_Tile", w // 2, h // 2, alpha=True)
        out.pixels.foreach_set(half.astype(np.float32).ravel())
        tp = os.path.join(SCRATCH, "tile_" + os.path.basename(p))
        out.filepath_raw = tp
        out.file_format = "PNG"
        out.save()
        bpy.data.images.remove(out)
        tiles.append(tp)
    frender.contact_sheet(tiles, P("props_sheet"), columns=3)
    for p in sheet:
        if p.endswith("_sq.png"):
            os.remove(p)


main()
