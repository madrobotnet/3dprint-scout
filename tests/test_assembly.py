"""Tests for scripts/assembly.py (parts grouped into objects) and its use in build.py."""
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
import assembly  # noqa: E402
import build  # noqa: E402
from test_validate import X2D, box, write_stl  # noqa: E402

HAS_M3D = find_spec("manifold3d") is not None and find_spec("numpy") is not None


class Grouping(unittest.TestCase):
    def test_parts_without_object_stay_alone(self):
        groups = assembly.group_parts({"box": {"expect": [1, 1, 1]}, "lid": {}})
        self.assertEqual(groups, [{"name": "box", "parts": ["box"], "main": "box"},
                                  {"name": "lid", "parts": ["lid"], "main": "lid"}])

    def test_object_groups_in_order_with_first_part_as_main(self):
        groups = assembly.group_parts({"box": {}, "lid": {"object": "top"}, "label": {"object": "top", "role": "fused"},
                                       "latch": {"object": "top", "role": "free", "clearance": 0.4}})
        self.assertEqual(groups, [{"name": "box", "parts": ["box"], "main": "box"},
                                  {"name": "top", "parts": ["lid", "label", "latch"], "main": "lid"}])
        self.assertEqual(assembly.part_role({}), "fused")
        self.assertEqual(assembly.part_clearance({"clearance": 0.4}), 0.4)
        self.assertEqual(assembly.part_clearance({}), assembly.DEFAULT_FREE_CLEARANCE)

    def test_bad_specs_are_usage_errors(self):
        for specs in ({"a": {"role": "glued", "object": "x"}, "b": {"object": "x"}},
                      {"a": {"object": "x", "role": "free", "clearance": -1}, "b": {"object": "x"}},
                      {"a": {"object": "x", "role": "free", "clearance": "thin"}, "b": {"object": "x"}},
                      {"a": {"object": "x", "role": "fused"}}):           # alone in its object
            with self.assertRaises(assembly.AssemblyError, msg=specs):
                assembly.group_parts(specs)


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class ObjectChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def stl(self, name, tris):
        p = os.path.join(self.d, name)
        write_stl(p, tris)
        return p

    def test_fused_free_and_floating_parts(self):
        stls = {"lid": self.stl("lid.stl", box(60, 40, 3)),
                "label": self.stl("label.stl", box(30, 10, 1, 15, 15, 3)),        # on the lid's top face
                "latch": self.stl("latch.stl", box(10, 6, 2, 25, 40.3, 0)),        # 0.3 mm from the lid
                "near": self.stl("near.stl", box(4, 4, 2, 0, -4.1, 0)),            # 0.1 mm: too close
                "float": self.stl("float.stl", box(5, 5, 1, 0, 0, 10))}            # fused but floating
        specs = {"lid": {"object": "o"}, "label": {"object": "o", "role": "fused"},
                 "latch": {"object": "o", "role": "free"}, "near": {"object": "o", "role": "free"},
                 "float": {"object": "o"}}
        obj = assembly.group_parts(specs)[0]
        rep = assembly.check_object(obj, stls, specs)
        states = {n: list(p["checks"].values())[0]["state"] for n, p in rep["parts"].items()}
        self.assertEqual(states, {"lid": "PASS", "label": "PASS", "latch": "PASS", "near": "WARN", "float": "FAIL"})
        self.assertIn("A1", rep["parts"]["float"]["checks"])
        self.assertIn("A2", rep["parts"]["near"]["checks"])
        self.assertEqual(rep["parts"]["lid"]["checks"]["A1"]["value"]["touches"], ["label"])
        self.assertEqual(rep["checks"]["D2"]["state"], "UNVERIFIED")       # no bed given
        self.assertEqual(rep["checks"]["P1"]["state"], "PASS")
        self.assertEqual(assembly.object_gate(rep), "FAIL")
        self.assertTrue(any("near A2" in w for w in rep["warnings"]))

    def test_overlapping_fused_parts_fail_on_both_sides(self):
        stls = {"lid": self.stl("lid.stl", box(60, 40, 3)), "deep": self.stl("deep.stl", box(5, 5, 2, 50, 30, 2))}
        specs = {"lid": {"object": "o"}, "deep": {"object": "o"}}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        self.assertEqual(rep["parts"]["deep"]["checks"]["A1"]["state"], "FAIL")
        self.assertEqual(rep["parts"]["lid"]["checks"]["A1"]["state"], "FAIL")
        self.assertIn("overlaps lid", rep["parts"]["deep"]["checks"]["A1"]["note"])
        self.assertAlmostEqual(rep["parts"]["deep"]["checks"]["A1"]["value"]["pairs"][0]["overlap_mm3"], 25.0, places=2)

    def test_mismatched_tessellations_still_count_as_touching(self):
        """A 48-segment inlay in a 64-segment pocket overlaps by a few hundredths of a mm3 (the
        polygons cross); that is tessellation, not a modelling error. Sunk 0.5 mm, it is."""
        import manifold3d as m3d
        from build import write_binary_stl

        def save(man, name):
            p = os.path.join(self.d, name)
            mesh = man.to_mesh()
            write_binary_stl(p, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
            return p
        block = m3d.Manifold.cube([30, 30, 10]) - m3d.Manifold.cylinder(5.1, 5, 5, 64).translate([15, 15, 5])
        inlay = m3d.Manifold.cylinder(5, 5, 5, 48).translate([15, 15, 5])
        sunk = m3d.Manifold.cylinder(5, 5, 5, 48).translate([15, 15, 4.5])
        stls = {"block": save(block, "block.stl"), "inlay": save(inlay, "inlay.stl")}
        specs = {"block": {"object": "o"}, "inlay": {"object": "o"}}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        a1 = rep["parts"]["inlay"]["checks"]["A1"]
        pair = a1["value"]["pairs"][0]
        self.assertGreater(pair["overlap_mm3"], 0.001)                      # the polygons cross
        self.assertLess(pair["overlap_mm3"], pair["allowed_overlap_mm3"])
        self.assertGreater(pair["shared_area_mm2"], 70)                    # the bottom face at least (the sides only partly coincide)
        self.assertEqual(a1["state"], "PASS", a1)
        self.assertEqual(rep["parts"]["block"]["checks"]["A1"]["state"], "PASS")
        stls["inlay"] = save(sunk, "sunk.stl")
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        self.assertEqual(rep["parts"]["inlay"]["checks"]["A1"]["state"], "FAIL")
        self.assertGreater(rep["parts"]["inlay"]["checks"]["A1"]["value"]["pairs"][0]["overlap_mm3"], 30)

    def test_shared_faces_are_not_overhangs(self):
        """A label on the lid's top: alone, its underside is 100 % overhang; as part of the
        object the shared face vanishes and P2 passes."""
        stls = {"lid": self.stl("lid.stl", box(60, 40, 3)), "label": self.stl("label.stl", box(30, 10, 1, 15, 15, 3))}
        specs = {"lid": {"object": "o"}, "label": {"object": "o"}}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        self.assertEqual(rep["checks"]["P2"]["state"], "PASS")
        self.assertEqual(rep["checks"]["P2"]["value"]["overhang_area_mm2"], 0.0)
        self.assertEqual(rep["metrics"]["shells"], 1)
        self.assertAlmostEqual(rep["metrics"]["volume_mm3"], 60 * 40 * 3 + 30 * 10 * 1, delta=0.5)


class BuildIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_record(self, specs, stls, extra=()):
        src = os.path.join(self.d, "gen_fusion.py")
        with open(src, "w") as f:
            f.write("def run(context=None):\n    pass\n")
        prm = os.path.join(self.d, "params.json")
        with open(prm, "w") as f:
            json.dump({"_parts": specs}, f)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = build.main(["record", *stls, "--source", src, "--params", prm, "--out", os.path.join(self.d, "out"),
                               "--no-wall-check", *extra])
        return code, json.loads(buf.getvalue())

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_record_groups_parts_and_reports_objects(self):
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3))
        label = os.path.join(self.d, "label.stl"); write_stl(label, box(30, 10, 1, 15, 15, 3))
        peg = os.path.join(self.d, "peg.stl"); write_stl(peg, box(5, 5, 5))
        printers = os.path.join(self.d, "printers.json")
        with open(printers, "w") as f:
            json.dump(X2D, f)
        specs = {"lid": {"expect": [60, 40, 3]}, "label": {"expect": [30, 10, 1], "object": "lid"},
                 "peg": {"expect": [5, 5, 5]}}
        code, out = self.run_record(specs, [lid, label, peg], ["--printer", printers])
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["gate"], "PASS", out)
        objects = {o["name"]: o for o in out["objects"]}
        self.assertEqual(objects["lid"]["parts"], ["lid", "label"])
        self.assertEqual(objects["lid"]["gate"], "PASS")
        self.assertEqual(objects["lid"]["checks"]["D2"]["state"], "PASS")
        self.assertEqual(objects["lid"]["checks"]["D2"]["value"]["tools"], [0, 1])     # both nozzles must reach it
        self.assertIn("intersection of tools", objects["lid"]["checks"]["D2"]["note"])
        self.assertEqual(objects["lid"]["checks"]["P2"]["state"], "PASS")
        self.assertEqual(objects["peg"]["parts"], ["peg"])
        self.assertNotIn("checks", objects["peg"])
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual((parts["label"]["object"], parts["label"]["role"]), ("lid", "fused"))
        self.assertEqual(parts["label"]["assembly"]["checks"]["A1"]["state"], "PASS")
        self.assertIsNone(parts["peg"]["role"])
        # The label's own validation takes its lowest face as the bed; only the object knows better.
        self.assertEqual(parts["label"]["validate"]["files"][0]["metrics"]["bbox_min_mm"][2], 3.0)
        import zipfile
        with zipfile.ZipFile(os.path.join(self.d, "out", "gen_fusion.3mf")) as z:
            self.assertIn("<components>", z.read("3D/3dmodel.model").decode())

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_multi_part_object_is_checked_against_the_shared_nozzle_area(self):
        """X2D: tool 1 reaches x >= 20.5 only, so the shared area is 235.5 mm wide. A 240 mm
        two-part object passes D2 alone (--tools 0) but fails as an object."""
        wide = os.path.join(self.d, "wide.stl"); write_stl(wide, box(240, 240, 5))
        tag = os.path.join(self.d, "tag.stl"); write_stl(tag, box(10, 10, 2, 0, 0, 5))
        printers = os.path.join(self.d, "printers.json")
        with open(printers, "w") as f:
            json.dump(X2D, f)
        code, out = self.run_record({"wide": {}, "tag": {"object": "wide"}}, [wide, tag], ["--printer", printers, "--tools", "0"])
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual(parts["wide"]["validate"]["files"][0]["checks"]["D2"]["state"], "PASS")   # full bed, tool 0
        d2 = out["objects"][0]["checks"]["D2"]
        self.assertEqual(d2["state"], "FAIL", d2)
        self.assertEqual(d2["value"]["bed"], [235.5, 256])
        self.assertEqual(out["gate"], "FAIL")

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_floating_fused_part_fails_the_gate(self):
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3))
        tag = os.path.join(self.d, "tag.stl"); write_stl(tag, box(5, 5, 1, 0, 0, 10))
        code, out = self.run_record({"lid": {}, "tag": {"object": "lid"}}, [lid, tag])
        self.assertEqual(out["gate"], "FAIL")
        self.assertEqual(out["objects"][0]["gate"], "FAIL")
        self.assertTrue(any("tag A1 FAIL" in w for w in out["warnings"]))

    def test_bad_grouping_is_reported_not_crashed(self):
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3))
        code, out = self.run_record({"lid": {"object": "x", "role": "fused"}}, [lid])
        self.assertEqual(code, 0)
        self.assertTrue(any("_parts" in e and "role" in e for e in out["errors"]), out["errors"])

    def test_copied_expect_is_flagged(self):
        """expect with three or more decimals that matches the mesh to 0.001 mm looks copied
        from a measured bounding box (D1 would be circular)."""
        odd = os.path.join(self.d, "odd.stl"); write_stl(odd, box(71.2004, 37.8, 33.6))
        code, out = self.run_record({"odd": {"expect": [71.2004, 37.8, 33.6]}}, [odd])
        d1 = out["parts"][0]["validate"]["files"][0]["checks"]["D1"]
        self.assertEqual(d1["state"], "PASS")
        self.assertTrue(d1.get("copied_expect"))
        self.assertTrue(any("copied" in w for w in out["warnings"]))
        code, out = self.run_record({"odd": {"expect": [71.2, 37.8, 33.6]}}, [odd])
        self.assertFalse(out["parts"][0]["validate"]["files"][0]["checks"]["D1"].get("copied_expect"))

    def test_help_describes_the_output(self):
        for argv in (["--help"], ["record", "--help"], ["run", "--help"]):
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
                build.main(argv)
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("objects[]", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
