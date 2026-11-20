#!/usr/bin/env python3
"""Dependency-free GLB summary used to verify the exported assets.

    python3 web/tools/inspect_glb.py web/public/assets/characters/mid.glb [--anims] [--joints name,name]

Prints nodes, meshes (primitive attributes, material, vertex count), skins, materials and animations
(name, duration, channel count, which channels move the root bone).
"""
import json
import math
import struct
import sys

COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load(path):
    data = open(path, "rb").read()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a GLB"
    off, doc, binchunk = 12, None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
        elif ctype == 0x004E4942:
            binchunk = chunk
        off += 8 + clen
    return doc, binchunk


def read_accessor(doc, binchunk, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    fmt, size = COMP[acc["componentType"]]
    n = NCOMP[acc["type"]]
    stride = view.get("byteStride", size * n)
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    out = []
    for i in range(acc["count"]):
        vals = struct.unpack_from("<" + fmt * n, binchunk, base + i * stride)
        out.append(vals if n > 1 else vals[0])
    return out


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def quat_rot(q, v):
    x, y, z, w = q
    vq = (v[0], v[1], v[2], 0.0)
    r = quat_mul(quat_mul(q, vq), (-x, -y, -z, w))
    return r[:3]


def world_rest(doc):
    """World (translation, rotation) of every node in its rest TRS (scale ignored: all 1)."""
    parent = {}
    for i, node in enumerate(doc["nodes"]):
        for c in node.get("children", []):
            parent[c] = i
    cache = {}

    def get(i):
        if i in cache:
            return cache[i]
        node = doc["nodes"][i]
        t = node.get("translation", [0, 0, 0])
        r = node.get("rotation", [0, 0, 0, 1])
        if i in parent:
            pt, pr = get(parent[i])
            wt = tuple(a + b for a, b in zip(pt, quat_rot(pr, t)))
            wr = quat_mul(pr, r)
        else:
            wt, wr = tuple(t), tuple(r)
        cache[i] = (wt, wr)
        return cache[i]

    return {doc["nodes"][i].get("name", str(i)): get(i) for i in range(len(doc["nodes"]))}


def main():
    path = sys.argv[1]
    show_anims = "--anims" in sys.argv
    joints = []
    if "--joints" in sys.argv:
        joints = sys.argv[sys.argv.index("--joints") + 1].split(",")
    doc, binchunk = load(path)
    print("file", path)
    print("extensionsUsed", doc.get("extensionsUsed", []))
    print("nodes", len(doc.get("nodes", [])), "| scenes root:", [doc["nodes"][n].get("name") for n in doc["scenes"][0]["nodes"]])
    for m in doc.get("meshes", []):
        for p in m["primitives"]:
            mat = doc["materials"][p["material"]]["name"] if "material" in p else None
            cnt = doc["accessors"][p["attributes"]["POSITION"]]["count"]
            attrs = {k: (doc["accessors"][v]["type"], doc["accessors"][v]["componentType"]) for k, v in p["attributes"].items()}
            print("  mesh %-12s prim mat=%-14s verts=%6d attrs=%s" % (m.get("name"), mat, cnt, attrs))
    for s in doc.get("skins", []):
        names = [doc["nodes"][j]["name"] for j in s["joints"]]
        print("  skin joints=%d first=%s" % (len(names), names[:6]))
        print("  joint names:", ",".join(names))
    for mat in doc.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        print("  material %-14s base=%s rough=%s metal=%s emissive=%s ext=%s tex=%s double=%s" % (
            mat["name"], [round(c, 3) for c in pbr.get("baseColorFactor", [1, 1, 1, 1])], pbr.get("roughnessFactor", 1),
            pbr.get("metallicFactor", 1), mat.get("emissiveFactor"), list(mat.get("extensions", {}).keys()),
            "baseColorTexture" in pbr, mat.get("doubleSided", False)))
    for img in doc.get("images", []):
        print("  image", img.get("name"), img.get("mimeType"))
    anims = doc.get("animations", [])
    print("animations", len(anims))
    if show_anims:
        node_names = [n.get("name") for n in doc["nodes"]]
        for a in anims:
            tmax = 0.0
            paths = {}
            root_moves = False
            for ch in a["channels"]:
                s = a["samplers"][ch["sampler"]]
                times = read_accessor(doc, binchunk, s["input"])
                tmax = max(tmax, max(times))
                key = ch["target"]["path"]
                paths[key] = paths.get(key, 0) + 1
                if node_names[ch["target"]["node"]] == "root" and key == "translation":
                    vals = read_accessor(doc, binchunk, s["output"])
                    root_moves = max(math.dist(v, vals[0]) for v in vals) > 1e-4
            interp = sorted({s.get("interpolation", "LINEAR") for s in a["samplers"]})
            print("  anim %-14s %.4f s  frames=%5.1f  channels=%s interp=%s root_translation_moves=%s" % (
                a["name"], tmax, tmax * 30, paths, interp, root_moves))
    if joints:
        rest = world_rest(doc)
        for j in joints:
            t, r = rest[j]
            axes = {ax: tuple(round(c, 3) for c in quat_rot(r, v)) for ax, v in (("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1)))}
            print("  joint %-12s world_pos=%s local axes in world: %s" % (j, tuple(round(c, 4) for c in t), axes))


if __name__ == "__main__":
    main()
