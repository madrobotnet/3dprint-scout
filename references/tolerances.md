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
| Snap-in cylinder (C-clip bore) | +0.15 | +0.30 | The snug row: the bore clearance sets only the rattle; the hold comes from the mouth undercut, sized by the strain rule (`design.md`, "Snap fits"). A start value: confirm with a test piece |
| Print-in-place joint (hinge, pivot, captive pin) | +0.30 (0.40–0.50 on a less tuned printer) | +0.60 (0.80–1.00) | Parts printed assembled that must move afterwards; Prusa KB ≥ 0.3 mm, Fictiv 0.4 mm for pivots, Hubs 0.5 mm (design.md sources 1, 2, 6) |

Material adjustments: PETG add +0.05 per side; TPU add +0.3 per side; ABS/ASA shrink about 0.5–0.7 %
(scale critical dimensions, or measure a test print).

## Compensation lives in one place (F1)

- Slicer compensates (Bambu Studio / OrcaSlicer "auto circle contour-hole compensation" on, or an
  XY hole compensation value set): model holes at nominal size. Bambu's system process presets
  have both off (`phase-2-printer-dimensions.md`, step 4).
- Slicer does not: add the hole compensation above in the model, to every round hole the part
  must fit, bores included, not only screw holes. Pass `fit.py --min-clearance` the clearance
  the model is built with, compensation included.
- `fit_test.py` pieces carry no model compensation; say so. A step that fits is the clearance
  as printed without it: build the part's hole the same way (that step, nothing added), or add
  the compensation to the pieces' `--clearance` before printing them.
- Unknown (the user does not know their slicer or its settings): model holes at nominal size plus
  the fit clearance, and tell the user that tight holes mean the slicer's hole compensation should be
  turned on. A hole that comes out tight can be drilled; one that comes out loose cannot be fixed.
- The same holds for elephant foot: either the slicer's elephant-foot compensation or a 0.3–0.5 mm
  chamfer on bottom edges that must stay sharp, not both shrinking the first layer. A chamfer
  that belongs to a standard's profile (the foot of a bin that sits in a baseplate) is geometry,
  not an elephant-foot chamfer: keep it at its size whatever the slicer does.

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
| Bottom edge | 0.3–0.5 mm chamfer | Chamfer, never a fillet (P6) |

## Threads and fasteners

- Printed threads: M6 and up. Below that, use heat-set inserts (hole size from the insert maker's
  datasheet) or self-tapping screws into an undersized hole. Hole tables, insert bosses, snap-fit
  formulas and strain limits: `design.md`.
- Snap-fit cantilevers: at least 1.2 mm thick, printed lying in the XY plane, never flexing across
  layer lines.

## Calibrate once

Print a coupon with holes and pegs stepping by 0.05 mm, measure with calipers, and store the
measured clearances in `printers.json` with `"source": "measured"`.
