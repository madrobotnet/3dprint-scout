# Phase 4 — Moving parts and members that carry load

Read this only when a part moves (a lid, a lever, a slider), sits on a standard's counterpart,
or carries load (a pin, knuckle, lever, link, hook or latch bar). The rest of Phase 4 is in
`references/phase-4-features-joints.md`.

## The sweep of a moving part

A moving part gets a sweep from its placed pose (`--sweep-axis z --sweep-pivot x,y,z
--sweep-angles 0:90:2 --sweep-travel 40`): the angle at which it hits its stop and the free
travel before it, the turn between two steps followed too. Always give the travel the part needs
(`--sweep-travel`, a magnitude, also for a clockwise sweep): PASS when it is free through it,
FAIL when it hits before it; without it a stop is only a WARN and a free sweep is UNVERIFIED. A
range that does not start at 0 or ends before the travel is UNVERIFIED too. Declare that joint
with `"sweep": true` in `_verify.joints`: without it finalize does not require F3_sweep, and a
report of the seated fit alone would pass for the moving part. A part that turns in contact (a
lever lying on its body) is checked every 0.2 mm of its swing, which can take a while on dense
meshes; a sweep that would need more than 1000 such checks is UNVERIFIED (sweep a shorter range,
or lighter proxies).

## A part built to a standard

A part built to a standard (a bin on a baseplate, a stacking lip) has a joint with the
standard's counterpart: build a proxy of it from the standard's numbers and run F3 against it.
To find a seat height, place B above its seat and run `--play 0,0,-1`: the play is how far B
drops before it touches; place it that much lower and run the fit again with the sideways
directions. A proxy built from the same numbers as the part only proves the two agree with each
other, not that the numbers are right: say so, and offer a fit test when the source is
unverified.

## strength.py: what each input means

The material is the part's (`_material`, `_parts.<name>.material`; `--material` is refused). A
hand-force key (`--load finger_push`) is a table value, and an input left out takes strength.py's
own default (`sf` 2, `orientation` z): neither counts as typed in. An input typed on the command
line (`--h 6`, `--support cantilever`, `--sf 3`, `--repeated`, `--load 141.2`) is `manual` in the
report's `inputs_from`, even when it equals the parameter: such a report can size a member, but it
is never evidence of a `use` promise. A parameter the build did not record is an error that names
it: add it to `DEFAULTS` or `PARAMETERS` (to params.json for a build of scope `overrides`) and
build again. The ribbon at 4.5 mm read WARN at SF 3 (1.88); at 6.0 it passes (3.34).

The cases are `pin`, `beam`, `link`, `bearing`, `hinge` and `snap`; loads come from a cited
hand-force table, or a force in N that is a parameter (`--param load=latch_load`: the key's
force × the lever ratio, worked out by you); materials from Bambu Lab data sheets, `orientation`
xy or z for the layer direction, `gap` for the print-in-place gap at a pin's root or between
knuckles, `sf` 2 by default (`references/materials.md`). The `hinge` case takes the hinge as
`parts.hinge` builds it, an integral or a loose pin, with the pull taken to cross the layers (the
axis prints flat and the pull turns with the lid: shear and the knuckle wall use the Z strength);
`parts.hinge` has one `clearance` for the radial clearance and the axial gap, so link it to both
`gap` and `clearance`; with `duty` it compares pin, wall, knuckle length and, for a lid, the
knuckle count with that duty's floors. The hinge of a lid with a latch:

```bash
python3 "$SKILL_DIR/scripts/strength.py" hinge --from-build out/build.json --part lid \
  --param pin_d=hinge_pin_d --param knuckle_d=hinge_knuckle_d --param knuckles=hinge_knuckles \
  --param length=hinge_len --param gap=hinge_clearance --param clearance=hinge_clearance \
  --param pin=hinge_pin --param duty=hinge_duty --param orientation=hinge_orient --load finger_pull \
  > out/strength_hinge.json
```

A snap arm: `strength.py snap` with the arm's `length`, `h`, `b` and `undercut` (and `repeated`,
true for a snap opened often: a params.json boolean such as `"snap_repeated": true`, linked with
`--param repeated=snap_repeated`) checks the strain against the limit and gives the deflection
force and the insertion and release forces; a straight arm can also go through `strength.py
beam` with that force as its load and SF 3, both parameters.

## Coupons and the lid hinge

A `lid` hinge must reach SF ≥ 2: at WARN grow the pin or the knuckle Ø or add knuckles (odd), and
its coupon print is required on top of that margin, never instead of it. A mechanism built into
the walls (a box hinge) still gets its coupon: the same section cut short, built as its own
`_parts` entry; "cutting it out would be most of the part" is not a reason to skip. A coupon is a
part like any other: every full build makes it, and it is delivered with the rest (Phase 6). A
snap's coupon keeps the full width (the click force scales with it, `references/design-features.md`) and
steps the undercut, one coupon part per step; `fit_test.py` steps only the clearance of closed
rings and plugs. The calculation is a sizing aid: it flagged the failed field latch's arms, not
its pins, so for latch duty the minimums and the test print decide; for a lid hinge the
calculation sizes and the coupon decides, and a paper SF ≥ 2 is never the last word.
