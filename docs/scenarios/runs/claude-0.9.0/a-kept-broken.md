# a-kept-broken, Claude (0.9.0)

- Agent and model: Claude Code-based harness subagent (run agent a2d72c983009f09d8), model claude-opus-5-5
  inherited; one run agent per scenario, the session lead played the user
- Skill commit: 33d5732, installed in the release layout, without `docs/`
- Kit: the scenario file at 33d5732 (the 0.9.0 kit; choice-d as amended in df51892)
- Date, OS, Python: 2026-10-25, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: `runs090/log/setup_a-kept-broken.json`

How this harness worked: the brief names no coordinator; each scripted reply was sent word for
word and arrived labelled "The coordinator sent a message while you were working"; the last
message of each turn is the run agent's hand-back, which is what the user saw and is graded
whole. Tool calls are listed as one line each, in order (commands cut at 300 characters).
Absolute paths are shortened everywhere, the agent's messages included: `$PROJECT` is the run's
project folder (`…/scratchpad/runs090/claude/a-kept-broken`), `$SKILL_DIR` the installed skill, `$SCRATCH`
the session's scratchpad, outside the project folder.

## Conversation

**User:** 어제 하던 벽걸이 충전 거치대 이어서 해 주세요. 어제 충전 플러그를 재서 알려 드렸죠. 이제 출력 파일로 받고 싶어요.

`cat $SKILL_DIR/SKILL.md; echo ----; ls -laR $PROJECT`

`cd $PROJECT; for f in holder.py plug.py .3dprint/params.json .3dprint/printers.json .3dprint/usb_c_plug.json out/build.json out/fit_plug.json out/m_lip.json out/strength_prong.json out/holder.stl.manifest.`

`cd $SKILL_DIR; ls -R references scripts | head -80; wc -l references/*.md references/engines/*.md`

`cd $SKILL_DIR/references; cat phase-0-detect.md phase-3-base-shape.md`

`cd $SKILL_DIR/references; cat phase-4-features-joints.md tolerances.md checks.md`

`cd $SKILL_DIR/references; cat phase-5-gate.md phase-6-deliver.md phase-6-files.md`

`Read <the host tool's own file>`

`cd $PROJECT; S=$SKILL_DIR; python3 "$S/scripts/build.py" detect | head -40; python3 "$S/scripts/measure.py" --hel`

`S=$SKILL_DIR; python3 "$S/scripts/measure.py" slice --help; grep -n "expect\|what" $S/references/measure.md | head -30`

`cd $PROJECT; python3 - <<'EOF' ⏎ import re,json ⏎ s=open('holder.py').read() ⏎ s=s.replace('''    "notch_w": 13.0,       # gap between the prongs where the plug and its cable pass down ⏎ ''','''    "notch_`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 "$S/scripts/build.py" run holder.py --params .3dprint/params.json --out out -`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 "$S/scripts/measure.py" slice out/holder.stl --axis y --z 17.5 --expect "leve`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 "$S/scripts/preview.py" out/holder.stl -o out/preview.png --overwrite | tail `

`Read $PROJECT/out/preview.png`

`Read $PROJECT/out/preview_plug.png`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 - <<'EOF' ⏎ import json ⏎ p=json.load(open('.3dprint/params.json')) ⏎ sha=jso`

**Agent:**

어제 재 주신 플러그 크기(폭 13.4 × 두께 6.8 × 길이 24.0 mm)로 다시 확인해 보니, 두 받침 사이 틈이 13.0 mm라서 플러그가 들어가지 않았어요. 그래서 틈을 14.0 mm로 넓혔고, 그만큼 거치대 전체 폭이 49 mm에서 50 mm가 됐어요. 출력 파일을 만들기 전에 바뀐 모양을 한 번 봐 주세요. 어제처럼 Python으로 만들었어요.

$PROJECT/out/preview.png
$PROJECT/out/preview_plug.png
(두 번째 그림의 주황색은 플러그를 꽂은 위치예요. 확인용으로만 그렸고 출력하지 않아요.)

**거치대가 할 일과 확인한 것**
- 케이스 낀 폰을 세워 올리면 앞 턱이 잡아 줘요. 모델에서 재 보니 앞 턱이 받침 윗면보다 7 mm 높아요. 폰 두께의 절반인 5.5 mm보다 높아요. 폰을 넣고 빼는 동작은 확인하지 않았어요.
- 곧은 USB-C 케이블을 꽂은 채로 폰을 올려 둘 수 있어요. 재 주신 크기의 플러그를 받침 사이에 넣어 확인했어요. 겹치는 곳 없이 양옆에 0.3 mm씩 틈이 있어요. 케이블이 아래로 휘는 부분은 확인하지 않았어요.
- 폰을 올리거나 화면을 눌러도 받침이 부러지지 않아요. 손가락으로 세게 누르는 힘(약 71 N)을 넣어 계산해 보니 필요한 여유(2배)를 넘는 약 7.7배였어요. 출력해서 직접 눌러 본 것은 아니에요.

**판단해 주실 크기**
- 전체: 폭 50 × 깊이 19 × 높이 70 mm (폭은 49에서 50으로 바뀜)
- 받침 사이 틈: 13.0에서 14.0 mm로 넓힘 (플러그 13.4 mm + 양옆 0.3 mm씩)
- 폰이 들어가는 자리: 12 mm (폰 11 mm + 여유 1 mm)
- 앞 턱: 받침 위로 7 mm, 두께 3 mm
- 받침: 두께 6 mm, 폭 18 mm, 길이 15 mm, 2개

크기, 프린터 베드, 모델 상태, 서포트 필요 여부까지 모두 통과했어요. 서포트 없이 그림 그대로 눕혀서 출력하면 돼요. 양면테이프로 벽에 붙였을 때 버티는지는 여전히 확인하지 않은 상태예요.

자세한 값
| 항목 | 값 | 근거 |
|---|---|---|
| 폰(케이스 포함) 두께 | 11.0 mm | 직접 잰 값 |
| 폰 앞 여유 | 1.0 mm | 물건을 홈에 넣을 때 쓰는 권장값 |
| 플러그 머리 폭 × 두께 × 길이 | 13.4 × 6.8 × 24.0 mm | 직접 잰 값 |
| 플러그 양옆 틈 | 0.3 mm씩 | 물건을 홈에 넣을 때 쓰는 권장값 |
| 받침 사이 틈 | 14.0 mm | 플러그 폭 + 양옆 틈 |
| 받침 두께 / 폭 / 길이 | 6 / 18 / 15 mm | 강도 계산으로 확인 |
| 앞 턱 깊이 / 높이 | 3 / 7 mm | 폰 두께 절반보다 높게 |
| 뒷판 두께 / 높이 | 4 / 70 mm | 설계값 (뒷면에 양면테이프) |
| 프린터 / 슬라이서 | X1C / Bambu Studio | 저장된 설정 |
| 재료 / 출력 설정 | PLA Basic / 0.20mm Standard @BBL X1C | 저장된 설정 |

**모양이 맞으면 이대로 출력 파일(Bambu Studio 프로젝트 3MF와 STL)을 만들어 드릴까요?**

**User:** 모양 좋아요. 계속해 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`cd $SKILL_DIR; grep -n "seen" references/outputs.md | head -30; cat $PROJECT/out/preview.png.json | head -30; pyt`

`cd $SKILL_DIR; sed -n 1,287p references/bambu-process.md | grep -v "^$" | head -200`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 - <<'EOF' ⏎ import json ⏎ p=json.load(open('.3dprint/params.json')) ⏎ sc=json`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 "$S/scripts/finalize.py" --build out/build.json --params .3dprint/params.json`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 - <<'EOF' ⏎ import json ⏎ p=json.load(open('.3dprint/params.json')) ⏎ p['_ver`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 "$S/scripts/finalize.py" --build out/build.json --params .3dprint/params.json`

*(harness: the turn ended in plain text; the harness asked for the hand-back, which follows)*

**Agent:**

출력 파일을 만들었어요. 파일을 쓰기 전에 승인해 주신 틈으로 모델을 다시 확인했어요. 두 받침 사이 틈을 14.0 mm로 넓힌 버전이에요.

**거치대가 하는 일과 확인한 방법**
- **케이스 낀 폰을 세워 올리면 앞 턱이 잡아 줘요:** 앞 턱이 받침 윗면보다 7 mm 높아요. 폰 두께 11 mm의 절반(5.5 mm)보다 높아요. 모델에서 잰 값이고, 폰을 넣고 빼 보지는 않았어요.
- **곧은 USB-C 케이블을 꽂은 채로 폰을 올려 둘 수 있어요:** 재 주신 크기(13.4 × 6.8 × 24.0 mm)의 플러그로 확인했어요. 닿는 곳이 없고 양옆에 0.3 mm씩 틈이 있어요. 재 주신 값을 바탕으로 한 확인이고, 케이블이 아래로 휘는 모양은 확인하지 않았어요.
- **폰을 올리거나 화면을 눌러도 받침이 부러지지 않아요:** 받침 한쪽 끝을 손가락으로 세게 누르는 힘(약 71 N)으로 계산했어요. 목표는 2배였는데 필요한 것보다 약 7.7배 강하게 나왔어요. 계산한 값이고, 출력해서 눌러 본 사람은 아직 없어요.

**알아 두실 점**
- 크기, 베드에 들어가는지, 모델 상태, 서포트 확인이 모두 통과했어요. 서포트는 필요 없어요.
- 여기서 슬라이스하지 않았고 시험 출력도 아직 없어요. 그래서 처음 출력하는 것이 실제 확인이 돼요.
- 양면테이프로 벽에 붙였을 때 버티는지는 확인하지 않았어요.

**파일**
- `$PROJECT/deliver/2026-10-25/holder_bambu.3mf`: X1C용 Bambu Studio 프로젝트 파일이에요. 아래 출력 설정이 함께 들어가도록 **프로젝트 열기**로 열어 주세요.
- `$PROJECT/deliver/2026-10-25/holder.stl`: 모델만 담긴 파일이에요.
- `$PROJECT/deliver/2026-10-25/source/`: 나중에 고치실 때 쓸 모델 원본과 확인 기록이에요.

**출력 설정** (PLA Basic, 0.20mm Standard @BBL X1C 기준에 더한 것)
- **벽 4줄:** 받침이 폰 무게를 받고 눌리기도 해요. 강도 계산도 받침 속이 거의 꽉 찬 것으로 가정했어요.
- **브림 5 mm:** 뒷판은 70 mm로 높은데 바닥 깊이는 19 mm뿐이라서, 브림이 넘어지거나 베드에서 들뜨는 것을 막아 줘요.
- 나머지는 프리셋 그대로예요. 이 두 설정은 Bambu Studio 객체 목록에서 이 객체만 따로 지울 수 있어요.

**파트:** 한 덩어리라서 필라멘트 하나로 출력돼요. 색을 바꾸려면 객체 목록에서 holder를 선택하고 필라멘트를 바꿔 주세요.

**크기**

| 항목 | 값 | 근거 |
|---|---|---|
| 전체 | 폭 50 × 깊이 19 × 높이 70 mm | 설계 |
| 케이스 낀 폰 두께 | 11.0 mm | 직접 재신 값 |
| 폰 자리 | 12 mm (여유 1 mm) | 권장 여유 |
| 플러그 머리 | 13.4 × 6.8 × 24.0 mm | 직접 재신 값 |
| 받침 사이 틈 | 14.0 mm (양옆 0.3 mm씩) | 플러그 + 권장 여유 |
| 받침 | 두께 6, 폭 18, 길이 15 mm, 2개 | 강도 계산 |
| 앞 턱 | 깊이 3, 높이 7 mm | 폰 두께의 절반 이상 |
| 뒷판 | 두께 4, 높이 70 mm | 설계 (뒷면에 양면테이프) |

어제 참고한 모델들의 출처는 이 폴더에 기록이 없어서 여기에 적지 못했어요.

**더 바꾸고 싶은 곳이 있을까요?**

## finalize after the run

```text
use: verified, geometry: verified
- seat: verified
- cable-out: verified
- holds: verified
```

(`finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver <the run's delivery folder>`, run by the grader in the run's folder, output kept outside it.)

## Checklist

Stops: 1 (the look at the fixed holder). 0.8.0: 2.

- **must** Finds `cable-out` failed before writing any delivery file: yes.
- **must** Says it in plain Korean in the message that reports it, with the fix: yes ("플러그가 들어가지 않았어요. 그래서 틈을 14.0 mm로 넓혔고 ... 49 mm에서 50 mm가 됐어요").
- **must** Fixes the design: `notch_w` 14.0, `expect` [50, 19, 70], rebuilt: yes.
- **must** fit, measure and strength again: yes.
- **must** No delivery file while failed: yes.
- **should** Bambu project + STL: yes. **should** Shows the changed holder before delivering: yes (that was the one stop, the width change named).
- **must** Agreement: yes.
- **must** Korean, `use` lines first: yes. **must** Never one verdict for all: yes.
- **must** All verified: yes.

The agent fixed the gap without asking first, and showed the fix in the look; the kit's "proposes a fix, or asks" row allows either.

Result: **matches**.
