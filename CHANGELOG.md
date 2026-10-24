# Changelog

## 0.8.0 — 2026-10-24

The same skill, smaller and in one piece. Over 0.7.0 the guidance had grown to about 4,300
lines, and an agent on the Blender path read about 3,400 of them. About twenty rules stood in
two or more places, eight pairs of sentences disagreed, and the rules broken most often sat in
files the agents had read, beside sentences that said something else. 0.8.0 gives each rule one
home and moves rare material behind a "read only when" line. It also breaks `finalize.py`'s
longest functions into named pieces. Verdicts, reasons, CLI options and file formats are
unchanged: the build and finalize output was compared byte for byte with v0.7.0. The plan (in
Korean) is in `docs/plans/v0.8.0.md`.

- **Four rules decided** (#29). Each pair of sentences that disagreed now says one thing:
  - A prototype's `_assumptions` line must end in the user's reply, word for word, when the
    user agreed; otherwise the note is recommended.
  - The Phase 3 look stops in every attended run. A part with several bodies or a mechanism
    shows its shell alone first; a simple part may be shown with its features.
  - Elephant foot is corrected in one place, the slicer's compensation or a bottom chamfer.
    With the slicer's on, a chamfer is for looks only.
  - Staleness: `_` keys never make an STL stale, but a `_parts` or `_material` change needs a
    new build. A look goes stale when the image's bytes or a part's bytes change.
- **One home per rule** (#29). Each rule written in several places (agreement and prototypes,
  load-carrying members, promise states, evidence a rebuild makes stale, delivery and bundle,
  hole compensation, unattended runs, and more) keeps one home; the other places point to it.
  The latch floors in the P7 row and the duty table in Phase 4 stay quoted on purpose, checked
  by a test against `strength.DUTIES`.
- **Read only when it applies** (#29):
  - **New files:**
    - `design-mechanisms.md`: print-in-place joints and members that carry load;
    - `design-features.md`: snaps, screws, keyholes, text;
    - `outputs.md`: every script's JSON (now with `build.py`'s), how finalize judges evidence,
      and a worked `_verify`;
    - `phase-4-mechanisms.md`: sweep, standards, strength inputs, coupons;
    - `phase-6-files.md`: print-file findings, bundle internals;
    - `engines/blender-live.md`, `engines/python-sdf.md` and `engines/mixed.md`.
  - **Moved:** Bambu's handling of touching parts and its compensation defaults now live in
    `bambu-process.md`.
  - **Pointers kept:** section names that the scripts print, such as
    `design.md, "Mechanisms that carry load"` or `parts.md` for `build.py`'s JSON, still lead
    to a pointer.
  - **The result:** `SKILL.md` is 300 lines (was 363). The reading path, counted as the
    0.8.0 audit counted it, is 2,366 lines for Blender (was 3,433) and 2,238 for Python (was
    3,220). Counting `measure.md` and `materials.md` as read only when they apply, it is
    2,049 and 1,921; a mechanism adds about 200.
- **The most-broken rules at their step** (#29):
  - the unattended opening is item 0 of the delivery message, before any result;
  - a confirmed value that changes in Phase 4 is named and stopped for;
  - a part rebuilt since the user's look is shown again before delivery;
  - Phase 2 writes the compensation state into `printers.json`;
  - the default purpose is recorded.
- **What the guidance now says about a hand-guided use** (sliding a phone in): finalize
  verifies it on its fits alone, so the delivery says the fit was checked and the motion was
  not. Enforcing a test print would change behaviour, and 0.8.0 does not.
- **A sentence map** (`docs/plans/v0.8.0-guide-map.md`) lists every one of the 316 sentences
  that changed, with its new home. Two were dropped on purpose, both informational.
- **`finalize.py` in modules** (#28):
  - `finalize_common`, `finalize_geometry`, `finalize_evidence`, `finalize_promises`,
    `finalize_deliver` and `finalize_bundle`;
  - `finalize.py` keeps the CLI, `finalize()` and every name it exported;
  - the four longest functions are broken into named steps (the longest is 87 lines, was 252);
  - `build.py`'s `finish()` runs its steps as named functions.
- **Conversation scenarios, run again** (`docs/scenarios/results-v0.8.0.md`):
  - All nine match with Claude, and no must item that held in 0.7.0 fails. Two of the nine
    matched only on a re-run after the restatements above.
  - The kit grades the 0.8.0 decisions: a simple part's look with its features, and the
    prototype note.
- **Upgrading**: nothing to do. Projects, reports and commands from 0.7.0 work unchanged.
- **Known, for 0.8.x**:
  - Paths in the build JSON are absolute; they become relative to the project folder.
  - The agent's P4–P6 decisions have no record, so finalize keeps them "yours to decide".
  - A "you decide" to another question was once taken as the concept pick.
  - A hand-guided use verifies without a test print.
  - P3 gives a false positive at an acute bed edge.
- **Tests**: the same 441 tests, passing on Python 3.13 + bpy 5.2.2, 3.11 + bpy 4.5.14 and
  3.9, and in CI.

## 0.7.0 — 2026-10-23

Verification evidence tied to the design. 0.6 checked that each report was about the current
STLs, but what the user was promised in words was outside every check: in a demo phone stand,
features promised with the concept were missing from the model, a seat height was
hand-calculated without the corner round, and a cable passage rested on plug sizes nobody had
measured. In 0.7.0 the promises are declared, and `finalize.py` calls one `verified` only when
its evidence is of a kind allowed for it, tied to the current build by sha256, passed, and
resting on no unmeasured size. The plan (in Korean) and the Codex review it takes in are in
`docs/plans/`.

- **Promises and the `use` tier** (#18). `_verify.promises` lists what the user was told, each
  with a `kind`: `use` (something the user does with the object; needs `conditions` and
  `success`), `feature` (needs `success`) or `look`. Its `evidence` names declared joints,
  members, measurements, seen images or test prints, each with an optional `covers` line: a use
  takes joints, members, measurements and test prints, a feature joints, measurements and test
  prints, a look seen images and test prints. A part's own check (`box M1`) is never evidence.
  Each promise gets one state: error, failed, not verified, excluded, assumed, accepted or
  verified; an exclusion never hides a failure. `use` is a fifth tier, judged apart from the
  geometry: the worst state of its promises, or `not declared` with no list or an empty one. It
  leads the summary, and the promises that are not verified lead `open`. A fit report now
  counts only when it holds F3, and F3_sweep too for a joint marked `"sweep": true`.
- **Real-world sizes in `_verify.dims`** (#18, #19). Each size the design rests on (a plug, a
  phone in its case) is tied to the params.json values it sets, which must be equal, and names
  its source: `assumed`; `caliper`, with `"by": "user"`; `spec`, with a `url` and `where` each
  number is in it (listed for the person to check: finalize reads no spec); or `user-file`,
  each number backed by a fresh, passed measurement of the user's file within `tol` (otherwise
  the entry is `unbacked`). A promise rests on the sizes its evidence names, so one that passed
  on an assumed size is `assumed`, not verified. A proxy (the plug as a box) is built with
  `build.py run --proxy` from a params file of its own whose numbers must be exactly its dims;
  a recorded proxy, or one built from numbers no dims entry declares, is assumed, one built
  from other values is not verified, and a changed params file makes it stale.
- **Measurements as evidence** (#19). `measure.py info`, `slice` and `raymap` take
  `--expect PATH=VALUE` with `--tol`, or `PATH>=VALUE` / `PATH<=VALUE`, on a number of their
  own output; the report gains the file's sha256, each expectation and a gate.
  `_verify.measurements` lists the saved reports, each `missing`, `stale`, `failed` or
  `passed`. finalize runs a report's command again on its file and reads every value itself, so
  an edited report does not count. A size a hand calculation assumed (a lip top = seat + lip
  height) is checked on the built part this way.
- **Seen images and test prints tied to the design** (#20). `preview.py` and `render.py` write
  a sidecar next to each image (`<image>.png.json`): the image's sha256, views, language,
  renderer and every STL drawn with its sha256, taken before drawing. A `_verify.seen` entry is
  a person's judgement of an image: the digest they looked at, `by` user or agent, the promises
  judged and `passed` or `failed`. It stands while the image is still those bytes, its sidecar
  says so and every STL it shows is a part of this build now; only the user's judgement
  verifies a look. A test print that lists `promises` records each printed part's sha256 and
  material, the printer, `orientation`, `by` and the preset. It verifies only for the current
  parts in their current materials, on the build's printer, printed as built, reported passed
  by the user, under the delivered preset. A 0.6 entry without `promises` stays in the print
  tier. A test print may list the user's `photos`; they are no evidence.
- **Materials and the process preset** (#20, #21). params.json declares `_material` (a
  strength.py key such as `pla_basic`), `_parts.<name>.material` for a part that differs, and
  `_print.preset`, the slicer's process preset. The build JSON records each part's material; a
  material changed since the build is open (`material_drift`), and a linked strength report or
  a test print of that part does not verify.
- **Strength tied to the build** (#21). The build JSON records `parameters`,
  `{"scope": "merged" | "overrides", "values": {...}}`: `merged` for Blender and for a Python
  generator with a `DEFAULTS` dict (a params.json key the defaults lack gives a warning),
  `overrides` for Python without `DEFAULTS`, OpenSCAD and `record`.
  `strength.py --from-build out/build.json --part NAME --param INPUT=PARAM` takes sizes and
  choices from those values (a dotted path reaches a nested one) and the material from the
  part; every report says where each input came from (`inputs_from`: `param:`, `table:`,
  `build:material`, `default:` or `manual`). Only a linked report with nothing typed in is
  evidence of a use. It goes stale, by name, when the part's STL, a linked parameter ("h was
  ribbon_t = 4.5, now 5.0") or the material changes. A missing part or parameter, an input
  given twice, a value not valid for its input, or `--material` with `--from-build` is an error
  that names the cause.
- **The delivered print file's filament and preset** (#21). `bambu3mf.py` writes each part's
  filament slot and the template's filament preset for it, and the process preset, into the 3MF
  manifest. `finalize.py --deliver` compares each part's filament with its material: another
  material leaves the part's material-dependent evidence not verified; a filament finalize
  cannot name, or a part delivered only as STL or core 3MF, leaves it assumed. A process preset
  other than `_print.preset` keeps the part's test prints from verifying, and a project that
  names none leaves them assumed.
- **`render.py --lang ko`** draws the view names in Korean (Blender; checked on bpy 5.2.2 and
  4.5.14). `preview.py` keeps English: its 5x7 bitmap font has no Hangul (#20).
- **`finalize.py --bundle` carries every input of the verdict** (#22): the reports `_verify`
  names, the measured user files, each proxy's generator and params file, seen images with
  their sidecars, test-print photos and, with `--deliver`, every delivered STL and 3MF with its
  manifest. `REPRODUCE.md` rebuilds the parts and proxies with the build's own engine and
  settings and runs finalize with `--deliver` on the bundled delivery, for the same tiers,
  states and reasons. A missing file is listed in `bundle_missing`. A build that no longer
  matches the project (stale sources, changed settings, grouping or material, a part not
  built), a file outside the project folder and a carried text file holding a path of this
  machine refuse the bundle. The build JSON says `"command": "run" | "record"`, so a recorded
  Blender build is not rebuilt as a run.
- **Guidance in every phase** (#22). Phase 1 writes a concept's features as promises; Phase 2
  makes the use list with the user, asks for real objects to be measured (otherwise an
  `assumed` dims entry and an offered test print) and records the material and preset; Phase 3
  makes every number a check links to a parameter; Phase 4 links strength with `--from-build`,
  checks hand-calculated sizes with `measure.py --expect`, and ends when finalize names no
  declaration error, each promise that is not verified decided with the user; Phase 5 lists
  what a rebuild makes stale; Phase 6 runs finalize with `--deliver`, puts `--bundle` on the
  last run and opens the delivery message with the `use` tier, in plain words.
- **What counts as the user's agreement** (#24). Excluding a promise, accepting a WARN and, in
  an attended run, delivering a promise that is not verified as a prototype rest on the user's
  reply to a question that named it, said in plain words what taking it means and costs, and
  offered the choices; the reply is recorded word for word. A reply that hands the decision
  back, a look, a reference or concept choice, an earlier answer or silence is never agreement:
  the agent then decides, but never excludes or accepts. A look belongs to its image; a stale
  one needs a new image and a new look. Unattended runs never exclude or accept, and their
  delivery opens with what was decided alone. The prototype line
  `"<id>: delivered as a prototype, not verified"` may end with a note in parentheses saying
  who chose it.
- **Rebuilds write the same STL bytes** (#23). Evidence is tied to an STL's sha256, but Blender
  and OpenSCAD 2021.01 wrote the same triangles in another order on some runs, and Blender's
  `from_mesh` dissolved edges in the order of a Python `set` and so made different triangles: a
  rebuild with nothing changed could make the evidence stale. `build.py run` now rewrites every
  part STL into one canonical order (the 50-byte triangle records sorted, each kept whole; the
  header kept) before anything hashes it, for every engine, `--only` and `--proxy`; `record`
  never rewrites an STL. `blender_builder.py` takes edges and faces in mesh-index order. The
  core 3MF and the `.blend` still differ per build; no evidence is tied to them.
- **A Python build no longer lists the skill's own `assembly.py`** among its sources (#22):
  since 0.6, updating the skill made every Python build stale.
- **Conversation scenarios, run** (#25). `docs/scenarios/` (not shipped) is a kit for the nine
  conversation checks: the six of 0.6.1 plus A (a kept and a broken promise), A2 (a use on an
  unmeasured size) and C (a parameter changed after the strength calculation). Each has a file
  with the opening message, scripted replies and a grading checklist; `setup.py` writes each
  start state with the skill's own scripts, and `--check-docs` checks the files against
  `conversation-checks.md`. The expected behaviour moved out of the shipped
  `references/development.md`, so a run agent cannot read it. Claude ran all nine; the causes of
  the differences found were fixed (#23, #24) and the affected scenarios run again. Runs with
  Codex were deferred. The graded runs are in `docs/scenarios/results-v0.7.0.md` in the
  repository.
- **Upgrading**:
  - Build JSONs from before 0.7.0 have no `parameters`, `parts[].material` or `command`.
    finalize still judges the geometry from them, but `strength.py --from-build` refuses them
    (no material or parameters recorded), a linked strength report against one is stale ("built
    before 0.7.0: build again"), no material drift can be reported, and the bundle tells a run
    from a record by its engine and `engine_info`. Build again and save the new JSON.
  - Promises need `_verify.promises` with their evidence. A project from before 0.7.0 has none,
    so its `use` tier reads `not declared`; its geometry is judged as before.
  - A strength report is evidence of a use only when made with `--from-build` and nothing typed
    in. A 0.6 report (every input typed) still counts for the geometry, with a note, but leaves
    a use not verified.
  - `build.py run` now sorts every part STL's triangles, so the first rebuild after upgrading
    changes the sha256 of every part it builds (Blender, OpenSCAD and the Python engine alike),
    with the same triangles. Evidence tied to the old hashes goes stale once and must be made
    again: fit reports, and any measurements, seen images, test prints or `--from-build`
    strength reports made before the change. A delivery folder made before it is no longer the
    verified STLs under `--deliver`: deliver into a new folder. `record` leaves STLs as
    exported.
- **Known, for 0.7.x**:
  - A use that needs a path by hand (sliding a part in), or a promise whose success rests on a
    hand calculation (a tip-over angle), can read `verified` on a fit or measurements alone,
    without a test print. The guidance asks for a test print; finalize cannot tell such a use.
  - `validate.py` P3 reads thin where a sloped wall meets the bed at an acute angle: rays from
    the bottom face near that edge leave through the slope.
  - A verified promise the user takes as a prototype has no record: the prototype line applies
    only to a promise that is not verified.
  - The soft checks the agent decides (P4, P5, P6) have no place to be recorded; finalize keeps
    listing them as yours to decide.
  - A data file a generator opens itself (not an import or include) is tracked by neither R3
    nor the bundle; the guidance says to keep those numbers in the parameters.
  - A user's own Bambu filament preset that inherits a Bambu one is not traced to it: finalize
    cannot name its material, so the evidence that rests on it stays assumed.
  - `build.py` writes absolute STL paths in the build JSON.
  - A seen image that also draws a declared proxy (a phone on the stand) is not taken: the
    proxy's STL is not a part of the build, so the look reads stale.
- **Tests and reviews**: 345 → 441 tests (here on Python 3.13 + bpy 5.2.2; the PRs also ran
  Python 3.11 + bpy 4.5.14 and Python 3.9). `test_pipeline` runs build.py, strength.py
  `--from-build`, bambu3mf.py and finalize.py `--deliver` together; other new tests bundle a
  project made by the real scripts and run REPRODUCE.md inside it for the same verdict. Codex
  reviewed steps 1 to 4 until a round found nothing; the bundle (step 5) took seven Codex
  rounds and an auditor who tried to break it and reproduced 13 more problems, all fixed. The
  Codex reviews of #23 and #24 did not finish: those rest on their tests, an independent
  reproduction (#23) and a reviewer's check (#24).

## 0.6.1 — 2026-10-22

Verification fixes and development setup/workflow improvements are shipped together in this
release; the separately proposed 0.6.2 work is included here.

- **Assembly evidence follows the assembly contract.** Build reports carry `assembly_sha256`
  separately from the geometry hash. `finalize.py` refuses to reuse object checks after object
  membership, roles or free-part clearances change, even when the STL bytes are unchanged.
  Notes, filament choices and dimensions that finalize checks again do not unnecessarily
  invalidate assembly evidence. Reports from before 0.6.1 need a fresh build/record report;
  copying a fingerprint into an old report is not an upgrade. A build of only some of the
  parts (`--only`) is reported by the parts it left out, not as changed metadata.
- **Engine detection reports usable engines.** A failed or outdated `BLENDER_PYTHON` candidate
  no longer hides a supported bpy in the current interpreter. An explicit `--blender-python` is
  now binding (it used to fall through to the other candidates), in `detect` too: there it
  reports only that interpreter, so a usable binary no longer lists Blender as available for a
  build that would run without it (Codex review). Invalid probe output and
  subprocess failures remain visible. OpenSCAD must pass its version probe and export a
  readable cube before it appears in `available`; the default backend is tried when the
  Manifold backend is unsupported.
- **One hole-compensation decision table.** Slicer correction, model correction and unknown
  settings are separate states, decided by the settings the part will be printed with. Unknown
  no longer means "add model compensation" in one phase and "nominal plus fit clearance" in
  another. A Bambu Studio project the skill delivers carries its settings, so a generated
  template (system presets, both corrections off) stays `model`; `bambu-process.md` says the same.
- **Reuse confirmed answers and finish the existing-model path.** A missing printers.json
  does not trigger questions already answered in the request. Choice D hands off the original
  link, licence, download location and unverified items without entering the modeling phases.
  Unattended defaults require an explicit user request or host mode; silence is not approval.
- **Protect originals and delivered versions while allowing working updates.** Relevant
  generator and project-state edits are allowed within the requested work; unrelated content,
  user originals, files open in a slicer and delivered versions remain protected. Calibration
  records still need the user's agreement.
- **Reproducible setup and binary smoke coverage.** Three installation levels, a pinned
  Python/Blender combination and readiness commands live in `references/development.md`.
  The real-binary smoke path checks STL, editable .blend and rendered PNG outputs separately
  from bpy and emulated-binary tests. Existing latest-dependency compatibility jobs remain.
  The job's download step and `smoke_blender.py` ran once outside CI against the official
  Blender 4.5.14 linux-x64 archive (SHA256 checked): build, reopened `.blend` and PNG passed,
  and the full suite passed with that binary present (344 tests). The first CI run is the
  weekly job after merge; GitHub dispatches it only from the default branch.
- **Regression coverage:** assembly metadata drift and legacy reports; bpy fallback, strict
  explicit selection in `run` and `detect`, and invalid probe output; failed OpenSCAD readiness. Conversation
  walkthroughs cover complete input, choice D, unknown compensation, project updates and
  explicit unattended execution. Walkthroughs are not an agent benchmark.

## 0.6.0 — 2026-10-21

Two things: Blender becomes the first engine for every shape, and a PASS now comes with the
evidence behind it. Blender first followed a comparison build with new helpers; the final report,
the calibration matching and the reference coverage by direction follow an outside review of
0.5 (by GPT) that asked for "why this result can be trusted, and what was not checked" more than
for new features.

- **Rule A: Blender first** (the owner's decision after the comparison). With the helpers below,
  a C-clip and a card-slot block built in Blender with no hand-computed geometry measured the same
  as the Python engine: fit features within 0.002 mm, the same `fit.py` gap (0.2488 mm) and play,
  corner radii 0.999 mm (0.935 with 0.5's `bevel`), the lip round where the analytic tangent puts
  it. Blender builds take about a second longer. A part that needs a parts.py helper (thread,
  hinge, snap, countersink) when Blender's Python has no manifold3d is built with the Python
  engine; without Blender nothing changes.
- **Blender helpers**:
  - `bb.fillet(obj, radius, bb.edges(...))`: each edge's offset comes from its own angle, so a
    120° edge gets the radius asked as a 90° one does (within 1.5 % along the arc, Blender's
    profile). It refuses, before changing anything, a fillet along a curved face's facets
    (0.5's bevel failed 33 of 33 there), an edge sharper than 90° (Blender's profile is no
    circle there: +12 % at 60°, +75 % at 30°) and rounds that would meet on a flat face (its
    outline, holes included, inset by each round's reach must stay a proper outline: a hexagon's
    rim or a hole's rim passes, a hole nearer the side than the two reaches does not), and names
    the way out: the profile, or a smaller radius. A cut leaves its flat faces split along edges
    from a hole's rim; those at a rounded corner are turned onto the corner's miter first (the
    bevel ran along them: a slit from the rim to the far corner), so a hole's rim gets a true
    round, and never past another round's tangent line. After the bevel every result is checked
    for zero-area triangles, non-manifold edges and faces that cross each other or overlap in one
    plane (`bb.self_intersections`, which validate.py does not look for); any of them puts the
    object back as it was (its scale and place too) and raises. A mesh shared with a linked
    duplicate is copied first. Known limit: a face cut by many
    holes can still be refused there (a split edge passing near another hole); a hole's
    chamfer or round then belongs in the cut's own tool.
  - `bb.arc`, `bb.outline`, `bb.round_profile`: 2D profiles from lines and true arcs, corners
    rounded with a circle tangent to both edges, straight or arc (a C-ring lip, a ridge foot);
    `bb.prism(plane="XZ" | "YZ")` extrudes them in any direction. `bb.cone`.
  - `bb.from_manifold`, `bb.from_mesh`, `bb.import_stl`: parts.py's geometry or another engine's
    STL inside a Blender build; parts.py and an imported STL are hashed into the manifest;
    `detect` says whether Blender's Python has manifold3d.
  - `bb.apply_transform`, and `bed_chamfer` on the world bed (a part rotated into its print
    orientation).
  - Found on the way and fixed: a location or rotation set a moment before was not yet in
    `matrix_world` (Blender updates it when the scene is evaluated); an XZ prism came out inside
    out; a boolean with a triangulated tool left sliver triangles on flat faces (now turned into
    proper ones, and only corners closer than the weld distance merged, as the export does);
    split facets of a parts.py tool are merged back by flatness, not by angle (manifold3d's face
    groups when they are flat, otherwise grown while every corner stays within 0.05 um of the
    seed's plane), so a countersink 300 mm from the origin cuts cleanly and the facets of a
    gentle curve (r = 1000 mm) are never folded into one bent face.
- **`finalize.py`**, the final report (Phase 6): from the saved build JSON and the evidence
  declared in `params.json` `_verify` (joints with their fit reports, members with their
  `strength.py` reports, test prints, accepted WARNs, unverified dimensions, reference coverage),
  it validates every part again and reports four tiers that are never folded into one PASS:
  geometry verified or not, shape by direction, slicing unverified, print unverified, plus every
  open item. A list that is not declared keeps the geometry unverified; a fit report about other
  STLs, a stale one, or a delivered copy that differs from the verified STL is a reason too.
  It re-checks with the settings the build used (now in the build JSON with each STL's sha256),
  needs every `_parts` part built and a build without errors, and with `--deliver` checks every
  STL and 3MF in the delivery folder (a 3MF through the `<file>.3mf.manifest.json` that
  `build.py` and `bambu3mf.py` now write next to it; a malformed one is an open reason).
  `--bundle` writes the generator and its own files at their places in the project folder (so
  imports, includes and loaded files still resolve), parameters, printers.json, the report and
  `REPRODUCE.md`, and refuses a source outside the project folder or a file that holds a path
  of this machine (a whole folder, in any form: JSON-escaped, MSYS, any case; the report itself
  is scrubbed of every form). The build's object checks count only with the build's settings
  and printers.json (`settings_drift`; a value left at validate.py's default counts as that
  default). A D1 against an expect copied from the model stays open
  until the user accepts it as `<part> D1`.
- **A `_parts` grouping that cannot be read** (a role with a typo) made no object check run and
  still gave the build a PASS; it is now a FAIL.
- **Upgrading**: the build JSON now carries each STL's sha256 and the settings it was validated
  with (`validate_settings`, with `printer_sha256`). A build JSON saved before 0.6 has neither,
  and `finalize.py` reports it as not verified: build again and save the new JSON first.
- **References by direction** (#8): Phase 1 records which of the six directions the references
  show (real, estimated, assumed); `finalize.py` reports the shape as not verified from the rest.
- **Calibration under the same conditions**: `lookup` recommends only entries printed with the
  query's nozzle, layer, load, orientation and process (two new optional fields); the others are
  a `reference` list with what differs. `worked` no longer passes off values from different
  prints as one set: `worked_set` is one print's values, and `combined` warns when `worked` mixes
  prints. The documented lookup gives `--nozzle`.
- **Reviews**: an independent review of this release found five blockers, all in what could
  be called verified without being checked (a stale build JSON, a part never built, bed
  settings dropped on re-check, build errors ignored, two fillets that overlapped); each is
  fixed with a test that fails without the fix. Its re-check found the overlap check refusing
  valid rims (a cylinder's, a hole's, a hexagon's); the check was rebuilt on the flat face's
  inset outline. A third pass found rounds on a cut's face that crossed themselves while every
  mesh check passed, a weld that hid an overlap, a gentle curve folded flat, a round's end that
  met another round, and an object judged on one printer reported as verified for another; all
  are fixed or refused, with tests. Codex's review found the bundle flattening sources into one
  folder and a malformed 3MF manifest giving a traceback; both fixed. A fourth pass found a
  straightened corner that could leave a 0.08 mm ridge on a neighbouring round, flat overlaps
  the crossing check missed, and a linked duplicate changed along; fixed, with tests.
- **Tests**: 289 → 328, with Python 3.13 + Blender 5.2.2 and without Blender.

## 0.5.1 — 2026-10-21

Three checks could pass what they should not. An outside review of 0.5.0 (by GPT) found them by
reading the code; each was reproduced with a small model before the fix, each fix has a test
that fails on 0.5.0, and an independent review of the fixes found two more of the same kind.

- **F3 play follows the whole move.** `fit.py` judged a direction by its two ends: a ring held
  under a lip, moved 10 mm up, was past the lip at the end and reported free (F3 PASS). The move
  is now followed in steps no longer than the gap to the other part (nothing can meet sooner)
  or 0.2 mm, and the first overlap is narrowed by bisection; the ring stops at 1.0 mm.
- **F3_sweep decides only the travel it checked.**
  - A sweep that ends before `--sweep-travel` (0–10° when 30° is needed) was a PASS when
    nothing was hit; it is now UNVERIFIED, and so is a sweep that does not start at the placed
    pose, unless it hits inside the needed travel, which is a FAIL wherever it started.
  - A free sweep without `--sweep-travel` is UNVERIFIED instead of PASS: the travel the part
    needs decides, so give it (a stop without it stays a WARN).
  - `--sweep-travel` is a magnitude: `-40` for a clockwise sweep was always met (a false PASS
    with a stop at −16°); it now means 40.
  - The required travel is checked as an angle of its own (Codex on #11): a stop that starts
    just short of it, between two checks, passed when the next check landed past it. A hit at
    the required angle itself is a FAIL.
  - The turn between two steps is followed too, wherever the gaps at the steps do not cover it,
    until no point of the part moves more than 0.2 mm between two checked angles: a thin stop
    between steps is found (a 0.6 mm post at 5° passed with 10° steps). A part turning in
    contact is bounded: past 1000 such checks the sweep is UNVERIFIED, never PASS. The table
    keeps the steps and the two angles that bracket the stop; the report adds
    `reach_radius_mm` and `between_steps_checked`.
- **A2 fails two free parts that touch.** A free part's contact was checked against fused parts
  only, so two print-in-place parts face to face got a short-clearance WARN; any contact or
  overlap of a free part is now an A2 FAIL. `parts.md` says what that means for a moving piece
  in two colours (not supported yet).
- Tests that run a script with `python -I` (which ignores `PYTHONDONTWRITEBYTECODE`) pass `-B`
  too, so a test run with that variable set leaves no `__pycache__` in `scripts/`.
- The 0.5.0 entry below said 255 tests before it; there were 257.
- **Tests**: 284 → 289.

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
- **Tests**: 257 → 284, passing with Python 3.13 + Blender 5.2.2, Python 3.11 + Blender 4.5.14
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
