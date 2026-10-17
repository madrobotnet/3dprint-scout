"""Box with a snap-fit lid and two heat-set insert bosses, built with parts.py.

Print orientation: the box stands on its floor; the lid prints plate-down with its plug and
two hooks pointing up. Assembled, the lid is flipped onto the box (fit.py: --b-rotate
180,0,0 --b-translate 0,<d>,<h + plate>). The hooks are built along Z in print, so their
strain is checked against HALF the PLA limit (design.md, snap fits; recorded in
_assumptions).
"""
import manifold3d as m3d
import parts

M = m3d.Manifold

DEFAULTS = {
    "w": 70.0,              # mm, outer width (demo value)
    "d": 45.0,              # mm, outer depth
    "h": 30.0,              # mm, box height
    "wall": 2.0,            # mm (tolerances.md: 1.6-2.0 structural; five 0.4 mm lines)
    "corner_r": 3.0,        # mm, vertical edge radius
    "bed_chamfer": 0.4,     # mm, elephant-foot chamfer (tolerances.md)
    "plate_t": 3.0,         # mm, lid plate
    "plug_h": 5.0,          # mm, lid plug reaching into the box
    "clearance": 0.2,       # mm per side, sliding/removable fit (tolerances.md)
    "hook_len": 16.0,       # mm, cantilever length
    "hook_t": 1.6,          # mm, cantilever thickness (>= 1.2, tolerances.md)
    "hook_w": 6.0,          # mm, cantilever width
    "undercut": 0.5,        # mm; strain 1.5*t*y/L^2 = 0.47 % < half of PLA 1 % (Z-built hook)
    "boss_h": 12.0,         # mm, insert bosses on the floor
}


def hook_and_window(p, side: str):
    """Hook on the lid in print orientation and the matching window cutter, same frame.

    Native hook: beam +X from the root, bump +Y, width along Z. Mirrored in Y so the bump
    points outward, tipped up with a -90 deg turn about Y (beam -> +Z, width -> -X), then
    placed with its outer face flush with the plug's outer face."""
    args = dict(length=p["hook_len"], thickness=p["hook_t"], width=p["hook_w"], undercut=p["undercut"])
    hook = parts.snap_hook(material="PLA", **args)
    window = parts.snap_window(wall=p["wall"], clearance=p["clearance"], **args)
    x0 = p["w"] / 2 + p["hook_w"] / 2
    y_face = p["wall"] + p["clearance"] + p["hook_t"]          # inner face of the beam
    out = []
    for body in (hook, window):
        body = body.mirror([0, 1, 0]).rotate([0, -90, 0]).translate([x0, y_face, p["plate_t"]])
        if side == "far":
            body = body.mirror([0, 1, 0]).translate([0, p["d"], 0])
        out.append(body)
    return out


def build(params):
    p = {**DEFAULTS, **params}
    w, d, h, t, c = p["w"], p["d"], p["h"], p["wall"], p["clearance"]
    check = parts.snap_fit_check(p["hook_len"], p["hook_t"], p["undercut"], "PLA")
    if check["strain"] > check["limit"] / 2:
        raise ValueError(f"hook built along Z: strain {check['strain']:.3%} must stay under half the limit")

    # Box: rounded outer, open top, elephant-foot chamfer, two insert bosses on the floor.
    inner = M.extrude(parts.rounded_rect(w - 2 * t, d - 2 * t, max(p["corner_r"] - t, 0.5)), h).translate([t, t, t])
    box = parts.rounded_box([w, d, h], p["corner_r"]) - inner
    box = parts.bottom_chamfer(box, p["bed_chamfer"])
    for x, y in ((9.0, 9.0), (w - 9.0, d - 9.0)):
        box += parts.standoff(p["boss_h"], "M3", "insert", foot=1.0).translate([x, y, t - 0.1])

    # Lid: plate + plug (inset by wall + clearance) + two hooks.
    lid = M.extrude(parts.rounded_rect(w, d, p["corner_r"]), p["plate_t"])
    plug_r = max(p["corner_r"] - t - c, 0.5)
    plug = M.extrude(parts.rounded_rect(w - 2 * (t + c), d - 2 * (t + c), plug_r), p["plug_h"] + 0.1) \
        .translate([t + c, t + c, p["plate_t"] - 0.1])
    plug -= M.extrude(parts.rounded_rect(w - 2 * (t + c) - 2 * t, d - 2 * (t + c) - 2 * t, 0.5), p["plug_h"] + 1) \
        .translate([2 * t + c, 2 * t + c, p["plate_t"]])   # hollow plug: a 2 mm lip, less material
    lid += plug
    for side in ("near", "far"):
        hook, window = hook_and_window(p, side)
        lid += hook
        # The window sits where the hook lands once the lid is flipped onto the box.
        box -= window.rotate([180, 0, 0]).translate([0, d, h + p["plate_t"]])
    # The hooks' outer faces are flush with the plug: the union leaves slivers, clean() welds them.
    return {"box": parts.clean(box), "lid": parts.clean(lid)}
