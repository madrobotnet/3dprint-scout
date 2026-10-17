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
| `grasp` | power grasp, whole hand | — | 452.4 ± 102.9 | 555.4 |

The design value covers about 84 % of male users at a brief peak; it is a starting point,
not a rule. A latch lever multiplies the hand force by its lever ratio: pass the amplified
force. Whatever load is used goes into `_assumptions` with its source.

## Safety factor

Default 2.0 against the data-sheet strength: specimens are solid, dried and annealed bars,
a part has walls and infill, corners without fillets and layer seams; PLA creeps under a
held load; a snap or a drop is an impact the static formula does not see. Use 3 for a
member that is loaded often or snapped over a cam. Below the factor, thicken the member or
print the mechanism alone first (SKILL.md, Phase 4).

## What the model does not see

The field comparison in `design.md`: the static formulas flag the failed latch's 1.2 mm
curved arms (bending from the bow, factor 0.2) and its thin bars, but its Ø2.6 stub pins
and 1.3 mm pin walls pass on paper with a factor of about 4 under a 35 N share of the
finger push, and they broke all the same. Impact at snap-over, the lever ratio, stress
concentration at sharp roots and a pin standing across layers are not in the formulas.
`strength.py` separates the hopeless from the plausible; the mechanism minimums in
`design.md` and a test print of the member decide.
