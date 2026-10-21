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
        self.assertIn("lid: the delivered deliver/lid.stl is not the STL that was verified", out["open"])
        self.assertEqual({d["name"]: d["same_as_verified"] for d in out["delivered"]}, {"box": True, "lid": False})
        self.assertEqual(sorted(out["bundle"]), ["deliver/source/REPRODUCE.md", "deliver/source/source/gen.py",
                                                 "deliver/source/source/params.json", "deliver/source/verification.json"])
        with open("deliver/source/verification.json", encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn(self.tmp, text)                                       # no path of this machine
        self.assertNotIn(os.path.realpath(self.tmp), text)
        with open("deliver/source/REPRODUCE.md", encoding="utf-8") as f:
            self.assertIn("build.py\" record", f.read())                    # a recorded build says how to record it
        code, out = self.finalize("--bundle", "deliver/source")
        self.assertEqual(code, 1)
        self.assertIn("never overwrites", out["errors"][0])

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
            self.params(v)
            code, out = self.finalize()
            self.assertFalse(any(o.startswith(f"open warning (not accepted in _verify.accepted): {who} ") for o in out["open"]))

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
