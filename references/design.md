# Designing for FDM printing

Read this in Phase 3 (base shape) and again in Phase 4 (features). Patterns to apply while
modelling, with the numbers that back them. Fit clearances live in `tolerances.md` and are only
linked from here. Numbers without a source are **starting points: calibrate** on the user's
printer (a 0.4 mm nozzle and PLA are assumed: SKILL.md Phase 2 defaults,
`phase-2-printer-dimensions.md`). `scripts/parts.py` builds most of these shapes with these
defaults.

Read only when the part has one:

- a hinge, pivot, latch, lever, clamp or other member that carries load: `design-mechanisms.md`
  ("Print-in-place joints", "Mechanisms that carry load");
- a snap fit, a screw, insert or thread, a keyhole, or text and logos: `design-features.md`.

Contents:

- [Bed edge: chamfer, never a fillet](#bed-edge-chamfer-never-a-fillet)
- [Overhangs and self-supporting shapes](#overhangs-and-self-supporting-shapes)
- [Walls and small features in nozzle multiples](#walls-and-small-features-in-nozzle-multiples)
- [Orientation for strength](#orientation-for-strength)
- [Colour and function seams: split into parts](#colour-and-function-seams-split-into-parts)
- [Supports policy](#supports-policy)
- The sections that moved, by name: [Snap fits (cantilever)](#snap-fits-cantilever), [Screws,
  inserts and threads](#screws-inserts-and-threads), [Keyholes and hanging
  slots](#keyholes-and-hanging-slots), [Print-in-place joints](#print-in-place-joints),
  [Mechanisms that carry load](#mechanisms-that-carry-load), [Text, logos, cosmetic
  faces](#text-logos-cosmetic-faces)

## Bed edge: chamfer, never a fillet

- The first layer squashes outwards (elephant foot). A fillet on the bed edge is an overhang
  that prints rough; a 45° chamfer prints clean and hides the foot [1][2]. Leg 0.3–0.5 mm
  (`tolerances.md`, Limits). Either this chamfer or the slicer's elephant-foot compensation,
  not both (F1 in `tolerances.md`). `parts.chamfered_box(..., "bottom")`,
  `parts.bottom_chamfer(part, 0.4)`.
- A 45° chamfer under any ledge, boss foot or lip (`parts.standoff(..., foot=1.0)`) removes
  the overhang; a fillet does not.
- Fillets elsewhere (top edges, vertical edges, a freeform body's rim) need an engine that has
  them: Fusion, or Blender's Bevel modifier (`blender_builder.bevel`, which leaves the bed edges
  alone and `bed_chamfer` cuts those slightly steeper than 45°); OpenSCAD and Python chamfer
  instead, or blend with `sdf.py`.

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
  slicer cannot fill); text strokes are the exception (`design-features.md`, "Text, logos, cosmetic faces").
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

In `design-features.md`.

## Screws, inserts and threads

In `design-features.md`.

## Keyholes and hanging slots

In `design-features.md`.

## Print-in-place joints

In `design-mechanisms.md`.

## Mechanisms that carry load

In `design-mechanisms.md`.

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
  (`design-mechanisms.md`); they are never merged.

## Text, logos, cosmetic faces

In `design-features.md`.

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
