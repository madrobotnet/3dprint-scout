# Conversation scenario results, 0.8.1

The four scenarios of `conversation-checks.md` that the 0.8.1 changes touch, run with Claude
from the same prompts as 0.8.0 (`README.md` in this folder): a2-unmeasured (a proxy build),
unattended (elephant foot, P6), given-answers and holes-unknown (the fallback and the concept
stop). The full transcript of each run, with its checklist marked, is in
`runs/claude-0.8.1/<id>.md`; a row only summarises it.

Three rows are the first pass at c6cfdea (the code of `v081-code` with the guidance of
`v081-guide`). The holes-unknown row is the re-run at 0b1e286, after the delivery rule it
missed was said again where the delivery is written ("First pass and re-run", below). The kit
is the scenario files at `v0.8.0`, unchanged.

The harness was the one 0.8.0 used. The run agent's last message of each turn is graded whole.
The scripted replies arrived labelled as a coordinator's message.

| Scenario | Prompt | Agent and model | Skill commit | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|---|---|
| given-answers | `given-answers.md` @ v0.8.0 | Claude Code-based harness subagent, claude-opus-5-5 | c6cfdea | Concept pick (3); Phase 2 table with a 0.3 or 1 mm clearance, the widest point stated as assumed (not asked); the base-shape look, naming two confirmed values it changed (wall 2.7 → 3.2, lead-in 1.5 → 1.0) and an optional test piece; after a 0.1 mm pocket-floor fix, the new look | Table without an A–D stop; `printers.json` from the message (holes and elephant foot `unknown`); both remotes caliper/user; Blender holder; proxy fits, depth and footprint measurements; P4–P6 in `_verify.decided`; STL + core 3MF + .blend + bundle | Five promises verified with what showed each; the feel of putting a remote in not confirmed (no test print); the elephant-foot line | `use` verified, `geometry` verified; big-in, small-in, no-tip, flared-foot, side-by-side verified | Matches (0.8.0's should miss, the widest-point question, holds) |
| holes-unknown | `holes-unknown.md` @ v0.8.0 | same | 0b1e286 (re-run) | A–D, rod length and place (fallback); the concept pick (3); the use list and table with a hole note and fit-test rings or go on; the base shape with a section | Concept stop held after the fallback; rod length 30 cm an `assumed` dims entry, recorded as handed back; holes and elephant foot `unknown`; socket 12.4 mm, no compensation; rings offered and skipped, with the reply; P4–P6 decided; Blender stand; STL + core 3MF + .blend + bundle | Fit checked on the model, the printed hole and the motion not confirmed; upright only for the assumed 30 cm rod; tight because the hole settings are unknown (drill), loose cannot be fixed; the elephant-foot line | `use` assumed (stands-upright rests on the rod length), `geometry` verified; rod-in-out, blind-bore, disc-base verified | Matches (0.8.0's should miss, the concept stop, holds) |
| unattended | `unattended.md` @ v0.8.0 | same | c6cfdea | The case size (and an optional cable path) | Defaults recorded (C, the first concept, purpose general, use list and base shape not reviewed); case caliper/user; elephant foot `unknown` with a 0.3 mm outer bottom chamfer; P4–P6 decided; Blender stand; STL + core 3MF + .blend + bundle | Opens with what it decided alone (no verdict before it), then the promise verified with what the fit does not cover; the elephant-foot line | `use` verified, `geometry` verified; stand-upright verified | Matches |
| A2 (a2-unmeasured) | `a2-unmeasured.md` @ v0.8.0 | same | c6cfdea | Measure the plug, a test print, or go on assumed | The user's measurement as caliper/user; proxy and holder rebuilt; fit again; P4–P6 decided; Bambu project + STL + bundle | Three promises verified with what showed each; the plug at rest, not the cable bending | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches |

## Compared with 0.8.0

| Scenario | 0.8.0 | 0.8.1 |
|---|---|---|
| given-answers | Matches; should missed: the widest-point question | Matches; the widest point stated as assumed, not asked |
| holes-unknown | Matches; should missed: the concept stop after the fallback | Matches at the re-run; the concept stop held in both passes |
| unattended | Matches (re-run) | Matches at the first pass |
| A2 | Matches | Matches |

No must item that held in 0.8.0 fails in the rows above.

## What 0.8.1 changed, as the runs show it

- **Relative paths.** Every build JSON of the four runs, proxies included, holds paths relative
  to the project folder; only `engine_info`'s tool paths are absolute. The a2 and unattended
  folders, copied to another depth, finalize to the same report (the unattended one, a Blender
  build, only with 30d52ae: see below).
- **`_verify.decided`.** All four runs recorded P4, P5 and P6 as `holds` with the part's STL
  hash, and finalize left none of them in `open`. None declared a check it may not decide.
- **The concept stop.** Both holes-unknown runs got the A–D answer with the fallback to its
  optional questions, and both stopped for the concept pick.
- **Elephant foot `unknown`.** given-answers, unattended and holes-unknown wrote `unknown`, put a
  0.3 mm chamfer on the outer bottom edges only, and (all three) said at delivery that the
  slicer's compensation, if on, makes that edge a little smaller.

## Found while checking, changed in 0.8.1

- **A moved Blender project lost its skill library.** Copying the unattended folder elsewhere,
  finalize said geometry not verified: "sources the build hashed are missing:
  ../../skill/3dprint-scout/references/engines/blender_builder.py". 0.8.0 does the same. 30d52ae
  reads the installed skill's file when such a library path is gone; the hash still decides.

## First pass and re-run

holes-unknown's first pass at c6cfdea (`runs/claude-0.8.1/holes-unknown-c6cfdea.md`) differed on
one must item of the last message. It said the printed hole was not confirmed at its size and
what to do when it prints tight; the reason, that the slicer's hole settings are unknown, and
that it may print loose were only in the message before it, which offered the fit-test rings.
The new elephant-foot line was missing too. Both rules lived in `tolerances.md` alone. 0b1e286
says them in Phase 6, item 2, where the delivery is written, and the scenario ran again.

The re-run at 0b1e286 matches: the last message gives the reason and both directions, and the
elephant-foot line. It also differs from 0.8.0 in one way the kit allows: the stand's upright
promise now rests on a rod length the agent chose after the fallback, a `_verify.dims` entry
`assumed`, so `use` reads `assumed` and the message names the 30 cm and what would settle it.
0.8.0's run checked the same promise on socket depth and base size alone.
