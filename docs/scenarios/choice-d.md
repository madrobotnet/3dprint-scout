# choice-d: the user takes an existing model as it is

## Expected behaviour

Copied word for word from `references/development.md`, "Conversation checks when editing the
skill", at commit 97d529c. `setup.py --check-docs` compares it with development.md as it is;
when they differ, development.md wins and this file is out of date.

> **Scenario:** User chooses D, an existing model
>
> **Expected behavior:** Deliver the source link, licence/download guidance and remaining checks; do not generate a substitute or claim mesh verification.

In this run: a clip at the edge of a desk that holds three charging cables, an object with many
published models. The user names no printer. After the four-model table the user takes the
first model as it is. Which model that is depends on the agent's search; the grading does not.

## Starting state

An empty folder: `python3 docs/scenarios/setup.py choice-d FOLDER`. Web search must be on
(README, "Before a run"): without it the agent asks for links and the scenario cannot run.

## Opening message

```text
책상 모서리에 붙여서 충전 케이블 세 개를 정리해 두는 클립이 필요해요. 3D 프린터로 출력하려고요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Shows existing models and asks which way to go (A–D) | `표에서 첫 번째 모델이 딱 좋네요. 그 모델을 그대로 출력할게요.` |
| Hands off the chosen model | (the run ends) |
| Anything else (the printer or slicer among it) | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

Before the choice:
- [ ] **must** Shows four existing models in a table: name, site, URL, licence ("not shown" when
  the page does not show one, never a guess) and what is worth borrowing; offers A, B, C and D
  (and "show 4 more"); stops.

After the choice:
- [ ] **must** The handoff gives the chosen model's page URL, its creator and its licence (as in
  the table, or "not shown"), and tells the user where and how to download it themselves.
- [ ] **must** It lists the checks that remain: the file's actual dimensions, the fit on the bed
  (not checked: the printer is not known), the fit to the desk edge and the cables, slicing, a
  test print.
- [ ] **must** Asks nothing more: not the printer, the slicer or a dimension (the bed fit stays
  unchecked rather than a Phase 2 questionnaire).
- [ ] **must** Builds nothing: no generator, no `out/build.json`, no `_verify` in a params.json;
  runs none of `build.py`, `validate.py`, `fit.py`, `finalize.py` on a model.
- [ ] **must** Downloads no model file: no `.stl`, `.3mf`, `.step` or `.zip` appears in the folder.
- [ ] **must** Generates no substitute and does not start modeling its own version (saying that a
  custom part is possible later is fine).
- [ ] **must** Claims nothing as checked or verified about the model's mesh, size or fit; a size
  or print advice from the page is said as the page's claim.
- [ ] **must** In Korean throughout.

finalize after the run: none. Choice D builds nothing; record "n/a (choice D)".
