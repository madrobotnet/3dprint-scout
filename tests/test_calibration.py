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

    def test_kind_keeps_floors_to_the_same_kind_of_member(self):
        """A member that broke is a floor for the same kind of member: --kind on add is stored, lookup --kind K
        takes worked / bounds from entries of kind K only, entries without a kind are listed apart, and a file
        written before `kind` existed still loads."""
        code, out = self.add("--feature", "mechanism", "--kind", "latch", "--result", "failed", "--material", "pla_pure",
                             "--value", "pin_d_mm=2.6", "--load", "finger_push", "--date", "2026-10-17")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["added"]["kind"], "latch")
        self.add("--feature", "mechanism", "--kind", "latch", "--result", "worked", "--value", "pin_d_mm=3.24", "--date", "2026-10-16")
        self.add("--feature", "mechanism", "--result", "worked", "--value", "pin_d_mm=3.0", "--date", "2026-10-15")   # no kind
        code, out = self.add("--feature", "mechanism", "--kind", "lid_hinge", "--result", "worked", "--value", "pin_d_mm=2.4",
                             "--value", "knuckle_d_mm=7.4", "--load", "finger_pull", "--date", "2026-10-19")
        self.assertEqual(out["added"]["kind"], "lid_hinge")
        code, fit = self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.3")
        self.assertNotIn("kind", fit["added"])                                                    # optional everywhere
        code, out = run("lookup", "--file", self.file, "--feature", "mechanism", "--kind", "lid_hinge")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["worked"]["pin_d_mm"]["value"], 2.4)
        self.assertEqual(out["worked"]["pin_d_mm"]["kind"], "lid_hinge")
        self.assertEqual(out["bounds"], {})                                                       # the latch failure sets no floor here
        self.assertEqual(out["unclassified"]["count"], 1)
        self.assertEqual(out["unclassified"]["entries"][0]["values"], {"pin_d_mm": 3.0})
        self.assertIn("set no floor", out["unclassified"]["note"])
        self.assertEqual(out["kinds"], {"lid_hinge": 1, "latch": 2, "unclassified": 1})
        self.assertEqual(out["query"]["kind"], "lid_hinge")
        code, out = run("lookup", "--file", self.file, "--feature", "mechanism", "--kind", "latch")
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["worked"]["pin_d_mm"]["value"], 3.24)
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["value"], 2.6)
        code, out = run("lookup", "--file", self.file, "--feature", "mechanism")                  # no --kind: as before
        self.assertEqual(out["count"], 4)
        self.assertNotIn("unclassified", out)
        self.assertEqual(out["worked"]["pin_d_mm"]["value"], 2.4)
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["value"], 2.6)
        self.assertEqual(out["kinds"], {"lid_hinge": 1, "latch": 2, "unclassified": 1})
        code, out = run("lookup", "--file", self.file, "--kind", "snap")
        self.assertEqual((out["count"], out["worked"], out["unclassified"]["count"]), (0, {}, 2))
        # The kind goes through the id checks: shape, length, identifier tokens (split on letter-digit boundaries
        # as for a printer id), digit runs and long letter-digit tokens; `unclassified` is reserved.
        for bad, word in (("9lives", "lowercase id"), ("a_kind_name_that_is_far_too_long", "24 at most"), ("Lid Hinge", "lowercase id"),
                          ("device_id", "identifier"), ("serial", "identifier"), ("lid-hinge!", "lowercase id"),
                          ("user1", "identifier"), ("sn2", "identifier"), ("ip4", "identifier"), ("mac2", "identifier"),
                          ("dev1", "identifier"), ("id2", "identifier"), ("x2d0123456789", "six or more digits"),
                          ("abcdefg12345", "letter-digit"), ("unclassified", "reserved")):
            code, out = self.add("--feature", "mechanism", "--kind", bad, "--result", "worked")
            self.assertEqual(code, 1, bad)
            self.assertIn(word, out["errors"][0], bad)
        code, out = run("lookup", "--file", self.file, "--kind", "device_id")
        self.assertEqual(code, 1)
        code, out = run("lookup", "--file", self.file, "--kind", "unclassified")
        self.assertEqual(code, 1)
        self.assertIn("reserved", out["errors"][0])
        for good in ("snap2", "lid_hinge", "latch", "lever_v2"):
            self.assertEqual(calibration.normalize_kind(good), good)
        # The same split refuses user1 as a printer id too.
        with self.assertRaisesRegex(calibration.CalibrationError, "identifier"):
            calibration.normalize_id("printer", "user1")
        code, out = run("lookup", "--file", self.file, "--feature", "mechanism", "--kind", "lid_hinge")
        self.assertIn("add", out["unclassified"]["note"])                                      # how to classify an old entry
        # An old file without kind loads and looks up unchanged; a kind in the file is validated too.
        with open(self.file, encoding="utf-8") as f:
            data = json.load(f)
        self.assertTrue(all("kind" not in e for e in data["entries"] if e["values"] == {"pin_d_mm": 3.0}))
        old = os.path.join(self.tmp.name, "old.json")
        with open(old, "w", encoding="utf-8") as f:
            json.dump({"schema": calibration.SCHEMA, "entries": [
                {"date": "2026-10-10", "printer": "x2d", "material": "pla_basic", "nozzle_mm": 0.4, "feature": "mechanism",
                 "result": "worked", "values": {"pin_d_mm": 3.2}, "note": ""}]}, f)
        code, out = run("lookup", "--file", old, "--feature", "mechanism")
        self.assertEqual((code, out["count"], out["worked"]["pin_d_mm"]["value"]), (0, 1, 3.2))
        self.assertNotIn("kind", out["worked"]["pin_d_mm"])
        with self.assertRaisesRegex(calibration.CalibrationError, "kind"):
            calibration.validate_entry({"date": "2026-10-10", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4,
                                        "feature": "mechanism", "result": "worked", "values": {}, "kind": "John Smith"})

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
                           (base + ["--note", "sn 00m00a0a0000001"], "digits"),
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
