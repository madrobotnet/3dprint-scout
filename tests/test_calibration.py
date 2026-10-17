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
        code, out = run("lookup", "--file", self.file, "--printer", "X2D", "--material", "pla_basic", "--feature", "fit")
        self.assertEqual(out["count"], 2)
        self.assertEqual([e["date"] for e in out["entries"]], ["2026-10-16", "2026-10-15"])      # newest first
        self.assertEqual(out["latest"]["clearance_per_side_mm"]["value"], 0.3)                 # the later ring wins
        self.assertEqual(out["latest"]["clearance_per_side_mm"]["result"], "fits")
        code, out = run("lookup", "--file", self.file, "--material", "pla_pure")
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["latest"]["pin_d_mm"]["value"], 2.6)
        code, out = run("lookup", "--file", self.file, "--nozzle", "0.6")
        self.assertEqual(out["count"], 0)

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
               (["--feature", "fit", "--result", "fits", "--nozzle", "40"], "plausible")]
        for argv, word in bad:
            code, out = self.add(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], argv)
        self.assertFalse(os.path.exists(self.file))

    def test_privacy_refusals(self):
        for argv, word in ((["--feature", "fit", "--result", "fits", "--value", "serial_number=123"], "serial"),
                           (["--feature", "fit", "--result", "fits", "--value", "access_code=1234"], "access"),
                           (["--feature", "fit", "--result", "fits", "--note", "printer at 192.168.1.20"], "IP address"),
                           (["--feature", "fit", "--result", "fits", "--note", "ask someone@example.com"], "e-mail"),
                           (["--feature", "fit", "--result", "fits", "--note", "SN 01P00A123456789"], "serial")):
            code, out = self.add(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], argv)
        for entry in ({"date": "2026-10-17", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4, "feature": "fit",
                       "result": "fits", "values": {}, "user_id": "123"},
                      {"date": "2026-10-17", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4, "feature": "fit",
                       "result": "fits", "values": {"ip_address": 1}}):
            with self.assertRaisesRegex(calibration.CalibrationError, "not allowed"):
                calibration.validate_entry(entry)
        # Ordinary notes with numbers and model names pass.
        code, out = self.add("--feature", "hole", "--result", "measured", "--value", "hole_d_nominal_mm=3.4",
                             "--value", "hole_d_measured_mm=3.25", "--note", "M3 clearance hole, Bambu Studio 02.08, 3 walls")
        self.assertEqual(code, 0, out["errors"])


if __name__ == "__main__":
    unittest.main()
