# Phase 5 — Gate and process tuning (review point)

Read this on entering Phase 5 (SKILL.md holds the checklist table and the rules that hold at
all times; `references/checks.md` describes `validate.py`'s JSON).

1. Validate every part against **its own** `expect`: re-run the Phase 3 `build.py run` (or
   `record`) command and save what it prints (`build.py run ... > out/build.json`); it validates
   each part with that part's `expect` and the exact source list it hashed. To re-check one STL without rebuilding, call `validate.py` once per part:

   ```bash
   python3 "$SKILL_DIR/scripts/validate.py" out/body.stl --expect 71.2,37.8,33.6 \
     --printer .3dprint/printers.json --source model.scad lib.scad --params .3dprint/params.json
   ```

   `--expect` is one part's size, so one `validate.py` call per part. `--source` must list the
   same files the build hashed (`build.py` prints them as `sources`, includes and all); R3 names
   both lists when they differ. Editing only `_` keys in `params.json` does not make an STL stale.
   Pass the same `--tools` the build had (`references/phase-2-printer-dimensions.md`, step 1).
2. Decide the checks `validate.py` lists in `not_covered`: F3 with `fit.py` (one run per joint,
   both parts placed as assembled); F1, F2, R1, R2 and R4 yourself, each with evidence. F3
   counts only from a report about the STLs being delivered: `fit.py --check out/fit_box_lid.json`
   must say PASS (G1); STALE means a part was rebuilt since, so run that fit again. F3 is N/A
   for a `fused` part (a colour inlay, a label): A1 decides its contact. P6 is not in that
   list but is yours too, from the `preview.py` image, or from the generator and its log when
   the image cannot show the bed edge: a `bb.bevel` with `bed=False` leaves it alone, and with
   no chamfer the preset's elephant-foot compensation covers it (0.15 mm in the X2D's
   `0.20mm Standard`, `phase-2-printer-dimensions.md`, step 4).
3. On a hard FAIL, go where its `return_to` says (the checklist table in SKILL.md), fix the
   cause, rebuild, re-validate. On a soft WARN, explain it and let the user choose (slicer
   supports or a redesign). Never model support structures into the part: overhangs get the
   slicer's supports (set per object in step 4) or a redesign such as a chamfer or teardrop.
4. **Print settings.** Keep the user's slicer preset as the baseline and change only what this
   part needs, each change with a reason. Bambu Studio: read `references/bambu-process.md`, make
   a template if `printers.json` has none (a saved empty project first, generated from preset
   names as the fallback), and write the changes as per-object settings with `bambu3mf.py`
   (supports, support interface filament and Z distance, brim, walls, infill, ...).
   Any other slicer: give a three-line recipe (material, layer height, walls, infill, supports,
   orientation, and why).
5. **Declare the evidence** in `params.json` under `_verify`, for `finalize.py` in Phase 6: every
   joint F3 covers with its saved report, every member's saved `strength.py` report
   (`strength.py ... > out/strength_latch.json`), the test prints with their status, each WARN the
   user accepted with their reason, and the dimensions taken without a measurement. A list left
   out is reported as "not declared", which keeps the geometry from being verified; an empty
   list says there is nothing of that kind:

   ```json
   "_verify": {
     "joints": [{"name": "lid on box", "report": "out/fit_box_lid.json"}],
     "strength": [],
     "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "user had no time"}],
     "accepted": [{"check": "body P2", "reason": "the user wants supports under the ledge"}],
     "unverified": ["wall behind the label: from a photo"],
     "references": {"box": {"front": "real", "top": "real", "back": "estimated"}}
   }
   ```

   A joint fitted against a proxy of the mating part (built from measured or published numbers)
   gets `"proxy": true`; `finalize.py` then says the fit shows agreement with those numbers, not
   that they are right. Test print status: `passed`, `failed`, `skipped`, `offered` or
   `pending`.
