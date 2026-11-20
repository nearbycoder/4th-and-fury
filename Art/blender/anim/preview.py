"""Contact sheets: every clip from a three-quarter view and a side view, plus one overview sheet.

Rendered with the Workbench engine (flat colours, outlines, shadows): fast and easy to read at
thumbnail size. Cameras are orthographic and fixed for a whole clip, fitted to everything the
clip does, so height and travel can be compared from tile to tile.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

from furylib import render
from furylib import rig as furyrig

from . import bake, dummy

MAX_SHEET = 1400
PAD = 6
VIEW_34 = (38.0, 12.0)        # azimuth (0 = from the front, + = toward the character's left), elevation
VIEW_SIDE = (-90.0, 3.0)      # from the character's right: it faces right in the picture
EXTRA_POINTS = ("head", "fingers_l", "fingers_r", "ball_l", "ball_r")


def socket_matrix(pose, which):
    """World matrix of the football when it rides in a socket ("hand" or "tuck")."""
    return pose.world("ball_hand_r" if which == "hand" else "ball_tuck_r").copy()


def ball_matrix(center, axis=(0.0, -1.0, 0.0), up=(0.0, 0.0, 1.0)):
    """World matrix of a free football: centre, long axis and the side its laces face."""
    y = Vector(axis).normalized()
    z = Vector(up) - y * Vector(up).dot(y)
    if z.length < 1e-6:
        z = y.orthogonal()
    z.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(center)
    return m


class Stage:
    def __init__(self, scene, armature, mesh="auto", player_blend=None, scratch=None):
        self.scene = scene
        self.arm = armature
        self.scratch = scratch
        self.body = None
        self.mesh_name = "dummy"
        if mesh in ("auto", "player") and player_blend and os.path.exists(player_blend):
            try:
                self.body = _load_player(scene, armature, player_blend)
                self.mesh_name = "player_mid" if self.body else "dummy"
            except Exception as exc:                      # the art is still in flux; never block on it
                print(f"[preview] could not use {player_blend}: {exc}")
                self.body = None
        if self.body is None and mesh == "blockout":
            from furylib import blockout
            self.body = blockout.build_blockout(armature)
            self.mesh_name = "blockout"
        if self.body is None:
            self.body = dummy.build_dummy(armature)
        self.ball = dummy.build_ball()
        self.ground = dummy.build_ground()
        self.cam = render.camera(scene)
        self.cam.data.type = "ORTHO"
        self.cam.data.clip_start = 0.1
        self.cam.data.clip_end = 100.0
        self._engine()

    def _engine(self):
        sc = self.scene
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "MATERIAL"
        sh.show_shadows = True
        sh.shadow_intensity = 0.4
        sh.show_cavity = True
        sh.show_object_outline = True
        sh.object_outline_color = (0.0, 0.0, 0.0)
        sh.show_specular_highlight = False
        sh.background_type = "VIEWPORT"
        sh.background_color = (0.07, 0.08, 0.10)
        sh.use_world_space_lighting = False         # light every view the same way
        sc.display.render_aa = "8"
        sc.display.light_direction = (0.35, 0.45, 0.82)
        sc.view_settings.view_transform = "Standard"
        sc.render.film_transparent = False
        sc.render.image_settings.file_format = "PNG"
        sc.render.resolution_percentage = 100
        r = sc.render
        r.use_stamp = True
        for attr in dir(r):
            if attr.startswith("use_stamp_"):
                setattr(r, attr, False)
        r.use_stamp_note = True
        r.stamp_background = (0.0, 0.0, 0.0, 0.55)
        r.stamp_foreground = (1.0, 1.0, 1.0, 1.0)

    # ---- camera --------------------------------------------------------------------------
    @staticmethod
    def _basis(view):
        az, el = math.radians(view[0]), math.radians(view[1])
        eye = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        right = Vector((0.0, 0.0, 1.0)).cross(eye).normalized()
        up = eye.cross(right).normalized()
        return eye, right, up

    def _extent(self, points, view):
        eye, right, up = self._basis(view)
        xs = [p.dot(right) for p in points]
        ys = [p.dot(up) for p in points]
        ds = [p.dot(eye) for p in points]
        return (min(xs), max(xs), min(ys), max(ys), (min(ds) + max(ds)) * 0.5)

    def _aim(self, view, extent, width, height, margin):
        eye, right, up = self._basis(view)
        x0, x1, y0, y1, depth = extent
        target = right * ((x0 + x1) * 0.5) + up * ((y0 + y1) * 0.5) + eye * depth
        render.aim(self.cam, target + eye * 20.0, target)
        need_w = max((x1 - x0) + 2 * margin, ((y1 - y0) + 2 * margin) * width / height)
        return need_w if width >= height else need_w * height / width

    def _points(self, clip, poses, frames=None):
        pts = [Vector((0.0, 0.0, 0.0))]
        for f, pose in enumerate(poses):
            if frames is not None and f not in frames:
                continue
            for n in pose.skel.names:
                pts.append(pose.head(n))
            for n in EXTRA_POINTS:
                pts.append(pose.tail(n))
            m = self._ball_at(clip, poses, f)
            if m is not None:
                # a free-flying preview ball must not blow up the framing
                near = min((m.translation - pose.head(n)).length for n in ("hand_r", "hand_l", "foot_r", "pelvis"))
                if clip.prop is None or near < 0.6:
                    pts.append(m.translation.copy())
        return pts

    # ---- ball ----------------------------------------------------------------------------
    def _ball_at(self, clip, poses, f):
        if clip.prop is not None:
            return clip.prop(f, poses[f])
        if clip.ball == "none":
            return None
        if clip.ball_frames is not None and not clip.ball_frames[0] <= f <= clip.ball_frames[1]:
            return None
        return socket_matrix(poses[f], clip.ball)

    def _set_frame(self, clip, poses, f):
        self.scene.frame_set(f)
        m = self._ball_at(clip, poses, f)
        self.ball.hide_render = m is None
        if m is not None:
            self.ball.matrix_world = m

    def _tile(self, path, width, height, note):
        r = self.scene.render
        r.resolution_x, r.resolution_y = width, height
        r.stamp_note_text = note
        r.stamp_font_size = max(9, int(width / 19))
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        return path

    # ---- sheets --------------------------------------------------------------------------
    @staticmethod
    def pick_frames(clip):
        n = clip.frames
        if clip.loop:
            k = min(n, 10)
            return sorted({int(round(i * n / k)) % n for i in range(k)})
        k = min(n + 1, 12 if (n + 1 <= 12 or n >= 40) else 10)
        frames = [int(round(i * n / (k - 1))) for i in range(k)]
        # nudge the nearest sample onto each event frame so the key moments are on the sheet
        for ev in sorted(clip.events.values()):
            if ev in frames or not 0 < ev < n:
                continue
            i = min(range(1, len(frames) - 1), key=lambda j: abs(frames[j] - ev))
            if frames[i] not in clip.events.values():
                frames[i] = ev
        return sorted(set(frames))

    def clip_sheet(self, clip, poses, action, out_path):
        bake.assign(self.arm, action)
        frames = self.pick_frames(clip)
        views = clip.views or (VIEW_34, VIEW_SIDE)
        pts = self._points(clip, poses)
        margin = 0.14
        extents = [self._extent(pts, v) for v in views]
        aspect = max(((e[1] - e[0]) + 2 * margin) / ((e[3] - e[2]) + 2 * margin) for e in extents)
        aspect = max(0.60, min(1.50, aspect))
        cols = 4 if len(frames) <= 8 else 5 if len(frames) <= 10 else 6
        rows = 2 * math.ceil(len(frames) / cols)
        width = (MAX_SHEET - PAD * (cols + 1)) // cols
        height = int(round(width / aspect))
        limit = (MAX_SHEET - PAD * (rows + 1)) // rows
        if height > limit:
            width = int(width * limit / height)
            height = limit
        scale = max(self._aim(v, e, width, height, margin) for v, e in zip(views, extents))
        tiles = []
        events = {v: k for k, v in clip.events.items()}
        tile_dir = os.path.join(self.scratch, "tiles", clip.name)
        os.makedirs(tile_dir, exist_ok=True)
        for vi, (view, extent) in enumerate(zip(views, extents)):
            self._aim(view, extent, width, height, margin)
            self.cam.data.ortho_scale = scale
            for f in frames:
                self._set_frame(clip, poses, f)
                note = f"{clip.name} {f}" + (f" {events[f]}" if f in events else "")
                tiles.append(self._tile(os.path.join(tile_dir, f"v{vi}_{f:03d}.png"), width, height, note))
            while len(tiles) % cols:
                tiles.append(_blank(os.path.join(tile_dir, f"blank_{width}x{height}.png"), width, height))
        render.contact_sheet(tiles, out_path, columns=cols, pad=PAD)
        _compress(out_path)
        return out_path

    def big(self, clip, poses, action, frames, out_dir, size=620):
        """Debug: a few frames, large, both views side by side."""
        bake.assign(self.arm, action)
        views = clip.views or (VIEW_34, VIEW_SIDE)
        margin = 0.12
        os.makedirs(out_dir, exist_ok=True)
        out = []
        for f in frames:
            pts = self._points(clip, poses, {f})
            tiles = []
            extents = [self._extent(pts, v) for v in views]
            scale = max(self._aim(v, e, size, size, margin) for v, e in zip(views, extents))
            for vi, (view, extent) in enumerate(zip(views, extents)):
                self._aim(view, extent, size, size, margin)
                self.cam.data.ortho_scale = scale
                self._set_frame(clip, poses, f)
                tiles.append(self._tile(os.path.join(out_dir, f"_{clip.name}_{f}_{vi}.png"), size, size, f"{clip.name} {f}"))
            path = os.path.join(out_dir, f"{clip.name}_{f:03d}.png")
            render.contact_sheet(tiles, path, columns=2, pad=PAD)
            for t in tiles:
                os.remove(t)
            out.append(path)
        return out

    def pose_sheet(self, name, pose, ball, path, size=440, zoom=None):
        """One static pose from four sides (front, three-quarter, right side, top).
        zoom = (bone, metres) frames just the surroundings of that bone."""
        from .clip import Clip
        clip = Clip(name, 0)
        clip.prop = (lambda f, p: ball) if ball is not None else None
        action = bake.make_action(self.arm, "A_pose_" + name, [pose])
        bake.assign(self.arm, action)
        views = ((0.0, 4.0), VIEW_34, VIEW_SIDE, (0.0, 89.0))
        pts = self._points(clip, [pose])
        if zoom is not None:
            c, r = pose.head(zoom[0]), zoom[1] * 0.5
            pts = [c + Vector((sx * r, sy * r, sz * r)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        extents = [self._extent(pts, v) for v in views]
        scale = max(self._aim(v, e, size, size, 0.1) for v, e in zip(views, extents))
        tiles = []
        for vi, (view, extent) in enumerate(zip(views, extents)):
            self._aim(view, extent, size, size, 0.1)
            self.cam.data.ortho_scale = scale
            self._set_frame(clip, [pose], 0)
            tiles.append(self._tile(path + f".{vi}.png", size, size, f"{name} {('front', '3/4', 'side', 'top')[vi]}"))
        render.contact_sheet(tiles, path, columns=2, pad=PAD)
        for t in tiles:
            os.remove(t)
        bpy.data.actions.remove(action)
        return path

    def overview_tile(self, clip, poses, action, path, size=192):
        bake.assign(self.arm, action)
        f = clip.key_frame
        if f is None:
            f = min(clip.events.values()) if clip.events else clip.frames // 2
        pts = self._points(clip, poses, {f})
        pelvis = poses[f].head("pelvis")
        pts.append(Vector((pelvis.x, pelvis.y, 0.0)))
        view = clip.views[0] if clip.views else VIEW_34
        extent = self._extent(pts, view)
        self.cam.data.ortho_scale = max(self._aim(view, extent, size, size, 0.12), 1.5)
        self._set_frame(clip, poses, f)
        return self._tile(path, size, size, clip.name)


def overview_sheet(tile_dir, order, out_path, columns=7):
    paths = [os.path.join(tile_dir, name + ".png") for name in order]
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return None
    render.contact_sheet(paths, out_path, columns=columns, pad=PAD)
    return _compress(out_path)


def _compress(path):
    """Re-save a sheet as an opaque, fully compressed PNG (about a third of the size)."""
    scene = bpy.context.scene
    settings = scene.render.image_settings
    old = (settings.file_format, settings.color_mode, settings.compression)
    img = bpy.data.images.load(path, check_existing=False)
    try:
        settings.file_format, settings.color_mode, settings.compression = "PNG", "RGB", 100
        img.save_render(path, scene=scene)
    finally:
        settings.file_format, settings.color_mode, settings.compression = old
        bpy.data.images.remove(img)
    return path


def _blank(path, width, height):
    if not os.path.exists(path):
        img = bpy.data.images.new("Blank", width, height, alpha=True)
        px = np.zeros((height, width, 4), dtype=np.float32)
        px[..., :3] = 0.05
        px[..., 3] = 1.0
        img.pixels.foreach_set(px.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        bpy.data.images.remove(img)
    return path


def _load_player(scene, armature, blend_path, object_name="SK_Player_Mid"):
    """Append the real athlete mesh and bind it to our armature (same bone names)."""
    with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
        if object_name not in src.objects:
            return None
        dst.objects = [object_name]
    obj = dst.objects[0]
    if obj is None:
        return None
    scene.collection.objects.link(obj)
    old_parent = obj.parent
    furyrig.skin_to_armature(obj, armature)
    obj.matrix_parent_inverse = Matrix.Identity(4)
    if old_parent is not None and old_parent is not armature:
        bpy.data.objects.remove(old_parent, do_unlink=True)
    return obj
