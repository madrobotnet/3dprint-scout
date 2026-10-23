# Conversation scenario results, 0.7.0

The nine scenarios of `references/development.md` ("Conversation checks when editing the
skill"), each run with Claude and with Codex from the same prompts, as `README.md` in this folder
describes. One row per run; the columns are development.md's "Recording a run". The full
transcript of each run, with its checklist marked, is in `runs/<agent>/<id>.md`
(`runs/claude/a2-unmeasured.md`, `runs/codex/a2-unmeasured.md`); a row only summarises it.

- **Prompt**: the scenario file and the commit it was taken from (`a2-unmeasured.md @ abc1234`):
  its opening message and scripted replies are the exact text given.
- **Asked**, **Did**: in order, short; "(fallback)" marks a fallback reply.
- **Claimed**: the last message's claims, quoted: what it called verified, assumed or not checked.
- **finalize**: `use`, `geometry` and each promise's state, from finalize run after the agent
  finished (with `--deliver` on its delivery folder).
- **Result**: "matches", or what differs, with the checklist items that failed.

| Scenario | Prompt | Agent and model | Skill commit | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|---|---|
| given-answers | `given-answers.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Concept pick (3 variants); Phase 2: clearance 1.3 mm a side?, sizes taken at the widest point? ("Asks again" row), print profile?, mouth chamfer? (fallback); base-shape look and a test piece offer; a second look after the rounds | Showed the 4-model table without an A–D stop; wrote `printers.json` (MK4, 250 × 210 × 220, PrusaSlicer, holes `unknown`) from the message; dims both remotes caliper/user; Blender holder; proxy fits with play and lift-out, four measurements; pocket radius 3 → 1 mm after the table, told afterwards; STL + core 3MF + bundle in `deliver/2026-10-23`; finalize `--deliver` | "처음 약속드린 다섯 가지는 모두 모델에서 확인했습니다. 다만 실제로 출력해서 꽂아 본 것은 아니에요." Each promise "확인됨" with its evidence; the remotes' fit not test-printed | `use` verified, `geometry` verified; remotes-in, third-deep, side-by-side, wide-foot, mouth-chamfer verified | Matches. Should missed: the given sizes re-confirmed at Phase 2 (widest point) |
| given-answers | | Codex | | | | | | |
| choice-d | `choice-d.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | A–D after four MakerWorld models, plus optional desk thickness and cable type (fallback) | Wrote nothing (only `build.py detect`); handoff of model 1 (GH05TU, CC BY-NC-SA) with URL, licence terms and download steps | "아직 확인되지 않은 것": desk fit, 3 vs 5 cables on the page, size and bed fit ("프린터도 확인하지 않았어요"), "슬라이싱 결과와 출력 품질: 아무것도 검증하지 않았어요"; page facts "만든 사람의 설명이고, 제가 확인한 건 아니에요" | n/a (choice D) | Matches |
| choice-d | | Codex | | | | | | |
| holes-unknown | `holes-unknown.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | A–D, plus how many rods and how long (fallback); concept pick (with the table for concept 2); base-shape look and three fit-test rings | `printers.json` holes `unknown`; socket 12.4 mm, fit `--min-clearance 0.2`; rings 12.2/12.4/12.6 delivered apart; a look promise added in Phase 4, a Blender rebuild made the look stale, then `_verify.accepted` on "모양 좋아요. 계속해 주세요."; rod-in-out and no-tip made prototypes without the Phase 4 question; STL + core 3MF + bundle; finalize `--deliver` | "시험 출력을 하지 않아서 아직 시제품입니다." rod-in-out, no-tip "확인 안 됨(시제품)"; rod-upright "모델에서 확인됨"; the look "그대로 받으신 걸로 기록했어요"; socket may be tight or loose; ends with an English "(Coordinator note, not for the user: …)" | `use` not verified, `geometry` verified; rod-in-out not verified (prototype), rod-upright verified, no-tip not verified (prototype), flat-disk-look excluded | Differs: Korean throughout (English coordinator notes in three messages, the delivery included); the look promise excluded on a look approval, not the user's agreement; no-tip a prototype the user did not agree to |
| holes-unknown | | Codex | | | | | | |
| bambu-template | `bambu-template.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | A–D, plus rod length and a stop lip (fallback); concept pick; use list and table; base-shape look; test print offer, a look at the redrawn image and "얇은 벽 알림을 그대로 둘까요?" (fallback) | `printers.json` holes `model` (Bambu's public profiles fetched with curl); a three-arm spring cup gripping by 0.15 mm modelled interference, +0.15 mm radial model compensation on the grip circle, fit `--max-interference 2.5 --min-clearance 0`; `_verify.accepted` "cap P3" on the fallback; flat-end a prototype after rebuilds staled both looks; made its Blender export deterministic; deleted the offered test-print project; `bambu3mf.py` project + STL + bundle; finalize `--deliver` | "시험 출력을 하지 않고 진행하기로 하셔서 시제품으로 드려요"; on-off-by-hand, stays-on, flat-end "확인 안 됨(시제품)"; spring-arms "가정이 맞으면 성립"; "얇은 벽 알림은 맡겨 주셔서 그대로 뒀어요"; slicing and print not done | `use` not verified, `geometry` verified; on-off-by-hand, stays-on, flat-end not verified (prototype), spring-arms assumed; 3MF names PLA Basic and 0.20mm Standard | Differs: the fallback recorded as the user's acceptance of the thin-wall warning; flat-end a prototype the user did not agree to. The socket-size item is n/a for this interference grip (the compensation was added) |
| bambu-template | | Codex | | | | | | |
| change-request | `change-request.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Nothing | Read development.md's scenario rows first; `back_h` 90 and `expect` [49, 19, 90]; rebuilt (Python engine); fit, member and lip renewed with the same links; new `deliver/2026-10-23` (`bambu3mf.py` project + STL + bundle); 2026-10-20 delivery and unrelated files byte-identical; `out/bambu_job.json` rewritten; no look stop | Three promises "확인했어요", each with what showed it; "새 폴더에 넣었고, 10월 20일 버전은 그대로 두었어요" | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches. Should missed: no look at the taller holder. Confounded: the agent read this row in development.md |
| change-request | | Codex | | | | | | |
| unattended | `unattended.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Once: the case's model or caliper size (with a cover? an optional cable hole) | References, concepts and table alone; `printers.json` MK4/PrusaSlicer; `petg_basic`; dims caliper/user 62 × 28 × 48; Blender stand, proxy fits seated and lifting out, two measurements, renewed after a rebuild changed the STL; 17 `_assumptions` lines, none for the base-shape look taken alone; STL + core 3MF + bundle; finalize `--deliver` | Opens "재 주신 크기 …로 거치대를 완성했어요 … 모델 검사는 모두 통과했습니다"; both promises "모델에서 확인됨"; what it decided alone comes third; "아직 직접 보신 적은 없어요" | `use` verified, `geometry` verified; case-stand, finger-notch verified | Differs: `_assumptions` does not record the base-shape look taken alone; the last message does not open with what was decided alone |
| unattended | | Codex | | | | | | |
| A (a-kept-broken) | `a-kept-broken.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Nothing | Read the failing fit report (no finalize on the found state); gap derived from the plug, 13.4 + 2 × 0.3 = 14.0 mm, `expect` [50, 19, 70]; rebuilt; fit at the new placement, member and lip renewed; finalize verified before any delivery file; `bambu3mf.py` project (brim, 4 walls) + STL + bundle | "어제 재 주신 플러그가 13.4 mm로, 두 받침 사이 틈(13.0 mm)보다 넓어서 들어가지 않는 상태였습니다. 그래서 틈을 … 14.0 mm로 넓혔습니다"; three "확인됨" lines with what showed each; the tape not checked | `use` verified, `geometry` verified; seat, cable-out, holds verified | Matches. Should missed: the wider holder not shown before delivering |
| A (a-kept-broken) | | Codex | | | | | | |
| A2 (a2-unmeasured) | `a2-unmeasured.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Measure the plug (recommended), a test piece, or go on with it assumed | finalize first (cable-out assumed); after the reply dims caliper/user 12.4/6.6/23.0 in params.json and `usb_c_plug.json`; gap widened 13.0 → 13.4 mm; proxy and holder rebuilt, fit at 18.5,6.2,−17.0, member and lip renewed; `bambu3mf.py` project + STL + bundle | "약속한 세 가지가 모두 확인돼서"; cable-out checked against the measured plug at rest, "케이블이 휘는 모양까지 본 건 아니에요" | `use` verified, `geometry` verified; seat, cable-out, holds verified; usb-c-plug measured | Matches |
| A2 (a2-unmeasured) | | Codex | | | | | | |
| C (c-param-changed) | `c-param-changed.md` @ 8a663aa | Claude Code-based harness subagent, claude-opus-5-5 | 1a9acb8 | Nothing | `base_t` 6.5 (params.json and the generator's default); rebuilt; fit at z −15.5, `strength.py --from-build` with the same links (SF 9.1, every input linked), lip ≥ 12.0; delivered, deleted that unshown delivery and delivered again with a brim | "6 mm 때 확인한 결과는 쓰지 않았습니다"; three "확인됨"; prong "약 9.1배 … 6 mm일 때는 7.75배였습니다", plus its own estimate that default infill still leaves enough | `use` verified, `geometry` verified; seat, cable-out, holds verified; member `h` base_t 6.5 | Matches |
| C (c-param-changed) | | Codex | | | | | | |

## Claude runs: setting and confounds

The nine Claude runs (2026-10-23) used the skill at 1a9acb8 (main, installed in the release
layout) and the kit at 8a663aa; each scenario was run by a separate Claude Code-based harness
subagent (claude-opus-5-5) on Linux with Python 3.13 and bpy 5.2.2, web search on; the session
lead played the user from the scripts, and a separate agent graded the runs. In that harness the
user saw only the last message of each turn: notes the agents wrote between tool calls (English
in seven runs) were not shown and are not graded; the English "(Coordinator note …)" blocks in
holes-unknown were inside messages the user saw and are graded.

Known confounds, found during the runs (facts, not excuses for a result):

- The run agents had the skill owner's account memory in their context; it names a Bambu Lab
  X2D and Bambu Studio. Codex runs will not.
- `references/development.md`, which ships with the skill, holds the scenario rows. The
  change-request agent read them (lines 110–140) before acting and cited "the change-request
  scenario expects a new delivery"; the other eight did not read the file.
- Blender-built STLs were not byte-deterministic at this commit (the triangle order changed
  between identical builds), so a rebuild made `seen` entries and other evidence stale.
  given-answers, holes-unknown, bambu-template and unattended built with Blender; in
  holes-unknown and bambu-template the stale looks led to the exclusion and the prototype graded
  there. This is being fixed separately.

