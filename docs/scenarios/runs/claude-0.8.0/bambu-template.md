# bambu-template, Claude (0.8.0)

- Agent and model: Claude Code-based harness subagent (run agent a8c26eb096d8d8b1a), model claude-opus-5-5
  inherited; one run agent per scenario, the session lead played the user
- Skill commit: d400348, installed in the release layout, without `docs/`
- Kit: the scenario file at `v080-scenarios`
- Date, OS, Python: 2026-10-24, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: `runs081/log/setup_bambu-template.json`
This is the re-run, after the clarifications in d400348; the first pass is [`bambu-template-f36e6b1.md`](bambu-template-f36e6b1.md).
How this harness worked: the brief names no coordinator; each scripted reply was sent word for
word and arrived labelled "The coordinator sent a message while you were working"; the last
message of each turn is the run agent's hand-back, which is what the user saw and is graded
whole. Tool calls are listed as one line each, in order (commands cut at 300 characters).
Absolute paths are shortened everywhere, the agent's messages included: `$PROJECT` is the run's
project folder (`…/scratchpad/runs081/claude/bambu-template`), `$SKILL_DIR` the installed skill, `$SCRATCH`
the session's scratchpad, outside the project folder.

## Conversation

**User:** 옷걸이 봉 끝에 끼울 마개를 하나 만들어 주세요. 봉은 둥근 쇠파이프이고, 바깥지름을 캘리퍼로 재 보니 22.0 mm예요. 마개는 손으로 끼웠다 뺐다 할 수 있으면 좋겠어요. 프린터 설정은 이 폴더에 저장해 둔 그대로예요.

`S=$SKILL_DIR; cat $S/SKILL.md; ls -R $S | head -100; echo ---; ls -la $PROJECT`

`S=$SKILL_DIR; P=$PROJECT; ls -laR $P/.3dprint; for f in $(find $P/.3dprint -type f); do echo "=== $f"; cat $f; d`

`S=$SKILL_DIR; cd $SCRATCH; python3 "$S/scripts/build.py" detect; cat $S/references/phase-1-references.md`

`WebSearch: 22mm tube end cap clothes rail printables`

`WebSearch: 22mm pipe end cap 3d print thingiverse OR makerworld`

`WebSearch: printables "end cap" outer diameter 22 mm tube cap over pipe`

`WebFetch: https://makerworld.com/en/models/2947453`

`WebFetch: https://www.printables.com/model/1031101-pipe-end-cap`

`WebFetch: https://www.printables.com/model/172012-tube-end-cap-wedge-clamp`

`WebFetch: https://www.printables.com/model/548118-cap-22mm-id`

`WebFetch: https://www.printables.com/model/860604-endkappe-fur-galerieschieneend-cap-gallery-rail`

`S=$SKILL_DIR; cat $S/references/phase-2-printer-dimensions.md; cat $S/references/tolerances.md`

*(harness: the turn ended in plain text; the harness asked for the hand-back, which follows)*

**Agent:**

찾아본 기존 모델 네 개와 진행 방법을 정리했어요.

**작업 환경:** Blender(bpy 5.2)로 모델링하고, 참고 모델은 웹 검색으로 찾았어요. 미리보기 이미지도 Blender로 만들어요. 결과물은 STL/3MF와 수정 가능한 `.blend` 파일이에요. Fusion처럼 치수를 고치면 따라 바뀌는 CAD 파일은 아니지만, 치수는 전부 스크립트 변수로 남겨 둬요. 폴더에 저장된 프린터 설정은 **Bambu Lab X1C + Bambu Studio**라서 그대로 쓸게요.

**요청 정리:** 바깥지름 22.0 mm인 둥근 쇠파이프(옷걸이 봉) 끝에 끼우는 마개를 만들어요. 손으로 끼웠다 뺄 수 있어야 하고, 꽉 끼어서 저절로 빠지지는 않아야 해요.

| # | 이름 | 사이트 | URL | 라이선스 | 가져올 만한 점 |
|---|---|---|---|---|---|
| 1 | Pipe Protective Cap All-in-One (Customize) | MakerWorld | https://makerworld.com/en/models/2947453 | Standard Digital File License (공유·판매 불가) | 안쪽 고정 돌기, 입구 모따기, 벽 4겹 이상 권장. 지원 규격이 DN32 이상 배관이라 22 mm 봉에는 맞지 않아요 |
| 2 | Cap 22mm I.D. | Printables | https://www.printables.com/model/548118-cap-22mm-id | 확인 안 됨 | 파이프 바깥에 씌우는 형태(안지름 22, 바깥지름 24, 높이 25 mm). 다만 출력물 안지름이 21.7 mm로 나왔다고 해서 22.0 mm 봉에는 안 들어갈 수 있어요. 벽도 1 mm로 얇아요 |
| 3 | tube end cap wedge clamp | Printables | https://www.printables.com/model/172012-tube-end-cap-wedge-clamp | 확인 안 됨 | 바깥지름 22 mm 튜브용이에요. 안쪽에 쐐기를 넣고 M5 볼트로 조이는 방식이라 단단하지만, 공구가 필요해서 손으로 뺐다 끼우기는 어려워요 |
| 4 | Pipe End Cap | Printables | https://www.printables.com/model/1031101-pipe-end-cap | 확인 안 됨 | 쇠파이프 마개를 대신하려고 만든 단순한 모양(지름 21.8, 높이 20 mm). 끼우는 방식은 설명이 없어요 |

Printables의 라이선스는 페이지를 그냥 불러와서는 보이지 않아요. 확인이 필요하면 각 모델 페이지 오른쪽의 **License** 칸을 보시면 돼요.

바로 받아 써도 될 만큼 딱 맞는 모델은 없었어요. 2번이 가장 비슷하지만 22.0 mm 봉에는 너무 빡빡할 가능성이 커요.

**어떻게 진행할까요?**
- **A. 하나를 참고:** 예를 들어 2번처럼 바깥에 씌우는 형태로, 끼움 여유와 벽 두께를 제대로 잡아서 만들어요.
- **B. 여러 개를 섞기 (추천):** 2번의 씌우는 형태에 1번의 고정 돌기와 입구 모따기를 더해요. 손으로 빼기 쉬우면서도 저절로 빠지지 않게 하려는 거예요.
- **C. 처음부터 새로 만들기**
- **D. 기존 모델을 그대로 쓰기:** 위 이유로 추천하지 않아요.
- **"4개 더 보여줘"**라고 하시면 다른 후보도 찾아볼게요.

B나 C를 고르시면 대략적인 모양 2~3가지를 이미지로 먼저 보여 드릴게요. 예를 들면 바깥에 씌우는 캡, 고정 돌기가 있는 캡 같은 것들이에요. 그중 하나를 고르시면 정확한 치수로 넘어가요.

**User:** 기존 모델 말고 새로 만들어 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`S=$SKILL_DIR; python3 $S/scripts/render.py --help; python3 $S/scripts/preview.py --help | head -40; grep -n "^def " $S/scripts/parts.py | head -60`

`P=$PROJECT; S=$SKILL_DIR; mkdir -p $P/out/concepts; cat > $P/out/concepts/concepts.py <<'EOF' ⏎ # Rough concept `

`Read $PROJECT/out/concepts/v2_ribs.png`

`Read $PROJECT/out/concepts/v3_slots.png`

`D=$PROJECT/out/concepts; python3 - "$D" <<'EOF' ⏎ import json, sys ⏎ d = sys.argv[1] ⏎ common_use = {"id": "on-off-by-hand", "kind": "use", "text": "마개를 손으로 봉 끝에 끼웠다 뺄 수 있다", ⏎               "conditions":`

**Agent:**

처음부터 새로 만드는 쪽으로 진행했어요. 대략적인 모양 세 가지예요. 아직 치수를 확정하기 전의 거친 모델이고, 크기는 모두 바깥지름 약 27 mm, 높이 약 27 mm예요. 봉이 들어가는 깊이는 25 mm, 벽 두께는 2.4 mm예요.

1번: 매끈한 캡
$PROJECT/out/concepts/v1_smooth.png
안쪽이 매끈한 컵 모양이에요. 가장 단순하고 출력도 제일 빨라요. 하지만 끼움 정도를 0.1 mm 단위로 맞춰야 해서, 출력 오차에 따라 헐겁거나 너무 뻑뻑해질 수 있어요.

2번: 안쪽 세로 돌기 캡 (추천)
$PROJECT/out/concepts/v2_ribs.png
안쪽에 가는 세로 돌기 6줄이 봉을 살짝 눌러 잡아요. 몸통은 여유 있게 들어가고 돌기만 닿아서, 손으로 끼우고 빼기 쉬우면서 흔들리지 않아요. 돌기가 조금 눌리면서 오차도 흡수해요. 출력 시간은 1번과 거의 같아요.

3번: 홈 파인 탄성 캡
$PROJECT/out/concepts/v3_slots.png
입구 쪽 벽에 세로 홈 4개를 내서 벽이 벌어졌다 오므라들어요. 입구 안쪽 턱이 봉을 잡아서, 끼울 때 딸깍 걸리는 느낌이 나요. 고정력은 가장 좋아요. 대신 PLA에서는 자주 뺐다 끼우면 홈 사이 벽이 갈라질 수 있고, 겉에 홈이 보여요.

세 가지 모두 출력할 때는 닫힌 윗면을 바닥에 두고 세워서 뽑아요. 그래서 서포트가 필요 없어요.

몇 번으로 할까요? 고르시면 정확한 치수와 끼움 여유를 정리해서 보여 드릴게요. 끝을 둥글게 하거나 위에 무늬를 넣는 식으로 조금 바꾸고 싶은 점이 있으면 같이 말씀해 주세요.

**User:** 첫 번째 안으로 할게요.  *(arrived labelled "The coordinator sent a message while you were working")*

`S=$SKILL_DIR; cat $S/references/bambu-process.md; cd /tmp && unzip -p $PROJECT/.3dprint/templates/x1c.3mf Metada`

`cd /tmp && unzip -p $PROJECT/.3dprint/templates/x1c.3mf Metadata/project_settings.config | grep -n -i -E "compens|elephant|wall_loops|layer_height" ; ls $SCRATCH/…`

`P=$PROJECT; cd $P && python3 - <<'EOF' ⏎ import json ⏎ pr = json.load(open(".3dprint/printers.json")) ⏎ x = pr["printers"]["x1c"] ⏎ x.setdefault("compensation", {}).update({"holes": "model", "elephant_foo`

**Agent:**

1번 매끈한 캡으로 정했어요. 모델링을 시작하기 전에 마개가 해야 할 일과 치수를 정리했으니 확인해 주세요.

**마개가 할 일**
1. **손으로 끼웠다 빼기:** 바깥지름 22.0 mm 봉 끝에 공구 없이 손으로 끼우고 뺄 수 있어야 해요. 끼운 상태에서는 흔들리거나 저절로 빠지지 않아야 해요. 매끈한 캡은 마찰만으로 붙어 있어서, 실제로 그렇게 되는지는 출력해서 끼워 봐야 확인돼요.
2. **봉 끝 덮기:** 막힌 윗면이 봉의 잘린 끝을 완전히 덮어요.
3. **입구 모따기:** 입구 안쪽 가장자리를 0.8 mm 비스듬히 깎아서 봉이 쉽게 들어가게 해요. 이건 제가 추가한 거라, 원하지 않으시면 빼 드릴게요.

**치수와 설정**

| 항목 | 값 | 출처 |
|---|---|---|
| 봉 바깥지름 | 22.0 mm | 직접 재신 값(캘리퍼) |
| 끼움 여유 | 한쪽 0.15 mm (지름 기준 0.30 mm) | 헐겁지 않게 끼는 일반적인 시작값 |
| 구멍 보정 | 한쪽 0.15 mm (지름 기준 0.30 mm) | 저장된 X1C 기본 설정은 출력 프로그램이 구멍 크기를 보정하지 않아요. 출력하면 구멍이 조금 작아지기 때문에 모델 쪽에서 미리 키워요 |
| → 모델 안지름 | 22.6 mm | 위 값들로 계산 |
| 벽 두께 | 2.4 mm | 튼튼한 벽의 권장값 |
| 봉이 들어가는 깊이 | 25 mm | 컨셉 값 |
| 윗면 두께 | 2.4 mm | 0.2 mm 층 12장 |
| → 마개 크기 | 바깥지름 27.4 × 높이 27.4 mm | 계산 |
| 입구 쪽 바깥 모서리 | 0.8 mm 둥글게 | 보기 좋게 |
| 바닥에 닿는 모서리(윗면 둘레) | 0.4 mm 모따기 | 출력할 때 바닥이 퍼지는 건 Bambu Studio가 자동으로 보정해요. 모따기는 모양을 위한 거예요 |
| 출력 방향 | 막힌 윗면을 바닥에 두고 세워서 출력, 서포트 없음 | 설계상 |
| 필라멘트 | PLA (Bambu PLA Basic) | 저장된 설정 기준. 직접 말씀하시진 않았어요 |
| 출력 품질 설정 | 0.20mm Standard @BBL X1C | 폴더에 저장된 설정 |
| 용도 | 일반 (무게를 버티는 부품 아님) | 따로 말씀이 없어서 제가 정했어요 |
| 출력판 여유 | 가로·세로 각각 228.6 mm, 높이 222.6 mm 남음 | X1C 256 × 256 × 250 mm 기준 |

**두 가지만 확인해 주세요.**
1. **봉 끝 상황:** 봉 끝이 벽 브래킷이나 받침 구멍에 들어가 있나요, 아니면 그냥 밖으로 나와 있나요? 마개가 봉보다 사방으로 2.7 mm쯤 굵어지기 때문에, 브래킷 안에 들어가야 한다면 그 구멍 크기도 알아야 해요.
2. **끼움 테스트 조각 (추천):** 매끈한 캡은 0.1 mm 차이로도 너무 빡빡하거나 헐거워질 수 있어요. 안지름이 22.45 / 22.60 / 22.75 mm인 짧은 링 세 개(몇 그램, 10분 정도)를 먼저 뽑아서 봉에 끼워 보시면 딱 맞는 크기로 마개를 만들 수 있어요. 테스트를 건너뛰면 가운데 값(22.60 mm)으로 만들고, "테스트 출력으로 확인하지 않음"이라고 기록해 둘게요.

다른 것도 바꾸고 싶으시면 함께 말씀해 주세요. 예를 들어 들어가는 깊이를 더 짧게 할 수도 있어요.

**User:** 네, 그대로 진행해 주세요. 잘 모르겠어요. 알아서 정해 주세요. 지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`S=$SKILL_DIR; cat $S/references/phase-3-base-shape.md $S/references/engines/blender.md`

`Read <the host tool's own file>`

`S=$SKILL_DIR; grep -n -A12 "^def round_profile\|^def from_manifold\|^def bed_chamfer\|^def segments_for\|^def circle_segments" $S/references/engines/blender_builder.py | head -90; cat $S/examples/blender-coas`

`P=$PROJECT; S=$SKILL_DIR; cat > $P/rail_cap.py <<'EOF' ⏎ # 3dprint-scout: engine=blender ⏎ """End cap for a roun`

`P=$PROJECT; S=$SKILL_DIR; cd $P && python3 -c " ⏎ import json; b=json.load(open('out/build.json')) ⏎ for n,pt in`

`cd $PROJECT && python3 -c " ⏎ import json; b=json.load(open('out/build.json')) ⏎ print(json.dumps(b['parts'], ensure_ascii=False)[:4000])"`

`Read $PROJECT/out/preview.png`

**Agent:**

마개 기본 모양을 만들었어요. 다음 단계로 넘어가기 전에 이 미리보기 한 장만 봐 주세요.

$PROJECT/out/preview.png

이미지는 출력할 때 놓는 방향이라 막힌 쪽이 아래에 있어요. 봉에 끼우면 뒤집혀서 막힌 쪽이 바깥을 보게 돼요.

- **크기:** 바깥지름 27.4 × 높이 27.4 mm. 안지름 22.6 mm, 봉이 들어가는 깊이 25 mm, 벽 두께 2.4 mm. 부피는 약 6.1 cm³로, PLA 7~8 g 정도예요.
- **보이는 부분:** 입구 바깥 모서리는 0.8 mm 둥글게, 입구 안쪽은 0.8 mm 비스듬히 깎았어요. 출력판에 닿는 모서리는 0.4 mm 모따기예요.
- **자동 검사:** 모두 통과했어요. 크기가 설계값과 일치하고, 구멍 없이 닫힌 한 덩어리이고, X1C 출력판에 들어가요. 서포트가 필요한 부분은 0 %예요(가장 기운 면 42°). 벽 두께도 2.4 mm로 기준을 넘어요.

모양이 괜찮으면 "좋아요"라고만 해 주세요. 그러면 봉과의 끼움 검사를 하고 출력 파일까지 마무리할게요.

말씀하신 대로 정한 것 두 가지도 기록해 뒀어요. 봉 끝은 브래킷 없이 밖으로 나와 있다고 보고 만들었고, 시험 출력은 하지 않고 가운데 값(안지름 22.6 mm)으로 만들었어요.

**User:** 모양 좋아요. 계속해 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`S=$SKILL_DIR; cat $S/references/phase-4-features-joints.md`

`S=$SKILL_DIR; cat $S/references/checks.md; grep -n "proxy" -A3 $S/references/measure.md | head -120`

`S=$SKILL_DIR; sed -n 73,95p $S/references/measure.md; grep -n "expect" $S/references/measure.md | head -30; python3 $S/scripts/measure.py --help | head -50`

`S=$SKILL_DIR; head -30 $S/examples/snap-box/snapbox.py; grep -n "def main\|__main__\|DEFAULTS" $S/examples/snap-box/snapbox.py | head; sed -n 1,60p $S/references/engines/python.md`

`P=$PROJECT; S=$SKILL_DIR; cd $P; cat > rail_pipe_proxy.py <<'EOF' ⏎ """Proxy of the user's clothes-rail pipe for`

`P=$PROJECT; S=$SKILL_DIR; cd $P; python3 "$S/scripts/fit.py" out/cap.stl out/pipe/rail_pipe_proxy.stl --b-transl`

`P=$PROJECT; S=$SKILL_DIR; cd $P; python3 - <<'EOF' ⏎ s = open("rail_cap.py").read() ⏎ s = s.replace('import blen`

`P=$PROJECT; S=$SKILL_DIR; cd $P; sed -n 41,66p $S/references/measure.md; python3 $S/scripts/measure.py slice --h`

`cd $PROJECT; S=$SKILL_DIR; python3 $S/scripts/measure.py slice out/cap.stl --z 1.2,27.35 | python3 -c " ⏎ import`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 $S/scripts/measure.py slice out/cap.stl --z 1.2 --expect "levels[0].loops[0]`

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint/params.json")) ⏎ v = `

`S=$SKILL_DIR; cat $S/references/phase-5-gate.md`

`S=$SKILL_DIR; cd $PROJECT; python3 $S/scripts/fit.py --check out/fit_cap_pipe.json | python3 -c "import json,sys`

`cd $PROJECT; S=$SKILL_DIR; python3 "$S/scripts/render.py" out/cap.stl -o out/preview_final.png --color "cap=Jade`

`Read $PROJECT/out/preview_final.png`

**Agent:**

검사를 마쳤고, 출력 파일만 남았어요. 파일을 만들기 전에 두 가지만 확인해 주세요.

**검사 결과**
- **봉과의 끼움:** 22.0 mm 봉 모형을 마개에 끝까지 넣어 봤어요. 걸리는 곳 없이 들어가고, 사방으로 0.30 mm씩 여유가 있어요. 설계한 그대로예요.
- **막힌 끝:** 바닥 쪽 단면이 구멍 없는 꽉 찬 원판인 걸 확인했어요.
- **입구 모따기:** 입구 안쪽 폭이 24.1 mm로, 0.8 mm 모따기가 들어가 있어요.
- **모양과 출력:** 크기, 닫힌 한 덩어리, 출력판에 들어가는지, 서포트 필요 없음, 벽 두께 모두 통과했어요.

**고친 것 하나:** 처음 검사에서 여유가 0.2988 mm로 나와 계획한 0.30 mm에 0.0012 mm 모자랐어요. 원을 다각형으로 만들면서 생긴 아주 작은 차이라, 안쪽 구멍을 그만큼 보정해서 다시 만들었어요. 눈으로는 차이가 없지만, 모델이 바뀌었으니 지금 모습을 한 번 더 보여 드려요.

$PROJECT/out/preview_final.png

**확인해 주세요**
1. **지금 모습:** 그대로 괜찮으면 "좋아요"라고 해 주세요.
2. **출력 설정 변경 하나:** 저장된 0.20mm Standard @BBL X1C 설정은 그대로 두고, 이 마개에만 **벽 둘레선을 2줄에서 5줄로** 늘리려고 해요. 기본값이면 2.4 mm 벽 안쪽이 듬성듬성한 채움으로 출력돼요. 5줄로 하면 벽 전체가 꽉 차서, 자주 끼웠다 빼도 잘 갈라지지 않고 안쪽 구멍도 더 둥글게 나와요. 출력 시간은 조금 늘어나요. 원하지 않으시면 기본값 그대로 둘게요.

"좋아요"라고 해 주시면 Bambu Studio 프로젝트 파일(3MF), STL, Blender 파일을 새 폴더에 만들어 드릴게요.

**아직 확인 안 된 것:** 손으로 끼우고 빼는 느낌과 끼운 채로 잘 버티는지는 실제로 출력해 봐야 알 수 있어요. 시험 출력은 건너뛰기로 하셨으니, 결과물에도 "시험 출력으로 확인 안 됨"이라고 적어 둘게요.

**User:** 모양 좋아요. 계속해 주세요. 잘 모르겠어요. 알아서 정해 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`cd $PROJECT; S=$SKILL_DIR ⏎ python3 - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint/params.json")) ⏎ sc =`

`cd $PROJECT; S=$SKILL_DIR; D=deliver/2026-10-24 ⏎ python3 - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint`

**Agent:**

옷걸이 봉 마개 출력 파일을 만들었어요. 다만 손으로 끼웠다 빼는 느낌과 끼운 채로 버티는지는 시험 출력을 건너뛰어서 아직 확인하지 못했어요.

**약속한 세 가지**
- **손으로 끼웠다 빼기:** 직접 재신 22.0 mm 봉 모형을 넣어 봤어요. 걸리는 곳 없이 끝까지 들어가고, 사방으로 0.30 mm씩 여유가 있어요(설계값 그대로). 이건 치수 검사예요. 손으로 끼우고 빼는 느낌과 저절로 빠지지 않는지는 실제로 출력해 봐야 알 수 있어요.
- **봉 끝 덮기:** 확인했어요. 막힌 쪽이 구멍 없는 원판이고, 봉 끝이 그 안으로 들어가요.
- **입구 모따기:** 확인했어요. 입구 안쪽이 0.8 mm 비스듬히 깎여 있어서 봉이 쉽게 들어가요.

**그 밖에 알아 두실 것**
- 크기, 닫힌 한 덩어리, 출력판에 들어가는지, 서포트 필요 없음 같은 모델 검사는 모두 통과했어요. 출력 프로그램으로 잘라 보거나 실제로 출력해 보지는 않았어요.
- 봉 끝은 브래킷 없이 밖으로 나와 있다고 보고 만들었어요. 마개가 봉보다 사방으로 2.7 mm쯤 굵어요.
- PLA(Bambu PLA Basic)와 0.20mm Standard 설정을 기준으로 했어요. 다른 필라멘트, 특히 PETG를 쓰면 끼움이 달라질 수 있어요.
- **출력해 보니 너무 빡빡하거나 헐거우면** 알려 주세요. 안지름만 0.1~0.2 mm 바꿔서 바로 다시 만들어 드릴게요.

**파일** (`$PROJECT/deliver/2026-10-24/`)
- `rail_cap_x1c.3mf`: Bambu Studio 프로젝트예요. **파일 > 프로젝트 열기(Open Project)**로 여세요. X1C, 0.20mm Standard, PLA Basic이 이미 설정돼 있어요.
- `cap.stl`: 마개 STL
- `rail_cap.blend`: Blender 파일이에요. 원본은 프로젝트 폴더의 `rail_cap.py` 스크립트라서, 다시 만들면 이 스크립트 기준으로 만들어져요.
- `preview.png`: 미리보기 이미지
- `source/`: 다시 만들 때 필요한 스크립트, 설정, 검사 기록

**치수**

| 항목 | 값 |
|---|---|
| 봉 바깥지름 | 22.0 mm (직접 재신 값) |
| 끼움 여유 + 구멍 보정 | 한쪽 0.15 + 0.15 mm → 안지름 22.6 mm |
| 벽 / 윗면 두께 | 2.4 mm / 2.4 mm |
| 봉이 들어가는 깊이 | 25 mm |
| 전체 크기 | 지름 27.4 × 높이 27.4 mm (PLA 약 7~8 g) |
| 입구 바깥 둥글림 / 안쪽 모따기 | 0.8 mm / 0.8 mm |

바꾸고 싶은 치수가 있나요?

**출력 설정:** 기본 설정에서 이 마개만 **벽 둘레선을 5줄**로 바꿨어요. 2.4 mm 벽을 꽉 채워서, 자주 끼웠다 빼도 잘 갈라지지 않고 안쪽 구멍도 둥글게 나와요. 나머지는 그대로예요. 막힌 쪽이 바닥에 닿게 세워서 출력하고, 서포트는 필요 없어요.

**부품:** 한 덩어리라 따로 나뉜 부품은 없어요. 색을 바꾸려면 Bambu Studio 객체 목록에서 마개를 골라 필라멘트를 바꾸시면 돼요.

**참고한 모델**
- Cap 22mm I.D. (Printables): https://www.printables.com/model/548118-cap-22mm-id
- Pipe Protective Cap All-in-One (MakerWorld): https://makerworld.com/en/models/2947453
- tube end cap wedge clamp (Printables): https://www.printables.com/model/172012-tube-end-cap-wedge-clamp
- Pipe End Cap (Printables): https://www.printables.com/model/1031101-pipe-end-cap

출력해 보시고 잘 맞았는지, 빡빡했는지, 헐거웠는지 알려 주세요. 원하시면 다음 작업에서 참고하도록 이 프린터의 끼움 기록으로 남겨 둘게요.

## finalize after the run

```text
use: verified, geometry: verified
- on-off-by-hand: verified
- covers-end: verified
- lead-in: verified
```

(`finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver <the run's delivery folder>`, run by the grader in the run's folder, output kept outside it.)

## Checklist

The compensation decision:
- **must** `printers.json` records `compensation.holes` `model`, with the reason: yes. It was added to the printer's entry (`elephant_foot` `slicer`, and a `source` naming the generated template's system preset), the rest of the file kept.
- **must** The fitted feature gets the model compensation: yes. Bore 22.6 mm (22.0 + 0.30 snug + 0.30 compensation, on the diameter); the proxy fit used `--min-clearance` 0.30.

Asking:
- **must** Asks nothing the project fixes: yes. It asked about the space at the rail end (fallback) and offered fit-test rings.
- **should** Stops for the reference choice, the concept pick and the base-shape look: yes, all three.

Doing:
- **must** Bambu project from the template into a new folder with its manifest, plus an STL; Open Project: yes.
- **must** finalize with `--deliver`: yes.
- **should** `_material` `pla_basic`, `_print.preset` `0.20mm Standard @BBL X1C`: yes.
- **should** The tube as a caliper dims entry: yes (`rail-pipe`, 22.0).
- **should** The template unchanged: yes.

Agreement:
- **must** yes. Nothing excluded, accepted or delivered as a prototype; the declined fit test and the setting it was left to decide (five wall loops) are recorded as handed back. After a 0.0012 mm bore correction it showed the current build again and recorded the new look.

Claiming:
- **must** Korean, `use` lines: yes. The first line says the hand fit and the hold are not confirmed because the test print was skipped.
- **must** Nothing verified beyond finalize: yes. `on-off-by-hand` is verified on the proxy fit; the message says the motion by hand is not confirmed (the 0.8.0 wording).

finalize:
- **must** `use` verified, `geometry` verified, states as said: yes.

Result: **matches**.
