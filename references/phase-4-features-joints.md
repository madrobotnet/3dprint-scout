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
evidence of a promise. Run every check from the project folder with relative paths, as below
(`references/checks.md`).

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
a sweep through the travel it needs (`--sweep-*`), its joint declared `"sweep": true`; a part
built to a standard is fitted against a proxy of the standard's counterpart: both in
`references/phase-4-mechanisms.md`. When the mating object has no closed mesh (a plug, a phone,
a housing), fit against a proxy of it (below). The report records the sha256 of both STLs; a
rebuild of either part makes it stale (`--check`, Phase 5). `--min-clearance` is the clearance
the model is built with, model hole compensation included (`references/tolerances.md`, F1).

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
the floors and follow the snap-fit check (`references/design-features.md`, "Snap fits"), loaded
by their own deflection or release force, not a hand-force key (`strength.py snap`).

**Link every input to the build.** Run strength.py as `--from-build out/build.json --part NAME`
with a `--param INPUT=PARAM` for every size, choice and flag of the member (h, b, length, d,
support, orientation, `repeated`, `load_across_layers`, sf when it is not 2, the load when it is
a force in N), each a parameter of the generator (Phase 3); a flag is a params.json `true` or
`false`. The phone stand's ribbon (a lid hinge's command: `references/phase-4-mechanisms.md`):

```bash
python3 "$SKILL_DIR/scripts/strength.py" beam --from-build out/build.json --part sled \
  --param h=ribbon_t --param b=ribbon_w --param length=ribbon_len --param support=ribbon_support \
  --param sf=ribbon_sf --load finger_push > out/strength_ribbon.json
```

Only a hand-force key may be typed in: any other input typed on the command line makes the report
`manual`, which can size a member but never verifies a `use` (what each input means, the cases,
the hinge and the snap: `references/phase-4-mechanisms.md`). Save each report and declare it in
`_verify.strength`. **After any change to a linked parameter, to the part or to its material,
run the same command again**: finalize names what changed ("h was ribbon_t = 4.5, now 6.0") and
the member is not verified until then. Record the load case, its share and the ratio in
`_assumptions`.

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

A `lid` hinge always gets a coupon on top of SF ≥ 2, and a mechanism built into the walls gets
one cut from the same section (`references/phase-4-mechanisms.md`, "Coupons and the lid hinge").

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
what to try; build the real part with the step that fits. Offer the pieces in the look (Phase 3,
item 5), not in a stop of their own. The pieces carry no model hole
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
names one). A print on another printer, in another orientation or with another preset does
not verify; a rebuilt part makes it stale, and only a new print renews it.

**Another filament, or a piece of the part** (since 0.10.0). A test in another filament (PLA for
a PETG part: the question comes often) counts for the geometric promises only, the fits, gaps,
passages and motions by hand, never for a use that carries a load (`load`, or `strength`
evidence). Say so when you offer it, before the user picks a filament: it shows the fit, not the
strength, and a fit with under 0.2 mm of play may come out differently in the final filament
(finalize warns). A **section piece**, the part cut by a box, saves time and filament on a big
part:

- Give the generator an optional cut, a `section_box` parameter (default `None` in `DEFAULTS` /
  `PARAMETERS`), applied last as the body intersected with the box.
- Build it from a second params file, `.3dprint/piece.json` (params.json plus the box, the
  part's `expect` set to the piece's size), into its own folder: `build.py run model.py --params
  .3dprint/piece.json --out out/piece > out/piece/build.json`. Never move the piece; the slicer
  puts it on the bed.
- Choose the box so it holds all of the part within 1 mm plus the fit's play of each mating
  part (through the whole turn of a moving joint) and the whole cross-section of each sliced
  measurement; keep a flexing member (a snap arm) whole inside it.
- Record the print with `parts.<name>`: the sha256 from `out/piece/build.json`, the material it
  was printed in, and `section` with the same box and the piece's STL path (`references/checks.md`,
  "Test prints").

finalize cuts the current part with the box itself and compares it with the piece, so a section
stays valid after a rebuild that changed nothing inside the box. Reading it: `"scope":
"geometry"` on the evidence means it counted; "checks X outside the section box" means a bigger
box; "is not X cut by its box as X is now" means the part changed inside the box: print again.
Record every print anyway (it is the user's result) and say in its `note` what it showed.
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
the `strength.py --from-build` command, the measurement, a new image for the user). A value of
the parameter table that changed since the user confirmed it (a wall thickened to pass a check)
is a changed design choice: name it with its old and new value and stop for it, in the look when
it comes before it (Phase 3, item 3), otherwise in a stop of its own.

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
  A `by_hand` use whose motion no passed print confirms is decided the same way, whatever its
  fits give: name the motion as not confirmed, offer the test print, and when the user takes it
  unproven, add the same line. finalize marks it a prototype and it keeps its state (verified on
  its fits, say, with the motion unproven).
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
including a promise added late and one a late change made stale that no new evidence renews. For
a simple part the first time is the look (Phase 3, item 5): its offer, naming the promise, what
goes unconfirmed and what it can cost, is this question, and the user's reply to it decides the
promise. Ask again only for a promise the look did not name, or one whose reason changed since.
Before the delivery message, no promise goes out as a prototype, excluded or with an accepted
WARN that the user was not asked about in a message that named it, except the defaults above
and those of an unattended run, each with its `_assumptions` line.

Run finalize again after each change. In an unattended run nobody can agree (SKILL.md,
"Unattended runs"): an `assumed` promise goes on assumed, a `not verified` one is a prototype
noted `(unattended run)`, and a WARN is fixed or left in `open`.
