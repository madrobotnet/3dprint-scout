# Parts, objects and the build report

Read this when a design has more than one body that prints as one object (a colour part,
a label, a lever, a print-in-place latch), when you need the exact shape of `build.py`'s
JSON, or when a Bambu project needs several parts in one object.

## Why parts are split

A region that has its own job or may get its own colour (a latch, a lever, a label, a
sign plate, an insert, a logo) is modelled as a **separate body that touches the main
body**: shared faces, no boolean union. The slicer then shows it as its own part, and the
user can give it another filament by selecting it, without any remodelling. Never ask the
user about colours: always split, give every part the main filament, and say at delivery
which parts are separate and how to recolour them. If the user already named colours,
apply them.

Where to put the seam (`design.md`, "Colour and function seams" has the numbers):

- Keep the seam in a low-stress place. Inside one object, two touching parts that print
  with the **same** filament and settings are merged into one region per layer, so the
  walls run continuously across the seam (see "What Bambu Studio does with touching
  parts"). With **different** filaments the seam is a wall-to-wall bond between two
  perimeters, weaker than continuous extrusion.
- Do not split where flex or load concentrates: the root of a snap hook, a living hinge,
  a boss that takes a screw. Split the lever's handle, not its pivot.
- Both sides of a seam must be the same material (PLA to PLA); PLA onto PETG does not bond.
- A print-in-place moving part is a separate part too, with its clearance kept (0.3 mm
  per side, `tolerances.md`), and it is never merged with anything.

## `_parts` schema (params.json)

```json
{"_parts": {
   "lid":   {"expect": [70, 45, 3]},
   "label": {"expect": [40, 12, 1], "object": "lid", "role": "fused", "filament": 2},
   "latch": {"expect": [12, 6, 4],  "object": "lid", "role": "free", "clearance": 0.3}},
 "_assumptions": ["..."], "wall": 2.0}
```

| Key | Meaning |
|---|---|
| `expect` | Size `[x, y, z]` from the dimension table (design intent). Never a measured bounding box: `validate.py` flags an `expect` with four or more decimals that matches the mesh to 0.001 mm as copied |
| `object` | Parts with the same value form one object. Every part of an object is modelled in the **same frame** (Z-up, Z = 0 on the bed), so the STLs already hold the assembled positions. Without `object`, a part is an object of its own |
| `role` | `fused` (default in a group): must share faces with at least one other part of the object, no overlap. `free`: print-in-place, must not touch any other part |
| `clearance` | For `free` parts: the gap kept all round, mm per side (default 0.3) |
| `filament` | 1-based slot for a Bambu project (default: the main part's; the main part defaults to 1) |
| `shells` | Bodies expected in this one STL (default 1), as before |

The **first part listed** for an object is its main part: its filament, plate and print
settings go on the object. Fusion: name the bodies exactly like the parts and export one
STL per body; `build.py record` groups them from `--params`.

## Checks on an object

Parts are validated one by one as always (D1, M1–M5, …). An object with several parts
gets, in `objects[]`:

| ID | Check | Kind | Note |
|---|---|---|---|
| D2 | The whole object fits the usable bed | hard | One rotation for the whole object; the 3MF writers place the parent, never a part alone. For an object with several parts, or any object of a job that uses several filaments, the usable bed is the intersection of every tool's area in `printers.json` (`value.tools`), as `bambu3mf.py` lays such jobs out: on an X2D / H2D both nozzles may have to reach it |
| P1, P2 | Bed contact and overhang of the union of the parts | soft | Needs manifold3d: shared faces vanish, so a label on a lid is no overhang. Without it P2 is UNVERIFIED |
| A1 | `fused` part shares faces with another part, no overlap | hard | FAIL when it floats (nearest part named with its gap) or overlaps (the slicer would clip the overlap by its own rules). Bodies exported separately rarely share a tessellation (a 48-segment pin in a 64-segment hole crosses it by a few hundredths of a mm³), so an overlap up to a 0.01 mm skin over the shared area counts as touching, and a gap up to 0.01 mm does too |
| A2 | `free` part keeps its clearance | hard | FAIL on contact or overlap; WARN below the clearance (like F3) |

The gate of the build is the worst of every part and every object. A part's own P1/P2
take its lowest face as the bed, so for a part that sits on another one read the object's
P1/P2, not the part's.

## `build.py` output

One JSON document, schema `3dprint-scout.build/1`, also for `record`:

```json
{"schema": "3dprint-scout.build/1", "ran": true, "engine": "fusion", "source": "adapter.py",
 "gate": "PASS | FAIL | INCOMPLETE", "R4": "PASS",
 "parts": [{"name": "lid", "stl": "out/lid.stl", "artifact_sane": true, "object": "lid", "role": "fused",
            "rotation_deg": 0, "engine_warnings": [],
            "validate": {"schema": "3dprint-scout.validate/1", "gate": "PASS",
                         "files": [{"path": "out/lid.stl", "checks": {"D1": {"state": "PASS", "...": "..."}},
                                    "metrics": {"bbox_mm": [70, 45, 3], "volume_mm3": 9450, "...": "..."}}]},
            "assembly": {"object": "lid", "role": "fused", "checks": {"A1": {"state": "PASS", "...": "..."}}}}],
 "objects": [{"name": "lid", "parts": ["lid", "label"], "main": "lid", "gate": "PASS",
              "checks": {"D2": {"...": "..."}, "P1": {"...": "..."}, "P2": {"...": "..."}},
              "metrics": {"bbox_mm": [70, 45, 4], "volume_mm3": 9930, "shells": 1, "overhang_pct": 0.0, "...": "..."},
              "rotation_deg": 0, "method": "union of the parts (manifold3d) ..."}],
 "sources": ["adapter.py"], "threemf": "out/adapter.3mf", "seconds": 1.2,
 "warnings": ["..."], "errors": []}
```

- `parts[i].validate` is the full `validate.py` document for that part (SKILL.md shows
  its shape); the part's verdicts are at `parts[i].validate.files[0].checks`, its numbers
  at `...files[0].metrics`. `role` is `null` for a part alone in its object; `assembly`
  exists only for parts in a group.
- `objects[]` lists every object; a single-part object has only `name`, `parts`, `main`.
- A broken STL has `artifact_sane: false` and `artifact_error`, no manifest and no
  `validate`; `R4` is then FAIL.
- `warnings` and `errors` repeat everything worth reading from every part and object
  (validator warnings, engine warnings, rotation notes, object FAILs with their notes).
  Read those two lists first.

## What Bambu Studio does with touching parts (02.08.02.61 source)

- Each part (a `ModelVolume` of type model part) gets a `PrintRegionConfig` from
  `region_config_from_model_volume` (`PrintObject.cpp`): the object's config, then the
  part's own config (`extruder` sets `wall_filament`, `sparse_infill_filament` and
  `solid_infill_filament`, `apply_to_print_region_config`).
- `generate_print_object_regions` (`PrintApply.cpp`) looks up or creates a `PrintRegion`
  per config through `get_create_region`: **two parts with the same config share one
  region** (the lookup key is the config hash and equality; a per-volume tag is added only
  for the "per-part gradient" filament feature, off by default).
- `slices_to_regions` (`PrintObjectSlice.cpp`): at every layer where two parts' bounding
  boxes meet in XY (touching counts, `overlap_in_xy` is inclusive), the slices are clipped
  against each other (`clip_multipart_objects`, default true; a later part carves an
  earlier one, or the smaller the larger with "order-independent overlap carving") and
  the slices of the **same region are appended and closed with `closing_ex(EPSILON)`**,
  which unites polygons that touch. So two touching parts with the same filament and
  settings become one polygon per layer, and perimeters run around the union: **no inner
  wall between them**. Parts with different filaments are different regions, each with
  its own perimeters: the seam is a wall-to-wall bond.
- Consequence for the modelling rule: a same-colour seam costs nothing; a two-colour seam
  is a bond between two outer walls, so keep it in a low-stress place. What the
  slicing preview shows for a same-filament pair has not yet been confirmed in the app.
- Per-part settings in `model_settings.config` (`<part>` metadata other than name,
  matrix and source keys, `bbs_3mf.cpp` `_generate_volumes_new`) are applied to the part;
  `bambu3mf.py` writes only `extruder` per part and keeps every other setting on the
  object, so same-filament parts always share a region.

## The Bambu project layout for an object with parts

Verified against `bbs_3mf.cpp` (`_add_mesh_to_object_stream`,
`_add_object_components_to_stream`, the `<part>` writer near `MESH_STAT_TAG`); opening a
file written this way in Bambu Studio 02.08.02.61 is still to be confirmed:

- `3D/Objects/object_N.model` holds **every part of object N** as its own sub-object
  (`<object id=sub p:UUID=... type="model">` with its mesh, vertices centred on the part's
  own box); the wrapper object in `3D/3dmodel.model` has one `<component p:path=...
  objectid=sub transform=...>` per part whose translation is the part's centre relative to
  the object's centre; the build item places the object.
- `Metadata/model_settings.config`: `<object id=wrapper>` with `name`, `extruder` (the main
  filament), the object-level settings and `face_count` (sum over parts), then one
  `<part id=sub subtype="normal_part">` per part with `name`, `matrix` (4 × 4, row-major,
  the same translation), `extruder` only when the part's filament differs from the object's,
  and `mesh_stat`. A part without its own `extruder` follows the object (`GUI_ObjectList.cpp`
  shows it the object's filament and erases the parts' own when the object's is changed), so
  recolouring the object recolours every part that was not given a colour of its own.
- On load (`_generate_volumes_new`) a part's mesh is centred again and its transform
  becomes component transform × centring, so positions survive; `matrix` only becomes the
  part's source transform.
