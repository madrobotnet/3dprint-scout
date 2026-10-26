# 3dprint-scout

[English](README.md)

<img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/docs/demo.ko.webp" width="100%" alt="데모: 문장 하나가 출력된 폰 거치대가 되기까지. 3dprint-scout가 기존 모델을 찾고, 옆 단면을 그리고, 부품 두 개를 만들고, 폰 세 대로 맞춤을 검사하고, Bambu Studio에서 슬라이스하고, 렌더와 같은 모양으로 출력돼요.">

3D 프린팅할 물건을 **레퍼런스부터** 설계하는 에이전트 스킬이에요.

만들고 싶은 물건을 말하면, 먼저 이미 있는 3D 모델을 찾아 보여 주고 참고·조합·새로 만들기·그대로
쓰기 중에서 고르게 해요. 그다음 모델링하고 숫자로 검증한 뒤 내 프린터와 슬라이서에 맞는 파일로
돌려줘요. Bambu Studio라면 객체별 출력 설정까지 담은 프로젝트 파일이에요.

## 진행 순서

1. **레퍼런스와 콘셉트(고르기)** — Printables, Thingiverse, MakerWorld 등에서 찾은 기존 모델 4개를
   라이선스와 함께, 그리고 그 모델에서 빌려 온 대략적인 시안 두세 가지를 미리보기 이미지와 함께 보여
   줘요. 시안 번호로 고르거나, "2번 모델처럼", 또는 이미 맞는 모델이 있으면 "그대로 쓸게요"라고 하면 돼요.
2. **프린터와 슬라이서** — 저장된 설정이 없으면 같은 메시지에서 쉬운 말로 물어봐요("어떤 프린터를 쓰고,
   출력 파일은 어떤 프로그램으로 여세요? 프로그램은 몰라도 괜찮아요"). 모르면 알맞은 기본값을 써요.
3. **치수** — 모든 치수를 출처와 함께 표로, 확인 때 보여 줘요(캘리퍼 실측, 공식 사양, 서로 일치하는 2차 자료
   두 곳). 지어낸 숫자는 없어요. 모양을 정확히 모르는 물건에 끼울 부품이면, 작은 끼워보기 조각을
   먼저 만들어요(공차를 세 단계로 나누고 구멍 1·2·3개로 표시해요). 이때 부품으로 할 일(폰 올리기,
   케이블 빼기)도 함께 목록으로 적고, 항목마다 나중에 그 항목의 근거로 확인해요.
4. **모델링** — [Blender](https://www.blender.org)가 있으면 어떤 모양이든 Blender가 먼저예요(MCP로
   연결한 내 Blender, `blender` 실행 파일, 또는 `bpy` 모듈): 정확한 반지름의 필렛, 곡면을 따라가는
   라운드는 단면에서, Manifold 불리언, 어떤 글꼴이든 글자, STL 옆에 편집 가능한 `.blend`, 그리고
   Blender의 Python에 [manifold3d](https://github.com/elalish/manifold)가 있으면 Python 부품
   라이브러리의 기계 부품 도우미까지 써요. Blender가 없으면 기계 부품은 Python(manifold3d) 또는
   OpenSCAD, 유기적인 모양은 Python으로 만들고, Fusion(MCP 연결)은 편집 가능한 CAD 설계를 원할 때만
   써요.
   Python 엔진에는 검증된 부품 라이브러리(모서리를 둥글리거나 깎은 상자, 나사·인서트 구멍, 물방울
   모양 구멍, 보스, 스냅 후크, 한 번에 출력하는 경첩, 글자, 나사산)와 매끈하게 이어지는 유기적인
   모양을 위한 SDF(부호 거리 함수) 도구가 함께 들어 있어요. 역할이 따로 있거나 색을 달리할 만한
   부분(걸쇠, 레버, 라벨)은 같은 객체 안의 별도 파트로 만들어서, 슬라이서에서 파트를 고르기만 하면
   다른 필라멘트를 줄 수 있어요. 한 번에 출력하는 움직이는 부품은 틈을 그대로 지켜요.
5. **검증** — 부품마다 크기, 베드에 들어가는지, 메시가 닫혀 있는지, 오버행, 벽 두께, 결과가
   최신인지(STL이 지금 소스·매개변수와 일치하는지)를 검사해요. 여러 파트로 된 객체는 전체로도
   검사해요(베드에 들어가는지, 합친 모양의 오버행, 붙는 파트가 실제로 닿는지, 움직이는 파트가
   틈을 지키는지). 서로 끼워지는 부품은 겹침, 유격, 틈, 접촉 면적까지 맞춰 보고, 움직이는 부품은
   돌려 보면서 어디서 걸리는지 찾아요. 힘을 받는 핀·레버·걸쇠는 검증된 참고 부품이 있으면 그 치수와
   나란히 비교하고, 간단한 강도 계산(`strength.py`, Bambu Lab 데이터시트 값과 출처 있는 손힘 표)을
   거치고, 여유가 부족하면 그 부분만 몇 그램짜리로 먼저 뽑아 봐요. 한 번에 출력하는 뚜껑 경첩은
   여유와 상관없이 늘 그 시험편을 먼저 뽑아요. 모든 부품은 화면 없이도 렌더링한 미리보기
   이미지(등각·정면·측면·위)를 받고, Blender가 있으면 내 필라멘트 색으로 렌더링한 이미지도 받아요.
6. **전달** — 먼저 최종 보고서(`finalize.py`)를 만들어요: 약속한 것마다 지금 부품으로 만든 그
   약속의 근거가 있을 때만 확인됐다고 말하고(아니면 가정, 확인 안 됨, 시제품으로 이름을 대요),
   그다음 형상이 검증됐는지, 참고 자료가 보여 주는 방향 기준으로 모양이 어디까지 확인됐는지,
   슬라이싱과 실제 출력은 여기서 확인하지 않았다는 것, 그리고 남은 항목 전부. 그다음 부품별 STL과
   슬라이서에 맞는 3MF, 바꾼 출력 설정과 그 이유, 어떤 파트가 따로 있고 색을 어떻게 바꾸는지 한 줄,
   그리고 생성 스크립트·파라미터·근거·다시 만드는 명령을 담아 같은 판정을 다시 낼 수 있는 묶음을
   줘요.

멈추는 곳은 두 번이에요. 고르기, 그리고 다 만들고 점검한 부품을 보는 확인이에요. 확인에는 약속, 판단할
치수, 전체 치수표, 필요할 때는 시험 출력 제안이 같이 나와요. 그 사이에는 새로 생긴 일(검사 실패, 확인해 주신
값을 바꿔야 할 때)이 있을 때만 멈춰요. 아직 확인되지 않은 약속은 확인 때나 그 일이 생겼을 때 함께 정해요:
재 보기, 시험 조각 출력, 확인 없이 시제품으로 받기, 약속에서 빼기. 단계마다 멈추길 원하면 "단계별로
보여 주세요"라고 하면 돼요. 끼울 대상의 파일(제조사 키트, 참고
모델)을 주면 그 파일에서 접하는 부분의 치수만 재고, 형상은 가져오지 않아요.

## 예제

<p>
<a href="https://github.com/madrobotnet/3dprint-scout/tree/main/examples/aa-battery-box/"><img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/examples/aa-battery-box/thumb.png" width="200" alt="AA battery box, OpenSCAD"></a>
<a href="https://github.com/madrobotnet/3dprint-scout/tree/main/examples/snap-box/"><img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/examples/snap-box/thumb.png" width="200" alt="snap-fit box, part library"></a>
<a href="https://github.com/madrobotnet/3dprint-scout/tree/main/examples/leaf-handle/"><img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/examples/leaf-handle/thumb.png" width="200" alt="leaf door handle, SDF"></a>
<a href="https://github.com/madrobotnet/3dprint-scout/tree/main/examples/fit-test/"><img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/examples/fit-test/thumb.png" width="200" alt="fit-test rings"></a>
<a href="https://github.com/madrobotnet/3dprint-scout/tree/main/examples/latch-box/"><img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/examples/latch-box/thumb.png" width="200" alt="latch box, colour part and print-in-place latch"></a>
<a href="https://github.com/madrobotnet/3dprint-scout/tree/main/examples/blender-coaster/"><img src="https://raw.githubusercontent.com/madrobotnet/3dprint-scout/main/examples/blender-coaster/thumb.png" width="200" alt="scalloped coaster, Blender"></a>
</p>

AA 건전지 상자(OpenSCAD), 스냅핏 상자(부품 라이브러리), 나뭇잎 문 손잡이(SDF 도구), 끼워보기
링, 색을 따로 줄 수 있는 라벨 부품과 한 번에 출력하는 걸쇠가 달린 걸쇠 상자, 그리고 글자를 돋을새김한
물결 테두리 컵받침(Blender)을 스킬의 스크립트로 만들었어요. 예제마다 소스, 매개변수, 검사 결과,
다시 빌드하는 명령이 들어 있어요. [examples/](https://github.com/madrobotnet/3dprint-scout/tree/main/examples)를 보세요.

## 설치

**Claude (웹·데스크톱).** [최신 릴리스](https://github.com/madrobotnet/3dprint-scout/releases/latest)에서 `3dprint-scout-v<버전>.zip`을
받은 뒤 **Customize > Skills**에서 **+**를 누르고 **Create skill > Upload a skill**로 올려요. 코드
실행 기능이 켜져 있어야 해요([Claude에서 스킬 사용하기](https://support.claude.com/en/articles/12512180-use-skills-in-claude)).

**Claude Code.** 개인 스킬 폴더(또는 프로젝트의 `.claude/skills/`)에 받아요.

```bash
git clone https://github.com/madrobotnet/3dprint-scout ~/.claude/skills/3dprint-scout
```

**어떤 에이전트든 명령 한 줄로.** [skills CLI](https://github.com/vercel-labs/skills)가 Claude Code,
Codex, Cursor, OpenCode 등 여러 에이전트에 설치해 줘요.

```bash
npx skills add madrobotnet/3dprint-scout
```

**다른 에이전트.** [Agent Skills](https://agentskills.io) 형식을 따르고 특정 에이전트의 도구 이름을
쓰지 않아서 `SKILL.md` 스킬을 읽는 에이전트라면 같은 폴더를 그대로 쓸 수 있어요. 그 에이전트가
스킬을 읽는 위치에 복사하세요.

**귀찮으면 에이전트에게 맡기세요.** *"https://github.com/madrobotnet/3dprint-scout 에 있는 스킬을
설치해 줘"*라고 말하면 돼요. 명령을 실행할 수 있는 에이전트라면 대개 알아서 설정해요.

그다음엔 어떤 언어로든 그냥 요청하면 돼요. 예: *"6mm 봉에 거는 벽걸이 고리 만들어줘"*, *"이 기판
케이스 만들어줘"*, *"X2D 프린터 문 손잡이를 만들고 싶어"*.

## 필요한 것

가상환경 설치법, 확인한 Python/Blender 조합, 실행 확인 명령은
[개발 환경 안내](references/development.md)에 정리했어요. 표준 라이브러리 검사 / Python 모델링 /
Blender 모델링 중 필요한 구성을 선택하세요. 아래 Python 최소 버전을 만족한다고 모든 버전에
맞는 bpy 패키지가 있는 것은 아니에요.

- Python 3.9 이상 (3.9, 3.13에서 시험). 검증기와 3MF 작성기는 표준 라이브러리만 써요.
- 모델링 엔진 하나: MCP로 연결한 **Fusion**, **OpenSCAD**(2021.01 또는 Manifold 백엔드가 있는 최신
  빌드), 또는 `pip install manifold3d`. **Blender**는 선택 사항인데, 있으면 첫 번째 엔진이 되고
  렌더링도 맡아요: MCP 커넥터로 연결한 내 Blender, `blender` 실행 파일, 또는 `pip install bpy`.
  어느 쪽이든 4.5 LTS 이상이어야 해요(Manifold 불리언). 단,
  [공식 Blender MCP 애드온](https://www.blender.org/lab/mcp-server/)은 Blender 5.1 이상이 필요해요.
  Blender가 없으면 예전처럼 다른 엔진이 모두 맡아요.
- 미리보기 이미지, 치수 재기 도구, 끼움 검사의 접촉 면적 계산에는 `numpy`, 끼움 검사와 회전
  검사·객체 검사·끼워보기 조각·부품 라이브러리·SDF 도구에는 `manifold3d`, 벽 두께 검사에는
  `rtree`(numpy와 함께)가 필요해요. 부품에 글자를 넣으려면 `matplotlib`, 또는 `fonttools`와 글꼴
  파일이 필요해요. 모두 선택 사항이에요. 없는 것은 "확인 못 함"이나 분명한 오류로 알려 주고, 절대
  있는 척하지 않아요.

## Bambu Studio

Bambu Lab 프린터에서는 Bambu Studio 프로젝트 파일을 만들어요(**파일 > 프로젝트 열기**로 여세요).
이때 템플릿 프로젝트가 필요한데, 두 가지 방법이 있어요.

- **직접 저장 (먼저 권해요).** Bambu Studio에서 프린터, 필라멘트, 출력 프로필을 고른 뒤 빈
  프로젝트를 저장해서 스킬에 주세요. 내가 손본 프로세스 설정과 AMS 필라멘트 구성이 그대로
  유지돼요. 이 파일에는 내 프리셋과 Bambu 계정 ID가 들어 있어요. 스킬이 만드는 파일에서는 ID를
  지우지만 템플릿 파일 자체는 공개하지 마세요.
- **자동 생성 (대안).** `bambu_template.py`가 시스템 프리셋의 **이름**만 적은 빈 프로젝트를
  만들어요. 예를 들면 `0.20mm Standard @BBL X2D`와 Bambu PLA Basic이에요. Bambu Studio가 이 파일을
  열 때 내 컴퓨터에 설치된 프리셋에서 모든 값을 채워요. 설정값을 복사하지 않고 개인정보도 없어요.

여러 파트로 된 객체는 Bambu 객체 하나로 들어가고, 파트마다 이름과 필라멘트가 붙은 채 조립된
위치 그대로 놓여요. 객체별 설정(서포트, 서포트 인터페이스 필라멘트와 간격, 브림, 벽, 채움, 레이어
높이 등)은 허용목록에 있는 키만, 범위 검사를 통과한 값만 써요. 프로그램을 실행하거나 G-code를
바꿀 수 있는 키는 절대 쓰지 않아요. X2D와 H2D에서는 두 노즐이 다 필요한 객체를 두 노즐이 모두
닿는 자리에 놓아요.

## 프로젝트에 만드는 것

| 경로 | 내용 |
|---|---|
| `.3dprint/params.json` | 모든 치수, 그리고 묻지 못하고 정한 가정. 약속한 것과 그 근거(`_verify`)도 여기에 적어요 |
| `.3dprint/printers.json` | 프린터 정보: 베드, 노즐, 슬라이서, 템플릿 (시리얼 번호·접속 코드·IP는 저장 안 함) |
| `.3dprint/calibration.json` | 내 출력 결과 기록(어느 끼워보기 링이 맞았는지, 어떤 걸쇠가 버티고 부러졌는지). 내가 "네"라고 한 뒤에만 써요. 여기 값이 모든 표보다 우선이에요 |
| `~/.3dprint/calibration.json` (홈 폴더) | 모든 프로젝트에 쓰도록 남기기로 한 결과. 따로 물어본 뒤에만 써요. 프로젝트 자체 기록이 이보다 우선이에요 |
| `.3dprint/templates/` | Bambu Studio 템플릿. 직접 저장한 템플릿에는 계정 ID가 있으니 공개하지 마세요 |
| `out/` | 작업 폴더. 빌드할 때마다 새로 써요: STL, 빌드 기록, 기본 3MF, Blender로 만들었다면 `.blend`, 미리보기 이미지, 끼워보기 조각 |
| 새 전달 폴더 | 최종 파일. 기존 파일은 절대 덮어쓰지 않아요 |

## 현황

**v0.9.1**은 0.9.0의 첫 실제 출력 시험(Bambu Lab X2D 배기 어댑터)에서 나온 것을 고쳤어요. 가장 비슷한 기존 모델은 페이지 글만이 아니라 어떻게 만들어졌는지를 보고, 이미 쓰고 있는 것이 맞았는지 물어요. 자료마다 치수가 다르면 이미 쓰고 있고 잘 맞는 물건이 기준이 돼요. 부품을 보여 주기 전에 힘이 지나가는 곳을 하나씩 적고 크기를 맞춰 두기 때문에, 튼튼한지 사용자가 먼저 물을 필요가 없어요. 무게는 계산한 숫자로만 말하고, 다른 필라멘트로 뽑은 시험 출력은 맞춤만 보여 준다고 미리 말해요. 원하는 결과는 홈 폴더에 남겨 모든 프로젝트에서 쓸 수 있어요. 재기만 한 남의 모델 파일은 묶음에 복사하지 않아요. Blender 내보내기는 잘못된 삼각형이 생기는 면만 다시 나누기 때문에 업데이트 뒤 기존 프로젝트를 다시 빌드해도 같은 파일이 나오고 점검 결과도 그대로 남아요.

**v0.9.0**은 덜 멈춰요. 새 부품을 만들 때 파일을 받기 전까지 두 번만 물어요. 한 번은 시안 두세 개 중에
고르기예요(찾은 기존 모델은 그 아래에 있어요). 또 한 번은 다 만들고 점검한 부품을 보는 확인이에요. 치수와,
필요할 때는 간단한 시험 출력 제안도 같이 보여 줘요. 치수표, 쓰임 목록, 시험 출력 질문은 따로 멈춰서 묻지
않아요. 예전처럼 단계마다 확인하고 싶으면 "단계별로 보여 주세요"라고 하면 돼요.

**v0.8.2**는 판정에 남아 있던 숙제 세 가지를 정리했어요. 손으로 하는 쓰임(폰을 밀어 넣기, 막대를
꽂았다 빼기)은 따로 표시하고, 시험 출력으로 동작을 확인하지 않았으면 최종 점검이 직접 그렇게
말해요. 확인 없이 받기로 하면 보고서에 시제품으로 남아요. 벽 두께 검사는 경사면이 바닥과 만나는
곳을 더는 얇다고 읽지 않아요. 직접 저장한 Bambu 필라멘트 프리셋은 그 바탕이 된 재료로 찾아요.

**v0.8.1**은 프로젝트 폴더를 옮길 수 있게 해요. 빌드 보고서가 경로를 프로젝트 폴더 기준으로
적어서, 폴더를 옮기거나 다른 사람에게 줘도 최종 점검을 그대로 통과해요. Blender 빌드도
마찬가지예요. 에이전트가 맡아 정하는 점검(브리지, 작은 형상, 바닥 모서리)은 이유와 함께 기록되어,
보고서마다 열린 항목으로 남지 않아요. 지침에는 두 줄을 더했어요. 다른 질문에 "알아서 정해 주세요"라고
한 답은 시안을 고른 것이 아니고, 슬라이서 설정을 모를 때는 전달할 때 구멍과 바닥 모서리에 어떤
뜻인지 말해요.

**v0.8.0**은 하는 일은 그대로 두고 스킬을 작게 만들었어요. 규칙마다 적힌 곳을 한 군데로 정했고,
일부 부품에만 필요한 내용(기구, 특수한 기능, 라이브 Blender, 소스 묶음 내부)은 그 부품일 때만
읽어요. Blender 경로를 따라가는 에이전트가 읽는 분량이 약 3,400줄에서 약 2,400줄로 줄었고,
`SKILL.md`는 300줄이에요. 지침에 두 가지로 적혀 있던 규칙 네 가지는 하나로 정했어요.
- 기본 모양 확인은 언제나 멈춰요.
- 단순한 부품은 완성된 모양으로 보여 줘도 돼요.
- 바닥 모서리 보정은 한 곳에서만 해요.
- 시제품은 사용자의 말을 그대로 남겨요.
`finalize.py`는 모듈로 나눴고, 출력은 0.7.0과 바이트까지 같아요. 대화 시나리오 9개를 다시
돌렸고, 나빠진 것은 없어요.

**v0.7.0**은 검증 근거를 설계에 묶어요. 약속한 것(부품으로 하는 일, 있어야 하는 기능, 모양)을
조건과 성공 기준과 함께 적고, 최종 보고서는 그 약속에 맞는 종류의 근거가 지금 부품으로(STL의
sha256으로) 만들어졌고, 통과했고, 아무도 재지 않은 치수에 기대지 않을 때만 확인됐다고 말해요.
근거는 끼움 검사, 빌드의 숫자를 그대로 가져온 강도 계산, 만든 부품을 잰 값, 미리보기 이미지를
내가 보고 한 확인, 같은 프린터·재료·프리셋으로 뽑은 시험 출력이에요. 보고서는 이 `use` 층을
형상과 따로, 맨 먼저 말해요. 0.7.0 전에 만든 프로젝트는 여기서 `not declared`로 나와요. 같은
생성기를 다시 빌드하면 이제 같은 STL 바이트가 나와서, 바뀐 것 없이 다시 빌드해도 근거가 그대로
유효해요. 업그레이드한 뒤 첫 빌드에서만 모든 해시가 한 번 바뀌어요([CHANGELOG.md](CHANGELOG.md)
참고). 소스 묶음에는 판정에 쓴 입력이 모두 들어가고, 대화 시나리오 9개를 Claude로 돌려
채점했어요.

**v0.6.1**은 검증 오류 수정과 설치·사용 흐름 개선을 함께 담아요.
부품 그룹·역할·가동 부품의 간격을 STL 형상과 별도로 기록해, 조립 조건이 바뀌면 이전 검증을
그대로 쓰지 않아요. 조립 기록이 없는 이전 보고서는 다시 빌드하거나 기록해야 해요. Blender
Python 후보가 실패하면 다음 정상 후보를 찾고, OpenSCAD는 실제 작은 모델 내보내기까지 확인해요.
이미 받은 답은 재사용하고, 기존 모델 사용 선택의 완료 경로와 작업 상태·전달물의 수정 규칙을
구분했어요. 설치 방법과 실제 Blender 실행 파일 검사는 [개발 환경 안내](references/development.md)를
참고하세요.

**v0.6.0**은 Blender를 모든 모양의 첫 번째 엔진으로 올렸어요. 새 도우미(정확한 반지름의 필렛, 단면에서
곡면을 따라가는 라운드, Blender 안에서 쓰는 Python 부품 라이브러리)로 C클립과 카드 슬롯 블록을 다시
만들어 비교했더니 Python 엔진과 결과가 같았거든요. 최종 보고서(`finalize.py`)가 모든 검사, 끼움·강도
보고서, 시험 출력, 받아들인 경고를 모아서 무엇이 검증됐고 무엇이 아닌지 말해요(방향별 모양, 슬라이싱,
실제 출력은 확인 안 됨으로 남겨요). 납품한 파일이 검증한 파일과 같은지도 확인해요. 출력 기록은 같은
조건(노즐, 레이어, 하중, 출력 방향, 프로세스)에서 출력한 결과만 추천하고, 서로 다른 출력의 값을 섞어서
추천하지 않아요.

**v0.5.1**은 외부 검토에서 나온, 통과시키면 안 되는 것을 통과시킬 수 있던 검사 세 가지를 고쳤어요:
움직이는 길 중간에 걸리는 장애물, 필요한 각도보다 덜 돌려 보거나 두 단계 사이의 멈춤 턱을 건너뛴
회전 검사, 서로 맞닿은 print-in-place 부품 둘.

**v0.5.0.** 실제 Windows의 Blender 5.2.2 LTS에서 실행 파일 경로와 공식 Blender Lab MCP 서버로
돌려 봤고, 다섯 가지 시나리오(유기적인 화분, 스냅 클립, 혼합 이름판, Gridfinity 빈, 한글 키링)로
스킬을 처음부터 끝까지 써 봤어요. 거기서 나온 문제를 고쳤어요: 필라멘트 실제 색 그대로 렌더링,
글꼴에 없는 글자는 오류로 알리는 글자 도구, 오래된 STL을 통과시키지 않는 `record`, `strength.py
snap`, 표준 규격·글꼴·두 색 글자 규칙. 기계 부품은 이제 Python이나 OpenSCAD로 만들고 Fusion은 편집
가능한 CAD를 원할 때만 써요. Blender와 비교했더니 정확도는 같았지만 곡면 옆 라운드를 안정적으로
못 만들었어요. 아직 안 돌려 본 것: MCP 서버의 백그라운드 도구, macOS·Linux의 실행 파일.
v0.4.0은 Blender(4.5 LTS 이상)가 있으면 써요: MCP 커넥터로 연결한 내 Blender, `blender` 실행
파일, 또는 `bpy` 모듈. 유기적·장식적인 모양에 진짜 필렛, Manifold 불리언, 어떤 글꼴이든 글자, 그리고
STL 옆에 편집 가능한 `.blend`가 생기고, 미리보기를 필라멘트 색으로 Blender가 렌더링할 수 있어요. 내
Blender에 연결했을 때는 별도의 씬에서 작업하고 출력 폴더에만 써요: 열려 있는 파일을
초기화하거나 저장하거나 덮어쓰는 일은 없고, 전달하는 `.blend`에 내 데이터가 섞여 들어가지도 않아요.
출시 때는 `bpy` 모듈 4.5.14와 5.2.2, 그리고 실행 파일을 흉내 낸 테스트로 확인했고, 실제 실행 파일과
MCP 서버는 v0.5.0에서 돌려 봤어요. Blender가 없으면 v0.3.1과 똑같이 동작해요.

v0.3.1은 v0.3.0으로 해 본 시험 요청(걸쇠 기준으로 경첩을 키우다 상자까지 커진 SD카드 케이스)에서
나온 수정이에요: 기구 부재의 규칙을 용도별로 나눴어요. 손으로 조작하는 걸쇠·레버·클램프는 현장
최소값을 그대로 쓰고, 마디가 번갈아 맞물리는 뚜껑 경첩은 새 `strength.py hinge` 계산(출처 있는 하중,
안전율 2 이상)으로 크기를 정한 뒤 작은 시험편으로 확인해요. 기구가 물건을 몰래 키우지 않도록 멈춰서
선택지를 묻고, 캘리브레이션 기록은 같은 종류의 부재끼리만 기준을 정해요(`--kind`). 경첩 계산은 손
계산과 테스트로 맞췄고, 실제 출력 시험편으로는 아직 확인하지 않았어요.

v0.3.0은 파트를 객체로 묶는 기능과 그에 맞는 검사·3MF 작성기, Fusion Builder 뼈대, 받은 파일의
치수를 재는 도구, 끼움 검사의 회전 검사, 힘을 받는 부재의 강도 계산과 캘리브레이션 기록, 그리고 2026-10-17 현장 시험(Fusion으로 설계해 X2D로 출력한 공구 없는 배기
어댑터, 한 번에 출력한 걸쇠가 부러진 건)에서 나온 진행 방식 수정이 더해졌어요.
v0.1.0과 v0.2.0은 Bambu Lab X2D + Bambu Studio 02.08.02.61, OpenSCAD 2021.01, manifold3d 3.5.4로
처음부터 끝까지 시험했고, 자동 생성 템플릿은 A1 mini, A1, P1S, X1C, H2D, H2C 프로필로도 확인했어요.
v0.3의 여러 파트로 된 Bambu 객체, 서포트 인터페이스 설정, v0.2.1의 필라멘트 6개 템플릿 수정은
2026-10-18에 앱에서 확인했어요. Fusion에서 아직 돌려 보지 않은 것: 정리한 Builder. 아직 돌려
보지 않은 것: Blender MCP 서버의 백그라운드 도구, macOS·Linux의 실행 파일. 아직 전혀 시험하지
않은 것: OrcaSlicer. 예정: 프린터 프로필 가져오기, 브리지·최소 크기 검사. FDM 전용이고 레진은
지원하지 않아요.

## 개발

[개발 환경 안내](references/development.md)에 따라 환경을 준비한 뒤 실행하세요.

```bash
python3 -m unittest discover -s tests
```

`tests/test_examples.py`는 모든 예제를 각 README의 명령 그대로 다시 빌드해요.
의존성 설치를 끝낸 뒤 테스트하고, Blender가 실행 중일 때 bpy를 다시 설치하지 마세요.
스킬 지침 변경은 [`docs/scenarios/`](docs/scenarios/README.md)의 대화 시나리오로도 검토해요. 이
시나리오는 스킬과 함께 배포되지 않아요. Python 단위 테스트만으로 에이전트의 질문과 판단까지
검증되지는 않아요. 시나리오 9개마다 첫 메시지, 정해진 답, 채점 목록이 있고, 시작 상태를 만드는
스크립트와 0.7.0, 0.8.0, 0.8.1, 0.8.2, 0.9.0, 0.9.1에서 돌려 채점한 기록도 함께 있어요.

진입점은 `SKILL.md`예요. 항상 지켜야 하는 규칙, 단계별 짧은 뼈대, 체크리스트가 거기에 있어요.
각 단계의 진행 방법(`references/phase-0-detect.md`부터 `phase-6-deliver.md`까지), 엔진별 규칙, 공차,
Bambu 관련 내용은 `references/`에 있고 그 단계에 들어갈 때 읽어요.

## 기여자

3dprint-scout를 함께 다듬어 주신 분들이에요.

- [@fivetaku](https://github.com/fivetaku): fit 보고서에 측정한 STL을 기록하고 `fit.py --check`로
  확인하는 기능([#9](https://github.com/madrobotnet/3dprint-scout/pull/9)), Blender MCP 작업 흐름 메모([#8](https://github.com/madrobotnet/3dprint-scout/issues/8)).

이슈와 PR은 언제든 환영해요.

## 응원하기

이 스킬이 시간을 아껴 줬다면 커피 한 잔으로 응원해 주세요.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://buymeacoffee.com/madrobotnet)

## 라이선스

MIT, [LICENSE](LICENSE) 참고. Bambu Studio 프로젝트 형식은 공개된 소스 코드를 보고 익혔고 호환에
필요한 파일 형식 상수만 써요. Bambu 프로필 데이터는 실행할 때 읽고(내 설치본 또는 Bambu 공개
프로필) 스킬에 포함하지 않아요.

Bambu Lab, Autodesk 등 여기 나온 어떤 회사와도 관계없어요.
