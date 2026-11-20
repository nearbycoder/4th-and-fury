"""The shared skeleton as plain maths: rest frames, forward kinematics and a Pose container.

Everything here works in armature space, which equals world space because the armature object
sits at the origin (metres, Z up, the character faces -Y, its left is +X).

A Pose stores exactly what Blender stores per pose bone -- a local quaternion and a local
location offset -- and evaluates world matrices the way Blender does:

    world(bone) = world(parent) @ (rest(parent)^-1 @ rest(bone)) @ Translation(loc) @ Rotation(q)

so a Pose can be written straight into an action and will play back identically.
"""
import math

from mathutils import Matrix, Quaternion, Vector

X_AXIS = Vector((1.0, 0.0, 0.0))
Y_AXIS = Vector((0.0, 1.0, 0.0))
Z_AXIS = Vector((0.0, 0.0, 1.0))

# Rest-pose ("character") directions.
LEFT = Vector((1.0, 0.0, 0.0))
FRONT = Vector((0.0, -1.0, 0.0))
BACK = Vector((0.0, 1.0, 0.0))
UP = Vector((0.0, 0.0, 1.0))
DOWN = Vector((0.0, 0.0, -1.0))


def rot3(axis, degrees):
    """3x3 rotation of `degrees` about `axis`."""
    return Matrix.Rotation(math.radians(degrees), 3, axis)


def frame_yz(y, z_hint):
    """3x3 frame whose Y is `y` and whose Z is as close to `z_hint` as possible (X = Y x Z)."""
    y = Vector(y).normalized()
    z = Vector(z_hint) - y * Vector(z_hint).dot(y)
    if z.length < 1e-6:
        z = y.orthogonal()
    z.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z))
    m.transpose()
    return m


def frame_yx(y, x_hint):
    """3x3 frame whose Y is `y` and whose X is as close to `x_hint` as possible (Z = X x Y)."""
    y = Vector(y).normalized()
    x = Vector(x_hint) - y * Vector(x_hint).dot(y)
    if x.length < 1e-6:
        x = y.orthogonal()
    x.normalize()
    z = x.cross(y)
    m = Matrix((x, y, z))
    m.transpose()
    return m


class Skel:
    """Rest data of the rig, read once from the Blender armature built by furylib.rig."""

    def __init__(self, armature_obj):
        bones = armature_obj.data.bones
        self.names = []

        def walk(bone):
            self.names.append(bone.name)
            for child in bone.children:
                walk(child)

        for bone in bones:
            if bone.parent is None:
                walk(bone)
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.rest_inv = {n: m.inverted() for n, m in self.rest.items()}
        self.rest_rot = {n: m.to_3x3() for n, m in self.rest.items()}
        self.head = {b.name: b.head_local.copy() for b in bones}
        self.tail = {b.name: b.tail_local.copy() for b in bones}
        self.length = {b.name: b.length for b in bones}
        self.offset = {}
        for n in self.names:
            p = self.parent[n]
            self.offset[n] = self.rest[n].copy() if p is None else self.rest_inv[p] @ self.rest[n]
        self.subtree = {n: [] for n in self.names}
        for n in self.names:
            p = n
            while p is not None:
                self.subtree[p].append(n)
                p = self.parent[p]

    def dist(self, a, b):
        """Rest distance between the heads of two bones."""
        return (self.head[a] - self.head[b]).length


class Pose:
    def __init__(self, skel):
        self.skel = skel
        self.q = {n: Quaternion() for n in skel.names}
        self.loc = {n: Vector((0.0, 0.0, 0.0)) for n in skel.names}
        self._w = {}
        self.warn = []          # solver notes (unreachable IK targets, ...)

    def copy(self):
        other = Pose(self.skel)
        other.q = {n: q.copy() for n, q in self.q.items()}
        other.loc = {n: v.copy() for n, v in self.loc.items()}
        other.warn = list(self.warn)
        return other

    # ---- setting -------------------------------------------------------------------------
    def _dirty(self, n):
        for d in self.skel.subtree[n]:
            self._w.pop(d, None)

    def set_q(self, n, q):
        self.q[n] = Quaternion(q)
        self._dirty(n)

    def set_loc(self, n, v):
        self.loc[n] = Vector(v)
        self._dirty(n)

    # ---- forward kinematics ---------------------------------------------------------------
    def base(self, n):
        """The frame the bone's own location/rotation is applied in (parent pose @ rest offset)."""
        p = self.skel.parent[n]
        if p is None:
            return self.skel.offset[n]
        return self.world(p) @ self.skel.offset[n]

    def world(self, n):
        m = self._w.get(n)
        if m is None:
            m = self.base(n) @ Matrix.Translation(self.loc[n]) @ self.q[n].to_matrix().to_4x4()
            self._w[n] = m
        return m

    def wrot(self, n):
        return self.world(n).to_3x3()

    def head(self, n):
        return self.world(n).translation.copy()

    def tail(self, n):
        return self.world(n) @ Vector((0.0, self.skel.length[n], 0.0))

    def delta(self, n):
        """Maps a rest-pose world point to where the posed bone `n` carries it.

        "torso" is a virtual space: it travels with the chest (spine_03) and turns with the
        chest's heading, but stays upright -- "in front of the chest, level with the ground".
        """
        if n == "torso":
            chest = self.world("spine_03") @ self.skel.rest_inv["spine_03"]
            front = chest.to_3x3() @ FRONT
            heading = math.atan2(front.x, -front.y) if abs(front.x) + abs(front.y) > 1e-6 else 0.0
            m = Matrix.Rotation(heading, 4, "Z")
            rest_head = self.skel.head["spine_03"]
            m.translation = self.head("spine_03") - m.to_3x3() @ rest_head
            return m
        return self.world(n) @ self.skel.rest_inv[n]

    def point(self, space, p):
        """A point given in rest-pose world coordinates, carried rigidly by bone `space`."""
        if space in (None, "world", "root"):
            return Vector(p)
        return self.delta(space) @ Vector(p)

    def direction(self, space, d):
        if space in (None, "world", "root"):
            return Vector(d)
        return self.delta(space).to_3x3() @ Vector(d)

    # ---- inverse helpers ------------------------------------------------------------------
    def set_world_rot(self, n, rot3x3):
        """Give the bone this world orientation (its position follows from its parents)."""
        base = self.base(n).to_3x3()
        self.set_q(n, (base.inverted() @ rot3x3).to_quaternion())

    def set_world(self, n, matrix4):
        """Give the bone this world position and orientation (uses the bone's location)."""
        basis = self.base(n).inverted() @ matrix4
        self.loc[n] = basis.translation.copy()
        self.q[n] = basis.to_quaternion()
        self._dirty(n)

    def aim(self, n, y, z_hint):
        self.set_world_rot(n, frame_yz(y, z_hint))

    def aim_x(self, n, y, x_hint):
        self.set_world_rot(n, frame_yx(y, x_hint))

    def rotate_local(self, n, axis, degrees):
        """Post-multiply a rotation about one of the bone's own axes."""
        self.set_q(n, self.q[n] @ Quaternion(axis, math.radians(degrees)))


def blend_poses(a, b, t, bones):
    """Slerp the listed bones of pose `a` toward pose `b` (in place on a copy of a's data)."""
    for n in bones:
        a.q[n] = a.q[n].slerp(b.q[n], t)
        a.loc[n] = a.loc[n].lerp(b.loc[n], t)
        a._dirty(n)
    return a
