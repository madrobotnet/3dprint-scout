# change-request, Claude

First pass, graded at skill 1a9acb8 and kit 8a663aa; the re-run at e2f7953 is [`change-request.md`](change-request.md).

- Agent and model: Claude Code-based harness subagent, model claude-opus-5-5 (one subagent per
  scenario; the session lead played the user and relayed the scripted replies)
- Skill commit: 1a9acb8 (main, installed in the release layout, without `docs/`)
- Kit: the scenario file at 8a663aa (`v070-scenarios`)
- Date, OS, Python: 2026-10-23, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: kept outside the project folder: the wall holder delivered on 2026-10-20, 34
  files with their sha256; its finalize with `--deliver deliver/2026-10-20`: `use` verified,
  `geometry` verified, `seat`, `cable-out`, `holds` verified
- Engine: the Python engine, as the project was built (the agent kept it, with `--engine python`)

Confounds of this run (facts; none of them changes a mark below):

- The run agent had the skill owner's account memory in its context (it names the owner's own
  printer and slicer). Its record says it followed the project's X1C. Codex runs will not have
  that memory.
- `references/development.md`, shipped with the skill, holds the scenario rows. **This agent read
  it** (lines 110–140, the conversation checks, after searching the references for "change
  request", "new version", "redeliver") and its record cites it: "the change-request scenario
  expects a new delivery". It saw this scenario's expected behaviour before acting.
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

**User:** 지난번에 받은 벽걸이 충전 거치대 말인데요, 뒤판을 지금보다 20 mm 높여서 90 mm로 해 주세요. 양면테이프 붙일 자리를 넓히고 싶어요. 나머지는 그대로 두고요.

*(opening message)*

Tool calls:

- read SKILL.md
- read (its saved output)
- `(shell) diff deliver/2026-10-20/source/holder.py holder.py`
- `(shell) diff deliver/2026-10-20/source/params.json .3dprint/params.json`
- read references/phase-0-detect.md
- read references/development.md (lines 110–140)
- read references/phase-3-base-shape.md
- read references/phase-2-printer-dimensions.md (lines 225–260)
- read references/phase-4-features-joints.md
- read references/phase-5-gate.md
- read references/phase-6-deliver.md
- read references/engines/python.md
- read references/bambu-process.md (lines 80–170)
- `build.py detect`
- read .3dprint/params.json, holder.py
- `edit .3dprint/params.json`
- `edit .3dprint/params.json`
- `edit holder.py`
- `build.py run holder.py --engine python --params .3dprint/params.json --out out --printer .3dprint/printers.json > out/build.json`
- `fit.py --check out/fit_plug.json`
- (probes: fit.py --help)
- `fit.py out/holder.stl out/plug/plug.stl --b-translate 18.5,6.25,-16 --min-clearance 0.2 > out/fit_plug.json`
- `strength.py beam --from-build out/build.json --part holder --param h=base_t --param b=prong_w --param length=base_d --param support=base_support --param orientation=base_orient --load finger_push > out/strength_prong.json`
- (probes: measure.py --help)
- `measure.py slice out/holder.stl --axis y --z 17.5 --max-loops 12 --expect "levels[0].loops[0].size[1]>=11.5" --what "lip top above the bed (base_t + phone_t / 2 = 11.5)" > out/m_lip.json`
- `render.py out/holder.stl -o out/render.png --lang ko --overwrite`
- read out/render.png
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json > (scratchpad)/runs070_fin1.json`
- `(shell) mkdir -p deliver/2026-10-23`
- `(shell) cp out/holder.stl deliver/2026-10-23/holder.stl`
- `(shell) wrote out/bambu_job.json`
- `bambu3mf.py out/bambu_job.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 > (scratchpad)/runs070_fin2.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 --bundle deliver/2026-10-23/source > (scratchpad)/runs070_fin3.json`
- `(shell) diff deliver/2026-10-20/source/holder.py holder.py`
- `(shell) diff deliver/2026-10-20/source/params.json .3dprint/params.json`

**Agent:**

> 뒤판을 70 mm에서 90 mm로 바꾼 새 버전을 만들었어요. 늘어난 20 mm는 모두 위쪽으로 붙었어요. 아래 끝(받침이 있는 쪽)은 그대로라서 콘센트와의 위치 관계는 전과 같아요. 받침, 앞 턱, 케이블이 지나가는 틈도 바꾸지 않았어요.
>
> 미리보기: out/render.png
>
> **처음에 정한 세 가지 쓰임새: 바뀐 모델로 다시 확인했고, 셋 다 그대로 지켜져요**
> - **폰을 세워 올리면 앞 턱이 잡아 줌 (케이스 포함 11 mm):** 확인했어요. 턱 윗면이 바닥에서 13 mm로, 필요한 11.5 mm(받침 6 mm + 폰 두께의 절반)보다 높아요. 모델에서 높이를 잰 결과이고, 폰을 넣고 빼는 동작까지 본 건 아니에요.
> - **케이블을 꽂은 채로 올려 둘 수 있음:** 확인했어요. 직접 재 주신 플러그 크기(12 × 6.5 × 22 mm)로 모형을 만들어 봤는데, 두 받침 사이로 지나가면서 아무 데도 닿지 않고 양옆에 0.5 mm씩 틈이 남아요. 다만 그 숫자로 만든 모형에 맞춰 본 것이라 숫자가 틀리면 결과도 달라져요. 케이블이 휘는 모습도 보지 않았어요.
> - **받침을 세게 눌러도 부러지지 않음:** 계산으로 확인했어요. 손가락으로 세게 누르는 힘(약 71 N)의 약 7.7배까지 버텨요. 기준은 2배예요. 실제로 출력해서 눌러 본 건 아니에요.
>
> **확인하지 않은 두 가지 (전과 같아요)**
> - **양면테이프가 버티는지:** 확인하지 않았어요. 대신 테이프 붙일 면이 49 × 70에서 49 × 90 mm로 약 29% 넓어졌어요.
> - **콘센트와 뒤판 아래 끝 사이 거리:** 재지 않았어요. 아래 끝은 전과 같으니 붙이던 자리에 그대로 붙이시면 돼요. 다만 위쪽으로 20 mm를 더 차지하니까, 그 자리에 스위치 같은 게 없는지만 한 번 봐 주세요.
>
> 크기와 메시 검사는 모두 통과했어요(49 × 19 × 90 mm). 슬라이스와 시험 출력은 여기서 하지 않았어요.
>
> **파일** (새 폴더에 넣었고, 10월 20일 버전은 그대로 두었어요)
> - Bambu Studio 프로젝트: deliver/2026-10-23/holder_bambu.3mf
>   - "프로젝트 열기"로 여세요.
> - STL: deliver/2026-10-23/holder.stl
> - 다시 만들 때 필요한 원본과 검사 기록: deliver/2026-10-23/source
> - 이전 버전: deliver/2026-10-20 (손대지 않았어요)
>
> **치수**
>
> | 항목 | 값 | 출처 |
> |---|---|---|
> | 뒤판 높이 | **90 mm** (전: 70) | 이번 요청 |
> | 뒤판 두께 | 4 mm | 전과 같음 |
> | 전체 폭 | 49 mm (받침 18 + 틈 13 + 받침 18) | 전과 같음 |
> | 받침 길이 / 두께 | 15 / 6 mm | 전과 같음 |
> | 앞 턱 두께 / 높이 | 3 / 7 mm | 전과 같음 |
> | 폰 두께 (케이스 포함) | 11 mm | 직접 재 주신 값 |
> | 플러그 머리 | 12 × 6.5 × 22 mm | 직접 재 주신 값 |
> | 재료 / 출력 설정 | Bambu PLA Basic, 0.20mm Standard @BBL X1C | 전과 같음 |
> | 출력판 여유 | 256 × 256 mm 판에 49 × 19 mm, 높이 90 / 250 mm | X1C 설정 |
>
> **출력 설정**
> - 전과 같아요. X1C, Bambu PLA Basic, 0.20mm Standard를 그대로 쓰고 따로 바꾼 값은 없어요.
> - 받침이 바닥에 닿게 세운 그대로 출력해요. 튀어나온 부분이 없어서 서포트도 필요 없어요.
> - 높이가 늘어난 만큼 출력 시간과 필라멘트(부피 17.7에서 21.6 cm³)가 조금 늘어요.
>
> 부품은 한 덩어리라서 색을 나눌 곳은 없어요.
>
> 더 바꿀 곳이 있으면 말씀해 주세요.

*(row: "Delivers the files": the run ends (no stop before it))*

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

Delivered files checked: `deliver/2026-10-23/holder.stl` same as verified: True; `deliver/2026-10-23/holder_bambu.3mf` same as verified: True, preset `0.20mm Standard @BBL X1C`, filament `Bambu PLA Basic @BBL X1C`

`open` lines on the print file's material or preset: none

Every file `setup.py` listed, compared by sha256 after the run:

| File | After the run |
|---|---|
| `holder.py` | changed: `back_h` default 70.0 → 90.0 and its comment, nothing else |
| `plug.py` | same |
| `.3dprint/params.json` | changed: `back_h` 70.0 → 90.0, `_parts.holder.expect` `[49.0, 19.0, 70.0]` → `[49.0, 19.0, 90.0]`, nothing else |
| `.3dprint/printers.json` | same |
| `.3dprint/usb_c_plug.json` | same |
| `.3dprint/templates/x1c.3mf` | same |
| `deliver/2026-10-20/` (16 files: the project, its manifest, the STL, `source/`) | all same; no file added |
| `out/build.json`, `out/holder.stl`, `out/holder.3mf` and their manifests | changed (the rebuild) |
| `out/fit_plug.json`, `out/m_lip.json`, `out/strength_prong.json` | changed (renewed) |
| `out/bambu_job.json` | changed: rewritten to write into `deliver/2026-10-23/` |
| `out/plug/build.json`, `out/plug/plug.stl` and its manifest | same |

New: `deliver/2026-10-23/` (`holder_bambu.3mf` and its manifest, `holder.stl`, `source/`),
`out/render.png` and its sidecar.

## Checklist

The relevant fields:
- [x] **must** `back_h` 90.0, `_parts.holder.expect` `[49.0, 19.0, 90.0]`, built again: **yes**
  (finalize: the holder's `D1` PASS against the new `expect`, the build is of the delivered STL).
- [x] **should** `holder.py` unchanged or only `back_h`'s default and comment: **yes**.

Everything else kept:
- [x] **must** Every other key of params.json keeps its value: **yes** (a key-by-key diff with the
  bundled copy of 2026-10-20 shows only the two changes; no `_assumptions` line was added).
- [x] **must** Byte-identical `plug.py`, `.3dprint/usb_c_plug.json`, `.3dprint/printers.json`,
  `.3dprint/templates/x1c.3mf`: **yes**.
- [x] **must** Byte-identical `deliver/2026-10-20/`, nothing added: **yes**.

The new version:
- [x] **must** A new folder with `holder.stl` and a Bambu project from the template with its
  manifest; a bundle in a new folder: **yes** (`deliver/2026-10-23/`, `bambu3mf.py
  out/bambu_job.json`; bundle `deliver/2026-10-23/source/`).
- [x] **must** After the rebuild `fit.py`, `measure.py`, `strength.py --from-build` with the same
  links, then finalize with `--deliver` on the new folder: **yes** (`fit.py … --b-translate
  18.5,6.25,-16 --min-clearance 0.2`, the member command as setup's, the lip slice `--z 17.5`
  `>=11.5`; finalize with `--deliver deliver/2026-10-23`).
- [x] **must** Does not overwrite the earlier delivery or ask whether it may: **yes**.
- [ ] **should** Shows the taller holder and stops for a look before delivering: **no** (the
  preview `out/render.png` came only with the delivery; the agent's record says it judged the stop
  unnecessary).

Claiming (the last message):
- [x] **must** Korean throughout; the `use` lines first: **yes**. A three-sentence lead on the
  change and the preview path come first, then "**처음에 정한 세 가지 쓰임새: 바뀐 모델로 다시
  확인했고, 셋 다 그대로 지켜져요**" and one line per promise, before the other tiers, files and
  tables.
- [x] **must** Says where the new files are and that the earlier ones are kept: **yes** ("새 폴더에
  넣었고, 10월 20일 버전은 그대로 두었어요"; "이전 버전: deliver/2026-10-20 (손대지 않았어요)").
- [x] **must** Nothing called verified that finalize does not: **yes** (three "확인했어요", each with
  what showed it and what it does not cover; finalize: three `verified`).

finalize after the run:
- [x] **must** `use` `verified`, `geometry` `verified`, the three promises `verified`: **yes**.

Rules in every scenario (README, "Grading"):
- Korean in every message the user saw: **yes**. Two English notes between tool calls ("Stale as
  expected. Now re-running …", "Now confirming the earlier delivery …") were not shown to the
  user in this harness.
- The last message claims no more than finalize: **yes**.

## Result

**Matches.** Every must item holds. Should missed: no look at the taller holder before delivering.
The run is confounded: the agent read this scenario's row in `references/development.md` first.

Other observations (not checklist items):
- `out/bambu_job.json`, the job of the 2026-10-20 project, was rewritten for the new delivery; the
  earlier job is not kept outside that delivery's manifest.
- No `_assumptions` line records why `back_h` changed (the comment in `holder.py` does).
- The agent did not give the one-line Phase 0 report and kept the project's Python engine without
  saying so.
