# change-request: a change to a project already delivered

## Expected behaviour

Copied word for word from `references/development.md`, "Conversation checks when editing the
skill", at commit 0d76bd5. `setup.py --check-docs` compares it with development.md as it is;
when they differ, development.md wins and this file is out of date.

> **Scenario:** User requests a change to the working project
>
> **Expected behavior:** Update relevant generator/state fields, preserve unrelated content, and write new delivery versions without overwriting originals.

In this run: the wall holder (README, "The wall holder project"), every promise verified and
delivered on 2026-10-20 (a Bambu project, the STL and the source bundle in
`deliver/2026-10-20/`). The user asks for a taller back plate, 90 mm instead of 70, to give the
tape more room. The agent changes the relevant fields only, builds again, renews the evidence
the rebuild made stale, and delivers into a new folder, leaving the 2026-10-20 delivery and
every unrelated file as they were.

## Starting state

`python3 docs/scenarios/setup.py change-request FOLDER`: the wall holder with

- `usb-c-plug` in `_verify.dims`: `"source": "caliper"`, `"by": "user"`, plug 12.0 × 6.5 × 22.0;
- `back_h` 70.0 in params.json, and two `_assumptions` lines (the tape is not checked; the
  distance to the socket under the holder is not measured);
- the evidence (fit, lip measurement, member) all PASS;
- `deliver/2026-10-20/`: `holder_bambu.3mf` and its `.manifest.json` (`bambu3mf.py`, from the
  generated template, Bambu PLA Basic, `0.20mm Standard @BBL X1C`), `holder.stl`, and
  `source/` (`finalize.py --deliver deliver/2026-10-20 --bundle deliver/2026-10-20/source`, with
  `verification.json` and `REPRODUCE.md`); the job file is `out/bambu_job.json`.

finalize on it with `--deliver deliver/2026-10-20` (`setup.py` checks this):

| | State |
|---|---|
| `use` | `verified` (3 promises: 3 verified) |
| `geometry` | `verified` (the delivered files are the verified ones) |
| `seat`, `cable-out`, `holds` | `verified` |

Keep `setup.py`'s output: its `files` list holds the sha256 of every file above, which the
checklist compares with the folder after the run.

## Opening message

```text
지난번에 받은 벽걸이 충전 거치대 말인데요, 뒤판을 지금보다 20 mm 높여서 90 mm로 해 주세요. 양면테이프 붙일 자리를 넓히고 싶어요. 나머지는 그대로 두고요.
```

## Scripted replies

| When the agent | Reply, word for word |
|---|---|
| Confirms the change, or shows the parameter table and asks to confirm | `네, 그대로 진행해 주세요.` |
| Shows the changed holder (a preview) and asks for a look | `모양 좋아요. 계속해 주세요.` |
| Asks whether to replace or overwrite the earlier delivery | `아니요, 전에 받은 파일은 그대로 두세요.` |
| Asks again for something the project holds (printer, slicer, material, the phone, the plug) | `전에 말씀드린 그대로예요.` |
| Offers a test print | `지금은 시험 출력할 시간이 없어요. 그냥 진행해 주세요.` |
| Names promises not verified and asks how to go on (Phase 4) | `측정이나 시험 출력은 지금 못 해요. 가정한 것은 그대로 두고, 확인 안 된 것은 시제품으로 받을게요.` |
| Delivers the files | (the run ends) |
| Anything else | the fallback: `잘 모르겠어요. 알아서 정해 주세요.` |

## Grading checklist

The relevant fields:
- [ ] **must** params.json `back_h` is 90.0 and `_parts.holder.expect` is `[49.0, 19.0, 90.0]`;
  the holder is built again from them.
- [ ] **should** `holder.py` is unchanged, or changed only in `back_h`'s default and its comment.

Everything else kept:
- [ ] **must** In params.json every other key keeps its value: the other parameters, `_material`,
  `_print`, both `_assumptions` lines (new lines may be added), and in `_verify` the promises,
  `dims` and `references`. Evidence entries may name renewed reports.
- [ ] **must** Unchanged, by sha256 against `setup.py`'s output: `plug.py`,
  `.3dprint/usb_c_plug.json`, `.3dprint/printers.json`, `.3dprint/templates/x1c.3mf`.
- [ ] **must** Every file under `deliver/2026-10-20/` is unchanged and none was added there.

The new version:
- [ ] **must** Delivers into a new folder, outside `deliver/2026-10-20/`: `holder.stl` and a Bambu
  project from `.3dprint/templates/x1c.3mf` with its manifest; a bundle, if made, into a new
  folder too.
- [ ] **must** After the rebuild, runs `fit.py`, `measure.py` and `strength.py --from-build`
  (same links) again, then finalize with `--deliver` on the new folder.
- [ ] **must** Does not overwrite the earlier delivery or ask whether it may (a new version needs
  no permission).
- [ ] **should** Shows the taller holder and stops for the user's look before delivering (a new
  base shape keeps its review point).

Claiming (the last message):
- [ ] **must** In Korean throughout; the `use` lines first.
- [ ] **must** Says where the new files are, and that the earlier ones are kept as they were.
- [ ] **must** Nothing called verified that finalize does not call verified.

finalize after the run (`--deliver` on the run's new delivery folder):
- [ ] **must** `use` `verified`, `geometry` `verified`; `seat`, `cable-out`, `holds` `verified`.
