# Evidence: the `_verify` declarations and the promise states

Read this from Phase 4 on: what to declare in `_verify` in params.json, what each promise state
means and what it asks of you. The exact JSON of `validate.py`, `fit.py` and `finalize.py`, and
how finalize judges each kind of evidence, is in `references/outputs.md`; the checklist itself,
with every ID, its kind and who decides it, is the table in SKILL.md.

## The `_verify` declarations

`finalize.py` reads the evidence from `_verify` in params.json (its docstring is the authority;
`references/outputs.md`, "A worked `_verify`", has the phone stand's whole block).
Every key is optional, but a key left out is reported as "not declared": without `joints` or
`strength` the geometry is not verified, and without `promises` (or with an empty list) the use
tier is not declared. An empty list says there is nothing of that kind. Declare each report as
you save it and name it in the `evidence` of the promise it checks.

Every path is relative to the project folder, the folder the build runs in. Run `fit.py`,
`measure.py`, `strength.py`, `preview.py` and `render.py` from there with relative paths: they
record the paths they are given, and an absolute one, even inside the project folder, makes
`--bundle` refuse the report (and is a declaration error in a test print's `photos`). Keep the
reports, the user's files (`ref/`) and photos (`photos/`) inside the project folder.

| Key | Each entry |
|---|---|
| `promises` | `id`, `kind` (`use`, `feature` or `look`), `text`; `conditions` and `success` for a `use`, `success` for a `feature`; `evidence`, a list of `{"<kind>": "<name>", "covers": "<what it covers, one line>"}` with the kind `joint`, `strength`, `measurement`, `seen` or `test_print`; `assumes`, the dims ids it rests on that no evidence names; `"by_hand": true` on a `use` that is a motion done by hand (below); `"load": true` on a `use` that carries a force (below); optional `note` |
| `dims` | `id`, `what`, `unit`, `params` (the params.json keys with the values params.json has), `source`: `assumed`, `caliper` (with `"by": "user"`), `spec` (with `url`, and `where`: the place of each parameter's number in it) or `user-file` (with `from`: each parameter's measurement of the user's file, and `tol`; optional `own`: `true` when the file is the user's own work, which `--bundle` then carries, else it names the file with its sha256 for the user to obtain; `url` and `licence`: where a file from someone else came from and its licence); optional `tol` and `note` (where an assumed number came from) |
| `joints` | `name`, `report` (a saved `fit.py` report); `"sweep": true` for a moving part, whose report must then hold F3_sweep; a proxy joint adds `"proxy": true`, its `dims` and `proxy_build` (`references/measure.md`) |
| `strength` | `name`, `report` (a saved `strength.py --from-build` report); optional `dims` |
| `measurements` | `name`, `report` (a saved `measure.py --expect` report); optional `dims` |
| `seen` | `name`, `image`, `image_sha256` (copied from the image's sidecar when the user judges it), `by` (`user` or `agent`), `promises`, `result` (`passed` or `failed`); optional `note` |
| `test_prints` | below |
| `accepted` | A WARN the user accepted: `{"check": "<name>", "reason": "<the user's reason>"}`, named as `open` lists it: `<part> <check>` (`lid A2`), `object <name> <check>`, `joint <name> <check>` or `member <name>`; a FAIL cannot be accepted. A promise the user takes unverified: `{"promise": "<id>", "reason": "<their words>", "by": "user"}`. Either `reason` is the user's reply, word for word, to a question that named it (`references/phase-4-features-joints.md`, "What counts as agreement") |
| `decided` | Your decision on a soft check finalize leaves to you (`<part> <check> UNVERIFIED (yours to decide)`: P3 when the wall check was skipped, P4, P5, P6): `{"check": "<part> <check>", "result": "holds" or "warn", "reason": "<one line>", "sha256": "<the part's sha256 in the build JSON>"}`. `holds` takes the line out of `open`; `warn` leaves it as a WARN the user decides (`accepted`); a part built again into another STL makes the decision stale: decide again. Any other check is a declaration error |
| `unverified` | Lines of text: estimated sizes no promise rests on (a size a promise rests on is a `dims` entry) |
| `references` | Per object, each direction (`front`, `back`, `left`, `right`, `top`, `bottom`): `real`, `estimated` or `assumed` |

`dims` on a joint, member or measurement names the sizes its numbers come from; a promise that
names it takes their state. Which evidence each promise kind takes, and what finalize makes of
it: "The promise states" below; the mechanics: `references/outputs.md`.

**Test prints.** A print the user made stands for the promises it lists; record it from the
user's report, never from your expectation:

- `promises`: the ids it checked; a promise may name the print only when its id is here.
- `parts`: `{"<part>": {"sha256": "...", "material": "<strength.py key>"}}` for each printed
  part. The sha256 is the part's in the build JSON of the build whose STLs the user printed
  (`out/build.json`, or `out/mech/build.json` for an `--only` build); after delivery, the
  delivered `verification.json` lists them (`parts[].sha256`). Copy it when the files are
  handed over, never later from the files as they are then. The material is the filament it
  was printed in.
- A piece of a part, the part cut by a box (a section piece, below): its part's entry adds
  `"section": {"box": [[x0, y0, z0], [x1, y1, z1]], "stl": "<the piece's STL>"}`, and its
  sha256 is the piece's as printed (from the build JSON of the build that made the piece).
  `box` is in mm in the coordinates of the part's STL, the box the generator cut with; `stl` is
  the piece's STL, relative to the project folder (`--bundle` carries it).
- `printer` (the printers.json key), `"orientation": "as built"` (as modelled: the 3MF only turns
  a part about Z), `"by": "user"`, `status`: `passed`, `failed`, `skipped`, `offered` or
  `pending`.
- `preset`: the process preset it was printed with, as the slicer names it. Without it the print
  cannot match the delivered preset: it is not verified when the delivery's preset is known
  (`_print.preset`, or the process preset of the delivered Bambu project), and `assumed` when
  neither is.
- optional `note`, and `photos`: the paths, relative to the project folder, of the user's
  pictures of the print, which `--bundle` copies; they are no evidence.

An entry without `promises` (a coupon the user skipped, `fit_test.py` pieces: `{"name": "plug
fit test", "status": "passed", "note": "step 2 fits"}`) is no evidence and stays in the print
tier.

**A section piece.** A print of the part cut by a box, made by the part's own generator with the
cut added (a second params file), so that the piece keeps the part's coordinates. finalize reads
the piece's STL (its sha256 must be the one recorded), cuts the part as it is now by the box
(manifold3d) and compares the two: they are the same when the volume of their symmetric
difference is at most 0.1 mm³ or a millionth of the piece's volume, whichever is larger (float
rounding leaves about 1e-4 mm³; a box 0.01 mm off differs by several mm³). The comparison is
with the part as it is now, so a section stays valid while the part inside the box is
unchanged, even after the part is built again into other bytes or changed outside the box; a
piece that differs makes the print stale, as a print of an earlier part is, and one that cannot
be compared (its STL gone or not the one printed, no manifold3d) verifies nothing. The section
then stands for a promise only where the promise's own evidence checks the cut part inside the
box:

- every joint of the promise that fitted the part: the part outside the box keeps at least 1 mm,
  plus the fit's largest play, from the mating part as the fit report placed them, and through
  the whole sweep of a moving joint;
- every measurement of the promise that read the part: the part outside the box keeps 1 mm from
  the plane it sliced or the rays it cast (a `measure.py info` reads the whole part: never inside);
- a promise that names no joint or measurement of the cut part is not raised by the section.

Otherwise the promise's reasons say which joint or measurement checks the part outside the box,
and how close. A section never stands for a promise that carries a force (below).

**Another material, a section, and the strength.** A print in another material than the part's,
or a section, shows the geometry: fits, clearances, a thing passing through, a motion by hand. It
stands for a geometric promise: its material line is dropped, its evidence item reads `"scope":
"geometry"`, and the promise's reasons say what it showed (`test print 'lid fit' shows the fit,
not the strength: lid printed in pla_basic, the part is petg_hf`). It never stands for a promise
that carries a force, a `use` with `"load": true` or with `strength` evidence: a print in another
material keeps its line (`lid was printed in pla_basic, the part is petg_hf`), and a section does
not stand for it at all. When a print in another material confirms a joint whose fit report has
less than 0.2 mm of play (its F3 `min_play_mm`), finalize names it, in the promise's reasons and
in `open`: another material shrinks and squishes differently. The printer, the preset and `"as
built"` are needed as for any print; a material changed since the build, or another filament in
the delivered print file, keeps its line.

**A use that carries a load.** `"load": true` marks a `use` that carries a force: it holds a
weight, is clamped, pulled or levered. Only a strength check shows that, so without a `strength`
item among its evidence it is not verified: "it carries a load and no strength check names it".
A print in the part's own material counts for it as before.

## The promise states

`use` is judged apart from `geometry`, from `_verify.promises` and `_verify.dims`. Each promise
gets one state:

| State | When |
|---|---|
| `error` | Declared wrongly: no id or the same id twice, an unknown field or kind, no `text`, a `use` without `conditions` and `success` or a `feature` without `success`, a `by_hand` or `load` that is not `true` or `false` or is on a `feature` or `look`, an evidence item that names nothing declared of its kind (a joint, member, measurement, seen image or test print), names a part's own check (`box M1`) or a kind the promise does not take, a seen image or test print that does not list the promise in its `promises` or is declared wrongly itself (a test print's `section` too: its `box` not two corners low to high, its `stl` missing or outside the project folder), or a dims entry that is missing or declared wrongly (`own` that is not `true` or `false`, `own` or `licence` on an entry that is not `user-file`, a `caliper` value without `"by": "user"`, a `spec` without its `url` or without `where` (the place in the spec of each parameter's number), a `user-file` value without `from` for each parameter or without `tol`, or naming a measurement that is not declared, values that differ from params.json) |
| `failed` | Fresh evidence it names failed (a joint, member or measurement FAIL, a seen image judged failed, a failed test print), even if the user took the promise; a FAIL of stale evidence only leaves it not verified |
| `excluded` | The user took it without verifying it (`{"promise": id, "reason": …, "by": "user"}` in `_verify.accepted`, whose reason is their reply to a question that named it); its other reasons stay listed |
| `not verified` | No evidence yet, a missing or stale report, a measurement of a file that is not a part of this build, a dims entry not backed by its measurements, a fit report without F3 (or without F3_sweep for a joint marked `"sweep": true`), a joint that fitted a part whose own checks FAIL, a proxy whose params file changed since it was built or that was built from other values than its dims declare, a check that is neither PASS nor an accepted WARN, a member with an input typed in (any report not made with `strength.py --from-build`) or whose `--from-build` report is stale or of a part whose own checks FAIL, a seen image drawn again since it was judged, without its sidecar, or judged only by the agent, a test print that did not pass, or is not of these parts (a section: not the part as it is now cut by its box, not compared, or not holding what the promise's joints and measurements check), in their materials (another material, or a section, counts for a geometric promise only, never for one that carries a force), on the build's printer, as built, under the delivered preset, by the user (below), a `load` use that no strength check names, or material-dependent evidence (a `--from-build` member, a test print) of a part whose material changed since the build or that the delivered Bambu project prints in another filament |
| `assumed` | Everything passed, but it rests on a dims entry with `source: "assumed"`, or on a proxy joint that names no dims or no `proxy_build` (the saved JSON of the `build.py run --proxy` that generated the proxy from its own params file; a proxy taken in with `build.py record` is not tied), or a proxy built from numbers its dims do not declare, or not given numbers they do; or, with `--deliver`, material-dependent evidence of a part whose filament in the print file cannot be read (a filament name finalize does not know, and no preset it inherits from of a known material whose type the slot's `filament_type` matches; or no Bambu project: another slicer), or a test print when no preset is recorded (`_print.preset`) or the delivered Bambu project names none |
| `accepted` | Everything passed with a WARN the user accepted in reply to a question that named it |
| `verified` | None of the above |

The table is the order for one promise: a user's exclusion stands over a missing or weaker
proof, never over a failure. The tier is the worst state of all promises in another order,
`error`, `failed`, `not verified`, `excluded`, `assumed`, `accepted`, `verified`: a promise
nobody agreed to leave unproven weighs more than one the user did. It is `not declared` when
there is no promise list or it is empty, and `error` when any declaration outside a promise is
wrong (a dims, accepted, seen or test print entry, `_material`, `_parts.<name>.material`,
`_print`), each listed in `promise_errors`. Each entry of `dims` has a `state`: `assumed`,
`measured` (a caliper value, or a user-file value its measurements back), `spec`, `unbacked`
(with `problems`) or `error` (with `errors`).
Evidence by kind: a `use` takes joints, members, measurements and test prints, a `feature`
joints, measurements and test prints, a `look` seen images and test prints.

**A use done by hand.** `"by_hand": true` marks a `use` a person does with their hands: pushing
a phone into a holder, a peg in and out, a lid slid shut. A fit report shows overlap and play,
not whether the motion is smooth or the printed hole comes out at its size; only a print shows
that. The promise keeps the state its evidence gives, but while no passed test print is among
that evidence (a `test_print` whose `result` is `passed`: fresh, and the user's print passed),
its `reasons` end with "the motion by hand is not confirmed by a print (no passed test print
among its evidence)". In `open` that reason is part of the promise's line when it is not
verified, and its own line, `promise '<id>' (use): the motion by hand is not confirmed by a
print (...)`, when it is verified. A passed test print of it takes the line away. Without
`by_hand` (or with `false`) nothing is said. When the user takes the motion unproven, the
prototype line in `_assumptions` (`"<id>: delivered as a prototype, not verified"`, with their
reply) marks the promise `"prototype": true` whatever its fits give (verified, assumed or
accepted): it keeps that state, and the use summary names it.

**Reading the tier.** Read `use` before `geometry`. Each promise's `reasons` say what is missing;
what each state asks of you, in the tier's order:

- `error`: fix the declarations `promise_errors` names, then run finalize again. Never deliver
  on `error`.
- `failed`: the design breaks the promise. Go back to the phase of the failed evidence (a joint,
  a member or a measurement: Phase 4; a real-world size: Phase 2), change the design, build and
  check again (G7); no acceptance hides a failure. If the user wants the files anyway, the
  failure is the delivery's first line.
- `not verified`: renew the evidence the reasons name when a change made it stale
  (`references/phase-5-gate.md`, step 1, "After a rebuild, renew what went stale"); otherwise
  decide it with the user (`references/phase-4-features-joints.md`, "Leaving Phase 4", whose
  "When to ask" holds through Phase 6): measure or print a test, a prototype, or the user
  excludes it. A decision never makes it `assumed`. At delivery it is named first. A prototype's promise
  carries `"prototype": true` (finalize reads its `_assumptions` line, `"<id>: delivered as a
  prototype, not verified"`, and its note: phase-4, "Leaving Phase 4") and the use summary
  names it ("delivered as a prototype: ..."). So does a `by_hand` use whose motion no passed
  print confirms, in any state its fits give ("A use done by hand", above).
- `excluded`: the user took it unproven. Repeat their reason at delivery.
- `assumed`: a size nobody measured (`rests_on` names the dims entry): ask the user to measure
  it (`references/phase-2-printer-dimensions.md`, step 3, records it), or offer a test print, or
  go on with it assumed. Or a print file whose filament or preset finalize cannot read: tell the
  user what to choose in the slicer (`references/phase-6-files.md`, "The print file"). Never
  call an assumed promise verified.
- `accepted`: name the WARN the user accepted.
- `verified`: say what showed it, and what its evidence's `covers` leaves out of the promise's
  `conditions`; for a use done by hand without a passed test print, that the motion by hand is
  not confirmed by a print (its line in `open`).
- `not declared`: no promise list (a project from before 0.7.0, or none written yet). List what
  the user was promised before saying anything about use.
