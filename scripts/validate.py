#!/usr/bin/env python3
"""
validate.py - dependency-free mesh validator for 3dprint-scout.

Reads one or more STL files and prints ONE JSON document to stdout with
per-file metrics and a per-check verdict. Standard library only; P3 (wall
thickness) additionally uses numpy + rtree when they happen to be installed.

Verdict states (G3): PASS, FAIL, WARN, N/A, UNVERIFIED.
  - N/A and UNVERIFIED never count as PASS.
  - "hard" checks are deterministic and may trigger an automatic fix loop.
  - "soft" checks are approximations; they can only WARN, never FAIL (G8).

Exit codes: 0 = validator ran (read the JSON for the gate),
            2 = at least one artifact failed the sanity check (G4),
            1 = usage / internal error.

Usage:
  python3 validate.py part.stl [more.stl ...]
      [--expect W,D,H] [--tol 0.1]
      [--printer .3dprint/printers.json] [--printer-id x2d] [--tools 0,1]
      [--shells 1] [--overhang-angle 45]
      [--source model.scad ...] [--params params.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from collections import defaultdict

SCHEMA = "3dprint-scout.validate/1"
WELD_Q = 1e-4            # mm; vertices closer than this are the same vertex
DEGENERATE_AREA = 1e-9   # mm^2
BED_EPS = 0.01           # mm; faces this close to z_min count as bed contact
UNIT_RATIOS = {10.0: "cm->mm", 0.1: "mm->cm", 25.4: "inch->mm", 1 / 25.4: "mm->inch"}

# Checks this validator cannot decide from a mesh; build.py / the agent owns them.
NOT_COVERED = ["F1", "F2", "F3", "R1", "R2", "R4"]


# --------------------------------------------------------------------------- #
# Freshness (G1): hash of what produced the artifact, never file mtimes
# --------------------------------------------------------------------------- #
def engine_params(params: dict | None) -> dict:
    """Keys starting with "_" are metadata (_parts, _assumptions) and never reach the engine."""
    return {k: v for k, v in (params or {}).items() if not str(k).startswith("_")}


def _source_blobs(sources: list[str]) -> list[tuple[str, bytes]]:
    """(basename, bytes) per distinct file, ordered by basename then content so the hash does
    not depend on how the paths were spelled (./model.scad vs model.scad) or listed."""
    seen, blobs = set(), []
    for path in sources:
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        with open(path, "rb") as f:
            blobs.append((os.path.basename(path), f.read()))
    return sorted(blobs, key=lambda b: (b[0], hashlib.sha256(b[1]).digest()))


def hash_inputs(sources: list[str], params: dict | None) -> str:
    """sha256 over source file bytes (sorted by basename) + canonical engine-params JSON.
    Only engine parameters count: editing `_assumptions` or `_parts` does not make an STL stale."""
    h = hashlib.sha256()
    for name, data in _source_blobs(sources):
        h.update(name.encode("utf-8"))
        h.update(data)
    h.update(json.dumps(engine_params(params), sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


def source_names(sources: list[str]) -> list[str]:
    return [name for name, _ in _source_blobs(sources)]


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_path(stl: str) -> str:
    return stl + ".manifest.json"


def write_manifest(stl: str, sources: list[str], params: dict | None, engine: str, by: str = "run") -> dict:
    """Called by build.py right after an engine writes `stl` (`by` "run"), or when `record` takes
    an STL exported elsewhere (`by` "record"): only a manifest `run` wrote is the generator's own
    word on that STL, which a later `record` keeps instead of re-stamping."""
    data = {
        "schema": "3dprint-scout.manifest/1",
        "engine": engine,
        "by": by,
        "input_hash": hash_inputs(sources, params),
        "artifact_sha256": file_sha256(stl),
        "sources": source_names(sources),
    }
    with open(manifest_path(stl), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


# --------------------------------------------------------------------------- #
# STL reading + artifact sanity (G4)
# --------------------------------------------------------------------------- #
class ArtifactError(Exception):
    pass


def read_stl(path: str) -> list[tuple]:
    """Return a list of triangles ((x,y,z),(x,y,z),(x,y,z)). Raises ArtifactError."""
    if not os.path.isfile(path):
        raise ArtifactError("file not found")
    size = os.path.getsize(path)
    if size == 0:
        raise ArtifactError("file is 0 bytes")
    with open(path, "rb") as f:
        data = f.read()
    if path.lower().endswith(".3mf") or data[:2] == b"PK":
        raise ArtifactError("3MF given; validate the STL export instead")

    if data.startswith(b"\xef\xbb\xbf"):            # UTF-8 BOM in front of an ASCII STL
        data = data[3:]
    head = data[:512].lstrip().lower()
    looks_ascii = head.startswith(b"solid") and b"facet" in data[:4096].lower()

    # Binary first: some binary exporters start their 80-byte header with "solid".
    n = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else None
    if n is not None and (len(data) == 84 + 50 * n or (len(data) > 84 + 50 * n and n > 0 and not looks_ascii)):
        if n == 0:
            raise ArtifactError("binary STL with 0 triangles")
        tris = []
        off = 84
        for _ in range(n):
            v = struct.unpack_from("<12f", data, off)
            tris.append((v[3:6], v[6:9], v[9:12]))
            off += 50
        _check_finite(tris)
        return tris                             # trailing bytes after the last triangle are ignored

    if looks_ascii:
        tris = []
        verts = []
        for raw in data.decode("ascii", errors="replace").splitlines():
            parts = raw.strip().split()
            if parts and parts[0] == "vertex" and len(parts) >= 4:
                try:
                    verts.append(tuple(float(p) for p in parts[1:4]))
                except ValueError as exc:
                    raise ArtifactError(f"unparsable vertex line: {raw.strip()[:60]}") from exc
                if len(verts) == 3:
                    tris.append(tuple(verts))
                    verts = []
        if not tris:
            raise ArtifactError("ASCII STL with 0 triangles")
        _check_finite(tris)
        return tris

    if n is not None and 0 < n <= 100_000_000 and len(data) < 84 + 50 * n:   # a real count, short file
        raise ArtifactError(f"binary STL truncated: header announces {n} triangles ({84 + 50 * n} bytes), "
                            f"file has {len(data)} bytes")
    raise ArtifactError("not a valid STL: no binary triangle count that matches the file size, and no "
                        "ASCII 'solid ... facet' header")


def _check_finite(tris):
    for t in tris:
        for v in t:
            for c in v:
                if not math.isfinite(c):
                    raise ArtifactError("non-finite coordinate (NaN/inf) in mesh")


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def convex_hull(points):
    """Andrew's monotone chain on 2D points; returns hull in CCW order."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def analyse(tris, overhang_angle=45.0) -> dict:
    """All mesh metrics in one pass over the triangles."""
    q = WELD_Q
    key = lambda v: (round(v[0] / q), round(v[1] / q), round(v[2] / q))

    xs = [c[0] for t in tris for c in t]
    ys = [c[1] for t in tris for c in t]
    zs = [c[2] for t in tris for c in t]
    lo = (min(xs), min(ys), min(zs))
    hi = (max(xs), max(ys), max(zs))
    zmin = lo[2]

    directed = defaultdict(int)            # (u, v) -> count
    face_keys = []                         # welded vertex keys per kept face
    seen_faces = set()
    degenerate = duplicate = 0
    volume = area_total = 0.0
    overhang_area = bed_area = 0.0
    steepest = 0.0                         # the most overhanging face off the bed, degrees from vertical
    # Overhang: angle between face normal and straight down (-Z). A face is an
    # overhang when that angle is below (90 - max overhang angle from vertical).
    theta_limit = 90.0 - overhang_angle

    for t in tris:
        a, b, c = t
        ka, kb, kc = key(a), key(b), key(c)
        n = _cross(_sub(b, a), _sub(c, a))
        area2 = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        area = area2 / 2.0
        if area < DEGENERATE_AREA or ka == kb or kb == kc or ka == kc:
            degenerate += 1
            continue                       # keep degenerate faces out of topology
        sig = tuple(sorted((ka, kb, kc)))
        if sig in seen_faces:
            duplicate += 1
        seen_faces.add(sig)
        face_keys.append((ka, kb, kc))
        for u, v in ((ka, kb), (kb, kc), (kc, ka)):
            directed[(u, v)] += 1
        # Signed volume (divergence theorem); positive for outward-facing normals.
        volume += (a[0] * (b[1] * c[2] - b[2] * c[1])
                   - a[1] * (b[0] * c[2] - b[2] * c[0])
                   + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        area_total += area
        nz = n[2] / area2
        theta = math.degrees(math.acos(max(-1.0, min(1.0, -nz))))
        on_bed = max(a[2], b[2], c[2]) <= zmin + BED_EPS
        if on_bed and nz < -0.99:
            bed_area += area
        else:
            if theta < theta_limit:
                overhang_area += area
            if nz < 0:
                steepest = max(steepest, 90.0 - theta)

    # Edge topology. For a closed, consistently oriented mesh every undirected
    # edge is used by exactly two faces, once in each direction.
    open_edges = flipped = nonmanifold = 0
    visited = set()
    for (u, v), cnt in directed.items():
        e = (u, v) if u < v else (v, u)
        if e in visited:
            continue
        visited.add(e)
        fwd, rev = directed.get(e, 0), directed.get((e[1], e[0]), 0)
        total = fwd + rev
        if total == 1:
            open_edges += 1
        elif total > 2:
            nonmanifold += 1
        elif fwd != 1 or rev != 1:
            flipped += 1

    # Shells: union-find over faces that share an undirected edge.
    parent = list(range(len(face_keys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for i, (ka, kb, kc) in enumerate(face_keys):
        for u, v in ((ka, kb), (kb, kc), (kc, ka)):
            e = (u, v) if u < v else (v, u)
            if e in owner:
                ri, rj = find(i), find(owner[e])
                if ri != rj:
                    parent[ri] = rj
            else:
                owner[e] = i
    shells = len({find(i) for i in range(len(face_keys))})

    hull = convex_hull([(c[0], c[1]) for t in tris for c in t])
    bbox = [hi[i] - lo[i] for i in range(3)]
    box_vol = bbox[0] * bbox[1] * bbox[2]
    return {
        "triangles": len(tris),
        "bbox_mm": [round(v, 4) for v in bbox],
        "bbox_min_mm": [round(v, 4) for v in lo],
        "volume_mm3": round(volume, 3),
        "area_mm2": round(area_total, 3),
        "fill_ratio": round(volume / box_vol, 4) if box_vol > 0 else None,
        "shells": shells,
        "open_edges": open_edges,
        "flipped_edges": flipped,
        "nonmanifold_edges": nonmanifold,
        "degenerate_faces": degenerate,
        "duplicate_faces": duplicate,
        "bed_contact_mm2": round(bed_area, 3),
        "overhang_area_mm2": round(overhang_area, 3),
        "overhang_pct": round(100.0 * overhang_area / area_total, 2) if area_total else 0.0,
        "overhang_steepest_deg": round(steepest, 1),
        "_hull": hull,
    }


# --------------------------------------------------------------------------- #
# Printer bed (D2)
# --------------------------------------------------------------------------- #
def _open_polygon(poly):
    """Drop a repeated closing point ([..., [0, 0]] after starting at [0, 0])."""
    pts = [tuple(float(c) for c in p[:2]) for p in (poly or []) if len(p) >= 2]
    while len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def _as_rect(poly):
    """Return (x0, y0, x1, y1) if the polygon is an axis-aligned rectangle, else None."""
    pts = _open_polygon(poly)
    if len(pts) != 4:
        return None
    xs = sorted({round(p[0], 6) for p in pts})
    ys = sorted({round(p[1], 6) for p in pts})
    if len(xs) == 2 and len(ys) == 2 and all(p[0] in xs and p[1] in ys for p in
                                             ((round(q[0], 6), round(q[1], 6)) for q in pts)):
        return (xs[0], ys[0], xs[1], ys[1])
    return None


def load_printer(path, printer_id=None):
    """printers.json is an envelope: {"schema": ..., "default": "<id>", "printers": {"<id>": {...}}}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    printers = data.get("printers") if isinstance(data, dict) else None
    if not isinstance(printers, dict) or not printers:
        raise ValueError(f'{path} has no "printers" object; expected {{"schema": "3dprint.printers/1", '
                         '"default": "<id>", "printers": {"<id>": {...}}}')
    pid = printer_id or data.get("default")
    if pid is None and len(printers) == 1:
        pid = next(iter(printers))                  # no "default" but only one printer: use it
    if pid not in printers:
        known = ", ".join(sorted(printers))
        raise ValueError(f"printer '{pid}' not found in {path} (known: {known}); set \"default\" or pass --printer-id")
    return pid, printers[pid]


def effective_bed(printer, tool_ids):
    """Intersect the reachable areas of the tools used by this print."""
    bed = printer.get("bed", {})
    tools = printer.get("tools") or []
    notes = []
    if tools and tool_ids:
        rects, heights = [], []
        for i in tool_ids:
            if i >= len(tools):
                raise ValueError(f"tool index {i} not defined for this printer")
            t = tools[i]
            r = _as_rect(t.get("area") or bed.get("area", []))
            if r is None:
                notes.append("non-rectangular tool area; using bed area")
                break
            rects.append(r)
            heights.append(t.get("height", bed.get("height")))
        else:
            x0 = max(r[0] for r in rects); y0 = max(r[1] for r in rects)
            x1 = min(r[2] for r in rects); y1 = min(r[3] for r in rects)
            return {"rect": (x0, y0, x1, y1), "poly": None,
                    "height": min(h for h in heights if h is not None),
                    "exclude": bed.get("exclude", []), "notes": notes}
    r = _as_rect(bed.get("area", []))
    return {"rect": r, "poly": None if r else bed.get("area", []),
            "height": bed.get("height"), "exclude": bed.get("exclude", []), "notes": notes}


def fit_rect(hull, w_avail, d_avail):
    """Search rotations 0..179 deg; return (angle, w, d) of the first fit, else best attempt."""
    best = None
    for deg in range(180):
        r = math.radians(deg)
        cs, sn = math.cos(r), math.sin(r)
        xs = [p[0] * cs - p[1] * sn for p in hull]
        ys = [p[0] * sn + p[1] * cs for p in hull]
        w, d = max(xs) - min(xs), max(ys) - min(ys)
        if w <= w_avail + 1e-6 and d <= d_avail + 1e-6:
            return True, deg, w, d
        over = max(w - w_avail, d - d_avail)
        if best is None or over < best[0]:
            best = (over, deg, w, d)
    return False, best[1], best[2], best[3]


def check_bed(metrics, bed, bed_source):
    """D2 verdict (state, value, note). A PASS carries value["rotation_deg"], the Z rotation
    (counter-clockwise, degrees) at which the footprint fits; threemf.py and bambu3mf.py place
    the part with that same rotation."""
    height = metrics["bbox_mm"][2]
    if bed_source == "default":
        return ("UNVERIFIED", None, "bed size is a default, not the user's printer")
    if bed["height"] is not None and height > bed["height"] + 1e-6:
        return ("FAIL", {"height": height, "max_height": bed["height"]},
                f"part is {height:.1f} mm tall, printer allows {bed['height']} mm")
    state, value, note = _check_area(metrics["_hull"], bed)
    if bed["height"] is None and state == "PASS":
        return ("UNVERIFIED", value, note + "; bed height missing in printers.json, so the height is unchecked")
    return state, value, note


def _check_area(hull, bed):
    if bed["rect"]:
        x0, y0, x1, y1 = bed["rect"]
        ok, deg, w, d = fit_rect(hull, x1 - x0, y1 - y0)
        if not ok:
            return ("FAIL", {"footprint": [round(w, 2), round(d, 2)], "bed": [x1 - x0, y1 - y0]},
                    "footprint does not fit the usable area at any rotation")
        excl = [_as_rect(e) for e in bed["exclude"] if e]
        if not excl:
            note = "fits" + (f" when rotated {deg} deg" if deg else "")
            return ("PASS", {"rotation_deg": deg, "footprint": [round(w, 2), round(d, 2)]}, note)
        # Try the usable area trimmed on each side of every exclusion zone.
        for ex in excl:
            if ex is None:
                continue
            ex0, ey0, ex1, ey1 = ex
            for cand in ((ex1, y0, x1, y1), (x0, y0, ex0, y1), (x0, ey1, x1, y1), (x0, y0, x1, ey0)):
                cw, cd = cand[2] - cand[0], cand[3] - cand[1]
                if cw <= 0 or cd <= 0:
                    continue
                ok2, deg2, w2, d2 = fit_rect(hull, cw, cd)
                if ok2:
                    return ("PASS", {"rotation_deg": deg2, "footprint": [round(w2, 2), round(d2, 2)]},
                            "fits beside the exclusion zone")
        return ("WARN", {"footprint": [round(w, 2), round(d, 2)]},
                "fits the bed only if it overlaps an exclusion zone; check placement in the slicer")
    # Non-rectangular bed (e.g. delta): approximate as inscribed circle.
    poly = _open_polygon(bed["poly"])
    if len(poly) < 3:
        return ("UNVERIFIED", None, "printer bed area missing")
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    r_bed = min(math.hypot(p[0] - cx, p[1] - cy) for p in poly)
    hx = sum(p[0] for p in hull) / len(hull)
    hy = sum(p[1] for p in hull) / len(hull)
    r_part = max(math.hypot(p[0] - hx, p[1] - hy) for p in hull)
    if r_part <= r_bed:
        return ("PASS", {"part_radius": round(r_part, 2), "bed_radius": round(r_bed, 2)}, "fits round bed")
    return ("WARN", {"part_radius": round(r_part, 2), "bed_radius": round(r_bed, 2)},
            "round-bed fit is approximate; check in the slicer")


# --------------------------------------------------------------------------- #
# Optional P3: wall thickness by ray casting (numpy + rtree)
# --------------------------------------------------------------------------- #
P3_MAX_FACES = 400_000     # above this the check is skipped (UNVERIFIED), never attempted
P3_PAIR_BUDGET = 200_000   # (ray, candidate triangle) pairs tested per numpy batch
P3_MAX_DEPTH = 20.0        # mm; a ray that finds no wall within this counts as "at least this thick"
P3_SKIN = 0.05             # mm; hits closer than this are the ray's own face or a corner neighbour


def _ray_triangle_t(tri, orig, dirs):
    """Moller-Trumbore for paired rows: tri (k,3,3), orig (k,3), dirs (k,3) -> t (k,), inf = miss."""
    import numpy as np
    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    p = np.cross(dirs, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = orig - tri[:, 0]
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = np.einsum("ij,ij->i", dirs, q) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    eps = 1e-9
    hit = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps) & (t > P3_SKIN)
    return np.where(hit, t, np.inf)


def wall_thickness(tris, min_wall, samples=2000):
    """Shoot a ray inward from `samples` random faces; the nearest opposite wall is the thickness.

    Memory is bounded by construction: each ray is a segment of at most P3_MAX_DEPTH mm, the
    broad phase (rtree over triangle boxes) only returns triangles near that segment, and the
    narrow phase runs in numpy batches of at most P3_PAIR_BUDGET (ray, triangle) pairs. An
    unbounded version (every ray against every box it crosses) grew super-linearly and was
    killed on meshes of a few hundred thousand faces.
    """
    n = len(tris)
    if n > P3_MAX_FACES:
        return ("UNVERIFIED", {"triangles": n, "max_triangles": P3_MAX_FACES},
                f"skipped: {n} triangles is above the {P3_MAX_FACES} limit of this check")
    try:
        import numpy as np
        from rtree import index as rtree_index
    except ImportError:
        return ("UNVERIFIED", None, "numpy/rtree not installed")
    # An optional check must never take the validator down.
    try:
        T = np.asarray(tris, dtype=np.float64)                       # (n, 3, 3)
        normals = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        length = np.linalg.norm(normals, axis=1)
        usable = np.nonzero(length > 1e-12)[0]
        if len(usable) == 0:
            return ("UNVERIFIED", None, "no usable faces")
        normals[usable] /= length[usable, None]
        rng = np.random.default_rng(0)
        picked = rng.choice(usable, size=min(samples, len(usable)), replace=False)
        centres = T[picked].mean(axis=1)
        dirs = -normals[picked]                                       # into the solid
        origins = centres + dirs * 1e-3
        ends = origins + dirs * P3_MAX_DEPTH
        lo, hi = T.min(axis=1), T.max(axis=1)
        prop = rtree_index.Property()
        prop.dimension = 3
        tree = rtree_index.Index(((i, (*lo[i], *hi[i]), None) for i in range(n)), properties=prop)
        best = np.full(len(picked), np.inf)
        pairs_r, pairs_t, pending = [], [], 0

        def flush():
            if not pending:
                return
            r = np.concatenate(pairs_r)
            c = np.concatenate(pairs_t)
            t = _ray_triangle_t(T[c], origins[r], dirs[r])
            np.minimum.at(best, r, t)
            pairs_r.clear()
            pairs_t.clear()

        for ri in range(len(picked)):
            box = np.minimum(origins[ri], ends[ri]) - 1e-5
            box2 = np.maximum(origins[ri], ends[ri]) + 1e-5
            cand = np.fromiter(tree.intersection((*box, *box2)), dtype=np.int64)
            if len(cand) == 0:
                continue
            pairs_r.append(np.full(len(cand), ri, dtype=np.int64))
            pairs_t.append(cand)
            pending += len(cand)
            if pending >= P3_PAIR_BUDGET:
                flush()
                pending = 0
        flush()
    except Exception as exc:  # noqa: BLE001 - any failure here means "could not measure"
        return ("UNVERIFIED", None, f"ray casting unavailable: {type(exc).__name__}: {exc}"[:160])
    dist = np.minimum(best, P3_MAX_DEPTH)      # no wall within the depth: at least that thick
    p5 = float(np.percentile(dist, 5))
    state = "PASS" if p5 >= min_wall else "WARN"
    return (state, {"wall_p5_mm": round(p5, 3), "min_wall_mm": min_wall, "rays": int(len(picked)),
                    "max_depth_mm": P3_MAX_DEPTH},
            f"5th-percentile wall {p5:.2f} mm against the {min_wall:g} mm minimum (ray casting, approximate; depth "
            f"capped at {P3_MAX_DEPTH:g} mm; on raised or inlaid text it measures the letters' depth)")


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def _decimals(x: float) -> int:
    """Decimals a number was written with (71.2004 -> 4, 70.0 -> 0); scientific notation counts as many."""
    text = repr(float(x))
    if "e" in text or "E" in text:
        return 9
    _, _, frac = text.partition(".")
    return len(frac.rstrip("0"))


def chk(state, kind, value=None, note="", return_to=None):
    d = {"state": state, "kind": kind}
    if value is not None:
        d["value"] = value
    if note:
        d["note"] = note
    if return_to and state == "FAIL":
        d["return_to"] = return_to
    return d


def run_checks(path, tris, m, args, bed, bed_source):
    c = {}
    exp = args.expect
    bbox = m["bbox_mm"]

    # D1 dimensions, D4 unit/axis sanity
    if exp:
        diffs = [abs(bbox[i] - exp[i]) for i in range(3)]
        ok = all(d <= args.tol for d in diffs)
        c["D1"] = chk("PASS" if ok else "FAIL", "hard", {"bbox": bbox, "expect": exp, "tol": args.tol},
                      "" if ok else "bounding box differs from the expected size", "phase2")
        if ok and max(diffs) <= 1e-3 and any(_decimals(e) >= 4 for e in exp):
            # A designed size has up to three decimals (25.4, 3.175 mm from inches); a value copied from a
            # measured bounding box has more.
            c["D1"]["note"] = ("expect has four or more decimals and matches the mesh to 0.001 mm: it looks copied "
                               "from a measured bounding box. expect comes from the dimension table (design intent); "
                               "a copied value proves nothing")
            c["D1"]["copied_expect"] = True
        ratios = [bbox[i] / exp[i] for i in range(3) if exp[i] > 0]
        unit = None
        for r, label in UNIT_RATIOS.items():
            if ratios and all(abs(x / r - 1) < 0.02 for x in ratios):
                unit = label
        axis = (not ok and sorted(round(v, 1) for v in bbox) == sorted(round(v, 1) for v in exp))
        if unit:
            c["D4"] = chk("FAIL", "hard", {"ratio": round(ratios[0], 4)}, f"looks like a unit error ({unit})", "phase3")
        elif axis:
            c["D4"] = chk("FAIL", "hard", {"bbox": bbox, "expect": exp},
                          "right size on the wrong axes; model must be Z-up (Z=0 is the bed)", "phase3")
        else:
            c["D4"] = chk("PASS", "hard")
    else:
        c["D1"] = chk("UNVERIFIED", "hard", note="no --expect given")
        big = max(bbox)
        if big < 1.0 or big > 2000.0:
            c["D4"] = chk("FAIL", "hard", {"max_dim": big}, "implausible scale for a printed part", "phase3")
        else:
            c["D4"] = chk("UNVERIFIED", "hard", note="no --expect given")

    # D2 bed fit
    if bed is None:
        c["D2"] = chk("UNVERIFIED", "hard", note=getattr(args, "no_bed_reason", None) or "no printer profile given")
    else:
        st, val, note = check_bed(m, bed, bed_source)
        c["D2"] = chk(st, "hard", val, note, "phase2")

    # D3 volume sign
    vol = m["volume_mm3"]
    c["D3"] = chk("PASS" if vol > 0 else "FAIL", "hard", {"volume_mm3": vol},
                  "" if vol > 0 else "non-positive volume: normals point inward", "current")

    # M1-M5 mesh topology
    m1 = m["open_edges"] == 0 and m["nonmanifold_edges"] == 0
    m1_note = "" if m1 else "mesh is not watertight"
    if not m1 and m["degenerate_faces"]:
        m1_note += (f" once its {m['degenerate_faces']} zero-area faces are left out (M3): fix those first, it is "
                    "usually the same defect (slivers from a boolean through a fan of thin triangles or a tool that "
                    "ends on a face)")
    c["M1"] = chk("PASS" if m1 else "FAIL", "hard",
                  {"open_edges": m["open_edges"], "nonmanifold_edges": m["nonmanifold_edges"]}, m1_note, "current")
    c["M2"] = chk("PASS" if m["flipped_edges"] == 0 else "FAIL", "hard", {"flipped_edges": m["flipped_edges"]},
                  "" if m["flipped_edges"] == 0 else "inconsistent face orientation", "current")
    c["M3"] = chk("PASS" if m["degenerate_faces"] == 0 else "FAIL", "hard", {"degenerate_faces": m["degenerate_faces"]},
                  "" if m["degenerate_faces"] == 0 else "zero-area faces", "current")
    c["M4"] = chk("PASS" if m["duplicate_faces"] == 0 else "FAIL", "hard", {"duplicate_faces": m["duplicate_faces"]},
                  "" if m["duplicate_faces"] == 0 else "duplicate faces", "current")
    want = args.shells
    c["M5"] = chk("PASS" if m["shells"] == want else "FAIL", "hard", {"shells": m["shells"], "expect": want},
                  "" if m["shells"] == want else "unexpected number of separate bodies", "current")

    # P1 flat bottom, P2 overhang (soft: WARN at most)
    w, d = bbox[0], bbox[1]
    need = max(10.0, 0.01 * w * d)
    c["P1"] = chk("PASS" if m["bed_contact_mm2"] >= need else "WARN", "soft",
                  {"bed_contact_mm2": m["bed_contact_mm2"]},
                  "" if m["bed_contact_mm2"] >= need else "little or no flat area on the bed")
    p2_ok = m["overhang_pct"] <= 2.0
    c["P2"] = chk("PASS" if p2_ok else "WARN", "soft",
                  {"overhang_pct": m["overhang_pct"], "overhang_area_mm2": m["overhang_area_mm2"],
                   "steepest_deg": m["overhang_steepest_deg"], "limit_deg": args.overhang_angle},
                  "" if p2_ok else f"overhangs need supports or a redesign ({m['overhang_pct']} % of the surface is "
                                   f"flatter than {args.overhang_angle:g} deg from vertical, the steepest face "
                                   f"{m['overhang_steepest_deg']} deg)")

    # P3 wall thickness (optional deps), P4-P6 not decidable here in v1
    st, val, note = wall_thickness(tris, args.min_wall) if args.wall_check else ("UNVERIFIED", None, "skipped")
    c["P3"] = chk(st, "soft", val, note)
    c["P4"] = chk("UNVERIFIED", "soft", note="bridge detection not implemented in v1")
    c["P5"] = chk("UNVERIFIED", "soft", note="minimum feature size not implemented in v1")
    c["P6"] = chk("UNVERIFIED", "soft", note="needs a look at the preview image")

    # R3 freshness
    mf = manifest_path(path)
    if not os.path.isfile(mf):
        c["R3"] = chk("UNVERIFIED", "hard", note="no build manifest next to the STL")
    elif not args.source:
        c["R3"] = chk("UNVERIFIED", "hard", note="no --source given")
    else:
        with open(mf, encoding="utf-8") as f:
            man = json.load(f)
        params = None
        if args.params:
            with open(args.params, encoding="utf-8") as f:
                params = json.load(f)
        given = source_names(args.source)
        built = man.get("sources")
        # The manifest names what the STL was built from; extra --source files (another part's
        # generator in a mixed build) do not make it stale. A missing one does.
        own = [s for s in args.source if os.path.basename(s) in set(built)] if built and set(built) <= set(given) else args.source
        fresh = man.get("input_hash") == hash_inputs(own, params)
        same = man.get("artifact_sha256") == file_sha256(path)
        if fresh and same:
            c["R3"] = chk("PASS", "hard")
        elif not fresh and built is not None and not set(built) <= set(given):
            c["R3"] = chk("FAIL", "hard", {"manifest_sources": built, "given_sources": given},
                          f"STALE or wrong --source list: the build hashed {built}, --source gave {given}; "
                          "pass the same files (build.py prints them as \"sources\"), or rebuild if the includes changed",
                          return_to="current")
        elif not fresh:
            c["R3"] = chk("FAIL", "hard", note="STALE: source or parameters changed after this STL was built", return_to="current")
        else:
            c["R3"] = chk("FAIL", "hard", note="STL was replaced after the build that recorded it", return_to="current")
    return c


def gate_of(files):
    hard = [ck for f in files for ck in f.get("checks", {}).values() if ck["kind"] == "hard"]
    if any(not f["artifact_sane"] for f in files) or any(ck["state"] == "FAIL" for ck in hard):
        return "FAIL"
    if any(ck["state"] == "UNVERIFIED" for ck in hard):
        return "INCOMPLETE"
    return "PASS"


class _JsonArgParser(argparse.ArgumentParser):
    """argparse prints usage text and exits 2 on bad input; we need JSON and exit 1."""

    def error(self, message):
        raise ValueError(f"usage error: {message}")


def _usage_failure(message):
    out = {"schema": SCHEMA, "ran": False, "gate": "FAIL", "files": [], "not_covered": NOT_COVERED,
           "warnings": [], "errors": [message]}
    print(json.dumps(out, indent=2))
    return 1


def main(argv=None):
    ap = _JsonArgParser(description="3dprint-scout mesh validator (standard library only)")
    ap.add_argument("stl", nargs="+")
    ap.add_argument("--expect", help="expected bounding box W,D,H in mm (X,Y,Z)")
    ap.add_argument("--tol", type=float, default=0.1, help="D1 tolerance in mm (default 0.1)")
    ap.add_argument("--printer", help="path to .3dprint/printers.json")
    ap.add_argument("--printer-id")
    ap.add_argument("--tools", default="0", help="tool indices used, e.g. 0 or 0,1")
    ap.add_argument("--shells", type=int, default=1, help="expected separate bodies per file")
    ap.add_argument("--overhang-angle", type=float, default=45.0)
    ap.add_argument("--min-wall", type=float, default=1.2)
    ap.add_argument("--no-wall-check", dest="wall_check", action="store_false")
    ap.add_argument("--source", nargs="*", default=[], help="files the STL was generated from")
    ap.add_argument("--params", help="JSON file with the parameters used for the build")
    try:
        args = ap.parse_args(argv)
    except ValueError as exc:
        return _usage_failure(str(exc))

    out = {"schema": SCHEMA, "ran": True, "gate": None, "files": [], "not_covered": NOT_COVERED,
           "warnings": [], "errors": []}
    try:
        args.expect = [float(x) for x in args.expect.split(",")] if args.expect else None
        if args.expect and len(args.expect) != 3:
            raise ValueError("--expect needs three numbers W,D,H")
        tool_ids = [int(x) for x in args.tools.split(",") if x.strip() != ""]
        bed = bed_source = None
        if args.printer and not os.path.isfile(args.printer):
            # The printer is simply not known yet (Phase 2 default): not an error, but D2 is
            # not decided either. A malformed file or an unknown id is still an error below.
            out["warnings"].append(f"printer file not found: {args.printer}; D2 (bed fit) stays UNVERIFIED")
            args.no_bed_reason = f"printer file not found: {args.printer}"
        elif args.printer:
            pid, printer = load_printer(args.printer, args.printer_id)
            if printer.get("process", "fdm") != "fdm":
                raise ValueError(f"printer '{pid}' is {printer.get('process')}; only FDM is supported")
            bed = effective_bed(printer, tool_ids)
            bed_source = printer.get("bed", {}).get("source", "user")
            out["printer"] = {"id": pid, "tools": tool_ids, "usable_rect": bed["rect"], "height": bed["height"]}
            out["warnings"] += bed["notes"]
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        out.update(ran=False, gate="FAIL")
        out["errors"].append(str(exc))
        print(json.dumps(out, indent=2))
        return 1

    insane = False
    for path in args.stl:
        entry = {"path": path, "artifact_sane": True}
        try:
            tris = read_stl(path)
        except ArtifactError as exc:
            insane = True
            entry.update(artifact_sane=False, artifact_error=str(exc))
            out["files"].append(entry)
            continue
        try:
            m = analyse(tris, args.overhang_angle)
            entry["checks"] = run_checks(path, tris, m, args, bed, bed_source)
            m.pop("_hull")
            entry["metrics"] = m
        except Exception as exc:  # noqa: BLE001 - always emit JSON, never a bare traceback
            out["ran"] = False
            out["errors"].append(f"{os.path.basename(path)}: internal error {type(exc).__name__}: {exc}")
        out["files"].append(entry)

    out["gate"] = gate_of(out["files"]) if out["ran"] else "FAIL"
    for f in out["files"]:
        for cid, ck in f.get("checks", {}).items():
            if ck["state"] == "WARN" or ck.get("copied_expect"):
                out["warnings"].append(f"{os.path.basename(f['path'])} {cid}: {ck.get('note', '')}")
    print(json.dumps(out, indent=2))
    if not out["ran"]:
        return 1
    return 2 if insane else 0


if __name__ == "__main__":
    sys.exit(main())
