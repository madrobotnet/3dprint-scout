#!/usr/bin/env python3
"""
fit.py - F3 check: do two mating parts fit, from both sides, with numbers.

Given two STLs placed as they will be assembled, it measures
  - interference: the volume both parts claim (exact boolean intersection, manifold3d);
  - play: how far part B can move along each --play direction before it first touches A
    (bisection on the boolean, to --play-precision mm). A lid seated on a rim has zero gap
    in -Z but 0.2 mm of play sideways: that sideways play is the clearance of the fit;
  - minimum gap: the smallest distance between the two surfaces at the given placement
    (manifold3d min_gap; 0 when the parts touch, as a seated lid does);
  - contact area: how much of the surfaces lie within --contact-tol of each other,
    estimated from random surface samples (numpy; relative error about 1/sqrt(samples)).

Parts are modelled in print orientation, so pass how part B (and A, if needed) sits in
the assembly: --b-rotate rx,ry,rz (degrees, about the part's own origin, X then Y then Z)
and --b-translate x,y,z (mm, applied after the rotation).

  python3 fit.py out/box.stl out/lid.stl --b-rotate 180,0,0 --b-translate 0,40,33 \\
      --min-clearance 0.2

A sweep rotates part B (after its placement) about an axis through a pivot over a range
of angles and reports the interference and gap at each step, the first angle with an
overlap, and a verdict of its own (F3_sweep): a lever that must turn 40 degrees before
it touches its stop, a lid that must open 90 degrees past the box edge.

  python3 fit.py out/body.stl out/lever.stl --sweep-axis z --sweep-pivot 12,0,0 \
      --sweep-angles 0:90:2

Verdict (same JSON style as validate.py): FAIL when the interference is above
--max-interference (a press fit fails by design: compare its interference with the
intended overlap instead); WARN when the smallest play is below --min-clearance, when
the parts bind (zero play) and no --min-clearance was given, or when they are farther
apart than --search (probably a placement mistake); PASS otherwise; UNVERIFIED when
manifold3d is missing or an STL is not a closed mesh (run validate.py first).
Exit 0 when it ran (read "gate"), 1 on a usage or file error.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from threemf import indexed  # noqa: E402
from validate import ArtifactError, read_stl  # noqa: E402

SCHEMA = "3dprint-scout.fit/1"
DEFAULT_SAMPLES = 20000
DEFAULT_CONTACT_TOL = 0.02       # mm; closer than this counts as touching
DEFAULT_MAX_INTERFERENCE = 0.001  # mm3; coincident faces can leave slivers of this order
DEFAULT_SEARCH = 5.0             # mm; gaps beyond this are "not mating"
DEFAULT_PLAY = "1,0,0;-1,0,0;0,1,0;0,-1,0"   # sideways play of a part dropped in from above
DEFAULT_PLAY_PRECISION = 0.001   # mm


class FitError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise FitError(f"usage error: {message}")


def _vec(text, name):
    if not text:
        return [0.0, 0.0, 0.0]
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        raise FitError(f"{name} needs three numbers x,y,z")
    if len(v) != 3:
        raise FitError(f"{name} needs three numbers x,y,z")
    return v


def load_part(path, m3d):
    """STL -> Manifold (welded at validate.py's quantum). Raises FitError if not closed."""
    try:
        verts, faces = indexed(read_stl(path))
    except ArtifactError as exc:
        raise FitError(f"{path}: {exc}")
    import numpy as np
    mesh = m3d.Mesh(vert_properties=np.asarray(verts, dtype=np.float32),
                    tri_verts=np.asarray(faces, dtype=np.uint32))
    man = m3d.Manifold(mesh)
    if man.status() != m3d.Error.NoError or man.is_empty():
        raise FitError(f"{path} is not a closed mesh ({man.status()}); run validate.py and fix M1-M4 first")
    return man


def place(man, rotate, translate):
    if any(rotate):
        man = man.rotate(rotate)
    if any(translate):
        man = man.translate(translate)
    return man


# --------------------------------------------------------------------------- #
# Sampled surface distances (numpy)
# --------------------------------------------------------------------------- #
def _point_triangle_distance(P, A, B, C):
    """Squared distance from points P (n,3) to triangles (A,B,C) (n,3) pairwise (Ericson,
    Real-Time Collision Detection 5.1.5)."""
    import numpy as np
    ab, ac, ap = B - A, C - A, P - A
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = P - B
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = P - C
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-30, 1e-30, denom)
    v = np.clip(vb / denom, 0.0, 1.0)
    w = np.clip(vc / denom, 0.0, 1.0)
    inside = A + ab * v[:, None] + ac * w[:, None]
    # edge / vertex regions
    t_ab = np.clip(np.where(np.abs(d1 - d3) < 1e-30, 0.0, d1 / np.where(np.abs(d1 - d3) < 1e-30, 1.0, d1 - d3)), 0.0, 1.0)
    on_ab = A + ab * t_ab[:, None]
    t_ac = np.clip(np.where(np.abs(d2 - d6) < 1e-30, 0.0, d2 / np.where(np.abs(d2 - d6) < 1e-30, 1.0, d2 - d6)), 0.0, 1.0)
    on_ac = A + ac * t_ac[:, None]
    num, den = d4 - d3, (d4 - d3) + (d5 - d6)
    t_bc = np.clip(np.where(np.abs(den) < 1e-30, 0.0, num / np.where(np.abs(den) < 1e-30, 1.0, den)), 0.0, 1.0)
    on_bc = B + (C - B) * t_bc[:, None]
    cands = np.stack([inside, on_ab, on_ac, on_bc, A, B, C], axis=1)        # (n, 7, 3)
    d = np.einsum("ijk,ijk->ij", cands - P[:, None, :], cands - P[:, None, :])
    face_ok = (va >= 0) & (vb >= 0) & (vc >= 0)
    d[:, 0] = np.where(face_ok, d[:, 0], np.inf)
    return d.min(axis=1)


def sample_surface(V, F, n, rng):
    """n points on the mesh surface, area-weighted; returns (points, total_area)."""
    import numpy as np
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
    total = float(area.sum())
    if total <= 0:
        return np.zeros((0, 3)), 0.0
    pick = rng.choice(len(F), size=n, p=area / total)
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    pts = A[pick] * (1 - s)[:, None] + B[pick] * (s * (1 - r2))[:, None] + C[pick] * (s * r2)[:, None]
    return pts, total


def distances_to_mesh(P, V, F, cutoff):
    """For each point, the distance to the mesh if it is below `cutoff`, else inf. A uniform
    grid of cell size `cutoff` over the triangle boxes is the broad phase."""
    import numpy as np
    n = len(P)
    out = np.full(n, np.inf)
    if n == 0 or len(F) == 0:
        return out
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    lo = np.minimum(np.minimum(A, B), C)
    hi = np.maximum(np.maximum(A, B), C)
    origin = lo.min(axis=0) - cutoff
    cell = float(cutoff)
    buckets = {}
    lo_c = np.floor((lo - origin) / cell).astype(np.int64)
    hi_c = np.floor((hi - origin) / cell).astype(np.int64)
    for t in range(len(F)):
        x0, y0, z0 = lo_c[t]
        x1, y1, z1 = hi_c[t]
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    buckets.setdefault((x, y, z), []).append(t)
    pc = np.floor((P - origin) / cell).astype(np.int64)
    pairs_p, pairs_t = [], []
    for i in range(n):
        cx, cy, cz = pc[i]
        cand = set()
        for x in (cx - 1, cx, cx + 1):
            for y in (cy - 1, cy, cy + 1):
                for z in (cz - 1, cz, cz + 1):
                    b = buckets.get((x, y, z))
                    if b:
                        cand.update(b)
        if cand:
            pairs_p.append(np.full(len(cand), i, dtype=np.int64))
            pairs_t.append(np.fromiter(cand, dtype=np.int64, count=len(cand)))
    if not pairs_p:
        return out
    pi = np.concatenate(pairs_p)
    ti = np.concatenate(pairs_t)
    best = np.full(n, np.inf)
    step = 200_000
    for s in range(0, len(pi), step):
        p, t = pi[s:s + step], ti[s:s + step]
        d2 = _point_triangle_distance(P[p], A[t], B[t], C[t])
        np.minimum.at(best, p, d2)
    d = np.sqrt(best)
    return np.where(d <= cutoff, d, np.inf)


def contact_metrics(a, b, samples, contact_tol, cutoff, seed):
    """Sampled contact area (mm2) and the sampled minimum gap, from both surfaces."""
    import numpy as np
    rng = np.random.default_rng(seed)
    areas, within, mins = [], [], []
    for src, dst in ((a, b), (b, a)):
        ms, md = src.to_mesh(), dst.to_mesh()
        Vs, Fs = np.asarray(ms.vert_properties[:, :3], dtype=np.float64), np.asarray(ms.tri_verts, dtype=np.int64)
        Vd, Fd = np.asarray(md.vert_properties[:, :3], dtype=np.float64), np.asarray(md.tri_verts, dtype=np.int64)
        P, area = sample_surface(Vs, Fs, samples, rng)
        d = distances_to_mesh(P, Vd, Fd, cutoff)
        areas.append(area * float(np.count_nonzero(d <= contact_tol)) / max(len(P), 1))
        within.append(int(np.count_nonzero(np.isfinite(d))))
        mins.append(float(d.min()) if len(d) else math.inf)
    return {"contact_area_mm2": round(sum(areas) / 2, 3),
            "contact_area_from_a_mm2": round(areas[0], 3), "contact_area_from_b_mm2": round(areas[1], 3),
            "samples_per_part": samples, "samples_within_cutoff": within,
            "sampled_min_gap_mm": round(min(mins), 4) if math.isfinite(min(mins)) else None}


# --------------------------------------------------------------------------- #
# Play: travel along a direction until first contact
# --------------------------------------------------------------------------- #
def parse_directions(text):
    dirs = []
    for chunk in (text or "").split(";"):
        chunk = chunk.strip()
        if not chunk or chunk.lower() == "none":
            continue
        v = _vec(chunk, "--play")
        n = math.sqrt(sum(c * c for c in v))
        if n == 0:
            raise FitError("--play directions must not be zero vectors")
        dirs.append([c / n for c in v])
    return dirs


def play(a, b, direction, max_travel, precision, eps):
    """How far B can move along `direction` before it overlaps A: bisection on the
    interference volume. Returns (travel, hit): hit False means free for max_travel."""
    def overlaps(t):
        moved = b.translate([direction[0] * t, direction[1] * t, direction[2] * t])
        inter = a ^ moved
        return (not inter.is_empty()) and inter.volume() > eps
    if overlaps(0.0):
        return 0.0, True
    if not overlaps(max_travel):
        return max_travel, False
    lo, hi = 0.0, max_travel
    while hi - lo > precision:
        mid = (lo + hi) / 2
        if overlaps(mid):
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2, True                    # true value within +- precision / 2


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Sweep: rotate B about an axis through a pivot, step by step
# --------------------------------------------------------------------------- #
def parse_axis(text):
    named = {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}
    if text.lower() in named:
        return named[text.lower()]
    v = _vec(text, "--sweep-axis")
    n = math.sqrt(sum(c * c for c in v))
    if n == 0:
        raise FitError("--sweep-axis must not be a zero vector")
    return [c / n for c in v]


def parse_angles(text):
    try:
        a, b, step = (float(x) for x in text.split(":"))
    except ValueError:
        raise FitError("--sweep-angles needs start:end:step in degrees")
    if step <= 0 or b < a:
        raise FitError("--sweep-angles needs end >= start and a positive step")
    n = int(math.floor((b - a) / step + 1e-9)) + 1
    if n > 3601:
        raise FitError("--sweep-angles: more than 3601 steps")
    return [round(a + i * step, 6) for i in range(n)]


def rotation_about(axis, pivot, deg):
    """3x4 affine matrix (manifold3d) rotating by deg about `axis` through `pivot` (Rodrigues)."""
    import numpy as np
    k = np.asarray(axis, dtype=np.float64)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    th = math.radians(deg)
    R = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)
    p = np.asarray(pivot, dtype=np.float64)
    t = p - R @ p
    return np.c_[R, t]


def sweep(a, b, axis, pivot, angles, eps, search):
    """[{angle_deg, interference_mm3, min_gap_mm}] over the angles, plus the first overlap."""
    rows, first = [], None
    for deg in angles:
        moved = b.transform(rotation_about(axis, pivot, deg)) if deg else b
        inter = a ^ moved
        vol = inter.volume() if not inter.is_empty() else 0.0
        gap = a.min_gap(moved, search)
        rows.append({"angle_deg": deg, "interference_mm3": round(vol, 4), "min_gap_mm": round(gap, 4)})
        if first is None and vol > eps:
            first = deg
    return rows, first


def part_info(path, man):
    bb = man.bounding_box()
    return {"path": path, "triangles": man.num_tri(), "volume_mm3": round(man.volume(), 3),
            "bbox_mm": [round(bb[i + 3] - bb[i], 4) for i in range(3)],
            "bbox_min_mm": [round(bb[i], 4) for i in range(3)]}


def check(args) -> dict:
    out = {"schema": SCHEMA, "ran": True, "gate": None, "parts": {}, "placement": {}, "checks": {}, "metrics": {},
           "warnings": [], "errors": []}
    try:
        import manifold3d as m3d
    except ImportError:
        out["checks"]["F3"] = {"state": "UNVERIFIED", "kind": "hard",
                               "note": "manifold3d is not installed (pip install manifold3d); fit not measured"}
        out["gate"] = "UNVERIFIED"
        return out
    a = place(load_part(args.a, m3d), args.a_rotate, args.a_translate)
    b = place(load_part(args.b, m3d), args.b_rotate, args.b_translate)
    out["parts"] = {"a": part_info(args.a, a), "b": part_info(args.b, b)}
    out["placement"] = {"a": {"rotate_deg": args.a_rotate, "translate_mm": args.a_translate},
                        "b": {"rotate_deg": args.b_rotate, "translate_mm": args.b_translate},
                        "note": "rotation about the part's own origin, X then Y then Z, then the translation"}

    inter = a ^ b
    interference = inter.volume() if not inter.is_empty() else 0.0
    gap = a.min_gap(b, args.search)
    metrics = {"interference_mm3": round(interference, 4),
               "min_gap_mm": round(gap, 4),
               "min_gap_method": "exact between the two meshes (manifold3d min_gap); 0 when they touch or overlap",
               "search_mm": args.search, "contact_tol_mm": args.contact_tol,
               "max_interference_mm3": args.max_interference, "min_clearance_mm": args.min_clearance}
    plays = []
    if interference <= args.max_interference:
        for d in args.play:
            travel, hit = play(a, b, d, args.search, args.play_precision, args.max_interference)
            plays.append({"direction": [round(c, 4) for c in d], "play_mm": round(travel, 4), "contact": hit})
    metrics["play"] = plays
    metrics["play_method"] = (f"B moved along each direction until the boolean overlap exceeds {args.max_interference} mm3, "
                              f"bisection to {args.play_precision} mm; a direction without contact within {args.search} mm "
                              "reports that length with contact false")
    try:
        import numpy  # noqa: F401
        cutoff = max(args.contact_tol * 2, (args.min_clearance or 0.0) * 1.5, 0.5)
        metrics.update(contact_metrics(a, b, args.samples, args.contact_tol, cutoff, args.seed))
        metrics["contact_method"] = (f"{args.samples} random surface points per part, within {args.contact_tol} mm of the "
                                     "other part, area-weighted; relative error about 1/sqrt(points in contact)")
    except ImportError:
        metrics["contact_area_mm2"] = None
        out["warnings"].append("numpy not installed: contact area not estimated")
    out["metrics"] = metrics

    hits = [p["play_mm"] for p in plays if p["contact"]]
    min_play = min(hits) if hits else None
    value = {"interference_mm3": metrics["interference_mm3"], "min_gap_mm": metrics["min_gap_mm"],
             "min_play_mm": min_play, "contact_area_mm2": metrics.get("contact_area_mm2")}
    seated = interference <= args.max_interference and gap <= 1e-6
    far = gap >= args.search - 1e-9
    play_text = ", ".join(f"{p['play_mm']:.3f}" if p["contact"] else f">{args.search:g}" for p in plays)
    if interference > args.max_interference:
        state, note = "FAIL", (f"parts overlap by {interference:.3f} mm3: one of them must shrink where they meet "
                               "(check the clearance in params.json, F2)")
    elif far:
        state, note = "WARN", (f"no part of B is within {args.search} mm of A: either the placement flags are wrong "
                               "or the parts do not mate here")
    elif args.min_clearance is not None and min_play is not None and min_play < args.min_clearance - args.play_precision:
        state, note = "WARN", (f"play of only {min_play:.3f} mm (directions: {play_text}) is below the "
                               f"{args.min_clearance} mm this fit needs (tolerances.md); it will bind or need force")
    elif args.min_clearance is None and min_play is not None and min_play <= args.play_precision:
        state, note = "WARN", (f"parts bind: zero play along at least one direction ({play_text}); pass "
                               "--min-clearance 0 if that is intended, otherwise add the clearance of the fit kind")
    else:
        where = "seated: the parts touch" if seated else f"first contact after {gap:.3f} mm"
        state, note = "PASS", f"no overlap; {where}; play along {len(plays)} directions: {play_text} mm" if plays else f"no overlap; {where}"
    out["checks"]["F3"] = {"state": state, "kind": "hard", "value": value, "note": note}
    if state == "FAIL":
        out["checks"]["F3"]["return_to"] = "phase4"
    out["gate"] = state
    if state == "WARN":
        out["warnings"].append(f"F3: {note}")

    if args.sweep_angles:
        rows, first = sweep(a, b, args.sweep_axis, args.sweep_pivot, args.sweep_angles, args.max_interference, args.search)
        free = [r["angle_deg"] for r in rows if r["interference_mm3"] <= args.max_interference
                and (first is None or r["angle_deg"] < first)]              # free travel before the first contact
        closest = min(rows, key=lambda r: r["min_gap_mm"]) if rows else None
        sw = {"axis": [round(c, 4) for c in args.sweep_axis], "pivot_mm": args.sweep_pivot,
              "angles_deg": [rows[0]["angle_deg"], rows[-1]["angle_deg"]], "step_deg": round(rows[1]["angle_deg"] - rows[0]["angle_deg"], 6) if len(rows) > 1 else None,
              "first_overlap_deg": first, "free_until_deg": free[-1] if free else None,
              "closest": closest, "table": rows,
              "method": "B is rotated about the axis through the pivot after its placement; interference and gap at each angle"}
        out["metrics"]["sweep"] = sw
        if first is None:
            st, note = "PASS", (f"no overlap over {rows[0]['angle_deg']}..{rows[-1]['angle_deg']} deg; closest approach "
                                f"{closest['min_gap_mm']} mm at {closest['angle_deg']} deg")
        else:
            st, note = "FAIL", (f"B overlaps A from {first} deg on (first step with more than {args.max_interference} mm3); "
                                + (f"free through {sw['free_until_deg']} deg" if sw["free_until_deg"] is not None else "no free angle"))
        out["checks"]["F3_sweep"] = {"state": st, "kind": "hard", "value": {k: sw[k] for k in ("first_overlap_deg", "free_until_deg", "closest")},
                                     "note": note}
        if st == "FAIL":
            out["checks"]["F3_sweep"]["return_to"] = "phase4"
            if out["gate"] != "FAIL":
                out["gate"] = "FAIL"
    return out


def main(argv=None):
    try:
        ap = _JsonArgParser(description="3dprint-scout fit check (F3) between two STLs")
        ap.add_argument("a")
        ap.add_argument("b")
        ap.add_argument("--a-rotate", default="", help="rx,ry,rz degrees for part A")
        ap.add_argument("--a-translate", default="", help="x,y,z mm for part A")
        ap.add_argument("--b-rotate", default="", help="rx,ry,rz degrees for part B")
        ap.add_argument("--b-translate", default="", help="x,y,z mm for part B")
        ap.add_argument("--min-clearance", type=float, default=None, help="gap the fit needs (mm); 0 = may touch")
        ap.add_argument("--max-interference", type=float, default=DEFAULT_MAX_INTERFERENCE, help="mm3 allowed")
        ap.add_argument("--contact-tol", type=float, default=DEFAULT_CONTACT_TOL)
        ap.add_argument("--search", type=float, default=DEFAULT_SEARCH, help="gaps beyond this mean 'not mating'")
        ap.add_argument("--play", default=DEFAULT_PLAY, help="directions 'x,y,z;x,y,z' to test travel; 'none' to skip")
        ap.add_argument("--play-precision", type=float, default=DEFAULT_PLAY_PRECISION)
        ap.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
        ap.add_argument("--seed", type=int, default=0)
        ap.add_argument("--sweep-axis", default="z", help="x, y, z or ax,ay,az: the axis B turns about")
        ap.add_argument("--sweep-pivot", default="", help="x,y,z mm: a point on the axis (after B's placement)")
        ap.add_argument("--sweep-angles", default="", help="start:end:step degrees; enables the sweep (write "
                                                            "--sweep-angles=-90:0:5 when it starts with a minus)")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        for name in ("a_rotate", "a_translate", "b_rotate", "b_translate", "sweep_pivot"):
            setattr(args, name, _vec(getattr(args, name), "--" + name.replace("_", "-")))
        args.play = parse_directions(args.play)
        args.sweep_axis = parse_axis(args.sweep_axis)
        args.sweep_angles = parse_angles(args.sweep_angles) if args.sweep_angles else None
        if args.samples < 100 or args.search <= 0 or args.contact_tol <= 0 or args.max_interference < 0 \
                or args.play_precision <= 0:
            raise FitError("--samples >= 100, --search > 0, --contact-tol > 0, --max-interference >= 0, --play-precision > 0")
        out = check(args)
    except (FitError, OSError, ValueError) as exc:
        out = {"schema": SCHEMA, "ran": False, "gate": "FAIL", "checks": {}, "warnings": [], "errors": [str(exc)]}
    print(json.dumps(out, indent=2))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
