# Parts, objects and the build report

Read this when a design has more than one body that prints as one object (a colour part,
a label, a lever, a print-in-place latch), when you need the exact shape of `build.py`'s
JSON, or when a Bambu project needs several parts in one object.

Contents:

- [Why parts are split](#why-parts-are-split)
- [`_parts` schema (params.json)](#_parts-schema-paramsjson)
- [Checks on an object](#checks-on-an-object)
- [Printing the mechanism first](#printing-the-mechanism-first)
- [`build.py` output](#buildpy-output)
- [What Bambu Studio does with touching parts (02.08.02.61 source)](#what-bambu-studio-does-with-touching-parts-02080261-source)
- [The Bambu project layout for an object with parts](#the-bambu-project-layout-for-an-object-with-parts)

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
| `shells` | Bodies expected in this one STL (default 1), as before. A text part counts glyph pieces, never letters: Hangul jamo, the dot of i and j and Hanzi radicals are bodies of their own (three Hangul syllables gave 7). Read the count from the `bb.text` line in Blender's `LOG` ("N glyph pieces, M separate bodies": M), in Python from the text solid's `decompose()` |

The **first part listed** for an object is its main part: its filament, plate and print
settings go on the object. Fusion: name the bodies exactly like the parts and export one
STL per body; `build.py record` groups them from `--params`.

## Checks on an object

Since 0.6.1, the build JSON contains `assembly_sha256`, a fingerprint of object membership,
roles and free-part clearances. `finalize.py` compares it with the current `_parts` before
reusing object checks. A missing or changed fingerprint requires a new build/record report;
STL freshness alone does not establish assembly freshness. Notes, `expect` (rechecked per
part), and filament choices do not invalidate this fingerprint.

Parts are validated one by one as always (D1, M1–M5, …). An object with several parts
gets, in `objects[]`:

| ID | Check | Kind | Note |
|---|---|---|---|
| D2 | The whole object fits the usable bed | hard | One rotation for the whole object; the 3MF writers place the parent, never a part alone. For an object with several parts, or any object of a job that uses several filaments, the usable bed is the intersection of every tool's area in `printers.json` (`value.tools`), as `bambu3mf.py` lays such jobs out: on an X2D / H2D both nozzles may have to reach it |
| P1, P2 | Bed contact and overhang of the union of the parts | soft | Needs manifold3d: shared faces vanish, so a label on a lid is no overhang. Without it P2 is UNVERIFIED |
| A1 | `fused` part shares faces with another part, no overlap | hard | FAIL when it floats (nearest part named with its gap) or overlaps (the slicer would clip the overlap by its own rules). Bodies exported separately rarely share a tessellation (a 48-segment pin in a 64-segment hole crosses it by a few hundredths of a mm³), so an overlap up to a 0.01 mm skin over the shared area counts as touching, and a gap up to 0.01 mm does too |
| A2 | `free` part keeps its clearance | hard | FAIL on contact or overlap with any other part, free or fused; WARN below the clearance (like F3). A print-in-place piece is one `free` part: two free parts that touch are two pieces fused together, and a `fused` colour part cannot sit on a free one (A1 counts fused partners only), so a moving piece is one colour for now |

The gate of the build is the worst of every part and every object. A part's own P1/P2
take its lowest face as the bed, so for a part that sits on another one read the object's
P1/P2, not the part's.

## Printing the mechanism first

When `strength.py` gives a short margin, or there is no proven reference to compare with,
print the risky member and the part it mates with before the full part:

```bash
python3 "$SKILL_DIR/scripts/build.py" run model.py --params .3dprint/params.json --out out/mech --only latch,keeper
```

`--only` builds the named `_parts` whole, in `_parts` order, and nothing else (into its own
`--out`, so the full build's manifests stay fresh). An empty list or an unknown name is an
error. An object built only in part is not judged as the whole: its `objects[]` entry gets
`partial` (`built`, `missing`, `total`), its D2 / P1 / P2 and the parts' A1 / A2 are
UNVERIFIED unless the built parts fail on their own (a D2 FAIL, two built parts that overlap),
its gate is INCOMPLETE, and it gets no core 3MF item (the subset would be dropped onto the
bed where the missing parts should carry it; place the test print in the slicer). A single
part built out of a larger object is the same: its own checks stand, its object is INCOMPLETE.
For a Bambu project, list the same parts in the `bambu3mf.py` job.

Whole parts can still be big. For "the minimum of the mating part" (the knuckles without
the lid, a slot without the box) add a coupon part to `_parts`, or keep a separate params
file with the coupon's sizes, and build that. A few grams, printed with the final filament
and preset; the user tries it and reports back (offer to record the result, `calibration.md`).
A snap is the exception to "a few grams": its click force scales with the width (`design.md`,
"Snap fits"), so its coupons keep the full width, cut short in the other directions, and step
the undercut, one coupon part per step. `fit_test.py` steps only the clearance of closed rings
and plugs; it cannot step an undercut.

A mechanism built into the walls (a box hinge, a latch formed on the lid) still gets a
coupon: the same section cut short, not the whole box. For a hinge, `parts.hinge` with the
real profile (`pin_d`, `knuckle_d`, `leaf_t`, `clearance`, `duty`; `clearance` is both the
radial clearance at the pin and the axial gap between knuckles, so `strength.py hinge` gets
it as `--gap` and `--clearance`), three knuckles of the real knuckle length b
(`length = 3·b + 2·clearance`, `knuckles=3`) and a few mm of each leaf (`leaf_w`), built as
its own `_parts` entry (`"hinge_coupon": {"expect": [...], "shells": 2}`) with
`build.py run --only hinge_coupon --out out/mech`. A three-knuckle coupon has one moving
knuckle that takes the whole pull, so it is a harder test than the full hinge (whose
moving knuckles share it): a coupon that holds is a hinge that holds. "Cutting it out would
be most of the part" is not a reason to skip it: a coupon is required for a `lid`-duty hinge
on top of its SF ≥ 2 (`design.md`, "Mechanisms that carry load") and the user's result sets
their own floors (`calibration.md`, `--kind lid_hinge`). A skipped coupon goes into
`_assumptions`.

## `build.py` output

One JSON document, schema `3dprint-scout.build/1`, also for `record` (this one is a `run`
with `--only`, so it shows `seconds` per part and a `partial` object):

```json
{"schema": "3dprint-scout.build/1", "ran": true, "engine": "python", "source": "adapter.py",
 "gate": "PASS | FAIL | INCOMPLETE", "R4": "PASS",
 "assembly_sha256": "<sha256 of the assembly inputs>",
 "parts": [{"name": "lid", "stl": "out/lid.stl", "seconds": 0.4, "artifact_sane": true, "object": "lid", "role": "fused",
            "rotation_deg": 0, "engine_warnings": [],
            "validate": {"schema": "3dprint-scout.validate/1", "gate": "PASS",
                         "files": [{"path": "out/lid.stl", "checks": {"D1": {"state": "PASS", "...": "..."}},
                                    "metrics": {"bbox_mm": [70, 45, 3], "volume_mm3": 9450, "...": "..."}}]},
            "assembly": {"object": "lid", "role": "fused", "checks": {"A1": {"state": "PASS", "...": "..."}}}}],
 "objects": [{"name": "lid", "parts": ["lid", "label"], "main": "lid", "gate": "PASS",
              "checks": {"D2": {"...": "..."}, "P1": {"...": "..."}, "P2": {"...": "..."}},
              "metrics": {"bbox_mm": [70, 45, 4], "volume_mm3": 9930, "shells": 1, "overhang_pct": 0.0, "...": "..."},
              "rotation_deg": 0, "method": "union of the parts (manifold3d) ..."},
             {"name": "box", "parts": ["latch", "keeper"], "main": "latch", "gate": "INCOMPLETE",
              "partial": {"object": "box", "built": ["latch", "keeper"], "missing": ["body"], "total": 3},
              "checks": {"D2": {"state": "UNVERIFIED", "note": "object built in part with --only ..."}, "...": "..."}}],
 "sources": ["adapter.py"], "threemf": "out/adapter.3mf", "seconds": 1.2,
 "warnings": ["..."], "errors": []}
```

- `parts[i].validate` is the full `validate.py` document for that part (`checks.md` shows
  its shape); the part's verdicts are at `parts[i].validate.files[0].checks`, its numbers
  at `...files[0].metrics`. `role` is `null` for a part alone in its object; `assembly`
  exists only for parts in a group.
- `objects[]` lists every object; a single-part object has only `name`, `parts`, `main`
  (plus `partial` and `gate` when it is one part of a larger object built with `--only`).
- `params` is the params file the engine got. A `--proxy` build (`references/measure.md`) carries
  `"proxy": true` and no `threemf`.
- `seconds` on a part is the engine's time for it (`run`); the top-level `seconds` is the
  whole command. `sha256` on a part is the STL its verdicts are about, and `validate_settings`
  the printer, printer id, tools and tolerances they were made with (and `printer_sha256`, the
  printers.json as it was): `finalize.py` re-checks with the same, and only trusts the object
  checks while every STL still has that hash, the settings and printers.json are unchanged,
  and `assembly_sha256` matches the current grouping, roles and free-part clearances.
- A `_parts` grouping that cannot be read (an unknown `role`, say) is in `errors` and makes the
  gate FAIL: the parts were validated, but no object check ran.
- `record` only: a part whose STL already has a manifest from `run` that describes this very
  file gets `prior_manifest` (`engine`, `sources`, `fresh`). A fresh one is kept as the record
  (its sources join `sources`); a stale one, or one none of whose generators is among
  `--source`, is not re-stamped and the part's R3 FAILs with the reason. A manifest an
  earlier `record` wrote is simply re-stamped.
- A broken STL has `artifact_sane: false` and `artifact_error`, no manifest and no
  `validate`; `R4` is then FAIL.
- `warnings` and `errors` repeat everything worth reading from every part and object
  (validator warnings, engine warnings, a Python generator's `UserWarning`s such as a font
  switch, rotation notes), and every hard FAIL of a part, an object or an assembly check is
  one line in `errors`, `<part> <check> FAIL: <note>`. Read those two lists first.

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
  is a bond between two outer walls, so keep it in a low-stress place. Confirmed in
  Bambu Studio 02.08.02.61 (2026-10-18, an inlay in a pocket): no inner wall with one
  filament, perimeters on both sides with two.
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
