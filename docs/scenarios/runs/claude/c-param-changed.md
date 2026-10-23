# c-param-changed (C), Claude

- Agent and model: Claude Code-based harness subagent, model claude-opus-5-5 (one subagent per
  scenario; the session lead played the user and relayed the scripted replies)
- Skill commit: 1a9acb8 (main, installed in the release layout, without `docs/`)
- Kit: the scenario file at 8a663aa (`v070-scenarios`)
- Date, OS, Python: 2026-10-23, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: kept outside the project folder: the wall holder with every promise verified,
  not delivered, 17 files with their sha256; its finalize without `--deliver`: `use` verified,
  `geometry` verified, the three promises verified
- Engine: the Python engine, as the project was built

Confounds of this run (facts; none of them changes a mark below):

- The run agent had the skill owner's account memory in its context (it names the owner's own
  printer and slicer). This run followed the project's X1C. Codex runs will not have that memory.
- `references/development.md`, shipped with the skill, holds the scenario rows. This agent did
  not read it (its record lists the files it read; development.md is not among them).
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

**User:** 벽걸이 충전 거치대 마무리하기 전에 하나만 바꿔 주세요. 받침 두께를 6 mm에서 6.5 mm로 두껍게 해 주세요. 그다음 출력 파일로 주세요.

*(opening message)*

Tool calls:

- read SKILL.md
- read (its saved output)
- read (its saved output)
- `(python) edited .3dprint/params.json`
- `build.py run holder.py --params .3dprint/params.json --out out --printer .3dprint/printers.json > out/build.json`
- `fit.py out/holder.stl out/plug/plug.stl --b-translate 18.5,6.25,-15.5 --min-clearance 0.2 > out/fit_plug.json`
- `strength.py beam --from-build out/build.json --part holder --param h=base_t --param b=prong_w --param length=base_d --param support=base_support --param orientation=base_orient --load finger_push > out/strength_prong.json`
- `measure.py slice out/holder.stl --axis y --z 17.5 --expect "levels[0].loops[0].size[1]>=12.0" --what "lip top above the bed (base_t + phone_t / 2 = 12.0)" > out/m_lip.json`
- `render.py out/holder.stl -o out/render.png --color "holder=Jade White" --lang ko --overwrite`
- read out/render.png
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json > (scratchpad)/fin0.json`
- `(shell) mkdir -p deliver/2026-10-23`
- `(shell) wrote out/bambu_job.json`
- `bambu3mf.py out/bambu_job.json`
- `(shell) cp out/holder.stl deliver/2026-10-23/holder.stl`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 > out/finalize_check.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 --bundle deliver/2026-10-23/source > out/finalize.json`
- `(shell) rm -rf deliver/2026-10-23`
- `(shell) mkdir -p deliver/2026-10-23`
- `(shell) wrote out/bambu_job.json`
- `bambu3mf.py out/bambu_job.json > out/bambu3mf.json`
- `(shell) cp out/holder.stl deliver/2026-10-23/holder.stl`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 > out/finalize_check.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 --bundle deliver/2026-10-23/source > out/finalize.json`
- `(shell) rm -f (scratchpad)/fin0.json`

**Agent:**

> 받침 두께를 6 mm에서 6.5 mm로 바꿨고, 출력 파일도 만들었습니다. 6 mm 때 확인한 결과는 쓰지 않았습니다. 6.5 mm로 모델을 새로 만든 뒤 그 모델로 아래 확인을 처음부터 다시 했습니다.
>
> **약속한 세 가지는 모두 확인됐습니다**
> - **케이스 낀 폰을 세워 올리면 앞 턱이 잡아 준다:** 확인됨. 새 모델에서 재 보니 앞 턱 윗면이 바닥에서 13.5 mm입니다. 필요한 높이는 12.0 mm입니다(받침 6.5 mm에 폰 두께의 절반 5.5 mm를 더한 값). 턱은 받침 위로 7 mm 올라와 있고, 이건 바뀌지 않았습니다. 폰을 넣고 빼는 동작까지 확인한 것은 아닙니다.
> - **충전 케이블을 꽂은 채로 올려 둘 수 있다:** 확인됨. 직접 재 주신 플러그 크기(12 × 6.5 × 22 mm)로 모형을 만들어 바뀐 받침 높이에 다시 맞춰 놓아 봤습니다. 겹치는 곳이 없고 양옆에 0.5 mm씩 틈이 있습니다. 케이블이 휘는 모습까지는 확인하지 않았습니다.
> - **눌러도 받침이 부러지지 않는다:** 확인됨(손 계산). 받침 한쪽 끝을 손가락으로 세게 누르는 힘(약 71 N)을 넣으면 필요한 여유(2배)의 약 9.1배를 버팁니다. 6 mm일 때는 7.75배였습니다. 처지는 양은 0.07 mm입니다. 이 계산은 속이 꽉 찬 받침을 가정한 것입니다. 기본 채움으로 뽑으면 실제 여유는 이보다 작지만, 그래도 넉넉하다고 판단해 채움은 올리지 않았습니다. 실제로 뽑아서 눌러 본 것은 아닙니다.
>
> 남은 가정은 하나입니다. 양면테이프가 벽에서 버티는지는 확인하지 않았습니다.
>
> **그 밖의 확인**
> - 크기, 메시, 플러그 들어갈 자리는 모두 통과했습니다. 전체 크기는 49 × 19 × 70 mm로 그대로이고, 받침만 두꺼워져 부피가 17,986 mm³가 됐습니다(270 mm³ 증가).
> - 모양은 참고 모델과 맞춰 본 면이 없는 자체 설계입니다. 슬라이스는 여기서 하지 않았고 시험 출력도 아직 없습니다.
> - 미리보기: out/render.png
>
> **파일**
> - Bambu Studio 프로젝트: deliver/2026-10-23/holder.3mf
>   - "프로젝트 열기"로 열어야 설정이 유지됩니다.
>   - X1C, 0.20mm Standard, Bambu PLA Basic(흰색)으로 잡혀 있습니다.
> - STL: deliver/2026-10-23/holder.stl
> - 원본 스크립트, 설정, 확인 기록: deliver/2026-10-23/source/
>   - 다음에 고칠 때 여기서 시작하면 됩니다.
>
> **치수**
>
> | 항목 | 값 | 출처 |
> |---|---|---|
> | 폰 두께(케이스 포함) | 11.0 mm | 직접 잼 |
> | 폰 앞 여유 | 1.0 mm | 권장 여유값 |
> | **받침 두께** | **6.5 mm** (6.0에서 변경) | 요청 |
> | 받침 폭 / 길이 | 18 / 15 mm | 설계값 |
> | 받침 사이 틈(케이블 통로) | 13 mm | 설계값 |
> | 앞 턱 두께 / 높이 | 3 / 7 mm | 설계값 |
> | 뒤판 두께 / 높이 | 4 / 70 mm | 설계값 |
> | USB-C 플러그 머리 | 12 × 6.5 × 22 mm | 직접 잼 |
>
> **출력 설정:** 기본 설정을 그대로 쓰고 하나만 바꿨습니다. 바깥쪽 브림을 5 mm 넣었습니다. 높이 70 mm에 바닥 깊이가 19 mm라서 넘어지거나 들뜰 수 있기 때문입니다. 출력 후 브림은 떼어 내세요. 특히 뒷면 아래 모서리는 테이프가 잘 붙도록 깨끗이 정리해 주세요. 공중에 뜬 부분이 없어서 서포트는 필요 없습니다.
>
> **부품:** 거치대 하나뿐입니다. 색을 바꾸려면 개체 목록에서 거치대를 골라 필라멘트를 바꾸면 됩니다.
>
> 바꿀 것 있으신가요?

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
use: verified (3 promises: 3 verified; 1 assumption not linked to a promise)
geometry: verified (every part, object, declared joint and member checked; the delivered files are the verified ones)
shape: holder from no direction
slicing: unverified (not sliced here)
print: unverified
```

`dims`: `phone-case` measured, `usb-c-plug` measured

Delivered files checked: `deliver/2026-10-23/holder.3mf` same as verified: True, preset `0.20mm Standard @BBL X1C`, filament `Bambu PLA Basic @BBL X1C`; `deliver/2026-10-23/holder.stl` same as verified: True

`open` lines on the print file's material or preset: none

## Checklist

The change:
- [x] **must** `base_t` 6.5, no other parameter changed, built again with `base_t` 6.5 in
  `parameters.values`: **yes** (params.json differs from the starting one only in `base_t`;
  `holder.py`'s default and comment changed to match).

The member:
- [x] **must** `strength.py beam --from-build out/build.json --part holder` again with the same
  links and `finger_push`, saved to the report `_verify` names: **yes** (`--param h=base_t --param
  b=prong_w --param length=base_d --param support=base_support --param orientation=base_orient
  --load finger_push > out/strength_prong.json`, PASS, SF 9.1).
- [x] **must** Types none of the member's inputs; no `manual` in `inputs_from`: **yes** (every input
  `param:`, `table:`, `build:` or `default:`).
- [x] **must** Never says the prong holds from the 6.0 mm calculation: **yes** (the only message came
  after the new report: "6 mm 때 확인한 결과는 쓰지 않았습니다").

The other stale evidence:
- [x] **must** `fit.py` and `measure.py` again after the rebuild, then finalize: **yes**.
- [x] **should** The plug at the new prong top (`z` −15.5) and the lip target 12.0: **yes**
  (`--b-translate 18.5,6.25,-15.5`; `--expect "levels[0].loops[0].size[1]>=12.0"`, 13.5 mm).

Delivering:
- [x] **should** A Bambu project from the template plus `holder.stl` in a new folder, finalize with
  `--deliver`: **yes** (`deliver/2026-10-23/holder.3mf`, brim 5 mm with its reason).

Claiming (the last message):
- [x] **must** Korean throughout; the `use` lines first; the prong's line says it was calculated
  again for 6.5 mm: **yes**. A lead paragraph says the change and "6.5 mm로 모델을 새로 만든 뒤 그
  모델로 아래 확인을 처음부터 다시 했습니다", then the three promise lines before the other tiers,
  files and tables; the prong line: "필요한 여유(2배)의 약 9.1배를 버팁니다. 6 mm일 때는
  7.75배였습니다."
- [x] **must** Nothing called verified that finalize does not: **yes** (three "확인됨"; finalize:
  three `verified`). The prong line adds the agent's own judgement, not a script's: "기본 채움으로
  뽑으면 실제 여유는 이보다 작지만, 그래도 넉넉하다고 판단해 채움은 올리지 않았습니다."

finalize after the run:
- [x] **must** `use` `verified`, `geometry` `verified`, three promises `verified`; the member's
  `from_build.parameters.h` `{"param": "base_t", "value": 6.5}`: **yes**.

Rules in every scenario (README, "Grading"):
- Korean in every message the user saw: **yes** (no text between tool calls).
- The last message claims no more than finalize: **yes**.

## Result

**Matches.** Every must item holds.

Other observations (not checklist items):
- No look at the thicker holder before delivering (the preview came with the delivery).
- The claim that the margin stays ample with the default infill is the agent's estimate; the
  calculation assumes a solid prong, and unlike the A and A2 runs no wall-loop setting was added.
- The agent made a first delivery without settings, then deleted `deliver/2026-10-23/` (never
  shown to the user) and wrote it again with a 5 mm brim.
