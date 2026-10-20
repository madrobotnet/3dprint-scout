# Phase 6 — Deliver

Read this on entering Phase 6 (SKILL.md names the rules that hold at all times).

Deliverables are new files outside `out/` (for example `deliver/<date>/`): copy the final STLs and
3MF there, or point `bambu3mf.py` there. Never write into a file the slicer has open, and never
overwrite an existing path: if it exists, ask and stop (the scripts refuse as well). Deliver:

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
   `PARAMETERS` empty; no path of the machine that built it), never overwriting. One line with it:
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
6. Verdicts, repeated at every delivery, also after a fix: FAIL, WARN and UNVERIFIED items, every
   dimension that is still unverified, and `_assumptions` in full. When the user later reports
   a print result (a ring that fit, a latch that held or broke), offer **once** to record it
   with `calibration.py add` in `.3dprint/calibration.json` (`references/calibration.md`); never
   write it without their yes. If all hard checks pass, say so in one line. When a fit test or a
   mechanism-first print was offered and skipped, update `_assumptions` first ("latch window
   clearance 0.3 mm: not confirmed by a fit test") so that the delivery says what is
   unconfirmed, never that a test confirmed it.
