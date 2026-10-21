"""references/engines/blender_builder.py: the pure helpers import and work without Blender; with
the `bpy` module the Blender calls are run for real in a subprocess (importing bpy loads most of
Blender, so it stays out of the test process itself) and their STLs go through validate.py.
Every subprocess starts from Blender's default file (a Cube, a Camera, a Light in "Scene"): the
module must build next to that, never reset it, and the tests look only at what it tagged."""
import glob
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.util import find_spec, module_from_spec, spec_from_file_location

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENGINES = os.path.join(ROOT, "references", "engines")
PATH = os.path.join(ENGINES, "blender_builder.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import validate  # noqa: E402

HAS_BPY = find_spec("bpy") is not None


def load():
    spec = spec_from_file_location("blender_builder_under_test", PATH)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_in_blender(code, cwd=None, timeout=300):
    """Run `code` in the Python that has bpy, with blender_builder importable; returns the JSON
    the code printed after '@@'."""
    prelude = ("import os, sys, json\n"
               f"sys.path.insert(0, {ENGINES!r})\n"
               f"sys.path.insert(0, {os.path.join(ROOT, 'scripts')!r})\n"
               "import blender_builder as bb\n"
               "import bpy\n"
               "def emit(**kw):\n"
               "    print('@@' + json.dumps(kw, default=str))\n"
               "def ours():\n"
               "    return sorted(o.name for o in bpy.data.objects if o.get(bb.TAG))\n")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", prelude + code], capture_output=True, encoding="utf-8",
                       errors="replace", env=env, timeout=timeout, cwd=cwd)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("@@")]
    if r.returncode != 0 or not lines:
        raise AssertionError(f"blender code failed (exit {r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-2500:]}")
    return json.loads(lines[-1][2:])


def check(stl, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        validate.main([stl, "--no-wall-check", *argv])
    doc = json.loads(buf.getvalue())
    return doc["files"][0]


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


GEN = """
def build(p):
    body = bb.box([p["w"], 20, 5], "body")
    bb.part(body, "body")
    return {"body": body}
"""


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
class PureHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bb = load()

    def test_cli_args_take_what_follows_the_double_dash(self):
        ns = self.bb.cli_args(["blender", "--background", "--python", "gen.py", "--", "--params", "p.json",
                               "--out", "o", "--only", "a,b", "--blend", "x.blend"])
        self.assertEqual((ns.cmd, ns.params, ns.out, ns.only, ns.blend, ns.no_blend), ("build", "p.json", "o", "a,b", "x.blend", False))
        ns = self.bb.cli_args(["gen.py", "--params", "p.json", "--out", "o"])            # plain python, no --
        self.assertEqual((ns.cmd, ns.params, ns.out), ("build", "p.json", "o"))
        ns = self.bb.cli_args(["/Applications/Blender.app/Contents/MacOS/Blender", "--out", "o", "--python-use-system-env"])
        self.assertEqual((ns.cmd, ns.out), ("build", "o"))                              # Blender's own flags ignored
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.bb.cli_args(["blender", "--", "--params", "p.json"])                   # --out is required
        ns = self.bb.cli_args(["blender_builder.py", "--", "render", "a.stl", "b.stl", "-o", "r.png", "--views", "iso,top",
                               "--size", "800x600", "--engine", "cycles", "--color", "a=black", "--overwrite"])
        self.assertEqual((ns.cmd, ns.stl, ns.out, ns.views, ns.size, ns.engine, ns.color, ns.overwrite),
                         ("render", ["a.stl", "b.stl"], "r.png", "iso,top", "800x600", "cycles", ["a=black"], True))

    def test_segments_from_the_line_width(self):
        bb = self.bb
        self.assertEqual(bb.segments_for(1.2), 5)                 # pi/2 * 1.2 / 0.45 = 4.19 -> 5
        self.assertEqual(bb.segments_for(0.3), 2)                 # never below 2
        self.assertEqual(bb.segments_for(50.0), bb.MAX_SEGMENTS)  # capped
        self.assertEqual(bb.segments_for(2.0, line_width=0.6), 6)
        with self.assertRaises(ValueError):
            bb.segments_for(0)

    def test_filament_colours_match_whole_names_only(self):
        bb = self.bb
        self.assertEqual(bb.colour_key("Bambu PLA Basic Jade White"), "jadewhite")
        self.assertEqual(bb.colour_key("PLA Matte Mistletoe Green"), "mistletoegreen")
        self.assertEqual(bb.filament_rgb("#ff0000"), (1.0, 0.0, 0.0))
        self.assertEqual(bb.filament_rgb("Bambu PLA Basic Jade White"), (1.0, 1.0, 1.0))
        self.assertEqual(bb.filament_rgb("black"), (0.0, 0.0, 0.0))
        rgb, warning = bb.colour_for("Light Blue")                # not 'blue' by substring: unknown, neutral grey
        self.assertEqual((rgb, "neutral grey" in warning, "approximate" in warning), (bb.NEUTRAL, True, True))
        self.assertEqual(bb.colour_for("Ice Blue")[0], bb.NEUTRAL)
        self.assertEqual(bb.colour_for("blue")[0], bb.hex_rgb(bb.FILAMENTS["blue"]))
        self.assertEqual(bb.filament_rgb("no such colour", default=(0.5, 0.5, 0.5)), (0.5, 0.5, 0.5))
        with self.assertRaises(ValueError):
            bb.filament_rgb("no such colour")
        with self.assertRaises(ValueError):
            bb.hex_rgb("#12345")
        colours, warnings = bb.parse_colors(["lid=black", "box=Ice Blue"], ["box", "lid"])
        self.assertEqual(colours["lid"], (0.0, 0.0, 0.0))
        self.assertEqual(colours["box"], bb.NEUTRAL)             # never a question, never an abort
        self.assertEqual(len(warnings), 1)
        self.assertIn("box: unknown filament colour 'Ice Blue'", warnings[0])
        colours, warnings = bb.parse_colors([], ["box", "lid"])
        self.assertEqual((colours["box"], colours["lid"], warnings), (bb.palette_rgb(0), bb.palette_rgb(1), []))
        with self.assertRaises(ValueError):
            bb.parse_colors(["nope=black"], ["box"])
        self.assertEqual(bb.preview_rgb((0.0, 0.0, 0.0)), (0.15, 0.15, 0.15))    # black lifted a little for the preview
        for c in bb.preview_rgb((1.0, 1.0, 1.0)):                                  # white taken down to 0.9: off the 246 background
            self.assertAlmostEqual(c, bb.LIGHT_MAX)
        self.assertEqual(bb.rgb_hex(bb.preview_rgb(bb.filament_rgb("Jade White"))), "#e6e6e6")
        ivory = bb.preview_rgb(bb.hex_rgb(bb.FILAMENTS["ivorywhite"]))
        self.assertLess(max(ivory), bb.LIGHT_MAX + 0.02)                           # light colours compressed, hue kept
        self.assertGreater(ivory[0], ivory[2])
        self.assertEqual(bb.preview_rgb((0.5, 0.6, 0.7)), (0.5, 0.6, 0.7))         # mid tones untouched
        self.assertEqual(bb.preview_rgb(bb.hex_rgb("#ff6a13")), bb.hex_rgb("#ff6a13"))
        # Blender's colour properties are scene-linear; #rrggbb is sRGB (the standard transfer function).
        self.assertEqual(bb.srgb_to_linear(0.0), 0.0)
        self.assertAlmostEqual(bb.srgb_to_linear(1.0), 1.0)
        self.assertAlmostEqual(bb.srgb_to_linear(0.5), 0.21404, places=5)
        self.assertAlmostEqual(bb.srgb_to_linear(0.04), 0.04 / 12.92)
        self.assertEqual(bb.linear_rgb((1.0, 1.0, 1.0)), (1.0, 1.0, 1.0))
        self.assertEqual(bb.rgb_hex((1.0, 0.0, 0.5)), "#ff0080")

    def test_foreground_bounds(self):
        bb = self.bb
        self.assertFalse(bb.fg_sane(0.0)[0])
        self.assertFalse(bb.fg_sane(0.0003)[0])
        self.assertTrue(bb.fg_sane(0.2)[0])
        ok, note = bb.fg_sane(0.99)                                # a black or missing background
        self.assertFalse(ok)
        self.assertIn("no background", note)
        ok, note = bb.fg_sane(0.2, {"iso": 0.4, "front": 0.0, "right": 0.2, "top": 0.0003})
        self.assertFalse(ok)                                       # a blank view fails though the grid is not blank
        self.assertIn("blank views front, top", note)
        self.assertTrue(bb.fg_sane(0.2, {"iso": 0.4, "front": 0.01})[0])

    def test_caption_box_in_pixels(self):
        """The caption's rectangle, left out of the blank check: from its laid-out bounds in the
        camera frame (bottom-up pixels, 2 px pad), or the whole caption band when not laid out."""
        from types import SimpleNamespace as NS
        bb = self.bb
        corners = [(x, y, 0.0) for x in (0.0, 12.0) for y in (-0.2, 1.0) for _ in (0, 1)]

        def near(box, expect):                                     # within a pixel: edges may land on a boundary
            self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(box, expect)), (box, expect))

        # Landscape: frame 40 x 30 mm in 800 x 600 px (20 px/mm); the text spans 16..256 x 12..36 px.
        lab = NS(location=NS(x=-20.0 + 0.8, y=-15.0 + 0.8), bound_box=corners, data=NS(size=1.4))
        near(bb._label_box(lab, 40.0, 4 / 3, 800, 600), (14, 10, 258, 38))
        flat = NS(location=lab.location, bound_box=[(0.0, 0.0, 0.0)] * 8, data=NS(size=1.4))
        near(bb._label_box(flat, 40.0, 4 / 3, 800, 600), (0, 0, 800, 74))    # not laid out: the caption band
        # Portrait: frame 30 x 40 mm in 300 x 400 px (10 px/mm); the text spans 8..128 x 6..18 px.
        tall = NS(location=NS(x=-15.0 + 0.8, y=-20.0 + 0.8), bound_box=corners, data=NS(size=1.4))
        near(bb._label_box(tall, 40.0, 0.75, 300, 400), (6, 4, 130, 20))
        wide = NS(location=lab.location, bound_box=[(x * 10, y, z) for x, y, z in corners], data=NS(size=1.4))
        self.assertEqual(bb._label_box(wide, 40.0, 4 / 3, 800, 600)[2], 800)     # clamped to the tile

    def test_view_basis_matches_preview(self):
        import preview
        bb = self.bb
        self.assertEqual(bb.VIEWS, preview.VIEWS)
        self.assertEqual(bb.DEFAULT_VIEWS, preview.DEFAULT_VIEWS)
        r, u, f = bb.view_basis(*bb.VIEWS["front"])
        self.assertEqual([round(c, 6) for c in r], [1.0, 0.0, 0.0])
        self.assertEqual([round(c, 6) for c in u], [0.0, 0.0, 1.0])
        self.assertEqual([round(c, 6) for c in f], [0.0, 1.0, 0.0])
        r, u, f = bb.view_basis(*bb.VIEWS["top"])
        self.assertEqual([round(c, 6) for c in r], [1.0, 0.0, 0.0])
        self.assertEqual([round(c, 6) for c in u], [0.0, 1.0, 0.0])
        w, h, cx, cy = bb.projected_extent(bb.box_corners((0, 0, 0), (40, 30, 6)), bb.view_basis(*bb.VIEWS["front"]))
        self.assertEqual((w, h, cx, cy), (40.0, 6.0, 20.0, 3.0))
        self.assertEqual(bb.grid_layout(4), (2, 2))
        self.assertEqual(bb.grid_layout(1), (1, 1))
        self.assertEqual(bb.grid_layout(3), (2, 2))

    def test_forbidden_strings_and_neutral_paths(self):
        bb = self.bb
        out = os.path.abspath(os.path.join(os.sep, "tmp", "some", "out"))     # D:\tmp\some\out on Windows
        forb = bb.forbidden_strings(out)
        self.assertIn(out.encode("utf-8"), forb)
        self.assertTrue(all(len(f) >= 5 for f in forb))
        found = bb.find_forbidden(b"xx " + out.encode("utf-8") + b"/a.stl yy", forb)
        self.assertIn(out.lower() if os.sep == "\\" else out, found)       # case-insensitive on Windows
        self.assertEqual(bb.find_forbidden(b"nothing here", [out.encode("utf-8")]), [])
        self.assertEqual(bb.neutral_filepath("/Users/someone/fonts/Bold.ttf"), "//Bold.ttf")
        self.assertEqual(bb.neutral_filepath("C:\\Users\\someone\\Bold.ttf"), "//Bold.ttf")
        self.assertEqual(bb.neutral_filepath(""), "")

    def test_paths_in_parameters_are_reduced_to_names(self):
        bb = self.bb
        for p in ("/home/someone/fonts/Bold.ttf", "C:\\Users\\someone\\Bold.ttf", "C:/Users/someone/x", "~/fonts/x.ttf",
                  "\\\\server\\share\\x"):
            self.assertTrue(bb.looks_like_path(p), p)
        for t in ("Bold.ttf", "SCOUT", "a/b", "", "x", "7.5"):
            self.assertFalse(bb.looks_like_path(t), t)
        self.assertEqual(bb.scrub_text("/home/someone/fonts/Bold.ttf"), "Bold.ttf")
        self.assertEqual(bb.scrub_text("C:\\Users\\someone\\Bold.ttf"), "Bold.ttf")
        self.assertEqual(bb.scrub_text("SCOUT"), "SCOUT")
        self.assertEqual(bb.prop_value(2.5), 2.5)
        self.assertEqual(bb.prop_value(True), True)
        self.assertEqual(bb.prop_value("/Users/someone/font.ttf"), "font.ttf")
        self.assertEqual(bb.prop_value([1, 2.5]), [1.0, 2.5])
        self.assertEqual(bb.prop_value(["a", "/home/someone/b.ttf"]), '["a", "b.ttf"]')
        self.assertEqual(bb.prop_value({"k": "C:\\\\Users\\\\x\\\\f.ttf"}), '{"k": "f.ttf"}')

    def test_summary_line_and_solver_by_version(self):
        bb = self.bb
        line = bb.summary([{"name": "a"}], blend=None)
        self.assertTrue(line.startswith("@@3DPS "))
        doc = json.loads(line[7:])
        self.assertEqual((doc["schema"], doc["parts"], doc["blend"]), (bb.SCHEMA, [{"name": "a"}], None))
        self.assertEqual(bb.boolean_solver((4, 5, 0)), "MANIFOLD")
        self.assertEqual(bb.boolean_solver((5, 2, 2)), "MANIFOLD")
        self.assertEqual(bb.boolean_solver((4, 4, 9)), "EXACT")

    def test_version_floor_is_four_five(self):
        bb = load()
        bb.bpy = types.SimpleNamespace(app=types.SimpleNamespace(version=(4, 2, 0), version_string="4.2.0"))
        with self.assertRaises(RuntimeError) as cm:
            bb.require_blender()
        self.assertIn("4.5", str(cm.exception))
        self.assertIn("4.2.0", str(cm.exception))
        bb.bpy = types.SimpleNamespace(app=types.SimpleNamespace(version=(4, 5, 14), version_string="4.5.14 LTS"))
        bb.require_blender()                                      # no error at the floor

    def test_blender_calls_refuse_to_run_without_bpy(self):
        bb = self.bb
        if bb.bpy is not None:
            self.skipTest("bpy importable here; the refusal is for machines without it")
        with self.assertRaises(RuntimeError):
            bb.require_blender()
        with self.assertRaises(RuntimeError):
            bb.box([1, 1, 1])


class Profiles(unittest.TestCase):
    """0.6: 2D profiles with true arcs and rounded corners (pure Python, no Blender)."""

    @classmethod
    def setUpClass(cls):
        cls.bb = load()

    def test_arc_and_outline(self):
        bb = self.bb
        a = bb.arc((0, 0), 10, 0, 90)
        self.assertEqual((a.center, a.r), ((0.0, 0.0), 10.0))
        self.assertAlmostEqual(a[0][0], 10)
        self.assertAlmostEqual(a[-1][1], 10)
        self.assertLessEqual(max(math.dist(a[i], a[i + 1]) for i in range(len(a) - 1)), 0.4 + 1e-9)   # the circle rule
        cw = bb.arc((0, 0), 10, 90, -90)                                       # clockwise through 0 deg
        self.assertAlmostEqual(cw[len(cw) // 2][0], 10, delta=0.01)
        pts = bb.outline([(0, 0), (10, 0)], (10, 0), bb.arc((10, 5), 5, -90, 90), (0, 10), (0, 0))
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertNotEqual(pts[-1], (0.0, 0.0))                               # no closing repeat
        self.assertEqual(len(pts), len(set(pts)))

    def test_round_profile_on_straight_corners(self):
        bb = self.bb
        pts = bb.round_profile([(0, 0), (30, 0), (30, 20), (0, 20)], 2.0)
        for cx, cy in ((2, 2), (28, 2), (28, 18), (2, 18)):
            near = [p for p in pts if math.dist(p, (cx, cy)) < 2.5]
            self.assertGreater(len(near), 3)
            self.assertTrue(all(abs(math.dist(p, (cx, cy)) - 2.0) < 1e-9 for p in near))
        self.assertAlmostEqual(min(p[0] for p in pts), 0.0)
        one = bb.round_profile([(0, 0), (30, 0), (30, 20), (0, 20)], 2.0, corners=[1])
        self.assertIn((0.0, 0.0), one)                                         # only corner 1 rounded
        self.assertNotIn((30.0, 0.0), one)
        with self.assertRaises(ValueError) as cm:
            bb.round_profile([(0, 0), (3, 0), (3, 20), (0, 20)], 2.0)           # 4 mm of round on a 3 mm edge
        self.assertIn("overlap", str(cm.exception))

    def test_round_profile_against_an_arc(self):
        """A plate with a half-round ridge: the feet are rounded against the ridge's circle, not
        its facets; a C-ring lip is rounded where the opening meets the ring."""
        bb = self.bb
        ridge = [(0, 0), (40, 0), (40, 3), bb.arc((20, 3), 6, 0, 180), (0, 3)]
        pts = bb.round_profile(ridge, 1.0, corners=[3, 4])
        for c in ((20 + math.sqrt(48), 4.0), (20 - math.sqrt(48), 4.0)):      # 7 mm from the ridge centre, 1 above the plate
            near = [p for p in pts if math.dist(p, c) < 1.0 + 1e-6]
            self.assertGreater(len(near), 3)
            self.assertTrue(all(abs(math.dist(p, c) - 1.0) < 1e-9 for p in near), near)
        r_i, r_o, half, r, zc = 16.45, 19.65, 14.0, 1.0, 19.95
        deg = math.degrees
        a_o = deg(math.atan2(math.sqrt(r_o ** 2 - half ** 2), half))
        a_i = deg(math.atan2(math.sqrt(r_i ** 2 - half ** 2), half))
        c_ring = [bb.arc((0, zc), r_o, -30, a_o), bb.arc((0, zc), r_i, a_i, 180 - a_i - 360),
                  bb.arc((0, zc), r_o, 180 - a_o, 210)]
        lip = bb.round_profile(c_ring, r, corners=[1, 2, 3, 4])
        top = max(p[1] for p in lip)
        self.assertAlmostEqual(top, zc + math.sqrt((r_o - r) ** 2 - (half + r) ** 2) + r, delta=0.002)   # tangent inside the outer circle

    def test_round_profile_shapes_the_review_found_refused(self):
        """Review of 0.6: a D (an arc and its chord: two corners), a Pac-Man (an arc and the centre)
        and a round against a concave arc at a 10 degree corner are valid and are built."""
        bb = self.bb
        d = bb.round_profile([bb.arc((0, 0), 10, 0, 180)], 1.0)
        self.assertGreater(bb._signed_area(d), 0)
        self.assertAlmostEqual(max(p[1] for p in d), 10.0, delta=1e-6)
        pac = bb.round_profile([bb.arc((0, 0), 10, 30, 330), (0, 0)], 0.5)
        self.assertGreater(bb._signed_area(pac), 0)
        a, R = math.radians(10), 10.0
        cy = -R * math.cos(a)
        start = math.degrees(math.atan2(-cy, R * math.sin(a)))
        notch = [(-20, -25), (20, -25), (20, 0), bb.arc((0, cy), R, start, 180 - start - 360), (-20, 0)]
        pts = bb.round_profile(notch, 1.0, corners=[3])
        c = (math.sqrt((R + 1) ** 2 - (-1 - cy) ** 2), -1.0)
        near = [q for q in pts if math.dist(q, c) < 1.0 + 1e-6]
        self.assertGreater(len(near), 2)
        self.assertTrue(all(abs(math.dist(q, c) - 1.0) < 1e-9 for q in near))

    def test_round_profile_turning_edges_are_not_corners(self):
        bb = self.bb
        pts = bb.round_profile([(0, 0), (20, 0), bb.arc((20, 10), 10, -90, 90), (0, 20)], 1.0)
        self.assertTrue(all(p[0] <= 30 + 1e-9 for p in pts))                  # the arc's joints are smooth: left alone
        self.assertTrue(any(abs(p[0]) < 1e-9 and 0.9 < p[1] < 19.1 for p in pts))


# --------------------------------------------------------------------------- #
# With Blender
# --------------------------------------------------------------------------- #
@unittest.skipUnless(HAS_BPY, "bpy module not installed")
class WithBlender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="3dps-bb-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_ten_mm_cube_exports_as_ten_mm_stl(self):
        rep = run_in_blender(f"""
sc = bb.new_scene_mm()
us = sc.unit_settings
cube = bb.box([10, 10, 10], "cube")
bb.part(cube, "cube")
info = bb.export_parts({self.tmp!r})
emit(units=[us.system, us.length_unit, round(us.scale_length, 6)], info=info, version=list(bpy.app.version),
     context_scene=bpy.context.scene.name, build_scene=sc.name, default_objects=sorted(o.name for o in bpy.data.objects if not o.get(bb.TAG)))
""")
        self.assertEqual(rep["units"], ["METRIC", "MILLIMETERS", 0.001])
        self.assertGreaterEqual(tuple(rep["version"][:2]), (4, 5))
        self.assertEqual(rep["build_scene"], "3dprint-scout")
        self.assertNotEqual(rep["context_scene"], "3dprint-scout")            # the window's scene is not switched
        self.assertIn("Cube", rep["default_objects"])                           # the default file was not reset
        stl = os.path.join(self.tmp, "cube.stl")
        tris = validate.read_stl(stl)
        m = validate.analyse(tris)
        self.assertEqual(m["bbox_mm"], [10.0, 10.0, 10.0])
        self.assertEqual(m["bbox_min_mm"], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(m["volume_mm3"], 1000.0, places=3)
        self.assertEqual(rep["info"][0]["bbox_mm"], [10.0, 10.0, 10.0])
        f = check(stl, "--expect", "10,10,10")
        self.assertEqual({k: f["checks"][k]["state"] for k in ("D1", "D3", "D4", "M1", "M2", "M3", "M4", "M5")},
                         {k: "PASS" for k in ("D1", "D3", "D4", "M1", "M2", "M3", "M4", "M5")})

    def test_boolean_manifold_by_default_and_exact_on_request(self):
        rep = run_in_blender(f"""
bb.new_scene_mm()
body = bb.box([30, 20, 10], "body")
hole = bb.cylinder(3.0, 12.0, name="hole"); hole.location = (10, 10, -1)
bb.boolean(body, hole, "difference")
bb.part(body, "body")
other = bb.box([30, 20, 10], "other"); peg = bb.cylinder(3.0, 12.0, name="peg"); peg.location = (20, 10, -1)
bb.boolean(other, peg, "difference", solver="EXACT")
bb.part(other, "other")
bb.export_parts({self.tmp!r})
emit(solver=bb.boolean_solver(), log=bb.LOG, objects=ours())
""")
        self.assertEqual(rep["solver"], "MANIFOLD")
        self.assertTrue(any("solver MANIFOLD" in n for n in rep["log"]), rep["log"])
        self.assertTrue(any("solver EXACT" in n for n in rep["log"]), rep["log"])
        self.assertEqual(rep["objects"], ["body", "other"])                    # the tools are gone after apply
        for name in ("body", "other"):
            f = check(os.path.join(self.tmp, name + ".stl"), "--expect", "30,20,10")
            self.assertEqual({k: f["checks"][k]["state"] for k in ("D1", "M1", "M2", "M3", "M4", "M5")},
                             {k: "PASS" for k in ("D1", "M1", "M2", "M3", "M4", "M5")}, name)
            self.assertAlmostEqual(f["metrics"]["volume_mm3"], 6000 - 3.14159 * 9 * 10, delta=3)

    def test_boolean_refuses_open_input(self):
        rep = run_in_blender("""
import bmesh
bb.new_scene_mm()
body = bb.box([10, 10, 10], "body")
tool = bb.box([4, 4, 4], "tool")
bm = bmesh.new(); bm.from_mesh(tool.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY"); bm.to_mesh(tool.data); bm.free()
try:
    bb.boolean(body, tool, "difference")
    emit(error=None)
except ValueError as exc:
    emit(error=str(exc))
""")
        self.assertIn("non-manifold", rep["error"])
        self.assertIn("tool", rep["error"])

    def test_bevel_makes_a_closed_mesh_off_the_bed(self):
        rep = run_in_blender(f"""
bb.new_scene_mm()
body = bb.box([40, 30, 8], "body")
bb.bevel(body, 2.0)
bb.part(body, "body")
bb.export_parts({self.tmp!r})
emit(segments=bb.segments_for(2.0), log=bb.LOG)
""")
        self.assertIn(f"{rep['segments']} segments", rep["log"][-1])
        self.assertIn("8 edges", rep["log"][-1])                               # top 4 + vertical 4; the 4 bed edges stay sharp
        f = check(os.path.join(self.tmp, "body.stl"), "--expect", "40,30,8")
        self.assertEqual({k: f["checks"][k]["state"] for k in ("D1", "M1", "M2", "M3", "M4", "M5", "P1", "P2")},
                         {k: "PASS" for k in ("D1", "M1", "M2", "M3", "M4", "M5", "P1", "P2")})
        # The bed edges stay sharp; only the four rounded vertical corners leave the footprint.
        self.assertAlmostEqual(f["metrics"]["bed_contact_mm2"], 1200 - 4 * (1 - 3.14159 / 4) * 4, delta=1.0)
        self.assertLess(f["metrics"]["volume_mm3"], 40 * 30 * 8)

    def test_bed_chamfer_cuts_into_the_body_and_is_no_overhang(self):
        run_in_blender(f"""
bb.new_scene_mm()
body = bb.box([20, 20, 5], "body")
bb.bed_chamfer(body, 0.4)
bb.part(body, "body")
bb.export_parts({self.tmp!r})
emit(log=bb.LOG)
""")
        f = check(os.path.join(self.tmp, "body.stl"), "--expect", "20,20,5")
        self.assertEqual(f["checks"]["D1"]["state"], "PASS")                  # the size did not grow
        self.assertEqual(f["checks"]["M1"]["state"], "PASS")
        self.assertEqual(f["checks"]["P2"]["state"], "PASS")
        self.assertEqual(f["metrics"]["overhang_pct"], 0.0)                   # steeper than 45 deg
        self.assertAlmostEqual(f["metrics"]["bed_contact_mm2"], (20 - 0.72) ** 2, delta=0.5)

    def test_export_welds_what_the_validator_welds(self):
        """S3-8: a closed mesh with two vertices closer than WELD (a boolean seam where a tool
        conforms to a face) exported as it is fails M3 in validate.py, which welds them; the
        export welds first, and refuses a mesh that keeps zero-area triangles after the weld."""
        rep = run_in_blender(f"""
import bmesh, bmesh.utils
bb.new_scene_mm()
cube = bb.box([10, 10, 10], "cube")
bm = bmesh.new(); bm.from_mesh(cube.data); bm.edges.ensure_lookup_table()
e = bm.edges[0]
bmesh.utils.edge_split(e, e.verts[0], 5e-6)                   # a vertex 0.00005 mm from a corner: a sliver on two faces
bm.to_mesh(cube.data); bm.free(); cube.data.update()
bb.part(cube, "cube")
raw = os.path.join({self.tmp!r}, "raw.stl")
bb._deselect_all(); cube.select_set(True, view_layer=bb._view_layer()); bb._view_layer().objects.active = cube
with bb._ctx():
    bpy.ops.wm.stl_export(filepath=raw, export_selected_objects=True, apply_modifiers=True, global_scale=1.0,
                          use_scene_unit=False, ascii_format=False, forward_axis="Y", up_axis="Z", check_existing=False)
info = bb.export_parts({self.tmp!r})
orig = bb.degenerate_triangles
bb.degenerate_triangles = lambda me, area=1e-9: 3
try:
    bb.export_parts({self.tmp!r}); refused = None
except ValueError as exc:
    refused = str(exc)
bb.degenerate_triangles = orig
emit(info=info, refused=refused, verts=len(cube.data.vertices), nonmanifold=bb.nonmanifold_edges(cube),
     log=[n for n in bb.LOG if n.startswith("export")], leftovers=[o.name for o in bpy.data.objects if o.name.startswith("_export")])
""")
        self.assertEqual(rep["nonmanifold"], 0)                                 # closed and manifold as Blender sees it
        self.assertEqual(rep["verts"], 9)                                       # the original is untouched
        raw = check(os.path.join(self.tmp, "raw.stl"))
        self.assertEqual(raw["checks"]["M3"]["state"], "FAIL", raw["metrics"])  # what the plain export gave (S3-8)
        self.assertGreaterEqual(raw["metrics"]["degenerate_faces"], 1)
        f = check(os.path.join(self.tmp, "cube.stl"), "--expect", "10,10,10")
        self.assertEqual({k: f["checks"][k]["state"] for k in ("D1", "M1", "M2", "M3", "M4", "M5")},
                         {k: "PASS" for k in ("D1", "M1", "M2", "M3", "M4", "M5")}, f["metrics"])
        self.assertEqual(rep["info"][0]["welded_vertices"], 1)
        self.assertEqual(rep["info"][0]["triangles"], 12)
        self.assertTrue(any("1 vertices welded on the" in n for n in rep["log"]), rep["log"])
        self.assertIn("zero-area triangles remain after welding", rep["refused"])
        self.assertIn("'cube'", rep["refused"])
        self.assertEqual(rep["leftovers"], [])                                  # the export copies are gone

    def test_export_welds_on_the_validators_grid(self):
        """Review N1: validate.py welds by rounding each coordinate to a multiple of WELD, so two
        vertices 1.5 WELD apart in one grid cell are one vertex to it. The export snaps to the
        same grid (in world mm, so a moved part too), and the STL passes M3."""
        rep = run_in_blender(f"""
import bmesh, bmesh.utils
from mathutils import Vector
bb.new_scene_mm()
cube = bb.box([10, 10, 10], "cube")
bm = bmesh.new(); bm.from_mesh(cube.data); bm.edges.ensure_lookup_table()
e = bm.edges[0]
corner = e.verts[0]
_, v = bmesh.utils.edge_split(e, corner, 0.5)
c = corner.co.copy() + Vector((0.3, 0.3, 0.3))       # on the grid once the object is moved by -0.3
corner.co = c - Vector((0.45, 0.45, 0.45)) * bb.WELD
v.co = c + Vector((0.45, 0.45, 0.45)) * bb.WELD          # 1.56 WELD from the corner, in the same cell
bm.to_mesh(cube.data); bm.free(); cube.data.update()
cube.location = (-0.3, -0.3, -0.3)
bb.part(cube, "cube")
m = bb.box([10, 20, 5], "m")
m.location = (30, 0, 0); m.scale = (-1, 1, 1)                 # a mirrored part keeps its faces pointing out
bb.part(m, "m")
info = bb.export_parts({self.tmp!r})
emit(info=info)
""")
        mirrored = check(os.path.join(self.tmp, "m.stl"))
        self.assertAlmostEqual(mirrored["metrics"]["volume_mm3"], 1000.0, delta=0.01)
        self.assertEqual(mirrored["metrics"]["bbox_min_mm"][0], 20.0)
        f = check(os.path.join(self.tmp, "cube.stl"))
        self.assertEqual({k: f["checks"][k]["state"] for k in ("M1", "M2", "M3")}, {k: "PASS" for k in ("M1", "M2", "M3")},
                         f["metrics"])
        self.assertEqual(rep["info"][0]["welded_vertices"], 1)
        self.assertEqual(rep["info"][0]["triangles"], 12)

    def test_fillet_has_a_true_radius_and_refuses_facets(self):
        """0.6: bevel's width is Blender's offset (the radius only at 90 degrees); fillet gives the
        same radius on a 90 and a 120 degree edge, and refuses to round along a curve's facets
        before changing anything, pointing at round_profile."""
        rep = run_in_blender(f"""
import math
bb.new_scene_mm()
O = [(0, 0), (30, 0), (30, 20), (15, 20 + 15 * math.tan(math.radians(30))), (0, 20)]
p = bb.prism(O, 10, name="p")
sel = bb.edges(p, axis="z")
bb.fillet(p, 2.0, sel)
top = [(v.co.x, v.co.y) for v in p.data.vertices if abs(v.co.z - 10) < 1e-6]
dist = {{}}
for k in range(len(O)):
    q, a_, b_ = O[k], O[k - 1], O[(k + 1) % len(O)]
    u = [a_[0] - q[0], a_[1] - q[1]]; v = [b_[0] - q[0], b_[1] - q[1]]
    lu, lv = math.hypot(*u), math.hypot(*v); u = [c / lu for c in u]; v = [c / lv for c in v]
    al = math.acos(u[0] * v[0] + u[1] * v[1]); bis = [u[0] + v[0], u[1] + v[1]]; lb = math.hypot(*bis)
    c = (q[0] + bis[0] / lb * 2 / math.sin(al / 2), q[1] + bis[1] / lb * 2 / math.sin(al / 2))
    t = 2 / math.tan(al / 2)
    ds = [math.hypot(x - c[0], y - c[1]) for x, y in top if 1e-6 < math.hypot(x - q[0], y - q[1]) <= t + 1e-6]
    dist[round(math.degrees(al))] = dist.get(round(math.degrees(al)), []) + [min(ds), max(ds)]
bb.part(p, "p")
info = bb.export_parts({self.tmp!r})
plate = bb.box([40, 30, 3], "plate")
ridge = bb.prism(bb.outline(bb.arc((20, 3), 6, 180, 0)), 30, name="ridge", plane="XZ")
bb.boolean(plate, ridge, "union")
before = len(plate.data.vertices)
try:
    bb.fillet(plate, 1.0, bb.edges(plate, axis="y", inside=((0, -1, 2.9), (40, 31, 3.1)))); refused = None
except ValueError as exc:
    refused = str(exc)
emit(selected=len(sel), dist=dist, refused=refused, untouched=len(plate.data.vertices) == before, mods=len(plate.modifiers))
""")
        self.assertEqual(rep["selected"], 5)
        self.assertEqual([round(x, 4) for x in rep["dist"]["90"]], [2.0, 2.0, 2.0, 2.0])
        lo, hi = min(rep["dist"]["120"]), max(rep["dist"]["120"])
        self.assertTrue(2.0 * 0.985 <= lo <= hi <= 2.0 + 1e-4, rep["dist"])   # within 1.5 % (Blender's profile)
        f = check(os.path.join(self.tmp, "p.stl"))
        self.assertEqual({k: f["checks"][k]["state"] for k in ("M1", "M2", "M3", "M4")}, {k: "PASS" for k in ("M1", "M2", "M3", "M4")})
        self.assertIn("facets of a curved face", rep["refused"])
        self.assertIn("round_profile", rep["refused"])
        self.assertTrue(rep["untouched"])
        self.assertEqual(rep["mods"], 0)

    def test_fillet_refuses_overlaps_and_sharp_edges(self):
        """Review of 0.6: two fillets on one face that would meet, and an edge sharper than 90
        degrees (Blender's profile is no circle there), are refused before any change."""
        rep = run_in_blender("""
import math
bb.new_scene_mm()
slab = bb.box([3, 20, 20], "slab")
try:
    bb.fillet(slab, 2.0, bb.edges(slab, axis="z")); overlap = None
except ValueError as exc:
    overlap = str(exc)
ok = bb.box([5, 20, 20], "ok")
bb.fillet(ok, 2.0, bb.edges(ok, axis="z"))                       # 2 + 2 <= 5: fine
tri = bb.prism([(0, 0), (20, 0), (0, 20 * math.tan(math.radians(30)))], 10, name="tri")
try:
    bb.fillet(tri, 1.0, bb.edges(tri, axis="z")); sharp = None
except ValueError as exc:
    sharp = str(exc)
emit(overlap=overlap, sharp=sharp, slab_mods=len(slab.modifiers), ok_nm=bb.nonmanifold_edges(ok), ok_deg=bb.degenerate_triangles(ok.data))
""")
        self.assertIn("would overlap", rep["overlap"])
        self.assertIn("would turn round", rep["overlap"])
        self.assertEqual(rep["slab_mods"], 0)
        self.assertEqual((rep["ok_nm"], rep["ok_deg"]), (0, 0))
        self.assertIn("sharper than 90 degrees", rep["sharp"])
        self.assertIn("round_profile", rep["sharp"])

    def test_fillet_overlap_check_keeps_rims_and_catches_holes(self):
        """Second and third review of 0.6: the overlap check insets each flat face's outline
        (holes included, across the faces a boolean splits it into), and every result is checked
        for faces that cross each other (validate.py does not look). A cut's face is split along
        edges from the hole's rim; where one leaves a rim corner at a shallow angle the bevel ran
        along it to the far corner (a slit, 101 crossing pairs), so those edges are turned onto the
        corner's miter first. Rims of a cylinder, a rounded rectangle, a hexagon, a hole and a
        boss's foot pass clean (the hole's round is a true radius); a hole too near the side, two
        holes too close, a hexagon past its inradius, and a round whose end meets another round,
        are refused, and a refusal after the bevel leaves the object as it was."""
        rep = run_in_blender("""
import math
def top(o, z):
    return bb.edges(o, inside=((-200, -200, z - 0.1), (200, 200, z + 0.1)))
def sel(o, fn):
    return [e.index for e in o.data.edges if fn([o.data.vertices[v].co for v in e.vertices])]
def attempt(fn):
    bb.new_scene_mm()
    try:
        o = fn()
        return [bb.nonmanifold_edges(o), bb.degenerate_triangles(o.data), bb.self_intersections(o)]
    except ValueError as exc:
        return str(exc)
def hole(at, r=4.0, size=(30, 30, 10)):
    blk = bb.box(list(size), "blk")
    for x, y in at:
        h = bb.cylinder(r, size[2] + 2, name="h"); h.location = (x, y, -1)
        bb.boolean(blk, h, "difference")
    return blk
def hex_(r):
    pts = [(5 * math.cos(math.radians(60 * i)), 5 * math.sin(math.radians(60 * i))) for i in range(6)]
    o = bb.prism(pts, 10, name="hex")
    return bb.fillet(o, r, top(o, 10))
def cyl():
    o = bb.cylinder(10, 10, name="c")
    return bb.fillet(o, 1.0, top(o, 10))
def rrect():
    o = bb.prism(bb.round_profile([(0, 0), (40, 0), (40, 20), (0, 20)], 4), 10, name="rr")
    return bb.fillet(o, 1.0, top(o, 10))
def hole_rim():
    o = hole([(15, 15)])
    return bb.fillet(o, 0.5, top(o, 10))
rim_r = []
def rim_only():
    o = hole([(15, 15)])
    bb.fillet(o, 1.0, sel(o, lambda p: all(abs(q.z - 10) < 1e-3 and abs(math.hypot(q.x - 15, q.y - 15) - 4) < 0.01 for q in p)))
    rim_r.append(min(math.hypot(v.co.x - 15, v.co.y - 15) for v in o.data.vertices if abs(v.co.z - 10) < 1e-4))
    rim_r.append(max(v.co.z for v in o.data.vertices if math.hypot(v.co.x - 15, v.co.y - 15) < 4.001))
    return o
def boss_foot():
    o = bb.box([30, 30, 4], "b"); c = bb.cylinder(5, 8, name="c"); c.location = (15, 15, 2)
    bb.boolean(o, c, "union")
    return bb.fillet(o, 1.0, sel(o, lambda p: all(abs(q.z - 4) < 1e-3 and abs(math.hypot(q.x - 15, q.y - 15) - 5) < 0.01 for q in p)))
def near_edge():
    o = hole([(15, 5.5)])                                   # rim 1.5 mm from the side
    return bb.fillet(o, 1.0, top(o, 10))
def near_edge_ok():
    o = hole([(15, 5.5)])
    return bb.fillet(o, 0.6, top(o, 10))
def two_holes():
    o = hole([(10, 10), (19, 10)], size=(30, 20, 5))        # 1 mm between the rims
    return bb.fillet(o, 0.6, top(o, 5))
kept = []
def end_meets():                                            # the top-front round's end meets the corner's round
    o = bb.box([30, 4, 10], "b")
    front = sel(o, lambda p: all(abs(q.z - 10) < 1e-6 and abs(q.y) < 1e-6 for q in p))
    corner = sel(o, lambda p: all(abs(q.x) < 1e-6 and abs(q.y - 4) < 1e-6 for q in p))
    n = len(o.data.vertices)
    try:
        return bb.fillet(o, 2.2, front + corner)
    finally:
        kept.append([n, len(o.data.vertices), len(o.modifiers)])
def full_round():
    o = bb.box([9.8, 30, 10], "b")
    return bb.fillet(o, 4.9, top(o, 10) + bb.edges(o, axis="z"))
def two_steps():
    o = bb.box([20, 20, 10], "b")
    bb.fillet(o, 1.0, top(o, 10))
    return bb.fillet(o, 3.0, bb.edges(o, axis="z"))
emit(rim_r=rim_r, kept=kept, **{n: attempt(f) for n, f in dict(
    hex3=lambda: hex_(3.0), hex44=lambda: hex_(4.4), cyl=cyl, rrect=rrect, hole_rim=hole_rim, rim_only=rim_only,
    boss_foot=boss_foot, near_edge=near_edge, near_edge_ok=near_edge_ok, two_holes=two_holes, end_meets=end_meets,
    full_round=full_round, two_steps=two_steps).items()})
""")
        for name in ("hex3", "cyl", "rrect", "hole_rim", "rim_only", "boss_foot", "near_edge_ok", "full_round",
                     "two_steps"):
            self.assertEqual(rep[name], [0, 0, 0], name)
        self.assertAlmostEqual(rep["rim_r"][0], 5.0, delta=0.01)                 # the round meets the top 1 mm out
        self.assertAlmostEqual(rep["rim_r"][1], 9.0, delta=0.01)                 # ... and the bore 1 mm down
        for name in ("hex44", "near_edge", "two_holes"):
            self.assertIsInstance(rep[name], str, name)
            self.assertIn("would overlap", rep[name], name)
        self.assertIn("cross each other", rep["end_meets"])
        self.assertEqual(rep["kept"][0][:2], [8, 8])                             # put back as it was
        self.assertEqual(rep["kept"][0][2], 0)

    def test_apply_transform_keeps_shared_meshes_and_children(self):
        rep = run_in_blender("""
bb.new_scene_mm()
a = bb.box([10, 10, 10], "a")
b = a.copy(); b[bb.TAG] = True; bb.scene().collection.objects.link(b)      # shares a's mesh
b.location = (50, 0, 0)
a.location = (0, 0, 5)
child = bb.box([2, 2, 2], "child"); child.parent = a; child.location = (20, 0, 0)
before_child = bb.world_bbox(child)[0][:]
before_b = bb.world_bbox(b)[0][:]
bb.apply_transform(a)
emit(a_min=list(bb.world_bbox(a)[0]), b_min=list(bb.world_bbox(b)[0]), b_before=list(before_b),
     child_min=list(bb.world_bbox(child)[0]), child_before=list(before_child), shared=a.data == b.data)
""")
        self.assertEqual([round(c, 4) for c in rep["a_min"]], [0.0, 0.0, 5.0])
        self.assertEqual([round(c, 4) for c in rep["b_min"]], [round(c, 4) for c in rep["b_before"]])   # the copy stayed
        self.assertEqual([round(c, 4) for c in rep["child_min"]], [round(c, 4) for c in rep["child_before"]])
        self.assertFalse(rep["shared"])

    @unittest.skipUnless(find_spec("manifold3d") is not None, "manifold3d not installed")
    def test_parts_reach_blender_through_from_manifold(self):
        """0.6: a parts.py countersunk hole cut from a Blender block (the bridge), the result
        exported and checked; an STL read back with import_stl keeps its volume."""
        rep = run_in_blender(f"""
import parts
bb.new_scene_mm()
blk = bb.box([20, 20, 8], "blk")
hole = bb.from_manifold(parts.screw_hole("M3", depth=8.5, kind="countersunk").translate([10, 10, 8]), "hole")
bb.boolean(blk, hole, "difference")
bb.part(blk, "blk")
info = bb.export_parts({self.tmp!r})
back = bb.import_stl(os.path.join({self.tmp!r}, "blk.stl"), "back")
try:
    bb.from_mesh([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)], "open"); open_refused = None
except ValueError as exc:
    open_refused = str(exc)
emit(nm=bb.nonmanifold_edges(back), open_refused=open_refused, deps=[os.path.basename(d) for d in bb._deps()],
     deps_full=bb._deps())
""")
        f = check(os.path.join(self.tmp, "blk.stl"))
        self.assertEqual({k: f["checks"][k]["state"] for k in ("M1", "M2", "M3", "M4", "D3")}, {k: "PASS" for k in ("M1", "M2", "M3", "M4", "D3")}, f["metrics"])
        csk = 3.14159 * 1.6 ** 2                                               # the shank alone, as a lower bound
        self.assertLess(f["metrics"]["volume_mm3"], 20 * 20 * 8 - csk * 8)
        self.assertEqual(rep["nm"], 0)
        self.assertIn("open or non-manifold", rep["open_refused"])
        self.assertIn("parts.py", rep["deps"])                                 # parts.py is hashed into the manifest
        self.assertIn(os.path.join(self.tmp, "blk.stl"), rep["deps_full"])      # so is an STL brought in

    def test_from_mesh_merges_split_facets_not_a_gentle_curve(self):
        """Second and third review of 0.6: split facets are merged back by flatness, never by an
        angle alone (float32 noise on a thin triangle and the bend of a large radius overlap):
        manifold3d's face groups when they are flat, else faces grown while every corner stays
        within WELD / 2 of the seed's plane. Two parts.py countersinks cut a plate cleanly near
        the origin and 300 mm out; the facets of an r = 1000 mm arc stay apart on both paths
        (folded, a later cut replaced the arc with its chord); a merged face is flat."""
        rep = run_in_blender("""
import math, parts
from manifold3d import CrossSection, Manifold
cuts = {}
for x0 in (0, 300):
    bb.new_scene_mm()
    plate = bb.box([70, 25, 4], "plate"); plate.location = (x0, 0, 0); bb.apply_transform(plate)
    for i, x in enumerate((10, 60)):
        tool = bb.from_manifold(parts.screw_hole("M4", depth=4.1, kind="countersunk").translate([x0 + x, 12.5, 4]),
                                f"h{i}")
        bb.boolean(plate, tool, "difference")
    cuts[x0] = [bb.degenerate_triangles(plate.data), bb.nonmanifold_edges(plate)]
R, n = 1000.0, 100
arc = [(R * math.sin(a), R - R * math.cos(a)) for a in (i * 0.0004 for i in range(n + 1))]
pts = arc + [(arc[-1][0], arc[-1][1] + 5), (0, 5)]
man = Manifold.extrude(CrossSection([pts]), 3)
bb.new_scene_mm()
strip = bb.from_manifold(man, "strip")
mesh = man.to_mesh()
raw = bb.from_mesh([tuple(v[:3]) for v in mesh.vert_properties.tolist()], mesh.tri_verts.tolist(), "raw")
def sides(o):
    return sum(1 for p in o.data.polygons if abs(p.normal.z) < 0.5)
def worst(o):
    me = o.data
    return max(max(abs((me.vertices[v].co - me.vertices[p.vertices[0]].co).dot(p.normal)) for v in p.vertices)
               for p in me.polygons)
emit(cuts=cuts, sides=sides(strip), raw_sides=sides(raw), outline=len(pts), worst=max(worst(strip), worst(raw)))
""")
        self.assertEqual(rep["cuts"], {"0": [0, 0], "300": [0, 0]})
        self.assertEqual(rep["sides"], rep["outline"])                         # one face per outline edge
        self.assertEqual(rep["raw_sides"], rep["outline"])
        self.assertLess(rep["worst"], 1e-4)

    def test_fillet_near_another_round_shared_meshes_and_flat_overlaps(self):
        """Fourth review of 0.6: a straightened rim corner never lands past another round's
        tangent line (a hole 2r + 0.05 from the side at r = 3 left a 0.08 mm ridge on the side's
        round): the surface across that round stays within faceting of the ideal one. A fillet on
        a mesh shared with a linked duplicate leaves the duplicate as it was, accepted or refused.
        Faces that overlap in one plane count as crossing (the BVH test alone saw 0)."""
        rep = run_in_blender("""
import math, bmesh
from mathutils.bvhtree import BVHTree
r, R, TOP = 3.0, 4.0, 8.0
cx, cy = 40 - (2 * r + 0.05) - R, 15.0
bb.new_scene_mm()
o = bb.box([40, 30, TOP], "blk")
h = bb.cylinder(R, TOP + 2, name="h"); h.location = (cx, cy, -1)
bb.boolean(o, h, "difference")
bb.fillet(o, r, bb.edges(o, inside=((-1, -1, TOP - 0.1), (41, 31, TOP + 0.1))))
bm = bmesh.new(); bm.from_mesh(o.data); tree = BVHTree.FromBMesh(bm)
def ideal(x):
    tl = 40 - r
    return TOP if x <= tl else TOP - r + math.sqrt(max(r * r - (x - tl) ** 2, 0.0))
worst = 0.0
for y in (cy - 1.5, cy, cy + 1.5):
    for k in range(60):
        x = 40 - r + 0.05 * k
        hit = tree.ray_cast((x, y, TOP + 5), (0, 0, -1))
        if hit[0] is not None and x < 39.9:
            worst = max(worst, hit[0].z - ideal(x))
bm.free()
clean = [bb.nonmanifold_edges(o), bb.degenerate_triangles(o.data), bb.self_intersections(o)]
twins = {}
for case, rad in (("ok", 1.0), ("refused", 6.0)):
    bb.new_scene_mm()
    a = bb.box([30, 30, 10], "a"); hh = bb.cylinder(4, 12, name="hh"); hh.location = (15, 15, -1)
    bb.boolean(a, hh, "difference")
    b = a.copy(); bpy.context.scene.collection.objects.link(b)
    n = len(b.data.vertices)
    try:
        bb.fillet(a, rad, bb.edges(a, inside=((-1, -1, 9.9), (31, 31, 10.1))))
    except ValueError:
        pass
    twins[case] = [n, len(b.data.vertices), "bevel_weight_edge" in b.data.attributes]
bb.new_scene_mm()
bm = bmesh.new()
for lo in ((0, 0, 0), (5, 5, 10)):                       # two blocks stacked: the faces at z = 10 overlap flat
    vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(10, 10, 10), verts=vs)
    bmesh.ops.translate(bm, vec=(lo[0] + 5, lo[1] + 5, lo[2] + 5), verts=vs)
stack = bb.mesh_object("stack", bm)
emit(worst=worst, clean=clean, twins=twins, flat=bb.self_intersections(stack))
""")
        self.assertEqual(rep["clean"], [0, 0, 0])
        self.assertLess(rep["worst"], 0.02)                                    # above the ideal round: no ridge
        for case in ("ok", "refused"):
            n, after, weight = rep["twins"][case]
            self.assertEqual((after, weight), (n, False), case)
        self.assertGreater(rep["flat"], 0)

    def test_boolean_welds_only_degenerate_corners(self):
        """Third review of 0.6: a boolean that leaves corners a hair apart merges only those
        corners (as the export would) and counts again; two shells 0.07 um apart elsewhere stay
        apart (a weld of the whole mesh joined them into a non-manifold edge, unreported)."""
        rep = run_in_blender("""
import bmesh
E = 5e-5
bb.new_scene_mm()
bm = bmesh.new()
for lo, hi in (((0, 0, 0), (10, 10, 10)), ((10 + E, 10 + E, 0), (20, 20, 10))):
    vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=[h - l for l, h in zip(lo, hi)], verts=vs)
    bmesh.ops.translate(bm, vec=[(l + h) / 2 for l, h in zip(lo, hi)], verts=vs)
o = bb.mesh_object("two", bm)
t = bb.box([5, 6, 7], "t"); t.location = (-E, 2, 5); bb.apply_transform(t)
try:
    bb.boolean(o, t, "union"); err = None
except ValueError as exc:
    err = str(exc)
emit(err=err, nm=bb.nonmanifold_edges(o), deg=bb.degenerate_triangles(o.data))
""")
        if rep["err"] is None:
            self.assertEqual((rep["nm"], rep["deg"]), (0, 0))
        else:
            self.assertIn("non-manifold", rep["err"])                          # never returned silently

    def test_planes_transforms_and_world_bed_chamfer(self):
        rep = run_in_blender(f"""
import math
bb.new_scene_mm()
def vol(o):
    me = o.data; me.calc_loop_triangles()
    return sum(me.vertices[t.vertices[0]].co.dot(me.vertices[t.vertices[1]].co.cross(me.vertices[t.vertices[2]].co)) / 6
               for t in me.loop_triangles)
vols, boxes = {{}}, {{}}
for plane in ("XY", "XZ", "YZ"):
    o = bb.prism([(0, 0), (10, 0), (10, 5), (0, 5)], 3, name=plane, plane=plane)
    vols[plane] = round(vol(o), 3)
    lo, hi, _ = bb.world_bbox(o)
    boxes[plane] = [round(c, 3) for c in hi]
c = bb.cone(2, 4, 2, name="c")
bar = bb.box([30, 6, 4], "bar")
bar.rotation_euler = (math.radians(90), 0, math.radians(30))
bar.location = (5, 5, 0)
bb.bed_chamfer(bar, 0.4)
bb.part(bar, "bar")
info = bb.export_parts({self.tmp!r})
emit(vols=vols, boxes=boxes, cone=round(vol(c), 3), identity=bar.matrix_world == bar.matrix_world.Identity(4))
""")
        self.assertEqual(rep["vols"], {"XY": 150.0, "XZ": 150.0, "YZ": 150.0})
        self.assertEqual(rep["boxes"], {"XY": [10.0, 5.0, 3.0], "XZ": [10.0, 3.0, 5.0], "YZ": [3.0, 10.0, 5.0]})
        self.assertAlmostEqual(rep["cone"], math.pi * 2 / 3 * (4 + 8 + 16), delta=0.5)   # frustum, faceted
        self.assertTrue(rep["identity"])
        f = check(os.path.join(self.tmp, "bar.stl"))
        self.assertEqual(f["checks"]["M1"]["state"], "PASS")
        self.assertAlmostEqual(f["metrics"]["bbox_min_mm"][2], 0.0, delta=1e-4)            # the world bed
        self.assertLess(f["metrics"]["bed_contact_mm2"], 30 * 4 - 1)                    # inset by the chamfer

    def test_text_single_letter_at_its_cap_height(self):
        rep = run_in_blender(f"""
bb.new_scene_mm()
mark = bb.text("H", height=6.0, depth=1.0)
bb.part(mark, "mark")
info = bb.export_parts({self.tmp!r})
emit(info=info)
""")
        bbox = rep["info"][0]["bbox_mm"]
        self.assertAlmostEqual(bbox[1], 6.0, delta=0.05)                       # cap height, not the em size
        self.assertAlmostEqual(bbox[2], 1.0, delta=1e-3)
        self.assertEqual(rep["info"][0]["bbox_min_mm"][2], 0.0)                # standing on z = 0
        f = check(os.path.join(self.tmp, "mark.stl"))
        self.assertEqual({k: f["checks"][k]["state"] for k in ("D3", "M1", "M2", "M3", "M4", "M5")}, {k: "PASS" for k in ("D3", "M1", "M2", "M3", "M4", "M5")})

    def test_text_with_touching_letters_is_closed(self):
        """AA, VV: the feet / tops kiss along an edge; AARON: one such pair among separate letters;
        Ab3 and O: holes stay holes, letters stay separate bodies."""
        cases = {"AA": 1, "VV": 1, "AARON": 4, "Ab3": 3, "O": 1}
        rep = run_in_blender(f"""
bb.new_scene_mm()
for i, s in enumerate({list(cases)!r}):
    bb.part(bb.text(s, 6.0, 1.0, name="t%d" % i), "t%d" % i)
info = bb.export_parts({self.tmp!r})
emit(info=info, log=[n for n in bb.LOG if n.startswith("text")])
""")
        for i, (s, shells) in enumerate(cases.items()):
            f = check(os.path.join(self.tmp, f"t{i}.stl"), "--shells", str(shells))
            self.assertEqual({k: f["checks"][k]["state"] for k in ("D3", "M1", "M2", "M3", "M4", "M5")},
                             {k: "PASS" for k in ("D3", "M1", "M2", "M3", "M4", "M5")}, (s, f["metrics"]))
            self.assertAlmostEqual(f["metrics"]["bbox_mm"][2], 1.0, delta=1e-3, msg=s)
        notes = {n.split("'")[1]: n for n in rep["log"]}
        self.assertIn("unioned", notes["AA"])
        self.assertIn("tightening the character spacing", notes["AA"])       # the letters only kissed along an edge
        self.assertIn("unioned", notes["VV"])
        self.assertIn("1 pair(s) with overlapping boxes unioned", notes["AARON"])
        self.assertIn("4 separate bodies", notes["AARON"])                     # counted after the union: what M5 sees
        self.assertIn("3 separate bodies", notes["Ab3"])
        self.assertIn("1 separate body", notes["O"])
        self.assertNotIn("unioned", notes["Ab3"])
        self.assertRegex(notes["Ab3"], r"box \d+\.\d\d x \d+\.\d\d x 1\.00 mm")    # the real box, for expect

    def test_text_refuses_characters_the_font_cannot_draw(self):
        """S5-F1: a font without Hangul must not print .notdef boxes for 고양이; a font that
        covers the script builds it, and the built-in font's fallback covers it too. A loaded
        font is packed once, however many text() calls use it."""
        latin = next(iter(glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)), None)
        cjk = next(iter(sorted(glob.glob("/usr/share/fonts/**/NotoSansCJK-*.ttc", recursive=True))), None)
        if not latin:
            self.skipTest("no DejaVuSans-Bold.ttf on this machine")
        rep = run_in_blender(f"""
bb.new_scene_mm()
out = {{"builtin_missing": bb.missing_glyphs("고양이 H"), "latin_missing": bb.missing_glyphs("고양이 H", {latin!r}),
        "format_chars": bb.missing_glyphs("A\u200bB\u00adC", {latin!r})}}
try:
    bb.text("고양이", 8.0, 1.0, font={latin!r}); out["error"] = None
except ValueError as exc:
    out["error"] = str(exc)
out["objects_after_error"] = ours()
a = bb.text("A", 6.0, 1.0, font={latin!r}, name="a"); bb.part(a, "a")
b = bb.text("B", 6.0, 1.0, font={latin!r}, name="b"); bb.part(b, "b")
out["fonts"] = [f.name for f in bpy.data.fonts if f.get(bb.TAG)]
if {cjk!r}:
    out["cjk_missing"] = bb.missing_glyphs("고양이 H", {cjk!r})
    out["cjk_emoji"] = bb.missing_glyphs("\U0001F600", {cjk!r})
    k = bb.text("고양이", 8.0, 1.0, font={cjk!r}, name="k"); bb.part(k, "k")
    out["cjk_note"] = [n for n in bb.LOG if n.startswith("text '고양이'")][0]
h = bb.text("고양이", 8.0, 1.0, name="h"); bb.part(h, "h")
out["builtin_note"] = [n for n in bb.LOG if n.startswith("text '고양이'")][-1]
info = bb.export_parts({self.tmp!r})
out["info"] = info
emit(**out)
""")
        self.assertEqual(rep["builtin_missing"], [])                            # Blender's fallback fonts draw Hangul
        self.assertEqual(rep["latin_missing"], [["고", "U+ACE0"], ["양", "U+C591"], ["이", "U+C774"]])
        self.assertEqual(rep["format_chars"], [])                               # review N3: no ink, not missing
        self.assertIn("'고' (U+ACE0)", rep["error"])
        self.assertIn("Noto Sans CJK", rep["error"])
        self.assertIn("DejaVu", rep["error"])                                   # the font is named
        self.assertEqual(rep["objects_after_error"], [])                        # nothing half-built is left behind
        self.assertEqual(rep["fonts"], ["DejaVu Sans Bold"])                    # one packed copy for two text() calls

        def bodies(note):                                                      # the LOG's count is what M5 expects
            return re.search(r"(\d+) separate bod", note).group(1)
        f = check(os.path.join(self.tmp, "h.stl"), "--shells", bodies(rep["builtin_note"]))
        self.assertEqual({k: f["checks"][k]["state"] for k in ("M1", "M5")}, {"M1": "PASS", "M5": "PASS"}, f["metrics"])
        self.assertGreaterEqual(int(bodies(rep["builtin_note"])), 3)            # jamo, not one body per syllable
        if cjk:
            self.assertEqual(rep["cjk_missing"], [])
            self.assertEqual(rep["cjk_emoji"], [["\U0001F600", "U+1F600"]])    # the .notdef box of that font
            self.assertIn("glyph pieces", rep["cjk_note"])
            f = check(os.path.join(self.tmp, "k.stl"), "--shells", bodies(rep["cjk_note"]))
            self.assertEqual({k: f["checks"][k]["state"] for k in ("M1", "M5")}, {"M1": "PASS", "M5": "PASS"}, f["metrics"])
            self.assertAlmostEqual(f["metrics"]["bbox_mm"][1], 8.0, delta=2.5)  # cap height 8 mm; Hangul runs taller

    def test_text_without_a_capital_h_uses_the_em_box(self):
        """A font of another script has no 'H' (S5-F5): the height is taken as the em size with
        a LOG note, and the note still gives the glyphs' real box."""
        if find_spec("fontTools") is None:
            self.skipTest("fontTools not installed (used to make a font without H)")
        latin = next(iter(glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)), None)
        if not latin:
            self.skipTest("no DejaVuSans-Bold.ttf on this machine")
        from fontTools import subset
        from fontTools.ttLib import TTFont
        font = TTFont(latin)
        options = subset.Options()
        options.notdef_outline = True
        sub = subset.Subsetter(options)
        sub.populate(text="ABC")
        sub.subset(font)
        noh = os.path.join(self.tmp, "NoH.ttf")
        font.save(noh)
        rep = run_in_blender(f"""
bb.new_scene_mm()
out = {{"missing_h": bb.missing_glyphs("H", {noh!r}), "missing_abc": bb.missing_glyphs("ABC", {noh!r})}}
t = bb.text("ABC", 5.0, 1.0, font={noh!r}, name="t"); bb.part(t, "t")
out["log"] = list(bb.LOG)
out["info"] = bb.export_parts({self.tmp!r})
emit(**out)
""")
        self.assertEqual(rep["missing_h"], [["H", "U+0048"]])
        self.assertEqual(rep["missing_abc"], [])
        self.assertTrue(any("has no 'H'" in n and "em size" in n for n in rep["log"]), rep["log"])
        note = [n for n in rep["log"] if n.startswith("text 'ABC'")][0]
        self.assertIn("em size 5.0 mm (font size 5.000)", note)
        bbox = rep["info"][0]["bbox_mm"]
        self.assertLess(bbox[1], 5.0)                                           # caps are shorter than the em
        self.assertGreater(bbox[1], 3.0)
        self.assertIn("box %.2f x %.2f x 1.00 mm" % (bbox[0], bbox[1]), note)

    def test_parts_go_into_tagged_collections_and_params_into_props(self):
        rep = run_in_blender("""
bb.new_scene_mm()
a = bb.box([10, 10, 2], "a"); b = bb.box([4, 4, 1], "b"); b.location = (3, 3, 2)
bb.part(a, "lid"); bb.part(b, "label", object="lid", role="fused")
e = bb.params_to_props({"w": 10.0, "name": "x", "flag": True, "_parts": {"lid": {}}, "list": [1, 2], "words": ["a", "b"],
                        "font": "/home/someone/fonts/Bold.ttf"})
cols = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections if c.get(bb.TAG)}
emit(cols=cols, role=b.get("role"), obj=b.get("object"), props={k: (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else v) for k, v in e.items()},
     in_root=sorted(o.name for o in bb.scene().collection.objects), scene_objects=sorted(o.name for o in bb.scene().objects))
""")
        self.assertEqual(rep["cols"], {"lid": ["label", "lid"]})
        self.assertEqual((rep["role"], rep["obj"]), ("fused", "lid"))
        self.assertNotIn("_parts", rep["props"])
        self.assertEqual(rep["props"]["w"], 10.0)
        self.assertEqual(rep["props"]["words"], '["a", "b"]')
        self.assertEqual(rep["props"]["list"], [1.0, 2.0])
        self.assertEqual(rep["props"]["font"], "Bold.ttf")                     # never a path of the machine
        self.assertIn("PARAMETERS", rep["in_root"])
        self.assertEqual(rep["scene_objects"], ["PARAMETERS", "label", "lid"])  # only the build's own objects
        with self.assertRaises(AssertionError):                               # a bad role is refused
            run_in_blender("bb.new_scene_mm(); a = bb.box([1,1,1]); bb.part(a, 'a', role='glued'); emit()")

    def test_a_path_in_a_property_fails_before_any_export(self):
        rep = run_in_blender(f"""
bb.new_scene_mm()
def build(p):
    a = bb.box([10, 10, 2], "a"); a["source"] = "/home/someone/private/model.blend"; bb.part(a, "a"); return {{"a": a}}
try:
    bb.main(build, {{}}, argv=["blender", "--", "--out", {self.tmp!r}])
    emit(error=None)
except ValueError as exc:
    emit(error=str(exc), files=sorted(os.listdir({self.tmp!r})))
""")
        self.assertIn("'source'", rep["error"])
        self.assertIn("'a'", rep["error"])
        self.assertEqual(rep["files"], [])                                     # nothing was written

    def test_save_blend_refuses_overwrite_and_leaks_no_path(self):
        ttf = next(iter(glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)), None)
        font_line = f"mark = bb.text('A', 5.0, 1.0, font={ttf!r}); bb.part(mark, 'mark')" if ttf else ""
        blend = os.path.join(self.tmp, "x.blend")
        rep = run_in_blender(f"""
bb.new_scene_mm()
a = bb.box([10, 10, 2], "a"); bb.part(a, "lid")
{font_line}
bb.params_to_props({{"w": 10.0}})
bb.save_blend({blend!r}, out_dir={self.tmp!r})
try:
    bb.save_blend({blend!r}); second = None
except FileExistsError as exc:
    second = str(exc)
bb.save_blend({blend!r}, overwrite=True, out_dir={self.tmp!r})
emit(second=second, fonts=[(f.name, f.filepath, f.packed_file is not None) for f in bpy.data.fonts], files=sorted(os.listdir({self.tmp!r})))
""")
        self.assertIn("already exists", rep["second"])
        self.assertEqual(rep["files"], ["x.blend"])                            # no twin or temp file left behind
        with open(blend, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"BLENDER") or data.startswith(b"\x28\xb5\x2f\xfd"))   # plain or zstd-compressed
        if ttf:
            packed = [f for f in rep["fonts"] if f[2]]
            self.assertEqual(packed[0][1], "//" + os.path.basename(ttf))
        # Reload in a fresh session: the content is there, no UI, every path relative or built in.
        back = run_in_blender(f"""
with bpy.data.libraries.load({blend!r}) as (data_from, data_to):
    listing = {{"screens": list(data_from.screens), "workspaces": list(data_from.workspaces),
               "objects": sorted(data_from.objects), "collections": sorted(data_from.collections), "scenes": list(data_from.scenes)}}
bpy.ops.wm.open_mainfile(filepath={blend!r}, load_ui=False)
paths = [i.filepath for coll in (bpy.data.fonts, bpy.data.images, bpy.data.libraries, bpy.data.sounds) for i in coll]
emit(listing=listing, paths=paths, params=dict(bpy.data.objects["PARAMETERS"].items()),
     units=[bpy.data.scenes["3dprint-scout"].unit_settings.system, bpy.data.scenes["3dprint-scout"].unit_settings.length_unit],
     world=bpy.data.scenes["3dprint-scout"].world.name)
""")
        self.assertEqual((back["listing"]["screens"], back["listing"]["workspaces"]), ([], []))
        self.assertEqual(back["listing"]["scenes"], ["3dprint-scout"])
        self.assertIn("lid", back["listing"]["objects"])
        self.assertIn("PARAMETERS", back["listing"]["objects"])
        self.assertNotIn("Cube", back["listing"]["objects"])                   # the default file's cube is not ours
        self.assertEqual(back["listing"]["collections"], ["lid", "mark"] if ttf else ["lid"])
        self.assertTrue(all(p == "" or p == "<builtin>" or p.startswith("//") for p in back["paths"]), back["paths"])
        self.assertTrue(all("/" not in p[2:] and "\\" not in p for p in back["paths"] if p.startswith("//")), back["paths"])
        self.assertEqual(back["params"]["w"], 10.0)
        self.assertEqual(back["units"], ["METRIC", "MILLIMETERS"])
        # Uncompressed twin for the scan, compressed file shipped: the twin's scan sees the strings.
        for s in (os.path.expanduser("~"), self.tmp, os.getcwd(), ENGINES):
            if len(s) >= 5:
                self.assertNotIn(s.encode(), data, s)

    def test_live_session_leaves_the_users_file_and_data_alone(self):
        """The user's file is open, with their object and a collection named like the part's
        object holding their secret object; the build runs through main() like the live loader."""
        users_file = os.path.join(self.tmp, "users_project.blend")
        out = os.path.join(self.tmp, "out")
        rep = run_in_blender(f"""
user = bpy.data.objects.new("users_work", bpy.data.meshes.new("users_mesh"))
bpy.context.scene.collection.objects.link(user)
col = bpy.data.collections.new("body")
bpy.context.scene.collection.children.link(col)
secret = bpy.data.objects.new("users_secret_obj", bpy.data.meshes.new("users_secret_mesh"))
col.objects.link(secret)
bpy.ops.wm.save_as_mainfile(filepath={users_file!r})
user.location = (1, 2, 3)                                   # an unsaved change
first_scene = bpy.context.scene.name
{GEN}
bb.main(build, {{"w": 30.0}}, argv=["blender", "--", "--out", {out!r}])
bb.main(build, {{"w": 30.0}}, argv=["blender", "--", "--out", {out!r}])   # a second run removes only its own
emit(filepath=bpy.data.filepath, context_scene=bpy.context.scene.name, first=first_scene,
     scenes=sorted(s.name for s in bpy.data.scenes), loc=list(user.location),
     user_col=[o.name for o in bpy.data.collections["body"].objects], user_col_tag=bpy.data.collections["body"].get(bb.TAG),
     ours=ours(), our_cols=sorted(c.name for c in bpy.data.collections if c.get(bb.TAG)),
     all_objects=sorted(o.name for o in bpy.data.objects), log=bb.LOG)
""")
        self.assertEqual(rep["filepath"], users_file)                          # still the user's file
        self.assertEqual(rep["context_scene"], rep["first"])                   # their window's scene untouched
        self.assertEqual(rep["scenes"], sorted({rep["first"], "3dprint-scout"}))
        self.assertEqual(rep["loc"], [1.0, 2.0, 3.0])                          # their unsaved edit kept
        self.assertEqual((rep["user_col"], rep["user_col_tag"]), (["users_secret_obj"], None))
        self.assertEqual(rep["ours"], ["PARAMETERS", "body"])
        self.assertEqual(rep["our_cols"], ["body.001"])                         # the user's 'body' was not reused
        self.assertIn("users_secret_obj", rep["all_objects"])
        self.assertFalse(any("reset" in n for n in rep["log"]))
        blend = os.path.join(out, "model.blend")
        self.assertTrue(os.path.isfile(blend))
        back = run_in_blender(f"""
with bpy.data.libraries.load({blend!r}) as (data_from, data_to):
    emit(objects=sorted(data_from.objects), collections=sorted(data_from.collections), meshes=sorted(data_from.meshes))
""")
        self.assertEqual(back["objects"], ["PARAMETERS", "body"])              # nothing of the user's in the deliverable
        self.assertEqual(back["collections"], ["body.001"])
        self.assertNotIn("users_secret_mesh", back["meshes"])
        # The user's file on disk is what they saved; the first scan string of a leak would be its name.
        with open(blend, "rb") as f:
            self.assertNotIn(b"users_secret", f.read())

    def test_part_refuses_the_users_own_objects(self):
        """A generator that hands part() an object of the user's (in their scene or their
        collection) gets an error; the object keeps its name, collections and no tag."""
        rep = run_in_blender("""
user = bpy.data.objects.new("users_work", bpy.data.meshes.new("users_mesh"))
bpy.context.scene.collection.objects.link(user)
col = bpy.data.collections.new("users_col")
bpy.context.scene.collection.children.link(col)
kept = bpy.data.objects.new("users_kept", bpy.data.meshes.new("users_kept_mesh"))
col.objects.link(kept)
bb.new_scene_mm()
errors = []
for obj in (user, kept):
    try:
        bb.part(obj, "body")
    except ValueError as exc:
        errors.append(str(exc))
emit(errors=errors, user=[user.name, sorted(c.name for c in user.users_collection), user.get(bb.TAG)],
     kept=[kept.name, sorted(c.name for c in kept.users_collection), kept.get(bb.TAG)])
""")
        self.assertEqual(len(rep["errors"]), 2, rep)
        self.assertTrue(all("not the build's own" in e for e in rep["errors"]), rep["errors"])
        self.assertEqual(rep["user"][0], "users_work")
        self.assertIsNone(rep["user"][2])
        self.assertEqual(rep["kept"], ["users_kept", ["users_col"], None])

    def test_main_blend_argument_is_guarded(self):
        users_file = os.path.join(self.tmp, "users.blend")
        out = os.path.join(self.tmp, "out")
        elsewhere = os.path.join(self.tmp, "elsewhere.blend")
        rep = run_in_blender(f"""
bpy.ops.wm.save_as_mainfile(filepath={users_file!r})
{GEN}
results = {{}}
for label, argv in (("open", ["--out", {out!r}, "--blend", {users_file!r}]),
                    ("outside", ["--out", {out!r}, "--blend", {elsewhere!r}]),
                    ("missing_out", ["--blend", {os.path.join(out, "x.blend")!r}])):
    try:
        bb.main(build, {{"w": 20.0}}, argv=["blender", "--"] + argv); results[label] = None
    except (ValueError, SystemExit) as exc:
        results[label] = str(exc) or type(exc).__name__
bb.main(build, {{"w": 20.0}}, argv=["blender", "--", "--out", {out!r}, "--blend", {os.path.join(out, "new.blend")!r}])
try:
    bb.main(build, {{"w": 20.0}}, argv=["blender", "--", "--out", {out!r}, "--blend", {os.path.join(out, "new.blend")!r}]); results["existing"] = None
except ValueError as exc:
    results["existing"] = str(exc)
bb.main(build, {{"w": 20.0}}, argv=["blender", "--", "--out", {out!r}])
bb.main(build, {{"w": 20.0}}, argv=["blender", "--", "--out", {out!r}])            # the default working copy is rewritten
emit(results=results, files=sorted(os.listdir({out!r})), filepath=bpy.data.filepath)
""")
        self.assertIn("open in Blender", rep["results"]["open"])
        self.assertIn("inside --out", rep["results"]["outside"])
        self.assertIsNotNone(rep["results"]["missing_out"])                    # --out is required
        self.assertIn("already exists", rep["results"]["existing"])
        self.assertEqual(rep["files"], ["body.stl", "model.blend", "new.blend"])
        self.assertFalse(os.path.exists(elsewhere))
        self.assertEqual(rep["filepath"], users_file)
        # The user's file was refused before anything was built: it is byte-for-byte what Blender saved.
        back = run_in_blender(f"""
with bpy.data.libraries.load({users_file!r}) as (data_from, data_to):
    emit(objects=sorted(data_from.objects), scenes=list(data_from.scenes))
""")
        self.assertNotIn("body", back["objects"])
        self.assertNotIn("3dprint-scout", back["scenes"])

    def test_render_views_give_a_sane_png_and_catch_a_black_background(self):
        png = os.path.join(self.tmp, "r.png")
        rep = run_in_blender(f"""
bb.new_scene_mm()
a = bb.box([40, 30, 6], "body"); bb.part(a, "body")
b = bb.cylinder(5, 3, name="knob"); b.location = (20, 15, 6); bb.part(b, "knob", object="body", role="fused")
r = bb.render_views({png!r}, ["iso", "front", "right", "top"], {{"knob": (1.0, 1.0, 1.0)}}, "workbench", (640, 480))
try:
    bb.render_views({png!r}, ["iso"], {{}}, "workbench", (320, 240)); again = None
except FileExistsError as exc:
    again = str(exc)
orig = bb._setup_engine
def dark(sc, engine):
    extras = orig(sc, engine)
    sc.world.color = (0.0, 0.0, 0.0)                       # what a missing world looked like on 4.5
    return extras
bb._setup_engine = dark
black = bb.render_views({os.path.join(self.tmp, "black.png")!r}, ["iso"], {{}}, "workbench", (320, 240))
bb._setup_engine = orig
for o in (a, b):
    o.hide_render = True                                    # nothing drawn: only the caption and the grid lines
blank = bb.render_views({os.path.join(self.tmp, "blank.png")!r}, ["iso", "front", "right", "top"], {{}}, "workbench", (1600, 1200))
emit(r=r, again=again, black=black, blank=blank, leftovers=[o.name for o in bpy.data.objects if o.name.startswith("_render")],
     materials=[m.name for m in bpy.data.materials if m.name.startswith("_render")], camera=bb.scene().camera,
     eevee=bb.engine_id("eevee"), files=sorted(os.listdir({self.tmp!r})))
""")
        r = rep["r"]
        self.assertTrue(r["sane"], r)
        self.assertGreater(r["fg"], 0.0005)
        self.assertLess(r["fg"], 0.95)
        self.assertEqual(r["size_mm"], [40.0, 30.0, 9.0])
        self.assertEqual(r["views"], ["iso", "front", "right", "top"])
        self.assertIn("already exists", rep["again"])                           # no silent overwrite
        self.assertFalse(rep["black"]["sane"])
        self.assertIn("no background", rep["black"]["note"])
        self.assertGreater(rep["black"]["fg"], 0.95)
        blank = rep["blank"]                                                   # captions and grid lines are not the part
        self.assertEqual((blank["sane"], blank["fg"]), (False, 0.0), blank)
        self.assertEqual(blank["fg_views"], {"iso": 0.0, "front": 0.0, "right": 0.0, "top": 0.0})
        self.assertIn("blank image", blank["note"])
        self.assertTrue(all(f > 0.0005 for f in r["fg_views"].values()), r["fg_views"])
        self.assertEqual(rep["leftovers"], [])                                 # cameras and labels cleaned up
        self.assertEqual(rep["materials"], [])
        self.assertIsNone(rep["camera"])
        self.assertIn(rep["eevee"], ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"))
        self.assertEqual(rep["files"], ["black.png", "blank.png", "r.png"])    # the tile folder is gone
        with open(png, "rb") as f:
            head = f.read(24)
        self.assertTrue(head.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", head[16:24]), (640, 480))

    def test_render_colours_read_true(self):
        """A white part reads white and an orange one orange: colours go in scene-linear and the
        studio light keeps faces towards the camera near their colour (the field test on
        Blender 5.2.2 drew Jade White as (176, 178, 179) and Orange as (177, 126, 74))."""
        png = os.path.join(self.tmp, "c.png")
        rep = run_in_blender(f"""
import numpy as np
bb.new_scene_mm()
w = bb.box([30, 30, 4], "white"); bb.part(w, "white")
o = bb.box([30, 30, 4], "orange"); o.location = (40, 0, 0); bb.part(o, "orange")
k = bb.box([30, 30, 4], "black"); k.location = (80, 0, 0); bb.part(k, "black")
cols = {{"white": bb.filament_rgb("Jade White"), "orange": bb.hex_rgb("#ff6a13"), "black": bb.filament_rgb("Black")}}
r = bb.render_views({png!r}, ["top"], cols, "workbench", (1100, 400))
img = bpy.data.images.load({png!r})
W, H = img.size
px = np.empty(W * H * 4, dtype=np.float32); img.pixels.foreach_get(px)
px = (px.reshape(H, W, 4)[..., :3] * 255).round().astype(int)
row = px[H // 2]
inside = [i for i in range(W) if abs(int(row[i][0]) - 246) > 12 or abs(int(row[i][2]) - 246) > 12]
a, b = inside[0], inside[-1]
pick = lambda f: [int(v) for v in row[int(a + (b - a) * f)]]
emit(r=r, white=pick(30 / 220), orange=pick(110 / 220), black=pick(190 / 220), corner=[int(v) for v in px[H - 5][W - 5]])
""")
        self.assertTrue(rep["r"]["sane"], rep["r"])
        self.assertTrue(all(abs(c - 246) <= 2 for c in rep["corner"]), rep)              # preview.py's background
        self.assertGreaterEqual(min(rep["white"]), 200, rep)                            # white, not grey (4.x: shadows on)...
        self.assertLessEqual(max(rep["white"]), 246 - 10, rep)                          # ...but off the background (S2-F12)
        # Three 30 mm squares fill about 46 % of the frame; a white face that faded into the
        # background would leave the blank check with its outline only (about 30 %).
        self.assertGreater(rep["r"]["fg_views"]["top"], 0.42, rep["r"])
        r_, g_, b_ = rep["orange"]
        self.assertTrue(r_ >= 215 and g_ <= 125 and b_ <= 60, rep)                      # orange, not tan
        self.assertTrue(20 <= max(rep["black"]) <= 90, rep)                             # black: dark grey, edges show

    def test_render_captions_pockets_and_facets(self):
        """S3-11: a view's caption is hidden after its tile, so BACK does not show FRONT's
        mirrored; S3-10: a blind pocket seen head-on darkens (world-space cavity scaled to the
        part); S1-F13: a cylinder is shaded smooth for the render, and the mesh is put back."""
        rep = run_in_blender(f"""
import numpy as np
def pixels(png):
    img = bpy.data.images.load(png); W, H = img.size
    px = np.empty(W * H * 4, dtype=np.float32); img.pixels.foreach_get(px); bpy.data.images.remove(img)
    return (px.reshape(H, W, 4)[..., :3] * 255).round().astype(int), W, H
bb.new_scene_mm()
plate = bb.box([40, 30, 4], "plate"); bb.part(plate, "plate")
bb.render_views({os.path.join(self.tmp, "cap.png")!r}, ["front", "back", "top", "bottom"], {{}}, "workbench", (800, 600))
px, W, H = pixels({os.path.join(self.tmp, "cap.png")!r})
# The BACK tile is top right (buffer rows are bottom-up): FRONT's caption, drawn mirrored from
# behind, would land in its lower right band, where the thin plate seen edge-on never reaches.
band = px[302:330, 600:800]                                                   # above the grid line
cap = dict(leaked=int((np.abs(band - 246) > 8).any(axis=2).sum()), own=int((np.abs(px[302:330, 402:560] - 246) > 8).any(axis=2).sum()))
bb.new_scene_mm()
body = bb.box([40, 30, 10], "body")
hole = bb.cylinder(4.0, 6.0, name="hole"); hole.location = (20, 15, 5)       # a blind 8 mm pocket, 5 mm deep
bb.boolean(body, hole, "difference"); bb.part(body, "body")
old_ssao = bb.scene().display.matcap_ssao_distance
seen = {{}}
orig = bb._setup_engine
def spy(sc, engine):
    seen["before"] = sc.display.matcap_ssao_distance
    return orig(sc, engine)
bb._setup_engine = spy
r = bb.render_views({os.path.join(self.tmp, "pocket.png")!r}, ["top"], {{"body": (1.0, 1.0, 1.0)}}, "workbench", (400, 300))
bb._setup_engine = orig
px, W, H = pixels({os.path.join(self.tmp, "pocket.png")!r})
pocket = dict(centre=px[H // 2, W // 2].tolist(), near_wall=px[H // 2, W // 2 + 29].tolist(), face=px[H // 2, W // 4].tolist(),
              ssao_before=seen["before"], ssao_after=bb.scene().display.matcap_ssao_distance, old=old_ssao)
bb.new_scene_mm()
cyl = bb.cylinder(10, 20, segments=48, name="cyl"); bb.part(cyl, "cyl")
me = cyl.data
me.polygons[0].use_smooth = True                                               # one face of the user's own choice
before = (sum(p.use_smooth for p in me.polygons), me.attributes.get("sharp_edge") is not None)
bb.render_views({os.path.join(self.tmp, "smooth.png")!r}, ["front"], {{"cyl": (0.3, 0.5, 0.8)}}, "workbench", (400, 300))
after = (sum(p.use_smooth for p in me.polygons), me.attributes.get("sharp_edge") is not None)
px, W, H = pixels({os.path.join(self.tmp, "smooth.png")!r})
row = px[H // 2, :, 1].astype(int)
inside = [i for i in range(W) if abs(int(row[i]) - 246) > 12]
a, b = inside[0] + 6, inside[-1] - 6
smooth_steps = int(np.abs(np.diff(row[a:b])).max())
bb._smooth_by_angle = lambda o, angle=30.0: (lambda: None)
bb.render_views({os.path.join(self.tmp, "flat.png")!r}, ["front"], {{"cyl": (0.3, 0.5, 0.8)}}, "workbench", (400, 300))
px, W, H = pixels({os.path.join(self.tmp, "flat.png")!r})
flat_steps = int(np.abs(np.diff(px[H // 2, a:b, 1].astype(int))).max())
emit(cap=cap, pocket=pocket, before=list(before), after=list(after), smooth_steps=smooth_steps, flat_steps=flat_steps)
""")
        self.assertEqual(rep["cap"]["leaked"], 0, rep["cap"])                           # no mirrored FRONT caption in BACK
        self.assertGreater(rep["cap"]["own"], 20, rep["cap"])                           # BACK's own caption is there
        p = rep["pocket"]
        self.assertGreaterEqual(p["face"][0] - p["centre"][0], 10, p)                   # the pocket floor reads darker
        self.assertGreaterEqual(p["face"][0] - p["near_wall"][0], 12, p)                # (5.x: cavity; 4.x: shadows)
        self.assertAlmostEqual(p["ssao_before"], 6.0, places=5)                         # 0.15 x 40 mm
        self.assertEqual(p["ssao_after"], p["old"])                                     # put back
        self.assertEqual(rep["before"], [1, False])
        self.assertEqual(rep["after"], [1, False])                                      # the mesh as it was
        self.assertLessEqual(rep["smooth_steps"], 4, rep)                               # a gradient...
        self.assertGreaterEqual(rep["flat_steps"], 8, rep)                              # ...where flat shading steps


if __name__ == "__main__":
    unittest.main()
