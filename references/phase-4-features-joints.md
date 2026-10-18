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
  --b-translate 0,40,33 --min-clearance 0.2
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
(`references/measure.md`).

## Members that carry load (P7)

Every pin, knuckle, lever and latch bar is checked against the mechanism minimums (P7) before
the fit, not after the print, and gets a hand calculation:

```bash
python3 "$SKILL_DIR/scripts/strength.py" pin --d 3.2 --engagement 4.25 --gap 0.3 --shear double \
  --support stub --load finger_push --material pla_basic --orientation xy
```

(`pin`, `beam`, `link`, `bearing`; loads from a cited hand-force table or `--load N`, the
lever ratio applied by you; materials from Bambu Lab data sheets, `--orientation xy|z` for
the layer direction, `--gap` for the print-in-place gap at a pin's root, `--sf` 2 by default;
`references/materials.md`.) Record the load and its share in `_assumptions`. FAIL → redesign;
WARN, or no proven reference to compare with → **print the mechanism first**: `build.py run
--only latch,keeper --out out/mech` builds those parts whole (a coupon part for less), a few
grams, and the user tries it before the full part (the same idea as the fit test; a Bambu job
lists only those parts; `references/parts.md`, "Printing the mechanism first"). The
calculation is a sizing aid: it flagged the failed field latch's arms, not its pins, so the
minimums and the test print decide.

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
("latch pin Ø3.2: not confirmed by a test print"). Print the test pieces and the final part with
the same printer, filament and process preset: another preset changes the fit.
