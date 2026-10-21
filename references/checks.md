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
