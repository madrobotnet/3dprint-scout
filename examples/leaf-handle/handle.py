"""Organic door handle: a leaf-shaped dome with a finger pocket and a round grip, as one SDF.

Phase 3/4 style generator (Python engine). Every dimension is a parameter; sources are
comments. Built with sdf.py so the pocket's vertical walls and the dome meet without the
needle triangles that height-field booleans produced (python.md).
"""
import math

import sdf

DEFAULTS = {
    "leaf_len": 60.0,     # mm, along X (example value)
    "leaf_w": 24.0,       # mm, widest point
    "dome_h": 6.0,        # mm above the 2 mm base plate
    "base_t": 2.0,        # mm, flat plate on the bed (prints without support)
    "pocket_w": 20.0,     # mm, finger pocket along X
    "pocket_d": 8.0,      # mm
    "grip_r": 3.0,        # mm, round grip radius (tolerances.md: feature >= 1.2 mm)
    "grip_len": 25.0,     # mm, how far the grip sticks out
    "blend_k": 2.5,       # mm, fillet-like blend between grip and dome (design.md: no sharp creases)
    "edge": 0.5,          # mm, mesh edge length (python.md: 0.5 for a 0.4 mm nozzle)
}


def build(params):
    p = {**DEFAULTS, **params}
    n = 48
    a, b = p["leaf_len"] / 2, p["leaf_w"] / 2
    leaf = [[a + a * math.cos(t), b * math.sin(t) * (1 + 0.3 * math.cos(t))]
            for t in [2 * math.pi * i / n for i in range(n)]]

    def top(x, y):
        return p["base_t"] + p["dome_h"] * max(0.0, 1 - ((x - a) / a) ** 2 - (y / b) ** 2)

    dome = sdf.height_field(leaf, top)
    pocket = sdf.box([p["pocket_w"], p["pocket_d"], 20]).translate([a - p["pocket_w"] / 2, -p["pocket_d"] / 2, p["base_t"] + 2])
    grip = sdf.capsule([5, 0, p["grip_r"]], [-p["grip_len"], 0, p["grip_r"]], p["grip_r"])
    body = sdf.smooth_union(dome - pocket, grip, p["blend_k"])
    part = sdf.to_manifold(body, p["edge"], floor=0.0)      # flat bed after the blend
    return {"handle": part}
