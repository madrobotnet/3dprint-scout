"""Tests for scripts/strength.py: formulas, verdicts, the data tables, and the field comparison
of 2026-10 (a failed and a working print-in-place latch) run through the same load."""
import io
import json
import math
import os
import sys
import tempfile
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
        # And the other cases' flags given to the hinge are an error too (shared: --length, --gap, --load-across-layers).
        for argv, names in ((["--support", "stub", "--shear", "single", "--b", "999", "--engagement", "999"],
                             "--engagement, --shear, --support, --b"),
                            (["--bow", "0"], "--bow"),
                            (["--d", "3", "--support-t", "2", "--h", "1", "--t", "2", "--edge", "1"],
                             "--d, --support-t, --h, --t, --edge")):
            code, out = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", *argv, *self.SD)
            self.assertEqual(code, 1, argv)
            self.assertIn(f"{names} do not apply to the hinge case", out["errors"][0])
        code, out = run("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--gap", "0.3", "--load-across-layers", *self.SD)
        self.assertEqual(out["gate"], "PASS", out["errors"])

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


class Snap(unittest.TestCase):
    """S2-F02 / F07: the snap case uses parts.snap_fit_check's formula and limits; its load is
    the arm's own deflection force, and the release force bounds what a hand can do."""

    def test_matches_parts_snap_fit_check(self):
        code, out = run("snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--material", "pla_basic",
                        "--orientation", "xy")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual((out["case"], out["gate"]), ("snap", "PASS"))
        snap = out["snap"]
        self.assertAlmostEqual(snap["strain"], 1.5 * 1.6 * 0.8 / 16 ** 2, places=5)                # e = 1.5 h y / L^2
        self.assertEqual((snap["limit"], snap["family"], snap["repeated"]), (0.01, "PLA", False))
        self.assertAlmostEqual(snap["max_deflection_mm"], 0.01 * 16 ** 2 / (1.5 * 1.6), places=3)
        self.assertEqual(out["checks"]["strain"]["state"], "PASS")
        self.assertEqual(out["checks"]["strain"]["sf_required"], 1.0)                              # the limit carries the margin
        try:
            import parts                                                                            # needs manifold3d
        except ImportError:
            parts = None
        if parts is not None:
            ref = parts.snap_fit_check(16, 1.6, 0.8, "PLA")
            self.assertEqual((snap["strain"], snap["limit"], snap["max_deflection_mm"]),
                             (ref["strain"], ref["limit"], ref["max_deflection_mm"]))
            self.assertEqual(dict(parts.SNAP_STRAIN), strength.SNAP_STRAIN)                        # one table
            rep = parts.snap_fit_check(16, 1.6, 0.8, "PLA", repeated=True)
            code, r = run("snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--material", "pla_basic", "--repeated")
            self.assertEqual((r["snap"]["limit"], r["snap"]["repeated"]), (rep["limit"], True))
        # The load is the deflection force P = 3 E I y / L^3 with the XY bending modulus; the bending
        # stress at the root is E e; both ramps follow the BASF mating-force formula.
        E, I = 2750, 6 * 1.6 ** 3 / 12
        P = 3 * E * I * 0.8 / 16 ** 3
        self.assertAlmostEqual(out["load_N"], P, places=2)
        self.assertAlmostEqual(snap["deflection_force_N"], P, places=2)
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], E * snap["strain"], delta=0.02)
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 6 * P * 16 / (6 * 1.6 ** 2), delta=0.02)
        t = math.tan(math.radians(30))
        self.assertAlmostEqual(snap["insertion_force_N"], P * (0.3 + t) / (1 - 0.3 * t), places=2)
        self.assertIsNone(snap["release_force_N"])                                                 # 90 deg: a release window
        self.assertTrue(any("own deflection force" in a for a in out["assumptions"]))
        self.assertTrue(any("release window" in a for a in out["assumptions"]))
        self.assertEqual(out["inputs"]["entry_angle"], 30.0)
        self.assertNotIn("load", out["inputs"])
        code, r = run("snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--material", "pla_basic",
                      "--retention-angle", "45", "--friction", "0.2", "--q", "2")
        t = math.tan(math.radians(45))
        self.assertAlmostEqual(r["snap"]["release_force_N"], r["load_N"] * (0.2 + t) / (1 - 0.2 * t), places=2)
        self.assertAlmostEqual(r["snap"]["strain"], 1.5 * 1.6 * 0.8 / (16 ** 2 * 2), places=5)      # Q halves the strain
        self.assertEqual(r["orientation"], "z")                                                     # the conservative default
        self.assertTrue(any("pass --orientation xy" in a for a in r["assumptions"]))

    def test_over_the_limit_fails_and_says_lengthen(self):
        code, out = run("snap", "--length", "10", "--h", "2.0", "--b", "6", "--undercut", "1.0", "--material", "pla_basic",
                        "--orientation", "xy")
        self.assertEqual(out["gate"], "FAIL")
        self.assertEqual(out["checks"]["strain"]["state"], "FAIL")                                 # 3 % against 1 %
        self.assertIn("lengthen", out["next_step"])
        self.assertIn("never thicken", out["next_step"])
        self.assertTrue(any("is over it" in a for a in out["assumptions"]))

    def test_usage(self):
        code, out = run("snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--material", "pla_basic",
                        "--load", "finger_pull")
        self.assertEqual(code, 1)
        self.assertIn("own deflection force", out["errors"][0])                                     # no hand-force key
        code, out = run("snap", "--length", "16", "--h", "1.6", "--b", "6", "--material", "pla_basic")
        self.assertEqual(code, 1)
        self.assertIn("--undercut", out["errors"][0])
        code, out = run("beam", "--b", "6", "--h", "3", "--length", "20", "--load", "70", "--material", "petg_basic", "--undercut", "1")
        self.assertEqual(code, 1)
        self.assertIn("snap case only", out["errors"][0])
        code, out = run("snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8")
        self.assertEqual(code, 1)
        self.assertIn("--material", out["errors"][0])


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


class FromBuild(unittest.TestCase):
    """--from-build, --part, --param and the report's inputs_from / from_build (contract 2 of
    0.7.0 step 4). The build JSONs are synthetic, in the shape build.py writes: top-level
    "parameters" {"scope", "values"}, parts with name, sha256 and material."""

    SHA = "ab" * 32
    VALUES = {"ribbon_t": 3, "ribbon_w": 6, "arm": 20.0, "plug": {"w": 13.0, "t": 2.5}, "dir": "xy", "pin": 2.4,
              "knuckle": 7.4, "count": 5, "hinge_len": 36, "gap": 0.3, "zero": 0, "often": False, "across": True,
              "pull": "finger_pull", "force": 70}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def build(self, values=None, scope="merged", parts=None, schema="3dprint-scout.build/1", name="build.json",
              parameters=True):
        doc = {"schema": schema, "params": "params.json",
               "parts": parts if parts is not None else
               [{"name": "sled", "stl": "out/sled.stl", "sha256": self.SHA, "material": "petg_basic"},
                {"name": "lid", "stl": "out/lid.stl", "sha256": "cd" * 32, "material": "pla_basic"}]}
        if parameters:
            doc["parameters"] = {"scope": scope, "values": self.VALUES if values is None else values}
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)                                   # allow_nan: a NaN in a build reaches the check
        return path

    def ok(self, *argv):
        code, out = run(*argv)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(set(out["inputs_from"]), set(out["inputs"]))
        return out

    def err(self, *argv):
        code, out = run(*argv)
        self.assertEqual(code, 1, argv)
        self.assertFalse(out["ran"])
        self.assertEqual(len(out["errors"]), 1, out["errors"])
        self.assertNotIn("inputs_from", out)
        return out["errors"][0]

    # ------------------------------------------------------------------ linked values
    def test_linked_inputs_drive_the_calculation(self):
        b = self.build()
        linked = self.ok("beam", "--from-build", b, "--part", "sled", "--param", "h=ribbon_t", "--param", "b=ribbon_w",
                         "--length", "20", "--load", "70", "--orientation", "xy")
        typed = self.ok("beam", "--h", "3", "--b", "6", "--length", "20", "--load", "70", "--material", "petg_basic",
                        "--orientation", "xy")
        self.assertEqual(linked["checks"], typed["checks"])                       # 70 x 20 x 1.5 / 13.5 = 155.56 MPa
        self.assertAlmostEqual(linked["checks"]["bending"]["stress_mpa"], 155.56, places=2)
        self.assertEqual(linked["inputs"], typed["inputs"])                       # 3 -> 3.0, as --h 3 gives it
        self.assertEqual(linked["material"]["key"], "petg_basic")                 # the build's part
        for key in ("deflection_mm", "moment_nmm", "I_mm4", "gate", "worst", "next_step", "assumptions"):
            self.assertEqual(linked[key], typed[key], key)
        # The build's number replaces the command line's: another value in the build gives another stress.
        b4 = self.build(values=dict(self.VALUES, ribbon_t=4), name="b4.json")
        four = self.ok("beam", "--from-build", b4, "--part", "sled", "--param", "h=ribbon_t", "--param", "b=ribbon_w",
                       "--length", "20", "--load", "70", "--orientation", "xy")
        self.assertAlmostEqual(four["checks"]["bending"]["stress_mpa"], 1400 * 2 / (6 * 64 / 12), places=2)
        self.assertEqual(four["from_build"]["parameters"]["h"], {"param": "ribbon_t", "value": 4})
        # A hinge from its build: the SD-card case numbers of the Hinge tests.
        lid = self.ok("hinge", "--from-build", b, "--part", "lid", "--param", "pin_d=pin", "--param", "knuckle_d=knuckle",
                      "--param", "knuckles=count", "--param", "length=hinge_len", "--param", "gap=gap",
                      "--param", "orientation=dir", "--param", "load=pull", "--clearance", "0.3", "--duty", "lid")
        self.assertAlmostEqual(lid["checks"]["pin_shear"]["sf_achieved"], 2.49, places=2)
        self.assertAlmostEqual(lid["checks"]["pin_bending"]["sf_achieved"], 3.1, places=2)
        self.assertEqual(lid["load_N"], 98.0)
        self.assertEqual(lid["inputs"]["knuckles"], 5)
        self.assertEqual(lid["inputs_from"]["load"], "param:pull")               # a linked load key is a param, not table
        self.assertEqual(lid["from_build"]["material"], "pla_basic")
        # A linked number load is used as a force in N.
        force = self.ok("beam", "--from-build", b, "--part", "sled", "--param", "load=force", "--h", "3", "--b", "6",
                        "--length", "20", "--orientation", "xy")
        self.assertEqual(force["load_N"], 70.0)
        self.assertEqual(force["checks"], typed["checks"])

    def test_dotted_params(self):
        b = self.build()
        out = self.ok("link", "--from-build", b, "--part", "sled", "--param", "b=plug.w", "--param", "h=plug.t",
                      "--load", "40", "--orientation", "xy")
        self.assertAlmostEqual(out["checks"]["tension"]["stress_mpa"], round(40 / (13 * 2.5), 2))
        self.assertEqual(out["inputs_from"]["b"], "param:plug.w")
        self.assertEqual(out["from_build"]["parameters"]["b"], {"param": "plug.w", "value": 13.0})
        # A key that has a dot in it is taken as it is before the path (finalize.lookup's rule).
        b2 = self.build(values={"plug.w": 5, "plug": {"w": 13.0}}, name="dot.json")
        out = self.ok("link", "--from-build", b2, "--part", "sled", "--param", "b=plug.w", "--h", "2", "--load", "40")
        self.assertEqual(out["inputs"]["b"], 5.0)
        self.assertEqual(strength.param_value({"plug": {"w": 13}}, "plug.w"), (True, 13))
        self.assertEqual(strength.param_value({"plug": {"w": 13}}, "plug.t"), (False, None))
        self.assertEqual(strength.param_value({"plug": 13}, "plug.w"), (False, None))     # not an object
        self.assertEqual(strength.param_value({"plug": {"w": 13}}, "plug"), (True, {"w": 13}))
        # A path to an object is not a number.
        self.assertIn("takes a finite number", self.err("link", "--from-build", b, "--part", "sled", "--param", "b=plug",
                                                        "--h", "2", "--load", "40"))

    # ------------------------------------------------------------------ origins
    def test_inputs_from_every_origin(self):
        b = self.build()
        out = self.ok("pin", "--from-build", b, "--part", "sled", "--param", "d=pin", "--engagement", "4",
                      "--load", "finger_push")
        self.assertEqual(out["inputs_from"], {"load": "table:finger_push", "material": "build:material",
                                              "orientation": "default:orientation", "sf": "default:sf",
                                              "d": "param:pin", "engagement": "manual", "gap": "default:gap",
                                              "shear": "default:shear", "support": "default:support"})
        self.assertEqual(out["inputs"]["orientation"], "z")
        self.assertEqual(out["from_build"], {"build": b, "part": "sled", "sha256": self.SHA, "material": "petg_basic",
                                             "parameters": {"d": {"param": "pin", "value": 2.4}}})
        # Without a build: a material key is table:<key> (normalised), a number load and every typed value manual,
        # even one equal to its default (--sf 2, --gap 0); no from_build.
        out = self.ok("pin", "--d", "3", "--engagement", "4", "--gap", "0", "--sf", "2", "--load", "70",
                      "--material", "PLA-Basic", "--orientation", "z")
        self.assertEqual(out["inputs_from"], {"load": "manual", "material": "table:pla_basic", "orientation": "manual",
                                              "sf": "manual", "d": "manual", "engagement": "manual", "gap": "manual",
                                              "shear": "default:shear", "support": "default:support"})
        self.assertNotIn("from_build", out)
        out = self.ok("pin", "--d", "3", "--engagement", "4", "--load", " Finger_Pull ", "--material", "abs",
                      "--shear", "double", "--support", "stub", "--load-across-layers")
        self.assertEqual(out["inputs_from"]["load"], "table:finger_pull")
        self.assertEqual((out["inputs_from"]["shear"], out["inputs_from"]["support"]), ("manual", "manual"))
        self.assertEqual(out["inputs_from"]["load_across_layers"], "manual")
        # The defaults strength.py fills per case.
        link = self.ok("link", "--b", "2", "--h", "2", "--load", "10", "--material", "abs")
        self.assertEqual(link["inputs_from"]["bow"], "default:bow")
        beam = self.ok("beam", "--b", "2", "--h", "2", "--length", "5", "--load", "10", "--material", "abs")
        self.assertEqual(beam["inputs_from"]["support"], "default:support")
        hinge = self.ok("hinge", "--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5", "--length", "36",
                        "--load", "finger_pull", "--material", "pla_basic", "--duty", "lid")
        self.assertEqual({k: hinge["inputs_from"][k] for k in ("gap", "clearance", "hole", "pin", "knuckles", "duty")},
                         {"gap": "default:gap", "clearance": "default:clearance", "hole": "default:hole",
                          "pin": "default:pin", "knuckles": "manual", "duty": "manual"})
        snap = self.ok("snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--material", "pla_basic",
                       "--friction", "0.2", "--repeated")
        self.assertEqual({k: snap["inputs_from"][k] for k in ("q", "entry_angle", "retention_angle", "friction", "repeated",
                                                              "material")},
                         {"q": "default:q", "entry_angle": "default:entry_angle",
                          "retention_angle": "default:retention_angle", "friction": "manual", "repeated": "manual",
                          "material": "table:pla_basic"})
        self.assertNotIn("load", snap["inputs_from"])
        # The tables carry no inputs and no origins.
        for case in ("materials", "loads", "duties"):
            self.assertNotIn("inputs_from", run(case)[1])

    def test_linked_flags_and_choices(self):
        b = self.build()
        # A linked flag that is false stays in the inputs, so its origin is recorded; true acts as the option.
        snap = self.ok("snap", "--from-build", b, "--part", "lid", "--param", "repeated=often", "--length", "16",
                       "--h", "1.6", "--b", "6", "--undercut", "0.8")
        self.assertEqual((snap["inputs"]["repeated"], snap["inputs_from"]["repeated"]), (False, "param:often"))
        self.assertEqual(snap["snap"]["limit"], 0.01)
        pin = self.ok("pin", "--from-build", b, "--part", "sled", "--param", "load_across_layers=across",
                      "--param", "orientation=dir", "--d", "4", "--engagement", "3", "--shear", "double", "--support", "stub",
                      "--load", "100")
        self.assertAlmostEqual(pin["checks"]["shear"]["strength_mpa"], 0.58 * 35, places=2)   # Z, as --load-across-layers
        self.assertEqual(pin["inputs_from"]["load_across_layers"], "param:across")
        self.assertFalse(any("conservative default" in a for a in pin["assumptions"]))          # orientation linked
        # A support linked by name, checked against the case's own choices.
        sup = self.build(values={"s": "simple"}, name="sup.json")
        beam = self.ok("beam", "--from-build", sup, "--part", "sled", "--param", "support=s", "--b", "6", "--h", "3",
                       "--length", "20", "--load", "60", "--orientation", "xy")
        self.assertAlmostEqual(beam["checks"]["bending"]["stress_mpa"], 133.33 / 4, places=2)
        self.assertIn("takes one of through, stub", self.err("pin", "--from-build", sup, "--part", "sled", "--param",
                                                             "support=s", "--d", "3", "--engagement", "4", "--load", "10"))

    def test_input_kinds_cover_every_input(self):
        every = set().union(*(strength.linkable_inputs(c) for c in strength.CASE_INPUTS))
        self.assertEqual(set(strength.INPUT_KIND), every)
        self.assertNotIn("material", every)
        self.assertNotIn("load", strength.linkable_inputs("snap"))
        self.assertEqual(set(strength.CHOICES["duty"]), set(strength.DUTIES))

    # ------------------------------------------------------------------ errors
    def test_build_and_part_errors(self):
        b = self.build()
        beam = ["--b", "6", "--h", "3", "--length", "20", "--load", "70"]
        self.assertIn("no such file", self.err("beam", "--from-build", os.path.join(self.dir, "nope.json"), "--part", "sled", *beam))
        wrong = self.build(schema="3dprint-scout.fit/1", name="fit.json")
        self.assertIn("not a build.py report (schema 3dprint-scout.build/1", self.err("beam", "--from-build", wrong, "--part", "sled", *beam))
        for text, name in (("[1, 2]", "list.json"), ("{not json", "broken.json")):
            path = os.path.join(self.dir, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.assertIn(f"--from-build {path}", self.err("beam", "--from-build", path, "--part", "sled", *beam))
        self.assertIn("part 'bracket' is not in", self.err("beam", "--from-build", b, "--part", "bracket", *beam))
        self.assertIn("its parts: sled, lid", self.err("beam", "--from-build", b, "--part", "bracket", *beam))
        for part in ({"name": "sled", "material": "pla_basic"}, {"name": "sled", "sha256": None, "material": "pla_basic"}):
            nosha = self.build(parts=[part], name="nosha.json")
            self.assertIn("part 'sled' in", self.err("beam", "--from-build", nosha, "--part", "sled", *beam))
            self.assertIn("has no sha256", self.err("beam", "--from-build", nosha, "--part", "sled", *beam))
        for part in ({"name": "sled", "sha256": self.SHA, "material": None}, {"name": "sled", "sha256": self.SHA}):
            nomat = self.build(parts=[part], name="nomat.json")
            self.assertEqual(self.err("beam", "--from-build", nomat, "--part", "sled", *beam),
                             "no material recorded for sled: set _material or _parts.sled.material and build again")
        odd = self.build(parts=[{"name": "sled", "sha256": self.SHA, "material": "PLA Basic"}], name="odd.json")
        self.assertIn("not a strength.py material key", self.err("beam", "--from-build", odd, "--part", "sled", *beam))
        self.assertIn("--material does not go with --from-build",
                      self.err("beam", "--from-build", b, "--part", "sled", "--material", "petg_basic", *beam))
        self.assertIn("--from-build needs --part", self.err("beam", "--from-build", b, *beam))
        self.assertIn("need --from-build", self.err("beam", "--part", "sled", "--material", "abs", *beam))
        self.assertIn("need --from-build", self.err("beam", "--param", "h=ribbon_t", "--material", "abs", "--b", "6",
                                                    "--length", "20", "--load", "70"))
        self.assertIn("not to materials", self.err("materials", "--from-build", b, "--part", "sled"))
        # A build with no parameters still gives the part and its material; linking needs the parameters.
        old = self.build(parameters=False, name="old.json")
        out = self.ok("beam", "--from-build", old, "--part", "sled", *beam)
        self.assertEqual(out["from_build"]["parameters"], {})
        self.assertIn("records no parameters", self.err("beam", "--from-build", old, "--part", "sled", "--param",
                                                        "h=ribbon_t", "--b", "6", "--length", "20", "--load", "70"))

    def test_link_errors(self):
        b = self.build()
        base = ["--from-build", b, "--part", "sled", "--length", "20", "--load", "70"]
        self.assertIn("h is given twice, as --h and as --param h=ribbon_t",
                      self.err("beam", *base, "--h", "3", "--param", "h=ribbon_t", "--b", "6"))
        self.assertIn("load is given twice", self.err("beam", *base, "--param", "load=force", "--h", "3", "--b", "6"))
        self.assertIn("h is linked twice", self.err("beam", *base, "--param", "h=ribbon_t", "--param", "h=arm", "--b", "6"))
        for bad, word in (("foo=ribbon_t", "'foo' is not an input of the beam case"),
                          ("pin_d=pin", "'pin_d' is not an input of the beam case"),
                          ("gap=gap", "'gap' is not an input of the beam case"),
                          ("pin-d=pin", "is not an input"),
                          ("material=dir", "the material is not a parameter"),
                          ("h", "--param takes INPUT=PARAM"), ("h=", "--param takes INPUT=PARAM"),
                          ("=ribbon_t", "--param takes INPUT=PARAM")):
            self.assertIn(word, self.err("beam", *base, "--param", bad, "--b", "6"), bad)
        self.assertIn("'load' is not an input of the snap case",
                      self.err("snap", "--from-build", b, "--part", "sled", "--param", "load=force", "--length", "16",
                               "--h", "1.6", "--b", "6", "--undercut", "0.8"))
        # A parameter the build does not have: merged lists what it has, overrides says the default is not recorded.
        msg = self.err("beam", *base, "--param", "h=ribbon_h", "--b", "6")
        self.assertIn("'ribbon_h' is not in the build's parameters (scope merged", msg)
        self.assertIn("plug.w", msg)
        self.assertNotIn("put it in params.json", msg)
        over = self.build(scope="overrides", values={"ribbon_w": 6}, name="over.json")
        msg = self.err("beam", "--from-build", over, "--part", "sled", "--param", "h=ribbon_t", "--param", "b=ribbon_w",
                       "--length", "20", "--load", "70")
        self.assertIn("default is not recorded", msg)
        self.assertIn("put it in params.json", msg)
        self.assertIn("plug.x", self.err("beam", *base, "--param", "h=plug.x", "--b", "6"))
        self.assertIn("scope overrides", msg)

    def test_value_errors(self):
        def value(case, inp, raw, *argv):
            b = self.build(values={"v": raw}, name="v.json")
            return run(case, "--from-build", b, "--part", "sled", "--param", f"{inp}=v", *argv)

        beam = ["--b", "6", "--length", "20", "--load", "70"]
        for raw, word in ((float("nan"), "a finite number"), (float("inf"), "a finite number"),
                          (float("-inf"), "a finite number"), (True, "a finite number"), (False, "a finite number"),
                          ("3", "a finite number"), (None, "a finite number"), ([3], "a finite number"),
                          (0, "a positive number (mm)"), (0.0, "a positive number (mm)"), (-3, "a positive number (mm)")):
            code, out = value("beam", "h", raw, *beam)
            self.assertEqual(code, 1, raw)
            self.assertIn(f"--param h=v: the build has v = {json.dumps(raw)}; h takes {word}", out["errors"][0])
        # Zero where the option allows it: a pin's gap, a link's bow, a hinge's clearance, a snap's friction.
        pin = ["--d", "3", "--engagement", "4", "--load", "10"]
        for case, inp, argv in (("pin", "gap", pin), ("link", "bow", ["--b", "2", "--h", "2", "--load", "10"]),
                                ("hinge", "clearance", ["--pin-d", "2.4", "--knuckle-d", "7.4", "--knuckles", "5",
                                                        "--length", "36", "--load", "10"]),
                                ("snap", "friction", ["--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8"])):
            code, out = value(case, inp, 0, *argv)
            self.assertEqual(code, 0, (case, out["errors"]))
            self.assertEqual((out["inputs"][inp], out["inputs_from"][inp]), (0.0, "param:v"))
            code, out = value(case, inp, -0.1, *argv)
            self.assertIn(f"{inp} takes zero or a positive number", out["errors"][0])
            code, out = value(case, inp, True, *argv)
            self.assertIn(f"{inp} takes a finite number", out["errors"][0])
        # Other positive inputs: an angle, q, sf.
        snap = ["--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8"]
        for inp in ("q", "entry_angle", "retention_angle", "undercut"):
            argv = [a for i, a in enumerate(snap) if not (a == f"--{inp}" or (i and snap[i - 1] == f"--{inp}"))]
            code, out = value("snap", inp, 0, *argv)
            self.assertIn(f"{inp} takes a positive number", out["errors"][0], inp)
        code, out = value("beam", "sf", 3, "--h", "3", *beam)
        self.assertEqual((code, out["checks"]["bending"]["sf_required"]), (0, 3.0))
        code, out = value("beam", "sf", 0.5, "--h", "3", *beam)
        self.assertIn("--sf must be a number of at least 1.0", out["errors"][0])     # the option's own rule still applies
        # knuckles: a JSON integer.
        hinge = ["--pin-d", "2.4", "--knuckle-d", "7.4", "--length", "36", "--load", "10"]
        for raw in (4.5, 5.0, "5", True, None):
            code, out = value("hinge", "knuckles", raw, *hinge)
            self.assertEqual(code, 1, raw)
            self.assertIn("knuckles takes a whole number (a JSON integer)", out["errors"][0])
        code, out = value("hinge", "knuckles", 1, *hinge)
        self.assertIn("--knuckles must be a whole number of at least 2", out["errors"][0])
        # Choices: strength.py's own.
        for case, inp, raw, argv in (("beam", "orientation", "XY", ["--h", "3", *beam]),
                                     ("beam", "orientation", "yz", ["--h", "3", *beam]),
                                     ("pin", "shear", "triple", pin), ("pin", "support", "cantilever", pin),
                                     ("beam", "support", "stub", ["--h", "3", *beam]),
                                     ("hinge", "hole", 3, ["--knuckles", "5", *hinge]),
                                     ("hinge", "pin", "glued", ["--knuckles", "5", *hinge]),
                                     ("hinge", "duty", "lever", ["--knuckles", "5", *hinge]),
                                     ("hinge", "duty", None, ["--knuckles", "5", *hinge])):
            code, out = value(case, inp, raw, *argv)
            self.assertEqual(code, 1, (inp, raw))
            self.assertIn(f"{inp} takes one of", out["errors"][0])
        code, out = value("hinge", "duty", "latch", "--knuckles", "5", *hinge)
        self.assertEqual((code, out["minimums"]["duty"]), (0, "latch"))
        # Flags take true or false; a load a positive force or a hand-force key.
        for raw in (1, "true", None):
            code, out = value("pin", "load_across_layers", raw, *pin)
            self.assertIn("load_across_layers takes true or false", out["errors"][0])
        pin_noload = ["--d", "3", "--engagement", "4"]
        for raw in (0, -5, float("nan"), True, "thumb", None):
            code, out = value("pin", "load", raw, *pin_noload)
            self.assertEqual(code, 1, raw)
            self.assertIn("load takes a positive force in N or one of finger_push", out["errors"][0])
        code, out = value("pin", "load", "Grasp", *pin_noload)
        self.assertEqual((code, out["load_N"]), (0, strength.LOADS["grasp"]["design_N"]))
        # An integer too large for a float (valid JSON) is refused as JSON, not a traceback (Codex, PR #21).
        for case, inp, argv, word in (("beam", "h", beam, "h takes a finite number"),
                                      ("hinge", "knuckles", hinge, "knuckles takes a whole number"),
                                      ("pin", "load", pin_noload, "load takes a positive force")):
            code, out = value(case, inp, 10 ** 400, *argv)
            self.assertEqual(code, 1, inp)
            self.assertIn(word, out["errors"][0])
            self.assertIn("the build has v = 1000000", out["errors"][0])       # shown cut short

    def test_build_path_as_given(self):
        self.build()
        here = os.getcwd()
        os.chdir(self.dir)
        try:
            out = self.ok("bearing", "--from-build", "build.json", "--part", "lid", "--d", "3", "--t", "5", "--edge", "2",
                          "--load", "30")
        finally:
            os.chdir(here)
        self.assertEqual(out["from_build"]["build"], "build.json")
        self.assertEqual(out["from_build"]["sha256"], "cd" * 32)
        self.assertEqual(out["inputs"]["material"], "pla_basic")
        self.assertEqual(out["inputs_from"]["material"], "build:material")


if __name__ == "__main__":
    unittest.main()
