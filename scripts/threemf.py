#!/usr/bin/env python3
"""
threemf.py - write a core-spec 3MF (ISO/IEC 25422) from STL parts. Standard library only.

One <object> per part, triangle winding copied unchanged from the STL (some third-party
writers flip the winding of internal cavities; this one never reorders vertices).
Objects are laid out side by side on the bed with a build-item transform; the mesh
coordinates themselves are not modified. When the usable bed size is known, an object
that only fits rotated is placed with the Z rotation the D2 check found (validate.py),
so the file and the verdict agree.

Parts grouped into one object (params.json `_parts` with "object", see assembly.py) are
written as mesh objects referenced by one parent object through <components>, each with
the identity transform, so they keep their assembled positions; the layout moves the
parent. A slicer that understands components shows one object with several parts.

This is the slicer-neutral 3MF. Bambu Studio project files (plates, filaments,
per-object settings) are produced by bambu3mf.py from a template instead.

Usage: python3 threemf.py out.3mf body.stl lid.stl      (prints one JSON document)
"""
from __future__ import annotations

import json
import math
import os
import sys
import zipfile
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate import WELD_Q, ArtifactError, convex_hull, fit_rect, file_sha256, read_stl  # noqa: E402

MANIFEST_SCHEMA = "3dprint-scout.3mf-manifest/1"


def write_3mf_manifest(path, parts):
    """`<path>.manifest.json` next to a 3MF: its own sha256 and the sha256 of every part STL it
    was written from, so finalize.py can tell a delivered 3MF holds the verified STLs. Copy it
    along with the 3MF (it says nothing about edits made in a slicer afterwards)."""
    data = {"schema": MANIFEST_SCHEMA, "artifact_sha256": file_sha256(path),
            "parts": {name: file_sha256(stl) for name, stl in parts}}
    with open(path + ".manifest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    "</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    "</Relationships>"
)
IDENTITY = "1 0 0 0 1 0 0 0 1"


def indexed(tris):
    """Weld STL triangles into (vertices, faces); drop faces that collapse when welded."""
    index, verts, faces = {}, [], []
    for t in tris:
        ids = []
        for v in t:
            k = (round(v[0] / WELD_Q), round(v[1] / WELD_Q), round(v[2] / WELD_Q))
            if k not in index:
                index[k] = len(verts)
                verts.append(v)
            ids.append(index[k])
        if len(set(ids)) == 3:
            faces.append(tuple(ids))
    return verts, faces


def _fmt(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _rotation(verts, bed):
    """Z rotation (deg, counter-clockwise) a footprint needs to fit a (w, d) bed; 0 if none or unknown."""
    if not bed:
        return 0
    xy = [(v[0], v[1]) for v in verts]
    w = max(p[0] for p in xy) - min(p[0] for p in xy)
    d = max(p[1] for p in xy) - min(p[1] for p in xy)
    if w <= bed[0] + 1e-6 and d <= bed[1] + 1e-6:
        return 0
    ok, deg, _, _ = fit_rect(convex_hull(xy), bed[0], bed[1])
    return deg if ok else 0


def _groups(parts, objects):
    """[(object name, [(part name, stl)])]: `objects` is [{"name", "parts": [names]}] or None."""
    by_name = {name: stl for name, stl in parts}
    if not objects:
        return [(name, [(name, stl)]) for name, stl in parts]
    out, seen = [], set()
    for obj in objects:
        members = [(n, by_name[n]) for n in obj["parts"] if n in by_name]
        if members:
            out.append((obj["name"], members))
            seen.update(n for n, _ in members)
    out += [(name, [(name, stl)]) for name, stl in parts if name not in seen]
    return out


def write_core_3mf(parts, out_path, spacing=10.0, title=None, bed=None, objects=None):
    """parts: list of (name, stl_path); bed: usable (width, depth) in mm or None;
    objects: optional grouping [{"name": ..., "parts": [part names]}] (assembly.group_parts).
    Returns {part name: {"triangles": n, "rotation_deg": deg, "object": object name}}."""
    resources, items, info = [], [], {}
    cursor, next_id = 0.0, 1
    for obj_name, members in _groups(parts, objects):
        meshes = []
        for name, stl in members:
            try:
                verts, faces = indexed(read_stl(stl))
            except ArtifactError as exc:
                raise ArtifactError(f"{name}: {exc}") from exc
            meshes.append((name, verts, faces))
        all_verts = [v for _n, verts, _f in meshes for v in verts]
        deg = _rotation(all_verts, bed)
        cs, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        xs = [v[0] * cs - v[1] * sn for v in all_verts]      # footprint after the rotation
        ys = [v[0] * sn + v[1] * cs for v in all_verts]
        zs = [v[2] for v in all_verts]
        mesh_ids = []
        for name, verts, faces in meshes:
            vx = "".join(f'<vertex x="{_fmt(v[0])}" y="{_fmt(v[1])}" z="{_fmt(v[2])}"/>' for v in verts)
            tr = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
            resources.append(f'<object id="{next_id}" type="model" name={quoteattr(name)}>'
                             f"<mesh><vertices>{vx}</vertices><triangles>{tr}</triangles></mesh></object>")
            mesh_ids.append(next_id)
            info[name] = {"triangles": len(faces), "rotation_deg": deg, "object": obj_name}
            next_id += 1
        if len(meshes) == 1:
            item_id = mesh_ids[0]
        else:
            # Parts keep their modelled (assembled) positions: identity component transforms.
            comps = "".join(f'<component objectid="{i}" transform="{IDENTITY} 0 0 0"/>' for i in mesh_ids)
            resources.append(f'<object id="{next_id}" type="model" name={quoteattr(obj_name)}>'
                             f"<components>{comps}</components></object>")
            item_id = next_id
            next_id += 1
        # Place the object on the bed (z = 0) next to the previous one. The 3MF transform is
        # row-vector: x' = x*m00 + y*m10 + z*m20 + m30, so a CCW rotation is "c s 0 -s c 0 0 0 1".
        rot = IDENTITY if not deg else f"{_fmt(cs)} {_fmt(sn)} 0 {_fmt(-sn)} {_fmt(cs)} 0 0 0 1"
        tx, ty, tz = cursor - min(xs), -min(ys), -min(zs)
        items.append(f'<item objectid="{item_id}" transform="{rot} {_fmt(tx)} {_fmt(ty)} {_fmt(tz)}"/>')
        cursor += (max(xs) - min(xs)) + spacing
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}">'
        f'<metadata name="Title">{escape(title or os.path.splitext(os.path.basename(out_path))[0])}</metadata>'
        '<metadata name="Application">3dprint-scout</metadata>'
        f"<resources>{''.join(resources)}</resources><build>{''.join(items)}</build></model>"
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
    write_3mf_manifest(out_path, parts)
    return info


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = {"schema": "3dprint-scout.threemf/1", "ran": False, "errors": []}
    try:
        if len(argv) < 2:
            raise ValueError("usage: threemf.py out.3mf part.stl [more.stl ...]")
        if os.path.exists(argv[0]):
            raise ValueError(f"{argv[0]} already exists; refusing to overwrite (choose a new file name)")
        parts = [(os.path.splitext(os.path.basename(p))[0], p) for p in argv[1:]]
        out["objects"] = write_core_3mf(parts, argv[0])
        out.update(ran=True, out=argv[0])
    except (ValueError, OSError, ArtifactError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
