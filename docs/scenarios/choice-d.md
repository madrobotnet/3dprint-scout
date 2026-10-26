# choice-d: the user takes an existing model as it is

## Expected behaviour

Copied word for word from the table in [`conversation-checks.md`](conversation-checks.md).
`setup.py --check-docs` compares it with that table as it is; when they differ, the table wins
and this file is out of date.

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
| Shows existing models and asks which way to go (the pick, with or without concepts; A–D step by step) | `표에서 첫 번째 모델이 딱 좋네요. 그 모델을 그대로 출력할게요.` |
| Hands off the chosen model | (the run ends) |
| Anything else (the printer or slicer among it) | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

Before the choice:
- [ ] **must** Shows four existing models, in a table or one line each: name, site, URL, licence
  ("not shown" when the page does not show one, never a guess) and what is worth borrowing;
  offers to use one as it is (and "show 4 more"), with concepts or without; stops.

After the choice:
- [ ] **must** The handoff gives the chosen model's page URL, its creator and its licence (as in
  the table, or "not shown"), and tells the user where and how to download it themselves.
- [ ] **must** It lists the checks that remain: the file's actual dimensions, the fit on the bed
  (not checked: the printer is not known), the fit to the desk edge and the cables, slicing, a
  test print.
- [ ] **must** Asks nothing more: not the printer, the slicer or a dimension (the bed fit stays
  unchecked rather than a Phase 2 questionnaire).
- [ ] **must** Builds nothing after the choice: no generator, no `out/build.json`, no `_verify` in
  `.3dprint/params.json`; runs none of `build.py`, `validate.py`, `fit.py`, `finalize.py` on a
  model. The concepts the pick showed (0.9.0) are built before it, in `out/concepts/` only, and
  are not graded here.
- [ ] **must** Downloads no model file: no `.stl`, `.3mf`, `.step` or `.zip` appears in the folder
  outside `out/concepts/` (the concepts' own builds).
- [ ] **must** Generates no substitute and does not start modeling its own version (saying that a
  custom part is possible later is fine).
- [ ] **must** Claims nothing as checked or verified about the model's mesh, size or fit; a size
  or print advice from the page is said as the page's claim.
- [ ] **must** In Korean throughout.

The user's agreement (the same item in every attended scenario):
- [ ] **must** A promise `excluded`, a WARN `accepted`, or a `not verified` promise delivered as
  a prototype rests on the user's agreement: their reply, taking that option, to a question that
  named that promise or warning, said in plain words what taking it means (it stays unverified,
  or the warning stays, and what that can cost) and offered the choices ("그냥 진행해 주세요" counts
  when going on as it is was the option named). An `accepted` entry's `reason` is that reply
  word for word, and so is the note of a prototype line the user agreed to. The question comes whenever finalize first reports a promise not verified, in
  Phase 4, 5 or 6 (one added late, or made stale by a late change, included), and before the
  delivery message; a question asked earlier about the same named promise counts. Never agreement: the fallback or another reply that hands the decision back
  to the agent, a look ("모양 좋아요"), a reference or concept choice, "계속해 주세요" after a progress
  note, an answer to another question, silence. After a reply that hands the decision back to
  the agent, nothing is `excluded` or `accepted`: a WARN is fixed or named at delivery, a
  promise gets evidence or goes out as a prototype, and `_assumptions` says that the user handed
  the decision back (the prototype line's note may say it). A look promise added after the user
  looked, or a look a rebuild made stale, needs an image of the current build and a new look; an
  old look never becomes `excluded` or `accepted`.

finalize after the run: none. Choice D builds nothing; record "n/a (choice D)".
