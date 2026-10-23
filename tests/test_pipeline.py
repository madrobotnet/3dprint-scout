"""The scripts together, as the skill runs them (0.7.0 step 4): build.py run records the
parameters and each part's material, strength.py --from-build links a member to them, bambu3mf.py
names the filament and process preset it delivers, and finalize.py --deliver ties the three.
Each script has its own tests; these check that the contracts between them still meet."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
from test_bambu3mf import make_template  # noqa: E402

HAS_M3D = find_spec("manifold3d") is not None and find_spec("numpy") is not None
PRESET = "0.20mm Standard @BBL X1C"
GEN = """import manifold3d as m3d
DEFAULTS = {"ribbon_t": 8.0, "ribbon_w": 12.0, "arm": {"len": 40.0}, "arm_support": "cantilever"}
def build(params):
    p = {**DEFAULTS, **params}
    return {"sled": m3d.Manifold.cube([p["arm"]["len"], p["ribbon_w"], p["ribbon_t"]])}
"""
PRINTERS = {"schema": "3dprint.printers/1", "printers": {"x1c": {
    "process": "fdm", "slicer": {"name": "bambu-studio"},
    "bed": {"area": [[0, 0], [256, 0], [256, 256], [0, 256]], "height": 250, "exclude": [], "source": "slicer-profile"}}}}
FILAMENTS = ["Bambu PLA Basic @BBL X1C", "Bambu PETG HF @BBL X1C", "My PLA", "Generic PLA"]
LINKS = ["--param", "h=ribbon_t", "--param", "b=ribbon_w", "--param", "length=arm.len"]


def script(name, *argv, ok=(0,)):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *argv], capture_output=True, text=True)
    assert r.returncode in ok, (name, r.returncode, r.stdout[-1500:], r.stderr[-1500:])
    return r.stdout


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@unittest.skipUnless(HAS_M3D, "manifold3d and numpy not installed")
class StrengthToDelivery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.makedirs(".3dprint")
        os.makedirs("out")
        os.makedirs("deliver")
        with open("gen.py", "w") as f:
            f.write(GEN)
        self.write(".3dprint/printers.json", PRINTERS)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def write(self, path, obj):
        with open(path, "w") as f:
            json.dump(obj, f)

    def params(self, material="pla_basic", printed=None, **values):
        """params.json: one use promise on the member, one on a test print of the sled (when
        printed gives the sha256 it printed)."""
        verify = {
            "promises": [{"id": "hold-push", "kind": "use", "text": "the arm takes a finger push",
                          "conditions": "pushed at the tip", "success": "no break",
                          "evidence": [{"strength": "sled arm", "covers": "the push"}]}],
            "dims": [], "joints": [], "measurements": [], "seen": [], "unverified": [], "accepted": [],
            "strength": [{"name": "sled arm", "report": "out/strength_sled.json"}], "test_prints": [],
            "references": {"sled": {d: "real" for d in ("front", "back", "left", "right", "top", "bottom")}}}
        if printed:
            verify["promises"].append({"id": "in-hand", "kind": "use", "text": "the arm feels right in the hand",
                                       "conditions": "held", "success": "the user says so",
                                       "evidence": [{"test_print": "arm print", "covers": "in hand"}]})
            verify["test_prints"] = [{"name": "arm print", "status": "passed", "promises": ["in-hand"],
                                      "printer": "x1c", "orientation": "as built", "by": "user", "preset": PRESET,
                                      "parts": {"sled": {"sha256": printed, "material": "pla_basic"}}}]
        expect = [40, 12, values.get("ribbon_t", 8.0)]
        self.write(".3dprint/params.json", dict({"_material": material, "_print": {"preset": PRESET},
                                                 "_parts": {"sled": {"expect": expect}}, "_verify": verify}, **values))

    def build(self):
        out = script("build.py", "run", "gen.py", "--params", ".3dprint/params.json",
                     "--printer", ".3dprint/printers.json", "--out", "out", "--no-3mf")
        with open("out/build.json", "w") as f:
            f.write(out)
        return json.loads(out)

    def strength(self, *extra):
        out = script("strength.py", "beam", "--from-build", "out/build.json", "--part", "sled", *LINKS,
                     "--load", "finger_push", *extra, ok=(0, 1))
        with open("out/strength_sled.json", "w") as f:
            f.write(out)
        return json.loads(out)

    def deliver(self, slot=1, process=PRESET):
        make_template("template.3mf", filament_settings_id=FILAMENTS, print_settings_id=process)
        self.write("job.json", {"template": "template.3mf", "out": "deliver/sled_bambu.3mf",
                                "parts": [{"name": "sled", "stl": "out/sled.stl", "filament": slot}]})
        script("bambu3mf.py", "job.json")

    def finalize(self):
        return json.loads(script("finalize.py", "--build", "out/build.json", "--params", ".3dprint/params.json",
                                 "--deliver", "deliver"))

    def states(self, out):
        return {p["id"]: (p["state"], p["reasons"]) for p in out["promises"]}

    def test_linked_member_and_test_print_verify_through_the_bambu_project(self):
        self.params()
        built = self.build()
        self.assertEqual(built["parameters"], {"scope": "merged", "values": {
            "ribbon_t": 8.0, "ribbon_w": 12.0, "arm": {"len": 40.0}, "arm_support": "cantilever"}})
        self.assertEqual([p["material"] for p in built["parts"]], ["pla_basic"])
        rep = self.strength("--param", "support=arm_support")
        self.assertEqual(rep["gate"], "PASS")
        self.assertEqual(rep["from_build"]["sha256"], [p["sha256"] for p in built["parts"]][0])
        self.assertEqual({k: v for k, v in rep["inputs_from"].items() if v.startswith("param:")},
                         {"h": "param:ribbon_t", "b": "param:ribbon_w", "length": "param:arm.len",
                          "support": "param:arm_support"})
        self.params(printed=sha256("out/sled.stl"))                           # _verify only: the build stays fresh
        self.deliver()
        out = self.finalize()
        self.assertEqual((out["use"], out["geometry"]), ("verified", "verified"), out["open"])
        bambu = [d for d in out["delivered"] if d["kind"] == "3mf"][0]
        self.assertEqual((bambu["filaments"], bambu["preset"]),
                         ({"sled": {"slot": 1, "settings": FILAMENTS[0], "material": "pla_basic"}}, PRESET))

    def test_what_breaks_the_links(self):
        """Reverse: each change the plan names keeps a promise from verifying, by name."""
        self.params()
        self.build()
        self.strength("--param", "support=arm_support")
        printed = sha256("out/sled.stl")
        self.params(printed=printed)
        with self.subTest("filament of another material"):
            self.deliver(slot=2)
            got = self.states(self.finalize())
            self.assertEqual(got["hold-push"], ("not verified", [
                "member 'sled arm': the print file prints sled in petg_hf, the part is pla_basic"]))
            self.assertEqual(got["in-hand"][0], "not verified")
        os.remove("deliver/sled_bambu.3mf")
        os.remove("deliver/sled_bambu.3mf.manifest.json")
        with self.subTest("a filament finalize cannot name"):
            self.deliver(slot=3)
            self.assertEqual(self.states(self.finalize())["hold-push"][0], "assumed")
        os.remove("deliver/sled_bambu.3mf")
        os.remove("deliver/sled_bambu.3mf.manifest.json")
        with self.subTest("another process preset"):
            self.deliver(process="0.16mm Optimal @BBL X1C")
            got = self.states(self.finalize())
            self.assertEqual(got["hold-push"][0], "verified")                  # the member does not hang on the preset
            self.assertEqual(got["in-hand"], ("not verified", [
                'test print \'arm print\': printed with preset "0.20mm Standard @BBL X1C", '
                'the delivery uses "0.16mm Optimal @BBL X1C"']))
        with self.subTest("support typed on the command line"):
            self.strength("--support", "cantilever")
            self.assertEqual(self.states(self.finalize())["hold-push"], ("not verified", [
                "member 'sled arm': support was typed in, not taken from the build's parameters"]))
        with self.subTest("a parameter changed and built again"):
            self.strength("--param", "support=arm_support")
            self.params(printed=printed, ribbon_t=8.5)
            self.build()
            out = self.finalize()
            self.assertEqual(self.states(out)["hold-push"], ("not verified", [
                "member 'sled arm': calculated for an earlier sled; h was ribbon_t = 8.0, now 8.5"]))
            self.assertEqual(out["geometry"], "not verified")
        with self.subTest("material changed in params.json after the build"):
            self.params(printed=printed, material="petg_hf", ribbon_t=8.5)
            out = self.finalize()
            self.assertEqual(out["material_drift"], ["sled: material changed since the build (pla_basic -> petg_hf)"])


if __name__ == "__main__":
    unittest.main()
