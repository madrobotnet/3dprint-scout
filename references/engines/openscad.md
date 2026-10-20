# OpenSCAD engine

Read this right before Phase 3 when Phase 0 picked OpenSCAD.

## Script shape

```openscad
// PARAMETERS (mm) ---------------------------------------------------------
cell_d    = 14.5;   // AA cell diameter, IEC 60086 LR6 max (source: ...)
clearance = 0.3;    // radial, per side (tolerances.md: sliding fit)
wall      = 2.0;
part      = "body"; // build.py sets this per part: -D part="lid"

$fa = 1; $fs = 0.4; // fine tessellation so D1 holds on curved parts

// MODEL --------------------------------------------------------------------
if (part == "body") body();
if (part == "lid")  lid();
```

- Every number used in geometry comes from the PARAMETERS block (R1). `build.py` overrides any of them
  with `-D name=value` from `params.json`, so names must match exactly. A cutter's overshoot past a
  face (0.01–0.1 mm) is construction, not a dimension: a literal passes R1, a named `eps` is clearer.
- One `.scad` file builds every part; `part` selects which. Each part is exported in its **print
  orientation**: Z = 0 is the bed, the face that sits on the bed is at Z = 0.
- `include <file.scad>` and `use <file.scad>` are fine: `build.py` collects them with `-d` and hashes
  them into the manifest, so editing a library makes old STLs stale (R3). Your own files, yes;
  someone else's geometry library only with a permissive licence, its attribution kept, and a
  note to the user; otherwise not. Numbers read from a spec, a drawing or published constants
  are sourced dimensions in your own code (R2), not a library.

## Run

```bash
python3 "$SKILL_DIR/scripts/build.py" run model.scad --params .3dprint/params.json --out out \
  --printer .3dprint/printers.json
```

`build.py` probes `--backend=manifold` itself. On CGAL-only builds (stable 2021.01) heavy booleans
are slow; `--timeout` defaults to 900 s. Never pass `--enable=manifold`.

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `WARNING: Object may not be a valid 2-manifold` | A cut body ends exactly on a face (coincident faces) | Make every cutting body overshoot by 0.01–0.1 mm on each open side |
| M5 FAIL: more bodies than expected | Parts that should touch are separated by a hairline, or a `union()` of shapes that only share an edge | Overlap joined shapes by ≥ 0.01 mm; never rely on edge contact |
| D1 FAIL by 0.1–0.3 mm on round parts | Default `$fa = 12, $fs = 2` gives 30 segments on large circles | Keep `$fa = 1; $fs = 0.4;` at the top |
| Holes print small | Circles are polygons inscribed in the circle | Compensation is decided in Phase 2 (one place only, F1); if it is the model's job, add the radial value from tolerances.md. A mating hole is circumscribed (Useful idioms) |
| Very slow render | `minkowski()` or many-sided `hull()` on CGAL | Round in 2D with `offset(r=)` then `linear_extrude`, or chamfer instead |
| `Current top level object is empty` | `part` value matches no branch | Check the `_parts` names in params.json against the `if (part == ...)` branches |
| `assert(... >= 1.2)` fails although the math says exactly 1.2 | Floating-point rounding (70.8 − 68.4 is not exactly 2.4) | Compare with a tolerance: `>= 1.2 - 1e-6`; better, design to the recommended value, not the minimum |
| `-o preview.png` writes a 0-byte file and exits cleanly (Linux, no display) | No OpenGL context | Run under `xvfb-run -a openscad ...`; always check the PNG size and signature |

## No native fillets

OpenSCAD has no fillet operation. Use, in order of preference:
1. **Chamfers**: `hull()` of two thin slabs, or `linear_extrude(height, scale=...)`.
2. **2D rounding**: `offset(r=+r) offset(delta=-r)` on the outline, then `linear_extrude`.
3. `minkowski()` with a small sphere: last resort, very slow on CGAL.

Bottom edges get chamfers, not fillets (P6): a fillet on the bed edge is an overhang.

## Useful idioms

```openscad
module rounded_box(size, r) {           // vertical edges rounded, flat top and bottom
  linear_extrude(size.z) offset(r = r) offset(delta = -r) square([size.x, size.y]);
}
module through_hole(d, h) {             // overshoots both faces by 0.1
  translate([0, 0, -0.1]) cylinder(d = d, h = h + 0.2);
}
module mating_hole(d, h, fn = 0) {      // circumscribed: the polygon's flats sit on d, not inside it
  n = fn > 0 ? fn : max(64, ceil(PI * d / 0.4));               // as parts.circle_segments
  translate([0, 0, -0.1]) cylinder(d = d / cos(180 / n), h = h + 0.2, $fn = n);
}
module teardrop_hole(d, length) {       // horizontal along +X from x = 0, 45° roof, point up (+Z)
  s = d / (2 * sqrt(2));                // where the 45° roof meets the circle
  translate([-0.1, 0, 0]) rotate([90, 0, 90]) linear_extrude(length + 0.2)
    hull() { circle(d = d); polygon([[-s, s], [0, d / sqrt(2)], [s, s]]); }
}
module countersunk_hole(d, head_d, depth) {   // mouth at z = 0 going down, 90° cone to head_d
  translate([0, 0, -depth - 0.1]) cylinder(d = d, h = depth + 0.2);
  translate([0, 0, -(head_d - d) / 2])  // the cone runs on 0.1 above the face, still at 45°
    cylinder(d1 = d, d2 = head_d + 0.2, h = (head_d - d) / 2 + 0.1);
}
```

- `mating_hole`: OpenSCAD inscribes its polygons, so a hole drawn at its nominal size leaves a
  few hundredths less play than designed and `fit.py` WARNs at exactly the clearance.
  Circumscribe holes that something must fit (pins and pegs stay inscribed), and pass
  `fit.py --min-clearance` the designed clearance, model hole compensation included (F1).
- `teardrop_hole`: the apex sits r·√2 above the axis, as `parts.teardrop_hole` (`design.md`,
  "Overhangs"); rotate it for a hole along Y.
- `countersunk_hole`: `head_d` is the head's diameter, from the caliper for a screw in hand, else
  the ISO table in `design.md`, plus 2 × 0.3 mm clearance (`design.md`, "Screws, inserts and
  threads").
- A snap's strain check runs outside OpenSCAD: `strength.py snap --length --h --b --undercut
  --material` (standard library only: strain against the limit, `--repeated` for a joint opened
  often, the deflection force as its load, insertion and release forces), or
  `parts.snap_fit_check(L, t, y, material)` where manifold3d is installed
  (`phase-4-features-joints.md`).
