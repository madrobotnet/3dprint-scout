# Conversation scenario results, 0.9.0

All nine scenarios of `conversation-checks.md`, run with Claude from the same prompts as before
(`README.md` in this folder), to see whether the 0.9.0 flow keeps every must item while stopping
less. 0.9.0 stops twice by default: the pick (the concepts, the references under them) and the
look (the part as built and checked, its promises, the sizes to judge and a test print offer).
The full transcript of each run, with its checklist marked, is in `runs/claude-0.9.0/<id>.md`; a
row only summarises it.

All nine ran at 33d5732 (the 0.9.0 guidance and the 0.9.0 kit), in one pass. The kit was
amended once while the runs were going (df51892, choice-d: the pick's concept builds, below).

The harness was the one 0.8.x used. The run agent's last message of each turn is graded whole,
and the scripted replies arrived labelled as a coordinator's message. "Stops" counts the
agent's messages that waited for the user before the delivery.

| Scenario | Stops (0.8.x) | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|
| given-answers | 2 (4) | The pick (3 concepts, the references under them); the look (the caddy built and checked, with the remotes in place, its sizes, a test frame or a prototype) | `printers.json` from the message; both remotes caliper/user; Blender caddy; box-proxy fits, depth measurements; `stand-two` `by_hand`, a prototype on the look's reply; STL + core 3MF + .blend + bundle | Opens with the prototype and the user's words; each promise with what showed it; the elephant-foot line | `use` verified, `geometry` verified; stand-two verified, a prototype | Matches |
| choice-d | 1 (1) | The pick (3 concepts, 4 models, "use as it is", optional measurements) | Concepts in `out/concepts/` only; handoff after the choice; nothing built after it, nothing downloaded | The model's page, creator, licence not shown (where to look); the desk thickness and the cable size left to check | none (builds nothing after the choice) | Matches (amended kit) |
| holes-unknown | 2 (5) | The pick; the look (rings 12.2 / 12.4 / 12.6, or a prototype) | Holes and elephant foot `unknown`; socket 12.4 mm, no compensation; `rod-in-out` `by_hand`, a prototype on the look's reply; Blender stand | Opens with the prototype; tight or loose because the hole settings are unknown; the elephant-foot line | `use` verified, `geometry` verified; rod-in-out verified, a prototype | Matches |
| bambu-template | 2 (5) | The pick; the look (three test options, a prototype among them) | `compensation` holes `model`, elephant foot `slicer`; rib tips 22.1 mm (interference + compensation); `on-off` `by_hand`, a prototype; Bambu project from the template + STL + .blend + bundle | Opens with the prototype; slicing and the print not checked | `use` verified, `geometry` verified; on-off verified, a prototype | Matches |
| change-request | 1 (1) | The look at the 90 mm holder | `back_h` 90, expect updated, rebuilt; fit, measure, strength again; new folder, the earlier delivery byte-identical | Three promises verified with what showed each; the old folder kept | `use` verified, `geometry` verified | Matches |
| unattended | 1 (1) | The case size | Defaults recorded; case caliper/user; corner radius assumed; `lift-out` `by_hand`, a prototype "(unattended run)"; Blender stand | Opens with what was decided alone (item 0), the prototype and the assumption among it | `use` assumed, `geometry` verified; stand-upright assumed, lift-out a prototype | Matches |
| A (a-kept-broken) | 1 (2) | The look at the fixed holder (the gap 13.0 → 14.0, the width 49 → 50, named) | Found `cable-out` failed; fixed the design; fit, measure, strength again; Bambu project + STL | The failure and the fix, then three promises verified | `use` verified, `geometry` verified | Matches |
| A2 (a2-unmeasured) | 1 (1) | The look, with the plug question in it | The user's measurement as caliper/user; proxy and holder rebuilt; fit again; Bambu project + STL + bundle | Three promises verified; the plug at rest, not the cable bending | `use` verified, `geometry` verified | Matches |
| C (c-param-changed) | 0 (0) | Nothing | `base_t` 6.5; strength `--from-build` with the same links (SF 9.1); plug at z −15.5 | Three promises verified; the prong recalculated | `use` verified, `geometry` verified | Matches |

No must item that held in 0.8.x fails in the rows above. The three scenarios that design a new
part stop twice instead of four or five times; the others stop as often as before or less.

## What changed in the conversations

- **The pick replaced two stops.** No run asked the A–D question. Each showed the concepts first
  and the four references under them, one line each, with what a concept borrows; choice-d's
  user took a reference as it is from the same message.
- **The look replaced the table stop and the Phase 4 question.** Each look in a design scenario
  held the image of the part as built and checked, its promises, three to six sizes, the checks
  in one line, a test print offer naming the promise and its cost, and the full table under it.
  The user's one reply settled the shape, the table and the test print.
- **A prototype on the look's reply.** In given-answers, holes-unknown and bambu-template the
  `by_hand` promise went out as a prototype on the look's reply, its line keeping that reply word
  for word, and finalize marked it (0.8.2's change). The 0.8.2 holes-unknown first pass had called
  a verified promise a prototype without the record; here record and message agree.

## Kit amended during the runs

choice-d's must items "builds nothing" and "downloads no model file" were written for a flow
in which the A–D choice came before any concept. In 0.9.0 the pick builds concepts first, so
the run had `out/concepts/` STLs, a generator and concept params before the user chose D.
df51892 limits those two items to what happens after the choice and outside `out/concepts/`.
The run is graded on the amended items; nothing was built or downloaded after the choice.

## Harness

- **English caller blocks.** given-answers and change-request ended a message with an English
  block for "the caller", as some 0.7.0 runs did. The user-facing text was Korean; graded as
  harness, as then.
- **The host's memory reached two run agents.** choice-d's pick assumed the owner's real
  printer, and given-answers' delivery called the user by the owner's real name. Neither is in
  the scenario folder or the skill: the run agents inherited the session's context about its
  user. The transcripts replace both with a placeholder. Graded as harness. A later run should
  start its agents without that context.
