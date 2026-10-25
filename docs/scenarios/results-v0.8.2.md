# Conversation scenario results, 0.8.2

Four scenarios of `conversation-checks.md` that the 0.8.2 changes touch, run with Claude
from the same prompts as 0.8.1 (`README.md` in this folder): holes-unknown, bambu-template and
given-answers (uses done by hand), and a2-unmeasured (a proxy fit). P3 and inherited filament
presets have no scenario that reaches them: the golden comparison and the tests cover those.
The full transcript of each run, with its checklist marked, is in `runs/claude-0.8.2/<id>.md`;
a row only summarises it.

The a2-unmeasured and bambu-template rows are the first pass at 01be02e. The holes-unknown and
given-answers rows are the re-runs at 165a7ad, after a finding of the first pass was fixed
("First pass and re-run", below). The kit is the scenario files at `v0.8.0`, unchanged.

The harness was the one 0.8.1 used. The run agent's last message of each turn is graded whole.
The scripted replies arrived labelled as a coordinator's message.

| Scenario | Prompt | Agent and model | Skill commit | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|---|---|
| holes-unknown | `holes-unknown.md` @ v0.8.0 | Claude Code-based harness subagent, claude-opus-5-5 | 165a7ad (re-run) | A–D with optional questions (fallback); the concept pick; the table; the look; in Phase 4 the motion by hand not confirmed (rings or a prototype) and the rod length assumed | Concept stop after the fallback; `rod-in-out` `by_hand`; rod length an `assumed` dims entry; holes and elephant foot `unknown`; socket 12.4 mm; rings offered and skipped; the prototype line with the reply; P4–P6 decided; Blender stand; STL + core 3MF + .blend + bundle | Opens with the prototype and the user's words; upright only for the assumed rod; tight or loose because the hole settings are unknown; the elephant-foot line | `use` assumed, `geometry` verified; rod-in-out verified and delivered as a prototype; rod-upright assumed | Matches |
| bambu-template | `bambu-template.md` @ v0.8.0 | same | 01be02e | A–D with optional questions (fallback); the concept pick; the table; the look; in Phase 4 fit-test cups or go on, and the rail end's length | Concept stop after the fallback; `compensation` holes `model`, elephant foot `slicer`; ribs 22.10 mm (fit + compensation); `on-off` `by_hand`, resting on the assumed rail-end length; cups offered and skipped; P4–P6 decided; Bambu project from the template + STL + .blend + bundle | `on-off` holds on the assumption, the grip by hand not confirmed by a print; slicing and the print not checked | `use` assumed, `geometry` verified; grip-ribs, flat-top verified; on-off assumed | Matches (0.8.0's first-pass miss, the concept stop, holds) |
| given-answers | `given-answers.md` @ v0.8.0 | same | 165a7ad (re-run) | The concept pick; the table (weights assumed, an optional weighing, fallback); the look, naming the changed walls and width | Table without an A–D stop; both remotes caliper/user; holes and elephant foot `unknown`; tip-over on assumed 150 g weights; no `by_hand` on putting the remotes in (1.0 mm a side); P4–P6 decided; STL + core 3MF + .blend + bundle | Each promise with what showed it; stays-up resting on the assumed weights; the elephant-foot line | `use` assumed, `geometry` verified; five verified, stays-up assumed | Matches |
| A2 (a2-unmeasured) | `a2-unmeasured.md` @ v0.8.0 | same | 01be02e | Measure the plug or go on assumed | The user's measurement as caliper/user; proxy and holder rebuilt; fit again; P4–P6 decided; Bambu project + STL + bundle | Three promises verified; the plug at rest, not the cable bending | `use` verified, `geometry` verified | Matches |

## Compared with 0.8.1

| Scenario | 0.8.1 | 0.8.2 |
|---|---|---|
| holes-unknown | Matches (re-run) | Matches (re-run); the motion by hand is now finalize's line and a prototype the user agreed to |
| bambu-template | not run in 0.8.1 (0.8.0: matches at the re-run) | Matches at the first pass |
| given-answers | Matches | Matches |
| A2 | Matches | Matches |

No must item that held in 0.8.1 (or, for bambu-template, in 0.8.0) fails in the rows above.

## What 0.8.2 changed, as the runs show it

- **A use done by hand.** Every run that marked a use `by_hand` (both holes-unknown runs,
  bambu-template, given-answers' first pass) got finalize's line that the motion is not confirmed
  by a print, said it in Phase 4 with the test print offered, and said it again at delivery.
  None added a stop: the test print was offered in the same message as before.
- **Inherited filaments and P3** are not reached by these scenarios (their templates use system
  presets, and no part has an acute bed edge). The golden comparison shows the P3 change: the
  0.7.0 given-answers holder reads P3 PASS (3.0 mm) and its geometry verified.

## First pass and re-run

The first pass ran all four at 01be02e. holes-unknown and given-answers matched the kit, but in
both the agent called a `by_hand` promise a prototype that finalize kept verified. The user's
reply had taken "what is not confirmed" as a prototype, and the motion was what was not
confirmed. given-answers also wrote the prototype line in `_assumptions`; finalize read
prototype lines only for a promise `not verified`, so it ignored the line, and the record and
the message disagreed. This was the 0.7.0 known limit "a verified promise the user takes as a
prototype has no record", now reached through `by_hand`.

4f7aa4d lets finalize take the prototype line on a `by_hand` use whose motion no passed print
confirms, in any state its fits give: it keeps that state, is marked `"prototype": true`, and
the use summary names it. 165a7ad says so in Phase 4 ("Leaving Phase 4") and Phase 6. Run on
the first pass's given-answers folder, finalize at 4f7aa4d reads "delivered as a prototype:
insert-both". Both scenarios ran again at 165a7ad. The holes-unknown re-run marked the
prototype and finalize agreed. The given-answers re-run did not mark putting the remotes in as
`by_hand` at all (below). The first-pass records are `runs/claude-0.8.2/holes-unknown-01be02e.md`
and `given-answers-01be02e.md`.

## Found, not changed in 0.8.2

- **Whether a use is `by_hand` rests on the agent.** given-answers' first pass marked putting the
  remotes in (1.0 mm a side) as `by_hand` and asked about it; the re-run did not mark it, so its
  delivery does not say the feel is unconfirmed. Both are within the Phase 2 line's examples
  ("sliding the phone in, pushing a rod in and pulling it out"). A drop-in pocket with a wide
  clearance is the case the line does not settle.
- **P3 on a very small part.** A 6 × 5 mm block with a 74° wall still reads WARN (1.09 mm): rays
  from the slope near the bed pull the 5th percentile down.
