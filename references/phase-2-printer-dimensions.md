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
`tools` (one area and height per nozzle), `compensation` (`holes`: `slicer`, `model` or `unknown`;
`elephant_foot`: `slicer`, `model` or `unknown`) and `tolerance` with its `source`. `default` names the printer the scripts use; with
exactly one printer it may be omitted, with several pass `--printer-id`. A bed without
`height` leaves D2 UNVERIFIED. Answers come as SKILL.md says (request, conversation, saved
settings); write the file from confirmed answers without asking again because it was missing.
When both answers are missing, ask in plain words: "Which printer do you have, and which program
do you open print files in? It's fine if you don't know the program." The printer sets the bed
and nozzles; the program (the slicer) sets the output file (Phase 6) and who compensates holes.
One brand can go with several slicers: if only the slicer is unknown, ask only that, never infer
it from the brand. Many users do not know the word "slicer"; never make them feel they should.
For a Bambu Lab printer the same message may ask for the Bambu Studio version, as optional
(`references/bambu-process.md`, `--app-version`).

**Defaults when an answer is missing or unclear** (record each one in `_assumptions`). A question
you asked waits for its answer; its fallback applies once the user says they do not know or asks
you to choose. Nozzle and material take their defaults without a new question.

- Slicer unknown, Bambu Lab printer → Bambu Studio (Bambu Lab's own slicer).
- Slicer unknown, any other printer → `unknown`: deliver STL plus core 3MF, which every slicer opens.
- Hole compensation unknown → use the `unknown` row of `tolerances.md`, "Compensation lives in
  one place"; record the uncertainty. Do not treat unknown as confirmed off.
- Nozzle 0.4 mm, material PLA (`pla_basic`; "Material and process preset" below).
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
- With several saved printers, ask which one in a single line only if the user has not already
  selected one for this project.

**Material and process preset.** Record both in `.3dprint/params.json` before the first build:
the build records each part's material, `strength.py --from-build` takes it from there, and
test prints and the delivered print file are compared with it (`references/checks.md`).

- `_material`: the filament the user prints with, as a `strength.py` material key (`pla_basic`
  for PLA; any other from the table in `references/materials.md`). A part printed in another gets its
  own: `"_parts": {"latch": {"expect": [12, 6, 4], "material": "petg_basic"}}`. Ask only when
  the material matters (a member carries load, the part sits in a car or in the sun), in plain
  words: "Which filament will you print it in? PLA is fine if you're not sure." When the user
  does not say (not asked, or not sure): `pla_basic`, and "material: PLA (pla_basic), not said
  by the user" in `_assumptions`. A filament the table does not have (another maker's PLA): the
  nearest key, and say in `_assumptions` that the strength numbers are Bambu's.
- `_print.preset`: the slicer's process preset the user prints with, by its name in the slicer:
  `"_print": {"preset": "0.20mm Standard @BBL X2D"}`. A saved Bambu Studio template names it
  (`references/bambu-process.md`), and a generated one names the printer's default. Otherwise ask
  only when a test print will back a promise, in plain words: "When you print, do you keep the
  default quality setting (such as 0.20mm Standard) or pick another?" Unknown: leave the key
  out; a test print then verifies only against the preset of a delivered Bambu project, and
  stays `assumed` without one.

## 2. Purpose and the use list

Decorative, general, or load-bearing. Default: general, recorded in `_assumptions` when the user
did not say.

Then make the **use list** with the user: what they will do with the part, under which
conditions, and what counts as success. Start from the request and the chosen concept's
promises, propose the list in plain words and let the user correct it; never ask them to write
it, or make them feel they should know this file's words. For a phone stand: "Here is what the
stand should let you do: stand the phone in its case upright; plug in a right-angle charging
cable while it stands, the cable leaving at the back. Anything to add or change?" Ask only about
the conditions that change the design (a case on or off, upright or sideways, how often it opens).

Each thing they will do is a `use` promise in `_verify.promises` with `conditions` and
`success`; complete the concept's promises the same way (`references/phase-1-references.md`,
"Promises"). Write `success` as something a check or a print can show, a size, a clearance, a
load held, never "works well":

```json
{"id": "cable-out", "kind": "use",
 "text": "a right-angle USB-C cable plugs in and leaves at the back",
 "conditions": "phone in its case on the seat, right-angle plug, cable to the back",
 "success": "plug head and cable clear the stand by 0.5 mm or more"}
```

`fit.py` checks a placed pose and a declared turn, not a path by hand or a cable that bends.
A use that needs one (sliding the phone in, a cable bent around a corner) needs a test print
among its evidence, since a fit report alone does not show it: say so when you write it, so the
user knows a print will decide it. finalize cannot tell such a use from others and
verifies it on its fits alone (an evidence item may name only a print already recorded), so
until the user's print is recorded (`references/checks.md`, "Test prints"), say at delivery
that the fit was checked and the motion was not. A promise that rests on a size no evidence will name lists
that dims id in `assumes` (below).

Unattended runs write the use list from the request alone and say in `_assumptions` that the
user did not confirm it.

## 3. Real-world dimensions

For anything the part must fit (ports, PCBs, screws, a device it wraps).
Two priorities. The size of the object: the user's caliper measurement > the official spec >
secondary sources (two that agree). How this printer prints (clearances, holes, members that
held): the user's calibration log > the starting points in `references/`. Record the source
as a comment next to the parameter. Read `.3dprint/calibration.json` first when it exists
(`calibration.py lookup` with `--nozzle`, and `--layer`, `--orientation`, `--process` when
known; `references/calibration.md`): a clearance that fit on this printer under the same
conditions beats every table. An entry printed under other conditions (`reference`, with
`differs`) is a reference only, never a setting or a floor; values that `worked` takes from
different prints (`combined`) were never printed together, so a combination starts from
`worked_set` or is marked unverified. A file the user supplies (a manufacturer's kit 3MF, a
reference model) is measured with `measure.py` (`references/measure.md`): interface numbers
only, never its geometry (licences); an official file counts as "official file, measured",
another maker's model as a secondary source. Dimension research has its own cap, about six page
fetches (Phase 1's counts only the reference table); past it, ask, or record the best value you
have as not measured (`assumed`, below).

**Published standards** (a bin system, a rail, a connector): a spec or drawing published by the
standard's owner counts as the official spec. Numbers read from a spec, a drawing or published
constants are sourced dimensions: record where each came from (R2). A standard defined by a
reference model rather than a drawing (Gridfinity, for one): offer the user to supply that file
for `measure.py` (numbers only). A value found in a single secondary source, or one two
independent sources share while another disagrees, was not measured: `assumed`, with its sources
(below). If none agree and the part must mate, ask, or offer a fit test (Phase 4).

**The sizes a promise rests on** (`_verify.dims`). Every real object the part must fit or hold
(the phone in its case, a USB-C plug, a cable, a screw) gets an entry: `id`, `what` (the object
and its sizes, in words), `unit`, `params` (the params.json keys the model is built from, with
their values), `source`, and `tol` when known (how far the real object may vary; recorded, not
applied to the fits). The keys must be engine parameters in params.json itself (not `_` keys,
not only a default in the generator), and the values must be the same numbers: `finalize.py`
compares them. Write such a size here even when nobody measured it, never as a sentence in
`_assumptions` or `_verify.unverified`: a sentence cannot be tied to a promise.
`_verify.unverified` holds only estimated sizes no promise rests on. For a phone stand with a
cable notch:

```json
{"phone_w": 78.5, "phone_t": 15.0, "plug_w": 13, "plug_h": 8, "plug_l": 9, "cable_d": 4.5,
 "_verify": {"dims": [
   {"id": "phone-case", "what": "the phone in its case: width and thickness", "unit": "mm",
    "params": {"phone_w": 78.5, "phone_t": 15.0}, "source": "caliper", "by": "user", "tol": 0.2},
   {"id": "usb-c-plug", "what": "right-angle USB-C plug head and its cable", "unit": "mm",
    "params": {"plug_w": 13, "plug_h": 8, "plug_l": 9, "cable_d": 4.5}, "source": "assumed",
    "tol": 0.5, "note": "a typical right-angle plug; the user has none at hand"}
 ]}}
```

- `caliper`: the user measured the object (calipers, or a ruler with a larger `tol`), with
  `"by": "user"`. Never write it for a number you found or chose: only the user measures.
- `spec`: the official spec or drawing, with its `url` and, for each parameter, the place of its
  number in it (`"where": {"phone_t": "Tech Specs, Size and Weight: Depth"}`). `finalize.py`
  reads no web page: it lists the URL and the places for the user to check.
- `user-file`: measured on a file the user gave (a maker's model of the plug, a scan). `from`
  names, for each parameter, its saved `measure.py --expect` report in `_verify.measurements`
  (one report per parameter, one `=` expectation), and `tol` is how far the measured value may
  differ: `"from": {"plug_w": "plug head width"}, "tol": 0.2` (`references/measure.md`). Keep
  the file inside the project folder (`ref/plug.stl`): `finalize.py --bundle` copies it and
  refuses one outside.
- `assumed`: everything else: a typical size, a value from secondary sources (two that agree
  are still `assumed`), a guess. Say where the number came from in `note` (the links, "a
  typical right-angle plug").

A promise rests on the dims its evidence names (a proxy joint names the dims it is built from,
`references/measure.md`) and on its own `assumes`. One that rests on an `assumed` size is
`assumed` at delivery, never verified.

**Ask the user to measure** what the part must fit whenever they have the object, in plain
words: "Could you measure the plug with a ruler or calipers? The width and thickness of the
plug head, and how far it sticks out." When they cannot (no tool, the object is elsewhere),
take the best source you have as `assumed`, offer a test print of that fit (`fit_test.py`
pieces, a few grams, Phase 4), and say it in one line: "I assumed the plug head is 13 × 8 mm,
and the cable notch rests on that; a small test piece would confirm it." Unattended runs cannot
ask: SKILL.md, "Unattended runs", says when a size stops the run.

When a measurement arrives later, change `source` and the value together in the dims entry,
params.json and any proxy's own params file (with `"by": "user"` for a caliper value). A new
value changes the model: build the part and the proxy again, then run again every check that
rests on it (finalize names each stale one). A value equal to the assumed one changes only the
source and leaves the reports standing.

**Members that carry load** (pins, knuckles, links, levers, hooks, brackets, handles): when a
proven reference's file is at hand (supplied by the user, or their own earlier project that
works), measure its corresponding members with `measure.py` and put them in the table next to
ours as a "reference member" note. The field-test latch, beside the user's own working latch,
would have shown up with half the member thickness and a sixth of the material.

## 4. Compensation lives in one place

Use the `slicer / model / unknown` table in `references/tolerances.md`, and write the state into
the printer's entry in `printers.json`: `compensation.holes` and `compensation.elephant_foot`,
added when missing (the other fields stay as they are), with the reason in
`compensation.source`. What counts is the setting the part will be printed with: a Bambu project
the skill delivers carries its settings, so a generated template means holes `"model"` and
elephant foot `"slicer"` (`references/bambu-process.md`, "Constraints"); STLs sliced with a
preset nobody has seen stay `"unknown"`.

## 5. Show the use list and the parameter table, and stop

First the use list: each promise in one line in the user's words, with what counts as success
and, when it rests on a size nobody measured, that size ("rests on the plug size, assumed").
Then the table:

| Parameter | Value | Source |
|---|---|---|

The source of a size a promise rests on is its dims source in plain words (measured by you,
from the spec with its link, assumed). The material and the print setting are rows too, marked
assumed when the user did not say. Include the bed margin (usable area minus footprint).
If it is negative, say so now.
Reuse unchanged dimensions the user already confirmed; stop for new or changed design choices
and unresolved dimensions that matter. A new derived dimension or assumption is not approved
merely because some other dimensions were supplied.
