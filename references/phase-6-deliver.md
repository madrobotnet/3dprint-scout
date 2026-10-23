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

**First, the final report.** Run it before the delivery message, and again after every fix.
The build's `assembly_sha256` must match the current grouping, roles and free-part clearances.
Changed metadata or an older build JSON without this field keeps geometry unverified: rebuild
or re-record with the current parameters and save its JSON. Do not copy a fingerprint into an
old report to make it pass.

Run:

```bash
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver deliver/2026-10-21 --bundle deliver/2026-10-21/source
```

It validates every part again with the settings the build used (R3 against the generator and
parameters as they are now), checks that the build JSON is the build of these very STLs and of
every part in `_parts`, and that it ran without errors, reads the `_verify` declarations
(Phase 5, step 5) and reports five tiers: **use**, the promises made to the user, each judged by
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

- `error`: a declaration in `_verify` is wrong; `promise_errors` names it. Fix it and run
  finalize again. Never deliver on `error`.
- `failed`: the design does not keep a promise. Go back to the phase of the evidence that failed
  (a joint, a member or a measurement: Phase 4; a real-world size: Phase 2), fix it, build and
  check again (G7). A failure is never accepted or excluded away. If the user wants these files
  anyway, the failure is the first line of the message.
- `not verified`: read each reason. Evidence a change made stale since Phase 4 (a rebuilt part, a
  parameter, a material, a preset) is run again as the reason says: `fit.py`, `strength.py
  --from-build` with the same `--param` links, `measure.py --expect`, a new image for the user to
  look at; then finalize again. Only a promise the user chose in Phase 4 to leave unproven (a
  prototype), or one left so in an unattended run, goes out not verified.
- `assumed`, `excluded`, `accepted`: deliver, and say each as below.

## The print file (`--deliver`)

A Bambu project must print each part in its material (`_parts.<name>.material`, else `_material`)
and under `_print.preset`. Its manifest names each part's filament and the process preset, and
finalize compares them (`delivered`, `references/checks.md`). Act on its `open` lines:

- **Another material** ("stand is printed in Bambu PETG HF @BBL X1C (petg_hf), the part is
  pla_basic"): the evidence that depends on the material (a `--from-build` member of that part,
  a test print of it) is not verified. Ask which material the user prints with. The part's own:
  write the project again into a new version folder with that part's `filament` set to the slot
  that holds it. Another: change the material in params.json, build again, run `strength.py
  --from-build` again, and offer a new test print (one in the old material no longer counts).
  Never edit a manifest.
- **A filament finalize cannot name** ("the slicer's filament for stand is not checked ("My PLA"
  is not a filament of a known material)"): a user preset or a generic name. The evidence that
  depends on the material stays `assumed`. Tell the user which filament to choose for each part
  in the slicer ("select stand in the object list and choose Bambu PLA Basic"), or, when they
  print with a system preset, write the project from a template that names it.
- **Another process preset** ("its process preset is "0.16mm Optimal @BBL X1C", not
  _print.preset "0.20mm Standard @BBL X1C""): test prints under one do not stand for the other.
  Ask which one the user prints with. The project's: set `_print.preset` to it and offer a new
  test print. `_print.preset`'s: write the project from a template with that preset.
- **No process preset in the project** ("the project names no process preset ..."): the
  template names none, so the test prints of its parts stay `assumed`. Tell the user to choose
  the preset `_print.preset` names in the slicer, or write the project from a template that
  names it.
- **STL per part, or a core 3MF** (another slicer, or no Bambu template): "the print file's
  material is not checked (no Bambu project)". The evidence that depends on the material stays
  `assumed`. Say in the message that the slicer's filament is not checked here, and which
  filament to choose for each part.

None of these is a geometry reason: they reach the user through the `use` tier and `open`.

## The source bundle (`--bundle`)

`--bundle` writes a new folder that holds what the verdicts were made from, each file at its
path in the project folder (`lib/helper.py` stays `lib/helper.py`):

- the generator and its own files (not the skill's libraries), `params.json`, the
  `printers.json` the build used, the report as `verification.json`, and `REPRODUCE.md`;
- the reports `_verify` names (fit, strength and measurement JSON) and the inputs they point to
  by hash: for a proxy joint its `proxy_build` JSON, the proxy STLs and their manifests, the
  proxy generator and its params file; for a `user-file` dims entry the user's file and the
  measurement reports of it;
- the seen images with their sidecars, the photos of a test print the user gave (its `photos`
  list), and the Bambu project `--deliver` compared, with its manifest.

`REPRODUCE.md` holds the commands that rebuild the parts and re-check them from the bundle alone,
with the same evidence. The bundle refuses a file outside the project folder: keep the user's
files and photos in it (`ref/plug.stl`, `photos/notch.jpg`), and move a source in and build
again. It refuses a source or `params.json` that holds a path of this machine (put a name
there). It carries the user's own files and photos: say so when they mean to share it. Deliver
it with the files so a later change can start from it.

## The delivery message

Write it in the user's language, at every delivery, also after a fix. In this order:

1. **The `use` tier, first.** One line per promise in `promises`: its `text` in the user's
   words, its state, and, when the state is not `verified`, why, in plain words from its
   `reasons` (no script names, check ids or JSON keys). When any promise is not verified or
   failed, the first line says the delivery is a prototype for those and names each ("This is a
   prototype: the cable exit is not checked yet, because ..."). Then, when the use summary counts
   assumptions not linked to a promise, how many (they are in `open`).

   | State | Say |
   |---|---|
   | `verified` | It holds, and what showed it ("checked against a plug of the size you measured", "your test print fit the cable"). When an evidence's `covers` is narrower than the promise's `conditions` (the fit checks the plug at rest; plugging it in at an angle is not simulated), say what was not covered. |
   | `accepted` | It holds apart from the warning the user accepted, named. Not "verified". |
   | `assumed` | It holds only if a size nobody measured is right: name it with its value ("the plug head was taken as 13 × 8 mm, not measured") and what would settle it (a caliper reading, a test print). For a filament the print file does not name: which filament to choose. Never "verified". |
   | `excluded` | Not checked: the user chose to take it as it is, with their reason. |
   | `not verified` | Not checked, and why ("the strength was calculated for the 6 mm base; it is 6.5 mm now"). |
   | `failed` | Not kept, and what failed ("the lip is 10 mm high; holding the phone needs 12 mm"). |

   A size taken from a spec is in `open` with its URL and the place of each number: give both,
   so the user can check them.
2. **The other tiers and `open`**: geometry, shape by direction, slicing unverified, print with
   the test prints and their results (`summary`), then the `open` list without the promises
   already named: the FAIL, WARN and UNVERIFIED items, every dimension that is still unverified,
   and `_assumptions` in full. If all hard checks pass, say so in one line. When a fit test or a
   mechanism-first print was offered and skipped, update `_assumptions` first ("latch window
   clearance 0.3 mm: not confirmed by a fit test") so that the delivery says what is
   unconfirmed, never that a test confirmed it.
3. **Files**, chosen by the slicer saved in Phase 2:

   | Slicer | Main file | Also deliver |
   |---|---|---|
   | Bambu Studio | Bambu project 3MF from `bambu3mf.py` with the generated or saved template (open with **Open Project**) | STL per part |
   | Bambu Studio, no template possible (no profiles readable, no saved project) | **STL per part** | Core 3MF, with this note: opening it shows "The 3mf file has invalid config, load geometry data only". That is expected for any 3MF without Bambu settings; the geometry loads correctly |
   | OrcaSlicer | STL per part | Core 3MF (current OrcaSlicer source imports config-less 3MFs silently; not yet tested in the app) |
   | Other or unknown | STL per part | Core 3MF |

   Name every STL after its part. The core 3MF holds all parts in one file, laid out side by side;
   an object that only fits the bed rotated is placed with that rotation (D2's angle), the STL is
   not. A Bambu project keeps parts of one object together with their assembled positions.
   A part built in Blender also gets its `out/<model>.blend` copied next to the STLs (one named
   object per part, a collection per object, the parameters as custom properties on the
   `PARAMETERS` empty; no path of the machine that built it), never overwriting. In a mixed
   object it holds only the Blender parts; the CAD parts are the STLs. A `.blend` that packs a
   proprietary font is not delivered (`design.md`, "Text, logos, cosmetic faces"). One line with it:
   the generator script is the source of truth; editing the `.blend` by hand is fine, the next
   rebuild comes from the script. The delivery image may be a `render.py` image when Blender is
   there (`preview.py` otherwise).
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
result that checks a promise also goes into `_verify.test_prints` (fields in
`references/checks.md`): the promises it checked, each printed part's sha256 from the delivered
`verification.json` (`parts[].sha256`) and the material it was printed in (a strength.py key), the printer, `"as built"` only when they
printed it as delivered, `"by": "user"`, the preset, and `photos` when they sent pictures (saved
in the project folder). Then run finalize again and tell them what it changed.
