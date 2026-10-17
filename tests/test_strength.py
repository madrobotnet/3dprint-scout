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
        rows = {line.split("|")[1].strip(): [c.strip() for c in line.strip().strip("|").split("|")]
                for line in text.splitlines() if line.startswith("| `")}
        for key, m in strength.MATERIALS.items():
            self.assertIn(m["url"], text, key)
            cells = rows[f"`{key}`"]
            self.assertEqual(cells[1], f"{m['name']} ({m['tds']})", key)
            for i, prop in enumerate(("tensile", "E", "flex", "flex_modulus", "elongation")):
                self.assertEqual(cells[2 + i], f"{m[prop]['xy']:g} / {m[prop]['z']:g}", (key, prop))
        self.assertIn(strength.LOADS_SOURCE["url"], text)
        for key, v in strength.LOADS.items():
            cells = rows[f"`{key}`"]                                   # all mean ± SD | male mean ± SD | design
            for cell, mean, sd in ((cells[2], v["mean"], v["sd"]), (cells[3], v["male_mean"], v["male_sd"])):
                shown = [float(x) for x in cell.split("±")]
                self.assertAlmostEqual(shown[0], mean, delta=0.051, msg=key)
                self.assertAlmostEqual(shown[1], sd, delta=0.051, msg=key)
            self.assertAlmostEqual(float(cells[4]), v["design_N"], delta=0.051, msg=key)


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
        # d = 4, double shear, 100 N: tau = 4/3 x 100 / (2 x 12.566) = 5.31 MPa (peak at the neutral axis).
        # Loose pin through two 3 mm supports, member 12 mm, no gap: M = 100 (12 + 6) / 8 = 225 N mm,
        # sigma = 32 x 225 / (pi x 64) = 35.81 MPa.
        code, out = run("pin", "--d", "4", "--engagement", "12", "--support-t", "3", "--shear", "double", "--load", "100",
                        "--material", "petg_basic", "--orientation", "xy")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["inputs"]["support"], "through")
        self.assertAlmostEqual(out["checks"]["shear"]["stress_mpa"], 5.31, places=2)
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 35.81, places=2)
        self.assertAlmostEqual(out["checks"]["shear"]["strength_mpa"], 0.58 * 51, places=2)
        self.assertIn("(b + 2 a + 4 g) / 8", out["checks"]["bending"]["formula"])
        self.assertTrue(any("no --gap given" in n for n in out["assumptions"]))
        # The gap on each side adds 4 g to the span: 0.5 mm -> M = 100 (18 + 2) / 8 = 250.
        code, gap = run("pin", "--d", "4", "--engagement", "12", "--support-t", "3", "--gap", "0.5", "--shear", "double",
                        "--load", "100", "--material", "petg_basic", "--orientation", "xy")
        self.assertAlmostEqual(gap["checks"]["bending"]["stress_mpa"], 35.81 * 250 / 225, places=2)
        self.assertFalse(any("no --gap given" in n for n in gap["assumptions"]))
        # One stub, 12 mm inside the mating part, 0.4 mm gap: M = 100 (0.4 + 6) = 640, sigma = 101.86; tau doubles.
        code, stub = run("pin", "--d", "4", "--engagement", "12", "--gap", "0.4", "--shear", "single", "--load", "100",
                         "--material", "petg_basic", "--orientation", "xy")
        self.assertEqual(stub["inputs"]["support"], "stub")
        self.assertAlmostEqual(stub["checks"]["bending"]["stress_mpa"], 32 * 640 / (math.pi * 64), places=2)
        self.assertAlmostEqual(stub["checks"]["shear"]["stress_mpa"], 2 * 5.305, places=2)
        # Both ends stubs (a pin formed on a lever, ends in 3 mm rails): F / 2 per end, M = 50 (0.4 + 1.5) = 95.
        code, two = run("pin", "--d", "4", "--engagement", "3", "--gap", "0.4", "--shear", "double", "--support", "stub",
                        "--load", "100", "--material", "petg_basic", "--orientation", "xy")
        self.assertAlmostEqual(two["checks"]["bending"]["stress_mpa"], 32 * 95 / (math.pi * 64), places=2)
        self.assertIn("F' = F / 2", two["checks"]["bending"]["formula"])
        # A flat pin pushed across the layers: shear on the layer joints uses Z, bending keeps X-Y.
        code, flat = run("pin", "--d", "4", "--engagement", "3", "--shear", "double", "--support", "stub", "--load", "100",
                         "--material", "petg_basic", "--orientation", "xy", "--load-across-layers")
        self.assertAlmostEqual(flat["checks"]["shear"]["strength_mpa"], 0.58 * 35, places=2)
        self.assertEqual(flat["checks"]["bending"]["strength_mpa"], 75)
        self.assertTrue(any("slides layer on layer" in n for n in flat["assumptions"]))
        code, up = run("pin", "--d", "4", "--engagement", "3", "--shear", "double", "--support", "stub", "--load", "100",
                       "--material", "petg_basic", "--orientation", "z")
        self.assertAlmostEqual(up["checks"]["shear"]["strength_mpa"], 0.58 * 35, places=2)
        self.assertEqual(up["checks"]["bending"]["strength_mpa"], 56)
        # A through pin is held at both ends: single shear is refused; a through pin needs the support thickness.
        code, out = run("pin", "--d", "4", "--engagement", "12", "--shear", "single", "--support", "through", "--load", "100",
                        "--material", "petg_basic")
        self.assertEqual(code, 1)
        self.assertIn("double shear", out["errors"][0])
        code, out = run("pin", "--d", "4", "--engagement", "12", "--shear", "double", "--load", "100", "--material", "petg_basic")
        self.assertEqual(code, 1)
        self.assertIn("--support-t", out["errors"][0])

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
                     ["beam", "--b", "2", "--h", "2", "--length", "5", "--load", "10", "--material", "abs", "--sf", "0.5"],
                     ["beam", "--b", "2", "--h", "2", "--length", "5", "--load", "10", "--material", "abs", "--sf", "nan"],
                     ["beam", "--b", "2", "--h", "2", "--length", "inf", "--load", "10", "--material", "abs"],
                     ["link", "--b", "2", "--h", "2", "--bow", "-3", "--load", "10", "--material", "abs"],
                     ["link", "--b", "2", "--h", "2", "--bow", "nan", "--load", "10", "--material", "abs"],
                     ["pin", "--d", "3", "--engagement", "5", "--gap", "-0.3", "--load", "10", "--material", "abs"],
                     ["pin", "--d", "3", "--engagement", "5", "--support-t", "nan", "--shear", "double", "--load", "10", "--material", "abs"],
                     ["pin", "--d", "-3", "--engagement", "5", "--load", "10", "--material", "abs"]):
            code, out = run(*argv)
            self.assertEqual(code, 1, argv)
            self.assertFalse(out["ran"])
            self.assertTrue(out["errors"])
            self.assertNotIn("nan", json.dumps(out).lower().replace("finance", ""))
        # Negative values reach the sign check with the option named, not argparse's "expected one argument".
        code, out = run("link", "--b", "2", "--h", "2", "--bow", "-3", "--load", "10", "--material", "abs")
        self.assertIn("--bow", out["errors"][0])


class FieldComparison(unittest.TestCase):
    """The two latches of design.md ("Mechanisms that carry load") under the same finger-push
    design load, 70.6 N, with the load share stated: the failed latch has two curved arms and
    two stub pins, one each side, so each arm, pin and pin wall takes 35.3 N; its bar is run
    both ways, as a 12 mm cantilever with the full load (the worst case) and as a span between
    the two arms with the load at its centre. The arm's 2.5 mm bow and the bar's 12 mm length
    come from the generator that made the failed latch. Print-in-place gaps at the pin roots
    are taken as the radial clearances (0.42 and 0.33 mm). The lever ratio of either latch was
    not measured, so the hand force is applied as is (1:1); at a ratio of 2 the failed stub pin
    reads WARN, at 3 FAIL. Failed latch material: PLA Pure per the project file (owner to
    confirm; with PETG Basic, X-Y 51 / 75 MPa, every verdict is the same).

    What the static model says, recorded as is: it flags the arms and the bar by a wide margin,
    but the Ø2.6 stub pins pass in bending (2.6) and in shear (3.4; 2.0, WARN, when the load
    crosses the layers), and the 1.3 mm pin walls pass tear-out at 4.4; the working latch passes
    everywhere. Pins and knuckles broke in the field all the same: snapping a latch over its cam
    is an impact, the lever ratio was not measured, and corners concentrate stress, none of
    which a static hand calculation sees. So the minimums in design.md stay the primary rule;
    strength.py separates the hopeless from the plausible."""

    LOAD = "finger_push"          # 70.6 N
    HALF = "35.3"                 # two arms, two pins: half each

    def test_failed_latch(self):
        arm = run("link", "--b", "2.2", "--h", "1.2", "--bow", "2.5", "--load", self.HALF, "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(arm["gate"], "FAIL")
        self.assertAlmostEqual(arm["checks"]["bending_from_bow"]["sf_achieved"], 0.42, places=2)
        self.assertEqual(arm["checks"]["tension"]["state"], "PASS")                      # straight and shared it would hold
        arm_full = run("link", "--b", "2.2", "--h", "1.2", "--bow", "2.5", "--load", self.LOAD, "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertAlmostEqual(arm_full["checks"]["bending_from_bow"]["sf_achieved"], 0.21, places=2)   # one arm alone
        bar = run("beam", "--b", "2.6", "--h", "1.7", "--length", "12", "--support", "cantilever", "--load", self.LOAD,
                  "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(bar["gate"], "FAIL")
        self.assertAlmostEqual(bar["checks"]["bending"]["sf_achieved"], 0.11, places=2)
        span = run("beam", "--b", "2.6", "--h", "1.7", "--length", "12", "--support", "simple", "--load", self.LOAD,
                   "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(span["gate"], "FAIL")
        self.assertAlmostEqual(span["checks"]["bending"]["sf_achieved"], 0.44, places=2)
        pin = run("pin", "--d", "2.6", "--engagement", "2.0", "--gap", "0.42", "--shear", "single", "--support", "stub",
                  "--load", self.HALF, "--material", "pla_pure", "--orientation", "xy")[1]
        self.assertEqual(pin["gate"], "PASS")                                             # on paper; it broke
        self.assertAlmostEqual(pin["checks"]["bending"]["sf_achieved"], 2.58, places=2)
        self.assertAlmostEqual(pin["checks"]["shear"]["sf_achieved"], 3.37, places=2)
        self.assertIn("engagement / d = 0.8", " ".join(pin["assumptions"]))
        pin_z = run("pin", "--d", "2.6", "--engagement", "2.0", "--gap", "0.42", "--shear", "single", "--support", "stub",
                    "--load", self.HALF, "--material", "pla_pure", "--orientation", "xy", "--load-across-layers")[1]
        self.assertEqual(pin_z["gate"], "WARN")                                           # shear on the layer joints
        self.assertAlmostEqual(pin_z["checks"]["shear"]["sf_achieved"], 1.96, places=2)
        for ratio, state in ((2, "WARN"), (3, "FAIL")):                                   # the unmeasured lever ratio
            lever = run("pin", "--d", "2.6", "--engagement", "2.0", "--gap", "0.42", "--shear", "single", "--support", "stub",
                        "--load", str(35.3 * ratio), "--material", "pla_pure", "--orientation", "xy")[1]
            self.assertEqual(lever["checks"]["bending"]["state"], state, ratio)
        wall = run("bearing", "--d", "3.45", "--t", "2.0", "--edge", "1.3", "--load", self.HALF, "--material", "pla_pure",
                   "--orientation", "xy")[1]
        self.assertEqual(wall["gate"], "PASS")                                            # on paper; it broke
        self.assertAlmostEqual(wall["checks"]["tear_out"]["sf_achieved"], 4.4, places=2)
        petg = run("pin", "--d", "2.6", "--engagement", "2.0", "--gap", "0.42", "--shear", "single", "--support", "stub",
                   "--load", self.HALF, "--material", "petg_basic", "--orientation", "xy")[1]
        self.assertEqual(petg["gate"], "PASS")

    def test_working_latch(self):
        # One Ø3.24 pin formed on the lever, both ends in 4.25 mm rails: two stubs, F / 2 each.
        pin = run("pin", "--d", "3.24", "--engagement", "4.25", "--gap", "0.33", "--shear", "double", "--support", "stub",
                  "--load", self.LOAD, "--material", "pla_basic", "--orientation", "xy")[1]
        self.assertEqual(pin["gate"], "PASS")
        self.assertAlmostEqual(pin["checks"]["bending"]["sf_achieved"], 2.93, places=2)
        self.assertAlmostEqual(pin["checks"]["shear"]["sf_achieved"], 3.56, places=2)
        wall = run("bearing", "--d", "3.9", "--t", "4.25", "--edge", "2.2", "--load", self.HALF, "--material", "pla_basic",
                   "--orientation", "xy")[1]
        self.assertEqual(wall["gate"], "PASS")
        self.assertGreater(wall["checks"]["tear_out"]["sf_achieved"], 10)
        rail = run("link", "--b", "4.25", "--h", "2.5", "--load", self.LOAD, "--material", "pla_basic", "--orientation", "xy")[1]
        self.assertEqual(rail["gate"], "PASS")
        self.assertGreater(rail["checks"]["tension"]["sf_achieved"], 5)
        # Across layers the same pin still passes, with less to spare.
        pin_z = run("pin", "--d", "3.24", "--engagement", "4.25", "--gap", "0.33", "--shear", "double", "--support", "stub",
                    "--load", self.LOAD, "--material", "pla_basic", "--orientation", "z")[1]
        self.assertEqual(pin_z["gate"], "PASS")
        self.assertAlmostEqual(pin_z["checks"]["bending"]["sf_achieved"], 2.27, places=2)
        # A loose pin of the same size through the same rails, with the 10.8 mm lever between them, would be WARN.
        loose = run("pin", "--d", "3.24", "--engagement", "10.8", "--support-t", "4.25", "--gap", "0.33", "--shear", "double",
                    "--support", "through", "--load", self.LOAD, "--material", "pla_basic", "--orientation", "xy")[1]
        self.assertEqual(loose["checks"]["bending"]["state"], "WARN")
        self.assertAlmostEqual(loose["checks"]["bending"]["sf_achieved"], 1.39, places=2)


if __name__ == "__main__":
    unittest.main()
