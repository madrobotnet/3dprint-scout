"""Tests for scripts/build.py and scripts/threemf.py."""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from importlib.util import find_spec
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import build    # noqa: E402
import threemf  # noqa: E402
from test_validate import X2D, box, write_stl  # noqa: E402

HAS_SCAD = build.find_openscad() is not None
HAS_M3D = find_spec("manifold3d") is not None
HAS_BPY = find_spec("bpy") is not None

SCAD = """
// PARAMETERS
w = 40; d = 30; h = 20; wall = 2; lid_h = 3;
part = "body";
$fa = 1; $fs = 0.4;
include <lib.scad>
if (part == "body") difference() { cube([w, d, h]); translate([wall, wall, wall]) cube([w - 2*wall, d - 2*wall, h]); }
if (part == "lid") lid(w, d, lid_h);
"""
LIB = "module lid(w, d, t) { cube([w, d, t]); }\n"

PYGEN = """
import manifold3d as m3d
def build(p):
    body = m3d.Manifold.cube([p["w"], p["d"], p["h"]])
    inner = m3d.Manifold.cube([p["w"] - 2*p["wall"], p["d"] - 2*p["wall"], p["h"]]).translate([p["wall"], p["wall"], p["wall"]])
    return {"body": body - inner, "peg": m3d.Manifold.cylinder(10, 4, 4, 64)}
"""

# The DEFAULTS convention (engines/python.md). build() writes to both dicts after merging: what
# it computes or changes there is not what the parts were built from and must not be recorded.
PYGEN_DEFAULTS = """
import manifold3d as m3d
DEFAULTS = {"w": 40.0, "d": 30.0, "h": 20.0, "wall": 2.0, "plug": {"w": 3.0, "fit": "snug"}, "_note": "metadata"}
def build(params):
    p = {**DEFAULTS, **params}
    params["derived"] = p["h"] - p["wall"]
    DEFAULTS["d"] = 999.0
    body = m3d.Manifold.cube([p["w"], p["d"], p["h"]])
    return {"body": body, "peg": m3d.Manifold.cylinder(10, 4, 4, 64)}
"""


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = build.main(list(argv))
    return code, json.loads(buf.getvalue())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.out = os.path.join(self.d, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w") as f:
            f.write(text)
        return p

    def params(self, data):
        return self.write("params.json", json.dumps(data))


class Detect(Base):
    def test_failed_openscad_is_not_available(self):
        with mock.patch.object(build, "find_openscad", return_value="/broken/openscad"), \
                mock.patch.object(build, "openscad_info", return_value={"error": "missing shared library"}), \
                mock.patch.object(build, "blender_status", return_value={"binary": None, "bpy": None, "notes": []}):
            code, out = run("detect")
        self.assertEqual(code, 0)
        self.assertNotIn("openscad", out["available"])
        self.assertIn("missing shared library", out["warnings"])
        self.assertFalse(any("CGAL" in n for n in out["notes"]))

    def test_openscad_version_failure_is_not_backend_support(self):
        result = subprocess.CompletedProcess([], 127, "", "missing library")
        with mock.patch.object(build.subprocess, "run", return_value=result) as probe:
            info = build.openscad_info("/broken/openscad")
        self.assertIn("status 127", info["error"])
        self.assertEqual(probe.call_count, 1)

    def test_openscad_default_export_must_produce_a_valid_mesh(self):
        def probe(argv, **kwargs):
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, "OpenSCAD version 2021.01", "")
            if "--backend=manifold" in argv:
                return subprocess.CompletedProcess(argv, 1, "", "unknown backend")
            write_stl(argv[argv.index("-o") + 1], box(1, 1, 1))
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(build.subprocess, "run", side_effect=probe):
            info = build.openscad_info("/scad")
        self.assertFalse(info["manifold"])
        self.assertNotIn("error", info)
        # A successful exit with no artifact is not readiness.
        with mock.patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "version 2021.01", "")):
            info = build.openscad_info("/scad")
        self.assertIn("cube export failed", info["error"])

    def test_detect_reports_engines(self):
        code, out = run("detect")
        self.assertEqual(code, 0)
        self.assertIn("available", out)
        if HAS_SCAD:
            self.assertIn("openscad", out["available"])
            self.assertIn(out["engines"]["openscad"]["manifold"], (True, False))


@unittest.skipUnless(HAS_SCAD, "OpenSCAD not installed")
class OpenSCAD(Base):
    def setUp(self):
        super().setUp()
        self.src = self.write("box.scad", SCAD)
        self.lib = self.write("lib.scad", LIB)
        self.prm = self.params({"_parts": {"body": {"expect": [40, 30, 20]}, "lid": {"expect": [40, 30, 3]}},
                                "w": 40, "d": 30, "h": 20, "wall": 2, "lid_h": 3})

    def test_two_parts_manifests_3mf_and_gate(self):
        code, out = run("run", self.src, "--params", self.prm, "--out", self.out, "--no-wall-check")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual([p["name"] for p in out["parts"]], ["body", "lid"])
        self.assertEqual(out["R4"], "PASS")
        for p in out["parts"]:
            self.assertTrue(os.path.isfile(p["stl"] + ".manifest.json"))
            checks = p["validate"]["files"][0]["checks"]
            self.assertEqual(checks["D1"]["state"], "PASS", p["name"])
            self.assertEqual(checks["R3"]["state"], "PASS", p["name"])
        self.assertTrue(any(os.path.basename(s) == "lib.scad" for s in out["sources"]))   # include tracked
        self.assertTrue(os.path.isfile(out["threemf"]))

    def test_parameter_override_reaches_openscad(self):
        prm = self.params({"_parts": {"lid": {"expect": [55, 30, 3]}}, "w": 55, "lid_h": 3})
        code, out = run("run", self.src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["D1"]["state"], "PASS")

    def test_parameters_are_the_overrides_and_parts_carry_their_material(self):
        """OpenSCAD's own defaults (`d = 30;` in the .scad) are never read: the build records
        the -D values only, and no key is called a typo."""
        prm = self.params({"_material": "pla_basic", "_parts": {"body": {"expect": [40, 30, 20]},
                                                                 "lid": {"expect": [40, 30, 3], "material": "petg_hf"}},
                           "w": 40, "lid_h": 3, "unused": 1})
        code, out = run("run", self.src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "overrides", "values": {"w": 40, "lid_h": 3, "unused": 1}})
        self.assertFalse(any("typo" in w for w in out["warnings"]), out["warnings"])
        self.assertEqual({p["name"]: p["material"] for p in out["parts"]}, {"body": "pla_basic", "lid": "petg_hf"})
        self.assertNotIn("parameters", out["engine_info"])

    def test_changed_include_makes_evidence_stale(self):
        run("run", self.src, "--params", self.prm, "--out", self.out, "--no-wall-check")
        with open(self.lib, "a") as f:
            f.write("// edited after the build\n")
        stl = os.path.join(self.out, "lid.stl")
        sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
        import validate
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate.main([stl, "--source", self.src, self.lib, "--params", self.prm, "--no-wall-check"])
        self.assertEqual(json.loads(buf.getvalue())["files"][0]["checks"]["R3"]["state"], "FAIL")

    def test_syntax_error_is_reported(self):
        bad = self.write("bad.scad", "cube([1,2,3]")
        code, out = run("run", bad, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertFalse(out["ran"])
        self.assertEqual(out["R4"], "FAIL")
        self.assertTrue(re.search(r"(?i)error|parser", out["errors"][0]))
        self.assertEqual([f for f in os.listdir(self.out) if f.endswith(".deps")], [])   # no leftover deps file

    def test_missing_printers_file_leaves_d2_unverified(self):
        """SKILL.md passes --printer .3dprint/printers.json before the printer is known."""
        code, out = run("run", self.src, "--params", self.prm, "--out", self.out, "--no-wall-check",
                        "--printer", os.path.join(self.d, "nope", "printers.json"))
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["gate"], "INCOMPLETE")
        self.assertEqual(out["errors"], [])
        self.assertTrue(any("printer file not found" in w for w in out["warnings"]))   # lifted to the top
        for p in out["parts"]:
            self.assertEqual(p["validate"]["files"][0]["checks"]["D2"]["state"], "UNVERIFIED")
            self.assertEqual(p["validate"]["files"][0]["checks"]["D1"]["state"], "PASS")

    def test_unknown_printer_id_error_is_lifted(self):
        printers = self.write("printers.json", json.dumps(X2D))
        code, out = run("run", self.src, "--params", self.prm, "--out", self.out, "--no-wall-check",
                        "--printer", printers, "--printer-id", "nope")
        self.assertEqual(out["gate"], "FAIL")
        self.assertTrue(any("nope" in e and "not found" in e for e in out["errors"]), out["errors"])

    def test_bed_rotation_reaches_the_3mf(self):
        """A part D2 passes 'when rotated' is placed with that rotation in the core 3MF."""
        src = self.write("bar.scad", "part = \"bar\"; cube([300, 20, 10]);")
        prm = self.params({"_parts": {"bar": {"expect": [300, 20, 10]}}})
        printers = self.write("printers.json", json.dumps(X2D))
        code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--printer", printers)
        self.assertEqual(code, 0, out.get("errors"))
        d2 = out["parts"][0]["validate"]["files"][0]["checks"]["D2"]
        self.assertEqual(d2["state"], "PASS")
        self.assertEqual(out["parts"][0]["rotation_deg"], d2["value"]["rotation_deg"])
        self.assertGreater(out["parts"][0]["rotation_deg"], 0)
        self.assertTrue(any("rotated" in w for w in out["warnings"]))


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class PythonEngine(Base):
    def test_generator_parts(self):
        src = self.write("gen.py", PYGEN)
        prm = self.params({"_parts": {"body": {"expect": [40, 30, 20]}, "peg": {"expect": [8, 8, 10]}},
                           "w": 40, "d": 30, "h": 20, "wall": 2})
        code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check")
        self.assertEqual(code, 0, out.get("errors"))
        body = out["parts"][0]["validate"]["files"][0]
        self.assertEqual(body["checks"]["M1"]["state"], "PASS")
        self.assertEqual(body["checks"]["M2"]["state"], "PASS")
        self.assertAlmostEqual(body["metrics"]["volume_mm3"], 40 * 30 * 20 - 36 * 26 * 18, delta=1)
        peg = out["parts"][1]["validate"]["files"][0]
        self.assertEqual(peg["checks"]["D1"]["state"], "PASS")

    def test_generator_leaves_no_pycache(self):
        """S4-16: the generator and the modules it imports are run with PYTHONDONTWRITEBYTECODE=1,
        so the user's project folder does not gain a __pycache__."""
        src = self.write("gen.py", "import lib\nimport manifold3d as m3d\ndef build(p):\n    return {'gen': m3d.Manifold.cube(lib.SIZE)}\n")
        self.write("lib.py", "SIZE = [10, 10, 10]\n")
        code, out = run("run", src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(sorted(os.listdir(self.d)), ["gen.py", "lib.py", "out"])
        self.assertIn("lib.py", [os.path.basename(s) for s in out["sources"]])
        # build.py's own modules are not the generator's sources (a skill update must not make
        # every build stale); a skill library the generator imports (parts.py, and the strength.py
        # it takes the duty floors from) is.
        self.assertEqual(sorted(os.path.basename(s) for s in out["sources"]), ["gen.py", "lib.py"])
        src = self.write("gen2.py", "import parts\nimport manifold3d as m3d\ndef build(p):\n"
                                    "    return {'gen2': m3d.Manifold.cube([10, 10, 10])}\n")
        code, out = run("run", src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(sorted(os.path.basename(s) for s in out["sources"]), ["gen2.py", "parts.py", "strength.py"])

    def test_generator_warnings_reach_the_report(self):
        """A UserWarning raised while the generator runs (parts.text switching fonts) is a line
        in the build's warnings, not stderr nobody reads."""
        src = self.write("gen.py", "import warnings\nimport manifold3d as m3d\n"
                                   "def build(p):\n    warnings.warn('font switched to X')\n"
                                   "    warnings.warn('font switched to X')\n"
                                   "    warnings.warn('old api', DeprecationWarning)\n"
                                   "    return {'gen': m3d.Manifold.cube([10, 10, 10])}\n")
        code, out = run("run", src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual([w for w in out["warnings"] if "switched" in w or "old api" in w], ["font switched to X"])
        self.assertNotIn("warnings", out["engine_info"])

    def test_generator_exception(self):
        src = self.write("boom.py", "def build(p):\n    raise ValueError('wall too thin')\n")
        code, out = run("run", src, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("wall too thin", out["errors"][0])

    def test_parameters_merged_with_defaults(self):
        """A module DEFAULTS dict: the build records {**DEFAULTS, **params} as it was before
        build() ran, names a params.json key DEFAULTS lacks, and each part gets its material."""
        src = self.write("gen.py", PYGEN_DEFAULTS)
        prm = self.params({"_material": "petg_hf", "_parts": {"body": {"expect": [44, 30, 20]}, "peg": {"material": "pla_basic"}},
                           "w": 44.0, "walll": 3.0})
        code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "merged", "values": {
            "w": 44.0, "d": 30.0, "h": 20.0, "wall": 2.0, "plug": {"w": 3.0, "fit": "snug"}, "walll": 3.0}})
        self.assertEqual([w for w in out["warnings"] if "typo" in w],
                         ["params.json key 'walll' is not in the generator's DEFAULTS (a typo?)"])
        self.assertEqual({p["name"]: p["material"] for p in out["parts"]}, {"body": "petg_hf", "peg": "pla_basic"})
        self.assertEqual(out["params"], build._relpath(prm))                   # the params path stays (another drive on Windows: absolute)
        self.assertEqual(out["command"], "run")                                # finalize --bundle builds it again
        self.assertNotIn("parameters", out["engine_info"])
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["D1"]["state"], "PASS")

    def test_parameters_without_defaults_are_the_overrides(self):
        src = self.write("gen.py", PYGEN)
        prm = self.params({"_parts": {"body": {}, "peg": {}}, "w": 40, "d": 30, "h": 20, "wall": 2, "extra": "x"})
        code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "overrides",
                                             "values": {"w": 40, "d": 30, "h": 20, "wall": 2, "extra": "x"}})
        self.assertFalse(any("typo" in w for w in out["warnings"]), out["warnings"])   # nothing to compare with
        self.assertEqual([p["material"] for p in out["parts"]], [None, None])      # no _material: null, not a guess
        # A DEFAULTS that is not a dict is not merged, and the build says so.
        src = self.write("gen_list.py", "import manifold3d as m3d\nDEFAULTS = [('w', 10.0)]\n"
                                        "def build(p):\n    return {'gen_list': m3d.Manifold.cube([p['w'], 10, 10])}\n")
        prm = self.params({"w": 12.0})
        code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "overrides", "values": {"w": 12.0}})
        self.assertTrue(any("DEFAULTS is a list, not a dict" in w for w in out["warnings"]), out["warnings"])

    def test_a_default_that_is_not_json_is_recorded_as_its_repr(self):
        src = self.write("gen.py", "import manifold3d as m3d\n"
                                   "DEFAULTS = {'size': (10, 10, 10), 'shape': len, 'holes': {1, 2}, "
                                   "'plug': {'w': 3.0, 'fit': len}, 'bad': float('nan')}\n"
                                   "def build(params):\n    p = {**DEFAULTS, **params}\n"
                                   "    return {'gen': m3d.Manifold.cube(list(p['size']))}\n")
        code, out = run("run", src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "merged", "values": {
            "size": [10, 10, 10], "shape": "<built-in function len>", "holes": "{1, 2}",
            "plug": {"w": 3.0, "fit": "<built-in function len>"}, "bad": "nan"}})
        json.dumps(out, allow_nan=False)                                           # strict JSON throughout
        noted = [w for w in out["warnings"] if "is not a JSON value" in w]
        self.assertEqual([re.search(r"'([^']+)'", w).group(1) for w in noted], ["shape", "holes", "plug.fit", "bad"])
        self.assertFalse(any("'size'" in w for w in out["warnings"]))               # a tuple is a list, no warning


class ParametersRecord(unittest.TestCase):
    """The build JSON's "parameters" and parts[].material, without an engine."""

    def test_merged_or_overrides_and_typos(self):
        given = {"_parts": {"a": {}}, "_material": "pla_basic", "w": 5, "x": 1}
        rec, warns = build.parameters_record(given, {"w": 1, "h": 2, "_k": 0})
        self.assertEqual(rec, {"scope": "merged", "values": {"w": 5, "h": 2, "x": 1}})   # no "_" key from either side
        self.assertEqual(warns, ["params.json key 'x' is not in the generator's DEFAULTS (a typo?)"])
        rec, warns = build.parameters_record(given, {"w": 1}, kind="PARAMETERS")
        self.assertIn("params.json key 'x' is not in the generator's PARAMETERS (a typo?)", warns)
        self.assertEqual(build.parameters_record(given), ({"scope": "overrides", "values": {"w": 5, "x": 1}}, []))
        self.assertEqual(build.parameters_record({}), ({"scope": "overrides", "values": {}}, []))
        # Known but empty defaults still merge: every params.json key is then unknown to them.
        rec, warns = build.parameters_record({"w": 5}, {})
        self.assertEqual((rec["scope"], len(warns)), ("merged", 1))
        # Defaults that are not a dict are not defaults.
        self.assertEqual(build.parameters_record({"w": 5}, [("w", 1)])[0]["scope"], "overrides")
        # A NaN from params.json (json.load reads it) is not JSON either.
        rec, warns = build.parameters_record({"x": float("nan"), "y": float("-inf")})
        self.assertEqual(rec["values"], {"x": "nan", "y": "-inf"})
        self.assertEqual(len(warns), 2)

    def test_json_value(self):
        warns = []
        self.assertEqual(build.json_value({"a": (1, 2.5, True, None, "s"), "b": {"c": [0.1]}}, "p", warns),
                         {"a": [1, 2.5, True, None, "s"], "b": {"c": [0.1]}})
        self.assertEqual(warns, [])
        self.assertEqual(build.json_value({1: "x"}, "k", warns), "{1: 'x'}")       # a non-string key: the whole dict
        self.assertEqual(build.json_value([1, object], "l", warns), [1, "<class 'object'>"])
        self.assertEqual([re.search(r"'([^']+)'", w).group(1) for w in warns], ["k", "l[1]"])

    def test_part_material(self):
        pm = build.part_material
        self.assertEqual(pm({"_material": "pla_basic", "_parts": {"a": {"material": "petg_hf"}}}, "a"), "petg_hf")
        self.assertEqual(pm({"_material": "pla_basic", "_parts": {"a": {"material": "petg_hf"}}}, "b"), "pla_basic")
        self.assertEqual(pm({"_material": "pla_basic", "_parts": {"a": {"material": None}}}, "a"), "pla_basic")
        self.assertEqual(pm({"_material": "pla_basic", "_parts": {"a": None}}, "a"), "pla_basic")
        self.assertEqual(pm({"_material": "pla_basic", "_parts": ["a"]}, "a"), "pla_basic")
        self.assertIsNone(pm({"_parts": {"a": {"expect": [1, 1, 1]}}}, "a"))
        self.assertIsNone(pm({"_material": ""}, "a"))
        self.assertIsNone(pm({}, "a"))


class Record(Base):
    def test_record_parameters_are_the_overrides_and_parts_carry_their_material(self):
        """record never imports the generator: even one with DEFAULTS gives the overrides."""
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(20, 20, 2))
        body = os.path.join(self.d, "body.stl"); write_stl(body, box(20, 20, 10))
        src = self.write("gen_fusion.py", "DEFAULTS = {'w': 1.0}\ndef run(context=None):\n    pass\n")
        prm = self.params({"_material": "pla_basic", "_parts": {"lid": {"material": "petg_hf"}, "body": {}},
                           "w": 20.0, "zzz": 1})
        code, out = run("record", lid, body, "--source", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "overrides", "values": {"w": 20.0, "zzz": 1}})
        self.assertEqual(out["command"], "record")                             # its STLs are exported, not built
        self.assertFalse(any("typo" in w for w in out["warnings"]), out["warnings"])
        self.assertEqual({p["name"]: p["material"] for p in out["parts"]}, {"lid": "petg_hf", "body": "pla_basic"})
        code, out = run("record", lid, "--source", src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual((out["parameters"], out["parts"][0]["material"], out["params"]),
                         ({"scope": "overrides", "values": {}}, None, None))

    def test_record_external_build(self):
        stl = os.path.join(self.d, "fusion_part.stl")
        write_stl(stl, box(20, 20, 20))
        src = self.write("gen_fusion.py", "def run(context=None):\n    pass\n")
        prm = self.params({"_parts": {"fusion_part": {"expect": [20, 20, 20]}}})
        code, out = run("record", stl, "--source", src, "--params", prm, "--out", self.out, "--no-wall-check")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["engine"], "fusion")
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")

    def test_record_keeps_a_run_manifests_sources_and_refuses_a_stale_one(self):
        """S3-1 / S3-2: in a mixed build, record is given STLs that `run` already built. Their
        manifests' sources (a generator's own imports) join the freshness hash, and an STL whose
        own manifest is stale is not re-stamped: R3 FAIL, rebuild that part."""
        import validate
        back = os.path.join(self.d, "back.stl"); write_stl(back, box(60, 40, 5))
        puff = os.path.join(self.d, "puff.stl"); write_stl(puff, box(10, 10, 3, 10, 10, 5))
        scad = self.write("back.scad", "cube([60, 40, 5]);")
        gen = self.write("cloud_blender.py", "import cloud_shape\n")
        lib = self.write("cloud_shape.py", "R = 20\n")
        prm = self.params({"_parts": {"back": {"expect": [60, 40, 5]}, "puff": {"expect": [10, 10, 3], "object": "back"}}, "r": 20})
        with open(prm, encoding="utf-8") as f:
            params = json.load(f)
        validate.write_manifest(back, [scad], params, "openscad")            # what `run` writes for each engine
        validate.write_manifest(puff, [gen, lib], params, "blender")
        code, out = run("record", back, puff, "--source", scad, gen, "--params", prm, "--out", self.out,
                        "--engine", "openscad+blender", "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertNotEqual(out["gate"], "FAIL", out["errors"])
        self.assertEqual([os.path.basename(s) for s in out["sources"]], ["back.scad", "cloud_blender.py", "cloud_shape.py"])
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual(parts["puff"]["prior_manifest"], {"engine": "blender", "sources": ["cloud_blender.py", "cloud_shape.py"], "fresh": True})
        self.assertEqual(parts["puff"]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")
        self.assertEqual(parts["back"]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")
        with open(puff + ".manifest.json", encoding="utf-8") as f:
            man = json.load(f)
        self.assertEqual((man["engine"], man["sources"]), ("blender", ["cloud_blender.py", "cloud_shape.py"]))   # kept as built
        # The same list validates every part later: R3 hashes each manifest's own files out of it.
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate.main([back, puff, "--source", *out["sources"], "--params", prm, "--no-wall-check"])
        self.assertEqual([f["checks"]["R3"]["state"] for f in json.loads(buf.getvalue())["files"]], ["PASS", "PASS"])
        # The Blender generator's import changes and the Blender part is not rebuilt: record
        # must not bless puff.stl; back.stl (OpenSCAD) does not depend on it and stays fresh.
        with open(lib, "a") as f:
            f.write("# edited after the build\n")
        code, out = run("record", back, puff, "--source", scad, gen, "--params", prm, "--out", self.out,
                        "--engine", "openscad+blender", "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0)
        self.assertEqual(out["gate"], "FAIL")
        parts = {p["name"]: p for p in out["parts"]}
        r3 = parts["puff"]["validate"]["files"][0]["checks"]["R3"]
        self.assertEqual((r3["state"], r3["return_to"]), ("FAIL", "current"))
        self.assertIn("STALE", r3["note"])
        self.assertIn("blender build", r3["note"])
        self.assertIn("Rebuild", r3["note"])
        self.assertFalse(parts["puff"]["prior_manifest"]["fresh"])
        self.assertEqual(parts["back"]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")
        self.assertTrue(any(e.startswith("puff R3 FAIL: STALE") for e in out["errors"]), out["errors"])
        with open(puff + ".manifest.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["engine"], "blender")             # the stale manifest was left alone
        # A manifest that names a source nobody can find is not fresh either, and says so.
        validate.write_manifest(puff, [gen, lib], params, "blender")
        os.remove(lib)
        code, out = run("record", puff, "--source", scad, gen, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(out["gate"], "FAIL")
        self.assertTrue(any("cloud_shape.py" in w and "not among --source" in w for w in out["warnings"]), out["warnings"])
        # An STL with no manifest, or a manifest of another file, is recorded as before.
        os.remove(puff + ".manifest.json")
        write_stl(puff, box(10, 10, 3, 10, 10, 5))
        code, out = run("record", puff, "--source", scad, gen, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")
        self.assertNotIn("prior_manifest", out["parts"][0])

    def test_record_again_after_a_param_change_re_stamps_its_own_manifests(self):
        """Review B1: record writes manifests too. A second record after a parameter change, with
        the unchanged parts re-exported byte for byte, must re-stamp those manifests (record is the
        only word on an STL exported elsewhere), not treat them as a stale `run` build."""
        body = os.path.join(self.d, "body.stl"); write_stl(body, box(40, 30, 5))
        label = os.path.join(self.d, "label.stl"); write_stl(label, box(10, 10, 1.5, 5, 5, 5))
        src = self.write("model_v3.py", "# 3dprint-scout: engine=blender\n")
        spec = {"body": {"expect": [40, 30, 5]}, "label": {"object": "body", "role": "fused"}}
        prm = self.params({"label_h": 1.5, "_parts": spec})
        code, out = run("record", body, label, "--source", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertNotEqual(out["gate"], "FAIL", out["errors"])
        with open(body + ".manifest.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["by"], "record")
        self.params({"label_h": 2.0, "_parts": spec})                       # the label grows; body.stl is re-exported unchanged
        write_stl(label, box(10, 10, 2.0, 5, 5, 5))
        write_stl(body, box(40, 30, 5))
        code, out = run("record", body, label, "--source", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0)
        self.assertNotEqual(out["gate"], "FAIL", out["errors"])
        self.assertEqual([p["validate"]["files"][0]["checks"]["R3"]["state"] for p in out["parts"]], ["PASS", "PASS"])
        self.assertTrue(all("prior_manifest" not in p for p in out["parts"]))

    def test_record_refuses_an_stl_built_from_another_generator(self):
        """Review S3: a fresh `run` manifest of cup.py says nothing for record --source cup_v2.py;
        none of the manifest's generators is among --source, so the STL is not blessed as cup_v2's."""
        import validate
        stl = os.path.join(self.d, "cup.stl"); write_stl(stl, box(20, 20, 20))
        cup = self.write("cup.scad", "cube([20, 20, 20]);")
        validate.write_manifest(stl, [cup], None, "openscad")              # what `run` writes
        with open(stl + ".manifest.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["by"], "run")
        v2 = self.write("cup_v2.scad", "cube([20, 20, 30]);")
        code, out = run("record", stl, "--source", v2, cup, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")   # cup.scad given too: fresh
        code, out = run("record", stl, "--source", v2, "--out", self.out, "--no-wall-check", "--no-3mf")
        r3 = out["parts"][0]["validate"]["files"][0]["checks"]["R3"]
        self.assertEqual((out["gate"], r3["state"]), ("FAIL", "FAIL"))
        self.assertIn("built from cup.scad, not from the given --source (cup_v2.scad)", r3["note"])
        self.assertFalse(out["parts"][0]["prior_manifest"]["fresh"])

    def test_broken_stl_keeps_the_json_contract(self):
        """G4: a 0-byte or truncated export gets no manifest, is left out of the 3MF and is
        reported; the other parts are still recorded and validated. JSON, never a traceback."""
        good = os.path.join(self.d, "good.stl"); write_stl(good, box(20, 20, 20))
        empty = os.path.join(self.d, "empty.stl"); open(empty, "wb").close()
        trunc = os.path.join(self.d, "trunc.stl"); write_stl(trunc, box(20, 20, 20))
        with open(trunc, "r+b") as f:
            f.truncate(84 + 50 * 5)
        src = self.write("gen_fusion.py", "def run(context=None):\n    pass\n")
        r = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "..", "scripts", "build.py"), "record",
                            good, empty, trunc, "--source", src, "--out", self.out, "--no-wall-check"],
                           capture_output=True, text=True, encoding="utf-8")
        out = json.loads(r.stdout)                                # stdout is one JSON document
        self.assertEqual(r.returncode, 0)                         # it ran; read the gate
        self.assertEqual((out["ran"], out["gate"], out["R4"]), (True, "FAIL", "FAIL"))
        self.assertEqual(len(out["errors"]), 2)
        self.assertTrue(all("broken artifact" in e for e in out["errors"]))
        sane = {p["name"]: p["artifact_sane"] for p in out["parts"]}
        self.assertEqual(sane, {"good": True, "empty": False, "trunc": False})
        self.assertIn("truncated", [p for p in out["parts"] if p["name"] == "trunc"][0]["artifact_error"])
        self.assertEqual([p["material"] for p in out["parts"]], [None, None, None])   # a broken part has the key too
        self.assertEqual(out["parameters"], {"scope": "overrides", "values": {}})
        self.assertTrue(os.path.isfile(good + ".manifest.json"))
        self.assertFalse(os.path.exists(empty + ".manifest.json"))
        self.assertFalse(os.path.exists(trunc + ".manifest.json"))
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["M1"]["state"], "PASS")
        with zipfile.ZipFile(out["threemf"]) as z:
            self.assertEqual(z.read("3D/3dmodel.model").decode().count("<object "), 1)


@unittest.skipUnless(os.name != "nt", "uses a shell wrapper as a fake OpenSCAD")
class FakeOpenSCAD(Base):
    """OpenSCAD stand-in that prints bytes that are not UTF-8 (a Korean Windows console) and
    reports a dependency whose path is not ASCII plus one that does not exist."""

    FAKE = r"""
import os, struct, sys
a = sys.argv[1:]
if "--version" in a:
    print("OpenSCAD version 2021.01"); sys.exit(0)
stl, src = a[a.index("-o") + 1], a[-1]
p = [(0,0,0),(10,0,0),(10,10,0),(0,10,0),(0,0,10),(10,0,10),(10,10,10),(0,10,10)]
f = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
with open(stl, "wb") as fh:
    fh.write(b"\0" * 80 + struct.pack("<I", 12))
    for t in f:
        fh.write(struct.pack("<3f", 0, 0, 0))
        for i in t:
            fh.write(struct.pack("<3f", *p[i]))
        fh.write(b"\0\0")
if "-d" in a:
    lib = os.path.join(os.path.dirname(os.path.abspath(src)), "\ub77c\uc774\ube0c\ub7ec\ub9ac.scad")
    with open(a[a.index("-d") + 1], "wb") as fh:
        fh.write((stl + ": " + src + " " + lib + " \\\n missing.scad\n").encode("utf-8"))
sys.stdout.buffer.write(b"WARNING: \xc7\xd1\xb1\xdb unknown variable\n")
"""

    def setUp(self):
        super().setUp()
        fake_py = self.write("fake_openscad.py", self.FAKE)
        self.exe = self.write("fake_openscad", f"#!/bin/sh\nexec {sys.executable} {fake_py} \"$@\"\n")
        os.chmod(self.exe, 0o755)
        self.write("\ub77c\uc774\ube0c\ub7ec\ub9ac.scad", "// library with a non-ASCII name\n")
        self.src = self.write("model.scad", "cube(10);")
        self.old = os.environ.get("OPENSCAD")
        os.environ["OPENSCAD"] = self.exe

    def tearDown(self):
        if self.old is None:
            os.environ.pop("OPENSCAD", None)
        else:
            os.environ["OPENSCAD"] = self.old
        super().tearDown()

    def test_non_utf8_output_and_dependency_paths(self):
        code, out = run("run", self.src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertTrue(out["ran"])
        self.assertTrue(any("unknown variable" in w for w in out["warnings"]))          # decoded with replacement
        self.assertIn("\ub77c\uc774\ube0c\ub7ec\ub9ac.scad", [os.path.basename(s) for s in out["sources"]])
        self.assertTrue(any("missing.scad" in w and "freshness hash" in w for w in out["warnings"]))
        with open(os.path.join(self.out, "model.stl.manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["sources"], ["model.scad", "\ub77c\uc774\ube0c\ub7ec\ub9ac.scad"])

    def test_parameters_are_the_overrides(self):
        prm = self.params({"_material": "petg_hf", "_assumptions": ["x"], "w": 10, "label": "A"})
        code, out = run("run", self.src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["parameters"], {"scope": "overrides", "values": {"w": 10, "label": "A"}})
        self.assertEqual([(p["name"], p["material"]) for p in out["parts"]], [("model", "petg_hf")])
        self.assertFalse(any("typo" in w or "JSON value" in w for w in out["warnings"]), out["warnings"])


# --------------------------------------------------------------------------- #
# Blender
# --------------------------------------------------------------------------- #
BLENDER_GEN = """# 3dprint-scout: engine=blender
import blender_builder as bb

PARAMETERS = {"w": 30.0, "d": 20.0, "h": 8.0, "fillet": 1.5}   # mm, example values

def build(p):
    body = bb.box([p["w"], p["d"], p["h"]], "body")
    bb.bevel(body, p["fillet"])
    peg = bb.cylinder(4.0, 5.0, name="peg"); peg.location = (p["w"] / 2, p["d"] / 2, p["h"])
    bb.part(body, "body")
    bb.part(peg, "peg", object="body", role="fused")
    return {"body": body, "peg": peg}

if __name__ == "__main__":
    bb.main(build, PARAMETERS)
"""

# A stand-in for the blender binary that needs no Blender: answers --version, writes a 10 mm
# cube per requested part into --out (or body.stl) and prints the @@3DPS line, like a generator
# run by blender_builder.main would. FAKE_BLENDER_SLEEP makes it hang (timeout test).
FAKE_BLENDER = r"""
import json, os, struct, sys, time
a = sys.argv[1:]
if "--version" in a:
    print("Blender 4.5.0 LTS\n\tbuild date: 2025-07-15"); sys.exit(0)
if os.environ.get("FAKE_BLENDER_SLEEP"):
    time.sleep(float(os.environ["FAKE_BLENDER_SLEEP"]))
if a[0] == "--background":                  # the binary
    assert a[:4] == ["--background", "--factory-startup", "--python-exit-code", "1"], a
    src = a[a.index("--python") + 1]
    mode = "binary"
else:                                       # `python gen.py -- ...`, as a Python with bpy runs it
    src, mode = a[0], "bpy"
rest = a[a.index("--") + 1:]
out = rest[rest.index("--out") + 1]
only = rest[rest.index("--only") + 1].split(",") if "--only" in rest else ["body"]
# The helper's rule: an explicit --blend is a new file; the default working copy is rewritten.
blend = rest[rest.index("--blend") + 1] if "--blend" in rest else None
if blend and os.path.exists(blend):
    sys.exit("--blend " + blend + " already exists")
blend = blend or os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".blend")
os.makedirs(out, exist_ok=True)
p = [(0,0,0),(10,0,0),(10,10,0),(0,10,0),(0,0,10),(10,0,10),(10,10,10),(0,10,10)]
f = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
if os.environ.get("FAKE_BLENDER_SHUFFLE"):  # the same triangles in another order on every run, as Blender does
    import random
    random.SystemRandom().shuffle(f)
parts = []
for name in only:
    stl = os.path.join(out, name + ".stl")
    with open(stl, "wb") as fh:
        fh.write(b"\0" * 80 + struct.pack("<I", 12))
        for t in f:
            fh.write(struct.pack("<3f", 0, 0, 0))
            for i in t:
                fh.write(struct.pack("<3f", *p[i]))
            fh.write(b"\0\0")
    parts.append({"name": name, "stl": stl, "bbox_mm": [10, 10, 10], "triangles": 12, "bytes": os.path.getsize(stl), "seconds": 0.0})
open(blend, "wb").write(b"BLENDER-v402fake")
print("Blender quit")
# FAKE_BLENDER_REPORT adds fields to the line (parameters); without it the line is a helper's from before 0.7.
extra = json.loads(os.environ.get("FAKE_BLENDER_REPORT") or "{}")
print("@@3DPS " + json.dumps(dict({"parts": parts, "deps": [src], "blend": blend, "blender": "4.5.0 LTS", "solver": "MANIFOLD",
                                   "mode": mode, "notes": ["fake"], "warnings": []}, **extra)))
"""

# The same, but a real emulation of the binary: runs the --python-expr and the generator in the
# Python that has bpy, as `blender --background --python` would (used only when bpy is there).
EMULATED_BLENDER = r"""
import runpy, sys
a = sys.argv[1:]
if "--version" in a:
    print("Blender 5.2.2 LTS"); sys.exit(0)
assert a[:4] == ["--background", "--factory-startup", "--python-exit-code", "1"], a
exec(a[a.index("--python-expr") + 1])
script = a[a.index("--python") + 1]
sys.argv = ["blender"] + a[a.index("--"):]
runpy.run_path(script, run_name="__main__")
"""


class BlenderDetect(Base):
    def test_bad_environment_candidate_does_not_hide_supported_bpy(self):
        good = subprocess.CompletedProcess([], 0, '@@BPY {"version":"4.5.14","version_tuple":[4,5,14]}\n', "")
        old = subprocess.CompletedProcess([], 0, '@@BPY {"version":"4.3.2","version_tuple":[4,3,2]}\n', "")
        bad_json = subprocess.CompletedProcess([], 0, '@@BPY broken\n', "")
        failed = subprocess.CompletedProcess([], 1, "", "missing shared library")
        missing = subprocess.CompletedProcess([], 0, "unexpected output", "")
        for first in (subprocess.TimeoutExpired("old-python", 120), old, bad_json,
                      OSError("interpreter missing"), failed, missing):
            with self.subTest(first=str(first)), \
                    mock.patch.dict(os.environ, {"BLENDER_PYTHON": "/old-python"}), \
                    mock.patch.object(build, "find_blender", return_value=None), \
                    mock.patch.object(build.subprocess, "run", side_effect=[first, good]) as probe:
                chosen = build.choose_blender()
                self.assertEqual(chosen["python"], sys.executable)
                self.assertEqual(probe.call_count, 2)
                self.assertTrue(chosen["skipped"])

    def test_invalid_bpy_versions_fall_back_without_claiming_readiness(self):
        good = subprocess.CompletedProcess([], 0, '@@BPY {"version":"4.5.14 LTS","version_tuple":[4,5,14]}\n', "")
        invalid = [None, [], {"version": "4.5.14", "version_tuple": [4, 5]},
                   {"version": "unknown", "version_tuple": [4, 5, 14]},
                   {"version": "4.3.2", "version_tuple": [4, 5, 14]},
                   {"version": "4.5.14", "version_tuple": [4, 5, True]},
                   {"version": "4.5.14", "version_tuple": [4, 5, 14, 0]}]
        for payload in invalid:
            bad = subprocess.CompletedProcess([], 0, '@@BPY ' + json.dumps(payload), "")
            with self.subTest(payload=payload), \
                    mock.patch.dict(os.environ, {"BLENDER_PYTHON": "/bad-python"}), \
                    mock.patch.object(build.subprocess, "run", side_effect=[bad, good]) as probe:
                info = build.bpy_info()
                self.assertEqual(info["python"], sys.executable)
                self.assertEqual(info["version_tuple"], (4, 5, 14))
                self.assertIn("invalid bpy probe response", info["notes"][0])
                self.assertEqual(probe.call_count, 2)

    def test_failed_bpy_candidates_keep_their_diagnostics(self):
        failed = subprocess.CompletedProcess([], -11, "", "missing shared library")
        with mock.patch.dict(os.environ, {"BLENDER_PYTHON": "/missing-python"}), \
                mock.patch.object(build, "find_blender", return_value=None), \
                mock.patch.object(build.subprocess, "run", side_effect=[OSError("interpreter missing"), failed]):
            with self.assertRaises(RuntimeError) as caught:
                build.choose_blender()
        message = str(caught.exception)
        self.assertIn("interpreter missing", message)
        self.assertIn("status -11", message)
        self.assertIn("missing shared library", message)

    def test_explicit_blender_python_is_not_silently_replaced(self):
        with mock.patch.dict(os.environ, {"BLENDER_PYTHON": "/other-python"}), \
                mock.patch.object(build.subprocess, "run", side_effect=subprocess.TimeoutExpired("explicit", 120)) as probe:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                build.choose_blender("/explicit-python")
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(probe.call_args[0][0][0], "/explicit-python")

    def test_version_parse(self):
        self.assertEqual(build.parse_blender_version("Blender 4.2.3 LTS\n\tbuild date: 2024-09-01"), "4.2.3")
        self.assertEqual(build.parse_blender_version("Blender 5.2.2 LTS"), "5.2.2")
        self.assertEqual(build.parse_blender_version("Blender 4.5"), "4.5")
        self.assertIsNone(build.parse_blender_version("bash: blender: not found"))
        self.assertEqual(build.version_tuple("4.2.3"), (4, 2, 3))
        self.assertEqual(build.version_tuple(None), ())

    def test_binary_search_order(self):
        fake = self.write("blender", "#!/bin/sh\necho Blender 4.2.0\n")
        with mock.patch.dict(os.environ, {"BLENDER": fake}):
            self.assertEqual(build.find_blender(), fake)                        # 1. the environment
        with mock.patch.dict(os.environ, {"BLENDER": "/nope/blender"}), \
                mock.patch.object(build.shutil, "which", return_value="/usr/local/bin/blender"):
            self.assertEqual(build.find_blender(), "/usr/local/bin/blender")   # 2. PATH (a bad BLENDER is ignored)
        env = {k: v for k, v in os.environ.items() if k != "BLENDER"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(build.shutil, "which", return_value=None), \
                mock.patch.object(build.sys, "platform", "linux"), mock.patch.object(build.os, "name", "posix"), \
                mock.patch.object(build.glob, "glob", side_effect=lambda pat: ["/opt/blender-4.5/blender"] if pat.startswith("/opt") else []), \
                mock.patch.object(build.os.path, "isfile", side_effect=lambda p: p == "/opt/blender-4.5/blender"):
            self.assertEqual(build.find_blender(), "/opt/blender-4.5/blender")  # 3. the usual folders
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(build.shutil, "which", return_value=None), \
                mock.patch.object(build.glob, "glob", return_value=[]):
            self.assertIsNone(build.find_blender())

    def test_version_from_the_binary_with_mocked_subprocess(self):
        done = subprocess.CompletedProcess(["blender", "--version"], 0, "Blender 4.5.1 LTS\n\tbuild date: x\n", "")
        with mock.patch.object(build.subprocess, "run", return_value=done) as run_:
            info = build.blender_info("/x/blender")
        self.assertEqual(info, {"path": "/x/blender", "version": "4.5.1"})
        self.assertEqual(run_.call_args[0][0], ["/x/blender", "--version"])
        with mock.patch.object(build.subprocess, "run", side_effect=subprocess.TimeoutExpired("blender", 60)):
            self.assertIn("error", build.blender_info("/x/blender"))
        failed = subprocess.CompletedProcess([], 1, "Blender 4.5.14 LTS", "startup failed")
        with mock.patch.object(build.subprocess, "run", return_value=failed):
            self.assertIn("status 1", build.blender_info("/x/blender")["error"])

    def test_bpy_probe_runs_in_a_subprocess_with_a_timeout(self):
        with mock.patch.object(build.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 120)) as run_:
            info = build.bpy_info("/x/python")
        self.assertIn("timed out", info["error"])
        self.assertEqual(run_.call_args[0][0][:2], ["/x/python", "-c"])
        self.assertEqual(run_.call_args[1]["timeout"], build.BPY_PROBE_TIMEOUT)
        cwd = run_.call_args[1]["cwd"]                                         # an empty folder, not the user's
        self.assertNotEqual(os.path.abspath(cwd), os.path.abspath(os.getcwd()))
        done = subprocess.CompletedProcess([], 0, '@@BPY {"version": "4.5.0", "version_tuple": [4, 5, 0], "python": "3.11.9"}\n', "")
        with mock.patch.object(build.subprocess, "run", return_value=done):
            info = build.bpy_info("/x/python")
        self.assertEqual((info["version"], info["version_tuple"], info["python"]), ("4.5.0", (4, 5, 0), "/x/python"))
        with mock.patch.object(build.subprocess, "run", side_effect=OSError("no such file")):
            self.assertIn("no such file", build.bpy_info("/x/python")["error"])

    def test_status_and_detect_without_blender(self):
        with mock.patch.object(build, "find_blender", return_value=None), mock.patch.object(build, "bpy_info", return_value=None):
            status = build.blender_status()
            code, out = run("detect")
        self.assertEqual(status, {"binary": None, "bpy": None, "manifold_boolean": False, "notes": []})
        self.assertEqual(code, 0)
        self.assertNotIn("blender", out["available"])
        self.assertEqual(out["blender"], status)                               # one place for the block
        self.assertNotIn("blender", out["engines"])

    def test_detect_with_explicit_interpreter_ignores_the_binary(self):
        # run --blender-python never uses the binary, so detect must not list Blender on its strength
        binary = {"path": "/x/blender", "version": "4.5.14"}
        failed = {"error": "import bpy exited with status 1 in /explicit/python", "python": "/explicit/python"}
        good = {"version": "4.5.14", "version_tuple": (4, 5, 14), "python": "/explicit/python"}
        with mock.patch.object(build, "find_blender", return_value="/x/blender") as find, \
                mock.patch.object(build, "blender_info", return_value=binary), \
                mock.patch.object(build, "blender_manifold3d", return_value=True), \
                mock.patch.object(build, "bpy_info", return_value=failed):
            code, out = run("detect", "--blender-python", "/explicit/python")
            self.assertEqual(code, 0)
            self.assertNotIn("blender", out["available"])
            self.assertIsNone(out["blender"]["binary"])
            self.assertFalse(out["blender"]["manifold_boolean"])
            self.assertTrue(any("--blender-python" in n for n in out["blender"]["notes"]))
            find.assert_not_called()
            with self.assertRaises(RuntimeError):          # and the build agrees
                build.choose_blender("/explicit/python")
        with mock.patch.object(build, "find_blender", return_value="/x/blender"), \
                mock.patch.object(build, "blender_info", return_value=binary), \
                mock.patch.object(build, "bpy_info", return_value=good):
            code, out = run("detect", "--blender-python", "/explicit/python")
            self.assertIn("blender", out["available"])
            self.assertEqual(out["blender"]["bpy"]["python"], "/explicit/python")
            self.assertEqual(build.choose_blender("/explicit/python")["mode"], "bpy")
        with mock.patch.object(build, "find_blender", return_value="/x/blender"), \
                mock.patch.object(build, "blender_info", return_value=binary), \
                mock.patch.object(build, "blender_manifold3d", return_value=True), \
                mock.patch.object(build, "bpy_info", return_value=None):
            status = build.blender_status()                   # without it the binary still counts
        self.assertEqual(status["binary"]["path"], "/x/blender")
        self.assertTrue(build.blender_usable(status))

    def test_status_version_gates(self):
        old = {"version": "4.4.0", "version_tuple": (4, 4, 0), "python": "/x/python"}
        with mock.patch.object(build, "find_blender", return_value=None), mock.patch.object(build, "bpy_info", return_value=old):
            status = build.blender_status()
        self.assertFalse(status["manifold_boolean"])
        self.assertFalse(build.blender_usable(status))                         # 4.5 LTS is the floor
        self.assertTrue(any("older than 4.5" in n for n in status["notes"]))
        floor = {"version": "4.5.14", "version_tuple": (4, 5, 14), "python": "/x/python"}
        with mock.patch.object(build, "find_blender", return_value=None), mock.patch.object(build, "bpy_info", return_value=floor):
            status = build.blender_status()
        self.assertTrue(status["manifold_boolean"])
        self.assertTrue(build.blender_usable(status))
        self.assertEqual(status["notes"], [])
        with mock.patch.object(build, "find_blender", return_value="/x/blender"), \
                mock.patch.object(build, "blender_info", return_value={"path": "/x/blender", "version": "4.5.1"}), \
                mock.patch.object(build, "bpy_info", return_value={"error": "import bpy timed out after 120s in /x/python", "python": "/x/python"}):
            status = build.blender_status()
        self.assertTrue(status["manifold_boolean"])
        self.assertIsNone(status["bpy"])
        self.assertTrue(any("timed out" in n for n in status["notes"]))


class BlenderEngine(Base):
    """build.py's side of the Blender engine, with a stand-in binary (no Blender needed)."""

    def fake(self, code, name="fake_blender"):
        py = self.write(name + ".py", code)
        exe = self.write(name, f"#!/bin/sh\nexec {sys.executable} {py} \"$@\"\n")
        os.chmod(exe, 0o755)
        return exe

    def test_marker_and_command_lines(self):
        marked = self.write("gen_blender.py", BLENDER_GEN)
        plain = self.write("gen_plain.py", "def build(p):\n    return {}\n")
        self.assertEqual(build.engine_marker(marked), "blender")
        self.assertIsNone(build.engine_marker(plain))
        self.assertIsNone(build.engine_marker(os.path.join(self.d, "missing.py")))
        shebang = self.write("gen_shebang.py", "#!/usr/bin/env python3\n" + BLENDER_GEN)
        self.assertEqual(build.engine_marker(shebang), "blender")               # a shebang may come first
        bom = os.path.join(self.d, "gen_bom.py")
        with open(bom, "wb") as f:
            f.write(b"\xef\xbb\xbf" + BLENDER_GEN.encode("utf-8"))
        self.assertEqual(build.engine_marker(bom), "blender")                   # a UTF-8 BOM is tolerated
        code, out = run("run", marked, "--engine", "python", "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("is a Blender generator", out["errors"][0])              # the python engine says so
        cmd = build.blender_command("/x/blender", marked, "/t/p.json", self.out, ["body", "peg"], "/o/gen.blend")
        self.assertEqual(cmd[:5], ["/x/blender", "--background", "--factory-startup", "--python-exit-code", "1"])
        self.assertEqual(cmd[5], "--python-expr")
        self.assertIn(repr(build.ENGINES_DIR), cmd[6])                        # Python literals: \\ on Windows
        self.assertIn(repr(os.path.dirname(os.path.abspath(marked))), cmd[6])
        self.assertEqual(cmd[7:9], ["--python", os.path.abspath(marked)])
        self.assertEqual(cmd[9:], ["--", "--params", "/t/p.json", "--out", os.path.abspath(self.out),
                                   "--only", "body,peg", "--blend", "/o/gen.blend"])
        cmd = build.bpy_command("/x/python3.13", marked, "/t/p.json", self.out, [])
        self.assertEqual(cmd, ["/x/python3.13", os.path.abspath(marked), "--", "--params", "/t/p.json", "--out", os.path.abspath(self.out)])

    @unittest.skipUnless(os.name != "nt", "uses a shell wrapper as a fake blender")
    def test_fake_binary_builds_records_and_validates(self):
        exe = self.fake(FAKE_BLENDER)
        src = self.write("gen_blender.py", BLENDER_GEN)
        prm = self.params({"_parts": {"body": {"expect": [10, 10, 10]}, "peg": {"expect": [10, 10, 10]}}, "w": 30.0})
        printers = self.write("printers.json", json.dumps(X2D))
        with mock.patch.dict(os.environ, {"BLENDER": exe}):
            code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--printer", printers)
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual((out["engine"], out["gate"], out["R4"]), ("blender", "PASS", "PASS"))
        self.assertEqual(out["engine_info"]["mode"], "binary")
        self.assertEqual(out["engine_info"]["path"], exe)
        self.assertEqual(out["engine_info"]["boolean_solver"], "MANIFOLD")
        self.assertEqual([p["name"] for p in out["parts"]], ["body", "peg"])
        self.assertEqual(out["blend"], os.path.join(os.path.abspath(self.out), "gen_blender.blend"))
        self.assertTrue(os.path.isfile(out["blend"]))
        for p in out["parts"]:
            self.assertTrue(os.path.isfile(p["stl"] + ".manifest.json"))
            checks = p["validate"]["files"][0]["checks"]
            self.assertEqual(checks["D1"]["state"], "PASS", p["name"])
            self.assertEqual(checks["R3"]["state"], "PASS", p["name"])
        with open(out["parts"][0]["stl"] + ".manifest.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["engine"], "blender")
        self.assertEqual([os.path.basename(s) for s in out["sources"]], ["gen_blender.py"])
        self.assertTrue(os.path.isfile(out["threemf"]))
        # A rebuild into the same out/ rewrites the working copy: build.py names no --blend.
        with mock.patch.dict(os.environ, {"BLENDER": exe}):
            code, again = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--printer", printers)
        self.assertEqual((code, again["gate"], again["blend"]), (0, "PASS", out["blend"]), again.get("errors"))
        self.assertNotIn("--blend", build.blender_command(exe, src, "/t/p.json", self.out, []))
        # --only reaches the generator, and the engine is also selectable explicitly.
        with mock.patch.dict(os.environ, {"BLENDER": exe}):
            code, out = run("run", src, "--params", prm, "--out", os.path.join(self.d, "mech"), "--only", "peg",
                            "--engine", "blender", "--no-wall-check", "--no-3mf")
        self.assertEqual([p["name"] for p in out["parts"]], ["peg"])

    @unittest.skipUnless(os.name != "nt", "uses a shell wrapper as a fake blender")
    def test_parameters_come_from_the_report_line(self):
        """bb.main reports the merged PARAMETERS and its warnings; build.py records them as they
        are. A line without them (an older blender_builder.py next to the generator), or with a
        malformed record, gives the params.json values with scope overrides."""
        exe = self.fake(FAKE_BLENDER)
        src = self.write("gen_blender.py", BLENDER_GEN)
        prm = self.params({"_material": "pla_basic", "_parts": {"body": {"material": "petg_hf"}, "peg": {}}, "w": 25.0, "x": 1})
        typo = "params.json key 'x' is not in the generator's PARAMETERS (a typo?)"
        merged = {"scope": "merged", "values": {"w": 25.0, "d": 20.0, "h": 8.0, "fillet": 1.5, "x": 1}}
        overrides = {"scope": "overrides", "values": {"w": 25.0, "x": 1}}
        cases = [({"parameters": merged, "parameter_warnings": [typo], "warnings": [typo]}, merged, [typo]),
                 ({}, overrides, []),
                 ({"parameters": {"scope": "everything", "values": {}}, "parameter_warnings": [typo]}, overrides, []),
                 ({"parameters": {"scope": "merged", "values": [1]}}, overrides, []),
                 ({"parameters": None}, overrides, [])]
        for extra, want, warns in cases:
            with self.subTest(extra=extra), \
                    mock.patch.dict(os.environ, {"BLENDER": exe, "FAKE_BLENDER_REPORT": json.dumps(extra)}):
                code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--no-3mf")
                self.assertEqual(code, 0, out.get("errors"))
                self.assertEqual(out["parameters"], want)
                self.assertEqual([w for w in out["warnings"] if "typo" in w], warns)   # lifted once, not twice
                self.assertNotIn("parameters", out["engine_info"])
                self.assertNotIn("warnings", out["engine_info"])
                self.assertEqual({p["name"]: p["material"] for p in out["parts"]}, {"body": "petg_hf", "peg": "pla_basic"})

    @unittest.skipUnless(os.name != "nt", "uses a shell wrapper as a fake blender")
    def test_timeout_and_failure_are_reported(self):
        exe = self.fake(FAKE_BLENDER)
        src = self.write("gen_blender.py", BLENDER_GEN)
        with mock.patch.dict(os.environ, {"BLENDER": exe, "FAKE_BLENDER_SLEEP": "5"}):
            code, out = run("run", src, "--out", self.out, "--timeout", "1")
        self.assertEqual(code, 1)
        self.assertFalse(out["ran"])
        self.assertEqual(out["R4"], "FAIL")
        self.assertIn("timed out after 1s", out["errors"][0])
        bad = self.fake("import sys; print('Blender 4.5.0') if '--version' in sys.argv else sys.exit(1)", "bad_blender")
        with mock.patch.dict(os.environ, {"BLENDER": bad}):
            code, out = run("run", src, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("Blender generator failed (binary, exit 1)", out["errors"][0])
        old = self.fake("print('Blender 4.2.3 LTS')", "old_blender")
        with mock.patch.dict(os.environ, {"BLENDER": old}), mock.patch.object(build, "bpy_info", return_value=None):
            code, out = run("run", src, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("Blender not usable", out["errors"][0])
        self.assertIn("older than 4.5", out["errors"][0])                      # every reason is named
        self.assertIn("import bpy` failed", out["errors"][0])

    @unittest.skipUnless(os.name != "nt", "uses shell wrappers as a fake blender and a fake Python")
    def test_an_unusable_binary_falls_back_to_a_usable_bpy_module(self):
        """What detect calls usable is what runs: an old binary on PATH or in BLENDER does not
        stop a build when a Python with a 4.5+ bpy module is there."""
        src = self.write("gen_blender.py", BLENDER_GEN)
        old = self.fake("print('Blender 4.2.3 LTS')", "old_blender")
        python = self.fake(FAKE_BLENDER, "python_with_bpy")
        probe = {"version": "4.5.3", "version_tuple": (4, 5, 3), "python": python}
        with mock.patch.dict(os.environ, {"BLENDER": old}), mock.patch.object(build, "bpy_info", return_value=dict(probe)):
            status = build.blender_status()
            chosen = build.choose_blender()
            code, out = run("run", src, "--out", self.out, "--no-wall-check", "--no-3mf")
        self.assertTrue(build.blender_usable(status) and status["manifold_boolean"])
        self.assertIn("the binary is not usable: build.py and render.py use the bpy module", status["notes"])
        self.assertEqual((chosen["mode"], chosen["python"]), ("bpy", python))
        self.assertIn("older than 4.5", chosen["skipped"][0])
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual((out["engine_info"]["mode"], out["engine_info"]["python"]), ("bpy", python))
        self.assertTrue(out["engine_info"]["notes"][0].endswith("used the bpy module instead"))
        self.assertTrue(os.path.isfile(out["blend"]))
        import render                                                           # scripts/ is on sys.path
        self.assertIs(render.build, build)
        with mock.patch.dict(os.environ, {"BLENDER": old}), mock.patch.object(build, "bpy_info", return_value=dict(probe)):
            self.assertEqual(render.choose_blender(), (None, python, "4.5.3"))          # renders choose the same

    def test_missing_blender_is_a_clear_error(self):
        src = self.write("gen_blender.py", BLENDER_GEN)
        with mock.patch.object(build, "find_blender", return_value=None), mock.patch.object(build, "bpy_info", return_value=None):
            code, out = run("run", src, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertEqual((out["ran"], out["gate"], out["R4"]), (False, "FAIL", "FAIL"))
        self.assertIn("Blender not found", out["errors"][0])
        self.assertIn("pip install bpy", out["errors"][0])
        self.assertIn("4.5", out["errors"][0])
        self.assertEqual(out["engine"], "blender")                              # picked by the marker

    @unittest.skipUnless(HAS_BPY, "bpy module not installed")
    def test_bpy_module_path_builds_for_real(self):
        src = self.write("gen_blender.py", BLENDER_GEN)
        prm = self.params({"_parts": {"body": {"expect": [30, 20, 8]},
                                      "peg": {"expect": [8, 8, 5], "object": "body", "role": "fused", "material": "petg_hf"}},
                           "_material": "pla_basic", "w": 30.0, "d": 20.0, "h": 8.0, "filet": 2.0})
        printers = self.write("printers.json", json.dumps(X2D))
        with mock.patch.object(build, "find_blender", return_value=None):
            code, out = run("run", src, "--params", prm, "--out", self.out, "--blender-python", sys.executable,
                            "--no-wall-check", "--printer", printers)
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual((out["engine"], out["gate"], out["R4"], out["errors"]), ("blender", "PASS", "PASS", []))
        # The runner's merge of PARAMETERS and params.json, a misspelt key named once.
        self.assertEqual(out["parameters"], {"scope": "merged", "values": {"w": 30.0, "d": 20.0, "h": 8.0, "fillet": 1.5,
                                                                           "filet": 2.0}})
        self.assertEqual([w for w in out["warnings"] if "typo" in w],
                         ["params.json key 'filet' is not in the generator's PARAMETERS (a typo?)"])
        self.assertEqual({p["name"]: p["material"] for p in out["parts"]}, {"body": "pla_basic", "peg": "petg_hf"})
        self.assertNotIn("parameters", out["engine_info"])
        self.assertEqual(out["engine_info"]["mode"], "bpy")
        self.assertEqual(out["engine_info"]["python"], sys.executable)
        self.assertIn(out["engine_info"]["boolean_solver"], ("MANIFOLD", "EXACT"))
        self.assertTrue(os.path.isfile(out["blend"]))
        with mock.patch.object(build, "find_blender", return_value=None):           # a rebuild into the same out/
            code, again = run("run", src, "--params", prm, "--out", self.out, "--blender-python", sys.executable,
                              "--no-wall-check", "--printer", printers)
        self.assertEqual((code, again["gate"], again["blend"]), (0, "PASS", out["blend"]), again.get("errors"))
        self.assertEqual({os.path.basename(s) for s in out["sources"]}, {"gen_blender.py", "blender_builder.py"})
        parts = {p["name"]: p for p in out["parts"]}
        self.assertEqual(parts["peg"]["assembly"]["checks"]["A1"]["state"], "PASS")
        self.assertEqual(parts["body"]["validate"]["files"][0]["checks"]["M1"]["state"], "PASS")
        self.assertEqual(out["objects"][0]["parts"], ["body", "peg"])
        with open(parts["body"]["stl"] + ".manifest.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["sources"], ["blender_builder.py", "gen_blender.py"])

    @unittest.skipUnless(HAS_BPY and os.name != "nt", "bpy module not installed")
    def test_emulated_binary_path_builds_for_real(self):
        """The exact command line build.py sends to `blender`, executed by a stand-in that runs
        the --python-expr and the generator under the Python that has bpy."""
        exe = self.fake(EMULATED_BLENDER, "emulated_blender")
        src = self.write("gen_blender.py", BLENDER_GEN)
        prm = self.params({"_parts": {"body": {"expect": [30, 20, 8]}, "peg": {"expect": [8, 8, 5], "object": "body", "role": "fused"}}})
        printers = self.write("printers.json", json.dumps(X2D))
        with mock.patch.dict(os.environ, {"BLENDER": exe}):
            code, out = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--printer", printers)
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual((out["gate"], out["engine_info"]["mode"], out["engine_info"]["path"]), ("PASS", "binary", exe))
        self.assertTrue(os.path.isfile(out["blend"]))
        with mock.patch.dict(os.environ, {"BLENDER": exe}):                          # a rebuild into the same out/
            code, again = run("run", src, "--params", prm, "--out", self.out, "--no-wall-check", "--printer", printers)
        self.assertEqual((code, again["gate"], again["blend"]), (0, "PASS", out["blend"]), again.get("errors"))
        self.assertTrue(all(p["validate"]["files"][0]["checks"]["D1"]["state"] == "PASS" for p in out["parts"]))


# Two parts whose STLs came out different on every build of the same generator before 0.7.0
# (review): a rounded block, bevelled, cut by a manifold3d solid and notched by a prism (the same
# triangles in another order: Blender's extrude gives the prism's faces in another order on each
# run), and a part made by manifold3d whose flat faces from_mesh merged in a set's order (other
# triangles: the n-gons came out another way).
BLENDER_REBUILD_GEN = """# 3dprint-scout: engine=blender
import manifold3d as m3d
import blender_builder as bb

PARAMETERS = {"w": 40.0, "d": 30.0, "h": 12.0, "corner": 5.0, "round": 1.5, "wall": 8.0, "support": "cantilever"}

def build(p):
    plan = bb.round_profile([(0.0, 0.0), (p["w"], 0.0), (p["w"], p["d"]), (0.0, p["d"])], p["corner"])
    block = bb.prism(plan, p["h"], name="block")
    bb.bevel(block, p["round"])
    pocket = m3d.Manifold.cube([p["w"] - 2 * p["wall"], p["d"] - 2 * p["wall"], p["h"]]).translate([p["wall"], p["wall"], 3.0])
    bb.boolean(block, bb.from_manifold(pocket, "pocket"), "difference")
    u = bb.round_profile([(14.0, 6.0), (26.0, 6.0), (26.0, 20.0), (14.0, 20.0)], 3.0, corners=[0, 1])
    bb.boolean(block, bb.prism(u, 12.0, name="notch", z0=-1.0, plane="XZ"), "difference")
    cap = m3d.Manifold.cube([20.0, 12.0, 6.0]) - m3d.Manifold.cylinder(10.0, 4.0, 4.0, 96).translate([10.0, 6.0, -2.0])
    cap = bb.from_manifold(cap.translate([p["w"] + 5.0, 0.0, 0.0]), "cap")
    bb.part(block, "block")
    bb.part(cap, "cap")
    return {"block": block, "cap": cap}

if __name__ == "__main__":
    bb.main(build, PARAMETERS)
"""

# Holes through a block: OpenSCAD 2021.01 (CGAL) writes its triangles in another order on some runs.
SCAD_HOLES = """
$fn = 48;
difference() {
  cube([40, 30, 20]);
  translate([20, 15, 2]) cylinder(r = 10, h = 20);
  for (x = [4, 36], y = [4, 26]) translate([x, y, -1]) cylinder(r = 2, h = 30);
}
"""


def stl_bytes(tris, header=b"canonical test", attrs=None):
    """A binary STL of `tris` in this order, each with its normal and its attribute from `attrs`
    (Blender writes 0; any value must stay with its triangle)."""
    import math
    import struct
    out = [header.ljust(80, b"\0"), struct.pack("<I", len(tris))]
    for (p, q, r), a in zip(tris, attrs or [0] * len(tris)):
        u = [q[k] - p[k] for k in range(3)]
        v = [r[k] - p[k] for k in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        ln = math.sqrt(sum(c * c for c in n)) or 1.0
        out.append(struct.pack("<12fH", *(c / ln for c in n), *p, *q, *r, a))
    return b"".join(out)


def records(data):
    return [data[i:i + 50] for i in range(84, len(data), 50)]


def signed_volume(data):
    import struct
    vol = 0.0
    for rec in records(data):
        v = struct.unpack("<12f", rec[:48])
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = v[3:6], v[6:9], v[9:12]
        vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6
    return vol


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class CanonicalSTL(Base):
    """canonical_stl: one triangle order for an STL, the triangles themselves unchanged."""

    def write_bytes(self, name, data):
        path = os.path.join(self.d, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_any_order_gives_the_same_bytes_with_every_triangle_kept_whole(self):
        import random
        tris = box(20, 10, 5) + box(12, 12, 12, 30, 0, 0) + box(8, 8, 8, 32, 2, 2, inward=True)
        orders = []
        for seed in (1, 2, 3):
            shuffled = list(enumerate(tris))
            random.Random(seed).shuffle(shuffled)
            orders.append(stl_bytes([t for _, t in shuffled], attrs=[i % 7 for i, _ in shuffled]))
        self.assertEqual(len(set(orders)), 3)
        written = []
        for i, data in enumerate(orders):
            path = self.write_bytes(f"p{i}.stl", data)
            self.assertTrue(build.canonical_stl(path))
            written.append(read_bytes(path))
        self.assertEqual(len(set(written)), 1)                       # one order, whatever came in
        out = written[0]
        self.assertEqual(out[:84], orders[0][:84])                   # header and count kept
        self.assertEqual(sorted(records(out)), records(out))
        # Every 50-byte record is kept whole: the same triangles, each with its own normal, its own
        # vertex order (winding) and attribute; the solid's signed volume (cavity included) is unchanged.
        self.assertEqual(sorted(records(out)), sorted(records(orders[0])))
        self.assertAlmostEqual(signed_volume(out), 20 * 10 * 5 + 12 ** 3 - 8 ** 3, places=3)
        self.assertAlmostEqual(signed_volume(out), signed_volume(orders[0]), places=6)
        import validate
        self.assertEqual(sorted(validate.read_stl(path)), sorted(tris))

    def test_a_file_that_is_not_a_plain_binary_stl_is_left_alone(self):
        good = stl_bytes(list(reversed(box(10, 10, 10))))
        cases = {"empty.stl": b"", "short.stl": b"\0" * 50, "truncated.stl": good[:-10],
                 "trailing.stl": good + b"\0\0\0\0", "zero.stl": b"\0" * 80 + b"\0\0\0\0",
                 "count.stl": good[:80] + (13).to_bytes(4, "little") + good[84:]}
        for name, data in cases.items():
            with self.subTest(name):
                path = self.write_bytes(name, data)
                self.assertFalse(build.canonical_stl(path))
                self.assertEqual(read_bytes(path), data)
        ascii_ = os.path.join(self.d, "ascii.stl")
        write_stl(ascii_, list(reversed(box(10, 10, 10))), ascii_=True)
        before = read_bytes(ascii_)
        self.assertFalse(build.canonical_stl(ascii_))
        self.assertEqual(read_bytes(ascii_), before)
        self.assertFalse(build.canonical_stl(os.path.join(self.d, "missing.stl")))
        self.assertEqual(sorted(os.listdir(self.d)), sorted(list(cases) + ["ascii.stl"]))   # no twin left behind

    @unittest.skipUnless(os.name != "nt", "POSIX file modes")
    def test_the_file_keeps_its_mode_and_a_sorted_file_is_not_written(self):
        given = stl_bytes(list(reversed(box(10, 10, 10))))
        path = self.write_bytes("p.stl", given)
        os.chmod(path, 0o640)
        self.assertTrue(build.canonical_stl(path))
        self.assertNotEqual(read_bytes(path), given)                  # rewritten in order
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)
        before = os.stat(path)
        self.assertTrue(build.canonical_stl(path))                   # already in order: left as it is
        after = os.stat(path)
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))
        self.assertEqual(os.listdir(self.d), ["p.stl"])


class RebuildSameBytes(Base):
    """Building the same generator again with nothing changed writes the same STL bytes (the
    sha256 evidence is tied to), for every engine `run` drives; `record` leaves an STL as it is."""

    def fake(self, code, name="fake_blender"):
        py = self.write(name + ".py", code)
        exe = self.write(name, f"#!/bin/sh\nexec {sys.executable} {py} \"$@\"\n")
        os.chmod(exe, 0o755)
        return exe

    def same(self, outs):
        """The parts' bytes in every build, after checking each report's sha256 and manifest
        describe the file as it is."""
        import validate
        found = []
        for out in outs:
            files = {}
            for p in out["parts"]:
                data = read_bytes(p["stl"])
                self.assertEqual(p["sha256"], validate.file_sha256(p["stl"]))
                with open(p["stl"] + ".manifest.json", encoding="utf-8") as f:
                    self.assertEqual(json.load(f)["artifact_sha256"], p["sha256"])
                files[p["name"]] = data
            found.append(files)
        return found

    @unittest.skipUnless(os.name != "nt", "uses a shell wrapper as a fake blender")
    def test_a_blender_build_in_another_order_is_written_in_one(self):
        """The stand-in writes the cube's triangles shuffled on every run: run, --only and --proxy
        all write the one canonical order, before anything hashes the file."""
        exe = self.fake(FAKE_BLENDER)
        src = self.write("gen_blender.py", BLENDER_GEN)
        prm = self.params({"_parts": {"body": {"expect": [10, 10, 10]}, "peg": {"expect": [10, 10, 10]}}})
        proxy = self.write("proxy.json", "{}")
        outs = []
        with mock.patch.dict(os.environ, {"BLENDER": exe, "FAKE_BLENDER_SHUFFLE": "1"}):
            for i in range(3):
                code, out = run("run", src, "--params", prm, "--out", os.path.join(self.d, f"o{i}"), "--no-wall-check")
                self.assertEqual((code, out["errors"]), (0, []))
                outs.append(out)
            code, only = run("run", src, "--params", prm, "--out", os.path.join(self.d, "only"), "--only", "peg",
                             "--no-wall-check")
            code, prox = run("run", src, "--params", proxy, "--proxy", "body", "--out", os.path.join(self.d, "px"),
                             "--no-wall-check")
        builds = self.same(outs + [only, prox])
        self.assertEqual(builds[0], builds[1])
        self.assertEqual(builds[0], builds[2])
        self.assertEqual(builds[3]["peg"], builds[0]["peg"])
        self.assertEqual(builds[4]["body"], builds[0]["body"])
        self.assertTrue(prox["proxy"])
        data = builds[0]["body"]
        self.assertEqual(sorted(records(data)), records(data))
        # record takes an STL exported elsewhere as it is: never rewritten.
        mine = os.path.join(self.d, "mine.stl")
        with open(mine, "wb") as f:
            f.write(stl_bytes(list(reversed(box(10, 10, 10)))))
        before = read_bytes(mine)
        code, rec = run("record", mine, "--source", src, "--engine", "blender", "--out", os.path.join(self.d, "rec"),
                        "--no-wall-check", "--no-3mf")
        self.assertEqual(code, 0, rec.get("errors"))
        self.assertEqual(read_bytes(mine), before)

    @unittest.skipUnless(HAS_SCAD, "OpenSCAD not installed")
    def test_openscad_builds_the_same_bytes(self):
        src = self.write("holes.scad", SCAD_HOLES)
        outs = []
        for i in range(4):                                  # CGAL's order changes on some runs, not all
            code, out = run("run", src, "--out", os.path.join(self.d, f"o{i}"), "--no-wall-check", "--no-3mf")
            self.assertEqual(code, 0, out.get("errors"))
            outs.append(out)
        builds = self.same(outs)
        self.assertTrue(all(b == builds[0] for b in builds[1:]))

    @unittest.skipUnless(HAS_M3D, "manifold3d not installed")
    def test_python_builds_the_same_bytes(self):
        src = self.write("gen.py", PYGEN)
        prm = self.params({"_parts": {"body": {}, "peg": {}}, "w": 40, "d": 30, "h": 20, "wall": 2})
        outs = []
        for i in range(2):
            code, out = run("run", src, "--params", prm, "--out", os.path.join(self.d, f"o{i}"), "--no-wall-check",
                            "--no-3mf")
            self.assertEqual(code, 0, out.get("errors"))
            outs.append(out)
        builds = self.same(outs)
        self.assertEqual(builds[0], builds[1])
        self.assertEqual(sorted(records(builds[0]["body"])), records(builds[0]["body"]))

    @unittest.skipUnless(HAS_BPY and HAS_M3D, "bpy module or manifold3d not installed")
    def test_blender_builds_the_same_bytes(self):
        """Two builds in the bpy module, a --proxy build and (POSIX) one through the binary's
        command line: the same bytes for both parts. Before 0.7.0 every build of this generator
        wrote other bytes, and the part made by manifold3d other triangles."""
        src = self.write("rebuild.py", BLENDER_REBUILD_GEN)
        prm = self.params({"_parts": {"block": {}, "cap": {}}})
        proxy = self.write("proxy.json", "{}")
        outs = []
        with mock.patch.object(build, "find_blender", return_value=None):
            for i in range(2):
                code, out = run("run", src, "--params", prm, "--out", os.path.join(self.d, f"o{i}"),
                                "--blender-python", sys.executable, "--no-wall-check", "--no-3mf")
                self.assertEqual((code, out["engine_info"]["mode"]), (0, "bpy"), out.get("errors"))
                outs.append(out)
            code, prox = run("run", src, "--params", proxy, "--proxy", "block,cap", "--out", os.path.join(self.d, "px"),
                             "--blender-python", sys.executable, "--no-wall-check")
            self.assertEqual(code, 0, prox.get("errors"))
            outs.append(prox)
        if os.name != "nt":
            exe = self.fake(EMULATED_BLENDER, "emulated_blender")
            with mock.patch.dict(os.environ, {"BLENDER": exe}):
                code, out = run("run", src, "--params", prm, "--out", os.path.join(self.d, "bin"), "--no-wall-check",
                                "--no-3mf")
            self.assertEqual((code, out["engine_info"]["mode"]), (0, "binary"), out.get("errors"))
            outs.append(out)
        builds = self.same(outs)
        for b in builds[1:]:
            for name in ("block", "cap"):
                self.assertEqual(sorted(records(b[name])), sorted(records(builds[0][name])), f"{name}: other triangles")
                self.assertEqual(b[name], builds[0][name], f"{name}: the same triangles in another order")


class ThreeMF(Base):
    def read_back(self, path):
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            model = z.read("3D/3dmodel.model").decode()
        return names, model

    def test_structure_and_winding(self):
        a = os.path.join(self.d, "a.stl"); write_stl(a, box(20, 10, 5, 100, 100, 7))
        b = os.path.join(self.d, "b.stl"); write_stl(b, box(16, 16, 16) + box(12, 12, 12, 2, 2, 2, inward=True))
        out = os.path.join(self.d, "x.3mf")
        info = threemf.write_core_3mf([("a", a), ("b", b)], out)
        self.assertEqual(info, {"a": {"triangles": 12, "rotation_deg": 0, "object": "a"},
                                "b": {"triangles": 24, "rotation_deg": 0, "object": "b"}})
        names, model = self.read_back(out)
        self.assertTrue({"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= names)
        import xml.etree.ElementTree as ET
        ns = {"m": threemf.CORE_NS}
        root = ET.fromstring(model)
        self.assertEqual(root.get("unit"), "millimeter")
        items = root.findall("m:build/m:item", ns)
        self.assertEqual(len(items), 2)
        tz = float(items[0].get("transform").split()[-1])
        self.assertAlmostEqual(tz, -7)                      # part a lifted onto the bed
        # Signed volume of each object must stay positive (winding preserved, cavity intact).
        for obj, expected in zip(root.findall("m:resources/m:object", ns), (1000, 16 ** 3 - 12 ** 3)):
            vs = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in obj.iter(f"{{{threemf.CORE_NS}}}vertex")]
            vol = 0.0
            for t in obj.iter(f"{{{threemf.CORE_NS}}}triangle"):
                p, q, r = (vs[int(t.get(k))] for k in ("v1", "v2", "v3"))
                vol += (p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0])
                        + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6
            self.assertAlmostEqual(vol, expected, delta=0.5)


    def test_rotated_placement_fits_the_bed(self):
        bar = os.path.join(self.d, "bar.stl"); write_stl(bar, box(300, 20, 10, 50, 50, 0))
        out = os.path.join(self.d, "r.3mf")
        info = threemf.write_core_3mf([("bar", bar)], out, bed=(256, 256))
        self.assertGreater(info["bar"]["rotation_deg"], 0)
        names, model = self.read_back(out)
        import xml.etree.ElementTree as ET
        ns = {"m": threemf.CORE_NS}
        root = ET.fromstring(model)
        m = [float(v) for v in root.find("m:build/m:item", ns).get("transform").split()]
        vs = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in root.iter(f"{{{threemf.CORE_NS}}}vertex")]
        placed = [(x * m[0] + y * m[3] + z * m[6] + m[9], x * m[1] + y * m[4] + z * m[7] + m[10],
                   x * m[2] + y * m[5] + z * m[8] + m[11]) for x, y, z in vs]
        for i, limit in enumerate((256, 256)):
            lo, hi = min(p[i] for p in placed), max(p[i] for p in placed)
            self.assertGreaterEqual(lo, -1e-3); self.assertLessEqual(hi, limit + 1e-3)
        self.assertAlmostEqual(min(p[2] for p in placed), 0, places=3)       # still on the bed
        self.assertEqual(threemf.write_core_3mf([("bar", bar)], os.path.join(self.d, "n.3mf"))["bar"]["rotation_deg"], 0)

    def test_grouped_parts_keep_their_positions_under_one_parent(self):
        """Parts of one object become mesh objects referenced by a parent through components
        with identity transforms; the layout moves the parent, so the assembly is intact."""
        import xml.etree.ElementTree as ET
        lid = os.path.join(self.d, "lid.stl"); write_stl(lid, box(60, 40, 3, 100, 100, 0))
        label = os.path.join(self.d, "label.stl"); write_stl(label, box(30, 10, 1, 115, 115, 3))
        peg = os.path.join(self.d, "peg.stl"); write_stl(peg, box(5, 5, 5))
        out = os.path.join(self.d, "g.3mf")
        info = threemf.write_core_3mf([("lid", lid), ("label", label), ("peg", peg)], out, bed=(256, 256),
                                      objects=[{"name": "lid", "parts": ["lid", "label"], "main": "lid"}])
        self.assertEqual({k: v["object"] for k, v in info.items()}, {"lid": "lid", "label": "lid", "peg": "peg"})
        ns = {"m": threemf.CORE_NS}
        root = ET.fromstring(self.read_back(out)[1])
        objs = {o.get("id"): o for o in root.findall("m:resources/m:object", ns)}
        parents = [o for o in objs.values() if o.find("m:components", ns) is not None]
        self.assertEqual(len(parents), 1)
        comps = parents[0].findall("m:components/m:component", ns)
        self.assertEqual([objs[c.get("objectid")].get("name") for c in comps], ["lid", "label"])
        self.assertTrue(all(c.get("transform").split() == ["1", "0", "0", "0", "1", "0", "0", "0", "1", "0", "0", "0"]
                            for c in comps))
        items = root.findall("m:build/m:item", ns)
        self.assertEqual({i.get("objectid") for i in items}, {parents[0].get("id"), [k for k, o in objs.items() if o.get("name") == "peg"][0]})
        # The parent's transform puts the assembly on the bed with its corner at the cursor.
        t = [float(v) for v in [i for i in items if i.get("objectid") == parents[0].get("id")][0].get("transform").split()]
        self.assertEqual(t[9:], [-100.0, -100.0, 0.0])

    def test_cli_prints_json(self):
        a = os.path.join(self.d, "a.stl"); write_stl(a, box(20, 10, 5))
        out = os.path.join(self.d, "c.3mf")
        r = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "..", "scripts", "threemf.py"), out, a],
                           capture_output=True, text=True, encoding="utf-8")
        rep = json.loads(r.stdout)
        self.assertEqual((r.returncode, rep["ran"], rep["objects"]["a"]["triangles"]), (0, True, 12))
        r = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "..", "scripts", "threemf.py"), out, a],
                           capture_output=True, text=True, encoding="utf-8")
        rep = json.loads(r.stdout)                                           # refuses to overwrite, in JSON
        self.assertEqual((r.returncode, rep["ran"]), (1, False))
        self.assertIn("already exists", rep["errors"][0])


class Usage(Base):
    def test_no_subcommand_is_json(self):
        code, out = run()
        self.assertEqual(code, 1)
        self.assertFalse(out["ran"])


if __name__ == "__main__":
    unittest.main()
