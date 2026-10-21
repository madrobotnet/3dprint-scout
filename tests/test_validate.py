"""Tests for scripts/validate.py. Standard library only: python3 -m unittest discover tests"""
import io
import json
import math
import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import validate  # noqa: E402


# ----------------------------------------------------------------- fixtures --
def box(w, d, h, x=0.0, y=0.0, z=0.0, inward=False):
    """12 triangles, counter-clockwise seen from outside (outward normals)."""
    p = [(x, y, z), (x + w, y, z), (x + w, y + d, z), (x, y + d, z),
         (x, y, z + h), (x + w, y, z + h), (x + w, y + d, z + h), (x, y + d, z + h)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    tris = [(p[a], p[b], p[c]) for a, b, c in f]
    return [(t[0], t[2], t[1]) for t in tris] if inward else tris


def cylinder(r, h, n):
    tris = []
    ring = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % n]
        tris.append(((0, 0, 0), (x1, y1, 0), (x0, y0, 0)))
        tris.append(((0, 0, h), (x0, y0, h), (x1, y1, h)))
        tris.append(((x0, y0, 0), (x1, y1, 0), (x1, y1, h)))
        tris.append(((x0, y0, 0), (x1, y1, h), (x0, y0, h)))
    return tris


def write_stl(path, tris, ascii_=False):
    if ascii_:
        with open(path, "w") as f:
            f.write("solid t\n")
            for t in tris:
                f.write(" facet normal 0 0 0\n  outer loop\n")
                for v in t:
                    f.write(f"   vertex {v[0]} {v[1]} {v[2]}\n")
                f.write("  endloop\n endfacet\n")
            f.write("endsolid t\n")
        return
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", 0, 0, 0))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(b"\0\0")


X2D = {"schema": "3dprint.printers/1", "default": "x2d", "printers": {
    "x2d": {"process": "fdm",
            "bed": {"area": [[0, 0], [256, 0], [256, 256], [0, 256]], "height": 261, "exclude": [],
                    "source": "slicer-profile"},
            "tools": [{"nozzle": 0.4, "area": [[0, 0], [256, 0], [256, 256], [0, 256]], "height": 261},
                      {"nozzle": 0.4, "area": [[20.5, 0], [256, 0], [256, 256], [20.5, 256]], "height": 256}]},
    "x1c": {"process": "fdm",
            "bed": {"area": [[0, 0], [256, 0], [256, 256], [0, 256]], "height": 250,
                    "exclude": [[[0, 0], [18, 0], [18, 28], [0, 28]]], "source": "slicer-profile"}},
    "guess": {"process": "fdm",
              "bed": {"area": [[0, 0], [220, 0], [220, 220], [0, 220]], "height": 250, "source": "default"}},
    "resin": {"process": "resin", "bed": {"area": [[0, 0], [100, 0], [100, 60], [0, 60]], "height": 150}},
}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.printers = os.path.join(self.d, "printers.json")
        with open(self.printers, "w") as f:
            json.dump(X2D, f)

    def tearDown(self):
        self.tmp.cleanup()

    def stl(self, name, tris, **kw):
        p = os.path.join(self.d, name)
        write_stl(p, tris, **kw)
        return p

    def run_v(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = validate.main(list(args) + ["--no-wall-check"])
        return code, json.loads(buf.getvalue())

    def check(self, out, cid, i=0):
        return out["files"][i]["checks"][cid]["state"]


# -------------------------------------------------------------------- tests --
class SanityG4(Base):
    def test_empty_file(self):
        p = os.path.join(self.d, "e.stl"); open(p, "wb").close()
        code, out = self.run_v(p)
        self.assertEqual(code, 2)
        self.assertFalse(out["files"][0]["artifact_sane"])
        self.assertEqual(out["gate"], "FAIL")

    def test_truncated_binary(self):
        p = self.stl("t.stl", box(10, 10, 10))
        with open(p, "r+b") as f:
            f.truncate(84 + 50 * 5)
        code, out = self.run_v(p)
        self.assertEqual(code, 2)

    def test_nan(self):
        tris = box(10, 10, 10); tris[0] = ((float("nan"), 0, 0), tris[0][1], tris[0][2])
        code, out = self.run_v(self.stl("n.stl", tris))
        self.assertIn("non-finite", out["files"][0]["artifact_error"])

    def test_ascii_ok(self):
        code, out = self.run_v(self.stl("a.stl", box(10, 20, 30), ascii_=True), "--expect", "10,20,30")
        self.assertEqual(code, 0)
        self.assertEqual(self.check(out, "D1"), "PASS")

    def test_trailing_bytes_and_bom_are_read(self):
        p = self.stl("t.stl", box(10, 20, 30))
        with open(p, "ab") as f:
            f.write(b"\0" * 7)                                 # some exporters pad the file
        code, out = self.run_v(p, "--expect", "10,20,30")
        self.assertEqual((code, self.check(out, "D1")), (0, "PASS"))
        a = self.stl("a.stl", box(10, 20, 30), ascii_=True)
        with open(a, "rb") as f:
            data = f.read()
        with open(a, "wb") as f:
            f.write(b"\xef\xbb\xbf" + data)                  # UTF-8 BOM
        code, out = self.run_v(a, "--expect", "10,20,30")
        self.assertEqual((code, self.check(out, "D1")), (0, "PASS"))

    def test_truncated_message_names_the_cause(self):
        p = self.stl("t.stl", box(10, 10, 10))
        with open(p, "r+b") as f:
            f.truncate(84 + 50 * 5)
        _, out = self.run_v(p)
        self.assertIn("truncated", out["files"][0]["artifact_error"])
        self.assertNotIn("ASCII header", out["files"][0]["artifact_error"])
        with open(p, "wb") as f:
            f.write(b"hello world" * 20)
        _, out = self.run_v(p)
        self.assertIn("not a valid STL", out["files"][0]["artifact_error"])


class MeshM(Base):
    def test_clean_cube(self):
        code, out = self.run_v(self.stl("c.stl", box(20, 20, 20)), "--expect", "20,20,20")
        m = out["files"][0]["metrics"]
        self.assertAlmostEqual(m["volume_mm3"], 8000, places=1)
        for cid in ("D1", "D3", "D4", "M1", "M2", "M3", "M4", "M5", "P1", "P2"):
            self.assertEqual(self.check(out, cid), "PASS", cid)

    def test_open_mesh(self):
        _, out = self.run_v(self.stl("o.stl", box(20, 20, 20)[1:]))
        self.assertEqual(self.check(out, "M1"), "FAIL")

    def test_flipped_face(self):
        t = box(20, 20, 20); a, b, c = t[4]; t[4] = (a, c, b)
        _, out = self.run_v(self.stl("f.stl", t))
        self.assertEqual(self.check(out, "M2"), "FAIL")

    def test_inverted_volume(self):
        _, out = self.run_v(self.stl("i.stl", box(20, 20, 20, inward=True)))
        self.assertEqual(self.check(out, "D3"), "FAIL")

    def test_degenerate_and_duplicate(self):
        t = box(20, 20, 20) + [((0, 0, 0), (1, 0, 0), (2, 0, 0))]
        _, out = self.run_v(self.stl("dg.stl", t))
        self.assertEqual(self.check(out, "M3"), "FAIL")
        t2 = box(20, 20, 20) + [box(20, 20, 20)[0]]
        _, out2 = self.run_v(self.stl("dp.stl", t2))
        self.assertEqual(self.check(out2, "M4"), "FAIL")

    def test_shell_count(self):
        two = box(10, 10, 10) + box(10, 10, 10, x=30)
        _, out = self.run_v(self.stl("2.stl", two))
        self.assertEqual(self.check(out, "M5"), "FAIL")
        _, out = self.run_v(self.stl("2.stl", two), "--shells", "2")
        self.assertEqual(self.check(out, "M5"), "PASS")

    def test_hollow_cube_cavity(self):
        t = box(20, 20, 20) + box(16, 16, 16, 2, 2, 2, inward=True)
        _, out = self.run_v(self.stl("h.stl", t), "--shells", "2")
        self.assertAlmostEqual(out["files"][0]["metrics"]["volume_mm3"], 8000 - 4096, places=1)
        self.assertEqual(self.check(out, "M1"), "PASS")


class DimensionsD(Base):
    def test_unit_error_cm(self):
        _, out = self.run_v(self.stl("u.stl", box(2, 4, 6)), "--expect", "20,40,60")
        self.assertEqual(self.check(out, "D1"), "FAIL")
        self.assertEqual(self.check(out, "D4"), "FAIL")
        self.assertIn("unit", out["files"][0]["checks"]["D4"]["note"])

    def test_axis_swap(self):
        _, out = self.run_v(self.stl("y.stl", box(20, 60, 40)), "--expect", "20,40,60")
        self.assertEqual(self.check(out, "D4"), "FAIL")
        self.assertIn("Z-up", out["files"][0]["checks"]["D4"]["note"])

    def test_tessellation_tolerance(self):
        # 30-segment cylinder r=30: Y extent is 2*r*cos(6 deg) ~ 59.67, off by more than 0.1
        p = self.stl("cy.stl", cylinder(30, 10, 30))
        _, out = self.run_v(p, "--expect", "60,60,10")
        self.assertEqual(self.check(out, "D1"), "FAIL")
        _, out = self.run_v(p, "--expect", "60,60,10", "--tol", "0.4")
        self.assertEqual(self.check(out, "D1"), "PASS")

    def test_no_expect_is_unverified(self):
        _, out = self.run_v(self.stl("c.stl", box(20, 20, 20)))
        self.assertEqual(self.check(out, "D1"), "UNVERIFIED")
        self.assertEqual(out["gate"], "INCOMPLETE")


class BedD2(Base):
    def p(self, *extra):
        return ["--printer", self.printers] + list(extra)

    def test_diagonal_fit(self):
        _, out = self.run_v(self.stl("bar.stl", box(300, 20, 10)), *self.p())
        self.assertEqual(self.check(out, "D2"), "PASS")
        self.assertGreater(out["files"][0]["checks"]["D2"]["value"]["rotation_deg"], 0)

    def test_too_long(self):
        _, out = self.run_v(self.stl("bar.stl", box(400, 20, 10)), *self.p())
        self.assertEqual(self.check(out, "D2"), "FAIL")
        self.assertEqual(out["files"][0]["checks"]["D2"]["return_to"], "phase2")

    def test_dual_nozzle_intersection(self):
        p = self.stl("sq.stl", box(240, 240, 10))
        _, one = self.run_v(p, *self.p("--tools", "0"))
        _, both = self.run_v(p, *self.p("--tools", "0,1"))
        self.assertEqual(self.check(one, "D2"), "PASS")
        self.assertEqual(self.check(both, "D2"), "FAIL")      # 235.5 mm usable with both nozzles
        self.assertEqual(both["printer"]["height"], 256)

    def test_height_limit(self):
        _, out = self.run_v(self.stl("t.stl", box(20, 20, 258)), *self.p("--tools", "0,1"))
        self.assertEqual(self.check(out, "D2"), "FAIL")

    def test_exclusion_zone(self):
        _, warn = self.run_v(self.stl("a.stl", box(250, 250, 10)),
                             *self.p("--printer-id", "x1c", "--tools", ""))
        self.assertEqual(self.check(warn, "D2"), "WARN")
        _, ok = self.run_v(self.stl("b.stl", box(225, 225, 10)),
                           *self.p("--printer-id", "x1c", "--tools", ""))
        self.assertEqual(self.check(ok, "D2"), "PASS")

    def test_default_bed_is_unverified(self):
        _, out = self.run_v(self.stl("c.stl", box(20, 20, 20)), *self.p("--printer-id", "guess", "--tools", ""))
        self.assertEqual(self.check(out, "D2"), "UNVERIFIED")

    def test_resin_rejected(self):
        code, out = self.run_v(self.stl("c.stl", box(20, 20, 20)), *self.p("--printer-id", "resin"))
        self.assertEqual(code, 1)
        self.assertIn("only FDM", out["errors"][0])

    def write_printers(self, name, data):
        path = os.path.join(self.d, name)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_closed_polygon_is_a_rectangle(self):
        closed = self.write_printers("closed.json", {"default": "p", "printers": {"p": {"process": "fdm", "bed": {
            "area": [[0, 0], [200, 0], [200, 200], [0, 200], [0, 0]], "height": 200}}}})
        _, out = self.run_v(self.stl("w.stl", box(250, 20, 10)), "--printer", closed)
        self.assertEqual(out["printer"]["usable_rect"], [0, 0, 200, 200])
        self.assertEqual(self.check(out, "D2"), "PASS")                 # fits diagonally, hard check
        _, out = self.run_v(self.stl("h.stl", box(400, 300, 10)), "--printer", closed)
        self.assertEqual(self.check(out, "D2"), "FAIL")                 # no soft round-bed WARN

    def test_missing_height_is_unverified_not_pass(self):
        nh = self.write_printers("nh.json", {"default": "p", "printers": {"p": {"process": "fdm", "bed": {
            "area": [[0, 0], [200, 0], [200, 200], [0, 200]]}}}})
        _, out = self.run_v(self.stl("t.stl", box(20, 20, 400)), "--printer", nh)
        self.assertEqual(self.check(out, "D2"), "UNVERIFIED")
        self.assertIn("height", out["files"][0]["checks"]["D2"]["note"])
        self.assertEqual(out["gate"], "INCOMPLETE")
        _, out = self.run_v(self.stl("w.stl", box(400, 300, 10)), "--printer", nh)
        self.assertEqual(self.check(out, "D2"), "FAIL")                 # the area is still checked

    def test_envelope_required_and_single_printer_default(self):
        flat = self.write_printers("flat.json", {"process": "fdm", "bed": {"area": [[0, 0], [1, 0], [1, 1], [0, 1]]}})
        code, out = self.run_v(self.stl("c.stl", box(20, 20, 20)), "--printer", flat)
        self.assertEqual(code, 1)
        self.assertIn('"printers"', out["errors"][0])
        one = self.write_printers("one.json", {"printers": {"only": X2D["printers"]["x2d"]}})
        code, out = self.run_v(self.stl("c.stl", box(20, 20, 20)), "--printer", one)
        self.assertEqual((code, out["printer"]["id"], self.check(out, "D2")), (0, "only", "PASS"))
        two = self.write_printers("two.json", {"printers": {"a": X2D["printers"]["x2d"], "b": X2D["printers"]["x1c"]}})
        code, out = self.run_v(self.stl("c.stl", box(20, 20, 20)), "--printer", two)
        self.assertEqual(code, 1)
        self.assertIn("--printer-id", out["errors"][0])


class PrintabilityP(Base):
    def test_cube_and_cylinder_have_no_overhang(self):
        for name, tris in (("c.stl", box(20, 20, 20)), ("cy.stl", cylinder(10, 20, 64))):
            _, out = self.run_v(self.stl(name, tris))
            self.assertEqual(out["files"][0]["metrics"]["overhang_pct"], 0.0, name)

    def test_t_shape_overhang_warns(self):
        t = box(6, 6, 20, 17, 0, 0) + box(40, 6, 4, 0, 0, 20)
        _, out = self.run_v(self.stl("t.stl", t), "--shells", "2")
        self.assertEqual(self.check(out, "P2"), "WARN")
        self.assertNotEqual(out["files"][0]["checks"]["P2"]["kind"], "hard")
        self.assertNotEqual(out["gate"], "FAIL")             # soft checks never fail the gate
        p2 = out["files"][0]["checks"]["P2"]
        # S1-F8: the limit is named as such, and the steepest overhang is measured (the bar's
        # underside faces straight down: 90 deg from vertical); the note carries both.
        self.assertEqual(p2["value"]["limit_deg"], 45.0)
        self.assertEqual(p2["value"]["steepest_deg"], 90.0)
        self.assertNotIn("max_angle_deg", p2["value"])
        self.assertIn("steepest face 90.0 deg", p2["note"])
        self.assertIn(f"{p2['value']['overhang_pct']} %", p2["note"])
        _, out = self.run_v(self.stl("c.stl", box(20, 20, 20)))
        self.assertEqual(out["files"][0]["checks"]["P2"]["value"]["steepest_deg"], 0.0)     # walls only: nothing overhangs
        # Octahedron on a vertex: its lower faces lean 45 deg from vertical (the limit itself is not over it).
        v = [(0, 0, -10), (10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0), (0, 0, 10)]
        f = [(0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 1, 4), (5, 1, 2), (5, 2, 3), (5, 3, 4), (5, 4, 1)]
        _, out = self.run_v(self.stl("oct.stl", [(v[a], v[b], v[c]) for a, b, c in f]))
        self.assertAlmostEqual(out["files"][0]["checks"]["P2"]["value"]["steepest_deg"], 35.3, delta=0.1)
        self.assertEqual(self.check(out, "P2"), "PASS")

    def test_no_flat_bottom(self):
        # Octahedron balanced on a vertex: nothing flat on the bed
        v = [(0, 0, -10), (10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0), (0, 0, 10)]
        f = [(0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 1, 4), (5, 1, 2), (5, 2, 3), (5, 3, 4), (5, 4, 1)]
        _, out = self.run_v(self.stl("oct.stl", [(v[a], v[b], v[c]) for a, b, c in f]))
        self.assertEqual(self.check(out, "P1"), "WARN")


class FreshnessR3(Base):
    def test_fresh_stale_replaced(self):
        src = os.path.join(self.d, "model.scad")
        with open(src, "w") as f:
            f.write("cube(20);")
        params = os.path.join(self.d, "params.json")
        with open(params, "w") as f:
            json.dump({"w": 20}, f)
        stl = self.stl("m.stl", box(20, 20, 20))
        validate.write_manifest(stl, [src], {"w": 20}, "openscad")

        _, out = self.run_v(stl, "--source", src, "--params", params)
        self.assertEqual(self.check(out, "R3"), "PASS")

        with open(params, "w") as f:
            json.dump({"w": 25}, f)                          # parameter changed, STL not rebuilt
        _, out = self.run_v(stl, "--source", src, "--params", params)
        self.assertEqual(self.check(out, "R3"), "FAIL")
        self.assertIn("STALE", out["files"][0]["checks"]["R3"]["note"])

        with open(params, "w") as f:
            json.dump({"w": 20}, f)
        write_stl(stl, box(21, 20, 20))                      # STL swapped after the build
        _, out = self.run_v(stl, "--source", src, "--params", params)
        self.assertEqual(self.check(out, "R3"), "FAIL")
        self.assertIn("replaced", out["files"][0]["checks"]["R3"]["note"])

    def test_no_manifest(self):
        _, out = self.run_v(self.stl("m.stl", box(20, 20, 20)))
        self.assertEqual(self.check(out, "R3"), "UNVERIFIED")

    def test_source_spelling_and_order_do_not_matter(self):
        cwd = os.getcwd()
        os.chdir(self.d)
        try:
            for name, text in (("model.scad", "include <lib.scad>\ncube(20);"), ("lib.scad", "// lib\n")):
                with open(name, "w") as f:
                    f.write(text)
            stl = self.stl("m.stl", box(20, 20, 20))
            validate.write_manifest(stl, [os.path.abspath("lib.scad"), "model.scad"], {"w": 20}, "openscad")
            with open(stl + ".manifest.json") as f:
                self.assertEqual(json.load(f)["sources"], ["lib.scad", "model.scad"])
            for sources in (["./model.scad", "lib.scad"], ["lib.scad", "model.scad"], ["model.scad", "./lib.scad", "lib.scad"]):
                _, out = self.run_v(stl, "--source", *sources)
                self.assertEqual(self.check(out, "R3"), "FAIL", sources)      # params differ ({} vs w=20) ...
            params = os.path.join(self.d, "p.json")
            with open(params, "w") as f:
                json.dump({"w": 20, "_assumptions": ["metadata keys are not hashed"], "_parts": {"m": {}}}, f)
            for sources in (["./model.scad", "lib.scad"], ["lib.scad", "model.scad"]):
                _, out = self.run_v(stl, "--source", *sources, "--params", params)
                self.assertEqual(self.check(out, "R3"), "PASS", sources)      # ... and "_" keys never count
        finally:
            os.chdir(cwd)

    def test_wrong_source_list_is_named(self):
        src = os.path.join(self.d, "model.scad"); lib = os.path.join(self.d, "lib.scad")
        for p in (src, lib):
            with open(p, "w") as f:
                f.write("// " + p)
        stl = self.stl("m.stl", box(20, 20, 20))
        validate.write_manifest(stl, [src, lib], {}, "openscad")
        _, out = self.run_v(stl, "--source", src)
        r3 = out["files"][0]["checks"]["R3"]
        self.assertEqual(r3["state"], "FAIL")
        self.assertEqual(r3["value"], {"manifest_sources": ["lib.scad", "model.scad"], "given_sources": ["model.scad"]})
        self.assertIn("lib.scad", r3["note"])
        self.assertIn("--source", r3["note"])

    def test_extra_sources_do_not_make_a_part_stale(self):
        """A mixed build's --source list holds every generator; R3 hashes only the files this
        STL's manifest recorded, so another part's generator may change (S3-1 / S3-2)."""
        src = os.path.join(self.d, "model.scad"); other = os.path.join(self.d, "other.py")
        for p in (src, other):
            with open(p, "w") as f:
                f.write("// " + p)
        stl = self.stl("m.stl", box(20, 20, 20))
        validate.write_manifest(stl, [src], {}, "openscad")
        _, out = self.run_v(stl, "--source", src, other)
        self.assertEqual(self.check(out, "R3"), "PASS")
        with open(other, "a") as f:
            f.write("\n# changed\n")
        _, out = self.run_v(stl, "--source", src, other)
        self.assertEqual(self.check(out, "R3"), "PASS")                     # not this part's source
        with open(src, "a") as f:
            f.write("\n// changed\n")
        _, out = self.run_v(stl, "--source", src, other)
        self.assertEqual(self.check(out, "R3"), "FAIL")
        self.assertTrue(out["files"][0]["checks"]["R3"]["note"].startswith("STALE: source"))


def tube(n, r_out=30.0, r_in=28.0, h=20.0):
    """A closed hollow cylinder with 2 mm walls and 8*n triangles."""
    ring = lambda r: [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    ro, ri, tris = ring(r_out), ring(r_in), []
    for i in range(n):
        j = (i + 1) % n
        (x0, y0), (x1, y1), (u0, v0), (u1, v1) = ro[i], ro[j], ri[i], ri[j]
        tris += [((x0, y0, 0), (x1, y1, 0), (x1, y1, h)), ((x0, y0, 0), (x1, y1, h), (x0, y0, h)),
                 ((u0, v0, 0), (u1, v1, h), (u1, v1, 0)), ((u0, v0, 0), (u0, v0, h), (u1, v1, h)),
                 ((x0, y0, 0), (u1, v1, 0), (x1, y1, 0)), ((x0, y0, 0), (u0, v0, 0), (u1, v1, 0)),
                 ((x0, y0, h), (x1, y1, h), (u1, v1, h)), ((x0, y0, h), (u1, v1, h), (u0, v0, h))]
    return tris


class OptionalWallP3(Base):
    def test_wall_check_never_crashes(self):
        """With or without numpy/rtree, P3 yields a verdict and JSON is emitted."""
        p = self.stl("h.stl", box(20, 20, 20) + box(16, 16, 16, 2, 2, 2, inward=True))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = validate.main([p, "--shells", "2"])      # wall check enabled
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertIn(out["files"][0]["checks"]["P3"]["state"], ("PASS", "WARN", "UNVERIFIED"))

    def test_thin_and_thick_walls(self):
        try:
            import numpy, rtree  # noqa: F401
        except ImportError:
            self.skipTest("numpy/rtree not installed")
        thin = validate.wall_thickness(box(30, 30, 30) + box(28, 28, 28, 1, 1, 1, inward=True), 1.2)
        self.assertEqual(thin[0], "WARN"); self.assertAlmostEqual(thin[1]["wall_p5_mm"], 1.0, delta=0.01)
        self.assertIn("wall 1.00 mm against the 1.2 mm minimum", thin[2])       # S5-F4: the value is in the note
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate.main([self.stl("thin.stl", box(30, 30, 30) + box(28, 28, 28, 1, 1, 1, inward=True)), "--shells", "2"])
        out = json.loads(buf.getvalue())
        self.assertTrue(any(w.startswith("thin.stl P3: 5th-percentile wall 1.00 mm") for w in out["warnings"]), out["warnings"])
        thick = validate.wall_thickness(box(30, 30, 30) + box(26, 26, 26, 2, 2, 2, inward=True), 1.2)
        self.assertEqual(thick[0], "PASS"); self.assertAlmostEqual(thick[1]["wall_p5_mm"], 2.0, delta=0.01)
        solid = validate.wall_thickness(box(30, 30, 30), 1.2)            # thicker than the depth cap
        self.assertEqual((solid[0], solid[1]["wall_p5_mm"]), ("PASS", validate.P3_MAX_DEPTH))

    def test_large_mesh_returns_json_quickly_in_bounded_memory(self):
        """100k triangles: the old all-pairs ray casting needed > 1 GB and was killed on bigger
        meshes; the batched version must finish inside a 768 MB address space (Linux) in seconds."""
        import subprocess, time
        p = self.stl("big.stl", tube(12500))                                  # 100 000 triangles
        cmd = [sys.executable, "-I", "-B", os.path.join(HERE, "..", "scripts", "validate.py"), p]
        kw = {}
        if sys.platform.startswith("linux"):
            import resource
            kw["preexec_fn"] = lambda: resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, timeout=120, **kw)
        self.assertLess(time.time() - t0, 60)
        out = json.loads(r.stdout.decode("utf-8"))                            # JSON, not a traceback
        self.assertTrue(out["ran"], out.get("errors"))
        p3 = out["files"][0]["checks"]["P3"]
        self.assertIn(p3["state"], ("PASS", "UNVERIFIED"))                    # 2 mm walls, or deps missing
        if p3["state"] == "PASS":
            self.assertAlmostEqual(p3["value"]["wall_p5_mm"], 2.0, delta=0.05)

    def test_face_cap_skips_with_a_note(self):
        old = validate.P3_MAX_FACES
        validate.P3_MAX_FACES = 10
        try:
            st, val, note = validate.wall_thickness(box(20, 20, 20), 1.2)
        finally:
            validate.P3_MAX_FACES = old
        self.assertEqual(st, "UNVERIFIED")
        self.assertIn("skipped", note)
        self.assertEqual(val["triangles"], 12)


class JsonContract(Base):
    def run_raw(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = validate.main(list(args))
        return code, json.loads(buf.getvalue())             # must parse: JSON even on errors

    def test_bad_arguments_still_json(self):
        for args in ([], ["--expect", "1,2", "x.stl"], ["x.stl", "--tol", "abc"]):
            code, out = self.run_raw(*args)
            self.assertEqual(code, 1, args)
            self.assertFalse(out["ran"])
            self.assertTrue(out["errors"])

    def test_missing_printer_file_is_unverified_not_fail(self):
        """The printer is often simply not known yet (Phase 2); D2 is undecided, not failed."""
        code, out = self.run_raw(self.stl("c.stl", box(20, 20, 20)), "--printer", "/nope/printers.json",
                                 "--expect", "20,20,20", "--no-wall-check")
        self.assertEqual(code, 0)
        self.assertEqual(out["gate"], "INCOMPLETE")
        self.assertEqual(out["files"][0]["checks"]["D2"]["state"], "UNVERIFIED")
        self.assertIn("/nope/printers.json", out["files"][0]["checks"]["D2"]["note"])
        self.assertTrue(any("printer file not found" in w for w in out["warnings"]))
        self.assertEqual(out["errors"], [])

    def test_malformed_printer_file_is_an_error(self):
        bad = os.path.join(self.d, "bad.json")
        with open(bad, "w") as f:
            f.write("{not json")
        code, out = self.run_raw(self.stl("c.stl", box(20, 20, 20)), "--printer", bad)
        self.assertEqual((code, out["gate"], out["ran"]), (1, "FAIL", False))
        self.assertTrue(out["errors"])


class GateG2(Base):
    def test_one_bad_part_fails_all(self):
        good = self.stl("g.stl", box(20, 20, 20))
        bad = self.stl("b.stl", box(20, 20, 20)[1:])
        _, out = self.run_v(good, bad, "--expect", "20,20,20")
        self.assertEqual(out["gate"], "FAIL")
        self.assertEqual(len(out["files"]), 2)


if __name__ == "__main__":
    unittest.main()
