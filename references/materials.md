# Material data and hand forces for `strength.py`

Read this when sizing a member that carries load (design.md, "Mechanisms that carry load").
The numbers below are the ones `scripts/strength.py` uses; the script is the source, this
file is the reading copy. Every value comes from an official Bambu Lab Technical Data Sheet
(PDF on store.bblcdn.com, retrieved 2026-10-18); nothing is interpolated. Another maker's
filament needs its own data sheet before it can be used (the script refuses unknown names).

## Bambu Lab filaments (MPa; X-Y = loaded within the layer plane, Z = across layers)

| Key | Material (TDS) | Tensile X-Y / Z | Young's E X-Y / Z | Bending strength X-Y / Z | Bending modulus X-Y / Z | Elongation X-Y / Z % |
|---|---|---|---|---|---|---|
| `pla_basic` | Bambu PLA Basic (V3.0) | 35 / 31 | 2580 / 2060 | 76 / 59 | 2750 / 2370 | 12.2 / 7.5 |
| `pla_matte` | Bambu PLA Matte (V3.0) | 30 / 22 | 1960 / 1670 | 53 / 29 | 2360 / 1770 | 14.8 / 4.8 |
| `pla_pure` | Bambu PLA Pure (V1.0) | 51.5 / 30 | 2481 / 2196 | 75 / 55 | 2880 / 2599 | 5.6 / 2.8 |
| `petg_basic` | Bambu PETG Basic (V3.0) | 51 / 35 | 2780 / 2550 | 75 / 56 | 1950 / 1740 | 9.5 / 5.2 |
| `petg_hf` | Bambu PETG HF (V1.0) | 34 / 23 | 1810 / 1540 | 64 / 48 | 2050 / 1810 | 8.6 / 5.1 |
| `abs` | Bambu ABS (V3.0) | 33 / 28 | 2200 / 1960 | 62 / 39 | 1880 / 1590 | 10.5 / 4.7 |
| `asa` | Bambu ASA (V3.0) | 37 / 31 | 2450 / 2120 | 65 / 40 | 1920 / 1650 | 9.2 / 4.6 |

Tensile and Young's modulus per ISO 527 / GB/T 1040, bending per ISO 178 / GB/T 9341; the
sheets give ± tolerances (a few MPa) that are left out here. Specimens were printed at
100 % infill and dried, most annealed (PETG Basic: annealing not recommended; PLA Pure: not
annealed, printed on an H2 with a 0.4 mm nozzle). The sheets call the values typical results
"for design reference and comparison only". The PLA Pure sheet's comparison table swaps the
labels of bending modulus and strength; its main table is used.

Sources:

- PLA Basic: https://store.bblcdn.com/s7/default/b189de92249a4b9ebed28b8ea1f080f0/Bambu_PLA_Basic_Technical_Data_Sheet.pdf
- PLA Matte: https://store.bblcdn.com/s7/default/5b061f2feeac4ba88f355a33248bbda7/Bambu_PLA_Matte_Technical_Data_Sheet.pdf
- PLA Pure: https://store.bblcdn.com/s7/default/0e7400b878d84516a1ae605c1edaeab0/pla_pure_-TDS.pdf
- PETG Basic: https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf
- PETG HF: https://store.bblcdn.com/3a230e260a3a47c2b0db0156e07eef91.pdf
- ABS: https://store.bblcdn.com/s7/default/23b4cf2b83d5470bb96d19970b5f3ae8/Bambu_ABS_Technical_Data_Sheet_V3.pdf
- ASA: https://store.bblcdn.com/ad7b08230c164e72856cffbe06bb7dc9.pdf

Not on the sheets, so assumed and printed with every result: shear strength = 0.58 ×
tensile (von Mises), bearing strength = tensile (conservative).

## Hand forces (N)

Peak forces of the dominant hand, seated, 100 adults (50 male, 50 female, 18–65), brief
exertions: A. DiDomenico and M. A. Nussbaum, "Measurement and prediction of single and
multi-digit finger strength", *Ergonomics* 46(15), 2003, 1531–1548, Table 2
(https://stacks.cdc.gov/view/cdc/191543/cdc_191543_DS1.pdf, retrieved 2026-10-18).

| Key | Action | All, mean ± SD | Male, mean ± SD | Design value (male mean + 1 SD) |
|---|---|---|---|---|
| `finger_push` | index finger push (poke) | 46.0 ± 17.8 | 52.6 ± 18.0 | 70.6 |
| `finger_press` | index fingertip press, 180° pad | 43.1 ± 18.4 | 50.9 ± 18.4 | 69.3 |
| `finger_pull` | index fingertip pull, 90° pad | 60.1 ± 25.2 | 70.8 ± 27.2 | 98.0 |
| `pinch_lateral` | lateral (key) pinch | 80.9 ± 28.2 | 97.0 ± 27.7 | 124.7 |
| `pinch_palmar` | palmar pinch | 54.2 ± 18.8 | 62.9 ± 19.2 | 82.1 |
| `grasp` | power grasp, whole hand | 370.7 ± 117.7 | 452.4 ± 102.9 | 555.4 |

The design value covers about 84 % of male users at a brief peak; it is a starting point,
not a rule. A latch lever multiplies the hand force by its lever ratio: pass the amplified
force. Whatever load is used goes into `_assumptions` with its source.

## Safety factor

Default 2.0 against the data-sheet strength: specimens are solid, dried and annealed bars,
a part has walls and infill, corners without fillets and layer seams; PLA creeps under a
held load; a snap or a drop is an impact the static formula does not see. Use 3 for a
member that is loaded often or snapped over a cam. Below the factor, thicken the member or
print the mechanism alone first (SKILL.md, Phase 4).

## The pin model

`strength.py pin` checks transverse shear, peak 4/3 of the average over the circle (one shear
plane for `--shear single`, two for `double`), and bending, 32 M / (π d³), with the moment
from the support type:

- `--support stub`: the pin grows out of one part and sits in the other. A cantilever from
  its root face, the load spread evenly over the engagement L inside the mating part, plus
  the gap g between root face and mating part (`--gap`; print-in-place has 0.3–0.42 mm
  there): M = F′ (g + L / 2). With `--shear double` both ends are stubs and each carries
  F′ = F / 2, the case of a pin formed on a lever with its ends in two rails (L = rail
  thickness).
- `--support through`: a loose pin through two supports of thickness a (`--support-t`),
  loaded by the member of width b (`--engagement`) between them, gap g on each side: the
  clevis formula M = F (b + 2a + 4g) / 8, every bearing load spread evenly. A load
  concentrated at the centre of the member would reach F (b + 2a) / 4. A through pin is in
  double shear.
- Layers: `--orientation` is the direction of the bending stress, which runs along the pin
  (xy for a pin lying flat, z for one standing up). Shear slides layer on layer when the pin
  stands up or when a flat pin is pushed across the layers: pass `--load-across-layers` for
  the latter and the shear check uses the Z strength while bending keeps X-Y.

## What the model does not see

The field comparison in `design.md`, with its inputs stated (`tests/test_strength.py`,
`FieldComparison`): finger push 70.6 N, shared by the failed latch's two curved arms and two
stub pins (35.3 N each); the arm's 2.5 mm bow and the bar's 12 mm length from the generator
that made it; root gaps taken as the radial clearances (0.42 and 0.33 mm); the lever ratio
of either latch **not measured**, so the hand force is applied 1:1; PLA Pure per the failed
latch's project file (owner to confirm; with PETG Basic, X-Y 51 / 75 MPa, every verdict is
the same).

The static formulas flag the failed latch's 1.2 mm curved arms (bending from the bow,
factor 0.42 with the load shared, 0.21 for one arm alone) and its 1.7 × 2.6 mm bar (0.11 as
a 12 mm cantilever with the full load, 0.44 as a span between the arms loaded at its
centre). Its Ø2.6 stub pins pass on paper: bending 2.6 with the gap, shear 3.4 in the layer
plane, 2.0 (WARN) when the load crosses the layers; at a lever ratio of 2 the pin is WARN,
at 3 FAIL. Its 1.3 mm pin walls pass tear-out at 4.4. Pins and walls broke all the same.
The working latch passes everywhere: pin bending 2.9 (2.3 across layers), shear 3.6, wall
10.8, rail 5.3; a loose pin of the same size through the same rails would read WARN 1.4.

So the model separates the hopeless from the plausible, and the unmeasured lever ratio
alone could move the failed pins into WARN or FAIL. Impact at snap-over, stress
concentration at sharp roots and layer seams at the root are not in the formulas either.
The mechanism minimums in `design.md` and a test print of the member decide.
