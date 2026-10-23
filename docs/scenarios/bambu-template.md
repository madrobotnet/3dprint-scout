# bambu-template: a Bambu printer whose project comes from a generated template

## Expected behaviour

Copied word for word from `references/development.md`, "Conversation checks when editing the
skill", at commit 0d76bd5. `setup.py --check-docs` compares it with development.md as it is;
when they differ, development.md wins and this file is out of date.

> **Scenario:** Bambu printer, project from a generated template
>
> **Expected behavior:** Record `model`: the delivered project carries the system preset with both corrections off. Do not ask the user for settings the project already fixes.

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
| Shows existing models and asks which way to go (A–D) | `기존 모델 말고 새로 만들어 주세요.` |
| Shows concept variants and asks which one | `첫 번째 안으로 할게요.` |
| Asks which filament | `PLA요.` |
| Asks again for something the folder or the opening message gave (printer, slicer, the tube's size) | `전에 말씀드린 그대로예요.` |
| Asks about hole, circle or elephant-foot compensation, or other slicer settings | `그런 설정은 잘 몰라요.` |
| Asks for the Bambu Studio version | `버전은 잘 모르겠어요.` |
| Suggests saving an empty project in Bambu Studio as the template | `지금은 컴퓨터 앞이 아니라서 못 해요.` |
| Asks which print profile (process preset) the user prints with | `기본 설정 그대로 써요.` |
| Shows the use list and the parameter table and asks to confirm | `네, 그대로 진행해 주세요.` |
| Shows the base shape (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Offers a fit test or a test print before the final part | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

The compensation decision:
- [ ] **must** `.3dprint/printers.json` records `"compensation": {"holes": "model", ...}`, with
  the reason in the reply or `_assumptions`: the delivered project carries the generated
  template's system preset, which has both hole corrections off.
- [ ] **must** The socket is 22.0 mm plus the fit clearance on the diameter (tolerances.md: +0.40
  sliding, +0.30 snug) plus the model hole compensation (+0.20 to +0.40 on the diameter): 22.5 to
  22.8 mm. A fit against a proxy of the tube uses `fit.py --min-clearance` of the radial
  clearance with the compensation included (0.25 to 0.40).

Asking:
- [ ] **must** Asks nothing the project fixes: not hole, circle or XY hole compensation, not
  elephant-foot compensation, not the printer or the slicer (read from `printers.json`), not for
  a template it needs. One optional suggestion to save an empty project instead
  (`bambu-process.md`, one line, not insisted on) is not a failure.
- [ ] **should** Stops for the reference choice, the concept pick and the base-shape look.

Doing:
- [ ] **must** Delivers a Bambu project written by `bambu3mf.py` from `.3dprint/templates/x1c.3mf`
  into a new delivery folder, its `.manifest.json` beside it, plus an STL per part; tells the
  user to open it with Open Project.
- [ ] **must** Runs finalize with `--deliver` on that folder.
- [ ] **should** `_material` is `pla_basic`; `_print.preset` is `0.20mm Standard @BBL X1C` (the
  generated template names the printer's default process).
- [ ] **should** The tube is a `_verify.dims` entry, `"source": "caliper"`, `"by": "user"`, 22.0.
- [ ] **should** `.3dprint/templates/x1c.3mf` is unchanged (its sha256 as `setup.py` printed).

Claiming (the last message):
- [ ] **must** In Korean throughout; opens with the `use` tier.
- [ ] **must** Does not call slicing or the print checked; may say the project carries the
  print settings (and so the hole corrections) the socket was sized for.

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** The delivered 3MF names `Bambu PLA Basic @BBL X1C` (`pla_basic`) and the process
  `0.20mm Standard @BBL X1C`; `open` has no line that the print file's material is not checked
  or that the project names no process preset.
- [ ] **must** `use` is not `error` or `failed`; `geometry` is `verified`; each promise's state is
  the one the last message gave it.
