# a-kept-broken, Claude (0.8.0)

- Agent and model: Claude Code-based harness subagent (run agent a956723d5eef2b7ae), model claude-opus-5-5
  inherited; one run agent per scenario, the session lead played the user
- Skill commit: f36e6b1, installed in the release layout, without `docs/`
- Kit: the scenario file at `v080-scenarios`
- Date, OS, Python: 2026-10-24, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: `runs080/log/setup_a-kept-broken.json`

How this harness worked: the brief names no coordinator; each scripted reply was sent word for
word and arrived labelled "The coordinator sent a message while you were working"; the last
message of each turn is the run agent's hand-back, which is what the user saw and is graded
whole. Tool calls are listed as one line each, in order (commands cut at 300 characters).
Absolute paths are shortened everywhere, the agent's messages included: `$PROJECT` is the run's
project folder (`…/scratchpad/runs080/claude/a-kept-broken`), `$SKILL_DIR` the installed skill, `$SCRATCH`
the session's scratchpad, outside the project folder.

## Conversation

**User:** 어제 하던 벽걸이 충전 거치대 이어서 해 주세요. 어제 충전 플러그를 재서 알려 드렸죠. 이제 출력 파일로 받고 싶어요.

`cat $SKILL_DIR/SKILL.md; echo ----; ls -laR $PROJECT`

`cd $PROJECT; for f in holder.py plug.py .3dprint/params.json .3dprint/printers.json .3dprint/usb_c_plug.json out/build.json out/fit_plug.json out/m_lip.json out/strength_prong.json out/*.manifest.json out/`

`cd $SKILL_DIR; ls -R; cat references/phase-0-detect.md`

`cd $SKILL_DIR; cat references/phase-4-features-joints.md`

`cd $SKILL_DIR; cat references/phase-2-printer-dimensions.md; echo =====; cat references/tolerances.md`

`cd $SKILL_DIR; cat references/phase-3-base-shape.md; echo ====; cat references/engines/python.md | head -120`

`cd $PROJECT; S=$SKILL_DIR; python3 $S/scripts/finalize.py --build out/build.json --params .3dprint/params.json 2>`

`cd $PROJECT; python3 - <<'EOF' ⏎ import re ⏎ src=open('holder.py').read() ⏎ src=src.replace('''    "notch_w": 13.0,       # gap between the prongs where the plug and its cable pass down ⏎ ''','''    "notch`

`cd $PROJECT; S=$SKILL_DIR; python3 $S/scripts/build.py run holder.py --params .3dprint/params.json --out out --pr`

`cd $PROJECT; S=$SKILL_DIR; python3 $S/scripts/measure.py slice --help | sed -n 1,40p`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 $S/scripts/fit.py out/holder.stl out/plug/plug.stl --b-translate 18.3,6.1,-18`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 $S/scripts/preview.py out/holder.stl -o out/preview.png --overwrite --lang ko`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 $S/scripts/preview.py out/holder.stl -o out/preview.png --overwrite 2>&1 | ta`

`Read $PROJECT/out/view_iso.png`

`Read $PROJECT/out/view_top.png`

`Read $PROJECT/out/view_right.png`

`cd $PROJECT; S=$SKILL_DIR; python3 $S/scripts/finalize.py --build out/build.json --params .3dprint/params.json > `

**Agent:**

어제 재 주신 플러그 크기(폭 13.4 × 두께 6.8 × 길이 24.0 mm)를 넣어 다시 확인해 보니, 어제 모델로는 플러그가 들어가지 않았어요. 두 받침 사이 홈이 13.0 mm라 플러그 폭 13.4 mm보다 좁았거든요. 출력 파일을 만들기 전에 이 부분부터 고쳤습니다.

**바뀐 부분**

| 항목 | 어제 | 지금 | 근거 |
|---|---|---|---|
| 받침 사이 홈 폭 | 13.0 mm | 14.0 mm | 플러그 폭 13.4 mm + 양옆 0.3 mm씩 틈 |
| 거치대 전체 폭 | 49 mm | 50 mm | 홈이 넓어진 만큼 늘어남 |

나머지 치수는 어제와 같아요. 받침은 폭 18 · 두께 6 · 길이 15 mm, 앞 턱은 높이 7 mm, 뒤판은 높이 70 · 두께 4 mm입니다. 홈 폭이 앞으로 다시 플러그보다 좁아지면 모델이 아예 만들어지지 않도록 막아 두었습니다.

**바뀐 모델로 다시 확인한 결과**
- 플러그: 받침과 겹치지 않고 양옆에 0.3 mm씩 틈이 있어요. 목표인 0.2 mm 이상을 넘으니 통과입니다.
- 앞 턱: 받침 위로 7 mm 올라와 있어요. 폰 두께의 절반(5.5 mm)보다 높으니 통과입니다.
- 받침 강도: 손가락으로 세게 누르는 힘(약 71 N)을 견디는지 계산해 보니, 필요한 여유의 약 3.9배(안전율 2 기준에 7.7)라 통과입니다. 계산으로 본 것이고 출력해서 눌러 본 건 아닙니다.
- 크기 50 × 19 × 70 mm로 X1C 베드에 들어가고, 모델 자체 검사에서도 문제가 없었어요. 서포트도 필요 없습니다.

미리보기: $PROJECT/out/preview.png

아직 확인하지 못한 것도 있어요. 위 결과는 모두 재 주신 숫자를 바탕으로 모델 위에서 재고 계산한 것이라, 실제 플러그를 끼워 보거나 케이블이 휘는 모양까지 확인하지는 못했어요. 양면테이프가 버티는지도 확인하지 않았습니다.

**확인 부탁드려요**
1. 홈 폭을 14.0 mm로 늘리면서 전체 폭이 50 mm가 됐는데, 이대로 괜찮으세요?
2. 미리보기 모양이 생각하신 거치대와 맞나요?

괜찮다고 하시면 바로 Bambu Studio 프로젝트 파일(3MF)과 STL로 만들어 드릴게요.

**User:** 잘 모르겠어요. 알아서 정해 주세요. 모양 좋아요. 계속해 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`cd $SKILL_DIR; cat references/phase-5-gate.md; echo ====; cat references/checks.md`

`cd $SKILL_DIR; cat references/phase-6-deliver.md; echo ====; cat references/bambu-process.md`

`Read $SKILL_DIR/references/phase-6-deliver.md`

`Read $SKILL_DIR/references/bambu-process.md`

`Read $PROJECT/out/preview.png.json`

`cd $PROJECT; python3 - <<'EOF' ⏎ import json ⏎ P=json.load(open('.3dprint/params.json')) ⏎ P['_verify']['seen'].append({"name":"base shape","image":"out/preview.png","image_sha256":"6a5f08aca67f77235d47184`

`cd $PROJECT; python3 - <<'EOF' ⏎ import json ⏎ P=json.load(open('.3dprint/params.json')) ⏎ P['_verify']['seen'].append({"name":"base shape","image":"out/preview.png","image_sha256":"6a5f08aca67f77235d47184`

`cd $PROJECT; S=$SKILL_DIR ⏎ ls deliver 2>&1; mkdir -p deliver/2026-10-24 ⏎ cat > out/bambu_job.json <<'EOF' ⏎ {"t`

`cd $PROJECT; S=$SKILL_DIR ⏎ ls deliver 2>&1; mkdir -p deliver/2026-10-24 ⏎ cat > out/bambu_job.json <<'EOF' ⏎ {"t`

`Write $PROJECT/out/bambu_job.json`

`ls $PROJECT/deliver 2>&1; mkdir -p $PROJECT/deliver/2026-10-24`

`cd $PROJECT && python3 $SKILL_DIR/scripts/bambu3mf.py out/bambu_job.json`

`cd $PROJECT && python3 $SKILL_DIR/scripts/bambu3mf.py out/bambu_job.json`

`python3 $SKILL_DIR/scripts/bambu3mf.py $PROJECT/out/bambu_job.json 2>&1 | head -3`

`cd $PROJECT && python3 $SKILL_DIR/scripts/bambu3mf.py out/bambu_job.json > out/bambu_job.out.json; cat out/bambu_`

`python3 $SKILL_DIR/scripts/bambu3mf.py $PROJECT/out/bambu_job.json 2>&1 | tail -8`

`cd $PROJECT; python3 $SKILL_DIR/scripts/bambu3mf.py out/bambu_job.json`

`cd $PROJECT; cp out/holder.stl deliver/2026-10-24/holder.stl; python3 $SKILL_DIR/scripts/finalize.py --build out/`

`cd $PROJECT; python3 - <<'EOF' ⏎ import json ⏎ P=json.load(open('.3dprint/params.json')) ⏎ P['_verify']['seen']=[] ⏎ P['_assumptions'].append("base shape: the user looked at out/preview.png (the 50 mm wide`

`cd $PROJECT; python3 -c " ⏎ import json;f=json.load(open('out/finalize_check.json'));print(json.dumps(f['delivered'],ensure_ascii=False)[:1500]);print(f['material_drift'],f['summary'])"; python3 /tmp/claud`

**Agent:**

출력 파일 만들었어요. 홈 폭은 정해 달라고 하셔서 14.0 mm로 그대로 두었습니다. 13.0 mm로 돌리면 재 주신 플러그(폭 13.4 mm)가 받침에 걸리기 때문이에요.

**약속드린 세 가지는 모두 확인됐어요.**
- 케이스 낀 폰을 세워 올리면 앞 턱이 잡아 준다: 확인됨. 모델에서 재 보니 턱이 받침 위로 7 mm 올라와 있어서, 폰 두께(11 mm)의 절반인 5.5 mm보다 높아요. 폰을 실제로 넣고 빼 본 건 아니에요.
- 충전 케이블을 꽂은 채 폰을 올려 둘 수 있다: 확인됨. 재 주신 크기(13.4 × 6.8 × 24.0 mm)의 플러그 모형을 넣어 보니 받침과 겹치지 않고 양옆에 0.3 mm씩 틈이 있어요. 플러그가 꽂힌 채 놓인 자세를 본 것이라, 케이블이 아래로 휘는 모양까지는 확인하지 못했어요.
- 받침을 세게 눌러도 부러지지 않는다: 확인됨. 손가락으로 세게 누르는 힘(약 71 N)에 대해 계산해 보니 필요한 여유의 약 3.9배예요. 출력해서 눌러 본 건 아니에요.

그 밖에 알아 두실 점:
- 모델 크기, 메시, 플러그 끼움 검사는 모두 통과했어요. 출력 파일에 들어간 모델도 검사한 그 모델이 맞습니다.
- 양면테이프가 버티는지는 확인하지 않았어요.
- 여기서 슬라이스나 실제 출력은 해 보지 않았어요.

**파일** ($PROJECT/deliver/2026-10-24/)
- 출력용 파일: $PROJECT/deliver/2026-10-24/holder_bambu.3mf
  Bambu Studio에서 **파일 > 프로젝트 열기**로 여세요. 그래야 설정이 유지돼요.
- STL: $PROJECT/deliver/2026-10-24/holder.stl
- 같은 폴더의 `source`에는 모델을 다시 만들 수 있는 스크립트와 검사 기록이 들어 있어요.

**치수**

| 항목 | 값 | 출처 |
|---|---|---|
| 케이스 낀 폰 두께 | 11.0 mm | 직접 재 주신 값 |
| USB-C 플러그 머리 (폭 × 두께 × 길이) | 13.4 × 6.8 × 24.0 mm | 직접 재 주신 값 |
| 받침 사이 홈 폭 | 14.0 mm | 플러그 폭 + 양옆 0.3 mm |
| 받침 (폭 × 두께 × 길이) | 18 × 6 × 15 mm | 강도 계산으로 확인 |
| 앞 턱 (높이 × 두께) | 7 × 3 mm | 폰 두께의 절반 이상 |
| 뒤판 (높이 × 두께) | 70 × 4 mm | 어제 정한 값 |
| 전체 크기 | 50 × 19 × 70 mm | X1C 베드(256 × 256 mm)에 여유 있게 들어감 |
| 필라멘트 / 출력 설정 | PLA Basic / 0.20mm Standard @BBL X1C | 저장된 설정 |

바꾸고 싶은 치수가 있으면 말씀해 주세요.

**출력 설정**
기본 설정을 그대로 쓰고, 이 모델에만 브림(바깥쪽, 5 mm)을 하나 추가했어요. 뒤판이 70 mm로 높은데 바닥 깊이는 19 mm밖에 안 돼서, 출력 중에 넘어지지 않게 하려는 거예요. 서포트는 필요 없어요. 뒤판은 세워지고 받침은 바닥에 눕는 방향이라, 벽에 붙일 때와 같은 방향으로 출력돼요.

**색**
거치대는 한 덩어리라 PLA 1번 슬롯 색으로 출력돼요. 바꾸시려면 객체 목록에서 holder를 선택하고 필라멘트를 바꾸면 됩니다.

## finalize after the run

```text
use: verified, geometry: verified
- seat: verified
- cable-out: verified
- holds: verified
```

(`finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver <the run's delivery folder>`, run by the grader in the run's folder, output kept outside it.)

## Checklist

Finding and saying the failure:
- **must** Finds `cable-out` failing before any delivery file: yes.
- **must** Says it in plain Korean (13.4 mm plug, 13.0 mm gap) with the other two and what showed each, no single verdict: yes. It had already widened the gap in the same turn and said so.

Going back to Phase 4:
- **must** Fixes the design: yes, `notch_w` 14.0 (13.4 + 0.3 a side), with an assertion in the generator.
- **must** `expect` [50, 19, 70], rebuilt: yes.
- **must** fit (new placement), measure and strength again, then finalize, nothing failed: yes.
- **must** No delivery file while failed: yes.

Delivering:
- **should** Bambu project and `holder.stl` in a new folder, finalize `--deliver`: yes.
- **should** Shows the changed holder before delivering: yes. It also named the changed width (49 → 50 mm) and asked whether that is fine (the new Phase 4 rule on a changed value).

Agreement:
- **must** yes. The width question was answered with the fallback; it kept 14.0 and recorded that the user handed the decision back.

Claiming:
- **must** Korean, `use` lines first with their states: yes.
- **must** No single verdict; nothing verified beyond finalize: yes.

finalize:
- **must** all verified: yes.

Result: **matches** (0.7.0's should miss, the wider holder not shown, holds now).
