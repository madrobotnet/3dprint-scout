#!/usr/bin/env python3
"""
assembly.py - parts grouped into objects: the `_parts` grouping schema, and the checks a
group needs beyond the per-part ones (bed fit, bed contact and overhang of the whole
object; contact between fused parts; clearance around print-in-place parts).

Schema (params.json, metadata keys never reach the engine):

  {"_parts": {
     "lid":   {"expect": [70, 45, 3]},                                   # its own object
     "label": {"expect": [40, 12, 1], "object": "lid", "role": "fused"}, # touches the lid
     "latch": {"expect": [12, 6, 4],  "object": "lid", "role": "free", "clearance": 0.3}}}

  - "object": parts with the same value form one object; the STL coordinates are the
    assembled positions (every part of an object is modelled in the same frame, Z-up,
    Z = 0 on the bed). A part without "object" is an object of its own, as before.
  - "role": "fused" (default inside a group) must touch at least one other part of the
    object with shared faces and no overlap; "free" (print-in-place) must not touch any
    other part and keeps "clearance" mm (default 0.3, tolerances.md) all round.
  - The first part listed for an object is its main part: its filament and settings go
    on the object in a Bambu project; the other parts take the main filament unless the
    user named colours.
  - "filament": 1-based slot for Bambu projects (optional, default 1).

Checks (IDs continue the SKILL.md table):
  per object (only when it has several parts): D2, P1, P2 on the union of its parts, so
    a fused part that floats or overhangs on its own is judged as part of the whole;
  per part: A1 (fused: shares faces with another part, no overlap; hard) and A2 (free:
    FAIL on contact or overlap, WARN below the clearance, like fit.py's F3; hard).

The union and the gap measurements need manifold3d; without it the object's D2 and P1
come from the concatenated triangles and P2, A1 and A2 stay UNVERIFIED. Nothing is faked.
Standard library plus optional manifold3d/numpy.
"""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import validate  # noqa: E402

ROLES = ("fused", "free")
DEFAULT_FREE_CLEARANCE = 0.3     # mm per side, print-in-place joint (references/tolerances.md)
MAX_INTERFERENCE = 0.001         # mm3; coincident faces can leave slivers of this order (fit.py)
GAP_SEARCH = 5.0                 # mm; a part farther than this from every other part "floats"
TOUCH_EPS = 1e-6                 # mm; min_gap below this means the surfaces touch


class AssemblyError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Grouping
# --------------------------------------------------------------------------- #
def group_parts(specs: dict) -> list:
    """[{"name": object, "parts": [part names in order], "main": first part}] from `_parts`.
    Raises AssemblyError on a bad role, a clearance that is not a positive number, or a
    role on a part that is alone in its object."""
    objects, order = {}, []
    for name, spec in specs.items():
        spec = spec or {}
        obj = str(spec.get("object") or name).strip()
        if not obj:
            raise AssemblyError(f"part '{name}': empty object name")
        role = spec.get("role")
        if role is not None and role not in ROLES:
            raise AssemblyError(f"part '{name}': role must be one of {ROLES}, got {role!r}")
        clearance = spec.get("clearance")
        if clearance is not None:
            try:
                clearance = float(clearance)
            except (TypeError, ValueError):
                raise AssemblyError(f"part '{name}': clearance must be a number in mm")
            if not math.isfinite(clearance) or clearance <= 0:
                raise AssemblyError(f"part '{name}': clearance must be a positive number in mm")
        if obj not in objects:
            objects[obj] = {"name": obj, "parts": [], "main": name}
            order.append(obj)
        objects[obj]["parts"].append(name)
    out = []
    for obj in order:
        o = objects[obj]
        if len(o["parts"]) == 1:
            spec = specs.get(o["parts"][0]) or {}
            if spec.get("role") is not None and spec.get("object"):
                raise AssemblyError(f"part '{o['parts'][0]}': role '{spec['role']}' needs at least one other "
                                    f"part in object '{obj}'")
        out.append(o)
    return out


def part_role(spec: dict) -> str:
    return (spec or {}).get("role") or "fused"


def part_clearance(spec: dict) -> float:
    c = (spec or {}).get("clearance")
    return float(c) if c is not None else DEFAULT_FREE_CLEARANCE


# --------------------------------------------------------------------------- #
# Meshes
# --------------------------------------------------------------------------- #
def _manifold():
    try:
        import manifold3d as m3d
        import numpy  # noqa: F401
        return m3d
    except ImportError:
        return None


def _to_manifold(m3d, tris, name):
    import numpy as np
    from threemf import indexed
    verts, faces = indexed(tris)
    mesh = m3d.Mesh(vert_properties=np.asarray(verts, dtype=np.float32),
                    tri_verts=np.asarray(faces, dtype=np.uint32))
    man = m3d.Manifold(mesh)
    if man.status() != m3d.Error.NoError or man.is_empty():
        raise AssemblyError(f"part '{name}' is not a closed mesh ({man.status()}); fix M1-M4 first")
    return man


def _tris_of(man):
    mesh = man.to_mesh()
    V = mesh.vert_properties[:, :3].tolist()
    return [(tuple(V[a]), tuple(V[b]), tuple(V[c])) for a, b, c in mesh.tri_verts.tolist()]


# --------------------------------------------------------------------------- #
# Object-level checks
# --------------------------------------------------------------------------- #
def _p1_p2(m, overhang_angle):
    """P1 and P2 with validate.py's thresholds, on an object's metrics."""
    w, d = m["bbox_mm"][0], m["bbox_mm"][1]
    need = max(10.0, 0.01 * w * d)
    p1 = m["bed_contact_mm2"] >= need
    p2 = m["overhang_pct"] <= 2.0
    return (validate.chk("PASS" if p1 else "WARN", "soft", {"bed_contact_mm2": m["bed_contact_mm2"]},
                         "" if p1 else "little or no flat area on the bed (whole object)"),
            validate.chk("PASS" if p2 else "WARN", "soft",
                         {"overhang_pct": m["overhang_pct"], "overhang_area_mm2": m["overhang_area_mm2"],
                          "max_angle_deg": overhang_angle},
                         "" if p2 else "the assembled object overhangs: supports or a redesign"))


def check_object(obj: dict, stls: dict, specs: dict, bed=None, bed_source=None, overhang_angle=45.0,
                 no_bed_reason=None) -> dict:
    """D2, P1, P2 of an object with several parts, plus A1 / A2 per part.

    stls: {part name: path}. Returns {"checks": {...object checks...}, "metrics": {...},
    "parts": {part: {"role", "checks": {A1 or A2}}}, "method": ..., "warnings": [...]}."""
    names = obj["parts"]
    tris = {n: validate.read_stl(stls[n]) for n in names}
    out = {"name": obj["name"], "parts": {}, "checks": {}, "metrics": {}, "warnings": []}
    m3d = _manifold()
    mans = None
    if m3d is not None:
        mans = {n: _to_manifold(m3d, tris[n], n) for n in names}
        union = mans[names[0]]
        for n in names[1:]:
            union = union + mans[n]
        m = validate.analyse(_tris_of(union), overhang_angle)
        out["method"] = "union of the parts (manifold3d): shared faces vanish, so overhang and bed contact are the object's"
    else:
        m = validate.analyse([t for n in names for t in tris[n]], overhang_angle)
        out["method"] = "concatenated triangles (manifold3d not installed): bounding box and bed contact only"

    # D2 on the whole footprint: every part of an object stays where it was modelled.
    if bed is None:
        out["checks"]["D2"] = validate.chk("UNVERIFIED", "hard", note=no_bed_reason or "no printer profile given")
    else:
        st, val, note = validate.check_bed(m, bed, bed_source)
        out["checks"]["D2"] = validate.chk(st, "hard", val, note, "phase2")
    p1, p2 = _p1_p2(m, overhang_angle)
    out["checks"]["P1"] = p1
    if mans is None:
        out["checks"]["P2"] = validate.chk("UNVERIFIED", "soft",
                                           note="needs manifold3d to remove the faces the parts share")
    else:
        out["checks"]["P2"] = p2
    hull = m.pop("_hull", None)
    out["metrics"] = {k: m[k] for k in ("triangles", "bbox_mm", "bbox_min_mm", "volume_mm3", "shells",
                                        "bed_contact_mm2", "overhang_area_mm2", "overhang_pct")}
    out["rotation_deg"] = (out["checks"]["D2"].get("value") or {}).get("rotation_deg", 0) or 0
    del hull

    # A1 / A2 per part.
    for n in names:
        spec = specs.get(n) or {}
        role = part_role(spec)
        entry = {"role": role, "checks": {}}
        cid = "A1" if role == "fused" else "A2"
        if mans is None:
            entry["checks"][cid] = validate.chk("UNVERIFIED", "hard",
                                                note="manifold3d is not installed (pip install manifold3d); contact not measured")
            out["parts"][n] = entry
            continue
        pairs = []
        for q in names:
            if q == n:
                continue
            inter = mans[n] ^ mans[q]
            overlap = inter.volume() if not inter.is_empty() else 0.0
            gap = mans[n].min_gap(mans[q], GAP_SEARCH)
            pairs.append({"part": q, "overlap_mm3": round(overlap, 4), "gap_mm": round(gap, 4)})
        overlapping = [p for p in pairs if p["overlap_mm3"] > MAX_INTERFERENCE]
        touching = [p for p in pairs if p["overlap_mm3"] <= MAX_INTERFERENCE and p["gap_mm"] <= TOUCH_EPS]
        nearest = min(pairs, key=lambda p: p["gap_mm"]) if pairs else None
        value = {"pairs": pairs}
        if role == "fused":
            if overlapping:
                who = ", ".join(f"{p['part']} ({p['overlap_mm3']} mm3)" for p in overlapping)
                entry["checks"]["A1"] = validate.chk(
                    "FAIL", "hard", value, f"overlaps {who}: a fused part shares faces with its neighbour, it does not "
                    "overlap it (the slicer would clip the overlap by its own rules)", "phase4")
            elif touching:
                value["touches"] = [p["part"] for p in touching]
                entry["checks"]["A1"] = validate.chk("PASS", "hard", value,
                                                     "shares faces with " + ", ".join(value["touches"]))
            else:
                near = f"nearest part {nearest['part']} at {nearest['gap_mm']} mm" if nearest else "no other part"
                entry["checks"]["A1"] = validate.chk(
                    "FAIL", "hard", value, f"touches nothing ({near}): a fused part must sit on another part of "
                    "the object; move it until the faces meet", "phase4")
        else:
            clearance = part_clearance(spec)
            value["clearance_mm"] = clearance
            if overlapping or touching:
                who = ", ".join(p["part"] for p in overlapping + touching)
                entry["checks"]["A2"] = validate.chk(
                    "FAIL", "hard", value, f"touches or overlaps {who}: a print-in-place part would fuse to it; "
                    f"keep {clearance} mm all round", "phase4")
            elif nearest and nearest["gap_mm"] < clearance - 1e-6:
                # Like fit.py's F3: a hard check that WARNs when the clearance is short.
                entry["checks"]["A2"] = validate.chk(
                    "WARN", "hard", value, f"only {nearest['gap_mm']} mm to {nearest['part']}, below the "
                    f"{clearance} mm this joint needs (tolerances.md): it may fuse on a less tuned printer")
            else:
                entry["checks"]["A2"] = validate.chk("PASS", "hard", value,
                                                     f"clear of every other part by at least {clearance} mm"
                                                     if nearest else "no other part")
        out["parts"][n] = entry

    for n, entry in out["parts"].items():
        for cid, ck in entry["checks"].items():
            if ck["state"] == "WARN":
                out["warnings"].append(f"{n} {cid}: {ck.get('note', '')}")
    for cid in ("P1", "P2"):
        if out["checks"][cid]["state"] == "WARN":
            out["warnings"].append(f"{obj['name']} {cid}: {out['checks'][cid].get('note', '')}")
    return out


def object_gate(report: dict) -> str:
    """PASS / FAIL / INCOMPLETE over the object's hard checks and its parts' A1 / A2."""
    hard = [ck for ck in report["checks"].values() if ck["kind"] == "hard"]
    hard += [ck for p in report["parts"].values() for ck in p["checks"].values() if ck["kind"] == "hard"]
    if any(ck["state"] == "FAIL" for ck in hard):
        return "FAIL"
    if any(ck["state"] == "UNVERIFIED" for ck in hard):
        return "INCOMPLETE"
    return "PASS"


__all__ = ["ROLES", "DEFAULT_FREE_CLEARANCE", "AssemblyError", "group_parts", "part_role", "part_clearance",
           "check_object", "object_gate"]
