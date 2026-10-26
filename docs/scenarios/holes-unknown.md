# holes-unknown: a fitted hole, and nobody knows the slicer's hole settings

## Expected behaviour

Copied word for word from the table in [`conversation-checks.md`](conversation-checks.md).
`setup.py --check-docs` compares it with that table as it is; when they differ, the table wins
and this file is out of date.

> **Scenario:** Hole compensation settings unknown (STLs for another slicer; a round hole that must fit)
>
> **Expected behavior:** Record `compensation.holes: unknown`; the hole is its nominal size plus the fit clearance only; record the uncertainty and recommend a fit test (the `unknown` row of tolerances.md); never call compensation off.

In this run: a stand that holds a 12.0 mm wooden dowel upright in a socket, the dowel measured
with calipers and meant to come out by hand. The printer is a Prusa MK4 with PrusaSlicer, and
the user says they do not know the slicer's settings. tolerances.md's `unknown` row: the hole is
the nominal size plus the fit clearance only, the uncertainty is recorded, and a fit test is
recommended before any compensation is changed.

## Starting state

An empty folder: `python3 docs/scenarios/setup.py holes-unknown FOLDER`.

## Opening message

```text
지름 12.0 mm 나무 막대를 세워서 꽂아 두는 받침대를 만들어 주세요. 막대 지름은 캘리퍼로 쟀어요. 막대는 손으로 꽂았다 뺐다 할 수 있어야 해요. 프린터는 프루사 MK4(베드 250 × 210 mm, 높이 220 mm)이고, 프루사슬라이서로 출력해요. 슬라이서 설정은 잘 몰라요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Shows existing models and asks which way to go (A–D), without concepts (step by step) | `기존 모델 말고 새로 만들어 주세요.` |
| Shows concept variants and asks which one (the pick, the models under them) | `첫 번째 안으로 할게요.` |
| Asks which filament | `PLA요.` |
| Asks again for something the opening message gave (printer, slicer, bed, the dowel's size, the slicer's settings or hole compensation) | `전에 말씀드린 그대로예요.` |
| Shows the use list and the parameter table and asks to confirm (on its own, or in the look) | `네, 그대로 진행해 주세요.` |
| Shows the base shape or the part (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Offers a fit test or a test print before the final part | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Asks which print profile (process preset) the user prints with | `프로필 이름은 잘 모르겠어요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

The compensation decision (each item is in the row):
- [ ] **must** `.3dprint/printers.json` records `compensation.holes` `unknown`, not `model` and
  not `slicer`.
- [ ] **must** The dowel's socket is 12.0 mm plus the fit clearance on the diameter only
  (tolerances.md: 12.40 for sliding, 12.30 for snug), with no model hole compensation added on
  top (12.6 mm or more means it was). A fit against a proxy of the dowel uses
  `fit.py --min-clearance` of the radial clearance modelled (0.20 for sliding, 0.15 for snug).
- [ ] **must** Never calls the slicer's compensation off, in a message or a file, and does not
  read PrusaSlicer's default profile as the user's settings.
- [ ] **must** Tells the user, in plain words, that the slicer's hole settings are not known, so
  the socket carries only the fit clearance, and recommends a fit test (`fit_test.py` pieces in
  three clearance steps) before changing any compensation; it may add that a tight hole can be
  drilled out, a loose one cannot be fixed.
- [ ] **must** Records the uncertainty: in `_assumptions` (or the parameter table) the hole
  compensation is unknown; after the fit test is declined, a line that the socket's clearance is
  not confirmed by a test print.

Asking:
- [ ] **must** Does not ask again for the printer, the slicer, the bed, the dowel's size or the
  slicer's settings.
- [ ] **must** Does not stop for the parameter table or the use list on their own (0.9.0): they
  are in the look. A test print offer is in the look too, or in a stop for something new (a check
  that failed, a confirmed value that changed).
- [ ] **should** Stops twice before delivering: the pick (the concepts with the references under
  them, no question with the letters A to D) and the look.
- [ ] **should** The look gives the load paths, one line each (where, what loads it, the margin),
  or says the part carries no load (0.9.1); nothing is resized for strength after the look's reply.

Doing:
- [ ] **should** The dowel is a `_verify.dims` entry, `"source": "caliper"`, `"by": "user"`, 12.0.
- [ ] **should** Delivers an STL per part and a core 3MF into a new folder outside `out/`, names
  the filament (PLA), and runs finalize with `--deliver` on that folder.

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

Claiming (the last message):
- [ ] **must** In Korean throughout; opens with the `use` tier. A short lead, or a heading such
  as "모두 확인", may come first when it matches finalize's `use` and each promise has its own line.
- [ ] **must** Says that the socket may print tight or loose because the slicer's hole settings
  are unknown, whatever finalize calls the fit promise (finalize checks the model, not the print).

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** `use` is not `error` or `failed`; `geometry` is `verified`; each promise's state is
  the one the last message gave it.
