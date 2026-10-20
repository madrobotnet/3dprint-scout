"""references/engines/blender_builder.py: the pure helpers import and work without Blender; with
the `bpy` module the Blender calls are run for real in a subprocess (importing bpy loads most of
Blender, so it never happens in the test process) and their STLs go through validate.py."""
import glob
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
               "    print('@@' + json.dumps(kw, default=str))\n")
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
        ns = self.bb.cli_args(["gen.py", "--params", "p.json"])            # plain python, no --
        self.assertEqual((ns.cmd, ns.params, ns.out), ("build", "p.json", None))
        ns = self.bb.cli_args(["blender_builder.py", "--", "render", "a.stl", "b.stl", "-o", "r.png",
                               "--views", "iso,top", "--size", "800x600", "--engine", "cycles", "--color", "a=black"])
        self.assertEqual((ns.cmd, ns.stl, ns.out, ns.views, ns.size, ns.engine, ns.color),
                         ("render", ["a.stl", "b.stl"], "r.png", "iso,top", "800x600", "cycles", ["a=black"]))

    def test_segments_from_the_line_width(self):
        bb = self.bb
        self.assertEqual(bb.segments_for(1.2), 5)                 # pi/2 * 1.2 / 0.45 = 4.19 -> 5
        self.assertEqual(bb.segments_for(0.3), 2)                 # never below 2
        self.assertEqual(bb.segments_for(50.0), bb.MAX_SEGMENTS)  # capped
        self.assertEqual(bb.segments_for(2.0, line_width=0.6), 6)
        with self.assertRaises(ValueError):
            bb.segments_for(0)

    def test_filament_colours(self):
        bb = self.bb
        self.assertEqual(bb.filament_rgb("#ff0000"), (1.0, 0.0, 0.0))
        self.assertEqual(bb.filament_rgb("Bambu PLA Basic Jade White"), (1.0, 1.0, 1.0))
        self.assertEqual(bb.filament_rgb("black"), (0.0, 0.0, 0.0))
        self.assertEqual(bb.filament_rgb("PLA Matte Mistletoe Green"), bb.hex_rgb(bb.FILAMENTS["mistletoegreen"]))
        self.assertEqual(bb.filament_rgb("no such colour", default=(0.5, 0.5, 0.5)), (0.5, 0.5, 0.5))
        with self.assertRaises(ValueError):
            bb.filament_rgb("no such colour")
        with self.assertRaises(ValueError):
            bb.hex_rgb("#12345")
        colours = bb.parse_colors(["lid=black"], ["box", "lid"])
        self.assertEqual(colours["lid"], (0.0, 0.0, 0.0))
        self.assertEqual(colours["box"], bb.palette_rgb(0))
        with self.assertRaises(ValueError):
            bb.parse_colors(["nope=black"], ["box"])

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

    def test_prop_values(self):
        bb = self.bb
        self.assertEqual(bb.prop_value(2.5), 2.5)
        self.assertEqual(bb.prop_value(True), True)
        self.assertEqual(bb.prop_value("x"), "x")
        self.assertEqual(bb.prop_value([1, 2.5]), [1.0, 2.5])
        self.assertEqual(bb.prop_value(["a", "b"]), '["a", "b"]')
        self.assertEqual(bb.prop_value({"k": 1}), '{"k": 1}')

    def test_summary_line(self):
        line = self.bb.summary([{"name": "a"}], blend=None)
        self.assertTrue(line.startswith("@@3DPS "))
        doc = json.loads(line[7:])
        self.assertEqual((doc["schema"], doc["parts"], doc["blend"]), (self.bb.SCHEMA, [{"name": "a"}], None))

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
emit(units=[us.system, us.length_unit, round(us.scale_length, 6)], info=info, version=list(bpy.app.version))
""")
        self.assertEqual(rep["units"], ["METRIC", "MILLIMETERS", 0.001])
        self.assertGreaterEqual(tuple(rep["version"][:2]), (4, 2))
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

    def test_boolean_solver_by_version_and_manifold_result(self):
        rep = run_in_blender(f"""
bb.new_scene_mm()
body = bb.box([30, 20, 10], "body")
hole = bb.cylinder(3.0, 12.0, name="hole"); hole.location = (10, 10, -1)
bb.boolean(body, hole, "difference")
bb.part(body, "body")
bb.export_parts({self.tmp!r})
emit(solver=bb.boolean_solver(), version=list(bpy.app.version), log=bb.LOG, objects=sorted(o.name for o in bpy.data.objects))
""")
        expected = "MANIFOLD" if tuple(rep["version"][:2]) >= (4, 5) else "EXACT"
        self.assertEqual(rep["solver"], expected)
        self.assertTrue(any(f"solver {expected}" in n for n in rep["log"]), rep["log"])
        self.assertNotIn("hole", rep["objects"])                               # the tool is gone after apply
        f = check(os.path.join(self.tmp, "body.stl"), "--expect", "30,20,10")
        self.assertEqual({k: f["checks"][k]["state"] for k in ("D1", "M1", "M2", "M3", "M4", "M5")}, {k: "PASS" for k in ("D1", "M1", "M2", "M3", "M4", "M5")})
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
        rep = run_in_blender(f"""
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

    def test_text_part_exports_at_its_cap_height(self):
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

    def test_parts_go_into_collections_and_params_into_props(self):
        rep = run_in_blender("""
bb.new_scene_mm()
a = bb.box([10, 10, 2], "a"); b = bb.box([4, 4, 1], "b"); b.location = (3, 3, 2)
bb.part(a, "lid"); bb.part(b, "label", object="lid", role="fused")
e = bb.params_to_props({"w": 10.0, "name": "x", "flag": True, "_parts": {"lid": {}}, "list": [1, 2], "words": ["a", "b"]})
cols = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections}
emit(cols=cols, role=b.get("role"), obj=b.get("object"), props={k: (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else v) for k, v in e.items()},
     in_root=sorted(o.name for o in bpy.context.scene.collection.objects))
""")
        self.assertEqual(rep["cols"], {"lid": ["label", "lid"]})
        self.assertEqual((rep["role"], rep["obj"]), ("fused", "lid"))
        self.assertNotIn("_parts", rep["props"])
        self.assertEqual(rep["props"]["w"], 10.0)
        self.assertEqual(rep["props"]["words"], '["a", "b"]')
        self.assertEqual(rep["props"]["list"], [1.0, 2.0])
        self.assertIn("PARAMETERS", rep["in_root"])
        with self.assertRaises(AssertionError):                               # a bad role is refused
            run_in_blender("bb.new_scene_mm(); a = bb.box([1,1,1]); bb.part(a, 'a', role='glued'); emit()")

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
emit(second=second, fonts=[(f.name, f.filepath, f.packed_file is not None) for f in bpy.data.fonts])
""")
        self.assertIn("already exists", rep["second"])
        with open(blend, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"BLENDER"))
        for s in (os.path.expanduser("~"), self.tmp, os.getcwd(), ENGINES):
            if len(s) >= 5:
                self.assertNotIn(s.encode(), data, s)
        if ttf:
            self.assertNotIn(os.path.dirname(ttf).encode(), data)
            packed = [f for f in rep["fonts"] if f[2]]
            self.assertEqual(packed[0][1], "//" + os.path.basename(ttf))
        # Reload in a fresh session: the content is there, every path is relative or built in.
        back = run_in_blender(f"""
bpy.ops.wm.open_mainfile(filepath={blend!r}, load_ui=False)
paths = [i.filepath for coll in (bpy.data.fonts, bpy.data.images, bpy.data.libraries, bpy.data.sounds) for i in coll]
emit(objects=sorted(o.name for o in bpy.data.objects), cols=sorted(c.name for c in bpy.data.collections),
     paths=paths, params=dict(bpy.data.objects["PARAMETERS"].items()),
     units=[bpy.data.scenes[0].unit_settings.system, bpy.data.scenes[0].unit_settings.length_unit],
     screens=len(bpy.data.screens), workspaces=len(bpy.data.workspaces))
""")
        self.assertIn("lid", back["objects"])
        self.assertIn("PARAMETERS", back["objects"])
        self.assertEqual(back["cols"], ["lid", "mark"] if ttf else ["lid"])
        self.assertTrue(all(p == "" or p == "<builtin>" or p.startswith("//") for p in back["paths"]), back["paths"])
        self.assertTrue(all("/" not in p[2:] and "\\" not in p for p in back["paths"] if p.startswith("//")), back["paths"])
        self.assertEqual(back["params"]["w"], 10.0)
        self.assertEqual(back["units"], ["METRIC", "MILLIMETERS"])

    def test_live_session_is_never_reset(self):
        users_file = os.path.join(self.tmp, "users_file.blend")
        rep = run_in_blender(f"""
# A "live" session: the user's own file is open (bpy.data.filepath is set) with their object in it.
user = bpy.data.objects.new("users_work", bpy.data.meshes.new("users_mesh"))
bpy.context.scene.collection.objects.link(user)
bpy.ops.wm.save_as_mainfile(filepath={users_file!r})
first_scene = bpy.context.scene.name
wipe = bb.can_wipe()
sc = bb.new_scene_mm()
a = bb.box([5, 5, 5], "a"); bb.part(a, "a")
sc2 = bb.new_scene_mm()                       # a second run removes only what the first one made
emit(wipe=wipe, scene=sc.name, same=sc is sc2, scenes=sorted(s.name for s in bpy.data.scenes),
     objects=sorted(o.name for o in bpy.data.objects), first=first_scene, note=bb.LOG[0],
     filepath=bpy.data.filepath)
""")
        self.assertFalse(rep["wipe"])
        self.assertEqual(rep["filepath"], users_file)                           # still the user's file
        self.assertEqual(rep["scene"], "3dprint-scout")
        self.assertTrue(rep["same"])
        self.assertEqual(rep["scenes"], sorted({rep["first"], "3dprint-scout"}))
        self.assertIn("users_work", rep["objects"])
        self.assertNotIn("a", rep["objects"])
        self.assertIn("not reset", rep["note"])

    def test_render_views_give_a_sane_png(self):
        png = os.path.join(self.tmp, "r.png")
        rep = run_in_blender(f"""
bb.new_scene_mm()
a = bb.box([40, 30, 6], "body"); bb.part(a, "body")
b = bb.cylinder(5, 3, name="knob"); b.location = (20, 15, 6); bb.part(b, "knob", object="body", role="fused")
r = bb.render_views({png!r}, ["iso", "front", "right", "top"], {{"knob": (1.0, 1.0, 1.0)}}, "workbench", (640, 480))
emit(r=r, leftovers=[o.name for o in bpy.data.objects if o.name.startswith("_render")],
     materials=[m.name for m in bpy.data.materials], camera=bpy.context.scene.camera)
""")
        r = rep["r"]
        self.assertGreater(r["fg"], 0.0005)
        self.assertEqual(r["size_mm"], [40.0, 30.0, 9.0])
        self.assertEqual(r["views"], ["iso", "front", "right", "top"])
        self.assertEqual(rep["leftovers"], [])                                 # cameras and labels cleaned up
        self.assertEqual(rep["materials"], [])
        self.assertIsNone(rep["camera"])
        with open(png, "rb") as f:
            head = f.read(24)
        self.assertTrue(head.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", head[16:24]), (640, 480))
        self.assertFalse(glob.glob(os.path.join(self.tmp, "r._*.png")))        # the per-view files are gone


if __name__ == "__main__":
    unittest.main()
