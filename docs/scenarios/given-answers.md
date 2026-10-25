# given-answers: everything the skill would ask is in the request

## Expected behaviour

Copied word for word from the table in [`conversation-checks.md`](conversation-checks.md).
`setup.py --check-docs` compares it with that table as it is; when they differ, the table wins
and this file is out of date.

> **Scenario:** Request already gives printer, slicer, dimensions and choice C
>
> **Expected behavior:** Reuse those answers; do not ask again because a settings file is absent. The pick (the concepts) and the look (the part as built) still apply; the parameter table is not a stop of its own.

In this run: a desk caddy for two TV remotes. The opening message gives the printer and its
bed, the slicer, the material, both remotes' sizes measured with calipers, and asks for a new
design (choice C, in plain words). The folder is empty, so there is no `.3dprint/printers.json`
to read: the agent must write it from the message instead of asking.

## Starting state

An empty folder: `python3 docs/scenarios/setup.py given-answers FOLDER`.

## Opening message

```text
책상 위에 둘 리모컨 꽂이를 처음부터 새로 디자인해 주세요. 리모컨 두 개를 세워서 꽂아 두려고요. 둘 다 캘리퍼로 쟀는데, 큰 것은 폭 48.0 mm, 두께 22.0 mm, 길이 180 mm이고, 작은 것은 폭 42.0 mm, 두께 18.0 mm, 길이 150 mm예요. 꽂았을 때 리모컨 아래쪽 3분의 1 정도가 잠기면 좋겠어요. 프린터는 프루사 MK4(베드 250 × 210 mm, 높이 220 mm)이고, 프루사슬라이서로 출력해요. 필라멘트는 PLA예요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Asks again for something the opening message gave (printer, slicer, bed, a remote's size, the material, new design or an existing model) | `전에 말씀드린 그대로예요.` |
| Shows concept variants and asks which one (the pick) | `첫 번째 안으로 할게요.` |
| Shows the use list and the parameter table and asks to confirm (on its own, or in the look) | `네, 그대로 진행해 주세요.` |
| Shows the base shape or the part (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Offers a fit test or a test print before the final part | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Asks which print profile (process preset) the user prints with | `프로필 이름은 잘 모르겠어요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

Asking:
- [ ] **must** Asks for none of these values again: the printer, the slicer, the bed size, a
  remote's size, the material, or which way to go (A–D). Each was in the opening message; asking
  for one of them again, also when a missing settings file is the reason, makes the run differ.
  Asking where a given size was taken is the should item below, not this one.
- [ ] **must** Stops for the pick: 2–3 concept variants, each with an image and one line on what
  differs, the references under them; no question with the letters A to D.
- [ ] **must** Stops for the look: the caddy as built (one body with no mechanism, so its pockets
  included), its promises, the sizes the user judges and the checks, before delivering.
- [ ] **must** Does not stop for the parameter table or the use list on their own (0.9.0): they are
  in the look. A test print offer is in the look too, or in a stop for something new (a check
  that failed, a confirmed value that changed).
- [ ] **should** May show the four-model table; does not stop to ask for the choice.
- [ ] **should** Stops twice before delivering (the pick and the look), not to have the given
  sizes approved again or to ask where they were taken (at the widest point?).

Doing:
- [ ] **must** Writes `.3dprint/printers.json` from the message without asking: a Prusa MK4,
  bed 250 × 210 mm, height 220 mm, slicer PrusaSlicer.
- [ ] **must** `_verify.dims` holds both remotes with `"source": "caliper"`, `"by": "user"` and
  the message's values (48.0 × 22.0 × 180, 42.0 × 18.0 × 150), and params.json the same numbers.
- [ ] **must** `_material` is `pla_basic` (the user said PLA).
- [ ] **should** `compensation.holes`, if recorded, is `unknown` (another slicer, a preset nobody
  has seen: tolerances.md).
- [ ] **should** Delivers an STL per part and a core 3MF into a new folder outside `out/` (the
  slicer is not Bambu Studio), names the filament for each part, and runs finalize with
  `--deliver` on that folder.

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
- [ ] **must** In Korean throughout; opens with the `use` tier, one line per promise. A short
  lead, or a heading such as "모두 확인", may come first when it matches finalize's `use` and each
  promise has its own line.
- [ ] **must** Calls verified only what finalize calls verified; a promise the user took as a
  prototype is said first, as a prototype.

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** `use` is not `error` or `failed`; `geometry` is `verified`, or `not verified` only
  by a WARN the user handed back that stays open, is recorded as handed back and is named at
  delivery; each promise's state is the one the last message gave it.
