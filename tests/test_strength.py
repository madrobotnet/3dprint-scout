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


class Hinge(unittest.TestCase):
    """The hinge case: a print-in-place hinge with alternating knuckles as parts.hinge builds it."""

    SD = ["--knuckles", "5", "--length", "36", "--gap", "0.3", "--clearance", "0.3", "--load", "finger_pull",
          "--material", "pla_basic", "--orientation", "xy"]

    def test_end_moment_formula_and_its_limits(self):
        # Fixed-fixed span L = b + 2 g, P spread over the middle b: the end moment is the mean of the simply
        # supported moment diagram, (1 / (2 L)) integral of w x (L - x) over the loaded part. Check the closed
        # form against that integral done numerically, then the two limits.
        for b, g in ((6.96, 0.3), (10.0, 2.0), (1.0, 5.0)):
            L, w, n = b + 2 * g, 1.0 / b, 20000
            numeric = sum(w * (g + (i + 0.5) * b / n) * (L - (g + (i + 0.5) * b / n)) * (b / n) for i in range(n)) / (2 * L)
            self.assertAlmostEqual(strength.hinge_end_moment(1.0, b, g), numeric, places=6, msg=(b, g))
        self.assertAlmostEqual(strength.hinge_end_moment(10.0, 6.0, 0.0), 10.0 * 6.0 / 12)          # g = 0: P b / 12
        self.assertAlmostEqual(strength.hinge_end_moment(10.0, 1e-9, 2.0), 10.0 * 4.0 / 8, places=6)  # b -> 0: P L / 8
        self.assertAlmostEqual(strength.hinge_mid_moment(10.0, 6.0, 0.0), 10.0 * 6.0 / 24)          # uniform: P L / 24
        self.assertAlmostEqual(strength.hinge_mid_moment(10.0, 1e-9, 2.0), 10.0 * 4.0 / 8, places=6)  # point load: P L / 8
        for b in (0.01, 0.5, 3.0, 20.0):
            for g in (0.0, 0.3, 5.0):
                self.assertGreaterEqual(strength.hinge_end_moment(1.0, b, g), strength.hinge_mid_moment(1.0, b, g) - 1e-12)
        self.assertAlmostEqual(strength.hinge_wall(7.4, 2.4, 0.3, "teardrop"), 3.7 - 1.5 * math.sqrt(2), places=9)
        self.assertAlmostEqual(strength.hinge_wall(7.4, 2.4, 0.3, "round"), 3.7 - 1.5, places=9)

    def test_sd_card_case_numbers(self):
        """Field test 2026-10: 36 mm lid hinge, five knuckles (b = 6.96), 98 N shared by two moving knuckles
        (49 N each), PLA Basic, axis flat (bending X-Y 76 MPa; shear and the knuckle wall against the Z tensile
        strength 31 MPa, the pull crosses the layers). Exact values from the formulas."""
        code, big = run("hinge", "--pin-d", "3.2", "--knuckle-d", "9.8", *self.SD)
        self.assertEqual(code, 0, big["errors"])
        c = big["checks"]
        self.assertEqual(set(c), {"pin_shear", "pin_bending", "wall_bearing", "wall_tear_out"})
        self.assertAlmostEqual(c["pin_shear"]["sf_achieved"], 4.43, places=2)
        self.assertAlmostEqual(c["pin_bending"]["sf_achieved"], 7.36, places=2)
        self.assertAlmostEqual(c["wall_bearing"]["sf_achieved"], 14.09, places=2)
        self.assertAlmostEqual(c["wall_tear_out"]["sf_achieved"], 11.3, places=2)
        self.assertEqual(big["gate"], "PASS")
        self.assertEqual(big["layout"]["knuckle_len_mm"], 6.96)
        self.assertEqual(big["layout"]["load_per_knuckle_N"], 49.0)
        self.assertEqual((big["layout"]["interior_moving"], big["layout"]["end_moving"]), (2, 0))
        self.assertAlmostEqual(big["layout"]["wall_mm"], 2.213, places=3)
        self.assertAlmostEqual(big["moments_nmm"]["interior_end_nmm"], 49 * (6 * 0.09 + 6 * 0.3 * 6.96 + 6.96 ** 2) / (12 * 7.56), places=3)
        self.assertAlmostEqual(big["moments_nmm"]["interior_mid_nmm"], 16.757, places=3)
        self.assertEqual(set(big["moments_nmm"]), {"interior_end_nmm", "interior_mid_nmm"})
        code, small = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", *self.SD)
        c = small["checks"]
        self.assertAlmostEqual(c["pin_shear"]["sf_achieved"], 2.49, places=2)
        self.assertAlmostEqual(c["pin_bending"]["sf_achieved"], 3.1, places=2)
        self.assertAlmostEqual(c["wall_bearing"]["sf_achieved"], 10.57, places=2)
        self.assertAlmostEqual(c["wall_tear_out"]["sf_achieved"], 8.06, places=2)
        self.assertEqual(small["gate"], "PASS")
        self.assertEqual(small["worst"], {"check": "pin_shear", "sf_achieved": 2.49})
        self.assertAlmostEqual(small["layout"]["wall_mm"], 1.579, places=3)
        # The stresses themselves: 4/3 x 49 / (2 x pi 2.4^2 / 4) = 7.22 MPa against 0.58 x 31 (Z); the wall against
        # 31 (bearing) and 0.58 x 31 (tear-out), the bending against 76 (X-Y).
        self.assertAlmostEqual(c["pin_shear"]["stress_mpa"], 4 / 3 * 49 / (2 * math.pi * 2.4 ** 2 / 4), places=2)
        self.assertAlmostEqual(c["pin_shear"]["strength_mpa"], 0.58 * 31, places=2)
        self.assertEqual(c["wall_bearing"]["strength_mpa"], 31)
        self.assertAlmostEqual(c["wall_tear_out"]["strength_mpa"], 0.58 * 31, places=2)
        self.assertEqual(c["pin_bending"]["strength_mpa"], 76)
        for name in ("pin_shear", "wall_bearing", "wall_tear_out"):
            self.assertIn("tensile Z", c[name]["strength_basis"], name)
        self.assertTrue(any("P = 49.0 N each" in a for a in small["assumptions"]))
        self.assertTrue(any("cross the layers" in a for a in small["assumptions"]))
        self.assertTrue(any("no --duty given" in a for a in small["assumptions"]))
        self.assertTrue(any("lid load case" in a for a in small["assumptions"]))          # no duty: the note is shown
        self.assertNotIn("minimums", small)
        # --load-across-layers changes nothing for a hinge; --orientation z moves only the bending to Z (59 MPa).
        code, flat = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--load-across-layers", *self.SD)
        self.assertEqual({k: v["sf_achieved"] for k, v in flat["checks"].items()}, {k: v["sf_achieved"] for k, v in c.items()})
        self.assertTrue(any("changes nothing" in a for a in flat["assumptions"]))
        code, up = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36", "--load", "finger_pull",
                       "--material", "pla_basic", "--orientation", "z")
        self.assertEqual(up["checks"]["pin_bending"]["strength_mpa"], 59)
        self.assertAlmostEqual(up["checks"]["pin_bending"]["sf_achieved"], 2.41, places=2)
        for name in ("pin_shear", "wall_bearing", "wall_tear_out"):
            self.assertEqual(up["checks"][name]["sf_achieved"], c[name]["sf_achieved"], name)
        # Three knuckles over the same 36 mm: one moving knuckle takes all 98 N on an 11.8 mm span.
        code, three = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "3", "--length", "36", "--load", "finger_pull",
                          "--material", "pla_basic", "--orientation", "xy")
        self.assertEqual((three["layout"]["moving_knuckles"], three["layout"]["load_per_knuckle_N"]), (1, 98.0))
        self.assertAlmostEqual(three["layout"]["knuckle_len_mm"], 11.8, places=3)
        self.assertAlmostEqual(three["checks"]["pin_bending"]["sf_achieved"], 0.97, places=2)
        self.assertAlmostEqual(three["checks"]["pin_shear"]["sf_achieved"], 1.24, places=2)
        self.assertEqual(three["gate"], "FAIL")

    def test_duty_minimums_block(self):
        code, lid = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--duty", "lid", *self.SD)
        self.assertEqual(code, 0, lid["errors"])
        m = lid["minimums"]
        self.assertEqual((m["duty"], m["state"]), ("lid", "PASS"))
        self.assertEqual(m["pin_d_mm"], {"value": 2.4, "floor": 2.0, "state": "PASS"})
        self.assertEqual(m["wall_mm"]["floor"], 1.2)
        self.assertEqual(m["knuckle_len_mm"], {"value": 6.96, "floor": 2.0, "state": "PASS"})
        self.assertEqual(m["knuckles"], {"value": 5, "floor": 3, "state": "PASS"})
        self.assertEqual(lid["gate"], "PASS")
        self.assertIn("coupon", lid["next_step"])
        self.assertIn("on top of the margin", lid["next_step"])
        self.assertIn("tolerances.md", m["source"])
        self.assertTrue(any("lid load case" in a for a in lid["assumptions"]))
        # Lid at WARN: a 2.0 mm pin in a 7.0 mm knuckle (wall 1.66, prints) reads 1.73 in shear: grow it; the coupon
        # is on top, never instead.
        code, warn = run("hinge", "--pin-d", "2.0", "--knuckle-d", "7.0", "--duty", "lid", *self.SD)
        self.assertEqual(warn["gate"], "WARN")
        self.assertAlmostEqual(warn["checks"]["pin_shear"]["sf_achieved"], 1.73, places=2)
        self.assertEqual(warn["minimums"]["state"], "PASS")
        self.assertIn("lid duty needs SF >= 2", warn["next_step"])
        self.assertIn("grow the pin or knuckle diameter or add knuckles (odd)", warn["next_step"])
        self.assertIn("does not replace the margin", warn["next_step"])
        # Lid: --sf under 2 is refused; an even count gets a note; fewer than 3 knuckles fails the floor.
        code, out = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--duty", "lid", "--sf", "1.5", *self.SD)
        self.assertEqual(code, 1)
        self.assertIn("duty lid needs --sf of at least 2", out["errors"][0])
        code, four = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "4", "--length", "36", "--duty", "lid",
                         "--load", "finger_pull", "--material", "pla_basic", "--orientation", "xy")
        self.assertEqual(four["minimums"]["knuckles"]["state"], "PASS")
        self.assertIn("odd count", four["minimums"]["knuckles"]["note"])
        code, two = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "2", "--knuckle-len", "7", "--duty", "lid",
                        "--load", "finger_pull", "--material", "pla_basic", "--orientation", "xy")
        self.assertEqual(two["minimums"]["knuckles"], {"value": 2, "floor": 3, "state": "FAIL", "note": two["minimums"]["knuckles"]["note"]})
        self.assertEqual(two["gate"], "FAIL")
        self.assertIn("needs 3 or more knuckles", two["next_step"])
        # Latch duty: the floors are the rule.
        code, latch = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--duty", "latch", *self.SD)
        m = latch["minimums"]
        self.assertEqual(m["state"], "FAIL")
        self.assertEqual(m["pin_d_mm"], {"value": 2.4, "floor": 3.2, "state": "FAIL"})
        self.assertEqual(m["wall_mm"]["state"], "FAIL")
        self.assertEqual(m["knuckle_len_mm"]["state"], "PASS")
        self.assertNotIn("knuckles", m)                                          # no count floor for a latch
        self.assertEqual(latch["gate"], "FAIL")                                   # the floors are the rule for a latch
        self.assertIn("pin_d_mm, wall_mm", latch["next_step"])
        self.assertEqual(latch["worst"]["check"], "pin_shear")                    # the calculation itself still passes
        self.assertFalse(any("lid load case" in a for a in latch["assumptions"]))
        code, ok = run("hinge", "--pin-d", "3.2", "--knuckle-d", "9.8", "--duty", "latch", *self.SD)
        self.assertEqual((ok["minimums"]["state"], ok["gate"]), ("PASS", "PASS"))
        # Decorative: the floors alone decide the gate, the checks are informational.
        code, deco = run("hinge", "--pin-d", "2.0", "--knuckle-d", "7.0", "--duty", "decorative", *self.SD)
        self.assertEqual(deco["minimums"]["state"], "PASS")
        self.assertEqual(deco["gate"], "PASS")                                    # shear reads 1.73, informational
        self.assertTrue(all(c["informational"] is True for c in deco["checks"].values()))
        self.assertIn("decorative: the floors decide", deco["next_step"])
        self.assertTrue(any("carries nothing" in a for a in deco["assumptions"]))
        self.assertFalse(any("lid load case" in a for a in deco["assumptions"]))
        code, out = run("duties")
        self.assertEqual(code, 0)
        self.assertEqual(set(out["duties"]), {"latch", "lid", "decorative"})
        self.assertEqual(out["duties"]["latch"]["floors"], {"pin_d": 3.2, "pin_wall": 2.2, "member": 2.5, "knuckle_len": 4.0})
        self.assertEqual(out["duties"]["lid"]["floors"], {"pin_d": 2.0, "pin_wall": 1.2, "member": 1.2, "knuckle_len": 2.0})
        self.assertEqual(out["duties"]["lid"]["floors"], out["duties"]["decorative"]["floors"])
        self.assertEqual(out["duties"]["lid"]["min_knuckles"], 3)
        self.assertNotIn("min_knuckles", out["duties"]["latch"])
        self.assertNotIn("min_knuckles", out["duties"]["decorative"])

    def test_end_knuckle_and_loose_pin(self):
        # Four knuckles: A B A B, the last B hangs on the pin's free end as a stub, M = P (g + b / 2).
        code, even = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "4", "--length", "36", "--load", "finger_pull",
                         "--material", "pla_basic", "--orientation", "xy")
        self.assertEqual(code, 0, even["errors"])
        b = (36 - 3 * 0.3) / 4
        self.assertEqual((even["layout"]["interior_moving"], even["layout"]["end_moving"]), (1, 1))
        self.assertAlmostEqual(even["layout"]["knuckle_len_mm"], b, places=3)
        self.assertAlmostEqual(even["moments_nmm"]["end_nmm"], 49 * (0.3 + b / 2), places=3)
        self.assertEqual(set(even["moments_nmm"]), {"interior_end_nmm", "interior_mid_nmm", "end_nmm"})
        self.assertAlmostEqual(even["checks"]["pin_bending_end"]["stress_mpa"], 32 * 49 * (0.3 + b / 2) / (math.pi * 2.4 ** 3), places=2)
        self.assertAlmostEqual(even["checks"]["pin_shear_end"]["stress_mpa"], 2 * even["checks"]["pin_shear"]["stress_mpa"], places=2)
        self.assertAlmostEqual(even["checks"]["pin_bending_end"]["sf_achieved"], 0.45, places=2)   # materials.md
        self.assertAlmostEqual(even["checks"]["pin_shear_end"]["sf_achieved"], 1.24, places=2)
        self.assertEqual(even["checks"]["pin_bending_end"]["state"], "FAIL")
        self.assertEqual(even["gate"], "FAIL")
        self.assertTrue(any("odd count" in a and "optimistic for the interior" in a for a in even["assumptions"]))
        # Loose pin: an interior B is the clevis of the pin case with a = b; the A knuckles bear the pin too,
        # P / 2 from an interior B neighbour and, from an end B, the overhang's statics 1.5 P (A B A B: the last A
        # takes 2 P = 98 N in all).
        code, loose = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "4", "--length", "36", "--pin", "loose",
                          "--load", "finger_pull", "--material", "pla_basic", "--orientation", "xy")
        M = 49 * (b + 2 * b + 4 * 0.3) / 8
        self.assertAlmostEqual(loose["checks"]["pin_bending"]["stress_mpa"], 32 * M / (math.pi * 2.4 ** 3), places=2)
        self.assertIn("(b + 2 a + 4 g) / 8", loose["checks"]["pin_bending"]["formula"])
        self.assertEqual(set(loose["moments_nmm"]), {"interior_nmm", "end_nmm"})
        self.assertEqual(loose["layout"]["fixed_knuckle_load_N"], 98.0)
        self.assertAlmostEqual(loose["checks"]["wall_bearing_fixed"]["stress_mpa"], 98.0 / (2.4 * b), places=2)
        self.assertAlmostEqual(loose["checks"]["wall_bearing_fixed"]["sf_achieved"], 6.66, places=2)
        self.assertAlmostEqual(loose["checks"]["wall_tear_out_fixed"]["sf_achieved"], 5.08, places=2)
        self.assertEqual(loose["checks"]["wall_bearing_fixed"]["strength_mpa"], 31)
        self.assertTrue(any("1.5 P" in a for a in loose["assumptions"]))
        # The same five-knuckle hinges with a loose pin, the numbers materials.md quotes.
        code, odd = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--pin", "loose", *self.SD)
        self.assertEqual(odd["layout"]["fixed_knuckle_load_N"], 49.0)             # A B A B A: the middle A takes P
        self.assertNotIn("pin_bending_end", odd["checks"])
        self.assertAlmostEqual(odd["checks"]["pin_bending"]["sf_achieved"], 0.76, places=2)
        self.assertEqual(odd["checks"]["pin_bending"]["state"], "FAIL")
        code, odd32 = run("hinge", "--pin-d", "3.2", "--knuckle-d", "9.8", "--pin", "loose", *self.SD)
        self.assertAlmostEqual(odd32["checks"]["pin_bending"]["sf_achieved"], 1.81, places=2)
        self.assertEqual(odd32["checks"]["pin_bending"]["state"], "WARN")
        code, clevis = run("pin", "--d", "3.2", "--engagement", "6.96", "--support-t", "6.96", "--gap", "0.3", "--shear", "double",
                           "--support", "through", "--load", "finger_pull", "--material", "pla_basic", "--orientation", "xy")
        self.assertAlmostEqual(clevis["checks"]["bending"]["sf_achieved"], 0.9, places=2)    # the whole load on one span
        # Two knuckles: one moving knuckle on a stub, the whole load, the single A takes P.
        code, two = run("hinge", "--pin-d", "3.2", "--knuckle-d", "9.8", "--knuckles", "2", "--knuckle-len", "8", "--pin", "loose",
                        "--load", "50", "--material", "pla_basic", "--orientation", "xy")
        self.assertEqual(set(two["checks"]), {"pin_shear_end", "pin_bending_end", "wall_bearing", "wall_tear_out",
                                              "wall_bearing_fixed", "wall_tear_out_fixed"})
        self.assertEqual(two["layout"]["load_per_knuckle_N"], 50.0)
        self.assertEqual(two["layout"]["fixed_knuckle_load_N"], 50.0)
        self.assertEqual(set(two["moments_nmm"]), {"end_nmm"})
        self.assertAlmostEqual(two["moments_nmm"]["end_nmm"], 50 * (0.3 + 4), places=3)
        # A round hole's wall is measured above the circle.
        code, rnd = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--hole", "round", *self.SD)
        self.assertAlmostEqual(rnd["layout"]["wall_mm"], 3.7 - 1.5, places=3)
        self.assertEqual(rnd["inputs"]["hole"], "round")

    def test_usage_errors(self):
        base = ["--load", "finger_pull", "--material", "pla_basic", "--orientation", "xy"]
        for argv, word in ((["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5"], "exactly one of --length"),
                           (["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36", "--knuckle-len", "7"], "exactly one"),
                           (["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "1", "--length", "36"], "at least 2"),
                           (["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "2.5", "--length", "36"], "invalid int"),
                           (["--pin-d", "2.4", "--knuckle-d", "4.0", "--knuckles", "5", "--length", "36"], "no wall"),
                           (["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "1"], "no knuckle length"),
                           (["--pin-d", "-2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36"], "--pin-d"),
                           (["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36", "--clearance", "-1"], "--clearance"),
                           (["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36", "--duty", "lever"], "invalid choice"),
                           (["--knuckle-d", "7.4", "--knuckles", "5", "--length", "36"], "--pin-d is required")):
            code, out = run("hinge", *argv, *base)
            self.assertEqual(code, 1, argv)
            self.assertFalse(out["ran"])
            self.assertIn(word, out["errors"][0], (argv, out["errors"]))
        code, out = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36")
        self.assertIn("--load and --material", out["errors"][0])
        # Hinge-only flags given to another case are an error, not silently ignored.
        for case, argv, names in (("pin", ["--d", "3", "--engagement", "4", "--duty", "lid"], "--duty"),
                                  ("beam", ["--b", "3", "--h", "4", "--length", "10", "--pin-d", "3", "--hole", "round"], "--pin-d, --hole"),
                                  ("link", ["--b", "3", "--h", "4", "--clearance", "0.3"], "--clearance"),
                                  ("bearing", ["--d", "3", "--t", "4", "--edge", "2", "--pin", "loose", "--knuckles", "3"], "--knuckles, --pin")):
            code, out = run(case, *argv, "--load", "50", "--material", "abs")
            self.assertEqual(code, 1, case)
            self.assertIn(f"{names} belong to the hinge case only (this is case {case})", out["errors"][0])

    def test_json_shape(self):
        code, out = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--duty", "lid", *self.SD)
        self.assertEqual(out["schema"], strength.SCHEMA)
        self.assertTrue(out["ran"])
        for key in ("case", "inputs", "load_N", "material", "orientation", "checks", "gate", "worst", "next_step",
                    "assumptions", "layout", "moments_nmm", "minimums"):
            self.assertIn(key, out, key)
        self.assertEqual(out["case"], "hinge")
        self.assertEqual(out["load_N"], 98.0)
        self.assertEqual(out["inputs"], {"load": "finger_pull", "material": "pla_basic", "orientation": "xy", "sf": 2.0, "gap": 0.3,
                                         "length": 36.0, "pin_d": 2.4, "knuckle_d": 7.4, "knuckles": 5, "clearance": 0.3,
                                         "hole": "teardrop", "pin": "integral", "duty": "lid"})
        for c in out["checks"].values():
            self.assertEqual(set(c), {"state", "stress_mpa", "strength_mpa", "sf_achieved", "sf_required", "formula", "strength_basis"})
        self.assertEqual(set(out["layout"]), {"knuckles", "moving_knuckles", "fixed_knuckles", "interior_moving", "end_moving",
                                              "knuckle_len_mm", "fixed_knuckle_len_mm", "gap_mm", "clearance_mm", "hole", "hole_d_mm",
                                              "wall_mm", "span_mm", "pin", "load_per_knuckle_N", "fixed_knuckle_load_N"})
        self.assertTrue(any("finger_pull" in a and "98.0 N" in a for a in out["assumptions"]))
        # Defaults: gap and clearance 0.3, a teardrop hole and an integral pin when not given (the effective values are
        # reported); the pin case keeps gap 0.
        code, d = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36", "--load", "50", "--material", "abs")
        self.assertEqual((d["inputs"]["gap"], d["inputs"]["clearance"], d["inputs"]["hole"], d["inputs"]["pin"], d["orientation"]),
                         (0.3, 0.3, "teardrop", "integral", "z"))
        code, p = run("pin", "--d", "4", "--engagement", "3", "--load", "50", "--material", "abs")
        self.assertEqual(p["inputs"]["gap"], 0.0)
        self.assertTrue(any("no --gap given" in n for n in p["assumptions"]))

    def test_parts_and_docs_share_the_duty_table(self):
        """One copy of the floors: parts.py imports strength.DUTIES, and design.md / SKILL.md quote the
        latch numbers."""
        with open(os.path.join(HERE, "..", "references", "design.md"), encoding="utf-8") as f:
            design = f.read()
        with open(os.path.join(HERE, "..", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        with open(os.path.join(HERE, "..", "references", "phase-4-features-joints.md"), encoding="utf-8") as f:
            phase4 = f.read()
        fl, lid = strength.DUTIES["latch"]["floors"], strength.DUTIES["lid"]["floors"]
        latch_line = f"pin ≥ {fl['pin_d']}, pin wall ≥ {fl['pin_wall']}, member ≥ {fl['member']} mm thick and ≥ 4 mm wide, knuckle ≥ {fl['knuckle_len']:.0f} mm"
        self.assertIn(latch_line, skill)                                                           # the P7 row
        self.assertIn(latch_line.replace(" mm thick", " thick").replace("≥ 4 mm wide", "≥ 4 wide").replace("knuckle ≥ 4 mm", "knuckle ≥ 4 long"), phase4)
        for piece in (f"Ø ≥ {fl['pin_d']} mm", f"≥ {fl['pin_wall']} mm", f"≥ {fl['member']} mm in the bending direction", f"≥ {fl['knuckle_len']:.0f} mm long"):
            self.assertIn(piece, design, piece)
        lid_line = f"pin {lid['pin_d']:.1f}, wall and leaf {lid['pin_wall']:.1f}, knuckle {lid['knuckle_len']:.0f} mm"
        for text in (design, phase4):
            self.assertIn(lid_line, text)
        with open(os.path.join(HERE, "..", "scripts", "parts.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn('spec_from_file_location(name, os.path.join(_HERE, "strength.py"))', text)   # by path, private name
        self.assertNotIn("from strength import", text)
        self.assertNotIn("sys.path.insert", text)
        self.assertIn("3 or more required, odd recommended", design + phase4)                      # S6 wording
        self.assertIn("don't force the lid past fully open", design)
        with open(os.path.join(HERE, "..", "references", "phase-6-deliver.md"), encoding="utf-8") as f:
            self.assertIn("don't force the lid past fully open", f.read())


class FieldComparison(unittest.TestCase):
    """The two latches of design.md ("Mechanisms that carry load") under the same finger-push
    design load, 70.6 N, with the load share stated: the failed latch has two curved arms and
    two stub pins, one each side, so each arm, pin and pin wall takes 35.3 N; its bar is run
    both ways, as a 12 mm cantilever with the full load (the worst case) and as a span between
    the two arms with the load at its centre. The arm's 2.5 mm bow and the bar's 12 mm length
    come from the generator that made the failed latch. Print-in-place gaps at the pin roots
    are taken as the radial clearances (0.42 and 0.33 mm). The lever ratio of either latch was
    not measured, so the hand force is applied as is (1:1); at a ratio of 2 the failed stub pin
    reads WARN, at 3 FAIL. Failed latch material: PLA Pure (confirmed by the owner).

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
