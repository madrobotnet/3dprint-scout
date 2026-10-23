# Phase 5 — Gate and process tuning (review point)

Read this on entering Phase 5 (SKILL.md holds the checklist table and the rules that hold at
all times; `references/checks.md` describes `validate.py`'s JSON).

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
   both lists when they differ. Editing only `_` keys in `params.json` does not make an STL stale.
   Pass the same `--tools` the build had (`references/phase-2-printer-dimensions.md`, step 1).

   **After a rebuild, renew what went stale.** Evidence is tied to the STLs, parameters and
   material it was made from, so a rebuild that changed a part, a linked parameter or a material
   leaves it stale: run each fit of that part again (`fit.py`, the same command), each
   `strength.py --from-build` command of it and each `measure.py --expect` on it; draw each
   preview that showed it again and ask the user to look again (a new `seen` entry with the new
   `image_sha256`); a test print of it stands only after a new print. A changed `_material`
   leaves the STLs fresh but the build's record old: build again, then run strength.py again.
   `finalize.py` names every stale item; run it (Phase 4) until none is left that you can renew.
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
   orientation, and why). Record the process preset the user prints with as `_print.preset`
   (`{"_print": {"preset": "0.20mm Standard @BBL X2D"}}`), named as the slicer names it: test
   prints count only under it, and `finalize.py --deliver` compares a Bambu project's preset and
   filaments with it and with each part's material (Phase 6).
5. **Declare the evidence** in `params.json` under `_verify`, for `finalize.py` in Phase 6. Most
   of it went in during Phase 4, as each report was saved; check that it is complete: the
   promises with their evidence, the real-world sizes they rest on (`dims`, Phase 2), every joint
   F3 covers with its saved report, every member's saved `strength.py --from-build` report, the
   measurements, the user's looks at preview images (`seen`), the test prints, each WARN the
   user accepted and each promise they took unverified. A list left out is reported as "not
   declared": without `joints` or `strength` the geometry is not verified, and without promises
   (or with an empty list) the use tier is not declared. Otherwise an empty list says there is
   nothing of that kind. The phone stand:

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
        "source": "assumed", "tol": 0.5}
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

   finalize reads this as `use: excluded` (5 promises: 1 excluded, 1 assumed, 3 verified):
   `cable-bend` the user took unverified, and `cable-out` rests on `usb-c-plug`, which nobody
   measured. Which evidence each kind takes, and every state: `references/checks.md`.

   - `dims` on a joint, member or measurement names the sizes its numbers come from; a promise
     on it takes their state. A real-world size a promise rests on goes into `dims`;
     `unverified` holds only an estimated size no promise rests on (free text is linked to no
     promise).
   - `image_sha256` is copied from the image's sidecar (`out/preview.png.json`) when the user
     judges the image, a test print's part `sha256` from the build JSON of the files the user
     printed; never fill them in later from the files as they are then.
   - `covers` says in one line what the evidence covers; the report shows it next to the
     promise's conditions and success.
   - A joint fitted against a proxy gets `"proxy": true` with its `dims` and `proxy_build`
     (Phase 4); `finalize.py` then says the fit shows agreement with those numbers, not that
     they are right.
   - Test print status: `passed`, `failed`, `skipped`, `offered` or `pending`; a print without
     `promises` (a hinge coupon the user skipped, `fit_test.py` pieces) stays in the print tier.
   - An accepted WARN is `{"check": "<name>", "reason": "<the user's reason>"}`, named as
     `finalize.py` lists it in `open`: `<part> <check>` (`lid A2`), `object <name> <check>` (an
     object's D2 / P1 / P2), `joint <name> <check>` (a fit's WARN) or `member <name>` (a
     strength.py WARN). A FAIL cannot be accepted.
