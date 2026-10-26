# Features: snap fits, screws and inserts, keyholes, text

Read the section a part needs: a snap fit, a screw, insert or thread, a keyhole, or text and
logos. The general patterns are in `design.md`; fit clearances in `tolerances.md`.

Contents:

- [Snap fits (cantilever)](#snap-fits-cantilever)
- [Screws, inserts and threads](#screws-inserts-and-threads)
- [Keyholes and hanging slots](#keyholes-and-hanging-slots)
- [Text, logos, cosmetic faces](#text-logos-cosmetic-faces)

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
- A snap opened every day: that 60 % strain and SF 3 on the arm (`materials.md`, "Safety
  factor"). PLA is fine when the arm is not held deflected (PLA creeps under a held load); PETG
  when the undercut needs more strain than PLA allows.
- Lead-in (entry) angle 30°; retention angle 90° locks (needs a release window), 45° lets the
  joint open by hand [9]. Thickness 1.2 mm minimum, flexing within the layer plane
  (`tolerances.md`). Fillet or chamfer the root (about half the wall thickness) [6].
- `strength.py snap` (any engine) and `parts.snap_fit_check(L, t, y, material)` give the strain
  against the limit and the maximum deflection; `strength.py snap` adds the deflection force and
  the insertion and release forces; a tapered arm, or the undercut when tolerances stack (the
  worst gap), goes through `strength_cases.py snap --taper ... --gap-worst ...`;
  `parts.snap_hook(...)` refuses a beam over the limit; `parts.snap_window(...)` cuts the
  matching window with the snug clearance of `tolerances.md`.
- A snap arm is exempt from the latch floors (`design-mechanisms.md`, "Mechanisms that carry load"). Its load case in
  `strength.py` is its own deflection or release force (P above, at full undercut), not a
  hand-force key.
- **Snap-in cylinder (C-clip)**: a round part pushed into a ring open at the mouth. The bore
  clearance sets only the rattle (snug, `tolerances.md`); the hold comes from the mouth
  undercut (cylinder Ø minus mouth width), sized by the strain formula above. Each arm deflects
  about half the undercut when both arms flex, the whole undercut when one side is rigid; the
  straight-beam formula only approximates a curved arm. A start value only: confirm it with a
  full-width test piece (`parts.md`, "Printing the mechanism first").

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
  For a wood screw or any screw in hand, the caliper's head diameter beats the ISO table
  (`parts.screw_hole(..., head_d=)`).
- Printed threads from M6 up (`tolerances.md`); `parts.thread(...)` makes an approximate ISO
  profile (60° flanks, flat crest and root, no rounding) with 0.25 mm radial clearance for the
  nut as a starting point. Below M6: inserts or thread-forming screws.

## Keyholes and hanging slots

- A keyhole hangs the part on a screw head in the wall: a round entry the head passes through,
  a slot for the shank, and a pocket behind the slot that holds the head. The part slides
  **down** onto the screw, so in the hanging pose the slot runs **up** from the entry.
- Shank slot and head pocket: the shank's and the head's diameter plus the sliding clearance
  (`tolerances.md`, per side); the entry a little wider than the pocket. Pocket depth: the
  head height plus room for how far the screw stands out of the wall.
- The head height is rarely given: ask, or assume it (a standard head of that size) and record
  it in `_assumptions`.
- The lip (between the back face and the pocket, it carries the part) and the roof (in front
  of the pocket) are structural walls, 1.6–2.0 mm (`tolerances.md`). Printed back-down, the
  roof bridges the pocket: keep that span under 10 mm (`design.md`, "Overhangs").
- These are start values: confirm the hang with a test piece when the screw is at hand.

## Text, logos, cosmetic faces

- Minimums: emboss 0.6 mm high, engrave 0.6 mm deep, strokes 0.8 mm wide; 1.0 mm recommended
  (`tolerances.md`). A bold sans-serif keeps strokes wide; at 0.8 mm minimum stroke a bold
  font needs a cap height of about 5 mm (derived: bold stroke ≈ 0.15 × cap height). Blender's
  built-in font is a regular weight: its strokes reach 0.8 mm only at about a 7 mm cap height
  (measured in the coaster example); pass a bold font file to `blender_builder.text` for
  smaller text (it is packed into the `.blend`).
- Text strokes are not walls: a 0.8–1.2 mm stroke prints with gap fill or the Arachne wall
  generator's variable-width lines, not whole perimeters, so "avoid 1.0 mm" (`design.md`, walls) does
  not apply. Bambu's system process presets use the classic wall generator (`fdm_process_common`,
  profiles 02.08.02.61): for small text set `wall_generator: "arachne"` on the object
  (`bambu-process.md`).
- **Two colours.** Light text on a dark body (white on black): a flush inlay at least 1.0 mm
  deep, 5 layers at 0.2 mm, so the dark does not show through the light layers (starting point).
  Raised text in a second colour only for dark on light, or 0.8 mm high or more (4 layers).
  The text is a `fused` part of the body's object (`parts.md`): A1 checks it, and F3 is N/A
  (no clearance, no joint). P3 WARNs on an inlay under 1.2 mm deep (it measures the depth); the
  text rule decides.
- **Fonts.** The font must cover the script: `bb.text` and `parts.text` refuse a character the
  font cannot draw, while OpenSCAD's `text()` draws boxes or falls back to another font without
  a word (2021.01, a test run), so there name a font that covers the script and check the body
  count and the preview. Prefer OFL or Apache fonts; for Korean and other CJK text the default
  is Noto Sans CJK (SIL OFL 1.1). Record the font and its licence in `_assumptions`. A font the
  user supplies stays in the project's `fonts/`. Never pack a proprietary system font (Malgun
  Gothic, Apple SD Gothic Neo, ...) into a delivered file: deliver the STLs only, without the
  `.blend`, or ask. A `.ttc` loads its first face, and a packed CJK font makes the `.blend`
  large (a 20 MB `.ttc` gave a 15 MB `.blend` in a test run).
- Text height is the cap height of a Latin "H": Hangul and other non-Latin glyphs come out
  taller (Hangul 25–33 % in a test run), so take the text's size from what the build reports
  (`engines/blender.md`, "Booleans and text"), not from the height you asked for.
- Engraved text on the top face prints sharpest. Embossed text on a vertical wall is fine when
  the relief is shallow (about 1 mm: the underside of each letter is a tiny overhang). Text on
  the bottom face takes the bed's finish; engrave it, and expect elephant foot to round it.
- Decide where the visible face is, then orient: the face on the bed is smoothest, the top
  face shows the infill-free top layers (ironing helps), side walls show the seam.
- Seams: the slicer's "aligned" or "back" seam position puts the Z seam on one line; design a
  corner or a groove there so it hides (`bambu-process.md` has the setting).

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
