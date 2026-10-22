# Measuring a supplied file and building a proxy of the mating part

Read this in Phase 2 when the user gives a file of the object the part must fit (a
manufacturer's kit 3MF, a scan, a reference model) or when a mechanism must be checked
against the thing it moves in.

## Rules

- **Numbers only.** Measure interface dimensions (openings, windows, pin spacing, corner
  radii, wall thickness); never copy geometry into the design and never ship the file's
  meshes. A manufacturer's file is an official source: record it as "official file,
  measured" in the dimension table. A model from another maker is a secondary source and
  needs a second source that agrees, as for any secondary source.
- Say which object and which file you measured, with the loop level or ray grid, so the
  user can repeat it.

## `measure.py`

```bash
python3 "$SKILL_DIR/scripts/measure.py" info kit.3mf --extract ref_mesh        # objects, parts, boxes; one STL each
python3 "$SKILL_DIR/scripts/measure.py" slice ref_mesh/obj_2_coupler.stl --z 0.5:70:5 --center
python3 "$SKILL_DIR/scripts/measure.py" raymap ref_mesh/obj_15_housing.stl --axis x --sign -1 --u -30:-12:1 --v 8:20:0.5
```

- `info` reads STL and 3MF (core objects, Bambu Studio components with their transforms
  and names, units converted to mm) and lists every placed object with its parts; with
  manifold3d it adds volume and watertightness. `--extract` writes one STL per object so
  the other commands and `preview.py` can work on it.
- `slice` gives the loops at each level: bounds, size, area, centroid, a circle fit
  (`is_circle` when at least eight points fit within 1 % of the radius) and the four corner
  radii of a rounded outline. `closed: false` marks an open chain (a hole in the surface, or
  crossing surfaces); it gets bounds only and a warning, never a made-up area. Slice a range (`--z 0:70:2`) to find where a profile changes
  (a lip, a step, the start of a chamfer), then single levels for the numbers. `--center`
  puts the XY centre of the box at the origin, which is how mating parts are dimensioned.
  `--axis x` or `y` slices across.
- `raymap` shoots a grid of rays at a wall and prints the depth of the first surface
  behind the outer face: a window is `.` (nothing within `--max-depth`), a recess is its
  depth, a rib stands at 0. Read the `text` rows (v from high to low) to size windows and
  locate them; refine the step around the edges you need (0.25 mm for a 0.1 mm answer).

## A watertight proxy of the mating part

A fit or a sweep needs a closed mesh of the thing the part mates with. The supplied file is
often not watertight (scans, exported assemblies) and is never shipped. Build a small proxy
from the measured numbers with the Python engine, as its own generator in the project:

```python
import manifold3d as m3d
import parts

def build(p):
    # Housing: an extrusion of the measured outline (rounded rectangle, slice at z = 10),
    # hollowed to the measured wall, with the three latch windows found by raymap.
    outer = parts.rounded_rect(p["housing_w"], p["housing_d"], p["corner_r"])
    shell = m3d.Manifold.extrude(outer, p["depth"]) - \
        m3d.Manifold.extrude(outer.offset(-p["wall"], m3d.JoinType.Round), p["depth"] + 1).translate([0, 0, -0.5])
    for x, y, w, h in p["windows"]:                       # from raymap: centre, size
        shell -= m3d.Manifold.cube([w, p["wall"] + 1, h]).translate([x - w / 2, y - 0.5, p["win_z"]])
    return {"housing_proxy": shell}
```

Keep it to the faces the part touches or sweeps past; everything else can be a box. Take every
size from the parameters, never a number written in the generator, and give the proxy a params
file of its own that holds only its numbers, with the values in the project's params.json
(`.3dprint/housing_proxy.json`). Build and validate it with `--proxy`, which writes no 3MF:

```bash
python3 "$SKILL_DIR/scripts/build.py" run housing_proxy.py --params .3dprint/housing_proxy.json \
  --proxy housing_proxy --out out/proxy > out/proxy_build.json
```

Use it as part A in `fit.py` (seated fit) or with `--sweep-angles` (a lever's travel to its
stop). The joint names `out/proxy_build.json` as `proxy_build` and the numbers as `dims`
(`references/checks.md`). `finalize.py` then checks that the proxy was generated from its params
file as it is now, and that those numbers are exactly the ones the dims declare, with the same
values. Without that, or for a proxy taken in with `record`, a promise resting on the joint is
only `assumed`; a proxy built from other values is not verified. A proxy stays in `out/`: it is never delivered.
