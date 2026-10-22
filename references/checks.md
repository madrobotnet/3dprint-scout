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
  "settings_drift": [],
  "parts": [{"name": "lid", "stl": "out/lid.stl", "sha256": "…", "same_as_build": true, "gate": "PASS", "checks": {"R3": "PASS", "...": "..."}}],
  "objects": [{"name": "box", "gate": "PASS", "parts": ["box", "lid"]}],
  "joints": [{"name": "lid on box", "report": "out/fit_box_lid.json", "fresh": "PASS", "checks": {"F3": "PASS"},
              "measured": ["box", "lid"], "result": "passed"}],
  "strength": [{"name": "latch arm", "report": "out/strength_latch.json", "gate": "PASS", "case": "pin",
                "manual": true, "result": "passed"}],
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
                {"file": "deliver/2026-10-21/box.3mf", "kind": "3mf", "manifest": true, "parts": ["box", "lid"], "same_as_verified": true}],
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
every declared member's `strength.py` gate is PASS, no WARN is left unaccepted, the delivered
copies (with `--deliver`) are the verified files, and `joints` and `strength` were declared at
all. Paths are relative to the folder it ran in. Exit 0 when it ran, 1 on a usage or file error
(a missing or wrong `--build`, a bad `_verify`, an existing `--bundle` folder, a source outside
the project folder). A malformed 3MF manifest is an `open` reason, not an error. A joint WARN
the user accepted (`joint <name> <check>` in `_verify.accepted`) does not keep the geometry from
being verified.

`use` is judged apart from `geometry`, from `_verify.promises` and `_verify.dims`. Each promise
gets one state:

| State | When |
|---|---|
| `error` | Declared wrongly: no id or the same id twice, an unknown field or kind, no `text`, a `use` without `conditions` and `success` or a `feature` without `success`, an evidence item that names no declared joint or member, names a part's own check (`box M1`) or a kind the promise does not take, or a dims entry that is missing or declared wrongly (a `caliper` value without `"by": "user"`, a `spec` without its `url` or without `where` (the place in the spec of each parameter's number), values that differ from params.json) |
| `failed` | A joint or member it names failed, even if the user took the promise |
| `excluded` | The user took it without verifying it (`{"promise": id, "reason": …, "by": "user"}` in `_verify.accepted`); its other reasons stay listed |
| `not verified` | No evidence yet, a missing or stale report, a fit report without F3 (or without F3_sweep for a joint marked `"sweep": true`), a joint that fitted a part whose own checks FAIL, a proxy whose params file changed since it was built or that was built from other values than its dims declare, a check that is neither PASS nor an accepted WARN, or a member whose inputs were typed in (every strength.py report for now) |
| `assumed` | Everything passed, but it rests on a dims entry with `source: "assumed"`, or on a proxy joint that names no dims or no `proxy_build` (the saved JSON of the `build.py run --proxy` that generated the proxy from its own params file; a proxy taken in with `build.py record` is not tied), or a proxy built from numbers its dims do not declare, or not given numbers they do |
| `accepted` | Everything passed with a WARN the user accepted |
| `verified` | None of the above |

The table is the order for one promise: a user's exclusion stands over a missing or weaker
proof, never over a failure. The tier is the worst state of all promises in another order,
`error`, `failed`, `not verified`, `excluded`, `assumed`, `accepted`, `verified`: a promise
nobody agreed to leave unproven weighs more than one the user did. It is `not declared` when
there is no promise list or it is empty, and `error` when any dims or accepted entry is
declared wrongly (`promise_errors`).
Evidence by kind: a `use` takes joints and members, a `feature` joints, a `look` nothing that is
read yet. Every promise that is not verified is the first thing in `open`; a dims entry taken
from a spec is listed there too, with its URL and places, because finalize does not read the spec.
