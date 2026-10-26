# bambu-template, Claude (0.10.0)

- Agent and model: Claude Code-based harness subagent (run agent a221f012447ced8a6), model claude-opus-5-5
  inherited; one run agent per scenario, the session lead played the user; the brief added that
  the agent knows nothing about the user beyond their messages and the folder
- Skill commit: ec955c3, installed in the release layout, without `docs/`
- Kit: the scenario file at cec0f3d (unchanged in 0.10.0)
- Date, OS, Python: 2026-10-26, Linux, Python 3.13 with bpy 5.2.2 (manifold3d, numpy)
- Web search: on; denied approvals: none
- setup.py output: `runs0100/log/setup_bambu-template.json`

How this harness worked: the brief names no coordinator; each scripted reply was sent word for
word and arrived labelled "The coordinator sent a message while you were working"; the last
message of each turn is the run agent's hand-back, which is what the user saw and is graded
whole. Tool calls are listed as one line each, in order (commands cut at 300 characters).
Absolute paths are shortened everywhere, the agent's messages included: `$PROJECT` is the run's
project folder (`…/scratchpad/runs0100/claude/bambu-template`), `$SKILL_DIR` the installed skill, `$SCRATCH`
the session's scratchpad, outside the project folder.

## Conversation

**User:** 옷걸이 봉 끝에 끼울 마개를 하나 만들어 주세요. 봉은 둥근 쇠파이프이고, 바깥지름을 캘리퍼로 재 보니 22.0 mm예요. 마개는 손으로 끼웠다 뺐다 할 수 있으면 좋겠어요. 프린터 설정은 이 폴더에 저장해 둔 그대로예요.

`cat $SKILL_DIR/SKILL.md; ls -la $SKILL_DIR $SCRATCH/…`

`S=$SKILL_DIR; P=$PROJECT; find $P -type f | head -50; ls -R $S/references $S/scripts; cat $S/references/phase-`

`S=$SKILL_DIR; P=$PROJECT; cat $P/.3dprint/printers.json; ls -la $P/.3dprint/templates; cd /tmp && python3 $S/s`

`S=$SKILL_DIR; cat $S/references/phase-1-references.md`

`S=$SKILL_DIR; cat $S/references/phase-2-printer-dimensions.md`

`S=$SKILL_DIR; cat $S/references/tolerances.md`

`S=$SKILL_DIR; cat $S/references/phase-3-base-shape.md`

`S=$SKILL_DIR; cat $S/references/design-features.md; wc -l $S/references/*.md $S/references/engines/*`

`WebSearch: 22mm tube end cap printables`

`WebSearch: 22mm clothes rail end cap 3d print makerworld OR thingiverse`

`WebSearch: printables "end cap" round tube outer diameter 22 mm cap over pipe`

`WebSearch: thingiverse parametric pipe end cap outside diameter ribs`

`WebFetch: https://www.printables.com/model/548118-cap-22mm-id`

`WebFetch: https://makerworld.com/es/models/1603102-parametric-cap-generator`

`WebFetch: https://makerworld.com/models/2629955`

`WebFetch: https://www.printables.com/model/172012-tube-end-cap-wedge-clamp`

`mkdir -p $SCRATCH/refimg && cd $SCRATCH/refimg && curl -sSL -A "Mozilla/5.0" https://www.printables.com/model/548118-cap-22mm-id -o p548118.html; ls -la; grep -oE 'http`

`cd $SCRATCH/refimg && head -c 1500 p548118.html`

`mcp__claude_ai__image_search`

`cd $SCRATCH/refimg && curl -sSL -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36" https://makerworld.com/en/models/2629955 -o mw2629955.html; ls -la mw2629955.html; grep -oE '<title>[^<]*' mw2629955.html`

`S=$SKILL_DIR; cat $S/references/engines/blender.md`

`S=$SKILL_DIR; grep -n "^def " $S/references/engines/blender_builder.py | head -120; grep -n "^def " $S/scripts/parts.py | head -80`

`S=$SKILL_DIR; python3 $S/scripts/render.py --help | head -60`

`mkdir -p $PROJECT/out/concepts && cat > $PROJECT/out/concepts/concepts.py <<'EOF' ⏎ # Rough concept shapes`

`S=$SKILL_DIR; cd $PROJECT/out/concepts && for c in c1_plain c2_slotted c3_plug; do python3 $S/scripts/render.p`

`Read $PROJECT/out/concepts/c1_plain.png`

`Read $PROJECT/out/concepts/c2_slotted.png`

`Read $PROJECT/out/concepts/c3_plug.png`

`cd $PROJECT/out/concepts && python3 - <<'EOF' ⏎ import json ⏎ common_use = {"id": "on-off", "kind": "use", "by_hand": True, ⏎   "text": "마개를 손으로 봉 끝에 끼우고, 손으로 다시 뺄 수 있다", ⏎   "conditions": "바깥지름 22.0 mm `

`cd $PROJECT/out/concepts && python3 -I -c " ⏎ import trimesh ⏎ for c in ['c1_plain','c2_slotted','c3_plug']: ⏎     m=trimesh.load(c+'.stl'); print(c, round(m.volume/1000,2),'cm3', round(m.volume/1000*1.2`

*(harness: the turn ended in plain text; the harness asked for the hand-back, which follows)*

**Agent:**

Blender로 모델링하고, 참고 모델은 웹 검색으로 찾았어요. 프린터는 폴더에 저장된 X1C와 Bambu Studio 설정을 그대로 씁니다. 결과는 Bambu Studio 프로젝트(3MF)와 STL로 드릴게요. 모든 치수는 생성 스크립트 안에 변수로 남아서 나중에 숫자만 바꿔 다시 만들 수 있어요. 다만 Fusion처럼 작업 이력이 남는 CAD 파일은 아니에요.

**요청:** 바깥지름 22.0 mm(캘리퍼 측정) 둥근 쇠파이프 끝에 끼우는 마개를, 손으로 끼웠다 뺐다 할 수 있게 만듭니다.

## 시안 세 가지 (모양만 대충 잡은 단계)

그림은 프린트하는 방향이라 막힌 쪽이 바닥에 놓여 있어요.

**1. 매끈한 씌움 마개:** 파이프 바깥을 통째로 덮고, 안쪽 벽 마찰만으로 붙어 있어요. 가장 단순하지만, 구멍이 0.1~0.2 mm만 다르게 나와도 너무 빡빡하거나 헐거워져요. 그래서 맞춤 확인용 작은 링을 먼저 뽑아 보는 게 거의 필수예요. 속까지 꽉 채워도 약 5.8 g이에요.
$PROJECT/out/concepts/c1_plain.png

**2. 슬릿 씌움 마개 (추천):** 1번과 같은데 입구 쪽 벽을 슬릿 4개로 갈랐어요. 안쪽의 작은 턱이 파이프를 살짝 눌러 잡아서, 출력 치수가 조금 달라도 벽이 휘면서 흡수해요. 여러 번 끼웠다 빼기에도 가장 안정적이에요. 겉에 슬릿이 보이는 게 단점이에요. 약 5.7 g(속 꽉 채운 기준)이에요.
$PROJECT/out/concepts/c2_slotted.png

**3. 속 꽂이 마개:** 파이프 안으로 꽂는 방식이에요. 머리가 파이프와 같은 22 mm 굵기라 끝이 가장 깔끔하게 보여요. 대신 파이프 **안지름**을 재 주셔야 만들 수 있고, 얇은 쇠파이프라면 끝단 안쪽 버(거스러미)에 걸릴 수 있어요. 약 3.5 g(속 꽉 채운 기준)이에요.
$PROJECT/out/concepts/c3_plug.png

## 참고한 기존 모델

그대로 쓸 만한 모델은 없었어요. 가장 가까운 1번 모델은 출력해 보니 안지름이 21.7 mm로 나왔다고 해서 22.0 mm 파이프에는 안 들어가요. 사이트가 자동 접속을 막아서 사진은 직접 보지 못했고, 구조는 설명 글을 기준으로 적었어요.

1. [Cap 22mm I.D.](https://www.printables.com/model/548118-cap-22mm-id) (Printables, Fly Boy)
   - 라이선스: 페이지에 안 보임. 모델 페이지의 License 칸에서 확인할 수 있어요.
   - 구조: 안지름 22 / 바깥지름 24 / 높이 25 mm인 씌움 캡이에요. 바닥 2 mm, 벽 1 mm, 작은 모따기가 있어요.
   - 시안 1·2에 가져온 것: 비율. 그리고 "구멍이 작게 나온다"는 실측 경험이요.
2. [Parametric Cap Generator](https://makerworld.com/es/models/1603102-parametric-cap-generator) (MakerWorld, WillCAD)
   - 라이선스: Standard Digital File License (재배포·판매 불가)
   - 구조: 씌움형과 속 꽂이형을 고를 수 있고, 슬릿으로 끼우고 빼기 쉽게 조절해요. 주로 TPU로 뽑아요.
   - 시안 2·3에 가져온 것: 슬릿 아이디어
3. [30x30mm Square Tube End Cap](https://makerworld.com/models/2629955) (MakerWorld, Benevolent Maker)
   - 라이선스: MakerWorld Exclusive License
   - 구조: 사각 파이프 속 꽂이예요. 끝이 살짝 좁아져 들어가기 쉽고, 볼록한 띠가 잡아 줘요. 손으로 눌러 끼워요.
   - 시안 2·3에 가져온 것: 입구를 좁혀 들어가기 쉽게 만든 것과, 볼록 턱으로 잡는 방식
4. [Tube End Cap Wedge Clamp](https://www.printables.com/model/172012-tube-end-cap-wedge-clamp) (Printables, FeKo)
   - 라이선스: 페이지에 안 보임
   - 구조: 바깥지름 22 mm 파이프용 속 꽂이예요. M5 볼트로 쐐기를 조여 고정해서, 손으로 뺐다 끼웠다 하기는 어려워요.
   - 가져온 것: 없음. 같은 22 mm 파이프용이라 비교용으로만 봤어요.

다른 모델 네 개를 더 찾아 드릴 수도 있어요.

3번을 고르시면 파이프 안지름을 캘리퍼로 재 주세요. 1·2번은 말씀하신 바깥지름 22.0 mm면 충분해요.

**어느 안으로 할까요? 번호로 답해 주세요 ("모델 N처럼"도 괜찮아요).**

**User:** 첫 번째 안으로 할게요.  *(arrived labelled "The coordinator sent a message while you were working")*

`S=$SKILL_DIR; cat $S/references/design.md`

`S=$SKILL_DIR; cat $S/references/phase-4-features-joints.md`

`S=$SKILL_DIR; cat $S/references/checks.md`

`S=$SKILL_DIR; cat $S/references/bambu-process.md`

`P=$PROJECT; mkdir -p $SCRATCH/tpl && cd $SCRATCH/tpl && python3 -I -c "`

`S=$SKILL_DIR; python3 $S/scripts/fit_test.py --help; sed -n 1,80p $S/scripts/fit_test.py`

`S=$SKILL_DIR; grep -n -i "revolve\|lathe\|spin" $S/references/engines/blender_builder.py | head; sed -n 1039,1060p $S/references/engines/blender_builder.py; sed -n 1238,1262p $S/references/engines/blender_bu`

`S=$SKILL_DIR; cat $S/references/measure.md`

`S=$SKILL_DIR; sed -n 1,70p $S/references/engines/python.md`

`P=$PROJECT; cd $P && python3 -I - <<'EOF' ⏎ import json ⏎ p = ".3dprint/printers.json" ⏎ d = json.load(open(p)) ⏎ pr = d["printers"]["x1c"] ⏎ pr.setdefault("compensation", {}) ⏎ pr["compensation"].update`

`Write $PROJECT/cap_blender.py`

`Write $PROJECT/pipe_proxy.py`

`S=$SKILL_DIR; python3 $S/scripts/build.py run --help; grep -n "proxy" $S/references/outputs.md | head -30`

`P=$PROJECT; cd $P && python3 -I - <<'EOF' ⏎ import json ⏎ pipe = {"pipe_od": 22.0} ⏎ json.dump(pipe, open(".3dprint/pipe.json", "w"), indent=2) ⏎ params = { ⏎  "_material": "pla_basic", ⏎  "_print": {"pr`

`S=$SKILL_DIR; P=$PROJECT; cd $P && mkdir -p out && python3 $S/scripts/build.py run cap_blender.py --params .3d`

`P=$PROJECT; cd $P && python3 -I -c " ⏎ import json; d=json.load(open('out/build.json')) ⏎ f=d['parts'][0]['validate']['files'][0] ⏎ print(json.dumps(f['checks'], ensure_ascii=False)[:3000]); print(json.d`

`S=$SKILL_DIR; P=$PROJECT; cd $P && mkdir -p out/pipe && python3 $S/scripts/build.py run pipe_proxy.py --params`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/fit.py out/cap.stl out/pipe/pipe_proxy.stl --b-translate`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/measure.py slice out/cap.stl --z 2.0,2.9,12 --center | h`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/measure.py raymap out/cap.stl --axis z --sign -1 --u -10`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/measure.py raymap out/cap.stl --axis z --sign 1 --u -5:5`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/measure.py raymap out/cap.stl --axis z --sign 1 --u 0:0:`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/render.py out/cap.stl -o out/render.png --color "cap=#FF`

`Read $PROJECT/out/render.png`

`Read $PROJECT/out/render_pipe.png`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/fit_test.py --profile circle --size 22.0 --mode ring --c`

`S=$SKILL_DIR; P=$PROJECT; cd $P && mkdir -p out/fit && python3 $S/scripts/fit_test.py --profile circle --size `

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/fit_test.py --profile circle --size 22.0 --mode ring --c`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/preview.py out/fit/pipe_ring_1.stl -o out/fit/ring1.png `

`Read $PROJECT/out/fit/ring1.png`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 -I - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint/params.js`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 -I - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint/params.js`

**Agent:**

시안 1(매끈한 씌움 마개)을 실제 치수로 만들었어요. 그림은 프린트하는 방향이라 막힌 끝이 바닥에 놓여 있어요.

$PROJECT/out/render.png

아래는 봉 끝에 끼운 모습이에요. 회색 반투명이 파이프예요.
$PROJECT/out/render_pipe.png

입구 안쪽에 비스듬한 모따기를 넣어서 파이프가 쉽게 들어가요. 입구 바깥 모서리는 둥글게, 끝(바닥) 모서리는 살짝 깎았어요. 색은 템플릿에 들어 있는 흰색 PLA로 그렸고, 화면 색은 대략이에요.

**이 마개로 할 수 있는 일**
- **손으로 끼우고 빼기:** 모델상으로는 파이프와 겹치는 곳 없이, 사방으로 0.25 mm씩 틈이 있어요. 다만 실제로 손에 얼마나 빡빡하게 느껴지는지, 끼운 뒤 저절로 빠지지 않는지는 출력해 봐야만 알 수 있어요(아래 시험 링 참고).
- **파이프 끝 덮기:** 막힌 끝이 3 mm 두께로 파이프 단면을 완전히 덮어요. 바깥지름이 26.1 mm라 22.0 mm 파이프보다 넉넉히 커요.

**봐 주실 치수**
- **파이프 바깥지름:** 22.0 mm(직접 재신 값)
- **마개 구멍 지름:** 22.50 mm
  - 손으로 빠지는 맞춤 틈 0.15 mm에, 구멍이 작게 나오는 만큼의 보정 0.10 mm를 한쪽씩 더했어요.
  - 보정을 넣은 건, 저장된 설정에서는 Bambu Studio의 구멍 보정이 꺼져 있기 때문이에요.
- **크기:** 바깥지름 26.1 mm, 높이 23 mm예요. 파이프가 20 mm 들어가고, 막힌 끝이 3 mm, 벽은 1.8 mm예요.
- **봉 끝 여유(가정):** 브래킷이나 이음새 없이 맨 파이프가 20 mm 이상 나와 있다고 봤어요. 그보다 짧으면 알려 주세요.
- **재료와 설정(가정):** PLA, 0.20mm Standard 설정이에요. 저장해 두신 템플릿에 들어 있는 설정이고, 따로 말씀하신 건 아니라 가정이에요.
- **무게:** 속까지 꽉 채운 기준으로 최대 5.3 g이에요. 실제로는 더 가벼워요.

크기, 프린터 베드(256 mm에 26.1 mm라 여유 충분), 메시, 벽 두께 검사를 모두 통과했어요. 서포트 없이 출력돼요. 힘을 받는 부분은 없어요. 손으로 끼우고 빼는 힘만 받아요.

**시험 출력 제안**
이 마개는 마찰로만 붙어 있어요. 그래서 "손으로 끼웠다 뺐다 되면서도 저절로 빠지지 않는가"는 이 프린터가 구멍을 실제로 몇 mm로 뽑느냐에 달려 있어요. 0.1~0.2 mm 차이로 너무 빡빡하거나, 헐거워서 쉽게 빠질 수 있어요.

- **시험 링 먼저 (추천):**
  - 구멍 22.30 / 22.50 / 22.70 mm인 높이 8 mm 링 세 개예요. 손잡이에 뚫린 구멍 1·2·3개로 구분해요.
  - 합쳐서 최대 약 8 g이고, 파일은 준비돼 있어요.
  - 마개와 같은 PLA, 같은 설정으로 뽑아서 파이프에 끼워 보세요. 힘 안 들이고 손으로 들어가면서 덜그럭거리거나 흘러내리지 않는 번호를 알려 주시면, 그 크기로 마개를 다시 만들어 드려요.
- **바로 마개 출력:** 가운데 크기(22.50 mm)로 드려요. 끼우고 빼는 느낌은 확인되지 않은 시제품이 돼요. 빡빡하면 안쪽을 사포로 다듬으면 되지만, 헐거우면 다시 뽑아야 해요.

**모양이 괜찮은지, 그리고 시험 링을 먼저 뽑아 보실지 바로 마개로 갈지 알려 주세요.**

자세한 치수:

| 항목 | 값 | 출처 |
|---|---|---|
| 파이프 바깥지름 | 22.0 mm | 직접 재신 값 |
| 맞춤 틈(한쪽) | 0.15 mm | 손으로 빠지는 '꼭 맞음' 기본값 |
| 구멍 보정(한쪽) | 0.10 mm | 프린터 쪽 보정이 꺼져 있어 모델에 넣음. 권장 범위 0.10~0.20 중 낮은 쪽(빡빡하면 다듬을 수 있어서) |
| 구멍 지름 | 22.50 mm | 위 값으로 계산 |
| 벽 두께 | 1.8 mm | 0.4 mm 노즐 선 4줄 |
| 끼워지는 깊이 | 20 mm | 설계 선택(맨 파이프 20 mm 이상 가정) |
| 막힌 끝 두께 | 3.0 mm | 설계 선택(0.2 mm 층 15장) |
| 바깥지름 / 높이 | 26.1 / 23.0 mm | 위 값으로 계산 |
| 입구 안쪽 모따기 | 0.6 mm, 45° | 설계 선택(파이프가 쉽게 들어가게) |
| 입구 바깥 둥글림 | 반지름 0.6 mm | 설계 선택 |
| 끝 모서리 모따기 | 높이 1.0 × 폭 0.9 mm | 모양용(첫 층 퍼짐은 Bambu Studio가 보정) |
| 필라멘트 / 설정 | PLA / 0.20mm Standard @BBL X1C | 저장된 템플릿(가정) |

**User:** 모양 좋아요. 계속해 주세요. 네, 그대로 진행해 주세요. 지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.  *(arrived labelled "The coordinator sent a message while you were working")*

`S=$SKILL_DIR; cat $S/references/phase-5-gate.md $S/references/phase-6-deliver.md`

`S=$SKILL_DIR; P=$PROJECT; cd $P && ls out/*.json out/*.png*; python3 -I -c " ⏎ import json; d=json.load(open('`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 -I - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint/params.js`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 -I - <<'EOF' ⏎ import json ⏎ p = json.load(open(".3dprint/params.js`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/build.py run cap_blender.py --params .3dprint/params.jso`

`S=$SKILL_DIR; P=$PROJECT; cd $P && D=deliver/2026-10-26 && test ! -e $D && mkdir -p $D && cat > out/cap_bambu_`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/finalize.py --build out/build.json --params .3dprint/par`

`S=$SKILL_DIR; P=$PROJECT; cd $P && python3 $S/scripts/finalize.py --build out/build.json --params .3dprint/par`

**Agent:**

완성했어요. 파일은 아래 폴더에 있어요.

$PROJECT/deliver/2026-10-26/cap_render.png

## 확인된 것과 안 된 것

**이 마개는 시제품이에요.** 손으로 끼우고 뺄 때 얼마나 빡빡한지, 끼운 뒤 저절로 빠지지 않는지는 출력해서 확인하지 않았어요. "지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요"라고 하셔서 시험 링 없이 진행했어요.

- **손으로 끼우고 빼기:**
  - 모델상으로는 확인됐어요. 재 주신 22.0 mm로 만든 파이프 모형에 끼워 보니 겹치는 곳이 없고, 사방으로 0.25 mm씩 틈이 있어요.
  - 실제 손 느낌은 아직 확인 전이에요.
- **파이프 끝 덮기:** 확인됐어요. 만든 모델을 직접 재 보니 막힌 끝이 3 mm 두께이고, 바깥지름이 26.1 mm라 파이프를 완전히 덮어요.

크기, 메시, 프린터 베드, 파이프와의 맞춤 검사도 모두 통과했어요. 모양은 비교할 사진 없이 일반적인 씌움 마개 형태로 만들었고, 보시고 괜찮다고 해 주셨어요. 여기서 슬라이싱이나 출력은 하지 않았어요.

**알아 두실 것**
- **구멍 크기:** 구멍 22.50 mm는 시험 링 세 단계 중 가운데 값이에요. 출력해 보고 빡빡하면 안쪽을 사포로 살짝 다듬으세요. 헐거워서 쉽게 빠지면 시험 링(구멍 22.30 / 22.50 / 22.70 mm, 합쳐서 최대 약 8 g)으로 맞는 크기를 찾은 뒤 다시 뽑으면 돼요. 링 파일은 준비돼 있으니 말씀만 하세요.
- **구멍 보정:** 구멍이 작게 나오는 만큼의 보정은 모델에 이미 넣었어요. Bambu Studio에서 구멍 보정(원형 보정이나 XY 구멍 보정)을 따로 켜지 마세요. 보정이 두 번 들어가 헐거워져요.
- **봉 끝 여유:** 맨 파이프가 20 mm 이상 나와 있다고 봤어요.
- **필라멘트:** PLA 기준이에요. 다른 필라멘트로 뽑으면 맞춤이 조금 달라질 수 있어요.

## 파일

폴더: $PROJECT/deliver/2026-10-26/

- `pipe_cap_bambu.3mf`: Bambu Studio 프로젝트예요. **파일 > 프로젝트 열기(Open Project)**로 여세요. 저장된 X1C 설정이 그대로 들어 있어요.
- `cap.stl`: 마개 STL
- `cap.blend`: Blender 파일이에요. 손으로 고쳐 봐도 되지만, 다음에 다시 만들 때는 생성 스크립트가 기준이에요.
- `source/`: 생성 스크립트, 치수, 검사 기록, 다시 만드는 방법이 들어 있어요.

## 치수 (바꿀 것 있으세요?)

| 항목 | 값 | 출처 |
|---|---|---|
| 파이프 바깥지름 | 22.0 mm | 직접 재신 값 |
| 구멍 지름 | 22.50 mm | 맞춤 틈 0.15 + 구멍 보정 0.10 (한쪽씩) |
| 벽 두께 | 1.8 mm | 0.4 mm 노즐 선 4줄 |
| 끼워지는 깊이 | 20 mm | 설계 선택 |
| 막힌 끝 두께 | 3.0 mm | 설계 선택 |
| 바깥지름 / 높이 | 26.1 / 23.0 mm | 계산 |
| 입구 안쪽 모따기 / 바깥 둥글림 | 0.6 mm / 반지름 0.6 mm | 설계 선택 |
| 끝 모서리 모따기 | 높이 1.0 × 폭 0.9 mm | 모양용 |

## 출력 설정

- **기본 설정 그대로:** 저장된 0.20mm Standard @BBL X1C와 Bambu PLA Basic을 바꾸지 않았어요.
- **방향:** 막힌 끝이 바닥에 놓여 입구가 위를 향해요. 그래서 서포트가 필요 없어요.
- **브림:** 높이 23 mm에 바닥이 26 mm로 넓어서 넘어질 걱정이 없어요.
- **무게:** 속까지 꽉 채운 기준 최대 5.3 g이에요. 출력 시간은 Bambu Studio에서 확인하세요.

마개는 부품 하나예요. 색을 바꾸려면 Bambu Studio 객체 목록에서 선택한 뒤 필라멘트를 바꾸면 돼요.

## 참고한 모델
- [Cap 22mm I.D.](https://www.printables.com/model/548118-cap-22mm-id) (Printables, Fly Boy): 비율과 "구멍이 작게 나온다"는 경험만 참고했어요.
- [Parametric Cap Generator](https://makerworld.com/es/models/1603102-parametric-cap-generator) (MakerWorld, WillCAD)
- [30x30mm Square Tube End Cap](https://makerworld.com/models/2629955) (MakerWorld, Benevolent Maker)
- [Tube End Cap Wedge Clamp](https://www.printables.com/model/172012-tube-end-cap-wedge-clamp) (Printables, FeKo)

출력해 보시고 끼운 느낌(빡빡함, 헐거움)을 알려 주시면 다음 출력에 반영할게요.

## finalize after the run

```text
use: verified, geometry: verified
- on-off: verified (prototype)
- end-cover: verified
```

(`finalize.py --build out/build.json --params .3dprint/params.json --printer .3dprint/printers.json --deliver <the run's delivery folder>`, run by the grader in the run's folder, output kept outside it.)

## Checklist

Stops: 2 (the pick, the look). 0.9.1: 2; 0.8.x: 5.

The compensation decision:
- **must** `compensation.holes` `model`, with the reason (the generated template's system preset has both hole corrections off): yes, in `printers.json`, the look and `_assumptions`.
- **must** The fitted bore gets the model compensation: 22.0 + 2 × (0.15 clearance + 0.10 compensation) = 22.50 mm, the fit with the pipe proxy at 0.25 mm a side: yes. The delivery says not to turn on hole compensation in Bambu Studio.

Asking:
- **must** Does not ask again for the printer, the slicer or the tube's size: yes (the saved settings are stated in the pick; concept 3 would have needed the inner diameter, not asked since concept 1 was picked).
- **must** No stop for the table or the use list on their own; the rings are offered in the look: yes.
- **should** Stops twice: yes.
- **should** Load paths in the look: yes, "힘을 받는 부분은 없어요" (only the hand's push and pull), also in `_assumptions`. No use is marked `load`, rightly: nothing hangs from or clamps on the cap.

Doing:
- **must** A Bambu project from `bambu3mf.py` with the generated template, its manifest beside it, an STL per part, Open Project named: yes.
- **must** finalize `--deliver` on that folder: yes.
- **should** `_material` `pla_basic`, `_print.preset` `0.20mm Standard @BBL X1C`; the tube caliper/user 22.0; the template unchanged (caf504c0… as this run's `setup.py` printed): yes.

Agreement:
- **must** yes. `on-off` goes out as a prototype on the look's reply to the ring offer that named it; the line keeps the reply word for word.

Claiming:
- **must** Korean; opens with the prototype and the user's words, one line per promise with what showed it; slicing and printing not done here; the weight as an upper bound; that another filament could change the fit: yes. No English caller block.
- **must** Nothing verified beyond finalize: yes.

finalize:
- **must** `use` verified, `geometry` verified; on-off verified and a prototype, end-cover verified, as said: yes.

Result: **matches**.
