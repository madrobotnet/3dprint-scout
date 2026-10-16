# 3dprint-scout

[English](README.md)

3D 프린팅할 물건을 **레퍼런스부터** 설계하는 에이전트 스킬이에요.

만들고 싶은 물건을 말하면, 먼저 이미 있는 3D 모델을 찾아 보여 주고 참고·조합·새로 만들기·그대로
쓰기 중에서 고르게 해요. 그다음 모델링하고 숫자로 검증한 뒤 내 프린터와 슬라이서에 맞는 파일로
돌려줘요. Bambu Studio라면 객체별 출력 설정까지 담은 프로젝트 파일이에요.

## 진행 순서

1. **레퍼런스** — Printables, Thingiverse, MakerWorld 등에서 기존 모델 4개를 라이선스와 함께
   보여 줘요. **A** 하나 참고, **B** 여러 개 조합, **C** 새로 만들기, **D** 그대로 쓰기 중에 골라요.
2. **프린터와 슬라이서** — 쉬운 말로 물어봐요("어떤 프린터를 쓰고, 출력 파일은 어떤 프로그램으로
   여세요? 프로그램은 몰라도 괜찮아요"). 모르면 알맞은 기본값을 써요.
3. **치수** — 모든 치수를 출처와 함께 표로 보여 줘요(캘리퍼 실측, 공식 사양, 서로 일치하는 2차 자료
   두 곳). 지어낸 숫자는 없어요. 모양을 정확히 모르는 물건에 끼울 부품이면, 작은 끼워보기 조각을
   먼저 제안해요.
4. **모델링** — 모양에 맞춰 엔진을 골라요. 기계 부품은 Fusion(MCP 연결), 없으면 OpenSCAD.
   곡면이 많은 유기적인 모양, 그리고 다른 엔진이 없을 때는 Python([manifold3d](https://github.com/elalish/manifold)).
5. **검증** — 부품마다 크기, 베드에 들어가는지, 메시가 닫혀 있는지, 오버행, 벽 두께, 결과가
   최신인지(STL이 지금 소스·매개변수와 일치하는지)를 검사해요.
6. **전달** — 부품별 STL과 슬라이서에 맞는 3MF, 그리고 바꾼 출력 설정과 그 이유를 줘요.

레퍼런스를 고를 때와 치수 표를 확인할 때는 멈추고 사용자의 답을 기다려요.

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

- Python 3.9 이상 (3.9, 3.13에서 시험). 스크립트는 따로 적은 곳 말고는 표준 라이브러리만 써요.
- 모델링 엔진 하나: MCP로 연결한 **Fusion**, **OpenSCAD**(2021.01 또는 Manifold 백엔드가 있는 최신
  빌드), 또는 `pip install manifold3d`.
- 선택: 벽 두께 검사용 `numpy`, `rtree` (없으면 이 검사는 건너뛰고 "확인 못 함"으로 보고해요).

## Bambu Studio

Bambu Lab 프린터에서는 Bambu Studio 프로젝트 파일을 만들어요(**파일 > 프로젝트 열기**로 여세요).
이때 템플릿 프로젝트가 필요한데, 두 가지 방법이 있어요.

- **자동 생성 (기본).** `bambu_template.py`가 시스템 프리셋의 **이름**만 적은 빈 프로젝트를
  만들어요. 예를 들면 `0.20mm Standard @BBL X2D`와 Bambu PLA Basic이에요. Bambu Studio가 이 파일을
  열 때 내 컴퓨터에 설치된 프리셋에서 모든 값을 채워요. 설정값을 복사하지 않고 개인정보도 없어요.
- **직접 저장.** 내가 만든 프로세스 프리셋이나 AMS 필라멘트 구성을 그대로 쓰고 싶으면, Bambu
  Studio에서 빈 프로젝트를 저장해서 스킬에 주세요. 이 파일에는 내 프리셋과 Bambu 계정 ID가 들어
  있어요. 스킬이 만드는 파일에서는 ID를 지우지만 템플릿 파일 자체는 공개하지 마세요.

객체별 설정(서포트, 브림, 벽, 채움, 레이어 높이 등)은 허용목록에 있는 키만, 범위 검사를 통과한
값만 써요. 프로그램을 실행하거나 G-code를 바꿀 수 있는 키는 절대 쓰지 않아요.

## 프로젝트에 만드는 것

| 경로 | 내용 |
|---|---|
| `.3dprint/params.json` | 모든 치수, 그리고 묻지 못하고 정한 가정 |
| `.3dprint/printers.json` | 프린터 정보: 베드, 노즐, 슬라이서, 템플릿 (시리얼 번호·접속 코드·IP는 저장 안 함) |
| `.3dprint/templates/` | Bambu Studio 템플릿. 직접 저장한 템플릿에는 계정 ID가 있으니 공개하지 마세요 |
| `out/` | 작업 폴더. 빌드할 때마다 새로 써요: STL, 빌드 기록, 기본 3MF |
| 새 전달 폴더 | 최종 파일. 기존 파일은 절대 덮어쓰지 않아요 |

## 현황

**v0.1.0.** Bambu Lab X2D + Bambu Studio 02.08.02.61, OpenSCAD 2021.01, manifold3d 3.5.4로 처음부터
끝까지 시험했어요. 자동 생성 템플릿은 A1 mini, A1, P1S, X1C, H2D, H2C 프로필로도 확인했어요. 앱에서
아직 시험하지 않은 것: OrcaSlicer. 예정: 미리보기 스크립트, 프린터 프로필 가져오기, 브리지·최소
크기 검사. FDM 전용이고 레진은 지원하지 않아요.

## 개발

```bash
python3 -m unittest discover -s tests
```

진입점은 `SKILL.md`예요. 엔진별 규칙, 공차, Bambu 관련 내용은 `references/`에 있고 필요할 때만
읽어요.

## 라이선스

MIT, [LICENSE](LICENSE) 참고. Bambu Studio 프로젝트 형식은 공개된 소스 코드를 보고 익혔고 호환에
필요한 파일 형식 상수만 써요. Bambu 프로필 데이터는 실행할 때 읽고(내 설치본 또는 Bambu 공개
프로필) 스킬에 포함하지 않아요.

Bambu Lab, Autodesk 등 여기 나온 어떤 회사와도 관계없어요.
