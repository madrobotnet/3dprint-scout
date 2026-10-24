# Python engine: organic and freeform shapes (`sdf.py`)

Read this only for an organic or freeform part built with the Python engine (a sculpted grip,
a leaf, a blended handle). The rest of the engine is in `references/engines/python.md`.

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

## Alternative: constrained triangulation lifted to surfaces

When a surface is a pure height field over a polygon with sharp constraint lines (a pocket rim
that must be exactly straight), build it as **one mesh**: triangulate the outline once with every
constraint loop as exact vertices (`scipy.spatial.Delaunay` is not constrained: split outline and
constraint edges to the point spacing so they survive, drop triangles outside the outline, check
every constraint edge is present), lift vertices to top and bottom surfaces, stitch the outline
with wall quads, then `parts.from_arrays(V, F)`. Plane cuts along constraint edges are fine
afterwards. Never intersect a height-field grid with extruded walls: that leaves needle triangles
far thinner than 0.001 mm (M3).
