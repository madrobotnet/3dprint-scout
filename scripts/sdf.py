#!/usr/bin/env python3
"""
sdf.py - organic shapes from signed distance functions, meshed with manifold3d's level_set.

An SDF gives, for every point, its distance to the surface: negative inside, positive
outside (mm). Smooth blends, shells and offsets are one line each, and the mesh comes out
of one marching pass, closed and free of the needle triangles that height-field booleans
leave behind (python.md). Use it for leaves, grips, handles, reliefs, blended bodies; use
parts.py or plain manifold3d for prismatic mechanical parts.

    import sdf

    body = sdf.capsule([0, 0, 4], [60, 0, 4], 4) | sdf.sphere(8, [60, 0, 6])      # union
    body = sdf.smooth_union(body, sdf.box([20, 10, 6]), k=3)                        # blended
    body = body - sdf.cylinder(2, 20, center=[30, 0, 0])                            # cut
    part = sdf.to_manifold(body, edge_length=0.5)                                   # Manifold

Every SDF carries a bounding box, so to_manifold() picks the grid bounds itself. The cost
is one Python call per grid point (about 2 * (extent / edge_length)^3 calls); to_manifold()
warns on stderr before a run that will take long. Convention check: manifold3d's level_set
wants positive INSIDE, so to_manifold() negates for you; keep the usual sign here.

Needs manifold3d (and numpy, which it depends on).
"""
from __future__ import annotations

import math
import os
import sys
import time

try:
    import manifold3d as m3d
    import numpy as np
except ImportError as exc:  # pragma: no cover
    raise ImportError("sdf.py needs manifold3d (pip install manifold3d)") from exc

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import parts as _parts  # noqa: E402  (clean(): welds the slivers level_set may leave)

INF = float("inf")
_sqrt, _hypot = math.sqrt, math.hypot


class SDF:
    """A signed distance function with a bounding box (lo, hi). Call it as f(x, y, z)."""

    __slots__ = ("fn", "lo", "hi")

    def __init__(self, fn, lo, hi):
        self.fn = fn
        self.lo = tuple(float(v) for v in lo)
        self.hi = tuple(float(v) for v in hi)
        if any(a > b for a, b in zip(self.lo, self.hi)):
            raise ValueError(f"bounds are inverted: {self.lo} > {self.hi}")

    def __call__(self, x, y, z):
        return self.fn(x, y, z)

    @property
    def bounds(self):
        return self.lo, self.hi

    @property
    def size(self):
        return tuple(h - l for l, h in zip(self.lo, self.hi))

    # operators
    def __or__(self, other):
        return union(self, other)

    def __sub__(self, other):
        return subtract(self, other)

    def __and__(self, other):
        return intersect(self, other)

    # transforms
    def translate(self, v):
        tx, ty, tz = (float(c) for c in v)
        f = self.fn
        return SDF(lambda x, y, z: f(x - tx, y - ty, z - tz),
                   (self.lo[0] + tx, self.lo[1] + ty, self.lo[2] + tz),
                   (self.hi[0] + tx, self.hi[1] + ty, self.hi[2] + tz))

    def rotate(self, degrees, axis: str = "z"):
        """Rotate about an axis through the origin (degrees, right-hand rule)."""
        a = math.radians(degrees)
        c, s = math.cos(a), math.sin(a)
        f = self.fn
        if axis == "z":
            fn = lambda x, y, z: f(c * x + s * y, -s * x + c * y, z)              # noqa: E731
        elif axis == "x":
            fn = lambda x, y, z: f(x, c * y + s * z, -s * y + c * z)              # noqa: E731
        elif axis == "y":
            fn = lambda x, y, z: f(c * x - s * z, y, s * x + c * z)               # noqa: E731
        else:
            raise ValueError("axis must be x, y or z")
        corners = [(x, y, z) for x in (self.lo[0], self.hi[0]) for y in (self.lo[1], self.hi[1])
                   for z in (self.lo[2], self.hi[2])]
        rot = []
        for x, y, z in corners:
            if axis == "z":
                rot.append((c * x - s * y, s * x + c * y, z))
            elif axis == "x":
                rot.append((x, c * y - s * z, s * y + c * z))
            else:
                rot.append((c * x + s * z, y, -s * x + c * z))
        return SDF(fn, [min(p[i] for p in rot) for i in range(3)], [max(p[i] for p in rot) for i in range(3)])

    def scale(self, factor):
        """Uniform scale about the origin (keeps true distances)."""
        k = float(factor)
        if k <= 0:
            raise ValueError("scale must be positive")
        f = self.fn
        return SDF(lambda x, y, z: f(x / k, y / k, z / k) * k, [v * k for v in self.lo], [v * k for v in self.hi])

    def mirror(self, axis: str = "x"):
        f = self.fn
        i = "xyz".index(axis)
        lo, hi = list(self.lo), list(self.hi)
        lo[i], hi[i] = -self.hi[i], -self.lo[i]
        if axis == "x":
            return SDF(lambda x, y, z: f(-x, y, z), lo, hi)
        if axis == "y":
            return SDF(lambda x, y, z: f(x, -y, z), lo, hi)
        return SDF(lambda x, y, z: f(x, y, -z), lo, hi)

    def offset(self, r):
        """Grow (r > 0) or shrink (r < 0) the surface by r mm; rounds convex edges."""
        f = self.fn
        r = float(r)
        return SDF(lambda x, y, z: f(x, y, z) - r, [v - r for v in self.lo], [v + r for v in self.hi])

    def shell(self, t):
        """Hollow the solid, keeping its outer surface and a wall of thickness t (mm)."""
        f = self.fn
        t = float(t)
        if t <= 0:
            raise ValueError("wall thickness must be positive")
        return SDF(lambda x, y, z: max(f(x, y, z), -(f(x, y, z) + t)), self.lo, self.hi)


# --------------------------------------------------------------------------- #
# Primitives (exact distances unless noted)
# --------------------------------------------------------------------------- #
def sphere(r: float, center=(0.0, 0.0, 0.0)) -> SDF:
    cx, cy, cz = (float(c) for c in center)
    r = float(r)
    return SDF(lambda x, y, z: _sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) - r,
               (cx - r, cy - r, cz - r), (cx + r, cy + r, cz + r))


def box(size, center: bool = False) -> SDF:
    """Axis-aligned box; corner at the origin like Manifold.cube, or centred."""
    sx, sy, sz = (float(s) / 2 for s in size)
    if min(sx, sy, sz) <= 0:
        raise ValueError("box size must be positive")
    ox, oy, oz = (0.0, 0.0, 0.0) if center else (sx, sy, sz)

    def fn(x, y, z):
        dx, dy, dz = abs(x - ox) - sx, abs(y - oy) - sy, abs(z - oz) - sz
        inside = min(max(dx, dy, dz), 0.0)
        return _sqrt(max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2 + max(dz, 0.0) ** 2) + inside
    return SDF(fn, (ox - sx, oy - sy, oz - sz), (ox + sx, oy + sy, oz + sz))


def rounded_box(size, r: float, center: bool = False) -> SDF:
    """Box with every edge rounded by r (bottom edges too: for parts that print on that face
    prefer parts.rounded_box(..., "top") or intersect with a box to flatten the bottom)."""
    sx, sy, sz = (float(s) for s in size)
    if 2 * r > min(sx, sy, sz):
        raise ValueError("radius does not fit the box")
    inner = box([sx - 2 * r, sy - 2 * r, sz - 2 * r], center)
    if not center:
        inner = inner.translate([r, r, r])
    return inner.offset(r)


def capsule(a, b, r: float) -> SDF:
    """Cylinder with hemispherical ends, from point a to point b, radius r."""
    ax, ay, az = (float(c) for c in a)
    bx, by, bz = (float(c) for c in b)
    vx, vy, vz = bx - ax, by - ay, bz - az
    vv = vx * vx + vy * vy + vz * vz
    r = float(r)

    def fn(x, y, z):
        px, py, pz = x - ax, y - ay, z - az
        t = 0.0 if vv == 0 else min(max((px * vx + py * vy + pz * vz) / vv, 0.0), 1.0)
        return _sqrt((px - t * vx) ** 2 + (py - t * vy) ** 2 + (pz - t * vz) ** 2) - r
    lo = (min(ax, bx) - r, min(ay, by) - r, min(az, bz) - r)
    hi = (max(ax, bx) + r, max(ay, by) + r, max(az, bz) + r)
    return SDF(fn, lo, hi)


def cylinder(r: float, h: float, center=(0.0, 0.0, 0.0), axis: str = "z") -> SDF:
    """Cylinder of radius r and height h along `axis`, starting at `center` (its base centre)."""
    r, h = float(r), float(h)
    cx, cy, cz = (float(c) for c in center)

    def fn(x, y, z):
        px, py, pz = x - cx, y - cy, z - cz
        if axis == "z":
            d_r, d_h = _hypot(px, py) - r, abs(pz - h / 2) - h / 2
        elif axis == "x":
            d_r, d_h = _hypot(py, pz) - r, abs(px - h / 2) - h / 2
        else:
            d_r, d_h = _hypot(px, pz) - r, abs(py - h / 2) - h / 2
        return min(max(d_r, d_h), 0.0) + _sqrt(max(d_r, 0.0) ** 2 + max(d_h, 0.0) ** 2)
    ext = {"z": (r, r, h), "x": (h, r, r), "y": (r, h, r)}[axis]
    off = {"z": (-r, -r, 0.0), "x": (0.0, -r, -r), "y": (-r, 0.0, -r)}[axis]
    lo = (cx + off[0], cy + off[1], cz + off[2])
    return SDF(fn, lo, (lo[0] + (2 * r if axis != "x" else h), lo[1] + (2 * r if axis != "y" else h),
                        lo[2] + (2 * r if axis != "z" else h)))


def torus(R: float, r: float, center=(0.0, 0.0, 0.0)) -> SDF:
    """Ring of tube radius r around a circle of radius R in the XY plane."""
    R, r = float(R), float(r)
    cx, cy, cz = (float(c) for c in center)
    return SDF(lambda x, y, z: _hypot(_hypot(x - cx, y - cy) - R, z - cz) - r,
               (cx - R - r, cy - R - r, cz - r), (cx + R + r, cy + R + r, cz + r))


def polygon2d(points):
    """Exact signed distance to a simple 2D polygon (negative inside). Returns f(x, y) and
    the polygon's bounds; the building block of extrude() and height_field(). Plain Python
    on purpose: per-call numpy overhead made it 10x slower for typical outlines."""
    P = [(float(x), float(y)) for x, y in points]
    if len(P) > 1 and abs(P[0][0] - P[-1][0]) < 1e-12 and abs(P[0][1] - P[-1][1]) < 1e-12:
        P = P[:-1]
    if len(P) < 3:
        raise ValueError("polygon needs at least three (x, y) points")
    n = len(P)
    segs = []
    for i in range(n):
        ax, ay = P[i]
        bx, by = P[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        segs.append((ax, ay, by, ex, ey, 1.0 / (ex * ex + ey * ey or 1e-18)))
    lo = (min(p[0] for p in P), min(p[1] for p in P))
    hi = (max(p[0] for p in P), max(p[1] for p in P))

    def fn(x, y):
        best = INF
        inside = False
        for ax, ay, by, ex, ey, inv in segs:
            px, py = x - ax, y - ay
            t = (px * ex + py * ey) * inv
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            dx, dy = px - t * ex, py - t * ey
            d = dx * dx + dy * dy
            if d < best:
                best = d
            if (ay > y) != (by > y) and ax + (y - ay) * ex / ey > x:      # even-odd crossing
                inside = not inside
        d = _sqrt(best)
        return -d if inside else d
    return fn, lo, hi


def extrude(points, h: float, z0: float = 0.0) -> SDF:
    """Polygon outline extruded along Z from z0 to z0 + h."""
    f2, lo2, hi2 = polygon2d(points)
    h = float(h)

    def fn(x, y, z):
        d2 = f2(x, y)
        dz = abs(z - z0 - h / 2) - h / 2
        return min(max(d2, dz), 0.0) + _sqrt(max(d2, 0.0) ** 2 + max(dz, 0.0) ** 2)
    return SDF(fn, (lo2[0], lo2[1], z0), (hi2[0], hi2[1], z0 + h))


def height_field(points, top, bottom=None, z_range=None) -> SDF:
    """Solid between two surfaces over a 2D outline: bottom(x, y) <= z <= top(x, y), with
    (x, y) inside the polygon `points`. top/bottom are callables (mm); bottom defaults to
    z = 0 (the bed). z_range (zmin, zmax) bounds the grid; it is sampled from the surfaces
    when omitted. This is a bound on the distance, not an exact one: fine for level_set,
    and blends with it stay smooth."""
    f2, lo2, hi2 = polygon2d(points)
    bot = bottom if bottom is not None else (lambda x, y: 0.0)
    if z_range is None:
        xs = np.linspace(lo2[0], hi2[0], 24)
        ys = np.linspace(lo2[1], hi2[1], 24)
        zs = [float(g(x, y)) for x in xs for y in ys for g in (top, bot)]
        z_range = (min(zs), max(zs))

    def fn(x, y, z):
        d2 = f2(x, y)
        dz = max(z - top(x, y), bot(x, y) - z)
        return min(max(d2, dz), 0.0) + _sqrt(max(d2, 0.0) ** 2 + max(dz, 0.0) ** 2)
    return SDF(fn, (lo2[0], lo2[1], float(z_range[0])), (hi2[0], hi2[1], float(z_range[1])))


def revolve(points) -> SDF:
    """Revolve a 2D profile given as (radius, z) points around the Z axis."""
    f2, lo2, hi2 = polygon2d(points)
    if lo2[0] < 0:
        raise ValueError("profile radii must be >= 0")
    R = hi2[0]
    return SDF(lambda x, y, z: f2(_hypot(x, y), z), (-R, -R, lo2[1]), (R, R, hi2[1]))


# --------------------------------------------------------------------------- #
# Combinations
# --------------------------------------------------------------------------- #
def _box_union(a: SDF, b: SDF, grow: float = 0.0):
    return ([min(p, q) - grow for p, q in zip(a.lo, b.lo)], [max(p, q) + grow for p, q in zip(a.hi, b.hi)])


def union(a: SDF, b: SDF) -> SDF:
    fa, fb = a.fn, b.fn
    lo, hi = _box_union(a, b)
    return SDF(lambda x, y, z: min(fa(x, y, z), fb(x, y, z)), lo, hi)


def subtract(a: SDF, b: SDF) -> SDF:
    fa, fb = a.fn, b.fn
    return SDF(lambda x, y, z: max(fa(x, y, z), -fb(x, y, z)), a.lo, a.hi)


def intersect(a: SDF, b: SDF) -> SDF:
    fa, fb = a.fn, b.fn
    lo = [max(p, q) for p, q in zip(a.lo, b.lo)]
    hi = [min(p, q) for p, q in zip(a.hi, b.hi)]
    if any(l > h for l, h in zip(lo, hi)):
        raise ValueError("the bounding boxes do not overlap: the intersection is empty")
    return SDF(lambda x, y, z: max(fa(x, y, z), fb(x, y, z)), lo, hi)


def smooth_union(a: SDF, b: SDF, k: float) -> SDF:
    """Union with a fillet-like blend of radius about k mm where the shapes meet
    (polynomial smooth minimum)."""
    fa, fb = a.fn, b.fn
    k = float(k)
    if k <= 0:
        return union(a, b)

    def fn(x, y, z):
        da, db = fa(x, y, z), fb(x, y, z)
        h = max(k - abs(da - db), 0.0) / k
        return min(da, db) - h * h * k * 0.25
    lo, hi = _box_union(a, b, k * 0.25)
    return SDF(fn, lo, hi)


def smooth_subtract(a: SDF, b: SDF, k: float) -> SDF:
    """a minus b with the cut edge rounded by about k mm."""
    fa, fb = a.fn, b.fn
    k = float(k)
    if k <= 0:
        return subtract(a, b)

    def fn(x, y, z):
        da, db = fa(x, y, z), -fb(x, y, z)
        h = max(k - abs(da - db), 0.0) / k
        return max(da, db) + h * h * k * 0.25
    return SDF(fn, a.lo, a.hi)


def smooth_intersect(a: SDF, b: SDF, k: float) -> SDF:
    fa, fb = a.fn, b.fn
    k = float(k)
    if k <= 0:
        return intersect(a, b)

    def fn(x, y, z):
        da, db = fa(x, y, z), fb(x, y, z)
        h = max(k - abs(da - db), 0.0) / k
        return max(da, db) + h * h * k * 0.25
    lo = [max(p, q) for p, q in zip(a.lo, b.lo)]
    hi = [min(p, q) for p, q in zip(a.hi, b.hi)]
    return SDF(fn, lo, hi)


# --------------------------------------------------------------------------- #
# Meshing
# --------------------------------------------------------------------------- #
DEFAULT_EDGE = 0.5             # mm; about one line width, fine enough for a 0.4 mm nozzle
WARN_EVALS = 3_000_000         # above this, say how long it will take before starting
WARN_SECONDS = 20.0            # or when the timed estimate is longer than this
MAX_EVALS = 60_000_000         # refuse: a grid this size would run for hours


def grid_estimate(sdf: SDF, edge_length: float, bounds=None, samples: int = 200) -> dict:
    """How big the level_set grid will be: evaluations, and a time estimate from timing
    `samples` calls of this SDF at points spread over the bounds."""
    lo, hi = bounds if bounds else _padded_bounds(sdf, edge_length)
    cells = [max(1, int(math.ceil((h - l) / edge_length)) + 1) for l, h in zip(lo, hi)]
    evals = 2 * cells[0] * cells[1] * cells[2]           # body-centred cubic: two grids
    fn = sdf.fn
    pts = [(lo[0] + (hi[0] - lo[0]) * ((i * 0.618) % 1.0), lo[1] + (hi[1] - lo[1]) * ((i * 0.382) % 1.0),
            lo[2] + (hi[2] - lo[2]) * ((i * 0.236) % 1.0)) for i in range(samples)]
    t0 = time.perf_counter()
    for x, y, z in pts:
        fn(x, y, z)
    per_call = (time.perf_counter() - t0) / max(samples, 1)
    return {"bounds": [list(lo), list(hi)], "cells": cells, "evaluations": evals,
            "seconds_estimate": round(evals * per_call, 1)}


def _padded_bounds(sdf: SDF, edge_length: float):
    pad = 2 * edge_length
    return ([v - pad for v in sdf.lo], [v + pad for v in sdf.hi])


def to_manifold(sdf: SDF, edge_length: float = DEFAULT_EDGE, bounds=None, drop_crumbs: bool = True,
                level: float = 0.0, floor: float | None = None, warn: bool = True,
                report: dict | None = None) -> m3d.Manifold:
    """Mesh an SDF into a closed Manifold.

    edge_length: approximate triangle edge (mm); 0.5 is a good default, 0.3 for fine detail.
    bounds: ((xmin, ymin, zmin), (xmax, ymax, zmax)); default: the SDF's own box plus a margin.
    drop_crumbs: remove bodies smaller than 0.1 % of the largest (grid noise that would fail
    M5); cavities and real second bodies are kept. level: extract the surface at this
    distance instead of 0 (negative = grow). floor: cut everything below this Z (0.0 = the
    bed) after meshing, for example the bulge a smooth union leaves below the bed, and weld
    the cut (a plain trim_by_plane leaves sliver triangles that fail M3).
    warn: print the grid size on stderr before a long run. report: a dict to fill with the
    grid size, time, bodies dropped and triangle count.

    The result is checked: manifold status, positive volume, and the slivers that marching
    sometimes leaves are welded away (parts.clean) so M1-M5 pass. Raises ValueError when
    the SDF produced nothing inside the bounds (wrong sign convention, or bounds too small)."""
    if edge_length <= 0:
        raise ValueError("edge_length must be positive")
    if bounds is None:
        lo, hi = _padded_bounds(sdf, edge_length)
    else:
        lo, hi = [float(v) for v in bounds[0]], [float(v) for v in bounds[1]]
    est = grid_estimate(sdf, edge_length, (lo, hi))
    if est["evaluations"] > MAX_EVALS:
        raise ValueError(f"grid of {est['evaluations']:,} evaluations is too large; raise edge_length "
                         f"(now {edge_length}) or shrink the bounds")
    if warn and (est["evaluations"] > WARN_EVALS or est["seconds_estimate"] > WARN_SECONDS):
        print(f"sdf.to_manifold: {est['evaluations']:,} SDF evaluations, roughly {est['seconds_estimate']} s; "
              "raise edge_length for a quick look", file=sys.stderr)
    fn = sdf.fn
    t0 = time.time()
    man = m3d.Manifold.level_set(lambda x, y, z: -fn(x, y, z), [lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]],
                                 edge_length, level)
    seconds = time.time() - t0
    if man.status() != m3d.Error.NoError:
        raise ValueError(f"level_set failed: {man.status()}")
    if man.is_empty() or man.volume() <= 0:
        raise ValueError("the SDF is empty inside the bounds (sign convention: negative inside; "
                         "or the bounds miss the shape)")
    bb = man.bounding_box()
    touch = [i for i in range(3) if bb[i] <= lo[i] + 1.5 * edge_length or bb[i + 3] >= hi[i] - 1.5 * edge_length]
    if touch:
        raise ValueError("the solid reaches the grid bounds on axis " + ", ".join("xyz"[i] for i in touch)
                         + ": the SDF is inverted (positive inside) or its bounds are too small")
    dropped = []
    if drop_crumbs:
        bodies = man.decompose()
        if len(bodies) > 1:
            # decompose() returns cavities as separate, negative-volume components: keep those
            # (they belong to the solid); drop only small positive crumbs (grid noise, M5).
            vols = [b.volume() for b in bodies]
            biggest = max(vols)
            limit = max(edge_length ** 3, 0.001 * biggest)
            kept = [b for b, v in zip(bodies, vols) if v < 0 or v >= limit]
            dropped = [round(v, 4) for v in vols if 0 <= v < limit]
            if dropped:
                man = m3d.Manifold.compose(kept)
    if floor is not None:
        man = man.trim_by_plane([0, 0, 1], float(floor))
        if man.is_empty():
            raise ValueError(f"nothing is left above z = {floor}")
    man = _parts.clean(man)
    if report is not None:
        report.update(est, seconds=round(seconds, 2), triangles=man.num_tri(), dropped_bodies=dropped,
                      volume_mm3=round(man.volume(), 3), bounding_box=[round(v, 4) for v in man.bounding_box()])
    return man


__all__ = ["SDF", "sphere", "box", "rounded_box", "capsule", "cylinder", "torus", "polygon2d", "extrude",
           "height_field", "revolve", "union", "subtract", "intersect", "smooth_union", "smooth_subtract",
           "smooth_intersect", "to_manifold", "grid_estimate", "DEFAULT_EDGE"]
