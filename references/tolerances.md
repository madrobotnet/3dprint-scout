# Tolerances and design limits (FDM, 0.4 mm nozzle)

Starting points to calibrate, not truths, unless a source is named. Values measured on the user's
printer (`printers.json` → `tolerance`, source `measured`) always win. Every value says whether it
applies **per side (radial)** or **to the diameter / total size**; mixing the two is a 2× error.
This file is the only place for fit clearances; `design.md` links here instead of repeating them.

## Fits

| Fit | Per side (radial) | On the diameter or size | Use |
|---|---|---|---|
| Hole compensation (model-side) | +0.10 to +0.20 | +0.20 to +0.40 | Only when the slicer does not compensate holes (F1) |
| Sliding / removable | +0.20 | +0.40 | Lids, drawers, parts that must come apart by hand |
| Snug, no rattle | +0.15 | +0.30 | Stacked parts, alignment lips |
| Press fit | −0.05 to −0.10 | −0.10 to −0.20 | Pins and bosses meant to stay; test before committing |
| Object in a pocket | +0.30 | +0.60 | A device dropped into a holder; add +1.0 per side if it must lift out easily by its sides. A thin item standing in a slot (a card, a sheet) keeps +0.30: easy removal comes from the height left exposed or a finger notch |
| Snap-in cylinder (C-clip bore) | +0.15 | +0.30 | The snug row: the bore clearance sets only the rattle; the hold comes from the mouth undercut, sized by the strain rule (`design-features.md`, "Snap fits"). A start value: confirm with a test piece |
| Print-in-place joint (hinge, pivot, captive pin) | +0.30 (0.40–0.50 on a less tuned printer) | +0.60 (0.80–1.00) | Parts printed assembled that must move afterwards; Prusa KB ≥ 0.3 mm, Fictiv 0.4 mm for pivots, Hubs 0.5 mm (design.md sources 1, 2, 6) |

Material adjustments: PETG add +0.05 per side; TPU add +0.3 per side; ABS/ASA shrink about 0.5–0.7 %
(scale critical dimensions, or measure a test print).

## Compensation lives in one place (F1)

This is the decision table for every engine and phase. Fit clearance is intentional space
between mating parts; printer hole compensation is a separate correction, applied only once.
Convert per-side clearance to a diameter allowance by multiplying by two: a 10 mm pin with
0.20 mm clearance per side needs a 10.40 mm modeled hole before any model compensation.

| Settings the part will be printed with | `compensation.holes` | Model hole size |
|---|---|---|
| Circle compensation or XY hole compensation on | `slicer` | Nominal size plus the chosen fit clearance; no model compensation |
| Both corrections off, as read: the user's preset, or the Bambu project the skill delivers (a generated template has both off) | `model` | Nominal size plus fit clearance plus the radial hole compensation above (twice it on diameter) |
| Not known: STLs for a slicer or preset nobody has seen | `unknown` | Nominal size plus fit clearance only; record the uncertainty and recommend a fit test before changing compensation |

Apply this to every round hole that must fit, including bores. Pass `fit.py --min-clearance`
the clearance actually modeled, including any model compensation. A delivered Bambu Studio
project prints with the settings it carries (`phase-2-printer-dimensions.md`, step 4); a
system default says nothing about a preset the user picks for loose STLs.
- `fit_test.py` pieces carry no model compensation; say so. A step that fits is the clearance
  as printed without it: build the part's hole the same way (that step, nothing added), or add
  the compensation to the pieces' `--clearance` before printing them.
- For `unknown`, explain that a tight test print may need slicer hole compensation; inspect the
  active preset before enabling it so a second correction is not added unknowingly. A hole
  that comes out tight can be drilled; one that comes out loose cannot be fixed.
- Elephant foot is corrected in one place too (`elephant_foot` in `printers.json`): the
  slicer's elephant-foot compensation (`"slicer"`, on in Bambu's system presets) or a 0.3–0.5 mm
  chamfer on the bottom edges (`"model"`), not both. With the slicer's on, a bottom chamfer is
  for looks only: it is not the correction, so the edge stays sharp or takes a small chamfer
  for its look. Never a fillet (P6). A chamfer that belongs to a standard's profile (the foot of
  a bin that sits in a baseplate) is geometry, not an elephant-foot chamfer: keep it at its size
  whatever the slicer does.

## Limits

| Feature | Minimum | Recommended |
|---|---|---|
| Wall | 1.2 mm | 1.6–2.0 mm structural; walls should be a multiple of the line width (one 0.4 mm-nozzle perimeter is about 0.45 mm wide, Prusa KB) |
| Feature (pin, rib) | 0.8 mm | 1.2 mm |
| Hole | 2.0 mm diameter | Drill or ream holes that need precision |
| Embossed text | 0.6 mm high, 0.8 mm stroke | 1.0 mm high |
| Engraved text | 0.6 mm deep, 0.8 mm stroke | 1.0 mm deep |
| Overhang from vertical | 45° (PLA often 50°) | Chamfer instead of a horizontal ledge |
| Unsupported bridge | — | under 10 mm (Hubs design rules); under 5 mm it does not sag at all; ribs underneath shorten longer spans |
| Bottom edge | 0.3–0.5 mm chamfer, or sharp with the slicer's compensation (one of them, above) | Never a fillet (P6) |

## Threads and fasteners

- Printed threads: M6 and up. Below that, use heat-set inserts (hole size from the insert maker's
  datasheet) or self-tapping screws into an undersized hole. Hole tables, insert bosses, snap-fit
  formulas and strain limits: `design.md`.
- Snap-fit cantilevers: at least 1.2 mm thick, printed lying in the XY plane, never flexing across
  layer lines.

## Calibrate once

Print a coupon with holes and pegs stepping by 0.05 mm, measure with calipers, and store the
measured clearances in `printers.json` with `"source": "measured"`.
