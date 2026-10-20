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

    def test_every_body_of_a_fused_part_must_touch(self):
        """S3-3: a text part is one STL of several bodies; a letter that floats above the plate
        fails A1 even though the other letters sit on it."""
        stls = {"plate": self.stl("plate.stl", box(60, 40, 3)),
                "text": self.stl("text.stl", box(8, 8, 1, 5, 5, 3) + box(8, 8, 1, 20, 5, 5) + box(8, 8, 1, 35, 5, 3))}
        specs = {"plate": {"object": "o"}, "text": {"object": "o", "role": "fused", "shells": 3}}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        a1 = rep["parts"]["text"]["checks"]["A1"]
        self.assertEqual(a1["state"], "FAIL")
        self.assertEqual(a1["value"]["shells"], 3)
        self.assertEqual([s["shell"] for s in a1["value"]["loose_shells"]], [1])
        self.assertEqual(a1["value"]["loose_shells"][0]["gap_mm"], 2.0)
        self.assertIn("1 of its 3 bodies touch nothing", a1["note"])
        self.assertIn("z 5.0..6.0", a1["note"])
        self.assertEqual(rep["parts"]["plate"]["checks"]["A1"]["state"], "PASS")   # the plate itself is touched
        self.assertEqual(assembly.object_gate(rep), "FAIL")
        stls["text"] = self.stl("text2.stl", box(8, 8, 1, 5, 5, 3) + box(8, 8, 1, 20, 5, 3) + box(8, 8, 1, 35, 5, 3))
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)   # the middle one on the plate too
        a1 = rep["parts"]["text"]["checks"]["A1"]
        self.assertEqual(a1["state"], "PASS")
        self.assertIn("all 3 bodies", a1["note"])
        self.assertNotIn("loose_shells", a1["value"])

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

    def test_main_part_with_only_free_partners(self):
        """A body with its print-in-place latch, or a hinge's two leaves: the main part has no
        fused partner, so A1 is N/A, not a failure; and a 0.298 mm gap from tessellation is
        not a WARN against 0.3."""
        import parts
        from build import write_binary_stl
        h = parts.hinge()
        stls = {}
        for name, man in h.items():
            p = os.path.join(self.d, name + ".stl")
            mesh = man.to_mesh()
            write_binary_stl(p, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
            stls[name] = p
        specs = {"leaf_a": {"object": "hinge"}, "leaf_b": {"object": "hinge", "role": "free"}}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        self.assertEqual(rep["parts"]["leaf_a"]["checks"]["A1"]["state"], "N/A")
        self.assertIn("free", rep["parts"]["leaf_a"]["checks"]["A1"]["note"])
        a2 = rep["parts"]["leaf_b"]["checks"]["A2"]
        self.assertEqual(a2["state"], "PASS", a2)
        self.assertGreaterEqual(a2["value"]["pairs"][0]["gap_mm"], 0.29)
        self.assertEqual(assembly.object_gate(rep), "INCOMPLETE")                      # only D2 is open: no bed given
        # A fused label that touches only the free latch is still floating.
        stls["tag"] = os.path.join(self.d, "tag.stl"); write_stl(stls["tag"], box(5, 5, 1, 0, 0, 30))
        specs["tag"] = {"object": "hinge", "role": "fused"}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        self.assertEqual(rep["parts"]["tag"]["checks"]["A1"]["state"], "FAIL")
        self.assertEqual(rep["parts"]["leaf_a"]["checks"]["A1"]["state"], "FAIL")      # now it has a fused partner it does not touch

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
        self.assertNotIn("contact_area_mm2", rep["metrics"])                 # coplanar faces merge: nothing to correct

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_unmerged_contact_on_a_curved_face_is_not_overhang(self):
        """S3-4: a letter cut to a domed face by another engine keeps its own tessellation, so
        the union keeps both the letter's underside and the dome under it; those downward
        faces are contact, not overhang, and P2 must not count them."""
        import manifold3d as m3d
        from build import write_binary_stl

        def dome(segments):                                                  # a cylinder r 50 lying along Y
            return m3d.Manifold.cylinder(80, 50, 50, segments).rotate([90, 0, 0]).translate([0, 40, -40])
        back = dome(256) ^ m3d.Manifold.cube([30, 30, 20]).translate([-15, -15, 0])
        letter = m3d.Manifold.cube([20, 20, 14]).translate([-10, -10, 0]) - dome(180)   # its underside: 180 segments
        stls = {}
        for name, man in (("back", back), ("letter", letter)):
            mesh = man.to_mesh()
            stls[name] = os.path.join(self.d, name + ".stl")
            write_binary_stl(stls[name], mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
        specs = {"back": {"object": "o"}, "letter": {"object": "o", "role": "fused"}}
        rep = assembly.check_object(assembly.group_parts(specs)[0], stls, specs)
        p2 = rep["checks"]["P2"]
        self.assertEqual(p2["state"], "PASS", p2)
        self.assertIn("fused contacts the union did not merge", p2["note"])
        self.assertAlmostEqual(rep["metrics"]["contact_area_mm2"], p2["value"]["contact_area_mm2"])
        self.assertEqual(rep["parts"]["letter"]["checks"]["A1"]["state"], "PASS", rep["parts"]["letter"])
        # The union keeps part of the two surfaces (Manifold merges the rest within its own
        # tolerance): what it keeps was counted as overhang, and is contact to the last mm2.
        union = assembly._to_manifold(m3d, assembly.validate.read_stl(stls["back"]), "back") + \
            assembly._to_manifold(m3d, assembly.validate.read_stl(stls["letter"]), "letter")
        raw = assembly.validate.analyse(assembly._tris_of(union))
        self.assertGreater(raw["overhang_area_mm2"], 20.0)
        self.assertAlmostEqual(p2["value"]["contact_area_mm2"], raw["overhang_area_mm2"], delta=0.05)
        self.assertEqual(p2["value"]["overhang_pct"], 0.0)
        self.assertEqual(p2["value"]["overhang_area_mm2"], 0.0)


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
        self.assertEqual(os.path.basename(out["threemf"]), "lid_peg.3mf")           # named after the objects, not the source (S3-15)
        self.assertIsInstance(out["seconds"], float)
        with zipfile.ZipFile(os.path.join(self.d, "out", "lid_peg.3mf")) as z:
            self.assertIn("<components>", z.read("3D/3dmodel.model").decode())
        self.assertEqual(build.threemf_stem(["nameplate"]), "nameplate")
        self.assertEqual(build.threemf_stem(["a" * 40, "b" * 40, "c"]), "a" * 40 + "_and_2_more")

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
        self.assertTrue(any(e.startswith("tag A1 FAIL: touches nothing") for e in out["errors"]), out["errors"])
        self.assertFalse(any("A1 FAIL" in w for w in out["warnings"]))         # a hard FAIL is an error, not a warning

    def test_part_level_hard_fails_are_errors(self):
        """S5-F3 / S2-F10: a part's D1 or M5 FAIL is one line in the top-level errors (the lists
        the agent reads first), not only in parts[].validate."""
        odd = os.path.join(self.d, "odd.stl"); write_stl(odd, box(63.4, 40, 24))
        code, out = self.run_record({"odd": {"expect": [63.6, 40, 24]}}, [odd])
        self.assertEqual(out["gate"], "FAIL")
        self.assertEqual([e for e in out["errors"] if e.startswith("odd D1 FAIL")],
                         ["odd D1 FAIL: bounding box differs from the expected size"])
        self.assertFalse(any("FAIL" in w for w in out["warnings"]), out["warnings"])
        two = os.path.join(self.d, "two.stl"); write_stl(two, box(10, 10, 10) + box(10, 10, 10, 20, 0, 0))
        code, out = self.run_record({"two": {"expect": [30, 10, 10]}}, [two])
        self.assertIn("two M5 FAIL: unexpected number of separate bodies", out["errors"])
        self.assertEqual([e for e in out["errors"] if "D1" in e], [])             # only what failed
        code, out = self.run_record({"two": {"expect": [30, 10, 10], "shells": 2}}, [two])
        self.assertEqual([e for e in out["errors"] if "FAIL" in e], [])

    def test_bad_grouping_is_reported_not_crashed(self):
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3))
        code, out = self.run_record({"lid": {"object": "x", "role": "fused"}}, [lid])
        self.assertEqual(code, 0)
        self.assertTrue(any("_parts" in e and "role" in e for e in out["errors"]), out["errors"])
        # A _parts that is not an object of objects (S3-18) is a usage error that names the form.
        for bad in ("lid", ["lid", 3], {"lid": "60x40"}, 7):
            prm = os.path.join(self.d, "params.json")
            with open(prm, "w") as f:
                json.dump({"_parts": bad}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build.main(["record", lid, "--source", prm, "--params", prm, "--out", os.path.join(self.d, "out")])
            out = json.loads(buf.getvalue())
            self.assertEqual((code, out["ran"]), (1, False), bad)
            self.assertIn('"_parts"', out["errors"][0])
            self.assertIn("expect", out["errors"][0])
        self.assertEqual(build.part_specs({"_parts": ["a", "b"]}, "x"), {"a": {}, "b": {}})
        self.assertEqual(build.part_specs({"_parts": {"a": None, "b": {"expect": [1, 2, 3]}}}, "x"), {"a": {}, "b": {"expect": [1, 2, 3]}})
        self.assertEqual(build.part_specs({}, "x"), {"x": {}})

    def test_copied_expect_is_flagged(self):
        """expect with four or more decimals that matches the mesh to 0.001 mm looks copied from a
        measured bounding box (D1 would be circular); inch-derived sizes (25.4, 3.175) are design."""
        odd = os.path.join(self.d, "odd.stl"); write_stl(odd, box(71.2004, 37.8, 33.6))
        code, out = self.run_record({"odd": {"expect": [71.2004, 37.8, 33.6]}}, [odd])
        d1 = out["parts"][0]["validate"]["files"][0]["checks"]["D1"]
        self.assertEqual(d1["state"], "PASS")
        self.assertTrue(d1.get("copied_expect"))
        self.assertTrue(any("copied" in w for w in out["warnings"]))
        code, out = self.run_record({"odd": {"expect": [71.2, 37.8, 33.6]}}, [odd])
        self.assertFalse(out["parts"][0]["validate"]["files"][0]["checks"]["D1"].get("copied_expect"))
        inch = os.path.join(self.d, "inch.stl"); write_stl(inch, box(25.4, 12.7, 3.175))
        code, out = self.run_record({"inch": {"expect": [25.4, 12.7, 3.175]}}, [inch])
        d1 = out["parts"][0]["validate"]["files"][0]["checks"]["D1"]
        self.assertEqual(d1["state"], "PASS")
        self.assertFalse(d1.get("copied_expect"))
        self.assertFalse(any("copied" in w for w in out["warnings"]))

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_only_builds_a_subset(self):
        """A test print of the mechanism alone: --only builds the named parts and nothing else."""
        src = os.path.join(self.d, "gen.py")
        with open(src, "w") as f:
            f.write("import manifold3d as m3d\n"
                    "def build(p):\n"
                    "    return {'body': m3d.Manifold.cube([40, 30, 10]), 'latch': m3d.Manifold.cube([10, 4, 3]).translate([0, 0, 10]),\n"
                    "            'keeper': m3d.Manifold.cube([12, 6, 5]).translate([0, 0, 13.3])}\n")
        prm = os.path.join(self.d, "params.json")
        with open(prm, "w") as f:
            json.dump({"_parts": {"body": {}, "latch": {"object": "body", "role": "free"}, "keeper": {"object": "body", "role": "free"}}}, f)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = build.main(["run", src, "--params", prm, "--out", os.path.join(self.d, "mech"), "--only", "latch,keeper",
                               "--no-wall-check"])
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual([p["name"] for p in out["parts"]], ["latch", "keeper"])
        self.assertEqual(sorted(f for f in os.listdir(os.path.join(self.d, "mech")) if f.endswith(".stl")), ["keeper.stl", "latch.stl"])
        # A partial object (S3-5): the subset is not judged as the whole. The body is missing, so
        # the bed, the footprint and what the free parts might hit are unknown: UNVERIFIED, not a
        # verdict; no core 3MF item either (the subset would be dropped onto the bed).
        obj = out["objects"][0]
        self.assertEqual(obj["parts"], ["latch", "keeper"])
        self.assertEqual(obj["partial"], {"object": "body", "built": ["latch", "keeper"], "missing": ["body"], "total": 3})
        self.assertEqual({k: v["state"] for k, v in obj["checks"].items()}, {"D2": "UNVERIFIED", "P1": "UNVERIFIED", "P2": "UNVERIFIED"})
        self.assertIn("missing body", obj["checks"]["P1"]["note"])
        self.assertEqual(obj["gate"], "INCOMPLETE")
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual(parts["latch"]["assembly"]["checks"]["A2"]["state"], "UNVERIFIED")
        self.assertEqual(parts["keeper"]["assembly"]["checks"]["A2"]["state"], "UNVERIFIED")
        self.assertIn("pairs", parts["keeper"]["assembly"]["checks"]["A2"]["value"])       # measured, for information
        self.assertTrue(any(w.startswith("object 'body': built 2 of 3 parts with --only (missing: body)") for w in out["warnings"]), out["warnings"])
        self.assertTrue(any(w.startswith("core 3MF not written") for w in out["warnings"]), out["warnings"])
        self.assertNotIn("threemf", out)
        self.assertEqual([f for f in os.listdir(os.path.join(self.d, "mech")) if f.endswith(".3mf")], [])
        self.assertNotEqual(out["gate"], "FAIL", out["warnings"])

        def run_only(only, folder):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build.main(["run", src, "--params", prm, "--out", os.path.join(self.d, folder), "--only", only, "--no-wall-check"])
            return code, json.loads(buf.getvalue())
        code, out = run_only("latch,hinge", "m2")
        self.assertEqual(code, 1)
        self.assertIn("--only", out["errors"][0])
        self.assertIn("hinge", out["errors"][0])
        code, out = run_only(",", "m3")
        self.assertEqual(code, 1)
        self.assertIn("--only names no part", out["errors"][0])
        code, out = run_only("keeper,body", "m4")                                       # _parts order wins: body is the main part
        self.assertEqual([p["name"] for p in out["parts"]], ["body", "keeper"])
        self.assertEqual(out["objects"][0]["main"], "body")
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual(parts["body"]["assembly"]["checks"]["A1"]["state"], "UNVERIFIED")   # the latch is missing
        self.assertEqual(parts["keeper"]["assembly"]["checks"]["A2"]["state"], "UNVERIFIED")
        self.assertNotEqual(out["gate"], "FAIL", out["warnings"])                        # INCOMPLETE: no expect, no printer
        code, out = run_only("latch", "m5")                                             # a free part alone: no object, a note
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["errors"], [])
        self.assertIsNone(out["parts"][0]["role"])
        self.assertTrue(any("built alone with --only" in w for w in out["warnings"]))
        self.assertTrue(any("built 1 of 3 parts" in w for w in out["warnings"]))
        self.assertNotIn("threemf", out)                                                # it would be dropped to the bed
        self.assertNotEqual(out["gate"], "FAIL")
        code, out = run_only("body,latch,keeper", "m6")                                 # every part: a whole object, as without --only
        self.assertEqual(out["objects"][0]["checks"]["P1"]["state"], "PASS")
        self.assertNotIn("partial", out["objects"][0])
        self.assertTrue(os.path.isfile(out["threemf"]))

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_partial_object_keeps_a_definite_failure(self):
        """Two free parts of a partial object that overlap each other fail A2 whatever the
        missing body would add; a floating fused part is only UNVERIFIED (its partner is absent)."""
        src = os.path.join(self.d, "gen.py")
        with open(src, "w") as f:
            f.write("import manifold3d as m3d\n"
                    "def build(p):\n"
                    "    return {'body': m3d.Manifold.cube([40, 30, 10]), 'latch': m3d.Manifold.cube([10, 4, 3]).translate([0, 0, 10]),\n"
                    "            'keeper': m3d.Manifold.cube([12, 6, 5]).translate([0, 0, 12]),\n"
                    "            'tag': m3d.Manifold.cube([5, 5, 1]).translate([30, 20, 10])}\n")
        prm = os.path.join(self.d, "params.json")
        with open(prm, "w") as f:
            json.dump({"_parts": {"body": {}, "latch": {"object": "body", "role": "free"}, "keeper": {"object": "body", "role": "free"},
                                  "tag": {"object": "body", "role": "fused"}}}, f)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = build.main(["run", src, "--params", prm, "--out", os.path.join(self.d, "mech"), "--only", "latch,keeper,tag",
                               "--no-wall-check"])
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0, out.get("errors"))
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual(parts["latch"]["assembly"]["checks"]["A2"]["state"], "FAIL")   # overlaps the keeper: real
        self.assertEqual(parts["keeper"]["assembly"]["checks"]["A2"]["state"], "FAIL")
        self.assertEqual(parts["tag"]["assembly"]["checks"]["A1"]["state"], "UNVERIFIED")   # it sits on the missing body
        self.assertEqual(out["gate"], "FAIL")
        self.assertTrue(any(e.startswith("latch A2 FAIL") for e in out["errors"]), out["errors"])
        self.assertFalse(any("tag A1" in e for e in out["errors"]), out["errors"])

    def test_help_describes_the_output(self):
        for argv in (["--help"], ["record", "--help"], ["run", "--help"]):
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
                build.main(argv)
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("objects[]", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
