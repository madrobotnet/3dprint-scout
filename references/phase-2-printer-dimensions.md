# Phase 2 — Printer, purpose, dimensions (STOP)

Read this on entering Phase 2 (SKILL.md names the rules that hold at all times).

## 1. Printer

Read `.3dprint/printers.json`. It is an envelope, not a flat profile:

```json
{"schema": "3dprint.printers/1", "default": "x2d",
 "printers": {"x2d": {"process": "fdm", "slicer": {"name": "bambu-studio"},
                      "bed": {"area": [[0,0],[256,0],[256,256],[0,256]], "height": 261,
                              "exclude": [], "source": "slicer-profile"}}}}
```

Per printer: `process` (`fdm`), `slicer` (`name`, and for Bambu Studio `template_3mf`,
`template_kind`), `bed` (`area` polygon in mm, `height`, `exclude` zones, `source`), optional
`tools` (one area and height per nozzle), `compensation` (`holes`, `elephant_foot`: `slicer` or
`model`) and `tolerance` with its `source`. `default` names the printer the scripts use; with
exactly one printer it may be omitted, with several pass `--printer-id`. A bed without
`height` leaves D2 UNVERIFIED. If the file is missing, **always ask; never skip this question**, in
plain words: "Which printer do you have, and which program do you open print files in? It's fine
if you don't know the program." Both answers change the result: the printer sets the bed and
nozzles, and the program (the slicer) sets the output file (Phase 6) and who compensates holes.
One printer brand can be paired with several slicers, so ask even when the printer seems to
imply it. Many users do not know the word "slicer"; never make them feel they should.
For a Bambu Lab printer the same message may ask for the Bambu Studio version, as optional
("Help > About; fine if you do not know"): a generated template must not be newer than the app
(`references/bambu-process.md`). Unknown, attended or not: use the version of the profiles you
read, say so, and record it in `_assumptions`.

**Defaults when an answer is missing or unclear** (record each one in `_assumptions`):

- Slicer unknown, Bambu Lab printer → Bambu Studio (Bambu Lab's own slicer).
- Slicer unknown, any other printer → `unknown`: deliver STL plus core 3MF, which every slicer opens.
- Hole compensation unknown → model holes at nominal size plus the fit clearance, and tell the
  user that tight holes mean their slicer's hole compensation should be turned on.
- Nozzle 0.4 mm, material PLA.
- Printer unknown → no bed size is assumed; D2 stays UNVERIFIED and the report says so.
- Printer named → read its bed in this order: the user's installed slicer profiles (read-only;
  resolve `inherits`, child values win, strip stray whitespace; Bambu Studio's data folder and
  its `system` subfolder are named in `references/bambu-process.md`) → the manufacturer's spec
  page → the slicer's public profiles at the tag of the user's version → numbers from the user.
  Never a reseller page, a review or a news article: they round, mix models and go stale.
  Save every block with its `source`, and save `slicer.name`.
- Bambu Studio and the user has the app open → suggest once, in one line, saving an empty
  project as the template (it keeps their process tweaks and AMS set); the generated template
  is the fallback (`references/bambu-process.md`).
- Usable area is the **intersection** of the areas of the nozzles this print uses. `build.py` and
  `validate.py` take them as `--tools` (indices into `tools`; without it, tool 0). An object
  with several parts, so any object with several filaments, is checked against every nozzle's
  intersection automatically. For a single-filament print on a printer with two nozzles (X2D,
  H2D), pass the nozzle the user prints with, or `--tools 0,1` when that is not known (or when
  separate objects use both); give both scripts the same `--tools`.
- Never store access codes, serial numbers, or IP addresses.
- FDM only. For resin, say so and stop.
- With several saved printers, ask which one in a single line.

## 2. Purpose

Decorative, general, or load-bearing. Default: general.

## 3. Real-world dimensions

For anything the part must fit (ports, PCBs, screws, a device it wraps).
Two priorities. The size of the object: the user's caliper measurement > the official spec >
secondary sources (two that agree). How this printer prints (clearances, holes, members that
held): the user's calibration log > the starting points in `references/`. Record the source
as a comment next to the parameter. Read `.3dprint/calibration.json` first when it exists
(`calibration.py lookup`, `references/calibration.md`): a clearance that fit on this printer
beats every table. A file the user supplies (a manufacturer's kit 3MF, a reference model) is
measured with `measure.py` (`references/measure.md`): interface numbers only, never its
geometry (licences); an official file counts as "official file, measured", another maker's
model as a secondary source. Dimension research has its own cap, about six page fetches (Phase
1's counts only the reference table); past it, ask or mark the value unverified.

**Published standards** (a bin system, a rail, a connector): a spec or drawing published by the
standard's owner counts as the official spec. Numbers read from a spec, a drawing or published
constants are sourced dimensions: record where each came from (R2). A standard defined by a
reference model rather than a drawing (Gridfinity, for one): offer the user to supply that file
for `measure.py` (numbers only). A value found in a single source is recorded and reported as
unverified. When secondary sources disagree, use the value two independent sources share, note
the other, and mark it unverified; if none agree and the part must mate, ask, or offer a fit
test (Phase 4).

**Members that carry load** (pins, knuckles, links, levers, hooks, brackets, handles): when a
proven reference's file is at hand (supplied by the user, or their own earlier project that
works), measure its corresponding members with `measure.py` and put them in the table next to
ours as a "reference member" note. The field-test latch, beside the user's own working latch,
would have shown up with half the member thickness and a sixth of the material.

## 4. Compensation lives in one place

If the slicer is Bambu Studio or OrcaSlicer with circle compensation on, model holes at nominal
size and record `compensation.holes = "slicer"`. Otherwise add the radial compensation from
`references/tolerances.md` in the model, on every round hole the part must fit, bores too.

Bambu's system process presets ship with it off: the X2D's `0.20mm Standard` inherits
`enable_circle_compensation` 0 and `xy_hole_compensation` 0 from `fdm_process_common` (public
profiles 02.08.02.61). So with a generated template, or a saved one that shows them off, record
`"model"`; `"slicer"` only when the user's preset has one of them on. The same preset's
elephant-foot compensation is 0.15 mm (`fdm_process_dual_0.20_nozzle_0.4`): `elephant_foot` is
`"slicer"` there.

## 5. Show the parameter table and stop

| Parameter | Value | Source |
|---|---|---|

Include the bed margin (usable area minus footprint). If it is negative, say so now.
