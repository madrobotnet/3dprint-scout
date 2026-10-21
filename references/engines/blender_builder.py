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
glyph piece (the LOG line counts them), so its `_parts` entry needs `shells` (parts.md) or it
fails M5.

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
import unicodedata

# The skill's own Python libraries (parts.py, sdf.py) are importable from a Blender generator,
# after the generator's own folder: parts.py's mechanical helpers reach Blender through
# from_manifold wherever manifold3d is installed in the Python that runs Blender.
SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
if os.path.isfile(os.path.join(SKILL_SCRIPTS, "parts.py")) and SKILL_SCRIPTS not in sys.path:
    sys.path.append(SKILL_SCRIPTS)

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
NOTDEF_PROBE = "\U0010FFFD"             # a code point no font maps: its outline is the font's .notdef box

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
LIGHT_KNEE = 0.85                       # preview_rgb: luminance above this is compressed towards LIGHT_MAX, so
LIGHT_MAX = 0.90                        # white (drawn ~230) stands off the 246 background instead of fading into it
SSAO_RATIO = 0.15                       # world-space cavity distance = this x the part's largest extent (mm)...
SSAO_MIN, SSAO_MAX = 1.0, 30.0          # ...within these bounds: pockets and keyholes darken, a flat face does not
SSAO_ATTENUATION = 0.05                 # Blender's 1.0 fades the effect out well inside that distance
SSAO_VALLEY = 2.0                       # cavity valley factor (1.0 left a 5 mm pocket at 1/255 off its face)
SSAO_RENDERS_FROM = (5, 0)              # a 4.x Workbench render ignores the world-space cavity: shadows instead
SHADOW_INTENSITY = 0.25                 # Workbench shadows on 4.x: a 5 mm pocket floor reads ~16/255 darker
SMOOTH_ANGLE = 30.0                     # degrees: faces meeting flatter than this are shaded smooth in a render
MARGIN = 0.08
ENGINE_NAMES = ("workbench", "eevee", "cycles")
COLOUR_TABLE_NOTE = ("colours are approximate screen values of common Bambu filaments (for previews and the "
                     "colour swatches of a project file; the filament loaded is what prints); "
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
    shading still shows their edges (black parts read as featureless otherwise), and very
    light ones are taken down a little so a white part stands off the near-white background
    instead of showing only its outline in the FRONT and TOP views. Preview only."""
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    if lum < 0.2:
        return tuple(DARK_LIFT + (1 - DARK_LIFT) * c for c in rgb)
    if lum > LIGHT_KNEE:
        target = LIGHT_KNEE + (lum - LIGHT_KNEE) * (LIGHT_MAX - LIGHT_KNEE) / (1.0 - LIGHT_KNEE)
        return tuple(c * target / lum for c in rgb)
    return tuple(rgb)


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
    """An object from a bmesh (consumed), linked into the build scene and tagged; its faces
    point outward."""
    require_blender()
    bm.normal_update()                      # recalc_face_normals starts from the current normals
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


def weld_degenerate(me):
    """Merge, within WELD, only the corners of triangles that have an edge shorter than WELD (a
    cut or a bevel can leave two corners a hair apart, which the export would weld as well).
    Returns how many vertices were merged; the caller counts degenerate and non-manifold edges
    again."""
    import numpy as np
    me.calc_loop_triangles()
    if not len(me.loop_triangles):
        return 0
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    idx = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", idx)
    tri = idx.reshape(-1, 3)
    a, b, c = (co[tri[:, k]] for k in range(3))
    short = np.minimum(np.minimum(np.linalg.norm(a - b, axis=1), np.linalg.norm(b - c, axis=1)), np.linalg.norm(a - c, axis=1))
    pick = set(tri[short < WELD].ravel().tolist())
    if not pick:
        return 0
    n = len(me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.remove_doubles(bm, verts=[bm.verts[i] for i in pick], dist=WELD)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return n - len(me.vertices)


def fix_slivers(me, area=1e-9):
    """Remove the zero-area triangles a flat face's triangulation makes where three of its
    corners lie almost in line (a cut through faceted geometry leaves such corners): the faces
    holding them are triangulated and the long edge of each sliver, a diagonal inside the flat
    face, is turned to the opposite corner, which gives two proper triangles in the same plane.
    Returns how many slivers remain (0 when all are gone); the shape is unchanged."""
    import numpy as np
    for _ in range(8):
        me.calc_loop_triangles()
        if not len(me.loop_triangles):
            return 0
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        bad = {t.polygon_index for t in me.loop_triangles
               if np.linalg.norm(np.cross(co[t.vertices[1]] - co[t.vertices[0]], co[t.vertices[2]] - co[t.vertices[0]])) / 2 < area}
        if not bad:
            return degenerate_triangles(me, area)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        res = bmesh.ops.triangulate(bm, faces=[bm.faces[i] for i in bad], quad_method="BEAUTY", ngon_method="BEAUTY")
        turn = []
        for f in res["faces"]:
            a, b, c = (v.co for v in f.verts)
            if (b - a).cross(c - a).length / 2 < area:
                e = max(f.edges, key=lambda e: e.calc_length())
                if len(e.link_faces) == 2 and e not in turn:
                    turn.append(e)
        if turn:
            bmesh.ops.rotate_edges(bm, edges=turn, use_ccw=False)
        bm.to_mesh(me)
        bm.free()
        me.update()
        if not turn:
            break
    return degenerate_triangles(me, area)


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


def cone(r_bottom, r_top, h, segments=None, name="cone", collection=None, z0=0.0):
    """A cone or frustum on the Z axis from z0 to z0 + h, radius r_bottom at the bottom and
    r_top at the top (either may be 0 for a point; not both). A countersink is
    `cone(shank_r, head_r + overshoot, head_r - shank_r + overshoot)` placed with its top
    `overshoot` above the face (90 degrees: the radius grows as fast as the height)."""
    require_blender()
    if h <= 0 or r_bottom < 0 or r_top < 0 or (r_bottom == 0 and r_top == 0):
        raise ValueError("cone needs h > 0 and radii >= 0, not both 0")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments or circle_segments(max(r_bottom, r_top)),
                          radius1=r_bottom, radius2=r_top, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, z0 + h / 2), verts=bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD)          # a zero radius collapses to the tip
    return mesh_object(name, bm, collection)


PLANES = {"XY": lambda u, v, w: (u, v, w),            # outline (x, y), extruded along +Z
          "XZ": lambda u, v, w: (u, w, v),            # outline (x, z), extruded along +Y
          "YZ": lambda u, v, w: (w, u, v)}            # outline (y, z), extruded along +X


def prism(outline, height, name="prism", collection=None, z0=0.0, plane="XY"):
    """A closed 2D outline [(u, v), ...] in mm extruded by `height` from z0 (caps are n-gons;
    the exporter triangulates them). `plane` says what the outline's two coordinates are and
    which way it is extruded: "XY" (x, y; along +Z, the default), "XZ" (x, z; along +Y: a
    profile drawn as seen from the front) or "YZ" (y, z; along +X). z0 is the start on the
    extrusion axis. Build a profile with `arc` and `round_profile`."""
    require_blender()
    if plane not in PLANES:
        raise ValueError(f"plane must be one of {sorted(PLANES)}; got {plane!r}")
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
    if plane != "XY":
        to = PLANES[plane]
        for v in bm.verts:
            v.co = to(v.co.x, v.co.y, v.co.z)
    return mesh_object(name, bm, collection)                  # normals are recalculated there


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


class Arc(list):
    """The points of a circular arc (a list, usable wherever points are), remembering the circle
    it lies on, so `round_profile` can round a corner against the true circle, not its facets."""

    def __init__(self, center, r, start_deg, end_deg, segments=None):
        if r <= 0:
            raise ValueError("arc radius must be positive")
        if abs(end_deg - start_deg) < 1e-9:
            raise ValueError("an arc needs two different angles")
        self.center = (float(center[0]), float(center[1]))
        self.r = float(r)
        self.start_deg, self.end_deg = float(start_deg), float(end_deg)
        n = segments or circle_segments(r)
        span = math.radians(end_deg - start_deg)
        k = max(1, math.ceil(abs(span) / (2 * math.pi / n)))
        a0 = math.radians(start_deg)
        super().__init__((self.center[0] + r * math.cos(a0 + span * i / k), self.center[1] + r * math.sin(a0 + span * i / k))
                         for i in range(k + 1))


def arc(center, r, start_deg, end_deg, segments=None):
    """A circular arc for a 2D profile: centre (u, v), radius r in mm, from start_deg to end_deg
    (degrees; counter-clockwise when end > start), both ends included, at the circle rule's
    spacing (`circle_segments(r)` per full turn). A list of points that also remembers its
    circle: join arcs and points with `outline`, round the corners with `round_profile`."""
    return Arc(center, r, start_deg, end_deg, segments)


def _pieces(items):
    """Pieces of an outline in order: a single (u, v) point, or a list of points (an Arc keeps
    its circle)."""
    out = []
    for piece in items:
        if piece and isinstance(piece[0], (int, float)):
            out.append([tuple(map(float, piece[:2]))])
        else:
            out.append(piece)
    return out


def outline(*pieces):
    """One closed 2D outline (a list of (u, v) points) from pieces: single points, lists of
    points and `arc`s, dropping a point that repeats the one before it (or closes onto the
    first). For rounded corners pass the same pieces to `round_profile` instead."""
    pts = []
    for piece in _pieces(pieces):
        for q in piece:
            q = (float(q[0]), float(q[1]))
            if not pts or math.dist(q, pts[-1]) > 1e-6:
                pts.append(q)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) <= 1e-6:
        pts.pop()
    return pts


def _signed_area(pts):
    return sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts))) / 2


def _edges_2d(pieces):
    """Nodes and edges of an outline: every point is a node except the inside points of an arc;
    edge i runs from node i to node i + 1 and is ("line",) or ("arc", centre, r, ccw)."""
    nodes, kinds = [], []
    for piece in _pieces(pieces):
        if isinstance(piece, Arc):
            a, b = piece[0], piece[-1]
            if nodes and math.dist(a, nodes[-1]) <= 1e-6:
                kinds[-1] = None                       # the arc starts where the last piece ended
            else:
                nodes.append(a)
                kinds.append(None)
            kinds[-1] = ("arc", piece.center, piece.r, piece.end_deg > piece.start_deg)
            nodes.append(b)
            kinds.append(("line",))
        else:
            for q in piece:
                q = (float(q[0]), float(q[1]))
                if nodes and math.dist(q, nodes[-1]) <= 1e-6:
                    continue
                nodes.append(q)
                kinds.append(("line",))
    if len(nodes) > 1 and math.dist(nodes[0], nodes[-1]) <= 1e-6:
        nodes.pop()                                        # closes onto the first: its edge now wraps round
        kinds.pop()
    return nodes, kinds


def _tangent(kind, p, q, at_start):
    """Unit direction of travel along edge p -> q at its start (or end)."""
    if kind[0] == "line":
        d = (q[0] - p[0], q[1] - p[1])
    else:
        c, ccw = kind[1], kind[3]
        x = p if at_start else q
        rx, ry = x[0] - c[0], x[1] - c[1]
        d = (-ry, rx) if ccw else (ry, -rx)
    n = math.hypot(*d)
    return (d[0] / n, d[1] / n)


def _dir_at(kind, p, q, x):
    """Unit direction of travel along edge p -> q at its point x."""
    if kind[0] == "line":
        d = (q[0] - p[0], q[1] - p[1])
    else:
        c, ccw = kind[1], kind[3]
        rx, ry = x[0] - c[0], x[1] - c[1]
        d = (-ry, rx) if ccw else (ry, -rx)
    n = math.hypot(*d)
    return (d[0] / n, d[1] / n)


def _carrier_offsets(kind, p, q, r):
    """The curves a fillet centre may lie on next to this edge: lines parallel to it at r, or
    circles concentric with it at R - r and R + r."""
    if kind[0] == "line":
        d = (q[0] - p[0], q[1] - p[1])
        n = math.hypot(*d)
        nx, ny = -d[1] / n, d[0] / n
        return [("line", (p[0] + s * r * nx, p[1] + s * r * ny), (d[0] / n, d[1] / n)) for s in (1, -1)]
    c, R = kind[1], kind[2]
    return [("circle", c, rr) for rr in (R - r, R + r) if rr > 1e-9]


def _intersect(a, b):
    """Intersections of two carriers (line: point + unit direction; circle: centre + radius)."""
    if a[0] == "circle" and b[0] == "line":
        a, b = b, a
    if a[0] == "line" and b[0] == "line":
        (p, d), (q, e) = a[1:], b[1:]
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            return []
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
        return [(p[0] + t * d[0], p[1] + t * d[1])]
    if a[0] == "line":
        (p, d), (c, R) = a[1:], b[1:]
        fx, fy = p[0] - c[0], p[1] - c[1]
        bq = fx * d[0] + fy * d[1]
        disc = bq * bq - (fx * fx + fy * fy - R * R)
        if disc < 0:
            return []
        s = math.sqrt(disc)
        return [(p[0] + t * d[0], p[1] + t * d[1]) for t in (-bq - s, -bq + s)]
    (c1, r1), (c2, r2) = a[1:], b[1:]
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-12 or dist > r1 + r2 or dist < abs(r1 - r2):
        return []
    a_ = (r1 * r1 - r2 * r2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(r1 * r1 - a_ * a_, 0.0))
    mx, my = c1[0] + a_ * dx / dist, c1[1] + a_ * dy / dist
    return [(mx + h * -dy / dist, my + h * dx / dist), (mx - h * -dy / dist, my - h * dx / dist)]


def _foot(kind, p, q, c):
    """Where a circle centred at c touches the edge's carrier, and that point's position along
    the edge (0 at p, 1 at q; outside 0..1 means beyond the edge)."""
    if kind[0] == "line":
        d = (q[0] - p[0], q[1] - p[1])
        L2 = d[0] * d[0] + d[1] * d[1]
        t = ((c[0] - p[0]) * d[0] + (c[1] - p[1]) * d[1]) / L2
        return (p[0] + t * d[0], p[1] + t * d[1]), t
    ctr, R, ccw = kind[1], kind[2], kind[3]
    ang = math.atan2(c[1] - ctr[1], c[0] - ctr[0])
    x = (ctr[0] + R * math.cos(ang), ctr[1] + R * math.sin(ang))
    a0 = math.atan2(p[1] - ctr[1], p[0] - ctr[0])
    a1 = math.atan2(q[1] - ctr[1], q[0] - ctr[0])
    span = (a1 - a0) % (2 * math.pi) if ccw else (a0 - a1) % (2 * math.pi)
    span = span or 2 * math.pi
    at = (ang - a0) % (2 * math.pi) if ccw else (a0 - ang) % (2 * math.pi)
    if at > span + (2 * math.pi - span) / 2:
        at -= 2 * math.pi                                 # just before the start, not far past the end
    return x, at / span


def round_profile(pieces, radius, corners=None, angle=20.0, segments=None):
    """A 2D outline with corners rounded to `radius` (mm), for `prism`: the round runs the full
    length of the extrusion, which a mesh fillet along a curved face's facets cannot do.
    `pieces` are what `outline` takes (points, lists of points, `arc`s); the corners are the
    points where two pieces or two straight segments meet, never the inside points of an arc.
    `corners`: their indices (default: every corner turning `angle` degrees or more, convex
    and concave). Each round is a true circle tangent to the two edges at the corner, straight
    or arc (a lip where a straight opening meets a ring is rounded against the ring's circle),
    and is refused with a message when it does not fit on both edges (a radius too big, or two
    rounds that would overlap)."""
    if radius <= 0:
        raise ValueError("round_profile radius must be positive")
    items = list(pieces) if not (pieces and isinstance(pieces[0], (int, float))) else [pieces]
    nodes, kinds = _edges_2d(items)
    n = len(nodes)
    sampled = outline(*items)
    if n < 2 or len(sampled) < 3:
        raise ValueError("an outline needs at least three points (an arc counts with its own)")
    lim = math.radians(angle)
    fillets = {}
    for i in range(n):
        if corners is not None and i not in {int(c) % n for c in corners}:
            continue
        p, k_in = nodes[i], kinds[i - 1]
        prev, nxt, k_out = nodes[i - 1], nodes[(i + 1) % n], kinds[i]
        t_in = _tangent(k_in, prev, p, at_start=False)
        t_out = _tangent(k_out, p, nxt, at_start=True)
        turn = math.atan2(t_in[0] * t_out[1] - t_in[1] * t_out[0], t_in[0] * t_out[0] + t_in[1] * t_out[1])
        if abs(turn) < (lim if corners is None else 1e-6):
            continue
        left = turn > 0                                     # the round's centre is on the inside of the turn
        best = None
        for ca in _carrier_offsets(k_in, prev, p, radius):
            for cb in _carrier_offsets(k_out, p, nxt, radius):
                for c in _intersect(ca, cb):
                    x1, s1 = _foot(k_in, prev, p, c)
                    x2, s2 = _foot(k_out, p, nxt, c)
                    if not (-1e-9 <= s1 <= 1 + 1e-9 and -1e-9 <= s2 <= 1 + 1e-9):
                        continue
                    d1, d2 = _dir_at(k_in, prev, p, x1), _dir_at(k_out, p, nxt, x2)
                    side1 = d1[0] * (c[1] - x1[1]) - d1[1] * (c[0] - x1[0])
                    side2 = d2[0] * (c[1] - x2[1]) - d2[1] * (c[0] - x2[0])
                    if (side1 > 0) != left or (side2 > 0) != left:
                        continue                            # tangent from the wrong side: not this corner's round
                    w = (c[0] - p[0], c[1] - p[1])
                    d = math.hypot(*w)
                    if best is None or d < best[0]:
                        best = (d, c, x1, s1, x2, s2)
        if best is None:
            raise ValueError(f"round_profile: no {radius} mm round fits at corner {i} {tuple(round(c, 3) for c in p)}: "
                             "the edges next to it are too short for it (or it turns the other way); use a smaller "
                             "radius, or give that corner more room")
        fillets[i] = best[1:]
    for i, f in fillets.items():                           # two rounds on one edge must not overlap
        j = (i + 1) % n
        if j in fillets and f[4] > fillets[j][2] + 1e-9:
            raise ValueError(f"round_profile: the {radius} mm rounds at corners {i} and {j} overlap on the edge "
                             "between them; use a smaller radius")
    out = []
    for i in range(n):
        p, q, k = nodes[i], nodes[(i + 1) % n], kinds[i]
        if i in fillets:
            c, x1, _, x2, _ = fillets[i]
            a1 = math.degrees(math.atan2(x1[1] - c[1], x1[0] - c[0]))
            a2 = math.degrees(math.atan2(x2[1] - c[1], x2[0] - c[0]))
            out.extend(Arc(c, radius, a1, a1 + ((a2 - a1 + 540.0) % 360.0 - 180.0), segments))
            start = x2
        else:
            start = p
        j = (i + 1) % n
        end = fillets[j][1] if j in fillets else q
        if k[0] == "arc":
            ctr, R, ccw = k[1], k[2], k[3]
            a0 = math.degrees(math.atan2(start[1] - ctr[1], start[0] - ctr[0]))
            a1 = math.degrees(math.atan2(end[1] - ctr[1], end[0] - ctr[0]))
            span = (a1 - a0) % 360.0 if ccw else -((a0 - a1) % 360.0)
            if abs(span) > 1e-9:
                out.extend(Arc(ctr, R, a0, a0 + span, segments))
            else:
                out.append(start)
        else:
            out.append(start)
    rounded = outline(out)
    if (_signed_area(rounded) > 0) != (_signed_area(sampled) > 0):
        raise ValueError("round_profile: the rounded outline turned inside out (a radius too big for the shape)")
    return rounded


FLAT_TOL_GROUP = 1e-3        # mm: a face group (manifold3d's face_id) merged back only when this flat


def _plane(points):
    """(unit normal, a point) of the best plane through `points` (area-weighted Newell normal of
    the polygon soup, in double precision), or None when they span no area."""
    nx = ny = nz = 0.0
    for poly in points:
        for (x1, y1, z1), (x2, y2, z2) in zip(poly, poly[1:] + poly[:1]):
            nx += (y1 - y2) * (z1 + z2)
            ny += (z1 - z2) * (x1 + x2)
            nz += (x1 - x2) * (y1 + y2)
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    if L == 0:
        return None
    pts = [p for poly in points for p in poly]
    c = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
    return (nx / L, ny / L, nz / L), c


def _off_plane(plane, pts):
    (nx, ny, nz), (ox, oy, oz) = plane
    return max(abs((x - ox) * nx + (y - oy) * ny + (z - oz) * nz) for x, y, z in pts)


def from_mesh(verts, faces, name="mesh", collection=None, groups=None):
    """An object from vertices [(x, y, z), ...] in mm and faces [(i, j, k, ...), ...]: the
    bridge for geometry made outside Blender (`from_manifold`, `import_stl`). Vertices closer
    than WELD are merged and the normals made consistent; a mesh that is not closed (open or
    non-manifold edges) is refused, as a boolean or the validator would refuse it.
    Triangles of one flat face become one face again (a cylinder's facets from manifold3d or an
    STL are split along a diagonal): a cut through such a facet would add a vertex on the
    diagonal, in line with the facet's edges, and leave zero-area triangles. `groups` (one id
    per face, manifold3d's face_id) says which triangles were one face: a group is merged when
    its corners are within 0.001 mm of one plane (a warped face keeps its id but is curved, and
    an id can span several faces). Every other face is grown from a seed only while every
    corner stays within WELD / 2 of the seed's plane, so a gentle curve's facets are never
    folded into one bent face."""
    require_blender()
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v[:3])) for v in verts], [], [tuple(int(i) for i in f) for f in faces])
    me.validate(clean_customdata=False)
    if groups is not None and len(me.polygons) != len(faces):
        groups = None                          # validate dropped a face: the ids no longer line up
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    gl = None
    if groups is not None:
        gl = bm.faces.layers.int.new("group")
        for f, g in zip(bm.faces, groups):
            f[gl] = int(g)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD)
    open_edges = sum(1 for e in bm.edges if not e.is_manifold)
    if not bm.faces or open_edges:
        bm.free()
        raise ValueError(f"'{name}': {open_edges} open or non-manifold edges; a part brought into Blender must be a "
                         "closed mesh (run validate.py on it first)")
    bm.normal_update()
    flat, seen = set(), set()
    if gl is not None:
        by = {}
        for f in bm.faces:
            by.setdefault(f[gl], []).append(f)
        for fs in by.values():
            if len(fs) < 2:
                continue
            polys = [[tuple(v.co) for v in f.verts] for f in fs]
            pl = _plane(polys)
            if pl is None or _off_plane(pl, [p for poly in polys for p in poly]) > FLAT_TOL_GROUP:
                continue                       # not one flat face after all: grown below instead
            members = set(fs)
            seen.update(fs)
            flat.update(e for f in fs for e in f.edges
                        if len(e.link_faces) == 2 and all(g in members for g in e.link_faces))
    for f0 in bm.faces:
        if f0 in seen:
            continue
        seen.add(f0)
        pl = _plane([[tuple(v.co) for v in f0.verts]])
        if pl is None:
            continue
        region, todo = {f0}, [f0]
        while todo:
            f = todo.pop()
            for e in f.edges:
                if len(e.link_faces) != 2 or e.calc_face_angle(0.0) > math.radians(0.05):
                    continue
                g = e.link_faces[0] if e.link_faces[1] == f else e.link_faces[1]
                if g in seen or _off_plane(pl, [tuple(v.co) for v in g.verts]) > WELD / 2:
                    continue
                seen.add(g)
                region.add(g)
                todo.append(g)
        flat.update(e for f in region for e in f.edges
                    if len(e.link_faces) == 2 and all(g in region for g in e.link_faces))
    if flat:
        bmesh.ops.dissolve_edges(bm, edges=list(flat), use_verts=False, use_face_split=False)
    if gl is not None:
        bm.faces.layers.int.remove(gl)
    return mesh_object(name, bm, collection)


def from_manifold(man, name="manifold", collection=None):
    """An object from a manifold3d solid: a part, or a feature to boolean, built with parts.py's
    mechanical helpers (screw holes, countersinks, teardrops, snaps, hinges, threads, rounded
    profiles from CrossSection offsets) and finished in Blender (fillets, text, renders).
    Needs manifold3d in the Python that runs Blender: the bpy module's own environment, or
    Blender's bundled Python with manifold3d installed (ask the user before installing).
    `build.py detect` says whether it is there (`blender.*.manifold3d`)."""
    if not hasattr(man, "to_mesh"):
        raise TypeError("from_manifold needs a manifold3d Manifold (it has no to_mesh())")
    if man.is_empty():
        raise ValueError(f"'{name}': the manifold is empty")
    mesh = man.to_mesh()
    verts = [tuple(v[:3]) for v in mesh.vert_properties.tolist()]
    tris = mesh.tri_verts.tolist()
    ids = getattr(mesh, "face_id", None)                 # which triangles were one face (manifold3d 3.x)
    ids = [int(i) for i in ids] if ids is not None and len(ids) == len(tris) else None
    return from_mesh(verts, tris, name=name, collection=collection, groups=ids)


def _read_stl(path):
    """Triangles [((x, y, z), (x, y, z), (x, y, z)), ...] of a binary or ASCII STL."""
    import struct
    with open(path, "rb") as f:
        data = f.read()
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            out = []
            for i in range(n):
                v = struct.unpack("<12f", data[84 + 50 * i: 84 + 50 * i + 48])
                out.append((v[3:6], v[6:9], v[9:12]))
            return out
    text = data.decode("ascii", errors="replace")
    pts = [tuple(float(x) for x in m.groups()) for m in re.finditer(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)]
    if not pts or len(pts) % 3:
        raise ValueError(f"{os.path.basename(path)}: not a binary or ASCII STL")
    return [tuple(pts[i:i + 3]) for i in range(0, len(pts), 3)]


_IMPORTED = []       # files import_stl read: hashed into the manifest like the generator's sources


def import_stl(path, name=None, collection=None):
    """An object from an STL (binary or ASCII, mm): a part another engine built (a Python
    generator's body) brought in to be finished in Blender. Welded and checked as `from_mesh`.
    The STL is one of this build's sources (its sha256 goes into the manifest, so a changed
    STL makes the Blender part stale)."""
    tris = _read_stl(path)
    if os.path.abspath(path) not in _IMPORTED:
        _IMPORTED.append(os.path.abspath(path))
    index, verts, faces = {}, [], []
    for t in tris:
        face = []
        for v in t:
            key = tuple(round(c / WELD) for c in v)
            if key not in index:
                index[key] = len(verts)
                verts.append(v)
            face.append(index[key])
        if len(set(face)) == 3:
            faces.append(face)
    return from_mesh(verts, faces, name=name or os.path.splitext(os.path.basename(path))[0], collection=collection)


def _world(obj):
    """The object's world matrix as it is now: Blender recomputes matrix_world only when the
    scene is evaluated, so a location or rotation set a moment ago is not in it yet."""
    _view_layer().update()
    return obj.matrix_world.copy()


def apply_transform(obj):
    """Bake the object's location, rotation and scale into its mesh (modifiers applied first),
    leaving it at the identity: helpers that read coordinates (bed_chamfer, fillet's `inside`)
    then see what the STL will hold. A mirrored transform keeps its faces pointing out."""
    require_blender()
    if obj.modifiers:
        apply_modifiers(obj)
    mw = _world(obj)
    if mw == mw.Identity(4):
        return obj
    children = {c: _world(c) for c in obj.children}
    if obj.data.users > 1:                 # a mesh shared with a linked copy: bake a copy of it only
        own = obj.data.copy()
        own[TAG] = True
        obj.data = own
    me = obj.data
    me.transform(mw)
    if mw.determinant() < 0:
        me.flip_normals()
    obj.parent = None
    obj.location, obj.scale = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.matrix_world = mw.Identity(4)
    me.update()
    _view_layer().update()                 # matrix_world is read again right away (export, edges)
    for c, cw in children.items():         # children stay where they were in the world
        c.matrix_world = cw
    if children:
        _view_layer().update()
    return obj


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
        d = 0
        if degenerate_triangles(target.data):
            weld_degenerate(target.data)                       # corners a hair apart, as the export welds
            d = fix_slivers(target.data)
            n = nonmanifold_edges(target)
            if n:
                raise ValueError(f"boolean {ops[operation].lower()} with solver {solver} left {n} non-manifold edges "
                                 f"on '{target.name}' once its corners closer than {WELD} mm were merged: two "
                                 "surfaces nearly touch; move the tool off them by 0.01-0.1 mm")
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


def _axis_vector(axis):
    if axis is None:
        return None
    named = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
    v = named.get(str(axis).lower()) if isinstance(axis, str) else tuple(float(c) for c in axis)
    if v is None or len(v) != 3:
        raise ValueError(f"axis must be 'x', 'y', 'z' or a vector; got {axis!r}")
    n = math.sqrt(sum(c * c for c in v))
    if n == 0:
        raise ValueError("axis must not be a zero vector")
    return mathutils.Vector(v) / n


def edges(obj, angle=30.0, axis=None, inside=None, bed=False):
    """Indices of the object's sharp edges (faces meeting at `angle` degrees or more), the
    ones `fillet` should round: only those parallel to `axis` ("x", "y", "z" or a vector,
    within 1 degree) when given, only those with both ends inside the box `inside` =
    ((x0, y0, z0), (x1, y1, z1)) in world mm when given, and never an edge on the bed unless
    bed=True (the bed edge gets bed_chamfer). Modifiers are applied first."""
    require_blender()
    if obj.modifiers:
        apply_modifiers(obj)
    mw = _world(obj)
    rot = mw.to_3x3()
    ax = _axis_vector(axis)
    lim = math.radians(angle)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    world = {v.index: mw @ v.co for v in bm.verts}
    zmin = min((c.z for c in world.values()), default=0.0)
    out = []
    for e in bm.edges:
        if len(e.link_faces) != 2 or e.calc_face_angle(0.0) < lim:
            continue
        a, b = (world[v.index] for v in e.verts)
        if not bed and abs(a.z - zmin) < 1e-5 and abs(b.z - zmin) < 1e-5:
            continue
        if ax is not None:
            d = rot @ (e.verts[1].co - e.verts[0].co)
            if d.length == 0 or abs(d.normalized().dot(ax)) < math.cos(math.radians(1.0)):
                continue
        if inside is not None:
            lo, hi = inside
            if not all(lo[i] - 1e-6 <= p[i] <= hi[i] + 1e-6 for p in (a, b) for i in range(3)):
                continue
        out.append(e.index)
    bm.free()
    return out


_edges = edges                                      # fillet's `edges` argument shadows the function


FLAT_COS = math.cos(math.radians(0.1))     # faces this close to parallel are one flat region (float32 normals)


def _flat_regions(bm, offsets):
    """The flat regions that hold a chosen edge: faces joined across flat edges (a boolean
    splits a top with a hole into faces along such edges), each as (a face, its boundary loops,
    its faces). A loop is a list of (edge, start vertex, end vertex, offset), walked with the
    faces' winding (left of travel, seen from the normal, is inside, for the outline and for a
    hole alike). Where a round ends at a corner of a face it does not run along (its end cap),
    the check after the bevel decides."""
    seen, regions = set(), []
    for f0 in bm.faces:
        if f0.index in seen or not any(offsets[e.index] > 0 for e in f0.edges):
            continue
        region, todo = {f0}, [f0]
        seen.add(f0.index)
        while todo:
            f = todo.pop()
            for e in f.edges:
                if offsets[e.index] > 0 or len(e.link_faces) != 2:
                    continue
                g = e.link_faces[0] if e.link_faces[1] == f else e.link_faces[1]
                if g.index not in seen and g.normal.dot(f0.normal) > FLAT_COS:
                    seen.add(g.index)
                    region.add(g)
                    todo.append(g)
        segs = {}
        for f in region:
            for l in f.loops:
                e = l.edge
                if sum(1 for g in e.link_faces if g in region) == 1:
                    a_, b_ = l.vert, l.link_loop_next.vert
                    segs.setdefault(a_.index, []).append((e, a_, b_, offsets[e.index]))
        loops, used = [], set()
        for start in list(segs):
            for first in segs[start]:
                if first[0].index in used:
                    continue
                loop, cur = [], first
                while cur and cur[0].index not in used:
                    used.add(cur[0].index)
                    loop.append(cur)
                    cur = next((c for c in segs.get(cur[2].index, []) if c[0].index not in used), None)
                loops.append(loop)
        regions.append((f0, loops, region))
    return regions


def _inset_fault(normal, loops):
    """None when the region's outline, each edge moved inward by its offset, is still a
    proper outline; else what goes wrong (an edge turned round, two edges crossing, a hole's
    rim meeting the outline)."""
    n = normal.normalized()
    ax = n.orthogonal().normalized()
    ay = n.cross(ax)
    o = loops[0][0][1].co
    def flat(v):
        d = v - o
        return (d.dot(ax), d.dot(ay))
    old_loops, new_loops, moved, names = [], [], [], []
    for loop in loops:
        k = len(loop)
        pts = [flat(s[1].co) for s in loop]
        off = [s[3] for s in loop]
        nm = [f"edge {s[0].index}" for s in loop]
        dirs, inward = [], []
        for i in range(k):
            a, b = pts[i], pts[(i + 1) % k]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1e-12
            dirs.append((dx / L, dy / L))
            inward.append((-dy / L, dx / L))
        new = []
        for i in range(k):
            j = i - 1                                            # segment j ends where segment i starts
            p = pts[i]
            a = (p[0] + inward[j][0] * off[j], p[1] + inward[j][1] * off[j])
            b = (p[0] + inward[i][0] * off[i], p[1] + inward[i][1] * off[i])
            den = dirs[j][0] * dirs[i][1] - dirs[j][1] * dirs[i][0]
            if abs(den) < 1e-3:                                  # in line (a split edge; float32 noise)
                new.append(b if off[i] >= off[j] else a)         # the deeper offset
                continue
            t = ((b[0] - a[0]) * dirs[i][1] - (b[1] - a[1]) * dirs[i][0]) / den
            new.append((a[0] + dirs[j][0] * t, a[1] + dirs[j][1] * t))
        mv = [off[i] > 0 or off[i - 1] > 0 or off[(i + 1) % k] > 0 for i in range(k)]
        for i in range(k):
            a, b = new[i], new[(i + 1) % k]
            if mv[i] and (b[0] - a[0]) * dirs[i][0] + (b[1] - a[1]) * dirs[i][1] < -1e-6:
                return f"{nm[i]} would turn round"
        old_loops.append(pts)
        new_loops.append(new)
        moved.append(mv)
        names.append(nm)

    def cross(o_, a, b):
        return (a[0] - o_[0]) * (b[1] - o_[1]) - (a[1] - o_[1]) * (b[0] - o_[0])

    segs = []                                                    # (min x, max x, loop, i, a, b, moved)
    for li, new in enumerate(new_loops):
        k = len(new)
        for i in range(k):
            a, b = new[i], new[(i + 1) % k]
            segs.append((min(a[0], b[0]), max(a[0], b[0]), li, i, a, b, moved[li][i]))
    segs.sort(key=lambda s_: s_[0])                              # sweep along x: only overlapping spans meet
    for x in range(len(segs)):
        _, hi, l1, i1, a, b, m1 = segs[x]
        for y in range(x + 1, len(segs)):
            lo2, _, l2, i2, c, d, m2 = segs[y]
            if lo2 > hi:
                break
            if not (m1 or m2):
                continue
            if l1 == l2:
                k = len(new_loops[l1])
                if (i2 - i1) % k in (1, k - 1):
                    continue
            if max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
                continue
            if cross(a, b, c) * cross(a, b, d) < -1e-12 and cross(c, d, a) * cross(c, d, b) < -1e-12:
                return f"{names[l1][i1]} and {names[l2][i2]} would cross"

    def inside(p, poly):
        hit = False
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
        return hit
    for la in range(len(loops)):                                 # a hole grown past the outline
        for lb in range(len(loops)):
            if la != lb and inside(old_loops[la][0], old_loops[lb]) != inside(new_loops[la][0], new_loops[lb]):
                return f"the loop of {names[la][0]} would meet the loop of {names[lb][0]}"
    return None


def _miter_point(v, e_prev_start, e_next_end, n, t_prev, t_next):
    """Where the inward offset lines of the two loop edges at corner `v` meet (in the plane with
    normal `n`): the point the bevel slides the corner to."""
    d1 = (v.co - e_prev_start.co)
    d2 = (e_next_end.co - v.co)
    if d1.length == 0 or d2.length == 0:
        return None
    d1, d2 = d1.normalized(), d2.normalized()
    i1, i2 = n.cross(d1).normalized(), n.cross(d2).normalized()     # left of travel: inside
    p1, p2 = v.co + i1 * t_prev, v.co + i2 * t_next
    c = d1.cross(d2).dot(n)
    if abs(c) < 1e-3:                                                # in line
        return v.co + (i1 + i2).normalized() * max(t_prev, t_next)
    s_ = (p2 - p1).cross(d2).dot(n) / c
    return p1 + d1 * s_


def _simple_polygon(pts):
    """True when the 2D polygon does not cross itself (O(n^2), faces are small)."""
    k = len(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    for i in range(k):
        a, b = pts[i], pts[(i + 1) % k]
        for j in range(i + 2, k):
            if i == 0 and j == k - 1:
                continue
            c, d = pts[j], pts[(j + 1) % k]
            if cross(a, b, c) * cross(a, b, d) < -1e-12 and cross(c, d, a) * cross(c, d, b) < -1e-12:
                return False
    return True


def _inner_edges(v, region):
    """The edges at `v` with a face of the region (a set, or a test) on both sides."""
    inside = region if callable(region) else region.__contains__
    return [e for e in v.link_edges if len(e.link_faces) == 2 and all(inside(f) for f in e.link_faces)]


def _thin_fans(bm, regions, offsets):
    """Dissolve the flat edges inside a face that fan out from a corner between two chosen
    edges, where more than one leaves it (bmesh keeps those a face with a hole needs).
    Returns how many were asked to go."""
    kill = set()
    for _, loops, region in regions:
        for loop in loops:
            for i in range(len(loop)):
                prev, nxt = loop[i - 1], loop[i]
                if offsets[prev[0].index] > 0 and offsets[nxt[0].index] > 0:
                    inner = _inner_edges(nxt[1], region)
                    if len(inner) > 1:
                        kill.update(inner)
    if kill:
        bmesh.ops.dissolve_edges(bm, edges=list(kill), use_verts=False, use_face_split=False)
    return len(kill)


def _seg_point_dist(p, a, b):
    ax_, ay_ = b[0] - a[0], b[1] - a[1]
    L2 = ax_ * ax_ + ay_ * ay_
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax_ + (p[1] - a[1]) * ay_) / L2))
    return math.hypot(p[0] - a[0] - ax_ * t, p[1] - a[1] - ay_ * t)


def _straighten_bridges(bm, regions, offset_of, reaches=(1.25, 1.1, 1.03, 1.01)):
    """A face with a hole is split by the cut into faces joined along edges from the hole's rim
    to the outline. Where such an edge leaves a corner between two chosen edges at a shallow
    angle, the bevel slides the corner along it far past the round (a slit across the face).
    The edges inside the face at such a corner are cut near it and their new ends welded into
    one point on the corner's miter line, a little farther than the round goes (the first of
    `reaches` x that stays clear of every other round's strip, so the point never lands past
    another round's tangent line), joined to the corner by one edge: the bevel then slides along
    the miter, as on a clean ring. A corner with no clear point, or whose faces would cross
    themselves, is left alone (the check after the bevel decides). Returns how many corners
    were straightened."""
    done = 0
    for f0, loops, _ in regions:
        n = f0.normal.normalized()
        ax = n.orthogonal().normalized()
        ay = n.cross(ax)
        p0 = f0.verts[0].co.copy()

        def to2(co, ax=ax, ay=ay):
            return (co.dot(ax), co.dot(ay))
        strips = [(to2(sg[1].co), to2(sg[2].co), offset_of(sg[0]), sg[1], sg[2])
                  for lp in loops for sg in lp if offset_of(sg[0]) > 0]
        cell = max((st[2] for st in strips), default=1.0) * 3 or 1.0
        grid = {}
        for j, (a2, b2, _, _, _) in enumerate(strips):
            for gx in range(int(math.floor(min(a2[0], b2[0]) / cell)), int(math.floor(max(a2[0], b2[0]) / cell)) + 1):
                for gy in range(int(math.floor(min(a2[1], b2[1]) / cell)), int(math.floor(max(a2[1], b2[1]) / cell)) + 1):
                    grid.setdefault((gx, gy), []).append(j)

        def clear(q, v, strips=strips, grid=grid, cell=cell):
            q2 = to2(q)
            gx, gy = int(math.floor(q2[0] / cell)), int(math.floor(q2[1] / cell))
            near = {j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((gx + dx, gy + dy), ())}
            return all(_seg_point_dist(q2, strips[j][0], strips[j][1]) >= strips[j][2] * 0.999
                       for j in near if v not in (strips[j][3], strips[j][4]))

        def region(f, n=n, p0=p0):                       # the region by its plane: cuts below add faces
            return f.is_valid and f.normal.dot(n) > FLAT_COS and abs((f.verts[0].co - p0).dot(n)) < 1e-4
        for loop in loops:
            k = len(loop)
            for i in range(k):
                prev, nxt = loop[i - 1], loop[i]
                v = nxt[1]
                if not (prev[0].is_valid and nxt[0].is_valid and v.is_valid):
                    continue
                t_prev, t_next = offset_of(prev[0]), offset_of(nxt[0])
                if t_prev <= 0 or t_next <= 0:
                    continue
                inner = _inner_edges(v, region)
                if not inner:
                    continue
                m = _miter_point(v, prev[1], nxt[2], n, t_prev, t_next)
                if m is None:
                    continue
                target = next((v.co + (m - v.co) * r for r in reaches if clear(v.co + (m - v.co) * r, v)), None)
                if target is None:
                    continue
                d = (target - v.co).length
                if any(e.calc_length() <= d * 1.01 for e in inner):
                    continue
                def flat(f):
                    return [((w.co - target).dot(ax), (w.co - target).dot(ay)) for w in f.verts]
                ends = []
                for e in inner:
                    _, nv = bmesh.utils.edge_split(e, v, min(0.5, d / e.calc_length()))
                    ends.append(nv)
                for f in list(v.link_faces):                     # a face between two cut edges: cut off its corner
                    mine = [w for w in f.verts if w in ends]
                    if len(mine) == 2 and region(f):
                        bmesh.utils.face_split(f, mine[0], mine[1])
                ends[0].co = target
                if len(ends) > 1:
                    bmesh.ops.weld_verts(bm, targetmap={w: ends[0] for w in ends[1:]})
                q = ends[0]
                faces = [f for f in q.link_faces if f.normal.dot(n) > FLAT_COS]
                for f in faces:
                    f.normal_update()
                if all(len(set(f.verts)) == len(f.verts) >= 3 and _simple_polygon(flat(f)) and f.normal.dot(n) > 0
                       for f in faces) and all(e.is_manifold for e in q.link_edges):
                    done += 1
    return done


def _tri2_overlap(t1, t2, eps=1e-6):
    """True when two 2D triangles share more than an edge or a point (separating axis test)."""
    for tri in (t1, t2):
        for i in range(3):
            (x1, y1), (x2, y2) = tri[i], tri[(i + 1) % 3]
            nx, ny = y2 - y1, x1 - x2
            L = math.hypot(nx, ny)
            if L == 0:
                continue
            nx, ny = nx / L, ny / L
            p1 = [x * nx + y * ny for x, y in t1]
            p2 = [x * nx + y * ny for x, y in t2]
            if max(p1) <= min(p2) + eps or max(p2) <= min(p1) + eps:
                return False
    return True


def self_intersections(obj):
    """How many pairs of the mesh's triangles cross each other, or overlap in one plane (a flap
    folded flat onto its neighbour); pairs that share a corner are not counted: 0 for a sound
    solid. validate.py does not look for this."""
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm, epsilon=0.0)
    n = 0
    for a, b in tree.overlap(tree):
        if a < b and not (set(bm.faces[a].verts) & set(bm.faces[b].verts)):
            n += 1
    planes = {}                                            # coplanar overlaps: the BVH test misses them
    for f in bm.faces:
        a, b, c = (v.co for v in f.verts)
        nrm = (b - a).cross(c - a)
        if nrm.length < 1e-12:
            continue
        nrm.normalize()
        if nrm.x < 0 or (nrm.x == 0 and (nrm.y < 0 or (nrm.y == 0 and nrm.z < 0))):
            nrm = -nrm
        key = (round(nrm.x, 4), round(nrm.y, 4), round(nrm.z, 4), round(nrm.dot(a), 3))
        planes.setdefault(key, []).append(f)
    for fs in planes.values():
        if len(fs) < 2:
            continue
        nrm = fs[0].normal.normalized()
        ax = nrm.orthogonal().normalized()
        ay = nrm.cross(ax)
        items = []
        for f in fs:
            t2 = [(v.co.dot(ax), v.co.dot(ay)) for v in f.verts]
            items.append((min(p[0] for p in t2), max(p[0] for p in t2), t2, f))
        items.sort(key=lambda it: it[0])
        for i in range(len(items)):
            lo, hi, t1, f1 = items[i]
            for j in range(i + 1, len(items)):
                lo2, _, t2, f2 = items[j]
                if lo2 >= hi:
                    break
                if set(f1.verts) & set(f2.verts):
                    continue
                if _tri2_overlap(t1, t2):
                    n += 1
    bm.free()
    return n


def _face_depth(face, edge):
    """How far the face reaches away from the edge, in its own plane (mm): the room a fillet's
    tangent line has on that face."""
    a, b = edge.verts[0].co, edge.verts[1].co
    d = (b - a)
    if d.length == 0:
        return 0.0
    d = d.normalized()
    return max(((v.co - a) - d * (v.co - a).dot(d)).length for v in face.verts)


def fillet(obj, radius, edges=None, segments=None, apply=True):
    """Round edges with a true `radius` in mm: the given edge indices (from `edges(...)`), or
    every sharp edge off the bed. Unlike `bevel`, whose width is Blender's offset (the radius
    only on a 90 degree edge), each edge's offset comes from the angle of its faces
    (offset = radius / tan(a / 2), a the angle between the faces: a 120 degree edge needs
    0.58 x radius), so every edge gets the same radius; a non-90-degree edge's arc is within
    1.5 % of the radius (Blender's profile), its tangent lines exact. Segments default to the
    circle rule (`circle_segments(radius)` per full turn). The object's scale is baked first.
    Refused, before anything is changed, when a face next to an edge is narrower than the
    fillet reaches into it: the facets of a curved face (a fillet along a cylinder's side
    cannot be rounded on its facets). Round such an edge in the 2D profile instead
    (`round_profile`), or build that part with parts.py and bring it in (`from_manifold`).
    Also refused before any change: an edge sharper than 90 degrees, and rounds that would
    meet on a flat face (its outline, holes included, inset by each round's reach). A cut
    leaves its flat faces split along edges from a hole's rim; those at a rounded corner are
    turned onto the corner's miter first, or the bevel would run along them. After the bevel
    the result is checked for zero-area triangles, non-manifold edges and faces that cross
    each other (a round's end meeting another round, a split edge that passes near another
    hole); any of them puts the object back as it was and raises."""
    require_blender()
    if radius <= 0:
        raise ValueError("fillet radius must be positive")
    if tuple(obj.scale) != (1.0, 1.0, 1.0):
        apply_transform(obj)
    elif obj.modifiers:
        apply_modifiers(obj)
    chosen = set(edges if edges is not None else _edges(obj))
    if not chosen:
        raise ValueError(f"fillet on '{obj.name}': no edge chosen (edges() found no sharp edge off the bed)")
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    layer = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
    bm.edges.ensure_lookup_table()                     # (a new layer moves the elements: add it first)
    offsets = [0.0] * len(bm.edges)
    turn = 0.0
    for i in sorted(chosen):
        if i < 0 or i >= len(bm.edges):
            bm.free()
            raise ValueError(f"fillet on '{obj.name}': edge {i} does not exist (take indices from edges() on this object)")
        e = bm.edges[i]
        if len(e.link_faces) != 2:
            bm.free()
            raise ValueError(f"fillet on '{obj.name}': edge {i} is not between two faces")
        phi = e.calc_face_angle(0.0)                 # the turn of the normal across the edge
        if phi < 1e-6:
            continue
        if phi > math.radians(90.5):
            mid = (e.verts[0].co + e.verts[1].co) / 2
            bm.free()
            raise ValueError(f"fillet on '{obj.name}': edge {i} (near {tuple(round(c, 2) for c in mid)}) is sharper than "
                             f"90 degrees ({180 - math.degrees(phi):.0f} between its faces); Blender's profile there is "
                             "no circle (up to +75 % at 30 degrees). Round it in the 2D profile (round_profile, then "
                             "prism)")
        t = radius / math.tan((math.pi - phi) / 2)
        room = min(_face_depth(f, e) for f in e.link_faces)
        if t > room + 1e-6:
            mid = (e.verts[0].co + e.verts[1].co) / 2
            bm.free()
            raise ValueError(f"fillet of {radius} mm on '{obj.name}': at edge {i} (near {tuple(round(c, 2) for c in mid)}) "
                             f"it reaches {t:.3f} mm into a face only {room:.3f} mm wide, the facets of a curved face. "
                             "Round it in the 2D profile (round_profile, then prism) or build it with parts.py and "
                             "from_manifold")
        offsets[i] = t
        turn = max(turn, phi)
    # Two fillets on one face must not meet: each eats a strip t wide into the face, from the
    # tangent line inward. The face's outline offset inward by every chosen edge's t must stay a
    # proper outline (no edge turned round, no crossing): a slab's two sides 3 mm apart cannot
    # take two 2 mm rounds, a rim's facets or a hexagon's sides can, as long as the inset fits.
    regions = _flat_regions(bm, offsets)
    for f, loops, _ in regions:
        bad = _inset_fault(f.normal, loops)
        if bad:
            at = tuple(round(c, 2) for c in f.calc_center_median())
            bm.free()
            raise ValueError(f"fillet of {radius} mm on '{obj.name}': the rounds on the flat face near {at} would "
                             f"overlap ({bad}). A smaller radius, or round that face's edges in the 2D profile")
    widest = max(offsets)
    if widest <= 0:
        bm.free()
        raise ValueError(f"fillet on '{obj.name}': the chosen edges are flat (their faces do not meet at an angle)")
    segments = segments or max(2, math.ceil(turn / (2 * math.pi) * circle_segments(radius)))
    for e in bm.edges:
        e[layer] = offsets[e.index] / widest
    if _thin_fans(bm, regions, offsets):                  # indices moved: read the offsets back from the weights
        bm.edges.index_update()
        bm.edges.ensure_lookup_table()
        offsets = [e[layer] * widest for e in bm.edges]
        regions = _flat_regions(bm, offsets)
    straightened = _straighten_bridges(bm, regions, lambda e: e[layer] * widest)
    shared = me if me.users > 1 else None                 # a linked duplicate keeps its mesh as it is
    if shared:
        me = shared.copy()
        me[TAG] = True
        obj.data = me
        backup = None
    else:
        backup = me.copy()                                 # a refusal after the bevel puts this back
    bm.to_mesh(me)
    bm.free()
    me.update()
    mod = obj.modifiers.new("fillet", "BEVEL")
    mod.offset_type = "OFFSET"
    mod.width = widest
    mod.segments = segments
    mod.profile = 0.5
    mod.limit_method = "WEIGHT"
    mod.use_clamp_overlap = False                  # a clamped fillet is a smaller radius than asked
    mod.miter_outer = "MITER_ARC"
    if apply:
        apply_modifiers(obj)
        me = obj.data
        if me.attributes.get("bevel_weight_edge"):
            me.attributes.remove(me.attributes["bevel_weight_edge"])
        weld_degenerate(me)                                # two tangent lines that meet (a full round)
        bad, nm = fix_slivers(me), nonmanifold_edges(obj)
        cross = 0 if bad or nm else self_intersections(obj)    # the deciding check: a weld cannot hide it
        if bad or nm or cross:
            name = me.name                                 # refused: the object is as it was
            obj.data = shared or backup
            bpy.data.meshes.remove(me)
            if backup:
                backup.name = name
            what = (f"{cross} pairs of faces that cross each other" if cross else
                    f"{bad} zero-area triangles and {nm} non-manifold edges")
            raise ValueError(f"fillet of {radius} mm on '{obj.name}' left {what}: two fillets (or a fillet and a "
                             "feature) overlap, or the cut left the face split along edges the round would run across. "
                             "Reduce the radius, fillet before the cut that is in its way, or put the round into the "
                             "cut's own tool (a profile with the round, round_profile, or a parts.py tool through "
                             "from_manifold)")
    if backup:
        bpy.data.meshes.remove(backup)
    LOG.append(f"fillet '{obj.name}': radius {radius} mm on {sum(1 for o in offsets if o)} edges, {segments} segments"
               + (f", {straightened} rim corners straightened" if straightened else ""))
    return obj


def chamfer(obj, width, angle=30.0, bed=False, apply=True):
    """A 45 degree chamfer of `width` on every qualifying edge (bevel with one segment)."""
    return bevel(obj, width, segments=1, angle=angle, bed=bed, apply=apply)


def bed_chamfer(obj, height=0.4, run=None):
    """Chamfer the edges that touch the bed (design.md: a chamfer, never a fillet, hides the
    elephant foot), cut into the body: its bottom faces are inset by `run` and the original
    bottom ring is lifted by `height`, so the overall size does not change. `run` defaults to
    0.9 x height: the band is steeper than 45 degrees and P2 never counts it. Works on any
    bottom outline; applied at once (modifiers and the object's transform are applied first,
    so a part rotated into its print orientation is chamfered where it meets the bed)."""
    require_blender()
    if height <= 0:
        raise ValueError("bed chamfer height must be positive")
    run = height * BED_CHAMFER_RUN if run is None else run
    if run <= 0 or run > height:
        raise ValueError("bed chamfer run must be positive and at most the height (steeper than 45 deg)")
    apply_transform(obj)                    # the bed is world z: a rotated or moved part is baked first
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


def _glyph_outline(text_, font, resolution, digits=4):
    """The flat outline of `text_` at size 1 (Blender's size is the em size): the sorted XY
    vertices, rounded to `digits` (None: exact) so two outlines can be compared."""
    cu = bpy.data.curves.new("_glyph", "FONT")
    cu.body = text_
    cu.size = 1.0
    cu.resolution_u = resolution
    if font is not None:
        cu.font = font
    ob = bpy.data.objects.new("_glyph", cu)
    scene().collection.objects.link(ob)
    me = evaluated_mesh(ob)
    if digits is None:
        pts = sorted((v.co.x, v.co.y) for v in me.vertices)
    else:
        pts = sorted((round(v.co.x, digits), round(v.co.y, digits)) for v in me.vertices)
    bpy.data.meshes.remove(me)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return pts


def _outline_box(pts):
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)) if pts else None


def missing_glyphs(string, font=None, resolution=6):
    """[(character, 'U+XXXX')] of the distinct non-space characters of `string` that the font
    cannot draw: their outline is the font's .notdef (probed with NOTDEF_PROBE, a code point
    no font maps) or empty. The built-in font falls back to Blender's other fonts first, so a
    character one of them covers is fine; what reaches the last-resort font (a box with the
    script's name, same frame for every block) is missing. A format character (Unicode
    category Cf: zero-width space, soft hyphen) that draws nothing is not missing."""
    require_blender()
    fnt = load_font(font) if isinstance(font, str) else font
    probe = _glyph_outline(NOTDEF_PROBE, fnt, resolution)
    probe_box = _outline_box(probe)
    out = []
    for ch in dict.fromkeys(string):                    # distinct, in order of first appearance
        if ch.isspace():
            continue
        pts = _glyph_outline(ch, fnt, resolution)
        if not pts and unicodedata.category(ch) == "Cf":
            continue                                    # a format character (zero-width space, soft hyphen) has no ink
        if not pts or pts == probe or _outline_box(pts) == probe_box:
            out.append((ch, f"U+{ord(ch):04X}"))
    return out


def _missing_glyph_error(string, missing, font_name):
    what = ", ".join(f"{ch!r} ({cp})" for ch, cp in missing)
    return ValueError(f"text {string!r}: the font ({font_name}) cannot draw {what}; it would print a placeholder box. "
                      "Use a font that covers this script (for Korean/CJK e.g. Noto Sans CJK), passed as font=path")


def _cap_ratio(font, resolution):
    """Height of a capital H at size 1 for this font (Blender's size is the em size); the em
    box itself (1.0, with a LOG note) when the font has no H (a font of another script)."""
    pts = _glyph_outline("H", font, resolution, digits=None)
    if pts and not missing_glyphs("H", font, resolution):
        box = _outline_box(pts)
        ratio = box[3] - box[1]
        if ratio > 0:
            return ratio
    LOG.append(f"font {'built-in' if font is None else font.name} has no 'H': `height` is taken as the em size, "
               "read the glyphs' real box from the text note")
    return 1.0


def load_font(path):
    """A font file loaded and packed into the .blend, its path reduced to its base name. A
    font this module already loaded from a file of the same name and size is reused, so a
    generator that calls text() several times packs one copy."""
    require_blender()
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    neutral, size = neutral_filepath(path), os.path.getsize(path)
    for font in bpy.data.fonts:
        packed = getattr(font, "packed_file", None)
        if font.get(TAG) and font.filepath == neutral and packed is not None and packed.size == size:
            return font
    font = bpy.data.fonts.load(os.path.abspath(path))
    font.pack()
    font.filepath = neutral
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
    try:
        for o in objs[1:]:
            boolean(base, o, "union")
    except ValueError as exc:
        # Letters that kiss along an edge can leave the union with slivers or open edges: the
        # caller tightens the spacing and tries again, so nothing of this attempt may stay.
        for o in objs:
            try:
                _remove_object(o)
            except ReferenceError:              # a tool the union already consumed
                pass
        raise _UnionError(str(exc)) from exc
    base.name = name
    base.data.name = name
    return base, pieces, touching


class _UnionError(ValueError):
    """The union of touching glyph pieces failed (slivers or open edges)."""


def text(string, height, depth, font=None, name="text", align="CENTER", resolution=6, collection=None):
    """Text as one mesh object: cap height `height` mm (the em size when the font has no 'H',
    noted in LOG), `depth` mm tall standing on z = 0, centred on the origin (align CENTER |
    LEFT | RIGHT). Blender's built-in font, or a font file (packed into the .blend once per
    file). A character the font cannot draw (`missing_glyphs`) raises instead of printing a
    placeholder box. Every glyph is welded on its own (welding the whole string would merge
    touching letters such as "AA" into an open mesh); glyphs whose outlines touch are unioned
    with the Manifold solver, and letters that only kiss along an edge (the feet of "AA", the
    tops of "VV") get the character spacing tightened by 1 % steps, 5 % at most, until they
    overlap and the union is one closed body; the rest stay separate bodies. The LOG note gives
    the glyphs' real box (for `expect`) and the body count (for `shells`). One body per
    separate glyph piece (a Hangul syllable can be several, the dot of an i is one): emboss them
    onto a face with `boolean(face_part, text_obj, "union")`, or give the part's `_parts` entry
    `shells` from that count (parts.md)."""
    require_blender()
    if not string:
        raise ValueError("empty text")
    if not string.strip():
        raise ValueError("text holds only spaces")
    if height <= 0 or depth <= 0:
        raise ValueError("text needs a positive height and depth")
    fnt = load_font(font) if isinstance(font, str) else font
    font_name = "built-in" if fnt is None else fnt.name
    missing = missing_glyphs(string, fnt, resolution)
    if missing:
        raise _missing_glyph_error(string, missing, font_name)
    ratio = _cap_ratio(fnt, resolution)
    size = height / ratio
    spacing = 1.0
    for attempt in range(6):
        try:
            obj, pieces, touching = _text_mesh(string, size, depth, fnt, resolution, align, name, spacing, collection)
        except _UnionError:                     # kissing letters: slivers or open edges, nothing left behind
            obj, bad = None, 1
        else:
            bad = _welded_nonmanifold(obj) if touching else 0
        if not bad:
            break
        if obj is not None:
            _remove_object(obj)
        spacing = round(spacing - 0.01, 2)
    else:
        raise ValueError(f"text {string!r}: letters touch only along an edge or a point, and even at {spacing + 0.01:.2f} "
                         "character spacing their union is not one closed body; put the text on a plate "
                         "(union with it) or choose a font or spacing where the letters either overlap or stand apart")
    lo, hi, _tris = world_bbox(obj)
    bodies = body_count(obj)
    note = (f"text {string!r}: {'cap height' if ratio != 1.0 else 'em size'} {height} mm (font size {size:.3f}), "
            f"depth {depth} mm, box {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f} x {hi[2] - lo[2]:.2f} mm "
            f"(x {lo[0]:.2f}..{hi[0]:.2f}, y {lo[1]:.2f}..{hi[1]:.2f}), {len(pieces)} glyph pieces, "
            f"{bodies} separate {'body' if bodies == 1 else 'bodies'}, font {font_name}")
    if touching:
        note += f", {len(touching)} pair(s) with overlapping boxes unioned"
        if spacing < 1.0:
            note += f" after tightening the character spacing to {spacing:.2f} (letters that only kissed along an edge)"
    LOG.append(note)
    return obj


def body_count(obj):
    """Separate bodies of the object's mesh (connected by shared edges, as validate.py's M5
    counts shells)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    n = len(_components(bm))
    bm.free()
    return n

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


def _export_copy(obj, name):
    """The mesh that goes into the STL: the part evaluated (modifiers applied), in world
    coordinates, its vertices snapped to the WELD grid and merged where they meet. That is how
    validate.py welds (each coordinate rounded to a multiple of WELD), so the vertices it will
    treat as one are one here too, and the seam a boolean leaves where a tool conforms to a
    face does not become a zero-area triangle in the STL. The shift is at most WELD / 2 per axis.
    Returns (temporary object, vertices welded, non-manifold edges); raises when zero-area
    triangles remain after the weld (the STL would fail M3, then M1)."""
    me = evaluated_mesh(obj)
    me[TAG] = True
    bm = bmesh.new()
    bm.from_mesh(me)
    mw = _world(obj)
    bm.transform(mw)                        # the grid is the STL's: world millimetres
    if mw.determinant() < 0:                # a mirrored part: keep its faces pointing out
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    before = len(bm.verts)
    for v in bm.verts:
        v.co = [round(c / WELD) * WELD for c in v.co]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD * 1e-3)
    welded = before - len(bm.verts)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.to_mesh(me)
    bm.free()
    me.update()
    bad = degenerate_triangles(me)
    if bad:
        bpy.data.meshes.remove(me)
        raise ValueError(f"part '{name}': {bad} zero-area triangles remain after welding on the {WELD} mm grid "
                         "(the STL would fail M3, and M1 once they are dropped): collinear slivers where a cut grazes "
                         "an edge or crosses a fan of thin triangles, or an arc sampled so finely that its sag between "
                         "points is under the grid (a radius of several hundred mm at chords under 0.5 mm: sample it "
                         "coarser); move the cut, or give that face ring topology")
    tmp = bpy.data.objects.new(f"_export_{name}", me)   # identity transform: the mesh is in world mm already
    tmp[TAG] = True
    scene().collection.objects.link(tmp)
    return tmp, welded, nm


def export_parts(out, names=None):
    """One binary STL per registered part into `out` (modifiers applied, vertices snapped to the
    WELD grid and merged as validate.py merges them, 1 unit = 1 mm, scene unit off, axes unchanged).
    Returns the part list with boxes in mm, triangles and bytes; refuses a part whose welded
    mesh still holds zero-area triangles."""
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
        t0 = time.time()
        tmp, welded, nm = _export_copy(obj, n)
        try:
            _deselect_all()
            tmp.select_set(True, view_layer=_view_layer())
            _view_layer().objects.active = tmp
            with _ctx():
                bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=False, global_scale=1.0,
                                      use_scene_unit=False, ascii_format=False, forward_axis="Y", up_axis="Z",
                                      check_existing=False)
            lo, hi, tris = world_bbox(tmp)
        finally:
            _remove_object(tmp)
        entry = {"name": n, "stl": path, "bbox_min_mm": [round(v, 4) for v in lo],
                 "bbox_mm": [round(h - l, 4) for l, h in zip(lo, hi)], "triangles": tris,
                 "bytes": os.path.getsize(path), "seconds": round(time.time() - t0, 3),
                 "object": _PARTS[n]["group"], "role": _PARTS[n]["role"]}
        if welded:
            entry["welded_vertices"] = welded
            LOG.append(f"export '{n}': {welded} vertices welded on the {WELD} mm grid (as validate.py welds them)")
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


def _smooth_by_angle(obj, angle=SMOOTH_ANGLE):
    """Shade the object's mesh smooth across edges whose faces meet flatter than `angle`
    (a cylinder's facets blend, a box's corners stay crisp), for the render only: returns a
    function that puts the mesh's own smoothness and sharp edges back."""
    import numpy as np
    me = obj.data
    if me is None or not hasattr(me, "polygons") or not len(me.polygons) or not len(me.edges):
        return lambda: None
    old_faces = np.empty(len(me.polygons), dtype=bool)
    me.polygons.foreach_get("use_smooth", old_faces)
    attr = me.attributes.get("sharp_edge")
    old_edges = None
    if attr is not None and attr.domain == "EDGE" and attr.data_type == "BOOLEAN":
        old_edges = np.empty(len(me.edges), dtype=bool)
        attr.data.foreach_get("value", old_edges)
    bm = bmesh.new()
    bm.from_mesh(me)
    lim = math.radians(angle)
    sharp = [e.calc_face_angle(0.0) >= lim for e in bm.edges]      # bmesh keeps the mesh's edge order
    bm.free()
    if len(sharp) != len(me.edges):
        return lambda: None
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), dtype=bool))
    if attr is None:
        attr = me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    attr.data.foreach_set("value", sharp)
    me.update()

    def restore():
        me.polygons.foreach_set("use_smooth", old_faces)
        current = me.attributes.get("sharp_edge")
        if old_edges is not None and current is not None:
            current.data.foreach_set("value", old_edges)
        elif current is not None:
            me.attributes.remove(current)
        me.update()
    return restore


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
        sh.cavity_valley_factor = SSAO_VALLEY
        # The world-space cavity darkens a pocket's floor by what surrounds it within
        # matcap_ssao_distance: Blender's default is 0.2 units, 0.2 mm here, so a blind pocket
        # seen head-on (a keyhole in the BOTTOM view) stayed invisible. render_views scales the
        # distance to the part; the attenuation keeps the effect over that distance.
        sc.display.matcap_ssao_attenuation = SSAO_ATTENUATION
        # Blender 4.x leaves the world-space cavity out of a Workbench render (any distance):
        # shadows stand in there, at the price of lit faces reading about 6 % darker.
        shadows = tuple(bpy.app.version[:2]) < SSAO_RENDERS_FROM
        sh.show_shadows = shadows
        if shadows:
            sh.shadow_intensity = SHADOW_INTENSITY
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
    smooth_undo = [_smooth_by_angle(o) for o in objects]
    old_ssao = sc.display.matcap_ssao_distance
    sc.display.matcap_ssao_distance = min(SSAO_MAX, max(SSAO_MIN, SSAO_RATIO * max(size_mm)))   # see _setup_engine
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
            lab.hide_render = True                  # or the next view draws it mirrored (TOP in the BOTTOM tile)
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
        for restore in reversed(smooth_undo):    # last in, first out: objects that share a mesh unwind in turn
            restore()
        sc.camera = old_camera
        sc.display.matcap_ssao_distance = old_ssao
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
    """Python files the build imported from the generator's folder, from here or from the
    skill's scripts folder (parts.py through from_manifold), hashed into the manifest by
    build.py, plus this file."""
    main = sys.modules.get("__main__")
    roots = {os.path.normcase(os.path.dirname(os.path.abspath(__file__))), os.path.normcase(SKILL_SCRIPTS)}
    if getattr(main, "__file__", None):
        roots.add(os.path.normcase(os.path.dirname(os.path.abspath(main.__file__))))
    deps = {os.path.abspath(__file__), *_IMPORTED}
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
