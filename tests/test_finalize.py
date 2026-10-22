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
        self.assertEqual(out["summary"][0], "use: not declared (_verify.promises)")    # said first at delivery
        self.assertTrue(out["summary"][1].startswith("geometry: verified"))
        self.assertEqual(out["shape"]["box"]["verified_from"], list(finalize.DIRECTIONS))
        self.assertEqual(out["summary"][3], "slicing: unverified (not sliced here)")

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
                    # nothing in _parts changed: the report names the parts left out, not a change
                    self.assertIn("not built:", out["assembly_drift"][0])
                    self.assertNotIn("changed", out["assembly_drift"][0])
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


def fit_report(path, a, b, **checks):
    """A saved fit.py report of the STLs a and b as they are now, with the check states given
    (F3 PASS by default): what finalize reads is the report, so the states are the test's."""
    import fit
    import validate
    checks = checks or {"F3": "PASS"}
    states = set(checks.values())
    rep = {"schema": fit.SCHEMA, "ran": True,
           "gate": "FAIL" if "FAIL" in states else "WARN" if "WARN" in states else "PASS",
           "parts": {k: {"path": p, "sha256": validate.file_sha256(p)} for k, p in (("a", a), ("b", b))},
           "checks": {cid: {"state": st, "kind": "hard", "note": f"{cid} {st} in the test"} for cid, st in checks.items()}}
    with open(path, "w") as f:
        json.dump(rep, f)


def strength_report(path, gate):
    with open(path, "w") as f:
        json.dump({"schema": "3dprint-scout.strength/1", "ran": True, "gate": gate, "case": "beam",
                   "worst": "bending", "inputs": {"h": 4.5, "b": 12}}, f)


class FinalizePromises(Workspace):
    """0.7.0: what the user was promised is judged by its own evidence (the use tier), apart
    from the geometry."""

    PLUG = {"plug_w": 13, "plug_h": 8, "plug_l": 9, "cable_d": 4.5}
    SEAT = {"id": "seat", "kind": "use", "text": "the lid sits on the box", "conditions": "lid on top, box on a desk",
            "success": "no overlap, and play", "evidence": [{"joint": "lid on box"}]}
    CABLE = {"id": "cable-out", "kind": "use", "text": "a right-angle USB-C cable plugs in and leaves at the back",
             "conditions": "phone on the seat, right-angle plug", "success": "plug and cable clear the part",
             "evidence": [{"joint": "plug through notch", "covers": "the plug head at rest, not the way in"}]}

    def setUp(self):
        super().setUp()
        write_stl("out/plug.stl", box(13, 8, 9, 50, 0, 0))                    # a proxy of the plug, not a part
        with open("plug.py", "w") as f:                                        # the proxy's own generator
            f.write("def build(p):\n    pass\n")
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl")
        fit_report("out/fit_plug.json", "out/box.stl", "out/plug.stl")

    def plug_dims(self, source="assumed", **extra):
        return {"id": "usb-c-plug", "what": "right-angle USB-C plug head and cable", "unit": "mm",
                "params": dict(self.PLUG), "source": source, **extra}

    def verify(self, promises, dims=None, joints=None, **more):
        v = self.full_verify()
        v["joints"] = joints if joints is not None else [
            {"name": "lid on box", "report": "out/fit_seat.json"},
            {"name": "plug through notch", "report": "out/fit_plug.json", "proxy": True, "dims": ["usb-c-plug"],
             "proxy_build": "out/plug_build.json"}]
        v["promises"] = promises
        v["dims"] = [self.plug_dims()] if dims is None else dims
        v.update(more)
        return v

    def record_proxy(self, values=None):
        """The proxy's own build, as `build.py run --proxy` leaves it: its params file (the plug's
        numbers only), a run manifest from that file, and the build JSON naming it. Written
        directly, so these tests need no engine."""
        import validate
        values = dict(self.PLUG if values is None else values)
        with open(".3dprint/plug.json", "w") as f:
            json.dump(values, f)
        validate.write_manifest("out/plug.stl", ["plug.py"], values, "python", by="run")
        with open("out/plug_build.json", "w") as f:
            json.dump({"schema": "3dprint-scout.build/1", "ran": True, "engine": "python", "sources": ["plug.py"],
                       "params": ".3dprint/plug.json", "proxy": True,
                       "parts": [{"name": "plug", "stl": "out/plug.stl",
                                  "sha256": validate.file_sha256("out/plug.stl")}]}, f)

    def run_use(self, verify, values=None, proxy=True, **extra):
        """params.json with the verify block and the plug values, recorded (the proxy too), then
        finalized."""
        self.params(verify, **dict(values or self.PLUG), **extra)
        self.record()
        if proxy:
            self.record_proxy(values)
        code, out = self.finalize()
        self.assertEqual(code, 0, out.get("errors"))
        return out

    @staticmethod
    def promise(out, pid):
        return next(p for p in out["promises"] if p["id"] == pid)

    def test_an_unmeasured_plug_makes_the_cable_promise_assumed(self):
        """The wave-curl case: the cable promise passed its fit only against an assumed plug."""
        out = self.run_use(self.verify([self.SEAT, self.CABLE]))
        self.assertEqual(out["geometry"], "verified", out["open"])             # the tiers stay apart
        self.assertEqual(out["use"], "assumed")
        self.assertEqual(self.promise(out, "seat")["state"], "verified")
        cable = self.promise(out, "cable-out")
        self.assertEqual((cable["state"], cable["rests_on"]), ("assumed", ["usb-c-plug"]))
        self.assertEqual(cable["evidence"], [{"joint": "plug through notch", "result": "passed",
                                              "covers": "the plug head at rest, not the way in"}])
        self.assertTrue(out["open"][0].startswith("promise 'cable-out' (use) assumed: rests on 'usb-c-plug'"),
                        out["open"])
        self.assertEqual(out["summary"][0], "use: assumed (2 promises: 1 assumed, 1 verified; 1 assumption not "
                                            "linked to a promise)")
        self.assertEqual(out["promise_counts"], {"use": {"verified": 1, "assumed": 1}})
        self.assertEqual(out["dims"][0]["state"], "assumed")

    def test_a_spec_value_is_shown_for_checking(self):
        where = {"plug_w": "table 3-2", "plug_h": "table 3-2", "plug_l": "fig. 3-5", "cable_d": "table 3-9"}
        out = self.run_use(self.verify([self.CABLE], dims=[self.plug_dims("spec", url="https://example.org/usb-c",
                                                                           where=where)]))
        self.assertEqual((out["use"], out["dims"][0]["state"]), ("verified", "spec"))
        self.assertIn("dims 'usb-c-plug' is taken from a spec, not checked here: compare plug_w = 13 (table 3-2); "
                      "plug_h = 8 (table 3-2); plug_l = 9 (fig. 3-5); cable_d = 4.5 (table 3-9) with "
                      "https://example.org/usb-c", out["open"])

    def test_measuring_the_plug_verifies_it(self):
        same = self.run_use(self.verify([self.SEAT, self.CABLE], dims=[self.plug_dims("caliper", by="user")]))
        self.assertEqual((same["use"], self.promise(same, "cable-out")["state"]), ("verified", "verified"))
        self.assertEqual(same["dims"][0]["state"], "measured")
        measured = dict(self.PLUG, plug_w=14)                                  # the plug was wider than assumed
        dims = [dict(self.plug_dims("caliper", by="user"), params=measured)]
        write_stl("out/plug.stl", box(14, 8, 9, 50, 0, 0))                    # the proxy built again from it
        out = self.run_use(self.verify([self.SEAT, self.CABLE], dims=dims), values=measured)
        cable = self.promise(out, "cable-out")
        self.assertEqual(cable["state"], "not verified")                       # its fit is of the old proxy
        self.assertIn("joint 'plug through notch': its fit report is not of the current parts", cable["reasons"])
        fit_report("out/fit_plug.json", "out/box.stl", "out/plug.stl")        # fitted again
        out = self.run_use(self.verify([self.SEAT, self.CABLE], dims=dims), values=measured)
        self.assertEqual((out["use"], self.promise(out, "cable-out")["state"]), ("verified", "verified"))

    def test_declaration_errors(self):
        """Reverse tests: a promise that is declared wrongly is an error, never verified."""
        seat, cable = self.SEAT, self.CABLE
        feature = {"id": "notch", "kind": "feature", "text": "a notch", "success": "6 mm wide"}
        cases = [
            ("a part's check as evidence", [dict(seat, evidence=[{"check": "box M1"}])], None,
             "'box M1' is a check of a part: it proves the part, not a promise"),
            ("the same id twice", [seat, dict(seat)], None, "the id is used more than once"),
            ("no such joint", [dict(seat, evidence=[{"joint": "nope"}])], None, "there is no joint 'nope' in _verify.joints"),
            ("evidence not read yet", [dict(seat, evidence=[{"seen": "out/x.png"}])], None, "unknown evidence kind 'seen'"),
            ("two kinds in one item", [dict(seat, evidence=[{"joint": "lid on box", "strength": "x"}])], None,
             "must name one of joint, strength"),
            ("a use without conditions", [{k: v for k, v in seat.items() if k != "conditions"}], None,
             "a use promise needs conditions"),
            ("a feature without success", [dict(feature, success="", evidence=[{"joint": "lid on box"}])], None,
             "a feature promise needs success"),
            ("strength for a feature", [dict(feature, evidence=[{"strength": "x"}])], None,
             "strength is not evidence for a feature promise (it takes joint)"),
            ("a typo in a field", [dict(seat, evidance=[])], None, "unknown field evidance"),
            ("a kind that does not exist", [dict(seat, kind="usage")], None, "kind must be one of use, feature, look"),
            ("an unknown dims id", [dict(seat, assumes=["phone"])], None, "the promise rests on dims 'phone', which is "
                                                                          "not in _verify.dims"),
            ("a caliper value nobody took", [cable], [self.plug_dims("caliper")],
             "dims 'usb-c-plug': a caliper value needs \"by\": \"user\""),
            ("a caliper value the agent took", [cable], [self.plug_dims("caliper", by="agent")], "needs \"by\": \"user\""),
            ("a spec without its url", [cable], [self.plug_dims("spec")], "a spec value needs the url"),
            ("a spec without where its numbers are", [cable],
             [self.plug_dims("spec", url="https://example.org/usb-c", where={"plug_w": "table 3-2"})],
             "the place in the spec its number comes from (missing: plug_h, plug_l, cable_d)"),
            ("a file value with no reading of it", [cable], [self.plug_dims("user-file", note="out/m.json")],
             "source must be one of assumed, caliper, spec"),
            ("dims that are not the model's numbers", [cable], [dict(self.plug_dims(), params=dict(self.PLUG, plug_w=12))],
             "plug_w is 12 here but 13 in params.json"),
            ("dims not in params.json", [cable], [dict(self.plug_dims(), params={"plug_depth": 9})],
             "plug_depth is not an engine parameter in params.json"),
            ("dims bound to metadata", [cable], [dict(self.plug_dims(), params={"_parts.box.expect": [40, 30, 20]})],
             "_parts.box.expect is not an engine parameter in params.json"),
        ]
        for name, promises, dims, message in cases:
            with self.subTest(name):
                out = self.run_use(self.verify(promises, dims=dims))
                self.assertEqual(out["use"], "error")
                self.assertEqual(promises[-1]["id"], out["promises"][-1]["id"])
                self.assertEqual(out["promises"][-1]["state"], "error")
                self.assertIn(message, "\n".join(out["open"]))
                self.assertEqual(out["geometry"], "verified", out["open"])     # the geometry is judged on its own

    def test_only_the_user_takes_a_promise_unverified(self):
        cable = dict(self.CABLE, evidence=[])
        for entry, message in (({"promise": "cable-out", "reason": "no plug here", "by": "agent"}, "only the user"),
                               ({"promise": "cable-out", "by": "user"}, "needs the user's reason"),
                               ({"promise": "cable", "reason": "x", "by": "user"}, "there is no promise 'cable'"),
                               ({"promise": "cable-out", "check": "box P2", "reason": "x", "by": "user"}, "not both")):
            with self.subTest(entry=entry):
                out = self.run_use(self.verify([self.SEAT, cable], accepted=[entry]))
                self.assertEqual(out["use"], "error")
                self.assertTrue(any(message in e for e in out["promise_errors"]), out["promise_errors"])
                self.assertEqual(self.promise(out, "cable-out")["state"], "not verified")
        out = self.run_use(self.verify([self.SEAT, cable], accepted=[
            {"promise": "cable-out", "reason": "the user tries the plug on the first print", "by": "user"}]))
        state = self.promise(out, "cable-out")
        self.assertEqual((out["use"], state["state"]), ("excluded", "excluded"))
        self.assertEqual(state["reasons"], ["taken by the user without verifying it: the user tries the plug on the "
                                            "first print", "no evidence yet"])

    def test_no_promises_or_an_empty_list_is_not_declared(self):
        for promises, line in ((None, "promises not declared (_verify.promises)"),
                               ([], "the promise list (_verify.promises) is empty: an empty list verifies nothing")):
            with self.subTest(promises=promises):
                v = self.full_verify()
                if promises is not None:
                    v["promises"] = promises
                out = self.run_use(v)
                self.assertEqual(out["use"], "not declared")
                self.assertTrue(out["open"][0].startswith(line), out["open"])
                self.assertEqual(out["summary"][0], "use: not declared (_verify.promises)")
                self.assertEqual(out["geometry"], "verified", out["open"])

    def test_a_failing_joint_beats_an_assumed_size(self):
        fit_report("out/fit_plug.json", "out/box.stl", "out/plug.stl", F3="FAIL")
        out = self.run_use(self.verify([self.SEAT, self.CABLE]))
        cable = self.promise(out, "cable-out")
        self.assertEqual((out["use"], cable["state"]), ("failed", "failed"))
        self.assertEqual(cable["reasons"][0], "joint 'plug through notch' failed")
        self.assertIn("rests on 'usb-c-plug' (right-angle USB-C plug head and cable), which is assumed, not measured",
                      cable["reasons"])
        out = self.run_use(self.verify([self.SEAT, self.CABLE], accepted=[
            {"promise": "cable-out", "reason": "ship it", "by": "user"}]))
        self.assertEqual(self.promise(out, "cable-out")["state"], "failed")     # a failure is never taken away

    def test_an_accepted_joint_warn_is_accepted_not_verified(self):
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl", F3="WARN")
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=[{"name": "lid on box", "report": "out/fit_seat.json"}]))
        self.assertEqual(self.promise(out, "seat")["state"], "not verified")
        self.assertEqual(out["geometry"], "not verified")
        self.assertTrue(any(o.startswith("joint 'lid on box': F3 WARN") for o in out["open"]), out["open"])
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=[{"name": "lid on box", "report": "out/fit_seat.json"}],
                                       accepted=[{"check": "joint lid  on box F3", "reason": "a snug lid"}]))
        self.assertEqual((out["use"], self.promise(out, "seat")["state"]), ("accepted", "accepted"))
        self.assertEqual(out["geometry"], "verified", out["open"])
        self.assertEqual(out["joints"][0]["accepted"], ["F3"])

    def test_strength_typed_in_does_not_verify_a_use(self):
        ribbon = {"id": "holds", "kind": "use", "text": "the ribbon holds the phone", "conditions": "a 240 g phone",
                  "success": "safety factor 2", "evidence": [{"strength": "ribbon"}]}
        for gate, state in (("PASS", "not verified"), ("WARN", "not verified"), ("FAIL", "failed")):
            with self.subTest(gate=gate):
                strength_report("out/strength_ribbon.json", gate)
                out = self.run_use(self.verify([ribbon], dims=[], strength=[{"name": "ribbon",
                                                                            "report": "out/strength_ribbon.json"}]))
                self.assertEqual(self.promise(out, "holds")["state"], state)
        strength_report("out/strength_ribbon.json", "WARN")                    # accepted as "member <name>"
        members = [{"name": "ribbon", "report": "out/strength_ribbon.json"}]
        out = self.run_use(self.verify([ribbon], dims=[], strength=members, accepted=[
            {"check": "member ribbon", "reason": "the user prints it first"}]))
        self.assertEqual((out["strength"][0]["result"], out["geometry"]), ("accepted", "verified"))
        self.assertEqual(self.promise(out, "holds")["state"], "not verified")   # still typed in
        strength_report("out/strength_ribbon.json", "FAIL")                    # a FAIL is never accepted
        out = self.run_use(self.verify([ribbon], dims=[], strength=members, accepted=[
            {"check": "member ribbon", "reason": "the user prints it first"}]))
        self.assertEqual((out["strength"][0]["result"], out["geometry"]), ("failed", "not verified"))
        strength_report("out/strength_ribbon.json", "PASS")
        out = self.run_use(self.verify([ribbon], dims=[], strength=[{"name": "ribbon", "report": "out/strength_ribbon.json"}]))
        self.assertIn("member 'ribbon': its inputs were typed in, not taken from the build's parameters",
                      self.promise(out, "holds")["reasons"])

    def test_a_proxy_is_tied_to_its_sizes_by_its_build(self):
        """Codex review of step 1 (P1): naming measured dims proves nothing unless the proxy was
        built from them; its build JSON and manifest tie it to params.json as it is now."""
        caliper = [self.plug_dims("caliper", by="user")]
        joints = self.verify([])["joints"]
        untied = [joints[0], {k: v for k, v in joints[1].items() if k != "proxy_build"}]
        out = self.run_use(self.verify([self.CABLE], dims=caliper, joints=untied))
        cable = self.promise(out, "cable-out")
        self.assertEqual(cable["state"], "assumed")
        self.assertEqual(cable["reasons"], ["joint 'plug through notch' names the sizes of its proxy, but nothing ties "
                                            "the proxy to them: no proxy_build names the build.py run that made the "
                                            "proxy"])
        self.assertEqual(self.promise(self.run_use(self.verify([self.CABLE], dims=caliper)), "cable-out")["state"],
                         "verified")
        wider = dict(self.PLUG, plug_w=14)                                      # measured again, the proxy not rebuilt
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params=wider)]), values=wider, proxy=False)
        cable = self.promise(out, "cable-out")
        self.assertEqual((cable["state"], out["joints"][1]["proxy_build"]), ("not verified", "tied"))
        self.assertIn("joint 'plug through notch': the proxy was built from plug_w = 13, not the values its dims "
                      "declare", cable["reasons"])
        with open(".3dprint/plug.json", "w") as f:                             # its numbers edited, not rebuilt
            json.dump(wider, f)
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params=wider)]), values=wider, proxy=False)
        self.assertEqual(out["joints"][1]["proxy_build"], "stale")
        self.assertIn("joint 'plug through notch': the proxy out/plug.stl was not built from .3dprint/plug.json as it "
                      "is now (or its generator changed): build it again and fit again",
                      self.promise(out, "cable-out")["reasons"])
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params={"plug_w": 13})]))
        cable = self.promise(out, "cable-out")                                 # ninth review (P1): dims cover one
        self.assertEqual(cable["state"], "assumed")                           # of the proxy's four numbers
        self.assertEqual(cable["reasons"], ["joint 'plug through notch': the proxy was also built from plug_h, plug_l, "
                                            "cable_d, which no dims entry it names declares"])
        nested = {"plug": {"w": 13, "h": 8, "l": 9}, "cable_d": 4.5}          # eleventh review (P2): nested numbers
        dims = [dict(caliper[0], params={"plug.w": 13, "plug.h": 8, "plug.l": 9, "cable_d": 4.5})]
        out = self.run_use(self.verify([self.CABLE], dims=dims), values=nested)
        self.assertEqual(self.promise(out, "cable-out")["state"], "verified", self.promise(out, "cable-out")["reasons"])
        self.record_proxy({"plug_w": 13, "plug_h": 8, "plug_l": 9})            # and the other way round
        out = self.run_use(self.verify([self.CABLE], dims=caliper), proxy=False)
        self.assertEqual(self.promise(out, "cable-out")["reasons"],
                         ["joint 'plug through notch': the proxy was not given cable_d, which its dims declare"])
        self.record_proxy(wider)
        with open("out/plug.stl.manifest.json", "w") as f:                    # JSON, but not a manifest
            json.dump([], f)
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params=wider)]), values=wider, proxy=False)
        self.assertIn("joint 'plug through notch': the proxy out/plug.stl has a malformed build manifest",
                      self.promise(out, "cable-out")["reasons"])
        self.record_proxy(wider)
        with open("out/plug.stl.manifest.json") as f:
            man = json.load(f)
        with open("out/plug.stl.manifest.json", "w") as f:                    # a source that is not a name
            json.dump(dict(man, sources=[[]]), f)
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params=wider)]), values=wider, proxy=False)
        self.assertIn("joint 'plug through notch': the proxy out/plug.stl has a malformed build manifest",
                      self.promise(out, "cable-out")["reasons"])
        os.remove("out/plug.stl.manifest.json")                                # a proxy made elsewhere, taken in
        code, rec = run(build, "record", "out/plug.stl", "--source", "plug.py", "--params", ".3dprint/params.json",
                        "--out", "out", "--no-wall-check", "--no-3mf")
        with open("out/plug_build.json", "w") as f:
            json.dump(rec, f)
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params=wider)]), values=wider, proxy=False)
        cable = self.promise(out, "cable-out")
        self.assertEqual(cable["state"], "assumed")                           # Codex review of step 1 (P1)
        self.assertIn("the proxy out/plug.stl was recorded (build.py record), not generated from its params by "
                      "build.py run", cable["reasons"][0])
        self.record_proxy(wider)                                               # fifth review (P1): a fit of two parts
        fit_report("out/fit_plug.json", "out/box.stl", "out/lid.stl")          # named as the proxy's joint
        out = self.run_use(self.verify([self.CABLE], dims=[dict(caliper[0], params=wider)]), values=wider, proxy=False)
        self.assertIn("joint 'plug through notch': the fit report measured no proxy, only parts of this build: drop "
                      "\"proxy\" or fit the proxy", self.promise(out, "cable-out")["reasons"])
        self.assertEqual(self.promise(out, "cable-out")["state"], "not verified")
        fit_report("out/fit_plug.json", "out/box.stl", "out/plug.stl")
        os.remove("out/plug_build.json")
        out = self.run_use(self.verify([self.CABLE], dims=caliper), proxy=False)
        self.assertIn("proxy build out/plug_build.json", "\n".join(self.promise(out, "cable-out")["reasons"]))

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_a_proxy_generated_by_build_run(self):
        """The whole path: a proxy generator run by build.py from its own params file, fitted, tied."""
        with open("plug.py", "w") as f:
            f.write("import manifold3d as m3d\n"
                    "def build(p):\n"
                    "    return {'plug': m3d.Manifold.cube([p['plug_w'], p['plug_h'], p['plug_l']]).translate([50, 0, 0])}\n")
        caliper = [self.plug_dims("caliper", by="user")]
        joint = dict(self.verify([])["joints"][1], proxy_build="out/plug/build.json")
        self.params(self.verify([self.CABLE], dims=caliper, joints=[joint]), **self.PLUG)
        self.record()
        with open(".3dprint/plug.json", "w") as f:                             # the proxy's numbers only
            json.dump(self.PLUG, f)
        code, built = run(build, "run", "plug.py", "--params", ".3dprint/plug.json", "--proxy", "plug",
                          "--out", "out/plug", "--no-wall-check")
        self.assertEqual(code, 0, built.get("errors"))
        self.assertEqual((built["proxy"], built.get("threemf")), (True, None))    # never delivered
        with open("out/plug/build.json", "w") as f:
            json.dump(built, f)
        fit_report("out/fit_plug.json", "out/box.stl", "out/plug/plug.stl")
        code, out = self.finalize()
        self.assertEqual((out["joints"][0]["proxy_build"], self.promise(out, "cable-out")["state"]), ("tied", "verified"))
        self.params(self.verify([self.CABLE], dims=[dict(caliper[0], params=dict(self.PLUG, plug_w=14))], joints=[joint]),
                    **dict(self.PLUG, plug_w=14))                               # measured again, not rebuilt
        self.record()
        code, out = self.finalize()
        self.assertEqual((out["joints"][0]["proxy_build"], self.promise(out, "cable-out")["state"]),
                         ("tied", "not verified"))                              # built from 13, measured 14
        with open(".3dprint/plug.json", "w") as f:
            json.dump(dict(self.PLUG, plug_w=14), f)
        code, out = self.finalize()
        self.assertEqual((out["joints"][0]["proxy_build"], self.promise(out, "cable-out")["state"]),
                         ("stale", "not verified"))                              # its numbers changed, not rebuilt
        for extra, message in ((["--proxy", "box"], "--proxy names parts of _parts (box)"),
                               (["--proxy", "plug", "--only", "box"], "--proxy and --only do not go together"),
                               (["--proxy", " , "], "--proxy names no part")):
            code, bad = run(build, "run", "plug.py", "--params", ".3dprint/params.json", "--out", "out/plug2", *extra)
            self.assertEqual(code, 1, bad)
            self.assertIn(message, bad["errors"][0])

    def test_a_malformed_acceptance_accepts_nothing(self):
        """Codex review of step 1 (P2): an entry naming both a check and a promise is an error,
        and its check is not taken either."""
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl", F3="WARN")
        joints = [{"name": "lid on box", "report": "out/fit_seat.json"}]
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=joints, accepted=[
            {"check": "joint lid on box F3", "promise": "seat", "reason": "x", "by": "user"}]))
        self.assertEqual((out["use"], out["geometry"]), ("error", "not verified"))
        self.assertTrue(any(o.startswith("joint 'lid on box': F3 WARN") for o in out["open"]), out["open"])
        self.assertNotIn("accepted", out["joints"][0])
        for entry in ({"check": "joint lid on box F3"}, {"check": "joint lid on box F3", "reason": ["x"]},
                      {"check": ["joint lid on box F3"], "reason": "x"}):              # fourth review (P2)
            with self.subTest(entry=entry):
                out = self.run_use(self.verify([self.SEAT], dims=[], joints=joints, accepted=[entry]))
                self.assertEqual((out["use"], out["geometry"]), ("error", "not verified"))
                self.assertEqual(self.promise(out, "seat")["state"], "not verified")
                self.assertTrue(any("it accepts nothing" in o for o in out["open"]), out["open"])
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl")              # eighth review (P2): even with
        for entry in ({}, {"check": "box P2", "reason": []}, {"reason": "x"}):     # nothing to accept, a malformed
            with self.subTest(entry=entry):                                         # entry is a declaration error
                out = self.run_use(self.verify([self.SEAT], dims=[], joints=joints, accepted=[entry]))
                self.assertEqual((out["use"], self.promise(out, "seat")["state"]), ("error", "verified"))
                self.assertTrue(any("it accepts nothing" in e for e in out["promise_errors"]), out["promise_errors"])

    def test_a_joint_passes_only_with_its_fit_check(self):
        """Codex review of step 1 (P2): a report without F3 (or without the sweep a moving joint
        declares) is not a passed fit, whatever else it holds."""
        joints = [{"name": "lid on box", "report": "out/fit_seat.json"}]
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl", F3_other="PASS")
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=joints))
        self.assertEqual((out["joints"][0]["result"], self.promise(out, "seat")["state"]), ("open", "not verified"))
        self.assertIn("joint 'lid on box': the report has no F3", out["open"])
        self.assertEqual(out["geometry"], "not verified")
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl")
        moving = [dict(joints[0], sweep=True)]
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=moving))
        self.assertEqual(self.promise(out, "seat")["state"], "not verified")
        self.assertIn("joint 'lid on box': the report has no F3_sweep (run fit.py with --sweep-angles)", out["open"])
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl", F3="PASS", F3_sweep="PASS")
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=moving))
        self.assertEqual((self.promise(out, "seat")["state"], out["geometry"]), ("verified", "verified"))
        self.params(self.verify([self.SEAT], dims=[], joints=[dict(joints[0], sweep="yes")]))
        code, out = self.finalize()
        self.assertEqual(code, 1)
        self.assertIn("sweep must be true or false", out["errors"][0])

    def test_a_proxy_without_its_sizes_is_assumed(self):
        joints = [{"name": "plug through notch", "report": "out/fit_plug.json", "proxy": True}]
        out = self.run_use(self.verify([self.CABLE], dims=[], joints=joints))
        cable = self.promise(out, "cable-out")
        self.assertEqual(cable["state"], "assumed")
        self.assertEqual(cable["reasons"], ["joint 'plug through notch' is fitted against a proxy whose sizes are not "
                                            "declared (dims)"])

    def test_stale_evidence_or_a_failing_part_does_not_verify(self):
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 31))                    # the lid changed after its fit
        out = self.run_use(self.verify([self.SEAT, self.CABLE]))
        self.assertEqual(self.promise(out, "seat")["state"], "not verified")
        self.assertIn("joint 'lid on box': its fit report is not of the current parts",
                      self.promise(out, "seat")["reasons"])
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl")
        out = self.run_use(self.verify([self.SEAT]), _parts={"box": {"expect": [50, 30, 20]},
                                                             "lid": {"expect": [40, 30, 3]}})
        self.assertEqual(out["parts"][0]["gate"], "FAIL")                      # box D1: 40 mm, not 50
        self.assertIn("joint 'lid on box' fitted box, whose own checks FAIL", self.promise(out, "seat")["reasons"])
        self.assertEqual(self.promise(out, "seat")["state"], "not verified")

    def test_malformed_values_are_declaration_errors(self):
        """Codex review of step 1 (P2): a list where a name belongs gave a traceback."""
        seat = self.SEAT
        for promises, accepted, dims in (
                ([dict(seat, evidence=[{"joint": []}])], [], None),
                ([dict(seat, evidence=[{"joint": {"a": 1}}])], [], None),
                ([dict(seat, evidence=[{"strength": 3}])], [], None),
                ([dict(seat, id=["seat"])], [], None),
                ([dict(seat, kind=["use"])], [], None),
                ([dict(seat, kind=[], evidence=[{"check": "box M1"}])], [], None),
                ([seat], [{"promise": ["seat"], "reason": "x", "by": "user"}], None),
                ([seat], [], [dict(self.plug_dims(), id=["usb-c-plug"])]),
                ([seat], [], [dict(self.plug_dims(), source=["assumed"], tol="0.5")])):
            with self.subTest(promises=promises, accepted=accepted, dims=dims):
                out = self.run_use(self.verify(promises, dims=dims, accepted=accepted))
                self.assertEqual(out["use"], "error", out["open"])
        self.params(self.verify([seat], joints=[{"name": ["lid on box"], "report": "out/fit_seat.json"}]))
        code, out = self.finalize()
        self.assertEqual(code, 1)
        self.assertIn("_verify.joints: name must be text", out["errors"][0])

    def test_identical_parts_keep_their_names(self):
        """Codex review of step 1 (P2): two byte-identical parts share a hash; a fit between them
        measured both, and a failing one is not hidden behind the other's name."""
        write_stl("out/lid.stl", box(40, 30, 20))                              # the same bytes as the box
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl")
        out = self.run_use(self.verify([self.SEAT], dims=[], joints=[{"name": "lid on box", "report": "out/fit_seat.json"}]),
                           _parts={"box": {"expect": [50, 30, 20]}, "lid": {"expect": [40, 30, 20]}})
        self.assertEqual(out["joints"][0]["measured"], ["box", "lid"])
        self.assertEqual([p["gate"] for p in out["parts"]], ["FAIL", "PASS"])
        self.assertIn("joint 'lid on box' fitted box, whose own checks FAIL", self.promise(out, "seat")["reasons"])
        os.makedirs("deliver")
        shutil.copyfile("out/box.stl", "deliver/box.stl")
        shutil.copyfile("out/lid.stl", "deliver/lid.stl")
        code, fin = self.finalize("--deliver", "deliver")
        self.assertEqual({d["file"]: d["part"] for d in fin["delivered"]}, {"deliver/box.stl": "box", "deliver/lid.stl": "lid"})
        self.assertFalse(any("not in the delivery" in o for o in fin["open"]), fin["open"])
        os.remove("deliver/lid.stl")                                           # one file for two parts is not enough
        code, fin = self.finalize("--deliver", "deliver")
        self.assertIn("lid: not in the delivery (deliver) as an STL or in a 3MF", fin["open"])

    def test_the_tier_is_the_worst_promise(self):
        nothing = {"id": "label", "kind": "look", "text": "the name on the front"}
        out = self.run_use(self.verify([self.SEAT, self.CABLE, nothing]))
        self.assertEqual([p["state"] for p in out["promises"]], ["verified", "assumed", "not verified"])
        self.assertEqual(out["use"], "not verified")
        self.assertEqual(out["promise_counts"], {"use": {"verified": 1, "assumed": 1}, "look": {"not verified": 1}})
        self.assertEqual(out["open"][1], "promise 'label' (look) not verified: no evidence yet")
        out = self.run_use(self.verify([self.SEAT, self.CABLE, nothing, dict(nothing, id="badge")], accepted=[
            {"promise": "badge", "reason": "the user judges it on the print", "by": "user"}]))
        self.assertEqual([p["state"] for p in out["promises"]], ["verified", "assumed", "not verified", "excluded"])
        self.assertEqual(out["use"], "not verified")             # an unagreed gap weighs more than an agreed one


if __name__ == "__main__":
    unittest.main()
