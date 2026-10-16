#!/usr/bin/env python3
"""
threemf.py - write a core-spec 3MF (ISO/IEC 25422) from STL parts. Standard library only.

One <object> per part, triangle winding copied unchanged from the STL (some third-party
writers flip the winding of internal cavities; this one never reorders vertices).
Each part is laid out side by side on the bed with a build-item transform; the mesh
coordinates themselves are not modified. When the usable bed size is known, a part
that only fits rotated is placed with the Z rotation the D2 check found (validate.py),
so the file and the verdict agree.

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
from validate import WELD_Q, ArtifactError, convex_hull, fit_rect, read_stl  # noqa: E402

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
    """Z rotation (deg, counter-clockwise) a part needs to fit a (w, d) bed; 0 if none or unknown."""
    if not bed:
        return 0
    xy = [(v[0], v[1]) for v in verts]
    w = max(p[0] for p in xy) - min(p[0] for p in xy)
    d = max(p[1] for p in xy) - min(p[1] for p in xy)
    if w <= bed[0] + 1e-6 and d <= bed[1] + 1e-6:
        return 0
    ok, deg, _, _ = fit_rect(convex_hull(xy), bed[0], bed[1])
    return deg if ok else 0


def write_core_3mf(parts, out_path, spacing=10.0, title=None, bed=None):
    """parts: list of (name, stl_path); bed: usable (width, depth) in mm or None.
    Returns {name: {"triangles": n, "rotation_deg": deg}}."""
    objects, items, info = [], [], {}
    cursor = 0.0
    for oid, (name, stl) in enumerate(parts, start=1):
        try:
            verts, faces = indexed(read_stl(stl))
        except ArtifactError as exc:
            raise ArtifactError(f"{name}: {exc}") from exc
        deg = _rotation(verts, bed)
        cs, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        xs = [v[0] * cs - v[1] * sn for v in verts]      # footprint after the rotation
        ys = [v[0] * sn + v[1] * cs for v in verts]
        zs = [v[2] for v in verts]
        vx = "".join(f'<vertex x="{_fmt(v[0])}" y="{_fmt(v[1])}" z="{_fmt(v[2])}"/>' for v in verts)
        tr = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
        objects.append(f'<object id="{oid}" type="model" name={quoteattr(name)}>'
                       f"<mesh><vertices>{vx}</vertices><triangles>{tr}</triangles></mesh></object>")
        # Place each part on the bed (z = 0) next to the previous one. The 3MF transform is
        # row-vector: x' = x*m00 + y*m10 + z*m20 + m30, so a CCW rotation is "c s 0 -s c 0 0 0 1".
        rot = "1 0 0 0 1 0 0 0 1" if not deg else f"{_fmt(cs)} {_fmt(sn)} 0 {_fmt(-sn)} {_fmt(cs)} 0 0 0 1"
        tx, ty, tz = cursor - min(xs), -min(ys), -min(zs)
        items.append(f'<item objectid="{oid}" transform="{rot} {_fmt(tx)} {_fmt(ty)} {_fmt(tz)}"/>')
        cursor += (max(xs) - min(xs)) + spacing
        info[name] = {"triangles": len(faces), "rotation_deg": deg}
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}">'
        f'<metadata name="Title">{escape(title or os.path.splitext(os.path.basename(out_path))[0])}</metadata>'
        '<metadata name="Application">3dprint-scout</metadata>'
        f"<resources>{''.join(objects)}</resources><build>{''.join(items)}</build></model>"
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
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
