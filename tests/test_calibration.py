"""Tests for scripts/calibration.py: schema, privacy refusals, add / show / lookup."""
import glob
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import calibration  # noqa: E402

PRESET = "0.20mm Standard @BBL X2D"
_USER_DIR = None
_ENV = None


def setUpModule():
    """No test reads or writes the real ~/.3dprint: the user-level file is a temporary path."""
    global _USER_DIR, _ENV
    _USER_DIR = tempfile.TemporaryDirectory()
    _ENV = mock.patch.dict(os.environ, {calibration.USER_ENV: os.path.join(_USER_DIR.name, "home", ".3dprint",
                                                                           "calibration.json")})
    _ENV.start()


def tearDownModule():
    _ENV.stop()
    _USER_DIR.cleanup()


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = calibration.main(list(argv))
    return code, json.loads(buf.getvalue())


def lookup_commands(text):
    """Every `calibration.py lookup --file ...` command in a text, its continuation lines joined."""
    lines, out = text.splitlines(), []
    for n, line in enumerate(lines):
        if re.search(r'calibration\.py"? lookup --file', line):
            cmd = line
            while cmd.rstrip().endswith("\\") and n + 1 < len(lines):
                n += 1
                cmd = cmd.rstrip()[:-1] + " " + lines[n].strip()
            out.append(cmd)
    return out


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

    def test_lookup_keeps_to_the_nozzle_and_the_docs_give_it(self):
        """Results from different nozzles mixed by default, and the documented lookup left --nozzle out. With
        --nozzle an entry from another nozzle is only a reference, with what differs; without it a warning says
        every nozzle is mixed; every documented lookup command gives --nozzle."""
        self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.3", "--date", "2026-10-15")
        code, out = run("add", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.6",
                        "--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.4", "--date", "2026-10-16")
        self.assertEqual(code, 0, out["errors"])
        code, out = run("lookup", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--feature", "fit")
        self.assertEqual(code, 0, out["errors"])
        self.assertTrue(any("--nozzle" in w and "mixed" in w and "0.4, 0.6" in w for w in out["warnings"]), out["warnings"])
        code, out = run("lookup", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4",
                        "--feature", "fit")
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["worked"]["clearance_per_side_mm"]["value"], 0.3)                  # not the 0.6 nozzle's 0.4
        self.assertEqual([(r["entry"], r["values"], r["differs"]) for r in out["reference"]],
                         [(1, {"clearance_per_side_mm": 0.4}, {"nozzle_mm": [0.6, 0.4]})])
        self.assertFalse(any("--nozzle" in w for w in out["warnings"]), out["warnings"])
        docs = {"calibration.py": calibration.__doc__}
        for path in [os.path.join(ROOT, n) for n in ("SKILL.md", "README.md", "README.ko.md")] + \
                glob.glob(os.path.join(ROOT, "references", "**", "*.md"), recursive=True):
            with open(path, encoding="utf-8") as f:
                docs[os.path.relpath(path, ROOT)] = f.read()
        commands = [(name, cmd) for name, text in docs.items() for cmd in lookup_commands(text)]
        self.assertGreaterEqual(len(commands), 3, commands)
        for name, cmd in commands:
            self.assertIn("--nozzle", cmd, (name, cmd))

    def test_lookup_matches_layer_load_orientation_and_process(self):
        """layer_mm and load were stored but never matched, orientation and the process preset not recorded. Each
        is a condition now: only an entry that records the query's value sets worked and bounds; one that differs,
        or does not record it, is a reference with what differs."""
        mech = ["--feature", "mechanism", "--kind", "latch"]
        same = ["--layer", "0.2", "--load", "finger_push", "--orientation", "flat", "--process", PRESET]

        def but(**changed):
            argv = list(same)
            for opt, value in changed.items():
                argv[argv.index("--" + opt) + 1] = value
            return argv
        code, out = self.add(*mech, "--result", "worked", "--value", "pin_d_mm=3.2", *same, "--date", "2026-10-14")  # 0
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual((out["added"]["orientation"], out["added"]["process"], out["added"]["layer_mm"]), ("flat", PRESET, 0.2))
        self.add(*mech, "--result", "worked", "--value", "pin_d_mm=2.8", *but(layer="0.28"), "--date", "2026-10-15")   # 1
        self.add(*mech, "--result", "failed", "--value", "pin_d_mm=3.6", *but(orientation="upright"), "--date", "2026-10-16")  # 2
        self.add(*mech, "--result", "failed", "--value", "pin_d_mm=3.4", *but(load="40"), "--date", "2026-10-17")      # 3
        self.add(*mech, "--result", "worked", "--value", "pin_d_mm=2.4", *but(process="0.20mm Strength @BBL X2D"),
                 "--date", "2026-10-18")                                                                            # 4
        self.add(*mech, "--result", "worked", "--value", "pin_d_mm=2.0", "--date", "2026-10-19")                     # 5: none
        query = ["lookup", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4",
                 "--feature", "mechanism", "--kind", "latch"]
        code, out = run(*query, *but(process=" 0.20mm  standard @BBL X2D"))       # case and repeated spaces aside
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual([e["entry"] for e in out["entries"]], [0])
        self.assertEqual((out["worked"]["pin_d_mm"]["value"], out["worked"]["pin_d_mm"]["entry"]), (3.2, 0))
        self.assertEqual(out["bounds"], {})                    # the upright and the 40 N failures are not this print's floors
        self.assertEqual({k: out["query"][k] for k in ("nozzle", "layer", "load", "orientation", "process")},
                         {"nozzle": 0.4, "layer": 0.2, "load": "finger_push", "orientation": "flat",
                          "process": "0.20mm standard @BBL X2D"})
        self.assertEqual([r["entry"] for r in out["reference"]], [5, 4, 3, 2, 1])                  # newest first
        self.assertEqual({r["entry"]: r["differs"] for r in out["reference"]}, {
            1: {"layer_mm": [0.28, 0.2]},
            2: {"orientation": ["upright", "flat"]},
            3: {"load": [40.0, "finger_push"]},
            4: {"process": ["0.20mm Strength @BBL X2D", "0.20mm standard @BBL X2D"]},
            5: {"layer_mm": ["not recorded", 0.2], "load": ["not recorded", "finger_push"],
                "orientation": ["not recorded", "flat"], "process": ["not recorded", "0.20mm standard @BBL X2D"]}})
        # A force matches within 1e-6 N; the 40 N failure is the floor under 40 N.
        code, out = run(*query, *but(load="40.0000001"))
        self.assertEqual([e["entry"] for e in out["entries"]], [3])
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["entry"], 3)
        self.assertEqual(out["worked"], {})
        # Without --layer the 0.2 and 0.28 mm prints both count, and a warning names the layer heights.
        argv = but()
        del argv[0:2]
        code, out = run(*query, *argv)
        self.assertEqual([e["entry"] for e in out["entries"]], [1, 0])
        self.assertTrue(any("--layer" in w and "0.28, 0.2" in w for w in out["warnings"]), out["warnings"])
        self.assertNotIn("layer_mm", out["reference"][0]["differs"])

    def test_worked_from_different_prints_is_marked_combined(self):
        """'worked' took each value name's newest value from any entry, pairing one print's pin with another
        print's wall as if they had been printed together. Each value now names its entry, 'combined' says
        when they come from different prints, and 'worked_set' is one print's values together."""
        mech = ["--feature", "mechanism", "--kind", "latch"]
        self.add(*mech, "--result", "worked", "--value", "pin_d_mm=3.0", "--value", "pin_wall_mm=2.2", "--date", "2026-10-15")
        self.add(*mech, "--result", "worked", "--value", "pin_d_mm=2.6", "--date", "2026-10-17")
        self.add(*mech, "--result", "failed", "--value", "pin_wall_mm=1.3", "--date", "2026-10-18")
        query = ["lookup", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4", "--kind", "latch"]
        code, out = run(*query)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual({k: (v["value"], v["entry"], v["date"]) for k, v in out["worked"].items()},
                         {"pin_d_mm": (2.6, 1, "2026-10-17"), "pin_wall_mm": (2.2, 0, "2026-10-15")})
        self.assertIs(out["combined"], True)
        self.assertTrue(any("never printed together" in w and "worked_set" in w for w in out["warnings"]), out["warnings"])
        self.assertEqual((out["worked_set"]["entry"], out["worked_set"]["values"]), (1, {"pin_d_mm": 2.6}))
        self.assertEqual((out["bounds"]["pin_wall_mm"]["failed"]["entry"], out["bounds"]["pin_wall_mm"]["failed"]["date"]),
                         (2, "2026-10-18"))
        self.assertEqual([e["entry"] for e in out["entries"]], [2, 1, 0])
        # One print that carries both values: one set, not combined.
        self.add(*mech, "--result", "worked", "--value", "pin_d_mm=3.24", "--value", "pin_wall_mm=2.2", "--date", "2026-10-19")
        code, out = run(*query)
        self.assertIs(out["combined"], False)
        self.assertEqual((out["worked_set"]["entry"], out["worked_set"]["values"]), (3, {"pin_d_mm": 3.24, "pin_wall_mm": 2.2}))
        self.assertEqual({v["entry"] for v in out["worked"].values()}, {3})
        self.assertFalse(any("never printed together" in w for w in out["warnings"]), out["warnings"])
        # Nothing that fit, worked or was measured: no set.
        code, out = run("lookup", "--file", self.file, "--nozzle", "0.4", "--kind", "lid_hinge")
        self.assertEqual((out["worked"], out["worked_set"], out["combined"]), ({}, None, False))

    def test_old_file_without_the_new_fields(self):
        """A file written before orientation and process, with entries that record no layer or load, loads, shows
        and looks up as before; given those conditions its entries are references, marked not recorded, and an
        entry without a kind stays under unclassified with what differs; add keeps the old entries as they are."""
        entries = [{"date": "2026-10-10", "printer": "x2d", "material": "pla_basic", "nozzle_mm": 0.4, "feature": "fit",
                    "result": "fits", "values": {"clearance_per_side_mm": 0.3}, "note": ""},
                   {"date": "2026-10-11", "printer": "x2d", "material": "pla_basic", "nozzle_mm": 0.4, "layer_mm": 0.2,
                    "feature": "mechanism", "kind": "latch", "result": "failed", "values": {"pin_d_mm": 2.6},
                    "load": "finger_push", "note": "broke on first use"}]
        os.makedirs(os.path.dirname(self.file))
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump({"schema": calibration.SCHEMA, "entries": entries}, f)
        code, out = run("show", "--file", self.file)
        self.assertEqual((code, out["count"]), (0, 2))
        self.assertTrue(all("orientation" not in e and "process" not in e for e in out["entries"]))
        code, out = run("lookup", "--file", self.file, "--printer", "x2d", "--nozzle", "0.4")
        self.assertEqual((code, out["count"], out["reference"], out["combined"]), (0, 2, [], False))
        self.assertEqual(out["worked"]["clearance_per_side_mm"]["value"], 0.3)
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["value"], 2.6)
        code, out = run("lookup", "--file", self.file, "--nozzle", "0.4", "--orientation", "flat", "--process", PRESET)
        self.assertEqual((out["count"], out["worked"], out["bounds"], out["worked_set"]), (0, {}, {}, None))
        self.assertEqual([(r["entry"], r["differs"]) for r in out["reference"]],
                         [(1, {"orientation": ["not recorded", "flat"], "process": ["not recorded", PRESET]}),
                          (0, {"orientation": ["not recorded", "flat"], "process": ["not recorded", PRESET]})])
        code, out = run("lookup", "--file", self.file, "--nozzle", "0.4", "--layer", "0.2", "--kind", "latch")
        self.assertEqual([e["entry"] for e in out["entries"]], [1])
        self.assertEqual(out["bounds"]["pin_d_mm"]["failed"]["entry"], 1)
        self.assertEqual([(u["entry"], u["differs"]) for u in out["unclassified"]["entries"]],
                         [(0, {"layer_mm": ["not recorded", 0.2]})])
        code, out = self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.25",
                             "--orientation", "flat", "--process", PRESET, "--date", "2026-10-20")
        self.assertEqual(code, 0, out["errors"])
        with open(self.file, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema"], calibration.SCHEMA)
        self.assertEqual(data["entries"][:2], entries)
        self.assertEqual((data["entries"][2]["orientation"], data["entries"][2]["process"]), ("flat", PRESET))

    def test_orientation_and_process_are_validated(self):
        """orientation goes through the kind's id checks; process is one line of text, 80 characters at most,
        through the note's checks; both are optional; the same checks hold for lookup and for a file."""
        base = ["--feature", "fit", "--result", "fits"]
        for argv, word in ((["--orientation", "On Side"], "lowercase id"), (["--orientation", "on-side"], "lowercase id"),
                           (["--orientation", "9flat"], "lowercase id"),
                           (["--orientation", "flat_on_the_bed_with_brim"], "24 at most"),
                           (["--orientation", "device_id"], "identifier"), (["--orientation", "user1"], "identifier"),
                           (["--orientation", "flat0123456789"], "six or more digits"),
                           (["--orientation", "flatk9q2m4p8w1"], "letter-digit"),
                           (["--process", "x" * 81], "80 characters"),
                           (["--process", PRESET + " at 192.168.1.20"], "IP address"),
                           (["--process", "preset from someone@example.com"], "e-mail"),
                           (["--process", "SN 01P00A123456789"], "digits"),
                           (["--process", "x7k9q2m4p8w1 preset"], "letter-digit"),
                           (["--process", "access code preset"], "announces"),
                           (["--process", "0.20mm\x00Standard"], "control")):
            code, out = self.add(*base, *argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], (argv, out["errors"]))
        self.assertFalse(os.path.exists(self.file))
        code, out = self.add(*base, "--orientation", "on_side", "--process", "  0.20mm   Standard\n@BBL X2D  ")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual((out["added"]["orientation"], out["added"]["process"]), ("on_side", PRESET))   # one line, trimmed
        code, out = self.add(*base, "--process", "0.16mm Optimal @BBL X2D, Bambu Studio 02.08.02.61")
        self.assertEqual(code, 0, out["errors"])
        code, out = self.add(*base, "--orientation", "", "--process", "  ")
        self.assertEqual(code, 0, out["errors"])
        self.assertNotIn("orientation", out["added"])                                                 # optional
        self.assertNotIn("process", out["added"])
        for argv, word in ((["--orientation", "On Side"], "lowercase id"), (["--process", "y" * 81], "80 characters"),
                           (["--load", "hard"], "force"), (["--load", "0"], "positive"), (["--layer", "9"], "plausible"),
                           (["--nozzle", "40"], "plausible")):
            code, out = run("lookup", "--file", self.file, *argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], (argv, out["errors"]))
        entry = {"date": "2026-10-17", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4, "feature": "fit",
                 "result": "fits", "values": {}}
        for bad, word in (({"orientation": "Flat Side"}, "lowercase id"), ({"process": 5}, "as text"),
                          ({"process": "z" * 81}, "80 characters"), ({"orientation": "serial"}, "identifier")):
            with self.assertRaisesRegex(calibration.CalibrationError, word):
                calibration.validate_entry(dict(entry, **bad))
        with open(self.file, encoding="utf-8") as f:
            data = json.load(f)
        data["entries"][0]["process"] = "printer at 192.168.1.20"
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        code, out = run("show", "--file", self.file)
        self.assertEqual(code, 1)
        self.assertIn("IP address", out["errors"][0])


class UserLevelFile(unittest.TestCase):
    """0.9.1: results carried from one project to the next in ~/.3dprint/calibration.json (here a temporary
    path through THREEDPRINT_USER_CALIBRATION): read after the project file, project entries first."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = os.path.join(self.tmp.name, "project", ".3dprint", "calibration.json")
        self.user = os.path.join(self.tmp.name, "home", ".3dprint", "calibration.json")
        env = mock.patch.dict(os.environ, {calibration.USER_ENV: self.user})
        env.start()
        self.addCleanup(env.stop)

    def add(self, *extra, user=False):
        where = ["--user"] if user else ["--file", self.file]
        return run("add", *where, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4", *extra)

    def test_add_user_writes_the_user_level_file_only(self):
        code, out = self.add("--feature", "fit", "--result", "fits", "--value", "sleeve_w_mm=61.5", "--date", "2026-10-20",
                             user=True)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual((out["from"], out["entries"]), ("user", 1))
        self.assertTrue(os.path.isfile(self.user))                          # ~/.3dprint/ made when needed
        self.assertFalse(os.path.exists(self.file))
        with open(self.user, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual((data["schema"], data["entries"][0]["values"]), (calibration.SCHEMA, {"sleeve_w_mm": 61.5}))
        code, out = self.add("--feature", "fit", "--result", "fits")
        self.assertEqual((code, out["from"], out["file"]), (0, "project", self.file))
        with open(self.user, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["entries"]), 1)                # the project's add left it alone
        code, out = run("add", "--user", "--file", self.file, "--printer", "x2d", "--material", "pla_basic",
                        "--nozzle", "0.4", "--feature", "fit", "--result", "fits")
        self.assertEqual(code, 1)
        self.assertIn("not both", out["errors"][0])
        code, out = run("add", "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4", "--feature", "fit",
                        "--result", "fits")
        self.assertEqual(code, 1)
        self.assertIn("--file", out["errors"][0])
        # The privacy guards hold for the user-level file too.
        for argv, word in ((["--note", "printer at 192.168.1.20"], "IP address"), (["--value", "serial_no=1"], "not allowed"),
                           (["--printer", "John Smith"], "lowercase id")):
            code, out = self.add("--feature", "fit", "--result", "fits", *argv, user=True)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, out["errors"][0], argv)
        with open(self.user, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["entries"]), 1)

    def test_lookup_reads_both_files_project_first(self):
        fit = ["--feature", "fit"]
        self.add(*fit, "--result", "fits", "--value", "clearance_per_side_mm=0.3", "--date", "2026-10-10")       # project 0
        self.add(*fit, "--result", "tight", "--value", "clearance_per_side_mm=0.2", "--date", "2026-10-11")      # project 1
        self.add(*fit, "--result", "fits", "--value", "clearance_per_side_mm=0.25", "--value", "sleeve_w_mm=61.5",
                 "--date", "2026-10-20", user=True)                                                            # user 0
        self.add(*fit, "--result", "loose", "--value", "clearance_per_side_mm=0.4", "--date", "2026-10-21",
                 user=True)                                                                                    # user 1
        self.add(*fit, "--result", "fits", "--value", "clearance_per_side_mm=0.35", "--nozzle", "0.6",
                 "--date", "2026-10-22", user=True)                                                            # user 2
        query = ["lookup", "--file", self.file, "--printer", "x2d", "--material", "pla_basic", "--nozzle", "0.4",
                 "--feature", "fit"]
        code, out = run(*query)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["user_file"], self.user)
        self.assertEqual([(e["from"], e["entry"]) for e in out["entries"]],
                         [("project", 1), ("project", 0), ("user", 1), ("user", 0)])   # the project's first, each newest first
        w = out["worked"]
        self.assertEqual((w["clearance_per_side_mm"]["value"], w["clearance_per_side_mm"]["from"]), (0.3, "project"))
        self.assertEqual((w["sleeve_w_mm"]["value"], w["sleeve_w_mm"]["from"], w["sleeve_w_mm"]["entry"]),
                         (61.5, "user", 0))                                       # only the user-level file has it
        self.assertEqual((out["worked_set"]["from"], out["worked_set"]["entry"]), ("project", 0))
        self.assertEqual(out["bounds"]["clearance_per_side_mm"]["tight"]["from"], "project")
        self.assertEqual(out["bounds"]["clearance_per_side_mm"]["loose"]["from"], "user")
        self.assertIs(out["combined"], True)
        self.assertTrue(any("entries 0, user 0" in w and "never printed together" in w for w in out["warnings"]),
                        out["warnings"])
        self.assertEqual([(r["from"], r["entry"], r["differs"]) for r in out["reference"]],
                         [("user", 2, {"nozzle_mm": [0.6, 0.4]})])
        code, out = run(*query, "--no-user")
        self.assertEqual((code, out["user_file"], out["count"], out["reference"]), (0, None, 2, []))
        self.assertNotIn("sleeve_w_mm", out["worked"])
        self.assertTrue(all(e["from"] == "project" for e in out["entries"]))
        code, out = run("show", "--file", self.file)
        self.assertEqual((code, out["count"]), (0, 5))
        self.assertEqual([e["from"] for e in out["entries"]], ["project"] * 2 + ["user"] * 3)
        code, out = run("show", "--file", self.file, "--no-user")
        self.assertEqual(out["count"], 2)
        # A project without a log of its own still finds the user-level results.
        code, out = run("lookup", "--file", os.path.join(self.tmp.name, "other", "calibration.json"), "--nozzle", "0.4",
                        "--feature", "fit")
        self.assertEqual((code, out["worked"]["clearance_per_side_mm"]["value"]), (0, 0.25))
        self.assertEqual(out["worked_set"]["from"], "user")
        # The user-level file given as the project file is read once.
        code, out = run("lookup", "--file", self.user, "--nozzle", "0.4", "--feature", "fit")
        self.assertEqual((code, out["count"]), (0, 2))
        self.assertTrue(all(e["from"] == "project" for e in out["entries"]))

    def test_an_unreadable_user_level_file_is_left_out_and_never_rewritten(self):
        self.add("--feature", "fit", "--result", "fits", "--value", "clearance_per_side_mm=0.3")
        os.makedirs(os.path.dirname(self.user))
        for bad, word in (("{not json", "not valid JSON"), ('{"schema": "other", "entries": []}', "not a calibration file"),
                          (json.dumps({"schema": calibration.SCHEMA, "entries": [
                              {"date": "2026-10-17", "printer": "x2d", "material": "pla", "nozzle_mm": 0.4,
                               "feature": "fit", "result": "fits", "values": {}, "note": "at 192.168.1.20"}]}),
                           "IP address")):
            with self.subTest(word=word):
                with open(self.user, "w", encoding="utf-8") as f:
                    f.write(bad)
                code, out = self.add("--feature", "fit", "--result", "fits", user=True)
                self.assertEqual(code, 1)
                self.assertIn(word, out["errors"][0])
                with open(self.user, encoding="utf-8") as f:
                    self.assertEqual(f.read(), bad)                                # refused, as it is
                for cmd in (["lookup", "--file", self.file, "--nozzle", "0.4"], ["show", "--file", self.file]):
                    code, out = run(*cmd)
                    self.assertEqual((code, out["count"]), (0, 1), out["errors"])     # the project's entries still
                    self.assertTrue(any("user-level file" in w and word in w and "--no-user" in w
                                        for w in out["warnings"]), out["warnings"])
                code, out = run("lookup", "--file", self.file, "--nozzle", "0.4", "--no-user")
                self.assertFalse(any("user-level" in w for w in out["warnings"]))

    def test_the_default_place_is_in_the_home_folder(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(calibration.USER_ENV, None)
            self.assertEqual(calibration.user_file(), os.path.expanduser(os.path.join("~", ".3dprint", "calibration.json")))
            self.assertEqual(calibration.shown_path(calibration.user_file()), "~/.3dprint/calibration.json")


if __name__ == "__main__":
    unittest.main()
