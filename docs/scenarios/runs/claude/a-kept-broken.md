# a-kept-broken (A), Claude

- Agent and model: Claude Code-based harness subagent, model claude-opus-5-5 (one subagent per
  scenario; the session lead played the user and relayed the scripted replies)
- Skill commit: 1a9acb8 (main, installed in the release layout, without `docs/`)
- Kit: the scenario file at 8a663aa (`v070-scenarios`)
- Date, OS, Python: 2026-10-23, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: kept outside the project folder: the wall holder with the measured plug
  (13.4 × 6.8 × 24.0) failing its fit, 17 files with their sha256; its finalize without
  `--deliver`: `use` failed, `geometry` not verified, `seat` verified, `cable-out` failed
  ("joint 'plug through notch' failed"), `holds` verified
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

**User:** 어제 하던 벽걸이 충전 거치대 이어서 해 주세요. 어제 충전 플러그를 재서 알려 드렸죠. 이제 출력 파일로 받고 싶어요.

*(opening message)*

Tool calls:

- read SKILL.md
- read (its saved output)
- read references/phase-4-features-joints.md, references/tolerances.md, references/phase-3-base-shape.md, references/phase-5-gate.md, references/phase-6-deliver.md, references/bambu-process.md, references/checks.md
- `build.py detect`
- (probes: fit.py --help, measure.py --help)
- read references/materials.md (lines 60–95)
- read holder.py, .3dprint/params.json
- `edit holder.py`
- `edit .3dprint/params.json`
- `edit .3dprint/params.json`
- `build.py run holder.py --params .3dprint/params.json --out out --printer .3dprint/printers.json > out/build.json`
- `fit.py out/holder.stl out/plug/plug.stl --b-translate 18.3,6.1,-18 --min-clearance 0.3 > out/fit_plug.json`
- `strength.py beam --from-build out/build.json --part holder --param h=base_t --param b=prong_w --param length=base_d --param support=base_support --param orientation=base_orient --load finger_push > out/strength_prong.json`
- `measure.py slice out/holder.stl --axis y --z 17.5 --expect "levels[0].loops[0].size[1]>=11.5" --what "lip top above the bed (base_t + phone_t / 2 = 11.5)" > out/m_lip.json`
- (probes: render.py --help)
- `render.py out/holder.stl -o out/preview.png --lang ko --views iso,front,right,top`
- `(shell) mkdir -p views`
- read (scratchpad)/views/v0.png, (scratchpad)/views/v1.png, (scratchpad)/views/v2.png, (scratchpad)/views/v3.png
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json > (scratchpad)/fin1.json`
- (probes: bambu3mf.py --help)
- `(shell) mkdir -p deliver/2026-10-23`
- `(shell) wrote out/bambu_job.json`
- `bambu3mf.py out/bambu_job.json`
- `(shell) cp out/holder.stl deliver/2026-10-23/holder.stl`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 > (scratchpad)/fin2.json`
- `finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver deliver/2026-10-23 --bundle deliver/2026-10-23/source > (scratchpad)/fin3.json`

**Agent:**

> 출력 파일을 만들었습니다. 그런데 어제 재 주신 플러그가 13.4 mm로, 두 받침 사이 틈(13.0 mm)보다 넓어서 들어가지 않는 상태였습니다. 그래서 틈을 플러그 폭에 양옆 0.3 mm씩 더한 **14.0 mm**로 넓혔습니다. 전체 폭은 49 mm에서 **50 mm**가 됐고, 나머지 치수는 어제와 같습니다.
>
> **약속한 세 가지는 모두 확인했습니다**
> - **케이스 낀 폰을 세워 올리면 앞 턱이 잡아 준다:** 확인됨. 완성된 모델에서 앞 턱이 받침 위로 7 mm 올라와 있어서, 폰 두께 11 mm의 절반(5.5 mm)보다 높습니다. 폰을 실제로 넣고 빼는 동작까지 확인한 건 아닙니다.
> - **충전 케이블을 꽂은 채로 폰을 올려 둘 수 있다:** 확인됨. 재 주신 플러그 크기(13.4 × 6.8 × 24 mm)로 모형을 만들어 받침 사이에 넣어 봤습니다. 겹치는 곳이 없고 양옆에 0.3 mm씩 틈이 남습니다. 다만 재신 숫자에 맞춰 봤다는 뜻이고, 케이블이 아래로 휘는 모양까지 본 건 아닙니다.
> - **폰을 올리거나 화면을 눌러도 받침이 부러지지 않는다:** 확인됨(손 계산). 손가락으로 세게 누르는 힘(약 71 N)이 받침 한쪽 끝에 걸려도 PLA Basic 기준으로 약 7.7배 여유가 있습니다(기준은 2배). 실제로 출력해서 눌러 본 결과는 아닙니다.
>
> 이와 별개로 확인하지 않은 가정이 하나 있습니다. **양면테이프가 벽에서 버텨 주는지는 확인하지 않았습니다.**
>
> **그 밖의 결과**
> - 크기, 모델 상태, 플러그 끼움 검사를 모두 통과했습니다. 드리는 파일이 바로 검사한 파일입니다.
> - 모양은 참고 사진과 면마다 대조한 게 아니라 추정입니다. 슬라이싱과 시험 출력은 여기서 하지 않았습니다.
> - 미리보기: out/preview.png
>   - 그림에서 "앞"이라고 된 면은 벽에 붙는 뒷면입니다. "위" 그림에서 넓어진 틈이 보입니다.
>
> **파일**
> - deliver/2026-10-23/holder_x1c.3mf
>   - Bambu Studio에서 **프로젝트 열기(Open Project)**로 여세요.
>   - X1C, 0.20mm Standard, Bambu PLA Basic(슬롯 1)이 설정되어 있습니다.
> - deliver/2026-10-23/holder.stl
>   - 다른 프로그램에서 쓸 때 여시면 됩니다.
> - deliver/2026-10-23/source/
>   - 나중에 다시 만들고 다시 확인할 때 쓰는 원본과 검사 기록입니다.
>
> **출력 설정** (이 물체에만 적용했고, 나머지는 0.20mm Standard 그대로입니다)
> - **브림 5 mm(바깥쪽만):** 높이가 70 mm인데 바닥 깊이는 19 mm라서, 출력 중에 들뜨거나 흔들리지 않게 했습니다. 출력이 끝나면 떼어 내세요.
> - **벽 4겹:** 받침이 폰 무게와 누르는 힘을 받습니다. 강도 계산은 속이 꽉 찬 받침을 가정했기 때문에 그에 가깝게 했습니다.
> - **출력 방향:** 파일에 놓인 그대로(뒤판이 서고 받침이 바닥에 닿게) 출력하시면 되고, 서포트는 필요 없습니다.
>
> **부품:** 한 덩어리로 된 부품 하나라서 색을 나눌 곳은 없습니다. 색을 바꾸려면 개체 목록에서 holder를 고르고 필라멘트를 바꾸시면 됩니다.
>
> **치수표**
>
> | 항목 | 값 (mm) | 근거 |
> |---|---|---|
> | 폰(케이스 포함) 두께 | 11.0 | 직접 재신 값 |
> | 폰 앞쪽 여유 | 1.0 | 기기를 넣는 홈에 권장하는 여유 |
> | 받침 두께 / 한쪽 폭 / 길이 | 6.0 / 18.0 / 15.0 | 설계값(강도 계산 대상), 길이 = 폰 + 여유 + 턱 |
> | **받침 사이 틈** | **14.0** (어제 13.0) | 플러그 폭 13.4 + 양옆 0.3 |
> | 앞 턱 두께 / 높이 | 3.0 / 7.0 | 높이는 폰 두께의 절반 이상 |
> | 뒤판 두께 / 높이 | 4.0 / 70.0 | 설계값, 양면테이프 붙는 면 |
> | 플러그 머리 (폭 × 두께 × 길이) | 13.4 × 6.8 × 24.0 | 직접 재신 값 |
> | 전체 크기 | 50 × 19 × 70 | |
>
> 바꾸고 싶은 치수가 있으면 말씀해 주세요. 출력해 보시고 플러그가 잘 들어가는지 알려 주시면 그에 맞춰 조정하겠습니다.

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

Delivered files checked: `deliver/2026-10-23/holder.stl` same as verified: True; `deliver/2026-10-23/holder_x1c.3mf` same as verified: True, preset `0.20mm Standard @BBL X1C`, filament `Bambu PLA Basic @BBL X1C`

`open` lines on the print file's material or preset: none

## Checklist

Finding and saying the failure:
- [x] **must** Before any delivery file, runs finalize or reads the fit report and finds
  `cable-out` failing: **yes**. It read `out/fit_plug.json` (FAIL, 16.32 mm³ overlap) before any
  change; it did not run finalize on the project as found (its record says so).
- [x] **must** Tells the user plainly, in the message that reports it, why the cable promise is not
  kept and that the other two hold, each with what showed it; no script names; never one verdict
  for all three: **yes**. The message that reports it is the delivery (the agent never stopped
  before it): "어제 재 주신 플러그가 13.4 mm로, 두 받침 사이 틈(13.0 mm)보다 넓어서 들어가지 않는
  상태였습니다. 그래서 틈을 … **14.0 mm**로 넓혔습니다." The lip line gives the measured lip
  height, the prong line the hand calculation (about 7.7 against 2). No script names, check ids or
  JSON keys. A heading "**약속한 세 가지는 모두 확인했습니다**" sums up the `use` tier after the fix
  (finalize: 3 of 3 verified) and each promise has its own line; not read as one verdict.

Going back to Phase 4:
- [x] **must** Fixes the design, not the evidence: **yes**. The gap is now derived, `notch_w =
  plug_w + 2 × plug_clear` with `plug_clear` 0.3, 14.0 mm; the plug's measured size is unchanged in
  params.json and `.3dprint/usb_c_plug.json`; `--min-clearance 0.3`; the joint stays in the
  evidence; no `accepted` entry. (`holder.py`'s `DEFAULTS` plug values were set to the measured
  13.4 / 6.8 / 24.0 as well.)
- [x] **must** `_parts.holder.expect` to the new width and built again: **yes** (`[50.0, 19.0,
  70.0]`; `out/build.json` new).
- [x] **must** `fit.py` with the new placement, `measure.py` and `strength.py --from-build` with the
  same links, then finalize without a failure: **yes** (`--b-translate 18.3,6.1,-18`; the lip slice
  as setup's; the member command as setup's, all inputs linked; finalize: three `verified`).
- [x] **must** No delivery file while `cable-out` is failed: **yes** (the delivery folder was made
  after that finalize).

Delivering:
- [x] **should** A Bambu project from the template plus `holder.stl` in a new folder, finalize with
  `--deliver`: **yes** (`deliver/2026-10-23/holder_x1c.3mf`, brim 5 mm and 4 walls set per object
  with reasons).
- [ ] **should** Shows the changed holder before delivering: **no** (the preview came with the
  delivery; no stop).

Claiming (the last message):
- [x] **must** Korean throughout; the `use` lines first, one per promise with its state and what
  showed it; the cable line says it was fixed and how: **yes**. The fix is said in the opening
  paragraph (gap 13.0 → 14.0 mm for the measured 13.4 mm plug, 0.3 mm a side); the cable line
  then gives the fit against the measured plug and what it does not cover ("케이블이 아래로 휘는
  모양까지 본 건 아닙니다").
- [x] **must** Never "all checks pass", never one verdict for all three, nothing called verified
  that finalize does not: **yes** (see the heading above; "크기, 모델 상태, 플러그 끼움 검사를 모두
  통과했습니다" is the `geometry` line).

finalize after the run:
- [x] **must** `use` `verified`, `geometry` `verified`, the three promises `verified`: **yes**.

Rules in every scenario (README, "Grading"):
- Korean in every message the user saw: **yes**. Fourteen English notes between tool calls (from
  "I'll start by reading the skill instructions …" to "Now the handback to the user.") were not
  shown to the user in this harness.
- The last message claims no more than finalize: **yes**.

## Result

**Matches.** Every must item holds. Should missed: the widened holder was not shown before the
delivery.

Other observations (not checklist items):
- The agent fixed the failure without telling the user first; the user learned of the failed fit
  only in the delivery, together with the fix. The scripted reply rows for proposing a fix were
  never used.
- 4 wall loops were set for the strength calculation's solid-section assumption; finalize does not
  check that link.
- Preview crops and finalize outputs were written to the scratchpad, outside the project folder.
