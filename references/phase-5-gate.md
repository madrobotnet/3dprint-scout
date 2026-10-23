# Phase 5 — Gate and process tuning (review point)

Read this on entering Phase 5 (SKILL.md holds the checklist table and the rules that hold at
all times; `references/outputs.md` describes `validate.py`'s JSON, `references/checks.md` the `_verify` declarations).

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
   the image cannot show the bed edge: a `bb.bevel` with `bed=False` leaves it alone, and with
   no chamfer the preset's elephant-foot compensation covers it (0.15 mm in the X2D's
   `0.20mm Standard`, `phase-2-printer-dimensions.md`, step 4). finalize lists every soft check
   left to you as "UNVERIFIED (yours to decide)": P6, P4 (bridges) and P5 (small features),
   which no script checks, and P3 when the wall check was skipped. Decide each now, before the
   delivery, from the preview and the generator: one that holds needs nothing more; one that
   needs the user (supports under a bridge, a feature too thin to print) is a WARN they decide
   (step 3). The delivery message carries only what the user must know or do.
3. On a hard FAIL, go where its `return_to` says (the checklist table in SKILL.md), fix the
   cause, rebuild, re-validate. On a soft WARN, explain it and let the user choose (slicer
   supports, a redesign, or keeping it as it is). Accept it only on their agreement
   (`references/phase-4-features-joints.md`, "What counts as agreement"): a question that names
   the warning, says that it stays and what that can cost, and offers the choices, and a reply
   that takes keeping it, recorded word for word as the `reason`. A reply that hands the decision
   back to you ("I'm not sure, you decide") accepts nothing: fix it, or leave it unaccepted (it
   stays in `open` and is named at delivery), with an `_assumptions` line saying so (`"cap P3:
   the user handed the decision to me; not accepted"`).
   Never model support structures into the part: overhangs get the slicer's supports (set per
   object in step 4) or a redesign such as a chamfer or teardrop.
4. **Print settings.** Keep the user's slicer preset as the baseline and change only what this
   part needs, each change with a reason. Bambu Studio: read `references/bambu-process.md`, make
   a template if `printers.json` has none (a saved empty project first, generated from preset
   names as the fallback), and write the changes as per-object settings with `bambu3mf.py`
   (supports, support interface filament and Z distance, brim, walls, infill, ...).
   Any other slicer: give a three-line recipe (material, layer height, walls, infill, supports,
   orientation, and why). Record the process preset the user prints with as `_print.preset`
   if Phase 2 did not (`phase-2-printer-dimensions.md`, "Material and process preset"): test
   prints count only under it, and `finalize.py --deliver` compares a Bambu project's preset and
   filaments with it and with each part's material (Phase 6).
5. **Declare the evidence** in `params.json` under `_verify`, for `finalize.py` in Phase 6. Most
   of it went in during Phase 4, as each report was saved; check that it is complete: the
   promises with their evidence, the real-world sizes they rest on (`dims`, Phase 2), every joint
   F3 covers with its saved report, every member's saved `strength.py --from-build` report, the
   measurements, the user's looks at preview images (`seen`), the test prints, each WARN the
   user accepted and each promise they took unverified (each with their reply to the question
   that named it as its `reason`). A list left out is reported as "not
   declared", which keeps its tier from being verified; an empty list says there is nothing of
   that kind. The phone stand:

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
   sled in. Each key's fields, the test prints' among them: `references/checks.md`, "The `_verify`
   declarations"; which evidence each kind takes, and every state: the same file.
