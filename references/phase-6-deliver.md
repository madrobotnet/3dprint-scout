# Phase 6 — Deliver

Read this on entering Phase 6 (SKILL.md names the rules that hold at all times).

Deliverables are new files outside `out/` (for example `deliver/<date>/`): copy the final STLs and
3MF there, or point `bambu3mf.py` there. Never write into a file the slicer has open, and never
overwrite an existing path: if it exists, ask and stop (the scripts refuse as well). The verdicts
come from `out/` before the copy, where the build's manifests are; copy `<part>.stl.manifest.json`
along only when the copy is to be re-checked (without it R3 reads UNVERIFIED).

**First, the final report.** Run it before the delivery message, and again after every fix:

```bash
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver deliver/2026-10-21 --bundle deliver/2026-10-21/source
```

It validates every part again with the settings the build used (R3 against the generator and
parameters as they are now), checks that the build JSON is the build of these very STLs and of
every part in `_parts`, and that it ran without errors, reads the `_verify` declarations
(Phase 5, step 5) and reports four tiers: **geometry** verified or not
verified, **shape** by direction (from `_verify.references`), **slicing** unverified (nothing here
slices) and **print** unverified (with the test prints and their results), plus `open`, every
reason the geometry is not verified, every unaccepted WARN, every unverified dimension and
assumption. Say "verified" only for what it calls verified; never fold the tiers into one "all
checks pass". `--deliver` checks the delivery folder: every STL must be one of the verified
STLs, every 3MF must carry its manifest (`<file>.3mf.manifest.json`, written next to it by
`build.py` and `bambu3mf.py`: copy it along, or write the Bambu project straight into the
delivery folder) naming exactly the verified STLs, and every part must be delivered in one of
them. `--bundle` writes a new folder with the generator (not the
skill's libraries), `params.json`, the `printers.json` the build used, the report as
`verification.json` and `REPRODUCE.md`, the commands that rebuild and re-check the parts; it
refuses a source or `params.json` that holds a path of this machine (put a name there); deliver it with the files so a later change can
start from it. Deliver:

1. Files chosen by the slicer saved in Phase 2:

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
2. The parameter table and "anything to change?"
3. Print settings: the per-object overrides with a reason for each, or the three-line recipe.
4. **Parts**, one line: which parts are separate and how to recolour one ("label and latch are
   parts of the lid; select a part in the object list and change its filament"). If the user
   named colours, they are already applied; never ask about colours.
   A print-in-place lid hinge adds one line: "don't force the lid past fully open" (the hinge is
   sized for the lid pulled away from the box, not for levering it past its stop; `design.md`).
5. Sources of the references used in Phase 1.
6. Verdicts, repeated at every delivery, also after a fix: `finalize.py`'s `summary` (the four
   tiers) and its `open` list, which holds the FAIL, WARN and UNVERIFIED items, every dimension
   that is still unverified, and `_assumptions` in full. When the user later reports
   a print result (a ring that fit, a latch that held or broke), offer **once** to record it
   with `calibration.py add` in `.3dprint/calibration.json` (`references/calibration.md`); never
   write it without their yes. If all hard checks pass, say so in one line. When a fit test or a
   mechanism-first print was offered and skipped, update `_assumptions` first ("latch window
   clearance 0.3 mm: not confirmed by a fit test") so that the delivery says what is
   unconfirmed, never that a test confirmed it.
