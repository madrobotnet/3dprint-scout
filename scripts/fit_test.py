#!/usr/bin/env python3
"""
fit_test.py - small test pieces to find the right clearance before building the real part.

When the part must fit an object whose exact shape is not known (no caliper numbers, no
drawing), print two or three thin pieces of the mating profile in clearance steps, try
them, and build the real part with the step that fits (SKILL.md, Phase 4). Each piece is
marked with 1, 2, 3 ... holes in a tab so the user can tell them apart.

  python3 fit_test.py --profile rounded --size 45.1,14.0 --radius 2 --out out/fit
  python3 fit_test.py --profile circle --size 12.6 --mode plug --clearance 0.2 --out out/fit
  python3 fit_test.py --profile polygon --polygon outline.json --out out/fit

Profiles: rect (W,D), rounded (W,D plus --radius), circle (diameter), polygon (a JSON file
holding [[x, y], ...] or {"points": [[x, y], ...]}, in mm).
Modes: ring (default): the piece has a hole shaped like the object, grown by the clearance;
the object goes INTO it (holders, pockets, caps). plug: the piece is the object's outline
shrunk by the clearance; it goes INTO the object's opening (lids, pegs, inserts).
Clearance steps: --clearance is the middle value per side (default: the "object in a
pocket" fit of tolerances.md, 0.30 mm), --step the spacing (0.15), --steps how many (3).

Writes <out>/<name>_1.stl ... and <out>/<name>.json (one JSON document is also printed) and
refuses to overwrite any existing file. With --bambu-template it also writes a job file for
bambu3mf.py. Needs manifold3d.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import write_binary_stl  # noqa: E402

SCHEMA = "3dprint-scout.fit_test/1"
PLA_DENSITY = 1.24          # g/cm3, typical PLA datasheet value (NatureWorks Ingeo 4043D)
DEFAULT_CLEARANCE = 0.30    # mm per side: "object in a pocket" (tolerances.md)
DEFAULT_STEP = 0.15
DEFAULT_STEPS = 3
MARK_HOLE_D = 2.5           # mm; marker holes, above the 2 mm minimum hole (tolerances.md)
MARK_PITCH = 4.5
TAB_DEPTH = 7.0


class FitTestError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise FitTestError(f"usage error: {message}")


def load_polygon(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    pts = data.get("points") if isinstance(data, dict) else data
    if not isinstance(pts, list) or len(pts) < 3:
        raise FitTestError("polygon file needs at least three [x, y] points")
    out = []
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise FitTestError(f"polygon point {p!r} is not [x, y]")
        out.append([float(p[0]), float(p[1])])
    return out


def profile_cross_section(args, m3d, parts):
    """The mating object's outline as a CrossSection, centred on the origin, plus a description."""
    if args.profile in ("rect", "rounded"):
        if len(args.size) != 2:
            raise FitTestError("--size W,D for rect and rounded")
        w, d = args.size
        r = args.radius if args.profile == "rounded" else 0.0
        if args.profile == "rounded" and r <= 0:
            raise FitTestError("--radius must be positive for a rounded rectangle")
        cs = parts.rounded_rect(w, d, r).translate([-w / 2, -d / 2])
        desc = {"profile": args.profile, "size_mm": [w, d], "radius_mm": r}
    elif args.profile == "circle":
        if len(args.size) != 1:
            raise FitTestError("--size D (diameter) for a circle")
        dia = args.size[0]
        cs = m3d.CrossSection.circle(dia / 2, parts.circle_segments(dia / 2))
        desc = {"profile": "circle", "size_mm": [dia, dia]}
    elif args.profile == "polygon":
        if not args.polygon:
            raise FitTestError("--polygon FILE is needed for the polygon profile")
        pts = load_polygon(args.polygon)
        cs = m3d.CrossSection([pts], m3d.FillRule.EvenOdd)
        if cs.is_empty():
            raise FitTestError("the polygon has no area (self-intersecting or repeated points?)")
        x0, y0, x1, y1 = cs.bounds()
        cs = cs.translate([-(x0 + x1) / 2, -(y0 + y1) / 2])
        desc = {"profile": "polygon", "size_mm": [round(x1 - x0, 3), round(y1 - y0, 3)], "points": len(pts),
                "polygon_file": os.path.basename(args.polygon)}
    else:
        raise FitTestError("--profile must be rect, rounded, circle or polygon")
    if any(v <= 0 for v in desc["size_mm"]):
        raise FitTestError("the profile size must be positive")
    return cs, desc


def piece(cs, clearance: float, index: int, args, m3d, parts):
    """One test piece: ring or plug of the profile at this clearance, plus the marker tab."""
    join = m3d.JoinType.Round
    seg = parts.circle_segments(max(abs(clearance), 0.5))
    h = args.height
    if args.mode == "ring":
        inner = cs.offset(clearance, join, 2.0, seg)
        outer = inner.offset(args.wall, join, 2.0, seg)
        body = m3d.Manifold.extrude(outer, h) - m3d.Manifold.extrude(inner, h + 0.2).translate([0, 0, -0.1])
        x0, y0, x1, y1 = outer.bounds()
        ix0, iy0, ix1, iy1 = inner.bounds()
        info = {"hole_size_mm": [round(ix1 - ix0, 3), round(iy1 - iy0, 3)]}
    else:
        plug = cs.offset(-clearance, join, 2.0, seg)
        if plug.is_empty():
            raise FitTestError(f"clearance {clearance} mm leaves nothing of the profile")
        body = m3d.Manifold.extrude(plug, h)
        x0, y0, x1, y1 = plug.bounds()
        info = {"plug_size_mm": [round(x1 - x0, 3), round(y1 - y0, 3)]}
    # Marker tab on the +Y side: `index` holes of MARK_HOLE_D in a row.
    tab_w = max(index * MARK_PITCH + 2.0, 8.0)
    tab = m3d.Manifold.cube([tab_w, TAB_DEPTH + 1.0, h]).translate([-tab_w / 2, y1 - 1.0, 0])
    for i in range(index):
        x = (i - (index - 1) / 2) * MARK_PITCH
        tab -= parts.hole(MARK_HOLE_D, h + 0.2).translate([x, y1 + TAB_DEPTH / 2, h + 0.1])
    out = body + tab
    if out.status() != m3d.Error.NoError or out.is_empty():
        raise FitTestError(f"piece {index}: geometry failed ({out.status()})")
    out = parts.clean(out)
    bb = out.bounding_box()
    info["piece_size_mm"] = [round(bb[3] - bb[0], 2), round(bb[4] - bb[1], 2), round(bb[5] - bb[2], 2)]
    return out, info


def export(man, path: str) -> int:
    mesh = man.to_mesh()
    write_binary_stl(path, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
    return int(mesh.tri_verts.shape[0])


def run(args) -> dict:
    try:
        import manifold3d as m3d
        import parts
    except ImportError as exc:
        raise FitTestError(f"manifold3d is needed for fit-test pieces (pip install manifold3d): {exc}")
    if args.steps < 1 or args.steps > 9:
        raise FitTestError("--steps must be 1..9")
    if args.height <= 0 or args.wall <= 0:
        raise FitTestError("--height and --wall must be positive")
    cs, desc = profile_cross_section(args, m3d, parts)
    clearances = [round(args.clearance + args.step * (i - (args.steps - 1) / 2), 3) for i in range(args.steps)]
    if args.mode not in ("ring", "plug"):
        raise FitTestError("--mode must be ring or plug")

    os.makedirs(args.out, exist_ok=True)
    summary_path = os.path.join(args.out, f"{args.name}.json")
    stl_paths = [os.path.join(args.out, f"{args.name}_{i + 1}.stl") for i in range(args.steps)]
    job_path = os.path.join(args.out, f"{args.name}_bambu_job.json") if args.bambu_template else None
    for p in [summary_path] + stl_paths + ([job_path] if job_path else []):
        if os.path.exists(p):
            raise FitTestError(f"{p} already exists; refusing to overwrite (choose another --out or --name)")

    steps = []
    for i, c in enumerate(clearances):
        man, info = piece(cs, c, i + 1, args, m3d, parts)
        tris = export(man, stl_paths[i])
        vol = man.volume()
        entry = {"index": i + 1, "marks": i + 1, "clearance_per_side_mm": c, "clearance_on_size_mm": round(2 * c, 3),
                 "stl": stl_paths[i], "triangles": tris, "volume_mm3": round(vol, 1),
                 "mass_g_pla": round(vol / 1000 * PLA_DENSITY, 1)}
        entry.update(info)
        steps.append(entry)

    how = ("Print all pieces with the same printer, filament and process preset as the real part. "
           + ("Slide the object into each ring: " if args.mode == "ring" else "Push each plug into the opening: ")
           + "the one that goes in by hand without force and does not rattle is right. Count the holes in its "
           "tab and use that step's clearance_per_side_mm in params.json. If the tightest piece is still loose, "
           "or the loosest still tight, run again with a shifted --clearance.")
    out = {"schema": SCHEMA, "ran": True, "mode": args.mode, "profile": desc,
           "height_mm": args.height, "wall_mm": args.wall if args.mode == "ring" else None,
           "clearance_mm": {"middle_per_side": args.clearance, "step": args.step, "steps": args.steps,
                            "source": "tolerances.md, object in a pocket" if args.clearance == DEFAULT_CLEARANCE else "user"},
           "steps": steps, "summary": summary_path, "how_to_read": how, "warnings": [], "errors": []}
    if job_path:
        job = {"template": args.bambu_template, "out": os.path.join(args.out, f"{args.name}_bambu.3mf"),
               "parts": [{"name": f"{args.name}_{s['index']}", "stl": s["stl"], "plate": 1} for s in steps]}
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)
        out["bambu_job"] = job_path
        out["warnings"].append(f"run: python3 bambu3mf.py {job_path}  (it refuses to overwrite {job['out']})")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return out


def main(argv=None):
    out = {"schema": SCHEMA, "ran": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="fit-test pieces in clearance steps")
        ap.add_argument("--profile", required=True, choices=["rect", "rounded", "circle", "polygon"])
        ap.add_argument("--size", default="", help="W,D in mm (rect, rounded) or D (circle)")
        ap.add_argument("--radius", type=float, default=0.0, help="corner radius for rounded")
        ap.add_argument("--polygon", help="JSON file with [[x, y], ...] in mm")
        ap.add_argument("--mode", default="ring", choices=["ring", "plug"])
        ap.add_argument("--clearance", type=float, default=DEFAULT_CLEARANCE, help="middle clearance per side (mm)")
        ap.add_argument("--step", type=float, default=DEFAULT_STEP, help="spacing between steps (mm)")
        ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
        ap.add_argument("--height", type=float, default=3.0, help="piece height (mm)")
        ap.add_argument("--wall", type=float, default=2.4, help="ring wall (mm)")
        ap.add_argument("--out", default=os.path.join("out", "fit"))
        ap.add_argument("--name", default="fit")
        ap.add_argument("--bambu-template", help="also write a bambu3mf.py job using this template")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        args.size = [float(x) for x in args.size.split(",") if x.strip()] if args.size else []
        out.update(run(args))
    except (FitTestError, OSError, ValueError, json.JSONDecodeError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
