# Tolerances and design limits (FDM, 0.4 mm nozzle)

Starting points, not truths. Values measured on the user's printer (`printers.json` → `tolerance`,
source `measured`) always win. Every value says whether it applies **per side (radial)** or **to the
diameter / total size**; mixing the two is a 2× error.

## Fits

| Fit | Per side (radial) | On the diameter or size | Use |
|---|---|---|---|
| Hole compensation (model-side) | +0.10 to +0.20 | +0.20 to +0.40 | Only when the slicer does not compensate holes (F1) |
| Sliding / removable | +0.20 | +0.40 | Lids, drawers, parts that must come apart by hand |
| Snug, no rattle | +0.15 | +0.30 | Stacked parts, alignment lips |
| Press fit | −0.05 to −0.10 | −0.10 to −0.20 | Pins and bosses meant to stay; test before committing |
| Object in a pocket | +0.30 | +0.60 | A device dropped into a holder; add +1.0 per side if it must lift out easily |

Material adjustments: PETG add +0.05 per side; TPU add +0.3 per side; ABS/ASA shrink about 0.5–0.7 %
(scale critical dimensions, or measure a test print).

## Compensation lives in one place (F1)

- Slicer compensates (Bambu Studio / OrcaSlicer "auto circle contour-hole compensation" on, or an
  XY hole compensation value set): model holes at nominal size.
- Slicer does not: add the hole compensation above in the model.
- Unknown (the user does not know their slicer or its settings): model holes at nominal size plus
  the fit clearance, and tell the user that tight holes mean the slicer's hole compensation should be
  turned on. A hole that comes out tight can be drilled; one that comes out loose cannot be fixed.
- The same holds for elephant foot: either the slicer's elephant-foot compensation or a 0.3–0.5 mm
  chamfer on bottom edges that must stay sharp, not both shrinking the first layer.

## Limits

| Feature | Minimum | Recommended |
|---|---|---|
| Wall | 1.2 mm | 1.6–2.0 mm structural; walls should be a multiple of the line width |
| Feature (pin, rib) | 0.8 mm | 1.2 mm |
| Hole | 2.0 mm diameter | Drill or ream holes that need precision |
| Embossed text | 0.6 mm high, 0.8 mm stroke | 1.0 mm high |
| Engraved text | 0.6 mm deep, 0.8 mm stroke | 1.0 mm deep |
| Overhang from vertical | 45° (PLA often 50°) | Chamfer instead of a horizontal ledge |
| Unsupported bridge | — | under 20 mm; ribs underneath shorten longer spans |
| Bottom edge | 0.3–0.5 mm chamfer | Chamfer, never a fillet (P6) |

## Threads and fasteners

- Printed threads: M6 and up. Below that, use heat-set inserts (hole size from the insert maker's
  datasheet) or self-tapping screws into an undersized hole.
- Snap-fit cantilevers: at least 1.2 mm thick, printed lying in the XY plane, never flexing across
  layer lines.

## Calibrate once

Print a coupon with holes and pegs stepping by 0.05 mm, measure with calipers, and store the
measured clearances in `printers.json` with `"source": "measured"`.
