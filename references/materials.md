# Material data and hand forces for `strength.py`

Read this when sizing a member that carries load (design.md, "Mechanisms that carry load").
The numbers below are the ones `scripts/strength.py` uses; the script is the source, this
file is the reading copy. Every value comes from an official Bambu Lab Technical Data Sheet
(PDF on store.bblcdn.com, retrieved 2026-10-18); nothing is interpolated. Another maker's
filament needs its own data sheet before it can be used (the script refuses unknown names).

Contents:

- [Bambu Lab filaments (MPa; X-Y = loaded within the layer plane, Z = across layers)](#bambu-lab-filaments-mpa-x-y--loaded-within-the-layer-plane-z--across-layers)
- [Hand forces (N)](#hand-forces-n)
- [Safety factor](#safety-factor)
- [Inputs from the build](#inputs-from-the-build)
- [The pin model](#the-pin-model)
- [The hinge model](#the-hinge-model)
- [What the model does not see](#what-the-model-does-not-see)

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
force. A lid hinge takes `finger_pull` (the open lid pulled away from the box) shared by its
moving knuckles, no lever ratio (`design.md`, "Mechanisms that carry load"). A snap arm
takes no hand-force key: its load is its own deflection or release force (`design.md`, "Snap
fits"). Whatever load is used goes into `_assumptions` with its source.

## Safety factor

Default 2.0 against the data-sheet strength: specimens are solid, dried and annealed bars,
a part has walls and infill, corners without fillets and layer seams; PLA creeps under a
held load; a snap or a drop is an impact the static formula does not see. Use 3 for a
member that is loaded often or snapped over a cam. Below the factor, thicken the member or
print the mechanism alone first (SKILL.md, Phase 4).

## Inputs from the build

`strength.py <case> --from-build out/build.json --part <name>` takes the part's material from
the build report (`_parts.<name>.material`, else `_material`; `--material` is then refused,
and so is a part with no material), and each `--param INPUT=PARAM` takes one input of the
report's `inputs` (`h`, `b`, `length`, `pin_d`, `knuckles`, `orientation`, `support` …) from
the build's `parameters.values` (`plug.w` reaches into an object), checked as its option is
checked. An input is either typed or linked, not both. A build of scope `overrides`
(OpenSCAD, Python without `DEFAULTS`, `record`) holds only what params.json passed: a value
left to a generator default goes into params.json first. Every report says where each input
came from in `inputs_from`: `param:<PARAM>`, `build:material`, `table:<key>` (a hand-force or
material key), `default:<input>` (strength.py's own choice, such as `sf` 2.0) or `manual`
(typed). With `--from-build` it also carries `from_build` (the build, the part, its sha256
and material, the linked values) for finalize.py to compare with the current build. A value
the generator derives inside (a rib height = seat + margin) is no parameter: check it with a
measurement instead.

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

## The hinge model

`strength.py hinge` takes a print-in-place hinge as `parts.hinge` builds it: k knuckles
alternating A, B, A … along the pin, each b long (`--knuckle-len`, or `--length` with
b = (length − (k − 1) g) / k), axial gap g (`--gap`, 0.3), the pin with radial clearance c
(`--clearance`, 0.3) in B's holes (`parts.hinge` has one `clearance` for both: pass the same
value to `--gap` and `--clearance`), the pin part of leaf A (`--pin integral`, the default)
or a loose pin through every knuckle (`--pin loose`). The n_B = k // 2 moving knuckles share
the load equally, P = F / n_B each (an assumption the output states: a stiff lid). A B
knuckle between two A knuckles is interior; with k even the last knuckle is a B on the pin's
free end, a stub far more compliant than an interior span, so the equal share is then
optimistic for the interior knuckles (the output says so).

- **Integral pin, interior B**: the pin is built in at both A faces, so the span L = b + 2g
  is fixed at both ends with P spread evenly over the middle b. With zero slope at both
  ends the end moment is the mean of the simply supported moment diagram, (1 / L) ∫ M_ss,
  which for this load is M_end = P (6g² + 6gb + b²) / (12 L); the mid-span moment is
  M_mid = P (2L − b) / 8 − M_end, and the larger of the two is used (always M_end; they
  meet only as b → 0). Limits: g = 0 gives P b / 12 (a uniform load), b → 0 gives P L / 8
  (a centre point load). Two shear planes: τ = 4/3 · P / (2A).
- **Integral pin, end B** (k even): a stub from the last A face, M = P (g + b / 2), one shear
  plane. An odd knuckle count puts every moving knuckle between two fixed ones.
- **Loose pin**: each interior B as the clevis of the pin case with a = the A knuckle length
  (= b), M = P (b + 2a + 4g) / 8, two planes; an end B as a stub. The A knuckles then bear the
  pin as well: P / 2 from each interior B beside them, and from an end B the overhang's
  statics on a two-support pin, P plus the overhang moment carried over the next span,
  P (1 + s / 2s) = 1.5 P (exact for k = 4, where the last A takes 2P in all; an upper bound
  for longer hinges), or P when k = 2; the most loaded A is checked.
- **Layers**: `parts.hinge` prints the axis flat and the pull turns with the lid (sideways
  with the lid open flat, upwards at 90°), so the load is taken to cross the layers: pin
  shear and the knuckle wall's bearing and tear-out use the Z tensile strength whatever
  `--orientation` says; bending runs along the pin and uses the bending strength of
  `--orientation` (xy for a flat axis, z for one standing up). `--load-across-layers` is
  accepted for the hinge and changes nothing.
- Bending 32 M / (π d³) (the teardrop section is taken as a circle of the pin diameter; its
  point adds a little); shear 4/3 · P / (n A) against 0.58 × tensile Z. Per B knuckle the
  wall: bearing P / (d b) and tear-out P / (2 e b) with e the thinnest wall, above a
  teardrop's point, R − (r + c) √2, or above a round hole, R − (r + c); the pull direction
  turns with the lid, so the thinnest wall is used.
- `--duty latch | lid | decorative` adds a `minimums` block against that duty's P7 floors
  (`strength.py duties`; for `lid` also the knuckle count, 3 or more, odd recommended); a
  floor not met makes the gate FAIL. `lid` refuses `--sf` under 2 and at WARN says to grow
  the pin or the knuckle Ø or add knuckles: the coupon print is required on top of the
  margin and never replaces it. `decorative`: the floors alone decide the gate and the
  checks are reported with `"informational": true`.

Worked example, the field test of 2026-10 (an SD-card case lid, 36 mm hinge, five knuckles,
gaps 0.3, clearance 0.3, `finger_pull` 98 N shared by two moving knuckles, 49 N each, PLA
Basic, axis flat, bending X-Y, shear and wall Z): Ø2.4 pin in Ø7.4 knuckles (wall 1.58 mm):
shear 2.49, bending 3.10, bearing 10.6, tear-out 8.1, so SF ≥ 2 everywhere and the `lid`
floors met; Ø3.2 in Ø9.8 (the latch minimums, wall 2.21 mm): shear 4.43, bending 7.36,
bearing 14.1, tear-out 11.3. The same hinges with `--pin loose` read 1.81 (WARN) and 0.76
(FAIL) in bending, and the `pin` case with the whole 98 N on one clevis span reads 0.90: the
field run that called the Ø3.2 hinge a FAIL had modelled a loose pin carrying the whole
load, and the pin of `parts.hinge` is neither. With four knuckles the end knuckle's stub
reads 0.45 in bending and 1.24 in shear at Ø2.4 (FAIL), and with three knuckles over the
same 36 mm the one moving knuckle takes all 98 N on an 11.8 mm span: bending 0.97, shear
1.24 (FAIL). So for this hinge: five knuckles, odd (the floor of 3 is what the duty needs,
not what every hinge passes with). A three-knuckle coupon of the real knuckle
length (`parts.md`) is a harder test than the full hinge for the same reason: its one moving
knuckle takes the whole pull, twice this hinge's share.

## What the model does not see

The field comparison in `design.md`, with its inputs stated (`tests/test_strength.py`,
`FieldComparison`): finger push 70.6 N, shared by the failed latch's two curved arms and two
stub pins (35.3 N each); the arm's 2.5 mm bow and the bar's 12 mm length from the generator
that made it; root gaps taken as the radial clearances (0.42 and 0.33 mm); the lever ratio
of either latch **not measured**, so the hand force is applied 1:1; the failed latch
was printed in PLA Pure (confirmed by the owner).

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
For latch duty the minimums in `design.md` and a test print decide; a lid hinge is sized by
the calculation and decided by its coupon; a paper SF ≥ 2 is never the last word (the field
latch's pins and walls passed on paper at 2.6–4.4 and broke).
