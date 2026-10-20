# Phase 4 — Features and joints (review point)

Read this on entering Phase 4 (SKILL.md names the rules that hold at all times).

Holes, bosses, slots, vents, snap fits, lips, cable paths. Fits and clearances come from
`references/tolerances.md`, which states whether each value is radial (per side) or on the diameter;
the shapes (teardrop holes, insert bosses, snap hooks, hinges, threads, text) from
`references/design.md`, with `parts.py` building them in the Python engine.

## Every joint from both sides (F3)

With several parts, build and validate **all** of them, and check every joint from both sides:

```bash
python3 "$SKILL_DIR/scripts/fit.py" out/box.stl out/lid.stl --b-rotate 180,0,0 \
  --b-translate 0,40,33 --min-clearance 0.2 > out/fit_box_lid.json
```

`fit.py` places part B as assembled (rotation about its origin, then translation), then measures
the overlap volume, how far B can move sideways before it touches A (`play`, the real clearance of
a seated part), the smallest gap and the contact area, and prints a verdict in the validate.py
style: FAIL on overlap, WARN when the play is below `--min-clearance` or the parts bind, PASS
otherwise. A press fit fails by design; compare its overlap with the intended one instead. A
moving part gets a sweep (`--sweep-axis z --sweep-pivot x,y,z --sweep-angles 0:90:2
--sweep-travel 40`): the angle at which it hits its stop and the free travel before it; PASS when
it is free through the travel the part needs (give it, or the sweep only WARNs). Build a small
proxy of the mating housing from measured numbers when there is no closed mesh of it
(`references/measure.md`). The report records the sha256 of both STLs; a rebuild of either part
makes it stale (`--check`, Phase 5).

## Members that carry load (P7)

Every pin, knuckle, lever and latch bar is checked against the floors of its **duty** (P7,
`references/design.md`, "Mechanisms that carry load") before the fit, not after the print,
and gets a hand calculation. The duty decides the rule and the load case:

| Duty | What | Floors | Load case |
|---|---|---|---|
| `latch` (default) | a hand pushes, pulls, pinches or snaps it, or a lever amplifies the force: latches, catches, levers, clamps, a latch's pivot pin, a hinge leaf used as a lever | the field minimums (pin ≥ 3.2, pin wall ≥ 2.2, member ≥ 2.5 thick and ≥ 4 wide, knuckle ≥ 4 long) | the hand-force key that matches the operation × the lever ratio |
| `lid` | a lid, door or flap hinge with alternating knuckles (3 or more required, odd recommended), no lever between hand and pin | only what prints (pin 2.0, wall and leaf 1.2, knuckle 2 mm); the size comes from `strength.py hinge` at SF ≥ 2, the coupon print on top | the open lid pulled away from the box: `finger_pull` shared by the moving knuckles, no lever ratio; levering it past its stop is misuse: "don't force the lid past fully open" goes into `_assumptions` and is said at delivery |
| `decorative` | carries nothing | the same floors | none |

```bash
python3 "$SKILL_DIR/scripts/strength.py" pin --d 3.2 --engagement 4.25 --gap 0.3 --shear double \
  --support stub --load finger_push --material pla_basic --orientation xy
python3 "$SKILL_DIR/scripts/strength.py" hinge --pin-d 2.4 --knuckle-d 7.4 --knuckles 5 --length 36 \
  --gap 0.3 --clearance 0.3 --pin integral --duty lid --load finger_pull --material pla_basic --orientation xy
```

(`pin`, `beam`, `link`, `bearing`, `hinge`; loads from a cited hand-force table or `--load N`,
the lever ratio applied by you; materials from Bambu Lab data sheets, `--orientation xy|z` for
the layer direction, `--gap` for the print-in-place gap at a pin's root or between knuckles,
`--sf` 2 by default; `references/materials.md`. The `hinge` case takes the hinge as
`parts.hinge` builds it, an integral or a loose pin, with the pull taken to cross the layers
(the axis prints flat and the pull turns with the lid: shear and the knuckle wall use the Z
strength); `parts.hinge` has one `clearance` for the radial clearance and the axial gap, so
pass it as both `--gap` and `--clearance`; with `--duty` it compares pin, wall, knuckle length
and, for a lid, the knuckle count with that duty's floors.) Record the load case, its share
and the ratio in `_assumptions`. FAIL → redesign. WARN, or no proven reference to compare
with → **print the mechanism first**: `build.py run --only latch,keeper --out out/mech` builds
those parts whole (a coupon part for less), a few grams, and the user tries it before the
full part (the same idea as the fit test; a Bambu job lists only those parts;
`references/parts.md`, "Printing the mechanism first"). A `lid` hinge must reach SF ≥ 2: at
WARN grow the pin or the knuckle Ø or add knuckles (odd), and its coupon print is required on
top of that margin, never instead of it. A mechanism built into the walls (a box hinge) still
gets its coupon: the same section cut short, built as its own `_parts` entry; "cutting it out
would be most of the part" is not a reason to skip. The calculation is a sizing aid: it
flagged the failed field latch's arms, not its pins, so for latch duty the minimums and the
test print decide; for a lid hinge the calculation sizes and the coupon decides, and a paper
SF ≥ 2 is never the last word.

## Fit test first

When the part must fit an existing object whose shape is not known exactly (no caliper numbers,
no official drawing): make test pieces of the mating profile, a few grams each, in three
clearance steps marked with 1, 2, 3 holes:

```bash
python3 "$SKILL_DIR/scripts/fit_test.py" --profile rounded --size 45.1,14.0 --radius 2 --out out/fit
```

(`--profile rect | rounded | circle | polygon`, `--mode ring` for an object that goes into the part,
`--mode plug` for a part that goes into the object; `--clearance`, `--step`, `--steps`;
`--bambu-template` also writes a `bambu3mf.py` job.) The JSON's `how_to_read` tells the user
what to try; build the real part with the step that fits. If the user cannot test now, build to the
middle step and record that in `_assumptions`; the same for a skipped mechanism-first print
("latch pin Ø3.2: not confirmed by a test print"; "lid hinge Ø2.4 in Ø7.4 knuckles: coupon not
printed"). Print the test pieces and the final part with the same printer, filament and process
preset: another preset changes the fit.
