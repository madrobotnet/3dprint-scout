# `validate.py` output

Read this when you need the exact shape of `validate.py`'s JSON (Phase 5), of the `fit.py` verdict,
of the `_verify` declarations (Phase 4 on), or of `finalize.py`'s report and how to read its `use`
tier (Phase 4 and 6). The checklist itself, with
every ID, its kind and who decides it, is the table in SKILL.md; `build.py`'s JSON, which wraps one
of these documents per part, is in `references/parts.md`.

Standard library only. Always prints one JSON document, even on errors.

```json
{
  "schema": "3dprint-scout.validate/1",
  "ran": true,
  "gate": "PASS | FAIL | INCOMPLETE",
  "printer": {"id": "x2d", "tools": [0, 1], "usable_rect": [20.5, 0, 256, 256], "height": 256},
  "files": [{
    "path": "body.stl",
    "artifact_sane": true,
    "checks": {"D2": {"state": "FAIL", "kind": "hard", "value": {"...": "..."},
                      "note": "footprint does not fit the usable area at any rotation",
                      "return_to": "phase2"}},
    "metrics": {"triangles": 12, "bbox_mm": [20, 20, 20], "volume_mm3": 8000, "shells": 1,
                "overhang_pct": 0.0, "bed_contact_mm2": 400}
  }],
  "not_covered": ["F1", "F2", "F3", "R1", "R2", "R4"],
  "warnings": [], "errors": []
}
```

`gate` is **PASS** (every hard check passed or N/A), **FAIL** (any hard FAIL or a broken
artifact), or **INCOMPLETE** (no FAIL, but some hard check is UNVERIFIED). Never present
INCOMPLETE as PASS; name what is unverified and why. Soft checks never change the gate.

Exit code 0 means it ran (read `gate`), 2 means a broken artifact (G4), 1 means a usage or
internal error. A failed artifact has `artifact_sane: false` and `artifact_error`, and no checks.
`not_covered` always lists F1–F3, R1, R2, R4: F3 is decided by `fit.py` (schema
`3dprint-scout.fit/1`, the same `checks.F3.state` / `kind` / `value` / `note` shape), the rest by you.
`build.py` wraps one such document per part under `parts[].validate` and adds `objects[]`
(`references/parts.md`).

## `fit.py` output

A fit report names the STLs it measured, so it can be told apart from a newer build (G1):

```json
{
  "schema": "3dprint-scout.fit/1",
  "ran": true,
  "gate": "PASS | WARN | FAIL | UNVERIFIED",
  "parts": {"a": {"path": "out/box.stl", "sha256": "9f2c…", "input_hash": "41ab… | null",
                  "triangles": 2296, "volume_mm3": 19495.969, "bbox_mm": [70, 45, 30], "bbox_min_mm": [0, 0, 0]},
            "b": {"...": "..."}},
  "placement": {"...": "..."},
  "checks": {"F3": {"state": "PASS", "kind": "hard", "value": {"...": "..."}, "note": "..."}},
  "metrics": {"...": "..."},
  "warnings": [], "errors": []
}
```

`sha256` is the STL file's hash; `input_hash` is copied from the build manifest next to the STL
only when that manifest records this very STL (its `artifact_sha256` matches), else `null`.
With `--sweep-*` there is a second check, `F3_sweep` (`value`: `first_overlap_deg`,
`free_until_deg`, `free_travel_deg`, `required_travel_deg`, `closest`), and `metrics.sweep`
holds the table of steps (plus the required travel, marked `required_travel`, and the two
angles between steps that bracket the stop, marked `between_steps`), `reach_radius_mm` (the farthest point of B from the axis) and
`between_steps_checked` (how many angles between steps were checked).
Save each report (`fit.py A B ... > out/fit_box_lid.json`). `fit.py --check REPORT`, run from the
folder the fit was run in, rehashes the STLs at the recorded paths and prints the same envelope
(plus `report`, the file it read; `parts` holds each path with its `recorded_sha256` and
`current_sha256`) with one check, `F3_fresh`: **PASS** when both are unchanged, **FAIL** when one changed (`STALE`,
`return_to: "current"`: run the fit again) or is missing, **UNVERIFIED** when the report has no
`sha256` (written before fit.py recorded them). It says nothing about the fit itself: read the
report's own gate, which `F3_fresh.value.report_gate` repeats.

## The `_verify` declarations

`finalize.py` reads the evidence from `_verify` in params.json (its docstring is the authority;
`references/phase-5-gate.md`, step 5, has the phone stand's whole block as a worked example).
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
| `promises` | `id`, `kind` (`use`, `feature` or `look`), `text`; `conditions` and `success` for a `use`, `success` for a `feature`; `evidence`, a list of `{"<kind>": "<name>", "covers": "<what it covers, one line>"}` with the kind `joint`, `strength`, `measurement`, `seen` or `test_print`; `assumes`, the dims ids it rests on that no evidence names; optional `note` |
| `dims` | `id`, `what`, `unit`, `params` (the params.json keys with the values params.json has), `source`: `assumed`, `caliper` (with `"by": "user"`), `spec` (with `url`, and `where`: the place of each parameter's number in it) or `user-file` (with `from`: each parameter's measurement of the user's file, and `tol`); optional `tol` and `note` (where an assumed number came from) |
| `joints` | `name`, `report` (a saved `fit.py` report); `"sweep": true` for a moving part, whose report must then hold F3_sweep; a proxy joint adds `"proxy": true`, its `dims` and `proxy_build` (`references/measure.md`) |
| `strength` | `name`, `report` (a saved `strength.py --from-build` report); optional `dims` |
| `measurements` | `name`, `report` (a saved `measure.py --expect` report); optional `dims` |
| `seen` | `name`, `image`, `image_sha256` (copied from the image's sidecar when the user judges it), `by` (`user` or `agent`), `promises`, `result` (`passed` or `failed`); optional `note` |
| `test_prints` | below |
| `accepted` | A WARN the user accepted: `{"check": "<name>", "reason": "<the user's reason>"}`, named as `open` lists it: `<part> <check>` (`lid A2`), `object <name> <check>`, `joint <name> <check>` or `member <name>`; a FAIL cannot be accepted. A promise the user takes unverified: `{"promise": "<id>", "reason": "<their words>", "by": "user"}`. Either `reason` is the user's reply, word for word, to a question that named that WARN or promise (`references/phase-4-features-joints.md`, "What counts as agreement"); a look, a "you decide", an earlier answer or silence makes no entry |
| `unverified` | Lines of text: estimated sizes no promise rests on (a size a promise rests on is a `dims` entry) |
| `references` | Per object, each direction (`front`, `back`, `left`, `right`, `top`, `bottom`): `real`, `estimated` or `assumed` |

`dims` on a joint, member or measurement names the sizes its numbers come from; a promise that
names it takes their state. Which evidence each promise kind takes, and what finalize makes of
it: "`finalize.py` output" below.

**Test prints.** A print the user made stands for the promises it lists; record it from the
user's report, never from your expectation:

- `promises`: the ids it checked; a promise may name the print only when its id is here.
- `parts`: `{"<part>": {"sha256": "...", "material": "<strength.py key>"}}` for each printed
  part. The sha256 is the part's in the build JSON of the build whose STLs the user printed
  (`out/build.json`, or `out/mech/build.json` for an `--only` build); after delivery, the
  delivered `verification.json` lists them (`parts[].sha256`). Copy it when the files are
  handed over, never later from the files as they are then. The material is the filament it
  was printed in.
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

## `finalize.py` output

The final report of Phase 6 (`references/phase-6-deliver.md`), schema `3dprint-scout.finalize/1`:

```json
{
  "schema": "3dprint-scout.finalize/1", "ran": true, "build": "out/build.json", "engine": "python",
  "use": "error | failed | not verified | excluded | assumed | accepted | verified | not declared",
  "geometry": "verified | not verified",
  "shape": {"lid": {"coverage": {"front": "real", "back": "estimated", "...": "..."},
                    "verified_from": ["front", "top"], "not_verified_from": ["back", "..."]}},
  "slicing": "unverified", "print": "unverified (test prints passed: hinge coupon; ...)",
  "settings": {"printer": ".3dprint/printers.json", "printer_id": null, "tools": "1", "tol": null, "...": "...", "wall_check": true},
  "settings_drift": [], "assembly_drift": [], "material_drift": ["lid: material changed since the build (pla_basic -> petg_hf)"],
  "parts": [{"name": "lid", "stl": "out/lid.stl", "sha256": "…", "same_as_build": true, "gate": "PASS", "checks": {"R3": "PASS", "...": "..."}}],
  "objects": [{"name": "box", "gate": "PASS", "parts": ["box", "lid"]}],
  "joints": [{"name": "lid on box", "report": "out/fit_box_lid.json", "fresh": "PASS", "checks": {"F3": "PASS"},
              "measured": ["box", "lid"], "result": "passed"},
             {"name": "plug through notch", "report": "out/fit_plug.json", "fresh": "PASS", "checks": {"F3": "PASS"},
              "measured": ["stand"], "proxy": true, "proxy_build": "tied",
              "proxy_params": {"plug_w": 13, "plug_h": 8, "plug_l": 9}, "result": "passed"}],
  "strength": [{"name": "ribbon", "report": "out/strength_ribbon.json", "gate": "PASS", "case": "beam",
                "linked": true, "part": "sled", "parameters": {"h": "ribbon_t", "b": "ribbon_w"},
                "manual": ["length"], "result": "passed"},
               {"name": "base", "report": "out/strength_base.json", "gate": "PASS", "case": "beam",
                "linked": true, "part": "stand", "parameters": {"h": "base_t", "b": "base_w"}, "manual": [],
                "stale": ["calculated for an earlier stand", "h was base_t = 6.0, now 6.5"], "result": "stale"},
               {"name": "latch arm", "report": "out/strength_latch.json", "gate": "WARN", "case": "pin",
                "linked": false, "manual": ["load", "material", "orientation", "sf", "d", "engagement", "gap", "shear",
                                            "support"], "result": "open"}],
  "seen": [{"name": "front look", "image": "out/look.png", "by": "user", "result": "passed", "promises": ["wave"],
            "state": "fresh", "shows": ["box", "lid"]}],
  "measurements": [{"name": "lip height", "report": "out/m_lip.json", "file": "out/sled.stl", "measured": ["sled"],
                    "expect": [{"path": "levels[0].loops[0].size[1]", "op": ">=", "target": 7.5, "value": 8.1,
                                "state": "PASS"}], "result": "passed"}],
  "promises": [{"id": "cable-out", "kind": "use", "text": "…", "conditions": "…", "success": "…",
                "state": "assumed", "reasons": ["rests on 'usb-c-plug' (…), which is assumed, not measured"],
                "evidence": [{"joint": "plug through notch", "result": "passed", "covers": "…"}],
                "rests_on": ["usb-c-plug"]}],
  "promise_counts": {"use": {"assumed": 1, "verified": 2}, "look": {"not verified": 1}},
  "dims": [{"id": "usb-c-plug", "what": "…", "source": "assumed", "params": {"plug_w": 13}, "unit": "mm", "tol": 0.5,
            "note": "a maker's drawing of a similar plug", "state": "assumed"}],
  "promise_errors": [],
  "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "…"}],
  "accepted": [{"check": "body P2", "reason": "…"}],
  "delivered": [{"file": "deliver/2026-10-21/lid.stl", "kind": "stl", "part": "lid", "same_as_verified": true},
                {"file": "deliver/2026-10-21/box.3mf", "kind": "3mf", "manifest": true, "parts": ["box", "lid"], "same_as_verified": true,
                 "filaments": {"box": {"slot": 1, "settings": "Bambu PLA Basic @BBL X1C", "material": "pla_basic"}, "lid": {"...": "..."}},
                 "preset": "0.20mm Standard @BBL X1C"}],
  "bundle": ["deliver/2026-10-21/source/REPRODUCE.md", "..."],
  "bundle_missing": ["photos/notch.jpg: photo of test print 'notch'"],
  "open": ["promise 'cable-out' (use) assumed: rests on 'usb-c-plug' …", "joint 'lid on box': F3_fresh FAIL: STALE: …",
           "assumption: …"],
  "summary": ["use: not verified (4 promises: 1 not verified, 1 assumed, 2 verified)", "geometry: …", "shape: …",
              "slicing: unverified (not sliced here)", "print: …"],
  "assumptions": ["…"], "unverified_dimensions": ["…"], "warnings": [], "errors": []
}
```

`geometry` is `verified` only when the build ran without errors and its gate was not FAIL (an
INCOMPLETE gate is named by the UNVERIFIED checks behind it), built every
part in `_parts`, every part validates now (with the build's settings) with R3 PASS and no hard
FAIL or UNVERIFIED and a D1 against an expect that was not copied from the model (or that the
user accepted as `<part> D1` in `_verify.accepted`), every STL is
the one the build JSON judged and the settings are the build's (`settings_drift` empty: no
other printer, printer id, tools or tolerance given here, and printers.json unchanged since the
build), so its object checks stand, every declared joint's
report is fresh and its F3 / F3_sweep PASS against the delivered parts (or a declared proxy;
F3 must be in it, and F3_sweep too for a joint marked `"sweep": true`),
every declared member's `strength.py` gate is PASS (and a `--from-build` report is still of this
build: see below), no WARN is left unaccepted, the delivered
copies (with `--deliver`) are the verified files, and `joints` and `strength` were declared at
all. Paths are relative to the folder it ran in. Exit 0 when it ran, 1 on a usage or file error
(a missing or wrong `--build`, a bad `_verify`; with `--bundle`, any refusal the phase 6 file
lists under "The source bundle": a folder that exists, a build that is no longer the project's,
a file outside the project folder, a carried file the rebuild writes again, a text file that
holds a path of this machine). `bundle` lists the files `--bundle` wrote; `bundle_missing` the files
`_verify` names that were not found (`"<path>: <what it is>"`), which the bundle leaves out and
REPRODUCE.md lists too. A malformed 3MF manifest is an `open` reason, not an error. A joint WARN
the user accepted (`joint <name> <check>` in `_verify.accepted`), or a member's strength.py WARN
accepted as `member <name>`, does not keep the geometry from being verified; a FAIL cannot be
accepted. Each `joints` and `strength` entry has the `result` a promise reads: `missing`, `stale`,
`failed`, `open` (a check neither PASS nor an accepted WARN), `accepted` or `passed`. A joint's
`measured` names the parts of this build it fitted; a proxy joint adds `proxy_build`: `tied`
(generated by `build.py run --proxy` from its params file as it is now; `proxy_params` are the
numbers it got), `untied` or `stale`, with `proxy_note` saying why.

`use` is judged apart from `geometry`, from `_verify.promises` and `_verify.dims`. Each promise
gets one state:

| State | When |
|---|---|
| `error` | Declared wrongly: no id or the same id twice, an unknown field or kind, no `text`, a `use` without `conditions` and `success` or a `feature` without `success`, an evidence item that names nothing declared of its kind (a joint, member, measurement, seen image or test print), names a part's own check (`box M1`) or a kind the promise does not take, a seen image or test print that does not list the promise in its `promises` or is declared wrongly itself, or a dims entry that is missing or declared wrongly (a `caliper` value without `"by": "user"`, a `spec` without its `url` or without `where` (the place in the spec of each parameter's number), a `user-file` value without `from` for each parameter or without `tol`, or naming a measurement that is not declared, values that differ from params.json) |
| `failed` | Fresh evidence it names failed (a joint, member or measurement FAIL, a seen image judged failed, a failed test print), even if the user took the promise; a FAIL of stale evidence only leaves it not verified |
| `excluded` | The user took it without verifying it (`{"promise": id, "reason": …, "by": "user"}` in `_verify.accepted`, whose reason is their reply to a question that named it); its other reasons stay listed |
| `not verified` | No evidence yet, a missing or stale report, a measurement of a file that is not a part of this build, a dims entry not backed by its measurements, a fit report without F3 (or without F3_sweep for a joint marked `"sweep": true`), a joint that fitted a part whose own checks FAIL, a proxy whose params file changed since it was built or that was built from other values than its dims declare, a check that is neither PASS nor an accepted WARN, a member with an input typed in (any report not made with `strength.py --from-build`) or whose `--from-build` report is stale or of a part whose own checks FAIL, a seen image drawn again since it was judged, without its sidecar, or judged only by the agent, a test print that did not pass, or is not of these parts in their materials on the build's printer, as built, under the delivered preset, by the user (below), or material-dependent evidence (a `--from-build` member, a test print) of a part whose material changed since the build or that the delivered Bambu project prints in another filament |
| `assumed` | Everything passed, but it rests on a dims entry with `source: "assumed"`, or on a proxy joint that names no dims or no `proxy_build` (the saved JSON of the `build.py run --proxy` that generated the proxy from its own params file; a proxy taken in with `build.py record` is not tied), or a proxy built from numbers its dims do not declare, or not given numbers they do; or, with `--deliver`, material-dependent evidence of a part whose filament in the print file cannot be read (a filament name finalize does not know, or no Bambu project: another slicer), or a test print when no preset is recorded (`_print.preset`) or the delivered Bambu project names none |
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

**Reading the tier.** Read `use` before `geometry`. Each promise's `reasons` say what is missing;
what each state asks of you, in the tier's order:

- `error`: fix the declarations `promise_errors` names, then run finalize again.
- `failed`: the design breaks the promise. Go back to the phase of the failed evidence and change
  the design; no acceptance hides a failure.
- `not verified`: renew the evidence the reasons name when a change made it stale
  (`references/phase-5-gate.md`, step 1, "After a rebuild, renew what went stale"); otherwise
  decide it with the user (`references/phase-4-features-joints.md`, "Leaving Phase 4"): measure
  or print a test, a prototype, or the user excludes it, asked in a message that names it. A
  decision never makes it `assumed`. At delivery it is named first. A prototype's promise
  carries `"prototype": true` (finalize reads its `_assumptions` line) and the use summary names
  it ("delivered as a prototype: ...").
- `excluded`: the user took it unproven. Repeat their reason at delivery.
- `assumed`: a size nobody measured (`rests_on` names the dims entry): ask the user to measure
  it (`references/phase-2-printer-dimensions.md`, step 3, records it), or offer a test print, or
  go on with it assumed. Or a print file whose filament or preset finalize cannot read: tell the
  user what to choose in the slicer (`references/phase-6-deliver.md`, "The print file"). Never
  call an assumed promise verified.
- `accepted`: name the WARN the user accepted.
- `verified`: say what showed it, and what its evidence's `covers` leaves out of the promise's
  `conditions`.
- `not declared`: no promise list (a project from before 0.7.0, or none written yet). List what
  the user was promised before saying anything about use.

A seen image (`_verify.seen`) is a person's judgement of a preview; `image_sha256` is the digest
of the image they looked at. The entry stands while the image is still
those bytes, its sidecar (`<image>.png.json`, written by `preview.py` and `render.py`) describes
those bytes, and every STL the sidecar lists is a part of this build as it is now; otherwise it is
`stale` or `missing` (with a `note`) and a promise on it is not verified. Only the user's judgement
verifies (`by: "agent"` is not verified), `failed` fails the promise, and a promise may name it
only when its id is in `promises`.

A test print (its fields: "The `_verify` declarations" above) verifies only when every part is
the part of this build now, each material is the part's own (`_parts.<name>.material`, else
`_material`), the printer is the build's, the orientation is `"as built"`, `by` is the user, the
status is `passed`, and the preset is the delivered one: `_print.preset` in params.json and, with
`--deliver`, the process preset of every delivered Bambu project the printed parts are in
(without `_print.preset` that project's preset is the one compared; when neither is recorded, or
a delivered project names no preset, the print is `assumed`). The material must also be the one
the build recorded, and with `--deliver` the one the print file selects (below). A failed print
fails the promise; a skipped, offered or pending one leaves it not verified. `_material`,
`_parts.<name>.material` and `_print` are checked as declared (an unknown material key is a
declaration error).

A measurement is a saved `measure.py ... --expect` report (`references/measure.md`). Its `result`
is `missing` (no readable report with expectations, or one whose values, states and gate do not
follow from the file: finalize runs the report's command again on it, which needs numpy, and reads
each path in that output), `stale` (the file it read is not the one whose `file_sha256` it
recorded, or is gone), `failed` (an expectation failed) or `passed`; `measured` names the parts of
this build it read. As evidence of a promise it must have read a part of this build, and that
part's own checks must not FAIL. A dims entry with `source: "user-file"` names in `from`, for each
parameter, the measurement of the user's file it was read from, and a `tol`: each measurement must
be fresh and passed, read no part of this build, hold one `=` expectation and have measured the
params value within `tol`; otherwise the entry is `unbacked` and lists its `problems`, and a
promise resting on it is not verified. `open` begins with the declaration errors, then every
promise that is not verified; a dims entry taken from a spec is listed there too, with its URL and
places, because finalize does not read the spec.

A member is evidence of a `use` promise only from a report written with `strength.py
--from-build out/build.json --part NAME --param INPUT=PARAM ...`. Such a report names the part,
its sha256 and material in that build, and each input it took from the build's `parameters`
(`from_build`), and says where every input came from (`inputs_from`: `param:<name>`,
`table:<key>`, `build:material`, `default:<input>` or `manual`). finalize keeps it fresh only
while NAME is a part of this build whose STL has the sha256 it read ("calculated for an earlier
sled"), every parameter it took has the same value in this build JSON's `parameters.values` (a
dotted path for a nested one: "h was ribbon_t = 4.5, now 5.0", "ribbon_t is not in the build's
parameters"), its material is the part's material now (`_parts.<name>.material`, else
`_material`), and its inputs, origins and `from_build` agree. Otherwise its entry has `stale`,
the reasons, and `result` `stale`. A stale report is a geometry reason
("run strength.py --from-build again", like a stale fit report) and leaves its promises not
verified; a FAIL of a stale report is not a failure of this design. `manual` lists the inputs
typed on the command line (every input of a report made without `--from-build`): the geometry
only notes them, as before, but a promise on that member is not verified, by their names (a
custom safety factor belongs in params.json too, linked with `--param sf=...`). `table:`,
`default:` and `build:` origins are not typed in. The member is not verified either while the
part's own checks FAIL (params.json changed and the part was not built again).

The build JSON records each part's material (`parts[].material`). A material is not an engine
parameter, so changing `_material` or `_parts.<name>.material` leaves every STL fresh; finalize
compares the recorded material with params.json now and lists each difference in
`material_drift` and `open` ("lid: material changed since the build (pla_basic -> petg_hf)").
It is not a geometry reason, but the material-dependent evidence of that part (a test print of
it; a `--from-build` member of it is stale already) is not verified until the build is made
again. A build JSON from before 0.7.0 records no material, and nothing is said.

With `--deliver`, a delivered Bambu project's manifest (written by `bambu3mf.py`) names each
part's filament slot and settings name (`filaments`) and the process preset (`process`); each
3MF entry of `delivered` repeats them, with the material key of each filament
(`strength.material_of_filament`: "Bambu PLA Basic @BBL X1C" is `pla_basic`). A filament of
another material than the part's is an `open` line and leaves the part's material-dependent
evidence (a `--from-build` member of it, a test print of it) not verified; a filament name
finalize does not know, or none, is an `open` line ("the slicer's filament for lid is not
checked") and leaves that evidence `assumed`; so does a part in no delivered Bambu project (STLs,
or a core 3MF of build.py, for another slicer: "the print file's material is not checked (no
Bambu project)"). A process preset other than a declared `_print.preset` is an `open` line and
keeps the test prints of that project's parts from verifying. A Bambu project that names no
process preset has `"preset": null`; it is an `open` line ("the project names no process preset, so a
test print cannot be compared with it: choose "0.20mm Standard @BBL X1C" in the slicer", the
declared preset) and leaves the test prints of its parts `assumed`, even with `_print.preset` declared.
A core 3MF selects neither, so its entry has neither `filaments` nor `preset`. None of these is
a geometry reason.
Without `--deliver` nothing of the print file is read.
