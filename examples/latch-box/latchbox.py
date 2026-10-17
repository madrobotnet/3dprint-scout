"""Box with a drop-in lid, a separate label plate (colour part) and a captive slider latch
printed in place, built with parts.py.

Three bodies form the "lid" object and are modelled in one frame (the lid plate's corner
at the origin, Z = 0 on the bed): the lid plate with its two rails, the label plate that
sits on the lid (role fused: shared face, no union, so the slicer shows it as its own part
and it can take another filament), and the latch bar that lies between the rails under
their lips (role free: 0.3 mm to the rails, 0.4 mm = two layers above the plate, bridged).
Pushed outwards, the bar enters a window in the keeper lug on the box wall.
"""
import manifold3d as m3d
import parts

M = m3d.Manifold
CS = m3d.CrossSection

DEFAULTS = {
    "w": 60.0,              # mm, box outer width (demo value)
    "d": 40.0,              # mm, box outer depth
    "h": 25.0,              # mm, box height
    "wall": 2.8,            # mm, seven 0.4 mm lines: rim plus ledge (tolerances.md)
    "floor": 2.0,           # mm
    "corner_r": 3.0,        # mm, vertical edge radius
    "bed_chamfer": 0.4,     # mm, elephant-foot chamfer (tolerances.md)
    "rim": 1.6,             # mm, rim left standing around the lid (four lines); the ledge is wall - rim
    "lid_t": 3.0,           # mm, lid plate; also the recess depth so the lid sits flush
    "clearance": 0.2,       # mm per side, lid in its recess (sliding fit, tolerances.md)
    "pip": 0.3,             # mm per side, print-in-place gap (tolerances.md)
    "z_gap": 0.4,           # mm, latch above the lid: two 0.2 mm layers, bridged
    "bar_w": 6.0,           # mm, latch bar width
    "bar_h": 2.5,           # mm, latch bar height to its flat top
    "bar_len": 24.0,        # mm
    "bar_chamfer": 1.2,     # mm, 45-degree chamfer on the bar's top edges (under the lips)
    "rail_w": 3.0,          # mm, rail width
    "rail_h": 4.0,          # mm, rail height above the lid
    "rail_len": 32.0,       # mm
    "lip": 1.2,             # mm, how far the lip reaches over the bar
    "lip_t": 0.8,           # mm, lip thickness at its tip
    "travel": 6.0,          # mm, how far the bar is pushed to lock (into the lug window)
    "label_w": 30.0,        # mm, label plate (colour part)
    "label_d": 8.0,         # mm
    "label_t": 1.6,         # mm, four 0.4 mm lines (tolerances.md)
    "lug_w": 14.0,          # mm, keeper lug on the box wall, along Y
    "lug_out": 6.0,         # mm, how far it stands out from the wall
}


def rail(p, y_inner: float, sign: float, x0: float) -> M:
    """One rail with its lip, profile in (y, z) extruded along X. y_inner is the face
    towards the bar; sign +1 for the rail on +Y, -1 for the one on -Y."""
    z0, z1 = p["lid_t"], p["lid_t"] + p["rail_h"]
    tip_y = y_inner - sign * p["lip"]
    tip_z = z1 - p["lip_t"]
    root_z = tip_z - p["lip"] * 1.1               # 47 degrees: steeper than the 45 limit (P2)
    outer = y_inner + sign * p["rail_w"]
    pts = [(y_inner, z0), (outer, z0), (outer, z1), (tip_y, z1), (tip_y, tip_z), (y_inner, root_z)]
    if sign < 0:
        pts = pts[::-1]
    return M.extrude(CS([pts]), p["rail_len"]).rotate([90, 0, 0]).rotate([0, 0, 90]).translate([x0, 0, 0])


def bar(p, cy: float, x0: float) -> M:
    """Latch bar, profile in (y, z), lying between the rails under the lips."""
    half, c = p["bar_w"] / 2, p["bar_chamfer"]
    z0 = p["lid_t"] + p["z_gap"]
    z1 = z0 + p["bar_h"]
    pts = [(cy - half, z0), (cy + half, z0), (cy + half, z1 - c), (cy + half - c, z1),
           (cy - half + c, z1), (cy - half, z1 - c)]
    return M.extrude(CS([pts]), p["bar_len"]).rotate([90, 0, 0]).rotate([0, 0, 90]).translate([x0, 0, 0])


def build(params):
    p = {**DEFAULTS, **params}
    w, d, h, t, r = p["w"], p["d"], p["h"], p["wall"], p["corner_r"]
    if p["z_gap"] + p["bar_h"] + p["pip"] + p["lip_t"] > p["rail_h"] + 1e-9:
        raise ValueError("the bar does not fit under the lips with its clearance: raise rail_h or lower bar_h")
    if p["bar_w"] - 2 * p["bar_chamfer"] >= p["bar_w"] + 2 * p["pip"] - 2 * p["lip"]:
        raise ValueError("the lips do not hold the bar: widen lip or the bar's chamfer")
    if p["rim"] < 1.2 - 1e-9 or t - p["rim"] < 0.8:
        raise ValueError("rim must be at least 1.2 mm and leave a ledge of 0.8 mm: wall - rim")

    # Box: rounded, chamfered bed edge, a recess inside the rim for the lid to drop into.
    inner = M.extrude(parts.rounded_rect(w - 2 * t, d - 2 * t, max(r - t, 0.5)), h).translate([t, t, p["floor"]])
    box = parts.rounded_box([w, d, h], r) - inner
    rc = p["rim"]
    recess = M.extrude(parts.rounded_rect(w - 2 * rc, d - 2 * rc, max(r - rc, 0.5)), p["lid_t"] + 0.1) \
        .translate([rc, rc, h - p["lid_t"]])
    box -= recess
    box = parts.bottom_chamfer(box, p["bed_chamfer"])
    # Keeper lug on the +X wall: a 47-degree underside so it prints without support, and a
    # window the latch bar slides into (0.3 mm clearance all round, 0.1 mm above the rim).
    lo, lw = p["lug_out"], p["lug_w"]
    cy = d / 2
    z_top = h + p["z_gap"] + p["bar_h"] + p["pip"] + 1.5
    lug_pts = [(w - 0.01, h - lo * 1.1 - 6.0), (w + lo, h - 6.0), (w + lo, z_top), (w - 0.01, z_top)]
    lug = M.extrude(CS([lug_pts]), lw).rotate([90, 0, 0]).translate([0, cy + lw / 2, 0])
    box += lug
    win = M.cube([lo + 0.2, p["bar_w"] + 2 * p["pip"], p["bar_h"] + p["z_gap"] + 2 * p["pip"]]) \
        .translate([w - 0.1, cy - p["bar_w"] / 2 - p["pip"], h + 0.1])
    box -= win
    box = parts.clean(box)

    # Lid object, all in the lid's frame: plate corner at the origin.
    lw_, ld = w - 2 * rc - 2 * p["clearance"], d - 2 * rc - 2 * p["clearance"]
    lid = M.extrude(parts.rounded_rect(lw_, ld, max(r - rc - p["clearance"], 0.5)), p["lid_t"])
    cyl = ld / 2                                              # channel centre line
    y_in = p["bar_w"] / 2 + p["pip"]                          # rail inner face from the centre line
    x_rail = lw_ - 10.0 - p["rail_len"]                      # rails end 10 mm before the lid's +X edge
    lid += rail(p, cyl + y_in, +1, x_rail) + rail(p, cyl - y_in, -1, x_rail)
    lid = parts.clean(lid)
    latch = bar(p, cyl, lw_ - p["bar_len"])                  # at rest: flush with the lid's +X edge
    label = parts.chamfered_box([p["label_w"], p["label_d"], p["label_t"]], 0.4, "top") \
        .translate([(lw_ - p["label_w"]) / 2, cyl + y_in + p["rail_w"] + 2.0, p["lid_t"]])
    return {"box": box, "lid": lid, "label": label, "latch": latch}
