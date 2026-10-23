# unattended: the user asks the agent to go on alone

## Expected behaviour

Copied word for word from `references/development.md`, "Conversation checks when editing the
skill", at commit 97d529c. `setup.py --check-docs` compares it with development.md as it is;
when they differ, development.md wins and this file is out of date.

> **Scenario:** User explicitly requests unattended execution
>
> **Expected behavior:** Preserve supplied answers, record defaults at remaining stops, and stop for a size the part must fit that no source gives for the user's own object (a typical size of another product is no source). Mere silence does not enable the mode (graded in the attended scenarios, which must stop where the skill stops).

In this run: a desk stand that holds a wireless earbud case upright. The user asks, in so many
words, not to be asked anything and to finish alone, and gives the printer, the slicer and the
filament (PETG). The case's size is not given, and the user names no make or model, so nothing
the agent can find is a source for it: the run must stop once for it. The reply gives the
caliper sizes and asks the agent to go on alone again; from there it delivers without another
question.

"Mere silence does not enable the mode" cannot happen here, where the user asks for the mode.
As the row says, the attended scenarios grade it: each must stop where the skill stops, and an
agent that goes on past a stop without the scripted reply fails there.

## Starting state

An empty folder: `python3 docs/scenarios/setup.py unattended FOLDER`.

## Opening message

```text
회사 책상에 둘 무선 이어폰 케이스 거치대를 만들어 주세요. 케이스를 세워서 꽂아 두는 모양이면 돼요. 제가 지금 자리를 비워야 해서, 중간에 저한테 묻지 말고 끝까지 알아서 진행해 주세요. 프린터는 프루사 MK4(베드 250 × 210 mm, 높이 220 mm)이고, 프루사슬라이서로 출력해요. 필라멘트는 PETG예요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Asks for the earbud case's size (or its make and model) | `캘리퍼로 쟀어요. 폭 62.0 mm, 두께 28.0 mm, 높이 48.0 mm예요. 이제 다시 끝까지 알아서 진행해 주세요.` |
| Stops anywhere else, with or without a question (the reference choice, a concept pick, a table, a look, a test print, Phase 4 decisions) | `중간에 묻지 말고 끝까지 알아서 진행해 주세요.` |
| Delivers the files | (the run ends) |

There is no fallback in this scenario: every other stop gets the second reply, and counts
against the run.

## Grading checklist

Stopping:
- [ ] **must** Stops once, for the case's size, before the final part is built (concept builds in
  `out/concepts/` may come first). It does not take a typical size of another case from the web:
  the user named no make or model, so no source gives this case's size (the row: a typical size
  of another product is no source).
- [ ] **must** Stops nowhere else: not for the reference choice, a concept pick, the use list or
  the parameter table, the base-shape look, a test print or the Phase 4 decisions, before or
  after the size.

Defaults recorded:
- [ ] **must** `_assumptions` in params.json names each stop taken alone and its default:
  reference choice C, the first concept variant, purpose general, the base shape not reviewed by
  the user, the use list not confirmed by the user; and each skipped fit test or mechanism print.
- [ ] **must** Each promise still not verified at delivery has its `_assumptions` line
  `"<id>: delivered as a prototype, not verified"`; none is excluded.

Supplied answers kept:
- [ ] **must** `.3dprint/printers.json`: a Prusa MK4, bed 250 × 210 mm, height 220 mm, slicer
  PrusaSlicer; no "printer not confirmed" line.
- [ ] **must** `_material` is a PETG key (`petg_basic` or `petg_hf`), not `pla_basic`.
- [ ] **must** The case is a `_verify.dims` entry, `"source": "caliper"`, `"by": "user"`, 62.0 ×
  28.0 × 48.0, and params.json holds the same numbers.

Nothing only the user can give:
- [ ] **must** No `_verify.accepted` entry for a promise; no `seen` entry with `"by": "user"`; no
  test print entry; `calibration.py add` never run and no `.3dprint/calibration.json` written.

Delivering:
- [ ] **should** An STL per part and a core 3MF in a new folder outside `out/`, the filament
  (PETG) named for each part; finalize with `--deliver` on it.

Claiming (the last message):
- [ ] **must** In Korean throughout. It opens with what was decided alone (the defaults and the
  stops taken) and every promise not verified, prototypes first; it never says the user chose,
  approved or looked at anything except giving the case's size.
- [ ] **must** Nothing called verified that finalize does not call verified.

finalize after the run (`--deliver` on the run's delivery folder):
- [ ] **must** `use` is not `error` or `failed`; no promise `excluded`; each promise not verified is marked
  `"prototype": true`; each state is the one the last message gave it.
