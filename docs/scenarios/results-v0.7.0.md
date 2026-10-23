# Conversation scenario results, 0.7.0

The nine scenarios of `conversation-checks.md` ("Conversation checks when editing the skill"),
run with Claude from the same prompts, as `README.md` in this folder describes. Runs with Codex
were planned for 0.7.0 and deferred: the skill's next target is a user in a chat app, so the
next check is a run there rather than a second coding agent. One row per run; the columns are the fields of its "Recording a run". The full
transcript of each run, with its checklist marked, is in `runs/<agent>/<id>.md`
(`runs/claude/a2-unmeasured.md`); a row only summarises it.
For Claude, the rows of given-answers, holes-unknown, bambu-template, change-request and
unattended are the re-runs at e2f7953; the other four are the first pass at 1a9acb8 ("First pass
and re-run", below).

- **Prompt**: the scenario file and the commit it was taken from (`a2-unmeasured.md @ abc1234`):
  its opening message and scripted replies are the exact text given.
- **Asked**, **Did**: in order, short; "(fallback)" marks a fallback reply.
- **Claimed**: the last message's claims, quoted: what it called verified, assumed or not checked.
- **finalize**: `use`, `geometry` and each promise's state, from finalize run after the agent
  finished (with `--deliver` on its delivery folder).
- **Result**: "matches", or what differs, with the checklist items that failed.

| Scenario | Prompt | Agent and model | Skill commit | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|---|---|
| given-answers | `given-answers.md` @ b6134c8 | Claude Code-based harness subagent, claude-opus-5-5 | e2f7953 (v070-rerun; content of main ecc5036 + kit b6134c8) | Concept pick (3 variants); Phase 2: the sizes taken at the widest point of the lower third? ("Asks again" row), clearance 1.3 mm a side?; base-shape look (pockets, mouth rounds and top chamfer already built) and "keep the P3 warning or add a 1 mm band?" (fallback) | Reference table without an A–D stop; `printers.json` (MK4, 250 × 210 × 220, PrusaSlicer, holes `unknown`) from the message; dims both remotes caliper/user; Blender holder; proxy fits with 1.3 mm play and lift-out, two measurements; the P3 warning left unaccepted, "the user handed the decision to me; not accepted"; no Phase 5 rebuild; STL + core 3MF + bundle in `deliver/2026-10-23`; finalize `--deliver` | "처음에 약속한 6가지: 모두 확인됨", one line each (the two looks share one); `stable` "계산했어요 … 약 17.7°"; the warning "열린 항목으로 남겨 두었어요 … '완전 확인'으로 표시되지 않아요"; not sliced or printed | `use` verified, `geometry` not verified (P3 open); insert-remotes, dip-third, wide-foot, stable, side-by-side, mouth-round verified | Differs: the base-shape look came after the mouth rounds and chamfer were built (skill); `geometry` not verified, the P3 warning the user handed back left open (the skill's path; the item was clarified after grading and holds under the new wording); Korean throughout (harness-only: English "Status:" blocks in every hand-back). Should missed: the widest-point question. Agreement holds |
| choice-d | `choice-d.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | A–D after four MakerWorld models, plus optional desk thickness and cable type (fallback) | Wrote nothing (only `build.py detect`); handoff of model 1 (GH05TU, CC BY-NC-SA) with URL, licence terms and download steps | "아직 확인되지 않은 것": desk fit, 3 vs 5 cables on the page, size and bed fit ("프린터도 확인하지 않았어요"), "슬라이싱 결과와 출력 품질: 아무것도 검증하지 않았어요"; page facts "만든 사람의 설명이고, 제가 확인한 건 아니에요" | n/a (choice D) | Matches |
| holes-unknown | `holes-unknown.md` @ b6134c8 | Claude Code-based harness subagent, claude-opus-5-5 | e2f7953 (v070-rerun; content of main ecc5036 + kit b6134c8) | A–D, plus the rod length and what goes on top, optional (fallback); concept pick; use list and table, plus the preset name, optional; base-shape look; leaving Phase 4: test rings first or straight on, and measure the rod length or keep it assumed | `printers.json` holes `unknown`; socket 12.4 mm, fit `--min-clearance 0.2`; rings 0.3 / 0.4 / 0.5 in `fit-test/`; rod length 40 cm assumed after the fallback, recorded as decided for the user; the printed fit taken as a prototype on the user's reply, kept as a plain `_assumptions` line; rebuild byte-identical; STL + core 3MF + bundle; finalize `--deliver` | "먼저, 시제품이라는 점부터" (the printed fit, with the user's words); rod-in-out "모델로는 확인됐습니다 … (시제품)"; rod-upright "가정에 기댑니다"; lead-in, disc-collar "확인됐습니다"; the socket may print tight or loose | `use` assumed, `geometry` verified; rod-in-out verified, rod-upright assumed, lead-in verified, disc-collar verified | Differs, harness-only: Korean throughout (an English preface and "Background for the caller" in every hand-back). The row and the agreement hold |
| bambu-template | `bambu-template.md` @ b6134c8 | Claude Code-based harness subagent, claude-opus-5-5 | e2f7953 (v070-rerun; content of main ecc5036 + kit b6134c8) | A–D; concept pick; Phase 2: the free rod length to the bracket (fallback), use list and table, a three-step test print, the Bambu Studio version (optional); base-shape look, and a prototype question naming on-off and stays-on with the cost and three choices | `printers.json` holes `model` (Bambu public profiles v02.08.02.61); six ribs, tip circle 22.0 = 22.0 − 0.30 + 0.30, bore 22.7; fit `--min-clearance 0`; free length assumed 20 mm, recorded as handed back; prototype lines with the user's reply word for word; `bambu3mf.py` project + STL + bundle; finalize `--deliver`; template unchanged | "다만 이 마개는 시제품이에요" with the user's reply; on-off, stays-on "확인 안 됨"; inner-ribs, lead-in, flat-top "확인했어요"; not sliced or printed; "구멍 보정 … 켜지 마세요" | `use` not verified, `geometry` verified; on-off, stays-on not verified (prototype); inner-ribs, lead-in, flat-top verified; the 3MF names PLA Basic and 0.20mm Standard | Matches |
| change-request | `change-request.md` @ b6134c8 | Claude Code-based harness subagent, claude-opus-5-5 | e2f7953 (v070-rerun; content of main ecc5036 + kit b6134c8) | A look at the taller holder (after the rebuild and the renewed checks) | `back_h` 90 (params.json and the generator's default), `expect` [49, 19, 90]; rebuilt (Python); fit, member and lip renewed with the same links; finalize; after the look a new `deliver/2026-10-23` (`bambu3mf.py` project with a 5 mm brim override, STL, bundle); the 2026-10-20 delivery and unrelated files byte-identical | In English: "The new version … is in a new folder, `deliver/2026-10-23`. I left the 2026-10-20 files as they were."; three promises "checked again", each with what was not covered; the brim, why and how to remove it | `use` verified, `geometry` verified; seat, cable-out, holds verified | Differs, harness-only: Korean throughout (the delivery in English after the reply arrived labelled as a coordinator message). Every row item holds |
| unattended | `unattended.md` @ b6134c8 | Claude Code-based harness subagent, claude-opus-5-5 | e2f7953 (v070-rerun; content of main ecc5036 + kit b6134c8) | Once: the case's model or caliper size (plus a cable path and V2/V3, optional) | References, concepts and use list alone; `printers.json` MK4/PrusaSlicer; `petg_basic`; dims caliper/user 62 × 28 × 48; Blender stand, proxy fit seated with 0.35 mm play, two measurements; rebuild gave the same STL; 21 `_assumptions` lines, the base-shape look taken alone among them; STL + core 3MF + bundle; finalize `--deliver` | Opens "… 끝까지 만들었어요. 약속한 세 가지가 모두 확인됐고 …", then "묻지 않고 제가 정한 것" (the skipped look among them) and "확인이 안 된 채 나가는 약속은 없어요"; three "확인됨" | `use` verified, `geometry` verified; stand-upright, take-out, finger-notch verified | Differs: the delivery opens with a result before what was decided alone (skill). The first pass's other miss, the base-shape look not recorded, is fixed |
| A (a-kept-broken) | `a-kept-broken.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Nothing | Read the failing fit report (no finalize on the found state); gap derived from the plug, 13.4 + 2 × 0.3 = 14.0 mm, `expect` [50, 19, 70]; rebuilt; fit at the new placement, member and lip renewed; finalize verified before any delivery file; `bambu3mf.py` project (brim, 4 walls) + STL + bundle | "어제 재 주신 플러그가 13.4 mm로, 두 받침 사이 틈(13.0 mm)보다 넓어서 들어가지 않는 상태였습니다. 그래서 틈을 … 14.0 mm로 넓혔습니다"; three "확인됨" lines with what showed each; the tape not checked | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches. Should missed: the wider holder not shown before delivering |
| A2 (a2-unmeasured) | `a2-unmeasured.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Measure the plug (recommended), a test piece, or go on with it assumed | finalize first (cable-out assumed); after the reply dims caliper/user 12.4/6.6/23.0 in params.json and `usb_c_plug.json`; gap widened 13.0 → 13.4 mm; proxy and holder rebuilt, fit at 18.5,6.2,−17.0, member and lip renewed; `bambu3mf.py` project + STL + bundle | "약속한 세 가지가 모두 확인돼서"; cable-out checked against the measured plug at rest, "케이블이 휘는 모양까지 본 건 아니에요" | `use` verified, `geometry` verified; seat, cable-out, holds verified; usb-c-plug measured | Matches |
| C (c-param-changed) | `c-param-changed.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Nothing | `base_t` 6.5 (params.json and the generator's default); rebuilt; fit at z −15.5, `strength.py --from-build` with the same links (SF 9.1, every input linked), lip ≥ 12.0; delivered, deleted that unshown delivery and delivered again with a brim | "6 mm 때 확인한 결과는 쓰지 않았습니다"; three "확인됨"; prong "약 9.1배 … 6 mm일 때는 7.75배였습니다", plus its own estimate that default infill still leaves enough | `use` verified, `geometry` verified; seat, cable-out, holds verified; member `h` base_t 6.5 | Matches |

## First pass and re-run

The first Claude pass ran all nine scenarios with the skill at 1a9acb8 and the kit at 8a663aa.
Its records are kept as `runs/claude/<id>-1a9acb8.md` for the five scenarios run again; the rows
of choice-d, A, A2 and C above are still that pass. What differed in the first pass, and why the
five were run again:

- **Blender STLs were not byte-deterministic** at 1a9acb8: a rebuild changed the triangle order,
  so looks and other evidence went stale. In holes-unknown and bambu-template that led to the
  exclusion and the prototypes graded there. #23 fixed the Blender STL export.
- **Agreement was read into replies that were not agreement**: a look approval recorded as the
  exclusion of a look promise (holes-unknown), the fallback recorded as the acceptance of a
  thin-wall warning (bambu-template), and promises delivered as prototypes without a question that
  named them. #24 wrote the agreement rules into the skill (what counts as agreement, what a
  reply that hands the decision back leads to, the prototype line's note), and every attended
  checklist gained the same agreement item (b6134c8).
- **The scenario table shipped with the skill** in `references/development.md`, and the
  change-request agent read its row before acting. b6134c8 moved the table to
  `docs/scenarios/conversation-checks.md`, which is not installed.
- The checklists also got the first grader's fixes (b6134c8), and the re-runs were graded against
  them.

The re-runs used e2f7953 (`v070-rerun`: the content of main ecc5036, that is 1a9acb8 with #23 and
#24, plus the kit commit b6134c8). Result per scenario, first pass → re-run:

- given-answers: matches → differs: the base-shape look came after the features; `geometry` not
  verified because the P3 warning the user handed back stays open; English caller blocks
  (harness-only).
- holes-unknown: differs → differs, harness-only (English caller blocks); the two agreement
  failures did not recur.
- bambu-template: differs → matches; the fallback is no longer an acceptance, and the prototypes
  rest on the user's reply to a question that named them.
- change-request: matches → differs, harness-only (the delivery in English after a reply labelled
  as from a coordinator); the look at the taller holder now happens, and the agent read no
  scenario row.
- unattended: differs → differs on one item: the delivery still opens with a result before what
  was decided alone; the base-shape look taken alone is now recorded.

The agreement item holds in all four attended re-runs: no `accepted` entry, no exclusion, the
prototypes (bambu-template) and the prototype claim (holes-unknown) on replies to questions that
named them, and each fallback (holes-unknown, bambu-template, given-answers) recorded as handed
back, never as agreement.

### Checklist clarifications after the re-run

The re-run grading found four items unclear; the kit now says, and later runs are graded by,
the following. Only the first changes a mark above, and the records keep the mark as graded with
a note:

- given-answers, the finalize item: `geometry` is `verified`, or `not verified` only by a WARN
  the user handed back that stays open, is recorded as handed back and is named at delivery.
  Under this wording the given-answers re-run holds that item; it still differs on the look
  taken after the features.
- unattended, the opening item: no result line comes before what was decided alone (graded so).
- The agreement item, in every attended scenario: a question asked earlier about the same named
  promise counts (graded so).
- bambu-template, asking: one optional question for the Bambu Studio version is not a failure
  (graded so).

## Claude runs: setting and confounds

The first pass (2026-10-23) ran all nine scenarios with the skill at 1a9acb8 (main, installed in
the release layout) and the kit at 8a663aa. The re-runs (2026-10-23) ran five of them with the
skill at e2f7953, installed the same way without `docs/`, and the kit at b6134c8 (unchanged at
91473b5). In both, each scenario was run by a separate Claude Code-based harness subagent
(claude-opus-5-5) on Linux with Python 3.13 and bpy 5.2.2, web search on; the session lead played
the user from the scripts, and a separate agent, which took no part in the runs, graded them.

How the harness worked, and what it does to the marks:

- The lead sent each scripted reply word for word with a messaging tool. The run agents received
  each reply labelled as a message from a coordinator ("The coordinator sent a message while you
  were working: …"); the change-request agent of the re-run says so in its own record. The
  re-run's brief named no coordinator and told each agent that the whole last message of a turn
  is shown to the user, as README's "A run played by another agent" asks; the label came from the
  messaging tool.
- A run agent returns each turn's message through a hand-back that is also a report to its
  caller. That hand-back is the last message of the turn, what the user saw, and it is graded
  whole. Notes written between tool calls were not shown and are not graded.
- Several agents wrote for the caller inside that message. In the first pass, holes-unknown ended
  three messages with English "(Coordinator note …)" blocks. In the re-runs, holes-unknown and
  given-answers wrapped every message in English ("Background for the caller", "Status:",
  "Message for the user (Korean, verbatim):"), and change-request switched to English after the
  first reply and delivered in English. These fail "In Korean throughout"; each Result names them
  as harness-only, apart from what the skill's own behaviour did.

Known confounds (facts, not excuses for a result):

- The run agents had the skill owner's account memory in their context; it names the owner's own
  printer and slicer. Every run used the printer of its folder or its opening message; in the
  re-runs, holes-unknown and given-answers mentioned the owner's printer in their caller blocks.
  An agent run outside this account will not have that memory.
- First pass only: `references/development.md`, which shipped with the skill, held the scenario
  rows, and the change-request agent read them (lines 110–140) and cited "the change-request
  scenario expects a new delivery"; the other eight did not read the file. In the re-runs the
  table is in `docs/scenarios/conversation-checks.md`, not installed; the change-request agent's
  searches found only pointers.
- First pass only: Blender-built STLs were not byte-deterministic (the triangle order changed
  between identical builds), so a rebuild made `seen` entries and other evidence stale.
  given-answers, holes-unknown, bambu-template and unattended built with Blender; in
  holes-unknown and bambu-template the stale looks led to the exclusion and the prototype graded
  there. #23 fixed it: in the re-runs, the rebuilds in holes-unknown and unattended gave the same
  STL, and no look went stale.
