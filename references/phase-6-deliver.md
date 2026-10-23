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

A part rebuilt to other bytes since the user last looked at it is shown again, and their look
recorded, before the delivery (Phase 5, step 1: a stale `seen` entry).

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
- `not verified`: renew the evidence a change made stale (`references/phase-5-gate.md`, step 1)
  and run finalize again. One still not verified goes out only as a prototype or excluded, decided
  as `references/phase-4-features-joints.md`, "Leaving Phase 4", says (its "When to ask" holds
  here too: a record made from other words comes out, and you ask now).
- `assumed`, `excluded`, `accepted`: deliver, and say each as below.

## The print file and the bundle

When `--deliver` names another material, a filament or preset it cannot read, or no Bambu
project, act on each `open` line as `references/phase-6-files.md` says; none of these is a
geometry reason. `--bundle` writes a new folder with the generator, parameters, reports, the
delivered files and `REPRODUCE.md`; it refuses a build that differs from the project, a file
outside the project folder and a text file holding a path of this machine (what it carries and
each refusal: `references/phase-6-files.md`). It may carry the user's own files and template
metadata: when they mean to share it, say so, and that sharing it is their call.

## The delivery message

Write it in the user's language and in plain words, at every delivery, also after a fix: no
script names, check ids, JSON keys or lines pasted from the report anywhere in it, the `open`
list and `_assumptions` included. In this order:

0. **Unattended runs only, before any result:** what was decided alone (each stop taken alone
   and each default in `_assumptions`, the base-shape look among them) and every promise not
   verified. Item 1 then gives the other promises.
1. **The `use` tier.** One line per promise in `promises`: its `text` in the user's
   words, its state, and, when the state is not `verified`, why, from its `reasons`. When a
   promise failed (the user wants the files anyway) or goes out as a prototype
   (`references/phase-4-features-joints.md`, "Leaving Phase 4"), the tier's first line says so and
   names each ("This is a prototype: the cable exit is not checked yet, because ...") and who
   chose it, as the note of its `_assumptions` line says: the user, in their words, or you when
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
   on reaches the message. A fit test or mechanism-first print offered and skipped is said as
   unconfirmed, from its `_assumptions` line (SKILL.md).
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
   (`design-features.md`, "Text, logos, cosmetic faces"). One line with it: the generator script is the
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
