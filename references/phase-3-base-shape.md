# Phase 3 — Base shape (review point, not skippable)

Read this on entering Phase 3 (SKILL.md names the rules that hold at all times), together with
`references/engines/<engine>.md` (only the engine in use) and `references/design.md` (bed-edge
chamfers, overhangs, walls in nozzle multiples, orientation for strength, where to split parts).

## The generator script

Before any geometry, write down per part (one line each, in `_assumptions`): what it is, the
usual structure of that kind of object, what the references actually show, and what is still
uncertain. Build the usual structure first, then this product's proportions: a ring is a
closed loop even where a photo shows an ellipse, and colour patches or a projected outline in a
photo are never traced into a mesh.

Write one generator script:

- Every dimension in a `PARAMETERS` block at the top, in mm, with descriptive names (`screw_hole_d`,
  not `d1`) and a comment on its source.
- **Z-up: Z = 0 is the print bed.** Model in the orientation it will print in.
- Each build regenerates everything from scratch in a safe order (fillets before cuts). Phases are
  review points, not build steps.
- OpenSCAD: set `$fa = 1; $fs = 0.4;` so curved parts meet D1.
- **Split into parts** what has its own job or may get its own colour (latches, levers, labels,
  signs, inserts): separate bodies that touch the main body (shared faces, no union), seams in
  low-stress places; print-in-place pieces keep their clearance. Never ask the user about
  colours: split, give every part the main filament, say so at delivery (`references/parts.md`).
- **Members that carry load** (pins, knuckles, levers, links, hooks, latch bars) are sized by
  `references/design.md`, "Mechanisms that carry load", by their duty (`latch`, `lid`,
  `decorative`), not by P3's 1.2 mm, which is only what prints: list each with its section in
  the dimension table (P7), beside the reference member when one was measured, and run
  `strength.py` on it (Phase 4).
- **A mechanism never silently grows the object**: a hinge on a box goes into the dimension
  table with its knuckle Ø and how far it stands proud of the wall (gusset included), next to
  the box's depth, and into the concept preview; if its duty's floors would make the object
  bigger than the user's sizes, or it looks out of proportion, stop and give the choices in
  `references/design.md`, "Print-in-place joints" (the right duty, notched-in knuckles, another
  closure, a bigger object), never resize the object on your own.
- Design to the recommended values in `references/tolerances.md`, not to the minimums: a wall
  planned at exactly 1.2 mm can fail its own check through floating-point rounding.
- Guard derived dimensions with assertions (`assert(...)` in OpenSCAD, `raise` in Python) so an
  impossible parameter combination fails the build with a readable message.

## `.3dprint/params.json`

Keys starting with `_` are metadata and never reach the engine:

```json
{"_parts": {"box": {"expect": [71.2, 37.8, 33.6]}, "lid": {"expect": [71.2, 37.8, 26.6]},
            "label": {"expect": [40, 12, 1.6], "object": "lid", "role": "fused"}},
 "_assumptions": ["defaults taken in an unattended run, one line each"],
 "wall": 3.0, "slide": 0.2}
```

`expect` is the size from the dimension table (design intent), never a measured bounding box:
a copied value makes D1 circular, and `validate.py` flags one. Parts of one object share an
`object` name and a `role`: `fused` (must share faces with another part) or `free`
(print-in-place, keeps `clearance`); all parts of an object are modelled in the same frame, so
the STLs hold the assembled positions (`references/parts.md`, schema and checks).

## Build, preview, stop

This phase: outer shell, walls, floor. No holes, no fillets yet. Build and validate:

```bash
python3 "$SKILL_DIR/scripts/build.py" run model.scad --params .3dprint/params.json --out out \
  --printer .3dprint/printers.json --tools 0
```

`build.py run` builds every part in `_parts`, writes `<part>.stl.manifest.json`, writes a core 3MF
(parts of an object under one parent), validates each part against its own `expect`, and checks
every object with several parts as a whole (D2 against the area every nozzle reaches, P1, P2 on
the union, A1 / A2 per part). For Fusion, export one STL per part from Fusion and use
`build.py record` instead (`references/engines/fusion.md`; its JSON is described in
`build.py record --help` and `references/parts.md`). A Blender generator (first line
`# 3dprint-scout: engine=blender`, `references/engines/blender.md`) runs through the same
`build.py run` in the `blender` binary or the `bpy` module and leaves `out/<model>.blend` next to
the STLs; in a live Blender the script runs through the host's tool and `build.py record
--engine blender` takes its STLs. Render the built STLs with `preview.py`
(`references/phase-0-detect.md`, step 3; `render.py` when Blender is there) and look at it
yourself first, **one view at a time**, never the grid as one picture: would someone name the
object from this view; silhouette, main volumes, thickness, edge radii. A view the references
do not show stays unverified (say so; do not call it right), and passing sizes, mesh checks or
a triangle count say nothing about the shape. Then report size, volume and verdicts in two or
three lines with the image, and **stop for the user's look**. For
a part with several bodies or a mechanism (lever, latch, hinge) this stop is never skipped: a
fit-test piece comes after it, not instead of it.

- `out/` is the build's working folder: every build rewrites `out/<part>.stl`, its manifest,
  `out/<model>.3mf` and, with Blender, `out/<model>.blend`. Deliverables (Phase 6) are written
  elsewhere as new files.
- Pass `--printer .3dprint/printers.json` even before the printer is known: a missing file is a
  warning and leaves D2 UNVERIFIED (gate INCOMPLETE), not a FAIL. A malformed file or an unknown
  `--printer-id` is an error in the top-level `errors`.
- A 0-byte or truncated STL is reported in `errors` with `artifact_sane: false`; it gets no
  manifest and is left out of the 3MF (G4). The build's `warnings` and `errors` include every
  part's validator messages, so read those two lists first.
