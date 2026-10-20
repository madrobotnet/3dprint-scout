"""
blender_builder.py - helpers for Blender generator scripts (3dprint-scout, engine "blender").

A generator imports this file (build.py puts this folder on the path; in a live session the
file is sent next to the generator) and builds in millimetres, Z-up, Z = 0 on the bed:

    # 3dprint-scout: engine=blender
    import blender_builder as bb

    PARAMETERS = {"w": 40.0, "d": 30.0, "h": 6.0, "fillet": 1.5, "label": "A"}   # mm, with sources

    def build(p):
        body = bb.box([p["w"], p["d"], p["h"]], "body")           # bottom on the bed
        bb.bevel(body, p["fillet"])                                # real fillets, not on the bed edge
        bb.bed_chamfer(body, 0.4)                                  # the bed edge gets a chamfer (P6)
        mark = bb.text(p["label"], height=6.0, depth=0.9)         # built-in font, or font=path (packed)
        mark.location = (p["w"] / 2, p["d"] / 2, p["h"] - 0.1)     # sunk 0.1 mm into the top face
        bb.boolean(body, mark, "union")                            # one body: letters fused to the face
        bb.part(body, "body")
        return {"body": body}

    if __name__ == "__main__":
        bb.main(build, PARAMETERS)                                 # --params, --out, --only, --blend

Letters that should keep their own colour go on a separate plate (a disc, a plaque) unioned
with them, registered as a `fused` part; a text object left as its own part is one body per
letter, so its `_parts` entry needs `shells` (parts.md) or it fails M5.

`main` builds into a scene of its own, calls `build`, writes the parameters as custom
properties on a PARAMETERS empty, exports one binary STL per part (modifiers applied,
1 unit = 1 mm, scene unit off), saves `<out>/<generator>.blend` and prints one `@@3DPS {...}`
line that build.py reads. validate.py decides every verdict from the STLs; nothing Blender
reports about dimensions is trusted.

Run as a script, this file renders STLs (`-- render a.stl b.stl -o out.png ...`); scripts/render.py
is the front end for that.

Safety: this module writes only under the folder it is given (`--out`, the render target), opens
no network connection, runs no other program and never resets, closes, saves over or discards
the file open in Blender: it always builds into a scene named "3dprint-scout" next to whatever
is open, touches only the data it tagged, and never switches the user's window to that scene.
`save_blend` writes a new file from the build scene's data-blocks alone (no UI, no preferences,
no window state), refuses the open file's path and any existing path it was not told to
rewrite, packs its own fonts and images under neutral names, and refuses to leave a file that
holds an absolute path of this machine.

Needs Blender 4.5 LTS or newer (the Manifold boolean solver; text and renders are tested from
4.5 on). The pure helpers (argument parsing, segment counts, colours, the camera maths) import
without bpy and are unit-tested; the Blender calls are tested with the `bpy` module.
"""
import argparse
import contextlib
import json
import math
import os
import re
import sys
import tempfile
import time

try:
    import bpy
    import bmesh
    import mathutils
except ImportError:                     # outside Blender (tests, syntax check): pure helpers still work
    bpy = bmesh = mathutils = None

SCHEMA = "3dprint-scout.blender_builder/1"
MIN_VERSION = (4, 5)                    # Manifold boolean solver; wm.stl_export exists since 4.2
TAG = "3dprint_scout"                   # custom property on everything this module creates
SCENE_NAME = "3dprint-scout"
LINE_WIDTH = 0.45                       # mm, one perimeter of a 0.4 mm nozzle (design.md)
WELD = 1e-4                             # mm, the validator's own welding distance
MAX_SEGMENTS = 32
BED_CHAMFER_RUN = 0.9                   # run / rise of the bed chamfer: steeper than 45 deg, so P2 never counts it
FG_MIN = 0.0005                         # at or below: a blank image (or view), nothing of the part drawn
FG_MAX = 0.95                           # a render whose pixels nearly all differ from the background has no background

# Views, palette and background as in scripts/preview.py, so both images read the same.
VIEWS = {
    "iso": ((1.0, -1.0, 0.8), (0.0, 0.0, 1.0)),
    "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "bottom": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
}
DEFAULT_VIEWS = ["iso", "front", "right", "top"]
PALETTE = ["#4682b4", "#dd783c", "#5aa05a", "#a064b4", "#c8aa32", "#50aab4"]
NEUTRAL = (0.5, 0.5, 0.5)               # an unknown filament name: neutral grey, never a question
BACKGROUND = (0.965, 0.965, 0.965)    # sRGB, as preview.py's (246, 246, 246)
INK = (0.16, 0.16, 0.16)               # sRGB
DARK_LIFT = 0.15                        # black is drawn as dark grey (sRGB 0.15) so its edges show
STUDIO_LIGHT = "paint.sl"               # Workbench studio light: faces towards the camera keep ~96 %
                                        # of their colour (the default light leaves ~69 %: white read grey)
MARGIN = 0.08
ENGINE_NAMES = ("workbench", "eevee", "cycles")
COLOUR_TABLE_NOTE = ("colours are approximate screen values of common Bambu filaments, for the preview only; "
                     "an unknown name gets neutral grey")

# Approximate screen colours of common Bambu Lab PLA Basic / Matte filaments, from the colour
# swatches on the Bambu Lab store (not from any slicer file). Only for preview images; the
# user's own AMS colours, when known, win. Keys: lower-case, brand / material words dropped.
FILAMENTS = {
    "jadewhite": "#ffffff", "white": "#ffffff", "black": "#000000", "red": "#c12e1f",
    "blue": "#0a2989", "yellow": "#f4ee2a", "gray": "#8e9089", "grey": "#8e9089",
    "bambugreen": "#00ae42", "green": "#00ae42", "orange": "#ff6a13", "pink": "#f55a74",
    "beige": "#e8dbb7", "lightgray": "#d1d3d5", "lightgrey": "#d1d3d5", "brown": "#9d432c",
    "purple": "#5e43b7", "cyan": "#0086d6", "magenta": "#ec008c", "bronze": "#847d48",
    "gold": "#e4bd68", "silver": "#a6a9aa", "darkgray": "#545454", "darkgrey": "#545454",
    "cocoabrown": "#6f5034", "sunfloweryellow": "#fec600", "hotpink": "#f5547c",
    "mistletoegreen": "#3f8e43", "turquoise": "#00b1b7", "brightgreen": "#becf00",
    "indigopurple": "#482960", "bluegray": "#5b6579", "bluegrey": "#5b6579", "cobaltblue": "#0056b8",
    "maroonred": "#9d2235", "ivorywhite": "#f6f3e8", "latte": "#d8c7a8", "lilac": "#a98ec4",
    "skyblue": "#56b7e6", "mandarinorange": "#f59a3c", "charcoal": "#333333",
}
IGNORED_WORDS = {"bambu", "bambulab", "lab", "pla", "petg", "abs", "asa", "pc", "tpu", "basic", "matte", "silk",
                 "tough", "lite", "cf", "gf", "plus", "filament", "hf", "translucent"}

_PARTS = {}          # part name -> {"object": bpy Object, "collection": str, "role": str | None}
_SCENE = None        # the build scene (new_scene_mm); everything builds, exports and renders there
LOG = []             # notes for the agent: which boolean solver ran, what was unioned, ...


# --------------------------------------------------------------------------- #
# Pure helpers (no Blender needed)
# --------------------------------------------------------------------------- #
def cli_args(argv=None):
    """Arguments after `--` (Blender's own come before it), parsed. Without `--` every
    argument after the script name counts, unknown ones (Blender's own flags in a live
    session) are ignored. Returns an argparse Namespace."""
    if argv is None:
        argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    ap = argparse.ArgumentParser(prog="blender_builder", description="3dprint-scout Blender generator runner / STL renderer")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="default: run the generator's build(params)")
    _build_args(b)
    r = sub.add_parser("render", help="render STLs to one PNG grid")
    r.add_argument("stl", nargs="+")
    r.add_argument("-o", "--out", required=True, help="PNG to write")
    r.add_argument("--views", default=",".join(DEFAULT_VIEWS))
    r.add_argument("--size", default="1600x1200")
    r.add_argument("--engine", default="workbench", choices=ENGINE_NAMES)
    r.add_argument("--color", action="append", default=[], help="part=filament name or #rrggbb (repeatable)")
    r.add_argument("--label", help="caption (default: the size in mm)")
    r.add_argument("--overwrite", action="store_true", help="replace an existing PNG (out/ is the working folder)")
    if args and args[0] in ("build", "render"):
        return ap.parse_args(args)
    if "--" in argv:
        ns = b.parse_args(args)
    else:                                   # a live session: Blender's own flags may be in argv
        ns, _unknown = b.parse_known_args(args)
    ns.cmd = "build"
    return ns


def _build_args(p):
    p.add_argument("--params", help="JSON file with the engine parameters (keys starting with _ are dropped)")
    p.add_argument("--out", required=True, help="the only folder the build writes: STLs and the .blend")
    p.add_argument("--only", help="comma list of parts to export (all are built)")
    p.add_argument("--blend", help="path of the .blend: a new file inside --out (default <out>/<generator>.blend, rewritten)")
    p.add_argument("--no-blend", action="store_true", help="do not save a .blend")
    p.add_argument("--scene", default=SCENE_NAME, help="name of the build scene")


def segments_for(width, line_width=LINE_WIDTH):
    """Bevel segments for a fillet of `width` mm: one segment per line width along the quarter
    arc, at least 2 and at most MAX_SEGMENTS (facets finer than a line do not print)."""
    if not (width > 0) or not (line_width > 0):
        raise ValueError("width and line_width must be positive")
    return max(2, min(MAX_SEGMENTS, int(math.ceil(math.pi / 2 * width / line_width))))


def circle_segments(r, chord=0.4):
    """Segments for a circle of radius r so a chord stays under `chord` mm (max 64 floor)."""
    return max(64, int(math.ceil(2 * math.pi * r / chord)))


def hex_rgb(text):
    """'#rrggbb' -> (r, g, b) floats 0..1."""
    t = text.strip().lstrip("#")
    if len(t) != 6 or any(c not in "0123456789abcdefABCDEF" for c in t):
        raise ValueError(f"not a #rrggbb colour: {text!r}")
    return tuple(int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb)


def colour_key(name):
    """'Bambu PLA Basic Jade White' -> 'jadewhite': lower case, brand / material words dropped,
    letters and digits only. Whole words only: 'Light Blue' stays 'lightblue', never 'blue'."""
    words = [w for w in re.split(r"[^0-9a-z]+", str(name).lower()) if w]
    return "".join(w for w in words if w not in IGNORED_WORDS)


def colour_for(name):
    """((r, g, b), warning or None) for a filament name or '#rrggbb'. The table is matched
    exactly after normalising; an unknown name gets neutral grey and a warning (never a
    question to the user)."""
    text = str(name).strip()
    if text.startswith("#"):
        return hex_rgb(text), None
    key = colour_key(text)
    if key in FILAMENTS:
        return hex_rgb(FILAMENTS[key]), None
    return NEUTRAL, f"unknown filament colour {name!r}: neutral grey used ({COLOUR_TABLE_NOTE}; give #rrggbb for an exact one)"


def filament_rgb(name, default=None):
    """(r, g, b) for a known filament name or '#rrggbb'; `default` for an unknown name, or a
    ValueError when no default is given (colour_for never raises on an unknown name)."""
    if name is None:
        if default is None:
            raise ValueError("no colour given")
        return default
    rgb, warning = colour_for(name)
    if warning is None:
        return rgb
    if default is None:
        raise ValueError(f"unknown filament colour {name!r}; give #rrggbb")
    return default


def palette_rgb(i):
    return hex_rgb(PALETTE[i % len(PALETTE)])


def preview_rgb(rgb):
    """The colour as drawn (sRGB): very dark filaments are lifted a little towards grey so the
    shading still shows their edges (black parts read as featureless otherwise). Preview only."""
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    if lum >= 0.2:
        return tuple(rgb)
    return tuple(DARK_LIFT + (1 - DARK_LIFT) * c for c in rgb)


def srgb_to_linear(c):
    """One sRGB channel (0..1, as in #rrggbb) -> the scene-linear value Blender's colour
    properties take. Object colours, material colours and the world colour are all linear;
    an sRGB value put there unconverted renders washed out (orange #ff6a13 came out #ffad4e)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_rgb(rgb):
    return tuple(srgb_to_linear(c) for c in rgb)


def parse_colors(items, names):
    """['body=black', 'lid=#ff0000'] + part names -> ({name: (r, g, b)}, [warnings]); unnamed
    parts take the palette in order, unknown colours neutral grey with a warning. A part
    name that is not rendered raises."""
    out, warnings = {}, []
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--color needs part=colour, got {item!r}")
        part, value = item.split("=", 1)
        if part not in names:
            raise ValueError(f"--color names a part that is not rendered: {part!r} (parts: {list(names)})")
        out[part], warning = colour_for(value)
        if warning:
            warnings.append(f"{part}: {warning}")
    for i, n in enumerate(names):
        out.setdefault(n, palette_rgb(i))
    return out, warnings


def fg_sane(fg, views=None):
    """The G4 verdict on a render's foreground fraction, measured on the rendered views without
    the caption or the grid lines: blank (nothing drawn), no background at all (a black or
    missing world) and, with `views` {view: fraction}, any blank view all fail."""
    if fg <= FG_MIN:
        return False, "blank image: nothing of the part is visible"
    if fg > FG_MAX:
        return False, (f"{fg * 100:.1f}% of the pixels differ from the background: the render has no background "
                       "(black world?), not a usable preview")
    blank = [v for v, f in (views or {}).items() if f <= FG_MIN]
    if blank:
        return False, f"blank view{'s' if len(blank) > 1 else ''} {', '.join(blank)}: nothing of the part is visible there"
    return True, f"{fg * 100:.1f}% of the pixels show the part"


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def view_basis(direction, up):
    """(right, up, forward) unit vectors of a camera placed along `direction` (from the scene
    towards the eye) with world `up`, as preview.py does it."""
    d = _norm(direction)
    f = tuple(-c for c in d)
    r = _cross(f, up)
    if math.sqrt(sum(c * c for c in r)) < 1e-9:
        up = (0.0, 1.0, 0.0) if abs(f[2]) > 0.9 else (0.0, 0.0, 1.0)
        r = _cross(f, up)
    r = _norm(r)
    u = _cross(r, f)
    return r, u, f


def projected_extent(corners, basis):
    """(width, height, centre_x, centre_y) of points projected on a camera basis."""
    r, u, _f = basis
    xs = [sum(p[i] * r[i] for i in range(3)) for p in corners]
    ys = [sum(p[i] * u[i] for i in range(3)) for p in corners]
    return max(xs) - min(xs), max(ys) - min(ys), (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2


def box_corners(lo, hi):
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def grid_layout(n):
    """(columns, rows) of the preview grid, as preview.py lays it out."""
    cols = 2 if n > 1 else 1
    return cols, int(math.ceil(n / cols))


def forbidden_strings(out_dir=None):
    """Byte strings that must not appear in a saved .blend: this machine's home folder, the
    working folders, the temp folder. Short or root-like paths are skipped."""
    cands = [os.path.expanduser("~"), os.getcwd(), out_dir, os.environ.get("TEMP"), os.environ.get("TMPDIR")]
    main = sys.modules.get("__main__")
    if main is not None and getattr(main, "__file__", None):
        cands.append(os.path.dirname(os.path.abspath(main.__file__)))
    out = []
    for c in cands:
        if c and len(c.rstrip("/\\")) >= 5 and os.path.isabs(c):
            s = os.path.abspath(c).rstrip("/\\")
            out.append(s.encode("utf-8"))
            if os.sep == "\\":
                out.append(s.replace("\\", "/").encode("utf-8"))
    return sorted(set(out), key=len, reverse=True)


def find_forbidden(data, forbidden):
    """The forbidden strings found in `data` (decoded for the message); case-insensitive on
    Windows, where paths are."""
    if os.sep == "\\":
        data = data.lower()
        forbidden = [f.lower() for f in forbidden]
    return [f.decode("utf-8", "replace") for f in forbidden if f in data]


def neutral_filepath(path):
    """A packed data-block keeps only its base name, relative: '//<name>'."""
    return "//" + os.path.basename(path.replace("\\", "/")) if path else path


def looks_like_path(text):
    """True for an absolute path of any platform ('/home/x', 'C:\\\\x', '\\\\\\\\server\\\\x', '~/x')."""
    if not isinstance(text, str) or len(text) < 2:
        return False
    return bool(re.match(r"^(/|~[/\\]|[A-Za-z]:[\\/]|\\\\)", text))


def scrub_text(text):
    """An absolute path becomes its base name; any other string is left as it is."""
    return os.path.basename(text.rstrip("/\\").replace("\\", "/")) if looks_like_path(text) else text


def prop_value(v):
    """A params.json value as a custom-property value: numbers, bools and lists of numbers as
    they are, strings with absolute paths reduced to their base name, anything else as a JSON
    string (scrubbed the same way)."""
    if isinstance(v, bool) or isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        return scrub_text(v)
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return [float(x) for x in v]
    return json.dumps(_scrub(v))


def _scrub(v):
    if isinstance(v, str):
        return scrub_text(v)
    if isinstance(v, dict):
        return {k: _scrub(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub(x) for x in v]
    return v


def summary(parts, **extra):
    """JSON text printed after a build: one line, prefixed with @@3DPS for build.py."""
    doc = {"schema": SCHEMA, "parts": parts}
    doc.update(extra)
    return "@@3DPS " + json.dumps(doc, sort_keys=True)


def boolean_solver(version=None):
    """'MANIFOLD' from Blender 4.5 on (the floor of this module), 'EXACT' before: for the
    record, and for an explicit `solver=` override."""
    if version is None:
        if bpy is None:
            return "MANIFOLD"
        version = bpy.app.version
    return "MANIFOLD" if tuple(version[:2]) >= MIN_VERSION else "EXACT"


def _same_file(a, b):
    """True when two paths name the same file (realpath, case-folded on Windows)."""
    if not a or not b:
        return False
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _inside(path, folder):
    """True when `path` lies inside `folder` (realpath, case-folded on Windows)."""
    p = os.path.normcase(os.path.realpath(path))
    f = os.path.normcase(os.path.realpath(folder))
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
def require_blender():
    if bpy is None:
        raise RuntimeError("blender_builder runs inside Blender (the blender binary or the bpy module)")
    if tuple(bpy.app.version[:2]) < MIN_VERSION:
        raise RuntimeError(f"Blender {bpy.app.version_string} is too old: 3dprint-scout needs Blender 4.5 LTS or newer "
                           "(the Manifold boolean solver; text and renders are tested from 4.5 on). Install a newer "
                           "Blender, or pip install bpy>=4.5")


def session_info():
    """A harmless read for Phase 0: version, mode and whether the open file has unsaved work."""
    require_blender()
    return {"blender": bpy.app.version_string, "version": list(bpy.app.version), "background": bpy.app.background,
            "filepath": bpy.data.filepath, "is_dirty": bpy.data.is_dirty, "python": sys.version.split()[0],
            "binary": bool(bpy.app.binary_path), "manifold_boolean": True}


def _tagged(coll):
    return [x for x in coll if x is not None and x.get(TAG)]


def new_scene_mm(name=SCENE_NAME):
    """The build scene, at 1 unit = 1 mm, next to whatever file is open: created on the first
    run, reused on the next with only this module's own objects removed. The open file, its
    scenes and the user's window are never touched; nothing is reset."""
    global _SCENE
    require_blender()
    _PARTS.clear()
    LOG.clear()
    sc = bpy.data.scenes.get(name)
    if sc is not None and not sc.get(TAG):
        sc = None                                       # the user's own scene of that name: leave it
    if sc is None:
        sc = bpy.data.scenes.new(name)
    for obj in _tagged(list(sc.objects)):
        data = obj.data
        bpy.data.objects.remove(obj)
        _remove_data(data)
    for col in _tagged(list(bpy.data.collections)):
        if not col.objects and not col.children:
            bpy.data.collections.remove(col)
    us = sc.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"
    sc.render.filepath = "//"
    sc[TAG] = True
    world = sc.world if sc.world is not None and sc.world.get(TAG) else None
    if world is None:
        world = bpy.data.worlds.new(name)
        world[TAG] = True
        sc.world = world
    world.color = linear_rgb(BACKGROUND)                # Workbench renders need a world: black otherwise (4.5)
    _SCENE = sc
    return sc


def _data_collection(data):
    """The bpy.data collection a data-block belongs to (for removing orphans)."""
    name = type(data).__name__
    return {"Mesh": "meshes", "Curve": "curves", "TextCurve": "curves", "Camera": "cameras",
            "Light": "lights", "SunLight": "lights", "PointLight": "lights"}.get(name, "meshes")


def _remove_data(data):
    """Remove an orphaned data-block of this module's own; the user's data is never removed."""
    if data is not None and data.users == 0 and data.get(TAG):
        getattr(bpy.data, _data_collection(data)).remove(data)


def scene():
    """The build scene: the one new_scene_mm made, else the context's."""
    if _SCENE is not None:
        try:
            _SCENE.name                                 # raises once the scene is gone
            return _SCENE
        except ReferenceError:
            pass
    return bpy.context.scene


def _view_layer():
    return scene().view_layers[0]


def _ctx():
    """A context on the build scene for operators and the depsgraph: a temp_override of the
    scene and its view layer (never the window, which is the user's)."""
    sc = scene()
    if bpy.context.scene == sc:
        return contextlib.nullcontext()
    return bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0])


def _link(obj, collection=None):
    col = collection or scene().collection
    if obj.name not in col.objects:
        col.objects.link(obj)
    obj[TAG] = True
    return obj


def _deselect_all():
    vl = _view_layer()
    for o in bpy.data.objects:
        try:
            o.select_set(False, view_layer=vl)
        except RuntimeError:            # not in this view layer
            pass


# --------------------------------------------------------------------------- #
# Meshes
# --------------------------------------------------------------------------- #
def mesh_object(name, bm, collection=None):
    """An object from a bmesh (consumed), linked into the build scene and tagged."""
    require_blender()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me[TAG] = True
    obj = bpy.data.objects.new(name, me)
    return _link(obj, collection)


def nonmanifold_edges(obj):
    """Edges of the object's mesh that are not shared by exactly two faces (evaluated: modifiers
    applied)."""
    me = evaluated_mesh(obj)
    bm = bmesh.new()
    bm.from_mesh(me)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    bpy.data.meshes.remove(me)
    return n


def degenerate_triangles(me, area=1e-9):
    """Triangles of a mesh (as the STL exporter will cut them) with an area under `area` mm2
    or two welded vertices: what validate.py's M3 counts."""
    import numpy as np                      # bundled with every Blender and the bpy wheel
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    if not n:
        return 0
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    idx = np.empty(n * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", idx)
    a, b, c = (co[idx.reshape(-1, 3)[:, k]] for k in range(3))
    areas = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    short = np.minimum(np.minimum(np.linalg.norm(a - b, axis=1), np.linalg.norm(b - c, axis=1)),
                       np.linalg.norm(a - c, axis=1))
    return int(np.count_nonzero((areas < area) | (short < WELD)))


def evaluated_mesh(obj):
    """A new mesh data-block with the object's modifiers applied (caller removes it)."""
    with _ctx():
        dg = bpy.context.evaluated_depsgraph_get()
        return bpy.data.meshes.new_from_object(obj.evaluated_get(dg), depsgraph=dg)


def apply_modifiers(obj):
    """Replace the object's mesh by the evaluated one and drop its modifiers."""
    me = evaluated_mesh(obj)
    me[TAG] = True
    old = obj.data
    name = old.name
    obj.data = me
    obj.modifiers.clear()
    _remove_data(old)
    me.name = name
    return obj


def box(size, name="box", collection=None):
    """Axis-aligned box of size [x, y, z] mm with its corner at the origin, bottom on the bed."""
    require_blender()
    sx, sy, sz = (float(v) for v in size)
    if min(sx, sy, sz) <= 0:
        raise ValueError(f"box size must be positive: {size}")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(sx / 2, sy / 2, sz / 2), verts=bm.verts)
    return mesh_object(name, bm, collection)


def cylinder(r, h, segments=None, name="cylinder", collection=None):
    """Cylinder on the bed, axis Z through the origin."""
    require_blender()
    if r <= 0 or h <= 0:
        raise ValueError("cylinder needs positive r and h")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments or circle_segments(r),
                          radius1=r, radius2=r, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    return mesh_object(name, bm, collection)


def prism(outline, height, name="prism", collection=None, z0=0.0):
    """A closed 2D outline [(x, y), ...] in mm extruded from z0 to z0 + height (caps are
    n-gons; the exporter triangulates them)."""
    require_blender()
    pts = [tuple(map(float, p[:2])) for p in outline]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 3:
        raise ValueError("an outline needs at least three points")
    if height <= 0:
        raise ValueError("prism height must be positive")
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z0)) for x, y in pts]
    face = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, height), verts=top)
    return mesh_object(name, bm, collection)


def ring(r_in, r_out, h, segments=None, name="ring", collection=None, z0=0.0):
    """An annulus (r_in < r_out) extruded from z0 to z0 + h: a groove or rim cutter."""
    require_blender()
    if not (0 < r_in < r_out) or h <= 0:
        raise ValueError("ring needs 0 < r_in < r_out and h > 0")
    bm = bmesh.new()
    segs = segments or circle_segments(r_out)
    bmesh.ops.create_circle(bm, cap_ends=False, radius=r_in, segments=segs)
    bmesh.ops.create_circle(bm, cap_ends=False, radius=r_out, segments=segs)
    bmesh.ops.bridge_loops(bm, edges=bm.edges[:])
    res = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    top = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, h), verts=top)
    bmesh.ops.translate(bm, vec=(0, 0, z0), verts=bm.verts)
    return mesh_object(name, bm, collection)


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def boolean(target, tool, operation="DIFFERENCE", apply=True, solver=None):
    """target = target (op) tool with the Boolean modifier, Manifold solver (closed, manifold
    input, which is checked first; `solver="EXACT"` forces Blender's older solver). With apply
    the result replaces the target's mesh and the tool is removed; otherwise the modifier stays
    live and the tool is hidden. Raises when an input or the result is not manifold."""
    require_blender()
    ops = {"DIFFERENCE": "DIFFERENCE", "UNION": "UNION", "INTERSECT": "INTERSECT",
           "difference": "DIFFERENCE", "union": "UNION", "intersect": "INTERSECT", "cut": "DIFFERENCE", "join": "UNION"}
    if operation not in ops:
        raise ValueError(f"operation must be one of difference, union, intersect; got {operation!r}")
    for what, obj in (("target", target), ("tool", tool)):
        n = nonmanifold_edges(obj)
        if n:
            raise ValueError(f"boolean {ops[operation].lower()}: {what} '{obj.name}' has {n} non-manifold edges; "
                             "the solver needs closed input, fix the shape that produced them")
    solver = solver or boolean_solver()
    mod = target.modifiers.new(f"bool_{ops[operation].lower()}", "BOOLEAN")
    mod.operation = ops[operation]
    mod.object = tool
    mod.solver = solver
    LOG.append(f"boolean {ops[operation].lower()} '{tool.name}' from '{target.name}': solver {solver}")
    if apply:
        apply_modifiers(target)
        _remove_object(tool)
        n = nonmanifold_edges(target)
        if n:
            raise ValueError(f"boolean {ops[operation].lower()} with solver {solver} left {n} non-manifold edges on "
                             f"'{target.name}': the tool probably touches the target on a face; overshoot it by 0.01-0.1 mm")
        d = degenerate_triangles(target.data)
        if d:
            raise ValueError(f"boolean {ops[operation].lower()} with solver {solver} left {d} zero-area triangles on "
                             f"'{target.name}' (the STL would fail M3, and M1 once they are dropped): the cut crosses a "
                             "fan of thin triangles (a pole or a cap) or grazes an edge. Give the face ring topology "
                             "where it is cut, build a round hole on the axis into the profile (a revolve), or move "
                             "the cut off the pole")
    else:
        tool.hide_viewport = True
        tool.hide_render = True
    return target


def join(target, *tools):
    """Union of the target with every tool (each a boolean UNION, applied)."""
    for t in tools:
        boolean(target, t, "UNION")
    return target


def _remove_object(obj):
    data = obj.data
    bpy.data.objects.remove(obj)
    _remove_data(data)
    _view_layer().update()


def _edge_weights(me, angle_deg, bed):
    bm = bmesh.new()
    bm.from_mesh(me)
    zmin = min((v.co.z for v in bm.verts), default=0.0)
    lim = math.radians(angle_deg)
    weights = []
    for e in bm.edges:
        on_bed = all(abs(v.co.z - zmin) < 1e-5 for v in e.verts)
        ang = e.calc_face_angle(0.0)
        weights.append(1.0 if (ang >= lim and (bed or not on_bed)) else 0.0)
    bm.free()
    return weights


def bevel(obj, width, segments=None, angle=30.0, bed=False, profile=0.5, apply=True):
    """Round (segments > 1) or chamfer (segments = 1) every edge whose faces meet at `angle`
    degrees or more, except edges on the bed (bed=True includes them; the bed edge should get
    `bed_chamfer`, design.md). Segments default to one per line width along the arc. Fillets
    come before cuts and before the bed chamfer: a bevel that overlaps a feature closer than
    its width is clamped into slivers, and this call refuses such a result instead of welding it."""
    require_blender()
    if width <= 0:
        raise ValueError("bevel width must be positive")
    segments = segments or segments_for(width)
    me = obj.data
    weights = _edge_weights(me, angle, bed)
    if not any(weights):
        raise ValueError(f"bevel on '{obj.name}': no edge meets the {angle} deg limit off the bed")
    attr = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    attr.data.foreach_set("value", weights)
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.profile = profile
    mod.limit_method = "WEIGHT"
    mod.use_clamp_overlap = True
    mod.miter_outer = "MITER_ARC"
    if apply:
        apply_modifiers(obj)
        bad = degenerate_triangles(obj.data)
        if bad:
            raise ValueError(f"bevel of {width} mm on '{obj.name}' made {bad} zero-area triangles: the width overlaps "
                             "another edge or feature; reduce it, or bevel before the cut / chamfer that is in its way")
    LOG.append(f"bevel '{obj.name}': width {width} mm, {segments} segments, {int(sum(weights))} edges")
    return obj


def chamfer(obj, width, angle=30.0, bed=False, apply=True):
    """A 45 degree chamfer of `width` on every qualifying edge (bevel with one segment)."""
    return bevel(obj, width, segments=1, angle=angle, bed=bed, apply=apply)


def bed_chamfer(obj, height=0.4, run=None):
    """Chamfer the edges that touch the bed (design.md: a chamfer, never a fillet, hides the
    elephant foot), cut into the body: its bottom faces are inset by `run` and the original
    bottom ring is lifted by `height`, so the overall size does not change. `run` defaults to
    0.9 x height: the band is steeper than 45 degrees and P2 never counts it. Works on any
    bottom outline; applied at once (modifiers are applied first)."""
    require_blender()
    if height <= 0:
        raise ValueError("bed chamfer height must be positive")
    run = height * BED_CHAMFER_RUN if run is None else run
    if run <= 0 or run > height:
        raise ValueError("bed chamfer run must be positive and at most the height (steeper than 45 deg)")
    if obj.modifiers:
        apply_modifiers(obj)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    zmin = min(v.co.z for v in bm.verts)
    bottom = [f for f in bm.faces if f.normal.z < -0.999 and all(abs(v.co.z - zmin) < 1e-5 for v in f.verts)]
    if not bottom:
        bm.free()
        raise ValueError(f"bed chamfer on '{obj.name}': no flat face on the bed (z = {zmin:.3f})")
    bmesh.ops.inset_region(bm, faces=bottom, thickness=run, depth=0.0, use_even_offset=True)
    # The inset keeps the original vertices on the shrunk bottom face and adds a new ring on the
    # old outline: that ring moves up and becomes the top edge of the chamfer band.
    inner = {v for f in bottom for v in f.verts}
    rim = [v for v in bm.verts if abs(v.co.z - zmin) < 1e-5 and v not in inner]
    bmesh.ops.translate(bm, vec=(0, 0, height), verts=rim)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    bad = degenerate_triangles(me)
    if bad:
        raise ValueError(f"bed chamfer on '{obj.name}' made {bad} zero-area triangles: the run is wider than a bottom feature")
    LOG.append(f"bed chamfer '{obj.name}': {height} mm high, {run:.3f} mm run")
    return obj


def _cap_ratio(font, resolution):
    """Height of a capital H at size 1 for this font (Blender's size is the em size)."""
    cu = bpy.data.curves.new("_cap", "FONT")
    cu.body = "H"
    cu.size = 1.0
    cu.resolution_u = resolution
    if font is not None:
        cu.font = font
    ob = bpy.data.objects.new("_cap", cu)
    scene().collection.objects.link(ob)
    me = evaluated_mesh(ob)
    ys = [v.co.y for v in me.vertices]
    ratio = (max(ys) - min(ys)) if ys else 0.0
    bpy.data.meshes.remove(me)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    if ratio <= 0:
        raise ValueError("font gives no outline for 'H'")
    return ratio


def load_font(path):
    """A font file loaded and packed into the .blend, its path reduced to its base name."""
    require_blender()
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    font = bpy.data.fonts.load(os.path.abspath(path))
    font.pack()
    font.filepath = neutral_filepath(path)
    font[TAG] = True
    return font


def _components(bm):
    """Connected vertex groups of a bmesh (by shared edges)."""
    seen, groups = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, group = [v], []
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            group.append(cur)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        groups.append(group)
    return groups


def _xy_bbox(verts):
    xs = [v.co.x for v in verts]
    ys = [v.co.y for v in verts]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap(a, b, tol=1e-4):
    return a[0] <= b[2] + tol and b[0] <= a[2] + tol and a[1] <= b[3] + tol and b[1] <= a[3] + tol


def _contains(outer, inner, tol=1e-4):
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1]
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _bbox_area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _welded_nonmanifold(obj):
    """Non-manifold edges after welding vertices the way validate.py does (two bodies that
    only kiss along an edge count as one edge with four faces)."""
    me = evaluated_mesh(obj)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    bpy.data.meshes.remove(me)
    return n


def _text_mesh(string, size, depth, fnt, resolution, align, name, spacing, collection):
    """One welded mesh object for `string` at character spacing `spacing`, glyphs that touch
    unioned. Returns (object, glyph pieces, touching pairs)."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = string
    cu.size = size
    cu.extrude = depth / 2
    cu.resolution_u = resolution
    cu.align_x = align.upper()
    cu.align_y = "BOTTOM_BASELINE"
    cu.space_character = spacing
    if fnt is not None:
        cu.font = fnt
    src = bpy.data.objects.new(name, cu)
    scene().collection.objects.link(src)
    me = evaluated_mesh(src)
    bpy.data.objects.remove(src)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    bmesh.ops.translate(bm, vec=(0, 0, depth / 2), verts=bm.verts)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    # The converted text is not welded: each glyph gives a front cap, a back cap and one side
    # strip per contour. Caps and the outer strip share the glyph's XY box; the strip of a hole
    # (the inside of an A or O) has a box inside it. Those pieces are one glyph: weld inside a
    # glyph only, never across glyphs (welding "AA" as a whole merges the touching letters).
    comps = sorted(_components(bm), key=lambda c: -_bbox_area(_xy_bbox(c)))
    glyphs = []                                            # [(outer box, verts)]
    for comp in comps:
        box = _xy_bbox(comp)
        for entry in glyphs:
            if _contains(entry[0], box):
                entry[1].extend(comp)
                break
        else:
            glyphs.append((box, list(comp)))
    for _box, verts in glyphs:
        bmesh.ops.remove_doubles(bm, verts=verts, dist=WELD)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    pieces = _components(bm)
    boxes = [_xy_bbox(p) for p in pieces]
    touching = [(i, j) for i in range(len(pieces)) for j in range(i + 1, len(pieces)) if _overlap(boxes[i], boxes[j])]
    if not touching:
        obj = mesh_object(name, bm, collection)
        n = nonmanifold_edges(obj)
        if n:
            raise ValueError(f"text {string!r}: {n} non-manifold edges after welding each glyph; a glyph outline of "
                             "this font self-intersects, try another font or a lower resolution")
        return obj, pieces, touching
    # Letters that touch share outline geometry: welded together they would be an open mesh, so
    # every piece becomes its own object and the pieces are unioned (Manifold handles contact).
    objs = []
    for i, verts in enumerate(pieces):
        part_bm = bmesh.new()
        lookup = {v.index: part_bm.verts.new(v.co) for v in verts}
        faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            part_bm.faces.new([lookup[v.index] for v in f.verts])
        objs.append(mesh_object(f"{name}_glyph{i}", part_bm, collection))
    bm.free()
    for i, o in enumerate(objs):
        n = nonmanifold_edges(o)
        if n:
            raise ValueError(f"text {string!r}: glyph piece {i} has {n} non-manifold edges after welding; a glyph "
                             "outline of this font self-intersects, try another font or a lower resolution")
    base = objs[0]
    for o in objs[1:]:
        boolean(base, o, "union")
    base.name = name
    base.data.name = name
    return base, pieces, touching


def text(string, height, depth, font=None, name="text", align="CENTER", resolution=6, collection=None):
    """Text as one mesh object: cap height `height` mm, `depth` mm tall standing on z = 0,
    centred on the origin (align CENTER | LEFT | RIGHT). Blender's built-in font, or a font
    file (packed into the .blend). Every glyph is welded on its own (welding the whole string
    would merge touching letters such as "AA" into an open mesh); glyphs whose outlines touch
    are unioned with the Manifold solver, and letters that only kiss along an edge (the feet of
    "AA", the tops of "VV") get the character spacing tightened by 1 % steps, 5 % at most, until
    they overlap and the union is one closed body; the rest stay separate bodies. One body per
    separate letter: emboss them onto a face with `boolean(face_part, text_obj, "union")`, or
    give the part's `_parts` entry `shells` (parts.md)."""
    require_blender()
    if not string:
        raise ValueError("empty text")
    if height <= 0 or depth <= 0:
        raise ValueError("text needs a positive height and depth")
    fnt = load_font(font) if isinstance(font, str) else font
    ratio = _cap_ratio(fnt, resolution)
    size = height / ratio
    spacing = 1.0
    for attempt in range(6):
        obj, pieces, touching = _text_mesh(string, size, depth, fnt, resolution, align, name, spacing, collection)
        bad = _welded_nonmanifold(obj) if touching else 0
        if not bad:
            break
        _remove_object(obj)
        spacing = round(spacing - 0.01, 2)
    else:
        raise ValueError(f"text {string!r}: letters touch only along an edge or a point, and even at {spacing + 0.01:.2f} "
                         "character spacing their union is not one closed body; put the text on a plate "
                         "(union with it) or choose a font or spacing where the letters either overlap or stand apart")
    note = (f"text {string!r}: cap height {height} mm (font size {size:.3f}), depth {depth} mm, "
            f"{len(pieces)} glyph pieces, font {'built-in' if fnt is None else fnt.name}")
    if touching:
        note += f", {len(touching)} touching pair(s) unioned"
        if spacing < 1.0:
            note += f" after tightening the character spacing to {spacing:.2f} (letters that only kissed along an edge)"
    else:
        note += ", separate bodies"
    LOG.append(note)
    return obj

# --------------------------------------------------------------------------- #
# Parts, parameters, export, save
# --------------------------------------------------------------------------- #
def part(obj, name, object=None, role=None):
    """Register `obj` as the part `name` (one STL named after it) in the collection of its
    object (`object`, default the part itself; parts of one object share a collection). A
    collection is reused only when this module made it; a user's collection of the same name
    is left alone and the new one takes Blender's `.001` suffix."""
    require_blender()
    if not name or not all(c.isalnum() or c in "_-" for c in name):
        raise ValueError(f"part name {name!r}: letters, digits, _ and - only (it becomes a file name)")
    if role is not None and role not in ("fused", "free"):
        raise ValueError(f"part '{name}': role must be fused or free, got {role!r}")
    if name in _PARTS and _PARTS[name]["object"] is not obj:
        raise ValueError(f"part '{name}' registered twice")
    # Only an object this build made may become a part: one linked into another scene or into a
    # collection the build does not own is the user's, and is never moved, renamed or tagged.
    sc = scene()
    elsewhere = [s.name for s in obj.users_scene if s != sc]
    foreign = [c.name for c in obj.users_collection if c != sc.collection and not c.get(TAG)]
    if obj.library is not None or elsewhere or foreign:
        where = ", ".join(elsewhere + foreign) or "a linked library"
        raise ValueError(f"part '{name}': object '{obj.name}' is not the build's own (it is in {where}); "
                         "build parts from new objects, the user's data is never moved or tagged")
    group = object or name
    col = None
    for cand in bpy.data.collections:
        if cand.get(TAG) and cand.get("object") == group and cand.name in scene().collection.children:
            col = cand
            break
    if col is None:
        col = bpy.data.collections.new(group)
        col[TAG] = True
        col["object"] = group
    if col.name not in scene().collection.children:
        scene().collection.children.link(col)
    if obj.name not in col.objects:
        col.objects.link(obj)
    for other in list(obj.users_collection):
        if other is not col:
            other.objects.unlink(obj)
    obj.name = name
    obj[TAG] = True
    obj["part"] = name
    obj["object"] = group
    if role:
        obj["role"] = role
    _PARTS[name] = {"object": obj, "collection": col.name, "group": group, "role": role}
    return obj


def params_to_props(params, name="PARAMETERS"):
    """The parameters as custom properties on an empty, for hand edits and the sidebar. A
    string parameter that is an absolute path is stored as its base name."""
    require_blender()
    empty = None
    for cand in bpy.data.objects:
        if cand.get(TAG) and cand.get("part") is None and cand.type == "EMPTY" and cand.name.startswith(name):
            empty = cand
            break
    if empty is None:
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 5.0
        _link(empty)
    for k, v in params.items():
        if str(k).startswith("_"):
            continue
        empty[str(k)] = prop_value(v)
    empty["_note"] = "parameters of the generator script, which is the source of truth; edit the script and rebuild"
    return empty


def check_props(objects=None):
    """Refuse string custom properties that hold an absolute path, naming object and property:
    they would be written into the .blend. Run before anything is exported."""
    require_blender()
    for obj in objects if objects is not None else _tagged(list(bpy.data.objects)):
        for key in obj.keys():
            value = obj.get(key)
            if isinstance(value, str) and looks_like_path(value):
                raise ValueError(f"custom property {key!r} on '{obj.name}' holds a path ({value!r}); store a name, "
                                 "not a path of this machine")


def world_bbox(obj):
    """(min, max, triangles) of the evaluated object in world coordinates (mm)."""
    me = evaluated_mesh(obj)
    pts = [obj.matrix_world @ v.co for v in me.vertices]
    tris = len(me.loop_triangles)
    bpy.data.meshes.remove(me)
    if not pts:
        raise ValueError(f"'{obj.name}' has no vertices")
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi, tris


def export_parts(out, names=None):
    """One binary STL per registered part into `out` (modifiers applied, 1 unit = 1 mm, scene
    unit off, axes unchanged). Returns the part list with boxes in mm, triangles and bytes."""
    require_blender()
    if not _PARTS:
        raise ValueError("no parts registered: call part(obj, name) for every body to export")
    wanted = list(names) if names else list(_PARTS)
    missing = [n for n in wanted if n not in _PARTS]
    if missing:
        raise ValueError(f"no part named {missing}; parts are {list(_PARTS)}")
    os.makedirs(out, exist_ok=True)
    info = []
    for n in wanted:
        obj = _PARTS[n]["object"]
        path = os.path.join(out, n + ".stl")
        _deselect_all()
        obj.select_set(True, view_layer=_view_layer())
        _view_layer().objects.active = obj
        t0 = time.time()
        with _ctx():
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True, global_scale=1.0,
                                  use_scene_unit=False, ascii_format=False, forward_axis="Y", up_axis="Z", check_existing=False)
        lo, hi, tris = world_bbox(obj)
        entry = {"name": n, "stl": path, "bbox_min_mm": [round(v, 4) for v in lo],
                 "bbox_mm": [round(h - l, 4) for l, h in zip(lo, hi)], "triangles": tris,
                 "bytes": os.path.getsize(path), "seconds": round(time.time() - t0, 3),
                 "object": _PARTS[n]["group"], "role": _PARTS[n]["role"]}
        nm = nonmanifold_edges(obj)
        if nm:
            entry["warning"] = f"{nm} non-manifold edges (validate.py will fail M1)"
        info.append(entry)
    return info


def _written_ids(sc):
    """The build scene and this module's own data-blocks; every object in the scene must be the
    module's (the user's data is never written)."""
    for obj in sc.objects:
        if not obj.get(TAG):
            raise ValueError(f"object '{obj.name}' in the build scene is not the build's own; nothing of it is written, "
                             "move it to another scene")
    ids = {sc}
    if sc.world is not None and sc.world.get(TAG):
        ids.add(sc.world)
    for col in bpy.data.collections:
        if col.get(TAG) and col.name in sc.collection.children:
            for obj in col.all_objects:
                if not obj.get(TAG):
                    raise ValueError(f"object '{obj.name}' sits in the build collection '{col.name}' but is not the "
                                     "build's own; nothing of it is written, move it out")
            ids.add(col)
    for obj in sc.objects:
        ids.add(obj)
        if obj.data is not None:
            ids.add(obj.data)
    for f in bpy.data.fonts:
        if f.get(TAG):
            ids.add(f)
    return ids


def save_blend(path, overwrite=False, out_dir=None):
    """Write the build scene (its objects, meshes, collections, world, packed fonts) to a new
    .blend without UI, preferences or window state, compressed. Refuses the file open in
    Blender, an existing path (unless overwrite: only for the working copy in out/) and any
    data-block that still points at an absolute path; packed fonts and images keep only their
    base name. The file is written uncompressed to a temporary twin first and scanned for this
    machine's folders: a hit removes that twin (the only file this call created) and raises,
    the destination is never touched."""
    require_blender()
    path = os.path.abspath(path)
    if _same_file(path, bpy.data.filepath):
        raise ValueError(f"refusing to write over the file open in Blender ({os.path.basename(path)}); save_blend writes new files only")
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"{path} already exists; choose a new name (never overwrite a deliverable)")
    sc = scene()
    sc.render.filepath = "//"
    sc.camera = None
    check_props(_tagged(list(sc.objects)))
    ids = _written_ids(sc)
    # Only this module's own fonts and images are packed (never the user's whole file, which
    # bpy.ops.file.pack_all would touch); a data-block that still points outside is refused.
    for item in list(bpy.data.fonts) + list(bpy.data.images):
        if item not in ids and not item.get(TAG):
            continue
        if item.filepath and item.filepath != "<builtin>" and getattr(item, "packed_file", None) is None \
                and getattr(item, "source", "FILE") not in ("VIEWER", "GENERATED"):
            item.pack()
        if getattr(item, "packed_file", None) is not None:
            item.filepath = neutral_filepath(item.filepath)
        elif item.filepath and not item.filepath.startswith("//") and item.filepath != "<builtin>" \
                and getattr(item, "source", "FILE") not in ("VIEWER", "GENERATED"):
            raise ValueError(f"{type(item).__name__} '{item.name}' points at {item.filepath!r}: pack it or drop it "
                             "(no absolute path may enter the .blend)")
    linked = [i.name for i in ids if getattr(i, "library", None) is not None]
    if linked:
        raise ValueError(f"{linked} are linked from another .blend file; a generated .blend must stand alone")
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, twin = tempfile.mkstemp(prefix=".scan-", suffix=".blend", dir=folder)
    os.close(fd)
    try:
        bpy.data.libraries.write(twin, ids, path_remap="RELATIVE_ALL", fake_user=False, compress=False)
        with open(twin, "rb") as f:
            data = f.read()
        hits = find_forbidden(data, forbidden_strings(out_dir))
        if hits:
            raise ValueError(f"the .blend would hold a path of this machine ({hits[0]!r}); nothing was written")
        fd, final = tempfile.mkstemp(prefix=".new-", suffix=".blend", dir=folder)
        os.close(fd)
        try:
            bpy.data.libraries.write(final, ids, path_remap="RELATIVE_ALL", fake_user=False, compress=True)
            os.replace(final, path)
        finally:
            if os.path.exists(final):
                os.remove(final)
    finally:
        if os.path.exists(twin):
            os.remove(twin)
    LOG.append(f"saved {os.path.basename(path)} ({os.path.getsize(path)} bytes, compressed)")
    return path


# --------------------------------------------------------------------------- #
# Renders
# --------------------------------------------------------------------------- #
def engine_id(engine):
    """Blender's identifier for a render engine name: EEVEE is BLENDER_EEVEE_NEXT in 4.x and
    BLENDER_EEVEE in 5.x, read from the enum."""
    if engine not in ENGINE_NAMES:
        raise ValueError(f"engine must be one of {ENGINE_NAMES}")
    if engine == "workbench":
        return "BLENDER_WORKBENCH"
    if engine == "cycles":
        return "CYCLES"
    ids = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    for cand in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if cand in ids:
            return cand
    raise ValueError(f"no EEVEE engine in this Blender (engines: {ids})")


def _camera_for(view, lo, hi, scale, aspect):
    """An orthographic camera for one view: its X, Y, Z axes are the view basis (right, up,
    towards the eye), so every view matches preview.py's; placed well outside the scene."""
    r, u, f = view_basis(*VIEWS[view])
    centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
    extent = max(hi[i] - lo[i] for i in range(3)) + 1.0
    cam_data = bpy.data.cameras.new("_render_cam")
    cam_data[TAG] = True
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = scale
    cam_data.sensor_fit = "HORIZONTAL" if aspect >= 1 else "VERTICAL"
    cam_data.clip_start = 0.01
    cam_data.clip_end = extent * 10
    cam = bpy.data.objects.new("_render_cam", cam_data)
    cam[TAG] = True
    scene().collection.objects.link(cam)
    loc = [centre[i] - f[i] * extent * 3 for i in range(3)]
    cam.matrix_world = mathutils.Matrix((
        (r[0], u[0], -f[0], loc[0]), (r[1], u[1], -f[1], loc[1]), (r[2], u[2], -f[2], loc[2]), (0, 0, 0, 1)))
    return cam


def _label(cam, text_, scale, aspect, materials):
    """A caption in the lower left of the camera frame, parented to the camera."""
    cu = bpy.data.curves.new("_render_label", "FONT")
    cu[TAG] = True
    cu.body = text_
    cu.size = scale * 0.035
    cu.align_x = "LEFT"
    ob = bpy.data.objects.new("_render_label", cu)
    ob[TAG] = True
    scene().collection.objects.link(ob)
    ob.parent = cam
    w = scale if aspect >= 1 else scale * aspect
    h = scale / aspect if aspect >= 1 else scale
    ob.location = (-w / 2 + scale * 0.02, -h / 2 + scale * 0.02, -1.0)
    ob.color = (*linear_rgb(INK), 1.0)
    mat = bpy.data.materials.new("_render_label")
    mat.diffuse_color = (*linear_rgb(INK), 1.0)
    mat.use_nodes = False
    cu.materials.append(mat)
    materials.append(mat)
    return ob


def _label_box(lab, scale, aspect, tw, th, pad=2):
    """The caption's pixel rectangle (x0, y0, x1, y1) in a tile, bottom-up like Blender's pixel
    buffer, so the blank check leaves it out. The caption sits in the camera's frame (parented,
    no rotation), so its laid-out bounds map straight to pixels; if they are not there yet, the
    whole bottom band up to the caption's top is left out instead."""
    w = scale if aspect >= 1 else scale * aspect
    h = scale / aspect if aspect >= 1 else scale
    xs = [lab.location.x + c[0] for c in lab.bound_box]
    ys = [lab.location.y + c[1] for c in lab.bound_box]
    if max(xs) - min(xs) <= 0 or max(ys) - min(ys) <= 0:
        xs, ys = [-w / 2, w / 2], [-h / 2, lab.location.y + 2 * lab.data.size]
    x0 = max(0, int(math.floor((min(xs) + w / 2) / w * tw)) - pad)
    x1 = min(tw, int(math.ceil((max(xs) + w / 2) / w * tw)) + pad)
    y0 = max(0, int(math.floor((min(ys) + h / 2) / h * th)) - pad)
    y1 = min(th, int(math.ceil((max(ys) + h / 2) / h * th)) + pad)
    return x0, y0, x1, y1


def _colour_objects(objects, colors, materials):
    """Object colour (Workbench) and a flat material (EEVEE / Cycles) per object, dark colours
    lifted for the preview; returns what to undo: [(mesh, previous material)]."""
    undo = []
    for obj in objects:
        rgb = linear_rgb(preview_rgb(colors.get(obj.get("part") or obj.name) or colors.get(obj.name) or palette_rgb(0)))
        obj.color = (*rgb, 1.0)
        mat = bpy.data.materials.new("_render_" + obj.name)
        mat.diffuse_color = (*rgb, 1.0)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.6
        materials.append(mat)
        if obj.data.materials:
            undo.append((obj.data, obj.data.materials[0]))
            obj.data.materials[0] = mat
        else:
            undo.append((obj.data, None))
            obj.data.materials.append(mat)
    return undo


def _setup_engine(sc, engine):
    """Render settings on the build scene; returns the extra objects (lights) to remove."""
    sc.render.engine = engine_id(engine)
    sc.view_settings.view_transform = "Standard"
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 90           # smaller PNGs (lossless either way)
    sc.render.resolution_percentage = 100
    world = sc.world if sc.world is not None and sc.world.get(TAG) else None
    if world is None:
        world = bpy.data.worlds.new("_render_world")
        world[TAG] = True
        sc.world = world
    world.color = linear_rgb(BACKGROUND)                # Workbench: a scene without a world renders black on 4.5
    if engine == "workbench":
        sh = sc.display.shading
        sh.light = "STUDIO"
        try:
            sh.studio_light = STUDIO_LIGHT              # bundled with Blender; the default one if it is missing
        except TypeError:
            pass
        sh.color_type = "OBJECT"
        sh.show_object_outline = True
        sh.show_cavity = True                   # ridges and valleys get a line: embossed text, grooves, fillets
        sh.cavity_type = "BOTH"
        sh.curvature_ridge_factor = 1.5
        sh.curvature_valley_factor = 1.5
        sh.cavity_ridge_factor = 1.0
        sh.cavity_valley_factor = 1.0
        sh.show_shadows = False
        sh.background_type = "WORLD"
        return []
    extras = []
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (*linear_rgb(BACKGROUND), 1.0)
        bg.inputs[1].default_value = 1.0
    sun_data = bpy.data.lights.new("_render_sun", "SUN")
    sun_data[TAG] = True
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("_render_sun", sun_data)
    sun[TAG] = True
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))
    extras.append(sun)
    if engine == "cycles":
        sc.cycles.samples = 32
        sc.cycles.device = "CPU"
    else:
        try:
            sc.eevee.taa_render_samples = 16
        except AttributeError:
            pass
    return extras


def render_views(out, views=None, colors=None, engine="workbench", size=(1600, 1200), objects=None, label=None,
                 overwrite=False):
    """Render the given objects (default: the registered parts) from `views` into one PNG grid
    at `out` (width, height), Workbench by default (headless, no GPU needed; eevee and cycles
    on request), part colours from `colors` {part: (r, g, b)} or the palette. The per-view
    tiles go to a temporary folder next to `out`. Returns {"path", "views", "fg", "fg_views",
    "sane", "note", "size_mm", "renderer", "seconds", "bytes"}; `fg` is the fraction of pixels
    that differ from the background, counted on the rendered views without the caption and the
    grid lines (`fg_views` per view), and `sane` the G4 verdict (`fg_sane`): every view must
    show the part."""
    require_blender()
    import numpy as np                      # bundled with every Blender and the bpy wheel
    views = list(views or DEFAULT_VIEWS)
    bad = [v for v in views if v not in VIEWS]
    if bad:
        raise ValueError(f"unknown views {bad}; choose from {list(VIEWS)}")
    if engine not in ENGINE_NAMES:
        raise ValueError(f"engine must be one of {ENGINE_NAMES}")
    objects = list(objects) if objects is not None else [p["object"] for p in _PARTS.values()]
    if not objects:
        raise ValueError("nothing to render")
    out = os.path.abspath(out)
    if os.path.exists(out) and not overwrite:
        raise FileExistsError(f"{out} already exists; pass overwrite for a working file in out/, or choose a new name")
    width, height = int(size[0]), int(size[1])
    cols, rows = grid_layout(len(views))
    tw, th = width // cols, height // rows
    aspect = tw / th
    colors = colors or {}
    t0 = time.time()
    sc = scene()
    boxes = [world_bbox(o)[:2] for o in objects]
    lo = [min(b[0][i] for b in boxes) for i in range(3)]
    hi = [max(b[1][i] for b in boxes) for i in range(3)]
    size_mm = [round(hi[i] - lo[i], 2) for i in range(3)]
    corners = box_corners(lo, hi)
    scale = 0.0
    for v in views:
        w, h, _cx, _cy = projected_extent(corners, view_basis(*VIEWS[v]))
        scale = max(scale, w, h * aspect if aspect >= 1 else h, w / aspect if aspect < 1 else w)
    scale = max(scale, 1e-6) * (1 + 2 * MARGIN)
    caption = label if label is not None else "%g x %g x %g mm" % tuple(size_mm)
    materials = []
    undo = _colour_objects(objects, {k: tuple(v) for k, v in colors.items()}, materials)
    extras = _setup_engine(sc, engine)
    old_res = (sc.render.resolution_x, sc.render.resolution_y)
    sc.render.resolution_x, sc.render.resolution_y = tw, th
    old_camera = sc.camera
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix=".render-", dir=os.path.dirname(out))
    tiles, captions, temp_objects = [], [], list(extras)
    try:
        for i, v in enumerate(views):
            cam = _camera_for(v, lo, hi, scale, aspect)
            lab = _label(cam, f"{v.upper()}   {caption}" if i == 0 else v.upper(), scale, aspect, materials)
            temp_objects += [cam, lab]
            sc.camera = cam
            tmp = os.path.join(tmpdir, f"{v}.png")
            sc.render.filepath = tmp
            with _ctx():
                bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(tmp)
            w, h = img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            tiles.append(buf.reshape(h, w, 4))
            captions.append(_label_box(lab, scale, aspect, tw, th))
        # The blank check counts the part only: per view, before the grid lines, the caption left out.
        bg = np.asarray(BACKGROUND, dtype=np.float32)
        fg_views, hits, counted = {}, 0, 0
        for v, tile, (x0, y0, x1, y1) in zip(views, tiles, captions):
            drawn = (np.abs(tile[:th, :tw, :3] - bg) > 0.03).any(axis=2)
            keep = np.ones(drawn.shape, dtype=bool)
            keep[y0:y1, x0:x1] = False
            n, k = int(keep.sum()), int((drawn & keep).sum())
            fg_views[v] = round(k / n, 5) if n else 0.0
            hits, counted = hits + k, counted + n
        fg = hits / counted if counted else 0.0
        canvas = np.empty((rows * th, cols * tw, 4), dtype=np.float32)
        canvas[..., :3] = BACKGROUND
        canvas[..., 3] = 1.0
        for i, tile in enumerate(tiles):
            r, c = divmod(i, cols)
            y0 = (rows - 1 - r) * th                      # Blender images are stored bottom-up
            canvas[y0:y0 + th, c * tw:c * tw + tw] = tile[:th, :tw]
        for c in range(1, cols):
            canvas[:, c * tw - 1:c * tw + 1, :3] = 0.82
        for r in range(1, rows):
            canvas[r * th - 1:r * th + 1, :, :3] = 0.82
        grid = bpy.data.images.new("_render_grid", cols * tw, rows * th, alpha=False)
        grid.pixels.foreach_set(canvas.ravel())
        grid.save_render(out, scene=sc)                  # PNG with the scene's compression setting
        bpy.data.images.remove(grid)
    finally:
        for f in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, f))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
        for o in temp_objects:
            data = o.data
            bpy.data.objects.remove(o)
            _remove_data(data)
        for me, previous in undo:
            if previous is None:
                me.materials.pop(index=len(me.materials) - 1)
            else:
                me.materials[0] = previous
        for mat in materials:
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        sc.camera = old_camera
        sc.render.resolution_x, sc.render.resolution_y = old_res
        sc.render.filepath = "//"
    sane, note = fg_sane(fg, fg_views)
    renderer = f"Blender {bpy.app.version_string} {engine} (orthographic, {cols}x{rows} grid)"
    return {"path": out, "views": views, "fg": round(fg, 5), "fg_views": fg_views, "sane": sane, "note": note,
            "size_mm": size_mm, "renderer": renderer, "seconds": round(time.time() - t0, 2), "bytes": os.path.getsize(out)}


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #
def load_params(path, defaults=None):
    p = dict(defaults or {})
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("params file must contain a JSON object")
        p.update({k: v for k, v in data.items() if not str(k).startswith("_")})
    return p


def _generator_stem():
    main = sys.modules.get("__main__")
    f = getattr(main, "__file__", None)
    return os.path.splitext(os.path.basename(f))[0] if f else "model"


def _deps():
    """Python files the build imported from the generator's folder or from here (hashed into
    the manifest by build.py), plus this file."""
    main = sys.modules.get("__main__")
    roots = {os.path.normcase(os.path.dirname(os.path.abspath(__file__)))}
    if getattr(main, "__file__", None):
        roots.add(os.path.normcase(os.path.dirname(os.path.abspath(main.__file__))))
    deps = {os.path.abspath(__file__)}
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if f and f.endswith(".py") and os.path.normcase(os.path.dirname(os.path.abspath(f))) in roots:
            deps.add(os.path.abspath(f))
    return sorted(deps)


def run_mode():
    """Where this runs: "bpy" (the module in some Python), "binary" (blender --background) or
    "live" (a user's open Blender, reached through an MCP tool)."""
    if not bpy.app.binary_path:
        return "bpy"
    return "binary" if bpy.app.background else "live"


def blend_target(blend, out_dir, stem):
    """Where main() saves the .blend and whether it may replace it: the default
    `<out>/<stem>.blend` is the working copy and is rewritten; an explicit --blend must be a
    new file inside --out and never the file open in Blender."""
    out_dir = os.path.abspath(out_dir)
    if not blend:
        return os.path.join(out_dir, stem + ".blend"), True
    path = os.path.abspath(blend)
    open_file = bpy.data.filepath if bpy is not None else ""
    if _same_file(path, open_file):
        raise ValueError(f"--blend names the file open in Blender ({os.path.basename(path)}); the open file is never written")
    if not _inside(path, out_dir):
        raise ValueError(f"--blend must lie inside --out ({out_dir}); got {path}")
    if os.path.exists(path):
        raise ValueError(f"--blend {path} already exists; a new name, or omit --blend for the working copy")
    return path, False


def main(build, defaults=None, argv=None):
    """Run a generator: parse the command line (`--out` is required), build into the build
    scene, check, export, save, report. `build(params)` returns {part_name: Object} (parts
    registered with `part` keep their object and role). Prints the @@3DPS line; raises on any
    failure (exit code 1 under `--python-exit-code 1`)."""
    require_blender()
    args = cli_args(argv)
    if args.cmd == "render":
        return render_cli(args)
    out_dir = os.path.abspath(args.out)
    params = load_params(args.params, defaults)
    t0 = time.time()
    new_scene_mm(args.scene)
    LOG.append(f"Blender {bpy.app.version_string}, {run_mode()}, "
               f"boolean solver {boolean_solver()}")
    blend = None
    if not args.no_blend:
        blend, rewrite = blend_target(args.blend, out_dir, _generator_stem())     # refused before anything is built
    result = build(params)
    if result is None:
        result = {n: p["object"] for n, p in _PARTS.items()}
    if not isinstance(result, dict):
        result = {next(iter(_PARTS), "part"): result}
    for name, obj in result.items():
        if name not in _PARTS:
            part(obj, name)
    params_to_props(params)
    check_props()                                        # a path in a property fails here, before any STL is written
    only = [n.strip() for n in args.only.split(",") if n.strip()] if args.only else None
    info = export_parts(out_dir, only)
    if blend:
        blend = save_blend(blend, overwrite=rewrite, out_dir=out_dir)
    print(summary(info, deps=_deps(), blend=blend, blender=bpy.app.version_string, solver=boolean_solver(),
                  mode=run_mode(), notes=list(LOG),
                  warnings=[f"{p['name']}: {p['warning']}" for p in info if p.get("warning")],
                  seconds=round(time.time() - t0, 2)))
    return info


def render_cli(args):
    """`render STL... -o out.png`: import the STLs (1 unit = 1 mm) into the build scene and
    render them."""
    require_blender()
    out = os.path.abspath(args.out)
    if os.path.exists(out) and not args.overwrite:
        raise FileExistsError(f"{out} already exists; pass --overwrite for a working file in out/, or choose a new name")
    sc = new_scene_mm()
    names = []
    objects = []
    for path in args.stl:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        before = set(bpy.data.objects)
        with _ctx():
            bpy.ops.wm.stl_import(filepath=os.path.abspath(path), global_scale=1.0, use_scene_unit=False,
                                  forward_axis="Y", up_axis="Z", use_mesh_validate=False)
        new = [o for o in bpy.data.objects if o not in before]
        if not new:
            raise ValueError(f"nothing imported from {path}")
        name = os.path.splitext(os.path.basename(path))[0]
        for o in new:
            o[TAG] = True
            if o.data is not None:
                o.data[TAG] = True
            o["part"] = name
            o.name = name
            for col in list(o.users_collection):       # the importer links into the context scene
                col.objects.unlink(o)
            sc.collection.objects.link(o)
        names.append(name)
        objects += new
    colors, warnings = parse_colors(args.color, names)
    views = [v.strip().lower() for v in args.views.split(",") if v.strip()]
    w, h = (int(x) for x in args.size.lower().split("x"))
    rep = render_views(out, views, colors, args.engine, (w, h), objects, args.label, overwrite=args.overwrite)
    rep["parts"] = [{"name": n, "colour": rgb_hex(colors[n]),
                     "drawn": rgb_hex(preview_rgb(colors[n]))} for n in names]
    rep["colour_note"] = COLOUR_TABLE_NOTE
    rep["warnings"] = warnings
    print("@@3DPS " + json.dumps(rep, sort_keys=True))
    return rep


if __name__ == "__main__":
    _args = cli_args()
    if _args.cmd != "render":
        raise SystemExit("blender_builder.py runs the 'render' command only; a generator calls main(build, PARAMETERS)")
    render_cli(_args)
