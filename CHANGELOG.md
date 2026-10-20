# Changelog

## 0.5.0 — 2026-10-21

Tested in the field and by scenario: the Blender paths ran on a real Windows install (Blender
5.2.2 LTS, the binary and the official Blender Lab MCP server), and five scenario runs used the
skill end to end (an organic pot, a snap clip, a mixed nameplate, a Gridfinity bin and a
Hangul keyring). What they found is fixed here, together with the first outside contribution
(#9, thanks @fivetaku) and workflow notes from #8.

- **Field test on Windows**: `detect` finds the binary in Program Files; build, rebuild into the
  same `out/` and render pass; no path of the machine in the STLs, manifests, 3MF or `.blend`.
  The official MCP server's GUI tool ran the documented loader in 0.17 s with the user's scene
  and window untouched. `blender.md` now says what that server needs: `result` instead of
  printed output (the loader hands back the `@@3DPS` line), a new empty `.blend` for its
  background tool (made with `bpy.data.libraries.write`, never the user's file),
  `BLENDER_PATH` for that tool on Windows and macOS, Allow Online Access for its bridge, and a
  harmless read before each live run. `detect` in a VM or container linked to the user's
  computer cannot see their Blender; the live tool can. `@@3DPS` says `mode: "live"` there.
- **Rule A** (the owner's decision after a comparison build): mechanical or prismatic parts go
  to Python (its part library) or OpenSCAD; Fusion only when the user wants editable CAD
  (slow through MCP); Blender builds a fit only when its fit features are booleans of
  primitives and every round sits on flat faces. Both engines measured the same (fit features
  within 0.002 mm, the same `fit.py` play), but Blender's bevel failed every round next to a
  curved, faceted face, and the mechanical helpers exist only in Python.
- **Renders in true colours**: colours go into Blender's scene-linear properties converted from
  sRGB, under a brighter studio light; Jade White was drawn (176, 178, 179) and Orange
  (177, 126, 74), now near-white just below the background and (243, 107, 46). Black is a dark
  grey whose edges show; the background is `preview.py`'s 246. Captions stay in their own
  tile, blind pockets darken, curved surfaces shade smooth, and the blank check counts the
  part only, per view (`fg_views`), so a blank view or grid fails.
- **Text**: `bb.text` and `parts.text` refuse a character the font cannot draw, naming it and
  its code point (a font without Hangul gave boxes or placeholder glyphs that passed every
  check). `parts.text` keeps its default font (DejaVu Sans, in `weight`) when it draws the
  text, else takes `parts.find_font(text)`'s choice with a warning in the build report (Noto
  Sans CJK for Korean and CJK); format characters such as a zero-width space are not missing. `shells` counts glyph pieces, not letters; height is the cap
  height of a Latin "H" (the em size without one) and the LOG gives the real box. Rules for
  fonts (licences, never a proprietary system font in a deliverable, `.ttc` size) and for
  two-colour text (inlay ≥ 1.0 mm for light on dark).
- **Fresh evidence**: `record` keeps the manifest `run` wrote for an STL and merges its sources;
  a stale one, or one built from a generator not among `--source`, fails R3 instead of being
  re-stamped (a manifest an earlier `record` wrote is re-stamped). R3 accepts a `--source`
  superset.
  Fit reports name their STLs (#9): `parts.a` and `parts.b` carry the STL's `sha256` and the
  manifest's `input_hash` when it records this very STL; `fit.py --check REPORT` prints
  `F3_fresh` (PASS, FAIL `STALE`, UNVERIFIED for an old report), and Phase 5 counts F3 only from
  a report that passes it.
- **Checks**: every hard FAIL of a part, an object or an assembly is a line in `errors`; A1
  checks every body of a multi-body fused part (a floating letter fails, a sealed void is no
  body); unmerged contacts of fused parts are no longer object overhang; `--only` on part of
  an object, one part or several, leaves its object INCOMPLETE and out of the 3MF; P2 reports `limit_deg` and `steepest_deg` (no
  `max_angle_deg`); P3's warning carries the measured wall. `bb.boolean` and `export_parts`
  refuse zero-area triangles with the cause, and the export welds on the validator's own grid;
  M1 points at M3 when they are the same defect.
- **Snaps, fits, standards**: `strength.py snap` (strain against the limit, the deflection force
  as the load, insertion and release forces); snap arms are exempt from the latch floors; a
  C-clip row, full-width snap coupons, hole compensation on bores, OpenSCAD idioms for mating,
  teardrop and countersunk holes (the head clearance built in, as in `parts.screw_hole`), `parts.screw_hole(head_d=, head_h=)` for a measured head,
  keyholes. Published standards and disagreeing sources, official sizes without a tolerance,
  a standard's counterpart as an F3 proxy, licences not shown, another maker's geometry
  library only with a permissive licence.
- **Workflow (#8)**: the 3-fix cap counts per phase and part and is never reset by going back;
  before any geometry, one line per part on what it is and what is uncertain; previews are
  judged one view at a time; symmetric shapes are built as a half and mirrored.
- **Smaller**: `--tools` explained once and no longer hard-coded in examples; a tuning row for
  parts that hold water; the X2D example's hole compensation corrected (its preset has it
  off); `bambu_template.py` and `bambu3mf.py` have `--help`, and `--colour` takes filament
  names; `fit_test.py --overwrite` (an earlier series' extra pieces are removed); no `__pycache__` in the project; Fusion files through a
  connected folder; P6 may be decided from the generator and its log; a Contributors section
  in the READMEs.
- **Tests**: 255 → 279, passing with Python 3.13 + Blender 5.2.2, Python 3.11 + Blender 4.5.14
  and without Blender or numpy. Not yet run: the official server's background tool with
  `BLENDER_PATH` set, and the binary path on macOS and Linux.

## 0.4.0 — 2026-10-20

Blender, used to the full when it is there. If the agent can reach Blender anywhere (an MCP
connector to the user's own Blender, a `blender` binary on the machine it runs on, or the `bpy`
module in some Python), the skill uses it for what the other engines lack on a freeform body:
real fillets, robust booleans, text in any font, renders. Blender 4.5 LTS or newer, on every
path (the Manifold boolean solver; the older Exact solver left unions of touching bodies open).
Without Blender nothing changes.

- **Detection** (`build.py detect`, Phase 0 file, SKILL.md Phase 0 line): a `blender` block with
  the binary (PATH, `BLENDER=`, the usual install folders on Windows, macOS and Linux, Steam,
  flatpak, snap, an unpacked archive in the home folder; version from `--version` with a
  timeout), the `bpy` module (probed in a subprocess with a timeout and from an empty folder,
  never imported into `detect`'s own process: it loads most of Blender), `manifold_boolean`
  and version notes (older than 4.5: listed, not used). A tool that runs Python in the user's
  Blender and answers a harmless read is the live path; a timeout gets one retry. `pip install
  bpy` is fine in a disposable sandbox, said in one line; on the user's machine ask.
- **Rule A** (SKILL.md, Phase 0 file): mechanical or prismatic → Fusion, OpenSCAD, Python as
  before, never Blender for a fit; organic, freeform, sculpted or decorative → Blender when it is
  there, else Python; mixed parts build the body in the CAD engine and the decorative part in
  Blender as its own `_parts` entry of the same object (`blender.md`, "Mixed parts": each engine
  with `--only`, then one `record` with both STLs and every source). The cost is said up
  front: Blender leaves an editable `.blend`, not a parametric CAD history.
- **The Blender engine** (`references/engines/blender.md`, `references/engines/blender_builder.py`).
  A generator is one script with a `PARAMETERS` block, first line `# 3dprint-scout:
  engine=blender` (a shebang may precede it), `import blender_builder as bb`, `build(p)` returning
  `{part: Object}`, and `bb.main(build, PARAMETERS)` at the end; rebuilt from scratch each run.
  Helpers: `new_scene_mm` (the `3dprint-scout` scene at 1 unit = 1 mm with its own world, next
  to whatever is open), `box` / `cylinder` / `prism` / `ring`, `bevel` (real fillets, segments
  from the line width, bed edges left alone, a result with zero-area faces refused instead of
  welded), `chamfer`, `bed_chamfer` (cut into the body, slightly steeper than 45° so P2 never
  counts it), `boolean` / `join` (Manifold solver, `solver="EXACT"` on request; both inputs and
  the result checked manifold; the solver reported), `text` (cap height, built-in font or a
  packed font file; each glyph welded on its own, touching glyphs unioned, letters that only
  kiss along an edge get the character spacing tightened by 1 % steps until the union is one
  closed body: "AA", "VV", "AARON" pass M1), `part` (one collection per object, made by the
  module and never a user's collection of the same name), `params_to_props` (custom properties
  on a `PARAMETERS` empty; a string that is an absolute path becomes its base name) and
  `check_props` (a path in any property stops the build before an STL is written),
  `export_parts` (one binary STL per part, modifiers applied, `global_scale` 1, scene unit off;
  a 10 mm cube is a 10 mm STL, tested), `save_blend` (the build scene's data-blocks only, no UI
  or preferences, compressed; fonts and images packed under their base names; refuses the open
  file's path, an existing path and any absolute path; an uncompressed twin is scanned for this
  machine's folders first and a hit leaves nothing behind), `render_views`. `build.py run
  --engine blender` (or the marker) runs the binary (`--background --factory-startup
  --python-exit-code 1 --python-expr <paths> --python gen.py -- --params … --out …`) or, without
  one, the Python that has `bpy` (`--blender-python`, `BLENDER_PYTHON`, the running Python); a
  binary older than 4.5 or one that does not answer is passed over for a usable `bpy` module, the
  same choice `detect` and `render.py` make. The `.blend` is the working copy in `out/`, rewritten
  on every build, and the build JSON gets `blend` and `engine_info.boolean_solver`. In a
  live Blender the same script runs through the host's tool (a loader that checks both files'
  md5, drops any stale helper and sets `sys.argv`) and `build.py record --engine blender` takes
  the STLs, hashing `blender_builder.py` with the generator. Validation is unchanged and
  authoritative: `validate.py` on the exported STLs, nothing Blender says about sizes is trusted.
- **Live-session safety**: the generator never resets, closes, saves over or discards the user's
  open file and never switches their window; it builds into its own scene, removes only what it
  tagged on an earlier run, writes only new files inside `--out` (the default `.blend` in `out/`
  is the one working copy it rewrites; `--blend` must be a new file inside `--out` and never the
  open file), packs only its own fonts (never `pack_all` on the user's data) and refuses to write
  a `.blend` if anything of the user's sits in the build scene or its collections. In an open
  GUI session the agent says first that a `3dprint-scout` scene is added and asks when the file
  has unsaved changes; the background tool is preferred. Generated scripts write only under
  `--out`, use no network and run no other program: the official MCP server runs code unguarded.
- **Renders** (`scripts/render.py`, Phase 0 / 1 / 6 files): STLs from any engine drawn by Blender's
  Workbench engine, headless, iso / front / right / top in the `preview.py` grid with a size
  caption, EEVEE (4.x `BLENDER_EEVEE_NEXT`, 5.x `BLENDER_EEVEE`) or Cycles on request, part
  colours from filament names: a small built-in table of approximate Bambu colours matched on
  whole names, `#rrggbb`, the palette otherwise; an unknown name gets neutral grey and a
  warning, checked before Blender starts, never a question; very dark colours are lifted for
  the preview (`drawn` beside `colour`). Same JSON and `sane` check as `preview.py` plus two: a
  render whose pixels nearly all differ from the background (a black or missing world) is not
  sane, and neither is one with a blank view; the check counts the rendered views without the
  caption and the grid lines (`fg_views`). `preview.py` stays the fallback and the G4 check. Concept previews and the delivery
  image may be these renders.
- **Delivery** (Phase 6 file): a Blender build's `.blend` goes next to the STLs and 3MF, never
  overwriting, with one line: the script is the source of truth, hand edits are fine, the next
  rebuild comes from the script. `*.blend` and `*.blend1` are ignored by git.
- **Example** `examples/blender-coaster`: a 74 mm scalloped coaster with a filleted rim, three
  grooves cut with the Manifold solver, a bed chamfer, and a medallion part carrying embossed
  text (gate PASS; one P3 warning on the letter strokes, explained in its README); preview and
  thumb rendered by Blender with the commands in the README; rebuilt by the tests when `bpy` is
  importable (4.5.14 and 5.2.2 here).
- **Docs**: `design.md` (fillets on freeform bodies through Blender's bevel; the built-in font's
  stroke width), READMEs (Blender as an optional engine, 4.5 LTS), SKILL.md file map and
  description ("builds in Fusion, OpenSCAD, Blender or Python"), still 300 lines. A text object
  left as its own part is one body per letter: union it onto a face or a plaque, or set `shells`.
- **Tests and CI**: detection with mocked subprocesses (search order, version parse, probe
  timeout and working folder, no Blender at all, the 4.5 gate), the exact binary and `bpy`
  command lines, the marker (shebang, BOM, the Python engine's refusal), a stand-in `blender`
  binary (build, a rebuild into the same `out/`, `--only`, timeout, failure, version gate, the
  fallback from an old binary to a usable `bpy` module), `render.py`'s refusals, colour warnings,
  the no-background verdict and the caption's pixel box; with `bpy`: the 10 mm cube, Manifold and the Exact
  branch, a bevelled and a chamfered body through `validate.py`, text with touching letters,
  parts → collections, parameters → properties, a path in a property, `save_blend` (overwrite
  refused, no UI in the file, no path of the machine, reload), the live session (the user's open
  file, their object and a same-named collection untouched; `--blend` guards), renders including
  a black background and a blank grid (captions and grid lines only), a real build and rebuild
  through the `bpy` path and through an emulated binary, and the example. Two CI jobs install `bpy` (4.5.14 on Python 3.11, 5.2.2 on 3.13); the other jobs
  keep skipping the Blender tests. `tests/test_fit.py` and `tests/test_parts.py` now skip
  cleanly without numpy / manifold3d instead of erroring. A real `blender` install and a Blender
  MCP server are still to be run.

## 0.3.1 — 2026-10-19

Driven by a test request with v0.3.0: an SD / microSD card case (43 × 16 mm footprint, PLA) with
a print-in-place lid hinge. The 0.3.0 mechanism minimums, taken from one comparison of
hand-operated latches, were applied to the lid hinge: Ø3.2 pin, Ø9.8 knuckles, 10.1 mm proud of
a 16.4 mm-deep box, and the box was enlarged to suit the hinge. `strength.py` had no model for
an integral pin in alternating knuckles and, run as a loose pin, called the hinge a FAIL (0.75)
where the real geometry has a safety factor of 4.4 in shear (this release's `hinge` case).

- **P7 rules split by duty** (`design.md`, "Mechanisms that carry load"; SKILL.md P7 row,
  Phase 3 and 4 files). `latch`: anything a hand pushes, pulls, pinches or snaps, or a lever
  amplifies: the field minimums stay (pin ≥ 3.2, wall ≥ 2.2, member ≥ 2.5 thick and ≥ 4 wide,
  knuckle ≥ 4 long), load = the matching hand force × the lever ratio. `lid`: a lid, door or
  flap hinge with alternating knuckles (3 or more required, odd recommended) and no lever
  between hand and pin: floors are only what prints (pin 2.0, wall and leaf 1.2, knuckle 2 mm,
  `tolerances.md`), the size comes from `strength.py hinge` reaching SF ≥ 2 under
  `finger_pull` shared by the moving knuckles, no lever ratio (at WARN grow the pin, the
  knuckle Ø or the count), and a hinge coupon print is required on top of that margin before
  the full part, never instead of it (a skipped one goes into `_assumptions`). Levering a lid
  past its stop is misuse the hinge is not sized for: "don't force the lid past fully open"
  goes into `_assumptions` and is said at delivery (Phase 6). `decorative`: carries nothing,
  the same floors, no calculation. One copy of the numbers in `strength.DUTIES` (`strength.py
  duties`); `parts.hinge(duty=...)`, with `duty` keyword-only, loads it from the sibling file
  under a private module name (a project's own `strength.py` cannot shadow it), keeps
  `decorative=True` as the old spelling of `duty="decorative"`, refuses it with another
  explicit duty, refuses a lid hinge with fewer than 3 knuckles, and keeps the latch values as
  its defaults. The `parts.py` table in `engines/python.md` now lists every call's arguments in
  their real order (`hinge`, `standoff`, `snap_hook`, `snap_fit_check`, `text` were off), and a
  test keeps it so.
- **`strength.py hinge`.** The hinge as `parts.hinge` builds it: k knuckles alternating A, B,
  A …, knuckle length from `--length` or `--knuckle-len`, `--gap`, `--clearance`, `--hole
  teardrop | round`, `--pin integral | loose`. The moving knuckles share the load equally; an
  interior knuckle on an integral pin is a fixed-fixed span L = b + 2g with the load spread over
  b, end moment P (6g² + 6gb + b²) / (12 L) (the mean of the simply supported moment diagram;
  P b / 12 at g = 0, P L / 8 as b → 0) and two shear planes; an end knuckle (even count) a
  stub, warned; a loose pin the clevis of the pin case, with the fixed knuckles' walls checked
  too (an end knuckle's overhang puts 1.5 P on the last fixed knuckle). Bearing and tear-out of
  the knuckle wall above the hole. The axis prints flat and the pull turns with the lid, so the
  load is taken to cross the layers: shear, bearing and tear-out use the Z tensile strength,
  bending the strength of `--orientation`. `--duty` adds a `minimums` block (a floor not met
  fails the gate; `lid` also needs 3 or more knuckles and `--sf` ≥ 2; `decorative` reports
  the checks as informational). The field case, Ø2.4 in Ø7.4 knuckles, five over 36 mm, 98 N,
  PLA Basic: shear 2.49, bending 3.10, wall bearing 10.6, tear-out 8.1; Ø3.2 in Ø9.8: shear
  4.43, bending 7.36, bearing 14.1, tear-out 11.3 (`materials.md`, "The hinge model"; the
  numbers are asserted in the tests).
- **The mechanism must not silently grow the object** (`design.md`, "Print-in-place joints";
  Phase 3): a hinge on a box goes into the dimension table with its knuckle Ø and how far it
  stands proud, next to the box's depth, and into the concept preview; when a duty's floors
  would make the object bigger than the user's sizes, or the mechanism looks out of proportion,
  the agent stops and offers the choices (the right duty, knuckles notched into the walls,
  another closure, a bigger object) instead of resizing.
- **Process fixes from the same run.** Changing the engine after Phase 0 (Fusion → Python) is
  said in one line with the reason before building and recorded in `_assumptions` (SKILL.md
  G9, which holds in every phase; Phase 0 file). Bed sizes: never a review or a news article
  either (Phase 2). A mechanism built into the walls still gets a coupon, the same section cut
  short as its own `_parts` entry;
  "cutting it out would be most of the part" is not a reason to skip (Phase 4, `parts.md`).
- **Calibration log by kind of member.** `calibration.py add --kind latch | lid_hinge | lever |
  clamp | snap` (a short lowercase id, optional, through the same identifier checks); `lookup
  --kind K` takes `worked` and `bounds` from entries of that kind only and lists entries
  without a kind under `unclassified` (a reserved name; the note says how to classify one: ask
  the user and `add` it again with `--kind`), so a stub pin that broke in a latch does not set
  the floor for a lid hinge's integral pin; `kinds` counts what the log holds. Old files
  without `kind` load unchanged. Note: 0.3.0's `calibration.py` does not know `kind` and drops
  it from every entry when it rewrites a 0.3.1 file, so keep the versions in step. The example
  entries in `calibration.md` carry `--kind latch`.

## 0.3.0 — 2026-10-18

Driven by a field test on 2026-10-17: a tool-free adapter from the Bambu Lab X2D rear exhaust
housing to a 100 mm duct, designed in Fusion through MCP, fit-tested and printed on the X2D.

- **SKILL.md split into a router and phase files.** SKILL.md (under 300 lines) keeps what holds
  at all times: the ground rules, the always-on rules (no model downloads or copied geometry,
  never ask about colours, never overwrite, no identifiers stored, nothing executable in a 3MF,
  no modelled supports), a skeleton per phase with its stop and its must-do rules, the full
  checklist and gate, the unattended rules and the file map. The how-to of each phase moved
  unchanged to `references/phase-0-detect.md` … `phase-6-deliver.md` (the `printers.json`
  schema and defaults in the Phase 2 file), `validate.py`'s JSON to `references/checks.md`.
  Every reference file is linked from SKILL.md with when to read it, one level deep, and the
  ones over 100 lines start with a table of contents.
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
  them; different filaments meet as two sets of perimeters. Confirmed in Bambu Studio
  02.08.02.61 on 2026-10-18 with sample projects.
- **Nozzle areas (X2D, H2D).** With `printer` in the job, `bambu3mf.py` lays objects out inside
  the intersection of the tools' reachable areas whenever an object has several parts or the
  job uses several filaments; otherwise the full bed, as before. `usable_area_reason` says
  which. This closes the known limitation of 0.1.0 for those jobs; a single-filament job of
  single-part objects can still land a very wide part in the strip.
- **Allowlist.** `support_interface_filament`, `support_filament` (a slot or 0 = the object's
  own, checked against the template's filament count), `support_top_z_distance` and
  `support_bottom_z_distance` (0–1 mm), from `PrintConfig.cpp` 02.08.02.61, with a tuning row for
  a PLA interface under a PETG part. Confirmed in the app: the values show in the object's
  settings.
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
- **Mechanism minimums** (`design.md`, "Mechanisms that carry load"; checklist P7). The field
  test's adapter was printed and its print-in-place draw latches broke on first use: Ø2.6 stub
  pins in ~2 mm plates, 1.3 mm of knuckle wall, 1.2 mm link arms, every member at the P3
  printability minimum. A working print-in-place latch from an earlier project (one Ø3.2
  through pin in 4.25 mm rails, ≥ 2.2 mm of wall around the hole, 2.5 mm at the thinnest
  member, about 6× the material) gives the starting points: pin ≥ 3.2 mm, pin wall ≥ 2.2 mm,
  load-carrying members ≥ 2.5 mm in the bending direction and ≥ 4 mm wide, one through pin
  supported at both ends, 0.3–0.35 mm radial clearance. Both latches were PLA. These are a
  one-pair field comparison, not a standard. `parts.hinge()` now defaults to them (pin 3.2, knuckle 9.8 so that 2.2 mm
  remain above the teardrop hole's point, leaf 2.6) and refuses thinner values unless
  `decorative=True`; `examples/latch-box` thickens its bar, rail lips and lug ceiling
  accordingly (it has no pin holes).
- **Judging load-carrying members without new field data.** Three steps in SKILL.md (P7):
  compare the member with the corresponding one of a proven reference when its file is at
  hand (measured with `measure.py`, the user's own working project or a supplied file, never a
  download); run `scripts/strength.py` (pin in single or double shear, peak 4/3 of the mean,
  and bending as a stub from its root face with the print-in-place gap, `--gap`, or as a loose
  clevis pin with the support thickness, `--support-t`; beam or lever bending and deflection;
  link in tension with the bending a bow adds; bearing and tear-out of a pin wall; standard
  library; materials from Bambu Lab's technical data sheets for PLA Basic, PLA Matte, PLA
  Pure, PETG Basic, PETG HF, ABS and ASA with X-Y and Z values, loads from a cited hand-force
  study, safety factor 2 with its rationale, every assumption printed; `references/materials.md`);
  and when the margin is short or there is no reference, print the mechanism alone first
  (`build.py run --only latch,keeper` builds those parts whole; a coupon part for less).
  Honest result of running the field comparison through the calculation, inputs stated
  (finger push 70.6 N shared by the failed latch's two arms and two pins, 35.3 N each; the
  arm's 2.5 mm bow and the bar's 12 mm length from its generator; root gaps as the radial
  clearances; the lever ratio of either latch not measured, so the hand force applied 1:1):
  it flags the failed latch's curved 1.2 mm arms (factor 0.42; 0.21 for one arm alone) and its
  bar (0.11 as a cantilever, 0.44 as a span), while its Ø2.6 stub pins (bending 2.6, shear 3.4;
  2.0, WARN, when the load crosses the layers) and 1.3 mm pin walls (4.4) pass on paper and
  broke anyway. A lever ratio of 2 alone would make the pins WARN, 3 FAIL; impact at
  snap-over and corners are not in a static hand calculation either. So the minimums in
  `design.md` stay the primary rule.
- **Calibration log.** `scripts/calibration.py` keeps the user's own results in the project's
  `.3dprint/calibration.json` (never in the skill): fit-test outcomes, measured clearances and
  holes, mechanism members that held or broke with their load; schema-checked, finite numbers
  under 10 000 only; what the script can recognise as identifying a person or a machine is
  refused (field names with id, code, device, serial, account and the like; IPv4, IPv6 and MAC
  addresses, e-mails, long digit runs and letter-digit tokens in notes; printers and materials
  that are not short lowercase ids), which reduces the risk without guaranteeing it, so the
  agent never writes a name. `lookup` keeps the newest value that worked apart from the
  failed, tight and loose bounds. Read in Phase 2 (for how this printer prints, a value there
  beats every starting point; the object's size still comes from the user's caliper or the
  official spec); written only after the user says yes to one offer, never in an unattended
  run (`references/calibration.md`).
- `examples/latch-box`: a box whose lid carries a separate label part (colour) and a captive
  print-in-place slider latch, grouped into one object; its README shows the object checks, the
  fit check and the expected P2 warning for the latch's bridged underside.
- **G9, no long silences.** In the field test the agent modelled and checked the fit-test frame
  for up to about 48 minutes and ~70 tool calls without showing anything, and the too-thin latch
  was only found after printing. SKILL.md now asks for a short update (latest preview, what
  changed, what is next) at least every ~20 tool calls or ~15 minutes, and for a mechanism's
  preview before more checks are built on it. The numbers are starting values.
- Tests: assembly, grouped writers, nozzle areas, the new allowlist keys, measure.py, the sweep,
  the Fusion Builder against an API stand-in, strength.py (formulas and the field
  comparison), calibration.py and the new example (200 tests).

Checked in Bambu Studio 02.08.02.61 on 2026-10-18 with five sample projects: a Bambu object with
several parts (named parts at their assembled positions, filament per part, placed inside the
area both X2D nozzles reach), the support interface keys, the v0.2.1 six-filament fix (all six
slots on system presets), and no inner wall between same-filament touching parts (walls on both
sides with two filaments). Not yet run in Fusion: the cleaned Builder.

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
