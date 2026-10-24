# Phase 3 — Base shape (review point, not skippable)

Read this on entering Phase 3, with `references/engines/<engine>.md` (the engine in use) and
`references/design.md`. A mixed object (a CAD body with a Blender part) needs both engine files
and `references/engines/mixed.md`.

## The generator script

Before any geometry, write down per part (one line each, in `_assumptions`): what it is, the
usual structure of that kind of object, what the references actually show, and what is still
uncertain. Build the usual structure first, then this product's proportions: a ring is a
closed loop even where a photo shows an ellipse, and colour patches or a projected outline in a
photo are never traced into a mesh.

Write one generator script:

- Every dimension in a parameter block at the top (`DEFAULTS` in Python, `PARAMETERS` in
  Blender, the top-level variables in OpenSCAD), in mm, with descriptive names (`screw_hole_d`,
  not `d1`) and a comment on its source. A cutter's overshoot past a face (0.01–0.1 mm) is
  construction, not a dimension: it may stay a literal under R1, though a named `eps` is clearer.
- **Every number a later check links to is a parameter**, not a literal and not a value worked
  out inside the generator: each size of a member `strength.py` will check (`ribbon_t`,
  `ribbon_w`, `ribbon_len`), each choice it takes as a string (`"ribbon_support": "cantilever"`;
  orientation, duty, pin, shear, hole), each flag it takes as `true` or `false`
  (`"snap_repeated": true` for a snap opened often, `"pin_across_layers": true` for
  `load_across_layers`), a safety factor other than strength.py's 2
  (`"ribbon_sf": 3.0` for a member loaded at every use), a load a lever amplifies
  (`"latch_load": 141.2`, N), and every real-world size of a `dims` entry (Phase 2).
  `strength.py --from-build` reads them from the build JSON's `parameters`: a Python
  generator's defaults are recorded only from a dict named `DEFAULTS` (scope `merged`); OpenSCAD,
  Fusion and a live Blender record only params.json (scope `overrides`), so put the values there
  (`references/outputs.md`, `references/engines/python.md`). A derived value (the lip top = seat +
  lip height) is not recorded: check it with a measurement in Phase 4.
- Read no data file of your own from the generator (a JSON or CSV of sizes, an SVG outline):
  the build hashes the generator and what it imports (Python modules, OpenSCAD includes, the
  Blender library), not files it opens, so a changed data file would not make the build stale
  and the source bundle would rebuild without it. Put those numbers in the parameter block or
  params.json; a shape from a file the user gave is measured (`measure.py`), not loaded.
  Another maker's geometry library only with a permissive licence, its attribution and a note
  to the user.
- **Z-up: Z = 0 is the print bed.** Model in the orientation it will print in.
- Each build regenerates everything from scratch in a safe order (fillets before cuts). Phases are
  review points, not build steps.
- OpenSCAD: set `$fa = 1; $fs = 0.4;` so curved parts meet D1.
- **Split into parts** what has its own job or may get its own colour (latches, levers, labels,
  signs, inserts): where the seam goes, `references/design.md`; the `_parts` entries,
  `references/parts.md`.
- **Members that carry load** (pins, knuckles, levers, links, hooks, latch bars) are sized by
  their duty, not by P3's 1.2 mm, and listed with their section in the dimension table (P7);
  **a mechanism never silently grows the object**: both in `references/design-mechanisms.md`.
- Design to the recommended values in `references/tolerances.md`, not to the minimums: a wall
  planned at exactly 1.2 mm can fail its own check through floating-point rounding.
- Guard derived dimensions with assertions (`assert(...)` in OpenSCAD, `raise` in Python) so an
  impossible parameter combination fails the build with a readable message.

## `.3dprint/params.json`

This is working project state: update relevant keys during the requested design, keeping the
user's unrelated values. The same applies to the current generator and printer settings.
Do not apply this exception to user-supplied originals, already delivered versions, files open
in the slicer, or calibration records that the user has not agreed to save.

Keys starting with `_` are metadata and never reach the engine:

```json
{"_material": "pla_basic",
 "_parts": {"box": {"expect": [71.2, 37.8, 33.6]}, "lid": {"expect": [71.2, 37.8, 26.6]},
            "label": {"expect": [40, 12, 1.6], "object": "lid", "role": "fused"}},
 "_assumptions": ["defaults taken in an unattended run, one line each"],
 "wall": 3.0, "slide": 0.2}
```

`expect` is the size from the dimension table (design intent), never a measured bounding box:
a copied value makes D1 circular, and `validate.py` flags one. Parts of one object share an
`object` name and a `role`: `fused` (must share faces with another part) or `free`
(print-in-place, keeps `clearance`); all parts of an object are modelled in the same frame, so
the STLs hold the assembled positions (`references/parts.md`, schema and checks).

Set the material before the first build: `_material` is Phase 2's key (`pla_basic` when the
user named none, in `_assumptions`), and `_parts.<name>.material` a part printed in another
one. The build records each part's material; `strength.py` and the test prints are judged in it
(Phase 4). The values of every `dims` entry (Phase 2) are written in
params.json itself, even when the generator's defaults hold the same numbers: finalize compares
the two.

Changing `object`, `role`, group membership or a free part's `clearance` requires a new build
report, even if no triangle changed. Since 0.6.1 the report's `assembly_sha256` records these
validation inputs separately from the geometry hash.

## Build, preview, stop

This phase: outer shell, walls, floor. For a part with several bodies or a mechanism, the user
looks at the shell alone first, before holes, fillets and joints: a generator rebuilt from
scratch may already build them, so give it a parameter that leaves them off for this look. A
simple part (one body, no mechanism) may be shown as built, features included. Build and
validate:

```bash
mkdir -p out && python3 "$SKILL_DIR/scripts/build.py" run model.scad --params .3dprint/params.json \
  --out out --printer .3dprint/printers.json > out/build.json
```

(`--tools`, the nozzles the print uses: `references/phase-2-printer-dimensions.md`, step 1.)
Keep the JSON of the latest full build in `out/build.json`: `strength.py --from-build` and
`finalize.py` read it from Phase 4 on.

`build.py run` builds every part in `_parts`, writes `<part>.stl.manifest.json`, writes a core 3MF
(parts of an object under one parent), validates each part against its own `expect`, and checks
every object with several parts as a whole (D2 against the area every nozzle reaches, P1, P2 on
the union, A1 / A2 per part). A Blender generator runs through the same `build.py run` and leaves
`out/<model>.blend`; Fusion, a live Blender and a mixed object hand their STLs to `build.py
record` instead, as their engine file says.
The build JSON records `parameters` (what the parts were built with, and its `scope`) and each
part's `material` (`references/outputs.md`). A warning that a params.json key is not in the
generator's `DEFAULTS` (or `PARAMETERS`) is a misspelt name that built with the default: fix it.
Render the built STLs with `preview.py`
(`references/phase-0-detect.md`, step 3; `render.py` when Blender is there) and look at it
yourself first, **one view at a time**, never the grid as one picture: would someone name the
object from this view; silhouette, main volumes, thickness, edge radii. A view the references
do not show stays unverified (say so; do not call it right), and passing sizes, mesh checks or
a triangle count say nothing about the shape. Then report size, volume and verdicts in two or
three lines with the image, and **stop for the user's look**, in every attended run: a
fit-test piece comes after it, not instead of it. Unattended: SKILL.md's rule; still make and
inspect the preview, and never call an unreviewed shape approved.

**Record the user's look.** When the user looks at the image and says a `look` promise (Phase
1) is right or wrong, add it to `_verify.seen`: the image, the `image_sha256` from its sidecar
(`out/preview.png.json`, written by `preview.py` and `render.py`), `"by": "user"`, the promises
judged and the result:

```json
{"name": "back wave", "image": "out/preview.png", "by": "user", "promises": ["wave-back"],
 "result": "passed", "image_sha256": "83fd97b2d288a3114da16be54a781ce0a05f1ade7549bcb5894caa2a83b6073f"}
```

Only the user's look verifies; yours is `"by": "agent"` and never does, so an unattended run has
none. An approval of the shell judges only the promises the image shows. The entry goes stale
when the image changes or a part it shows is rebuilt to different bytes (a rebuild that changed
nothing keeps it; `references/outputs.md`): show the new image at the next stop and record the
user's new look; never copy an old judgement onto a new image.

- `out/` is the build's working folder: every build rewrites its STLs, manifests, the core 3MF
  with its `.3mf.manifest.json` (which `finalize.py --deliver` reads) and the `.blend`.
  Deliverables (Phase 6) are written elsewhere as new files.
- Pass `--printer .3dprint/printers.json` even before the printer is known: a missing file is a
  warning and leaves D2 UNVERIFIED (gate INCOMPLETE), not a FAIL. A malformed file or an unknown
  `--printer-id` is an error in the top-level `errors`.
- A 0-byte or truncated STL is reported in `errors` with `artifact_sane: false`; it gets no
  manifest and is left out of the 3MF (G4). The build's `warnings` and `errors` include every
  part's validator messages, so read those two lists first.
