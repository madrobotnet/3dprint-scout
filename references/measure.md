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

## A number kept as evidence: `--expect`

A size read once in a chat is gone at the next rebuild. To keep it as evidence, run the same
command with `--expect` on the number you read, named by its path in the output, and save the
report:

```bash
# a hand calculation confirmed on the built part (the lip top at least 17.5 mm above the bed:
# a cut across the stand at y = 2, so the loop's size[1] is its height)
python3 "$SKILL_DIR/scripts/measure.py" slice out/sled.stl --axis y --z 2 \
  --expect "levels[0].loops[0].size[1]>=17.5" --what "lip top above the bed" > out/m_lip.json
# a size read from the user's file (the plug head is 13 mm wide)
python3 "$SKILL_DIR/scripts/measure.py" info ref/plug.stl --expect "objects[0].size_mm[0]=13" --tol 0.2 \
  --what "plug head width" > out/m_plug_w.json
```

- The path follows the JSON: `levels[0].loops[0].size[1]` (slice), `depth_mm[3][5]`
  (raymap, row by v then u), `objects[0].size_mm[2]` (info). Look at the output first and
  choose the number that is the size you mean; loops are sorted by area, largest first.
- `=` needs `--tol`; `>=` and `<=` are bounds, for success criteria such as "at least 6 mm".
- With `--axis y` (or x) `--z` is the position along that axis and the cut is the x/z (or y/z)
  plane, so a loop's `size` is its width and height there.
- The report records the file's sha256 and the command, and `gate` is PASS only when every
  expectation passes. A rebuilt part has a new hash, so the report goes stale: measure again.
  Run it from the project folder with a relative path, and keep a user's file inside the
  project folder (`ref/plug.stl`): the report records the path as given, and the bundle refuses
  an absolute one or a file outside.
- Declare it in params.json `_verify.measurements` (`{"name": "lip height", "report":
  "out/m_lip.json"}`) and name it in a promise's evidence, or, for the user's file, in the
  `from` of a `user-file` dims entry (`references/checks.md`). Evidence of a promise must have
  read a part of this build; a `user-file` dims entry must have read the user's file.

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
file of its own that holds only the numbers of its `dims` entry, with the values in the
project's params.json (`.3dprint/housing_proxy.json`). Those keys in the project's params.json
are not the part generator's parameters: list them in `"_proxy_only": [...]` there, so the
part's build does not report them as typos, rather than adding them to the part's `PARAMETERS`
or `DEFAULTS`. Build and validate a proxy with
`--proxy`, which writes no 3MF, into a folder of its own, and save its JSON there; the phone
stand's plug proxy, `plug_proxy.py` with its numbers in `.3dprint/usb_c_plug.json`:

```bash
mkdir -p out/plug && python3 "$SKILL_DIR/scripts/build.py" run plug_proxy.py \
  --params .3dprint/usb_c_plug.json --proxy plug_proxy --out out/plug > out/plug/build.json
```

Use it in `fit.py` (seated fit) or with `--sweep-angles` (a lever's travel to its stop). The
joint names `out/plug/build.json` as `proxy_build` and the entry as `dims`; what `finalize.py`
makes of it: `references/outputs.md`. A proxy stays in `out/` and is never delivered; the
bundle carries its generator and params file, and its REPRODUCE.md builds it again.
