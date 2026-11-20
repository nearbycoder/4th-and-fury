#!/usr/bin/env python3
"""crowd.bin (Blender seats) -> web/public/assets/stadium/crowd_instances.bin (spectators exactly as the game seats them).

Also copies the original seat file unchanged to web/public/assets/stadium/crowd.bin (web/src/game/stadium.ts
reads that one and runs the seating itself).

    python3 web/tools/convert_crowd.py

Input  Art/export/stadium/crowd.bin: int32 count, then count x float32 (x, y, z, yaw, section), Blender metres,
       Z up, one record per seat (yaw about +Z; a figure at yaw 0 faces -Y).

AFuryStadium::BuildCrowd walks the seats with FRandomStream(20261117): 6% stay empty, the rest get a figure
(58% SM_CrowdA seated, 27% SM_CrowdB standing, 15% SM_CrowdC arms up), a yaw jitter of +-9 degrees and a
size of 0.92..1.08. That stream is reproduced bit for bit here, so the web crowd is the game's crowd.

Output crowd_instances.bin (little-endian):
    header  16 bytes: char[4] "FCRD", uint32 version (1), uint32 count, uint32 record_size (20)
    record  20 bytes, one per spectator, already in glTF / three.js space (metres, +Y up):
        0  float32 x
        4  float32 y            the tread the figure stands / sits on
        8  float32 z
       12  float32 yaw          radians about +Y; at 0 the figure faces +Z (toward the TV-camera side)
       16  uint8   kind         0 = crowdA (seated), 1 = crowdB (standing), 2 = crowdC (arms up)
       17  uint8   flags        bit 0: section (0 = SeatA block, 1 = SeatB block)
                                bit 1: camera-flash spot (the game's SeatSample(): flashes spawn 1.1 m above)
       18  uint8   scale        uniform scale = 0.92 + 0.16 * scale / 255
       19  uint8   rand         per-instance random 0..255 (stands in for Unreal's PerInstanceRandom)
"""
import json
import math
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(REPO, "Art", "export", "stadium", "crowd.bin")
DST = os.path.join(REPO, "web", "public", "assets", "stadium", "crowd_instances.bin")
RAW = os.path.join(REPO, "web", "public", "assets", "stadium", "crowd.bin")
GAME_COPY = os.path.join(REPO, "FourthAndFury", "Content", "Data", "crowd.bin")


class FRandomStream:
    """Unreal's FRandomStream (Engine/Source/Runtime/Core/Public/Math/RandomStream.h)."""

    def __init__(self, seed):
        self.seed = seed & 0xFFFFFFFF

    def frand(self):
        self.seed = (self.seed * 196314165 + 907633515) & 0xFFFFFFFF
        bits = 0x3F800000 | (self.seed >> 9)
        return struct.unpack("<f", struct.pack("<I", bits))[0] - 1.0

    def frand_range(self, lo, hi):
        return lo + (hi - lo) * self.frand()


def f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def main():
    data = open(SRC, "rb").read()
    if os.path.exists(GAME_COPY) and open(GAME_COPY, "rb").read() != data:
        print("WARNING: Art/export/stadium/crowd.bin differs from FourthAndFury/Content/Data/crowd.bin")
    (count,) = struct.unpack_from("<i", data, 0)
    count = min(count, (len(data) - 4) // 20)
    rng = FRandomStream(20261117)
    extra = FRandomStream(1117)            # only for the per-instance random byte
    out = []
    kinds = [0, 0, 0]
    sections = [0, 0]
    flashes = 0
    for i in range(count):
        x, y, z, yaw, section = struct.unpack_from("<5f", data, 4 + 20 * i)
        if rng.frand() < 0.06:
            continue
        roll = rng.frand()
        kind = 0 if roll < 0.58 else 1 if roll < 0.85 else 2
        ue_yaw = f32(-math.degrees(yaw) + rng.frand_range(-9.0, 9.0))
        size = rng.frand_range(0.92, 1.08)
        # Unreal yaw is clockwise seen from above once Y is mirrored; back to a +Y-up right-handed angle.
        gl_yaw = -math.radians(ue_yaw)
        flash = (i & 7) == 0
        flags = (1 if section > 0.5 else 0) | (2 if flash else 0)
        scale_b = max(0, min(255, int(round((size - 0.92) / 0.16 * 255))))
        rand_b = int(extra.frand() * 256) & 255
        out.append(struct.pack("<4f4B", x, z, -y, gl_yaw, kind, flags, scale_b, rand_b))
        kinds[kind] += 1
        sections[flags & 1] += 1
        flashes += flash
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(RAW, "wb") as handle:
        handle.write(data)
    with open(DST, "wb") as handle:
        handle.write(b"FCRD" + struct.pack("<3I", 1, len(out), 20))
        handle.write(b"".join(out))
    summary = dict(seats=count, spectators=len(out), by_kind=dict(crowdA=kinds[0], crowdB=kinds[1], crowdC=kinds[2]),
                   by_section=dict(SeatA=sections[0], SeatB=sections[1]), flash_spots=flashes,
                   bytes=os.path.getsize(DST))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
