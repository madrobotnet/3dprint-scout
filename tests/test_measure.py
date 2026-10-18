"""Tests for scripts/measure.py: 3MF loading with transforms, slices with fits, ray depth maps."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
from test_validate import box, cylinder, write_stl  # noqa: E402

HAS_NP = find_spec("numpy") is not None
HAS_M3D = HAS_NP and find_spec("manifold3d") is not None


def run(*argv):
    import measure
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = measure.main(list(argv))
    return code, json.loads(buf.getvalue())


@unittest.skipUnless(HAS_NP, "numpy not installed")
class Info(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_core_3mf_components_and_item_transforms(self):
        """A grouped core 3MF (threemf.py): parts under one parent, the parent placed by the
        build item; measure.py reports the placed boxes."""
        import threemf
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3, 100, 100, 5))
        label = os.path.join(self.d, "label.stl"); write_stl(label, box(30, 10, 1, 115, 115, 8))
        bar = os.path.join(self.d, "bar.stl"); write_stl(bar, box(300, 20, 10))
        out = os.path.join(self.d, "g.3mf")
        threemf.write_core_3mf([("lid", lid), ("label", label), ("bar", bar)], out, bed=(256, 256),
                               objects=[{"name": "lid", "parts": ["lid", "label"], "main": "lid"}])
        code, rep = run("info", out, "--extract", os.path.join(self.d, "x"))
        self.assertEqual(code, 0, rep["errors"])
        objs = {o["name"]: o for o in rep["objects"]}
        self.assertEqual(objs["lid"]["size_mm"], [60.0, 40.0, 4.0])
        self.assertEqual(objs["lid"]["bbox_min_mm"], [0.0, 0.0, 0.0])          # placed on the bed at the cursor
        self.assertEqual([p["name"] for p in objs["lid"]["parts"]], ["lid", "label"])
        self.assertEqual(objs["lid"]["parts"][1]["bbox_min_mm"], [15.0, 15.0, 3.0])
        self.assertEqual(objs["lid"]["triangles"], 24)
        self.assertLess(objs["bar"]["size_mm"][0], 256.1)                     # rotated to fit, as placed
        self.assertTrue(os.path.isfile(objs["lid"]["stl"]))
        if HAS_M3D:
            self.assertTrue(objs["bar"]["watertight"])
            self.assertAlmostEqual(objs["bar"]["volume_mm3"], 300 * 20 * 10, delta=1)

    def test_bambu_3mf_parts_keep_positions_and_names(self):
        import bambu3mf
        from test_bambu3mf import make_template
        template = os.path.join(self.d, "t.3mf")
        make_template(template)
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3))
        label = os.path.join(self.d, "label.stl"); write_stl(label, box(30, 10, 1, 15, 15, 3))
        out = os.path.join(self.d, "b.3mf")
        bambu3mf.build({"template": template, "out": out,
                        "parts": [{"name": "lid", "stl": lid}, {"name": "label", "stl": label, "object": "lid", "filament": 2}]})
        code, rep = run("info", out)
        self.assertEqual(code, 0, rep["errors"])
        o = rep["objects"][0]
        self.assertEqual(o["name"], "lid")
        self.assertEqual([p["name"] for p in o["parts"]], ["lid", "label"])
        self.assertEqual(o["size_mm"], [60.0, 40.0, 4.0])
        lid_p, label_p = o["parts"]
        self.assertAlmostEqual(label_p["bbox_min_mm"][2] - lid_p["bbox_min_mm"][2], 3.0, places=3)
        self.assertAlmostEqual(label_p["bbox_min_mm"][0] - lid_p["bbox_min_mm"][0], 15.0, places=3)
        self.assertAlmostEqual(lid_p["bbox_min_mm"][2], 0.0, places=3)

    def test_unit_conversion_and_errors(self):
        import zipfile
        import threemf
        a = os.path.join(self.d, "a.stl"); write_stl(a, box(1, 2, 3))
        out = os.path.join(self.d, "inch.3mf")
        threemf.write_core_3mf([("a", a)], out)
        with zipfile.ZipFile(out) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        entries["3D/3dmodel.model"] = entries["3D/3dmodel.model"].replace(b'unit="millimeter"', b'unit="inch"')
        with zipfile.ZipFile(out, "w") as z:
            for n, data in entries.items():
                z.writestr(n, data)
        code, rep = run("info", out)
        self.assertEqual(rep["objects"][0]["size_mm"], [25.4, 50.8, 76.2])
        # A sub-file keeps its own unit: a Bambu-style component file in millimetres under an inch root.
        from test_bambu3mf import make_template
        import bambu3mf
        template = os.path.join(self.d, "t.3mf"); make_template(template)
        b = os.path.join(self.d, "mixed.3mf")
        bambu3mf.build({"template": template, "out": b, "parts": [{"name": "a&b <c>", "stl": a}]})
        with zipfile.ZipFile(b) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        entries["3D/3dmodel.model"] = entries["3D/3dmodel.model"].replace(b'unit="millimeter"', b'unit="inch"')
        with zipfile.ZipFile(b, "w") as z:
            for n, data in entries.items():
                z.writestr(n, data)
        code, rep = run("info", b)
        self.assertEqual(rep["objects"][0]["size_mm"], [1.0, 2.0, 3.0])       # the mesh file says millimeter
        self.assertEqual(rep["objects"][0]["name"], "a&b <c>")              # entities unescaped
        code, rep = run("info", os.path.join(self.d, "missing.stl"))
        self.assertEqual(code, 1)
        self.assertIn("not found", rep["errors"][0])
        code, rep = run("slice", a, "--z", "1", "--object", "nope")
        self.assertEqual(code, 1)
        self.assertIn("no object", rep["errors"][0])


@unittest.skipUnless(HAS_NP, "numpy not installed")
class Slice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_box_and_cylinder_loops(self):
        tube = os.path.join(self.d, "t.stl")
        write_stl(tube, box(40, 30, 10, 5, 5, 0))
        code, rep = run("slice", tube, "--z", "2,8", "--center")
        self.assertEqual(code, 0, rep["errors"])
        self.assertEqual(rep["shift_mm"], [-25.0, -20.0, 0.0])
        for level in rep["levels"]:
            self.assertEqual(len(level["loops"]), 1)
            loop = level["loops"][0]
            self.assertEqual(loop["size"], [40.0, 30.0])
            self.assertEqual(loop["bounds"], [-20.0, -15.0, 20.0, 15.0])
            self.assertAlmostEqual(loop["area_mm2"], 1200.0, places=1)
            self.assertFalse(loop.get("is_circle", False))
            self.assertEqual(loop["corner_radii_mm"], {"x0y0": 0.0, "x1y0": 0.0, "x1y1": 0.0, "x0y1": 0.0})
        cyl = os.path.join(self.d, "c.stl")
        write_stl(cyl, cylinder(6, 20, 96))
        code, rep = run("slice", cyl, "--z", "0:20:5")
        self.assertEqual([lv["level"] for lv in rep["levels"]], [0.0, 5.0, 10.0, 15.0, 20.0])
        loop = rep["levels"][2]["loops"][0]
        self.assertTrue(loop["is_circle"])
        self.assertAlmostEqual(loop["circle_fit"]["radius_mm"], 6.0, places=2)
        self.assertEqual(loop["circle_fit"]["centre"], [0.0, 0.0])
        self.assertEqual(rep["levels"][0]["loops"], [])                     # a face lies in the plane: nudged, no crossing
        code, rep = run("slice", cyl, "--z", "10", "--axis", "x")
        self.assertEqual(rep["plane_axes"], ["y", "z"])
        self.assertEqual(rep["levels"][0]["loops"], [])                     # x = 10 is outside a r = 6 cylinder
        code, rep = run("slice", cyl, "--z", "0", "--axis", "x")
        self.assertEqual(rep["levels"][0]["loops"][0]["size"], [12.0, 20.0])

    def test_low_vertex_shapes_close_their_loops(self):
        """A pyramid sliced halfway is a 5 x 5 square (the chaining used to drop the last point);
        a box gives 200 mm2 whatever the triangle order; a cavity gives two loops."""
        import random
        apex, base = (5, 5, 10), [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
        tris = [(base[0], base[2], base[1]), (base[0], base[3], base[2])]
        tris += [(base[i], base[(i + 1) % 4], apex) for i in range(4)]
        pyr = os.path.join(self.d, "pyr.stl"); write_stl(pyr, tris)
        code, rep = run("slice", pyr, "--z", "5")
        loop = rep["levels"][0]["loops"][0]
        self.assertEqual((loop["points"], loop["closed"], loop["area_mm2"], loop["size"]), (4, True, 25.0, [5.0, 5.0]))
        self.assertFalse(loop["is_circle"])                                 # four corners lie on a circle, a square is not one
        self.assertEqual(loop["corner_radii_mm"], {"x0y0": 0.0, "x1y0": 0.0, "x1y1": 0.0, "x0y1": 0.0})
        for seed in range(6):
            t = box(20, 10, 5)
            random.Random(seed).shuffle(t)
            if seed % 2:
                t = [(a, b, c) for a, b, c in t]
            p = os.path.join(self.d, f"b{seed}.stl"); write_stl(p, t)
            code, rep = run("slice", p, "--z", "2.5")
            self.assertEqual([(l["points"], l["closed"], l["area_mm2"]) for l in rep["levels"][0]["loops"]], [(8, True, 200.0)], seed)
        hole = os.path.join(self.d, "hole.stl"); write_stl(hole, box(16, 16, 16) + box(12, 12, 12, 2, 2, 2, inward=True))
        code, rep = run("slice", hole, "--z", "8")
        self.assertEqual([(l["closed"], l["area_mm2"], l["size"]) for l in rep["levels"][0]["loops"]],
                         [(True, 256.0, [16.0, 16.0]), (True, 144.0, [12.0, 12.0])])
        # An open surface (one box face missing) gives an open chain and a warning, never a fake area.
        t = box(10, 10, 10)
        del t[4:6]                                                            # the y = 0 side face
        opened = os.path.join(self.d, "open.stl"); write_stl(opened, t)
        code, rep = run("slice", opened, "--z", "5")
        self.assertTrue(any(not l["closed"] for l in rep["levels"][0]["loops"]))
        self.assertTrue(any("open chain" in w for w in rep.get("warnings", [])))

    def test_negative_values_after_options(self):
        p = os.path.join(self.d, "c.stl"); write_stl(p, box(10, 10, 10, -5, -5, -5))
        code, rep = run("slice", p, "--z", "-5:5:5")
        self.assertEqual(code, 0, rep["errors"])
        self.assertEqual([lv["level"] for lv in rep["levels"]], [-5.0, 0.0, 5.0])
        code, rep = run("raymap", p, "--axis", "x", "--sign", "+1", "--u", "-4:4:4", "--v", "-4:4:4")
        self.assertEqual(code, 0, rep["errors"])
        self.assertEqual(rep["u"], [-4.0, 0.0, 4.0])
        self.assertTrue(all(x == 0.0 for row in rep["depth_mm"] for x in row))
        import measure
        self.assertEqual(measure.join_negative_values(["--u", "-1:2:1", "--z", "3", "--v", "-x"]), ["--u=-1:2:1", "--z", "3", "--v", "-x"])

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_corner_radii_of_a_rounded_outline(self):
        import parts
        from build import write_binary_stl
        m = parts.rounded_box([40, 30, 5], 4)
        mesh = m.to_mesh()
        p = os.path.join(self.d, "r.stl")
        write_binary_stl(p, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
        code, rep = run("slice", p, "--z", "2.5")
        loop = rep["levels"][0]["loops"][0]
        self.assertEqual(loop["size"], [40.0, 30.0])
        for r in loop["corner_radii_mm"].values():
            self.assertAlmostEqual(r, 4.0, delta=0.02)


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class RayMap(unittest.TestCase):
    def test_window_in_a_wall(self):
        import manifold3d as m3d
        from build import write_binary_stl
        wall = m3d.Manifold.cube([2, 40, 30]) - m3d.Manifold.cube([3, 12, 4]).translate([-0.5, 14, 10])   # window y 14..26, z 10..14
        wall -= m3d.Manifold.cube([1, 6, 6]).translate([1.5, 4, 20])                                     # 0.5 mm deep recess on +X
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "wall.stl")
            mesh = wall.to_mesh()
            write_binary_stl(p, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
            code, rep = run("raymap", p, "--axis", "x", "--sign", "+1", "--u", "1:39:2", "--v", "1:29:1", "--max-depth", "1.5")
        self.assertEqual(code, 0, rep["errors"])
        self.assertEqual(rep["grid_axes"], ["y", "z"])
        self.assertEqual(rep["outer_face_mm"], 2.0)
        depth = rep["depth_mm"]
        vs, us = rep["v"], rep["u"]
        cell = lambda u, v: depth[vs.index(v)][us.index(u)]          # noqa: E731
        self.assertEqual(cell(5, 5), 0.0)                              # plain wall
        self.assertIsNone(cell(19, 12))                                # through the window
        self.assertEqual(cell(5, 22), 0.5)                             # the recess
        self.assertTrue(any("." in row for row in rep["text"]))


if __name__ == "__main__":
    unittest.main()
