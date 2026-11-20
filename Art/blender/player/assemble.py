"""Turn a list of meshkit Parts into the one skinned Blender mesh the engine imports."""
import math
import bpy
import numpy as np

from furylib import rig

SLOTS = ["Helmet", "HelmetStripe", "HelmetLogo", "Facemask", "Visor", "Strap", "Skin", "Eyes",
         "Jersey", "JerseyTrim", "Pants", "PantsStripe", "Belt", "Socks", "Shoes", "ShoeSole",
         "Gloves", "Bands"]

DEFORM_BONES = [row[0] for row in rig.bone_table() if row[5]]
MAX_INFLUENCES = 4
UV_PAD = 0.006            # metres between charts in the atlas


# ------------------------------------------------------------------------------- UV atlas
def pack_atlas(parts):
    """Lay every chart of every part out in one 0..1 square at one common scale.

    Returns (per-part list of per-face corner UV tuples, metres spanned by the 0..1 square).
    """
    charts = {}
    for pi, part in enumerate(parts):
        if part.uv_absolute:
            continue
        for fi, key in enumerate(part.fchart):
            charts.setdefault((pi, key), []).append(fi)
    info = []
    for (pi, key), faces in charts.items():
        part = parts[pi]
        pts = np.array([c for fi in faces for c in part.fuv[fi]], float)
        lo = pts.min(axis=0); hi = pts.max(axis=0)
        w, h = (hi - lo)
        rot = h > w
        if rot:
            w, h = h, w
        info.append(dict(pi=pi, key=key, faces=faces, lo=lo, hi=hi, w=float(w), h=float(h), rot=rot))
    info.sort(key=lambda c: (-c["h"], -c["w"]))

    def try_pack(L):
        x = y = UV_PAD
        row = 0.0
        for c in info:
            if c["w"] + 2 * UV_PAD > L:
                return False
            if x + c["w"] + UV_PAD > L:
                y += row + UV_PAD
                x = UV_PAD
                row = 0.0
            c["x"], c["y"] = x, y
            x += c["w"] + UV_PAD
            row = max(row, c["h"])
        return y + row + UV_PAD <= L

    area = sum((c["w"] + UV_PAD) * (c["h"] + UV_PAD) for c in info)
    L = max(math.sqrt(area), max(c["w"] for c in info) + 2 * UV_PAD)
    while not try_pack(L):
        L *= 1.02
    out = [list(part.fuv) for part in parts]
    for c in info:
        part = parts[c["pi"]]
        for fi in c["faces"]:
            corners = []
            for (u, v) in part.fuv[fi]:
                a, b = u - c["lo"][0], v - c["lo"][1]
                if c["rot"]:
                    a, b = b, (c["hi"][0] - c["lo"][0]) - a
                corners.append(((c["x"] + a) / L, (c["y"] + b) / L))
            out[c["pi"]][fi] = tuple(corners)
    return out, L


# ------------------------------------------------------------------------------- NumberUV
def number_uvs(parts, panels):
    """Second UV set. panels: name -> dict(origin, eu, ev, w, h). A face tagged "torso" is
    projected to "front" or "back" by which way it faces; a face tagged with a panel name uses
    that panel if it faces the reader; every other face gets (-1, -1) on all corners."""
    out = []
    for part in parts:
        normals = part.face_normals() if any(t is not None for t in part.ftag) else None
        uvs = []
        for fi, f in enumerate(part.faces):
            tag = part.ftag[fi]
            name = None
            if tag == "torso":
                name = "front" if normals[fi][1] < 0.0 else "back"
            elif tag is not None:
                name = tag
            panel = panels.get(name) if name else None
            if panel is not None and name not in ("front", "back"):
                facing = np.cross(panel["eu"], panel["ev"]) @ normals[fi]
                if facing <= 0.05:
                    panel = None
            if panel is None:
                uvs.append(tuple((-1.0, -1.0) for _ in f))
                continue
            q = part.v[list(f)] - panel["origin"]
            u = q @ panel["eu"] / panel["w"] + 0.5
            v = q @ panel["ev"] / panel["h"] + 0.5
            uvs.append(tuple((float(a), float(b)) for a, b in zip(u, v)))
        out.append(uvs)
    return out


# -------------------------------------------------------------------------------- weights
def gather_weights(parts):
    """(N, len(DEFORM_BONES)) weights: at most 4 per vertex, normalized."""
    total = sum(len(p.v) for p in parts)
    W = np.zeros((total, len(DEFORM_BONES)))
    col = {b: i for i, b in enumerate(DEFORM_BONES)}
    off = 0
    for part in parts:
        n = len(part.v)
        if not part.w:
            raise RuntimeError(f"part {part.name} has no skin weights")
        for bone, arr in part.w.items():
            if bone not in col:
                raise RuntimeError(f"part {part.name} is weighted to non-deforming bone {bone}")
            if len(arr) != n:
                raise RuntimeError(f"part {part.name}: weight array for {bone} has the wrong length")
            W[off:off + n, col[bone]] = np.maximum(arr, 0.0)
        off += n
    W[W < 1e-4] = 0.0
    # keep the 4 strongest
    order = np.argsort(-W, axis=1)
    drop = order[:, MAX_INFLUENCES:]
    rows = np.repeat(np.arange(total)[:, None], drop.shape[1], axis=1)
    W[rows, drop] = 0.0
    s = W.sum(axis=1)
    if (s <= 1e-9).any():
        bad = int(np.argmax(s <= 1e-9))
        raise RuntimeError(f"{int((s <= 1e-9).sum())} vertices have no weight (first: {bad})")
    return W / s[:, None]


# ---------------------------------------------------------------------------------- mesh
def sharp_edges(parts, offsets):
    """Hard edges as global vertex pairs: explicit ones plus per-part angle thresholds."""
    out = set()
    for part, off in zip(parts, offsets):
        for a, b in part.sharp:
            out.add((a + off, b + off) if a < b else (b + off, a + off))
        if part.smooth_angle is None:
            continue
        cos_limit = math.cos(math.radians(part.smooth_angle))
        normals = part.face_normals()
        edge_faces = {}
        for fi, f in enumerate(part.faces):
            n = len(f)
            for k in range(n):
                a, b = f[k], f[(k + 1) % n]
                edge_faces.setdefault((a, b) if a < b else (b, a), []).append(fi)
        for (a, b), fl in edge_faces.items():
            if len(fl) == 2 and normals[fl[0]] @ normals[fl[1]] < cos_limit:
                out.add((a + off, b + off))
    return out


def build_object(name, parts, armature, materials, panels, collection=None):
    """Create the skinned mesh object. Returns (object, stats dict)."""
    parts = [p for p in parts if len(p.faces)]
    offsets = np.cumsum([0] + [len(p.v) for p in parts])[:-1]
    verts = np.vstack([p.v for p in parts])
    faces = [tuple(i + off for i in f) for p, off in zip(parts, offsets) for f in p.faces]
    used = [s for s in SLOTS if any(s in p.fmat for p in parts)]
    unknown = {m for p in parts for m in p.fmat} - set(SLOTS)
    if unknown:
        raise RuntimeError(f"unknown material slots: {unknown}")
    slot_index = {s: i for i, s in enumerate(used)}

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts.tolist(), [], faces)
    mesh.update(calc_edges=True)
    for s in used:
        mesh.materials.append(materials[s])
    mat_idx = [slot_index[m] for p in parts for m in p.fmat]
    mesh.polygons.foreach_set("material_index", mat_idx)
    mesh.polygons.foreach_set("use_smooth", [True] * len(faces))

    atlas, atlas_metres = pack_atlas(parts)
    numbers = number_uvs(parts, panels)
    for layer_name, data in (("UVMap", atlas), ("NumberUV", numbers)):
        layer = mesh.uv_layers.new(name=layer_name)
        flat = np.array([c for part_uv in data for face in part_uv for c in face], dtype=np.float32).ravel()
        layer.data.foreach_set("uv", flat)
    mesh.uv_layers.active = mesh.uv_layers["UVMap"]
    mesh.uv_layers["UVMap"].active_render = True

    hard = sharp_edges(parts, offsets)
    if hard:
        ev = np.empty(len(mesh.edges) * 2, dtype=np.int32)
        mesh.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        lo = np.minimum(ev[:, 0], ev[:, 1]); hi = np.maximum(ev[:, 0], ev[:, 1])
        flags = np.fromiter(((int(a), int(b)) in hard for a, b in zip(lo, hi)), dtype=bool, count=len(ev))
        mesh.edges.foreach_set("use_edge_sharp", flags)
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)

    W = gather_weights(parts)
    groups = [obj.vertex_groups.new(name=b) for b in DEFORM_BONES]
    for bi, group in enumerate(groups):
        col = W[:, bi]
        nz = np.nonzero(col)[0]
        if not len(nz):
            continue
        full = nz[col[nz] > 0.99999]
        if len(full):
            group.add(full.tolist(), 1.0, "REPLACE")
        for vi in nz[col[nz] <= 0.99999]:
            group.add([int(vi)], float(col[vi]), "REPLACE")
    # drop groups for bones nothing is weighted to? keep them all: the engine wants every bone.
    rig.skin_to_armature(obj, armature)

    tri = sum(len(f) - 2 for f in faces)
    stats = dict(
        triangles=int(tri), vertices=int(len(verts)), faces=int(len(faces)),
        material_slots=list(used), uv_atlas_metres=float(atlas_metres),
        influences_max=int((W > 0).sum(axis=1).max()),
        triangles_by_slot={s: int(sum(len(f) - 2 for p in parts for f, m in zip(p.faces, p.fmat) if m == s)) for s in used},
    )
    return obj, stats
