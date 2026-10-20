# 3dprint-scout: engine=blender
"""Scalloped coaster: a wavy outline with a real fillet on its top edge, three ring grooves
cut with the Manifold boolean solver, and a raised medallion carrying embossed text as a
separate part (its own colour in the slicer). A decorative, freeform shape, so the skill
uses the Blender engine (references/engines/blender.md, blender_builder.py).

Phase 3/4 style generator: every dimension is a parameter with its source; the scene is
rebuilt from scratch on every run; derived sizes are checked with assertions.
"""
import math

import blender_builder as bb

PARAMETERS = {
    "r": 35.0,            # mm, mean radius of the outline (example value: a 70 mm coaster)
    "scallop": 0.06,      # the rim waves in and out by this fraction of r (example value)
    "lobes": 8,           # scallops around the rim (example value)
    "h": 4.0,             # mm, thickness (design.md: floors 3-4 layers at least; 4 mm is sturdy)
    "fillet": 1.2,        # mm, fillet on the top edge (Blender bevel; the bed edge gets a chamfer, P6)
    "bed_chamfer": 0.4,   # mm, elephant-foot chamfer (tolerances.md: 0.3-0.5)
    "groove_w": 1.0,      # mm, ring groove width, two line widths (design.md)
    "groove_d": 0.6,      # mm, groove depth (tolerances.md: engrave >= 0.6)
    "groove_r": [23.0, 26.0, 29.0],   # mm, ring radii (example values)
    "medallion_d": 40.0,  # mm, raised disc in the centre: its own part, so it can take another filament
    "medallion_h": 1.0,   # mm, how far the disc stands proud of the top face (five layers)
    "text": "SCOUT",      # embossed on the medallion (example value)
    "text_h": 7.0,        # mm, cap height: the built-in font's strokes reach 0.9 mm here (design.md: >= 0.8)
    "text_d": 0.8,        # mm, emboss height (tolerances.md: emboss >= 0.6)
    "text_margin": 1.5,   # mm, letters stay this far inside the disc (example value)
    "outline_n": 160,     # points on the outline: chords of about 1.2 mm (D1 holds to 0.1 mm)
}


def outline(p):
    """Scalloped outline: r (1 + scallop cos(lobes t)), lobes on the X and Y axes."""
    n = int(p["outline_n"])
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = p["r"] * (1 + p["scallop"] * math.cos(p["lobes"] * t))
        pts.append((rr * math.cos(t), rr * math.sin(t)))
    return pts


def build(p):
    r_min = p["r"] * (1 - p["scallop"])
    inner_edge = r_min - p["fillet"]                          # where the fillet starts, at the narrowest
    outer_groove = max(p["groove_r"]) + p["groove_w"] / 2
    if outer_groove >= inner_edge - 0.5:
        raise ValueError(f"the outer groove ({outer_groove} mm) runs into the fillet ({inner_edge:.1f} mm)")
    if p["medallion_d"] / 2 >= min(p["groove_r"]) - p["groove_w"] / 2:
        raise ValueError("the medallion overlaps the inner groove")

    coaster = bb.prism(outline(p), p["h"], "coaster")
    bb.bevel(coaster, p["fillet"])                            # top edge only; fillets before cuts
    for rr in p["groove_r"]:
        groove = bb.ring(rr - p["groove_w"] / 2, rr + p["groove_w"] / 2, p["groove_d"] + 0.1,
                         z0=p["h"] - p["groove_d"], name="groove")        # 0.1 mm overshoot above the face
        bb.boolean(coaster, groove, "difference")
    bb.bed_chamfer(coaster, p["bed_chamfer"])                 # last: the chamfer must not meet a fillet

    medallion = bb.cylinder(p["medallion_d"] / 2, p["medallion_h"], name="medallion")
    mark = bb.text(p["text"], height=p["text_h"], depth=p["text_d"] + 0.1)    # 0.1 mm into the disc
    lo, hi, _tris = bb.world_bbox(mark)
    half = max(hi[0] - lo[0], hi[1] - lo[1]) / 2
    if math.hypot(hi[0] - lo[0], hi[1] - lo[1]) / 2 > p["medallion_d"] / 2 - p["text_margin"]:
        raise ValueError(f"text {p['text']!r} is {hi[0] - lo[0]:.1f} x {hi[1] - lo[1]:.1f} mm, too wide for the disc")
    mark.location = (0.0, -(hi[1] - lo[1]) / 2, p["medallion_h"] - 0.1)  # centred, sunk 0.1 mm into the disc
    bb.boolean(medallion, mark, "union")                      # one body: disc plus letters
    medallion.location = (0.0, 0.0, p["h"])                   # sits on the top face
    assert half < p["medallion_d"] / 2

    bb.part(coaster, "coaster")
    bb.part(medallion, "medallion", object="coaster", role="fused")
    return {"coaster": coaster, "medallion": medallion}


if __name__ == "__main__":
    bb.main(build, PARAMETERS)
