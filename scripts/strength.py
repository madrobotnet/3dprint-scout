#!/usr/bin/env python3
"""
strength.py - quick hand calculations for members that carry load: pins, beams and levers,
links, the wall around a pin hole, a print-in-place hinge with alternating knuckles. Standard
library only; one JSON document per call.

  python3 strength.py pin --d 3.2 --engagement 4 --gap 0.3 --shear double --support stub --load finger_push --material pla_basic --orientation xy
  python3 strength.py pin --d 3.2 --engagement 10 --support-t 4 --gap 0.3 --shear double --load finger_push --material pla_basic --orientation xy
  python3 strength.py beam --b 6 --h 3 --length 20 --support cantilever --load 70 --material petg_basic --orientation z
  python3 strength.py link --b 4 --h 2.5 --length 15 --bow 0 --load finger_push --material pla_basic --orientation xy
  python3 strength.py bearing --d 3.3 --t 8 --edge 2.2 --load finger_push --material pla_basic --orientation xy
  python3 strength.py hinge --pin-d 2.4 --knuckle-d 7.4 --knuckles 5 --length 36 --gap 0.3 --clearance 0.3 --pin integral --duty lid --load finger_pull --material pla_basic --orientation xy
  python3 strength.py snap --length 16 --h 1.6 --b 6 --undercut 0.8 --material pla_basic --orientation xy [--repeated]
  python3 strength.py beam --from-build out/build.json --part sled --param h=ribbon_t --param b=ribbon_w --length 20 --load 70 --orientation xy
  python3 strength.py materials            # the data table with its sources
  python3 strength.py loads                # the hand-force table with its source
  python3 strength.py duties               # the P7 floors per duty (latch, lid, decorative) with their sources

Cases
  pin      transverse shear on one plane (--shear single) or two (double), peak 4/3 of the
           average over the circle: tau = 4/3 F / (n pi d^2 / 4). Bending by support type:
           --support stub   a pin that grows out of one part and sits in the other: a cantilever
                            from its root face, its load spread evenly over the engagement L
                            inside the mating part, with the gap g between the root face and
                            the mating part added to the lever arm: M = F' (g + L / 2). With
                            --shear double both ends are stubs and each carries F' = F / 2
                            (a pin formed on a lever, its ends in two rails: L = rail thickness).
           --support through  a loose pin through two supports of thickness a (--support-t),
                            loaded by the member of width b (--engagement) between them, with
                            the gap g on each side: the clevis formula M = F (b + 2 a + 4 g) / 8,
                            every bearing load spread evenly (a load concentrated at the
                            centre would give up to F (b + 2 a) / 4: narrow the member, not
                            the formula). A through pin is in double shear.
           Bending stress 32 M / (pi d^3). --load-across-layers: the pin lies flat and its
           load crosses the layers, so the shear slides layer on layer and uses the Z strength
           while bending keeps --orientation; --orientation z (a pin standing up) uses Z for both.
  beam     rectangular section b x h: bending stress M c / I and tip deflection, cantilever
           with an end load (M = F L, d = F L^3 / 3 E I) or simply supported with a centre
           load (M = F L / 4, d = F L^3 / 48 E I).
  link     a strut in tension: F / A, plus bending from a bow (sagitta) when the link is
           curved: M = F x bow, stress F / A + M c / I about the thin axis.
  bearing  the wall around a pin hole: bearing stress F / (d t) and tear-out shear on the two
           planes between the hole and the nearest edge, F / (2 e t).
  hinge    a print-in-place hinge as parts.hinge builds it: k knuckles alternating A, B, A ...
           along the pin, each b long (--knuckle-len, or --length with b = (length - (k - 1)
           gap) / k), gap g between them, the pin with radial clearance c in B's holes
           (parts.hinge has one `clearance` for both: pass the same value to --gap and
           --clearance). The pin belongs to leaf A (--pin integral, the default) or is a loose
           pin through every knuckle (--pin loose). The n_B = k // 2 moving (B) knuckles share
           the load equally, P = F / n_B each (an assumption, stated). A B knuckle between two
           A knuckles is "interior"; with k even the last knuckle is a B on the pin's free end
           ("end"); that end stub is far more compliant than an interior span, so the equal
           share is then optimistic for the interior knuckles (noted).
           Integral pin, interior B: the pin is built in at both A faces, a fixed-fixed span
             L = b + 2 g with P spread over the middle b. End moment (the mean of the simply
             supported moment diagram, which is what the zero end slopes require)
             M_end = P (6 g^2 + 6 g b + b^2) / (12 L); mid-span M_mid = P (2 L - b) / 8 - M_end;
             M = max(M_end, M_mid). Limits: g = 0 gives P b / 12, b -> 0 gives P L / 8. Two
             shear planes: tau = 4/3 P / (2 A).
           Integral pin, end B (k even): a stub, M = P (g + b / 2), one shear plane. An odd
             knuckle count puts every moving knuckle between two fixed ones (warned).
           Loose pin: each interior B as the clevis of the pin case with a = the A knuckle
             length (= b): M = P (b + 2 a + 4 g) / 8, two planes; an end B as a stub. The A
             knuckles then bear the pin too: P / 2 from an interior B neighbour, and from an
             end B neighbour 1.5 P (the overhang's statics on a two-support pin: P plus the
             overhang moment carried over the next span, P s / 2 s; exact for k = 4, an upper
             bound for longer hinges) or P when k = 2; the most loaded A is checked.
           Layers: parts.hinge prints the axis flat and the pull turns with the lid, so the
           load is taken to cross the layers: pin shear and the knuckle wall's bearing and
           tear-out use the Z tensile strength whatever --orientation says; bending runs along
           the pin and uses the bending strength of --orientation (xy for a flat axis, z for a
           standing one). --load-across-layers is accepted for the hinge and changes nothing.
           Bending 32 M / (pi d^3); shear 4/3 P / (n A) against 0.58 x tensile Z. Per B knuckle
           the wall: bearing P / (d b) and tear-out P / (2 e b) with e = the wall above the
           hole, R - (r + c) sqrt(2) for a teardrop hole (--hole teardrop, parts.hinge),
           R - (r + c) for a round one. With --duty latch | lid | decorative a "minimums" block
           compares pin, wall and knuckle length (and, for lid, the knuckle count: 3 or more,
           odd recommended) with that duty's P7 floors (DUTIES below; a floor not met makes
           the gate FAIL); without it a note says P7 still needs them. Duty lid refuses --sf
           under 2 and at WARN says to grow the hinge: the coupon print is required on top of
           the margin and never replaces it. Duty decorative: the floors alone decide the gate,
           the checks are reported with "informational": true. The "moments_nmm" keys depend
           on the layout: interior_end_nmm and interior_mid_nmm (integral, interior knuckles),
           interior_nmm (loose, interior knuckles), end_nmm (an end knuckle, k even).

  snap     a straight cantilever snap arm printed flat, as parts.snap_hook builds it: length L
           (--length), thickness h in the flexing direction (--h), width b (--b), deflected by
           the undercut y (--undercut) at full travel. Strain at the root e = 1.5 h y / (L^2 Q)
           (BASF snap-fit design manual; Q 1 for a rigid wall, about 2 for a thin one, --q)
           against the material family's one-time design strain (SNAP_STRAIN, the copy
           parts.snap_fit_check uses; x 0.6 with --repeated for a joint opened often): PASS or
           FAIL, no margin on top (the limit holds it). The deflection force P = 3 E I y / (Q L^3)
           is the arm's own load (no --load: a hand force is bounded by the release force); the
           bending stress at the root, sigma = E e, is checked against the bending strength at
           --sf. Insertion and release forces over the entry ramp (--entry-angle, 30) and the
           retention face (--retention-angle, 90 = none without a release window):
           W = P (mu + tan a) / (1 - mu tan a) with --friction (0.3, a starting point).

Loads: a number in N, or a hand-force key from the table (finger_push, finger_pull,
pinch_lateral, pinch_palmar, grasp) whose design value is the male mean plus one standard
deviation from DiDomenico & Nussbaum (2003); the lever ratio of a latch is NOT applied, pass
the amplified force yourself. Record the load in _assumptions. A lid hinge takes finger_pull
(the open lid pulled away from the box) shared by its moving knuckles, no lever ratio
(design.md, "Mechanisms that carry load").

Materials: Bambu Lab technical data sheets (official PDFs on store.bblcdn.com, retrieved
2026-10-18), X-Y and Z values as published. --orientation xy when the stress acts within the
layer plane (a member lying flat, bent sideways or along its length), z when it crosses the
layers (a pin standing up, a lever bent so its layers peel). Default z: conservative.

Linking to a build: --from-build BUILD_JSON --part NAME takes the material the build.py report
(schema 3dprint-scout.build/1) recorded for the part (_parts.<part>.material, else _material;
--material is then an error, and a part with no material is one too), and each --param
INPUT=PARAM (repeatable) takes the input INPUT, a name as it appears in the report's "inputs"
(h, b, length, d, t, edge, pin_d, knuckles, orientation, support ...), from the build's
parameters.values[PARAM] (a dotted path reaches into a nested object: plug.w). An input is
given one way: on the command line or through --param, not both. A linked value is checked as
its option is: a finite number (not true or false), above zero for a size, zero allowed where
the option allows it (gap, bow, clearance, friction), a whole number for knuckles, one of the
option's choices for orientation, shear, support, hole, pin and duty, true or false for
repeated and load_across_layers. A build of scope "overrides" records only what params.json
passed, not the generator's defaults: a value left to a default goes into params.json first.
The report then carries "from_build": the build as given, the part, the part's sha256 and
material in the build, and per linked input its param and value (finalize.py compares them
with the current build). Every calculation report carries "inputs_from", the origin of each
key of "inputs": param:<PARAM>; table:<key> (a hand-force key given as --load, a material key
given as --material); build:material; default:<input> (strength.py chose it because nothing
was given: sf, the orientation z, a pin's gap 0, a hinge's 0.3 gap and clearance, snap's q and
angles); manual (a number or choice typed on the command line, even one equal to the default).

Verdict per check: achieved safety factor = material strength / stress. PASS when it reaches
--sf (default 2.0: the TDS specimens are 100 % infill, dried and annealed, real parts have
walls and infill, corners and layer seams, and PLA creeps), WARN when the stress is below the
strength but the margin is short, FAIL when the stress exceeds the strength itself. Shear and
bearing strengths are not on the data sheets: shear = 0.58 x tensile (von Mises), bearing =
tensile; both are stated as assumptions in the output. This is a sizing aid for a hand
calculation, not an analysis: a low margin means "print the member first" (SKILL.md).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

SCHEMA = "3dprint-scout.strength/1"
BUILD_SCHEMA = "3dprint-scout.build/1"
RETRIEVED = "2026-10-18"
SHEAR_RATIO = 0.58          # tau_allow = 0.58 x tensile (von Mises); not on the data sheets
SHEAR_PEAK = 4.0 / 3.0      # transverse shear in a solid round section peaks at 4/3 of the average (neutral axis)
BEARING_RATIO = 1.0         # bearing allowable = tensile strength; conservative, not on the data sheets
DEFAULT_SF = 2.0

# Bambu Lab Technical Data Sheets. Tensile per ISO 527, bending per ISO 178; X-Y = specimen
# printed and loaded in the layer plane, Z = loaded across layers. Specimens: 100 % infill,
# dried and (except PETG Basic, PLA Pure) annealed before testing; values are "typical" and the
# sheets say actual parts depend on printer, settings and geometry. Units: MPa and %.
MATERIALS = {
    "pla_basic": {
        "name": "Bambu PLA Basic", "tds": "V3.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/s7/default/b189de92249a4b9ebed28b8ea1f080f0/Bambu_PLA_Basic_Technical_Data_Sheet.pdf",
        "E": {"xy": 2580, "z": 2060}, "tensile": {"xy": 35, "z": 31}, "elongation": {"xy": 12.2, "z": 7.5},
        "flex_modulus": {"xy": 2750, "z": 2370}, "flex": {"xy": 76, "z": 59},
        "specimens": "220 C nozzle, 35 C bed, 200 mm/s, 100 % infill, annealed and dried 55 C 8 h"},
    "pla_matte": {
        "name": "Bambu PLA Matte", "tds": "V3.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/s7/default/5b061f2feeac4ba88f355a33248bbda7/Bambu_PLA_Matte_Technical_Data_Sheet.pdf",
        "E": {"xy": 1960, "z": 1670}, "tensile": {"xy": 30, "z": 22}, "elongation": {"xy": 14.8, "z": 4.8},
        "flex_modulus": {"xy": 2360, "z": 1770}, "flex": {"xy": 53, "z": 29},
        "specimens": "220 C nozzle, 35 C bed, 200 mm/s, 100 % infill, annealed and dried 55 C 8 h"},
    "pla_pure": {
        "name": "Bambu PLA Pure", "tds": "V1.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/s7/default/0e7400b878d84516a1ae605c1edaeab0/pla_pure_-TDS.pdf",
        "E": {"xy": 2481, "z": 2196}, "tensile": {"xy": 51.5, "z": 30.0}, "elongation": {"xy": 5.6, "z": 2.8},
        "flex_modulus": {"xy": 2880, "z": 2599}, "flex": {"xy": 75, "z": 55},
        "specimens": "H2, 0.4 mm nozzle, 220 C nozzle, 55 C bed, 147 mm/s, 100 % infill, filament dried 50 C 8 h; "
                     "the sheet's comparison table swaps the bending modulus and strength labels, the main table is used"},
    "petg_basic": {
        "name": "Bambu PETG Basic", "tds": "V3.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf",
        "E": {"xy": 2780, "z": 2550}, "tensile": {"xy": 51, "z": 35}, "elongation": {"xy": 9.5, "z": 5.2},
        "flex_modulus": {"xy": 1950, "z": 1740}, "flex": {"xy": 75, "z": 56},
        "specimens": "X1-Carbon, 255 C nozzle, 70 C bed, 150 mm/s, 100 % infill; annealing not recommended"},
    "petg_hf": {
        "name": "Bambu PETG HF", "tds": "V1.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/3a230e260a3a47c2b0db0156e07eef91.pdf",
        "E": {"xy": 1810, "z": 1540}, "tensile": {"xy": 34, "z": 23}, "elongation": {"xy": 8.6, "z": 5.1},
        "flex_modulus": {"xy": 2050, "z": 1810}, "flex": {"xy": 64, "z": 48},
        "specimens": "255 C nozzle, 70 C bed, 200 mm/s, 100 % infill, annealed and dried 75 C 8 h"},
    "abs": {
        "name": "Bambu ABS", "tds": "V3.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/s7/default/23b4cf2b83d5470bb96d19970b5f3ae8/Bambu_ABS_Technical_Data_Sheet_V3.pdf",
        "E": {"xy": 2200, "z": 1960}, "tensile": {"xy": 33, "z": 28}, "elongation": {"xy": 10.5, "z": 4.7},
        "flex_modulus": {"xy": 1880, "z": 1590}, "flex": {"xy": 62, "z": 39},
        "specimens": "260 C nozzle, 80 C bed, 200 mm/s, 100 % infill, annealed and dried 80 C 12 h"},
    "asa": {
        "name": "Bambu ASA", "tds": "V3.0", "retrieved": RETRIEVED,
        "url": "https://store.bblcdn.com/ad7b08230c164e72856cffbe06bb7dc9.pdf",
        "E": {"xy": 2450, "z": 2120}, "tensile": {"xy": 37, "z": 31}, "elongation": {"xy": 9.2, "z": 4.6},
        "flex_modulus": {"xy": 1920, "z": 1650}, "flex": {"xy": 65, "z": 40},
        "specimens": "260 C nozzle, 80 C bed, 200 mm/s, 100 % infill, annealed and dried 80 C 12 h"},
}

# Peak finger and hand forces, dominant hand, seated, n = 100 (50 male, 50 female), means and
# standard deviations in N: A. DiDomenico, M. A. Nussbaum, "Measurement and prediction of single
# and multi-digit finger strength", Ergonomics 46(15), 2003, pp. 1531-1548, Table 2. Brief peak
# exertions, not sustained use. The design value is the male mean + 1 SD (about the 84th
# percentile of male users): a latch that survives it survives most hands.
LOADS_SOURCE = {"citation": "DiDomenico & Nussbaum, Ergonomics 46(15), 2003, 1531-1548, Table 2",
                "url": "https://stacks.cdc.gov/view/cdc/191543/cdc_191543_DS1.pdf", "retrieved": RETRIEVED,
                "design_rule": "male mean + 1 SD; brief peak, dominant hand, seated"}
LOADS = {
    "finger_push": {"what": "index finger push (poke)", "mean": 45.95, "sd": 17.80, "male_mean": 52.58, "male_sd": 18.01},
    "finger_press": {"what": "index fingertip press, 180 deg distal pad", "mean": 43.05, "sd": 18.43, "male_mean": 50.90, "male_sd": 18.37},
    "finger_pull": {"what": "index fingertip pull, 90 deg distal pad", "mean": 60.09, "sd": 25.24, "male_mean": 70.84, "male_sd": 27.16},
    "pinch_lateral": {"what": "lateral (key) pinch, thumb and index", "mean": 80.93, "sd": 28.15, "male_mean": 97.02, "male_sd": 27.67},
    "pinch_palmar": {"what": "palmar pinch, thumb and index pads", "mean": 54.16, "sd": 18.84, "male_mean": 62.88, "male_sd": 19.20},
    "grasp": {"what": "power grasp, whole hand", "mean": 370.67, "sd": 117.73, "male_mean": 452.44, "male_sd": 102.94},
}
for _k, _v in LOADS.items():
    _v["design_N"] = round(_v["male_mean"] + _v["male_sd"], 1)

# P7 floors by duty (design.md, "Mechanisms that carry load"; the one copy, parts.py imports it).
# latch: the field comparison of 2026-10 (a failed and a working hand-operated print-in-place
# latch, both PLA): pin diameter, wall around the pin hole measured above a teardrop's point,
# member thickness in the bending direction, knuckle length; starting points, not a standard.
# lid / decorative: only what prints (tolerances.md limits: pin 2.0, wall and leaf 1.2, knuckle
# 2 mm); a lid hinge's size comes from the hinge case at SF >= 2 plus a coupon print.
_PRINTS = {"pin_d": 2.0, "pin_wall": 1.2, "member": 1.2, "knuckle_len": 2.0}
DUTIES = {
    "latch": {"floors": {"pin_d": 3.2, "pin_wall": 2.2, "member": 2.5, "knuckle_len": 4.0},
              "what": "anything a hand pushes, pulls, pinches or snaps to operate, or that a lever amplifies: latches, "
                      "catches, levers, clamps, a latch's pivot pin, a hinge whose leaf is used as a lever",
              "source": "design.md, Mechanisms that carry load: field comparison 2026-10 (starting points)",
              "sizing": "the floors, a proven reference when one is at hand, strength.py at the hand force x lever ratio"},
    "lid": {"floors": dict(_PRINTS), "min_knuckles": 3,
            "what": "a lid, door or flap hinge with alternating knuckles (3 or more required, odd recommended) where the "
                    "hand force reaches the pin without a lever multiplying it",
            "source": "tolerances.md limits (what prints); the size comes from strength.py hinge at SF >= 2 under "
                      "finger_pull shared by the moving knuckles, confirmed by a hinge coupon print before the full part",
            "sizing": "strength.py hinge at finger_pull with SF >= 2, then a coupon print (required)"},
    "decorative": {"floors": dict(_PRINTS),
                   "what": "a hinge that carries nothing",
                   "source": "tolerances.md limits (what prints); no calculation",
                   "sizing": "the floors only"},
}
DUTY_NAMES = tuple(DUTIES)

# One-time design strain for a cantilever snap arm printed flat (the beam flexing within the
# layer plane), by material family (the one copy; parts.py reads it from here). Starting
# points, calibrate with a test hook: derived from bulk one-time values (Bayer: PC 4 %,
# PC/ABS 2.5 %) and printed break strains (Fictiv: PLA 4-8 %, ABS 7 %, nylon 4-15 %) with a
# safety factor for layer bonds (references/design.md, snap fits). A joint opened often takes
# 60 % of it (Bayer design guide).
SNAP_STRAIN = {"PLA": 0.010, "PETG": 0.015, "ABS": 0.020, "ASA": 0.020, "PC": 0.025, "PA": 0.030, "NYLON": 0.030}
SNAP_REPEATED = 0.6
SNAP_FRICTION = 0.3         # plastic on plastic, dry: a starting point (BASF snap-fit design manual table), --friction


HINGE_ONLY = ("pin_d", "knuckle_d", "knuckles", "knuckle_len", "clearance", "hole", "pin", "duty")
SNAP_ONLY = ("undercut", "q", "entry_angle", "retention_angle", "friction", "repeated")
# Options of the other cases that mean nothing to a hinge (--length, --gap and --load-across-layers are shared).
NOT_HINGE = ("d", "engagement", "support_t", "shear", "support", "b", "h", "bow", "t", "edge")
CASE_INPUTS = {"pin": {"d", "engagement", "support_t", "gap", "shear", "support", "load_across_layers"},
               "beam": {"b", "h", "length", "support"}, "link": {"b", "h", "length", "bow"}, "bearing": {"d", "t", "edge"},
               "hinge": {"pin_d", "knuckle_d", "knuckles", "length", "knuckle_len", "gap", "clearance", "hole", "pin", "duty",
                         "load_across_layers"},
               "snap": {"b", "h", "length", "undercut", "q", "repeated", "entry_angle", "retention_angle", "friction"}}
# The choices of the categorical inputs, one copy for argparse and --param; --support by case.
CHOICES = {"orientation": ("xy", "z"), "shear": ("single", "double"), "hole": ("teardrop", "round"),
           "pin": ("integral", "loose"), "duty": DUTY_NAMES}
SUPPORTS = {"pin": ("through", "stub"), "beam": ("cantilever", "simple")}
# What a value linked with --param must be, input by input: the rules the options already follow.
# size: a number above zero (mm); positive: above zero; non_negative: zero allowed; whole: an
# integer; flag: true or false; choice: CHOICES / SUPPORTS; load: a force in N or a LOADS key.
INPUT_KIND = {**dict.fromkeys(("d", "engagement", "support_t", "b", "h", "length", "t", "edge", "pin_d", "knuckle_d",
                               "knuckle_len", "undercut"), "size"),
              **dict.fromkeys(("sf", "q", "entry_angle", "retention_angle"), "positive"),
              **dict.fromkeys(("gap", "bow", "clearance", "friction"), "non_negative"),
              **dict.fromkeys(("orientation", "shear", "support", "hole", "pin", "duty"), "choice"),
              "knuckles": "whole", "load_across_layers": "flag", "repeated": "flag", "load": "load"}
LINK_OPTIONS = ("from_build", "part", "param")


class StrengthError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise StrengthError(f"usage error: {message}")


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
def material(key: str) -> dict:
    k = (key or "").lower().replace("-", "_").replace(" ", "_")
    if k not in MATERIALS:
        raise StrengthError(f"unknown material '{key}'; known: {', '.join(MATERIALS)} (Bambu Lab data sheets only; "
                            "another maker's filament needs its own data sheet)")
    return dict(MATERIALS[k], key=k)


def load_value(text) -> tuple:
    """(N, description) from a number or a hand-force key."""
    s = str(text).strip().lower()
    if s in LOADS:
        v = LOADS[s]
        return v["design_N"], (f"{s}: {v['what']}, male mean {v['male_mean']} N + 1 SD {v['male_sd']} N = {v['design_N']} N "
                               f"({LOADS_SOURCE['citation']})")
    try:
        n = float(s)
    except ValueError:
        raise StrengthError(f"--load is a force in N or one of {', '.join(LOADS)}")
    if not math.isfinite(n) or n <= 0:
        raise StrengthError("--load must be a positive force in N")
    return n, f"{n} N given by the caller (record its source in _assumptions)"


def positive(args, *names, unit="mm"):
    for n in names:
        v = getattr(args, n)
        if v is None:
            raise StrengthError(f"--{n.replace('_', '-')} is required")
        if not math.isfinite(v) or v <= 0:
            raise StrengthError(f"--{n.replace('_', '-')} must be a positive number ({unit})")


def non_negative(args, *names):
    for n in names:
        v = getattr(args, n)
        if v is None:
            continue
        if not math.isfinite(v) or v < 0:
            raise StrengthError(f"--{n.replace('_', '-')} must be zero or a positive number (mm)")


def verdict(stress: float, strength: float, sf: float) -> tuple:
    """(state, achieved SF). FAIL when the stress exceeds the strength itself, WARN when the
    margin is short of the required factor, PASS otherwise."""
    if stress <= 0:
        return "PASS", math.inf
    achieved = strength / stress
    if achieved < 1.0:
        return "FAIL", achieved
    if achieved < sf:
        return "WARN", achieved
    return "PASS", achieved


def check(name, stress, strength, sf, formula, basis):
    state, achieved = verdict(stress, strength, sf)
    return {"state": state, "stress_mpa": round(stress, 2), "strength_mpa": round(strength, 2),
            "sf_achieved": round(achieved, 2) if math.isfinite(achieved) else None, "sf_required": sf,
            "formula": formula, "strength_basis": basis}


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
def case_pin(args, mat, F, o):
    positive(args, "d", "engagement")
    non_negative(args, "gap")
    d, L, g = args.d, args.engagement, args.gap or 0.0
    A = math.pi * d * d / 4
    n = 2 if args.shear == "double" else 1
    if args.support == "through" and n == 1:
        raise StrengthError("a through pin is held at both ends, so it is in double shear: --shear double "
                            "(a pin held at one end is --support stub)")
    tau = SHEAR_PEAK * F / (n * A)
    o_shear = "z" if (o == "z" or args.load_across_layers) else "xy"
    tau_allow = SHEAR_RATIO * mat["tensile"][o_shear]
    if args.support == "through":
        if args.support_t is None:
            raise StrengthError("a through pin needs --support-t, the thickness of each support its ends sit in "
                                "(--engagement is then the width of the loaded member between the supports)")
        a = args.support_t
        M = F * (L + 2 * a + 4 * g) / 8
        how = (f"loose pin through two supports of thickness a = {a} mm, loaded by the member of width b = {L} mm "
               f"between them, gap g = {g} mm on each side, every bearing load spread evenly: M = F (b + 2 a + 4 g) / 8")
        arm_note = (f"lever arm: supports {a} mm thick react at their centres, {L / 2 + g + a / 2:.2f} mm from the pin's "
                    "centre; a load concentrated at the centre of the member would give up to F (b + 2 a) / 4")
    else:
        Fe = F / n
        M = Fe * (g + L / 2)
        how = (f"stub pin as a cantilever from its root face, the load spread evenly over the engagement L = {L} mm "
               f"inside the mating part, gap g = {g} mm between root face and mating part: M = F' (g + L / 2)"
               + (f", F' = F / 2 = {Fe:.1f} N per end (both ends are stubs)" if n == 2 else f", F' = F = {Fe:.1f} N"))
        arm_note = f"lever arm from the root face to the resultant: g + L / 2 = {g + L / 2:.2f} mm"
    sigma = 32 * M / (math.pi * d ** 3)
    checks = {
        "shear": check("shear", tau, tau_allow, args.sf, f"tau = 4/3 F / ({n} x pi d^2 / 4) (peak at the neutral axis)",
                       f"{SHEAR_RATIO} x tensile {o_shear.upper()} {mat['tensile'][o_shear]} MPa"),
        "bending": check("bending", sigma, mat["flex"][o], args.sf, f"sigma = 32 M / (pi d^3), {how}",
                         f"bending strength {o.upper()} {mat['flex'][o]} MPa"),
    }
    notes = [f"{'double' if n == 2 else 'single'} shear: {'both ends held, two shear planes' if n == 2 else 'one end held, one shear plane'}",
             arm_note, f"moment {M:.2f} N mm",
             f"engagement / d = {L / d:.1f} (design.md suggests about 3 or more)"]
    if o_shear != o:
        notes.append("shear uses the Z strength: the pin lies flat and the load crosses the layers, so the shear "
                     "slides layer on layer; bending stress runs along the pin, in the layer plane")
    elif o == "xy":
        notes.append("shear uses the X-Y strength: the load is taken to act within the layer plane; pass "
                     "--load-across-layers when a flat pin is pushed up or down (the shear then slides layer on layer)")
    if not g:
        notes.append("no --gap given: a print-in-place pin has 0.3 to 0.42 mm between its root face and the mating part "
                     "(tolerances.md); it adds to the lever arm, pass it")
    return checks, notes


def case_beam(args, mat, F, o):
    positive(args, "b", "h", "length")
    b, h, L = args.b, args.h, args.length
    I = b * h ** 3 / 12
    c = h / 2
    E = mat["flex_modulus"][o]
    if args.support == "cantilever":
        M, d, how = F * L, F * L ** 3 / (3 * E * I), "cantilever with an end load: M = F L, deflection F L^3 / (3 E I)"
    else:
        M, d, how = F * L / 4, F * L ** 3 / (48 * E * I), "simply supported with a centre load: M = F L / 4, deflection F L^3 / (48 E I)"
    sigma = M * c / I
    checks = {"bending": check("bending", sigma, mat["flex"][o], args.sf, f"sigma = M c / I, I = b h^3 / 12; {how}",
                               f"bending strength {o.upper()} {mat['flex'][o]} MPa")}
    notes = [f"h = {h} mm is the dimension in the bending direction (the thin way), b = {b} mm the width",
             f"tip deflection {d:.3f} mm with the bending modulus {o.upper()} {E} MPa (ISO 178)",
             "a solid section is assumed: give members that carry load solid infill or enough walls (design.md)"]
    return checks, notes, {"deflection_mm": round(d, 3), "moment_nmm": round(M, 2), "I_mm4": round(I, 4)}


def case_link(args, mat, F, o):
    positive(args, "b", "h")
    b, h = args.b, args.h
    A = b * h
    sigma_t = F / A
    checks = {"tension": check("tension", sigma_t, mat["tensile"][o], args.sf, "sigma = F / (b h)",
                               f"tensile strength {o.upper()} {mat['tensile'][o]} MPa")}
    notes = []
    bow = args.bow or 0.0
    if bow > 0:
        I = b * h ** 3 / 12
        M = F * bow
        sigma = sigma_t + M * (h / 2) / I
        checks["bending_from_bow"] = check("bending_from_bow", sigma, mat["flex"][o], args.sf,
                                           "sigma = F / A + F bow (h / 2) / I: a bowed strut carries its load with an "
                                           "eccentricity equal to the bow (simplification: the bow is taken as the full "
                                           "lever arm, the curve as a straight beam of the same section)",
                                           f"bending strength {o.upper()} {mat['flex'][o]} MPa")
        notes.append(f"curved link: bow (sagitta) {bow} mm bends the {h} mm thickness; a straight link would see only F / A")
    if args.length:
        notes.append(f"length {args.length} mm is reported only; buckling in compression is not checked")
    return checks, notes


def case_bearing(args, mat, F, o):
    positive(args, "d", "t", "edge")
    d, t, e = args.d, args.t, args.edge
    sigma_b = F / (d * t)
    tau = F / (2 * e * t)
    checks = {
        "bearing": check("bearing", sigma_b, BEARING_RATIO * mat["tensile"][o], args.sf, "sigma_b = F / (d t)",
                         f"{BEARING_RATIO} x tensile {o.upper()} {mat['tensile'][o]} MPa (bearing strength is not on the data sheet)"),
        "tear_out": check("tear_out", tau, SHEAR_RATIO * mat["tensile"][o], args.sf, "tau = F / (2 e t)",
                          f"{SHEAR_RATIO} x tensile {o.upper()} {mat['tensile'][o]} MPa"),
    }
    notes = [f"edge {e} mm is the wall between the hole and the nearest free edge; design.md asks for 2.2 mm or more around a pin",
             f"t = {t} mm is the thickness the pin bears on (the hole's length)"]
    return checks, notes


def hinge_end_moment(P: float, b: float, g: float) -> float:
    """Fixed-fixed span L = b + 2 g, load P spread evenly over the middle b: the end moment.
    With zero slope at both built-in ends the end moment equals the mean of the simply
    supported moment diagram, (1 / L) integral of M_ss = (1 / (2 L)) integral of w x (L - x)
    over the loaded part, which integrates to P (6 g^2 + 6 g b + b^2) / (12 L).
    Limits: g = 0 -> P b / 12 (uniform load), b -> 0 -> P L / 8 (centre point load)."""
    L = b + 2 * g
    return P * (6 * g * g + 6 * g * b + b * b) / (12 * L)


def hinge_mid_moment(P: float, b: float, g: float) -> float:
    """The same span's mid-span moment: the simply supported value P (2 L - b) / 8 less the
    end moment. Never above the end moment (equal only as b -> 0)."""
    L = b + 2 * g
    return P * (2 * L - b) / 8 - hinge_end_moment(P, b, g)


def hinge_wall(knuckle_d: float, pin_d: float, clearance: float, hole: str) -> float:
    """The thinnest wall of a knuckle around its hole: above the point of a teardrop hole
    (its apex is (r + c) sqrt(2) above the axis, parts.hinge) or above a round hole."""
    R, rc = knuckle_d / 2, pin_d / 2 + clearance
    return R - (rc * math.sqrt(2) if hole == "teardrop" else rc)


def case_hinge(args, mat, F, o):
    positive(args, "pin_d", "knuckle_d")
    non_negative(args, "gap", "clearance")
    k = args.knuckles
    if k is None or k < 2:
        raise StrengthError("--knuckles must be a whole number of at least 2 (A, B; a lid hinge needs 3 or more, odd recommended)")
    if (args.length is None) == (args.knuckle_len is None):
        raise StrengthError("hinge: give exactly one of --length (the whole hinge, knuckles and gaps) or --knuckle-len "
                            "(one knuckle)")
    # Defaults resolved here, not in argparse, so a hinge-only flag given to another case is an error
    # (and --shear / --bow default to None so another case's flag given to the hinge is one too).
    g = 0.3 if args.gap is None else args.gap                      # tolerances.md, print-in-place joint
    c = 0.3 if args.clearance is None else args.clearance
    hole = args.hole or "teardrop"
    pin = args.pin or "integral"
    args.gap, args.clearance, args.hole, args.pin = g, c, hole, pin    # the effective values go into "inputs"
    duty = args.duty
    if duty is not None and duty not in DUTIES:
        raise StrengthError(f"--duty is one of {', '.join(DUTY_NAMES)}")
    if duty == "lid" and args.sf < DEFAULT_SF - 1e-9:
        raise StrengthError(f"duty lid needs --sf of at least {DEFAULT_SF} (design.md: a lid hinge is sized by this calculation "
                            "at SF >= 2 and the coupon print comes on top of that margin, it does not replace it)")
    d, D = args.pin_d, args.knuckle_d
    if args.length is not None:
        positive(args, "length")
        b = (args.length - (k - 1) * g) / k
        if b <= 0:
            raise StrengthError(f"--length {args.length} mm leaves no knuckle length for {k} knuckles with {g} mm gaps")
    else:
        positive(args, "knuckle_len")
        b = args.knuckle_len
    a = b                                                       # every knuckle is b long (parts.hinge)
    e = hinge_wall(D, d, c, hole)
    if e <= 0:
        reach = (d / 2 + c) * (math.sqrt(2) if hole == "teardrop" else 1.0)
        raise StrengthError(f"knuckle {D} mm leaves no wall around the {d} mm pin with {c} mm clearance: the {hole} "
                            f"hole reaches {reach:.2f} mm from the axis, so the knuckle must be over {2 * reach:.2f} mm "
                            "across before any wall remains; raise --knuckle-d")
    n_b = k // 2
    n_end = 1 if k % 2 == 0 else 0
    n_int = n_b - n_end
    P = F / n_b
    L = b + 2 * g
    A = math.pi * d * d / 4
    # The axis prints flat and the pull turns with the lid, so the load is taken to cross the layers:
    # shear, bearing and tear-out use the Z tensile strength; bending runs along the pin (--orientation).
    tau_allow = SHEAR_RATIO * mat["tensile"]["z"]
    shear_basis = f"{SHEAR_RATIO} x tensile Z {mat['tensile']['z']} MPa (the pull crosses the layers)"
    bend_basis = f"bending strength {o.upper()} {mat['flex'][o]} MPa"
    integral = pin == "integral"
    checks, notes = {}, []
    moments = {}
    if n_int:
        if integral:
            M_end, M_mid = hinge_end_moment(P, b, g), hinge_mid_moment(P, b, g)
            M = max(M_end, M_mid)
            moments.update({"interior_end_nmm": round(M_end, 3), "interior_mid_nmm": round(M_mid, 3)})
            how = (f"integral pin built in at both A faces: fixed-fixed span L = b + 2 g = {L:.2f} mm, P = {P:.1f} N spread "
                   f"over the middle b = {b:.2f} mm; M_end = P (6 g^2 + 6 g b + b^2) / (12 L) = {M_end:.2f} N mm, "
                   f"M_mid = P (2 L - b) / 8 - M_end = {M_mid:.2f} N mm; M = max of the two")
        else:
            M = P * (b + 2 * a + 4 * g) / 8
            moments["interior_nmm"] = round(M, 3)
            how = (f"loose pin: clevis between two A knuckles of a = {a:.2f} mm, loaded by the B knuckle of b = {b:.2f} mm, "
                   f"gap g = {g} mm each side: M = P (b + 2 a + 4 g) / 8 = {M:.2f} N mm")
        checks["pin_shear"] = check("pin_shear", SHEAR_PEAK * P / (2 * A), tau_allow, args.sf,
                                    "tau = 4/3 P / (2 x pi d^2 / 4): two shear planes, one at each A face (peak at the neutral axis)",
                                    shear_basis)
        checks["pin_bending"] = check("pin_bending", 32 * M / (math.pi * d ** 3), mat["flex"][o], args.sf,
                                      f"sigma = 32 M / (pi d^3), {how}", bend_basis)
    if n_end:
        M_e = P * (g + b / 2)
        moments["end_nmm"] = round(M_e, 3)
        checks["pin_shear_end"] = check("pin_shear_end", SHEAR_PEAK * P / A, tau_allow, args.sf,
                                        "tau = 4/3 P / (pi d^2 / 4): the end B hangs on one shear plane at the last A face",
                                        shear_basis)
        checks["pin_bending_end"] = check("pin_bending_end", 32 * M_e / (math.pi * d ** 3), mat["flex"][o], args.sf,
                                          f"sigma = 32 M / (pi d^3), stub from the last A face: M = P (g + b / 2) = {M_e:.2f} N mm "
                                          f"({'the pin end past the last A knuckle is a cantilever' if integral else 'a loose pin held on one side only'})",
                                          bend_basis)
    bear_allow = BEARING_RATIO * mat["tensile"]["z"]
    bear_basis = (f"{BEARING_RATIO} x tensile Z {mat['tensile']['z']} MPa (bearing strength is not on the data sheet; "
                  "the pull crosses the layers)")
    tear_allow = SHEAR_RATIO * mat["tensile"]["z"]
    tear_basis = f"{SHEAR_RATIO} x tensile Z {mat['tensile']['z']} MPa (the pull crosses the layers)"
    checks["wall_bearing"] = check("wall_bearing", P / (d * b), bear_allow, args.sf,
                                   f"sigma_b = P / (d b): each B knuckle bears its P = {P:.1f} N on the pin over its length b", bear_basis)
    checks["wall_tear_out"] = check("wall_tear_out", P / (2 * e * b), tear_allow, args.sf,
                                    f"tau = P / (2 e b), e = {e:.2f} mm, the thinnest wall of the B knuckle (above the {hole} hole)",
                                    tear_basis)
    P_a = 0.0
    if not integral:
        # A knuckles are supports for a loose pin: P / 2 from each interior B beside them; an end B hangs past the
        # last A, and on a two-support pin its statics give that A the load plus the overhang moment carried over the
        # next span, P (1 + s / 2 s) = 1.5 P (exact for k = 4, an upper bound for longer hinges); with k = 2 there is
        # no span and the single A takes P.
        end_share = 1.5 if k >= 4 else 1.0
        kinds = ["A" if i % 2 == 0 else ("end" if (k % 2 == 0 and i == k - 1) else "int") for i in range(k)]
        for i, kind in enumerate(kinds):
            if kind != "A":
                continue
            load = sum((end_share * P if kinds[j] == "end" else P / 2) for j in (i - 1, i + 1) if 0 <= j < k)
            P_a = max(P_a, load)
        checks["wall_bearing_fixed"] = check("wall_bearing_fixed", P_a / (d * a), bear_allow, args.sf,
                                             f"sigma_b = P_A / (d a): the most loaded A knuckle takes P_A = {P_a:.1f} N "
                                             f"(P / 2 per interior B beside it, {end_share:g} P from an end B: the overhang's statics)",
                                             bear_basis)
        checks["wall_tear_out_fixed"] = check("wall_tear_out_fixed", P_a / (2 * e * a), tear_allow, args.sf,
                                              f"tau = P_A / (2 e a), e = {e:.2f} mm (the A knuckles have the same hole)", tear_basis)
    notes.append(f"layout: {k} knuckles alternating A, B, A ... each {b:.2f} mm long with {g} mm gaps; {n_b} moving (B) knuckles "
                 f"share F = {F} N equally, P = {P:.1f} N each (an assumption: a stiff lid; a twisted one loads one knuckle more); "
                 f"{n_int} interior (between two A), {n_end} on the pin's free end")
    if n_end:
        notes.append(f"{k} is even: the last knuckle is a B on the pin's free end, held on one side only; an odd count "
                     "puts every moving knuckle between two fixed ones. The end stub is far more compliant than an "
                     "interior span, so the equal share is optimistic for the interior knuckles" +
                     ("; for a loose pin the last A knuckle takes the overhang's statics, 1.5 P plus its interior share"
                      if not integral and k >= 4 else ""))
    notes.append(f"{'integral' if integral else 'loose'} pin: " + (
        "part of leaf A, built in at every A knuckle, so an interior span is fixed at both ends; the teardrop section is "
        "taken as a circle of the pin diameter (its point adds a little)" if integral else
        "a separate pin bearing in every knuckle's hole; its A knuckles are supports with the same wall"))
    notes.append(f"wall {e:.2f} mm above the {hole} hole (knuckle {D} mm, hole {d + 2 * c:.2f} mm across the circle); the "
                 "pull direction turns with the lid, so the thinnest wall is used")
    notes.append("layers: the axis prints flat (parts.hinge) and the pull turns with the lid, so the load is taken to cross "
                 "the layers: pin shear, wall bearing and tear-out use the Z tensile strength; bending runs along the pin "
                 f"and uses the {o.upper()} bending strength" +
                 (" (--load-across-layers changes nothing for a hinge)" if args.load_across_layers else ""))
    if duty in (None, "lid"):
        notes.append("lid load case: the open lid pulled away from the box, finger_pull at the hinge, no lever ratio; levering "
                     "the lid past its stop multiplies the force by (finger distance / stop distance from the axis) and is "
                     "misuse a print-in-place hinge is not sized for: say so at delivery and record it in _assumptions "
                     "(design.md)")
    extra = {"layout": {"knuckles": k, "moving_knuckles": n_b, "fixed_knuckles": k - n_b, "interior_moving": n_int,
                        "end_moving": n_end, "knuckle_len_mm": round(b, 3), "fixed_knuckle_len_mm": round(a, 3),
                        "gap_mm": g, "clearance_mm": c, "hole": hole, "hole_d_mm": round(d + 2 * c, 3),
                        "wall_mm": round(e, 3), "span_mm": round(L, 3), "pin": pin,
                        "load_per_knuckle_N": round(P, 2), "fixed_knuckle_load_N": round(P_a, 2) if not integral else None},
             "moments_nmm": moments}
    if duty:
        extra["minimums"] = hinge_minimums(duty, d, e, b, k)
        if duty == "decorative":
            for ch in checks.values():
                ch["informational"] = True
            notes.append("duty decorative: the hinge carries nothing, the floors alone decide the gate; the checks are "
                         "reported for information (\"informational\": true) and do not change it")
        elif duty == "lid":
            notes.append("duty lid: the floors are only what prints; the size comes from this calculation at SF >= 2, and a "
                         "hinge coupon print before the full part is required on top of that margin (a skipped one goes "
                         "into _assumptions)")
        else:
            notes.append("duty latch: the field floors are the primary rule; this calculation separates the hopeless from the plausible")
    else:
        notes.append("no --duty given: P7 also needs the duty's floors (latch: design.md field minimums; lid, decorative: what "
                     "prints, tolerances.md); pass --duty latch | lid | decorative for the minimums block")
    return checks, notes, extra


def snap_strain(length: float, thickness: float, deflection: float, q: float = 1.0) -> float:
    """Maximum strain at the root of a uniform cantilever deflected by `deflection` at its tip:
    e = 1.5 t y / (L^2 Q) (BASF snap-fit design manual; Q = 1 for a beam on a rigid wall, about
    2 for a short beam on a thin wall). The same formula as parts.snap_fit_strain."""
    if length <= 0 or thickness <= 0:
        raise StrengthError("--length and --h must be positive")
    if q <= 0:
        raise StrengthError("--q must be positive (1 for a rigid wall, up to about 2 for a thin one)")
    return 1.5 * thickness * deflection / (length ** 2 * q)


def snap_family(mat: dict) -> str:
    """The SNAP_STRAIN family of a Bambu material key: pla_basic -> PLA, petg_hf -> PETG."""
    family = mat["key"].split("_")[0].upper()
    if family not in SNAP_STRAIN:
        raise StrengthError(f"no snap strain limit for {mat['key']}; families: {', '.join(SNAP_STRAIN)}")
    return family


def mating_force(P: float, angle_deg: float, mu: float):
    """Force to push the arm over a ramp of `angle_deg` from the mating direction while it
    carries the deflection force P: W = P (mu + tan a) / (1 - mu tan a) (BASF). None at 90
    degrees or past the self-locking angle (the joint does not come apart that way)."""
    if angle_deg >= 90.0:
        return None
    t = math.tan(math.radians(angle_deg))
    if 1.0 - mu * t <= 0:
        return None
    return P * (mu + t) / (1.0 - mu * t)


def case_snap(args, mat, o):
    """A straight cantilever snap arm printed flat (parts.snap_hook): strain at full deflection
    against the material family's one-time design strain (x 0.6 when the joint is opened often),
    the force that deflection takes (the arm's own load, no hand-force key), the bending
    stress it causes (sigma = E e) against the bending strength, and the insertion and release
    forces over the ramps. Returns (checks, notes, extra, load N, load description)."""
    positive(args, "b", "h", "length", "undercut")
    non_negative(args, "friction")
    if args.load is not None:
        raise StrengthError("a snap arm's load is its own deflection force (from the undercut): do not pass --load; "
                            "a hand force is bounded by the release force this case reports")
    q = 1.0 if args.q is None else args.q
    entry = 30.0 if args.entry_angle is None else args.entry_angle
    retention = 90.0 if args.retention_angle is None else args.retention_angle
    mu = SNAP_FRICTION if args.friction is None else args.friction
    if not 0 < entry < 90 or not 0 < retention <= 90:
        raise StrengthError("--entry-angle is between 0 and 90 degrees, --retention-angle between 0 and 90 (90: no release)")
    args.q, args.entry_angle, args.retention_angle, args.friction = q, entry, retention, mu
    b, h, L, y = args.b, args.h, args.length, args.undercut
    family = snap_family(mat)
    limit = SNAP_STRAIN[family] * (SNAP_REPEATED if args.repeated else 1.0)
    e = snap_strain(L, h, y, q)
    max_y = limit * L ** 2 * q / (1.5 * h)
    E = mat["flex_modulus"][o]
    I = b * h ** 3 / 12
    P = 3 * E * I * y / (q * L ** 3)                      # y = Q P L^3 / (3 E I)
    sigma = E * e                                         # = 6 P L / (b h^2) for a cantilever
    checks = {
        "strain": {"state": "PASS" if e <= limit else "FAIL", "strain": round(e, 5), "limit": limit,
                   "sf_achieved": round(limit / e, 2) if e > 0 else None, "sf_required": 1.0,
                   "formula": "e = 1.5 h y / (L^2 Q) at the root, full deflection y = the undercut",
                   "strength_basis": f"one-time design strain of {family} {SNAP_STRAIN[family]:.1%}"
                                     + (f" x {SNAP_REPEATED} for a joint opened often" if args.repeated else "")
                                     + " (design.md, snap fits: starting points, calibrate with a test hook)"},
        "bending": check("bending", sigma, mat["flex"][o], args.sf, "sigma = E e = 6 P L / (b h^2) at the root",
                         f"bending strength {o.upper()} {mat['flex'][o]} MPa, modulus {E} MPa (ISO 178)"),
    }
    w_in, w_rel = mating_force(P, entry, mu), mating_force(P, retention, mu)
    notes = [f"deflection force P = 3 E I y / (Q L^3) = {P:.2f} N for y = {y} mm (E {E} MPa {o.upper()}, "
             f"I = b h^3 / 12 = {I:.4f} mm4, Q = {q:g}): the arm's own load; a hand force on the joint is bounded by "
             "the release force, not by a hand-force key",
             f"max deflection at the strain limit: {max_y:.3f} mm (undercut {y} mm"
             + (" is over it: lengthen or thin the arm, never thicken it" if y > max_y + 1e-9 else " fits") + ")",
             f"insertion force over the {entry:g} deg entry ramp: "
             + (f"{w_in:.1f} N" if w_in is not None else "not computable (self-locking ramp)")
             + f"; release force over the {retention:g} deg retention face: "
             + (f"{w_rel:.1f} N" if w_rel is not None else "none (90 deg or self-locking: it needs a release window "
                                                            "or a tool, parts.snap_hook)")
             + f"; W = P (mu + tan a) / (1 - mu tan a) with mu = {mu:g} (plastic on plastic, dry: a starting point)",
             "the arm prints flat and flexes within the layer plane (parts.snap_hook): pass --orientation xy for its "
             "modulus and strength; z is the conservative default" if o == "z" else
             "orientation xy: the arm prints flat and flexes within the layer plane (parts.snap_hook)",
             f"length / thickness = {L / h:.1f} (design.md: about 5 to 10 for a PLA arm)"]
    extra = {"snap": {"strain": round(e, 5), "limit": limit, "family": family, "repeated": bool(args.repeated),
                      "max_deflection_mm": round(max_y, 3), "deflection_force_N": round(P, 3),
                      "insertion_force_N": round(w_in, 2) if w_in is not None else None,
                      "release_force_N": round(w_rel, 2) if w_rel is not None else None,
                      "friction": mu, "q": q, "I_mm4": round(I, 4), "length_to_thickness": round(L / h, 2)}}
    load_desc = (f"the arm's own deflection force at the {y} mm undercut (3 E I y / (Q L^3)); no hand-force key "
                 "applies to a flexure")
    return checks, notes, extra, P, load_desc


def hinge_minimums(duty: str, pin_d: float, wall: float, knuckle_len: float, knuckles: int) -> dict:
    """Compare a hinge's pin, wall, knuckle length and, for a lid, knuckle count with the P7
    floors of its duty."""
    if duty not in DUTIES:
        raise StrengthError(f"--duty is one of {', '.join(DUTY_NAMES)}")
    fl = DUTIES[duty]["floors"]
    rows = {}
    for name, value, floor in (("pin_d_mm", pin_d, fl["pin_d"]), ("wall_mm", wall, fl["pin_wall"]),
                               ("knuckle_len_mm", knuckle_len, fl["knuckle_len"])):
        rows[name] = {"value": round(value, 3), "floor": floor, "state": "PASS" if value >= floor - 1e-9 else "FAIL"}
    min_k = DUTIES[duty].get("min_knuckles")
    if min_k:
        rows["knuckles"] = {"value": knuckles, "floor": min_k, "state": "PASS" if knuckles >= min_k else "FAIL"}
        if knuckles % 2 == 0:
            rows["knuckles"]["note"] = "an even count leaves a moving knuckle on the pin's free end; an odd count puts every " \
                                       "moving knuckle between two fixed ones (recommended)"
    state = "FAIL" if any(r["state"] == "FAIL" for r in rows.values()) else "PASS"
    return {"duty": duty, "state": state, "source": DUTIES[duty]["source"], "sizing": DUTIES[duty]["sizing"], **rows,
            "member_mm": {"floor": fl["member"], "note": "leaf thickness is not an input here; parts.hinge checks it"}}


# --------------------------------------------------------------------------- #
# Linking to a build (--from-build, --part, --param)
# --------------------------------------------------------------------------- #
def linkable_inputs(case: str) -> set:
    """The inputs --param can set for a case: the keys its report's "inputs" can hold, less the
    material (it comes from the build's part) and, for a snap arm, the load (its own)."""
    return ({"orientation", "sf"} | ({"load"} if case != "snap" else set()) | CASE_INPUTS[case])


def param_value(values: dict, name: str) -> tuple:
    """(found, value) of a build parameter: the key itself, else a dotted path into nested
    objects ("plug.w"). The same rule as finalize.lookup."""
    if name in values:
        return True, values[name]
    cur = values
    for k in name.split("."):
        if not (isinstance(cur, dict) and k in cur):
            return False, None
        cur = cur[k]
    return True, cur


def _leaf_names(d: dict, prefix: str = "") -> list:
    out = []
    for k, v in d.items():
        if isinstance(v, dict) and v:
            out += _leaf_names(v, f"{prefix}{k}.")
        else:
            out.append(f"{prefix}{k}")
    return out


def _finite(v) -> bool:
    """A real, finite number; an integer too large for a float (10**400 in edited JSON) is not."""
    try:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    except OverflowError:
        return False


def link_value(case: str, inp: str, param: str, raw):
    """A build parameter's value as the input `inp` takes it, checked as its option is checked:
    a finite number that is not a bool, above zero for a size, zero allowed where the option
    allows it, an integer for knuckles, one of the option's choices, true or false for a flag."""
    shown = json.dumps(raw)
    if len(shown) > 60:
        shown = shown[:57] + "..."
    where = f"--param {inp}={param}: the build has {param} = {shown}; {inp} takes"
    number = _finite(raw)
    kind = INPUT_KIND[inp]
    if kind in ("size", "positive", "non_negative"):
        if not number:
            raise StrengthError(f"{where} a finite number")
        if kind == "non_negative" and raw < 0:
            raise StrengthError(f"{where} zero or a positive number")
        if kind != "non_negative" and raw <= 0:
            raise StrengthError(f"{where} a positive number" + (" (mm)" if kind == "size" else ""))
        return float(raw)                                   # as the option's type=float gives it
    if kind == "whole":
        if not isinstance(raw, int) or isinstance(raw, bool) or not _finite(raw):
            raise StrengthError(f"{where} a whole number (a JSON integer)")
        return raw
    if kind == "flag":
        if not isinstance(raw, bool):
            raise StrengthError(f"{where} true or false")
        return raw
    if kind == "choice":
        choices = SUPPORTS[case] if inp == "support" else CHOICES[inp]
        if not isinstance(raw, str) or raw not in choices:
            raise StrengthError(f"{where} one of {', '.join(choices)}")
        return raw
    if number and raw > 0:                                  # load: a force in N or a hand-force key
        return raw
    if isinstance(raw, str) and raw.strip().lower() in LOADS:
        return raw
    raise StrengthError(f"{where} a positive force in N or one of {', '.join(LOADS)}")


def read_build(path: str) -> dict:
    if not os.path.isfile(path):
        raise StrengthError(f"--from-build {path}: no such file (run build.py first)")
    try:
        with open(path, encoding="utf-8") as f:
            build = json.load(f)
    except (OSError, ValueError) as exc:
        raise StrengthError(f"--from-build {path}: not a readable JSON file ({exc})")
    schema = build.get("schema") if isinstance(build, dict) else None
    if schema != BUILD_SCHEMA:
        raise StrengthError(f"--from-build {path}: not a build.py report (schema {BUILD_SCHEMA}, found {json.dumps(schema)})")
    return build


def link_build(args) -> dict:
    """--from-build, --part and --param: set the part's material and every linked input on
    `args` (args.linked: {input: param}) and return the report's "from_build" block."""
    if args.case not in CASE_INPUTS:
        raise StrengthError(f"--from-build, --part and --param belong to the calculation cases ({', '.join(CASE_INPUTS)}), "
                            f"not to {args.case}")
    if args.from_build is None:
        raise StrengthError("--part and --param need --from-build, the build.py report (out/build.json) the part and "
                            "its parameters come from")
    if not args.part:
        raise StrengthError("--from-build needs --part, the part of the build this member belongs to")
    if args.material is not None:
        raise StrengthError("--material does not go with --from-build: the material is the one the build recorded for "
                            "the part (_parts.<part>.material, else _material in params.json)")
    links, known = {}, linkable_inputs(args.case)
    for text in args.param or []:
        inp, sep, param = text.partition("=")
        inp, param = inp.strip(), param.strip()
        if not sep or not inp or not param:
            raise StrengthError(f"--param takes INPUT=PARAM (h=ribbon_t), not '{text}'")
        if inp == "material":
            raise StrengthError("--param material=...: the material is not a parameter; with --from-build it is the one "
                                "the build recorded for the part (_parts.<part>.material, else _material)")
        if inp not in known:
            raise StrengthError(f"--param {text}: '{inp}' is not an input of the {args.case} case (its inputs: "
                                f"{', '.join(sorted(known))})")
        if inp in links:
            raise StrengthError(f"--param: {inp} is linked twice ({inp}={links[inp]} and {text})")
        if inp in args.given:
            raise StrengthError(f"{inp} is given twice, as --{inp.replace('_', '-')} and as --param {text}: give it one way")
        links[inp] = param
    path = args.from_build
    build = read_build(path)
    parts = build.get("parts")
    if not isinstance(parts, list):
        raise StrengthError(f"--from-build {path}: lists no parts")
    part = next((p for p in parts if isinstance(p, dict) and p.get("name") == args.part), None)
    if part is None:
        names = [p["name"] for p in parts if isinstance(p, dict) and isinstance(p.get("name"), str)]
        raise StrengthError(f"part '{args.part}' is not in {path} (its parts: {', '.join(names) or 'none'})")
    sha = part.get("sha256")
    if not isinstance(sha, str) or not sha:
        raise StrengthError(f"part '{args.part}' in {path} has no sha256: the build made no sound STL of it (fix the part "
                            "and build again)")
    mat = part.get("material")
    if mat is None:
        raise StrengthError(f"no material recorded for {args.part}: set _material or _parts.{args.part}.material and "
                            "build again")
    if not isinstance(mat, str) or mat not in MATERIALS:
        raise StrengthError(f"{path} records the material {json.dumps(mat)} for {args.part}, not a strength.py material "
                            f"key ({', '.join(MATERIALS)})")
    args.material = mat
    block = {"build": path, "part": args.part, "sha256": sha, "material": mat, "parameters": {}}
    if links:
        p = build.get("parameters")
        if not (isinstance(p, dict) and p.get("scope") in ("merged", "overrides") and isinstance(p.get("values"), dict)):
            raise StrengthError(f"--from-build {path}: records no parameters ({{\"scope\": \"merged\" | \"overrides\", "
                                "\"values\": {...}}): build it again with this version of build.py")
        values, scope = p["values"], p["scope"]
        for inp, param in links.items():
            found, raw = param_value(values, param)
            if not found:
                if scope == "overrides":
                    raise StrengthError(f"--param {inp}={param}: '{param}' is not in the build's parameters, and this "
                                        "build (scope overrides) records only what params.json passed, so a generator's "
                                        "default is not recorded: put it in params.json and build again")
                names = _leaf_names(values)
                raise StrengthError(f"--param {inp}={param}: '{param}' is not in the build's parameters (scope merged, "
                                    f"the generator's defaults and params.json: {', '.join(names[:30]) or 'none'}"
                                    + (", ..." if len(names) > 30 else "") + ")")
            setattr(args, inp, link_value(args.case, inp, param, raw))
            block["parameters"][inp] = {"param": param, "value": raw}
    args.linked = links
    return block


def input_origins(args, inputs: dict, material_key: str) -> dict:
    """{input: origin} for every key of the report's inputs: param:<PARAM> (--param),
    build:material, table:<key> (a hand-force or material key), manual (typed on the command
    line) or default:<input> (strength.py chose it because nothing was given)."""
    given, linked = getattr(args, "given", set()), getattr(args, "linked", {})
    out = {}
    for k, v in inputs.items():
        if k in linked:
            out[k] = f"param:{linked[k]}"
        elif k == "material":
            out[k] = "build:material" if getattr(args, "build_link", None) else f"table:{material_key}"
        elif k == "load" and str(v).strip().lower() in LOADS:
            out[k] = f"table:{str(v).strip().lower()}"
        elif k in given:
            out[k] = "manual"
        else:
            out[k] = f"default:{k}"
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run(args) -> dict:
    if args.case == "materials":
        return {"materials": MATERIALS, "shear_ratio": SHEAR_RATIO, "bearing_ratio": BEARING_RATIO,
                "note": "values as published on the Bambu Lab data sheets (MPa, %); specimens 100 % infill"}
    if args.case == "loads":
        return {"loads": LOADS, "source": LOADS_SOURCE}
    if args.case == "duties":
        return {"duties": DUTIES, "note": "P7 floors per duty (design.md, Mechanisms that carry load); parts.hinge(duty=...) "
                                          "refuses thinner values; a lid hinge is sized by the hinge case plus a coupon print"}
    mat = material(args.material)
    F, load_desc = load_value(args.load) if args.case != "snap" else (None, None)
    o = args.orientation
    if o not in CHOICES["orientation"]:
        raise StrengthError("--orientation is xy (stress within the layer plane) or z (stress across layers)")
    if not math.isfinite(args.sf) or args.sf < 1.0:
        raise StrengthError("--sf must be a number of at least 1.0")
    for name in ("d", "engagement", "support_t", "b", "h", "length", "t", "edge", "pin_d", "knuckle_d", "knuckle_len"):
        v = getattr(args, name)
        if v is not None and (not math.isfinite(v) or v <= 0):
            raise StrengthError(f"--{name.replace('_', '-')} must be a positive number (mm)")
    non_negative(args, "gap", "bow", "clearance")
    if args.case != "hinge":
        stray = [f"--{n.replace('_', '-')}" for n in HINGE_ONLY if getattr(args, n) is not None]
        if stray:
            raise StrengthError(f"{', '.join(stray)} belong to the hinge case only (this is case {args.case})")
    if args.case != "snap":
        stray = [f"--{n.replace('_', '-')}" for n in SNAP_ONLY if getattr(args, n) not in (None, False)]
        if stray:
            raise StrengthError(f"{', '.join(stray)} belong to the snap case only (this is case {args.case})")
    if args.case == "hinge":
        stray = [f"--{n.replace('_', '-')}" for n in NOT_HINGE if getattr(args, n) is not None]
        if stray:
            raise StrengthError(f"{', '.join(stray)} do not apply to the hinge case (they belong to pin, beam, link or "
                                "bearing); a hinge takes --pin-d, --knuckle-d, --knuckles, --length or --knuckle-len, "
                                "--gap, --clearance, --hole, --pin and --duty")
    extra = {}
    if args.case == "pin":
        checks, notes = case_pin(args, mat, F, o)
    elif args.case == "beam":
        checks, notes, extra = case_beam(args, mat, F, o)
    elif args.case == "link":
        checks, notes = case_link(args, mat, F, o)
    elif args.case == "bearing":
        checks, notes = case_bearing(args, mat, F, o)
    elif args.case == "hinge":
        checks, notes, extra = case_hinge(args, mat, F, o)
    elif args.case == "snap":
        checks, notes, extra, F, load_desc = case_snap(args, mat, o)
    else:
        raise StrengthError("case must be pin, beam, link, bearing, hinge, snap, materials, loads or duties")
    states = [c["state"] for c in checks.values()]
    gate = "FAIL" if "FAIL" in states else "WARN" if "WARN" in states else "PASS"
    duty = getattr(args, "duty", None) if args.case == "hinge" else None
    if duty == "decorative":
        gate = extra["minimums"]["state"]                            # the checks are informational
    floors_fail = extra.get("minimums", {}).get("state") == "FAIL"
    if floors_fail:
        gate = "FAIL"
    worst = min(checks.values(), key=lambda c: c["sf_achieved"] if c["sf_achieved"] is not None else math.inf)
    assumptions = [
        f"load {round(F, 3) if args.case == 'snap' else F} N: {load_desc}",
        f"material {mat['name']} ({mat['tds']}, retrieved {mat['retrieved']}), {o.upper()} values: the stress "
        + ("acts within the layer plane" if o == "xy" else "crosses the layers (layer adhesion)") + ("; z is the conservative default" if args.orientation_defaulted else ""),
        f"safety factor {args.sf}: data-sheet specimens are 100 % infill, dried and annealed; a part has walls, infill, "
        "corners and layer seams, PLA creeps under a held load, and a latch is snapped, not pressed slowly",
        "static hand calculation on a solid section with the load spread evenly: no stress concentration at corners "
        "(fillet the roots), no fatigue, no impact, no lever ratio (pass the amplified force when a lever multiplies "
        "the hand force)",
    ] + notes
    if args.case == "snap":
        assumptions[2] = (f"safety factor {args.sf} on the bending stress only; the strain check compares the strain "
                          "with the one-time design limit as it is (the limit already holds the layer-bond margin)")
    keep = {"load", "material", "orientation", "sf"} | CASE_INPUTS[args.case]
    linked = getattr(args, "linked", {})
    # A linked flag stays in the inputs when false, so its origin (and a change of it) is recorded.
    inputs = {k: v for k, v in vars(args).items() if k in keep and v is not None and (v is not False or k in linked)}
    next_step = {"PASS": "size holds on paper; the margin covers the usual unknowns",
                 "WARN": "short margin: thicken the member, or print the mechanism alone first (SKILL.md, Phase 4)",
                 "FAIL": "the member breaks on paper: redesign before printing"}[gate]
    if args.case == "snap":
        next_step = {"PASS": "the arm holds on paper; print the snap alone first and feel the insertion force (Phase 4)",
                     "WARN": "short bending margin: lengthen the arm or reduce the undercut (not thicker: that raises the "
                             "strain), or print the snap alone first",
                     "FAIL": "the arm yields or breaks on paper: lengthen it, thin it or reduce the undercut, never "
                             "thicken it"}[gate]
    if floors_fail:
        below = [k for k, v in extra["minimums"].items() if isinstance(v, dict) and v.get("state") == "FAIL"]
        next_step = (f"under the {extra['minimums']['duty']} floors ({', '.join(below)}): " +
                     ("the field minimums are the rule for this duty, grow the member or change the duty if it is really a lid"
                      if duty == "latch" else
                      "a lid hinge needs 3 or more knuckles (odd recommended); add knuckles" if "knuckles" in below else
                      "below what prints (tolerances.md); grow the member"))
    elif duty == "lid" and gate == "WARN":
        next_step = ("lid duty needs SF >= 2: grow the pin or knuckle diameter or add knuckles (odd); the coupon print is "
                     "required on top and does not replace the margin")
    elif duty == "lid" and gate == "PASS":
        next_step += "; lid duty: print the hinge coupon before the full part (required on top of the margin, parts.md)"
    elif duty == "decorative":
        next_step = ("decorative: the floors decide" + (" and are met; no calculation is needed for a hinge that carries nothing"
                                                        if gate == "PASS" else ""))
    link = getattr(args, "build_link", None)
    return {"case": args.case, "inputs": inputs, "inputs_from": input_origins(args, inputs, mat["key"]),
            **({"from_build": link} if link else {}),
            "load_N": F, "material": {k: mat[k] for k in ("key", "name", "tds", "url", "retrieved")},
            "orientation": o, "checks": checks, "gate": gate,
            "worst": {"check": next(k for k, v in checks.items() if v is worst), "sf_achieved": worst["sf_achieved"]},
            "next_step": next_step, "assumptions": assumptions, **extra}


def join_negative_values(argv):
    """argparse reads `--bow -3` as an option with no value; turn `--opt -3` into `--opt=-3` so
    the number reaches the sign check and the error names the option."""
    out, i = [], 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--") and "=" not in tok and i + 1 < len(argv) and re.fullmatch(r"-[0-9.][0-9.eE+-]*", argv[i + 1]):
            out.append(f"{tok}={argv[i + 1]}")
            i += 2
        else:
            out.append(tok)
            i += 1
    return out


def utf8_stdout():
    """Windows consoles and pipes may not be UTF-8; material names and notes are. Best effort."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def material_of_filament(settings_name):
    """The MATERIALS key of a slicer filament preset name, or None: Bambu Studio names its presets
    after the filament and the printer ("Bambu PLA Basic @BBL X1C"); the part before " @" must be a
    material's own name exactly ("Bambu PLA Basic Gradient" is not PLA Basic). Used to compare the
    filament a print file selects with the material a design declares (finalize.py)."""
    if not isinstance(settings_name, str):
        return None
    base = settings_name.split(" @")[0].strip()
    return next((k for k, m in MATERIALS.items() if m["name"] == base), None)


def main(argv=None):
    utf8_stdout()
    out = {"schema": SCHEMA, "ran": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="hand calculations for load-carrying members (Bambu Lab data-sheet values)")
        ap.add_argument("case", choices=["pin", "beam", "link", "bearing", "hinge", "snap", "materials", "loads", "duties"])
        ap.add_argument("--load", help="force in N, or finger_push, finger_press, finger_pull, pinch_lateral, pinch_palmar, grasp "
                                       "(not for snap: its load is its own deflection force)")
        ap.add_argument("--material", help="pla_basic, pla_matte, pla_pure, petg_basic, petg_hf, abs, asa")
        ap.add_argument("--orientation", help="xy (stress within the layer plane) or z (across layers; default)")
        ap.add_argument("--sf", type=float, default=None, help=f"required safety factor (default {DEFAULT_SF})")
        ap.add_argument("--d", type=float, help="pin or hole diameter (mm)")
        ap.add_argument("--engagement", type=float,
                        help="pin: stub: length L inside the mating part (per end with --shear double); through: width b of the loaded member between the supports (mm)")
        ap.add_argument("--support-t", type=float, dest="support_t", help="pin, through: thickness a of each support the pin's ends sit in (mm)")
        ap.add_argument("--gap", type=float, default=None,
                        help="pin: gap between the root face (stub) or each support (through) and the mating part (mm, default 0); "
                             "hinge: axial gap between knuckles (mm, default 0.3)")
        ap.add_argument("--load-across-layers", action="store_true", dest="load_across_layers",
                        help="pin lying flat whose load crosses the layers: shear uses the Z strength (a hinge always does; "
                             "accepted there, no effect)")
        ap.add_argument("--shear", default=None, choices=list(CHOICES["shear"]),
                        help="pin: shear planes, one end held or both (default single)")
        ap.add_argument("--support", default=None, choices=list(SUPPORTS["pin"] + SUPPORTS["beam"]),
                        help="pin: stub (grows out of a part; both ends with --shear double) or through (loose pin, needs --support-t); beam: cantilever or simple")
        ap.add_argument("--b", type=float, help="section width (mm)")
        ap.add_argument("--h", type=float, help="section thickness in the bending direction (mm)")
        ap.add_argument("--length", type=float, help="beam length / link length / hinge length, knuckles and gaps (mm)")
        ap.add_argument("--bow", type=float, default=None, help="link: sagitta of a curved link (mm, default 0)")
        ap.add_argument("--t", type=float, help="bearing: thickness the pin bears on (mm)")
        ap.add_argument("--edge", type=float, help="bearing: wall from the hole to the nearest edge (mm)")
        ap.add_argument("--pin-d", type=float, dest="pin_d", help="hinge: pin diameter (mm)")
        ap.add_argument("--knuckle-d", type=float, dest="knuckle_d", help="hinge: knuckle outer diameter (mm)")
        ap.add_argument("--knuckles", type=int, help="hinge: number of knuckles, alternating A, B, A ... (2 or more; a lid 3 or more, odd recommended)")
        ap.add_argument("--knuckle-len", type=float, dest="knuckle_len", help="hinge: length of one knuckle (mm), instead of --length")
        ap.add_argument("--clearance", type=float, default=None,
                        help="hinge: radial clearance between pin and hole (mm, default 0.3, tolerances.md print-in-place)")
        ap.add_argument("--hole", default=None, choices=list(CHOICES["hole"]),
                        help="hinge: hole shape; the wall is measured above a teardrop's point (default) or above a round hole")
        ap.add_argument("--pin", default=None, choices=list(CHOICES["pin"]),
                        help="hinge: the pin is part of leaf A (default, parts.hinge) or a loose pin through every knuckle")
        ap.add_argument("--duty", default=None, choices=list(CHOICES["duty"]),
                        help="hinge: compare pin, wall, knuckle length (lid: and count) with this duty's P7 floors; "
                             "lid needs --sf 2 or more and a coupon print on top")
        ap.add_argument("--undercut", type=float, help="snap: the catch's undercut = the arm's deflection at full travel (mm)")
        ap.add_argument("--q", type=float, default=None, help="snap: deflection magnification, 1 (rigid wall, default) to about 2 (thin wall)")
        ap.add_argument("--repeated", action="store_true", help="snap: the joint is opened often (60 %% of the strain limit)")
        ap.add_argument("--entry-angle", type=float, dest="entry_angle", default=None, help="snap: lead-in ramp angle (deg, default 30)")
        ap.add_argument("--retention-angle", type=float, dest="retention_angle", default=None,
                        help="snap: retention face angle (deg, default 90: no release without a window)")
        ap.add_argument("--friction", type=float, default=None, help=f"snap: friction coefficient over the ramps (default {SNAP_FRICTION})")
        ap.add_argument("--from-build", dest="from_build", metavar="BUILD_JSON",
                        help="a build.py report (out/build.json): the material is the one it recorded for --part, and "
                             "--param takes inputs from its parameters")
        ap.add_argument("--part", help="with --from-build: the part of the build this member belongs to")
        ap.add_argument("--param", action="append", metavar="INPUT=PARAM",
                        help="with --from-build: take INPUT (a name in the report's inputs: h, b, length, d, pin_d, "
                             "knuckles, orientation, support ...) from the build's parameter PARAM (a dotted path "
                             "reaches into a nested object: plug.w); repeatable")
        args = ap.parse_args(join_negative_values(sys.argv[1:] if argv is None else argv))
        # What the command line gave, before any link or default fills the rest (inputs_from: manual).
        args.given = {k for k, v in vars(args).items()
                      if k != "case" and k not in LINK_OPTIONS and v is not None and v is not False}
        args.linked, args.build_link = {}, None
        if args.from_build is not None or args.part is not None or args.param:
            args.build_link = link_build(args)
        if args.sf is None:
            args.sf = DEFAULT_SF
        args.orientation_defaulted = args.orientation is None
        if args.orientation is None:
            args.orientation = "z"
        if args.case == "snap" and args.material is None:
            raise StrengthError("--material is required (the snap arm's load is its own deflection force, no --load)")
        if args.case in ("pin", "beam", "link", "bearing", "hinge"):
            if args.load is None or args.material is None:
                raise StrengthError("--load and --material are required")
            if args.case == "pin":
                args.shear = args.shear or "single"
                args.support = args.support or ("through" if args.shear == "double" else "stub")
                if args.support not in SUPPORTS["pin"]:
                    raise StrengthError("pin: --support is through or stub")
            if args.case == "beam":
                args.support = args.support or "cantilever"
                if args.support not in SUPPORTS["beam"]:
                    raise StrengthError("beam: --support is cantilever or simple")
            if args.case == "link" and args.bow is None:
                args.bow = 0.0
            if args.case != "hinge" and args.gap is None:
                args.gap = 0.0                           # the hinge resolves its own defaults (0.3, tolerances.md)
        if args.case == "snap" and args.gap is None:
            args.gap = 0.0
        out.update(run(args))
        out["ran"] = True
    except (StrengthError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
