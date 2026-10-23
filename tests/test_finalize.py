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
HAS_NP = find_spec("numpy") is not None


def measure_report(path, *argv):
    """A saved measure.py report (with --expect, as finalize reads it)."""
    import measure
    code, rep = run(measure, *argv)
    assert code == 0, rep["errors"]
    with open(path, "w") as f:
        json.dump(rep, f)
    return rep


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
        self.assertEqual(sorted(out["bundle"]), ["deliver/source/REPRODUCE.md", "deliver/source/deliver/box.stl",
                                                 "deliver/source/deliver/lid.stl", "deliver/source/gen.py",
                                                 "deliver/source/params.json", "deliver/source/printers.json",
                                                 "deliver/source/verification.json"])     # the delivery as judged
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


def linked_report(path, gate="PASS", part="lid", material="pla_basic", sha=None, links=None, typed=None, **change):
    """A strength.py --from-build report as contract 2 of step 4 writes it: the inputs in links
    (input -> (param, value)) taken from the build's parameters, the load from the table, sf by
    default, the material from the build's part, and typed ({input: value}) given on the command
    line. Written directly, so the test says what finalize reads."""
    import validate
    links = {"h": ("ribbon_t", 4.5), "b": ("ribbon_w", 12), "length": ("ribbon_l", 30)} if links is None else links
    inputs = {k: v for k, (_p, v) in links.items()}
    origins = {k: f"param:{p}" for k, (p, _v) in links.items()}
    inputs.update(load="finger_pull", material=material, sf=2.0)
    origins.update(load="table:finger_pull", material="build:material", sf="default:sf")
    for k, v in (typed or {}).items():
        inputs[k], origins[k] = v, "manual"
    rep = {"schema": "3dprint-scout.strength/1", "ran": True, "gate": gate, "case": "beam",
           "worst": {"check": "bending", "sf_achieved": 2.6}, "inputs": inputs, "inputs_from": origins,
           "material": {"key": material},
           "from_build": {"build": "out/build.json", "part": part,
                          "sha256": sha or validate.file_sha256(os.path.join("out", part + ".stl")), "material": material,
                          "parameters": {k: {"param": p, "value": v} for k, (p, v) in links.items()}}}
    rep.update(change)
    with open(path, "w") as f:
        json.dump(rep, f)
    return rep


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
            json.dump({"schema": "3dprint-scout.build/1", "ran": True, "command": "run", "engine": "python",
                       "sources": ["plug.py"], "params": ".3dprint/plug.json", "proxy": True,
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
        # A prototype (phase 4): the _assumptions line belongs to its promise while that promise is
        # not verified, and is not counted as an assumption on its own; a dims note is shown.
        proto = "cable-out: delivered as a prototype, not verified"
        noted = [dict(dims[0], note="read off the user's own plug")]
        write_stl("out/plug.stl", box(14.5, 8, 9, 50, 0, 0))                  # the proxy changed, not fitted again
        out = self.run_use(self.verify([self.SEAT, self.CABLE], dims=noted), values=measured,
                           _assumptions=[proto, "the stand sits on a flat desk", "seat: no proof"])
        cable = self.promise(out, "cable-out")
        self.assertEqual((cable["state"], cable.get("prototype")), ("not verified", True))
        self.assertNotIn("prototype", self.promise(out, "seat"))
        self.assertTrue(out["summary"][0].endswith("; delivered as a prototype: cable-out; 2 assumptions not linked "
                                                   "to a promise)"), out["summary"][0])
        self.assertEqual(out["dims"][0]["note"], "read off the user's own plug")
        fit_report("out/fit_plug.json", "out/box.stl", "out/plug.stl")        # verified now: the line is a plain one
        out = self.run_use(self.verify([self.SEAT, self.CABLE], dims=noted), values=measured, _assumptions=[proto])
        self.assertNotIn("prototype", self.promise(out, "cable-out"))
        self.assertTrue(out["summary"][0].endswith("(2 promises: 2 verified; 1 assumption not linked to a promise)"),
                        out["summary"][0])
        out = self.run_use(self.verify([self.SEAT, self.CABLE], dims=noted), values=measured,
                           _assumptions=["lid: delivered as a prototype, not verified"])     # no such promise
        self.assertTrue(out["summary"][0].endswith("1 assumption not linked to a promise)"), out["summary"][0])
        # The part under the proxy rebuilt, the joint not fitted again: the reason names the part's change.
        write_stl("out/box.stl", box(61, 40, 30))
        out = self.run_use(self.verify([self.SEAT, self.CABLE], dims=dims), values=measured)
        cable = self.promise(out, "cable-out")
        self.assertEqual(cable["state"], "not verified")
        self.assertIn("joint 'plug through notch': the part it was fitted to has changed since", cable["reasons"])
        self.assertIn("joint 'plug through notch': the part it was fitted to has changed since (neither STL the "
                      "report measured is a part of this build now): run fit.py again", out["open"])

    BEND = {"id": "cable-bend", "kind": "use", "text": "the cable bends down without a kink",
            "conditions": "the user's own cable", "success": "no sharp bend at the lip", "evidence": []}

    def run_prototype(self, line):
        """The seat verified, the cable bend with no evidence yet, and one _assumptions line."""
        out = self.run_use(self.verify([self.SEAT, self.BEND]), _assumptions=[line])
        self.assertEqual(self.promise(out, "cable-bend")["state"], "not verified")
        self.assertEqual(out["assumptions"], [line])                          # echoed as written
        return out

    def test_a_prototype_line_with_a_note_marks_the_promise(self):
        """The line may end with a note in parentheses saying who chose the prototype (phase 4)."""
        for note in ('(the user: "I have no time for a test print now, just go on")',
                     "(the user handed the decision to me)", "(unattended run)"):
            out = self.run_prototype(f"cable-bend: delivered as a prototype, not verified {note}")
            self.assertTrue(self.promise(out, "cable-bend").get("prototype"), note)
            self.assertEqual(out["summary"][0], "use: not verified (2 promises: 1 not verified, 1 verified; "
                                                "delivered as a prototype: cable-bend)", note)

    def test_a_prototype_line_without_a_note_still_marks_it(self):
        out = self.run_prototype("cable-bend: delivered as a prototype, not verified")
        self.assertTrue(self.promise(out, "cable-bend").get("prototype"))
        self.assertEqual(out["summary"][0], "use: not verified (2 promises: 1 not verified, 1 verified; "
                                            "delivered as a prototype: cable-bend)")

    def test_other_text_after_not_verified_is_no_prototype_line(self):
        """Only a parenthesised note may follow: anything else is a plain assumption."""
        for line in ("cable-bend: delivered as a prototype, not verified yet",
                     "cable-bend: delivered as a prototype, not verified, not verified yet",
                     "cable-bend: delivered as a prototype, not verified (",
                     "cable-bend: delivered as a prototype, not verified (the user) and more"):
            out = self.run_prototype(line)
            self.assertNotIn("prototype", self.promise(out, "cable-bend"), line)
            self.assertEqual(out["summary"][0], "use: not verified (2 promises: 1 not verified, 1 verified; "
                                                "1 assumption not linked to a promise)", line)

    def test_declaration_errors(self):
        """Reverse tests: a promise that is declared wrongly is an error, never verified."""
        seat, cable = self.SEAT, self.CABLE
        feature = {"id": "notch", "kind": "feature", "text": "a notch", "success": "6 mm wide"}
        cases = [
            ("a part's check as evidence", [dict(seat, evidence=[{"check": "box M1"}])], None,
             "'box M1' is a check of a part: it proves the part, not a promise"),
            ("the same id twice", [seat, dict(seat)], None, "the id is used more than once"),
            ("no such joint", [dict(seat, evidence=[{"joint": "nope"}])], None, "there is no joint 'nope' in _verify.joints"),
            ("a viewing for a use", [dict(seat, evidence=[{"seen": "out/x.png"}])], None,
             "seen is not evidence for a use promise (it takes joint, strength, measurement, test_print)"),
            ("evidence not read", [dict(seat, evidence=[{"photo": "out/x.jpg"}])], None, "unknown evidence kind 'photo'"),
            ("two kinds in one item", [dict(seat, evidence=[{"joint": "lid on box", "strength": "x"}])], None,
             "must name one of joint, strength"),
            ("a use without conditions", [{k: v for k, v in seat.items() if k != "conditions"}], None,
             "a use promise needs conditions"),
            ("a feature without success", [dict(feature, success="", evidence=[{"joint": "lid on box"}])], None,
             "a feature promise needs success"),
            ("strength for a feature", [dict(feature, evidence=[{"strength": "x"}])], None,
             "strength is not evidence for a feature promise (it takes joint, measurement, test_print)"),
            ("a typo in a field", [dict(seat, evidance=[])], None, "unknown field evidance"),
            ("a measurement for a look", [{"id": "look", "kind": "look", "text": "a wave",
                                           "evidence": [{"measurement": "m"}]}], None,
             "measurement is not evidence for a look promise"),
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
             "needs from, for each parameter, the name of the measurement of that file it was read from"),
            ("a file value with no tolerance", [cable], [self.plug_dims("user-file", **{"from": {
                "plug_w": "w", "plug_h": "h", "plug_l": "l", "cable_d": "d"}})], "needs tol"),
            ("a file value read by no measurement", [cable], [self.plug_dims("user-file", tol=0.1, **{"from": {
                "plug_w": "w", "plug_h": "h", "plug_l": "l", "cable_d": "d"}})],
             "plug_w comes from measurement 'w', which is not in _verify.measurements"),
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

    @unittest.skipUnless(HAS_NP, "numpy not installed")
    def test_a_measurement_confirms_a_size_on_the_built_part(self):
        """0.7.0 step 2: a hand-calculated size is reported only once the built STL is measured."""
        depth = {"id": "depth", "kind": "feature", "text": "the box is 30 mm deep", "success": "30 mm within 0.05",
                 "evidence": [{"measurement": "box depth"}]}
        members = {"measurements": [{"name": "box depth", "report": "out/m_depth.json"}]}
        measure_report("out/m_depth.json", "slice", "out/box.stl", "--z", "10", "--expect",
                       "levels[0].loops[0].size[1]=30", "--tol", "0.05")
        out = self.run_use(self.verify([depth], dims=[], **members))
        self.assertEqual((out["use"], self.promise(out, "depth")["state"]), ("verified", "verified"))
        self.assertEqual(out["measurements"][0]["measured"], ["box"])
        measure_report("out/m_depth.json", "slice", "out/box.stl", "--z", "10", "--expect",
                       "levels[0].loops[0].size[1]=31", "--tol", "0.05")
        out = self.run_use(self.verify([depth], dims=[], **members))
        self.assertEqual(self.promise(out, "depth")["state"], "failed")
        self.assertIn("measurement 'box depth' failed: levels[0].loops[0].size[1] = 30.0, expected = 31.0",
                      self.promise(out, "depth")["reasons"])
        write_stl("out/box.stl", box(40, 32, 20))                              # rebuilt after the measurement
        out = self.run_use(self.verify([depth], dims=[], **members))
        self.assertEqual(self.promise(out, "depth")["reasons"],
                         ["measurement 'box depth': the file it measured has changed since, or is gone"])
        write_stl("out/other.stl", box(40, 30, 20, 0, 0, 0))                  # not a part of this build
        measure_report("out/m_depth.json", "slice", "out/other.stl", "--z", "10", "--expect",
                       "levels[0].loops[0].size[1]=30", "--tol", "0.05")
        out = self.run_use(self.verify([depth], dims=[], **members))
        self.assertIn("measurement 'box depth': it read out/other.stl, which is not a part of this build",
                      self.promise(out, "depth")["reasons"])
        good = measure_report("out/m_depth.json", "slice", "out/box.stl", "--z", "10", "--expect",
                              "levels[0].loops[0].size[1]=31", "--tol", "0.05")          # a FAIL, then edited by hand
        e0 = good["expect"][0]
        for edit, message in (({"expect": [{"state": "PASS"}], "gate": "PASS"}, "lacks its path, op or target"),
                              ({"expect": [dict(e0, value=31.0, state="PASS")], "gate": "PASS"},
                               f"value 31.0 is not what measure.py reads from the file now ({e0['value']})"),
                              ({"expect": [dict(e0, value=31.0, state="PASS")], "gate": "PASS",
                                "levels": [{"level": 10, "loops": [{"size": [40, 31.0]}]}]},
                               f"value 31.0 is not what measure.py reads from the file now ({e0['value']})"),
                              ({"query": dict(good["query"], cmd="volume")}, "records no command"),
                              ({"expect": [dict(e0, target=10 ** 400)]}, "lacks its path, op or target"),
                              ({"expect": [dict(e0, tol=10 ** 400)]}, "has no tol"),
                              ({"expect": [dict(e0, state="PASS")], "gate": "PASS"}, "does not follow from its numbers"),
                              ({"gate": "PASS"}, "its gate does not follow"),
                              ({"expect": [dict(e0, tol=None)]}, "has no tol"),
                              ({"expect": [dict(e0, path="levels[0].loops[5].size[1]")]}, "index [5] is outside")):
            with self.subTest(edit=edit):                                       # Codex review of step 2 (P1)
                with open("out/m_depth.json", "w") as f:
                    json.dump(dict(good, **edit), f)
                out = self.run_use(self.verify([depth], dims=[], **members))
                self.assertEqual((out["measurements"][0]["result"], self.promise(out, "depth")["state"]),
                                 ("missing", "not verified"))
                self.assertIn(message, out["measurements"][0]["note"])
        measure_report("out/m_depth.json", "slice", "out/box.stl", "--z", "10")  # no --expect
        out = self.run_use(self.verify([depth], dims=[], **members))
        self.assertEqual(self.promise(out, "depth")["reasons"],
                         ["measurement 'box depth': no report (out/m_depth.json has no expectations "
                          "(measure.py --expect))"])

    @unittest.skipUnless(HAS_NP, "numpy not installed")
    def test_a_size_read_from_the_users_file(self):
        """0.7.0 step 2: a user-file dims entry is backed only by a fresh, passed measurement of
        that file whose value is the params value within tol (Codex review of the plan, #17)."""
        os.makedirs("ref")
        write_stl("ref/plug.stl", box(13.1, 8, 9))                            # the user's model of the plug
        measure_report("out/m_plug.json", "info", "ref/plug.stl", "--expect", "objects[0].size_mm[0]=13", "--tol", "0.2")
        head = {"id": "plug-head", "what": "plug head width, from the maker's model", "params": {"plug_w": 13.1},
                "source": "user-file", "from": {"plug_w": "plug width"}, "tol": 0.05}
        rest = dict(self.plug_dims("caliper", by="user"), id="plug-rest",
                    params={"plug_h": 8, "plug_l": 9, "cable_d": 4.5})
        joints = [dict(self.verify([])["joints"][1], dims=["plug-head", "plug-rest"])]
        values = dict(self.PLUG, plug_w=13.1)
        members = {"measurements": [{"name": "plug width", "report": "out/m_plug.json"}]}
        out = self.run_use(self.verify([self.CABLE], dims=[head, rest], joints=joints, **members), values=values)
        self.assertEqual([d["state"] for d in out["dims"]], ["measured", "measured"])
        self.assertEqual(self.promise(out, "cable-out")["state"], "verified", self.promise(out, "cable-out")["reasons"])
        far = dict(values, plug_w=13.4)                                        # the model's number is not the reading
        out = self.run_use(self.verify([self.CABLE], dims=[dict(head, params={"plug_w": 13.4}), rest], joints=joints,
                                       **members), values=far)
        self.assertEqual(out["dims"][0]["state"], "unbacked")
        self.assertIn("dims 'plug-head' is not backed by its measurements: plug_w: measurement 'plug width' read 13.1, "
                      "not 13.4 within 0.05", self.promise(out, "cable-out")["reasons"])
        out = self.run_use(self.verify([self.CABLE], dims=[dict(head, tol=10 ** 400), rest], joints=joints, **members),
                           values=values)
        self.assertIn("dims 'plug-head': tol must be a number of 0 or more", out["promise_errors"])  # step 2 review
        write_stl("ref/plug.stl", box(13.2, 8, 9))                            # the file changed after its reading
        out = self.run_use(self.verify([self.CABLE], dims=[head, rest], joints=joints, **members), values=values)
        self.assertEqual(out["dims"][0]["problems"], ["plug_w: measurement 'plug width' is stale (the file it measured "
                                                      "(ref/plug.stl) has changed since, or is gone)"])
        measure_report("out/m_plug.json", "info", "out/box.stl", "--expect", "objects[0].size_mm[0]=40", "--tol", "0.2")
        out = self.run_use(self.verify([self.CABLE], dims=[dict(head, params={"plug_w": 40})], joints=joints, **members),
                           values=dict(values, plug_w=40))
        self.assertEqual(out["dims"][0]["problems"], ["plug_w: measurement 'plug width' read box, a part of this build, "
                                                      "not the user's file"])

    @unittest.skipUnless(HAS_NP, "numpy not installed")
    def test_a_look_is_judged_on_an_image_of_these_parts(self):
        """0.7.0 step 3: a look promise is verified by the user's judgement of an image whose
        sidecar ties it to the parts as they are now, and only for the promises they judged."""
        import preview
        import validate

        def draw(*extra):
            code, rep = run(preview, "out/box.stl", "out/lid.stl", "-o", "out/look.png", "--size", "400x300", *extra)
            self.assertEqual(code, 0, rep["errors"])
            return validate.file_sha256("out/look.png")

        wave = {"id": "wave", "kind": "look", "text": "the lid sits flush", "evidence": [{"seen": "front look"}]}
        judged = {"name": "front look", "image": "out/look.png", "by": "user", "promises": ["wave"], "result": "passed"}

        def judge(**change):
            return self.run_use(self.verify([wave], dims=[], seen=[dict(judged, **change)]))

        sha = draw()
        judged["image_sha256"] = sha
        out = judge()
        self.assertEqual((out["use"], out["seen"][0]["shows"]), ("verified", ["box", "lid"]))
        self.assertEqual(self.promise(judge(by="agent"), "wave")["reasons"], ["seen 'front look': only the agent looked at it"])
        self.assertEqual(self.promise(judge(result="failed"), "wave")["state"], "failed")
        out = judge(promises=["other"])
        self.assertEqual(self.promise(out, "wave")["reasons"], ["seen 'front look' does not list this promise (its promises "
                                                                 "are what it checked)"])
        out = judge(by="robot")
        self.assertEqual(out["use"], "error")
        self.assertIn('seen \'front look\': by must be "user" or "agent" (who looked)', out["promise_errors"])
        shutil.copyfile("out/look.png", "out/look_judged.png")
        draw("--size", "500x300", "--overwrite")                                # drawn again at the same path
        self.assertIn("the image is not the one that was judged", self.promise(judge(), "wave")["reasons"][0])
        shutil.copyfile("out/look_judged.png", "out/look.png")                 # the old pixels next to the new sidecar
        self.assertIn("describes another image", self.promise(judge(), "wave")["reasons"][0])
        sha = draw("--overwrite")
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 31))                    # the lid changed after the drawing
        out = judge(image_sha256=sha)
        self.assertIn("it shows out/lid.stl, not a part of this build as it is now", self.promise(out, "wave")["reasons"][0])
        os.remove("out/look.png.json")
        out = judge(image_sha256=sha)
        self.assertIn("no sidecar (out/look.png.json) says what it shows", self.promise(out, "wave")["reasons"][0])

    def test_a_test_print_stands_for_the_parts_it_printed(self):
        """0.7.0 step 3: a print verifies the promises it lists, for the parts as they are now, in
        their material, on this printer, as built and under the delivered preset."""
        import validate
        self.record()
        lid = validate.file_sha256("out/lid.stl")
        printed = {"name": "lid fit", "status": "passed", "promises": ["seat"], "printer": "x2d",
                   "orientation": "as built", "by": "user", "preset": "0.20mm Standard",
                   "parts": {"lid": {"sha256": lid, "material": "pla_basic"}}}
        seat = dict(self.SEAT, evidence=[{"test_print": "lid fit"}])
        contract = {"_material": "pla_basic", "_print": {"preset": "0.20mm Standard"}}

        def judge(change=None, **extra):
            return self.run_use(self.verify([seat], dims=[], test_prints=[dict(printed, **(change or {}))]),
                                **dict(contract, **extra))

        out = judge()
        self.assertEqual((out["use"], self.promise(out, "seat")["state"]), ("verified", "verified"))
        self.assertEqual(self.promise(out, "seat")["evidence"], [{"test_print": "lid fit", "result": "passed"}])
        for change, extra, state, reason in (
                ({}, {"_print": {}}, "assumed", "the delivered preset is not recorded (_print.preset)"),
                ({"parts": {"lid": {"sha256": lid, "material": "pla_matte"}}}, {}, "not verified",
                 "lid was printed in pla_matte, the part is pla_basic"),
                ({}, {"_parts": {"box": {"expect": [40, 30, 20]}, "lid": {"expect": [40, 30, 3], "material": "petg_hf"}}},
                 "not verified", "lid was printed in pla_basic, the part is petg_hf"),
                ({}, {"_material": None}, "not verified", "no material is declared for lid"),
                ({"printer": "p1s"}, {}, "not verified", "printed on p1s, the build is for x2d"),
                ({"orientation": "on its side"}, {}, "not verified", "printed on its side, not as built"),
                ({"preset": "0.12mm Fine"}, {}, "not verified", 'printed with preset "0.12mm Fine"'),
                ({"by": "agent"}, {}, "not verified", 'only the user prints'),
                ({"status": "skipped"}, {}, "not verified", "test print 'lid fit': skipped"),
                ({"status": "failed"}, {}, "failed", "test print 'lid fit' failed"),
                ({"parts": {"lid": {"sha256": "0" * 64, "material": "pla_basic"}}}, {}, "not verified",
                 "it printed lid as they were then")):
            with self.subTest(change=change, extra=extra):
                if extra.get("_material", "") is None:
                    out = self.run_use(self.verify([seat], dims=[], test_prints=[printed]), _print=contract["_print"])
                else:
                    out = judge(change, **extra)
                promise = self.promise(out, "seat")
                self.assertEqual(promise["state"], state, promise["reasons"])
                self.assertTrue(any(reason in r for r in promise["reasons"]), promise["reasons"])
        for change, message in (({"promises": ["other"]}, "does not list this promise"),
                                ({"parts": {"lid": {"sha256": lid}}}, "has a declaration error"),
                                ({"orientation": ""}, "has a declaration error")):
            with self.subTest(change=change):
                out = judge(change)
                self.assertEqual((out["use"], self.promise(out, "seat")["state"]), ("error", "error"))
                self.assertTrue(any(message in r for r in self.promise(out, "seat")["reasons"]))
        old = {"name": "lid fit", "status": "passed"}                                 # a 0.6 entry
        out = self.run_use(self.verify([seat], dims=[], test_prints=[old]), **contract)
        self.assertIn("lists no promises", self.promise(out, "seat")["reasons"][0])
        out = judge(None, _material="pla")
        self.assertIn("_material must be a strength.py material key", " ".join(out["promise_errors"]))

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

    # 0.7.0 step 4: strength inputs taken from the build, the material the build recorded, and the
    # filament and preset of the delivered Bambu project.

    RIBBON = {"ribbon_t": 4.5, "ribbon_w": 12, "ribbon_l": 30}
    HOLDS = {"id": "holds", "kind": "use", "text": "the ribbon holds the phone", "conditions": "a 240 g phone pulled by a finger",
             "success": "safety factor 2", "evidence": [{"strength": "ribbon"}]}
    STANDS = {"id": "stands", "kind": "use", "text": "the box stands on the desk", "conditions": "empty box on a desk",
              "success": "it does not tip", "evidence": [{"test_print": "box print"}]}
    BAMBU_PLA = "Bambu PLA Basic @BBL X1C"
    STANDARD = "0.20mm Standard @BBL X1C"

    def linked_verify(self, promises=None, members=True, **more):
        """The seat joint, the ribbon member (when members) and the promises (holds by default)."""
        return self.verify([self.HOLDS] if promises is None else promises, dims=[],
                           joints=[{"name": "lid on box", "report": "out/fit_seat.json"}],
                           strength=[{"name": "ribbon", "report": "out/strength_ribbon.json"}] if members else [], **more)

    def stamp(self, built=None, materials=None):
        """The saved build JSON as build.py records it from 0.7.0 (contract 1 of step 4): the
        parameters it was built from and each part's material. built=False or materials=False
        leave the field out, as a build JSON from before 0.7.0."""
        with open("out/build.json") as f:
            b = json.load(f)
        if built is False:
            b.pop("parameters", None)                                          # build.py records it now
        else:
            b["parameters"] = {"scope": "overrides", "values": built}
        for p in b["parts"]:
            if materials is False:
                p.pop("material", None)
            else:
                p["material"] = (materials or {}).get(p["name"], "pla_basic")
        with open("out/build.json", "w") as f:
            json.dump(b, f)

    def run_linked(self, verify, values=None, built=None, materials=None, deliver=None, **extra):
        """params.json (verify, the ribbon's numbers or values, _material pla_basic unless given;
        None leaves it out), recorded, the build JSON stamped with built (default: the values) and
        the materials, then finalized (with --deliver when given)."""
        values = dict(self.RIBBON if values is None else values)
        extra.setdefault("_material", "pla_basic")
        if extra["_material"] is None:
            del extra["_material"]
        self.params(verify, **dict(values, **extra))
        self.record()
        self.stamp(values if built is None else built, materials)
        code, out = self.finalize(*(("--deliver", deliver) if deliver else ()))
        self.assertEqual(code, 0, out.get("errors"))
        return out

    def test_a_strength_report_from_the_build_verifies_a_use(self):
        linked_report("out/strength_ribbon.json")
        out = self.run_linked(self.linked_verify())
        self.assertEqual((out["use"], self.promise(out, "holds")["state"]), ("verified", "verified"))
        self.assertEqual(out["geometry"], "verified", out["open"])
        member = out["strength"][0]
        self.assertEqual((member["linked"], member["manual"], member["part"], member["result"]), (True, [], "lid", "passed"))
        self.assertEqual(member["parameters"], {"h": "ribbon_t", "b": "ribbon_w", "length": "ribbon_l"})
        self.assertFalse(any("member 'ribbon'" in w for w in out["warnings"]), out["warnings"])  # nothing typed in
        self.assertEqual(out["material_drift"], [])
        linked_report("out/strength_ribbon.json", links={"h": ("ribbon.t", 4.5), "b": ("ribbon.w", 12),
                                                         "length": ("ribbon_l", 30)})
        out = self.run_linked(self.linked_verify(), values={"ribbon": {"t": 4.5, "w": 12}, "ribbon_l": 30})
        self.assertEqual(self.promise(out, "holds")["state"], "verified", out["open"])     # a dotted path
        out = self.run_linked(self.linked_verify(), values={"ribbon": {"t": 4.5, "w": 12.5}, "ribbon_l": 30})
        self.assertIn("member 'ribbon': b was ribbon.w = 12, now 12.5", self.promise(out, "holds")["reasons"])

    def test_typed_strength_inputs_are_named(self):
        """Reverse: a number typed on the command line keeps a member from verifying a use, by
        name; the geometry only notes it, as in 0.6."""
        linked_report("out/strength_ribbon.json", links={"h": ("ribbon_t", 4.5), "b": ("ribbon_w", 12)},
                      typed={"length": 30})
        out = self.run_linked(self.linked_verify())
        holds = self.promise(out, "holds")
        self.assertEqual(holds["state"], "not verified")
        self.assertEqual(holds["reasons"], ["member 'ribbon': length was typed in, not taken from the build's parameters"])
        self.assertEqual(out["strength"][0]["manual"], ["length"])
        self.assertEqual(out["geometry"], "verified", out["open"])
        self.assertIn("member 'ribbon': length = 30 was typed in, not taken from the build's parameters (strength.py "
                      "--param): they must be the dimension table's", out["warnings"])
        linked_report("out/strength_ribbon.json", links={"h": ("ribbon_t", 4.5), "b": ("ribbon_w", 12)},
                      typed={"length": 30, "load": 60})
        out = self.run_linked(self.linked_verify())
        self.assertIn("member 'ribbon': load, length were typed in, not taken from the build's parameters",
                      self.promise(out, "holds")["reasons"])
        rep = linked_report("out/strength_ribbon.json")
        for drop in ("from_build", "inputs_from"):                             # not made with --from-build
            with self.subTest(drop=drop):
                with open("out/strength_ribbon.json", "w") as f:
                    json.dump({k: v for k, v in rep.items() if k != drop}, f)
                out = self.run_linked(self.linked_verify())
                self.assertEqual(self.promise(out, "holds")["reasons"],
                                 ["member 'ribbon': its inputs were typed in, not taken from the build's parameters"])
                self.assertEqual((out["strength"][0]["linked"], out["strength"][0]["manual"]),
                                 (False, ["h", "b", "length", "load", "material", "sf"]))
                self.assertEqual(out["geometry"], "verified", out["open"])
                self.assertTrue(any(w.startswith("member 'ribbon': strength.py took its sizes from the numbers it was "
                                                 "given") for w in out["warnings"]), out["warnings"])

    def test_a_parameter_changed_since_the_calculation_is_named(self):
        """Plan C, done criterion 3: ribbon_t changed and the member was not calculated again."""
        linked_report("out/strength_ribbon.json")
        out = self.run_linked(self.linked_verify(), values=dict(self.RIBBON, ribbon_t=5.0))
        holds = self.promise(out, "holds")
        self.assertEqual((out["use"], holds["state"]), ("not verified", "not verified"))
        self.assertEqual(holds["reasons"], ["member 'ribbon': h was ribbon_t = 4.5, now 5.0"])
        self.assertEqual(out["strength"][0]["result"], "stale")
        self.assertEqual(out["geometry"], "not verified")                      # like a stale fit report
        self.assertIn("member 'ribbon': h was ribbon_t = 4.5, now 5.0: run strength.py --from-build again", out["open"])
        out = self.run_linked(self.linked_verify(), built={"ribbon_w": 12, "ribbon_l": 30})
        self.assertEqual(self.promise(out, "holds")["reasons"], ["member 'ribbon': ribbon_t is not in the build's parameters"])
        out = self.run_linked(self.linked_verify(), built=False)                # a build JSON from before 0.7.0
        self.assertEqual(self.promise(out, "holds")["reasons"], ["member 'ribbon': the build JSON records no parameters "
                                                                  "to compare with (built before 0.7.0): build again"])
        linked_report("out/strength_ribbon.json", gate="FAIL")
        out = self.run_linked(self.linked_verify(), values=dict(self.RIBBON, ribbon_t=5.0))
        self.assertEqual(self.promise(out, "holds")["state"], "not verified")  # a FAIL of other numbers is no failure here
        self.assertTrue(any(o.startswith("member 'ribbon': strength.py beam FAIL") for o in out["open"]), out["open"])
        out = self.run_linked(self.linked_verify())
        self.assertEqual(self.promise(out, "holds")["state"], "failed")        # of these numbers it is

    def test_a_calculation_of_another_part_or_material_does_not_stand(self):
        linked_report("out/strength_ribbon.json")
        write_stl("out/lid.stl", box(40, 30, 4, 0, 0, 30))                    # the lid built again since
        fit_report("out/fit_seat.json", "out/box.stl", "out/lid.stl")
        out = self.run_linked(self.linked_verify())
        self.assertEqual(self.promise(out, "holds")["reasons"], ["member 'ribbon': calculated for an earlier lid"])
        self.assertIn("member 'ribbon': calculated for an earlier lid: run strength.py --from-build again", out["open"])
        linked_report("out/strength_ribbon.json", part="hinge", sha="0" * 64)
        out = self.run_linked(self.linked_verify())
        self.assertEqual(self.promise(out, "holds")["reasons"],
                         ["member 'ribbon': calculated for hinge, which is not a part of this build"])
        linked_report("out/strength_ribbon.json")
        parts = {"box": {"expect": [40, 30, 20]}, "lid": {"expect": [40, 30, 3], "material": "petg_hf"}}
        for extra, materials, why in (
                ({"_material": "petg_hf"}, {"box": "petg_hf", "lid": "petg_hf"}, "lid is petg_hf now"),
                ({"_parts": parts}, {"lid": "petg_hf"}, "lid is petg_hf now"),
                ({"_material": None}, {"box": None, "lid": None}, "no material is declared for lid now")):
            with self.subTest(extra=extra):                                    # built again in it, not calculated again
                out = self.run_linked(self.linked_verify(), materials=materials, **extra)
                self.assertEqual(self.promise(out, "holds")["reasons"], [f"member 'ribbon': calculated in pla_basic, {why}"])
                self.assertEqual(out["geometry"], "not verified")
                self.assertEqual(out["material_drift"], [])

    def test_a_linked_member_on_a_failing_part_or_with_an_accepted_warn(self):
        linked_report("out/strength_ribbon.json")
        self.run_linked(self.linked_verify())
        self.params(self.linked_verify(), **dict(self.RIBBON, ribbon_t=5.0), _material="pla_basic")  # not built again
        code, out = self.finalize()
        self.assertEqual(out["strength"][0]["result"], "passed")               # true of the build it read
        self.assertIn("member 'ribbon' is calculated for lid, whose own checks FAIL", self.promise(out, "holds")["reasons"])
        self.assertEqual(self.promise(out, "holds")["state"], "not verified")
        linked_report("out/strength_ribbon.json", gate="WARN")
        out = self.run_linked(self.linked_verify())
        self.assertEqual(self.promise(out, "holds")["reasons"], ["member 'ribbon': strength.py gate WARN"])
        out = self.run_linked(self.linked_verify(accepted=[{"check": "member ribbon", "reason": "the user prints it first"}]))
        self.assertEqual((out["use"], self.promise(out, "holds")["state"]), ("accepted", "accepted"))
        self.assertEqual(out["geometry"], "verified", out["open"])

    def test_a_report_that_disagrees_with_itself_does_not_stand(self):
        """Reverse: the inputs, their origins and from_build are written together; one edited
        apart from the others is not a calculation of the build."""
        cases = (({"inputs": {"h": 5.0, "b": 12, "length": 30, "load": "finger_pull", "material": "pla_basic", "sf": 2.0}},
                  "its inputs_from and from_build do not agree on h"),
                 ({"inputs_from": {"h": "manual", "b": "param:ribbon_w", "length": "param:ribbon_l"}},
                  "its inputs_from and from_build do not agree on h"),
                 ({"material": {"key": "petg_hf"}}, "it was calculated in petg_hf, not in the material its build recorded "
                                                   "(pla_basic)"),
                 ({"from_build": {"part": "lid", "parameters": []}}, "its from_build is not a strength.py --from-build record"))
        for change, why in cases:
            with self.subTest(why=why, change=change):
                rep = dict(linked_report("out/strength_ribbon.json"), **change)
                with open("out/strength_ribbon.json", "w") as f:
                    json.dump(rep, f)
                out = self.run_linked(self.linked_verify())
                holds = self.promise(out, "holds")
                self.assertEqual(holds["state"], "not verified")
                self.assertIn(why, holds["reasons"][0])
                self.assertEqual(out["geometry"], "not verified")

    def test_a_material_changed_since_the_build(self):
        """Plan C: a material is no engine parameter, so the STLs stay fresh; what was printed
        for the material the build recorded is not evidence for another."""
        import validate
        lid = validate.file_sha256("out/lid.stl")
        printed = {"name": "lid fit", "status": "passed", "promises": ["seat"], "printer": "x2d",
                   "orientation": "as built", "by": "user", "preset": self.STANDARD,
                   "parts": {"lid": {"sha256": lid, "material": "petg_hf"}}}
        seat = dict(self.SEAT, evidence=[{"test_print": "lid fit"}])
        v = self.linked_verify([seat], members=False, test_prints=[printed])
        out = self.run_linked(v, _material="petg_hf", _print={"preset": self.STANDARD})   # built in pla_basic
        self.assertEqual(out["material_drift"], ["box: material changed since the build (pla_basic -> petg_hf)",
                                                 "lid: material changed since the build (pla_basic -> petg_hf)"])
        self.assertIn("lid: material changed since the build (pla_basic -> petg_hf)", out["open"])
        self.assertEqual(self.promise(out, "seat")["reasons"],
                         ["test print 'lid fit': lid: material changed since the build (pla_basic -> petg_hf)"])
        self.assertEqual(out["geometry"], "verified", out["open"])             # the shape did not change
        out = self.run_linked(v, _material="petg_hf", _print={"preset": self.STANDARD},
                              materials={"box": "petg_hf", "lid": "petg_hf"})  # built again
        self.assertEqual((out["material_drift"], self.promise(out, "seat")["state"]), ([], "verified"))
        out = self.run_linked(v, _material="petg_hf", _print={"preset": self.STANDARD}, materials=False)
        self.assertEqual((out["material_drift"], self.promise(out, "seat")["state"]), ([], "verified"))  # before 0.7.0
        out = self.run_linked(v, _material="petg_hf", _print={"preset": self.STANDARD}, materials={"box": None, "lid": None})
        self.assertIn("lid: material changed since the build (none -> petg_hf)", out["material_drift"])
        self.assertEqual(self.promise(out, "seat")["state"], "not verified")
        out = self.run_linked(v, _material=None, _print={"preset": self.STANDARD}, materials={"box": None, "lid": None})
        self.assertEqual(out["material_drift"], [])                            # none then, none now

    def bambu_project(self, filaments=None, process=STANDARD, parts=("box", "lid"), name="set.3mf"):
        """A delivered Bambu project and its manifest as bambu3mf.py writes it (contract 3 of step
        4): the parts' sha256, each part's filament slot and settings name, the process preset.
        filaments=False or process=False leave the key out, as a core 3MF of build.py."""
        import validate
        os.makedirs("deliver", exist_ok=True)
        path = os.path.join("deliver", name)
        with open(path, "wb") as f:
            f.write(b"PK a Bambu project: " + name.encode())
        m = {"schema": finalize.MANIFEST_3MF, "artifact_sha256": validate.file_sha256(path),
             "parts": {n: validate.file_sha256(os.path.join("out", n + ".stl")) for n in parts}}
        if filaments is not False:
            fil = dict({n: self.BAMBU_PLA for n in parts}, **(filaments or {}))
            m["filaments"] = {n: {"slot": i + 1, "settings": s} for i, (n, s) in enumerate(sorted(fil.items()))}
        if process is not False:
            m["process"] = {"settings": process}
        with open(path + ".manifest.json", "w") as f:
            json.dump(m, f)

    def delivered_verify(self, preset=STANDARD):
        """holds (the ribbon member, of the lid), seat (a print of the lid), stands (a print of the box)."""
        import validate
        prints = []
        for name, part, pid in (("lid fit", "lid", "seat"), ("box print", "box", "stands")):
            prints.append({"name": name, "status": "passed", "promises": [pid], "printer": "x2d",
                           "orientation": "as built", "by": "user", "preset": preset,
                           "parts": {part: {"sha256": validate.file_sha256(os.path.join("out", part + ".stl")),
                                            "material": "pla_basic"}}})
        linked_report("out/strength_ribbon.json")
        return self.linked_verify([self.HOLDS, dict(self.SEAT, evidence=[{"test_print": "lid fit"}]), self.STANDS],
                                  test_prints=prints)

    def states(self, out):
        return {p["id"]: p["state"] for p in out["promises"]}

    def test_the_delivered_bambu_project_prints_each_part_in_its_material(self):
        v = self.delivered_verify()
        self.bambu_project()
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "verified", "stands": "verified"}, out["open"])
        self.assertEqual(out["geometry"], "verified", out["open"])
        self.assertEqual(out["delivered"][0]["filaments"]["lid"], {"slot": 2, "settings": self.BAMBU_PLA,
                                                                   "material": "pla_basic"})
        self.assertEqual(out["delivered"][0]["preset"], self.STANDARD)
        self.assertFalse(any("print file" in o or "filament" in o for o in out["open"]), out["open"])
        self.bambu_project({"lid": "Bambu PETG HF @BBL X1C"})                  # the wrong slot for the lid
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "not verified", "seat": "not verified", "stands": "verified"})
        self.assertIn("member 'ribbon': the print file prints lid in petg_hf, the part is pla_basic",
                      self.promise(out, "holds")["reasons"])
        self.assertIn("test print 'lid fit': the print file prints lid in petg_hf, the part is pla_basic",
                      self.promise(out, "seat")["reasons"])
        self.assertTrue(any(o.startswith("deliver/set.3mf: lid is printed in Bambu PETG HF @BBL X1C (petg_hf), the part "
                                         "is pla_basic") for o in out["open"]), out["open"])
        self.assertEqual(out["geometry"], "verified", out["open"])             # a filament is not a shape
        out = self.run_linked(v, _print={"preset": self.STANDARD})             # without --deliver: not read
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "verified", "stands": "verified"})
        self.assertFalse(any("print file" in o or "filament" in o for o in out["open"]), out["open"])

    def test_a_filament_finalize_cannot_name_leaves_the_part_assumed(self):
        v = self.delivered_verify()
        for settings, why in (("Generic PLA @BBL X1C", '"Generic PLA @BBL X1C" is not a filament of a known material'),
                              ("Bambu PLA Basic Gradient @BBL X1C", "is not a filament of a known material"),
                              (None, "the project names no filament for its slot")):
            with self.subTest(settings=settings):
                self.bambu_project({"lid": settings})
                out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
                self.assertEqual(self.states(out), {"holds": "assumed", "seat": "assumed", "stands": "verified"})
                self.assertEqual(self.promise(out, "holds")["reasons"],
                                 ["member 'ribbon': the slicer's filament for lid is not checked"])
                self.assertEqual(self.promise(out, "seat")["reasons"],
                                 ["test print 'lid fit': the slicer's filament for lid is not checked"])
                self.assertTrue(any(o.startswith("deliver/set.3mf: the slicer's filament for lid is not checked") and why in o
                                    for o in out["open"]), out["open"])

    def test_without_a_bambu_project_the_print_files_material_is_assumed(self):
        v = self.delivered_verify()
        os.makedirs("deliver")
        for n in ("box", "lid"):
            shutil.copyfile(os.path.join("out", n + ".stl"), os.path.join("deliver", n + ".stl"))
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "assumed", "seat": "assumed", "stands": "assumed"})
        self.assertEqual(self.promise(out, "holds")["reasons"],
                         ["member 'ribbon': the print file's material is not checked (no Bambu project)"])
        self.assertIn("the print file's material is not checked (no Bambu project): set the slicer's filament to box: "
                      "pla_basic, lid: pla_basic", out["open"])
        self.assertEqual(out["geometry"], "verified", out["open"])
        for n in ("box", "lid"):
            os.remove(os.path.join("deliver", n + ".stl"))
        self.bambu_project(filaments=False, process=False)                     # a core 3MF names no filament
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "assumed", "seat": "assumed", "stands": "assumed"})
        os.remove("deliver/set.3mf")
        os.remove("deliver/set.3mf.manifest.json")
        self.bambu_project(parts=("lid",))                                     # the lid in a project, the box as an STL
        shutil.copyfile("out/box.stl", "deliver/box.stl")
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "verified", "stands": "assumed"})
        self.assertIn("the print file's material is not checked (no Bambu project) for box: set the slicer's filament to "
                      "box: pla_basic", out["open"])

    def test_the_delivered_process_preset(self):
        v = self.delivered_verify()
        self.bambu_project(process="0.16mm Optimal @BBL X1C")
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "not verified", "stands": "not verified"})
        self.assertEqual(self.promise(out, "seat")["reasons"], ['test print \'lid fit\': printed with preset "0.20mm '
                                                                'Standard @BBL X1C", the delivery uses "0.16mm Optimal @BBL '
                                                                'X1C"'])
        self.assertTrue(any(o.startswith('deliver/set.3mf: its process preset is "0.16mm Optimal @BBL X1C", not '
                                         '_print.preset "0.20mm Standard @BBL X1C"') for o in out["open"]), out["open"])
        self.bambu_project()                                                   # no _print.preset: the project's is the one
        out = self.run_linked(v, deliver="deliver")
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "verified", "stands": "verified"}, out["open"])
        out = self.run_linked(v)                                               # without --deliver, as before
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "assumed", "stands": "assumed"})
        self.assertIn("test print 'lid fit': the delivered preset is not recorded (_print.preset)",
                      self.promise(out, "seat")["reasons"])
        self.bambu_project(process="0.12mm Fine @BBL X1C")
        out = self.run_linked(v, deliver="deliver")
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "not verified", "stands": "not verified"})
        self.assertIn('test print \'lid fit\': printed with preset "0.20mm Standard @BBL X1C", the delivery uses '
                      '"0.12mm Fine @BBL X1C"', self.promise(out, "seat")["reasons"])
        self.bambu_project(process=None)                                       # the template names no process
        out = self.run_linked(v, deliver="deliver")
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "assumed", "stands": "assumed"})
        # Reverse (Codex, PR #21): _print.preset does not stand in for a project that names none.
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out), {"holds": "verified", "seat": "assumed", "stands": "assumed"})
        self.assertEqual(self.promise(out, "seat")["reasons"],
                         ["test print 'lid fit': the delivered project names no process preset (deliver/set.3mf)"])
        self.assertIn('deliver/set.3mf: the project names no process preset, so a test print cannot be compared with '
                      'it: choose "0.20mm Standard @BBL X1C" in the slicer', out["open"])
        self.assertIsNone([d for d in out["delivered"] if d["kind"] == "3mf"][0]["preset"])
        self.bambu_project(filaments={}, process="")                           # a blank name is no name
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertEqual(self.states(out)["seat"], "assumed")
        self.bambu_project(filaments=False, process=False)                     # a core 3MF: no slicer settings at all
        out = self.run_linked(v, deliver="deliver", _print={"preset": self.STANDARD})
        self.assertFalse(any("names no process preset" in o for o in out["open"]), out["open"])
        self.assertNotIn("preset", [d for d in out["delivered"] if d["kind"] == "3mf"][0])


SKILL = os.path.normpath(os.path.join(HERE, ".."))


def reproduce(folder):
    """The commands of a bundle's REPRODUCE.md run as written, from the bundle (python3 is this
    interpreter, $SKILL_DIR this skill, `> FILE` saves the output): the last one's JSON, which
    is finalize's report."""
    import re
    import shlex
    import subprocess
    with open(os.path.join(folder, "REPRODUCE.md"), encoding="utf-8") as f:
        blocks = re.findall(r"```bash\n(.*?)```", f.read(), flags=re.S)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    text = None
    for line in (ln for b in blocks for ln in b.splitlines() if ln.strip()):
        argv, target = shlex.split(line), None
        if ">" in argv:
            argv, target = argv[:argv.index(">")], argv[argv.index(">") + 1]
        argv = [sys.executable if a == "python3" else a.replace("$SKILL_DIR", SKILL) for a in argv]
        r = subprocess.run(argv, cwd=folder, capture_output=True, encoding="utf-8", env=env)
        assert r.returncode == 0, (line, r.stdout[-2000:], r.stderr[-2000:])
        if target:
            with open(os.path.join(folder, target), "w", encoding="utf-8") as f:
                f.write(r.stdout)
        text = r.stdout
    return json.loads(text)


def verdict(out):
    """What a bundle must reach again: the tiers, each promise's state and reasons, the open lines."""
    return {"use": out["use"], "geometry": out["geometry"], "print": out["print"], "open": out["open"],
            "promises": {p["id"]: (p["state"], p["reasons"]) for p in out["promises"]}}


class FinalizeBundle(FinalizePromises):
    """0.7.0 step 5: --bundle holds what it takes to reach the same verdict from the bundle alone
    (plan, 번들): the reports _verify names and what they read by hash, the seen images, the test
    print photos and the delivered Bambu project."""

    LOOK = {"id": "flush", "kind": "look", "text": "the lid sits flush", "evidence": [{"seen": "front look"}]}

    def record_proxy(self, values=None):
        """The plug proxy recorded (build.py record of an STL made elsewhere): the bundle carries
        it as it is, build JSON and all (a `build.py run --proxy` proxy is built again instead:
        BundleFromTheScripts). Recorded, it ties nothing to its sizes, so the cable is assumed."""
        values = dict(self.PLUG if values is None else values)
        with open(".3dprint/plug.json", "w") as f:
            json.dump(values, f)
        code, out = run(build, "record", "out/plug.stl", "--source", "plug.py", "--params", ".3dprint/plug.json",
                        "--out", "out", "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        with open("out/plug_build.json", "w") as f:
            json.dump(out, f)

    def evidence_project(self):
        """A recorded box and lid with one of each kind of evidence: the seat fit, the plug fit
        against its proxy (built by build.py run from its own params file), the plug width read
        from the user's file, the ribbon member linked to the build, a look the user judged on a
        preview, a test print with the user's photo, and the delivered Bambu project. Returns
        the params.json values and _verify."""
        import preview
        import validate
        os.makedirs("ref")
        os.makedirs("photos")
        write_stl("ref/plug.stl", box(13, 8, 9))                             # the user's model of the plug
        measure_report("out/m_plug.json", "info", "ref/plug.stl", "--expect", "objects[0].size_mm[0]=13", "--tol", "0.2")
        with open("photos/lid-fit.jpg", "wb") as f:
            f.write(b"\xff\xd8\xff\xe0 the user's photo of the printed lid")
        code, rep = run(preview, "out/box.stl", "out/lid.stl", "-o", "out/look.png", "--size", "400x300")
        self.assertEqual(code, 0, rep["errors"])
        linked_report("out/strength_ribbon.json")
        self.bambu_project()
        head = {"id": "plug-head", "what": "plug head width, from the maker's model", "params": {"plug_w": 13},
                "source": "user-file", "from": {"plug_w": "plug width"}, "tol": 0.05}
        rest = dict(self.plug_dims("caliper", by="user"), id="plug-rest", params={"plug_h": 8, "plug_l": 9, "cable_d": 4.5})
        joints = [{"name": "lid on box", "report": "out/fit_seat.json"},
                  {"name": "plug through notch", "report": "out/fit_plug.json", "proxy": True,
                   "dims": ["plug-head", "plug-rest"], "proxy_build": "out/plug_build.json"}]
        printed = {"name": "lid fit", "status": "passed", "promises": ["lid-print"], "printer": "x2d",
                   "orientation": "as built", "by": "user", "preset": self.STANDARD, "photos": ["photos/lid-fit.jpg"],
                   "parts": {"lid": {"sha256": validate.file_sha256("out/lid.stl"), "material": "pla_basic"}}}
        seen = {"name": "front look", "image": "out/look.png", "image_sha256": validate.file_sha256("out/look.png"),
                "by": "user", "promises": ["flush"], "result": "passed"}
        promises = [self.SEAT, self.CABLE, self.HOLDS, self.LOOK,
                    dict(self.SEAT, id="lid-print", evidence=[{"test_print": "lid fit"}])]
        verify = self.verify(promises, dims=[head, rest], joints=joints, seen=[seen], test_prints=[printed],
                             measurements=[{"name": "plug width", "report": "out/m_plug.json"}],
                             strength=[{"name": "ribbon", "report": "out/strength_ribbon.json"}])
        return dict(self.PLUG, **self.RIBBON, _material="pla_basic", _print={"preset": self.STANDARD}), verify

    def bundle(self, verify, values, *extra):
        self.params(verify, **values)
        self.record()
        self.record_proxy()
        return self.finalize("--deliver", "deliver", "--bundle", "deliver/source", *extra)

    def export(self, folder="deliver/source"):
        """What REPRODUCE.md asks of a recorded build: the parts exported again (the same STLs)."""
        os.makedirs(os.path.join(folder, "out"), exist_ok=True)
        for n in ("box", "lid"):
            shutil.copyfile(os.path.join("out", n + ".stl"), os.path.join(folder, "out", n + ".stl"))

    @unittest.skipUnless(HAS_NP, "numpy not installed")
    def test_the_bundle_reaches_the_same_verdict(self):
        values, verify = self.evidence_project()
        code, out = self.bundle(verify, values)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual((out["use"], out["geometry"]), ("assumed", "verified"), out["open"])
        self.assertEqual({p["id"]: p["state"] for p in out["promises"]},
                         {"seat": "verified", "cable-out": "assumed", "holds": "verified", "flush": "verified",
                          "lid-print": "verified"})
        carried = {"out/fit_seat.json", "out/fit_plug.json",                   # the reports _verify names
                   "out/strength_ribbon.json", "out/m_plug.json",
                   "out/plug_build.json", "out/plug.stl", "out/plug.stl.manifest.json",   # the proxy and its inputs
                   "plug.py", ".3dprint/plug.json",
                   "ref/plug.stl",                                             # the user's file the dims rest on
                   "out/look.png", "out/look.png.json",                        # the image the user judged
                   "photos/lid-fit.jpg",                                       # the user's photo of the print
                   "deliver/set.3mf", "deliver/set.3mf.manifest.json"}         # the delivered Bambu project
        prefix = "deliver/source/"
        bundled = {p[len(prefix):] for p in out["bundle"]}
        self.assertEqual(carried - bundled, set())                             # reverse: nothing left out
        self.assertEqual(bundled - carried, {"gen.py", "params.json", "printers.json", "REPRODUCE.md",
                                             "verification.json"})             # the parts are made again, not carried
        self.assertEqual(out["bundle_missing"], [])
        for path in carried:                                                   # copied, never moved
            self.assertTrue(os.path.isfile(path), path)
            with open(path, "rb") as a, open(prefix + path, "rb") as b:
                self.assertEqual(a.read(), b.read(), path)
        with open(prefix + "REPRODUCE.md", encoding="utf-8") as f:
            text = f.read()
        self.assertIn('finalize.py" --build build.json --params params.json --printer printers.json --no-wall-check '
                      '--deliver deliver\n', text)                            # the settings finalize was given
        self.assertIn("`ref/plug.stl`: file read by measurement 'plug width'", text)
        self.assertIn("record out/box.stl out/lid.stl --source gen.py", text)
        self.assertNotIn(self.tmp, text)
        self.export()
        again = reproduce("deliver/source")
        self.assertEqual(verdict(again), verdict(out))

    @unittest.skipUnless(HAS_NP, "numpy not installed")
    def test_a_file_named_but_not_found_is_listed_not_hidden(self):
        """Reverse: a missing report or photo leaves the bundle as the verdict is (not verified),
        names the file in REPRODUCE.md, and a re-check from the bundle says the same."""
        values, verify = self.evidence_project()
        verify["measurements"].append({"name": "lid gap", "report": "out/m_gap.json"})
        verify["promises"].append({"id": "gap", "kind": "feature", "text": "a 0.3 mm gap", "success": "0.3 within 0.05",
                                   "evidence": [{"measurement": "lid gap"}]})
        verify["test_prints"][0]["photos"].append("photos/lid-side.jpg")
        code, out = self.bundle(verify, values)
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(self.promise(out, "gap")["state"], "not verified")
        self.assertEqual(out["bundle_missing"], ["out/m_gap.json: report of measurement 'lid gap'",
                                                 "photos/lid-side.jpg: photo of test print 'lid fit'"])
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("## Not in this bundle", text)
        self.assertIn("- `photos/lid-side.jpg`: photo of test print 'lid fit'", text)
        self.assertTrue(os.path.isfile("deliver/source/photos/lid-fit.jpg"))   # what exists is still carried
        self.export()
        self.assertEqual(verdict(reproduce("deliver/source")), verdict(out))

    def test_a_delivery_folder_not_found_is_named_in_reproduce(self):
        """Reverse (Codex, PR #22): --deliver naming a missing folder, or a file, is "not found" in
        the verdict; REPRODUCE.md keeps the --deliver, so the re-check says the same."""
        values, verify = self.evidence_project()
        self.params(verify, **values)
        self.record()
        self.record_proxy()
        with open("notes.txt", "w") as f:
            f.write("not a folder")
        for n, deliver in enumerate(("deliver/never", "notes.txt")):
            with self.subTest(deliver=deliver):
                folder = f"bundle{n}"
                code, out = self.finalize("--deliver", deliver, "--bundle", folder)
                self.assertEqual(code, 0, out["errors"])
                self.assertIn(f"delivery folder {deliver} not found", out["open"])
                with open(os.path.join(folder, "REPRODUCE.md"), encoding="utf-8") as f:
                    self.assertIn(f"--deliver {deliver}", f.read())
                self.assertFalse(os.path.exists(os.path.join(folder, deliver)))   # not made: still not found there
                self.export(folder)
                self.assertEqual(verdict(reproduce(folder)), verdict(out))

    def test_what_refuses_a_bundle(self):
        """Reverse: a file outside the project folder, or a report that holds a path of this
        machine, refuses the bundle and leaves no folder behind."""
        import validate
        outside = tempfile.mkdtemp(prefix="3dps-far-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        far = os.path.relpath(os.path.join(outside, "fit.json"))               # ../3dps-far-.../fit.json
        fit_report(os.path.join(outside, "fit.json"), "out/box.stl", "out/lid.stl")
        here = os.path.join(self.tmp, "out", "plug.stl")
        cases = (
            ("a report outside the project", {"joints": [{"name": "lid on box", "report": far}]},
             "fit.json is outside the project folder"),
            ("a photo outside the project", {"test_prints": [{"name": "lid fit", "status": "skipped",
                                                              "photos": ["../lid.jpg"]}]},
             "lid.jpg is outside the project folder"),
            ("a fit report naming an STL by its absolute path", None, "out/fit_plug.json holds a path of this machine"),
            ("a recorded proxy naming its STL by its absolute path", "proxy",
             "out/plug_build.json holds a path of this machine"),
            ("a sidecar naming an STL by its absolute path", "sidecar", "out/look.png.json holds a path of this machine"),
            ("an input in the place of the rebuilt build JSON", "build.json", "build.json would take the place of a file"),
            ("a missing report in the place of the rebuilt build JSON (Codex, PR #22)",
             {"measurements": [{"name": "lip height", "report": "build.json"}]}, "build.json would take the place of a file"),
            ("a missing report named REPRODUCE.md", {"strength": [{"name": "ribbon", "report": "REPRODUCE.md"}]},
             "REPRODUCE.md would take the place of a file"),
            ("a link inside the project to a report outside it (Codex, PR #22)", "link",
             "out/fit_far.json is outside the project folder"))
        for what, change, message in cases:
            with self.subTest(what):
                v = self.verify([self.SEAT, self.CABLE])
                if isinstance(change, dict):
                    v.update(change)
                elif change is None:
                    fit_report("out/fit_plug.json", "out/box.stl", here)
                elif change == "proxy":
                    with open("out/plug_build.json") as f:
                        b = json.load(f)
                    b["parts"][0]["stl"] = here                               # as build.py run writes it today
                    with open("out/plug_build.json", "w") as f:
                        json.dump(b, f)
                elif change == "sidecar":
                    with open("out/look.png", "wb") as f:
                        f.write(b"\x89PNG not drawn here")
                    with open("out/look.png.json", "w") as f:
                        json.dump({"schema": finalize.IMAGE_SCHEMA, "image": "look.png",
                                   "image_sha256": validate.file_sha256("out/look.png"),
                                   "stls": [{"path": os.path.join(self.tmp, "out", "box.stl"), "sha256": "0" * 64}]}, f)
                    v["seen"] = [{"name": "look", "image": "out/look.png", "image_sha256": "0" * 64, "by": "user",
                                  "promises": ["seat"], "result": "passed"}]
                elif change == "link":
                    try:
                        os.symlink(os.path.join(outside, "fit.json"), "out/fit_far.json")
                    except (OSError, NotImplementedError):                 # Windows without the privilege
                        continue
                    v["joints"] = [dict(v["joints"][0], report="out/fit_far.json")] + v["joints"][1:]
                else:
                    with open("build.json", "w") as f:
                        json.dump({"schema": "3dprint-scout.build/1"}, f)
                    v["joints"][1]["proxy_build"] = "build.json"
                self.params(v, **self.PLUG)
                self.record()
                if change != "proxy":
                    self.record_proxy()
                fit_report("out/fit_plug.json", "out/box.stl", here if change is None else "out/plug.stl")
                code, out = self.finalize("--bundle", "deliver/source")
                self.assertEqual(code, 1, out.get("bundle"))
                self.assertIn(message, out["errors"][0])
                self.assertNotIn(self.tmp, json.dumps(out))
                self.assertFalse(os.path.exists("deliver/source"))
                for path in ("build.json", "out/look.png", "out/look.png.json", "out/fit_far.json"):
                    if os.path.lexists(path):
                        os.remove(path)
        code, out = self.finalize("--deliver", outside, "--bundle", "deliver/source")
        self.assertEqual(code, 1)
        self.assertIn("is outside the project folder", out["errors"][0])     # a delivery folder outside it too
        # params.json and printers.json outside the project, or linked from inside it (Codex, PR #22).
        self.params(self.verify([self.SEAT, self.CABLE]), **self.PLUG)
        far_params = os.path.join(outside, "params.json")
        shutil.copyfile(".3dprint/params.json", far_params)
        code, out = self.finalize("--params", os.path.relpath(far_params), "--bundle", "deliver/source")
        self.assertEqual(code, 1)
        self.assertIn("params.json is outside the project folder", out["errors"][0])
        shutil.copyfile(".3dprint/printers.json", os.path.join(outside, "printers.json"))
        os.remove(".3dprint/printers.json")
        try:
            os.symlink(os.path.join(outside, "printers.json"), ".3dprint/printers.json")
        except (OSError, NotImplementedError):                                # Windows without the privilege
            return
        code, out = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 1)
        self.assertIn(".3dprint/printers.json is outside the project folder", out["errors"][0])
        self.assertFalse(os.path.exists("deliver/source"))

    def test_photos_are_paths_in_the_project_folder(self):
        """A test print's photos are optional; given, they list paths in the project folder
        (anything else is a declaration error, as for the other fields), and they are no
        evidence: a print stands or not by its other fields."""
        import validate
        self.record()
        printed = {"name": "lid fit", "status": "passed", "promises": ["seat"], "printer": "x2d",
                   "orientation": "as built", "by": "user", "preset": self.STANDARD,
                   "parts": {"lid": {"sha256": validate.file_sha256("out/lid.stl"), "material": "pla_basic"}}}
        seat = dict(self.SEAT, evidence=[{"test_print": "lid fit"}])
        contract = {"_material": "pla_basic", "_print": {"preset": self.STANDARD}}
        for photos in (None, [], ["photos/lid.jpg", "photos\\side.jpg"]):
            with self.subTest(photos=photos):
                t = dict(printed, **({} if photos is None else {"photos": photos}))
                out = self.run_use(self.verify([seat], dims=[], test_prints=[t]), **contract)
                self.assertEqual(self.promise(out, "seat")["state"], "verified", out["open"])
        for photos, why in (("photos/lid.jpg", "photos must list the paths"), ([""], "photos must list the paths"),
                            ([3], "photos must list the paths"), (["/home/me/lid.jpg"], "not /home/me/lid.jpg"),
                            (["C:\\Users\\me\\lid.jpg"], "relative to it"), (["~/lid.jpg"], "relative to it"),
                            (["photos/../../lid.jpg"], "relative to it")):
            with self.subTest(photos=photos):
                out = self.run_use(self.verify([seat], dims=[], test_prints=[dict(printed, photos=photos)]), **contract)
                self.assertEqual((out["use"], self.promise(out, "seat")["state"]), ("error", "error"))
                self.assertTrue(any(e.startswith("test print 'lid fit': photos") and why in e
                                    for e in out["promise_errors"]), out["promise_errors"])
                old = {"name": "hinge coupon", "status": "passed", "photos": photos}       # no promises: still declared
                out = self.run_use(self.verify([self.SEAT], dims=[], test_prints=[old]), **contract)
                self.assertEqual(out["use"], "error")
                self.assertTrue(any(e.startswith("test print 'hinge coupon': photos") for e in out["promise_errors"]))

    def test_a_3mf_manifest_left_in_out_goes_beside_the_3mf(self):
        """The core 3MF's manifest stays in out/, which the rebuild in REPRODUCE.md writes again
        (a new 3MF, a new manifest): the bundle puts the one finalize compared beside the
        delivered 3MF, so the delivery is judged the same from the bundle."""
        self.params(self.full_verify())
        code, built = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "--params",
                          ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out", "--no-wall-check")
        with open("out/build.json", "w") as f:
            json.dump(built, f)
        os.makedirs("deliver")
        shutil.copyfile(built["threemf"], "deliver/set.3mf")                   # the manifest is left in out/
        code, out = self.finalize("--deliver", "deliver", "--bundle", "deliver/source")
        self.assertEqual(out["geometry"], "verified", out["open"])
        self.assertIn("deliver/source/deliver/set.3mf.manifest.json", out["bundle"])
        self.assertNotIn("deliver/source/" + built["threemf"] + ".manifest.json", out["bundle"])
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            self.assertIn(f"manifest of deliver/set.3mf, found at {built['threemf'].replace(os.sep, '/')}.manifest.json",
                          f.read())                                    # a bundle path: / on Windows too
        self.export()
        self.assertEqual(verdict(reproduce("deliver/source")), verdict(out))   # a new core 3MF there or not

    def test_the_manifest_the_verdict_read_is_the_one_carried(self):
        """Reverse (Codex, PR #22): two sound manifests for one delivered 3MF, one beside it and
        one in out/ (found later, so the verdict reads it): the bundle carries that one, beside
        the 3MF, not the other, so the re-check judges the same filaments."""
        self.params(self.full_verify(), _material="pla_basic")
        self.record()
        self.bambu_project()                                                   # beside it: PLA Basic
        with open("deliver/set.3mf.manifest.json") as f:
            m = json.load(f)
        m["filaments"]["lid"]["settings"] = "Bambu PETG HF @BBL X1C"
        with open("out/set.3mf.manifest.json", "w") as f:                       # the same 3MF, another filament
            json.dump(m, f)
        code, out = self.finalize("--deliver", "deliver", "--bundle", "deliver/source")
        self.assertEqual(code, 0, out["errors"])
        bambu = [d for d in out["delivered"] if d["kind"] == "3mf"][0]
        self.assertEqual(bambu["filaments"]["lid"]["material"], "petg_hf")       # out/'s was read
        with open("deliver/source/deliver/set.3mf.manifest.json") as f:
            self.assertEqual(json.load(f)["filaments"]["lid"]["settings"], "Bambu PETG HF @BBL X1C")
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            self.assertIn("manifest of deliver/set.3mf, found at out/set.3mf.manifest.json", f.read())
        self.export()
        self.assertEqual(verdict(reproduce("deliver/source")), verdict(out))
        os.remove("out/set.3mf.manifest.json")                                 # only the one beside it
        shutil.rmtree("deliver/source")
        code, out = self.finalize("--deliver", "deliver", "--bundle", "deliver/source")
        self.assertEqual([d for d in out["delivered"] if d["kind"] == "3mf"][0]["filaments"]["lid"]["material"],
                         "pla_basic")
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("- `deliver/set.3mf.manifest.json`: manifest of deliver/set.3mf\n", text)
        self.export()
        self.assertEqual(verdict(reproduce("deliver/source")), verdict(out))

    GROUPED = {"box": {"expect": [40, 30, 20], "object": "set"},
               "lid": {"expect": [40, 30, 3], "object": "set", "role": "free", "clearance": 0.3}}

    def write_params(self, parts=None, verify=None, **extra):
        """params.json with these _parts (the box and the lid by default) and _verify."""
        data = {"_parts": parts or {"box": {"expect": [40, 30, 20]}, "lid": {"expect": [40, 30, 3]}},
                "_verify": self.full_verify() if verify is None else verify, **extra}
        with open(".3dprint/params.json", "w") as f:
            json.dump(data, f)

    def record_3mf(self, *stls, flags=()):
        """build.py record of the box and the lid, with the core 3MF unless flags say otherwise; its
        JSON, saved."""
        code, built = run(build, "record", *(stls or ("out/box.stl", "out/lid.stl")), "--source", "gen.py", "--params",
                          ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out",
                          "--no-wall-check", *flags)
        self.assertEqual(code, 0, built["errors"])
        with open("out/build.json", "w") as f:
            json.dump(built, f)
        return built

    def refused(self, *flags, folder="deliver/source", why=()):
        """finalize --bundle refuses (exit 1, finalize's JSON error, each `why` in it) and leaves no
        folder behind. Returns the error."""
        code, out = self.finalize(*flags, "--bundle", folder)
        self.assertEqual(code, 1, out.get("bundle"))
        for w in why:
            self.assertIn(w, out["errors"][0])
        self.assertFalse(os.path.lexists(folder))
        return out["errors"][0]

    def reproduce_text(self, folder="deliver/source"):
        with open(os.path.join(folder, "REPRODUCE.md"), encoding="utf-8") as f:
            return f.read()

    def test_a_build_that_is_no_longer_the_projects_is_refused(self):
        """Reverse (audit 1): REPRODUCE.md builds the parts again from the project as it is now and
        with the build's own settings, so a reason that compares the saved build with the project
        now (a parameter, the material, printers.json or the grouping changed since, an STL that is
        not the build's, a part it did not make) would be gone in the bundle: not verified here,
        verified there. So would a setting given to finalize that differs from the build's. Each
        refuses the bundle before the folder is made."""
        def bed():
            printers = json.loads(json.dumps(X2D))
            printers["printers"]["x2d"]["bed"]["height"] = 250
            with open(".3dprint/printers.json", "w") as f:
                json.dump(printers, f)
        pin = {"box": {"expect": [40, 30, 20]}, "lid": {"expect": [40, 30, 3]}, "pin": {"expect": [3, 3, 9]}}
        for what, change, why in (
                ("a parameter changed", lambda: self.write_params(_material="pla_basic", w=41), "box R3 FAIL"),
                ("the material changed", lambda: self.write_params(_material="petg_hf"),
                 "box: material changed since the build (pla_basic -> petg_hf)"),
                ("printers.json edited", bed, ".3dprint/printers.json changed since the build"),
                ("the grouping changed", lambda: self.write_params(self.GROUPED, _material="pla_basic"),
                 "assembly metadata changed since the build"),
                ("an STL changed", lambda: write_stl("out/lid.stl", box(40, 30, 3.2, 0, 0, 30)),
                 "lid: out/lid.stl is not the STL the build judged"),
                ("a part not built", lambda: self.write_params(pin, _material="pla_basic"),
                 "pin: in _parts but not built")):
            with self.subTest(what):
                write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 30))
                with open(".3dprint/printers.json", "w") as f:
                    json.dump(X2D, f)
                self.write_params(_material="pla_basic")
                self.record()
                code, out = self.finalize("--bundle", "deliver/fresh")
                self.assertEqual(code, 0, out["errors"])                         # as built, it bundles
                shutil.rmtree("deliver")
                change()
                self.refused(why=(why, "build again, save that build's JSON and bundle again"))
        write_stl("out/lid.stl", box(40, 30, 3, 0, 0, 30))
        with open(".3dprint/printers.json", "w") as f:
            json.dump(X2D, f)
        self.write_params(_material="pla_basic")
        self.record()
        shutil.copyfile(".3dprint/printers.json", "other.json")                 # the same bed, another file
        for flags, why in ((("--tol", "0.05"), "tol None -> 0.05"), (("--min-wall", "2"), "min_wall None -> 2.0"),
                           (("--printer", "other.json"), "printer .3dprint/printers.json -> other.json")):
            with self.subTest(flags=flags):
                self.refused(*flags, why=(why, "bundle without those options"))

    def test_the_rebuild_is_made_as_the_build_was(self):
        """Reverse (audit 3, 4): REPRODUCE.md builds again with the build's engine (a Blender
        generator without the marker line is built with --engine blender), its core 3MF choice (the
        same name, or --no-3mf) and its settings, every value quoted (a printer id with a space was
        split by the shell); a build JSON that cannot tell whether a core 3MF was asked for refuses."""
        self.write_params()
        self.record()                                                          # --no-3mf
        code, out = self.finalize("--bundle", "deliver/a")
        self.assertEqual(code, 0, out["errors"])
        self.assertIn('build.py" record out/box.stl out/lid.stl --source gen.py --params params.json --engine fusion '
                      "--out out --no-3mf --printer printers.json --no-wall-check > build.json",
                      self.reproduce_text("deliver/a"))
        with open("out/build.json") as f:
            recorded = json.load(f)
        with open("out/build.json", "w") as f:                       # as `run gen.py --engine blender` saves it
            json.dump(dict(recorded, command="run", engine="blender", source="gen.py"), f)
        code, out = self.finalize("--bundle", "deliver/b")
        self.assertEqual(code, 0, out["errors"])
        self.assertIn('build.py" run gen.py --engine blender --params params.json --out out --no-3mf',
                      self.reproduce_text("deliver/b"))
        # Reverse (Codex, PR #22): `record --engine blender` (a live Blender's export) names an engine
        # `run` knows; the build JSON's command, not the engine, says it is recorded. A JSON from
        # before 0.7.0 has no command: a run reports its engine_info, a record none.
        for n, b in enumerate((dict(recorded, engine="blender"), dict(recorded, engine="python", command=None),
                               dict(recorded, engine="blender", command=None, engine_info={"blender": "4.5.14"}))):
            with self.subTest(build={k: b.get(k) for k in ("command", "engine", "engine_info")}):
                with open("out/build.json", "w") as f:
                    json.dump({k: v for k, v in b.items() if v is not None}, f)
                code, out = self.finalize("--bundle", f"deliver/r{n}")
                self.assertEqual(code, 0, out["errors"])
                text = self.reproduce_text(f"deliver/r{n}")
                ran = n == 2
                self.assertEqual(('build.py" run ' in text, "This build was recorded" in text), (ran, not ran), text)
        with open("out/build.json", "w") as f:
            json.dump(dict(recorded, errors=["core 3MF not written: disk full"]), f)
        self.refused(folder="deliver/c", why=("does not tell whether one was asked for",))
        printers = {"schema": X2D["schema"], "printers": {"Prusa MK4": X2D["printers"]["x2d"]}}
        with open(".3dprint/printers.json", "w") as f:
            json.dump(printers, f)
        self.record_3mf(flags=("--printer-id", "Prusa MK4"))
        code, out = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 0, out["errors"])
        self.assertIn("--engine fusion --out out --3mf box_lid.3mf --printer printers.json --printer-id 'Prusa MK4' "
                      "--no-wall-check > build.json", self.reproduce_text())
        self.export()
        self.assertEqual(verdict(reproduce("deliver/source")), verdict(out))

    def test_a_missing_printers_json_is_named_not_dropped(self):
        """Reverse (audit 8): the printers.json the build used is gone. The commands keep naming it,
        so the re-check finds it missing too, and bundle_missing lists it; when the build judged an
        object with it, the bundle is refused (the rebuild would judge that object without it)."""
        self.write_params()
        self.record()
        os.remove(".3dprint/printers.json")
        code, out = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 0, out["errors"])
        self.assertIn(".3dprint/printers.json: the printers.json the build used", out["bundle_missing"])
        text = self.reproduce_text()
        self.assertIn("--no-3mf --printer .3dprint/printers.json --no-wall-check > build.json", text)
        self.assertIn("finalize.py\" --build build.json --params params.json --printer .3dprint/printers.json", text)
        self.export()
        self.assertEqual(verdict(reproduce("deliver/source")), verdict(out))   # "printer file not found" there too
        with open(".3dprint/printers.json", "w") as f:
            json.dump(X2D, f)
        self.write_params(self.GROUPED)
        built = self.record()
        os.remove(".3dprint/printers.json")
        if any(o.get("checks") for o in built["objects"]):
            self.refused(folder="deliver/set", why=(".3dprint/printers.json is gone since the build",))

    def run_proxy(self, place):
        """The plug proxy as `build.py run --proxy` leaves it, its build JSON saved at `place`
        (written directly: no engine)."""
        import validate
        with open(".3dprint/plug.json", "w") as f:
            json.dump(self.PLUG, f)
        validate.write_manifest("out/plug.stl", ["plug.py"], self.PLUG, "python", by="run")
        with open(place, "w") as f:
            json.dump({"schema": "3dprint-scout.build/1", "ran": True, "command": "run", "engine": "python",
                       "source": "plug.py",
                       "sources": ["plug.py"], "params": ".3dprint/plug.json", "proxy": True,
                       "parts": [{"name": "plug", "stl": "out/plug.stl",
                                  "sha256": validate.file_sha256("out/plug.stl")}]}, f)

    def test_a_proxy_built_again_takes_no_place_the_bundle_writes(self):
        """Reverse (audit 2): REPRODUCE.md saves a proxy built again at its build JSON's place, after
        the main rebuild wrote build.json: there it must not take a file the bundle writes itself,
        nor the place of another build's output."""
        plug = {"name": "plug through notch", "report": "out/fit_plug.json", "proxy": True, "dims": ["usb-c-plug"]}
        for place in ("out/plug_build.json", "build.json", "Params.json"):
            with self.subTest(place=place):
                self.params(self.verify([self.SEAT, self.CABLE], joints=[
                    {"name": "lid on box", "report": "out/fit_seat.json"}, dict(plug, proxy_build=place)]), **self.PLUG)
                self.record()
                self.run_proxy(place)
                if place == "out/plug_build.json":
                    code, out = self.finalize("--bundle", "deliver/source")
                    self.assertEqual(code, 0, out["errors"])
                    self.assertEqual(out["joints"][1]["proxy_build"], "tied")
                    self.assertIn("--proxy plug --engine python --out out > out/plug_build.json", self.reproduce_text())
                    shutil.rmtree("deliver")
                else:
                    self.refused(why=(f"is saved as or built into {place}, a file the bundle writes itself",))
                    os.remove(place)
        self.run_proxy("out/plug_again.json")                                  # the same proxy, saved twice
        self.params(self.verify([self.SEAT, self.CABLE], joints=[
            {"name": "lid on box", "report": "out/fit_seat.json"}, dict(plug, proxy_build="out/plug_build.json"),
            dict(plug, name="plug again", proxy_build="out/plug_again.json")]), **self.PLUG)
        self.refused(why=("is built again into out/plug.stl (the proxy of joint 'plug again')",
                          "which another build in REPRODUCE.md writes too"))

    def test_a_file_the_rebuild_writes_again_is_not_carried(self):
        """Reverse (audit 6): the commands of REPRODUCE.md write the parts, their manifests and the
        core 3MF again; a carried file at one of those places (a delivery into out/, a measurement of
        the core 3MF) would be replaced by the rebuild and judged anew, so the bundle refuses it."""
        self.write_params()
        built = self.record_3mf()
        self.refused("--deliver", "out", why=("out/box.stl (delivered file; REPRODUCE.md writes the part box there)",
                                              "deliver into a folder of its own"))
        if HAS_NP:
            measure_report("out/m_plate.json", "info", built["threemf"], "--expect", "objects[0].size_mm[0]=40",
                           "--tol", "0.1")
            v = self.full_verify()
            v["measurements"] = [{"name": "plate", "report": "out/m_plate.json"}]
            self.write_params(verify=v)
            self.refused(why=("out/box_lid.3mf (file read by measurement 'plate'; REPRODUCE.md writes the core 3MF "
                              "there)",))

    def test_the_delivery_folder_is_looked_for_before_the_bundle_is_made(self):
        """Reverse (audit 7): the documented call, `--deliver deliver/<date> --bundle
        deliver/<date>/source`, before the delivery folder is made: the bundle folder makes it, so it
        must be looked for first; the bundle holds no empty delivery folder and the re-check from it
        says "not found" too."""
        self.write_params()
        self.record()
        code, out = self.finalize("--deliver", "deliver/2026-10-21", "--bundle", "deliver/2026-10-21/source")
        self.assertEqual(code, 0, out["errors"])
        self.assertIn("delivery folder deliver/2026-10-21 not found", out["open"])
        self.assertFalse(os.path.exists("deliver/2026-10-21/source/deliver"))
        self.export("deliver/2026-10-21/source")
        self.assertEqual(verdict(reproduce("deliver/2026-10-21/source")), verdict(out))

    def test_parts_outside_the_project_are_refused(self):
        """Reverse (audit 9): parts built or recorded outside the project folder (../exports/box.stl)
        are not carried (the rebuild makes them in the bundle's out/), but the reports still name
        them where they were: the bundle is refused."""
        far = tempfile.mkdtemp(prefix="3dps-parts-")
        self.addCleanup(shutil.rmtree, far, ignore_errors=True)
        for n in ("box", "lid"):
            shutil.copyfile(os.path.join("out", n + ".stl"), os.path.join(far, n + ".stl"))
        self.write_params()
        self.record_3mf(*(os.path.relpath(os.path.join(far, n + ".stl")) for n in ("box", "lid")), flags=("--no-3mf",))
        error = self.refused(why=("box.stl, lid.stl is outside the project folder",))
        self.assertNotIn(far, error)

    def test_a_machine_path_is_found_in_any_usual_encoding(self):
        """Reverse (audit 11): a carried text file saved in Latin-1, cp1252 or UTF-16 that holds a
        folder of this machine with a non-ASCII letter was read as UTF-8 and missed; the bytes are
        searched in each encoding. A whole folder only: not /home/joséphine, not src/home/josé."""
        homes = ["/home/josé", "/home/Šárka"]
        with mock.patch.object(finalize, "machine_prefixes", return_value=homes):
            for text, enc, found in (("x = '/home/josé/a.svg'", "utf-8", True),
                                     ("x = '/home/josé/a.svg'", "latin-1", True),
                                     ("x = '/home/Šárka/a.svg'", "cp1252", True),
                                     ("x = '/home/josé/a.svg'", "utf-16-le", True),
                                     ("x = '/HOME/josé/a.svg'", "utf-16", True),
                                     ("x = '/home/josé/a.svg'", "utf-16-be", True),
                                     ("-I/home/josé/inc", "latin-1", True),
                                     ("x = '/home/joséphine/a.svg'", "latin-1", False),
                                     ("x = 'src/home/josé/a.svg'", "latin-1", False)):
                with self.subTest(text=text, enc=enc):
                    with open("t.txt", "wb") as f:
                        f.write(text.encode(enc))
                    self.assertEqual(finalize.holds_machine_path("t.txt"), found)
        with open("gen.py", "ab") as f:
            f.write("# outline traced from /home/josé/outline.dxf\n".encode("latin-1"))
        self.write_params()
        self.record()
        with mock.patch.object(finalize, "machine_prefixes", return_value=[os.getcwd(), "/home/josé"]):
            self.refused(why=("gen.py holds a path of this machine",))

    def test_commands_are_never_scrubbed_and_a_folder_is_taken_out_whole(self):
        """Reverse (audit 5): with a short home folder (/root: a container, CI), REPRODUCE.md's
        command `run src/root/gen.py` came out as `run src~/gen.py`. The commands hold relative paths
        and are not scrubbed; elsewhere a folder is taken out only as a whole folder."""
        with mock.patch.object(finalize, "machine_forms", return_value=[("/root", "~")]):
            for text, want in (("src/root/gen.py", None), ("src/roots/gen.py", None), ("/rootbeer/x", None),
                               ("/root/x", "~/x"), ("-I/root/inc", "-I~/inc"), ("file:///root/x", "file://~/x"),
                               ('"/root"', '"~"'), ("saved in /root.", "saved in ~.")):
                self.assertEqual(finalize.scrub(text), want or text, text)
        os.makedirs("src/root")
        shutil.move("gen.py", "src/root/gen.py")
        self.write_params()
        code, built = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "src/root/gen.py", "--params",
                          ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out",
                          "--no-wall-check", "--no-3mf")
        with open("out/build.json", "w") as f:
            json.dump(built, f)
        with mock.patch.object(finalize, "machine_prefixes", return_value=[os.getcwd(), "/root"]):
            code, out = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 0, out["errors"])
        text = self.reproduce_text()
        self.assertIn("Generator: `src/root/gen.py`", text)
        self.assertIn("--source src/root/gen.py --params params.json", text)

    def test_nothing_is_left_half_written(self):
        """Reverse (audit 12): what can make writing fail is checked before the folder is made (a
        source gone or a folder now, a build JSON field of another type), and a failure after it
        takes away every folder this run made; finalize alone reports a malformed build JSON as
        JSON, not a traceback."""
        self.write_params()
        with open("helper.py", "w") as f:
            f.write("W = 2\n")
        code, built = run(build, "record", "out/box.stl", "out/lid.stl", "--source", "gen.py", "helper.py", "--params",
                          ".3dprint/params.json", "--printer", ".3dprint/printers.json", "--out", "out",
                          "--no-wall-check", "--no-3mf")
        with open("out/build.json", "w") as f:
            json.dump(built, f)
        os.remove("helper.py")
        self.refused(why=("helper.py: a source the build hashed is gone or not a file",))
        os.makedirs("helper.py")
        self.refused(why=("helper.py: a source the build hashed is gone or not a file",))
        os.rmdir("helper.py")
        good = self.record()
        for change, why in (({"source": 5}, "the build JSON's source is not as build.py writes it"),
                            ({"engine": None}, "the build JSON's engine is"),
                            ({"validate_settings": dict(good["validate_settings"], tol="x")}, "validate_settings.tol")):
            with self.subTest(change=change):
                with open("out/build.json", "w") as f:
                    json.dump(dict(good, **change), f)
                self.refused(why=(why,))
        for change in ({"sources": ["gen.py", 7]}, {"parts": ["box"]}, {"validate_settings": "x"},
                       {"validate_settings": dict(good["validate_settings"], printer=5)}):
            with self.subTest(change=change):
                with open("out/build.json", "w") as f:
                    json.dump(dict(good, **change), f)
                code, out = self.finalize()
                self.assertEqual(code, 1)
                self.assertIn("as build.py writes it", out["errors"][0])
        with open("out/build.json", "w") as f:
            json.dump(good, f)
        real = shutil.copyfile

        def full_disk(src, dst, *a, **k):                    # the second copy fails, the folder is made by then
            calls.append(dst)
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            return real(src, dst, *a, **k)
        for parent in (False, True):
            with self.subTest(parent_exists=parent):
                if parent:
                    os.makedirs("deliver")
                calls = []
                with mock.patch("shutil.copyfile", full_disk):
                    code, out = self.finalize("--bundle", "deliver/new/source")
                self.assertEqual(code, 1, out.get("bundle"))
                self.assertIn("writing the bundle failed", out["errors"][0])
                self.assertEqual(len(calls), 2)
                self.assertEqual(os.path.isdir("deliver"), parent)              # only what this run made is gone
                self.assertFalse(os.path.exists("deliver/new"))

    @unittest.skipUnless(os.name == "posix", "a file name of raw bytes")
    def test_a_name_that_is_not_utf8(self):
        """Reverse (audit 12): a photo, or a delivered file, whose name is not UTF-8 (Latin-1 bytes from
        a camera card): the bundle names it and refuses before the folder is made (it wrote half a
        bundle, then a traceback), and finalize --deliver prints it as a JSON escape (a traceback)."""
        import subprocess
        os.makedirs("photos")
        try:
            with open(b"photos/caf\xe9.jpg", "wb") as f:
                f.write(b"\xff\xd8\xff\xe0 the user's photo")
        except OSError:
            self.skipTest("this file system takes UTF-8 names only")
        v = self.full_verify()
        v["test_prints"] = [{"name": "lid fit", "status": "skipped", "photos": [os.fsdecode(b"photos/caf\xe9.jpg")]}]
        self.write_params(verify=v)
        self.record()
        self.refused(why=("photos/caf\\udce9.jpg: a name the bundle would write is not UTF-8",))
        os.makedirs("deliver")
        shutil.copyfile("out/box.stl", b"deliver/bo\xeete.stl")
        r = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "finalize.py"), "--build", "out/build.json",
                            "--params", ".3dprint/params.json", "--deliver", "deliver"], capture_output=True,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        out = json.loads(r.stdout.decode("utf-8"))
        self.assertIn(os.fsdecode(b"deliver/bo\xeete.stl"), [d["file"] for d in out["delivered"]])


for _name in [n for n in dir(FinalizePromises) if n.startswith("test_")]:
    setattr(FinalizeBundle, _name, None)            # its helpers only: the promise tests run once, above


@unittest.skipUnless(HAS_M3D, "manifold3d and numpy not installed")
class BundleFromTheScripts(unittest.TestCase):
    """A project the scripts made as the skill runs them (build.py run, a proxy by build.py run
    --proxy from its own params file, fit.py, strength.py --from-build, measure.py of the user's
    file, preview.py, bambu3mf.py), bundled, then rebuilt and re-checked from the bundle alone
    with the commands of its REPRODUCE.md as written: the same verdict."""

    GEN = ("import manifold3d as m3d\n"
           "DEFAULTS = {'ribbon_t': 8.0, 'ribbon_w': 12.0, 'arm': {'len': 40.0}, 'arm_support': 'cantilever',\n"
           "            'plug_w': 13, 'plug_h': 8, 'plug_l': 9}\n"
           "def build(params):\n"
           "    p = {**DEFAULTS, **params}\n"
           "    return {'sled': m3d.Manifold.cube([p['arm']['len'], p['ribbon_w'], p['ribbon_t']])}\n")
    PROXY = ("import manifold3d as m3d\n"
             "def build(p):\n"
             "    return {'plug': m3d.Manifold.cube([p['plug_w'], p['plug_h'], p['plug_l']]).translate([0, 0, 8.5])}\n")
    PRESET = "0.20mm Standard @BBL X1C"
    PRINTERS = {"schema": "3dprint.printers/1", "printers": {"x1c": {
        "process": "fdm", "slicer": {"name": "bambu-studio"},
        "bed": {"area": [[0, 0], [256, 0], [256, 256], [0, 256]], "height": 250, "exclude": [], "source": "slicer-profile"}}}}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="3dps-bundle-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)
        for d in (".3dprint", "out", "ref", "photos", "deliver"):
            os.makedirs(d)
        for path, text in (("gen.py", self.GEN), ("plug.py", self.PROXY)):
            with open(path, "w") as f:
                f.write(text)
        self.write(".3dprint/printers.json", self.PRINTERS)
        self.write(".3dprint/plug.json", {"plug_w": 13, "plug_h": 8, "plug_l": 9})        # the proxy's numbers only

    @staticmethod
    def write(path, obj):
        with open(path, "w") as f:
            json.dump(obj, f)

    @staticmethod
    def script(name, *argv, save=None):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", name), *argv], capture_output=True,
                           encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert r.returncode in (0, 1), (name, r.stdout[-1500:], r.stderr[-1500:])
        if save:
            with open(save, "w", encoding="utf-8") as f:
                f.write(r.stdout)
        return r.returncode, json.loads(r.stdout) if r.stdout.strip().startswith("{") else None

    def params(self, verify=None):
        self.write(".3dprint/params.json", {"_material": "pla_basic", "_print": {"preset": self.PRESET},
                                             "_parts": {"sled": {"expect": [40, 12, 8]}},
                                             "plug_w": 13, "plug_h": 8, "plug_l": 9, "_verify": verify or {}})

    def test_the_bundle_rebuilds_and_reaches_the_same_verdict(self):
        import validate
        from test_bambu3mf import make_template
        self.params()
        code, built = self.script("build.py", "run", "gen.py", "--params", ".3dprint/params.json", "--printer",
                                  ".3dprint/printers.json", "--out", "out", save="out/build.json")
        self.assertEqual(built["gate"], "PASS", built["errors"])
        self.script("build.py", "run", "plug.py", "--params", ".3dprint/plug.json", "--proxy", "plug", "--out", "out/plug",
                    save="out/plug_build.json")
        code, fit = self.script("fit.py", "out/sled.stl", "out/plug/plug.stl", "--play", "none", save="out/fit_plug.json")
        self.assertEqual(fit["gate"], "PASS", fit)
        code, member = self.script("strength.py", "beam", "--from-build", "out/build.json", "--part", "sled",
                                   "--param", "h=ribbon_t", "--param", "b=ribbon_w", "--param", "length=arm.len",
                                   "--param", "support=arm_support", "--load", "finger_push", save="out/strength_sled.json")
        self.assertEqual(member["gate"], "PASS", member)
        write_stl("ref/plug.stl", box(13.05, 8, 9))                            # the user's model of the plug
        self.script("measure.py", "info", "ref/plug.stl", "--expect", "objects[0].size_mm[0]=13", "--tol", "0.1",
                    save="out/m_plug.json")
        self.script("preview.py", "out/sled.stl", "-o", "out/look.png", "--size", "400x300")
        with open("photos/arm.jpg", "wb") as f:
            f.write(b"\xff\xd8\xff\xe0 the user's photo of the printed arm")
        make_template("template.3mf", filament_settings_id=["Bambu PLA Basic @BBL X1C", "Bambu PETG HF @BBL X1C"],
                      print_settings_id=self.PRESET)
        self.write("job.json", {"template": "template.3mf", "out": "deliver/sled_bambu.3mf",
                                "parts": [{"name": "sled", "stl": "out/sled.stl", "filament": 1}]})
        self.script("bambu3mf.py", "job.json")
        sled = validate.file_sha256("out/sled.stl")
        self.params({
            "promises": [
                {"id": "cable-out", "kind": "use", "text": "the plug clears the sled", "conditions": "plug at rest",
                 "success": "no overlap", "evidence": [{"joint": "plug over sled"}]},
                {"id": "hold-push", "kind": "use", "text": "the arm takes a finger push", "conditions": "pushed at the tip",
                 "success": "no break", "evidence": [{"strength": "sled arm"}]},
                {"id": "plain", "kind": "look", "text": "a plain block", "evidence": [{"seen": "iso"}]},
                {"id": "in-hand", "kind": "use", "text": "it feels right in the hand", "conditions": "held",
                 "success": "the user says so", "evidence": [{"test_print": "arm print"}]}],
            "dims": [{"id": "plug-head", "what": "plug head width, from the maker's model", "params": {"plug_w": 13},
                      "source": "user-file", "from": {"plug_w": "plug width"}, "tol": 0.1},
                     {"id": "plug-rest", "what": "plug height and length", "params": {"plug_h": 8, "plug_l": 9},
                      "source": "caliper", "by": "user"}],
            "joints": [{"name": "plug over sled", "report": "out/fit_plug.json", "proxy": True,
                        "dims": ["plug-head", "plug-rest"], "proxy_build": "out/plug_build.json"}],
            "strength": [{"name": "sled arm", "report": "out/strength_sled.json"}],
            "measurements": [{"name": "plug width", "report": "out/m_plug.json"}],
            "seen": [{"name": "iso", "image": "out/look.png", "image_sha256": validate.file_sha256("out/look.png"),
                      "by": "user", "promises": ["plain"], "result": "passed"}],
            "test_prints": [{"name": "arm print", "status": "passed", "promises": ["in-hand"], "printer": "x1c",
                             "orientation": "as built", "by": "user", "preset": self.PRESET, "photos": ["photos/arm.jpg"],
                             "parts": {"sled": {"sha256": sled, "material": "pla_basic"}}}],
            "accepted": [], "unverified": [],
            "references": {"sled": {d: "real" for d in finalize.DIRECTIONS}}})
        argv = ("finalize.py", "--build", "out/build.json", "--params", ".3dprint/params.json", "--deliver", "deliver")
        code, out = self.script(*argv, "--bundle", "deliver/source")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual((out["use"], out["geometry"]), ("verified", "verified"), out["open"])
        for path in ("plug.py", ".3dprint/plug.json", "ref/plug.stl", "out/fit_plug.json", "out/m_plug.json",
                     "out/strength_sled.json", "out/look.png", "out/look.png.json", "photos/arm.jpg",
                     "deliver/sled_bambu.3mf", "deliver/sled_bambu.3mf.manifest.json"):
            self.assertIn("deliver/source/" + path, out["bundle"])
        for path in ("out/sled.stl", "out/plug_build.json", "out/plug/plug.stl"):   # made again, like the parts
            self.assertFalse(os.path.exists("deliver/source/" + path), path)
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            text = f.read()
        self.assertIn('build.py" run plug.py --params .3dprint/plug.json --proxy plug --engine python --out out/plug '
                      '> out/plug_build.json', text)                       # the engine it was built with (Codex, PR #22)
        self.assertLess(text.index("--proxy plug"), text.index("finalize.py"))
        self.assertIn('build.py" run gen.py --engine python --params params.json --out out --3mf gen.3mf '
                      "--printer printers.json > build.json", text)    # its engine and its core 3MF, as built
        self.assertNotIn(self.tmp, text)
        again = reproduce("deliver/source")
        self.assertEqual(verdict(again), verdict(out))
        self.assertTrue(os.path.isfile("deliver/source/out/plug/plug.stl"))
        # Reverse: a proxy whose params file changed since it was built would be another proxy built
        # again; its STL is carried as it was, and its build JSON left out (and said so).
        self.write(".3dprint/plug.json", {"plug_w": 13, "plug_h": 8, "plug_l": 9, "plug_r": 1})
        code, out = self.script(*argv, "--bundle", "deliver/later")
        self.assertEqual(code, 0, out["errors"])
        self.assertEqual(out["use"], "not verified")
        self.assertTrue(any(r.endswith("was not built from .3dprint/plug.json as it is now (or its generator changed): "
                                       "build it again and fit again") for r in out["promises"][0]["reasons"]))
        self.assertIn("deliver/later/out/plug/plug.stl", out["bundle"])
        self.assertTrue(any(m.startswith("out/plug_build.json: proxy build of joint 'plug over sled', left out")
                            for m in out["bundle_missing"]), out["bundle_missing"])
        with open("deliver/later/REPRODUCE.md", encoding="utf-8") as f:
            self.assertNotIn("--proxy", f.read())
        again = reproduce("deliver/later")
        # A known difference, accepted: the same tiers and states, but not the same reason. Here the
        # proxy "was not built from .3dprint/plug.json as it is now"; in the bundle, whose build JSON
        # for it is left out, "proxy build out/plug_build.json: No such file or directory". So this
        # case compares tiers and states only, not reasons or the open lines.
        same = ("use", "geometry", "print")
        self.assertEqual({k: again[k] for k in same}, {k: out[k] for k in same})
        self.assertEqual([(p["id"], p["state"]) for p in again["promises"]], [(p["id"], p["state"]) for p in out["promises"]])


@unittest.skipUnless(find_spec("bpy") is not None and HAS_M3D, "bpy module or manifold3d not installed")
class BundleFromABlenderBuild(unittest.TestCase):
    """A Blender project bundled, then rebuilt from its REPRODUCE.md: the parts are the same bytes
    again, so the evidence tied to them by sha256 (a look at a preview, a test print, a strength
    report linked to the build) reaches the same verdict. Before 0.7.0's fix every Blender build
    wrote the same triangles in another order (and a manifold3d part other triangles), and the
    bundle lost all three."""

    PRESET = BundleFromTheScripts.PRESET
    PRINTERS = BundleFromTheScripts.PRINTERS
    write = staticmethod(BundleFromTheScripts.write)
    script = staticmethod(BundleFromTheScripts.script)

    def setUp(self):
        from test_build import BLENDER_REBUILD_GEN
        self.tmp = tempfile.mkdtemp(prefix="3dps-bundle-blender-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)
        for d in (".3dprint", "out", "photos", "deliver"):
            os.makedirs(d)
        with open("stand.py", "w") as f:
            f.write(BLENDER_REBUILD_GEN)
        self.write(".3dprint/printers.json", self.PRINTERS)

    def params(self, verify=None):
        self.write(".3dprint/params.json", {"_material": "pla_basic", "_print": {"preset": self.PRESET},
                                             "_parts": {"block": {"expect": [40, 30, 12]}, "cap": {"expect": [20, 12, 6]}},
                                             "_verify": verify or {}})

    def test_the_bundle_rebuilds_the_same_stls_and_reaches_the_same_verdict(self):
        import validate
        self.params()
        code, built = self.script("build.py", "run", "stand.py", "--params", ".3dprint/params.json", "--printer",
                                  ".3dprint/printers.json", "--out", "out", save="out/build.json")
        self.assertEqual((built["engine"], built["gate"]), ("blender", "PASS"), built["errors"])
        code, member = self.script("strength.py", "beam", "--from-build", "out/build.json", "--part", "block",
                                   "--param", "h=h", "--param", "b=d", "--param", "length=w", "--param", "support=support",
                                   "--load", "finger_push", save="out/strength_block.json")
        self.assertEqual(member["gate"], "PASS", member)
        self.script("preview.py", "out/block.stl", "out/cap.stl", "-o", "out/look.png", "--size", "400x300")
        with open("photos/print.jpg", "wb") as f:
            f.write(b"\xff\xd8\xff\xe0 the user's photo of the print")
        from test_bambu3mf import make_template
        make_template("template.3mf", filament_settings_id=["Bambu PLA Basic @BBL X1C"], print_settings_id=self.PRESET)
        self.write("job.json", {"template": "template.3mf", "out": "deliver/stand_bambu.3mf",
                                "parts": [{"name": n, "stl": f"out/{n}.stl", "filament": 1} for n in ("block", "cap")]})
        self.script("bambu3mf.py", "job.json")                      # its manifest names each STL by its sha256
        sha = {p["name"]: p["sha256"] for p in built["parts"]}
        self.params({
            "promises": [
                {"id": "plain", "kind": "look", "text": "a plain block and cap", "evidence": [{"seen": "iso"}]},
                {"id": "push", "kind": "use", "text": "the block takes a finger push", "conditions": "pushed at the end",
                 "success": "no break", "evidence": [{"strength": "block"}]},
                {"id": "in-hand", "kind": "use", "text": "it feels right in the hand", "conditions": "held",
                 "success": "the user says so", "evidence": [{"test_print": "first print"}]}],
            "strength": [{"name": "block", "report": "out/strength_block.json"}], "joints": [],
            "seen": [{"name": "iso", "image": "out/look.png", "image_sha256": validate.file_sha256("out/look.png"),
                      "by": "user", "promises": ["plain"], "result": "passed"}],
            "test_prints": [{"name": "first print", "status": "passed", "promises": ["in-hand"], "printer": "x1c",
                             "orientation": "as built", "by": "user", "preset": self.PRESET, "photos": ["photos/print.jpg"],
                             "parts": {n: {"sha256": s, "material": "pla_basic"} for n, s in sha.items()}}],
            "accepted": [], "unverified": [],
            "references": {n: {d: "real" for d in finalize.DIRECTIONS} for n in sha}})
        code, out = self.script("finalize.py", "--build", "out/build.json", "--params", ".3dprint/params.json",
                                "--deliver", "deliver", "--bundle", "deliver/source")
        self.assertEqual(code, 0, out["errors"])
        states = {p["id"]: p["state"] for p in out["promises"]}
        self.assertEqual((out["use"], states), ("verified", {"plain": "verified", "push": "verified", "in-hand": "verified"}),
                         out["open"])
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            self.assertIn('build.py" run stand.py --engine blender ', f.read())
        again = reproduce("deliver/source")
        self.assertEqual(verdict(again), verdict(out))
        self.assertEqual({n: validate.file_sha256(os.path.join("deliver/source/out", n + ".stl")) for n in sha}, sha)


if __name__ == "__main__":
    unittest.main()
