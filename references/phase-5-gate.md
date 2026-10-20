# Phase 5 — Gate and process tuning (review point)

Read this on entering Phase 5 (SKILL.md holds the checklist table and the rules that hold at
all times; `references/checks.md` describes `validate.py`'s JSON).

1. Validate every part against **its own** `expect`: re-run the Phase 3 `build.py run` (or
   `record`) command; it validates each part with that part's `expect` and the exact source list
   it hashed. To re-check one STL without rebuilding, call `validate.py` once per part:

   ```bash
   python3 "$SKILL_DIR/scripts/validate.py" out/body.stl --expect 71.2,37.8,33.6 \
     --printer .3dprint/printers.json --tools 0 --source model.scad lib.scad --params .3dprint/params.json
   ```

   `--expect` is one part's size, so one `validate.py` call per part. `--source` must list the
   same files the build hashed (`build.py` prints them as `sources`, includes and all); R3 names
   both lists when they differ. Editing only `_` keys in `params.json` does not make an STL stale.
2. Decide the checks `validate.py` lists in `not_covered`: F3 with `fit.py` (one run per joint,
   both parts placed as assembled); F1, F2, R1, R2 and R4 yourself, each with evidence. F3
   counts only from a report about the STLs being delivered: `fit.py --check out/fit_box_lid.json`
   must say PASS (G1); STALE means a part was rebuilt since, so run that fit again. P6 is not in that
   list but is yours too, from the `preview.py` image.
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
