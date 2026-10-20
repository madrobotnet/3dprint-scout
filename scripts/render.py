#!/usr/bin/env python3
"""
render.py - Blender renders of STL parts from any engine: iso, front, right and top views in
one PNG, the same grid as preview.py, drawn by Blender's Workbench engine (headless, no GPU
needed; EEVEE or Cycles on request) with part colours from filament names.

  python3 render.py out/body.stl -o out/render.png
  python3 render.py out/box.stl out/lid.stl -o out/render.png --color "lid=Jade White" --color box=#1a1a1a
  python3 render.py out/body.stl -o out/render.png --engine cycles --views iso --size 1200x900

Needs Blender: the `blender` binary (PATH, BLENDER=/path, or the usual install folders) or
the `bpy` module in some Python (--blender-python, BLENDER_PYTHON, or the Python running
this script). Without one it says so and exits 1: preview.py is the fallback and stays the
G4 check. The STLs are passed through unchanged (1 unit = 1 mm) and drawn where their
coordinates put them, like preview.py.

Prints one JSON document in preview.py's style: files written with the G4 sanity check of
the image (a real PNG with pixels that show the part), the parts with their colours, the
size in mm and the renderer. Exit 0 = rendered and sane, 2 = blank image (G4), 1 = usage,
file or Blender error. Refuses to overwrite unless --overwrite is given.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build    # noqa: E402  (Blender discovery)
import preview  # noqa: E402  (png_sane, VIEWS)
from validate import ArtifactError, read_stl  # noqa: E402

SCHEMA = "3dprint-scout.render/1"
BUILDER = os.path.join(build.ENGINES_DIR, "blender_builder.py")
ENGINES = ("workbench", "eevee", "cycles")


class RenderError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise RenderError(f"usage error: {message}")


def render_command(stls, out, views, size, engine, colors, label=None, exe=None, python=None):
    """The command line: the blender binary running blender_builder.py as a script, or the bpy
    Python running it; the renderer's own arguments follow `--`."""
    args = ["--", "render", *[os.path.abspath(s) for s in stls], "-o", os.path.abspath(out),
            "--views", ",".join(views), "--size", f"{size[0]}x{size[1]}", "--engine", engine]
    for c in colors:
        args += ["--color", c]
    if label is not None:
        args += ["--label", label]
    if exe:
        return [exe, "--background", "--factory-startup", "--python-exit-code", "1", "--python", BUILDER] + args
    return [python, BUILDER] + args


def choose_blender(blender_python=None):
    """(binary path or None, bpy python or None); raises RenderError when neither works."""
    exe = None if blender_python else build.find_blender()
    if exe:
        info = build.blender_info(exe)
        if not info.get("error") and build.version_tuple(info["version"])[:2] >= (4, 2):
            return exe, None, info["version"]
    probe = build.bpy_info(blender_python)
    if probe and "error" not in probe and tuple(probe["version_tuple"])[:2] >= (4, 2):
        return None, probe["python"], probe["version"]
    raise RenderError("Blender not found (no `blender` binary 4.2+ on PATH or in the usual folders, no bpy module in "
                      + ", ".join(build.bpy_pythons(blender_python)) + "); use preview.py, or install Blender / pip install bpy")


def run(args) -> dict:
    views = [v.strip().lower() for v in args.views.split(",") if v.strip()]
    bad = [v for v in views if v not in preview.VIEWS]
    if bad or not views:
        raise RenderError(f"unknown view(s) {bad}; choose from {', '.join(preview.VIEWS)}")
    try:
        width, height = (int(x) for x in args.size.lower().split("x"))
    except ValueError:
        raise RenderError("--size WIDTHxHEIGHT, e.g. 1600x1200")
    if width < 200 or height < 200 or width * height > preview.MAX_PIXELS:
        raise RenderError("--size between 200x200 and 4096x4096")
    if args.engine not in ENGINES:
        raise RenderError(f"--engine must be one of {', '.join(ENGINES)}")
    names = []
    for path in args.stl:
        try:
            read_stl(path)                                       # G4 on the input, before Blender starts
        except ArtifactError as exc:
            raise RenderError(f"{path}: {exc}")
        names.append(os.path.splitext(os.path.basename(path))[0])
    for c in args.color:
        if "=" not in c or c.split("=", 1)[0] not in names:
            raise RenderError(f"--color needs part=colour with a part among {names}, got {c!r}")
    if not args.out.lower().endswith(".png"):
        raise RenderError("-o must end in .png")
    if os.path.exists(args.out) and not args.overwrite:
        raise RenderError(f"{args.out} already exists; pass --overwrite for a working file in out/, or choose a new name")
    exe, python, version = choose_blender(args.blender_python)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cmd = render_command(args.stl, args.out, views, (width, height), args.engine, args.color, args.label, exe, python)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=args.timeout, env=env, **build.TEXT)
    except subprocess.TimeoutExpired:
        raise RenderError(f"Blender timed out after {args.timeout}s")
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("@@3DPS ")]
    if r.returncode != 0 or not lines:
        tail = "\n".join(ln for ln in (r.stdout + r.stderr).splitlines()
                         if ln.strip() and not ln.startswith("EGL Error"))[-2000:]
        raise RenderError(f"Blender render failed (exit {r.returncode}):\n{tail}")
    rep = json.loads(lines[-1][len("@@3DPS "):])
    sane, note = preview.png_sane(rep["path"], rep["fg"])
    return {"files": [{"path": args.out, "views": views, "sane": sane, "note": note, "bytes": os.path.getsize(args.out)}],
            "parts": rep["parts"], "size_mm": rep["size_mm"],
            "renderer": rep["renderer"] + (" (binary)" if exe else " (bpy module)"),
            "seconds": round(time.time() - t0, 2), "sane": sane}


def main(argv=None):
    out = {"schema": SCHEMA, "ran": False, "sane": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="Blender renders of STL parts (Workbench by default)")
        ap.add_argument("stl", nargs="+")
        ap.add_argument("-o", "--out", required=True, help="PNG path")
        ap.add_argument("--views", default=",".join(preview.DEFAULT_VIEWS), help="comma list of " + ", ".join(preview.VIEWS))
        ap.add_argument("--size", default="1600x1200")
        ap.add_argument("--engine", default="workbench", help="workbench (default, headless) | eevee | cycles")
        ap.add_argument("--color", action="append", default=[],
                        help="part=filament name or #rrggbb, e.g. lid=\"Jade White\" (repeatable; default palette)")
        ap.add_argument("--label", help="caption text (default: the size in mm)")
        ap.add_argument("--blender-python", help="Python with the bpy module (forces the bpy path)")
        ap.add_argument("--timeout", type=int, default=600, help="seconds (default 600)")
        ap.add_argument("--overwrite", action="store_true")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        out.update(run(args))
        out["ran"] = True
    except (RenderError, OSError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if not out["ran"]:
        return 1
    return 0 if out["sane"] else 2


if __name__ == "__main__":
    sys.exit(main())
