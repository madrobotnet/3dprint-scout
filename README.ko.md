# 3dprint-scout

[English](README.md)

3D 프린팅할 물건을 **레퍼런스부터** 설계하는 에이전트 스킬이에요.

만들고 싶은 물건을 말하면, 먼저 이미 있는 3D 모델을 찾아 보여 주고 참고·조합·새로 만들기·그대로
쓰기 중에서 고르게 해요. 그다음 모델링하고 숫자로 검증한 뒤 내 프린터와 슬라이서에 맞는 파일로
돌려줘요. Bambu Studio라면 객체별 출력 설정까지 담은 프로젝트 파일이에요.

## 진행 순서

1. **레퍼런스** — Printables, Thingiverse, MakerWorld 등에서 기존 모델 4개를 라이선스와 함께
   보여 줘요. **A** 하나 참고, **B** 여러 개 조합, **C** 새로 만들기, **D** 그대로 쓰기 중에 골라요.
2. **콘셉트** — B나 C를 골랐다면, 대략적인 모양 두세 가지를 미리보기 이미지와 함께 보여 줘요.
   세부 작업에 들어가기 전에 방향을 먼저 정할 수 있어요.
3. **프린터와 슬라이서** — 쉬운 말로 물어봐요("어떤 프린터를 쓰고, 출력 파일은 어떤 프로그램으로
   여세요? 프로그램은 몰라도 괜찮아요"). 모르면 알맞은 기본값을 써요.
4. **치수** — 모든 치수를 출처와 함께 표로 보여 줘요(캘리퍼 실측, 공식 사양, 서로 일치하는 2차 자료
   두 곳). 지어낸 숫자는 없어요. 모양을 정확히 모르는 물건에 끼울 부품이면, 작은 끼워보기 조각을
   먼저 만들어요(공차를 세 단계로 나누고 구멍 1·2·3개로 표시해요).
5. **모델링** — 모양에 맞춰 엔진을 골라요. 기계 부품은 Fusion(MCP 연결), 없으면 OpenSCAD.
   곡면이 많은 유기적인 모양, 그리고 다른 엔진이 없을 때는 Python([manifold3d](https://github.com/elalish/manifold)).
   Python 엔진에는 검증된 부품 라이브러리(모서리를 둥글리거나 깎은 상자, 나사·인서트 구멍, 물방울
   모양 구멍, 보스, 스냅 후크, 한 번에 출력하는 경첩, 글자, 나사산)와 매끈하게 이어지는 유기적인
   모양을 위한 SDF(부호 거리 함수) 도구가 함께 들어 있어요. 역할이 따로 있거나 색을 달리할 만한
   부분(걸쇠, 레버, 라벨)은 같은 객체 안의 별도 파트로 만들어서, 슬라이서에서 파트를 고르기만 하면
   다른 필라멘트를 줄 수 있어요. 한 번에 출력하는 움직이는 부품은 틈을 그대로 지켜요.
6. **검증** — 부품마다 크기, 베드에 들어가는지, 메시가 닫혀 있는지, 오버행, 벽 두께, 결과가
   최신인지(STL이 지금 소스·매개변수와 일치하는지)를 검사해요. 여러 파트로 된 객체는 전체로도
   검사해요(베드에 들어가는지, 합친 모양의 오버행, 붙는 파트가 실제로 닿는지, 움직이는 파트가
   틈을 지키는지). 서로 끼워지는 부품은 겹침, 유격, 틈, 접촉 면적까지 맞춰 보고, 움직이는 부품은
   돌려 보면서 어디서 걸리는지 찾아요. 힘을 받는 핀·레버·걸쇠는 검증된 참고 부품이 있으면 그 치수와
   나란히 비교하고, 간단한 강도 계산(`strength.py`, Bambu Lab 데이터시트 값과 출처 있는 손힘 표)을
   거치고, 여유가 부족하면 그 부분만 몇 그램짜리로 먼저 뽑아 봐요. 모든 부품은 화면 없이도 렌더링한
   미리보기 이미지(등각·정면·측면·위)를 받아요.
7. **전달** — 부품별 STL과 슬라이서에 맞는 3MF, 바꾼 출력 설정과 그 이유, 그리고 어떤 파트가
   따로 있고 색을 어떻게 바꾸는지 한 줄을 줘요.

레퍼런스를 고를 때, 콘셉트를 고를 때, 치수 표를 확인할 때, 기본 형태를 볼 때는 멈추고 사용자의
답을 기다려요. 끼울 대상의 파일(제조사 키트, 참고 모델)을 주면 그 파일에서 접하는 부분의 치수만
재고, 형상은 가져오지 않아요.

## 예제

<p>
<a href="examples/aa-battery-box/"><img src="examples/aa-battery-box/thumb.png" width="200" alt="AA battery box, OpenSCAD"></a>
<a href="examples/snap-box/"><img src="examples/snap-box/thumb.png" width="200" alt="snap-fit box, part library"></a>
<a href="examples/leaf-handle/"><img src="examples/leaf-handle/thumb.png" width="200" alt="leaf door handle, SDF"></a>
<a href="examples/fit-test/"><img src="examples/fit-test/thumb.png" width="200" alt="fit-test rings"></a>
<a href="examples/latch-box/"><img src="examples/latch-box/thumb.png" width="200" alt="latch box, colour part and print-in-place latch"></a>
</p>

AA 건전지 상자(OpenSCAD), 스냅핏 상자(부품 라이브러리), 나뭇잎 문 손잡이(SDF 도구), 끼워보기
링, 그리고 색을 따로 줄 수 있는 라벨 부품과 한 번에 출력하는 걸쇠가 달린 걸쇠 상자를 스킬의
스크립트로 만들었어요. 예제마다 소스, 매개변수, 검사 결과, 다시 빌드하는 명령이 들어 있어요.
[examples/](examples/)를 보세요.

## 설치

**Claude (웹·데스크톱).** [최신 릴리스](../../releases/latest)에서 `3dprint-scout-v<버전>.zip`을
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

- Python 3.9 이상 (3.9, 3.13에서 시험). 검증기와 3MF 작성기는 표준 라이브러리만 써요.
- 모델링 엔진 하나: MCP로 연결한 **Fusion**, **OpenSCAD**(2021.01 또는 Manifold 백엔드가 있는 최신
  빌드), 또는 `pip install manifold3d`.
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
| `.3dprint/params.json` | 모든 치수, 그리고 묻지 못하고 정한 가정 |
| `.3dprint/printers.json` | 프린터 정보: 베드, 노즐, 슬라이서, 템플릿 (시리얼 번호·접속 코드·IP는 저장 안 함) |
| `.3dprint/calibration.json` | 내 출력 결과 기록(어느 끼워보기 링이 맞았는지, 어떤 걸쇠가 버티고 부러졌는지). 내가 "네"라고 한 뒤에만 써요. 여기 값이 모든 표보다 우선이에요 |
| `.3dprint/templates/` | Bambu Studio 템플릿. 직접 저장한 템플릿에는 계정 ID가 있으니 공개하지 마세요 |
| `out/` | 작업 폴더. 빌드할 때마다 새로 써요: STL, 빌드 기록, 기본 3MF, 미리보기 이미지, 끼워보기 조각 |
| 새 전달 폴더 | 최종 파일. 기존 파일은 절대 덮어쓰지 않아요 |

## 현황

**v0.3.0 (미공개, 최신 릴리스는 v0.2.1).** 파트를 객체로 묶는 기능과 그에 맞는 검사·3MF 작성기,
Fusion Builder 뼈대, 받은 파일의 치수를 재는 도구, 끼움 검사의 회전 검사, 힘을 받는 부재의 강도
계산과 캘리브레이션 기록, 그리고 2026-10-17 현장 시험(Fusion으로 설계해 X2D로 출력한 공구 없는 배기
어댑터, 한 번에 출력한 걸쇠가 부러진 건)에서 나온 진행 방식 수정이 더해졌어요.
v0.1.0과 v0.2.0은 Bambu Lab X2D + Bambu Studio 02.08.02.61, OpenSCAD 2021.01, manifold3d 3.5.4로
처음부터 끝까지 시험했고, 자동 생성 템플릿은 A1 mini, A1, P1S, X1C, H2D, H2C 프로필로도 확인했어요.
앱에서 아직 열어 보지 않은 것: v0.2.1의 필라멘트 6개 템플릿 수정, v0.3의 여러 파트로 된 Bambu
객체와 서포트 인터페이스 설정. Fusion에서 아직 돌려 보지 않은 것: 정리한 Builder. 아직 전혀 시험하지
않은 것: OrcaSlicer. 예정: 프린터 프로필 가져오기, 브리지·최소 크기 검사. FDM 전용이고 레진은
지원하지 않아요.

## 개발

```bash
python3 -m unittest discover -s tests
```

`tests/test_examples.py`는 모든 예제를 각 README의 명령 그대로 다시 빌드해요.

진입점은 `SKILL.md`예요. 엔진별 규칙, 공차, Bambu 관련 내용은 `references/`에 있고 필요할 때만
읽어요.

## 응원하기

이 스킬이 시간을 아껴 줬다면 커피 한 잔으로 응원해 주세요.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://buymeacoffee.com/madrobotnet)

## 라이선스

MIT, [LICENSE](LICENSE) 참고. Bambu Studio 프로젝트 형식은 공개된 소스 코드를 보고 익혔고 호환에
필요한 파일 형식 상수만 써요. Bambu 프로필 데이터는 실행할 때 읽고(내 설치본 또는 Bambu 공개
프로필) 스킬에 포함하지 않아요.

Bambu Lab, Autodesk 등 여기 나온 어떤 회사와도 관계없어요.
