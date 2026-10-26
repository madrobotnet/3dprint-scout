"""Tests for scripts/strength_cases.py: a tube under a band clamp, a post whose root is loaded
across the layers, and a snap arm with a taper and a worst-case undercut, each with numbers
worked by hand; linking to a build; usage errors. And the reason the file exists: strength.py
is a hashed source of every build that imports parts.py, so it stays byte-identical and new
cases go here."""
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import strength  # noqa: E402
import strength_cases as sc  # noqa: E402

# sha256 of scripts/strength.py (LF line endings) as shipped from 0.7.0 to 0.9.1.
STRENGTH_SHA256 = "60a354ad96c8159befc3a4ae4a6edd7a09d0b35e2ac5c19c8c1db009a9382cc7"


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = sc.main(list(argv))
    return code, json.loads(buf.getvalue())


def run_strength(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = strength.main(list(argv))
    return code, json.loads(buf.getvalue())


def ok(test, *argv):
    code, out = run(*argv)
    test.assertEqual(code, 0, out["errors"])
    test.assertEqual(out["schema"], "3dprint-scout.strength/1")
    test.assertEqual(set(out["inputs_from"]), set(out["inputs"]))
    return out


def err(test, *argv):
    code, out = run(*argv)
    test.assertEqual(code, 1, argv)
    test.assertFalse(out["ran"])
    test.assertEqual(len(out["errors"]), 1, out["errors"])
    test.assertNotIn("nan", json.dumps(out).lower())
    return out["errors"][0]


class Staleness(unittest.TestCase):
    """build.py hashes every skill module a generator loaded; parts.py loads strength.py (the
    duty floors, the snap strain table), so a byte changed in strength.py makes every build that
    imports parts.py stale (validate.py R3; CHANGELOG 0.8.2). New cases live in
    strength_cases.py, which no generator loads."""

    def test_strength_py_is_the_shipped_file(self):
        with open(os.path.join(SCRIPTS, "strength.py"), "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(data).hexdigest(), STRENGTH_SHA256,
                         "strength.py changed: it is a hashed source of every build whose generator imports parts.py, "
                         "so this makes all of those builds stale. Put a new case in strength_cases.py; change this pin "
                         "only on purpose, with the staleness said in the CHANGELOG's Upgrading line")

    def test_parts_does_not_load_this_file(self):
        with open(os.path.join(SCRIPTS, "parts.py"), encoding="utf-8") as f:
            self.assertNotIn("strength_cases", f.read())
        code = ("import sys; sys.path.insert(0, %r)\n"
                "try:\n    import parts\nexcept ImportError:\n    print('SKIP'); raise SystemExit\n"
                "print(sorted(n for n, m in sys.modules.items() if 'strength' in n))" % SCRIPTS)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        if r.stdout.strip() == "SKIP":
            self.skipTest("parts.py needs manifold3d")
        self.assertEqual(r.stdout.strip(), "['_3dps_strength']")

    def test_reads_strength_without_changing_it(self):
        self.assertIs(sc.S, sys.modules["_3dps_strength"])               # parts.py's private name, shared
        self.assertEqual(os.path.realpath(sc.S.__file__), os.path.realpath(os.path.join(SCRIPTS, "strength.py")))
        ok(self, "tube", "--d", "100", "--t", "3", "--band-w", "9", "--tension", "500", "--material", "petg_basic")
        ok(self, "post", "--d", "5", "--length", "10", "--load", "30", "--material", "petg_basic")
        ok(self, "snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--taper", "0.5",
           "--material", "pla_basic")
        self.assertEqual(sc.S.CASE_INPUTS, strength.CASE_INPUTS)           # strength.py's tables, untouched
        self.assertEqual(sc.S.INPUT_KIND, strength.INPUT_KIND)
        self.assertEqual(set(sc.INPUT_KIND), set().union(*(sc.linkable_inputs(c) for c in sc.CASES)))


class Tube(unittest.TestCase):
    """A 100 mm spigot under a 9 mm band at 500 N, PETG Basic standing on the bed (XY)."""

    BASE = ["--d", "100", "--band-w", "9", "--material", "petg_basic", "--orientation", "xy"]

    def test_hand_numbers(self):
        out = ok(self, "tube", *self.BASE, "--t", "3", "--tension", "500")
        hoop = out["checks"]["hoop_compression"]
        # sigma = T / (w t) = 500 / 27 = 18.52 MPa against tensile XY 51 MPa: SF 2.75.
        self.assertEqual((hoop["stress_mpa"], hoop["strength_mpa"], hoop["sf_achieved"], hoop["state"]),
                         (18.52, 51.0, 2.75, "PASS"))
        self.assertEqual((out["gate"], out["load_N"], out["case"]), ("PASS", 500.0, "tube"))
        tube = out["tube"]
        self.assertEqual(tube["r_mean_mm"], 48.5)
        self.assertAlmostEqual(tube["band_pressure_mpa"], 500 / (50 * 9), places=4)            # 1.1111 MPa
        self.assertAlmostEqual(tube["radial_shrink_mm"], 500 * 48.5 / (2780 * 9 * 3), places=3)   # 0.323 mm
        self.assertEqual(tube["tension_at_sf_N"], 688.5)                                     # 51 x 27 / 2
        p3 = 1950 * 27 / (4 * 48.5 ** 3)                                                     # 0.11538 MPa
        self.assertAlmostEqual(tube["ring_critical_pressure_mpa"], p3, places=5)
        self.assertEqual(set(out["checks"]), {"hoop_compression"})                           # buckling is not a check
        self.assertTrue(any("R18.2.5" in a for a in out["assumptions"]))
        # A 2 mm wall: 27.78 MPa, SF 1.84 (WARN); its ring is (3/2)^3 x (49/48.5)^3 = 3.48 x weaker.
        two = ok(self, "tube", *self.BASE, "--t", "2", "--tension", "500")
        self.assertEqual((two["checks"]["hoop_compression"]["stress_mpa"], two["checks"]["hoop_compression"]["sf_achieved"],
                          two["gate"]), (27.78, 1.84, "WARN"))
        self.assertAlmostEqual(p3 / two["tube"]["ring_critical_pressure_mpa"], 3.48, places=2)
        self.assertIn("thicken the wall under the band", two["next_step"])
        # 1500 N on 2 mm: 83.33 MPa, past the strength: FAIL.
        hard = ok(self, "tube", *self.BASE, "--t", "2", "--tension", "1500")
        self.assertEqual((hard["checks"]["hoop_compression"]["sf_achieved"], hard["gate"]), (0.61, "FAIL"))
        self.assertIn("crushes the tube", hard["next_step"])
        # The default orientation is z (tensile Z 35 MPa): the same tube reads SF 1.89 and says to pass xy.
        z = ok(self, "tube", "--d", "100", "--band-w", "9", "--material", "petg_basic", "--t", "3", "--tension", "500")
        self.assertEqual((z["checks"]["hoop_compression"]["sf_achieved"], z["gate"]), (1.89, "WARN"))
        self.assertEqual(z["inputs_from"]["orientation"], "default:orientation")
        self.assertTrue(any("takes --orientation xy" in a for a in z["assumptions"]))

    def test_usage(self):
        base = [*self.BASE, "--t", "3"]
        self.assertIn("--tension", err(self, "tube", *base, "--load", "500"))
        self.assertIn("--tension is required", err(self, "tube", *base))
        self.assertIn("no bore", err(self, "tube", "--d", "6", "--t", "3", "--band-w", "9", "--tension", "500",
                                     "--material", "abs"))
        self.assertIn("--undercut does not apply to the tube case", err(self, "tube", *base, "--tension", "500",
                                                                        "--undercut", "1"))
        for bad in ("-5", "0", "nan", "inf"):
            self.assertIn("--tension", err(self, "tube", *base, "--tension", bad), bad)
        self.assertIn("--band-w", err(self, "tube", "--d", "100", "--t", "3", "--band-w", "0", "--tension", "500",
                                      "--material", "abs"))
        self.assertIn("--material is required", err(self, "tube", "--d", "100", "--t", "3", "--band-w", "9",
                                                    "--tension", "500"))


class Post(unittest.TestCase):
    def test_rectangle_is_strength_beam_across_the_layers(self):
        # 6 x 4 mm post, finger push 70.6 N at 8 mm: M = 564.8 N mm, I = 32 mm4, sigma = 35.3 MPa against bending Z
        # 59 MPa (PLA Basic): SF 1.67, WARN. Root shear 3/2 x 70.6 / 24 = 4.41 MPa against 0.58 x 31: SF 4.07.
        out = ok(self, "post", "--b", "6", "--h", "4", "--length", "8", "--load", "finger_push", "--material", "pla_basic")
        bend, shear = out["checks"]["bending"], out["checks"]["shear"]
        self.assertEqual((bend["stress_mpa"], bend["strength_mpa"], bend["sf_achieved"], bend["state"]),
                         (35.3, 59.0, 1.67, "WARN"))
        self.assertEqual((shear["stress_mpa"], shear["sf_achieved"]), (4.41, 4.07))
        self.assertAlmostEqual(shear["strength_mpa"], 0.58 * 31, places=2)
        self.assertEqual((out["gate"], out["orientation"], out["post"]["section"]), ("WARN", "z", "rectangle"))
        self.assertEqual(out["inputs_from"]["load"], "table:finger_push")
        # strength.py beam gives the same bending across the layers.
        code, beam = run_strength("beam", "--b", "6", "--h", "4", "--length", "8", "--support", "cantilever",
                                  "--load", "finger_push", "--material", "pla_basic", "--orientation", "z")
        self.assertEqual(beam["checks"]["bending"]["stress_mpa"], bend["stress_mpa"])
        self.assertEqual((beam["deflection_mm"], beam["moment_nmm"], beam["I_mm4"]),
                         (out["deflection_mm"], out["moment_nmm"], out["I_mm4"]))
        self.assertTrue(any("layer on layer" in c["strength_basis"] for c in out["checks"].values()))

    def test_round_post_and_orientation(self):
        # d = 5 mm, 30 N at 10 mm, PETG Basic: sigma = 32 x 300 / (pi 125) = 24.45 MPa against bending Z 56: SF 2.29;
        # shear 4/3 x 30 / 19.635 = 2.04 MPa against 0.58 x 35 = 20.3: SF 9.96.
        out = ok(self, "post", "--d", "5", "--length", "10", "--load", "30", "--material", "petg_basic")
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 32 * 300 / (math.pi * 125), places=2)
        self.assertEqual((out["checks"]["bending"]["sf_achieved"], out["checks"]["shear"]["sf_achieved"], out["gate"]),
                         (2.29, 9.96, "PASS"))
        self.assertAlmostEqual(out["deflection_mm"], 30 * 1000 / (3 * 1740 * math.pi * 625 / 64), places=3)
        self.assertEqual(out["post"]["section"], "round")
        flat = ok(self, "post", "--d", "5", "--length", "10", "--load", "30", "--material", "petg_basic",
                  "--orientation", "xy")
        self.assertEqual(flat["checks"]["bending"]["strength_mpa"], 75)                      # bending XY
        self.assertTrue(any("lies flat" in a for a in flat["assumptions"]))
        # A block shorter than it is deep says beam theory is rough there.
        block = ok(self, "post", "--b", "10", "--h", "8", "--length", "4", "--load", "100", "--material", "abs")
        self.assertTrue(any("shorter than it is deep" in a for a in block["assumptions"]))

    def test_usage(self):
        tail = ["--length", "8", "--load", "50", "--material", "abs"]
        self.assertIn("not both", err(self, "post", "--d", "5", "--b", "6", "--h", "4", *tail))
        self.assertIn("not both", err(self, "post", *tail))
        self.assertIn("--h is required", err(self, "post", "--b", "6", *tail))
        self.assertIn("--load is required", err(self, "post", "--d", "5", "--length", "8", "--material", "abs"))
        self.assertIn("--tension does not apply to the post case", err(self, "post", "--d", "5", "--tension", "9", *tail))
        self.assertIn("--length", err(self, "post", "--d", "5", "--load", "50", "--material", "abs"))
        self.assertIn("--load", err(self, "post", "--d", "5", "--length", "8", "--load", "thumb", "--material", "abs"))


class Snap(unittest.TestCase):
    ARM = ["--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--material", "pla_basic", "--orientation", "xy"]
    UNIFORM_E = 1.5 * 1.6 * 0.8 / 16 ** 2                 # 0.0075
    UNIFORM_P = 3 * 2750 * (6 * 1.6 ** 3 / 12) * 0.8 / 16 ** 3   # 3.3 N

    def test_taper_factor(self):
        self.assertEqual(sc.taper_factor(1.0), 1.0)
        self.assertAlmostEqual(2 / 3 * sc.taper_factor(0.5), 1.09, places=2)                 # Bayer type 2: y = 1.09 e L^2 / h
        # The tapered-hook K table (designerdata.nl), h at the hook / h at the root.
        for a, K in ((0.33, 2.137), (0.4, 1.893), (0.5, 1.636), (0.6, 1.445), (0.7, 1.297), (0.8, 1.179),
                     (0.89, 1.091), (0.95, 1.039), (0.99, 1.008)):
            self.assertAlmostEqual(sc.taper_factor(a), K, delta=0.0006, msg=a)
        # The series near 1 meets the closed form, and K falls as the taper eases.
        k = 0.01
        closed = 3 * (-math.log(1 - k) + 2 * (1 - k) - (1 - k) ** 2 / 2 - 1.5) / k ** 3
        self.assertAlmostEqual(sc.taper_factor(1 - k + 1e-12), closed, places=9)
        ks = [sc.taper_factor(1 - i / 1000) for i in range(0, 600, 7)]
        self.assertEqual(ks, sorted(ks))
        self.assertEqual(sc.taper_peak(0.5), (1.0, 1.0))
        self.assertAlmostEqual(sc.taper_peak(0.4)[0], 1 / (4 * 0.4 * 0.6))
        for bad in (0, -0.5, 1.5, float("nan")):
            with self.assertRaises(sc.StrengthError):
                sc.taper_factor(bad)

    def test_half_taper(self):
        out = ok(self, "snap", *self.ARM, "--taper", "0.5")
        K = sc.taper_factor(0.5)
        snap = out["snap"]
        self.assertAlmostEqual(snap["strain"], self.UNIFORM_E / K, places=5)                 # 0.00459
        self.assertAlmostEqual(snap["deflection_force_N"], self.UNIFORM_P / K, places=3)     # 2.018 N
        self.assertAlmostEqual(snap["max_deflection_mm"], 1.0904 * 0.01 * 16 ** 2 / 1.6, places=2)   # 1.745 mm
        self.assertEqual((snap["taper"], snap["h_tip_mm"], snap["peak_factor"], snap["worst"]), (0.5, 0.8, 1.0, None))
        self.assertAlmostEqual(out["checks"]["bending"]["stress_mpa"], 2750 * self.UNIFORM_E / K, delta=0.01)
        self.assertEqual(out["gate"], "PASS")
        self.assertIn("K = 1.636", out["checks"]["strain"]["formula"])
        # --h-tip 0.8 is the same arm.
        tip = ok(self, "snap", *self.ARM, "--h-tip", "0.8")
        self.assertEqual(tip["checks"], out["checks"])
        self.assertEqual(tip["inputs"]["h_tip"], 0.8)
        self.assertNotIn("taper", tip["inputs"])

    def test_steep_taper_peaks_inside_the_arm(self):
        out = ok(self, "snap", *self.ARM, "--taper", "0.4")
        peak = 1 / (4 * 0.4 * 0.6)
        self.assertAlmostEqual(out["snap"]["strain"], self.UNIFORM_E / sc.taper_factor(0.4) * peak, places=5)
        self.assertEqual((out["snap"]["peak_factor"], out["snap"]["peak_from_hook"]), (round(peak, 4), 0.6667))
        self.assertIn("inside the arm", out["checks"]["strain"]["formula"])
        self.assertTrue(any("under the 1.2 mm minimum" in a for a in out["assumptions"]))   # a 0.64 mm hook end

    def test_no_taper_is_strength_py_snap(self):
        out = ok(self, "snap", *self.ARM, "--taper", "1")
        code, ref = run_strength("snap", *self.ARM)
        self.assertEqual(out["checks"], ref["checks"])
        self.assertEqual(out["load_N"], ref["load_N"])
        self.assertEqual({k: out["snap"][k] for k in ref["snap"]}, ref["snap"])
        self.assertEqual(out["assumptions"][:4], ref["assumptions"][:4])
        self.assertEqual(out["next_step"], ref["next_step"])

    def test_worst_case_undercut(self):
        # Uniform arm, 0.8 mm nominal + 0.4 mm stack = 1.2 mm: strain 0.01125 over PLA's 1 %: the worst case fails.
        out = ok(self, "snap", *self.ARM, "--gap-worst", "0.4")
        c = out["checks"]
        self.assertEqual({k: v["state"] for k, v in c.items()},
                         {"strain": "PASS", "bending": "PASS", "strain_worst": "FAIL", "bending_worst": "PASS"})
        self.assertAlmostEqual(c["strain_worst"]["strain"], 1.5 * 1.6 * 1.2 / 256, places=5)
        self.assertEqual(out["gate"], "FAIL")
        self.assertIn("holds at the nominal 0.8 mm undercut, not at the worst-case 1.2 mm", out["next_step"])
        worst = out["snap"]["worst"]
        Pw = self.UNIFORM_P * 1.5
        t30 = math.tan(math.radians(30))
        self.assertEqual((worst["undercut_mm"], worst["gap_worst_mm"]), (1.2, 0.4))
        self.assertAlmostEqual(worst["deflection_force_N"], Pw, places=3)                     # 4.95 N
        self.assertAlmostEqual(worst["insertion_force_N"], Pw * (0.3 + t30) / (1 - 0.3 * t30), places=2)
        self.assertIsNone(worst["release_force_N"])
        self.assertAlmostEqual(out["load_N"], self.UNIFORM_P, places=9)                       # the nominal force
        self.assertTrue(any("worst-case undercut 1.2 mm" in a for a in out["assumptions"]))
        # Tapered to half, the same stack fits: 0.01125 / 1.636 = 0.00688.
        half = ok(self, "snap", *self.ARM, "--taper", "0.5", "--gap-worst", "0.4")
        self.assertEqual(half["gate"], "PASS")
        self.assertAlmostEqual(half["snap"]["worst"]["strain"], 0.01125 / sc.taper_factor(0.5), places=5)
        # A zero stack is the nominal again; a retention face gives a release force at both.
        zero = ok(self, "snap", *self.ARM, "--gap-worst", "0", "--retention-angle", "45")
        self.assertEqual(zero["checks"]["strain_worst"]["strain"], zero["checks"]["strain"]["strain"])
        self.assertEqual(zero["snap"]["worst"]["release_force_N"], zero["snap"]["release_force_N"])

    def test_usage(self):
        self.assertIn("strength.py snap", err(self, "snap", *self.ARM))
        self.assertIn("one way", err(self, "snap", *self.ARM, "--taper", "0.5", "--h-tip", "0.8"))
        for bad in ("1.5", "0", "-0.5"):
            self.assertIn("--taper", err(self, "snap", *self.ARM, "--taper", bad), bad)
        self.assertIn("at most the root's", err(self, "snap", *self.ARM, "--h-tip", "2"))
        self.assertIn("--gap-worst must be zero or a positive number", err(self, "snap", *self.ARM, "--gap-worst", "-0.1"))
        self.assertIn("own deflection force", err(self, "snap", *self.ARM, "--taper", "0.5", "--load", "finger_pull"))
        self.assertIn("--q must be positive", err(self, "snap", *self.ARM, "--taper", "0.5", "--q", "nan"))
        self.assertIn("--band-w does not apply to the snap case", err(self, "snap", *self.ARM, "--taper", "0.5",
                                                                      "--band-w", "9"))
        self.assertIn("usage error", err(self, "pin", "--d", "3"))                            # strength.py's cases stay there


class FromBuild(unittest.TestCase):
    """--from-build, --part and --param as strength.py's, for the new inputs."""

    SHA = "ef" * 32
    VALUES = {"spigot_d": 100, "spigot_wall": 3, "band": 9, "clamp_T": 500, "dir": "xy", "snap_taper": 0.5,
              "tol": 0.4, "zero": 0, "post_d": 5, "pull": "finger_pull", "neg": -0.1, "text": "0.5", "big": 1.5}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def build(self, values=None, name="build.json"):
        doc = {"schema": "3dprint-scout.build/1", "params": "params.json",
               "parameters": {"scope": "merged", "values": self.VALUES if values is None else values},
               "parts": [{"name": "adapter", "stl": "out/adapter.stl", "sha256": self.SHA, "material": "petg_basic"},
                         {"name": "clip", "stl": "out/clip.stl", "sha256": "12" * 32, "material": "pla_basic"}]}
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        return path

    def test_linked_tube_matches_typed_and_finalize_takes_it(self):
        b = self.build()
        linked = ok(self, "tube", "--from-build", b, "--part", "adapter", "--param", "d=spigot_d", "--param",
                    "t=spigot_wall", "--param", "band_w=band", "--param", "tension=clamp_T", "--param", "orientation=dir")
        typed = ok(self, "tube", "--d", "100", "--t", "3", "--band-w", "9", "--tension", "500", "--material",
                   "petg_basic", "--orientation", "xy")
        self.assertEqual(linked["checks"], typed["checks"])
        self.assertEqual(linked["inputs"], typed["inputs"])
        self.assertEqual(linked["tube"], typed["tube"])
        self.assertEqual(linked["inputs_from"], {"material": "build:material", "orientation": "param:dir", "sf": "default:sf",
                                                 "d": "param:spigot_d", "t": "param:spigot_wall", "band_w": "param:band",
                                                 "tension": "param:clamp_T"})
        self.assertEqual(linked["from_build"]["parameters"]["tension"], {"param": "clamp_T", "value": 500})
        self.assertEqual((linked["from_build"]["sha256"], linked["material"]["key"]), (self.SHA, "petg_basic"))
        self.assertNotIn("from_build", typed)
        # finalize reads it as any strength.py report: tied to the build while the part and parameters stand.
        import finalize_evidence
        with open(b, encoding="utf-8") as f:
            build = json.load(f)
        params = {"_material": "petg_basic"}
        tie = finalize_evidence.strength_link(linked, linked["inputs"], build["parts"], build, params, {})
        self.assertEqual((tie["linked"], tie["manual"], tie.get("stale")), (True, [], None))
        moved = json.loads(json.dumps(build))
        moved["parameters"]["values"]["spigot_wall"] = 2
        tie = finalize_evidence.strength_link(linked, linked["inputs"], moved["parts"], moved, params, {})
        self.assertEqual(tie["stale"], ["t was spigot_wall = 3, now 2"])

    def test_linked_snap_and_post(self):
        b = self.build()
        snap = ok(self, "snap", "--from-build", b, "--part", "clip", "--param", "taper=snap_taper", "--param",
                  "gap_worst=tol", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--orientation", "xy")
        typed = ok(self, "snap", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8", "--orientation", "xy",
                   "--taper", "0.5", "--gap-worst", "0.4", "--material", "pla_basic")
        self.assertEqual(snap["checks"], typed["checks"])
        self.assertEqual((snap["inputs_from"]["taper"], snap["inputs_from"]["gap_worst"]), ("param:snap_taper", "param:tol"))
        zero = ok(self, "snap", "--from-build", b, "--part", "clip", "--param", "gap_worst=zero", "--length", "16",
                  "--h", "1.6", "--b", "6", "--undercut", "0.8")
        self.assertEqual((zero["inputs"]["gap_worst"], zero["inputs_from"]["gap_worst"]), (0.0, "param:zero"))
        post = ok(self, "post", "--from-build", b, "--part", "adapter", "--param", "d=post_d", "--param", "load=pull",
                  "--length", "10")
        self.assertEqual((post["inputs_from"]["load"], post["load_N"]), ("param:pull", strength.LOADS["finger_pull"]["design_N"]))
        self.assertEqual(post["inputs_from"]["d"], "param:post_d")

    def test_link_errors(self):
        b = self.build()
        tube = ["tube", "--from-build", b, "--part", "adapter", "--d", "100", "--t", "3"]
        self.assertIn("'load' is not an input of the tube case", err(self, *tube, "--band-w", "9", "--param", "load=clamp_T"))
        self.assertIn("'load' is not an input of the snap case",
                      err(self, "snap", "--from-build", b, "--part", "clip", "--param", "load=clamp_T", "--length", "16",
                          "--h", "1.6", "--b", "6", "--undercut", "0.8", "--taper", "0.5"))
        self.assertIn("'undercut' is not an input of the tube case", err(self, *tube, "--param", "undercut=tol"))
        self.assertIn("band_w takes a positive number (mm)", err(self, *tube, "--tension", "500", "--param", "band_w=zero"))
        self.assertIn("tension takes a positive number", err(self, *tube, "--band-w", "9", "--param", "tension=neg"))
        self.assertIn("tension takes a finite number", err(self, *tube, "--band-w", "9", "--param", "tension=text"))
        snap = ["snap", "--from-build", b, "--part", "clip", "--length", "16", "--h", "1.6", "--b", "6", "--undercut", "0.8"]
        self.assertIn("gap_worst takes zero or a positive number", err(self, *snap, "--param", "gap_worst=neg"))
        self.assertIn("taper takes a finite number", err(self, *snap, "--param", "taper=text"))
        self.assertIn("--taper is the thickness at the hook", err(self, *snap, "--param", "taper=big"))
        self.assertIn("h is given twice", err(self, *snap, "--param", "h=spigot_wall", "--taper", "0.5"))
        self.assertIn("taper is linked twice", err(self, *snap, "--param", "taper=snap_taper", "--param", "taper=big"))
        self.assertIn("--material does not go with --from-build", err(self, *tube, "--band-w", "9", "--tension", "5",
                                                                      "--material", "abs"))
        self.assertIn("'clamp_N' is not in the build's parameters", err(self, *tube, "--band-w", "9", "--param",
                                                                        "tension=clamp_N"))
        self.assertIn("part 'lid' is not in", err(self, "tube", "--from-build", b, "--part", "lid", "--d", "100", "--t", "3",
                                                  "--band-w", "9", "--tension", "5"))
        self.assertIn("need --from-build", err(self, "tube", "--param", "d=spigot_d", "--t", "3", "--band-w", "9",
                                               "--tension", "5", "--material", "abs"))


class Docs(unittest.TestCase):
    def test_references_give_each_case(self):
        with open(os.path.join(HERE, "..", "references", "phase-4-mechanisms.md"), encoding="utf-8") as f:
            phase4 = f.read()
        with open(os.path.join(HERE, "..", "references", "materials.md"), encoding="utf-8") as f:
            materials = f.read()
        for case in ("tube", "post", "snap"):
            self.assertTrue(f"strength_cases.py {case}" in phase4, case)
            self.assertTrue(f"strength_cases.py {case}" in materials, case)
        for word in ("--tension", "--band-w", "--taper", "--h-tip", "--gap-worst"):
            self.assertTrue(word in phase4, word)
        # The example's links are the case's inputs.
        example = phase4.split('strength_cases.py" tube', 1)[1].split("```", 1)[0]
        linked = {p.split("=")[0] for p in example.split("--param ")[1:]}
        self.assertEqual(linked, sc.CASE_INPUTS["tube"] | {"orientation"})
        self.assertIn("R18.2.5", materials)
        self.assertIn("Timoshenko", materials)


if __name__ == "__main__":
    unittest.main()
