# bambu-template: a Bambu printer whose project comes from a generated template

## Expected behaviour

Copied word for word from the table in [`conversation-checks.md`](conversation-checks.md).
`setup.py --check-docs` compares it with that table as it is; when they differ, the table wins
and this file is out of date.

> **Scenario:** Bambu printer, project from a generated template
>
> **Expected behavior:** Record `compensation.holes: model` in printers.json and add the model hole compensation to fitted holes (the `model` row of tolerances.md): the delivered project carries the system preset with both corrections off. Do not ask the user for settings the project already fixes.

In this run: an end cap for a clothes rail, a round steel tube of 22.0 mm measured with
calipers; the cap must go on and come off by hand. The printer settings are already saved in the
folder: a Bambu Lab X1 Carbon with Bambu Studio and a generated template, and no `compensation`
entry yet. The delivered Bambu project carries the template's system preset, whose hole
corrections are off, so the socket gets the model hole compensation and `compensation.holes` is
`model`. Nobody needs to ask the user about it.

## Starting state

`python3 docs/scenarios/setup.py bambu-template FOLDER` writes:

- `.3dprint/printers.json` (from `fixtures/bambu-template/printers.json`): printer `x1c`, slicer
  `bambu-studio`, `template_3mf` `.3dprint/templates/x1c.3mf`, `template_kind` `generated`, the
  bed 256 × 256 mm, height 250 mm; no `compensation`.
- `.3dprint/templates/x1c.3mf`: written by `scripts/bambu_template.py --printer "Bambu Lab X1
  Carbon 0.4 nozzle" --app-version 02.08.02.61` from a synthetic profile folder that `setup.py`
  makes in a temporary folder and deletes: the real preset names (`0.20mm Standard @BBL X1C`,
  `Bambu PLA Basic @BBL X1C`) and the X1 Carbon's bed, no setting values. It stands in for the
  user's installed Bambu Studio, which a sandboxed run cannot read; generating the template from
  the user's own profiles is not part of this run.

Nothing else: no `params.json`, no generator. finalize has nothing to read yet.

## Opening message

```text
옷걸이 봉 끝에 끼울 마개를 하나 만들어 주세요. 봉은 둥근 쇠파이프이고, 바깥지름을 캘리퍼로 재 보니 22.0 mm예요. 마개는 손으로 끼웠다 뺐다 할 수 있으면 좋겠어요. 프린터 설정은 이 폴더에 저장해 둔 그대로예요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Shows existing models and asks which way to go (A–D), without concepts (step by step) | `기존 모델 말고 새로 만들어 주세요.` |
| Shows concept variants and asks which one (the pick, the models under them) | `첫 번째 안으로 할게요.` |
| Asks which filament | `PLA요.` |
| Asks again for something the folder or the opening message gave (printer, slicer, the tube's size) | `전에 말씀드린 그대로예요.` |
| Asks about hole, circle or elephant-foot compensation, or other slicer settings | `그런 설정은 잘 몰라요.` |
| Asks for the Bambu Studio version | `버전은 잘 모르겠어요.` |
| Suggests saving an empty project in Bambu Studio as the template | `지금은 컴퓨터 앞이 아니라서 못 해요.` |
| Asks which print profile (process preset) the user prints with | `기본 설정 그대로 써요.` |
| Shows the use list and the parameter table and asks to confirm (on its own, or in the look) | `네, 그대로 진행해 주세요.` |
| Shows the base shape or the part (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Offers a fit test or a test print before the final part | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

The compensation decision (each item is in the row):
- [ ] **must** `.3dprint/printers.json` records `compensation.holes` `model`, with the reason in
  the reply or `_assumptions`: the delivered project carries the generated template's system
  preset, which has both hole corrections off.
- [ ] **must** The fitted feature that takes the tube gets the model hole compensation (the
  `model` row of tolerances.md, +0.10 to +0.20 radial) on top of its fit. For a clearance socket
  that is 22.0 mm plus the fit clearance on the diameter (+0.40 sliding, +0.30 snug) plus the
  compensation (+0.20 to +0.40 on the diameter), 22.5 to 22.8 mm (22.4 mm or less means none was
  added), and a fit against a proxy of the tube uses `fit.py --min-clearance` of the radial
  clearance with the compensation included (0.25 to 0.40). For another fit, such as a grip that
  holds the tube by interference, the fitted circle is 22.0 mm minus the modelled interference
  plus the compensation (both on the diameter); a circle without the compensation means none was
  added.

Asking:
- [ ] **must** Asks nothing the project fixes: not hole, circle or XY hole compensation, not
  elephant-foot compensation, not the printer or the slicer (read from `printers.json`), not for
  a template it needs. One optional suggestion to save an empty project instead
  (`bambu-process.md`, one line, not insisted on) is not a failure, nor is one optional question
  for the Bambu Studio version.
- [ ] **must** Does not stop for the parameter table or the use list on their own (0.9.0): they
  are in the look. A test print offer is in the look too, or in a stop for something new (a check
  that failed, a confirmed value that changed).
- [ ] **should** Stops twice before delivering: the pick (the concepts with the references under
  them, no question with the letters A to D) and the look.

Doing:
- [ ] **must** Delivers a Bambu project written by `bambu3mf.py` from `.3dprint/templates/x1c.3mf`
  into a new delivery folder, its `.manifest.json` beside it, plus an STL per part; tells the
  user to open it with Open Project.
- [ ] **must** Runs finalize with `--deliver` on that folder.
- [ ] **should** `_material` is `pla_basic`; `_print.preset` is `0.20mm Standard @BBL X1C` (the
  generated template names the printer's default process).
- [ ] **should** The tube is a `_verify.dims` entry, `"source": "caliper"`, `"by": "user"`, 22.0.
- [ ] **should** `.3dprint/templates/x1c.3mf` is unchanged (its sha256 as `setup.py` printed).

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
- [ ] **must** Does not call slicing or the print checked; may say the project carries the
  print settings (and so the hole corrections) the socket was sized for.

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** The delivered 3MF names `Bambu PLA Basic @BBL X1C` (`pla_basic`) and the process
  `0.20mm Standard @BBL X1C`; `open` has no line that the print file's material is not checked
  or that the project names no process preset.
- [ ] **must** `use` is not `error` or `failed`; `geometry` is `verified`; each promise's state is
  the one the last message gave it.
