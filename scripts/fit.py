#!/usr/bin/env python3
"""
fit.py - F3 check: do two mating parts fit, from both sides, with numbers.

Given two STLs placed as they will be assembled, it measures
  - interference: the volume both parts claim (exact boolean intersection, manifold3d);
  - play: how far part B can move along each --play direction before it first touches A,
    following the whole move (in steps no longer than the current gap, or 0.2 mm, so an
    obstacle B would pass through and leave is found), then bisection on the boolean to
    --play-precision mm. A lid seated on a rim has zero gap
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

A sweep rotates part B (after its placement) about an axis through a pivot, step by step
away from its placed pose, and reports the interference and gap at each step, the angle at
which B first hits A (its stop) and the free travel before it. Angles are travel from the
placed pose in one direction: 0:90:2 turns counter-clockwise about the axis, -40:0:2 (or
0:-40:2) clockwise; a range on both sides of 0 is two sweeps, run them separately. The
verdict F3_sweep needs --sweep-travel DEG, the travel the part must have (a magnitude): PASS
when the part is free through it (a stop beyond it is reported); FAIL when it hits before
it; WARN when it hits and no travel was given (then say what the part must do);
UNVERIFIED when nothing is hit but no travel was given, when the range does not start at 0
or ends before the travel, or when the turn between steps needed more checks than a sweep
allows. Between two steps the turn is followed too, wherever the gaps at the steps do not
cover it, so a thin stop between steps is found. A lever that must turn 40 degrees before
its stop:

  python3 fit.py out/body.stl out/lever.stl --sweep-axis z --sweep-pivot 12,0,0 \
      --sweep-angles 0:90:2 --sweep-travel 40

Verdict (same JSON style as validate.py): FAIL when the interference is above
--max-interference (a press fit fails by design: compare its interference with the
intended overlap instead); WARN when the smallest play is below --min-clearance, when
the parts bind (zero play) and no --min-clearance was given, or when they are farther
apart than --search (probably a placement mistake); PASS otherwise; UNVERIFIED when
manifold3d is missing or an STL is not a closed mesh (run validate.py first).
Exit 0 when it ran (read "gate"), 1 on a usage or file error.

Each part in the report carries the sha256 of its STL, and the input_hash of its build
manifest when that manifest records this very STL (null otherwise). A saved report is
evidence only for the STLs it measured (G1): --check REPORT.json compares the recorded
sha256 with the STLs at the recorded paths, run from the folder the fit was run in. F3_fresh:
PASS when both match; FAIL (STALE) when a part changed since, run the fit again; UNVERIFIED
when the report has no sha256 (written before fit.py recorded them).

  python3 fit.py out/box.stl out/lid.stl --b-rotate 180,0,0 --b-translate 0,40,33 > out/fit_box_lid.json
  python3 fit.py --check out/fit_box_lid.json
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
from validate import ArtifactError, file_sha256, manifest_path, read_stl  # noqa: E402

SCHEMA = "3dprint-scout.fit/1"
DEFAULT_SAMPLES = 20000
DEFAULT_CONTACT_TOL = 0.02       # mm; closer than this counts as touching
DEFAULT_MAX_INTERFERENCE = 0.001  # mm3; coincident faces can leave slivers of this order
DEFAULT_SEARCH = 5.0             # mm; gaps beyond this are "not mating"
DEFAULT_PLAY = "1,0,0;-1,0,0;0,1,0;0,-1,0"   # sideways play of a part dropped in from above
DEFAULT_PLAY_PRECISION = 0.001   # mm
PATH_STEP = 0.2                  # mm: the finest step along a move or a turn. A move is followed
                                 # in steps no longer than the current gap (nothing can meet
                                 # sooner) or this; only an obstacle and B's own feature together
                                 # thinner than this along the path (half a 0.4 mm line) could be
                                 # passed unseen
SWEEP_BUDGET = 1000              # turns checked between the steps of one sweep; more and the
                                 # sweep is UNVERIFIED (a slow, huge report helps nobody)


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


def distances_to_mesh(P, V, F, cutoff, cell=None):
    """For each point, the distance to the mesh if it is below `cutoff`, else inf. A uniform
    grid of cell size `cell` (default `cutoff`; never smaller, so the neighbouring cells hold
    every triangle within the cutoff) over the triangle boxes is the broad phase."""
    import numpy as np
    n = len(P)
    out = np.full(n, np.inf)
    if n == 0 or len(F) == 0:
        return out
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    lo = np.minimum(np.minimum(A, B), C)
    hi = np.maximum(np.maximum(A, B), C)
    origin = lo.min(axis=0) - cutoff
    cell = max(float(cutoff), float(cell or 0.0))
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
    """How far B can move along `direction` before it first overlaps A, following the whole
    path: B advances by its current gap to A (a move shorter than the gap cannot make them
    meet), or by PATH_STEP where the gap is smaller, checking the overlap at each stop; the
    first overlap is then narrowed by bisection. An obstacle B would pass through and leave
    (a lip a ring sits behind) is found, not only one still in the way at max_travel.
    Returns (travel, hit): hit False means free for max_travel."""
    def moved(t):
        return b.translate([direction[0] * t, direction[1] * t, direction[2] * t])

    def overlaps(t):
        inter = a ^ moved(t)
        return (not inter.is_empty()) and inter.volume() > eps
    if overlaps(0.0):
        return 0.0, True
    t = 0.0
    while True:
        remaining = max_travel - t
        gap = a.min_gap(moved(t), remaining + PATH_STEP)
        if gap >= remaining:                       # nothing of A within reach of the rest of the move
            return max_travel, False
        nxt = min(max_travel, t + max(gap, PATH_STEP))
        if overlaps(nxt):
            lo, hi = t, nxt
            break
        if nxt >= max_travel:
            return max_travel, False
        t = nxt
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
    """Angles of the sweep in travel order: from the end of the range nearest the placed pose
    (0) outward. The range may be written in either order; the step's sign is ignored."""
    try:
        a, b, step = (float(x) for x in text.split(":"))
    except ValueError:
        raise FitError("--sweep-angles needs start:end:step in degrees")
    step = abs(step)
    lo, hi = min(a, b), max(a, b)
    if step == 0:
        raise FitError("--sweep-angles needs a non-zero step")
    if lo < 0 < hi:
        raise FitError("--sweep-angles: sweep one direction at a time (0:40:2 or -40:0:2); a range on both sides "
                       "of 0 is two sweeps")
    n = int(math.floor((hi - lo) / step + 1e-9)) + 1
    if n > 3601:
        raise FitError("--sweep-angles: more than 3601 steps")
    angles = [round(lo + i * step, 6) for i in range(n)]
    return sorted(angles, key=abs)


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


def reach_radius(b, axis, pivot):
    """The largest distance of B's vertices from the axis through the pivot (mm): a turn by
    d degrees moves no point of B farther than 2 r sin(d / 2)."""
    import numpy as np
    v = np.asarray(b.to_mesh().vert_properties[:, :3], dtype=np.float64) - np.asarray(pivot, dtype=np.float64)
    k = np.asarray(axis, dtype=np.float64)
    radial = v - np.outer(v @ k, k)
    return float(np.sqrt((radial * radial).sum(axis=1)).max()) if len(v) else 0.0


def _reach_deg(gap, radius):
    """Degrees B can turn with no point moving farther than `gap` (so it cannot meet A)."""
    if radius <= 0 or gap >= 2 * radius:
        return 180.0
    return math.degrees(2 * math.asin(max(gap, 0.0) / (2 * radius)))


def sweep(a, b, axis, pivot, angles, eps, search, budget=None):
    """([{angle_deg, interference_mm3, min_gap_mm}], first overlap, reach radius, turns checked
    between steps, whether that check finished). Up to the first overlap the turn between two
    steps is followed too: where the gaps at the two steps leave part of it uncovered (a point
    of B could move farther than the gap), angles in between are added (marked
    "between_steps") until no point of B moves more than PATH_STEP between two checked angles,
    so a thin stop between two steps is found. A part that turns in contact (gap 0 all the
    way) needs the most of them; past `budget` the check stops unfinished."""
    radius = reach_radius(b, axis, pivot)
    fine = math.degrees(PATH_STEP / radius) if radius > 0 else 180.0
    budget = SWEEP_BUDGET if budget is None else budget
    used = [0, True]                                   # turns checked between steps, finished

    def sample(deg):
        moved = b.transform(rotation_about(axis, pivot, deg)) if deg else b
        inter = a ^ moved
        vol = inter.volume() if not inter.is_empty() else 0.0
        gap = a.min_gap(moved, search)
        return {"angle_deg": round(deg, 6), "interference_mm3": round(vol, 4), "min_gap_mm": round(gap, 4)}, vol, gap

    def between(u0, g0, u1, g1, sign):
        """Rows added inside (u0, u1) (travel in degrees) and the first overlap there, or None."""
        if _reach_deg(g0, radius) + _reach_deg(g1, radius) >= u1 - u0 or u1 - u0 <= fine:
            return [], None
        if used[0] >= budget:
            used[1] = False
            return [], None
        used[0] += 1
        m = (u0 + u1) / 2
        row, vol, gm = sample(sign * m)
        row["between_steps"] = True
        hit = vol > eps
        left, first = between(u0, g0, m, 0.0 if hit else gm, sign)
        if first is not None:
            return left, first
        if hit:
            return left + [row], row["angle_deg"]
        right, first = between(m, gm, u1, g1, sign)
        return left + [row] + right, first

    rows, first, prev = [], None, None
    for deg in angles:
        row, vol, gap = sample(deg)
        if first is None and prev is not None:
            extra, first = between(abs(prev[0]), prev[1], abs(deg), gap, -1.0 if deg < 0 else 1.0)
            rows += extra
        rows.append(row)
        if first is None and vol > eps:
            first = deg
        prev = (deg, gap) if vol <= eps else None
    return rows, first, radius, used[0], used[1]


def build_input_hash(path, sha):
    """The manifest's input_hash, only when the manifest records this very STL."""
    mf = manifest_path(path)
    if not os.path.isfile(mf):
        return None
    try:
        with open(mf, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError):
        return None
    return man.get("input_hash") if man.get("artifact_sha256") == sha else None


def part_info(path, man):
    bb = man.bounding_box()
    sha = file_sha256(path)
    return {"path": path, "sha256": sha, "input_hash": build_input_hash(path, sha),
            "triangles": man.num_tri(), "volume_mm3": round(man.volume(), 3),
            "bbox_mm": [round(bb[i + 3] - bb[i], 4) for i in range(3)],
            "bbox_min_mm": [round(bb[i], 4) for i in range(3)]}


def check_report(report_path) -> dict:
    """F3_fresh: does a saved fit report still describe the STLs at its recorded paths?"""
    out = {"schema": SCHEMA, "ran": True, "gate": None, "report": report_path, "parts": {}, "checks": {},
           "warnings": [], "errors": []}
    with open(report_path, encoding="utf-8") as f:
        try:
            rep = json.load(f)
        except ValueError as exc:
            raise FitError(f"{report_path}: not JSON ({exc})")
    if not isinstance(rep, dict) or rep.get("schema") != SCHEMA:
        raise FitError(f"{report_path}: not a {SCHEMA} report")
    parts = rep.get("parts") or {}
    value = {"report_gate": rep.get("gate"), "parts": {}}
    if not rep.get("ran") or not all(isinstance(parts.get(k), dict) for k in ("a", "b")):
        state, note = "UNVERIFIED", "the report did not run (ran false or no parts): nothing to compare"
    elif not all(parts[k].get("sha256") for k in ("a", "b")):
        state, note = "UNVERIFIED", "the report has no sha256 for its parts (written before fit.py recorded them); run fit.py again"
    else:
        changed, missing = [], []
        for k in ("a", "b"):
            path, recorded = parts[k].get("path"), parts[k]["sha256"]
            current = file_sha256(path) if path and os.path.isfile(path) else None
            value["parts"][k] = {"path": path, "recorded_sha256": recorded, "current_sha256": current}
            if current is None:
                missing.append(path)
            elif current != recorded:
                changed.append(path)
        if missing:
            state, note = "FAIL", (f"file not found: {', '.join(map(str, missing))} (run --check from the folder "
                                   "the fit was run in, or run fit.py again)")
        elif changed:
            state, note = "FAIL", f"STALE: {', '.join(changed)} changed after this fit report; run fit.py again"
        else:
            state, note = "PASS", f"both STLs are the ones this report measured (its gate: {rep.get('gate')})"
    out["parts"] = value["parts"]
    out["checks"]["F3_fresh"] = {"state": state, "kind": "hard", "value": value, "note": note}
    if state == "FAIL":
        out["checks"]["F3_fresh"]["return_to"] = "current"
    out["gate"] = state
    return out


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
    metrics["play_method"] = (f"B moved along each direction, in steps no longer than its gap to A or {PATH_STEP} mm, until "
                              f"the boolean overlap first exceeds {args.max_interference} mm3, then bisection to "
                              f"{args.play_precision} mm; a direction without contact within {args.search} mm reports that "
                              "length with contact false")
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
        state, note = "FAIL", (f"parts overlap by {interference:.3f} mm3: if this overlap is a designed snap or press "
                               "fit, compare it with the intended undercut (the designed interference, not a clearance); "
                               "otherwise one part must shrink where they meet (check the clearance in params.json, F2)")
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
        angles = args.sweep_angles
        rows, first, radius, checked, finished = sweep(a, b, args.sweep_axis, args.sweep_pivot, angles,
                                                       args.max_interference, args.search)
        before = rows if first is None else rows[: [r["angle_deg"] for r in rows].index(first)]
        free = [r["angle_deg"] for r in before if r["interference_mm3"] <= args.max_interference]
        closest = min(rows, key=lambda r: r["min_gap_mm"]) if rows else None
        direction = "counter-clockwise" if angles[-1] >= 0 else "clockwise"
        start, end = abs(angles[0]), abs(angles[-1])
        need = abs(args.sweep_travel) if args.sweep_travel is not None else None     # a travel, either way round
        from_pose = start <= 1e-9
        until = free[-1] if free and from_pose else None
        # The table keeps the steps, and of the turns checked between them only the two that
        # bracket the stop; the rest are counted (a part turning in contact needs hundreds).
        keep = {first, until}
        table = [r for r in rows if not r.get("between_steps") or r["angle_deg"] in keep]
        sw = {"axis": [round(c, 4) for c in args.sweep_axis], "pivot_mm": args.sweep_pivot,
              "direction": direction, "angles_deg": [angles[0], angles[-1]],
              "step_deg": round(abs(angles[1] - angles[0]), 6) if len(angles) > 1 else None,
              "reach_radius_mm": round(radius, 3), "between_steps_checked": checked,
              "first_overlap_deg": first, "free_until_deg": until,
              "free_travel_deg": abs(until) if until is not None else 0.0, "required_travel_deg": need,
              "closest": closest, "table": table,
              "method": "B is rotated about the axis through the pivot, from its placed pose outward in travel order; "
                        "interference and gap at each angle, and between two steps wherever their gaps do not cover "
                        f"the turn, until no point of B moves more than {PATH_STEP} mm between two checked angles "
                        f"(at most {SWEEP_BUDGET}); the first overlap is the stop"}
        out["metrics"]["sweep"] = sw
        span = f"{angles[0]}..{angles[-1]} deg ({direction})"
        if first is not None and need is not None and abs(first) < need - 1e-9:
            # A hit inside the needed travel decides on its own, wherever the sweep started.
            st, note = "FAIL", (f"hits at {first} deg, before the required {need:g} deg of travel"
                                + (f" (free through {until} deg)" if until is not None else
                                   " (not free from the placed pose)" if from_pose else ""))
        elif not from_pose:
            # Travel is counted from the placed pose: a sweep that starts later says nothing about
            # the first degrees, where a part is most often caught.
            st, note = "UNVERIFIED", (f"the sweep starts at {angles[0]} deg, not at the placed pose (0): the first "
                                      f"{start:g} deg are not checked; run it from 0")
        elif not finished and (first is None or need is None or abs(first) >= need):
            st, note = "UNVERIFIED", (f"the turn between the steps needed more than {SWEEP_BUDGET} checks (the part stays "
                                      f"within {closest['min_gap_mm']} mm of the other as it turns), so a thin stop between "
                                      "steps is not ruled out: sweep a shorter range at a time, or the parts as lighter "
                                      "proxies")
        elif first is None and need is None:
            st, note = "UNVERIFIED", (f"no overlap over {span}, but the travel the part needs is not given: pass "
                                      "--sweep-travel DEG to decide")
        elif first is None and end + 1e-9 < need:
            st, note = "UNVERIFIED", (f"no overlap over {span}, but the sweep ends at {angles[-1]} deg, short of the "
                                      f"required {need:g} deg: run it through {need:g} deg")
        elif first is None:
            st, note = "PASS", (f"free through the required {need:g} deg: no overlap over {span}; closest approach "
                                f"{closest['min_gap_mm']} mm at {closest['angle_deg']} deg")
        elif need is not None:
            st, note = "PASS", f"free through the required {need:g} deg (last free check {until} deg); stops at {first} deg"
        else:
            st, note = "WARN", (f"hits at {first} deg over {span}, free through {until} deg; pass --sweep-travel DEG "
                                "with the travel the part needs to decide PASS or FAIL" if until is not None else
                                f"hits at {first} deg, the first step; pass --sweep-travel DEG to decide")
        out["checks"]["F3_sweep"] = {"state": st, "kind": "hard",
                                     "value": {k: sw[k] for k in ("first_overlap_deg", "free_until_deg", "free_travel_deg",
                                                                  "required_travel_deg", "closest")},
                                     "note": note}
        if st == "FAIL":
            out["checks"]["F3_sweep"]["return_to"] = "phase4"
            out["gate"] = "FAIL"
        elif st == "WARN":
            out["warnings"].append(f"F3_sweep: {note}")
            if out["gate"] == "PASS":
                out["gate"] = "WARN"
        elif st == "UNVERIFIED":
            out["warnings"].append(f"F3_sweep: {note}")
            if out["gate"] in ("PASS", "WARN"):
                out["gate"] = "UNVERIFIED"                 # the motion is not decided: no PASS from this report
    return out


NEGATIVE_OK = ("--a-rotate", "--a-translate", "--b-rotate", "--b-translate", "--sweep-axis", "--sweep-pivot", "--sweep-angles")


def join_negative_values(argv, options=NEGATIVE_OK):
    """argparse reads `--sweep-angles -40:0:2` as two options; join a value that looks like numbers."""
    import re
    out, i = [], 0
    while i < len(argv):
        tok = argv[i]
        if tok in options and i + 1 < len(argv) and re.fullmatch(r"-[0-9.,:+-]*", argv[i + 1]):
            out.append(f"{tok}={argv[i + 1]}")
            i += 2
        else:
            out.append(tok)
            i += 1
    return out


def main(argv=None):
    try:
        ap = _JsonArgParser(description="3dprint-scout fit check (F3) between two STLs")
        ap.add_argument("a", nargs="?")
        ap.add_argument("b", nargs="?")
        ap.add_argument("--check", metavar="REPORT", default=None,
                        help="saved fit.py JSON: are its STLs still the ones it measured? (F3_fresh)")
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
        ap.add_argument("--sweep-angles", default="", help="start:end:step degrees from the placed pose, one direction "
                                                            "(0:90:2 or -40:0:2); enables the sweep")
        ap.add_argument("--sweep-travel", type=float, default=None,
                        help="degrees the part must turn freely from its placed pose, a magnitude (decides PASS/FAIL)")
        args = ap.parse_args(join_negative_values(sys.argv[1:] if argv is None else argv))
        if args.check:
            if args.a or args.b:
                raise FitError("usage error: --check REPORT takes no STLs (it reads their paths from the report)")
        elif not (args.a and args.b):
            raise FitError("usage error: two STLs A and B are needed (or --check REPORT)")
        for name in ("a_rotate", "a_translate", "b_rotate", "b_translate", "sweep_pivot"):
            setattr(args, name, _vec(getattr(args, name), "--" + name.replace("_", "-")))
        args.play = parse_directions(args.play)
        args.sweep_axis = parse_axis(args.sweep_axis)
        args.sweep_angles = parse_angles(args.sweep_angles) if args.sweep_angles else None
        if args.samples < 100 or args.search <= 0 or args.contact_tol <= 0 or args.max_interference < 0 \
                or args.play_precision <= 0:
            raise FitError("--samples >= 100, --search > 0, --contact-tol > 0, --max-interference >= 0, --play-precision > 0")
        out = check_report(args.check) if args.check else check(args)
    except (FitError, OSError, ValueError) as exc:
        out = {"schema": SCHEMA, "ran": False, "gate": "FAIL", "checks": {}, "warnings": [], "errors": [str(exc)]}
    print(json.dumps(out, indent=2))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
