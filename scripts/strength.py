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
           gap) / k), gap g between them, the pin with radial clearance c in B's holes. The pin
           belongs to leaf A (--pin integral, the default) or is a loose pin through every
           knuckle (--pin loose). The n_B = k // 2 moving (B) knuckles share the load equally,
           P = F / n_B each (an assumption, stated). A B knuckle between two A knuckles is
           "interior"; with k even the last knuckle is a B on the pin's free end ("end").
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
             knuckles then bear the pin too: each takes P / 2 from an interior B neighbour and
             P from an end B neighbour; the most loaded A is checked.
           Bending 32 M / (pi d^3) against the bending strength; shear against 0.58 x tensile
           (Z with --load-across-layers or --orientation z, as the pin case). Per B knuckle the
           wall: bearing P / (d b) and tear-out P / (2 e b) with e = the wall above the hole,
           R - (r + c) sqrt(2) for a teardrop hole (--hole teardrop, parts.hinge), R - (r + c)
           for a round one. With --duty latch | lid | decorative a "minimums" block compares
           pin, wall and knuckle length with that duty's P7 floors (DUTIES below; a floor not
           met makes the gate FAIL); without it a note says P7 still needs them.

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
import re
import sys

SCHEMA = "3dprint-scout.strength/1"
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
    "lid": {"floors": dict(_PRINTS),
            "what": "a lid, door or flap hinge with alternating knuckles (3 or more, odd count recommended) where the "
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


CASE_INPUTS = {"pin": {"d", "engagement", "support_t", "gap", "shear", "support", "load_across_layers"},
               "beam": {"b", "h", "length", "support"}, "link": {"b", "h", "length", "bow"}, "bearing": {"d", "t", "edge"},
               "hinge": {"pin_d", "knuckle_d", "knuckles", "length", "knuckle_len", "gap", "clearance", "hole", "pin", "duty",
                         "load_across_layers"}}


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
        raise StrengthError("--knuckles must be a whole number of at least 2 (A, B; a lid hinge wants 3 or more, odd)")
    if (args.length is None) == (args.knuckle_len is None):
        raise StrengthError("hinge: give exactly one of --length (the whole hinge, knuckles and gaps) or --knuckle-len "
                            "(one knuckle)")
    d, D, g, c = args.pin_d, args.knuckle_d, args.gap, args.clearance
    if args.length is not None:
        positive(args, "length")
        b = (args.length - (k - 1) * g) / k
        if b <= 0:
            raise StrengthError(f"--length {args.length} mm leaves no knuckle length for {k} knuckles with {g} mm gaps")
    else:
        positive(args, "knuckle_len")
        b = args.knuckle_len
    a = b                                                       # every knuckle is b long (parts.hinge)
    e = hinge_wall(D, d, c, args.hole)
    if e <= 0:
        reach = (d / 2 + c) * (math.sqrt(2) if args.hole == "teardrop" else 1.0)
        raise StrengthError(f"knuckle {D} mm leaves no wall around the {d} mm pin with {c} mm clearance: the {args.hole} "
                            f"hole reaches {reach:.2f} mm from the axis, so the knuckle must be over {2 * reach:.2f} mm "
                            "across before any wall remains; raise --knuckle-d")
    n_b = k // 2
    n_end = 1 if k % 2 == 0 else 0
    n_int = n_b - n_end
    P = F / n_b
    L = b + 2 * g
    A = math.pi * d * d / 4
    o_shear = "z" if (o == "z" or args.load_across_layers) else "xy"
    tau_allow = SHEAR_RATIO * mat["tensile"][o_shear]
    shear_basis = f"{SHEAR_RATIO} x tensile {o_shear.upper()} {mat['tensile'][o_shear]} MPa"
    bend_basis = f"bending strength {o.upper()} {mat['flex'][o]} MPa"
    integral = args.pin == "integral"
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
    bear_allow = BEARING_RATIO * mat["tensile"][o]
    bear_basis = f"{BEARING_RATIO} x tensile {o.upper()} {mat['tensile'][o]} MPa (bearing strength is not on the data sheet)"
    tear_allow = SHEAR_RATIO * mat["tensile"][o]
    tear_basis = f"{SHEAR_RATIO} x tensile {o.upper()} {mat['tensile'][o]} MPa"
    checks["wall_bearing"] = check("wall_bearing", P / (d * b), bear_allow, args.sf,
                                   f"sigma_b = P / (d b): each B knuckle bears its P = {P:.1f} N on the pin over its length b", bear_basis)
    checks["wall_tear_out"] = check("wall_tear_out", P / (2 * e * b), tear_allow, args.sf,
                                    f"tau = P / (2 e b), e = {e:.2f} mm, the thinnest wall of the B knuckle (above the {args.hole} hole)",
                                    tear_basis)
    P_a = 0.0
    if not integral:
        # A knuckles are supports for a loose pin: P / 2 from each interior B beside them, P from an end B.
        kinds = ["A" if i % 2 == 0 else ("end" if (k % 2 == 0 and i == k - 1) else "int") for i in range(k)]
        for i, kind in enumerate(kinds):
            if kind != "A":
                continue
            load = sum((P if kinds[j] == "end" else P / 2) for j in (i - 1, i + 1) if 0 <= j < k)
            P_a = max(P_a, load)
        checks["wall_bearing_fixed"] = check("wall_bearing_fixed", P_a / (d * a), bear_allow, args.sf,
                                             f"sigma_b = P_A / (d a): the most loaded A knuckle takes P_A = {P_a:.1f} N "
                                             "(P / 2 per interior B beside it, P from an end B)", bear_basis)
        checks["wall_tear_out_fixed"] = check("wall_tear_out_fixed", P_a / (2 * e * a), tear_allow, args.sf,
                                              f"tau = P_A / (2 e a), e = {e:.2f} mm (the A knuckles have the same hole)", tear_basis)
    notes.append(f"layout: {k} knuckles alternating A, B, A ... each {b:.2f} mm long with {g} mm gaps; {n_b} moving (B) knuckles "
                 f"share F = {F} N equally, P = {P:.1f} N each (an assumption: a stiff lid; a twisted one loads one knuckle more); "
                 f"{n_int} interior (between two A), {n_end} on the pin's free end")
    if n_end:
        notes.append(f"{k} is even: the last knuckle is a B on the pin's free end, held on one side only; an odd count "
                     "puts every moving knuckle between two fixed ones")
    notes.append(f"{'integral' if integral else 'loose'} pin: " + (
        "part of leaf A, built in at every A knuckle, so an interior span is fixed at both ends; the teardrop section is "
        "taken as a circle of the pin diameter (its point adds a little)" if integral else
        "a separate pin bearing in every knuckle's hole; its A knuckles are supports with the same wall"))
    notes.append(f"wall {e:.2f} mm above the {args.hole} hole (knuckle {D} mm, hole {d + 2 * c:.2f} mm across the circle); the "
                 "pull direction turns with the lid, so the thinnest wall is used")
    if o_shear != o:
        notes.append("shear uses the Z strength: the pin lies flat and the load crosses the layers (the open lid pulled up), "
                     "so the shear slides layer on layer; bending stress runs along the pin, in the layer plane")
    elif o == "xy":
        notes.append("shear uses the X-Y strength: the pull is taken to act within the layer plane (a lid opened flat and "
                     "pulled sideways); pass --load-across-layers when the open lid is pulled up, across the layers")
    notes.append("lid load case: the open lid pulled away from the box, finger_pull at the hinge, no lever ratio; levering "
                 "the lid past its stop multiplies the force by (finger distance / stop distance from the axis) and is "
                 "misuse a print-in-place hinge is not sized for: say so at delivery (design.md)")
    extra = {"layout": {"knuckles": k, "moving_knuckles": n_b, "fixed_knuckles": k - n_b, "interior_moving": n_int,
                        "end_moving": n_end, "knuckle_len_mm": round(b, 3), "fixed_knuckle_len_mm": round(a, 3),
                        "gap_mm": g, "clearance_mm": c, "hole": args.hole, "hole_d_mm": round(d + 2 * c, 3),
                        "wall_mm": round(e, 3), "span_mm": round(L, 3), "pin": args.pin,
                        "load_per_knuckle_N": round(P, 2), "fixed_knuckle_load_N": round(P_a, 2) if not integral else None},
             "moments_nmm": moments}
    if args.duty:
        extra["minimums"] = hinge_minimums(args.duty, d, e, b)
        if args.duty == "decorative":
            notes.append("duty decorative: the hinge carries nothing, the floors are all P7 asks; the calculation is for information")
        elif args.duty == "lid":
            notes.append("duty lid: the floors are only what prints; the size comes from this calculation at SF >= 2 and a hinge "
                         "coupon print before the full part (required; a skipped one goes into _assumptions)")
        else:
            notes.append("duty latch: the field floors are the primary rule; this calculation separates the hopeless from the plausible")
    else:
        notes.append("no --duty given: P7 also needs the duty's floors (latch: design.md field minimums; lid, decorative: what "
                     "prints, tolerances.md); pass --duty latch | lid | decorative for the minimums block")
    return checks, notes, extra


def hinge_minimums(duty: str, pin_d: float, wall: float, knuckle_len: float) -> dict:
    """Compare a hinge's pin, wall and knuckle length with the P7 floors of its duty."""
    if duty not in DUTIES:
        raise StrengthError(f"--duty is one of {', '.join(DUTY_NAMES)}")
    fl = DUTIES[duty]["floors"]
    rows = {}
    for name, value, floor in (("pin_d_mm", pin_d, fl["pin_d"]), ("wall_mm", wall, fl["pin_wall"]),
                               ("knuckle_len_mm", knuckle_len, fl["knuckle_len"])):
        rows[name] = {"value": round(value, 3), "floor": floor, "state": "PASS" if value >= floor - 1e-9 else "FAIL"}
    state = "FAIL" if any(r["state"] == "FAIL" for r in rows.values()) else "PASS"
    return {"duty": duty, "state": state, "source": DUTIES[duty]["source"], "sizing": DUTIES[duty]["sizing"], **rows,
            "member_mm": {"floor": fl["member"], "note": "leaf thickness is not an input here; parts.hinge checks it"}}


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
    F, load_desc = load_value(args.load)
    o = args.orientation
    if o not in ("xy", "z"):
        raise StrengthError("--orientation is xy (stress within the layer plane) or z (stress across layers)")
    if not math.isfinite(args.sf) or args.sf < 1.0:
        raise StrengthError("--sf must be a number of at least 1.0")
    for name in ("d", "engagement", "support_t", "b", "h", "length", "t", "edge", "pin_d", "knuckle_d", "knuckle_len"):
        v = getattr(args, name)
        if v is not None and (not math.isfinite(v) or v <= 0):
            raise StrengthError(f"--{name.replace('_', '-')} must be a positive number (mm)")
    non_negative(args, "gap", "bow", "clearance")
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
    else:
        raise StrengthError("case must be pin, beam, link, bearing, hinge, materials, loads or duties")
    states = [c["state"] for c in checks.values()]
    gate = "FAIL" if "FAIL" in states else "WARN" if "WARN" in states else "PASS"
    floors_fail = extra.get("minimums", {}).get("state") == "FAIL"
    if floors_fail:
        gate = "FAIL"
    worst = min(checks.values(), key=lambda c: c["sf_achieved"] if c["sf_achieved"] is not None else math.inf)
    assumptions = [
        f"load {F} N: {load_desc}",
        f"material {mat['name']} ({mat['tds']}, retrieved {mat['retrieved']}), {o.upper()} values: the stress "
        + ("acts within the layer plane" if o == "xy" else "crosses the layers (layer adhesion)") + ("; z is the conservative default" if args.orientation_defaulted else ""),
        f"safety factor {args.sf}: data-sheet specimens are 100 % infill, dried and annealed; a part has walls, infill, "
        "corners and layer seams, PLA creeps under a held load, and a latch is snapped, not pressed slowly",
        "static hand calculation on a solid section with the load spread evenly: no stress concentration at corners "
        "(fillet the roots), no fatigue, no impact, no lever ratio (pass the amplified force when a lever multiplies "
        "the hand force)",
    ] + notes
    keep = {"load", "material", "orientation", "sf"} | CASE_INPUTS[args.case]
    inputs = {k: v for k, v in vars(args).items() if k in keep and v is not None and v is not False}
    next_step = {"PASS": "size holds on paper; the margin covers the usual unknowns",
                 "WARN": "short margin: thicken the member, or print the mechanism alone first (SKILL.md, Phase 4)",
                 "FAIL": "the member breaks on paper: redesign before printing"}[gate]
    if floors_fail:
        below = [k for k, v in extra["minimums"].items() if isinstance(v, dict) and v.get("state") == "FAIL"]
        next_step = (f"under the {extra['minimums']['duty']} floors ({', '.join(below)}): " +
                     ("the field minimums are the rule for this duty, grow the member or change the duty if it is really a lid"
                      if extra["minimums"]["duty"] == "latch" else "below what prints (tolerances.md); grow the member"))
    elif args.case == "hinge" and args.duty == "lid" and gate != "FAIL":
        next_step += "; lid duty: print the hinge coupon before the full part (required, parts.md)"
    return {"case": args.case, "inputs": inputs, "load_N": F, "material": {k: mat[k] for k in ("key", "name", "tds", "url", "retrieved")},
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


def main(argv=None):
    utf8_stdout()
    out = {"schema": SCHEMA, "ran": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="hand calculations for load-carrying members (Bambu Lab data-sheet values)")
        ap.add_argument("case", choices=["pin", "beam", "link", "bearing", "hinge", "materials", "loads", "duties"])
        ap.add_argument("--load", help="force in N, or finger_push, finger_press, finger_pull, pinch_lateral, pinch_palmar, grasp")
        ap.add_argument("--material", help="pla_basic, pla_matte, pla_pure, petg_basic, petg_hf, abs, asa")
        ap.add_argument("--orientation", help="xy (stress within the layer plane) or z (across layers; default)")
        ap.add_argument("--sf", type=float, default=DEFAULT_SF, help=f"required safety factor (default {DEFAULT_SF})")
        ap.add_argument("--d", type=float, help="pin or hole diameter (mm)")
        ap.add_argument("--engagement", type=float,
                        help="pin: stub: length L inside the mating part (per end with --shear double); through: width b of the loaded member between the supports (mm)")
        ap.add_argument("--support-t", type=float, dest="support_t", help="pin, through: thickness a of each support the pin's ends sit in (mm)")
        ap.add_argument("--gap", type=float, default=None,
                        help="pin: gap between the root face (stub) or each support (through) and the mating part (mm, default 0); "
                             "hinge: axial gap between knuckles (mm, default 0.3)")
        ap.add_argument("--load-across-layers", action="store_true", dest="load_across_layers",
                        help="pin or hinge pin lying flat whose load crosses the layers: shear uses the Z strength")
        ap.add_argument("--shear", default="single", choices=["single", "double"], help="pin: shear planes, one end held or both")
        ap.add_argument("--support", default=None, choices=["through", "stub", "cantilever", "simple"],
                        help="pin: stub (grows out of a part; both ends with --shear double) or through (loose pin, needs --support-t); beam: cantilever or simple")
        ap.add_argument("--b", type=float, help="section width (mm)")
        ap.add_argument("--h", type=float, help="section thickness in the bending direction (mm)")
        ap.add_argument("--length", type=float, help="beam length / link length / hinge length, knuckles and gaps (mm)")
        ap.add_argument("--bow", type=float, default=0.0, help="link: sagitta of a curved link (mm, default 0)")
        ap.add_argument("--t", type=float, help="bearing: thickness the pin bears on (mm)")
        ap.add_argument("--edge", type=float, help="bearing: wall from the hole to the nearest edge (mm)")
        ap.add_argument("--pin-d", type=float, dest="pin_d", help="hinge: pin diameter (mm)")
        ap.add_argument("--knuckle-d", type=float, dest="knuckle_d", help="hinge: knuckle outer diameter (mm)")
        ap.add_argument("--knuckles", type=int, help="hinge: number of knuckles, alternating A, B, A ... (2 or more; odd recommended)")
        ap.add_argument("--knuckle-len", type=float, dest="knuckle_len", help="hinge: length of one knuckle (mm), instead of --length")
        ap.add_argument("--clearance", type=float, default=None,
                        help="hinge: radial clearance between pin and hole (mm, default 0.3, tolerances.md print-in-place)")
        ap.add_argument("--hole", default="teardrop", choices=["teardrop", "round"],
                        help="hinge: hole shape; the wall is measured above a teardrop's point (default) or above a round hole")
        ap.add_argument("--pin", default="integral", choices=["integral", "loose"],
                        help="hinge: the pin is part of leaf A (default, parts.hinge) or a loose pin through every knuckle")
        ap.add_argument("--duty", default=None, choices=list(DUTY_NAMES),
                        help="hinge: compare pin, wall and knuckle length with this duty's P7 floors (latch, lid, decorative)")
        args = ap.parse_args(join_negative_values(sys.argv[1:] if argv is None else argv))
        args.orientation_defaulted = args.orientation is None
        if args.orientation is None:
            args.orientation = "z"
        if args.case in ("pin", "beam", "link", "bearing", "hinge"):
            if args.load is None or args.material is None:
                raise StrengthError("--load and --material are required")
            if args.case == "pin":
                args.support = args.support or ("through" if args.shear == "double" else "stub")
                if args.support not in ("through", "stub"):
                    raise StrengthError("pin: --support is through or stub")
            if args.case == "beam":
                args.support = args.support or "cantilever"
                if args.support not in ("cantilever", "simple"):
                    raise StrengthError("beam: --support is cantilever or simple")
            if args.case == "hinge":
                if args.gap is None:
                    args.gap = 0.3                       # tolerances.md, print-in-place joint
                if args.clearance is None:
                    args.clearance = 0.3
            elif args.gap is None:
                args.gap = 0.0
        out.update(run(args))
        out["ran"] = True
    except (StrengthError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
