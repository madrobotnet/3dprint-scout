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
  with `-D name=value` from `params.json`, so names must match exactly.
- One `.scad` file builds every part; `part` selects which. Each part is exported in its **print
  orientation**: Z = 0 is the bed, the face that sits on the bed is at Z = 0.
- `include <file.scad>` and `use <file.scad>` are fine: `build.py` collects them with `-d` and hashes
  them into the manifest, so editing a library makes old STLs stale (R3).

## Run

```bash
python3 "$SKILL_DIR/scripts/build.py" run model.scad --params .3dprint/params.json --out out \
  --printer .3dprint/printers.json --tools 0
```

`build.py` probes `--backend=manifold` itself. On CGAL-only builds (stable 2021.01) heavy booleans
are slow; `--timeout` defaults to 900 s. Never pass `--enable=manifold`.

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `WARNING: Object may not be a valid 2-manifold` | A cut body ends exactly on a face (coincident faces) | Make every cutting body overshoot by 0.01–0.1 mm on each open side |
| M5 FAIL: more bodies than expected | Parts that should touch are separated by a hairline, or a `union()` of shapes that only share an edge | Overlap joined shapes by ≥ 0.01 mm; never rely on edge contact |
| D1 FAIL by 0.1–0.3 mm on round parts | Default `$fa = 12, $fs = 2` gives 30 segments on large circles | Keep `$fa = 1; $fs = 0.4;` at the top |
| Holes print small | Circles are polygons inscribed in the circle | Compensation is decided in Phase 2 (one place only, F1); if it is the model's job, add the radial value from tolerances.md |
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
```
