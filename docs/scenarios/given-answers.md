# given-answers: everything the skill would ask is in the request

## Expected behaviour

Copied word for word from `references/development.md`, "Conversation checks when editing the
skill", at commit 0d76bd5. `setup.py --check-docs` compares it with development.md as it is;
when they differ, development.md wins and this file is out of date.

> **Scenario:** Request already gives printer, slicer, dimensions and choice C
>
> **Expected behavior:** Reuse those answers; do not ask again because a settings file is absent. New concept/base-shape reviews still apply.

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
| Shows concept variants and asks which one | `첫 번째 안으로 할게요.` |
| Shows the use list and the parameter table and asks to confirm | `네, 그대로 진행해 주세요.` |
| Shows the base shape (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Offers a fit test or a test print before the final part | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Asks which print profile (process preset) the user prints with | `프로필 이름은 잘 모르겠어요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

Asking:
- [ ] **must** Asks none of: the printer, the slicer, the bed size, a remote's size, the
  material, or which way to go (A–D). Each was in the opening message; a question about one of
  them, also one justified by a missing settings file, makes the run differ.
- [ ] **must** Stops for the concept pick: 2–3 variants, each with an image and one line on what
  differs (choice C is followed by a concepts stop).
- [ ] **must** Stops for the base-shape look: the preview with the size and the verdicts, before
  holes, pockets or other features are built on it.
- [ ] **should** May show the four-model table; does not stop to ask for the choice.
- [ ] **should** At Phase 2 it stops only for new decisions (the use list, derived sizes, the
  pocket clearance), not to have the given sizes approved again.

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

Claiming (the last message):
- [ ] **must** In Korean throughout; opens with the `use` tier, one line per promise.
- [ ] **must** Calls verified only what finalize calls verified; a promise the user took as a
  prototype is said first, as a prototype.

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** `use` is not `error` or `failed`; `geometry` is `verified`; each promise's state
  is the one the last message gave it.
