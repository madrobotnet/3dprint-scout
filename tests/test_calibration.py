"""Tests for scripts/calibration.py: schema, privacy refusals, add / show / lookup."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import calibration  # noqa: E402


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = calibration.main(list(argv))
    return code, json.loads(buf.getvalue())


class Calibration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, ".3dprint", "calibration.json")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, *extra):
        return run("add", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4", *extra)

    def test_add_show_lookup(self):
        code, out = self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.3",
                             "--value", "profile_w_mm=45.1", "--note", "ring 2 slid on by hand", "--date", "2026-10-16")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["entries"], 1)
        self.assertEqual(out["added"]["values"], {"clearance_per_side_mm": 0.3, "profile_w_mm": 45.1})
        code, out = self.add("--feature", "fit", "--result", "loose", "--value", "clearance_per_side_mm=0.45", "--date", "2026-10-15")
        code, out = self.add("--feature", "mechanism", "--result", "failed", "--material", "pla_pure", "--value", "pin_d_mm=2.6",
                             "--value", "pin_wall_mm=1.3", "--load", "finger_push", "--note", "draw latch broke on first use",
                             "--date", "2026-10-17", "--layer", "0.2")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["added"]["load"], "finger_push")
        self.assertEqual(out["added"]["layer_mm"], 0.2)
        with open(self.file, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema"], calibration.SCHEMA)
        self.assertEqual(len(data["entries"]), 3)
        code, out = run("show", "--file", self.file)
        self.assertEqual(out["count"], 3)
        code, out = run("lookup", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--feature", "fit")
        self.assertEqual(out["count"], 2)
        self.assertEqual([e["date"] for e in out["entries"]], ["2026-10-16", "2026-10-15"])      # newest first
        self.assertEqual(out["worked"]["clearance_per_side_mm"]["value"], 0.3)                 # the later ring wins
        self.assertEqual(out["worked"]["clearance_per_side_mm"]["result"], "fits")
        self.assertEqual(out["bounds"]["clearance_per_side_mm"]["loose"]["value"], 0.45)
        code, out = run("lookup", "--file", self.file, "--material", "pla_pure")
        self.assertEqual(out["count"], 1)
        self.assertNotIn("pin_d_mm", out["worked"])                                             # a failure is never a setting
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["value"], 2.6)
        code, out = run("lookup", "--file", self.file, "--nozzle", "0.6")
        self.assertEqual(out["count"], 0)

    def test_same_day_entries_and_results_are_kept_apart(self):
        """Three entries on one day: the one added last is the newest, and 'worked' only takes
        values from results that fit, worked or were measured."""
        self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.3", "--date", "2026-10-17")
        self.add("--feature", "fit", "--result", "tight", "--value", "clearance_per_side_mm=0.2", "--date", "2026-10-17")
        self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.25", "--date", "2026-10-17")
        code, out = run("lookup", "--file", self.file, "--printer", "x2d")
        self.assertEqual([e["values"]["clearance_per_side_mm"] for e in out["entries"]], [0.25, 0.2, 0.3])
        self.assertEqual(out["worked"]["clearance_per_side_mm"]["value"], 0.25)
        self.assertEqual(out["bounds"]["clearance_per_side_mm"]["tight"]["value"], 0.2)
        self.assertNotIn("failed", out["bounds"]["clearance_per_side_mm"])
        self.add("--feature", "mechanism", "--result", "failed", "--value", "pin_d_mm=2.6", "--date", "2026-10-17")
        self.add("--feature", "mechanism", "--result", "worked", "--value", "pin_d_mm=3.24", "--date", "2026-10-17")
        code, out = run("lookup", "--file", self.file, "--feature", "mechanism")
        self.assertEqual(out["worked"]["pin_d_mm"]["value"], 3.24)
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["value"], 2.6)

    def test_missing_file_reads_as_empty_and_bad_file_is_refused(self):
        code, out = run("lookup", "--file", self.file, "--printer", "x2d")
        self.assertEqual((code, out["count"]), (0, 0))
        os.makedirs(os.path.dirname(self.file))
        with open(self.file, "w") as f:
            f.write('{"schema": "other", "entries": []}')
        code, out = run("show", "--file", self.file)
        self.assertEqual(code, 1)
        self.assertIn("not a calibration file", out["errors"][0])

    def test_schema_refusals(self):
        bad = [(["--feature", "fit", "--result", "maybe"], "result"),
               (["--feature", "latch", "--result", "fits"], "feature"),
               (["--feature", "fit", "--result", "fits", "--value", "clearance=tight"], "number"),
               (["--feature", "fit", "--result", "fits", "--value", "clearance"], "name=number"),
               (["--feature", "fit", "--result", "fits", "--date", "17/10/2026"], "YYYY-MM-DD"),
               (["--feature", "fit", "--result", "fits", "--load", "hard"], "force"),
               (["--feature", "fit", "--result", "fits", "--load", "-5"], "positive"),
               (["--feature", "fit", "--result", "fits", "--load", "nan"], "positive"),
               (["--feature", "fit", "--result", "fits", "--value", "x=nan"], "finite"),
               (["--feature", "fit", "--result", "fits", "--value", "x=inf"], "finite"),
               (["--feature", "fit", "--result", "fits", "--value", "x=1234567890"], "too large"),
               (["--feature", "fit", "--result", "fits", "--nozzle", "40"], "plausible")]
        for argv, word in bad:
            code, out = self.add(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], argv)
        self.assertFalse(os.path.exists(self.file))

    def test_privacy_refusals(self):
        base = ["--feature", "fit", "--result", "fits"]
        for argv, word in ((base + ["--value", "serial_number=123"], "not allowed"),
                           (base + ["--value", "access_code=1234"], "not allowed"),
                           (base + ["--value", "uid=1234"], "not allowed"),
                           (base + ["--value", "device_id=7"], "not allowed"),
                           (base + ["--value", "lan_code=1234"], "not allowed"),
                           (base + ["--value", "mac_addr=1"], "not allowed"),
                           (base + ["--note", "printer at 192.168.1.20"], "IP address"),
                           (base + ["--note", "link local fe80::1ff:fe23:4567:890a"], "IPv6"),
                           (base + ["--note", "mac 00:1A:2B:3C:4D:5E"], "MAC"),
                           (base + ["--note", "ask someone@example.com"], "e-mail"),
                           (base + ["--note", "SN 01P00A123456789"], "digits"),
                           (base + ["--note", "sn 00m09a3b1000685"], "digits"),
                           (base + ["--note", "code x7k9q2m4p8w1"], "letter-digit"),
                           (base + ["--note", "access code 1234, uid 20938"], "announces"),
                           (base + ["--note", "the serial is on the back"], "announces"),
                           (["--feature", "fit", "--result", "fits", "--printer", "John Smith"], "lowercase id"),
                           (["--feature", "fit", "--result", "fits", "--material", "Bambu PLA Basic"], "lowercase id"),
                           (["--feature", "fit", "--result", "fits", "--printer", "device_id"], "identifier")):
            code, out = run("add", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4", *argv) \
                if "--printer" not in argv and "--material" not in argv else \
                run("add", "--file", self.file, *(["--printer", "x2d"] if "--printer" not in argv else []),
                    *(["--material", "pla_basic"] if "--material" not in argv else []), "--nozzle", "0.4", *argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], (argv, out["errors"]))
        self.assertFalse(os.path.exists(self.file))
        # A material written the way strength.py spells it, or close to it, is stored as its key.
        code, out = run("add", "--file", self.file, "--printer", "x2d", "--material", "PLA Basic", "--nozzle", "0.4",
                        "--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.3")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["added"]["material"], "pla_basic")
        code, out = run("lookup", "--file", self.file, "--material", "pla-basic")
        self.assertEqual(out["count"], 1)
        # A printers.json pins the printer to one of its ids.
        printers = os.path.join(self.tmp.name, "printers.json")
        with open(printers, "w") as f:
            json.dump({"schema": "3dprint.printers/1", "printers": {"x2d": {}}}, f)
        code, out = self.add("--feature", "fit", "--result", "fits", "--printers", printers)
        self.assertEqual(code, 0, out["errors"])
        code, out = run("add", "--file", self.file, "--printer", "p1s", "--material", "pla_basic", "--nozzle", "0.4",
                        "--feature", "fit", "--result", "fits", "--printers", printers)
        self.assertEqual(code, 1)
        self.assertIn("not in", out["errors"][0])
        for entry in ({"date": "2026-10-17", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4, "feature": "fit",
                       "result": "fits", "values": {}, "user_id": "123"},
                      {"date": "2026-10-17", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4, "feature": "fit",
                       "result": "fits", "values": {"ip_address": 1}}):
            with self.assertRaisesRegex(calibration.CalibrationError, "not allowed"):
                calibration.validate_entry(entry)
        # Ordinary notes with numbers, versions and model names pass, Korean included.
        code, out = self.add("--feature", "hole", "--result", "measured", "--value", "hole_d_nominal_mm=3.4",
                             "--value", "hole_d_measured_mm=3.25",
                             "--note", "M3 clearance hole, Bambu Studio 02.08.02.61, 3 walls, X2D 0.4 nozzle; 2번 링이 맞았어요")
        self.assertEqual(code, 0, out["errors"])
        code, out = run("show", "--file", self.file)
        self.assertIn("2번 링", out["entries"][-1]["note"])


if __name__ == "__main__":
    unittest.main()
