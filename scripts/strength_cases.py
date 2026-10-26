#!/usr/bin/env python3
"""
strength_cases.py - more hand calculations in strength.py's report format (schema
3dprint-scout.strength/1: the same inputs, inputs_from, from_build, checks, gate and worst, so
finalize.py takes these reports as it takes strength.py's): a printed tube under a band
(worm-gear) hose clamp, a post or block whose root is loaded across the layers, and a snap
arm that tapers or whose undercut grows when tolerances stack. Standard library only; one JSON
document per call.

  python3 strength_cases.py tube --d 100 --t 3 --band-w 9 --tension 500 --material petg_basic --orientation xy
  python3 strength_cases.py post --b 6 --h 4 --length 8 --load finger_push --material pla_basic
  python3 strength_cases.py post --d 5 --length 10 --load 30 --material petg_basic
  python3 strength_cases.py snap --length 16 --h 1.6 --b 6 --undercut 0.8 --taper 0.5 --gap-worst 0.2 --material pla_basic --orientation xy
  python3 strength_cases.py tube --from-build out/build.json --part adapter --param d=spigot_d --param t=spigot_wall --band-w 9 --tension 500 --orientation xy

Why a file of its own: strength.py is a source of every build whose generator imports parts.py
(parts.py loads it for the duty floors and the snap strain table; build.py hashes every skill
module a generator loaded, and validate.py's R3 compares those bytes), so any change to
strength.py makes all of those builds stale (CHANGELOG 0.8.2). No generator loads this file.
It loads strength.py by file path under parts.py's private name and only reads from it: the
material table, the hand-force table, the verdict, the build reader and the origins of the
inputs are strength.py's, unchanged.

Cases
  tube   a printed tube under a band (worm-gear) hose clamp: outside diameter d (--d) where the
         band sits, wall t (--t), band width w (--band-w), band tension T (--tension, N; no
         default and no table: clamp makers publish a tightening torque, not a tension, and
         the torque-to-tension conversion rests on unknown screw friction, so measure it or
         take the maker's figure and record its source). The band's pressure on the tube is
         p = T / (r w); cut the tube and band in half and the band's two ends pull T each, so
         the ring under the band carries a hoop compression N = T: sigma = T / (w t) (thin
         ring, = p r / t), checked against the compressive strength, taken equal to the
         tensile strength (compression is not on the data sheets; an assumption, stated), at
         --sf. The tube beyond the band carries part of N too (neglected: conservative). The
         radial shrink under the band, T r / (E w t) with the tensile modulus, is reported
         (short-term; PLA creeps under a held load). Ring buckling is reported, not checked:
         a pressure from outside the system (suction in a duct) buckles a free ring at
         q_cr = 3 E I / r^3 per unit length of its centre line (r the mean radius, I = w t^3
         / 12; Timoshenko & Gere, Theory of Elastic Stability, 2nd ed., 1961, ch. 7; the
         lowest classical value, a pressure that stays normal to the ring), i.e. p_cr =
         E t^3 / (4 r^3) with the bending modulus. The band's own tension is not checked
         against it: a member in complete contact with the tendon that compresses it cannot
         be buckled by that tendon (ACI 318-11, commentary R18.2.5), and a band locked by its
         screw is such a tendon, so it crushes the tube (the check) rather than buckling it.
         --orientation xy for a tube standing on the bed (the hoop stress runs along the
         layers), z for one lying down (default: conservative).
  post   a post or block standing on its root and pushed sideways: a cantilever of
         rectangular section b x h (--b across the force, --h in its direction) or round
         section d (--d), the force F (--load, N or a hand-force key) at --length above the
         root. Bending at the root sigma = M c / I with M = F L (I = b h^3 / 12, c = h / 2;
         or I = pi d^4 / 64, c = d / 2: sigma = 32 M / (pi d^3)) against the bending
         strength, and the transverse shear on the root plane, peak 3/2 F / A (rectangle) or
         4/3 F / A (circle), against 0.58 x tensile (as strength.py). The default orientation
         z is this case: a post standing on the bed has its layers across it, so the bending
         stress at the root crosses them (the data sheet's Z bending strength) and the shear
         slides layer on layer (0.58 x the Z tensile strength); --orientation xy for a member
         lying flat. Tip deflection F L^3 / (3 E I) with the bending modulus. A straight pull
         along the post is strength.py link --orientation z (F / A against tensile Z).
         (strength.py beam --support cantilever --orientation z already gives the bending of
         a rectangular post; this case adds the round section, the root shear and z by
         intent.)
  snap   strength.py's snap (a straight cantilever arm printed flat, as parts.snap_hook builds
         it; its inputs, formulas, limits and ramps) with:
         --taper a (the thickness at the hook as a fraction of the root's, 0 < a <= 1) or
         --h-tip (that thickness in mm): the thickness falls linearly from h at the root to
         a h at the hook. For a tip load P on such an arm (Euler-Bernoulli; s from the hook,
         h(s) = h (a + (1 - a) s / L)) the tip deflection is y = (12 P / (E b)) int_0^L s^2 /
         h(s)^3 ds and the root strain e = 6 P L / (E b h^2), so e = 1.5 h y / (L^2 Q K) and
         P = 3 E I y / (Q L^3 K) with I the root section's and
           K = 3 (-ln a + 2 a - a^2 / 2 - 3 / 2) / (1 - a)^3   (= 3 sum_n (1 - a)^n / (n + 3))
         K = 1 for a uniform arm; a = 1/2 gives K = 1.636, Bayer's design type 2 (y = 1.09 e
         L^2 / h against 0.67 for a uniform arm: Bayer MaterialScience, Snap-Fit Joints for
         Plastics - A Design Guide, Table 1 and calculation example I; Bayer tabulates only the
         half taper, and its own K, Fig. 10, is a factor for ring-segment sections, not this
         one); the formula reproduces the tapered-hook K table of designerdata.nl to +-0.0005
         for a = 0.33 ... 1.00. For a < 1/2 the strain peaks
         inside the arm, at a / (1 - a) of the length from the hook, 1 / (4 a (1 - a)) times
         the root's; that peak is checked. Q is applied as for a uniform arm.
         --gap-worst g (mm, >= 0): the undercut when tolerances stack is y + g; strain, force
         and the insertion and release forces are given at the nominal y and at y + g, and
         both are checked (strain_worst, bending_worst), so the worst case decides the gate.
         One of --taper, --h-tip or --gap-worst is required: a uniform arm at its nominal
         undercut is strength.py snap.

Loads, materials, orientation, the safety factor, the verdicts and linking to a build
(--from-build, --part, --param INPUT=PARAM; inputs_from; from_build) are strength.py's: see its
docstring. The linkable inputs are each case's inputs below, plus orientation and sf, and load
for post (a tube's load is --tension, a snap's its own deflection force).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_strength():
    """The sibling strength.py by file path under parts.py's private module name: a project's
    own strength.py earlier on sys.path cannot shadow it, and a process that has imported
    parts.py already shares the one module. Nothing here writes to it."""
    name = "_3dps_strength"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, "strength.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


S = _load_strength()
StrengthError = S.StrengthError
SCHEMA = S.SCHEMA
COMPRESSION_RATIO = 1.0     # compressive allowable = tensile strength; not on the data sheets (as bearing in strength.py)
SNAP_MIN_T = 1.2            # mm; design-features.md, snap fits: thickness 1.2 mm minimum

CASES = ("tube", "post", "snap")
COMMON = ("load", "material", "orientation", "sf")
CASE_INPUTS = {
    "tube": {"d", "t", "band_w", "tension"},
    "post": {"b", "h", "d", "length"},
    "snap": {"b", "h", "length", "undercut", "q", "repeated", "entry_angle", "retention_angle", "friction",
             "taper", "h_tip", "gap_worst"},
}
# What a value linked with --param must be: strength.py's kinds for the inputs it has, these for the new ones.
NEW_KIND = {"band_w": "size", "h_tip": "size", "tension": "positive", "taper": "positive", "gap_worst": "non_negative"}
INPUT_KIND = {**{k: S.INPUT_KIND[k] for k in set().union(*CASE_INPUTS.values(), {"load", "orientation", "sf"})
                 if k in S.INPUT_KIND}, **NEW_KIND}
SIZES = ("d", "t", "band_w", "b", "h", "length", "undercut", "h_tip")
LINK_OPTIONS = S.LINK_OPTIONS


# --------------------------------------------------------------------------- #
# Formulas
# --------------------------------------------------------------------------- #
def taper_factor(a: float) -> float:
    """K of a cantilever whose thickness falls linearly from h at the root to a h at the tip,
    width constant, loaded at the tip: e = 1.5 h y / (L^2 Q K), P = 3 E I y / (Q L^3 K) with
    the root section's I (derivation in the module docstring). K(1) = 1; K(1/2) = 1.636, Bayer's
    type 2 (y = 1.09 e L^2 / h = 0.667 K e L^2 / h). Closed form 3 (-ln a + 2 a - a^2 / 2 -
    3 / 2) / (1 - a)^3; near a = 1 that cancels, so the series 3 sum_n k^n / (n + 3), k = 1 - a,
    is used there."""
    if not (isinstance(a, (int, float)) and math.isfinite(a)) or not 0 < a <= 1:
        raise StrengthError("the taper is the thickness at the hook over the thickness at the root: above 0, at most 1")
    k = 1.0 - a
    if k < 0.01:
        return 3.0 * sum(k ** n / (n + 3) for n in range(12))
    return 3.0 * (-math.log(a) + 2 * a - a * a / 2 - 1.5) / k ** 3


def taper_peak(a: float) -> tuple:
    """(peak strain / root strain, distance of the peak from the hook as a fraction of L) for
    the tapered arm: e(s) / e_root = u / (a + (1 - a) u)^2, u = s / L, which is largest at the
    root for a >= 1/2 and at u = a / (1 - a), 1 / (4 a (1 - a)) times the root's, below."""
    if a >= 0.5:
        return 1.0, 1.0
    return 1.0 / (4 * a * (1 - a)), a / (1 - a)


def ring_critical_pressure(E: float, t: float, r: float) -> float:
    """Critical uniform external pressure of a free thin ring of wall t on the mean radius r:
    q_cr = 3 E I / r^3 per unit length of the centre line (Timoshenko & Gere, Theory of Elastic
    Stability, ch. 7; a pressure that stays normal to the ring), I = w t^3 / 12 for a width w,
    so p_cr = q_cr / w = E t^3 / (4 r^3). Plane stress (a ring); a long tube in plane strain
    divides it by 1 - nu^2."""
    return E * t ** 3 / (4 * r ** 3)


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
def case_tube(args, mat, o):
    """A printed tube under a band clamp: hoop compression T / (w t) against the compressive
    (= tensile) strength at --sf; the shrink, the band tension at --sf and the free ring's
    critical pressure reported. Returns (checks, notes, extra, load N, load description)."""
    if args.load is not None:
        raise StrengthError("a tube's load is the band tension: --tension N (no hand-force key applies to a clamp)")
    if args.tension is None:
        raise StrengthError("--tension is required: the band tension in N (measured, or the clamp maker's figure; makers "
                            "publish a tightening torque, not a tension, so record where it came from)")
    S.positive(args, "d", "t", "band_w")
    S.positive(args, "tension", unit="N")
    d, t, w, T = args.d, args.t, args.band_w, args.tension
    if t >= d / 2:
        raise StrengthError(f"--t {t} mm leaves no bore in a {d} mm tube: the wall must be under half the diameter")
    r_o, r = d / 2, (d - t) / 2
    E, Ef = mat["E"][o], mat["flex_modulus"][o]
    allow = COMPRESSION_RATIO * mat["tensile"][o]
    sigma = T / (w * t)                                     # hoop force N = T in the ring of width w under the band
    p_o = T / (r_o * w)                                     # the band's pressure on the tube's outside
    shrink = T * r / (E * w * t)                            # sigma r / E, the mean circle
    T_sf = allow * w * t / args.sf
    p_cr = ring_critical_pressure(Ef, t, r)
    checks = {"hoop_compression": S.check(
        "hoop_compression", sigma, allow, args.sf,
        "sigma = T / (w t): cut tube and band in half, the band's two ends pull T each, so the ring of width w under the "
        "band carries a hoop compression T (thin ring; = p r / t with the band's pressure p = T / (r w))",
        f"compressive strength taken as the tensile strength {o.upper()} {mat['tensile'][o]} MPa (compression is not on "
        "the data sheet)")}
    notes = [
        f"band pressure on the tube p = T / (r w) = {p_o:.3f} MPa at its outside (d = {d:g} mm); hoop force {T:g} N in the "
        f"{w:g} x {t:g} mm ring under the band; this tube carries up to {T_sf:.0f} N of band tension at SF {args.sf:g}",
        f"the tube shrinks about {shrink:.2f} mm in radius under the band (T r / (E w t), mean radius {r:g} mm, E "
        f"{o.upper()} {E} MPa, short-term): the clamp's take-up and the hose seal see it",
        "the tube beyond the band carries part of the hoop force (neglected: conservative); near the screw housing the "
        "band leaves the tube and the pressure there is uneven, and friction makes the tension uneven round the band "
        "(neither in the formula)",
        f"ring buckling, reported, not checked: a pressure from outside the system (suction in a duct) buckles a free "
        f"ring of this wall at p_cr = 3 E I / (w r^3) = E t^3 / (4 r^3) = {p_cr:.4f} MPa (Timoshenko & Gere, ch. 7; "
        f"bending modulus {o.upper()} {Ef} MPa). The band's own pressure ({T / (r * w):.3f} MPa on the mean circle) is "
        "not compared with it: a member in complete contact with the tendon that compresses it cannot be buckled by "
        "that tendon (ACI 318-11, R18.2.5), and a band locked by its screw is such a tendon; it crushes the tube "
        "instead (the check). p_cr grows with t^3: a 3 mm wall is (3/2)^3 = 3.4 x a 2 mm wall's",
        "a clamp holds its load for good: PLA creeps under a held load and the band loosens (materials.md); PETG or ASA "
        "hold it better; say to tighten the clamp no more than the hose needs",
        "orientation xy: the tube stands on the bed (axis Z), so the hoop stress runs along the layers" if o == "xy" else
        "orientation z: the hoop stress is taken to cross the layers (a tube lying down; the conservative default); a "
        "tube standing on the bed takes --orientation xy",
    ]
    if t / r > 0.1:
        notes.append(f"a thick wall (t / r = {t / r:.2f}): the thin-ring formulas are approximate")
    extra = {"tube": {"r_mean_mm": round(r, 3), "band_width_mm": w, "band_pressure_mpa": round(p_o, 4),
                      "hoop_force_N": T, "radial_shrink_mm": round(shrink, 3), "tension_at_sf_N": round(T_sf, 1),
                      "ring_critical_pressure_mpa": round(p_cr, 5),
                      "ring_critical_pressure_note": "a free ring under a pressure from outside (suction in a duct), "
                                                     "3 E I / r^3 per unit length (Timoshenko & Gere); not a check "
                                                     "against the band, which cannot buckle the tube it is in contact "
                                                     "with (ACI 318-11, R18.2.5)"}}
    desc = (f"band tension {T:g} N given by the caller (a measurement or the clamp maker's figure: makers publish a "
            "tightening torque, not a tension; record its source in _assumptions)")
    return checks, notes, extra, T, desc


def case_post(args, mat, F, o):
    """A post or block on its root pushed sideways at --length: root bending M c / I and the
    root shear (peak 3/2 or 4/3 of F / A) against the strengths of --orientation (z by
    default: a post standing on the bed). Returns (checks, notes, extra)."""
    rect = args.b is not None or args.h is not None
    if rect == (args.d is not None):
        raise StrengthError("post: give --d (a round post) or --b and --h (a rectangular one: h in the direction of the "
                            "force, b across it), not both")
    S.positive(args, *(("b", "h") if rect else ("d",)), "length")
    L = args.length
    if rect:
        b, h = args.b, args.h
        A, I, c, k, depth = b * h, b * h ** 3 / 12, h / 2, 1.5, h
        sec = f"rectangle b x h = {b:g} x {h:g} mm (h = {h:g} in the direction of the force): I = b h^3 / 12, c = h / 2"
        shear_f = "tau = 3/2 F / (b h)"
    else:
        dd = args.d
        A, I, c, k, depth = math.pi * dd * dd / 4, math.pi * dd ** 4 / 64, dd / 2, 4.0 / 3.0, dd
        sec = f"circle d = {dd:g} mm: I = pi d^4 / 64, c = d / 2, so sigma = 32 M / (pi d^3)"
        shear_f = "tau = 4/3 F / (pi d^2 / 4)"
    M = F * L
    sigma = M * c / I
    tau = k * F / A
    E = mat["flex_modulus"][o]
    defl = F * L ** 3 / (3 * E * I)
    if o == "z":
        bend_basis = (f"bending strength Z {mat['flex']['z']} MPa: the post stands on the bed, so the bending stress at "
                      "its root crosses the layers")
        shear_basis = (f"{S.SHEAR_RATIO} x tensile Z {mat['tensile']['z']} MPa: the shear on the root plane slides "
                       "layer on layer")
    else:
        bend_basis = f"bending strength XY {mat['flex']['xy']} MPa (the member lies flat, bent within the layer plane)"
        shear_basis = f"{S.SHEAR_RATIO} x tensile XY {mat['tensile']['xy']} MPa"
    checks = {
        "bending": S.check("bending", sigma, mat["flex"][o], args.sf, f"sigma = M c / I at the root, M = F L; {sec}",
                           bend_basis),
        "shear": S.check("shear", tau, S.SHEAR_RATIO * mat["tensile"][o], args.sf,
                         f"{shear_f} on the root plane (peak at the neutral axis)", shear_basis),
    }
    notes = [f"lever arm L = {L:g} mm: the force acts that far above the root, where the post leaves the solid below it "
             "(the top of a plate, not the bed)",
             f"moment {M:.2f} N mm; tip deflection {defl:.3f} mm (F L^3 / (3 E I), bending modulus {o.upper()} {E} MPa)",
             "orientation z: the post stands on the bed, its root's layers lie across the bending stress: the layer "
             "joints carry it (the data sheet's Z values)" if o == "z" else
             "orientation xy: the member lies flat and bends within the layer plane; a post standing on the bed is z "
             "(the default)",
             "a sharp root concentrates the stress and a layer seam there is the weakest plane (neither in the formula): "
             "fillet the root (design.md)",
             "a straight pull along the post, across the layers, is strength.py link --orientation z (F / A against the "
             "tensile Z strength)"]
    if L < depth:
        notes.append(f"a block shorter than it is deep (L = {L:g} < {depth:g} mm): beam theory is only a rough guide "
                     "here; the shear check and the root fillet matter more")
    extra = {"deflection_mm": round(defl, 3), "moment_nmm": round(M, 2), "I_mm4": round(I, 4),
             "post": {"section": "rectangle" if rect else "round", "area_mm2": round(A, 3), "lever_arm_mm": L}}
    return checks, notes, extra


def _strain_check(e, limit, family, repeated, formula):
    return {"state": "PASS" if e <= limit else "FAIL", "strain": round(e, 5), "limit": limit,
            "sf_achieved": round(limit / e, 2) if e > 0 else None, "sf_required": 1.0, "formula": formula,
            "strength_basis": f"one-time design strain of {family} {S.SNAP_STRAIN[family]:.1%}"
                              + (f" x {S.SNAP_REPEATED} for a joint opened often" if repeated else "")
                              + " (design.md, snap fits: starting points, calibrate with a test hook)"}


def case_snap(args, mat, o):
    """strength.py's snap with a linear taper (--taper or --h-tip, factor K) and a worst-case
    undercut (--gap-worst): the strain (its peak) against the family's limit, the bending
    stress E e at --sf, the deflection force and the ramp forces, at the nominal undercut and,
    with --gap-worst, at the worst. Returns (checks, notes, extra, load N, load description)."""
    S.positive(args, "b", "h", "length", "undercut")
    S.non_negative(args, "friction", "gap_worst")
    if args.load is not None:
        raise StrengthError("a snap arm's load is its own deflection force (from the undercut): do not pass --load; "
                            "a hand force is bounded by the release force this case reports")
    if args.taper is not None and args.h_tip is not None:
        raise StrengthError("give the taper one way: --taper (the thickness at the hook over the root's) or --h-tip (mm)")
    if args.taper is None and args.h_tip is None and args.gap_worst is None:
        raise StrengthError("this snap adds --taper / --h-tip and --gap-worst to strength.py snap; give one of them (a "
                            "uniform arm at its nominal undercut is strength.py snap)")
    q = 1.0 if args.q is None else args.q
    entry = 30.0 if args.entry_angle is None else args.entry_angle
    retention = 90.0 if args.retention_angle is None else args.retention_angle
    mu = S.SNAP_FRICTION if args.friction is None else args.friction
    if not 0 < entry < 90 or not 0 < retention <= 90:
        raise StrengthError("--entry-angle is between 0 and 90 degrees, --retention-angle between 0 and 90 (90: no release)")
    if not math.isfinite(q) or q <= 0:
        raise StrengthError("--q must be positive (1 for a rigid wall, up to about 2 for a thin one)")
    args.q, args.entry_angle, args.retention_angle, args.friction = q, entry, retention, mu
    b, h, L, y = args.b, args.h, args.length, args.undercut
    if args.h_tip is not None:
        if args.h_tip > h:
            raise StrengthError(f"--h-tip {args.h_tip} mm is the thickness at the hook, at most the root's --h {h} mm (an "
                                "arm thicker at the hook is not a taper this formula covers)")
        a = args.h_tip / h
    elif args.taper is not None:
        if not 0 < args.taper <= 1:
            raise StrengthError("--taper is the thickness at the hook over the thickness at the root: above 0, at most 1")
        a = args.taper
    else:
        a = 1.0
    K = taper_factor(a)
    peak, at_u = taper_peak(a)
    family = S.snap_family(mat)
    limit = S.SNAP_STRAIN[family] * (S.SNAP_REPEATED if args.repeated else 1.0)
    E = mat["flex_modulus"][o]
    I = b * h ** 3 / 12

    def state(yy):
        e = S.snap_strain(L, h, yy, q) / K * peak             # the peak strain (at the root for a >= 1/2)
        P = 3 * E * I * yy / (q * L ** 3) / K
        return e, P, E * e, S.mating_force(P, entry, mu), S.mating_force(P, retention, mu)

    e, P, sigma, w_in, w_rel = state(y)
    max_y = limit * L ** 2 * q * K / (1.5 * h * peak)
    if a < 1:
        where = ("at the root" if peak == 1.0 else
                 f"inside the arm, {at_u:.2f} L from the hook, {peak:.3f} x the root's (a taper under 1/2)")
        strain_f = (f"e = 1.5 h y / (L^2 Q K) at the root, K = {K:.3f} for a thickness tapering to {a:.3g} of the root's "
                    f"at the hook (K = 3 (-ln a + 2 a - a^2/2 - 3/2) / (1 - a)^3; Bayer type 2, a = 1/2: K = 1.636, "
                    f"y = 1.09 e L^2 / h); the peak {where}")
        bend_f = "sigma = E e at the peak strain (= 6 P L / (b h^2) at the root)"
    else:
        strain_f = "e = 1.5 h y / (L^2 Q) at the root"
        bend_f = "sigma = E e = 6 P L / (b h^2) at the root"
    bend_basis = f"bending strength {o.upper()} {mat['flex'][o]} MPa, modulus {E} MPa (ISO 178)"
    checks = {"strain": _strain_check(e, limit, family, args.repeated, f"{strain_f}, full deflection y = the undercut"),
              "bending": S.check("bending", sigma, mat["flex"][o], args.sf, bend_f, bend_basis)}
    g = args.gap_worst
    worst = None
    if g is not None:
        yw = y + g
        ew, Pw, sw, w_in_w, w_rel_w = state(yw)
        checks["strain_worst"] = _strain_check(ew, limit, family, args.repeated,
                                               f"{strain_f}, full deflection y = the worst-case undercut y + g = "
                                               f"{y:g} + {g:g} = {yw:g} mm")
        checks["bending_worst"] = S.check("bending_worst", sw, mat["flex"][o], args.sf,
                                          f"{bend_f}, at the worst-case undercut {yw:g} mm", bend_basis)
        worst = {"undercut_mm": round(yw, 4), "gap_worst_mm": g, "strain": round(ew, 5),
                 "deflection_force_N": round(Pw, 3),
                 "insertion_force_N": round(w_in_w, 2) if w_in_w is not None else None,
                 "release_force_N": round(w_rel_w, 2) if w_rel_w is not None else None}

    def ramps(wi, wr):
        return ((f"{wi:.1f} N" if wi is not None else "not computable (self-locking ramp)")
                + f" in over the {entry:g} deg entry ramp, "
                + (f"{wr:.1f} N" if wr is not None else "no release (90 deg or self-locking: it needs a release window "
                                                         "or a tool, parts.snap_hook)")
                + f" out over the {retention:g} deg retention face")

    notes = [f"deflection force P = 3 E I y / (Q L^3{' K' if a < 1 else ''}) = {P:.2f} N for y = {y:g} mm (E {E} MPa "
             f"{o.upper()}, I = b h^3 / 12 = {I:.4f} mm4 at the root, Q = {q:g}): the arm's own load; a hand force on "
             "the joint is bounded by the release force, not by a hand-force key",
             f"max deflection at the strain limit: {max_y:.3f} mm (undercut {y:g} mm"
             + (" is over it: lengthen or thin the arm, never thicken it" if y > max_y + 1e-9 else " fits")
             + (f"; worst case {y + g:g} mm" + (" is over it" if y + g > max_y + 1e-9 else " fits") if g is not None else "")
             + ")",
             f"forces at the nominal {y:g} mm: {ramps(w_in, w_rel)}; W = P (mu + tan a) / (1 - mu tan a) with mu = {mu:g} "
             "(plastic on plastic, dry: a starting point)",
             "the arm prints flat and flexes within the layer plane (parts.snap_hook): pass --orientation xy for its "
             "modulus and strength; z is the conservative default" if o == "z" else
             "orientation xy: the arm prints flat and flexes within the layer plane (parts.snap_hook)",
             f"length / thickness = {L / h:.1f} at the root (design.md: about 5 to 10 for a PLA arm)"]
    if a < 1:
        notes.append(f"taper: {h:g} mm at the root to {a * h:.3g} mm at the hook (a = {a:.3g}, K = {K:.3f}): for the same "
                     f"undercut the strain and the force are 1 / K = {1 / K:.3f} of a uniform {h:g} mm arm's"
                     + ("" if a >= 0.5 else f"; under a = 1/2 the strain peaks inside the arm, {at_u:.2f} L from the hook, "
                                            f"{peak:.3f} x the root's (Bayer's design type 2 stops at 1/2)"))
        if a * h < SNAP_MIN_T - 1e-9:
            notes.append(f"the hook end is {a * h:.2f} mm thick, under the {SNAP_MIN_T} mm minimum for a snap arm "
                         "(design-features.md, snap fits)")
    if worst is not None:
        notes.append(f"worst-case undercut {worst['undercut_mm']:g} mm (nominal {y:g} + {g:g} from the tolerance stack): "
                     f"strain {worst['strain']:.4f} against {limit:g}, force {worst['deflection_force_N']:.2f} N, "
                     f"{ramps(w_in_w, w_rel_w)}")
    extra = {"snap": {"strain": round(e, 5), "limit": limit, "family": family, "repeated": bool(args.repeated),
                      "max_deflection_mm": round(max_y, 3), "deflection_force_N": round(P, 3),
                      "insertion_force_N": round(w_in, 2) if w_in is not None else None,
                      "release_force_N": round(w_rel, 2) if w_rel is not None else None,
                      "friction": mu, "q": q, "I_mm4": round(I, 4), "length_to_thickness": round(L / h, 2),
                      "taper": round(a, 6), "h_tip_mm": round(a * h, 4), "K": round(K, 4),
                      "peak_factor": round(peak, 4), "peak_from_hook": round(at_u, 4), "worst": worst}}
    desc = (f"the arm's own deflection force at the {y:g} mm undercut (3 E I y / (Q L^3{' K' if a < 1 else ''}))"
            + (f"; {worst['deflection_force_N']:g} N at the worst-case {worst['undercut_mm']:g} mm" if worst else "")
            + "; no hand-force key applies to a flexure")
    return checks, notes, extra, P, desc


# --------------------------------------------------------------------------- #
# Linking to a build: strength.link_build's rules for these cases' inputs
# --------------------------------------------------------------------------- #
def linkable_inputs(case: str) -> set:
    """The inputs --param can set: the case's own, orientation, sf, and load for a post (a tube's
    load is its tension, a snap's its own deflection force); never the material."""
    return {"orientation", "sf"} | ({"load"} if case == "post" else set()) | CASE_INPUTS[case]


def link_value(case: str, inp: str, param: str, raw):
    """strength.link_value for the inputs strength.py has; its number rule for the new ones
    (band_w and h_tip above zero in mm, tension and taper above zero, gap_worst zero or more)."""
    if inp in S.INPUT_KIND:
        return S.link_value(case, inp, param, raw)
    shown = json.dumps(raw)
    if len(shown) > 60:
        shown = shown[:57] + "..."
    where = f"--param {inp}={param}: the build has {param} = {shown}; {inp} takes"
    kind = NEW_KIND[inp]
    if not S._finite(raw):
        raise StrengthError(f"{where} a finite number")
    if kind == "non_negative" and raw < 0:
        raise StrengthError(f"{where} zero or a positive number")
    if kind != "non_negative" and raw <= 0:
        raise StrengthError(f"{where} a positive number" + (" (mm)" if kind == "size" else ""))
    return float(raw)


def link_build(args) -> dict:
    """--from-build, --part and --param as strength.link_build: the part's material and each
    linked input set on `args` (args.linked), the report's "from_build" block returned."""
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
            raise StrengthError(f"--param takes INPUT=PARAM (t=spigot_wall), not '{text}'")
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
    build = S.read_build(path)
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
    if not isinstance(mat, str) or mat not in S.MATERIALS:
        raise StrengthError(f"{path} records the material {json.dumps(mat)} for {args.part}, not a strength.py material "
                            f"key ({', '.join(S.MATERIALS)})")
    args.material = mat
    block = {"build": path, "part": args.part, "sha256": sha, "material": mat, "parameters": {}}
    if links:
        p = build.get("parameters")
        if not (isinstance(p, dict) and p.get("scope") in ("merged", "overrides") and isinstance(p.get("values"), dict)):
            raise StrengthError(f"--from-build {path}: records no parameters ({{\"scope\": \"merged\" | \"overrides\", "
                                "\"values\": {...}}): build it again with this version of build.py")
        values, scope = p["values"], p["scope"]
        for inp, param in links.items():
            found, raw = S.param_value(values, param)
            if not found:
                if scope == "overrides":
                    raise StrengthError(f"--param {inp}={param}: '{param}' is not in the build's parameters, and this "
                                        "build (scope overrides) records only what params.json passed, so a generator's "
                                        "default is not recorded: put it in params.json and build again")
                names = S._leaf_names(values)
                raise StrengthError(f"--param {inp}={param}: '{param}' is not in the build's parameters (scope merged, "
                                    f"the generator's defaults and params.json: {', '.join(names[:30]) or 'none'}"
                                    + (", ..." if len(names) > 30 else "") + ")")
            setattr(args, inp, link_value(args.case, inp, param, raw))
            block["parameters"][inp] = {"param": param, "value": raw}
    args.linked = links
    return block


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
STATIC = {
    "tube": "static hand calculation on a thin ring, the band's pressure even all round and carried by the band's width "
            "alone: no creep, no stress at the screw housing, the hose's share neglected",
    "post": "static hand calculation on a solid section with the load at one point: no stress concentration at the root "
            "(fillet it), no fatigue, no impact, no lever ratio (pass the amplified force when a lever multiplies the "
            "hand force)",
    "snap": "static hand calculation on a solid section with the load spread evenly: no stress concentration at corners "
            "(fillet the roots), no fatigue, no impact, no lever ratio (pass the amplified force when a lever multiplies "
            "the hand force)",                  # strength.py's own line for its snap
}
NEXT = {
    "tube": {"PASS": "the tube holds the band on paper; a clamp holds its load for good, so PETG or ASA rather than PLA, "
                     "and tighten it no more than the hose needs",
             "WARN": "short margin: thicken the wall under the band (or a collar there) or use a wider band; print the "
                     "spigot ring first and clamp it (SKILL.md, Phase 4)",
             "FAIL": "the band crushes the tube on paper: thicken the wall under the band (or a collar there), use a "
                     "wider band, or tighten less"},
    "post": {"PASS": "the root holds on paper; the margin covers the usual unknowns, fillet the root",
             "WARN": "short margin: grow the post in the direction of the force, shorten the lever arm or fillet the "
                     "root; or print the part alone first (SKILL.md, Phase 4)",
             "FAIL": "the root breaks on paper: grow the post in the direction of the force, shorten the lever arm, or "
                     "print it so its root's layers do not cross the stress (lying flat)"},
    "snap": {"PASS": "the arm holds on paper; print the snap alone first and feel the insertion force (Phase 4)",
             "WARN": "short bending margin: lengthen the arm or reduce the undercut (not thicker: that raises the "
                     "strain), or print the snap alone first",
             "FAIL": "the arm yields or breaks on paper: lengthen it, thin or taper it, or reduce the undercut, never "
                     "thicken it"},
}


def run(args) -> dict:
    mat = S.material(args.material)
    o = args.orientation
    if o not in S.CHOICES["orientation"]:
        raise StrengthError("--orientation is xy (stress within the layer plane) or z (stress across layers)")
    if not math.isfinite(args.sf) or args.sf < 1.0:
        raise StrengthError("--sf must be a number of at least 1.0")
    for name in SIZES:
        v = getattr(args, name)
        if v is not None and (not math.isfinite(v) or v <= 0):
            raise StrengthError(f"--{name.replace('_', '-')} must be a positive number (mm)")
    for name in ("tension", "taper"):
        v = getattr(args, name)
        if v is not None and (not math.isfinite(v) or v <= 0):
            raise StrengthError(f"--{name} must be a positive number" + (" (N)" if name == "tension" else ""))
    S.non_negative(args, "gap_worst", "friction")
    stray = sorted(n for n in set(args.given) | set(args.linked)
                   if n not in COMMON and n not in CASE_INPUTS[args.case])
    if stray:
        takes = sorted(linkable_inputs(args.case) | {"material"})
        raise StrengthError(f"{', '.join('--' + n.replace('_', '-') for n in stray)} "
                            f"{'does' if len(stray) == 1 else 'do'} not apply to the {args.case} case (it takes "
                            f"{', '.join('--' + n.replace('_', '-') for n in takes)})")
    extra = {}
    if args.case == "tube":
        checks, notes, extra, F, load_desc = case_tube(args, mat, o)
    elif args.case == "post":
        if args.load is None:
            raise StrengthError("--load is required: the sideways force in N, or a hand-force key")
        F, load_desc = S.load_value(args.load)
        checks, notes, extra = case_post(args, mat, F, o)
    else:
        checks, notes, extra, F, load_desc = case_snap(args, mat, o)
    states = [c["state"] for c in checks.values()]
    gate = "FAIL" if "FAIL" in states else "WARN" if "WARN" in states else "PASS"
    worst = min(checks.values(), key=lambda c: c["sf_achieved"] if c["sf_achieved"] is not None else math.inf)
    assumptions = [
        f"load {round(F, 3) if args.case == 'snap' else F} N: {load_desc}",
        f"material {mat['name']} ({mat['tds']}, retrieved {mat['retrieved']}), {o.upper()} values: the stress "
        + ("acts within the layer plane" if o == "xy" else "crosses the layers (layer adhesion)")
        + ("; z is the conservative default" if args.orientation_defaulted else ""),
        (f"safety factor {args.sf} on the bending stress only; the strain check compares the strain with the one-time "
         "design limit as it is (the limit already holds the layer-bond margin)") if args.case == "snap" else
        (f"safety factor {args.sf}: data-sheet specimens are 100 % infill, dried and annealed; a part has walls, infill, "
         "corners and layer seams, PLA creeps under a held load, and a latch is snapped, not pressed slowly"),
        STATIC[args.case],
    ] + notes
    next_step = NEXT[args.case][gate]
    if args.case == "snap" and gate != "PASS" and "strain_worst" in checks and \
            all(checks[k]["state"] == "PASS" for k in ("strain", "bending")):
        next_step = (f"holds at the nominal {args.undercut:g} mm undercut, not at the worst-case "
                     f"{extra['snap']['worst']['undercut_mm']:g} mm: tighten the tolerance that grows the undercut, "
                     "reduce the undercut, taper or lengthen the arm (never thicken it)")
    keep = set(COMMON) | CASE_INPUTS[args.case]
    linked = getattr(args, "linked", {})
    inputs = {k: v for k, v in vars(args).items() if k in keep and v is not None and (v is not False or k in linked)}
    link = getattr(args, "build_link", None)
    return {"case": args.case, "inputs": inputs, "inputs_from": S.input_origins(args, inputs, mat["key"]),
            **({"from_build": link} if link else {}),
            "load_N": F, "material": {k: mat[k] for k in ("key", "name", "tds", "url", "retrieved")},
            "orientation": o, "checks": checks, "gate": gate,
            "worst": {"check": next(k for k, v in checks.items() if v is worst), "sf_achieved": worst["sf_achieved"]},
            "next_step": next_step, "assumptions": assumptions, **extra}


def parser():
    ap = S._JsonArgParser(description="more hand calculations in strength.py's report format: a tube under a band clamp, "
                                      "a post loaded across the layers, a tapered snap with a worst-case undercut")
    ap.add_argument("case", choices=list(CASES))
    ap.add_argument("--load", help="post: the sideways force in N, or a hand-force key (strength.py loads); not for tube "
                                   "(--tension) or snap (its own deflection force)")
    ap.add_argument("--material", help="pla_basic, pla_matte, pla_pure, petg_basic, petg_hf, abs, asa")
    ap.add_argument("--orientation", help="xy (stress within the layer plane) or z (across layers; default)")
    ap.add_argument("--sf", type=float, default=None, help=f"required safety factor (default {S.DEFAULT_SF})")
    ap.add_argument("--d", type=float, help="tube: outside diameter where the band sits (mm); post: diameter of a round post (mm)")
    ap.add_argument("--t", type=float, help="tube: wall thickness under the band (mm)")
    ap.add_argument("--band-w", type=float, dest="band_w", help="tube: width of the clamp's band (mm)")
    ap.add_argument("--tension", type=float, help="tube: band tension (N), measured or the clamp maker's figure")
    ap.add_argument("--b", type=float, help="post: width across the force (mm); snap: arm width (mm)")
    ap.add_argument("--h", type=float, help="post: depth in the direction of the force (mm); snap: thickness at the root (mm)")
    ap.add_argument("--length", type=float, help="post: height of the force above the root (mm); snap: arm length (mm)")
    ap.add_argument("--undercut", type=float, help="snap: the catch's undercut = the arm's deflection at full travel (mm)")
    ap.add_argument("--q", type=float, default=None, help="snap: deflection magnification, 1 (rigid wall, default) to about 2")
    ap.add_argument("--repeated", action="store_true", help="snap: the joint is opened often (60 %% of the strain limit)")
    ap.add_argument("--entry-angle", type=float, dest="entry_angle", default=None, help="snap: lead-in ramp angle (deg, default 30)")
    ap.add_argument("--retention-angle", type=float, dest="retention_angle", default=None,
                    help="snap: retention face angle (deg, default 90: no release without a window)")
    ap.add_argument("--friction", type=float, default=None, help=f"snap: friction over the ramps (default {S.SNAP_FRICTION})")
    ap.add_argument("--taper", type=float, help="snap: thickness at the hook / thickness at the root (0 < a <= 1)")
    ap.add_argument("--h-tip", type=float, dest="h_tip", help="snap: thickness at the hook (mm), instead of --taper")
    ap.add_argument("--gap-worst", type=float, dest="gap_worst",
                    help="snap: extra undercut when tolerances stack (mm, >= 0): checked at undercut + gap-worst too")
    ap.add_argument("--from-build", dest="from_build", metavar="BUILD_JSON",
                    help="a build.py report (out/build.json): the material is the one it recorded for --part, and "
                         "--param takes inputs from its parameters")
    ap.add_argument("--part", help="with --from-build: the part of the build this member belongs to")
    ap.add_argument("--param", action="append", metavar="INPUT=PARAM",
                    help="with --from-build: take INPUT (d, t, band_w, tension, b, h, length, taper, gap_worst, "
                         "orientation ...) from the build's parameter PARAM (a dotted path reaches into an object); repeatable")
    return ap


def main(argv=None):
    S.utf8_stdout()
    out = {"schema": SCHEMA, "ran": False, "warnings": [], "errors": []}
    try:
        args = parser().parse_args(S.join_negative_values(sys.argv[1:] if argv is None else argv))
        # What the command line gave, before any link or default fills the rest (inputs_from: manual).
        args.given = {k for k, v in vars(args).items()
                      if k != "case" and k not in LINK_OPTIONS and v is not None and v is not False}
        args.linked, args.build_link = {}, None
        if args.from_build is not None or args.part is not None or args.param:
            args.build_link = link_build(args)
        if args.sf is None:
            args.sf = S.DEFAULT_SF
        args.orientation_defaulted = args.orientation is None
        if args.orientation is None:
            args.orientation = "z"
        if args.material is None:
            raise StrengthError("--material is required")
        out.update(run(args))
        out["ran"] = True
    except (StrengthError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
