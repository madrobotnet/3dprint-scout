# Parts, objects and the build report

Read this when a design has more than one body that prints as one object (a colour part,
a label, a lever, a print-in-place latch), or when a mechanism is printed first. How Bambu
Studio treats touching parts and lays out an object with parts: `references/bambu-process.md`.

Contents:

- [Why parts are split](#why-parts-are-split)
- [`_parts` schema (params.json)](#_parts-schema-paramsjson)
- [Checks on an object](#checks-on-an-object)
- [Printing the mechanism first](#printing-the-mechanism-first)
- [`build.py` output](#buildpy-output)

## Why parts are split

A region that has its own job or may get its own colour is a separate body that touches the
main body, never asked about, given the main filament and named at delivery; where to put the
seam and why: `design.md`, "Colour and function seams". A print-in-place moving part is a
separate part too, with its clearance kept (0.3 mm per side, `tolerances.md`), and it is never
merged with anything.

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
mkdir -p out/mech && python3 "$SKILL_DIR/scripts/build.py" run model.py \
  --params .3dprint/params.json --out out/mech --only latch,keeper \
  --printer .3dprint/printers.json > out/mech/build.json
```

`--only` builds the named `_parts` whole, in `_parts` order, and nothing else (into its own
`--out`, so the full build's manifests stay fresh). Its saved JSON holds the sha256 of each part
the user prints, which a test print records (`references/checks.md`, "Test prints"). An empty list
or an unknown name is an error. An object built only in part is not judged as the whole: its
`objects[]` entry gets `partial` (`built`, `missing`, `total`), its D2 / P1 / P2 and the parts'
A1 / A2 are UNVERIFIED unless the built parts fail on their own (a D2 FAIL, two built parts that
overlap), its gate is INCOMPLETE, and it gets no core 3MF item (the subset would be dropped onto
the bed where the missing parts should carry it; place the test print in the slicer). A single
part built out of a larger object is the same: its own checks stand, its object is INCOMPLETE. For
a Bambu project, list the same parts in the `bambu3mf.py` job.

Whole parts can still be big. For "the minimum of the mating part" (the knuckles without
the lid, a slot without the box) add a coupon part to `_parts`, or keep a separate params
file with the coupon's sizes, and build that. A few grams, printed with the final filament
and preset; the user tries it and reports back (offer to record the result, `calibration.md`).
A snap is the exception to "a few grams": its click force scales with the width (`design-features.md`,
"Snap fits"), so its coupons keep the full width, cut short in the other directions, and step
the undercut, one coupon part per step. `fit_test.py` steps only the clearance of closed rings
and plugs; it cannot step an undercut.

A mechanism built into the walls (a box hinge, a latch formed on the lid) still gets a coupon: the
same section cut short, not the whole box. For a hinge, `parts.hinge` with the real profile
(`pin_d`, `knuckle_d`, `leaf_t`, `clearance`, `duty`; `clearance` is both the radial clearance at
the pin and the axial gap between knuckles, so `strength.py hinge` gets it as `--gap` and
`--clearance`), three knuckles of the real knuckle length b (`length = 3·b + 2·clearance`,
`knuckles=3`) and a few mm of each leaf (`leaf_w`), built as its own `_parts` entry
(`"hinge_coupon": {"expect": [...], "shells": 2}`) with
`build.py run --only hinge_coupon --out out/mech`, its JSON saved as above. A coupon in `_parts`
is a part like any other: every full build makes it, and it is delivered with the rest. A
three-knuckle coupon has one moving knuckle that takes the whole pull, so it is a harder test than
the full hinge (whose moving knuckles share it): a coupon that holds is a hinge that holds.
"Cutting it out would be most of the part" is not a reason to skip it: a coupon is required for a
`lid`-duty hinge on top of its SF ≥ 2 (`design-mechanisms.md`, "Mechanisms that carry load") and the user's
result sets their own floors (`calibration.md`, `--kind lid_hinge`). A skipped coupon goes into
`_assumptions`.

## `build.py` output

In `references/outputs.md`, "`build.py` output".
