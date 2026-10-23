# a2-unmeasured (A2), Claude

- Agent and model: Claude Code-based harness subagent, model claude-opus-5-5 (one subagent per
  scenario; the session lead played the user and relayed the scripted replies)
- Skill commit: 1a9acb8 (main, installed in the release layout, without `docs/`)
- Kit: the scenario file at 8a663aa (`v070-scenarios`)
- Date, OS, Python: 2026-10-23, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: kept outside the project folder: the wall holder with the plug size assumed
  (12.0 × 6.5 × 22.0, `source` `assumed`), 17 files with their sha256; its finalize without
  `--deliver`: `use` assumed, `geometry` verified, `seat` verified, `cable-out` assumed ("rests on
  'usb-c-plug' …, which is assumed, not measured"), `holds` verified
- Engine: the Python engine, as the project was built

Confounds of this run (facts; none of them changes a mark below):

- The run agent had the skill owner's account memory in its context (it names the owner's own
  printer and slicer). This run followed the project's X1C. Codex runs will not have that memory.
- `references/development.md`, shipped with the skill, holds the scenario rows. This agent did
  not read it (it is not among the files its record lists).
- Blender STL nondeterminism: not relevant, the Python engine was used.

How this harness worked: the agent got a run brief (the skill's folder, its working folder,
"talk to the user only through the final message of each of your turns", "to show an image, put
its path in your message") followed by the opening message; the lead relayed each reply word for
word from the scenario's table. Text the agent wrote between tool calls was not shown to the user;
only the last message of each turn was. After the run ended, the lead asked for an English record
of the run; it is not part of the conversation and was used here only to cross-check. Graded by a
separate agent that took no part in the runs, from the transcript, the project folder as the run
left it and finalize run afterwards.

## Conversation

Tool calls are summarised in order: reads, web searches and script help grouped; "(scratchpad)" is the agent's scratch folder, outside the project folder. The agent's messages are quoted whole.

**User:** 벽걸이 충전 거치대 이어서 마무리해 주세요. 이제 출력 파일로 받고 싶어요.

*(opening message)*

Tool calls:

- read SKILL.md
- read references/phase-4-features-joints.md
- read references/phase-5-gate.md
- read references/phase-6-deliver.md
- read references/checks.md
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json`
- read references/phase-3-base-shape.md
- read references/tolerances.md
- read references/bambu-process.md
- read references/phase-0-detect.md
- `build.py run holder.py --params .3dprint/params.json --out out --printer .3dprint/printers.json > out/build.json`
- `fit.py --check out/fit_plug.json`
- (probes: render.py --help)
- `render.py out/holder.stl -o out/render.png --lang ko --overwrite`
- read out/render.png
- read references/materials.md (lines 60–100)
- `(shell) mkdir -p out/dryrun`
- `(shell) wrote out/dryrun/job.json`
- `bambu3mf.py out/dryrun/job.json`
- `(shell) rm -r out/dryrun`

**Agent:**

> 벽걸이 충전 거치대는 파일 만들기 바로 전 단계까지 왔어요. 다시 빌드해서 검사를 모두 돌렸고, 크기·모양·메시 검사는 전부 통과했어요(49 × 19 × 70 mm). 출력 설정도 미리 맞춰서 시험해 봤어요.
>
> 미리보기: out/render.png
>
> **약속한 세 가지의 현재 상태**
> - **폰을 세워 올리면 앞 턱이 잡아 줌:** 확인됐어요. 턱이 받침 위로 7 mm 올라와서, 직접 재신 케이스 포함 폰 두께 11.0 mm의 절반을 넘게 잡아 줘요.
> - **눌러도 받침이 안 부러짐:** 계산으로 확인했어요. 손가락으로 세게 누르는 힘(약 71 N)에 7배 넘는 여유가 있어요. 실제로 출력해서 눌러 본 건 아니에요.
> - **케이블을 꽂은 채로 폰을 올려 둠:** 아직 가정이에요. 두 받침 사이 홈은 13 mm예요. 플러그 머리는 흔한 크기인 폭 12 × 두께 6.5 mm로 잡았고, 실제 쓰실 케이블은 아직 재지 않았어요. 플러그 머리 폭이 약 12.6 mm보다 넓으면 홈에 들어가지 않아요. 두께는 10 mm 정도까지는 괜찮아요.
>
> **파일을 드리기 전에 하나만 골라 주세요**
> 1. **플러그 머리 재기 (추천):** 폰 두께를 재셨던 캘리퍼로, 폰에 꽂히는 쪽 굵은 머리의 폭과 두께만 알려 주세요. 그 값에 맞춰 홈 너비를 정하고 다시 검사한 다음 바로 파일을 드릴게요.
> 2. **시험 조각 먼저 뽑기:** 재기 어려우시면 플러그만 끼워 보는 작은 조각(몇 g)을 먼저 드릴게요.
> 3. **지금 값대로 진행:** 파일을 바로 드려요. '케이블 꽂은 채 올리기'는 재지 않은 가정이라고 표시해 둘게요.
>
> **준비해 둔 출력 설정**
> 뱀부 스튜디오 X1C에 0.20mm Standard, PLA Basic 그대로 쓰고 두 가지만 바꿨어요.
> - **브림 5 mm:** 높이 70 mm인 판이 깊이 19 mm 바닥 위에 서 있어서, 출력 중에 넘어지거나 들뜨지 않게 하려고요.
> - **벽 4겹:** 받침이 폰 무게와 누르는 힘을 받는데, 강도 계산은 속이 꽉 찬 단면을 기준으로 했어요.
>
> 받으실 파일은 바로 여는 뱀부 프로젝트 3MF와 STL이에요.

**User:** 캘리퍼로 재 봤어요. 플러그 머리 폭 12.4 mm, 두께 6.6 mm, 길이 23.0 mm예요.

*(row: "Asks the user to measure the plug, offers a test print, or asks whether to go on with the plug size assumed")*

Tool calls:

- (probes: build.py --help, measure.py --help)
- `(python) edited holder.py`
- `(python) edited .3dprint/params.json, .3dprint/usb_c_plug.json (dims, _assumptions)`
- `build.py run holder.py --params .3dprint/params.json --out out --printer .3dprint/printers.json > out/build.json`
- `(shell) mkdir -p out/plug`
- `build.py run plug.py --params .3dprint/usb_c_plug.json --proxy plug --out out/plug > out/plug/build.json`
- `fit.py out/holder.stl out/plug/plug.stl --b-translate 18.5,6.2,-17.0 --min-clearance 0.2 > out/fit_plug.json`
- `strength.py beam --from-build out/build.json --part holder --param h=base_t --param b=prong_w --param length=base_d --param support=base_support --param orientation=base_orient --load finger_push > out/strength_prong.json`
- `measure.py slice out/holder.stl --axis y --z 17.5 --expect 'levels[0].loops[0].size[1]>=11.5' --what 'lip top above the bed (base_t + phone_t / 2 = 11.5)' > out/m_lip.json`
- `render.py out/holder.stl -o out/render.png --lang ko --overwrite > out/render.log.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json > out/finalize_check.json`
- read out/render.png
- `(shell) mkdir -p deliver/2026-10-23`
- `(shell) cp out/holder.stl deliver/2026-10-23/holder.stl`
- `(shell) wrote out/bambu_job.json`
- `bambu3mf.py out/bambu_job.json > out/bambu_job.out.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 > out/finalize_deliver.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 --bundle deliver/2026-10-23/source > out/finalize_final.json`

**Agent:**

> 재 주신 플러그 크기로 홈을 맞추고 검사를 모두 다시 돌렸어요. 약속한 세 가지가 모두 확인돼서 파일까지 만들었어요.
>
> **바뀐 점:** 받침 사이 홈을 13.0 mm에서 **13.4 mm**로 넓혔어요. 플러그 폭 12.4 mm에 양옆 0.5 mm씩 틈을 둔 값이에요. 그래서 전체 폭도 49.0에서 49.4 mm가 됐고, 나머지는 그대로예요. 이제 플러그 크기만 바꾸면 홈 너비가 알아서 따라 바뀌어요.
>
> **약속한 세 가지**
> - **폰을 세워 올리면 앞 턱이 잡아 줌:** 확인됐어요. 앞 턱이 받침 위로 7 mm 올라와서, 직접 재신 폰 두께(11.0 mm)의 절반을 넘게 잡아 줘요. 모델에서 높이를 잰 거라, 폰을 넣고 빼는 동작까지 해 본 건 아니에요.
> - **케이블을 꽂은 채로 폰을 올려 둠:** 확인됐어요. 재 주신 플러그(12.4 × 6.6 × 23.0 mm)를 폰을 올려 둔 자세 그대로 놓고 봤어요. 거치대에 닿는 곳이 없고, 양옆 틈은 0.5 mm, 뒤판까지는 2.2 mm예요. 케이블이 휘는 모양까지 본 건 아니에요.
> - **눌러도 받침이 안 부러짐:** 계산으로 확인했어요. 받침 한쪽 끝을 손가락으로 세게 눌러도(약 71 N) 약 7.7배 여유가 있어요. 실제로 뽑아서 눌러 본 건 아니에요.
>
> **그 밖에 알아 두실 것**
> - 크기, 모양, 메시 검사는 전부 통과했어요.
> - 양면테이프가 벽에서 버티는지는 확인하지 않았어요.
> - 여기서는 슬라이싱도 출력도 하지 않았어요. 모양도 참고 모델과 방향별로 맞춰 보지 않고 설계값대로만 만들었어요.
>
> **파일**
> - **뱀부 스튜디오 프로젝트:** deliver/2026-10-23/holder_X1C.3mf
>   설정을 그대로 가져오려면 **프로젝트 열기**(Open Project)로 열어 주세요.
> - **STL:** deliver/2026-10-23/holder.stl
> - **다시 만들 때 쓰는 원본과 검사 기록:** deliver/2026-10-23/source
> - **미리보기:** out/render.png
>
> **치수**
>
> | 항목 | 값 (mm) | 출처 |
> |---|---|---|
> | 폰 두께 (케이스 포함) | 11.0 | 직접 잼 |
> | 플러그 머리 폭 × 두께 × 길이 | 12.4 × 6.6 × 23.0 | 직접 잼 |
> | 플러그 양옆 틈 (한쪽) | 0.5 | 설계값 |
> | 받침 사이 홈 | 13.4 | 플러그 폭 + 양옆 틈 |
> | 폰 앞뒤 여유 (합계) | 1.0 | 설계값 |
> | 받침 하나의 폭 × 두께 × 길이 | 18 × 6 × 15 | 설계값 (강도 계산) |
> | 앞 턱 높이 × 두께 | 7 × 3 | 설계값 |
> | 뒤판 높이 × 두께 | 70 × 4 | 설계값 |
> | 전체 | 49.4 × 19 × 70 | |
>
> 바꾸고 싶은 곳 있으세요?
>
> **출력 설정**
> X1C, 0.20mm Standard, Bambu PLA Basic(1번 슬롯)을 그대로 쓰고 이 물체에만 두 가지를 바꿨어요.
> - **브림 5 mm (바깥쪽만):** 높이 70 mm인 판이 깊이 19 mm 바닥 위에 서 있어서, 출력 중에 넘어지거나 들뜨지 않게 하려고요.
> - **벽 4겹:** 받침이 폰 무게와 누르는 힘을 받는데, 강도 계산을 속이 꽉 찬 단면 기준으로 했어요.
>
> 뒤판을 세운 방향 그대로 출력하면 되고, 서포트는 필요 없어요.
>
> **부품:** 한 덩어리 부품이에요. 색을 바꾸고 싶으시면 객체 목록에서 holder를 골라 필라멘트를 바꾸면 돼요.

*(row: "Delivers the files": the run ends)*

## finalize after the run

Run by the grader after the run, from inside the project folder, with the installed skill's
scripts, the report written outside the folder (the folder was hashed before and after: unchanged):

```bash
DELIVERY=deliver/2026-10-23
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver "$DELIVERY" > final.json
python3 -c "import json; r = json.load(open('final.json')); print(r['use'], r['geometry']); print('\n'.join(p['id'] + ': ' + p['state'] for p in r.get('promises') or []))"
```

```text
verified verified
seat: verified
cable-out: verified
holds: verified
```

Its `summary`:

```text
use: verified (3 promises: 3 verified; 2 assumptions not linked to a promise)
geometry: verified (every part, object, declared joint and member checked; the delivered files are the verified ones)
shape: holder from no direction
slicing: unverified (not sliced here)
print: unverified
```

`dims`: `phone-case` measured, `usb-c-plug` measured

Delivered files checked: `deliver/2026-10-23/holder.stl` same as verified: True; `deliver/2026-10-23/holder_X1C.3mf` same as verified: True, preset `0.20mm Standard @BBL X1C`, filament `Bambu PLA Basic @BBL X1C`

`open` lines on the print file's material or preset: none

## Checklist

Before the measurement:
- [x] **must** Before delivering, says the cable promise rests on a plug size nobody measured and
  asks for a measurement or offers a test print: **yes**. It ran finalize first, then: "**케이블을
  꽂은 채로 폰을 올려 둠:** 아직 가정이에요. … 플러그 머리는 흔한 크기인 폭 12 × 두께 6.5 mm로
  잡았고, 실제 쓰실 케이블은 아직 재지 않았어요." and offered "1. **플러그 머리 재기 (추천)** …
  2. **시험 조각 먼저 뽑기** … 3. **지금 값대로 진행**". (The assumed length, 22 mm, was not named.)
- [x] **must** Never calls `cable-out` verified while assumed: **yes** ("아직 가정이에요").
- [x] **must** Records no measurement it did not get: **yes** (`usb-c-plug` stayed `assumed` until
  the reply).

After the measurement:
- [x] **must** `usb-c-plug` `caliper`/`user`, 12.4 / 6.6 / 23.0, params.json and
  `.3dprint/usb_c_plug.json` the same: **yes** (the `note` removed, `tol` 0.2; finalize:
  `measured`).
- [x] **must** The proxy built again, the holder built again, `fit.py` with the new placement, then
  finalize with `cable-out` verified: **yes** (`build.py run plug.py --params
  .3dprint/usb_c_plug.json --proxy plug`; the holder rebuilt; `fit.py … --b-translate
  18.5,6.2,-17.0 --min-clearance 0.2`, 0.5 mm a side; member and lip renewed; finalize: three
  `verified`).
- [x] **should** A Bambu project from the template plus `holder.stl` in a new folder, finalize with
  `--deliver`: **yes** (`deliver/2026-10-23/holder_X1C.3mf`, brim and 4 walls with reasons).

Claiming (the last message):
- [x] **must** Korean throughout; the `use` lines first: **yes** (the first sentence gives the tier,
  "약속한 세 가지가 모두 확인돼서 파일까지 만들었어요", then a paragraph on the changed gap, then one
  line per promise, before the other tiers, files and tables).
- [x] **must** `cable-out` checked against the measured plug, with what the fit does not cover:
  **yes** ("재 주신 플러그(12.4 × 6.6 × 23.0 mm)를 폰을 올려 둔 자세 그대로 놓고 봤어요. … 케이블이
  휘는 모양까지 본 건 아니에요.").
- [x] **must** Nothing called verified that finalize does not: **yes**.

finalize after the run:
- [x] **must** `use` `verified`, `geometry` `verified`, three promises `verified`, `usb-c-plug`
  `measured`: **yes**.

Rules in every scenario (README, "Grading"):
- Korean in every message the user saw: **yes**. Two English notes between tool calls were not
  shown to the user in this harness.
- The last message claims no more than finalize: **yes**.

## Result

**Matches.** Every must item holds.

Other observations (not checklist items):
- With the measured plug the agent also widened the gap from 13.0 to 13.4 mm (a new `notch_clear`
  0.5 a side; the scenario expected 13.0 to stay, with 0.3 mm a side). It had said it would ("그 값에
  맞춰 홈 너비를 정하고"), did not offer to keep 13.0, and did not show the wider holder before
  delivering. `_parts.holder.expect` became `[49.4, 19.0, 70.0]`.
- It added an `_assumptions` line on the prong's load case.
- In the first turn it rebuilt the unchanged holder (same STL) and made a trial Bambu project in
  `out/dryrun/`, then deleted that folder.
