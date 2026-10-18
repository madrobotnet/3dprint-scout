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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import build    # noqa: E402
import threemf  # noqa: E402
from test_validate import X2D, box, write_stl  # noqa: E402

HAS_SCAD = build.find_openscad() is not None
HAS_M3D = find_spec("manifold3d") is not None

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

    def test_generator_exception(self):
        src = self.write("boom.py", "def build(p):\n    raise ValueError('wall too thin')\n")
        code, out = run("run", src, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("wall too thin", out["errors"][0])


class Record(Base):
    def test_record_external_build(self):
        stl = os.path.join(self.d, "fusion_part.stl")
        write_stl(stl, box(20, 20, 20))
        src = self.write("gen_fusion.py", "def run(context=None):\n    pass\n")
        prm = self.params({"_parts": {"fusion_part": {"expect": [20, 20, 20]}}})
        code, out = run("record", stl, "--source", src, "--params", prm, "--out", self.out, "--no-wall-check")
        self.assertEqual(code, 0, out.get("errors"))
        self.assertEqual(out["engine"], "fusion")
        self.assertEqual(out["parts"][0]["validate"]["files"][0]["checks"]["R3"]["state"], "PASS")

    def test_broken_stl_keeps_the_json_contract(self):
        """G4: a 0-byte or truncated export gets no manifest, is left out of the 3MF and is
        reported; the other parts are still recorded and validated. JSON, never a traceback."""
        good = os.path.join(self.d, "good.stl"); write_stl(good, box(20, 20, 20))
        empty = os.path.join(self.d, "empty.stl"); open(empty, "wb").close()
        trunc = os.path.join(self.d, "trunc.stl"); write_stl(trunc, box(20, 20, 20))
        with open(trunc, "r+b") as f:
            f.truncate(84 + 50 * 5)
        src = self.write("gen_fusion.py", "def run(context=None):\n    pass\n")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "scripts", "build.py"), "record",
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
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "scripts", "threemf.py"), out, a],
                           capture_output=True, text=True, encoding="utf-8")
        rep = json.loads(r.stdout)
        self.assertEqual((r.returncode, rep["ran"], rep["objects"]["a"]["triangles"]), (0, True, 12))
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "scripts", "threemf.py"), out, a],
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
