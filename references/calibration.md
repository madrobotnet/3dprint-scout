# The user's calibration log

`.3dprint/calibration.json` in the user's project holds what their own printer, filament and
nozzle actually did: which fit-test ring fit, what clearance a hole came out at, which
mechanism member held or broke and under what load. It lives with the project, never in
this repository, and it holds print results only. `calibration.py` refuses what it can
recognise as identifying a person or a machine (value names with id, code, device, mac,
serial, token, account, mail, ip, user or name in them; notes with an IP, IPv6 or MAC
address, an e-mail, a run of six or more digits or a long letter-digit token, or the words
serial, access code, account, password; printers and materials that are not short lowercase
ids; a material spelt like `PLA Basic` is stored as `strength.py`'s `pla_basic`). That
reduces the risk, it cannot guarantee it: the script cannot tell a person's name in a note,
so the agent never writes one, and values are numbers under 10 000 (mm, N).

## When to read it (Phase 2)

Before the dimension table:

```bash
python3 "$SKILL_DIR/scripts/calibration.py" lookup --file .3dprint/calibration.json --printer x2d --material pla_basic
```

`worked` gives, per value name, the newest number from a result that fit, worked or was
measured; `bounds` gives the newest failed, tight and loose numbers, kept apart so a
failure is never read as a setting (entries are ordered by date, then by their order in the
file, newest first). Two priorities, not one: for **how this printer prints** (clearances,
hole sizes, member sizes that held), the user's calibration > the starting points in
`design.md` and `tolerances.md`; for **the size of the object the part must fit**, the
user's caliper > the official spec > secondary sources. A clearance that fit on this printer
beats the table; a member that broke on this printer is a floor to stay above **for the
same kind of member under the same kind of load**: a stub pin that broke in a hand-operated
latch does not set the floor for a lid hinge's integral pin. So look a mechanism up by its
kind (`--feature mechanism --kind lid_hinge`): only entries of that kind set `worked` and
`bounds`, entries without a kind are listed under `unclassified` so they are seen but set no
floor, and `kinds` counts what the log holds. Say in the dimension table which values came
from the log ("calibration, 2026-10-16, lid_hinge").

## When to write it (after a print)

When the user reports a result (a ring that fit, a hole that was tight, a latch that broke
or held), **ask once, in the user's language** (the gist: "Shall I record this for your X2D
with PLA Basic, so the next design starts from it?"). On yes, run `add`; on no or no answer,
do not write. Never write silently, never in an unattended run, and never record a failure
as a success.

```bash
python3 "$SKILL_DIR/scripts/calibration.py" add --file .3dprint/calibration.json --printer x2d --material pla_basic \
  --nozzle 0.4 --layer 0.2 --feature fit --result fits --value clearance_per_side_mm=0.3 --value profile_w_mm=45.1 \
  --note "fit-test ring 2 slid onto the housing by hand without rattle"
```

| Field | Values |
|---|---|
| `feature` | `fit` (fit-test rings and plugs), `clearance` (a measured moving-part gap), `hole` (a measured hole), `mechanism` (a member under load), `other` |
| `--kind` | the kind of member, a short lowercase id (a letter, then letters, digits or underscores, 24 at most): `latch`, `lid_hinge`, `lever`, `clamp`, `snap`. Optional for every feature, give it for every `mechanism` entry so its floors apply to the same kind; the same identifier checks as a printer id (no capitals, spaces or names) |
| `result` | `fits`, `tight`, `loose`, `worked`, `failed`, `measured` |
| `--value name=number` | numbers only, names such as `clearance_per_side_mm`, `pin_d_mm`, `pin_wall_mm`, `arm_mm`, `hole_d_measured_mm` |
| `--load` | a force in N or a `strength.py` key (`finger_push`, ...) when a mechanism was loaded |
| `--note` | free text, up to 500 characters, no personal or machine identifiers (the checks above) |
| `--printers` | `.3dprint/printers.json`: when given, the printer must be one of its ids |

## Example: a field comparison turned into entries

The two latches of `design.md` ("Mechanisms that carry load"), written as a user would
record them (generic wording; dates and sizes as in that section):

```bash
python3 "$SKILL_DIR/scripts/calibration.py" add --file .3dprint/calibration.json --printer x2d --material pla_pure \
  --nozzle 0.4 --layer 0.2 --feature mechanism --kind latch --result failed --load finger_push \
  --value pin_d_mm=2.6 --value pin_wall_mm=1.3 --value arm_mm=1.2 --value engagement_mm=2.0 \
  --note "print-in-place draw latch: stub pins, knuckle rings and 1.2 mm arms all broke on first use"
python3 "$SKILL_DIR/scripts/calibration.py" add --file .3dprint/calibration.json --printer x2d --material pla_basic \
  --nozzle 0.4 --layer 0.2 --feature mechanism --kind latch --result worked --load finger_push \
  --value pin_d_mm=3.24 --value pin_wall_mm=2.2 --value rail_w_mm=4.25 --value rail_min_mm=2.5 --value engagement_mm=4.25 \
  --note "print-in-place box latch, 3 walls, 10 % infill: pin on the lever, both ends in 4.25 mm rails, works after many uses"
```

A later `lookup --feature mechanism --kind latch` then shows `worked.pin_d_mm` 3.24 and
`bounds.pin_d_mm.failed` 2.6: the value to start from and the floor to stay above for the
next latch. A lid hinge's coupon result is its own kind (`--kind lid_hinge`, with
`pin_d_mm`, `knuckle_d_mm`, `knuckle_len_mm`, `knuckles` and the load it was pulled with); a
`lookup --kind lid_hinge` leaves the latch entries out, and lists an old entry that has no
kind under `unclassified`, where it sets no floor.
