#!/usr/bin/env python3
"""
parts.py - a small, tested library of FDM-friendly parts for Python generators (manifold3d).

Every function returns a manifold3d.Manifold (or a dict of them) in millimetres, Z-up, with
Z = 0 on the print bed unless the docstring says otherwise. Cutters (holes) are returned as
solids to subtract. Defaults follow references/design.md and references/tolerances.md; every
number that comes from a standard or a datasheet says so next to it, the rest are starting
points to calibrate.

Use from a generator (build.py puts this folder on sys.path, so a plain import works):

    import manifold3d as m3d
    import parts

    def build(p):
        box = parts.rounded_box([60, 40, 25], r=3)
        box -= parts.screw_hole("M3", depth=8, kind="insert").translate([10, 10, 25])
        return {"box": box}

Compensation (F1): holes are modelled at nominal size. Pass `comp=` (radial, per side) only
when the slicer does not compensate holes (tolerances.md).

Needs manifold3d. Text needs matplotlib or fontTools (plus a font file) as well.
"""
from __future__ import annotations

import math
import os
import sys

try:
    import manifold3d as m3d
    import numpy as np                       # a dependency of manifold3d
except ImportError as exc:  # pragma: no cover - the generator cannot run at all without it
    raise ImportError("parts.py needs manifold3d (pip install manifold3d)") from exc

Manifold = m3d.Manifold
CrossSection = m3d.CrossSection

# --------------------------------------------------------------------------- #
# Reference data (sources in references/design.md)
# --------------------------------------------------------------------------- #
# ISO 261 coarse pitch; ISO 273 clearance holes (fine / medium / coarse); tap drill = d - P
# (ISO 262 coarse; in printed plastic a starting point to calibrate); heat-set insert holes
# and lengths from maker charts (Accu: M3 4.0, M4 5.6, M5 6.4, M6 8.0; Albany County
# Fasteners: M2 3.2, M2.5 3.7, lengths = the long end of their ranges) - always prefer the
# datasheet of the insert in hand (insert_d=); M8 insert values are starting points; socket
# head dk / k from ISO 4762; countersunk dk (theoretical) / k from ISO 10642, 90 deg (M2 and
# M2.5 countersink values are starting points).
METRIC = {
    #        pitch  clearance (fine, medium, coarse)  tap   insert hole/len  cap head d/h   csk d/h
    "M2":   {"pitch": 0.40, "clearance": (2.2, 2.4, 2.6), "tap": 1.6, "insert": (3.2, 5.0), "cap": (3.8, 2.0), "csk": (4.4, 1.2)},
    "M2.5": {"pitch": 0.45, "clearance": (2.7, 2.9, 3.1), "tap": 2.05, "insert": (3.7, 6.0), "cap": (4.5, 2.5), "csk": (5.5, 1.5)},
    "M3":   {"pitch": 0.50, "clearance": (3.2, 3.4, 3.6), "tap": 2.5, "insert": (4.0, 6.0), "cap": (5.5, 3.0), "csk": (6.72, 1.86)},
    "M4":   {"pitch": 0.70, "clearance": (4.3, 4.5, 4.8), "tap": 3.3, "insert": (5.6, 8.0), "cap": (7.0, 4.0), "csk": (8.96, 2.48)},
    "M5":   {"pitch": 0.80, "clearance": (5.3, 5.5, 5.8), "tap": 4.2, "insert": (6.4, 10.0), "cap": (8.5, 5.0), "csk": (11.2, 3.1)},
    "M6":   {"pitch": 1.00, "clearance": (6.4, 6.6, 7.0), "tap": 5.0, "insert": (8.0, 12.0), "cap": (10.0, 6.0), "csk": (13.44, 3.72)},
    "M8":   {"pitch": 1.25, "clearance": (8.4, 9.0, 10.0), "tap": 6.8, "insert": (10.0, 12.0), "cap": (13.0, 8.0), "csk": (17.92, 4.96)},
}
FITS = {"fine": 0, "medium": 1, "coarse": 2}

# One-time design strain for a cantilever printed flat (beam flexing within the layer plane).
# Starting points, calibrate with a test hook: derived from bulk one-time values (Bayer:
# PC 4 %, PC/ABS 2.5 %) and printed break strains (Fictiv: PLA 4-8 %, ABS 7 %, nylon 4-15 %)
# with a safety factor for layer bonds (references/design.md, snap fits).
SNAP_STRAIN = {"PLA": 0.010, "PETG": 0.015, "ABS": 0.020, "ASA": 0.020, "PC": 0.025, "PA": 0.030, "NYLON": 0.030}

OVERSHOOT = 0.1          # mm; cutters pass through faces by this much (no coincident faces)
MIN_SEGMENTS = 64        # python.md: enough segments so round parts meet D1
LINE_WIDTH = 0.4         # mm; 0.4 mm nozzle (SKILL.md default)
PRINT_IN_PLACE_CLEARANCE = 0.3   # mm per side (tolerances.md: print-in-place joints)


def circle_segments(r: float, line_width: float = LINE_WIDTH) -> int:
    """Segments so that chord error stays below the line width (python.md)."""
    return max(MIN_SEGMENTS, int(math.ceil(2 * math.pi * max(r, 0.0) / line_width)))


def _size3(size) -> tuple:
    if len(size) != 3 or any(s <= 0 for s in size):
        raise ValueError(f"size must be three positive numbers, got {size!r}")
    return tuple(float(s) for s in size)


def _metric(size: str) -> dict:
    key = str(size).upper().replace(" ", "")
    if key not in METRIC:
        raise ValueError(f"unknown screw size {size!r}; known: {', '.join(METRIC)}")
    return dict(METRIC[key], d=float(key[1:]))


# --------------------------------------------------------------------------- #
# Boxes
# --------------------------------------------------------------------------- #
def rounded_rect(w: float, d: float, r: float, segments: int | None = None) -> CrossSection:
    """2D rectangle w x d with corner radius r, corner at the origin."""
    if r < 0 or 2 * r > min(w, d) + 1e-9:
        raise ValueError(f"corner radius {r} does not fit a {w} x {d} rectangle")
    if r == 0:
        return CrossSection.square([w, d])
    seg = segments or circle_segments(r)
    return CrossSection.square([w - 2 * r, d - 2 * r]).offset(r, m3d.JoinType.Round, 2.0, seg).translate([r, r])


def rounded_box(size, r: float, edges: str = "vertical", segments: int | None = None) -> Manifold:
    """Box with rounded edges, corner at the origin, bottom on the bed.

    edges: "vertical" (default, the four vertical edges; top and bottom stay flat and sharp),
    "top" (vertical and top edges; the bottom edge stays sharp, as design.md asks, P6), or
    "all" (every edge; the bottom fillet is an overhang, so use it only for parts that do not
    print on that face)."""
    w, d, h = _size3(size)
    if edges == "vertical":
        return Manifold.extrude(rounded_rect(w, d, r, segments), h)
    if r <= 0:
        return Manifold.cube([w, d, h])
    seg = segments or circle_segments(r)
    sphere = Manifold.sphere(r, seg)
    if edges == "top":
        if h <= r or 2 * r > min(w, d) + 1e-9:
            raise ValueError(f"radius {r} does not fit a {w} x {d} x {h} box")
        core = Manifold.cube([w - 2 * r, d - 2 * r, h - r]).translate([r, r, 0])
        return clean(core.minkowski_sum(sphere).trim_by_plane([0, 0, 1], 0.0))
    if edges == "all":
        if 2 * r > min(w, d, h) + 1e-9:
            raise ValueError(f"radius {r} does not fit a {w} x {d} x {h} box")
        core = Manifold.cube([w - 2 * r, d - 2 * r, h - 2 * r]).translate([r, r, r])
        return clean(core.minkowski_sum(sphere))
    raise ValueError("edges must be 'vertical', 'top' or 'all'")


def chamfered_box(size, c: float, edges: str = "bottom") -> Manifold:
    """Box with chamfered edges, corner at the origin.

    edges: "bottom" (default: the bed edge, against elephant foot, design.md), "top",
    "vertical", or "all". c is the chamfer leg (45 degrees)."""
    w, d, h = _size3(size)
    if c <= 0:
        return Manifold.cube([w, d, h])
    if 2 * c >= min(w, d) or c >= h:
        raise ValueError(f"chamfer {c} does not fit a {w} x {d} x {h} box")
    thin = 1e-3
    if edges == "bottom":
        foot = Manifold.cube([w - 2 * c, d - 2 * c, thin]).translate([c, c, 0])
        body = Manifold.cube([w, d, h - c]).translate([0, 0, c])
        return Manifold.batch_hull([foot, body])
    if edges == "top":
        cap = Manifold.cube([w - 2 * c, d - 2 * c, thin]).translate([c, c, h - thin])
        body = Manifold.cube([w, d, h - c])
        return Manifold.batch_hull([cap, body])
    if edges == "vertical":
        octagon = [[c, 0], [w - c, 0], [w, c], [w, d - c], [w - c, d], [c, d], [0, d - c], [0, c]]
        return Manifold.extrude(CrossSection([octagon]), h)
    if edges == "all":
        if 2 * c >= h:
            raise ValueError(f"chamfer {c} does not fit a {w} x {d} x {h} box")
        return Manifold.batch_hull([
            Manifold.cube([w - 2 * c, d - 2 * c, h]).translate([c, c, 0]),
            Manifold.cube([w, d - 2 * c, h - 2 * c]).translate([0, c, c]),
            Manifold.cube([w - 2 * c, d, h - 2 * c]).translate([c, 0, c]),
        ])
    raise ValueError("edges must be 'bottom', 'top', 'vertical' or 'all'")


def mesh_arrays(part: Manifold) -> tuple:
    """(vertices (n, 3) float64, triangles (m, 3) int64) of a Manifold."""
    mesh = part.to_mesh()
    return (np.asarray(mesh.vert_properties[:, :3], dtype=np.float64),
            np.asarray(mesh.tri_verts, dtype=np.int64))


def from_arrays(verts, tris) -> Manifold:
    """Manifold from vertex and triangle arrays (faces counter-clockwise seen from outside).
    Raises ValueError with the manifold status when the mesh is not closed."""
    out = Manifold(m3d.Mesh(vert_properties=np.ascontiguousarray(verts, dtype=np.float32),
                            tri_verts=np.ascontiguousarray(tris, dtype=np.uint32)))
    if out.status() != m3d.Error.NoError or out.is_empty():
        raise ValueError(f"mesh is not a closed solid: {out.status()}")
    return out


WELD = 1e-4              # mm; the same quantum validate.py welds with (WELD_Q)


def clean(part: Manifold, weld: float = WELD) -> Manifold:
    """Remove the zero-area slivers that hulls, Minkowski sums and some booleans leave behind
    (coincident vertices, collinear triangles) so that M1-M4 pass once the STL is welded.
    Geometry is unchanged beyond `weld` mm. Raises ValueError if the result is not closed."""
    orig = part.get_tolerance()
    part = part.set_tolerance(max(orig, 1e-5)).set_tolerance(orig)    # collapses some slivers already
    V, F = mesh_arrays(part)
    if len(F) == 0:
        raise ValueError("empty mesh")
    keys = np.round(V / weld).astype(np.int64)
    _, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    F2 = inv.reshape(-1)[F]
    V2 = V[first]
    F2 = _drop_slivers(V2, F2)
    if len(F2) == len(F) and len(V2) == len(V):
        return part
    return from_arrays(V2, F2)


def _drop_slivers(V, F):
    """Faces with a repeated vertex are dropped. A collinear face (three different vertices on
    one line) is a T-junction: the face across its long edge is split at the middle vertex,
    then the sliver is dropped, so every edge keeps two faces."""
    F = np.asarray(F, dtype=np.int64)
    for _ in range(64):
        distinct = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        F = F[distinct]
        area2 = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
        flat = np.nonzero(area2 <= 2e-9)[0]
        if len(flat) == 0:
            return F
        owner = {}
        for i, (a, b, c) in enumerate(F):
            owner[(a, b)] = i
            owner[(b, c)] = i
            owner[(c, a)] = i
        drop, add = set(), []
        for i in flat:
            if i in drop:
                continue
            tri = [int(v) for v in F[i]]
            # the middle vertex lies between the other two
            mid = None
            for k in range(3):
                m, p, q = V[tri[k]], V[tri[(k + 1) % 3]], V[tri[(k + 2) % 3]]
                if np.dot(p - m, q - m) < 0:
                    mid = k
                    break
            if mid is None:
                drop.add(i)                                   # three coincident-ish points
                continue
            m, p, q = tri[mid], tri[(mid + 1) % 3], tri[(mid + 2) % 3]
            # the sliver's edges are q->m, m->p and the long edge p->q; its neighbour across
            # the long edge uses q->p, and gets split at m into (q, m, x) and (m, p, x)
            j = owner.get((q, p))
            if j is None or j in drop or j == i:
                drop.add(i)
                continue
            nb = [int(v) for v in F[j]]
            k = nb.index(q)
            x = nb[(k + 2) % 3]                               # the neighbour's third vertex
            add.append([q, m, x])
            add.append([m, p, x])
            drop.add(i)
            drop.add(j)
        keep = np.ones(len(F), dtype=bool)
        keep[list(drop)] = False
        F = np.concatenate([F[keep], np.asarray(add, dtype=np.int64).reshape(-1, 3)])
    return F


def _offset_contour(pts, dist: float):
    """Move every vertex of a closed polygon `dist` to its left (inside, for a counter-clockwise
    outline) along the corner bisector, mitre limited to 2 x dist at sharp corners."""
    P = np.asarray(pts, dtype=np.float64)
    e1 = P - np.roll(P, 1, axis=0)                    # incoming edges
    e2 = np.roll(P, -1, axis=0) - P                   # outgoing edges
    e1 /= np.maximum(np.linalg.norm(e1, axis=1), 1e-12)[:, None]
    e2 /= np.maximum(np.linalg.norm(e2, axis=1), 1e-12)[:, None]
    n1 = np.stack([-e1[:, 1], e1[:, 0]], axis=1)      # left normals
    n2 = np.stack([-e2[:, 1], e2[:, 0]], axis=1)
    bis = n1 + n2
    L = np.linalg.norm(bis, axis=1)
    straight = L < 1e-9
    bis[straight] = n1[straight]
    L[straight] = 1.0
    bis /= L[:, None]
    cos_half = np.clip(np.einsum("ij,ij->i", bis, n1), 0.5, 1.0)   # mitre limit 2
    return P + bis * (dist / cos_half)[:, None]


def _loops(directed_edges) -> list:
    """Chain directed boundary edges into closed vertex loops."""
    nxt = dict(directed_edges)
    loops, seen = [], set()
    for start in nxt:
        if start in seen:
            continue
        loop, cur = [start], nxt[start]
        seen.add(start)
        while cur != start:
            if cur in seen:
                raise ValueError("boundary is not a set of simple loops")
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
        loops.append(loop)
    return loops


def bottom_chamfer(part: Manifold, c: float) -> Manifold:
    """Chamfer the bed edge of any part whose lowest c mm are a straight extrusion (boxes,
    cylinders, enclosures, tubes: inner edges get chamfered too). The chamfer leg c is
    0.3-0.5 mm against elephant foot (tolerances.md); do not also enable the slicer's
    elephant-foot compensation.

    No booleans: the part is cut at z = c, the flat cut face is replaced by a 45-degree
    skirt down to the outline inset by c, so no sliver triangles appear (M3)."""
    if c <= 0:
        return part
    z0 = part.bounding_box()[2]
    zc = z0 + c
    upper = part.trim_by_plane([0, 0, 1], zc)
    if upper.is_empty():
        raise ValueError("the part is not taller than the chamfer")
    V, F = mesh_arrays(upper)
    on_plane = np.abs(V[:, 2] - zc) < 1e-5
    cap = on_plane[F].all(axis=1)                      # the flat face the cut left behind
    directed = set()
    for a, b, d in F[cap]:
        directed.update([(int(a), int(b)), (int(b), int(d)), (int(d), int(a))])
    loops = _loops([(a, b) for a, b in directed if (b, a) not in directed])
    if not loops:
        raise ValueError("no outline at the chamfer height")
    new_v, band, bottoms, base = [], [], [], len(V)
    for loop in loops:
        loop = loop[::-1]                               # the cut face faces -Z; seen from above its outer loops run clockwise
        inset = _offset_contour(V[loop][:, :2], c)
        n = len(loop)
        idx = list(range(base, base + n))
        base += n
        new_v += [[x, y, z0] for x, y in inset]
        for i in range(n):
            j = (i + 1) % n
            band.append([idx[i], idx[j], loop[j]])
            band.append([idx[i], loop[j], loop[i]])
        bottoms.append((inset, idx))
    tri = np.asarray(m3d.triangulate([b[0] for b in bottoms]), dtype=np.int64)
    if len(tri) == 0:
        raise ValueError(f"a {c} mm chamfer does not fit this outline")
    flat = np.concatenate([np.asarray(b[1]) for b in bottoms])
    bottom = flat[tri[:, [0, 2, 1]]]                   # faces -Z
    V2 = np.concatenate([V, np.asarray(new_v, dtype=np.float64)])
    F2 = np.concatenate([F[~cap], np.asarray(band, dtype=np.int64), bottom])
    try:
        return from_arrays(V2, F2)
    except ValueError as exc:
        raise ValueError(f"a {c} mm chamfer does not fit this outline ({exc})") from exc


# --------------------------------------------------------------------------- #
# Holes (cutters). Mouth at z = 0, the hole goes DOWN to z = -depth, and every cutter
# passes OVERSHOOT above the mouth so the cut never leaves a coincident face.
# --------------------------------------------------------------------------- #
def hole(d: float, depth: float, comp: float = 0.0, segments: int | None = None, overshoot: float = OVERSHOOT) -> Manifold:
    """Plain round cutter: diameter d (+ 2*comp), mouth at z = 0, bottom at z = -depth."""
    if d <= 0 or depth <= 0:
        raise ValueError("hole needs d > 0 and depth > 0")
    r = d / 2 + comp
    return Manifold.cylinder(depth + overshoot, r, r, segments or circle_segments(r)).translate([0, 0, -depth])


def screw_hole(size: str = "M3", depth: float = 10.0, kind: str = "clearance", fit: str = "medium",
               comp: float = 0.0, insert_d: float | None = None, head_clearance: float = 0.3,
               segments: int | None = None) -> Manifold:
    """Cutter for a metric screw. Mouth at z = 0, going down.

    kind: "clearance" (ISO 273, `fit` fine/medium/coarse), "tap" (d - P, screw forms its own
    thread; starting point), "insert" (heat-set insert hole; pass insert_d from the datasheet
    of your insert, the default is the common chart value), "countersunk" (medium clearance
    plus a 90-degree countersink to ISO 10642 dk), "counterbore" (medium clearance plus a
    recess for an ISO 4762 socket head). head_clearance widens head recesses (radial)."""
    spec = _metric(size)
    if kind == "clearance":
        d = spec["clearance"][FITS[fit]]
        return hole(d, depth, comp, segments)
    if kind == "tap":
        return hole(spec["tap"], depth, comp, segments)
    if kind == "insert":
        d = float(insert_d) if insert_d else spec["insert"][0]
        return hole(d, depth, comp, segments)
    if kind in ("countersunk", "counterbore"):
        d = spec["clearance"][FITS["medium"]]
        shank = hole(d, depth, comp, segments)
        if kind == "countersunk":
            top_d = spec["csk"][0] + 2 * head_clearance + 2 * comp
            cone_h = (top_d - d) / 2            # 90 degrees: radius drop equals depth
            r_top = top_d / 2 + OVERSHOOT       # the cone keeps widening above the mouth
            head = Manifold.cylinder(cone_h + OVERSHOOT, d / 2 + comp, r_top,
                                     segments or circle_segments(r_top)).translate([0, 0, -cone_h])
        else:
            hd = spec["cap"][0] + 2 * head_clearance + 2 * comp
            hh = spec["cap"][1] + head_clearance
            head = hole(hd, hh, 0.0, segments)
        return shank + head
    raise ValueError("kind must be clearance, tap, insert, countersunk or counterbore")


def teardrop_profile(r: float, segments: int | None = None) -> CrossSection:
    """Circle of radius r with a 45-degree point on +Y: a horizontal hole that needs no
    support (design.md). The apex sits at y = r * sqrt(2)."""
    circle = CrossSection.circle(r, segments or circle_segments(r))
    k = r / math.sqrt(2)
    roof = CrossSection([[[-k, k], [k, k], [0.0, r * math.sqrt(2)]]])
    return circle + roof


def teardrop_hole(d: float, length: float, axis: str = "x", comp: float = 0.0,
                  overshoot: float = OVERSHOOT, segments: int | None = None) -> Manifold:
    """Cutter for a horizontal hole along `axis` ("x" or "y"), centred on the origin, point up
    (+Z). length is the wall thickness it crosses; the cutter overshoots both ends."""
    if d <= 0 or length <= 0:
        raise ValueError("teardrop_hole needs d > 0 and length > 0")
    r = d / 2 + comp
    prism = Manifold.extrude(teardrop_profile(r, segments), length + 2 * overshoot)
    prism = prism.translate([0, 0, -(length / 2 + overshoot)])     # along Z, centred
    # Extruded along Z with the point on +Y. Rotating 90 deg about X puts the axis on Y and the
    # point on +Z; a further 90 deg about Z turns the axis onto X.
    if axis == "y":
        return prism.rotate([90, 0, 0])
    if axis == "x":
        return prism.rotate([90, 0, 0]).rotate([0, 0, 90])
    raise ValueError("axis must be 'x' or 'y'")


# --------------------------------------------------------------------------- #
# Bosses
# --------------------------------------------------------------------------- #
def standoff(h: float, size: str = "M3", kind: str = "insert", wall: float = 2.0, depth: float | None = None,
             foot: float = 0.0, insert_d: float | None = None, comp: float = 0.0, segments: int | None = None) -> Manifold:
    """Round boss on the bed (z = 0) with a screw hole from its top face.

    kind "insert" or "tap" (screw_hole). wall is the plastic around the hole (2.0 mm = five
    0.4 mm lines, design.md). depth defaults to the insert length + 1 mm, or 2 x d for a tap
    hole, and always leaves a 1 mm floor. foot > 0 adds a 45-degree flare at the base (prints
    without support, and spreads the load into the floor)."""
    spec = _metric(size)
    if kind == "insert":
        hole_d = float(insert_d) if insert_d else spec["insert"][0]
        depth = depth if depth is not None else spec["insert"][1] + 1.0
    elif kind == "tap":
        hole_d = spec["tap"]
        depth = depth if depth is not None else 2 * spec["d"]
    else:
        raise ValueError("standoff kind must be 'insert' or 'tap'")
    od = hole_d + 2 * wall
    if depth >= h - 1.0:
        raise ValueError(f"hole depth {depth} leaves less than 1 mm floor in a {h} mm standoff")
    seg = segments or circle_segments(od / 2 + foot)
    body = Manifold.cylinder(h, od / 2, od / 2, seg)
    if foot > 0:
        body += Manifold.cylinder(foot, od / 2 + foot, od / 2, seg)
    cutter = screw_hole(size, depth, kind, comp=comp, insert_d=hole_d if kind == "insert" else None, segments=seg)
    return body - cutter.translate([0, 0, h])


# --------------------------------------------------------------------------- #
# Snap fits (cantilever hook printed flat: beam along +X, flexes in Y, width along Z)
# --------------------------------------------------------------------------- #
def snap_fit_strain(length: float, thickness: float, deflection: float, q: float = 1.0) -> float:
    """Maximum strain at the root of a uniform cantilever: e = 1.5 * t * y / (L^2 * Q)
    (BASF snap-fit design manual; Q = 1 for a beam on a rigid wall, about 2 for short beams
    on a thin wall)."""
    if length <= 0 or thickness <= 0:
        raise ValueError("length and thickness must be positive")
    return 1.5 * thickness * deflection / (length ** 2 * q)


def snap_fit_check(length: float, thickness: float, deflection: float, material: str = "PLA",
                   q: float = 1.0, repeated: bool = False) -> dict:
    """Strain of a hook against the design limit of the material (SNAP_STRAIN; 60 % of it for a
    joint that is opened often, Bayer design guide). Returns a dict; `ok` False means
    lengthen the beam or thin it, not "print and hope"."""
    key = material.upper()
    if key not in SNAP_STRAIN:
        raise ValueError(f"no strain limit for {material!r}; known: {', '.join(SNAP_STRAIN)}")
    limit = SNAP_STRAIN[key] * (0.6 if repeated else 1.0)
    strain = snap_fit_strain(length, thickness, deflection, q)
    max_deflection = limit * length ** 2 * q / (1.5 * thickness)
    return {"strain": round(strain, 5), "limit": limit, "ok": strain <= limit,
            "max_deflection_mm": round(max_deflection, 3), "material": key, "repeated": repeated,
            "length_to_thickness": round(length / thickness, 2)}


def snap_hook(length: float = 16.0, thickness: float = 1.6, width: float = 6.0, undercut: float = 0.8,
              entry_angle: float = 30.0, retention_angle: float = 90.0, flat: float = 0.6,
              root_overlap: float = 0.5, material: str = "PLA") -> Manifold:
    """Cantilever hook lying flat on the bed: root at x = 0 (extended root_overlap into -X so it
    fuses with its wall), beam to x = length with thickness along Y (y in [0, thickness]),
    catch bump on +Y rising `undercut`, printed width along Z (z in [0, width]).

    The catch has a `flat` top, an entry ramp at entry_angle (lead-in, towards +X) and a
    retention face at retention_angle (90 = cannot be pulled off without a release window,
    Bayer design guide). Raises if the strain at full deflection (= undercut) exceeds the
    material's limit (snap_fit_check): make it longer or thinner, never thicker than 1.2 mm
    minimum (tolerances.md). Printed flat, the beam flexes within the layer plane."""
    if min(length, thickness, width, undercut) <= 0:
        raise ValueError("length, thickness, width and undercut must be positive")
    if thickness < 1.2 - 1e-9:
        raise ValueError("snap hook thinner than 1.2 mm (tolerances.md: snap-fit cantilevers)")
    if not 10 <= entry_angle <= 60 or not 30 <= retention_angle <= 90:
        raise ValueError("entry_angle 10-60 and retention_angle 30-90 degrees")
    check = snap_fit_check(length, thickness, undercut, material)
    if not check["ok"]:
        raise ValueError(f"snap hook strain {check['strain']:.3%} exceeds the {material} limit "
                         f"{check['limit']:.1%}; max deflection for this beam is {check['max_deflection_mm']} mm "
                         "(lengthen or thin the beam)")
    entry_run = undercut / math.tan(math.radians(entry_angle))
    ret_run = 0.0 if retention_angle >= 90 else undercut / math.tan(math.radians(retention_angle))
    catch = ret_run + flat + entry_run
    if catch >= length - thickness:
        raise ValueError(f"catch ({catch:.1f} mm) is too long for a {length} mm beam")
    x_ret = length - catch                       # start of the retention face
    t, u = thickness, undercut
    # Counter-clockwise: along the underside, up the tip, back over the catch and the beam.
    outline = [[-root_overlap, 0.0], [length, 0.0], [length, t],
               [length - entry_run, t + u],                   # top of the entry ramp
               [x_ret + ret_run, t + u],                      # end of the flat
               [x_ret, t],                                    # foot of the retention face
               [-root_overlap, t]]
    return Manifold.extrude(CrossSection([outline]), width)


def snap_window(length: float = 16.0, thickness: float = 1.6, width: float = 6.0, undercut: float = 0.8,
                entry_angle: float = 30.0, retention_angle: float = 90.0, flat: float = 0.6,
                wall: float = 2.0, clearance: float = 0.2) -> Manifold:
    """Cutter for the window that the hook from snap_hook(...) (same arguments) snaps into,
    in the hook's coordinate frame: a mating wall whose inner face is at y = thickness +
    clearance. clearance (per side) is the snug fit of tolerances.md. Subtract it from the
    wall at the position where the hook sits."""
    entry_run = undercut / math.tan(math.radians(entry_angle))
    ret_run = 0.0 if retention_angle >= 90 else undercut / math.tan(math.radians(retention_angle))
    catch = ret_run + flat + entry_run
    x0 = length - catch - clearance
    size = [catch + 2 * clearance + OVERSHOOT, wall + 2 * OVERSHOOT, width + 2 * clearance]
    return Manifold.cube(size).translate([x0, thickness + clearance - OVERSHOOT, -clearance])


# --------------------------------------------------------------------------- #
# Print-in-place hinge (axis along X, lying on the bed)
# --------------------------------------------------------------------------- #
def hinge(length: float = 30.0, knuckle_d: float = 8.0, pin_d: float = 3.0, leaf_w: float = 12.0,
          leaf_t: float = 2.4, knuckles: int = 3, clearance: float = PRINT_IN_PLACE_CLEARANCE,
          segments: int | None = None) -> dict:
    """Two leaves joined by a pin, printed assembled. Axis along X at z = knuckle_d / 2, leaf A on
    -Y, leaf B on +Y, both flat on the bed. Knuckles alternate A, B, A ... along X with
    `clearance` between them; the pin is part of A and runs through B's knuckles with
    `clearance` all round. The pin is a teardrop (round below, 45-degree point on top) so it
    prints without support, and the knuckles have a flat underside.

    Returns {"leaf_a": Manifold, "leaf_b": Manifold}: two bodies that never touch. Export both
    into ONE STL (validate with --shells 2) or two STLs placed as built."""
    if knuckles < 2:
        raise ValueError("a hinge needs at least two knuckles")
    R = knuckle_d / 2
    rp = pin_d / 2
    if rp + clearance >= R - 1.2:
        raise ValueError("knuckle wall around the pin is thinner than 1.2 mm; raise knuckle_d")
    if leaf_t > R:
        raise ValueError("leaf thickness must not exceed the knuckle radius")
    seg = segments or circle_segments(R)
    kl = (length - (knuckles - 1) * clearance) / knuckles          # knuckle length along X
    if kl < 2.0:
        raise ValueError("knuckles shorter than 2 mm; use fewer knuckles or a longer hinge")

    def tombstone(r: float) -> CrossSection:
        """Circle of radius r at (0, r) with a flat bottom on y = 0 (profile in the YZ plane)."""
        return CrossSection.circle(r, seg).translate([0, r]) + CrossSection.square([2 * r, r], center=False).translate([-r, 0])

    def along_x(cs: CrossSection, x0: float, lx: float) -> Manifold:
        # Profile drawn in the (y, z) plane as (u, v); extrude along X.
        return Manifold.extrude(cs, lx).rotate([90, 0, 0]).rotate([0, 0, 90]).translate([x0, 0, 0])

    pin_cs = teardrop_profile(rp, seg).translate([0, R])                 # point up, centred on the axis
    pin_hole_cs = teardrop_profile(rp + clearance, seg).translate([0, R])
    leaf_a = Manifold.cube([length, leaf_w, leaf_t]).translate([0, -(R + clearance + leaf_w), 0])
    leaf_b = Manifold.cube([length, leaf_w, leaf_t]).translate([0, R + clearance, 0])
    pin = along_x(pin_cs, 0.0, length)
    neck_len = R + clearance + 2 * OVERSHOOT       # from inside the plate to inside the knuckle
    for i in range(knuckles):
        x0 = i * (kl + clearance)
        knuckle = along_x(tombstone(R), x0, kl)
        if i % 2 == 0:                                                   # leaf A: knuckle + neck + pin
            neck = Manifold.cube([kl, neck_len, leaf_t]).translate([x0, -(R + clearance + OVERSHOOT), 0])
            leaf_a += knuckle + neck
        else:                                                            # leaf B: knuckle + neck, then the pin hole
            neck = Manifold.cube([kl, neck_len, leaf_t]).translate([x0, -OVERSHOOT, 0])
            leaf_b += (knuckle + neck) - along_x(pin_hole_cs, x0 - OVERSHOOT, kl + 2 * OVERSHOOT)
    leaf_a += pin
    return {"leaf_a": clean(leaf_a), "leaf_b": clean(leaf_b)}


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
              "/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts"),
              os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
_FONT_NAMES = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf", "arial.ttf",
               "NotoSans-Bold.ttf", "FreeSansBold.ttf", "Helvetica.ttc"]


def text_backends() -> list:
    """Outline sources that are installed, in the order they are tried."""
    out = []
    try:
        import matplotlib.textpath  # noqa: F401
        out.append("matplotlib")
    except ImportError:
        pass
    try:
        import fontTools.ttLib  # noqa: F401
        out.append("fonttools")
    except ImportError:
        pass
    return out


def find_font() -> str | None:
    """A bold sans-serif font file on this machine (bold strokes print better, design.md)."""
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for name in _FONT_NAMES:
                if name in files:
                    return os.path.join(root, name)
    return None


def _outlines_matplotlib(text: str, font: str | None, weight: str) -> list:
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    prop = FontProperties(fname=font) if font and os.path.isfile(font) else FontProperties(family=font or "DejaVu Sans", weight=weight)
    path = TextPath((0, 0), text, size=1000, prop=prop)      # big size: curves are flattened finely
    return [[(float(x) / 1000.0, float(y) / 1000.0) for x, y in poly] for poly in path.to_polygons() if len(poly) >= 3]


def _outlines_fonttools(text: str, font: str | None, weight: str) -> list:
    from fontTools.pens.basePen import BasePen
    from fontTools.ttLib import TTFont
    path = font if font and os.path.isfile(font) else find_font()
    if not path:
        raise ImportError("fontTools needs a font file: pass font='/path/to/font.ttf'")
    tt = TTFont(path, fontNumber=0)
    upm = float(tt["head"].unitsPerEm)
    cmap = tt.getBestCmap()
    glyphs = tt.getGlyphSet()
    hmtx = tt["hmtx"]

    class FlatPen(BasePen):
        def __init__(self, glyph_set, dx):
            super().__init__(glyph_set)
            self.dx, self.contours, self.cur = dx, [], []

        def _moveTo(self, p):
            self.cur = [(p[0] + self.dx, p[1])]

        def _lineTo(self, p):
            self.cur.append((p[0] + self.dx, p[1]))

        def _curveToOne(self, p1, p2, p3):
            p0 = (self.cur[-1][0] - self.dx, self.cur[-1][1])
            for i in range(1, 17):
                s = i / 16.0
                x = (1 - s) ** 3 * p0[0] + 3 * (1 - s) ** 2 * s * p1[0] + 3 * (1 - s) * s * s * p2[0] + s ** 3 * p3[0]
                y = (1 - s) ** 3 * p0[1] + 3 * (1 - s) ** 2 * s * p1[1] + 3 * (1 - s) * s * s * p2[1] + s ** 3 * p3[1]
                self.cur.append((x + self.dx, y))

        def _closePath(self):
            if len(self.cur) >= 3:
                self.contours.append(self.cur)
            self.cur = []

        def _endPath(self):
            self._closePath()

    out, x = [], 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            name = cmap.get(ord("?")) or ".notdef"
        pen = FlatPen(glyphs, x)
        glyphs[name].draw(pen)
        out += pen.contours
        x += hmtx[name][0]
    return [[(px / upm, py / upm) for px, py in c] for c in out]


def text_outlines(text: str, font: str | None = None, weight: str = "bold") -> list:
    """Closed outlines of `text` in font units (1.0 = the font size), as lists of (x, y)."""
    backends = text_backends()
    if not backends:
        raise ImportError("text needs an outline source: pip install matplotlib (recommended), "
                          "or pip install fonttools and pass font='/path/to/font.ttf'")
    errors = []
    for name in backends:
        try:
            return (_outlines_matplotlib if name == "matplotlib" else _outlines_fonttools)(text, font, weight)
        except ImportError as exc:
            errors.append(f"{name}: {exc}")
    raise ImportError("; ".join(errors))


def text(string: str, height: float = 6.0, depth: float = 1.0, font: str | None = None, weight: str = "bold",
         align: str = "left") -> Manifold:
    """Text as a solid from z = 0 to z = depth, baseline on y = 0, cap height = `height` mm.

    Union it onto a face for embossed text, or subtract it (translated so it starts `depth`
    below the face) for engraved text. Minimum sizes: tolerances.md (0.6 mm high or deep,
    0.8 mm stroke; 1.0 mm recommended). `align`: "left" (x starts at 0) or "center".
    font: a font family name (matplotlib) or a .ttf/.otf path; default a bold sans-serif.
    Needs matplotlib, or fontTools plus a font file (text_backends())."""
    if not string.strip():
        raise ValueError("text is empty")
    if height <= 0 or depth <= 0:
        raise ValueError("height and depth must be positive")
    outlines = text_outlines(string, font, weight)
    cap = text_outlines("H", font, weight)
    cap_h = max(y for c in cap for _, y in c) - min(y for c in cap for _, y in c)
    scale = height / cap_h
    contours = [[[x * scale, y * scale] for x, y in c] for c in outlines]
    cs = CrossSection(contours, m3d.FillRule.NonZero)
    if cs.is_empty():
        raise ValueError("text produced no outline (unsupported characters for this font?)")
    if align == "center":
        x0, _, x1, _ = cs.bounds()
        cs = cs.translate([-(x0 + x1) / 2, 0])
    elif align == "left":
        x0 = cs.bounds()[0]
        cs = cs.translate([-x0, 0])
    else:
        raise ValueError("align must be 'left' or 'center'")
    return Manifold.extrude(cs, depth)


# --------------------------------------------------------------------------- #
# ISO metric threads (approximate: 60-degree flanks, flat crest p/8 and root p/4, no rounding,
# no tolerance class). Built as a twisted extrusion of the thread profile. Printed threads work
# from about M6 up (tolerances.md).
# --------------------------------------------------------------------------- #
THREAD_DEPTH = 5 * math.sqrt(3) / 16     # 0.5413 p: H - H/8 - H/4 with H = 0.866 p (ISO 68-1)


def thread_profile_radius(u: float, r_major: float, pitch: float) -> float:
    """Radius of the ISO profile at axial position u (0..1 of a pitch, crest centred on 0)."""
    u = u % 1.0
    if u > 0.5:
        u = 1.0 - u
    crest, root = 1 / 16, 3 / 8          # crest flat p/8 wide, root flat p/4 wide
    if u <= crest:
        return r_major
    if u >= root:
        return r_major - THREAD_DEPTH * pitch
    return r_major - THREAD_DEPTH * pitch * (u - crest) / (root - crest)


def thread(d: float = 6.0, pitch: float | None = None, length: float = 10.0, internal: bool = False,
           clearance: float = 0.25, points: int = 96, per_turn: int = 24, lead_in: bool = True) -> Manifold:
    """Right-hand single-start ISO metric thread along +Z from z = 0, axis on the origin.

    External (internal=False): a threaded rod of nominal diameter d. Internal (internal=True):
    a CUTTER for a nut or threaded hole, the same profile grown by `clearance` radially (the
    gap measured across the 60-degree flanks is about half of that; starting point, calibrate
    with a short test nut). pitch defaults to the
    ISO coarse pitch of M<d>. `lead_in` chamfers the end faces at 45 degrees to the minor
    diameter (easier start, and the bed edge of an external thread stays printable).
    Approximate: no crest/root rounding, no tolerance class; the agent says so to the user."""
    if d <= 0 or length <= 0:
        raise ValueError("thread needs d > 0 and length > 0")
    key = f"M{d:g}"
    if pitch is None:
        if key not in METRIC:
            raise ValueError(f"no default pitch for {key}; pass pitch=")
        pitch = METRIC[key]["pitch"]
    r_major = d / 2 + (clearance if internal else 0.0)
    pts = []
    for i in range(points):
        u = i / points
        r = thread_profile_radius(u, r_major, pitch)
        a = 2 * math.pi * u
        pts.append([r * math.cos(a), r * math.sin(a)])
    turns = length / pitch
    divisions = max(2, int(math.ceil(turns * per_turn)))
    body = Manifold.extrude(CrossSection([pts]), length, divisions, 360.0 * turns)
    if lead_in:
        r_minor = r_major - THREAD_DEPTH * pitch
        c = r_major - r_minor
        if length <= 2 * c:
            raise ValueError("thread too short for a lead-in chamfer at both ends")
        r_out = r_major + 0.05                     # clear of the crests: only the end cones cut
        profile = CrossSection([[[0.0, -0.01], [r_minor, -0.01], [r_out, c], [r_out, length - c],
                                 [r_minor, length + 0.01], [0.0, length + 0.01]]])
        body = clean(body ^ Manifold.revolve(profile, circle_segments(r_out)))
    if internal:
        body += Manifold.cylinder(OVERSHOOT, r_major, r_major, circle_segments(r_major)).translate([0, 0, -OVERSHOOT])
        body += Manifold.cylinder(OVERSHOOT, r_major, r_major, circle_segments(r_major)).translate([0, 0, length])
    return body


__all__ = [n for n in dir() if not n.startswith("_") and n not in ("math", "os", "sys", "m3d", "np", "annotations")]
