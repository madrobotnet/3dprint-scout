#!/usr/bin/env python3
"""
render.py - Blender renders of STL parts from any engine: iso, front, right and top views in
one PNG, the same grid as preview.py, drawn by Blender's Workbench engine (headless, no GPU
needed; EEVEE or Cycles on request) with part colours from filament names.

  python3 render.py out/body.stl -o out/render.png
  python3 render.py out/box.stl out/lid.stl -o out/render.png --color "lid=Jade White" --color box=#1a1a1a
  python3 render.py out/body.stl -o out/render.png --engine cycles --views iso --size 1200x900

Needs Blender 4.5 LTS or newer: the `blender` binary (PATH, BLENDER=/path, or the usual
install folders) or the `bpy` module in some Python (--blender-python, BLENDER_PYTHON, or
the Python running this script). Without one it says so and exits 1: preview.py is the
fallback and stays the G4 check. The STLs are passed through unchanged (1 unit = 1 mm) and
drawn where their coordinates put them, like preview.py. Colours come from a small table of
approximate Bambu filament colours or #rrggbb; an unknown name gets neutral grey and a
warning, never a question (the names are checked before Blender starts).

Prints one JSON document in preview.py's style: files written with the G4 sanity check of
the image (a real PNG whose pixels show the part against a background; `fg` and `fg_views`
are the fractions of pixels showing the part, per view), the parts with their colours (and
the colour drawn: very light and very dark filaments are moved a little off the background
and off black), the size in mm and the renderer. Exit 0 = rendered and sane, 2 = image not
usable (blank, or no background), 1 = usage, file or Blender error. Refuses to overwrite
unless --overwrite is given.

`--lang ko` draws the view names in Korean (등각, 앞, 오른쪽, 위, ...), for a user who reads
Korean; the caption takes any text Blender's fonts can draw. Next to the image it writes the
same sidecar as preview.py (`<image>.png.json`: the image's sha256, the views, each STL with its
sha256), which ties a person's judgement of the image to the parts (finalize.py).
"""
from __future__ import annotations

import argparse
import importlib.util
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
LANGS = ("en", "ko")                    # the view names drawn in the image (blender_builder.VIEW_LABELS)


def builder_module():
    """blender_builder's pure helpers (colours, the G4 bound), imported without bpy."""
    spec = importlib.util.spec_from_file_location("_blender_builder_helpers", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RenderError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise RenderError(f"usage error: {message}")


def render_command(stls, out, views, size, engine, colors, label=None, exe=None, python=None, overwrite=False,
                   lang="en"):
    """The command line: the blender binary running blender_builder.py as a script, or the bpy
    Python running it; the renderer's own arguments follow `--`."""
    args = ["--", "render", *[os.path.abspath(s) for s in stls], "-o", os.path.abspath(out),
            "--views", ",".join(views), "--size", f"{size[0]}x{size[1]}", "--engine", engine]
    for c in colors:
        args += ["--color", c]
    if label is not None:
        args += ["--label", label]
    if lang != "en":
        args += ["--lang", lang]
    if overwrite:
        args.append("--overwrite")
    if exe:
        return [exe, "--background", "--factory-startup", "--python-exit-code", "1", "--python", BUILDER] + args
    return [python, BUILDER] + args


def choose_blender(blender_python=None):
    """(binary path or None, bpy python or None); raises RenderError when neither works."""
    try:
        chosen = build.choose_blender(blender_python)            # the same choice as build.py and detect
    except RuntimeError as exc:
        raise RenderError(f"{exc}; or use preview.py")
    return chosen["exe"], chosen["python"], chosen["info"]["version"]


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
    hashes = preview.stl_hashes(args.stl)              # before Blender reads them: the sidecar names the bytes drawn
    for path in args.stl:
        try:
            read_stl(path)                                       # G4 on the input, before Blender starts
        except ArtifactError as exc:
            raise RenderError(f"{path}: {exc}")
        names.append(os.path.splitext(os.path.basename(path))[0])
    bb = builder_module()
    try:
        colours, warnings = bb.parse_colors(args.color, names)   # names checked here, before Blender starts
    except ValueError as exc:
        raise RenderError(str(exc))
    if not args.out.lower().endswith(".png"):
        raise RenderError("-o must end in .png")
    if args.lang not in LANGS:
        raise RenderError(f"--lang must be one of {', '.join(LANGS)}")
    for t in (args.out, preview.sidecar_path(args.out)):
        if os.path.exists(t) and not args.overwrite:
            raise RenderError(f"{t} already exists; pass --overwrite for a working file in out/, or choose a new name")
    exe, python, version = choose_blender(args.blender_python)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cmd = render_command(args.stl, args.out, views, (width, height), args.engine, args.color, args.label, exe, python,
                         overwrite=args.overwrite, lang=args.lang)
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
    sane, note = preview.png_sane(rep["path"], rep["fg"])      # a real PNG with pixels, something drawn
    if sane:
        sane, note = bb.fg_sane(rep["fg"], rep.get("fg_views"))  # a background behind it, every view drawn
    renderer = rep["renderer"] + (" (binary)" if exe else " (bpy module)")
    try:
        sidecar = preview.write_sidecar(args.out, args.stl, views, renderer, args.lang, hashes=hashes)
    except ValueError as exc:
        raise RenderError(str(exc))
    return {"files": [{"path": args.out, "views": views, "sane": sane, "note": note, "fg": rep["fg"],
                       "fg_views": rep.get("fg_views"), "bytes": os.path.getsize(args.out), "sidecar": sidecar}],
            "parts": rep["parts"], "size_mm": rep["size_mm"], "colour_note": rep.get("colour_note", bb.COLOUR_TABLE_NOTE),
            "renderer": renderer,
            "seconds": round(time.time() - t0, 2), "sane": sane,
            "warnings": warnings + [w for w in rep.get("warnings", []) if w not in warnings]}


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
                        help="part=filament name or #rrggbb, e.g. lid=\"Jade White\" (repeatable; default palette; "
                             "an unknown name gives neutral grey and a warning)")
        ap.add_argument("--label", help="caption text (default: the size in mm)")
        ap.add_argument("--lang", default="en", help="language of the view names: en (default) or ko")
        ap.add_argument("--blender-python", help="Python with the bpy module (forces the bpy path)")
        ap.add_argument("--timeout", type=int, default=600, help="seconds (default 600)")
        ap.add_argument("--overwrite", action="store_true")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        result = run(args)
        out["warnings"] += result.pop("warnings", [])
        out.update(result)
        out["ran"] = True
    except (RenderError, OSError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if not out["ran"]:
        return 1
    return 0 if out["sane"] else 2


if __name__ == "__main__":
    sys.exit(main())
