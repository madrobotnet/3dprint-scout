"""The examples/ folder rebuilds with the commands in its READMEs, and the results match them."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")
HAS_SCAD = build.find_openscad() is not None
HAS_M3D = find_spec("manifold3d") is not None and find_spec("numpy") is not None


def run(cwd, *args):
    """Run a script the way an example README does, from a copy of the example folder."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, encoding="utf-8",
                          errors="replace", env=env, timeout=600)
    return proc.returncode, proc.stdout, proc.stderr


class ExampleCase(unittest.TestCase):
    def copy(self, name):
        """Copy examples/ to a temp dir (sources only) so builds never touch the repository."""
        tmp = tempfile.mkdtemp(prefix="3dps-ex-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        dst = os.path.join(tmp, "examples")
        shutil.copytree(EXAMPLES, dst, ignore=shutil.ignore_patterns("out", "__pycache__", "*.png"))
        shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(tmp, "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        return os.path.join(dst, name)

    def build(self, cwd, source, *extra):
        code, out, err = run(cwd, "../../scripts/build.py", "run", source, "--params", "params.json",
                             "--out", "out", "--printer", "../printers.x2d.json", "--tools", "0", *extra)
        report = json.loads(out)
        self.assertEqual(report["gate"], "PASS", (report.get("errors"), err[-2000:]))
        return report

    def fit(self, cwd, rotate, translate):
        code, out, err = run(cwd, "../../scripts/fit.py", "out/box.stl", "out/lid.stl",
                             "--b-rotate", rotate, "--b-translate", translate, "--min-clearance", "0.2")
        report = json.loads(out)
        self.assertEqual(report["gate"], "PASS", (report.get("checks"), err[-2000:]))
        f3 = report["metrics"]
        self.assertEqual(f3["interference_mm3"], 0.0)
        self.assertEqual(f3["min_gap_mm"], 0.0)   # seated: the parts touch
        for p in f3["play"]:
            self.assertAlmostEqual(p["play_mm"], 0.2, delta=0.005)
        return report

    def place_and_preview(self, cwd, stls, moves, *extra):
        for src, dst, translate in moves:
            code, out, err = run(cwd, "../place.py", src, dst, "--translate", translate)
            self.assertEqual(code, 0, err[-2000:])
        code, out, err = run(cwd, "../../scripts/preview.py", *stls, "-o", "out/preview.png", *extra)
        self.assertTrue(json.loads(out)["sane"], err[-2000:])


@unittest.skipUnless(HAS_SCAD and HAS_M3D, "needs OpenSCAD, manifold3d and numpy")
class TestAABatteryBox(ExampleCase):
    def test_readme_commands(self):
        cwd = self.copy("aa-battery-box")
        report = self.build(cwd, "aa_box.scad")
        self.assertEqual(report["warnings"], [])
        self.fit(cwd, "180,0,0", "0,37.8,54.2")
        self.place_and_preview(cwd, ["out/box.stl", "out/lid_side.stl"],
                               [("out/lid.stl", "out/lid_side.stl", "0,47.8,0")])


@unittest.skipUnless(HAS_M3D, "needs manifold3d and numpy")
class TestSnapBox(ExampleCase):
    def test_readme_commands(self):
        cwd = self.copy("snap-box")
        report = self.build(cwd, "snapbox.py")
        self.assertEqual(report["warnings"], [])
        self.fit(cwd, "180,0,0", "0,45,33")
        self.place_and_preview(cwd, ["out/box.stl", "out/lid_side.stl"],
                               [("out/lid.stl", "out/lid_side.stl", "0,55,0")])


@unittest.skipUnless(HAS_M3D, "needs manifold3d and numpy")
class TestLeafHandle(ExampleCase):
    def test_readme_commands(self):
        cwd = self.copy("leaf-handle")
        report = self.build(cwd, "handle.py")
        # The README promises exactly one soft warning: P2 under the round grip.
        self.assertEqual(len(report["warnings"]), 1, report["warnings"])
        self.assertIn("P2", report["warnings"][0])
        code, out, err = run(cwd, "../../scripts/preview.py", "out/handle.stl", "-o", "out/preview.png")
        self.assertTrue(json.loads(out)["sane"], err[-2000:])


@unittest.skipUnless(HAS_M3D, "needs manifold3d and numpy")
class TestFitTest(ExampleCase):
    def test_readme_commands(self):
        cwd = self.copy("fit-test")
        code, out, err = run(cwd, "../../scripts/fit_test.py", "--profile", "rounded", "--size", "45.1,14.0",
                             "--radius", "2", "--out", "out", "--name", "fit")
        self.assertEqual(code, 0, err[-2000:])
        with open(os.path.join(cwd, "out", "fit.json"), encoding="utf-8") as f:
            summary = json.load(f)
        self.assertEqual([s["clearance_per_side_mm"] for s in summary["steps"]], [0.15, 0.3, 0.45])
        self.assertEqual([s["marks"] for s in summary["steps"]], [1, 2, 3])
        self.place_and_preview(cwd, ["out/fit_1.stl", "out/fit_2_side.stl", "out/fit_3_side.stl"],
                               [("out/fit_2.stl", "out/fit_2_side.stl", "0,30,0"),
                                ("out/fit_3.stl", "out/fit_3_side.stl", "0,60,0")],
                               "--views", "iso,top")


class TestExampleFiles(unittest.TestCase):
    def test_every_example_has_readme_and_preview(self):
        for name in ("aa-battery-box", "snap-box", "leaf-handle", "fit-test"):
            for f in ("README.md", "preview.png", "thumb.png"):
                self.assertTrue(os.path.isfile(os.path.join(EXAMPLES, name, f)), f"{name}/{f}")

    def test_printers_file_names_no_template(self):
        with open(os.path.join(EXAMPLES, "printers.x2d.json"), encoding="utf-8") as f:
            printers = json.load(f)
        x2d = printers["printers"]["x2d"]
        self.assertNotIn("template_3mf", x2d["slicer"])
        self.assertEqual(len(x2d["tools"]), 2)


if __name__ == "__main__":
    unittest.main()
