# Conversation scenario results, 0.8.0

The nine scenarios of `conversation-checks.md`, run with Claude from the same prompts as
0.7.0 (`README.md` in this folder), to see whether the 0.8.0 guidance work (one home per rule,
rare material read only when it applies) made any run worse. The full transcript of each run,
with its checklist marked, is in `runs/claude-0.8.0/<id>.md`; a row only summarises it.

Seven rows are the first pass at f36e6b1 (the guidance of #29). The bambu-template and
unattended rows are the re-runs at d400348, after three rules the first pass missed were said
again where they act ("First pass and re-run", below). The kit is `v080-scenarios`: the 0.7.0
kit with two items brought in line with the 0.8.0 decisions. The given-answers look may show
the pockets of a one-body part, and in every attended scenario a prototype the user agreed to
keeps their reply in its note.

The harness was the one 0.7.0 used. The run agent's last message of each turn is graded whole.
The scripted replies arrived labelled as a coordinator's message.

| Scenario | Prompt | Agent and model | Skill commit | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|---|---|
| given-answers | `given-answers.md` @ v080-scenarios | Claude Code-based harness subagent, claude-opus-5-5 | f36e6b1 | Concept pick (3); Phase 2 table with a 1.0 or 0.3 mm clearance, "are the sizes the widest points?", the remote weights (fallback); the base-shape look; after a pocket change, the new look and "tipping: test print, go on unverified, or widen the foot?" | Table without an A–D stop; `printers.json` from the message (holes `unknown`); both remotes caliper/user; Blender holder; proxy fits, depth measurements; pocket corners changed in Phase 4 and shown again; `no-tip` as a prototype with the user's reply as its note; STL + core 3MF + bundle | "시제품으로 드려요", the user's reply quoted; four promises "확인됨" with what showed each; `no-tip` "확인 안 됨(시제품)" | `use` not verified, `geometry` verified; big-in, small-in, flat-top, foot verified; no-tip not verified (prototype) | Matches. Should missed: the widest-point question |
| choice-d | `choice-d.md` @ v080-scenarios | same | f36e6b1 | A–D with four models; also clamp or tape? (fallback) | Phase 0 detect only; web search; handoff | The model's page, creator, CC BY-NC-SA; the checks left to the user (desk thickness, cable size, slot count, bed fit unchecked, slicing, a test print) | none (builds nothing) | Matches |
| holes-unknown | `holes-unknown.md` @ v080-scenarios | same | f36e6b1 | A–D, rod length, count, place (fallback); then the base shape with the concepts, the use list and table, and fit-test rings or go on | Concept picked itself after the fallback, recorded as handed back; holes `unknown`; socket 12.4 mm, no compensation; fit-test rings made, declined, recorded | "모델 치수로 확인"; the hand motion and the printed hole not confirmed; tight → drill, loose → tape | `use` verified, `geometry` verified; insert-remove, stand-upright, cone-look verified | Matches. Should missed: the concept stop |
| bambu-template | `bambu-template.md` @ v080-scenarios | same | d400348 (re-run) | A–D; concept pick (3); table, rail-end space (fallback), fit-test rings; the base-shape look; after a 0.0012 mm bore fix, the new look and five wall loops (fallback) | `compensation` holes `model`, elephant foot `slicer` written into `printers.json` with the reason; bore 22.6 mm (fit + compensation); Bambu project from the template + STL + .blend + bundle | Hand fit and hold not confirmed (test print skipped); the three promises with what showed each | `use` verified, `geometry` verified; on-off-by-hand, covers-end, lead-in verified | Matches |
| change-request | `change-request.md` @ v080-scenarios | same | f36e6b1 | The look at the 90 mm holder | `back_h` 90, expect updated, rebuilt; fit, measure, strength again; new folder, `2026-10-20` byte-identical | The three promises verified with what showed each; the old folder kept | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches |
| unattended | `unattended.md` @ v080-scenarios | same | d400348 (re-run) | The case size (and an optional cable path) | Defaults recorded (C, the first concept, purpose general, use list and base shape not reviewed, no fit test); case caliper/user; Blender stand; STL + core 3MF + .blend + bundle | Opens with the files ready (no verdict), then what it decided alone, then four promises verified with what showed each | `use` verified, `geometry` verified; four promises verified | Matches |
| A (a-kept-broken) | `a-kept-broken.md` @ v080-scenarios | same | f36e6b1 | After fixing the gap: "the holder is 50 mm wide now, fine?" (fallback) and the look | Found `cable-out` failed; `notch_w` 14.0 with an assertion, expect 50 mm, rebuilt; fit, measure, strength again; Bambu project + STL + bundle | The failure and the fix, then three promises verified | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches (0.7.0's should miss, the wider holder not shown, holds) |
| A2 (a2-unmeasured) | `a2-unmeasured.md` @ v080-scenarios | same | f36e6b1 | Measure the plug, go on assumed, or widen the gap; and a look | The user's measurement as caliper/user; proxy and holder rebuilt; fit again; Bambu project + STL + bundle | Three promises verified with what showed each | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches |
| C (c-param-changed) | `c-param-changed.md` @ v080-scenarios | same | f36e6b1 | Nothing | `base_t` 6.5; rebuilt; strength `--from-build` with the same links (SF 9.1); plug at z −15.5, lip target 12.0; Bambu project + STL + bundle | Three promises verified; the prong recalculated for 6.5 (was 7.75 at 6.0) | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches |

## Compared with 0.7.0

| Scenario | 0.7.0 | 0.8.0 |
|---|---|---|
| given-answers | Differs: the look after the features; a P3 warning left open; English caller blocks (harness) | Matches. The one-body look with its pockets is allowed now, and no warning was left open |
| choice-d | Matches | Matches |
| holes-unknown | Differs, harness only (English caller blocks) | Matches, no English blocks. Should missed: the concept stop |
| bambu-template | Matches | Matches (re-run; the first pass differed, below) |
| change-request | Differs, harness only (an English delivery) | Matches, Korean throughout |
| unattended | Differs: the delivery opens with a result | Matches (re-run; the first pass still opened with a result) |
| A | Matches; should missed: the wider holder not shown | Matches; the wider holder shown, the changed width named and asked about |
| A2 | Matches | Matches |
| C | Matches | Matches |

No must item that held in 0.7.0 fails in the rows above. The English caller blocks of 0.7.0 did
not appear in any run; the harness and its labels were the same. Three runs still wrote a scratch
file outside the project folder (bambu-template's first pass, A, C), against five in 0.7.0.

## First pass and re-run

The first pass ran all nine at f36e6b1. Two runs differed on a must item that held in both
0.7.x passes:

- **bambu-template:** `compensation.holes` `model` was recorded in `_assumptions` and applied to
  the bore, but not written into `printers.json`. In 0.8.0, Phase 2 step 4 had moved Bambu's
  "a generated template means model" to `bambu-process.md`. Its "record the state" did not say
  where.
- **unattended:**
  - purpose general was missing from `_assumptions`;
  - as in 0.7.0, the delivery opened with "the files are ready and every model check passed"
    before the list of what was decided alone.

d400348 said all three where the step happens, adding no rule:

- Phase 2 step 4 writes the state into the printer's entry in `printers.json`, adding the keys
  when they are missing, and names what a generated Bambu template means.
- Phase 2 step 2 puts the default purpose into `_assumptions`.
- Phase 6 item 0 comes before any result, "ready and passed" included.

Both scenarios ran again at d400348 and match. The first-pass records are
`runs/claude-0.8.0/bambu-template-f36e6b1.md` and `unattended-f36e6b1.md`.

## Found, not changed in 0.8.0

- **A fallback taken as handing back the concept pick (should).** In holes-unknown and in
  bambu-template's first pass, the A–D message also held optional questions. The scripted
  fallback to those ("잘 모르겠어요. 알아서 정해 주세요.") was read as leaving every later choice to
  the agent: it picked a concept itself and showed the concepts with its pick, without the
  concept stop. The 0.7.x runs got the same reply and stopped. The bambu-template re-run, whose
  A–D message asked nothing else, stopped. The candidate rule: a "you decide" to another question
  is not a concept pick. It goes to the stop design of the beginner flow.
- **`compensation.elephant_foot: "unknown"`** in the unattended re-run, a value the
  `printers.json` schema does not list. Nothing reads it as a correction, so no verdict changes.
- **A hand-guided use verified on fits alone** (holes-unknown, bambu-template). Every such run
  said in the message that the motion was not confirmed, as 0.8.0's Phase 2 now asks. finalize
  still verifies it; enforcing a print is a judgement change, left for later.
