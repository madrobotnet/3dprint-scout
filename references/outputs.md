# Script output: `validate.py`, `fit.py`, `finalize.py`

Read this when you need the exact shape of a script's JSON, or why `finalize.py` judged a piece
of evidence as it did. What to declare in `_verify` and what each promise state asks of you are
in `references/checks.md`; `build.py`'s JSON, which wraps one `validate.py` document per part, is
below ("`build.py` output"). The checklist itself, with every ID, its kind and who decides it, is the
table in SKILL.md.

## `validate.py` output

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
(below).

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
(a missing or wrong `--build`, a bad `_verify`; with `--bundle`, any refusal
`references/phase-6-files.md` lists under "The source bundle": a folder that exists, a build that is no longer the project's,
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

## How finalize judges each kind of evidence

A seen image (`_verify.seen`) is a person's judgement of a preview; `image_sha256` is the digest
of the image they looked at. The entry stands while the image is still
those bytes, its sidecar (`<image>.png.json`, written by `preview.py` and `render.py`) describes
those bytes, and every STL the sidecar lists is a part of this build as it is now; otherwise it is
`stale` or `missing` (with a `note`) and a promise on it is not verified. Only the user's judgement
verifies (`by: "agent"` is not verified), `failed` fails the promise, and a promise may name it
only when its id is in `promises`.

A test print (its fields: `references/checks.md`, "Test prints") verifies only when every part is
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

## `build.py` output

One JSON document, schema `3dprint-scout.build/1`, also for `record` (this one is a `run`
with `--only`, so it shows `seconds` per part and a `partial` object):

```json
{"schema": "3dprint-scout.build/1", "ran": true, "command": "run", "engine": "python", "source": "adapter.py",
 "gate": "PASS | FAIL | INCOMPLETE", "R4": "PASS",
 "assembly_sha256": "<sha256 of the assembly inputs>",
 "parameters": {"scope": "merged", "values": {"w": 70.0, "wall": 2.0, "clearance": 0.3}},
 "parts": [{"name": "lid", "stl": "out/lid.stl", "seconds": 0.4, "material": "pla_basic", "artifact_sane": true,
            "object": "lid", "role": "fused", "rotation_deg": 0, "engine_warnings": [],
            "validate": {"schema": "3dprint-scout.validate/1", "gate": "PASS",
                         "files": [{"path": "out/lid.stl", "checks": {"D1": {"state": "PASS", "...": "..."}},
                                    "metrics": {"bbox_mm": [70, 45, 3], "volume_mm3": 9450, "...": "..."}}]},
            "assembly": {"object": "lid", "role": "fused", "checks": {"A1": {"state": "PASS", "...": "..."}}}}],
 "objects": [{"name": "lid", "parts": ["lid", "label"], "main": "lid", "gate": "PASS",
              "checks": {"D2": {"...": "..."}, "P1": {"...": "..."}, "P2": {"...": "..."}},
              "metrics": {"bbox_mm": [70, 45, 4], "volume_mm3": 9930, "shells": 1, "overhang_pct": 0.0, "...": "..."},
              "rotation_deg": 0, "method": "union of the parts (manifold3d) ..."},
             {"name": "box", "parts": ["latch", "keeper"], "main": "latch", "gate": "INCOMPLETE",
              "partial": {"object": "box", "built": ["latch", "keeper"], "missing": ["body"], "total": 3},
              "checks": {"D2": {"state": "UNVERIFIED", "note": "object built in part with --only ..."}, "...": "..."}}],
 "sources": ["adapter.py"], "threemf": "out/adapter.3mf", "seconds": 1.2,
 "warnings": ["..."], "errors": []}
```

- `parts[i].validate` is the full `validate.py` document for that part (`outputs.md` shows
  its shape); the part's verdicts are at `parts[i].validate.files[0].checks`, its numbers
  at `...files[0].metrics`. `role` is `null` for a part alone in its object; `assembly`
  exists only for parts in a group.
- `objects[]` lists every object; a single-part object has only `name`, `parts`, `main`
  (plus `partial` and `gate` when it is one part of a larger object built with `--only`).
- `command` is `run` or `record` (since 0.7.0): `finalize.py --bundle` builds a `run` again and asks
  for a `record`'s STLs to be exported again, whatever `engine` says (`record --engine blender`).
- `params` is the params file the engine got. A `--proxy` build (`references/measure.md`) carries
  `"proxy": true` and no `threemf`.
- `parameters` is what the parts were built with. `values` holds the params.json engine keys
  (no `_` keys), merged with the generator's defaults when build.py knows them:
  - `"scope": "merged"`: a Python module's `DEFAULTS` dict (`engines/python.md`) or a Blender
    generator's `PARAMETERS` (`bb.main(build, PARAMETERS)`), as `{**defaults, **params}`. A
    params.json key the defaults lack is a warning, `params.json key 'x' is not in the
    generator's DEFAULTS (a typo?)` (`PARAMETERS` for Blender): a misspelt key leaves the part
    at the default.
  - `"scope": "overrides"`: OpenSCAD, a Python generator without `DEFAULTS`, and `record`
    (Fusion, a live Blender): only the params.json values; a default kept in the generator is
    not recorded, so put a value in params.json to link to it.
  - Values are JSON. A default that is not (a function, a set, a NaN) is recorded as its repr
    string, with a warning. A value the generator computes from others (a rib height = seat +
    clearance) is not here; check it with a `measurement` instead.
  - `strength.py --from-build` links its inputs to these values (`--param h=ribbon_t`).
- `material` on a part is its material: `_parts.<name>.material`, else `_material`, else
  `null` (strength.py material keys). `_` keys are not in the freshness hash, so a changed
  material leaves the build fresh; `finalize.py` compares this record with the current
  params.json instead.
- `seconds` on a part is the engine's time for it (`run`); the top-level `seconds` is the
  whole command. `sha256` on a part is the STL its verdicts are about, and `validate_settings`
  the printer, printer id, tools and tolerances they were made with (and `printer_sha256`, the
  printers.json as it was): `finalize.py` re-checks with the same, and only trusts the object
  checks while every STL still has that hash, the settings and printers.json are unchanged,
  and `assembly_sha256` matches the current grouping, roles and free-part clearances. `run`
  writes every part STL with its triangles in a canonical order (sorted, each keeping its
  normal and winding), so a rebuild with nothing changed keeps the same bytes and hash;
  `record` leaves an STL as it was exported.
- A `_parts` grouping that cannot be read (an unknown `role`, say) is in `errors` and makes the
  gate FAIL: the parts were validated, but no object check ran.
- `record` only: a part whose STL already has a manifest from `run` that describes this very
  file gets `prior_manifest` (`engine`, `sources`, `fresh`). A fresh one is kept as the record
  (its sources join `sources`); a stale one, or one none of whose generators is among
  `--source`, is not re-stamped and the part's R3 FAILs with the reason. A manifest an
  earlier `record` wrote is simply re-stamped.
- A broken STL has `artifact_sane: false` and `artifact_error`, no manifest and no
  `validate`; `R4` is then FAIL.
- `warnings` and `errors` repeat everything worth reading from every part and object
  (validator warnings, engine warnings, a Python generator's `UserWarning`s such as a font
  switch, rotation notes), and every hard FAIL of a part, an object or an assembly check is
  one line in `errors`, `<part> <check> FAIL: <note>`. Read those two lists first.

## A worked `_verify`

The phone stand's declarations at the end of Phase 5 (each key's fields: `references/checks.md`):


```json
"_verify": {
  "promises": [
    {"id": "seat-pm15-case", "kind": "use", "text": "a 15 Pro Max in its case sits in the seat",
     "conditions": "phone upright, 15 mm thick with its case, stand on a desk",
     "success": "the lip reaches half the phone's thickness above the seat",
     "evidence": [{"measurement": "lip height"}]},
    {"id": "cable-out", "kind": "use",
     "text": "a right-angle USB-C cable plugs in and leaves at the front",
     "conditions": "phone in the seat, right-angle plug",
     "success": "plug head and cable clear the part by 0.2 mm or more",
     "evidence": [{"joint": "plug through notch", "covers": "the plug at rest in its pocket"}]},
    {"id": "cable-bend", "kind": "use", "text": "the cable bends down to the desk without a kink",
     "conditions": "the user's own cable", "success": "no sharp bend at the lip", "evidence": []},
    {"id": "tap-holds", "kind": "use", "text": "tapping the screen does not break the ribbon",
     "conditions": "phone leaning on the ribbon, a finger pushing at its top",
     "success": "the ribbon reaches SF 3 under finger_push; the printed stand takes a firm push",
     "evidence": [{"strength": "ribbon"},
                  {"test_print": "first sled", "covers": "a firm push by hand"}]},
    {"id": "wave-back", "kind": "look", "text": "the back waves once",
     "evidence": [{"seen": "back wave"}]}
  ],
  "dims": [
    {"id": "pm15-case", "what": "15 Pro Max in its case, thickness", "unit": "mm",
     "params": {"phone_t": 15.0}, "source": "caliper", "by": "user"},
    {"id": "usb-c-plug", "what": "right-angle USB-C plug head and cable", "unit": "mm",
     "params": {"plug_w": 13, "plug_h": 8, "plug_l": 9, "cable_d": 4.5},
     "source": "assumed", "tol": 0.5,
     "note": "a typical right-angle plug; the user has none at hand"}
  ],
  "joints": [{"name": "plug through notch", "report": "out/fit_plug.json", "proxy": true,
              "dims": ["usb-c-plug"], "proxy_build": "out/plug/build.json"}],
  "strength": [{"name": "ribbon", "report": "out/strength_ribbon.json"}],
  "measurements": [{"name": "lip height", "report": "out/m_lip.json", "dims": ["pm15-case"]}],
  "seen": [{"name": "back wave", "image": "out/preview.png", "by": "user", "promises": ["wave-back"],
            "result": "passed",
            "image_sha256": "83fd97b2d288a3114da16be54a781ce0a05f1ade7549bcb5894caa2a83b6073f"}],
  "test_prints": [{"name": "first sled", "status": "passed", "promises": ["tap-holds"],
                   "printer": "x2d", "orientation": "as built", "by": "user",
                   "photos": ["photos/first-sled.jpg"],
                   "preset": "0.20mm Standard @BBL X2D", "parts": {"sled": {"material": "pla_basic",
                     "sha256": "1fc1c97fe97d3feb7d4094720716000d30855fe7e5a62b4e3bd039cdef9b2c44"}}}],
  "accepted": [{"promise": "cable-bend", "reason": "I'll try it with my own cable", "by": "user"}],
  "references": {"sled": {"front": "real", "top": "real", "right": "real", "back": "estimated"}}
}
```

Delivered with `--deliver` on a folder that holds the sled's STL and a Bambu project printing
it in Bambu PLA Basic under `0.20mm Standard @BBL X2D`, finalize reads this as `use: excluded`
(5 promises: 1 excluded, 1 assumed, 3 verified): `cable-bend` the user took unverified, and
`cable-out` rests on `usb-c-plug`, which nobody measured. Delivered as STLs only, `tap-holds`
reads `assumed` too (2 assumed, 2 verified): nothing says which filament the slicer prints the
sled in.
