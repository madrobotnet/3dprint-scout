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

    def test_overwrite_only_under_the_working_folder(self):
        """S4-10: a rerun into out/ replaces the pieces with --overwrite; a folder outside the
        current directory (a delivered copy) is never replaced."""
        cwd = os.getcwd()
        os.chdir(self.d)
        try:
            code, out = run_fit_test("--profile", "circle", "--size", "12", "--out", "out/fit", "--steps", "2")
            self.assertEqual(code, 0, out["errors"])
            code, out = run_fit_test("--profile", "circle", "--size", "12", "--out", "out/fit", "--steps", "2")
            self.assertEqual(code, 1)
            self.assertIn("already exists", out["errors"][0])
            self.assertIn("--overwrite", out["errors"][0])
            code, out = run_fit_test("--profile", "circle", "--size", "12.4", "--out", "out/fit", "--steps", "2", "--overwrite")
            self.assertEqual(code, 0, out["errors"])
            self.assertEqual(out["profile"]["size_mm"], [12.4, 12.4])
            with open(os.path.join("out", "fit", "fit.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["profile"]["size_mm"], [12.4, 12.4])     # rewritten
            # Review N5: fewer steps than last time; the earlier series' extra pieces go, so the
            # folder holds one series (and says what it removed).
            code, out = run_fit_test("--profile", "circle", "--size", "12", "--out", "out/fit", "--steps", "4", "--overwrite")
            self.assertEqual(code, 0, out["errors"])
            code, out = run_fit_test("--profile", "circle", "--size", "12", "--out", "out/fit", "--steps", "1", "--overwrite")
            self.assertEqual(code, 0, out["errors"])
            self.assertEqual(sorted(os.listdir(os.path.join("out", "fit"))), ["fit.json", "fit_1.stl"])
            self.assertTrue(any(w.startswith("removed fit_2.stl, fit_3.stl, fit_4.stl") for w in out["warnings"]), out["warnings"])
            with tempfile.TemporaryDirectory() as elsewhere:
                code, out = run_fit_test("--profile", "circle", "--size", "12", "--out", elsewhere, "--steps", "1")
                self.assertEqual(code, 0, out["errors"])
                code, out = run_fit_test("--profile", "circle", "--size", "12", "--out", elsewhere, "--steps", "1", "--overwrite")
                self.assertEqual(code, 1)
                self.assertIn("working folder under the current directory only", out["errors"][0])
        finally:
            os.chdir(cwd)

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
        self.assertIn("designed snap or press fit", f3["note"])                     # S2-F06: not "shrink" for a snap
        self.assertIn("intended undercut", f3["note"])
        self.assertIn("otherwise one part must shrink", f3["note"])

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
        r = subprocess.run([sys.executable, "-I", "-B", os.path.join(SCRIPTS, "fit.py"), self.box, self.lids["lid"], *self.place,
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
        # Between the 14 and 16 deg steps the turn is followed, so the stop is bracketed to within
        # PATH_STEP at the reach radius (0.2 mm at 15.03 mm: 0.76 deg); the table keeps the two
        # angles that bracket it and counts the other checks between steps.
        self.assertTrue(15.4 <= sw["first_overlap_deg"] <= 16.0, sw["first_overlap_deg"])
        self.assertTrue(0 < sw["first_overlap_deg"] - sw["free_until_deg"] <= 0.77, sw)
        self.assertGreaterEqual(sw["between_steps_checked"], 1)
        self.assertEqual(sw["free_travel_deg"], sw["free_until_deg"])
        self.assertAlmostEqual(sw["reach_radius_mm"], math.hypot(15, 1), places=3)
        self.assertEqual(sw["direction"], "counter-clockwise")
        self.assertEqual(len([r for r in sw["table"] if not r.get("between_steps")]), 46)
        self.assertTrue(all(14 < r["angle_deg"] < 16 for r in sw["table"] if r.get("between_steps")))
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
        cw_z = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "z", "--sweep-angles", "-40:0:2",
                       "--sweep-travel", "40")[1]
        ccw_negz = run_fit(self.stop, self.lever, "--play", "none", "--sweep-axis", "0,0,-1", "--sweep-angles", "0:40:2",
                           "--sweep-travel", "40")[1]
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
@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class FollowsThePath(unittest.TestCase):
    """0.5.1: a move or a turn is followed along its path, not judged at its ends only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, man, name):
        from build import write_binary_stl
        path = os.path.join(self.d, name)
        mesh = man.to_mesh()
        write_binary_stl(path, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
        return path

    def test_a_ring_behind_a_lip_is_caught_by_the_lip(self):
        """A ring sits in a tube under a lip 1 mm above it. At the end of a 10 mm move up it would
        be past the lip, so an end-point check called it free; the lip stops it after 1 mm."""
        import manifold3d as m3d
        tube = m3d.Manifold.cylinder(10, 15, 15, 96) - m3d.Manifold.cylinder(10, 10.5, 10.5, 96)
        lip = (m3d.Manifold.cylinder(1, 15, 15, 96) - m3d.Manifold.cylinder(1, 9, 9, 96)).translate([0, 0, 10])
        ring = (m3d.Manifold.cylinder(2, 10.3, 10.3, 96) - m3d.Manifold.cylinder(2, 9.5, 9.5, 96)).translate([0, 0, 7])
        a, b = self.save(tube + lip, "tube.stl"), self.save(ring, "ring.stl")
        code, out = run_fit(a, b, "--play", "0,0,1;1,0,0", "--search", "10", "--min-clearance", "0.15")
        self.assertEqual(code, 0, out["errors"])
        up, side = out["metrics"]["play"]
        self.assertTrue(up["contact"], up)
        self.assertAlmostEqual(up["play_mm"], 1.0, delta=0.01)             # ring top z 9, lip underside z 10
        self.assertTrue(side["contact"])
        self.assertAlmostEqual(side["play_mm"], 0.2, delta=0.02)          # 10.5 bore, 10.3 ring
        self.assertIn("0.2 mm", out["metrics"]["play_method"])

    def test_a_thin_stop_between_two_steps_is_found(self):
        """A lever 0.6 mm thick and a 0.6 mm post at 5 deg: the 10 deg steps land on either side
        of it, so a step check called the turn free; the turn between the steps is followed."""
        import manifold3d as m3d
        post = m3d.Manifold.cube([0.6, 0.6, 4], center=True).translate([12 * math.cos(math.radians(5)),
                                                                          12 * math.sin(math.radians(5)), 0])
        lever = m3d.Manifold.cube([15, 0.6, 2]).translate([0, -0.3, -1])
        a, b = self.save(post, "post.stl"), self.save(lever, "lever.stl")
        code, out = run_fit(a, b, "--play", "none", "--sweep-axis", "z", "--sweep-pivot", "0,0,0",
                            "--sweep-angles", "0:30:10", "--sweep-travel", "30")
        self.assertEqual(code, 0, out["errors"])
        sw, f3 = out["metrics"]["sweep"], out["checks"]["F3_sweep"]
        self.assertEqual([r["interference_mm3"] for r in sw["table"] if not r.get("between_steps")], [0.0] * 4)
        self.assertEqual(f3["state"], "FAIL", f3)
        self.assertTrue(1.5 < sw["first_overlap_deg"] < 3.5, sw["first_overlap_deg"])
        self.assertEqual(out["gate"], "FAIL")

    def test_a_sweep_short_of_the_travel_or_not_from_zero_is_unverified(self):
        import manifold3d as m3d
        a = self.save(m3d.Manifold.cube([10, 10, 10]).translate([10, 5, -4]), "stop.stl")
        b = self.save(m3d.Manifold.cube([15, 2, 2]).translate([0, -1, 0]), "lever.stl")
        code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "0:10:2", "--sweep-travel", "30")
        f3 = out["checks"]["F3_sweep"]
        self.assertEqual((f3["state"], out["gate"]), ("UNVERIFIED", "UNVERIFIED"))   # free to 10 deg, 30 needed
        self.assertIn("short of the required 30 deg", f3["note"])
        code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "40:90:2")
        f3 = out["checks"]["F3_sweep"]
        self.assertEqual(f3["state"], "UNVERIFIED")                                   # the stop at ~15.5 deg is before 40
        self.assertIn("the first 40 deg are not checked", f3["note"])
        self.assertEqual(out["metrics"]["sweep"]["free_travel_deg"], 0.0)
        self.assertIsNone(out["metrics"]["sweep"]["free_until_deg"])
        # A hit inside the needed travel decides on its own, wherever the sweep started.
        code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "5:60:2", "--sweep-travel", "40")
        self.assertEqual(out["checks"]["F3_sweep"]["state"], "FAIL")
        # The travel is a magnitude: -40 for a clockwise sweep is 40, not a requirement always met.
        code, out = run_fit(a, b, "--play", "none", "--sweep-axis", "0,0,-1", "--sweep-angles", "-60:0:2",
                            "--sweep-travel", "-40")
        f3 = out["checks"]["F3_sweep"]
        self.assertEqual((f3["state"], f3["value"]["required_travel_deg"]), ("FAIL", 40.0), f3)
        # Codex (PR #11): a stop that starts just short of the required travel, between the last
        # free check (15.5) and the next one (16), passed because that next check landed past the
        # travel. The required angle is checked as an angle of its own.
        for need, state in (("15", "PASS"), ("15.95", "FAIL"), ("16", "FAIL")):
            code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "0:90:2", "--sweep-travel", need)
            f3, sw = out["checks"]["F3_sweep"], out["metrics"]["sweep"]
            self.assertEqual(f3["state"], state, (need, f3))
            if state == "FAIL":
                self.assertLessEqual(sw["first_overlap_deg"], float(need))
                self.assertTrue(any(r.get("required_travel") for r in sw["table"]) or float(need) in
                                [r["angle_deg"] for r in sw["table"]])
            else:
                self.assertGreaterEqual(sw["free_until_deg"], float(need))
        # Nothing hit and no travel given: nothing to decide.
        code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "-40:0:2")
        self.assertEqual(out["checks"]["F3_sweep"]["state"], "UNVERIFIED")
        self.assertIn("--sweep-travel", out["checks"]["F3_sweep"]["note"])

    def test_a_turn_in_contact_is_bounded(self):
        """A lever lying on its plate turns with gap 0 all the way: the checks between steps stop
        at PATH_STEP spacing, the table keeps only the steps, and a budget too small to finish
        leaves the sweep UNVERIFIED, never PASS."""
        import manifold3d as m3d
        a = self.save(m3d.Manifold.cube([120, 120, 2]).translate([-60, -60, -2]), "plate.stl")
        b = self.save(m3d.Manifold.cube([50, 4, 2]).translate([0, -2, 0]), "lever.stl")
        code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "0:90:2", "--sweep-travel", "90")
        sw = out["metrics"]["sweep"]
        self.assertEqual(out["checks"]["F3_sweep"]["state"], "PASS", out["checks"]["F3_sweep"])
        self.assertEqual(len(sw["table"]), 46)                                       # steps only: no stop to bracket
        spacing = math.radians(2) * sw["reach_radius_mm"] / (sw["between_steps_checked"] / 45 + 1)
        self.assertLessEqual(spacing, fit.PATH_STEP + 1e-6)                           # every gap covered at 0.2 mm
        self.assertLess(sw["between_steps_checked"], fit.SWEEP_BUDGET)
        orig = fit.SWEEP_BUDGET
        try:
            fit.SWEEP_BUDGET = 50
            code, out = run_fit(a, b, "--play", "none", "--sweep-angles", "0:90:2", "--sweep-travel", "90")
        finally:
            fit.SWEEP_BUDGET = orig
        f3 = out["checks"]["F3_sweep"]
        self.assertEqual((f3["state"], out["gate"]), ("UNVERIFIED", "UNVERIFIED"), f3)
        self.assertIn("more than 50 checks", f3["note"])
        self.assertEqual(out["metrics"]["sweep"]["between_steps_checked"], 50)


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
