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
