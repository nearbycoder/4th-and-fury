"""Every dimension of the stadium (Blender metres, Z up). One source of truth for the mesh,
the seat list, the metadata and the validation checks.

Offsets `*_D` are measured outward from the field-side face of the padded wall (the ring's
reference curve); heights `*_Z` are world Z.
"""
from .terrace import row_heights

# ---- given by the brief ----------------------------------------------------------------------
FIELD_HX = 54.86            # end lines
GOAL_X = 45.72              # goal lines
FIELD_HY = 24.38            # sidelines
TURF_HX, TURF_HY = 64.0, 32.0          # engine ground plane: nothing of ours above z=0 inside
CAMERA = (0.0, -52.0, 26.0)
CLEAR_X, CLEAR_Y0, CLEAR_Y1, CLEAR_Z = 75.0, -62.0, -30.0, 17.0   # keep-out volume for the camera

# ---- plan ------------------------------------------------------------------------------------
# The wall hugs the engine's turf rectangle as closely as a rounded corner allows: the corner arc
# has to pass outside the rectangle's sharp corner at (64, 32), which caps the radius.
WALL_HX = 64.5              # wall face behind the end zones (9.6 m beyond the end lines)
WALL_HY = 33.8              # wall face along the sidelines (9.4 m beyond the sidelines)
WALL_R = 3.4                # corner radius of the wall face
ARC_STEP_DEG = 6.0

AISLE_W = 1.2
SIDE_PITCH = 2 * (WALL_HX - WALL_R) / 12     # aisle spacing along the N/S sides (12 blocks, 10.18 m)
END_PITCH = 2 * (WALL_HY - WALL_R) / 6       # aisle spacing along the E/W ends (6 blocks, 10.13 m)

# ---- field wall ------------------------------------------------------------------------------
WALL_H = 1.30
WALL_T = 0.30
AD_Z0, AD_Z1 = 0.20, 1.10   # ad-board band on the wall face
AD_PROUD = 0.03
AD_LEN = 6.0                # one board

# ---- lower bowl ------------------------------------------------------------------------------
LB_D0 = 0.50                                   # front edge of row 0 (a 0.2 m ledge behind the wall = legroom)
LB_TREAD = 0.80
LB_ROWS = 26
LB_ZS = row_heights(0.80, LB_ROWS, 0.37, 0.006)
LB_D1 = LB_D0 + LB_ROWS * LB_TREAD            # 21.3
LB_HOLE_ROWS = (11, 16)                        # rows cut by the lower-bowl vomitories
WALK_Z = LB_ZS[-1]                             # top cross-walkway (about 12.5)
WALK_D1 = 24.0                                 # back of the walkway = mouth of the concourse
REC_D1 = 28.4                                  # back wall of the open concourse recess
REC_H = 3.0
DECK_Z = WALK_Z + REC_H                        # suite floor slab / -Y deck level (about 15.5)
CEIL_Z = DECK_Z - 0.30                         # concourse ceiling (the slab above it is 0.3 thick)
BAND_D = 23.6                                  # face of the band above the concourse mouth

# ---- suite strip and upper deck (the horseshoe: +Y side, both ends, most of each corner) ----
SUITE_SILL = 0.40
SUITE_GLASS = 2.60
SUITE_HEAD = 0.40
SOFFIT_Z = DECK_Z + SUITE_SILL + SUITE_GLASS + SUITE_HEAD
FASCIA_D = 21.5
FASCIA_H = 1.70
PARAPET_Z = SOFFIT_Z + FASCIA_H
PARAPET_T = 0.18
UD_D0 = FASCIA_D + 0.45                        # parapet, then a legroom ledge, then row 0
UD_TREAD = 0.80
UD_ROWS = 24
UD_ZS = row_heights(SOFFIT_Z + 0.70, UD_ROWS, 0.56, 0.005)
UD_D1 = UD_D0 + UD_ROWS * UD_TREAD            # 41.0
TOPWALK_D1 = 42.2
SHELL_D = 43.0                                 # outer face of the building
RIM_Z = UD_ZS[-1] + 4.2                        # top of the rear wall
HS_END_DEG = 46.0                              # how far the horseshoe runs into the two -Y corners

# ---- roof ------------------------------------------------------------------------------------
ROOF_D0 = 21.5              # leading edge
ROOF_D1 = 44.6              # back edge
ROOF_Z1 = RIM_Z + 1.7       # top surface at the back edge
ROOF_RISE = 3.0             # the leading edge is this much higher
ROOF_T0, ROOF_T1 = 0.28, 0.55
MAST_H = 12.0               # masts rise this far above the rim

# ---- -Y side: open deck above the concourse, then a set-back tier behind the camera gap ------
ST_FASCIA_D = 28.5
ST_D0 = ST_FASCIA_D + 0.45
ST_ROWS = 16
ST_TREAD = 0.80
ST_ZS = row_heights(DECK_Z + 1.40, ST_ROWS, 0.56, 0.005)
ST_D1 = ST_D0 + ST_ROWS * ST_TREAD            # 41.7
ST_RIM_Z = ST_ZS[-1] + 3.6
ST_ROOF_D0 = 28.9
ST_ROOF_Z1 = ST_RIM_Z + 1.7
ST_ROOF_RISE = 2.2
ST_MAST_H = 9.0

# ---- video board (centre of the +Y stand) ------------------------------------------------------
SCREEN_W = 33.0
SCREEN_H = SCREEN_W * 9.0 / 16.0               # 18.5625
SCREEN_Z0 = SOFFIT_Z + 0.75
SCREEN_D = 22.0                                # screen plane
BOARD_HX = 17.4                                # half width of the board housing
PIER_X0, PIER_X1 = 17.4, 2 * SIDE_PITCH        # the two piers flanking it (out to an aisle line)
PIER_D0 = 21.3
PIER_TOP = RIM_Z + 7.5

# ---- end-zone scoreboards ----------------------------------------------------------------------
SMALL_W, SMALL_H = 24.0, 6.0
SMALL_Z0 = PARAPET_Z - SMALL_H
SMALL_D = 21.3

# ---- players' tunnel (west end of the +Y stand) ------------------------------------------------
TUN_SIDE = "N"              # the straight it cuts through: N (+Y), S (-Y), E (+X) or W (-X)
TUN_POS = -5 * SIDE_PITCH   # where along that side (x for N/S, y for E/W); must be an aisle line
TUN_HW = 3.5                # half width of the cut through the lower rows
TUN_ROWS = 10               # rows removed in front of the portal
TUN_WALL_T = 0.30
TUN_PORTAL_W = 5.6
TUN_PORTAL_H = 3.8

# ---- floodlights -------------------------------------------------------------------------------
BANK_COLS, BANK_ROWS = 11, 4
LAMP_PITCH = 1.25
LAMP_R = 0.47

PLAZA_W = 26.0              # paved ground outside the building
