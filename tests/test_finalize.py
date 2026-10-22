"""scripts/finalize.py: the final verification report keeps every check it could not make open."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.util import find_spec
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import build  # noqa: E402
import finalize  # noqa: E402
from test_validate import X2D, box, write_stl  # noqa: E402

HAS_M3D = find_spec("manifold3d") is not None and find_spec("numpy") is not None


def run(module, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = module.main(list(argv))
    return code, json.loads(buf.getvalue())


class Workspace(unittest.TestCase):
    """A box and its lid recorded as one build, in a working folder of their own."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="3dps-fin-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)
        os.makedirs("out")
        os.makedirs(".3dprint")
        write_stl("out/box.stl", box(40, 30, 20))
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 30))
        with open("gen.py", "w") as f:
            f.write("def run(context=None):\n    pass\n")
        with open(".3dprint/printers.json", "w") as f:
            json.dump(X2D, f)
        self.params({})

    def params(self, verify, **extra):
        data = {"_parts": {"box": {"expect": [40, 30, 20]}, "lid": {"expect": [40, 30, 3]}},
                "_assumptions": ["wall 2 mm: not measured"], **extra}
        if verify is not None:
            data["_verify"] = verify
        with open(".3dprint/params.json", "w") as f:
            json.dump(data, f)

    def record(self):
        code, out = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "--params",
                        ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out",
                        "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        return out

    def finalize(self, *extra):
        return run(finalize, "--build", "out/build.json", "--params", ".3dprint/params.json",
                   "--printer", ".3dprint/printers.json", "--no-wall-check", *extra)

    def full_verify(self):
        return {"joints": [], "strength": [], "test_prints": [],
                "references": {"box": {d: "real" for d in finalize.DIRECTIONS},
                               "lid": {d: "real" for d in finalize.DIRECTIONS}}}



class Finalize(Workspace):
    def test_nothing_declared_is_not_verified(self):
        self.record()
        code, out = self.finalize()
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["geometry"], "not verified")
        self.assertEqual((out["slicing"], out["print"]), ("unverified", "unverified"))
        self.assertTrue(any(o.startswith("joints not declared") for o in out["open"]), out["open"])
        self.assertTrue(any(o.startswith("members not declared") for o in out["open"]))
        self.assertTrue(any("reference coverage not declared" in o for o in out["open"]))
        self.assertIn("assumption: wall 2 mm: not measured", out["open"])
        self.assertEqual([p["checks"]["R3"] for p in out["parts"]], ["PASS", "PASS"])

    def test_everything_declared_and_fresh_is_verified(self):
        self.params(self.full_verify())
        self.record()
        code, out = self.finalize()
        self.assertEqual(out["geometry"], "verified", out["open"])
        self.assertTrue(out["summary"][0].startswith("geometry: verified"))
        self.assertEqual(out["shape"]["box"]["verified_from"], list(finalize.DIRECTIONS))
        self.assertEqual(out["summary"][2], "slicing: unverified (not sliced here)")

    def test_a_changed_generator_or_stl_is_caught(self):
        self.params(self.full_verify())
        self.record()
        with open("gen.py", "a") as f:
            f.write("# edited after the build\n")
        code, out = self.finalize()
        self.assertEqual(out["geometry"], "not verified")
        self.assertTrue(any(o.startswith("box R3 FAIL") for o in out["open"]), out["open"])
        self.record()                                                         # rebuilt: fresh again
        write_stl("out/lid.stl", box(40, 30, 4, 0, 0, 30))                    # the lid changed after the build
        code, out = self.finalize()
        self.assertEqual(out["geometry"], "not verified")
        self.assertTrue(any("lid R3" in o for o in out["open"]), out["open"])

    def test_new_grouping_invalidates_old_object_checks_without_changing_stls(self):
        self.params(self.full_verify())
        built = self.record()
        self.assertEqual(self.finalize()[1]["geometry"], "verified")
        specs = {"box": {"expect": [40, 30, 20], "object": "assembly", "role": "fused"},
                 "lid": {"expect": [40, 30, 3], "object": "assembly", "role": "fused"}}
        self.params(self.full_verify(), _parts=specs)
        code, out = self.finalize()
        self.assertEqual(code, 0)
        self.assertEqual(out["geometry"], "not verified")
        self.assertIn("assembly metadata changed", out["assembly_drift"][0])
        self.assertEqual([p["checks"]["R3"] for p in out["parts"]], ["PASS", "PASS"])
        self.assertEqual([p["sha256"] for p in built["parts"]], [p["sha256"] for p in out["parts"]])
        if HAS_M3D:
            fresh = self.record()
            self.assertEqual(fresh["gate"], "FAIL")
            self.assertTrue(any("A1 FAIL" in e for e in fresh["errors"]))

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_role_clearance_and_membership_changes_invalidate_assembly(self):
        specs = {"box": {"expect": [40, 30, 20], "object": "o"},
                 "lid": {"expect": [40, 30, 3], "object": "o", "role": "free", "clearance": 0.3}}
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 20.3))
        self.params(self.full_verify(), _parts=specs)
        self.record()
        for change in ("role", "clearance", "membership", "invalid"):
            with self.subTest(change=change):
                current = json.loads(json.dumps(specs))
                if change == "role":
                    current["lid"]["role"] = "fused"
                elif change == "clearance":
                    current["lid"]["clearance"] = 0.8
                elif change == "membership":
                    current = {"box": {"expect": [40, 30, 20]}}
                else:
                    current["lid"]["role"] = "typo"
                self.params(self.full_verify(), _parts=current)
                code, out = self.finalize()
                self.assertEqual(code, 0)
                self.assertEqual(out["geometry"], "not verified")
                self.assertTrue(out["assembly_drift"])
                self.assertEqual(out["objects"][0]["state"], "UNVERIFIED")

    def test_notes_and_rechecked_expect_do_not_invalidate_assembly(self):
        self.params(self.full_verify())
        self.record()
        self.params(self.full_verify(), _assumptions=["a clarified assumption"],
                    _parts={"lid": {"expect": [40, 30, 3], "filament": 2},
                            "box": {"expect": [40.01, 30, 20]}})
        code, out = self.finalize()
        self.assertEqual(code, 0)
        self.assertEqual(out["assembly_drift"], [])
        self.assertEqual(out["geometry"], "verified", out["open"])

    def test_old_build_needs_assembly_evidence_even_without_groups(self):
        self.params(self.full_verify())
        built = self.record()
        del built["assembly_sha256"]
        with open("out/build.json", "w") as f:
            json.dump(built, f)
        code, out = self.finalize()
        self.assertEqual(code, 0)
        self.assertEqual(out["geometry"], "not verified")
        self.assertIn("build has no assembly fingerprint", out["assembly_drift"][0])

    def test_implicit_parts_do_not_create_false_assembly_drift(self):
        # record accepts both an entirely implicit set and a partially documented set.
        # Missing dimensions stay unverified, but their unchanged grouping is not stale.
        for specs in ({}, {"box": {"expect": [40, 30, 20]}}):
            with self.subTest(specs=specs):
                self.params(self.full_verify(), _parts=specs)
                self.record()
                code, out = self.finalize()
                self.assertEqual(code, 0)
                self.assertEqual(out["assembly_drift"], [])
                self.assertEqual(out["geometry"], "not verified")
                self.assertTrue(any("D1 UNVERIFIED" in line for line in out["open"]))

    def test_invalid_parts_metadata_is_a_json_usage_error(self):
        self.params(self.full_verify())
        self.record()
        for specs in (False, [], {"box": False}, {"box": "fused"}, {"box": [1, 2]}):
            with self.subTest(specs=specs):
                self.params(self.full_verify(), _parts=specs)
                code, out = self.finalize()
                self.assertEqual(code, 1)
                self.assertFalse(out["ran"])
                self.assertIn("_parts in params.json", out["errors"][0])

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_only_build_cannot_verify_the_whole_assembly(self):
        specs = {"box": {"expect": [40, 30, 20], "object": "o"},
                 "lid": {"expect": [40, 30, 3], "object": "o", "role": "free"}}
        self.params(self.full_verify(), _parts=specs)
        with open("gen.py", "w") as f:
            f.write("import manifold3d as m3d\n"
                    "def build(p):\n"
                    "    return {'box': m3d.Manifold.cube([40,30,20]), "
                    "'lid': m3d.Manifold.cube([40,30,3]).translate([40.3,0,0])}\n")
        for selected in ("box", "lid", "box,lid"):
            with self.subTest(selected=selected):
                code, built = run(build, "run", "gen.py", "--params", ".3dprint/params.json",
                                  "--printer", ".3dprint/printers.json", "--out", "out",
                                  "--only", selected, "--no-wall-check", "--no-3mf")
                self.assertEqual(code, 0, built["errors"])
                with open("out/build.json", "w") as f:
                    json.dump(built, f)
                code, out = self.finalize()
                self.assertEqual(code, 0)
                if selected == "box,lid":
                    self.assertEqual(out["assembly_drift"], [])
                    self.assertEqual(out["geometry"], "verified", out["open"])
                else:
                    self.assertEqual(out["geometry"], "not verified")
                    self.assertTrue(out["assembly_drift"])
                    self.assertTrue(any("in _parts but not in this build" in line for line in out["open"]))

    def test_shape_directions_and_test_prints(self):
        v = self.full_verify()
        v["references"]["lid"].update(back="estimated", bottom="assumed")
        v["test_prints"] = [{"name": "lid fit coupon", "status": "skipped", "note": "no time"},
                            {"name": "hinge coupon", "status": "passed"}]
        v["unverified"] = ["lid lip height: from a photo"]
        self.params(v)
        self.record()
        code, out = self.finalize()
        self.assertEqual(out["geometry"], "verified", out["open"])              # shape and prints are their own tiers
        self.assertEqual(out["shape"]["lid"]["not_verified_from"], ["back", "bottom"])
        self.assertIn("lid: shape not verified from back (estimated), bottom (assumed)", out["open"])
        self.assertIn("test print 'lid fit coupon': skipped (no time)", out["open"])
        self.assertIn("unverified: lid lip height: from a photo", out["open"])
        self.assertIn("hinge coupon", out["print"])
        v["test_prints"] = [{"name": "x", "status": "maybe"}]
        self.params(v)
        code, out = self.finalize()
        self.assertEqual(code, 1)
        self.assertIn("status must be one of", out["errors"][0])

    def test_strength_reports_count(self):
        v = self.full_verify()
        v["strength"] = [{"name": "latch arm", "report": "out/strength_latch.json"}]
        self.params(v)
        self.record()
        code, out = self.finalize()
        self.assertTrue(any("strength report out/strength_latch.json not found" in o for o in out["open"]))
        import strength
        code_s, rep = run(strength, "pin", "--d", "3", "--engagement", "4", "--support-t", "3", "--load", "finger_push",
                          "--material", "pla_basic")
        with open("out/strength_latch.json", "w") as f:
            json.dump(rep, f)
        code, out = self.finalize()
        self.assertEqual(out["strength"][0]["gate"], rep["gate"])
        if rep["gate"] != "PASS":
            self.assertEqual(out["geometry"], "not verified")
            self.assertTrue(any(o.startswith("member 'latch arm': strength.py pin") for o in out["open"]), out["open"])

    def test_deliver_and_bundle(self):
        self.params(self.full_verify())
        self.record()
        os.makedirs("deliver")
        shutil.copyfile("out/box.stl", "deliver/box.stl")
        write_stl("deliver/lid.stl", box(40, 30, 3.2, 0, 0, 30))             # not the verified lid
        code, out = self.finalize("--deliver", "deliver", "--bundle", "deliver/source")
        self.assertEqual(out["geometry"], "not verified")
        self.assertTrue(any(o.startswith("deliver/lid.stl is not one of the verified STLs") for o in out["open"]), out["open"])
        self.assertIn("lid: not in the delivery (deliver) as an STL or in a 3MF", out["open"])
        self.assertEqual({d["file"]: d["same_as_verified"] for d in out["delivered"]},
                         {"deliver/box.stl": True, "deliver/lid.stl": False})
        self.assertEqual(sorted(out["bundle"]), ["deliver/source/REPRODUCE.md", "deliver/source/gen.py",
                                                 "deliver/source/params.json", "deliver/source/printers.json",
                                                 "deliver/source/verification.json"])
        with open("deliver/source/verification.json", encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn(self.tmp, text)                                       # no path of this machine
        self.assertNotIn(os.path.realpath(self.tmp), text)
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            reproduce = f.read()
        self.assertIn("build.py\" record", reproduce)                       # a recorded build says how to record it
        self.assertIn("--printer printers.json", reproduce)                    # with the bed the build had
        code, out = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 1)
        self.assertIn("never overwrites", out["errors"][0])
        with open("gen.py", "a") as f:                                         # a path of this machine in a source
            f.write(f"FONT = {os.path.join(self.tmp, 'font.ttf')!r}\n")
        self.record()
        code, out = self.finalize("--bundle", "deliver/other")
        self.assertEqual(code, 1)
        self.assertIn("gen.py holds a path of this machine", out["errors"][0])
        self.assertNotIn(self.tmp, json.dumps(out))
        self.assertFalse(os.path.exists("deliver/other"))

    def test_a_delivered_3mf_must_name_the_verified_stls(self):
        self.params(self.full_verify())
        code, out = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "--params",
                        ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out", "--no-wall-check")
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        self.assertTrue(os.path.isfile(out["threemf"] + ".manifest.json"))
        os.makedirs("deliver")
        shutil.copyfile(out["threemf"], os.path.join("deliver", "set.3mf"))
        code, fin = self.finalize("--deliver", "deliver")
        self.assertEqual(fin["geometry"], "verified", fin["open"])            # the manifest in out/ matches its hash
        self.assertEqual(fin["delivered"][0]["parts"], ["box", "lid"])
        with open("deliver/old.3mf", "wb") as f:
            f.write(b"PK not the verified project")
        code, fin = self.finalize("--deliver", "deliver")
        self.assertTrue(any("old.3mf: no 3MF manifest" in o for o in fin["open"]), fin["open"])

    def test_the_bundle_keeps_each_source_at_its_place(self):
        """Codex review of 0.6 (P1): a generator that imports lib/helper.py or loads
        assets/base.stl rebuilds from the bundle only if those keep their places; a source
        outside the project folder is refused, not flattened."""
        self.params(self.full_verify())
        os.makedirs("lib")
        os.makedirs("assets")
        with open("lib/helper.py", "w") as f:
            f.write("W = 2\n")
        with open("assets/base.txt", "w") as f:
            f.write("base\n")
        code, out = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "lib/helper.py",
                        "assets/base.txt", "--params", ".3dprint/params.json", "--printer", ".3dprint/printers.json",
                        "--out", "out", "--no-wall-check", "--no-3mf")
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        code, fin = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 0, fin["errors"])
        for path in ("deliver/source/gen.py", "deliver/source/lib/helper.py", "deliver/source/assets/base.txt"):
            self.assertIn(path, fin["bundle"])
            self.assertTrue(os.path.isfile(path), path)
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            line = next(ln for ln in f.read().splitlines() if "--source" in ln)
        self.assertEqual(sorted(line.split("--source ")[1].split(" --params")[0].split()),
                         ["assets/base.txt", "gen.py", "lib/helper.py"])
        outside = tempfile.mkdtemp(prefix="3dps-out-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        with open(os.path.join(outside, "far.py"), "w") as f:
            f.write("X = 1\n")
        code, out = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py",
                        os.path.join(outside, "far.py"), "--params", ".3dprint/params.json", "--printer",
                        ".3dprint/printers.json", "--out", "out", "--no-wall-check", "--no-3mf")
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        code, fin = self.finalize("--bundle", "deliver/other")
        self.assertEqual(code, 1)
        self.assertIn("far.py is outside the folder the build ran in", fin["errors"][0])
        self.assertFalse(os.path.exists("deliver/other"))

    def test_a_malformed_3mf_manifest_is_a_reason_not_a_crash(self):
        """Codex review of 0.6 (P2): a manifest whose parts is not a map gave a traceback."""
        self.params(self.full_verify())
        code, out = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "--params",
                        ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out", "--no-wall-check")
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        os.makedirs("deliver")
        shutil.copyfile(out["threemf"], "deliver/set.3mf")
        with open(out["threemf"] + ".manifest.json", encoding="utf-8") as f:
            good = json.load(f)
        for bad in (["box", "lid"], "box", {"box": 1}, None):
            os.remove(out["threemf"] + ".manifest.json") if os.path.exists(out["threemf"] + ".manifest.json") else None
            with open("deliver/set.3mf.manifest.json", "w", encoding="utf-8") as f:
                json.dump(dict(good, parts=bad), f)
            code, fin = self.finalize("--deliver", "deliver")
            self.assertEqual(code, 0, fin.get("errors"))
            self.assertTrue(any("deliver/set.3mf: its manifest set.3mf.manifest.json is malformed" in o
                                for o in fin["open"]), (bad, fin["open"]))
            self.assertEqual(fin["geometry"], "not verified")
        with open("deliver/set.3mf.manifest.json", "w", encoding="utf-8") as f:
            json.dump(dict(good, artifact_sha256=["x"]), f)                   # not even a hash: no manifest
        code, fin = self.finalize("--deliver", "deliver")
        self.assertEqual(code, 0, fin.get("errors"))
        self.assertTrue(any("deliver/set.3mf: no 3MF manifest" in o for o in fin["open"]), fin["open"])

    def test_a_stale_build_json_or_a_missing_part_is_not_verified(self):
        """Review of 0.6: the saved build JSON must be the build of these STLs, and of every part."""
        self.params(self.full_verify(), _parts={"box": {"expect": [40, 30, 20], "object": "o"},
                                                "lid": {"expect": [40, 30, 3], "object": "o", "role": "fused"}})
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 20))                    # on the box: A1 PASS
        gate_a = self.record()["gate"]
        shutil.copyfile("out/build.json", "out/build_a.json")
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 18))                    # sunk 2 mm into the box: A1 FAIL
        gate_b = self.record()["gate"]                                        # a new record, not the one finalize gets
        if HAS_M3D:                                                           # A1 needs manifold3d
            self.assertEqual((gate_a, gate_b), ("PASS", "FAIL"))
        shutil.copyfile("out/build_a.json", "out/build.json")
        code, fin = self.finalize()
        self.assertEqual(fin["geometry"], "not verified")
        self.assertIn("lid: out/lid.stl is not the STL this build JSON judged", fin["open"])
        self.assertTrue(any(o.startswith("object 'o': its checks are from a build whose STLs have changed") for o in fin["open"]))
        self.params(self.full_verify())
        code, out = run(build, "record", "out/box.stl", "--source", "gen.py", "--params", ".3dprint/params.json",
                        "--printer", ".3dprint/printers.json", "--out", "out", "--no-wall-check", "--no-3mf")
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        code, fin = self.finalize()
        self.assertIn("lid: in _parts but not in this build (built with --only, or not recorded): build every part, "
                      "save that build's JSON", fin["open"])

    def test_the_build_settings_are_kept(self):
        """A part too tall for one nozzle's area: the build's --tools made D2 FAIL; finalize uses them."""
        with open(".3dprint/printers.json", encoding="utf-8") as f:
            printers = json.load(f)
        write_stl("out/box.stl", box(40, 30, 258))
        data = {"_parts": {"box": {"expect": [40, 30, 258]}, "lid": {"expect": [40, 30, 3]}}, "_verify": self.full_verify()}
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 300))
        with open(".3dprint/params.json", "w") as f:
            json.dump(data, f)
        code, out = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "--params",
                        ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--tools", "1", "--out", "out",
                        "--no-wall-check", "--no-3mf")
        with open("out/build.json", "w") as f:
            json.dump(out, f)
        self.assertEqual(out["validate_settings"]["tools"], "1")
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["D2"]["state"], "FAIL")   # 256 mm on tool 1
        code, fin = self.finalize()
        self.assertEqual(fin["settings"]["tools"], "1")
        self.assertEqual(fin["parts"][0]["checks"]["D2"], "FAIL")
        self.assertEqual(fin["geometry"], "not verified")
        self.assertTrue(any(o.startswith("box D2 FAIL: part is 258.0 mm tall") for o in fin["open"]), fin["open"])
        self.assertIn("x2d", json.dumps(printers))

    def test_build_errors_keep_it_unverified(self):
        """A role with a trailing space breaks the grouping: no object check ran, so the build is
        FAIL (it used to be PASS) and finalize lists the error."""
        v = self.full_verify()
        self.params(v, _parts={"box": {"expect": [40, 30, 20], "object": "o"},
                               "lid": {"expect": [40, 30, 3], "object": "o", "role": "fused "}})
        out = self.record()
        self.assertEqual(out["gate"], "FAIL")
        code, fin = self.finalize()
        self.assertEqual(fin["geometry"], "not verified")
        self.assertTrue(any(o.startswith("the build reported: params.json _parts") for o in fin["open"]), fin["open"])

    def test_bad_verify_and_bad_arguments_are_json_errors(self):
        self.record()
        self.params({"joints": {"name": "x"}})
        code, out = self.finalize()
        self.assertEqual((code, out["errors"]), (1, ["_verify.joints must be a list of objects"]))
        self.params({"accepted": ["body P2"]})
        code, out = self.finalize()
        self.assertEqual(code, 1)
        code, out = run(finalize, "--bogus")
        self.assertEqual(code, 1)
        self.assertTrue(out["errors"][0].startswith("usage:"))

    def test_open_warnings_unless_accepted(self):
        write_stl("out/box.stl", box(40, 30, 20) + box(4, 4, 6, 10, 10, -6))   # a peg under the box: off the bed
        v = self.full_verify()
        self.params(v)
        self.record()
        code, out = self.finalize()
        warn = [o for o in out["open"] if o.startswith("open warning")]
        if warn:                                                              # whatever WARN the validator gives
            who = warn[0].split(": ", 1)[1].split(" WARN")[0]
            v["accepted"] = [{"check": who, "reason": "the user wants it that way"}]
            self.assertFalse(who.startswith("object "))                          # a part's check: "<part> <ID>"
            self.params(v)
            code, out = self.finalize()
            self.assertFalse(any(o.startswith(f"open warning (not accepted in _verify.accepted): {who} ") for o in out["open"]))

    def test_a_copied_expect_can_be_accepted(self):
        """Second review of 0.6: a D1 against a copied expect is open until the user accepts it."""
        write_stl("out/box.stl", box(40.2004, 30, 20))
        v = self.full_verify()
        self.params(v, _parts={"box": {"expect": [40.2004, 30, 20]}, "lid": {"expect": [40, 30, 3]}})
        self.record()
        code, out = self.finalize()
        self.assertEqual(out["geometry"], "not verified")
        self.assertTrue(any(o.startswith("box D1: its expect was copied") for o in out["open"]), out["open"])
        v["accepted"] = [{"check": "box D1", "reason": "no drawing: the printed box is the size"}]
        self.params(v, _parts={"box": {"expect": [40.2004, 30, 20]}, "lid": {"expect": [40, 30, 3]}})
        code, out = self.finalize()
        self.assertEqual(out["geometry"], "verified", out["open"])

    def test_an_incomplete_build_is_named_by_its_checks(self):
        """INCOMPLETE is not a reason of its own (the UNVERIFIED checks behind it are); FAIL is."""
        self.assertEqual(finalize.check_build({"ran": True, "gate": "INCOMPLETE"}), [])
        self.assertEqual(finalize.check_build({"ran": True, "gate": "FAIL"}), ["the build's gate was FAIL, not PASS"])
        self.assertEqual(finalize.check_build({"ran": True, "gate": None}), ["the build's gate was None, not PASS"])

    def test_machine_paths_are_taken_out_in_every_form(self):
        """Third review of 0.6: the report is scrubbed leniently (a file:// link, after -I, before
        a dot or a bar, any case); the bundle refuses a source only for a whole folder of this
        machine (not /home/anne for /home/ann), JSON-escaped or in MSYS form included."""
        here = os.getcwd()
        for text in (f"file://{here}/a.stl", f"-I{here}/include", f"<p>{here}</p>", f"{here}|x", f"saved in {here}.",
                     here.upper() + "/x"):
            self.assertNotIn(here.lower(), finalize.scrub(text).lower(), text)
        self.assertEqual(finalize.scrub(f'"{here}/out/a.stl"'), '"./out/a.stl"')
        for name, body, leaks in (("a.txt", f"FONT = '{here}-fonts/a.ttf'", False),
                                  ("b.txt", f"FONT = '{here}/a.ttf'", True),
                                  ("c.txt", f"CFLAGS = '-I{here}/inc'", True),
                                  ("d.txt", f"saved in {here}.", True)):
            with open(name, "w") as f:
                f.write(body + "\n")
            self.assertEqual(finalize.holds_machine_path(name), leaks, body)
        win = "C:\\Users\\경우"
        with mock.patch.object(finalize, "machine_prefixes", return_value=[win]):
            for text in ("c:\\users\\경우\\x", "/c/Users/경우/x", "file:///C:/Users/경우/x", "/mnt/c/Users/경우/x",
                         json.dumps({"p": win + "\\x"}), json.dumps({"p": win + "\\x"}, ensure_ascii=False)):
                self.assertNotIn("경우", finalize.scrub(text), text)
                self.assertNotIn("uacbd", finalize.scrub(text), text)
            with open("e.json", "w") as f:
                json.dump({"font": win + "\\fonts\\a.ttf"}, f)                    # \uXXXX escapes (ensure_ascii)
            self.assertTrue(finalize.holds_machine_path("e.json"))

    def test_object_checks_need_the_build_settings(self):
        """Third review of 0.6: an object judged on one printer is not verified for another, nor
        after printers.json changed since the build (each part is re-checked, the object is not)."""
        self.params(self.full_verify(), _parts={"box": {"expect": [40, 30, 20], "object": "o"},
                                                "lid": {"expect": [40, 30, 3], "object": "o", "role": "fused"}})
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 20))
        self.record()
        code, fin = self.finalize()
        self.assertEqual(fin["settings_drift"], [])
        self.assertFalse(any("other settings" in o for o in fin["open"]), fin["open"])
        code, fin = self.finalize("--tools", "0")                              # validate.py's own default
        self.assertEqual(fin["settings_drift"], [])
        code, fin = self.finalize("--tools", "1")
        self.assertTrue(any(o.startswith("object 'o': its checks (A1 / A2, D2, P1 / P2 on the whole) were made with "
                                         "other settings") for o in fin["open"]), fin["open"])
        self.assertEqual(fin["geometry"], "not verified")
        with open(".3dprint/printers.json", encoding="utf-8") as f:
            printers = json.load(f)
        printers["_note"] = "edited after the build"
        with open(".3dprint/printers.json", "w", encoding="utf-8") as f:
            json.dump(printers, f)
        code, fin = self.finalize()
        self.assertIn(".3dprint/printers.json changed since the build", fin["settings_drift"])
        self.assertEqual(fin["geometry"], "not verified")

    def test_bad_input_is_an_error(self):
        with open("out/build.json", "w") as f:
            json.dump({"schema": "something/1"}, f)
        code, out = self.finalize()
        self.assertEqual(code, 1)
        self.assertIn("not a build.py run / record report", out["errors"][0])


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class FinalizeJoints(Workspace):
    def test_joint_reports_must_be_fresh_and_pass(self):
        import fit
        v = self.full_verify()
        v["joints"] = [{"name": "lid on box", "report": "out/fit_box_lid.json"}]
        self.params(v)
        self.record()
        code, out = self.finalize()
        self.assertTrue(any("fit report out/fit_box_lid.json not found" in o for o in out["open"]))
        code, rep = run(fit, "out/box.stl", "out/lid.stl", "--b-translate", "0,0,-10", "--play", "none")
        with open("out/fit_box_lid.json", "w") as f:
            json.dump(rep, f)
        code, out = self.finalize()
        self.assertEqual(out["joints"][0]["fresh"], "PASS")
        self.assertEqual(out["geometry"], "verified" if rep["gate"] == "PASS" else "not verified", out["open"])
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 30.5))
        self.record()                                                         # a new build, the fit not run again
        code, out = self.finalize()
        self.assertEqual(out["joints"][0]["fresh"], "FAIL")
        self.assertTrue(any("joint 'lid on box': F3_fresh FAIL" in o for o in out["open"]), out["open"])
        write_stl("out/proxy.stl", box(40, 30, 2, 0, 0, 31))                 # a proxy: not one of the parts
        code, rep = run(fit, "out/box.stl", "out/proxy.stl", "--b-translate", "0,0,-11", "--play", "none")
        with open("out/fit_box_lid.json", "w") as f:
            json.dump(rep, f)
        code, out = self.finalize()
        self.assertTrue(any("not a part of this build" in o for o in out["open"]), out["open"])
        v["joints"][0]["proxy"] = True
        self.params(v)
        code, out = self.finalize()
        self.assertFalse(any("not a part of this build" in o for o in out["open"]))
        self.assertTrue(any("against a proxy" in w for w in out["warnings"]))


if __name__ == "__main__":
    unittest.main()
