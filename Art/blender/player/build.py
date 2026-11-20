"""Put one athlete together: every part, the number panels and the facts for the meta file."""
import numpy as np

from . import body, extras, feet, hands, head, helmet, sdf
from .params import Build, PANEL_FRONT, PANEL_BACK, HEAD_SCALE, HEAD_PIVOT

X = np.array([1.0, 0.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])
MIRROR = np.array([-1.0, 1.0, 1.0])


def build_parts(build_name):
    """Returns (parts, panels, info)."""
    b = Build(build_name)
    parts = []

    trunk, trunk_info = body.build_trunk(b, under=head.head_field(b))
    parts.append(trunk)
    sleeve, cap_panel = body.build_sleeve(b)
    parts += [sleeve, sleeve.mirrored()]
    arm = body.build_arm(b)
    parts += [arm, arm.mirrored()]
    parts.append(body.build_pants(b))
    sock = body.build_sock(b)
    parts += [sock, sock.mirrored()]

    # helmet and head are modelled life-size, then enlarged together about the base of the skull
    pivot = np.array(HEAD_PIVOT)
    helmet_parts, logo_info = helmet.build_helmet(b.name)
    skin_part, eyes_part = head.build_head(b)
    for part in helmet_parts + [eyes_part]:
        part.v = pivot + (part.v - pivot) * HEAD_SCALE
    k = 1.0 + (HEAD_SCALE - 1.0) * sdf.smoothstep(1.555, 1.625, skin_part.v[:, 2])
    skin_part.v = pivot + (skin_part.v - pivot) * k[:, None]
    logo_info["centre_left"] = [round(float(x), 4) for x in pivot + (np.array(logo_info["centre_left"]) - pivot) * HEAD_SCALE]
    logo_info["size"] = round(logo_info["size"] * HEAD_SCALE, 4)
    parts += helmet_parts + [skin_part, eyes_part]

    glove = hands.build_hand(b)
    parts += [glove, glove.mirrored()]
    for piece in feet.build_shoe(b):
        parts += [piece, piece.mirrored()]

    parts += extras.build_extras(b)

    panels = {
        "front": dict(origin=np.array([0.0, 0.0, PANEL_FRONT["z"]]), eu=X.copy(), ev=Z.copy(),
                      w=PANEL_FRONT["w"], h=PANEL_FRONT["h"]),
        "back": dict(origin=np.array([0.0, 0.0, PANEL_BACK["z"]]), eu=-X, ev=Z.copy(),
                     w=PANEL_BACK["w"], h=PANEL_BACK["h"]),
        "cap_l": cap_panel,
        # mirrored geometry, but U is flipped back so the digits are never mirrored
        "cap_r": dict(origin=cap_panel["origin"] * MIRROR, eu=-(cap_panel["eu"] * MIRROR),
                      ev=cap_panel["ev"] * MIRROR, w=cap_panel["w"], h=cap_panel["h"]),
    }
    info = dict(
        build=build_name,
        number_panels={
            name: dict(center=[round(float(v), 4) + 0.0 for v in p["origin"]],
                       u_axis=[round(float(v), 4) + 0.0 for v in p["eu"]],
                       v_axis=[round(float(v), 4) + 0.0 for v in p["ev"]],
                       width_m=p["w"], height_m=p["h"])
            for name, p in panels.items()
        },
        helmet_logo=logo_info,
        collar_z_front=round(trunk_info["collar_z_front"], 4),
    )
    return parts, panels, info
