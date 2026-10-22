#!/usr/bin/env python3
"""
measure.py - measure interface dimensions in an STL or 3MF the user supplied (a manufacturer's
file, a reference model): list its objects, slice it, map a wall with rays. Numbers only:
the geometry is never copied into a design (licences); record the source as "official
file, measured" or "reference model, measured" (a secondary source).

  python3 measure.py info kit.3mf                         objects / parts: names, boxes, triangles
  python3 measure.py info kit.3mf --extract ref_mesh      ... and one STL per object, build coordinates
  python3 measure.py slice part.stl --z 0.5,20,66.5       closed loops per level: bounds, area, circle fit,
  python3 measure.py slice part.stl --z 0:70:5 --center   corner radii of a rounded outline
  python3 measure.py raymap housing.stl --axis x --sign -1 --u -30:-12:1 --v 8:20:0.5
                                                           depth map of the -X wall: windows, recesses

3MF: core objects and Bambu Studio production-extension components (`p:path`) with their
transforms and the build items' transforms; names from the core `name` attribute or Bambu's
model_settings.config. Units are converted to mm. `--object ID` limits slice / raymap to one
object (default: everything, as placed). `--center` moves the XY centre of the box to the origin
first, which is how a mating part is usually dimensioned.

slice: `--axis z` (default), `x` or `y`; `--z` takes a comma list or `start:end:step`. Every
closed loop gets bounds, area, centroid, a least-squares circle fit (centre, radius, rms:
a circle when rms is well below 1 % of the radius) and, for outlines that look rectangular,
the four corner radii from circle fits on the corner arcs (0 = sharp, null = too few points).

raymap: rays start outside the box and travel along -sign * axis; the grid is (u, v) on the
other two axes in the order they come (y, z for axis x; x, z for y; x, y for z). Each cell
holds the depth of the first hit measured from the outer face, or null beyond --max-depth
(a through-hole or a deep recess). `text` holds the same map as rows for reading.

--expect PATH=VALUE (or >=, <=) checks one number of the output, named by its path
(levels[0].loops[0].size[0], depth_mm[3][5], objects[0].size_mm[2]); repeat it for several.
`=` needs --tol. The report then carries `expect` (path, op, target, tol, value, state) and
`gate` (PASS when every expectation passes; a path to no number, such as a through-hole's null
depth, is a FAIL), plus `file_sha256` and `query`, which tie it to the very file and command:
finalize.py takes such a report as a `measurement` (a hand calculation confirmed on the built
part, or a size read from the user's file). Save it: `measure.py ... > out/m_lip.json`.

Needs numpy; manifold3d, when installed, adds volume and watertightness to `info`. Prints
one JSON document; exit 0 on success (a FAIL expectation included: read `gate`), 1 on a usage
or file error.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate import ArtifactError, file_sha256, read_stl  # noqa: E402

SCHEMA = "3dprint-scout.measure/1"
CORE_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PROD_NS = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
UNIT_MM = {"millimeter": 1.0, "micron": 0.001, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}
WELD = 1e-4


class MeasureError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise MeasureError(f"usage error: {message}")


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _np():
    try:
        import numpy as np
        return np
    except ImportError:
        raise MeasureError("measure.py needs numpy (pip install numpy)")


def _matrix(text):
    """3MF transform (row-vector, 12 numbers) -> 4x4 column-vector matrix."""
    np = _np()
    M = np.eye(4)
    if text:
        v = [float(x) for x in text.split()]
        if len(v) != 12:
            raise MeasureError(f"transform needs 12 numbers, got {len(v)}")
        M[:3, :3] = np.array(v[:9]).reshape(3, 3).T
        M[:3, 3] = v[9:12]
    return M


def _apply(M, V):
    np = _np()
    return (V @ M[:3, :3].T) + M[:3, 3]


def load_stl(path):
    np = _np()
    T = np.asarray(read_stl(path), dtype=np.float64)
    V = T.reshape(-1, 3)
    F = np.arange(len(V)).reshape(-1, 3)
    return [{"id": "1", "name": os.path.splitext(os.path.basename(path))[0], "V": V, "F": F, "parts": []}]


def _bambu_names(z):
    """{object id: name, part id: name} from Bambu Studio's model_settings.config, if present."""
    names = {}
    try:
        xml = z.read("Metadata/model_settings.config").decode("utf-8", "replace")
    except KeyError:
        return names
    ents = {"&quot;": '"', "&apos;": "'"}
    for m in re.finditer(r'<part id="(\d+)"[^>]*>(.*?)</part>', xml, re.S):
        nm = re.search(r'key="name" value="([^"]*)"', m.group(2))
        if nm:
            names[m.group(1)] = unescape(nm.group(1), ents)
    for m in re.finditer(r'<object id="(\d+)"[^>]*>(.*?)</object>', xml, re.S):
        own = m.group(2).split("<part", 1)[0]                  # the object's own metadata comes first
        nm = re.search(r'key="name" value="([^"]*)"', own)
        if nm:
            names[m.group(1)] = unescape(nm.group(1), ents)
    return names


def load_3mf(path):
    """Objects of a 3MF as placed by the build items: [{"id", "name", "V", "F", "parts": [...]}]."""
    np = _np()
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise MeasureError(f"{path} is not a 3MF (zip) file")
    with z:
        try:
            main = ET.fromstring(z.read("3D/3dmodel.model"))
        except KeyError:
            raise MeasureError(f"{path} has no 3D/3dmodel.model")
        bambu = _bambu_names(z)
        cache, scales = {}, {}

        def objects_of(entry):
            if entry not in cache:
                root = main if entry == "3D/3dmodel.model" else ET.fromstring(z.read(entry))
                cache[entry] = {o.get("id"): o for o in root.iter(CORE_NS + "object")}
                scales[entry] = UNIT_MM.get(root.get("unit", "millimeter"), 1.0)   # each model file has its own unit
            return cache[entry]

        def mesh_of(el, entry):
            m = el.find(CORE_NS + "mesh")
            if m is None:
                return None
            vs = m.find(CORE_NS + "vertices")
            ts = m.find(CORE_NS + "triangles")
            scale = scales[entry]
            V = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))] for v in vs], dtype=np.float64) * scale
            F = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))] for t in ts], dtype=np.int64)
            return V, F

        def resolve(entry, oid, M, depth=0):
            """[(name, V placed, F)] for object oid of file `entry` under transform M."""
            if depth > 8:
                raise MeasureError("component nesting deeper than 8")
            el = objects_of(entry).get(oid)
            if el is None:
                raise MeasureError(f"object {oid} not found in {entry}")
            out = []
            comps = el.find(CORE_NS + "components")
            if comps is not None:
                for c in comps:
                    sub_entry = (c.get(PROD_NS + "path") or "").lstrip("/") or entry
                    Mc = M @ _matrix(c.get("transform"))
                    out += resolve(sub_entry, c.get("objectid"), Mc, depth + 1)
            mesh = mesh_of(el, entry)
            if mesh is not None:
                V, F = mesh
                out.append((bambu.get(oid) or el.get("name") or f"object_{oid}", _apply(M, V), F))
            return out

        objects = []
        for item in main.iter(CORE_NS + "item"):
            oid = item.get("objectid")
            parts = resolve("3D/3dmodel.model", oid, _matrix(item.get("transform")))
            if not parts:
                continue
            el = objects_of("3D/3dmodel.model")[oid]
            name = bambu.get(oid) or el.get("name") or f"object_{oid}"
            V = np.concatenate([p[1] for p in parts])
            off, Fs = 0, []
            for _n, pv, pf in parts:
                Fs.append(pf + off)
                off += len(pv)
            objects.append({"id": oid, "name": name, "V": V, "F": np.concatenate(Fs),
                            "parts": [{"name": n, "triangles": int(len(f)), "bbox_min_mm": [round(float(x), 3) for x in v.min(axis=0)],
                                       "bbox_max_mm": [round(float(x), 3) for x in v.max(axis=0)]} for n, v, f in parts]})
    if not objects:
        raise MeasureError("the 3MF has no build items with meshes")
    return objects


def load(path):
    if not os.path.isfile(path):
        raise MeasureError(f"file not found: {path}")
    with open(path, "rb") as f:
        head = f.read(2)
    if path.lower().endswith(".3mf") or head == b"PK":
        return load_3mf(path)
    try:
        return load_stl(path)
    except ArtifactError as exc:
        raise MeasureError(f"{path}: {exc}")


def select(objects, wanted, center):
    np = _np()
    if wanted:
        chosen = [o for o in objects if o["id"] == wanted or o["name"] == wanted]
        if not chosen:
            raise MeasureError(f"no object '{wanted}'; objects are " + ", ".join(f"{o['id']} ({o['name']})" for o in objects))
    else:
        chosen = objects
    V = np.concatenate([o["V"] for o in chosen])
    off, Fs = 0, []
    for o in chosen:
        Fs.append(o["F"] + off)
        off += len(o["V"])
    F = np.concatenate(Fs)
    shift = [0.0, 0.0, 0.0]
    if center:
        lo, hi = V.min(axis=0), V.max(axis=0)
        shift = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, 0.0]
        V = V + np.array(shift)
    return V, F, [o["name"] for o in chosen], shift


def box_info(V):
    lo, hi = V.min(axis=0), V.max(axis=0)
    return {"bbox_min_mm": [round(float(x), 3) for x in lo], "bbox_max_mm": [round(float(x), 3) for x in hi],
            "size_mm": [round(float(x), 3) for x in hi - lo]}


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #
def _manifold_stats(V, F):
    try:
        import manifold3d as m3d
        import numpy as np
    except ImportError:
        return {"volume_mm3": None, "watertight": None, "note": "manifold3d not installed"}
    keys = np.round(V / WELD).astype(np.int64)
    _, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    F2 = inv.reshape(-1)[F]
    F2 = F2[(F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])]
    man = m3d.Manifold(m3d.Mesh(vert_properties=np.ascontiguousarray(V[first], dtype=np.float32),
                                tri_verts=np.ascontiguousarray(F2, dtype=np.uint32)))
    ok = man.status() == m3d.Error.NoError and not man.is_empty()
    return {"volume_mm3": round(man.volume(), 1) if ok else None, "watertight": bool(ok)}


def cmd_info(args):
    objects = load(args.file)
    out = {"file": args.file, "objects": []}
    if args.extract:
        os.makedirs(args.extract, exist_ok=True)
        from build import write_binary_stl
    for o in objects:
        entry = {"id": o["id"], "name": o["name"], "triangles": int(len(o["F"])), **box_info(o["V"]), "parts": o["parts"]}
        entry.update(_manifold_stats(o["V"], o["F"]))
        if args.extract:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", o["name"]) or "object"
            path = os.path.join(args.extract, f"obj_{o['id']}_{safe}.stl")
            if os.path.exists(path):
                raise MeasureError(f"{path} already exists; refusing to overwrite")
            write_binary_stl(path, o["V"].tolist(), o["F"].tolist())
            entry["stl"] = path
        out["objects"].append(entry)
    return out


# --------------------------------------------------------------------------- #
# slice
# --------------------------------------------------------------------------- #
def parse_levels(text):
    if ":" in text:
        parts = [float(x) for x in text.split(":")]
        if len(parts) != 3 or parts[2] <= 0:
            raise MeasureError("--z start:end:step needs a positive step")
        a, b, s = parts
        n = int(math.floor((b - a) / s + 1e-9)) + 1
        return [round(a + i * s, 6) for i in range(max(n, 0))]
    try:
        return [float(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise MeasureError("--z takes numbers separated by commas, or start:end:step")


def plane_loops(V, F, axis, level):
    """Loops where the mesh crosses axis = level: [(points, closed)], points as 2D (u, w) on
    the two other axes, one point per welded vertex. `closed` is False for an open chain (a
    mesh with a hole in its surface, or a non-manifold junction)."""
    np = _np()
    a = "xyz".index(axis)
    u, w = [i for i in range(3) if i != a]
    T = V[F]                                              # (m, 3, 3)
    d = T[:, :, a] - level
    # Nudge vertices exactly on the plane so every crossing is a clean edge crossing.
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    sgn = d > 0
    cross = sgn.any(axis=1) & (~sgn).any(axis=1)
    key = lambda p: (round(p[0] / WELD), round(p[1] / WELD))      # noqa: E731
    point, adj, seen = {}, {}, set()
    for t in np.nonzero(cross)[0]:
        pts = []
        for i in range(3):
            j = (i + 1) % 3
            if sgn[t, i] != sgn[t, j]:
                s = d[t, i] / (d[t, i] - d[t, j])
                p = T[t, i] + s * (T[t, j] - T[t, i])
                pts.append((float(p[u]), float(p[w])))
        if len(pts) != 2:
            continue
        kp, kq = key(pts[0]), key(pts[1])
        if kp == kq or (kp, kq) in seen or (kq, kp) in seen:   # zero-length, or the same edge twice
            continue
        seen.add((kp, kq))
        point.setdefault(kp, pts[0])
        point.setdefault(kq, pts[1])
        adj.setdefault(kp, []).append(kq)
        adj.setdefault(kq, []).append(kp)
    used, loops = set(), []
    for start in adj:
        if start in used:
            continue
        loop, cur, prev, closed = [], start, None, False
        while True:
            used.add(cur)
            loop.append(point[cur])
            nxt = None
            for k in adj[cur]:
                if k == prev:
                    continue
                if k == start and len(loop) >= 3:
                    closed = True
                    break
                if k not in used:
                    nxt = k
                    break
            if closed or nxt is None:
                break
            prev, cur = cur, nxt
        if len(loop) >= 3:
            loops.append((loop, closed))
        elif len(loop) == 2 and not closed:
            loops.append((loop, False))
    return loops


def polygon_area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def circle_fit(pts):
    """Least-squares circle (Kasa): centre, radius, rms residual; None with fewer than 3 points."""
    np = _np()
    P = np.asarray(pts, dtype=np.float64)
    if len(P) < 3:
        return None
    A = np.c_[2 * P, np.ones(len(P))]
    b = (P ** 2).sum(axis=1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = sol[0], sol[1]
    r2 = sol[2] + cx * cx + cy * cy
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    rms = float(np.sqrt(np.mean((np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r) ** 2)))
    return {"centre": [round(float(cx), 3), round(float(cy), 3)], "radius_mm": round(r, 3), "rms_mm": round(rms, 4)}


def corner_radii(pts, bounds):
    """Radius of the arc in each corner of a rounded outline: circle fit on the loop points near
    the box corner that lie off the two straight sides. 0 = sharp, None = too few points."""
    np = _np()
    P = np.asarray(pts, dtype=np.float64)
    x0, y0, x1, y1 = bounds
    w, d = x1 - x0, y1 - y0
    window = min(w, d) / 2.5
    out = {}
    for label, cx, cy, sx, sy in (("x0y0", x0, y0, 1, 1), ("x1y0", x1, y0, -1, 1), ("x1y1", x1, y1, -1, -1), ("x0y1", x0, y1, 1, -1)):
        near = (np.abs(P[:, 0] - cx) <= window) & (np.abs(P[:, 1] - cy) <= window)
        off_sides = (np.abs(P[:, 0] - cx) > 1e-3) & (np.abs(P[:, 1] - cy) > 1e-3)
        sel = P[near & off_sides]
        if len(sel) < 3:
            out[label] = 0.0 if near.any() else None
            continue
        fit = circle_fit(sel.tolist())
        if fit is None or fit["radius_mm"] > window * 1.5:
            out[label] = None
            continue
        out[label] = fit["radius_mm"]
    return out


def cmd_slice(args):
    V, F, names, shift = select(load(args.file), args.object, args.center)
    axis = args.axis.lower()
    if axis not in "xyz" or len(axis) != 1:
        raise MeasureError("--axis must be x, y or z")
    others = [c for c in "xyz" if c != axis]
    out = {"file": args.file, "objects": names, "axis": axis, "plane_axes": others, "centred": args.center,
           "shift_mm": shift, **box_info(V), "levels": []}
    for level in parse_levels(args.z):
        loops = []
        for pts, closed in plane_loops(V, F, axis, level):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            bounds = [min(xs), min(ys), max(xs), max(ys)]
            area = polygon_area(pts) if closed else 0.0
            entry = {"points": len(pts), "closed": closed, "bounds": [round(b, 3) for b in bounds],
                     "size": [round(bounds[2] - bounds[0], 3), round(bounds[3] - bounds[1], 3)],
                     "area_mm2": round(abs(area), 2) if closed else None,
                     "centroid": [round(sum(xs) / len(xs), 3), round(sum(ys) / len(ys), 3)]}
            if not closed:
                out.setdefault("warnings", []).append(f"level {level}: an open chain of {len(pts)} points (the mesh is not "
                                                      "closed there, or surfaces cross); bounds only")
            fit = circle_fit(pts)
            if fit:
                entry["circle_fit"] = fit
                entry["is_circle"] = len(pts) >= 8 and fit["rms_mm"] < 0.01 * fit["radius_mm"]   # 4 corners also lie on a circle
            if closed and not entry.get("is_circle") and len(pts) >= 4:
                entry["corner_radii_mm"] = corner_radii(pts, bounds)
            loops.append(entry)
        loops.sort(key=lambda e: -(e["area_mm2"] or 0.0))
        out["levels"].append({"level": level, "loops": loops[: args.max_loops]})
    return out


# --------------------------------------------------------------------------- #
# raymap
# --------------------------------------------------------------------------- #
def parse_range(text, name):
    try:
        a, b, s = (float(x) for x in text.split(":"))
    except ValueError:
        raise MeasureError(f"{name} needs start:end:step")
    if s <= 0:
        raise MeasureError(f"{name} needs a positive step")
    n = int(math.floor((b - a) / s + 1e-9)) + 1
    if n < 1 or n > 2000:
        raise MeasureError(f"{name}: between 1 and 2000 samples")
    return [round(a + i * s, 6) for i in range(n)]


def ray_depths(V, F, axis, sign, us, vs, max_depth):
    """First-hit distance from the outer face for rays along -sign * axis, on a (u, v) grid."""
    np = _np()
    a = "xyz".index(axis)
    u_ax, v_ax = [i for i in range(3) if i != a]
    T = V[F]
    lo, hi = V.min(axis=0), V.max(axis=0)
    outer = hi[a] if sign > 0 else lo[a]
    # Per triangle: range on u and v (for the broad phase) and the plane.
    tu0, tu1 = T[:, :, u_ax].min(axis=1), T[:, :, u_ax].max(axis=1)
    tv0, tv1 = T[:, :, v_ax].min(axis=1), T[:, :, v_ax].max(axis=1)
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    direction = np.zeros(3)
    direction[a] = -sign
    p = np.cross(direction, e2)
    det = np.einsum("ij,ij->i", e1, p)
    grid = np.full((len(vs), len(us)), np.nan)
    start = outer + sign * 5.0
    for vi, vv in enumerate(vs):
        cand_v = (tv0 <= vv + 1e-9) & (tv1 >= vv - 1e-9)
        for ui, uu in enumerate(us):
            cand = np.nonzero(cand_v & (tu0 <= uu + 1e-9) & (tu1 >= uu - 1e-9) & (np.abs(det) > 1e-12))[0]
            if len(cand) == 0:
                continue
            origin = np.zeros(3)
            origin[a], origin[u_ax], origin[v_ax] = start, uu, vv
            s = origin - T[cand, 0]
            inv = 1.0 / det[cand]
            uu_b = np.einsum("ij,ij->i", s, p[cand]) * inv
            q = np.cross(s, e1[cand])
            vv_b = (q @ direction) * inv
            t = np.einsum("ij,ij->i", e2[cand], q) * inv
            eps = 1e-9
            hit = (uu_b >= -eps) & (vv_b >= -eps) & (uu_b + vv_b <= 1 + eps) & (t > 0)
            if hit.any():
                depth = max(float(t[hit].min()) - 5.0, 0.0)
                if depth <= max_depth:
                    grid[vi, ui] = depth
    return grid, float(outer)


def cmd_raymap(args):
    V, F, names, shift = select(load(args.file), args.object, args.center)
    axis = args.axis.lower()
    if axis not in ("x", "y", "z"):
        raise MeasureError("--axis must be x, y or z")
    sign = 1 if args.sign in ("+1", "1", "+") else -1 if args.sign in ("-1", "-") else None
    if sign is None:
        raise MeasureError("--sign is +1 (rays hit the +axis face) or -1")
    us, vs = parse_range(args.u, "--u"), parse_range(args.v, "--v")
    grid, outer = ray_depths(V, F, axis, sign, us, vs, args.max_depth)
    others = [c for c in "xyz" if c != axis]
    rows = []
    for vi in range(len(vs) - 1, -1, -1):
        cells = ("  .  " if math.isnan(grid[vi, ui]) else f"{grid[vi, ui]:5.2f}" for ui in range(len(us)))
        rows.append(f"{others[1]}={vs[vi]:7.2f} | " + " ".join(cells))
    header = " " * 12 + "| " + " ".join(f"{u:5.1f}" for u in us) + f"   ({others[0]})"
    return {"file": args.file, "objects": names, "axis": axis, "sign": sign, "outer_face_mm": round(outer, 3),
            "grid_axes": others, "u": us, "v": vs, "max_depth_mm": args.max_depth, "centred": args.center, "shift_mm": shift,
            "depth_mm": [[None if math.isnan(x) else round(float(x), 3) for x in row] for row in grid],
            "text": [header] + rows,
            "how_to_read": "each cell is the depth of the first surface behind the outer face; '.' means nothing within "
                           f"{args.max_depth} mm (a through-hole or a deep recess). Rows are v from high to low."}


# --------------------------------------------------------------------------- #
# expect: a number of the output, checked against a target
# --------------------------------------------------------------------------- #
EXPECT_RE = re.compile(r"^\s*(?P<path>[^<>=]+?)\s*(?P<op>>=|<=|=)\s*(?P<target>\S+)\s*$")
PATH_TOKEN = re.compile(r"(?:^|\.)([A-Za-z_][A-Za-z0-9_]*)|\[(-?\d+)\]")


def parse_path(path):
    """levels[0].loops[0].size[1] -> [("levels", None), (None, 0), ("loops", None), ...]."""
    tokens, pos = [], 0
    for m in PATH_TOKEN.finditer(path):
        if m.start() != pos:
            break
        tokens.append((m.group(1), None) if m.group(1) else (None, int(m.group(2))))
        pos = m.end()
    if not tokens or pos != len(path):
        raise MeasureError(f"--expect: '{path}' is not a path into the output (e.g. levels[0].loops[0].size[0], "
                           "depth_mm[3][5], objects[0].size_mm[2])")
    return tokens


def parse_expect(text):
    m = EXPECT_RE.match(text)
    if not m:
        raise MeasureError(f"--expect {text!r}: write PATH=VALUE, PATH>=VALUE or PATH<=VALUE")
    try:
        target = float(m.group("target"))
    except ValueError:
        target = float("nan")
    if not math.isfinite(target):
        raise MeasureError(f"--expect {text!r}: the target must be a finite number")
    parse_path(m.group("path"))
    return {"path": m.group("path"), "op": m.group("op"), "target": target}


def resolve(doc, path):
    cur = doc
    for key, idx in parse_path(path):
        if key is not None:
            if not isinstance(cur, dict) or key not in cur:
                raise MeasureError(f"--expect {path}: the output has no '{key}' there")
            cur = cur[key]
        else:
            if not isinstance(cur, list) or not -len(cur) <= idx < len(cur):
                raise MeasureError(f"--expect {path}: index [{idx}] is outside the list there")
            cur = cur[idx]
    return cur


def judge(doc, expects, tol):
    """Each expectation with the measured value and PASS / FAIL; the gate PASS only when all pass.
    A path that leads to nothing that is a number (a through-hole's null depth) is a FAIL."""
    out = []
    for e in expects:
        v = resolve(doc, e["path"])
        entry = dict(e)
        number = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        entry["value"] = v if number else None
        if e["op"] == "=":
            entry["tol"] = tol
        if not number:
            entry.update(state="FAIL", note=f"no number there ({json.dumps(v)})")
        elif e["op"] == "=":
            entry["state"] = "PASS" if abs(v - e["target"]) <= tol + 1e-9 else "FAIL"
        elif e["op"] == ">=":
            entry["state"] = "PASS" if v >= e["target"] - 1e-9 else "FAIL"
        else:
            entry["state"] = "PASS" if v <= e["target"] + 1e-9 else "FAIL"
        out.append(entry)
    return out, ("PASS" if all(e["state"] == "PASS" for e in out) else "FAIL")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
NEGATIVE_OK = ("--z", "--u", "--v")      # options whose value may start with a minus sign


def join_negative_values(argv, options=NEGATIVE_OK):
    """argparse reads `--u -30:-12:1` as two options; turn it into `--u=-30:-12:1` so the documented
    form works. Only a value that looks like numbers, colons and commas is joined."""
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


def utf8_stdout():
    """Windows consoles and pipes may not be UTF-8; names in a 3MF may be. Best effort."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def main(argv=None):
    utf8_stdout()
    out = {"schema": SCHEMA, "ran": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="measure interface dimensions in an STL or 3MF (numbers only, never geometry)")
        sub = ap.add_subparsers(dest="cmd")
        p_info = sub.add_parser("info", help="objects and parts with boxes; --extract DIR writes one STL per object")
        p_info.add_argument("file")
        p_info.add_argument("--extract", help="folder for one STL per object, in build coordinates")
        p_slice = sub.add_parser("slice", help="closed loops at given levels along an axis")
        p_slice.add_argument("file")
        p_slice.add_argument("--z", required=True, help="levels: 0.5,20,66 or start:end:step")
        p_slice.add_argument("--axis", default="z")
        p_slice.add_argument("--object", help="object id or name (default: all, as placed)")
        p_slice.add_argument("--center", action="store_true", help="put the XY centre of the box at the origin first")
        p_slice.add_argument("--max-loops", type=int, default=12, help="largest loops to report per level")
        p_ray = sub.add_parser("raymap", help="depth map of a wall from a grid of rays")
        p_ray.add_argument("file")
        p_ray.add_argument("--axis", required=True, help="x, y or z: the axis the rays travel along")
        p_ray.add_argument("--sign", required=True, help="+1: rays come from +axis and hit that face; -1: from -axis")
        p_ray.add_argument("--u", required=True, help="start:end:step on the first other axis")
        p_ray.add_argument("--v", required=True, help="start:end:step on the second other axis")
        p_ray.add_argument("--max-depth", type=float, default=6.0, help="deeper hits count as 'through' (mm)")
        p_ray.add_argument("--object")
        p_ray.add_argument("--center", action="store_true")
        for p in (p_info, p_slice, p_ray):
            p.add_argument("--expect", action="append", help="PATH=VALUE, PATH>=VALUE or PATH<=VALUE on a number of "
                           "this output (levels[0].loops[0].size[0]=6); repeatable; adds expect and gate")
            p.add_argument("--tol", type=float, help="allowed difference for PATH=VALUE (mm)")
            p.add_argument("--what", help="what the expectation measures, in words (lip height)")
        args = ap.parse_args(join_negative_values(sys.argv[1:] if argv is None else argv))
        if args.cmd is None:
            raise MeasureError("usage error: choose a subcommand: info, slice, raymap")
        expects = [parse_expect(t) for t in args.expect or []]
        if any(e["op"] == "=" for e in expects) and args.tol is None:
            raise MeasureError("--tol is needed with PATH=VALUE (the allowed difference, mm)")
        if args.tol is not None and not (math.isfinite(args.tol) and args.tol >= 0):
            raise MeasureError("--tol must be a number of 0 or more")
        out.update({"info": cmd_info, "slice": cmd_slice, "raymap": cmd_raymap}[args.cmd](args))
        out["file_sha256"] = file_sha256(args.file)       # the very file these numbers are about (finalize.py)
        out["query"] = {k: v for k, v in sorted(vars(args).items()) if k not in ("expect", "tol", "what", "extract")}
        if expects:
            if args.what:
                out["what"] = args.what
            out["expect"], out["gate"] = judge(out, expects, args.tol)
        out["ran"] = True
    except (MeasureError, OSError, ValueError, ET.ParseError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
