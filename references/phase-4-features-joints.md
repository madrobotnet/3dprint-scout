# Phase 4 — Features and joints (review point)

Read this on entering Phase 4 (SKILL.md names the rules that hold at all times).

Holes, bosses, slots, vents, snap fits, lips, cable paths. Fits and clearances come from
`references/tolerances.md`, which states whether each value is radial (per side) or on the diameter;
the shapes from `references/design.md` (teardrop holes), `references/design-features.md` (insert
bosses, snap hooks, threads, text) and `references/design-mechanisms.md` (hinges and members that
carry load), with `parts.py` building them in the Python engine.

Each check below is evidence of a promise (Phase 1) once its report is saved: declare it in
`_verify` as you save it (the format: `references/checks.md`, "The `_verify` declarations") and
name it in the `evidence` of the promise it checks. A part's own checks (D1, M1, ...) are never
evidence of a promise. Run every check from the project folder with relative paths, as below:
the reports record the paths they are given, and the bundle refuses an absolute one.

## Every joint from both sides (F3)

With several parts, build and validate **all** of them, and check every joint from both sides:

```bash
python3 "$SKILL_DIR/scripts/fit.py" out/box.stl out/lid.stl --b-rotate 180,0,0 \
  --b-translate 0,40,33 --min-clearance 0.2 > out/fit_box_lid.json
```

`fit.py` places part B as assembled (rotation about its origin, then translation), then measures
the overlap volume, how far B can move sideways before it touches A (`play`, the real clearance of
a seated part; the whole move is followed, so a lip B would pass through and leave still stops
it), the smallest gap and the contact area, and prints a verdict in the validate.py style: FAIL
on overlap, WARN when the play is below `--min-clearance` or the parts bind, PASS otherwise. A
press fit fails by design; compare its overlap with the intended one instead. A moving part gets
a sweep from its placed pose (`--sweep-axis z --sweep-pivot x,y,z --sweep-angles 0:90:2
--sweep-travel 40`): the angle at which it hits its stop and the free travel before it, the turn
between two steps followed too. Always give the travel the part needs (`--sweep-travel`, a
magnitude, also for a clockwise sweep): PASS when it is free through it, FAIL when it hits
before it; without it a stop is only a WARN and a free sweep is UNVERIFIED. A range that does
not start at 0 or ends before the travel is UNVERIFIED too. Declare that joint with `"sweep":
true` in `_verify.joints`: without it finalize does not require F3_sweep, and a report of the
seated fit alone would pass for the moving part. A part that turns in contact (a
lever lying on its body) is checked every 0.2 mm of its swing, which can take a while on dense
meshes; a sweep that would need more than 1000 such checks is UNVERIFIED (sweep a shorter range,
or lighter proxies). When the mating object has no closed mesh (a plug, a phone, a housing),
fit against a proxy of it (below). The report records the sha256 of both STLs; a rebuild of
either part makes it stale (`--check`, Phase 5). `--min-clearance` is the clearance the model is
built with, model hole compensation included (`references/tolerances.md`, F1).

A part built to a standard (a bin on a baseplate, a stacking lip) has a joint with the
standard's counterpart: build a proxy of it from the standard's numbers and run F3 against it.
To find a seat height, place B above its seat and run `--play 0,0,-1`: the play is how far B
drops before it touches; place it that much lower and run the fit again with the sideways
directions. A proxy built from the same numbers as the part only proves the two agree with each
other, not that the numbers are right: say so, and offer a fit test when the source is
unverified.

**A proxy of the mating part**: a small generator of its own that takes every size from a
params file of its own, holding exactly the numbers of the object's `dims` entry (Phase 2) with
the values params.json has; built with `--proxy` into a folder of its own, its JSON saved there;
the joint declared with `"proxy": true`, those `dims` and that JSON as `proxy_build`. How to
build one: `references/measure.md`, "A watertight proxy of the mating part"; what finalize makes
of it (a promise on it stays `assumed` while its dims are): `references/checks.md`. The phone
stand's right-angle plug, with `.3dprint/usb_c_plug.json` holding `plug_w`, `plug_h`, `plug_l`
and `cable_d` and nothing else:

```bash
mkdir -p out/plug && python3 "$SKILL_DIR/scripts/build.py" run plug_proxy.py \
  --params .3dprint/usb_c_plug.json --proxy plug_proxy --out out/plug > out/plug/build.json
python3 "$SKILL_DIR/scripts/fit.py" out/sled.stl out/plug/plug_proxy.stl --b-translate 33.5,7,1.75 \
  --min-clearance 0.2 > out/fit_plug.json
```

When the user measures the object later, Phase 2 (step 3) records it; a changed value means
building the part and the proxy again, then the fit and every other check of the part.

## Members that carry load (P7)

Every pin, knuckle, lever and latch bar is checked against the floors of its **duty** (P7,
`references/design-mechanisms.md`, "Mechanisms that carry load") before the fit, not after the print,
and gets a hand calculation. The duty decides the rule and the load case:

| Duty | What | Floors | Load case |
|---|---|---|---|
| `latch` (default) | a hand pushes, pulls, pinches or snaps it, or a lever amplifies the force: latches, catches, levers, clamps, a latch's pivot pin, a hinge leaf used as a lever | the field minimums (pin ≥ 3.2, pin wall ≥ 2.2, member ≥ 2.5 thick and ≥ 4 wide, knuckle ≥ 4 long) | the hand-force key that matches the operation × the lever ratio |
| `lid` | a lid, door or flap hinge with alternating knuckles (3 or more required, odd recommended), no lever between hand and pin | only what prints (pin 2.0, wall and leaf 1.2, knuckle 2 mm); the size comes from `strength.py hinge` at SF ≥ 2, the coupon print on top | the open lid pulled away from the box: `finger_pull` shared by the moving knuckles, no lever ratio; levering it past its stop is misuse: "don't force the lid past fully open" goes into `_assumptions` and is said at delivery |
| `decorative` | carries nothing | the same floors | none |

Snap arms and other flexures designed by the strain formula have no duty: they are exempt from
the floors and follow the snap-fit check (`references/design-features.md`, "Snap fits"). Their load case
is their own deflection or release force (P there, at full undercut), not a hand-force key:
`strength.py snap` with the arm's `length`, `h`, `b` and `undercut` (and `repeated`, true for a
snap opened often: a params.json boolean such as `"snap_repeated": true`, linked with `--param
repeated=snap_repeated`) checks the strain against the limit and gives that force and the
insertion and release forces; a straight arm can also go through `strength.py beam` with that
force as its load and SF 3, both parameters.

**Link every input to the build.** Run strength.py as `--from-build out/build.json --part NAME`
with a `--param INPUT=PARAM` for every size, choice and flag of the member (h, b, length, d,
support, orientation, `repeated`, `load_across_layers`, sf when it is not 2, the load when it is
a force in N), each a parameter of the generator (Phase 3); a flag is a params.json `true` or
`false`. The phone stand's ribbon, and the hinge of a lid with a latch:

```bash
python3 "$SKILL_DIR/scripts/strength.py" beam --from-build out/build.json --part sled \
  --param h=ribbon_t --param b=ribbon_w --param length=ribbon_len --param support=ribbon_support \
  --param sf=ribbon_sf --load finger_push > out/strength_ribbon.json
python3 "$SKILL_DIR/scripts/strength.py" hinge --from-build out/build.json --part lid \
  --param pin_d=hinge_pin_d --param knuckle_d=hinge_knuckle_d --param knuckles=hinge_knuckles \
  --param length=hinge_len --param gap=hinge_clearance --param clearance=hinge_clearance \
  --param pin=hinge_pin --param duty=hinge_duty --param orientation=hinge_orient --load finger_pull \
  > out/strength_hinge.json
```

The material is the part's (`_material`, `_parts.<name>.material`; `--material` is refused). A
hand-force key (`--load finger_push`) is a table value, and an input left out takes strength.py's
own default (`sf` 2, `orientation` z): neither counts as typed in. An input typed on the command
line (`--h 6`, `--support cantilever`, `--sf 3`, `--repeated`, `--load 141.2`) is `manual` in the
report's `inputs_from`, even when it equals the parameter: such a report can size a member, but it
is never evidence of a `use` promise. A parameter the build did not record is an error that names
it: add it to `DEFAULTS` or `PARAMETERS` (to params.json for a build of scope `overrides`) and
build again. Save each report and declare it in `_verify.strength`. **After any change to a linked
parameter, to the part or to its material, run the same command again**: finalize names what
changed ("h was ribbon_t = 4.5, now 6.0") and the member is not verified until then. The ribbon at
4.5 mm read WARN at SF 3 (1.88); at 6.0 it passes (3.34).

(`pin`, `beam`, `link`, `bearing`, `hinge`, `snap`; loads from a cited hand-force table, or a
force in N that is a parameter (`--param load=latch_load`: the key's force × the lever ratio,
worked out by you); materials from Bambu Lab data sheets, `orientation` xy or z for the layer
direction, `gap` for the print-in-place gap at a pin's root or between knuckles, `sf` 2 by
default; `references/materials.md`. The `hinge` case takes the hinge as `parts.hinge` builds it,
an integral or a loose pin, with the pull taken to cross the layers (the axis prints flat and
the pull turns with the lid: shear and the knuckle wall use the Z strength); `parts.hinge` has
one `clearance` for the radial clearance and the axial gap, so link it to both `gap` and
`clearance`; with `duty` it compares pin, wall, knuckle length and, for a lid, the knuckle count
with that duty's floors.) Record the load case, its share and the ratio in `_assumptions`.
FAIL → redesign. WARN, or no proven reference to compare
with → **print the mechanism first**, those parts whole (a coupon part for less), a few grams,
which the user tries before the full part (the same idea as the fit test; a Bambu job lists
only those parts; `references/parts.md`, "Printing the mechanism first"). Save its JSON: a test
print's sha256 comes from it.

```bash
mkdir -p out/mech && python3 "$SKILL_DIR/scripts/build.py" run model.py \
  --params .3dprint/params.json --out out/mech --only latch,keeper \
  --printer .3dprint/printers.json > out/mech/build.json
```

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

## A hand calculation checked on the built part

Where a hand calculation or a fit assumed a size the generator makes from others (the lip top =
seat + lip height, the floor left under a channel, a wall after a cut), measure it on the built
STL with `measure.py ... --expect` and save the report (`references/measure.md`, "A number kept
as evidence"). For the phone stand, a slice across the lip expects its top at 17.5 mm or more
(the 10 mm seat plus half the 15 mm phone), saved as `out/m_lip.json`. Declare it in
`_verify.measurements`, with the `dims` its target comes from, and name it in the promise.
Report a hand-calculated size as a number only when a measurement or a joint checks it; say any
other one is "a hand calculation, not checked on the model". A rebuilt part makes the report
stale: measure again.

## Fit test first

When the part must fit an existing object whose shape is not known exactly (no caliper numbers,
no official spec; an official size without a tolerance counts as not known exactly when the
fit's clearance is smaller than its likely tolerance): make test pieces of the mating profile, a
few grams each, in three clearance steps marked with 1, 2, 3 holes:

```bash
python3 "$SKILL_DIR/scripts/fit_test.py" --profile rounded --size 45.1,14.0 --radius 2 --out out/fit
```

(`--profile rect | rounded | circle | polygon`, `--mode ring` for an object that goes into the part,
`--mode plug` for a part that goes into the object; `--clearance`, `--step`, `--steps`;
`--bambu-template` also writes a `bambu3mf.py` job.) The JSON's `how_to_read` tells the user
what to try; build the real part with the step that fits. The pieces carry no model hole
compensation: say so (`references/tolerances.md`, F1). If the user cannot test now, build to the
middle step and record that in `_assumptions`; the same for a skipped mechanism-first print
("latch pin Ø3.2: not confirmed by a test print"; "lid hinge Ø2.4 in Ø7.4 knuckles: coupon not
printed"). Print the test pieces and the final part with the same printer, filament and process
preset: another preset changes the fit.

## Test prints as evidence

A print the user makes before the delivery (a mechanism-first print, the part itself to try a
cable or a fit) can stand for promises. Record it in `_verify.test_prints` from the user's
report, never from your expectation, with the sha256 of each printed part from the build JSON
of the build they printed (`out/build.json`, or `out/mech/build.json`) and the other fields in
`references/checks.md`, "Test prints". Hand the print over with the delivery's printer,
filament and process preset: when the preset is known, `_print.preset` holds it before the first
test print (`references/phase-2-printer-dimensions.md`, "Material and process preset"; unknown,
the key stays out and the print stays `assumed` on the preset unless a delivered Bambu project
names one). A print in another material, on another printer, in another orientation or with
another preset does not verify; a rebuilt part makes it stale, and only a new print renews it.
`fit_test.py` pieces are not parts of the build: record them without `promises` and build the
part with the step that fits.

## Leaving Phase 4: every promise has a state

Phase 4 ends when finalize names no error: `promise_errors` is empty and the `use` tier is not
`error`. The evidence need not be complete. After the last full build (saved as
`out/build.json`), with the reports declared in `_verify`, run finalize; it is cheap and
delivers nothing:

```bash
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json
```

Read `use`, `promise_errors` and each promise's `state` and `reasons` (`references/checks.md`).
Fix every error it names now: a promise declared wrongly (a missing field, a name with no entry, a
dims value that differs from params.json), and any other declaration (a dims, accepted, seen or
test print entry, `_material`, `_print`), which makes the tier `error` with no promise in error. A
`failed` promise is never accepted or excluded away: go back to the phase of the evidence that
failed and fix it (G7). Run again the evidence a change made stale, as its reason says (the fit,
the `strength.py --from-build` command, the measurement, a new image for the user).

**A look belongs to its image.** The user's look is evidence for the `seen` entry of the image
they looked at, and nothing more. A `look` promise added after they looked, or a `seen` entry a
rebuild made stale, needs an image of the current build and a new look from the user ("The end
is flatter now: does it look right to you?"). An old look is never copied onto a new image, nor
turned into `excluded` or `accepted`. A promise whose new image the user does not judge is
decided below like any other.

Name every other promise that is not `verified` to the user, with its reason in plain words, and
decide each one together:

- **Make the evidence.** Run the check it still lacks, or the user measures the object (Phase 2,
  step 3, records it) or prints the part or the mechanism and reports back (a test print, above).
- **Go on with it assumed**, only for a promise finalize reports `assumed` (its evidence passed
  but rests on a size nobody measured, or on a preset not recorded). It stays `assumed` and is
  named at delivery with what it rests on. No decision makes a `not verified` promise assumed.
- **A prototype**, for a `not verified` promise the user agrees to take unproven, or hands back
  to you (below): it is delivered unproven. Add the `_assumptions` line `"<promise id>: delivered
  as a prototype, not verified"`, word for word (finalize reads it and marks the promise
  `"prototype": true`), ending in a note in parentheses that says who chose it. When the user
  agreed, the note is required and holds their reply, word for word, the one place it is kept
  (`"flat-end: delivered as a prototype, not verified (the user: \"I have no time for a test
  print now, just go on\")"`). Otherwise it is recommended: `(the user handed the decision to
  me)`, or `(unattended run)`. It stays `not verified`, and the delivery message opens with it.
- **The user excludes it**: drops it, or takes it unverified. It stays in the list as `excluded`,
  through an entry in `_verify.accepted` whose `reason` is their reply, word for word:
  `{"promise": "cable-bend", "reason": "I'll try it with my own cable", "by": "user"}`.

**What counts as agreement.** Three records need it: excluding a promise (`_verify.accepted` with
`promise`), accepting a WARN (`_verify.accepted` with `check`, Phase 5) and, in an attended run,
delivering a `not verified` promise as a prototype (its `_assumptions` line). Agreement is the
user's reply to a question that named that promise or warning, said in plain words what taking it
means (the promise stays unverified, or the warning stays, and what that can cost) and offered
the choices; the reply takes that option. Record the reply word for word: as the entry's
`reason`, or, for a prototype, in its line's note. For `cable-bend`:
"That the cable bends down without a kink is not checked: it may kink at the lip. Shall I make a
test piece, or do you take it as it is, unchecked?", and the reply "I'll try it with my own
cable". "Just go on" agrees when going on as it is was the option named: "The flat end is not
checked since the last change. A test print would show it; without one it goes out as a
prototype, and it may rock" → "I have no time for a test print now, just go on".

None of these is agreement, and none is ever recorded as one:

- **A reply that hands the decision back to you** ("I'm not sure, you decide", "I'll leave it to
  you"). The decision is then yours, and yours cannot be the user's: a `not verified` promise
  gets evidence you can make yourself, or goes out as a prototype, the unattended default; a WARN
  is fixed, or left unaccepted and named at delivery (it stays in `open`). Either way an
  `_assumptions` line says the user handed it back: the prototype line's note, `(the user handed
  the decision to me)`, or for a WARN a line of its own (`"cap P3: the user handed the decision
  to me; not accepted"`). Never `excluded`, never `accepted`.
- **An approval of something else**: a look ("The shape looks good") is evidence for that image's
  `seen` entry and nothing more; a reference or concept choice; "carry on" after a progress note.
- **An earlier answer to another question, or silence.**

**When to ask.** Whenever finalize first reports a promise not verified, in Phase 4, 5 or 6,
including a promise added late and one a late change made stale that no new evidence renews.
Before the delivery message, no promise goes out as a prototype, excluded or with an accepted
WARN that the user was not asked about in a message that named it, except the defaults above
and those of an unattended run, each with its `_assumptions` line.

Run finalize again after each change. In an unattended run nobody can agree, so nothing is
excluded or accepted: an `assumed` promise goes on assumed, one `not verified` is delivered as a
prototype (its line as above, noted `(unattended run)`) and a WARN is fixed or left in `open`;
each decision taken alone has its `_assumptions` line and is said at the top of the delivery,
before any result.
