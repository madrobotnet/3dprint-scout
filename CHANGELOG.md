# Changelog

## 0.2.0 — unreleased

- `references/design.md`: design for FDM printing with sources for every number — bed-edge
  chamfers, the 45° rule and self-supporting shapes, teardrop holes, bridges, walls in nozzle
  multiples, orientation for strength, cantilever snap fits (formula and strain limits), screw,
  insert, countersink and counterbore tables for M2–M8, print-in-place clearances, text sizes,
  seams, and the supports policy. `tolerances.md` gains a print-in-place row and sources.
- `scripts/parts.py`: tested part library for Python generators — rounded and chamfered boxes,
  a boolean-free bed-edge chamfer for any prismatic part, clearance / tap / insert /
  countersunk / counterbore holes, teardrop holes, standoffs, snap hooks with a strain check
  and their windows, a print-in-place hinge, text (matplotlib or fontTools), approximate ISO
  threads, and `clean()` for sliver triangles. `build.py` makes it importable from any generator
  and hashes it into the manifest.
- `scripts/sdf.py`: organic shapes as signed distance functions — primitives, height fields,
  extrusions and revolves, smooth union / subtract / intersect, offset and shell — meshed
  watertight with `to_manifold()` over manifold3d's `level_set`, with a cost estimate, crumb
  removal and the M1–M5 guarantees tested on the leaf-and-handle case that used to fail M3.
- `scripts/fit_test.py`: fit-test pieces (ring or plug) of a rectangle, rounded rectangle,
  circle or polygon profile in clearance steps, marked with 1/2/3 holes, with a JSON summary and
  an optional Bambu job.
- `scripts/fit.py`: the F3 check between two placed STLs — overlap volume, play along chosen
  directions, minimum gap, contact area, and a PASS / FAIL / WARN / UNVERIFIED verdict in the
  validate.py style. SKILL.md's checklist now names it for F3.
- `scripts/preview.py`: iso / front / right / top previews of one or more STLs from a numpy
  software renderer (no display, no fonts, no OpenGL), with the G4 blank-image check.
- SKILL.md: a concept step after the reference choice (two or three low-detail variants with
  previews, then a stop), preview.py in Phase 0 and 3, design.md in Phase 3 and 4, fit_test.py
  and fit.py in Phase 4 and 5.
- CI installs matplotlib as well, so the text tests run on Linux and Windows.

## 0.1.0 — 2026-10-16

First public release.

- Reference-first workflow in `SKILL.md`: four existing models with licenses, then reference, mix,
  original, or use as is; review stops after references and after the dimension table.
- Plain-words printer and slicer question with defaults; `printers.json` envelope for saved printers.
- Engine chosen by shape: Fusion (MCP) or OpenSCAD for mechanical parts, Python (manifold3d) for
  organic shapes and as the fallback.
- `validate.py`: size, bed fit at any rotation, watertightness, orientation, degenerate and
  duplicate faces, bodies, bed contact, overhang, wall thickness with bounded memory, and freshness
  of the evidence; always prints one JSON document.
- `build.py`: `detect`, `run` (OpenSCAD, Python) and `record` (parts built in Fusion), with
  manifests, per-part validation, and a core 3MF.
- `threemf.py`: slicer-neutral 3MF; parts that only fit rotated are placed rotated.
- `bambu_template.py`: an empty Bambu Studio project that names system presets, so Bambu Studio
  fills in the values from the user's installation.
- `bambu3mf.py`: Bambu Studio project 3MF with allowlisted per-object settings; owner metadata
  blanked; never overwrites.
- References for Fusion, OpenSCAD and Python, fit tolerances, and Bambu process settings.

Known limitations:

- On printers with a bed strip only one nozzle reaches (X2D, H2D), parts are laid out on the full
  bed, so a very wide part can land in that strip. Bambu Studio shows it; move the part or assign
  that nozzle.
- Not yet tested in the app: OrcaSlicer, and Bambu projects built from a template saved after
  slicing. The Fusion path (`build.py record`) has not yet been run on a real part.
