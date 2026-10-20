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

    def test_report_records_the_stl_hashes(self):
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--min-clearance", "0.2")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["parts"]["a"]["sha256"], validate.file_sha256(self.box))
        self.assertEqual(out["parts"]["b"]["sha256"], validate.file_sha256(self.lids["lid"]))
        self.assertIsNone(out["parts"]["a"]["input_hash"])                       # no build manifest
        src = os.path.join(self.d, "box.py")
        with open(src, "w") as f:
            f.write("# box\n")
        man = validate.write_manifest(self.box, [src], {"w": 60}, "python")
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--min-clearance", "0.2")
        self.assertEqual(out["parts"]["a"]["input_hash"], man["input_hash"])
        # A manifest that records another STL says nothing about this one.
        with open(validate.manifest_path(self.lids["lid"]), "w") as f:
            json.dump(dict(man, artifact_sha256="0" * 64), f)
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--min-clearance", "0.2")
        self.assertIsNone(out["parts"]["b"]["input_hash"])

    def test_check_finds_a_stale_report(self):
        code, out = run_fit(self.box, self.lids["lid"], *self.place, "--min-clearance", "0.2")
        self.assertEqual(out["gate"], "PASS")
        report = os.path.join(self.d, "fit_box_lid.json")
        with open(report, "w") as f:
            json.dump(out, f)
        code, chk = run_fit("--check", report)
        self.assertEqual(code, 0, chk["errors"])
        self.assertEqual((chk["gate"], chk["checks"]["F3_fresh"]["state"]), ("PASS", "PASS"))
        self.assertEqual(chk["checks"]["F3_fresh"]["value"]["report_gate"], "PASS")
        # The lid is rebuilt with other geometry at the same path: the old PASS proves nothing.
        with open(self.lids["touch"], "rb") as src, open(self.lids["lid"], "wb") as dst:
            dst.write(src.read())
        code, chk = run_fit("--check", report)
        self.assertEqual(code, 0)
        f3 = chk["checks"]["F3_fresh"]
        self.assertEqual((chk["gate"], f3["state"], f3["return_to"]), ("FAIL", "FAIL", "current"))
        self.assertIn("STALE", f3["note"])
        self.assertIn(self.lids["lid"], f3["note"])
        self.assertNotEqual(chk["parts"]["b"]["current_sha256"], chk["parts"]["b"]["recorded_sha256"])
        self.assertEqual(chk["parts"]["a"]["current_sha256"], chk["parts"]["a"]["recorded_sha256"])
        # A part that is gone, and a report from before the hashes were recorded.
        os.remove(self.lids["lid"])
        code, chk = run_fit("--check", report)
        self.assertEqual(chk["gate"], "FAIL")
        self.assertIn("file not found", chk["checks"]["F3_fresh"]["note"])
        for k in ("a", "b"):
            del out["parts"][k]["sha256"]
        with open(report, "w") as f:
            json.dump(out, f)
        code, chk = run_fit("--check", report)
        self.assertEqual(chk["gate"], "UNVERIFIED")

    def test_check_usage(self):
        code, out = run_fit("--check", os.path.join(self.d, "nope.json"))
        self.assertEqual((code, out["ran"]), (1, False))
        code, out = run_fit(self.box, "--check", os.path.join(self.d, "nope.json"))
        self.assertEqual(code, 1)
        self.assertIn("takes no STLs", out["errors"][0])
        code, out = run_fit(self.box)
        self.assertEqual(code, 1)
        self.assertIn("two STLs", out["errors"][0])
        bad = os.path.join(self.d, "other.json")
        with open(bad, "w") as f:
            json.dump({"schema": "3dprint-scout.validate/1"}, f)
        code, out = run_fit("--check", bad)
        self.assertEqual(code, 1)
        self.assertIn("not a 3dprint-scout.fit/1 report", out["errors"][0])

    def test_cli_prints_json(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "fit.py"), self.box, self.lids["lid"], *self.place,
                            "--min-clearance", "0.2"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["gate"], "PASS")


@unittest.skipUnless(HAS_NP, "numpy not installed")
@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class Sweep(unittest.TestCase):
    """A lever (bar 15 x 2 x 2 along +X from its pivot at the origin) and a stop block in its
    path at x 10..20, y 5..15: turning about Z it hits the block between 20 and 30 degrees;
    turning the other way it stays free."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        import manifold3d as m3d
        from build import write_binary_stl

        def save(man, path):
            mesh = man.to_mesh()
            write_binary_stl(path, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
        self.stop = os.path.join(self.d, "stop.stl")
        save(m3d.Manifold.cube([10, 10, 10]).translate([10, 5, -4]), self.stop)
        self.lever = os.path.join(self.d, "lever.stl")
        save(m3d.Manifold.cube([15, 2, 2]).translate([0, -1, 0]), self.lever)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stop_angle_table_and_travel_verdicts(self):
        code, out = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "z", "--sweep-pivot", "0,0,0",
                            "--sweep-angles", "0:90:2")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["checks"]["F3"]["state"], "PASS")              # the placed pose is clear
        sw = out["metrics"]["sweep"]
        # The bar's far corner (15, 1) reaches y = 5 when 15 sin(t) + cos(t) = 5: t is about 15.5 deg.
        self.assertTrue(14 <= sw["first_overlap_deg"] <= 18, sw["first_overlap_deg"])
        self.assertEqual(sw["free_until_deg"], sw["first_overlap_deg"] - 2)
        self.assertEqual(sw["free_travel_deg"], sw["free_until_deg"])
        self.assertEqual(sw["direction"], "counter-clockwise")
        self.assertEqual(len(sw["table"]), 46)
        self.assertEqual(sw["table"][0], {"angle_deg": 0.0, "interference_mm3": 0.0, "min_gap_mm": 4.0})
        gaps = [r["min_gap_mm"] for r in sw["table"][: sw["table"].index(next(r for r in sw["table"] if r["interference_mm3"] > 0))]]
        self.assertEqual(gaps, sorted(gaps, reverse=True))                  # closing in step by step
        self.assertGreater(max(r["interference_mm3"] for r in sw["table"]), 10)   # deep inside the block mid-sweep
        self.assertEqual(sw["table"][-1]["interference_mm3"], 0.0)                 # at 90 deg the bar has passed it
        # A stop within the range is not a failure by itself: WARN until the needed travel is known.
        self.assertEqual(out["checks"]["F3_sweep"]["state"], "WARN")
        self.assertEqual(out["gate"], "WARN")
        self.assertTrue(any("--sweep-travel" in w for w in out["warnings"]))
        # Required travel below the stop: PASS and the stop is reported; above it: FAIL.
        code, out = run_fit(self.stop, self.lever, "--play", "none", "--sweep-angles", "0:90:2", "--sweep-travel", "10")
        self.assertEqual(out["checks"]["F3_sweep"]["state"], "PASS")
        self.assertEqual(out["gate"], "PASS")
        self.assertIn("stops at", out["checks"]["F3_sweep"]["note"])
        code, out = run_fit(self.stop, self.lever, "--play", "none", "--sweep-angles", "0:90:2", "--sweep-travel", "30")
        self.assertEqual(out["checks"]["F3_sweep"]["state"], "FAIL")
        self.assertEqual(out["gate"], "FAIL")
        self.assertEqual(out["checks"]["F3_sweep"]["return_to"], "phase4")

    def test_direction_matches_the_reversed_axis(self):
        """-40:0:2 about +z is the clockwise sweep from the placed pose: the bar swings away from
        the block and stays free, exactly like 0:40:2 about -z; and 0:40:2 about +z hits where
        -40:0:2 about -z hits, at the same magnitude."""
        cw_z = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "z", "--sweep-angles", "-40:0:2")[1]
        ccw_negz = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "0,0,-1", "--sweep-angles", "0:40:2")[1]
        for out in (cw_z, ccw_negz):
            self.assertEqual(out["checks"]["F3_sweep"]["state"], "PASS", out["checks"]["F3_sweep"])
            self.assertIsNone(out["metrics"]["sweep"]["first_overlap_deg"])
            self.assertEqual(out["metrics"]["sweep"]["closest"]["angle_deg"], 0.0)
        self.assertEqual(cw_z["metrics"]["sweep"]["direction"], "clockwise")
        self.assertEqual([r["angle_deg"] for r in cw_z["metrics"]["sweep"]["table"][:3]], [0.0, -2.0, -4.0])
        self.assertEqual([r["min_gap_mm"] for r in cw_z["metrics"]["sweep"]["table"]],
                         [r["min_gap_mm"] for r in ccw_negz["metrics"]["sweep"]["table"]])
        ccw_z = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "z", "--sweep-angles", "0:40:2")[1]
        cw_negz = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "0,0,-1", "--sweep-angles", "0:-40:2")[1]
        self.assertEqual(cw_negz["metrics"]["sweep"]["first_overlap_deg"], -ccw_z["metrics"]["sweep"]["first_overlap_deg"])
        self.assertEqual(cw_negz["metrics"]["sweep"]["free_travel_deg"], ccw_z["metrics"]["sweep"]["free_travel_deg"])
        self.assertEqual([r["interference_mm3"] for r in cw_negz["metrics"]["sweep"]["table"]],
                         [r["interference_mm3"] for r in ccw_z["metrics"]["sweep"]["table"]])

    def test_sweep_usage_errors(self):
        for argv in (["--sweep-angles", "0:90"], ["--sweep-angles", "0:90:0"], ["--sweep-angles", "-20:20:5"],
                     ["--sweep-axis", "0,0,0", "--sweep-angles", "0:9:1"]):
            code, out = run_fit(self.stop, self.lever, *argv)
            self.assertEqual(code, 1, argv)
            self.assertFalse(out["ran"])
        self.assertEqual(fit.parse_angles("40:0:-5"), [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0])
        self.assertEqual(fit.parse_angles("-10:0:5"), [0.0, -5.0, -10.0])


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
