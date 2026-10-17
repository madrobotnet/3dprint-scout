"""Tests for scripts/strength.py: formulas, verdicts, the data tables, and the field comparison
of 2026-10 (a failed and a working print-in-place latch) run through the same load."""
import io
import json
import math
import os
import sys
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import strength  # noqa: E402


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = strength.main(list(argv))
    return code, json.loads(buf.getvalue())


class Tables(unittest.TestCase):
    def test_materials_come_from_bambu_data_sheets_with_xy_and_z(self):
        for key, m in strength.MATERIALS.items():
            self.assertTrue(m["url"].startswith("https://store.bblcdn.com/"), key)
            self.assertEqual(m["retrieved"], "2026-10-18")
            self.assertRegex(m["tds"], r"^V\d\.\d$")
            for prop in ("E", "tensile", "elongation", "flex_modulus", "flex"):
                self.assertEqual(set(m[prop]), {"xy", "z"}, (key, prop))
                self.assertGreater(m[prop]["xy"], 0)
                self.assertGreaterEqual(m[prop]["xy"], m[prop]["z"], (key, prop))   # layers are the weak direction
        self.assertEqual(set(strength.MATERIALS), {"pla_basic", "pla_matte", "pla_pure", "petg_basic", "petg_hf", "abs", "asa"})
        self.assertEqual(strength.MATERIALS["pla_basic"]["tensile"], {"xy": 35, "z": 31})
        self.assertEqual(strength.MATERIALS["petg_basic"]["flex"], {"xy": 75, "z": 56})

    def test_loads_have_a_source_and_a_design_rule(self):
        self.assertIn("Ergonomics 46(15)", strength.LOADS_SOURCE["citation"])
        fp = strength.LOADS["finger_push"]
        self.assertAlmostEqual(fp["design_N"], 52.58 + 18.01, places=1)
        self.assertEqual(strength.load_value("finger_push")[0], fp["design_N"])
        self.assertEqual(strength.load_value("35")[0], 35.0)
        for bad in ("thumb", "-5", "0", "nan"):
            with self.assertRaises(strength.StrengthError, msg=bad):
                strength.load_value(bad)
        code, out = run("materials")
        self.assertEqual(code, 0)
        self.assertIn("pla_pure", out["materials"])
        code, out = run("loads")
        self.assertEqual(out["source"]["retrieved"], "2026-10-18")

    def test_materials_reference_mirrors_the_table(self):
        with open(os.path.join(HERE, "..", "references", "materials.md"), encoding="utf-8") as f:
            text = f.read()
        for key, m in strength.MATERIALS.items():
            self.assertIn(m["url"], text, key)
            self.assertIn(m["name"], text, key)
            self.assertIn(f"{m['tensile']['xy']:g}", text, key)
        self.assertIn(strength.LOADS_SOURCE["url"], text)


class Formulas(unittest.TestCase):
    def test_beam_matches_hand_values(self):
        # 6 x 3 mm cantilever, 20 mm, 60 N: I = 13.5, M = 1200 N mm, sigma = 1200 * 1.5 / 13.5 = 133.3 MPa
        code, out = run("beam", "--b", "6", "--h", "3", "--length", "20", "--support", "cantilever", "--load", "60",
                        "--material", "pla_basic", "--orientation", "xy")
        self.assertEqual(code, 0, out["errors"])
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 133.33, places=2)
        self.assertEqual(out["checks"]["bending"]["state"], "FAIL")
        self.assertAlmostEqual(out["deflection_mm"], 60 * 20 ** 3 / (3 * 2750 * 13.5), places=3)
        code, out = run("beam", "--b", "6", "--h", "3", "--length", "20", "--support", "simple", "--load", "60",
                        "--material", "pla_basic", "--orientation", "xy")
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 133.33 / 4, places=2)
        self.assertEqual(out["checks"]["bending"]["state"], "PASS")

    def test_pin_shear_and_bending(self):
        # d = 4, double shear, 100 N: tau = 100 / (2 * 12.566) = 3.98 MPa; through, L = 12: M = 150, sigma = 32*150/(pi*64) = 23.9
        code, out = run("pin", "--d", "4", "--engagement", "12", "--shear", "double", "--load", "100",
                        "--material", "petg_basic", "--orientation", "xy")
        self.assertAlmostEqual(out["checks"]["shear"]["stress_mpa"], 3.98, places=2)
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 23.87, places=2)
        self.assertAlmostEqual(out["checks"]["shear"]["strength_mpa"], 0.58 * 51, places=2)
        self.assertIn("F L / 8", out["checks"]["bending"]["formula"])
        code, stub = run("pin", "--d", "4", "--engagement", "12", "--shear", "single", "--load", "100",
                         "--material", "petg_basic", "--orientation", "xy")
        self.assertEqual(stub["inputs"]["support"], "stub")
        self.assertAlmostEqual(stub["checks"]["bending"]["stress_mpa"], 4 * 23.87, places=1)     # F L / 2 vs F L / 8
        self.assertAlmostEqual(stub["checks"]["shear"]["stress_mpa"], 2 * 3.98, places=2)

    def test_link_bearing_and_verdicts(self):
        code, out = run("link", "--b", "4", "--h", "2", "--load", "40", "--material", "abs", "--orientation", "z")
        self.assertAlmostEqual(out["checks"]["tension"]["stress_mpa"], 5.0)
        self.assertEqual(out["checks"]["tension"]["strength_mpa"], 28)                  # Z value, the default
        self.assertNotIn("bending_from_bow", out["checks"])
        code, out = run("link", "--b", "4", "--h", "2", "--bow", "3", "--load", "40", "--material", "abs")
        self.assertIn("bending_from_bow", out["checks"])
        self.assertTrue(any("conservative default" in a for a in out["assumptions"]))
        code, out = run("bearing", "--d", "3", "--t", "5", "--edge", "2", "--load", "30", "--material", "asa", "--orientation", "xy")
        self.assertAlmostEqual(out["checks"]["bearing"]["stress_mpa"], 2.0)
        self.assertAlmostEqual(out["checks"]["tear_out"]["stress_mpa"], 1.5)
        self.assertEqual(strength.verdict(10, 25, 2.0)[0], "PASS")
        self.assertEqual(strength.verdict(15, 25, 2.0)[0], "WARN")
        self.assertEqual(strength.verdict(30, 25, 2.0)[0], "FAIL")
        self.assertEqual(strength.verdict(0, 25, 2.0), ("PASS", math.inf))

    def test_usage_errors_are_json(self):
        for argv in (["pin", "--d", "3"], ["pin", "--d", "3", "--engagement", "5", "--load", "x", "--material", "pla_basic"],
                     ["beam", "--b", "0", "--h", "2", "--length", "5", "--load", "10", "--material", "pla_basic"],
                     ["link", "--b", "2", "--h", "2", "--load", "10", "--material", "unobtainium"],
                     ["bearing", "--d", "3", "--t", "2", "--edge", "1", "--load", "10", "--material", "abs", "--orientation", "yz"],
                     ["beam", "--b", "2", "--h", "2", "--length", "5", "--load", "10", "--material", "abs", "--sf", "0.5"]):
            code, out = run(*argv)
            self.assertEqual(code, 1, argv)
            self.assertFalse(out["ran"])
            self.assertTrue(out["errors"])


class FieldComparison(unittest.TestCase):
    """The two latches of design.md ("Mechanisms that carry load") under the same finger-push
    design load (70.6 N; each of the failed latch's two stub pins takes half). What the static
    model says, recorded as is: it flags the failed latch's 1.2 mm curved arms and bars by a
    wide margin, but its Ø2.6 stub pins and 1.3 mm pin walls pass on paper with a factor of
    about 4; the working latch passes everywhere. Pins and knuckles broke in the field all the
    same: snapping a latch over its cam is an impact, the lever multiplies the hand force, and
    corners concentrate stress, none of which this hand calculation sees. So the minimums in
    design.md stay the primary rule; strength.py separates the hopeless from the plausible."""

    LOAD = "finger_push"

    def test_failed_latch(self):
        arm = run("link", "--b", "2.2", "--h", "1.2", "--bow", "2.5", "--load", self.LOAD, "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(arm["gate"], "FAIL")
        self.assertLess(arm["checks"]["bending_from_bow"]["sf_achieved"], 0.3)
        self.assertEqual(arm["checks"]["tension"]["state"], "WARN")                      # even straight, under the factor
        bar = run("beam", "--b", "2.6", "--h", "1.7", "--length", "12", "--support", "cantilever", "--load", self.LOAD,
                  "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(bar["gate"], "FAIL")
        pin = run("pin", "--d", "2.6", "--engagement", "2.0", "--shear", "single", "--support", "stub", "--load", "35.3",
                  "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(pin["gate"], "PASS")                                             # on paper; it broke
        self.assertLess(pin["checks"]["bending"]["sf_achieved"], 4.0)
        self.assertIn("engagement / d = 0.8", " ".join(pin["assumptions"]))
        wall = run("bearing", "--d", "3.45", "--t", "2.0", "--edge", "1.3", "--load", "35.3", "--material", "pla_pure",
                   "--orientation", "xy")[1]
        self.assertEqual(wall["gate"], "PASS")                                            # on paper; it broke
        self.assertLess(wall["checks"]["tear_out"]["sf_achieved"], 5.0)

    def test_working_latch(self):
        pin = run("pin", "--d", "3.24", "--engagement", "10.8", "--shear", "double", "--support", "through", "--load", self.LOAD,
                  "--material", "pla_basic", "--orientation", "xy")[1]
        self.assertEqual(pin["gate"], "PASS")
        self.assertGreater(pin["checks"]["bending"]["sf_achieved"], 2.5)
        self.assertGreater(pin["checks"]["shear"]["sf_achieved"], 4.5)
        wall = run("bearing", "--d", "3.9", "--t", "4.25", "--edge", "2.2", "--load", "35.3", "--material", "pla_basic",
                   "--orientation", "xy")[1]
        self.assertEqual(wall["gate"], "PASS")
        self.assertGreater(wall["checks"]["tear_out"]["sf_achieved"], 10)
        rail = run("link", "--b", "4.25", "--h", "2.5", "--load", self.LOAD, "--material", "pla_basic", "--orientation", "xy")[1]
        self.assertEqual(rail["gate"], "PASS")
        self.assertGreater(rail["checks"]["tension"]["sf_achieved"], 5)
        # Across layers the same pin still passes, with less to spare.
        pin_z = run("pin", "--d", "3.24", "--engagement", "10.8", "--shear", "double", "--load", self.LOAD,
                    "--material", "pla_basic", "--orientation", "z")[1]
        self.assertEqual(pin_z["gate"], "PASS")
        self.assertLess(pin_z["checks"]["bending"]["sf_achieved"], pin["checks"]["bending"]["sf_achieved"])


if __name__ == "__main__":
    unittest.main()
