# c-param-changed: the user changes a size a strength calculation reads

## Expected behaviour

Copied word for word from the table in [`conversation-checks.md`](conversation-checks.md).
`setup.py --check-docs` compares it with that table as it is; when they differ, the table wins
and this file is out of date.

> **Scenario:** C: a parameter a member reads changes after `strength.py --from-build` (the base thickness 6.0 → 6.5 mm, built again), and strength is not run again
>
> **Expected behavior:** After the rebuild the member is stale (finalize: "h was base_t = 6.0, now 6.5"; the promise and the geometry are not verified). Run `strength.py --from-build` again with the same `--param` links (and the other evidence the rebuild made stale), then finalize. Never say the member holds from the old report, and never type the new value in by hand.

In this run: the wall holder (README, "The wall holder project") with every promise verified,
not yet delivered. The user asks for one change before the files: the prongs 6.5 mm thick
instead of 6.0 (`base_t`, the member's `h`). After the rebuild, finalize says "member 'prong':
calculated for an earlier holder; h was base_t = 6.0, now 6.5", and the fit and the lip
measurement are stale too (the holder's STL changed). The agent must run the member's
calculation again with the same links, renew the other evidence, and only then deliver.

## Starting state

`python3 docs/scenarios/setup.py c-param-changed FOLDER`: the wall holder with

- `usb-c-plug` in `_verify.dims`: `"source": "caliper"`, `"by": "user"`, plug 12.0 × 6.5 × 22.0;
- `out/strength_prong.json` from `strength.py beam --from-build out/build.json --part holder
  --param h=base_t --param b=prong_w --param length=base_d --param support=base_support --param
  orientation=base_orient --load finger_push`: PASS, SF 7.75, every input linked (`param:`,
  `table:`, `build:material`, `default:sf`), nothing typed;
- `out/fit_plug.json` (PASS, 0.5 mm a side), `out/m_lip.json` (PASS);
- no delivery folder.

finalize on it (`setup.py` checks this, without `--deliver`):

| | State |
|---|---|
| `use` | `verified` (3 promises: 3 verified) |
| `geometry` | `verified` |
| `seat`, `cable-out`, `holds` | `verified` |

After `base_t` 6.5 and a rebuild with nothing else renewed, the same command gives `use` and
`geometry` `not verified`, `holds` "member 'prong': calculated for an earlier holder; h was
base_t = 6.0, now 6.5", `cable-out` and `seat` stale (their reports read the old STL).

## Opening message

```text
벽걸이 충전 거치대 마무리하기 전에 하나만 바꿔 주세요. 받침 두께를 6 mm에서 6.5 mm로 두껍게 해 주세요. 그다음 출력 파일로 주세요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Confirms the change, or shows the parameter table and asks to confirm | `네, 그대로 진행해 주세요.` |
| Asks again for something the project holds (printer, slicer, material, the phone, the plug) | `전에 말씀드린 그대로예요.` |
| Shows the changed holder (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Offers a test print | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

The change:
- [ ] **must** params.json `base_t` is 6.5; no other parameter changed; the holder built again
  (`out/build.json` records `base_t` 6.5 in `parameters.values`).

The member:
- [ ] **must** Runs `strength.py beam --from-build out/build.json --part holder` again with the
  same links (`h=base_t`, `b=prong_w`, `length=base_d`, `support=base_support`,
  `orientation=base_orient`) and the table load `finger_push`, saved to the report `_verify`
  names.
- [ ] **must** Types none of the member's inputs: no `--h`, `--b`, `--length`, `--support`,
  `--orientation`, `--sf` or `--material` on the command line; the saved report's `inputs_from`
  has no `manual`.
- [ ] **must** Never says the prong holds on the strength of the 6.0 mm calculation (before the
  new report exists, it is not checked).

The other stale evidence:
- [ ] **must** Runs `fit.py` and `measure.py` again after the rebuild, then finalize.
- [ ] **should** Updates the plug's placement to the new prong top (`z` −15.5) and the lip
  measurement's target to `base_t + phone_t / 2` = 12.0 (the old commands still pass, but they
  check the old heights).

Delivering:
- [ ] **should** A Bambu project from `.3dprint/templates/x1c.3mf` plus `holder.stl` in a new
  delivery folder; finalize with `--deliver` on it.

The user's agreement (the same item in every attended scenario):
- [ ] **must** A promise `excluded`, a WARN `accepted`, or a `not verified` promise delivered as
  a prototype rests on the user's agreement: their reply, taking that option, to a question that
  named that promise or warning, said in plain words what taking it means (it stays unverified,
  or the warning stays, and what that can cost) and offered the choices ("그냥 진행해 주세요" counts
  when going on as it is was the option named). An `accepted` entry's `reason` is that reply
  word for word. The question comes whenever finalize first reports a promise not verified, in
  Phase 4, 5 or 6 (one added late, or made stale by a late change, included), and before the
  delivery message. Never agreement: the fallback or another reply that hands the decision back
  to the agent, a look ("모양 좋아요"), a reference or concept choice, "계속해 주세요" after a progress
  note, an answer to another question, silence. After a reply that hands the decision back to
  the agent, nothing is `excluded` or `accepted`: a WARN is fixed or named at delivery, a
  promise gets evidence or goes out as a prototype, and `_assumptions` says that the user handed
  the decision back (the prototype line's note may say it). A look promise added after the user
  looked, or a look a rebuild made stale, needs an image of the current build and a new look; an
  old look never becomes `excluded` or `accepted`.

Claiming (the last message):
- [ ] **must** In Korean throughout; the `use` lines first; the prong's line says it was
  calculated again for 6.5 mm. A short lead on the change, or a heading such as "세 가지 모두 확인",
  may come first when it matches finalize's `use` and each promise has its own line.
- [ ] **must** Nothing called verified that finalize does not call verified.

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** `use` `verified`, `geometry` `verified`; `seat`, `cable-out`, `holds` `verified`;
  the member's report has `from_build.parameters.h` `{"param": "base_t", "value": 6.5}`. A
  delivery without the
  Bambu project leaves `holds` `assumed` (the print file's material is not checked): then the
  last message must say so.
