# Python engine (manifold3d)

Read this right before Phase 3 when Phase 0 picked Python: as the fallback, or by choice for
organic and freeform shapes. Tell the user once: this path produces meshes only (no editable CAD
file) and has no native fillets (smooth blends come from `sdf.py`, chamfers from `parts.py`).

## Script shape

```python
import manifold3d as m3d
import parts                        # the skill's part library (scripts/parts.py)

# PARAMETERS come from params.json; defaults here document units and sources.
DEFAULTS = {
    "w": 60.0,          # mm, outer width
    "wall": 2.0,        # mm
    "clearance": 0.3,   # mm, radial per side (tolerances.md)
}

def build(params):
    p = {**DEFAULTS, **params}
    outer = parts.rounded_box([p["w"], 40, 25], r=3)                   # vertical edges rounded
    inner = m3d.Manifold.cube([p["w"] - 2 * p["wall"], 40 - 2 * p["wall"], 25]) \
        .translate([p["wall"], p["wall"], p["wall"]])
    body = parts.bottom_chamfer(outer - inner, 0.4)                     # elephant-foot chamfer
    body -= parts.screw_hole("M3", depth=8, kind="insert").translate([8, 8, 25])
    return {"body": body}          # one entry per part, in print orientation
```

- `build(params)` returns `{part_name: Manifold}`. Names must match `_parts` in params.json.
- Model Z-up with Z = 0 on the bed. `build.py` exports each part as binary STL itself; do not write
  files from the generator.
- `import parts` and `import sdf` work from any generator: `build.py` puts the skill's `scripts/`
  folder on the path (after the generator's own folder). Both files are hashed into the manifest
  with the generator, so `build.py` lists them in `sources`; pass that same list to `validate.py`.
- Local helper modules next to the generator are allowed and hashed the same way.

## Run

```bash
python3 "$SKILL_DIR/scripts/build.py" run model.py --params .3dprint/params.json --out out
```

## Part library: `parts.py`

Tested FDM-friendly building blocks (mm, Z-up, bottom on the bed; holes are cutters to subtract,
mouth at z = 0 going down, overshooting the face by 0.1 mm). Defaults follow `design.md` and
`tolerances.md`; holes are nominal size (F1: pass `comp=` only when the model compensates).

| Call | Makes |
|---|---|
| `rounded_box(size, r, edges="vertical"\|"top"\|"all")` | Box with rounded vertical edges (default), plus top edges, or every edge |
| `chamfered_box(size, c, edges="bottom"\|"top"\|"vertical"\|"all")` | Box with 45° chamfers; `"bottom"` is the elephant-foot chamfer |
| `bottom_chamfer(part, c)` | Chamfers the bed edge of any prismatic part, inner edges included, without booleans |
| `screw_hole(size, depth, kind, fit, comp, insert_d)` | `kind`: `clearance` (ISO 273 `fit` fine/medium/coarse), `tap` (d − P), `insert` (heat-set; `insert_d` from the datasheet), `countersunk` (ISO 10642, 90°), `counterbore` (ISO 4762 head) |
| `hole(d, depth, comp)` | Plain round cutter |
| `teardrop_hole(d, length, axis="x"\|"y")` | Horizontal hole with a 45° roof, point up |
| `standoff(h, size, kind="insert"\|"tap", wall, foot)` | Boss on the bed with the hole from its top; `foot` adds a 45° flare |
| `snap_hook(length, thickness, width, undercut, entry_angle, retention_angle, material)` | Cantilever hook lying flat (flexes in Y); raises when the strain exceeds the material limit |
| `snap_window(...)` | Cutter for the matching window in the mating wall (snug clearance) |
| `snap_fit_check(L, t, y, material, repeated)` | Strain, limit, `ok`, maximum deflection |
| `hinge(length, knuckle_d, pin_d, leaf_w, leaf_t, knuckles, clearance)` | Print-in-place hinge: `{"leaf_a", "leaf_b"}`, two bodies that never touch (validate with `--shells 2`) |
| `text(string, height, depth, font, align)` | Text solid (cap height in mm) to union (emboss) or subtract (engrave); needs matplotlib, or fontTools plus a font file |
| `thread(d, pitch, length, internal, clearance)` | Approximate ISO thread: a rod, or with `internal=True` a cutter for a nut |
| `clean(part)` | Welds the slivers hulls, Minkowski sums and some booleans leave (M3) |
| `circle_segments(r)` | Segments so curved parts meet D1 |

Every function's docstring names its defaults and sources. Letters of `text()` are separate
bodies until they sit on a face; `thread()` is a twisted extrusion with flat crest and root, no
tolerance class, and the agent says so when delivering.

## Organic and freeform shapes: `sdf.py`

Build smooth, blended, sculpted shapes as a **signed distance function** and mesh it once with
`sdf.to_manifold`. That one marching pass yields a closed mesh with no needle triangles; the
booleans-of-height-fields route (below) produced M3 failures that no cleanup pass could fix.

```python
import sdf

def build(p):
    leaf = [[x, y], ...]                                        # outline in mm
    top = lambda x, y: 2.0 + 6.0 * max(0.0, 1 - (x / 30) ** 2 - (y / 12) ** 2)
    body = sdf.height_field(leaf, top)                          # 0 <= z <= top(x, y) inside the outline
    body = body - sdf.box([20, 8, 10]).translate([20, -4, 4])   # pocket with vertical walls
    grip = sdf.capsule([5, 0, 3], [-20, 0, 3], 3)
    body = sdf.smooth_union(body, grip, k=2.5)                  # fillet-like blend, about k mm
    part = sdf.to_manifold(body, edge_length=0.5, floor=0.0)          # flat bed after the blend
    return {"handle": part}
```

- Primitives: `sphere`, `box`, `rounded_box`, `capsule`, `cylinder` (any axis), `torus`,
  `extrude(polygon, h)`, `height_field(polygon, top, bottom)`, `revolve(profile)`.
  Operators: `a | b`, `a - b`, `a & b`; `smooth_union / smooth_subtract / smooth_intersect(a, b, k)`;
  `.offset(r)`, `.shell(t)` (hollow, wall t), `.translate`, `.rotate(deg, axis)`, `.scale`, `.mirror`.
- Sign: negative inside, like every SDF reference. `to_manifold` flips the sign for manifold3d's
  `level_set` (which wants positive inside) and raises if the result is empty or touches the
  grid bounds (inverted function or bounds too small).
- Cost: one Python call per grid point, about 2 × (extent / edge_length)³. `edge_length` 0.5 mm
  suits a 0.4 mm nozzle; 1.0 for a quick look. `to_manifold` times the function first and warns on
  stderr when a run will take long; `sdf.grid_estimate(f, edge)` gives the numbers. A 60 × 25 mm
  blended handle at 0.5 mm takes about half a minute.
- Crumbs (bodies under 0.1 % of the largest) are dropped so M5 holds; cavities are kept. Pass
  `report={}` to get grid size, time, triangles and dropped bodies back.
- Smooth unions bulge up to k / 4 beyond the inputs: `floor=0.0` cuts the bed flat afterwards
  (and welds the cut; a bare `trim_by_plane` leaves slivers that fail M3, `parts.clean` fixes
  those too).

### Alternative: constrained triangulation lifted to surfaces

When a surface is a pure height field over a polygon with sharp constraint lines (a pocket rim
that must be exactly straight), build it as **one mesh**: triangulate the outline once with every
constraint loop as exact vertices (`scipy.spatial.Delaunay` is not constrained: split outline and
constraint edges to the point spacing so they survive, drop triangles outside the outline, check
every constraint edge is present), lift vertices to top and bottom surfaces, stitch the outline
with wall quads, then `parts.from_arrays(V, F)`. Plane cuts along constraint edges are fine
afterwards. Never intersect a height-field grid with extruded walls: that leaves needle triangles
far thinner than 0.001 mm (M3).

## API you will need

Checked against manifold3d 3.5.4 (`pip show manifold3d`).

| Need | Call |
|---|---|
| Box, cylinder, sphere | `Manifold.cube([x, y, z])`, `Manifold.cylinder(h, r_low, r_high, segments)`, `Manifold.sphere(r, segments)` |
| Move, rotate, scale | `.translate([x, y, z])`, `.rotate([rx, ry, rz])` (degrees, X then Y then Z), `.scale([sx, sy, sz])` |
| Union, difference, intersection | `a + b`, `a - b`, `a ^ b` |
| 2D outline | `m3d.CrossSection([[[x, y], ...]])` (a **list of contours**), `CrossSection.square([w, d])`, `CrossSection.circle(r, segments)` |
| Rounded 2D corners | `cs.offset(-r, m3d.JoinType.Round).offset(r, m3d.JoinType.Round)` or `parts.rounded_rect(w, d, r)` |
| Extrude, revolve | `Manifold.extrude(cs, height, n_divisions, twist_degrees, (sx, sy))`, `Manifold.revolve(cs, segments)` |
| Hull (chamfers, tapers) | `Manifold.batch_hull([a, b])` or `(a + b).hull()` |
| Cut flat, split | `.trim_by_plane(normal, offset)` keeps the side the normal points to; `.split_by_plane` |
| Mesh in, mesh out | `parts.mesh_arrays(m)` → `(V, F)`; `parts.from_arrays(V, F)` (raises if not closed) |
| Gap, overlap | `a.min_gap(b, search)`, `(a ^ b).volume()` (fit.py does the F3 check from STLs) |

Signatures change between manifold3d releases. If a call fails, print `help(m3d.Manifold.<name>)` and
adapt instead of guessing.

## Preview

`python3 "$SKILL_DIR/scripts/preview.py" out/body.stl -o out/preview.png --overwrite` renders iso,
front, right and top views (numpy only; see SKILL.md Phase 0). The numbers from `validate.py` stay the
evidence; the image is for the user and for P6.

## Pitfalls

| Symptom | Fix |
|---|---|
| Generator error "status ..." | A boolean got invalid input (often a zero-thickness wall); check parameters |
| D1 FAIL on round parts | Pass enough segments: `parts.circle_segments(r)` (= max(64, 2πr / 0.4)) |
| M5 FAIL | Shapes meant to join only touch; overlap them by ≥ 0.01 mm. With `sdf.py`: crumbs are dropped already, so a second body is real |
| Coincident-face artefacts | Overshoot cutting bodies by 0.01–0.1 mm (the `parts` cutters do) |
| M3 FAIL after a hull, Minkowski sum or boolean | `parts.clean(part)` welds the slivers; if it raises, the geometry itself is open |
| M3 FAIL on a curved surface | Height-field booleans made needle triangles; build it with `sdf.py` or as one mesh (above) |
| D3 FAIL with a negative volume | The mesh is wound inward; reverse every face (`F[:, [0, 2, 1]]`) |
| `sdf.to_manifold` raises "reaches the grid bounds" | The function is positive inside (flip the sign) or `bounds=` is too small |
| `sdf.to_manifold` takes minutes | Raise `edge_length`, shrink the bounds, or simplify the SDF (polygons with hundreds of points are slow) |
| `parts.text` raises ImportError | `pip install matplotlib`, or `pip install fonttools` and pass `font="/path/to/font.ttf"` |
