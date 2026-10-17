# Designing for FDM printing

Read this in Phase 3 (base shape) and again in Phase 4 (features). Patterns to apply while
modelling, with the numbers that back them. Fit clearances live in `tolerances.md` and are
only linked from here. Numbers without a source are **starting points: calibrate** on the
user's printer (a 0.4 mm nozzle and PLA are assumed, SKILL.md defaults). `scripts/parts.py`
builds most of these shapes with these defaults.

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
- Knuckles get a flat on the bed side; the leaf plates lie flat. `parts.hinge(...)` builds
  such a hinge; validate it with `--shells 2` (two bodies that never touch).
- After the print, free the joint with a few firm twists before the parts cool completely
  (PLA is still soft) — tell the user.

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

Never model support structures into a part (SKILL.md Phase 5). An overhang gets, in this
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
