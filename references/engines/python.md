# Python engine (manifold3d)

Read this right before Phase 3 when Phase 0 picked Python: as the fallback, or by choice for
organic and freeform shapes. Tell the user once: this path produces meshes only (no editable CAD
file) and has no fillets.

## Script shape

```python
import manifold3d as m3d

# PARAMETERS come from params.json; defaults here document units and sources.
DEFAULTS = {
    "w": 60.0,          # mm, outer width
    "wall": 2.0,        # mm
    "clearance": 0.3,   # mm, radial per side (tolerances.md)
}

def build(params):
    p = {**DEFAULTS, **params}
    outer = m3d.Manifold.cube([p["w"], 40, 25])
    inner = m3d.Manifold.cube([p["w"] - 2 * p["wall"], 40 - 2 * p["wall"], 25]) \
        .translate([p["wall"], p["wall"], p["wall"]])
    return {"body": outer - inner}          # one entry per part, in print orientation
```

- `build(params)` returns `{part_name: Manifold}`. Names must match `_parts` in params.json.
- Model Z-up with Z = 0 on the bed. `build.py` exports each part as binary STL itself; do not write
  files from the generator.
- Local helper modules next to the generator are allowed; `build.py` hashes every `.py` the generator
  imports from its own folder into the manifest.

## Run

```bash
python3 "$SKILL_DIR/scripts/build.py" run model.py --params .3dprint/params.json --out out
```

## API you will need

Checked against manifold3d 3.5.4 (`pip show manifold3d`).

| Need | Call |
|---|---|
| Box, cylinder, sphere | `Manifold.cube([x, y, z])`, `Manifold.cylinder(h, r_low, r_high, segments)`, `Manifold.sphere(r, segments)` |
| Move, rotate, scale | `.translate([x, y, z])`, `.rotate([rx, ry, rz])` (degrees), `.scale([sx, sy, sz])` |
| Union, difference, intersection | `a + b`, `a - b`, `a ^ b` |
| 2D outline | `m3d.CrossSection([[[x, y], ...]])` (a **list of contours**), `CrossSection.square([w, d])`, `CrossSection.circle(r, segments)` |
| Rounded 2D corners | `cs.offset(-r, m3d.JoinType.Round).offset(r, m3d.JoinType.Round)` |
| Extrude, revolve | `Manifold.extrude(cs, height, n_divisions, twist_degrees, (sx, sy))`, `Manifold.revolve(cs, segments)` |
| Hull (chamfers, tapers) | `Manifold.batch_hull([a, b])` or `(a + b).hull()` |

Signatures change between manifold3d releases. If a call fails, print `help(m3d.Manifold.<name>)` and
adapt instead of guessing.

## Organic and freeform surfaces

Build the surface as **one mesh**, not as booleans of a height-field grid with extruded walls.
Intersecting a grid surface with vertical walls leaves needle triangles far thinner than
0.001 mm; M3 fails, and simplify, refine or warp passes do not reliably remove them.

1. Triangulate the 2D outline once, with the outline and every constraint loop (pocket rim, lip
   edge, any line a later cut or feature follows) as exact vertices. `scipy.spatial.Delaunay` is
   not constrained: split every outline and constraint edge into pieces no longer than the point
   spacing so its edges survive, drop triangles whose centroid lies outside the outline or inside a
   hole, then check that every constraint edge is present.
2. Lift the vertices with height functions to a top and a bottom surface, and stitch the outline
   with wall quads.
3. Make the solid: `m3d.Manifold(m3d.Mesh(vert_properties=V.astype("float32"),
   tri_verts=F.astype("uint32")))`. Check `status()` and that `volume() > 0`: a mesh wound
   inward still constructs, with a negative volume. Faces wind counter-clockwise seen from outside.
4. Plane cuts and booleans are fine afterwards when they run along constraint edges.

## Preview

A quick look at the STL: matplotlib's `Poly3DCollection` draws hidden faces in the wrong order on
concave parts, so treat it as rough. When `trimesh` and `embreex` are installed, a ray-traced
depth or shading image is accurate. Either way, the numbers from `validate.py` are the evidence.

## Pitfalls

| Symptom | Fix |
|---|---|
| Generator error "status ..." | A boolean got invalid input (often a zero-thickness wall); check parameters |
| D1 FAIL on round parts | Pass enough segments: `segments = max(64, int(2 * math.pi * r / 0.4))` |
| M5 FAIL | Shapes meant to join only touch; overlap them by ≥ 0.01 mm |
| Coincident-face artefacts | Overshoot cutting bodies by 0.01–0.1 mm |
| M3 FAIL on a curved surface | Height-field booleans made needle triangles; build one mesh (see above) |
| D3 FAIL with a negative volume | The mesh is wound inward; reverse every face |
