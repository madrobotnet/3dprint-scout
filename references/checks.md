# `validate.py` output

Read this when you need the exact shape of `validate.py`'s JSON (Phase 5), or of the `fit.py`
verdict. The checklist itself, with every ID, its kind and who decides it, is the table in
SKILL.md; `build.py`'s JSON, which wraps one of these documents per part, is in
`references/parts.md`.

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
  "settings_drift": [], "material_drift": ["lid: material changed since the build (pla_basic -> petg_hf)"],
  "parts": [{"name": "lid", "stl": "out/lid.stl", "sha256": "…", "same_as_build": true, "gate": "PASS", "checks": {"R3": "PASS", "...": "..."}}],
  "objects": [{"name": "box", "gate": "PASS", "parts": ["box", "lid"]}],
  "joints": [{"name": "lid on box", "report": "out/fit_box_lid.json", "fresh": "PASS", "checks": {"F3": "PASS"},
              "measured": ["box", "lid"], "result": "passed"}],
  "strength": [{"name": "ribbon", "report": "out/strength_ribbon.json", "gate": "PASS", "case": "beam",
                "linked": true, "part": "sled", "parameters": {"h": "ribbon_t", "b": "ribbon_w"},
                "manual": ["length"], "result": "passed"},
               {"name": "latch arm", "report": "out/strength_latch.json", "gate": "PASS", "case": "pin",
                "linked": false, "manual": ["d", "engagement", "load", "material", "sf"], "result": "passed"}],
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
  "dims": [{"id": "usb-c-plug", "what": "…", "source": "assumed", "params": {"plug_w": 13}, "state": "assumed"}],
  "promise_errors": [],
  "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "…"}],
  "accepted": [{"check": "body P2", "reason": "…"}],
  "delivered": [{"file": "deliver/2026-10-21/lid.stl", "kind": "stl", "part": "lid", "same_as_verified": true},
                {"file": "deliver/2026-10-21/box.3mf", "kind": "3mf", "manifest": true, "parts": ["box", "lid"], "same_as_verified": true,
                 "filaments": {"box": {"slot": 1, "settings": "Bambu PLA Basic @BBL X1C", "material": "pla_basic"}, "lid": {"...": "..."}},
                 "preset": "0.20mm Standard @BBL X1C"}],
  "bundle": ["deliver/2026-10-21/source/REPRODUCE.md", "..."],
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
(a missing or wrong `--build`, a bad `_verify`, an existing `--bundle` folder, a source outside
the project folder). A malformed 3MF manifest is an `open` reason, not an error. A joint WARN
the user accepted (`joint <name> <check>` in `_verify.accepted`), or a member's strength.py WARN
accepted as `member <name>`, does not keep the geometry from being verified; a FAIL cannot be
accepted.

`use` is judged apart from `geometry`, from `_verify.promises` and `_verify.dims`. Each promise
gets one state:

| State | When |
|---|---|
| `error` | Declared wrongly: no id or the same id twice, an unknown field or kind, no `text`, a `use` without `conditions` and `success` or a `feature` without `success`, an evidence item that names no declared joint or member, names a part's own check (`box M1`) or a kind the promise does not take, or a dims entry that is missing or declared wrongly (a `caliper` value without `"by": "user"`, a `spec` without its `url` or without `where` (the place in the spec of each parameter's number), a `user-file` value without `from` for each parameter or without `tol`, or naming a measurement that is not declared, values that differ from params.json) |
| `failed` | A joint or member it names failed, even if the user took the promise |
| `excluded` | The user took it without verifying it (`{"promise": id, "reason": …, "by": "user"}` in `_verify.accepted`); its other reasons stay listed |
| `not verified` | No evidence yet, a missing or stale report, a measurement of a file that is not a part of this build, a dims entry not backed by its measurements, a fit report without F3 (or without F3_sweep for a joint marked `"sweep": true`), a joint that fitted a part whose own checks FAIL, a proxy whose params file changed since it was built or that was built from other values than its dims declare, a check that is neither PASS nor an accepted WARN, a member with an input typed in (any report not made with `strength.py --from-build`) or whose `--from-build` report is stale or of a part whose own checks FAIL, or material-dependent evidence (a `--from-build` member, a test print) of a part whose material changed since the build or that the delivered Bambu project prints in another filament |
| `assumed` | Everything passed, but it rests on a dims entry with `source: "assumed"`, or on a proxy joint that names no dims or no `proxy_build` (the saved JSON of the `build.py run --proxy` that generated the proxy from its own params file; a proxy taken in with `build.py record` is not tied), or a proxy built from numbers its dims do not declare, or not given numbers they do; or, with `--deliver`, material-dependent evidence of a part whose filament in the print file cannot be read (a filament name finalize does not know, or no Bambu project: another slicer) |
| `accepted` | Everything passed with a WARN the user accepted |
| `verified` | None of the above |

The table is the order for one promise: a user's exclusion stands over a missing or weaker
proof, never over a failure. The tier is the worst state of all promises in another order,
`error`, `failed`, `not verified`, `excluded`, `assumed`, `accepted`, `verified`: a promise
nobody agreed to leave unproven weighs more than one the user did. It is `not declared` when
there is no promise list or it is empty, and `error` when any dims or accepted entry is
declared wrongly (`promise_errors`).
Evidence by kind: a `use` takes joints, members, measurements and test prints, a `feature`
joints, measurements and test prints, a `look` seen images and test prints.

A seen image (`_verify.seen`) is a person's judgement of a preview: `{"name", "image",
"image_sha256", "by": "user" | "agent", "promises": [ids], "result": "passed" | "failed"}`.
`image_sha256` is the digest of the image they looked at. The entry stands while the image is
still those bytes, its sidecar (`<image>.png.json`, written by `preview.py` and `render.py`)
describes those bytes, and every STL the sidecar lists is a part of this build as it is now;
otherwise it is `stale` or `missing` and a promise on it is not verified. Only the user's
judgement verifies (`by: "agent"` is not verified), `failed` fails the promise, and a promise
may name it only when its id is in `promises`.

A test print stands as evidence when it lists `promises` (the promise must be one of them),
`parts` (each printed part's sha256 from the build JSON handed over, and the `material` it was
printed in, a strength.py key), `printer`, `orientation` and `by`, and `preset` when one was
used. It verifies only when every part is the part of this build now, each material is the
part's own (`_parts.<name>.material`, else `_material`), the printer is the build's, the
orientation is `"as built"`, `by` is the user, the status is `passed`, and the preset is the
delivered one: `_print.preset` in params.json and, with `--deliver`, the process preset of every
delivered Bambu project the printed parts are in (without `_print.preset` that project's preset is
the one compared; when neither is recorded the print is `assumed`). The material must also be
the one the build recorded, and with `--deliver` the one the print file selects (below).
A failed print fails the promise; a skipped, offered or pending one leaves it not verified. A
0.6 entry without `promises` stays in the print tier and is not evidence. `_material`,
`_parts.<name>.material` and `_print` are checked as declared (an unknown material key is a
declaration error).

A measurement is a saved `measure.py ... --expect` report (`references/measure.md`). Its
`result` is `missing` (no readable report with expectations, or one whose values, states and
gate do not follow from the file: finalize runs the report's command again on it, which needs
numpy, and reads each path in that output), `stale` (the file it read is not
the one whose `file_sha256` it recorded, or is gone), `failed` (an expectation failed) or
`passed`; `measured` names the parts of this build it read. As evidence of a promise it must
have read a part of this build, and that part's own checks must not FAIL. A dims entry with
`source: "user-file"` names in `from`, for each parameter, the measurement of the user's file
it was read from, and a `tol`: each measurement must be fresh and passed, read no part of this
build, hold one `=` expectation and have measured the params value within `tol`; otherwise the
entry is `unbacked` and lists its `problems`, and a promise resting on it is not verified. Every promise that is not verified is the first thing in `open`; a dims entry taken
from a spec is listed there too, with its URL and places, because finalize does not read the spec.

A member is evidence of a `use` promise only from a report written with `strength.py
--from-build out/build.json --part NAME --param INPUT=PARAM ...`. Such a report names the part,
its sha256 and material in that build, and each input it took from the build's `parameters`
(`from_build`), and says where every input came from (`inputs_from`: `param:<name>`,
`table:<key>`, `build:material`, `default:<input>` or `manual`). finalize keeps it fresh only
while NAME is a part of this build whose STL has the sha256 it read ("calculated for an earlier
sled"), every parameter it took has the same value in this build JSON's `parameters.values` (a
dotted path for a nested one: "h was ribbon_t = 4.5, now 5.0", "ribbon_t is not in the build's
parameters"), its material is the part's material now (`_parts.<name>.material`, else
`_material`), and its inputs, origins and `from_build` agree. A stale report is a geometry reason
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
keeps the test prints of that project's parts from verifying. None of these is a geometry reason.
Without `--deliver` nothing of the print file is read.
