# Changelog

## Unreleased

Driven by a field test on 2026-10-17: a tool-free adapter from the Bambu Lab X2D rear exhaust
housing to a 100 mm duct, designed in Fusion through MCP, fit-tested and printed on the X2D.

- **Parts grouped into objects.** `params.json` `_parts` entries can name an `object` and a
  `role`: `fused` (a separate body that shares faces with the main body, no boolean union, so a
  latch, lever or label is its own part in the slicer and can take another filament) or `free`
  (print-in-place, keeps its `clearance`). All parts of an object are modelled in one frame, so
  the STLs hold the assembled positions. `assembly.py` checks each object as a whole (D2, P1 and
  P2 on the union of its parts with manifold3d, so a label on a lid is no overhang) and each
  part's A1 (fused: shares faces, no overlap) or A2 (free: clearance; WARN below it). `build.py`
  reports per part and per object, and `build.py --help` / `record --help` now describe the JSON
  (`references/parts.md` has it in full). The rule, the seam placement and why: `design.md`
  ("Colour and function seams") and `parts.md`. The agent never asks about colours: it splits,
  gives every part the main filament and says at delivery which parts are separate and how to
  recolour one.
- **Grouped 3MF writers.** `threemf.py` writes parts of an object as mesh objects under one
  parent with identity component transforms; `bambu3mf.py` writes one Bambu object with
  several parts (one `object_N.model` per object, a component per part, per-part `extruder`,
  the main part's settings on the object, assembled positions kept), lays out objects instead
  of parts, takes `object` and `filament` from `params` when the job names it, and keeps the
  old flat job format. What Bambu Studio 02.08.02.61 does with touching parts, from its source:
  parts with the same filament and settings share one `PrintRegion` (`PrintApply.cpp`,
  `generate_print_object_regions`) and their slices are united per layer
  (`PrintObjectSlice.cpp`, `slices_to_regions`, `closing_ex`), so there is no inner wall between
  them; different filaments meet as two sets of perimeters. Not yet opened in the app.
- **Nozzle areas (X2D, H2D).** With `printer` in the job, `bambu3mf.py` lays objects out inside
  the intersection of the tools' reachable areas whenever an object has several parts or the
  job uses several filaments; otherwise the full bed, as before. `usable_area_reason` says
  which. This closes the known limitation of 0.1.0 for those jobs; a single-filament job of
  single-part objects can still land a very wide part in the strip.
- **Allowlist.** `support_interface_filament`, `support_filament` (a slot or 0 = the object's
  own, checked against the template's filament count), `support_top_z_distance` and
  `support_bottom_z_distance` (0–1 mm), from `PrintConfig.cpp` 02.08.02.61, with a tuning row for
  a PLA interface under a PETG part. Not yet checked in the app.
- **Templates.** When the user has Bambu Studio open, the agent first suggests saving an empty
  project (it keeps their process tweaks and AMS set); the generated template is the fallback.
  The Bambu Studio data folders are named from `GUI_App.cpp` / `PresetBundle.cpp`
  (`%APPDATA%\BambuStudio`, `~/Library/Application Support/BambuStudio`,
  `$XDG_CONFIG_HOME/BambuStudio`, profiles under `system`, presets under `user/<id>`).
- **Fusion kit.** `references/engines/fusion_builder.py`: a Builder to paste into Fusion MCP
  scripts: user parameters that drive the features through expressions, sketches with real
  circles and arcs, extrude / revolve, right-handed frames, join / cut that refuse a tool whose
  box does not touch the target and report leftover bodies, one STL per named body at High
  refinement, a JSON summary in mm. Derived from the Builder that ran in the field test; this
  cleaned version has not yet been run in Fusion (stub-based tests only). `fusion.md` has the
  field pitfalls (joins that leave the tool behind, left-handed `Matrix3D`, taper sign, a
  re-sent script running stale content, parameters created but not used, polyline circles), the
  transfer pattern (inline when short; a new path per version plus an md5 check before `exec`),
  the no-save rule (10-document cap) and body names matching `_parts`.
- **`measure.py`.** Measures a file the user supplies, numbers only: `info` lists the placed
  objects and parts of an STL or 3MF (core objects, Bambu components with transforms and names,
  units to mm) and extracts one STL per object; `slice` gives closed loops at levels along an
  axis with bounds, area, a circle fit and the corner radii of a rounded outline; `raymap`
  prints the depth of the first surface behind a wall on a grid of rays (windows, recesses).
  `references/measure.md`: the licence rule (an official file is "official file, measured",
  never copied; another maker's model is a secondary source) and the pattern for a small
  watertight proxy of the mating part.
- **`fit.py --sweep-axis / --sweep-pivot / --sweep-angles / --sweep-travel`.** Rotates part B
  about an axis through a pivot, step by step from its placed pose in one direction (`0:90:2`
  counter-clockwise, `-40:0:2` clockwise), and reports interference and gap per angle, the stop
  angle, the free travel before it and an `F3_sweep` verdict: PASS when nothing is hit or the
  part is free through `--sweep-travel`, FAIL when it hits before that travel, WARN when it hits
  and no travel was required.
- **Process fixes in SKILL.md.** Every user-facing line, progress notes included, in the user's
  language. In a disposable sandbox `pip install` of the listed libraries is fine and said in one
  line; on the user's machine ask first; never `apt`/`brew` for OpenSCAD in a sandbox. Reference
  research capped at about six page fetches for the four models. Bed and nozzle areas read from
  the user's installed slicer profiles first, then the manufacturer's page, then the slicer's
  public profiles at a matching tag, never a reseller page. A supplied file is measured, not
  copied. The Phase 3 base-shape stop is not skippable, least of all for multi-part or
  mechanism parts. `expect` comes from the dimension table, never from a measured box:
  `validate.py` flags an `expect` with four or more decimals that matches the mesh to 0.001 mm.
  Every delivery repeats unverified dimensions, `_assumptions` and open WARNs, and a skipped fit
  test is recorded as unconfirmed in `_assumptions` before delivery.
- `examples/latch-box`: a box whose lid carries a separate label part (colour) and a captive
  print-in-place slider latch, grouped into one object; its README shows the object checks, the
  fit check and the expected P2 warning for the latch's bridged underside.
- Tests: assembly, grouped writers, nozzle areas, the new allowlist keys, measure.py, the sweep,
  the Fusion Builder against an API stand-in, and the new example (183 tests).

Not yet tested in the app: a Bambu object with several parts, the support interface keys, the
v0.2.1 six-filament template fix, whether the slicing preview shows no inner wall between two
same-filament touching parts, and the cleaned Fusion Builder in Fusion.

## 0.2.1 — 2026-10-17

- Fix: `bambu_template.py` projects with more than one filament opened in Bambu Studio with
  filaments 2..n as project presets named after the file ("(part.3mf)", "1(part.3mf)", ...)
  instead of the named system presets. Bambu Studio's `Preset::normalize` resizes every
  per-filament vector, `filament_settings_id` included, to the length of `filament_diameter`
  before it matches presets, and the template did not write `filament_diameter`. It now writes
  each filament's nominal diameter (read through `inherits`, default 1.75). Found on an X2D
  with PETG Basic and five PLA Pure slots; a regression test mirrors the resize.
- `examples/`: four parts built with the skill's scripts: an AA battery box (OpenSCAD), a snap-fit
  box (`parts.py`), a leaf door handle (`sdf.py`) and fit-test rings (`fit_test.py`). Each has its
  source, parameters, preview images, fit-check results where parts mate, and the commands that
  rebuild it. `examples/place.py` moves a copy of an STL for side-by-side or assembled previews.
- `tests/test_examples.py` runs every example's README commands in CI and checks the results the
  READMEs state.
- README: an examples gallery; the status line no longer calls v0.2.0 unreleased.

## 0.2.0 — 2026-10-17

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
