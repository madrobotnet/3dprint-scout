# Mechanisms: print-in-place joints and members that carry load

Read this when the part has a mechanism: a hinge, pivot, latch, lever, clamp, pin, link or any
member a hand pushes, pulls, pinches or snaps (Phase 3 for its size, Phase 4 for its checks). The
general patterns (bed edge, overhangs, walls, orientation, seams) are in `design.md`; fit
clearances in `tolerances.md`; loads and materials in `materials.md`.

## Print-in-place joints

- Clearance 0.3 mm per side between moving surfaces, 0.4–0.5 mm on a less tuned printer
  (`tolerances.md`, print-in-place row) [1][2][6]. Model the moving piece as its own part
  with `role: free` so `build.py` measures the gap (A2) and the slicer keeps it a part.
- A horizontal pin prints as a teardrop or diamond so its top is self-supporting; the first
  layer of the upper part bridges the gap, so keep gaps a whole number of layer heights (0.2
  or 0.4 mm at 0.2 mm layers) where a surface sits above another (starting point).
- Knuckles get a flat on the bed side; the leaf plates lie flat. `parts.hinge(..., duty=)`
  builds such a hinge to the floors of its duty (below: `latch`, `lid`, `decorative`);
  validate it with `--shells 2` (two bodies that never touch).
- **The mechanism must not silently grow the object.** For a hinge on a box, the dimension
  table lists the knuckle Ø and how far the hinge, with any gusset under it, stands proud
  of the wall, next to the box's depth, and the concept preview shows the hinge. When a
  mechanism's duty floors would make the main object bigger than the user's sizes, or the
  mechanism stands out of proportion to it, stop and give the choices instead of resizing:
  the right duty (a lid hinge sized by `strength.py hinge` and a coupon print, not by the
  latch minimums), knuckles set partly into notches in the walls so less stands proud, a
  different closure (a slide-on or snap-on lid), or a bigger object that the user chooses.
  (Field test, 2026-10: a 16.4 mm-deep SD-card case got a lid hinge 10.1 mm proud of the
  wall from the latch minimums, and the box was enlarged to suit the hinge.)
- After the print, free the joint with a few firm twists before the parts cool completely
  (PLA is still soft) — tell the user.

## Mechanisms that carry load

P3's 1.2 mm is a **printability** minimum, not a strength minimum. A latch, lever, pin,
knuckle or link that is pushed, pulled or snapped by hand sees far more than a wall does.
The rule depends on the member's **duty** (one copy of the numbers: `strength.DUTIES`,
`strength.py duties`; `parts.hinge(duty=)` refuses thinner values):

- **`latch`** (the default): anything a hand pushes, pulls, pinches or snaps to operate, or
  that a lever amplifies: latches, catches, levers, clamps, a latch's pivot pin, a hinge
  whose leaf is used as a lever. The field minimums below apply. Load case: the hand-force
  key that matches how it is operated (push, pull, pinch) × the lever ratio where a lever
  multiplies it (`materials.md`).
- **`lid`**: a lid, door or flap hinge with alternating knuckles (3 or more, required; an odd
  count is recommended, so every moving knuckle sits between two fixed ones) where the hand
  force reaches the pin without a lever multiplying it. Its pin is shared over several shear
  planes and nothing amplifies the pull, so the latch minimums do not apply; the floors are
  only what prints (pin 2.0, wall and leaf 1.2, knuckle 2 mm, `tolerances.md`) and the size
  comes from `strength.py hinge` reaching **SF ≥ 2** at the load case below: at WARN grow the
  pin or the knuckle Ø or add knuckles (odd), never print instead. A **hinge coupon print is
  required** on top of that margin before the full part (`parts.md`, "Printing the mechanism
  first"); it never replaces the margin, and a skipped one goes into `_assumptions` and is
  said at delivery, as for a fit test. Load case: the abuse case of pulling the open lid away
  from the box, `finger_pull` (98 N) at the hinge, shared equally by the moving knuckles, no
  lever ratio; the axis prints flat and the pull turns with the lid, so the load is taken to
  cross the layers. Levering a lid backwards past its stop multiplies the force by (the
  finger's distance from the axis / the stop's distance from the axis) and is misuse a
  print-in-place hinge is not sized for: record "don't force the lid past fully open" in
  `_assumptions` (Phase 6 repeats it at delivery) instead of growing the hinge. A stop the
  user is meant to push against makes it a latch-duty case with that ratio.
- **`decorative`**: carries nothing; the same floors as `lid`, no calculation (the floors alone
  decide P7).

Record the load case, the share and the ratio in `_assumptions`. The user's own results in
the calibration log set their own floors, per kind of member (`calibration.md`).

**Latch-duty minimums**, starting points for members a hand operates (field comparison,
2026-10, one failed and one working print-in-place latch, both PLA, 0.4 mm nozzle, 0.2 mm
layers; starting points, not a standard):

- **Pins** Ø ≥ 3.2 mm; one **through pin supported at both ends** (double shear) rather than
  short stub pins in thin plates; engagement length ≥ about 3 × Ø where the design allows.
- **Wall around a pin hole** ≥ 2.2 mm (about five 0.45 mm lines) all round, including
  towards the bed.
- **Arms, links, levers, hooks** ≥ 2.5 mm in the bending direction and ≥ 4 mm wide; a
  curved 1.2 mm link is a hinge, not a member.
- **Knuckles** ≥ 4 mm long.
- **Radial clearance** 0.3–0.35 mm at the pin (`tolerances.md`); the failed latch's 0.42 mm
  did not help it.
- Flexures designed by the strain formula (snap hooks, living hinges) are exempt: they follow
  the snap-fit check (`design-features.md`, "Snap fits"). Their roots still must not double as the wall of a pin hole.

| Member | Failed latch (broke on first use) | Working latch |
|---|---|---|
| Pin | Ø2.6 stub pins, single-ended, in ~2 mm plates | one Ø3.2 through pin formed on the lever, both ends in 4.25 mm rails |
| Hole and clearance | Ø3.45 teardrop, ~0.42 mm radial | Ø3.9, ~0.33 mm radial |
| Wall around the pin | ~1.3 mm (knuckle ring OD 6.0) | ≥ 2.2 mm (2.4 mm to the bed), block 8.3 × 10.8 × 18.4 |
| Load-carrying arms | two, 1.2 × ~2.2 mm, curved (2.5 mm bow) | rails 4.25 wide, 2.5 mm at the thinnest notch, 3.6–7.4 elsewhere |
| Bars | 1.7 × 2.6 (12 mm long) and 2.2 × 2.4 mm | lever plate 20 × 2.6 mm at its thinnest |
| Lever ratio | not measured | not measured |
| Material per latch | ~640 mm³ | ~3 820 mm³ (about 6×) |

The agent checks every load-carrying member against the floors of its duty in the dimension
table (checklist P7), the same way it checks walls against P3, in three steps: compare with
the corresponding member of a proven reference when its file is at hand (SKILL.md, Phase 2);
run `strength.py` on it with a cited load and the data-sheet values (`materials.md`; the
`hinge` case for a hinge with alternating knuckles); and when the margin is short, there is
no reference, or the duty is `lid`, print the mechanism alone first (`parts.md`, "Printing
the mechanism first"). The user's own results go into the calibration log
(`calibration.md`) and beat every table here. `parts.hinge(duty="latch")`, the default,
refuses a pin wall under 2.2 mm (measured above the teardrop's point, which reaches
(r + clearance) × √2 above the axis, so a 3.2 mm pin needs a 9.8 mm knuckle), a leaf under
2.5 mm or a knuckle under 4 mm; `duty="lid"` and `duty="decorative"` (the old
`decorative=True`) refuse only what does not print.

## Sources

Numbered as in `design.md`.

1. Prusa Knowledge Base, "Modeling with 3D printing in mind" — perimeter widths, overhang
   angles, chamfer vs fillet, movable parts ≥ 0.3 mm, splitting parts.
   https://help.prusa3d.com/en/article/modeling-with-3d-printing-in-mind_164135/
2. Hubs, "How to design parts for FDM 3D printing" — 45°, bridges under 5 mm, pins under
   5 mm, chamfer the bed edge, drill holes.
   https://www.hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/
6. Fictiv, "How to design snap fit components" — strain formula with Q, printed break strains
   (PLA 4–8 %, ABS 7 %, nylon 4–15 %), Z-built cantilevers at half strain (tensile −20–30 %,
   elongation −50 %), clearances 0.2–0.4 mm, root radius.
   https://www.fictiv.com/articles/how-to-design-snap-fit-components
