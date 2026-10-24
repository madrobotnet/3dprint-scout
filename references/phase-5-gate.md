# Phase 5 — Gate and process tuning (review point)

Read this on entering Phase 5 (SKILL.md holds the checklist table and the rules that hold at
all times; `references/checks.md` has the `_verify` declarations).

1. Validate every part against **its own** `expect`: re-run the Phase 3 `build.py run` (or
   `record`) command and save what it prints (`build.py run ... > out/build.json`); it validates
   each part with that part's `expect` and the exact source list it hashed. To re-check one STL
   without rebuilding, call `validate.py` once per part:

   ```bash
   python3 "$SKILL_DIR/scripts/validate.py" out/body.stl --expect 71.2,37.8,33.6 \
     --printer .3dprint/printers.json --source model.scad lib.scad --params .3dprint/params.json
   ```

   `--expect` is one part's size, so one `validate.py` call per part. `--source` must list the
   same files the build hashed (`build.py` prints them as `sources`, includes and all); R3 names
   both lists when they differ. Editing only `_` keys in `params.json` does not make an STL stale,
   but some leave the build report old: a changed `_parts` object, role or clearance (Phase 3)
   or `_material` (below) needs a new build.
   Pass the same `--tools` the build had (`references/phase-2-printer-dimensions.md`, step 1).

   **After a rebuild, renew what went stale.** Evidence is tied to the STLs, parameters and
   material it was made from, so a rebuild that changed a part, a linked parameter or a material
   leaves it stale: run each fit of that part again (`fit.py`, the same command), each
   `strength.py --from-build` command of it (the same `--param` links) and each `measure.py
   --expect` on it; draw each preview that showed it again and ask the user to look again (a new
   `seen` entry with the new `image_sha256`; the old look is never copied onto it, nor recorded
   as `excluded` or `accepted`); a test print of it stands only after a new print.
   A changed `dims` value also changes the proxy built from it: build the proxy again, then its
   fit. A changed `_material` leaves the STLs fresh but the build's record old: build again,
   then run strength.py again. `finalize.py` names every stale item; run it (Phase 4) until none
   is left that you can renew. A promise it reports not verified for the first time now (added
   late, or made stale by a late change) is decided with the user as Phase 4 says ("Leaving
   Phase 4").
2. Decide the checks `validate.py` lists in `not_covered`: F3 with `fit.py` (one run per joint,
   both parts placed as assembled); F1, F2, R1, R2 and R4 yourself, each with evidence. F3
   counts only from a report about the STLs being delivered: `fit.py --check out/fit_box_lid.json`
   must say PASS (G1); STALE means a part was rebuilt since, so run that fit again. F3 is N/A
   for a `fused` part (a colour inlay, a label): A1 decides its contact. P6 is not in that
   list but is yours too, from the `preview.py` image, or from the generator and its log when
   the image cannot show the bed edge (`bb.bevel` with `bed=False`; the foot corrected one way,
   `references/tolerances.md`). finalize lists every soft check
   left to you as "UNVERIFIED (yours to decide)": P6, P4 (bridges) and P5 (small features),
   which no script checks, and P3 when the wall check was skipped. Decide each now, before the
   delivery, from the preview and the generator: one that holds needs nothing more; one that
   needs the user (supports under a bridge, a feature too thin to print) is a WARN they decide
   (step 3). The delivery message carries only what the user must know or do.
3. On a hard FAIL, go where its `return_to` says (the checklist table in SKILL.md), fix the
   cause, rebuild, re-validate. On a soft WARN, explain it and let the user choose (slicer
   supports, a redesign, or keeping it as it is). Accept it only on their agreement, recorded
   word for word as the `reason`; a reply that hands the decision back accepts nothing
   (`references/phase-4-features-joints.md`, "What counts as agreement"). Supports are the
   slicer's (set per object in step 4), never modelled into the part.
4. **Print settings.** Keep the user's slicer preset as the baseline and change only what this
   part needs, each change with a reason. Bambu Studio: read `references/bambu-process.md`, make
   a template if `printers.json` has none (a saved empty project first, generated from preset
   names as the fallback), and write the changes as per-object settings with `bambu3mf.py`
   (supports, support interface filament and Z distance, brim, walls, infill, ...).
   Any other slicer: give a three-line recipe (material, layer height, walls, infill, supports,
   orientation, and why). Record `_print.preset` if Phase 2 did not
   (`phase-2-printer-dimensions.md`, "Material and process preset").
5. **Declare the evidence** in `params.json` under `_verify`, for `finalize.py` in Phase 6. Most
   of it went in during Phase 4, as each report was saved; check that it is complete: the
   promises with their evidence, the real-world sizes they rest on (`dims`, Phase 2), every joint
   F3 covers with its saved report, every member's saved `strength.py --from-build` report, the
   measurements, the user's looks at preview images (`seen`), the test prints, each WARN the
   user accepted and each promise they took unverified (each with their reply to the question
   that named it as its `reason`). A list left out is reported as "not
   declared", which keeps its tier from being verified; an empty list says there is nothing of
   that kind. A worked example, the phone stand, and what finalize makes of it:
   `references/outputs.md`, "A worked `_verify`". Each key's fields: `references/checks.md`.
