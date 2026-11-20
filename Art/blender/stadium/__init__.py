"""Stadium and static-prop generators for 4th & Fury.

Entry point: Art/blender/build_stadium.py. Modules:

    meshkit   polygon-soup mesh builder (primitives, transforms, UVs, welding)
    ring      the rounded-rectangle plan every terrace and wall is swept around
    spec      every dimension of the stadium, in one place
    terrace   stepped tiers with aisles and vomitories, and the seat list they imply
    bowl      the stadium itself
    props     goalpost, ball, sideline props
    crowd     low-poly spectators and crowd.bin
    preview   stand-in materials, test textures, turf with markings, night lighting, cameras
    shots     the preview renders themselves (stadium, crowd, props) and the back-face audit
    checks    automated validation (camera-clear volume, turf rectangle, seats on steps, UV
              conventions, back faces a camera could see)
"""
