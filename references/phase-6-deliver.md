# Phase 6 — Deliver

Read this on entering Phase 6 (SKILL.md names the rules that hold at all times).

Choice D in Phase 1 ends with the original-model handoff; this phase and finalize.py apply only
to parts built or recorded by this workflow.

Deliverables are new files outside `out/` (for example `deliver/<date>/`): copy the final STLs and
3MF there, or point `bambu3mf.py` there. Never write into a file the slicer has open, and never
overwrite an existing delivery path: choose a new version folder, or ask and stop if replacing
that particular path is necessary (the scripts refuse overwrites as well). Updating the current
project's working state is allowed under SKILL.md's file-protection rule. The verdicts
come from `out/` before the copy, where the build's manifests are; copy `<part>.stl.manifest.json`
along only when the copy is to be re-checked (without it R3 reads UNVERIFIED).

**First, the final report.** Run it before the delivery message, and again after every fix, always
with `--deliver` on the delivery folder. Add `--bundle` only to the last run, the one the message
reports, into a new folder: it refuses a folder that exists, so a re-check never takes it. The
build's `assembly_sha256` must match the current grouping, roles and free-part clearances. Changed
metadata or an older build JSON without this field keeps geometry unverified: rebuild or re-record
with the current parameters and save its JSON. Do not copy a fingerprint into an old report to
make it pass.

```bash
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver deliver/2026-10-21
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver deliver/2026-10-21 --bundle deliver/2026-10-21/source
```

It validates every part again with the settings the build used (R3 against the generator and
parameters as they are now), checks that the build JSON is the build of these very STLs and of
every part in `_parts`, and that it ran without errors, reads the `_verify` declarations
(`references/checks.md`) and reports five tiers: **use**, the promises made to the user, each judged by
its own evidence (`references/checks.md` says what each state means); **geometry** verified or
not verified; **shape** by direction (from `_verify.references`); **slicing** unverified (nothing
here slices) and **print** unverified (with the test prints and their results), plus `open`: every
promise that is not verified and why, every reason the geometry is not verified, every
unaccepted WARN, every unverified dimension and assumption. Say "verified" only for what it calls
verified; never fold the tiers into one "all checks pass". `--deliver` checks the delivery folder:
every STL must be one of the verified STLs, every 3MF must carry its manifest
(`<file>.3mf.manifest.json`, written next to it by `build.py` and `bambu3mf.py`: copy it along, or
write the Bambu project straight into the delivery folder) naming exactly the verified STLs, and
every part must be delivered in one of them. Always pass it: without it, finalize reads nothing
of the print file, and a promise can read verified while the file prints another material.

**Before the message, act on the `use` tier** (the worst state of the promises):

- `error`: a declaration is wrong (in `_verify`, `_material`, `_parts.<name>.material` or
  `_print`); `promise_errors` names it. Fix it and run finalize again. Never deliver on `error`.
- `failed`: the design does not keep a promise. Go back to the phase of the evidence that failed
  (a joint, a member or a measurement: Phase 4; a real-world size: Phase 2), fix it, build and
  check again (G7). A failure is never accepted or excluded away. If the user wants these files
  anyway, the failure is the first line of the message.
- `not verified`: read each reason. Renew the evidence a change made stale since Phase 4
  (`references/phase-5-gate.md`, step 1), then run finalize again; a stale look gets an image of
  the current build and a new look from the user, never the old look carried over. A promise
  still not verified goes out only as a prototype, or excluded by the user, as
  `references/phase-4-features-joints.md`, "Leaving Phase 4", says; when this is the first time
  finalize reports it, decide it with the user now by that rule.
- `assumed`, `excluded`, `accepted`: deliver, and say each as below.

Before the message, no promise goes out as a prototype or excluded, and no WARN accepted, that
the user was not asked about in a message that named it (`references/phase-4-features-joints.md`,
"What counts as agreement"), except the defaults when the user handed the decision back to you
and those of an unattended run, each with its `_assumptions` line. A record made from other
words (a look, a "you decide", an earlier answer) comes out: ask now.

## The print file (`--deliver`)

A Bambu project must print each part in its material (`_parts.<name>.material`, else `_material`)
and under `_print.preset`. finalize compares its manifest with them; what each finding leaves of
the evidence that depends on the material or the preset is in `references/checks.md` (the
`--deliver` paragraph). Act on its `open` lines:

- **Another material** ("stand is printed in Bambu PETG HF @BBL X1C (petg_hf), the part is
  pla_basic"): ask which material the user prints with. The part's own: write the project again
  into a new version folder with that part's `filament` set to the slot that holds it. Another:
  change the material in params.json, build again, renew what went stale
  (`references/phase-5-gate.md`, step 1) and offer a new test print. Never edit a manifest.
- **A filament finalize cannot name** ("the slicer's filament for stand is not checked ("My PLA"
  is not a filament of a known material)"): tell the user which filament to choose for each part
  in the slicer ("select stand in the object list and choose Bambu PLA Basic"), or, when they
  print with a system preset, write the project from a template that names it.
- **Another process preset** ("its process preset is "0.16mm Optimal @BBL X1C", not
  _print.preset "0.20mm Standard @BBL X1C""): ask which one the user prints with. The project's:
  set `_print.preset` to it and offer a new test print. `_print.preset`'s: write the project from
  a template with that preset.
- **No process preset in the project** ("the project names no process preset ..."): tell the
  user to choose the preset `_print.preset` names in the slicer, or write the project from a
  template that names it.
- **STL per part, or a core 3MF** (another slicer, or no Bambu template: "the print file's
  material is not checked (no Bambu project)"): say in the message which filament to choose for
  each part.

None of these is a geometry reason: they reach the user through the `use` tier and `open`.

## The source bundle (`--bundle`)

`--bundle` writes a new folder that holds what the verdicts were made from, each file at its
path in the project folder (`lib/helper.py` stays `lib/helper.py`):

- the generator and its own files (not the skill's libraries), `params.json`, the
  `printers.json` the build used, the report as `verification.json`, and `REPRODUCE.md`;
- the reports `_verify` names (fit, strength and measurement JSON); a proxy's generator and
  params file (a proxy taken in with `record` also with its build JSON, STLs and manifests); a
  `user-file` dims entry's file and its measurement reports; the seen images with their
  sidecars; the photos of a test print (its `photos`);
- with `--deliver`, the delivered files (every STL and 3MF), each 3MF with its manifest.

`REPRODUCE.md` holds the commands that rebuild the parts (and the proxies `build.py run` made)
and re-check them from the bundle alone (finalize with `--deliver` on the bundled delivery
folder); the reports hold while the rebuild makes the same STLs, so with the same engine and
library versions. A recorded build (Fusion, a live Blender) needs the user to export the part
STLs again first; REPRODUCE.md lists them. A file `_verify` names that is missing does not stop
the bundle: it is left out and listed in `bundle_missing` and in REPRODUCE.md; make it again and
bundle into a new folder, or say it is missing.

Bundle a build that is the project as it is now: the bundle rebuilds the parts, so a verdict
that says the build differs from the project (an STL or a source changed since, the settings,
grouping or material changed since, a part not built, or finalize run with other settings than
the build) is refused: build again (`build.py run`, with `--printer`), re-check, then bundle.
It also refuses a carried file that the rebuild writes again (a core 3MF a measurement read,
or a delivery made into `out/`: deliver into a folder of its own) or a file at a name the
bundle writes itself (`build.json`, `REPRODUCE.md`, ...), and a printers.json the build used
that is gone when the build judged an object of several parts with it.
A generator that reads a data file of its own (not a Python import, an OpenSCAD include or a
Blender library) is rebuilt without it: neither the freshness check nor the bundle tracks such a
file, so keep those numbers in DEFAULTS / PARAMETERS or params.json (Phase 3).

The bundle refuses any file it would carry, or the `--deliver` folder, outside the project
folder (a part STL or the core 3MF too, and a link inside the folder to a file outside it),
and any carried text file that holds a path of this machine: keep the user's files,
photos and reports in the project folder (`ref/plug.stl`, `photos/notch.jpg`), run the scripts
from there with relative paths (Phase 4), move a source in and build again, and put a name, not
a path, in a source or `params.json`. The bundle carries the user's own files, photos and the
delivered files, and a delivered Bambu project may carry metadata from the user's template
(`bambu3mf.py` blanks the designer and account fields it knows): when the user means to share
it, say so, and that sharing it is their call. Deliver it with the files so a later change can
start from it.

## The delivery message

Write it in the user's language and in plain words, at every delivery, also after a fix: no
script names, check ids, JSON keys or lines pasted from the report anywhere in it, the `open`
list and `_assumptions` included. An unattended run opens, before any result, with what was
decided alone (each stop taken alone and each default in `_assumptions`, the base-shape look
among them) and every promise not verified, then goes on as below (item 1 then gives the other
promises). In this order:

1. **The `use` tier, first.** One line per promise in `promises`: its `text` in the user's
   words, its state, and, when the state is not `verified`, why, from its `reasons`. When a
   promise failed (the user wants the files anyway) or goes out as a prototype
   (`references/phase-4-features-joints.md`, "Leaving Phase 4"), the first line says so and
   names each ("This is a prototype: the cable exit is not checked yet, because ...") and who
   chose it, as the note of its `_assumptions` line says (`"<id>: delivered as a prototype, not
   verified (<who chose it>)"`; the note is recommended): the user, in their words, or you when
   they handed the decision back or the run was unattended. Then, when `_assumptions` or
   `_verify.unverified` hold other lines, how many (item 2 gives them).
   finalize marks a prototype promise `"prototype": true` and names it in the use summary
   ("delivered as a prototype: cable-out"), so its line is not counted among those.

   | State | Say |
   |---|---|
   | `verified` | It holds, and what showed it ("checked against a plug of the size you measured", "your test print fit the cable"). When an evidence's `covers` is narrower than the promise's `conditions` (the fit checks the plug at rest; plugging it in at an angle is not simulated), say what was not covered. |
   | `accepted` | It holds apart from the warning the user accepted, named, with their reply. Not "verified". |
   | `assumed` | It holds only if a size nobody measured is right: name it with its value ("the plug head was taken as 13 × 8 mm, not measured") and what would settle it (a caliper reading, a test print). For a filament the print file does not name: which filament to choose. Never "verified". |
   | `excluded` | Not checked: the user chose to take it as it is, with their reason in their own words. |
   | `not verified` | Not checked, and why ("the strength was calculated for the 6 mm base; it is 6.5 mm now"). |
   | `failed` | Not kept, and what failed ("the lip is 10 mm high; holding the phone needs 12 mm"). |

   A size taken from a spec is in `open` with its URL and the place of each number: give both,
   so the user can check them.
2. **The other tiers and `open`**, summarised: the model's sizes, mesh and fits (`geometry`:
   when it is verified, one line saying they all passed), which sides of the shape a reference
   showed, that nothing was sliced here, the test prints and their results; then what `open`
   holds beyond the promises already named, in plain words: what the user must know or do (a
   warning they accepted or must decide, one they handed back to you that stays, a size still
   estimated, each `_assumptions` line that changes how they print or use the part). Never
   paste a line as finalize wrote it ("sled P6 UNVERIFIED (yours to decide)"): the soft checks
   left to you were decided before delivery (Phase 5, step 2), and only what the user must act
   on reaches the message. When a fit test or a mechanism-first print was offered and skipped,
   update `_assumptions` first ("latch window clearance 0.3 mm: not confirmed by a fit test") so
   that the delivery says what is unconfirmed, never that a test confirmed it.
3. **Files**, chosen by the slicer saved in Phase 2:

   | Slicer | Main file | Also deliver |
   |---|---|---|
   | Bambu Studio | Bambu project 3MF from `bambu3mf.py` with the generated or saved template (open with **Open Project**) | STL per part |
   | Bambu Studio, no template possible (no profiles readable, no saved project) | **STL per part** | Core 3MF, with this note: opening it shows "The 3mf file has invalid config, load geometry data only". That is expected for any 3MF without Bambu settings; the geometry loads correctly |
   | OrcaSlicer | STL per part | Core 3MF (current OrcaSlicer source imports config-less 3MFs silently; not yet tested in the app) |
   | Other or unknown | STL per part | Core 3MF |

   Name every STL after its part. Every part in `_parts` is delivered (`--deliver` requires each),
   a coupon or a mechanism-first part too: its STL is printed first, or kept as the record of the
   test. The core 3MF holds all parts in one file, laid out side by side; an object that only fits
   the bed rotated is placed with that rotation (D2's angle), the STL is not. A Bambu project
   keeps parts of one object together with their assembled positions. A part built in Blender also
   gets its `out/<model>.blend` copied next to the STLs (one named object per part, a collection
   per object, the parameters as custom properties on the `PARAMETERS` empty; no path of the
   machine that built it), never overwriting. In a mixed object it holds only the Blender parts;
   the CAD parts are the STLs. A `.blend` that packs a proprietary font is not delivered
   (`design.md`, "Text, logos, cosmetic faces"). One line with it: the generator script is the
   source of truth; editing the `.blend` by hand is fine, the next rebuild comes from the script.
   The delivery image may be a `render.py` image when Blender is there (`preview.py` otherwise).
4. The parameter table and "anything to change?"
5. Print settings: the per-object overrides with a reason for each, or the three-line recipe.
   Without a Bambu project, the filament to choose for each part (its material).
6. **Parts**, one line: which parts are separate and how to recolour one ("label and latch are
   parts of the lid; select a part in the object list and change its filament"). If the user
   named colours, they are already applied; never ask about colours.
   A print-in-place lid hinge adds one line: "don't force the lid past fully open" (the hinge is
   sized for the lid pulled away from the box, not for levering it past its stop; `design.md`).
7. Sources of the references used in Phase 1.

**After delivery.** When the user later reports a print result (a ring that fit, a latch that
held or broke), offer **once** to record it with `calibration.py add` in
`.3dprint/calibration.json` (`references/calibration.md`); never write it without their yes. A
result that checks a promise also goes into `_verify.test_prints` (`references/checks.md`,
"Test prints": each printed part's sha256 from the delivered `verification.json`, `"as built"`
only when they printed it as delivered, their photos saved in the project folder). Then run
finalize again with `--deliver` (a new bundle goes into a new folder) and tell them what it
changed.
