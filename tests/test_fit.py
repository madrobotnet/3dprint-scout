"""Tests for scripts/fit_test.py (fit-test pieces) and scripts/fit.py (F3 check)."""
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import fit  # noqa: E402
import fit_test  # noqa: E402
import validate  # noqa: E402
from test_validate import box, write_stl  # noqa: E402

HAS_M3D = find_spec("manifold3d") is not None
HAS_NP = find_spec("numpy") is not None


def run_fit_test(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fit_test.main(list(argv))
    return code, json.loads(buf.getvalue())


def run_fit(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fit.main(list(argv))
    return code, json.loads(buf.getvalue())


def validate_stl(path):
    buf = io.StringIO()
    with redirect_stdout(buf):
        validate.main([path, "--no-wall-check"])
    return json.loads(buf.getvalue())["files"][0]


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class FitTestPieces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_rounded_ring_steps(self):
        out_dir = os.path.join(self.d, "fit")
        code, out = run_fit_test("--profile", "rounded", "--size", "45.1,14.0", "--radius", "2", "--out", out_dir)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["mode"], "ring")
        self.assertEqual([s["clearance_per_side_mm"] for s in out["steps"]], [0.15, 0.3, 0.45])
        self.assertEqual([s["marks"] for s in out["steps"]], [1, 2, 3])
        self.assertEqual(out["clearance_mm"]["source"], "tolerances.md, object in a pocket")
        for s in out["steps"]:
            self.assertAlmostEqual(s["hole_size_mm"][0], 45.1 + 2 * s["clearance_per_side_mm"], places=2)
            self.assertAlmostEqual(s["hole_size_mm"][1], 14.0 + 2 * s["clearance_per_side_mm"], places=2)
            self.assertLess(s["mass_g_pla"], 3.0)                                 # a few grams
            f = validate_stl(s["stl"])
            self.assertTrue(f["artifact_sane"])
            for cid in ("D3", "M1", "M2", "M3", "M4", "M5"):
                self.assertEqual(f["checks"][cid]["state"], "PASS", (s["stl"], cid))
            self.assertAlmostEqual(f["metrics"]["bbox_mm"][2], 3.0)
        self.assertTrue(os.path.isfile(out["summary"]))
        with open(out["summary"], encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["schema"], fit_test.SCHEMA)
        # Marker holes: piece 3 has two more holes than piece 1, each a through hole
        import manifold3d as m3d
        from threemf import indexed
        import numpy as np

        def genus(path):
            v, f = indexed(validate.read_stl(path))
            return m3d.Manifold(m3d.Mesh(np.asarray(v, dtype=np.float32), np.asarray(f, dtype=np.uint32))).genus()
        self.assertEqual(genus(out["steps"][0]["stl"]), 2)                       # ring hole + 1 mark
        self.assertEqual(genus(out["steps"][2]["stl"]), 4)                       # ring hole + 3 marks
        # refuses to overwrite
        code, out2 = run_fit_test("--profile", "rounded", "--size", "45.1,14.0", "--radius", "2", "--out", out_dir)
        self.assertEqual(code, 1)
        self.assertIn("already exists", out2["errors"][0])

    def test_circle_plug_and_custom_steps(self):
        out_dir = os.path.join(self.d, "p")
        code, out = run_fit_test("--profile", "circle", "--size", "12.6", "--mode", "plug", "--clearance", "0.2",
                                 "--step", "0.1", "--steps", "2", "--height", "2", "--out", out_dir, "--name", "peg")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual([s["clearance_per_side_mm"] for s in out["steps"]], [0.15, 0.25])
        self.assertEqual(out["clearance_mm"]["source"], "user")
        self.assertAlmostEqual(out["steps"][0]["plug_size_mm"][0], 12.6 - 0.3, delta=0.01)
        self.assertTrue(out["steps"][1]["stl"].endswith("peg_2.stl"))
        f = validate_stl(out["steps"][1]["stl"])
        self.assertEqual(f["checks"]["M1"]["state"], "PASS")
        self.assertAlmostEqual(f["metrics"]["bbox_mm"][2], 2.0)

    def test_polygon_profile_and_bambu_job(self):
        poly = os.path.join(self.d, "outline.json")
        with open(poly, "w", encoding="utf-8") as fh:
            json.dump({"points": [[0, 0], [30, 0], [30, 10], [15, 18], [0, 10]]}, fh)
        out_dir = os.path.join(self.d, "poly")
        code, out = run_fit_test("--profile", "polygon", "--polygon", poly, "--out", out_dir,
                                 "--bambu-template", os.path.join(self.d, "x.3mf"))
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["profile"]["size_mm"], [30.0, 18.0])
        with open(out["bambu_job"], encoding="utf-8") as fh:
            job = json.load(fh)
        self.assertEqual([p["name"] for p in job["parts"]], ["fit_1", "fit_2", "fit_3"])
        self.assertTrue(all(os.path.isfile(p["stl"]) for p in job["parts"]))
        self.assertEqual(job["out"], os.path.join(out_dir, "fit_bambu.3mf"))
        f = validate_stl(out["steps"][0]["stl"])
        self.assertEqual(f["checks"]["M1"]["state"], "PASS")

    def test_usage_errors_are_json(self):
        code, out = run_fit_test("--profile", "rect", "--size", "10", "--out", os.path.join(self.d, "x"))
        self.assertEqual(code, 1)
        self.assertIn("--size W,D", out["errors"][0])
        code, out = run_fit_test("--profile", "circle", "--size", "4", "--mode", "plug", "--clearance", "3",
                                 "--out", os.path.join(self.d, "y"))
        self.assertEqual(code, 1)
        self.assertIn("leaves nothing", out["errors"][0])
        code, out = run_fit_test("--profile", "nope")
        self.assertEqual(code, 1)
        self.assertIn("usage error", out["errors"][0])


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class FitCheck(unittest.TestCase):
    """A box 60 x 40 x 30 (wall 2, open top) and lids whose plug has 0.2, 0 or -0.3 mm clearance per
    side; the lid prints plug-up and is assembled upside down on the box."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        import manifold3d as m3d
        from build import write_binary_stl
        w, d, h, wall = 60.0, 40.0, 30.0, 2.0
        def save(man, path):
            mesh = man.to_mesh()
            write_binary_stl(path, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
        self.box = os.path.join(self.d, "box.stl")
        save(m3d.Manifold.cube([w, d, h]) - m3d.Manifold.cube([w - 2 * wall, d - 2 * wall, h]).translate([wall, wall, wall]),
             self.box)
        self.lids = {}
        for name, c in (("lid", 0.2), ("touch", 0.0), ("big", -0.3)):
            self.lids[name] = os.path.join(self.d, f"{name}.stl")
            save(m3d.Manifold.cube([w, d, 3])
                 + m3d.Manifold.cube([w - 2 * wall - 2 * c, d - 2 * wall - 2 * c, 5]).translate([wall + c, wall + c, 3]),
                 self.lids[name])
        self.place = ["--b-rotate", "180,0,0", "--b-translate", "0,40,33"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_clearance_lid_passes_with_its_play(self):
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--min-clearance", "0.2")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["gate"], "PASS")
        f3 = out["checks"]["F3"]
        self.assertEqual((f3["state"], f3["kind"]), ("PASS", "hard"))
        self.assertEqual(f3["value"]["interference_mm3"], 0.0)
        self.assertEqual(f3["value"]["min_gap_mm"], 0.0)                         # seated on the rim
        self.assertAlmostEqual(f3["value"]["min_play_mm"], 0.2, delta=0.002)       # sideways clearance
        self.assertEqual(len(out["metrics"]["play"]), 4)
        for p in out["metrics"]["play"]:
            self.assertTrue(p["contact"])
            self.assertAlmostEqual(p["play_mm"], 0.2, delta=0.002)
        self.assertEqual(out["parts"]["b"]["bbox_min_mm"][2], 25.0)              # placed: plug reaches 5 mm into the box
        if HAS_NP:
            self.assertAlmostEqual(out["metrics"]["contact_area_mm2"], 60 * 40 - 56 * 36, delta=40)   # the rim
        self.assertEqual(out["schema"], fit.SCHEMA)

    def test_needs_more_clearance_warns(self):
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--min-clearance", "0.3")
        self.assertEqual(out["gate"], "WARN")
        self.assertIn("below the 0.3 mm", out["checks"]["F3"]["note"])
        self.assertTrue(out["warnings"])

    def test_touching_binds_unless_intended(self):
        code, out = run_fit(self.box, self.lids["touch"], *self.place)
        self.assertEqual(out["gate"], "WARN")
        self.assertIn("bind", out["checks"]["F3"]["note"])
        code, out = run_fit(self.box, self.lids["touch"], *self.place, "--min-clearance", "0")
        self.assertEqual(out["gate"], "PASS")

    def test_interference_fails(self):
        code, out = run_fit(self.box, self.lids["big"], *self.place)
        self.assertEqual(code, 0)
        self.assertEqual(out["gate"], "FAIL")
        f3 = out["checks"]["F3"]
        self.assertEqual(f3["return_to"], "phase4")
        # plug 56.6 x 36.6 overlaps the 2 mm walls by 0.3 mm on each side over 5 mm height
        self.assertAlmostEqual(f3["value"]["interference_mm3"], (56.6 * 36.6 - 56 * 36) * 5, delta=1.0)
        self.assertEqual(out["metrics"]["play"], [])                               # not measured when overlapping

    def test_far_apart_and_custom_directions(self):
        code, out = run_fit(self.box, self.lids["lid"], "--b-translate", "0,0,100")
        self.assertEqual(out["gate"], "WARN")
        self.assertIn("within 5.0 mm", out["checks"]["F3"]["note"])
        code, out = run_fit(self.box, self.lids["lid"], "--b-rotate", "180,0,0", "--b-translate", "0,40,33.5",
                            "--play", "0,0,-1;1,0,0")
        self.assertEqual(out["gate"], "PASS")
        plays = {tuple(p["direction"]): p["play_mm"] for p in out["metrics"]["play"]}
        self.assertAlmostEqual(plays[(0.0, 0.0, -1.0)], 0.5, delta=0.002)         # lifted lid drops 0.5 mm
        self.assertAlmostEqual(plays[(1.0, 0.0, 0.0)], 0.2, delta=0.002)
        self.assertAlmostEqual(out["metrics"]["min_gap_mm"], 0.2, delta=0.01)       # closest surfaces: the plug walls
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--play", "none")
        self.assertEqual(out["gate"], "PASS")
        self.assertIsNone(out["checks"]["F3"]["value"]["min_play_mm"])

    def test_bad_inputs(self):
        code, out = run_fit(self.box, os.path.join(self.d, "nope.stl"))
        self.assertEqual((code, out["ran"]), (1, False))
        self.assertIn("file not found", out["errors"][0])
        code, out = run_fit(self.box, self.lids["lid"], "--b-rotate", "1,2")
        self.assertEqual(code, 1)
        self.assertIn("three numbers", out["errors"][0])
        open_mesh = os.path.join(self.d, "open.stl")
        write_stl(open_mesh, box(10, 10, 10)[:-2])                                  # two faces missing
        code, out = run_fit(self.box, open_mesh)
        self.assertEqual(code, 1)
        self.assertIn("not a closed mesh", out["errors"][0])

    def test_cli_prints_json(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "fit.py"), self.box, self.lids["lid"], *self.place,
                            "--min-clearance", "0.2"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["gate"], "PASS")


@unittest.skipUnless(HAS_NP, "numpy not installed")
class PointTriangle(unittest.TestCase):
    def test_distances(self):
        import numpy as np
        A = np.array([[0.0, 0.0, 0.0]] * 5)
        B = np.array([[10.0, 0.0, 0.0]] * 5)
        C = np.array([[0.0, 10.0, 0.0]] * 5)
        P = np.array([[2.0, 2.0, 3.0],      # above the face
                      [-1.0, -1.0, 0.0],    # beyond vertex A
                      [5.0, -2.0, 0.0],     # beside edge AB
                      [8.0, 8.0, 0.0],      # beyond the hypotenuse
                      [12.0, 0.0, 1.0]])    # beyond vertex B
        d = np.sqrt(fit._point_triangle_distance(P, A, B, C))
        np.testing.assert_allclose(d, [3.0, math.sqrt(2), 2.0, math.sqrt(2) * 3, math.sqrt(5)], atol=1e-9)


if __name__ == "__main__":
    unittest.main()
