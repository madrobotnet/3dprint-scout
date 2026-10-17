# The user's calibration log

`.3dprint/calibration.json` in the user's project holds what their own printer, filament and
nozzle actually did: which fit-test ring fit, what clearance a hole came out at, which
mechanism member held or broke and under what load. It lives with the project, never in
this repository, and it never holds serial numbers, IP addresses, access codes, account
ids or names (`calibration.py` refuses them).

## When to read it (Phase 2)

Before the dimension table:

```bash
python3 "$SKILL_DIR/scripts/calibration.py" lookup --file .3dprint/calibration.json --printer x2d --material pla_basic
```

`latest` gives, per value name, the newest number for that printer and material. Priority
for any value: **the user's caliper measurement or their own calibration > the official
spec > the starting points in `design.md` and `tolerances.md`**. A clearance that fit on
this printer beats the table; a member that broke on this printer is a floor to stay above.
Say in the dimension table which values came from the log ("calibration, 2026-10-16").

## When to write it (after a print)

When the user reports a result (a ring that fit, a hole that was tight, a latch that broke
or held), **ask once**: "Shall I record this for your X2D with PLA Basic, so the next design
starts from it?" On yes, run `add`; on no or no answer, do not write. Never write silently,
and never record a failure as a success.

```bash
python3 "$SKILL_DIR/scripts/calibration.py" add --file .3dprint/calibration.json --printer x2d --material pla_basic \
  --nozzle 0.4 --layer 0.2 --feature fit --result fits --value clearance_per_side_mm=0.3 --value profile_w_mm=45.1 \
  --note "fit-test ring 2 slid onto the housing by hand without rattle"
```

| Field | Values |
|---|---|
| `feature` | `fit` (fit-test rings and plugs), `clearance` (a measured moving-part gap), `hole` (a measured hole), `mechanism` (a member under load), `other` |
| `result` | `fits`, `tight`, `loose`, `worked`, `failed`, `measured` |
| `--value name=number` | numbers only, names such as `clearance_per_side_mm`, `pin_d_mm`, `pin_wall_mm`, `arm_mm`, `hole_d_measured_mm` |
| `--load` | a force in N or a `strength.py` key (`finger_push`, ...) when a mechanism was loaded |
| `--note` | free text, up to 500 characters, no personal or machine identifiers |

## Example: a field comparison turned into entries

The two latches of `design.md` ("Mechanisms that carry load"), written as a user would
record them (generic wording; dates and sizes as in that section):

```bash
python3 "$SKILL_DIR/scripts/calibration.py" add --file .3dprint/calibration.json --printer x2d --material pla_pure \
  --nozzle 0.4 --layer 0.2 --feature mechanism --result failed --load finger_push \
  --value pin_d_mm=2.6 --value pin_wall_mm=1.3 --value arm_mm=1.2 --value engagement_mm=2.0 \
  --note "print-in-place draw latch: stub pins, knuckle rings and 1.2 mm arms all broke on first use"
python3 "$SKILL_DIR/scripts/calibration.py" add --file .3dprint/calibration.json --printer x2d --material pla_basic \
  --nozzle 0.4 --layer 0.2 --feature mechanism --result worked --load finger_push \
  --value pin_d_mm=3.24 --value pin_wall_mm=2.2 --value rail_w_mm=4.25 --value rail_min_mm=2.5 --value engagement_mm=10.8 \
  --note "print-in-place box latch, 3 walls, 10 % infill: through pin in two rails, works after many uses"
```

A later `lookup --feature mechanism` then shows `pin_d_mm` 3.24 as the latest value that
worked and 2.6 as one that failed, which is exactly the floor the next latch starts from.
