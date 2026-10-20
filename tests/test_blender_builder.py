"""references/engines/blender_builder.py: the pure helpers import and work without Blender; with
the `bpy` module the Blender calls are run for real in a subprocess (importing bpy loads most of
Blender, so it stays out of the test process itself) and their STLs go through validate.py.
Every subprocess starts from Blender's default file (a Cube, a Camera, a Light in "Scene"): the
module must build next to that, never reset it, and the tests look only at what it tagged."""
import glob
import hashlib
import io
import json
import os
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
        self.assertEqual(bb.preview_rgb((0.0, 0.0, 0.0)), (0.3, 0.3, 0.3))       # black lifted for the preview
        self.assertEqual(bb.preview_rgb((1.0, 1.0, 1.0)), (1.0, 1.0, 1.0))
        self.assertEqual(bb.rgb_hex((1.0, 0.0, 0.5)), "#ff0080")

    def test_foreground_bounds(self):
        bb = self.bb
        self.assertFalse(bb.fg_sane(0.0)[0])
        self.assertFalse(bb.fg_sane(0.0003)[0])
        self.assertTrue(bb.fg_sane(0.2)[0])
        ok, note = bb.fg_sane(0.99)                                # a black or missing background
        self.assertFalse(ok)
        self.assertIn("no background", note)

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
        forb = bb.forbidden_strings("/tmp/some/out")
        self.assertIn(b"/tmp/some/out", forb)
        self.assertTrue(all(len(f) >= 5 for f in forb))
        self.assertEqual(bb.find_forbidden(b"xx /tmp/some/out/a.stl yy", forb), ["/tmp/some/out"])
        self.assertEqual(bb.find_forbidden(b"nothing here", [b"/tmp/some/out"]), [])
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
        self.assertIn("1 touching pair", notes["AARON"])
        self.assertIn("separate bodies", notes["Ab3"])

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
emit(r=r, again=again, black=black, leftovers=[o.name for o in bpy.data.objects if o.name.startswith("_render")],
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
        self.assertEqual(rep["leftovers"], [])                                 # cameras and labels cleaned up
        self.assertEqual(rep["materials"], [])
        self.assertIsNone(rep["camera"])
        self.assertIn(rep["eevee"], ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"))
        self.assertEqual(rep["files"], ["black.png", "r.png"])                 # the tile folder is gone
        with open(png, "rb") as f:
            head = f.read(24)
        self.assertTrue(head.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", head[16:24]), (640, 480))


if __name__ == "__main__":
    unittest.main()
