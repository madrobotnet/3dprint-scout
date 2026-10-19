# Designing for FDM printing

Read this in Phase 3 (base shape) and again in Phase 4 (features). Patterns to apply while
modelling, with the numbers that back them. Fit clearances live in `tolerances.md` and are only
linked from here. Numbers without a source are **starting points: calibrate** on the user's
printer (a 0.4 mm nozzle and PLA are assumed: SKILL.md Phase 2 defaults,
`phase-2-printer-dimensions.md`). `scripts/parts.py` builds most of these shapes with these
defaults.

Contents:

- [Bed edge: chamfer, never a fillet](#bed-edge-chamfer-never-a-fillet)
- [Overhangs and self-supporting shapes](#overhangs-and-self-supporting-shapes)
- [Walls and small features in nozzle multiples](#walls-and-small-features-in-nozzle-multiples)
- [Orientation for strength](#orientation-for-strength)
- [Snap fits (cantilever)](#snap-fits-cantilever)
- [Screws, inserts and threads](#screws-inserts-and-threads)
- [Print-in-place joints](#print-in-place-joints)
- [Mechanisms that carry load](#mechanisms-that-carry-load)
- [Colour and function seams: split into parts](#colour-and-function-seams-split-into-parts)
- [Text, logos, cosmetic faces](#text-logos-cosmetic-faces)
- [Supports policy](#supports-policy)
- [Sources](#sources)

## Bed edge: chamfer, never a fillet

- The first layer squashes outwards (elephant foot). A fillet on the bed edge is an overhang
  that prints rough; a 45° chamfer prints clean and hides the foot [1][2]. Leg 0.3–0.5 mm
  (`tolerances.md`, Limits). Either this chamfer or the slicer's elephant-foot compensation,
  not both (F1 in `tolerances.md`). `parts.chamfered_box(..., "bottom")`,
  `parts.bottom_chamfer(part, 0.4)`.
- A 45° chamfer under any ledge, boss foot or lip (`parts.standoff(..., foot=1.0)`) removes
  the overhang; a fillet does not.

## Overhangs and self-supporting shapes

- **45° from vertical** prints without support on most printers; 50–60° on well-cooled ones,
  up to 75° on 360° cooling [1][3]. The validator's P2 uses 45° unless `--overhang-angle` says
  otherwise. Design to 45°; let the user's printer surprise them, not the other way round.
- A horizontal ceiling inside a part is a bridge; a sloped one (45° roof, like a gabled house)
  is not. Pockets open to the top, not to the side.
- **Horizontal holes**: round holes have a flat ceiling that sags. Use a **teardrop** (circle
  plus a 45° point on top; apex at r·√2 above the centre) or a diamond, or turn the part so the
  hole is vertical [4][2]. `parts.teardrop_hole(d, length, axis)`.
- **Bridges**: keep spans under 10 mm; under 5 mm they do not sag at all [2][5]. Ribs or a
  centre pillar cut a long span in two. Limits in `tolerances.md`.
- Lids and caps print open side up, flat face on the bed; a flat face against the bed comes
  out smoothest [1] and needs no support.

## Walls and small features in nozzle multiples

- One perimeter of a 0.4 mm nozzle is about 0.45 mm wide; 2, 3, 4 perimeters are about 0.9,
  1.35, 1.8 mm. Walls thinner than one perimeter do not print, and walls between one and two
  perimeters print badly [1]. Design walls as a whole number of lines: 1.2 mm minimum,
  1.6–2.0 mm for anything structural (`tolerances.md`). Avoid 1.0 mm (two lines plus a gap the
  slicer cannot fill).
- Free-standing pins under 5 mm are weak; give them a fillet or chamfer at the base, or use a
  metal pin for anything that must not snap off [2]. Printed pins and ribs: 0.8 mm minimum,
  1.2 mm recommended (`tolerances.md`).
- Vertical holes: 2 mm minimum; print undersize and drill when the size matters [2][5].
- Floors: 3–4 layers minimum (0.6–0.8 mm at 0.2 mm layers) so infill does not show through
  (starting point).

## Orientation for strength

- A print is weakest across its layers: tensile strength along Z is 20–30 % lower and
  elongation at break about half [6]; badly bonded layers can lose far more [7]. Plan with Z
  strength at **half** of XY (starting point) and design so that bending and tension run
  **within** layers, not across them:
  - snap arms, clips and living hinges lie flat on the bed and flex sideways;
  - a hook or bracket prints so the load path follows the layers (a wall hook prints on its
    back, not standing);
  - a pin loaded sideways prints lying down (teardrop section) or gets a metal insert.
- Split a part and join with pegs or screws rather than printing a weak orientation with
  supports [1].

## Snap fits (cantilever)

- Strain at the root of a uniform beam: **ε = 1.5 · t · y / (L² · Q)** with thickness t,
  deflection y (= the undercut), length L and Q = 1 for a beam on a rigid wall (about 2 for a
  short beam on a thin wall); deflection force P = b · t² · E · ε / (6 · L) with width b and
  flexural modulus E [8][9]. Taper the beam to half its thickness at the hook (y = 1.09 ε L²/h
  instead of 0.67) and the strain spreads along it [9].
- Design strain (one-time, printed flat): PLA 1.0 %, PETG 1.5 %, ABS/ASA 2.0 %, PC 2.5 %,
  nylon 3 % — **starting points**: derived from bulk one-time values (PC 4 %, PC/ABS 2.5 % [9])
  and printed break strains (PLA 4–8 %, ABS 7 %, nylon 4–15 % [6]) with a safety margin for
  layer bonds. Joints opened often: 60 % of that [9]. A cantilever built along Z halves the
  allowable strain [6]; do not build them that way.
- Lead-in (entry) angle 30°; retention angle 90° locks (needs a release window), 45° lets the
  joint open by hand [9]. Thickness 1.2 mm minimum, flexing within the layer plane
  (`tolerances.md`). Fillet or chamfer the root (about half the wall thickness) [6].
- `parts.snap_fit_check(L, t, y, material)` gives the strain and the maximum deflection;
  `parts.snap_hook(...)` refuses a beam over the limit; `parts.snap_window(...)` cuts the
  matching window with the snug clearance of `tolerances.md`.

## Screws, inserts and threads

| Screw | Pitch | Clearance hole fine / medium / coarse | Thread-forming hole (d − P) | Heat-set insert hole (chart) | Socket head dk × k | Countersink dk, 90° |
|---|---|---|---|---|---|---|
| M2 | 0.40 | 2.2 / 2.4 / 2.6 | 1.6 | 3.2 | 3.8 × 2.0 | 4.4 |
| M2.5 | 0.45 | 2.7 / 2.9 / 3.1 | 2.05 | 3.7 | 4.5 × 2.5 | 5.5 |
| M3 | 0.50 | 3.2 / 3.4 / 3.6 | 2.5 | 4.0 | 5.5 × 3.0 | 6.72 |
| M4 | 0.70 | 4.3 / 4.5 / 4.8 | 3.3 | 5.6 (5.3 for 6.0 mm-OD inserts) | 7.0 × 4.0 | 8.96 |
| M5 | 0.80 | 5.3 / 5.5 / 5.8 | 4.2 | 6.4 | 8.5 × 5.0 | 11.2 |
| M6 | 1.00 | 6.4 / 6.6 / 7.0 | 5.0 | 8.0 (7.6 for 8.4 mm-OD inserts) | 10.0 × 6.0 | 13.44 |

Sources: pitch and thread-forming (tap) hole ISO 261/262 [10]; clearance holes ISO 273 [11];
heat-set insert holes from maker charts [12][13], which differ by insert: **the datasheet of
the insert in hand wins** (`insert_d=` in `parts.screw_hole`); socket heads ISO 4762; countersunk
heads ISO 10642 (theoretical dk, 90°) [14]; M2/M2.5 countersink values are starting points.

- Clearance holes at nominal size, hole compensation in one place only (F1, `tolerances.md`).
- Screws into plastic: a thread-forming screw into a d − P hole works in PLA and PETG for a
  few assemblies (starting point: a tight hole cracks a thin boss, a loose one strips). For
  anything opened more than a few times, use a heat-set insert.
- Heat-set insert boss: hole depth = insert length + 1 mm (room for displaced plastic), wall
  around the hole 2 mm (five lines), and a 1 mm floor (starting points; `parts.standoff`).
- Countersink: 90° cone to the head's theoretical dk plus 0.3 mm radial clearance; counterbore:
  dk plus 0.3 mm radial, k plus 0.3 mm deep (starting points; `parts.screw_hole(kind=...)`).
- Printed threads from M6 up (`tolerances.md`); `parts.thread(...)` makes an approximate ISO
  profile (60° flanks, flat crest and root, no rounding) with 0.25 mm radial clearance for the
  nut as a starting point. Below M6: inserts or thread-forming screws.

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
- **`lid`**: a lid, door or flap hinge with alternating knuckles (three or more; an odd count is
  recommended, so every moving knuckle sits between two fixed ones) where the hand force
  reaches the pin without a lever multiplying it. Its pin is shared over several shear planes and nothing
  amplifies the pull, so the latch minimums do not apply; the floors are only what prints
  (pin 2.0, wall and leaf 1.2, knuckle 2 mm, `tolerances.md`) and the size comes from
  `strength.py hinge` reaching SF ≥ 2 at the load case below. A **hinge coupon print is
  required** before the full part (`parts.md`, "Printing the mechanism first"); a skipped
  one goes into `_assumptions` and is said at delivery, as for a fit test. Load case: the
  abuse case of pulling the open lid away from the box, `finger_pull` (98 N) at the hinge,
  shared equally by the moving knuckles, no lever ratio. Levering a lid backwards past its
  stop multiplies the force by (the finger's distance from the axis / the stop's distance
  from the axis) and is misuse a print-in-place hinge is not sized for: say so at delivery
  ("don't force the lid past fully open") instead of growing the hinge. A stop the user is
  meant to push against makes it a latch-duty case with that ratio.
- **`decorative`**: carries nothing; the same floors as `lid`, no calculation.

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
  the snap-fit check above. Their roots still must not double as the wall of a pin hole.

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

## Colour and function seams: split into parts

- A region with its own job or a likely different colour (latches, levers, labels, signs,
  inserts, logos) is a **separate body that touches the main body** (shared faces, no
  boolean union), recorded in `params.json` with `"object"` and `"role"` (`parts.md`).
  The slicer shows it as its own part, so the user recolours it by selecting it. Never
  ask about colours: split, give every part the main filament, say so at delivery.
- Same filament on both sides: Bambu Studio merges touching parts of one object into
  one region per layer, so the walls run through and the seam costs nothing (`parts.md`,
  source reading). Different filaments: two sets of perimeters meet at the seam, a
  wall-to-wall bond, weaker than continuous extrusion (starting point: treat it like a
  layer bond, half of XY strength, the orientation rule above).
- So keep seams in low-stress places: split a lever's handle, not its pivot; a label on
  a face, not through a wall; never at the root of a snap hook or across a boss. Both
  sides of a seam are the same material (PLA to PLA); PLA on PETG does not bond.
- Print-in-place moving parts are separate parts with `role: free` and their clearance
  (below); they are never merged.

## Text, logos, cosmetic faces

- Minimums: emboss 0.6 mm high, engrave 0.6 mm deep, strokes 0.8 mm wide; 1.0 mm recommended
  (`tolerances.md`). A bold sans-serif keeps strokes wide; at 0.8 mm minimum stroke a bold
  font needs a cap height of about 5 mm (derived: bold stroke ≈ 0.15 × cap height).
- Engraved text on the top face prints sharpest. Embossed text on a vertical wall is fine when
  the relief is shallow (about 1 mm: the underside of each letter is a tiny overhang). Text on
  the bottom face takes the bed's finish; engrave it, and expect elephant foot to round it.
- Decide where the visible face is, then orient: the face on the bed is smoothest, the top
  face shows the infill-free top layers (ironing helps), side walls show the seam.
- Seams: the slicer's "aligned" or "back" seam position puts the Z seam on one line; design a
  corner or a groove there so it hides (`bambu-process.md` has the setting).

## Supports policy

Never model support structures into a part (SKILL.md, rules that hold in every phase). An overhang gets, in this
order: a redesign (chamfer, 45° roof, teardrop, split and pegs [1]), a different print
orientation, and only then the slicer's supports for that object (tree supports leave less
marks). Surfaces above supports stay rough [1]: keep them away from fits and visible faces.

## Sources

1. Prusa Knowledge Base, "Modeling with 3D printing in mind" — perimeter widths, overhang
   angles, chamfer vs fillet, movable parts ≥ 0.3 mm, splitting parts.
   https://help.prusa3d.com/en/article/modeling-with-3d-printing-in-mind_164135/
2. Hubs, "How to design parts for FDM 3D printing" — 45°, bridges under 5 mm, pins under
   5 mm, chamfer the bed edge, drill holes.
   https://www.hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/
3. Prusa Knowledge Base (same article): 360° cooling prints overhangs to 75°.
4. engineering.com, "Conserving support material" — 45° angles and teardrop holes.
   https://mobile.engineering.com/amp/5070.html
5. Hubs, "Design rules for 3D printing" (FDM column: supported/unsupported walls 0.8 mm,
   overhangs 45°, bridges 10 mm, holes 2 mm, moving parts 0.5 mm, embossed details 0.6 mm).
   Infographic, mirrored at https://storytelling.robotics.umich.edu/assets/images/designrulesfor3dprinting.pdf
6. Fictiv, "How to design snap fit components" — strain formula with Q, printed break strains
   (PLA 4–8 %, ABS 7 %, nylon 4–15 %), Z-built cantilevers at half strain (tensile −20–30 %,
   elongation −50 %), clearances 0.2–0.4 mm, root radius.
   https://www.fictiv.com/articles/how-to-design-snap-fit-components
7. Shapeways, "How does part orientation affect the strength of 3D printed parts" — Z tensile
   strength up to 4–5× lower than XY in FDM.
   https://support.shapeways.com/hc/en-us/articles/17839359742876
8. Machine Design, "New equations make fastening plastic components a snap" (BASF) —
   ε = 1.5·t·Y/(L²·Q), P = b·t²·E·ε/(6·L·Q).
   https://www.machinedesign.com/archive/article/21818595/new-equations-make-fastening-plastic-components-a-snap
9. Bayer MaterialScience, "Snap-Fit Joints for Plastics — A Design Guide" — permissible
   strain table (PC 4 %, PC/ABS 2.5 %), taper to h/2 (y = 1.09 ε l²/h), 60 % for repeated use,
   30° lead angle. https://fab.cba.mit.edu/classes/S62.12/people/vernelle.noel/Plastic_Snap_fit_design.pdf
10. ISO 261 coarse pitches and tap drill = d − P, as tabulated by The Engineering ToolBox.
    https://www.engineeringtoolbox.com/iso-metric-thread-drill-tap-size-d_2045.html
11. ISO 273 clearance holes (fine / medium / coarse; the same nominal values as ASME B18.2.8
    close / normal / loose). https://amesweb.info/Screws/Metric-Clearance-Hole-Chart.aspx
12. Accu, "Threaded insert hole size charts for 3D printing" — heat-set M3 4.0, M4 5.6,
    M5 6.4, M6 8.0 mm. https://accu-components.com/us/p/488-threaded-insert-hole-size-charts-for-3d-printing-pla-petg-resin
13. Albany County Fasteners, heat-set insert specs — M2 3.2, M2.5 3.7, M3 4.0, M4 5.3, M5 6.4,
    M6 7.6 mm (inserts with a different OD than [12]).
    https://www.albanycountyfasteners.com/media/64/3d/5a/1764619189/heat-set-insert-specs.pdf
14. ISO 10642 countersunk socket screws (dk theoretical max, k), as tabulated by Engineers Edge.
    https://engineersedge.com/hardware/bs_en_iso_10642_14583.htm
