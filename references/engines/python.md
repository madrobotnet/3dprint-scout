# Python engine (manifold3d)

Read this right before Phase 3 when Phase 0 picked Python: when Blender is not usable (Rule A:
mechanical and prismatic parts with its part library, OpenSCAD being the other choice there;
organic and freeform shapes with `sdf.py`), or for a part that needs a parts.py helper Blender
cannot reach (no manifold3d in Blender's Python). Tell the user once: this path produces meshes only (no editable CAD
file) and has no native fillets (smooth blends come from `sdf.py`, chamfers from `parts.py`).

## Script shape

```python
import manifold3d as m3d
import parts                        # the skill's part library (scripts/parts.py)

# Every parameter with its unit and source; params.json overrides by key.
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
- Defaults are a module-level dict named `DEFAULTS`, merged as `p = {**DEFAULTS, **params}`
  (`params` is params.json without its `_` keys). `build.py` records the same merge in the
  build JSON (`parameters`, scope `merged`), which `strength.py --from-build` links to, and warns
  about a params.json key that `DEFAULTS` lacks (a typo builds with the default). Without
  `DEFAULTS` the build records only the params.json values (scope `overrides`). Values the
  generator computes from others are not recorded (`references/outputs.md`).
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
Arguments are listed in the order the function takes them; `...` stands for arguments left
out (they have defaults), and names after `*` are keyword-only. Pass anything after the first
few by keyword.

| Call | Makes |
|---|---|
| `rounded_box(size, r, edges="vertical"\|"top"\|"all")` | Box with rounded vertical edges (default), plus top edges, or every edge |
| `chamfered_box(size, c, edges="bottom"\|"top"\|"vertical"\|"all")` | Box with 45° chamfers; `"bottom"` is the elephant-foot chamfer |
| `bottom_chamfer(part, c)` | Chamfers the bed edge of any prismatic part, inner edges included, without booleans |
| `screw_hole(size, depth, kind, fit, comp, insert_d, ..., head_d, head_h)` | `kind`: `clearance` (ISO 273 `fit` fine/medium/coarse), `tap` (d − P), `insert` (heat-set; `insert_d` from the datasheet), `countersunk` (ISO 10642, 90°), `counterbore` (ISO 4762 head); `head_d` (and `head_h` for a counterbore) is a measured head, a wood screw's say, that beats the ISO table |
| `hole(d, depth, comp)` | Plain round cutter |
| `teardrop_hole(d, length, axis="x"\|"y")` | Horizontal hole with a 45° roof, point up |
| `standoff(h, size, kind="insert"\|"tap", wall, depth, foot, ...)` | Boss on the bed with the hole from its top; `foot` adds a 45° flare |
| `snap_hook(length, thickness, width, undercut, entry_angle, retention_angle, flat, root_overlap, material)` | Cantilever hook lying flat (flexes in Y); raises when the strain exceeds the material limit |
| `snap_window(...)` | Cutter for the matching window in the mating wall (snug clearance) |
| `snap_fit_check(length, thickness, deflection, material, q, repeated)` | Strain, limit, `ok`, maximum deflection |
| `hinge(length, knuckle_d, pin_d, leaf_w, leaf_t, knuckles, clearance, segments, decorative, *, duty)` | Print-in-place hinge: `{"leaf_a", "leaf_b"}`, two bodies that never touch (validate with `--shells 2`). `duty` is keyword-only: `duty="latch"` (default) refuses less than design.md's field minimums (pin 3.2, pin wall 2.2 above the teardrop's point, leaf 2.5, knuckle 4 mm); `duty="lid"` (a lid, door or flap hinge, no lever between hand and pin) refuses only what does not print (pin 2.0, wall and leaf 1.2, knuckle 2 mm) and fewer than 3 knuckles (odd recommended): its size must pass `strength.py hinge` at SF ≥ 2 plus a coupon print on top (`references/parts.md`); `duty="decorative"` for a hinge that carries nothing (`decorative=True` is its old spelling). `clearance` is both the radial clearance and the axial gap: pass it to `strength.py hinge` as `--gap` and `--clearance` |
| `text(string, height, depth, font, weight, align)` | Text solid (cap height in mm) to union (emboss) or subtract (engrave); without `font`, DejaVu Sans when it draws the text, else the first installed font that does (Noto Sans CJK for Korean), named in a warning in the build report; needs matplotlib, or fontTools plus a font file |
| `thread(d, pitch, length, internal, clearance)` | Approximate ISO thread: a rod, or with `internal=True` a cutter for a nut |
| `clean(part)` | Welds the slivers hulls, Minkowski sums and some booleans leave (M3) |
| `circle_segments(r)` | Segments so curved parts meet D1 |

Every function's docstring names its defaults and sources. Letters of `text()` are separate
bodies until they sit on a face; `thread()` is a twisted extrusion with flat crest and root, no
tolerance class, and the agent says so when delivering. Members that carry load are checked in
Phase 4.

## Organic and freeform shapes: `sdf.py`

Smooth, blended or sculpted shapes are a signed distance function meshed once with
`sdf.to_manifold`: `references/engines/python-sdf.md`.

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
| Hull (chamfers, tapers) | `Manifold.batch_hull([a, b])` or `(a + b).hull()`. manifold3d gathers a hull of more than 3333 triangles on several threads, in another triangle order on each run; while `build()` runs under `build.py run` such a hull comes out sorted, so the rebuild writes the same STL. Build large hulls inside `build()` |
| Cut flat, split | `.trim_by_plane(normal, offset)` keeps the side the normal points to; `.split_by_plane` |
| Mesh in, mesh out | `parts.mesh_arrays(m)` → `(V, F)`; `parts.from_arrays(V, F)` (raises if not closed) |
| Gap, overlap | `a.min_gap(b, search)`, `(a ^ b).volume()` (fit.py does the F3 check from STLs) |

Signatures change between manifold3d releases. If a call fails, print `help(m3d.Manifold.<name>)` and
adapt instead of guessing.

## Preview

`python3 "$SKILL_DIR/scripts/preview.py" out/body.stl -o out/preview.png --overwrite` renders iso,
front, right and top views (numpy only; see `references/phase-0-detect.md`). The numbers from `validate.py` stay the
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
