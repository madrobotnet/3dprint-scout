"""Tests for scripts/sdf.py (needs manifold3d)."""
import io
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import validate  # noqa: E402

HAS_M3D = find_spec("manifold3d") is not None
if HAS_M3D:
    import manifold3d as m3d  # noqa: E402
    import parts  # noqa: E402
    import sdf  # noqa: E402

TOPOLOGY = ("open_edges", "nonmanifold_edges", "flipped_edges", "degenerate_faces", "duplicate_faces")


def metrics(man):
    V, F = parts.mesh_arrays(man)
    return validate.analyse([(tuple(V[a]), tuple(V[b]), tuple(V[c])) for a, b, c in F])


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class SdfCase(unittest.TestCase):
    def assertSolid(self, man, shells=1, bbox=None, volume=None, rel=0.03):
        self.assertEqual(man.status(), m3d.Error.NoError)
        m = metrics(man)
        bad = {k: m[k] for k in TOPOLOGY if m[k]}
        self.assertEqual(bad, {}, f"topology: {bad}")
        self.assertEqual(m["shells"], shells)
        self.assertGreater(m["volume_mm3"], 0)
        if bbox is not None:
            for got, want in zip(m["bbox_mm"], bbox):
                self.assertAlmostEqual(got, want, delta=0.3)       # grid resolution 0.5
        if volume is not None:
            self.assertAlmostEqual(m["volume_mm3"], volume, delta=abs(volume) * rel)
        return m


class Primitives(SdfCase):
    def test_distances_and_bounds(self):
        s = sdf.sphere(10, [1, 2, 3])
        self.assertAlmostEqual(s(1, 2, 3), -10)
        self.assertAlmostEqual(s(13, 2, 3), 2)
        self.assertEqual(s.bounds, ((-9, -8, -7), (11, 12, 13)))
        b = sdf.box([20, 10, 5])
        self.assertAlmostEqual(b(10, 5, 2.5), -2.5)
        self.assertAlmostEqual(b(25, 5, 2.5), 5)
        self.assertAlmostEqual(b(-3, -4, 2.5), 5)                   # corner: true euclidean distance
        self.assertEqual(sdf.box([2, 2, 2], center=True).bounds, ((-1, -1, -1), (1, 1, 1)))
        c = sdf.capsule([0, 0, 0], [10, 0, 0], 2)
        self.assertAlmostEqual(c(5, 0, 0), -2)
        self.assertAlmostEqual(c(14, 0, 0), 2)
        t = sdf.torus(10, 3)
        self.assertAlmostEqual(t(10, 0, 0), -3)
        self.assertAlmostEqual(t(0, 0, 0), 7)
        f2, lo, hi = sdf.polygon2d([[0, 0], [10, 0], [10, 10], [0, 10]])
        self.assertAlmostEqual(f2(5, 5), -5)
        self.assertAlmostEqual(f2(12, 5), 2)
        self.assertAlmostEqual(f2(13, 14), 5)
        self.assertEqual((lo, hi), ((0, 0), (10, 10)))

    def test_meshed_volumes(self):
        self.assertSolid(sdf.to_manifold(sdf.sphere(10), 0.5), bbox=[20, 20, 20], volume=4 / 3 * math.pi * 1000, rel=0.005)
        self.assertSolid(sdf.to_manifold(sdf.box([20, 10, 5]), 0.5), bbox=[20, 10, 5], volume=1000, rel=0.01)
        self.assertSolid(sdf.to_manifold(sdf.capsule([0, 0, 3], [30, 0, 3], 3), 0.5), bbox=[36, 6, 6],
                         volume=math.pi * 9 * 30 + 4 / 3 * math.pi * 27)
        self.assertSolid(sdf.to_manifold(sdf.cylinder(5, 12), 0.5), bbox=[10, 10, 12], volume=math.pi * 25 * 12)
        self.assertSolid(sdf.to_manifold(sdf.cylinder(5, 12, axis="x"), 0.5), bbox=[12, 10, 10], volume=math.pi * 25 * 12)
        self.assertSolid(sdf.to_manifold(sdf.torus(10, 3), 0.5), bbox=[26, 26, 6], volume=2 * math.pi ** 2 * 10 * 9)
        self.assertSolid(sdf.to_manifold(sdf.rounded_box([20, 10, 8], 2), 0.5), bbox=[20, 10, 8])
        self.assertSolid(sdf.to_manifold(sdf.extrude([[0, 0], [30, 0], [15, 20]], 5), 0.5), bbox=[30, 20, 5], volume=1500)
        self.assertSolid(sdf.to_manifold(sdf.revolve([[0, 0], [8, 0], [6, 10], [0, 10]]), 0.5), bbox=[16, 16, 10],
                         volume=math.pi * 10 / 3 * (64 + 48 + 36))

    def test_transforms(self):
        m = self.assertSolid(sdf.to_manifold(sdf.box([20, 10, 5]).translate([5, 5, 5]), 0.5), bbox=[20, 10, 5])
        self.assertAlmostEqual(m["bbox_min_mm"][2], 5, delta=0.3)
        self.assertSolid(sdf.to_manifold(sdf.box([20, 10, 5]).rotate(90), 0.5), bbox=[10, 20, 5], volume=1000, rel=0.02)
        self.assertSolid(sdf.to_manifold(sdf.box([20, 10, 5]).rotate(90, "x"), 0.5), bbox=[20, 5, 10], volume=1000, rel=0.02)
        self.assertSolid(sdf.to_manifold(sdf.sphere(5).scale(2), 0.5), bbox=[20, 20, 20], volume=4 / 3 * math.pi * 1000, rel=0.01)
        m = self.assertSolid(sdf.to_manifold(sdf.box([20, 10, 5]).mirror("x"), 0.5), bbox=[20, 10, 5])
        self.assertAlmostEqual(m["bbox_min_mm"][0], -20, delta=0.3)
        self.assertSolid(sdf.to_manifold(sdf.sphere(5).offset(1), 0.5), volume=4 / 3 * math.pi * 216, rel=0.01)


class Combinations(SdfCase):
    def test_boolean_operators(self):
        a, b = sdf.box([20, 20, 10]), sdf.cylinder(3, 20, [10, 10, -5])
        self.assertSolid(sdf.to_manifold(a - b, 0.5), volume=4000 - math.pi * 9 * 10, rel=0.02)
        self.assertSolid(sdf.to_manifold(a & sdf.sphere(10, [10, 10, 0]), 0.5), volume=2 / 3 * math.pi * 1000, rel=0.02)
        self.assertSolid(sdf.to_manifold(sdf.sphere(6, [0, 0, 6]) | sdf.sphere(6, [20, 0, 6]), 0.5), shells=2)
        with self.assertRaises(ValueError):
            sdf.box([10, 10, 10]) & sdf.box([10, 10, 10]).translate([50, 0, 0])

    def test_smooth_union_adds_a_fillet(self):
        plain = sdf.to_manifold(sdf.sphere(6, [0, 0, 6]) | sdf.box([30, 10, 4]), 0.5)
        blended = sdf.to_manifold(sdf.smooth_union(sdf.sphere(6, [0, 0, 6]), sdf.box([30, 10, 4]), 3), 0.5)
        self.assertSolid(blended)
        self.assertGreater(blended.volume(), plain.volume())        # material added in the crease
        self.assertLess(blended.volume(), plain.volume() * 1.15)
        cut = sdf.to_manifold(sdf.smooth_subtract(sdf.box([20, 20, 10]), sdf.cylinder(3, 20, [10, 10, -5]), 2), 0.5)
        self.assertSolid(cut)
        self.assertLess(cut.volume(), 4000 - math.pi * 9 * 10)      # rounded edge removes a little more
        self.assertSolid(sdf.to_manifold(sdf.smooth_intersect(sdf.box([20, 20, 10]), sdf.sphere(10, [10, 10, 0]), 2), 0.5))

    def test_shell_keeps_the_cavity(self):
        rep = {}
        hollow = sdf.to_manifold(sdf.sphere(10).shell(2), 0.5, report=rep)
        m = self.assertSolid(hollow, shells=2, volume=4 / 3 * math.pi * (1000 - 512), rel=0.01)   # outer + inner surface
        self.assertEqual(rep["dropped_bodies"], [])
        self.assertEqual(m["bbox_mm"], [20.0, 20.0, 20.0])


class Meshing(SdfCase):
    def test_crumbs_are_dropped_but_bodies_kept(self):
        rep = {}
        man = sdf.to_manifold(sdf.sphere(10) | sdf.sphere(0.3, [15, 0, 0]), 0.5, report=rep)
        self.assertEqual(len(rep["dropped_bodies"]), 1)
        self.assertSolid(man, shells=1)
        rep = {}
        man = sdf.to_manifold(sdf.sphere(10) | sdf.sphere(4, [20, 0, 0]), 0.5, report=rep)
        self.assertEqual(rep["dropped_bodies"], [])
        self.assertSolid(man, shells=2)
        kept = sdf.to_manifold(sdf.sphere(10) | sdf.sphere(0.3, [15, 0, 0]), 0.5, drop_crumbs=False)
        self.assertEqual(len(kept.decompose()), 2)

    def test_report_bounds_and_warnings(self):
        rep = {}
        sdf.to_manifold(sdf.sphere(10), 0.5, report=rep)
        self.assertEqual(rep["bounds"], [[-11, -11, -11], [11, 11, 11]])    # own box plus 2 x edge
        self.assertGreater(rep["triangles"], 1000)
        self.assertGreaterEqual(rep["seconds"], 0)
        est = sdf.grid_estimate(sdf.sphere(10), 0.5)
        self.assertEqual(est["evaluations"], 2 * 45 ** 3)
        err = io.StringIO()
        with redirect_stderr(err):
            sdf.to_manifold(sdf.sphere(10), 0.5, warn=False)
        self.assertEqual(err.getvalue(), "")
        with self.assertRaises(ValueError):
            sdf.to_manifold(sdf.sphere(10), 0.02)                              # too many evaluations
        with self.assertRaises(ValueError):
            sdf.to_manifold(sdf.sphere(10), 0.5, bounds=([20, 20, 20], [30, 30, 30]))   # nothing inside
        with self.assertRaises(ValueError):
            sdf.to_manifold(sdf.SDF(lambda x, y, z: 10 - math.sqrt(x * x + y * y + z * z),
                                    (-10, -10, -10), (10, 10, 10)), 0.5)       # wrong sign convention: empty

    def test_leaf_handle_case_is_watertight(self):
        """The door-handle trial: a domed height field over a leaf outline, a pocket with
        vertical walls cut into it, and a round handle blended on. Built with booleans this
        failed M3 with needle triangles; as one SDF it meshes clean."""
        n = 24
        leaf = [[30 + 30 * math.cos(t), 12 * math.sin(t) * (1 + 0.3 * math.cos(t))]
                for t in [2 * math.pi * i / n for i in range(n)]]
        top = lambda x, y: 2.0 + 6.0 * max(0.0, 1 - ((x - 30) / 30) ** 2 - (y / 12) ** 2)   # noqa: E731
        dome = sdf.height_field(leaf, top)
        pocket = sdf.box([20, 8, 10]).translate([20, -4, 4])
        handle = sdf.capsule([5, 0, 3], [-20, 0, 3], 3)
        part = sdf.smooth_union(dome - pocket, handle, 2.5)
        rep = {}
        man = sdf.to_manifold(part, 1.0, floor=0.0, report=rep)                   # flat bed after the blend
        m = self.assertSolid(man)
        self.assertAlmostEqual(m["bbox_min_mm"][2], 0.0, delta=1e-6)
        self.assertAlmostEqual(m["bbox_mm"][0], 83, delta=1.0)
        self.assertGreater(m["bed_contact_mm2"], 100)
        self.assertLess(m["overhang_pct"], 15)                               # the capsule's underside only
        self.assertEqual(rep["dropped_bodies"], [])
        fine = sdf.to_manifold(part, 0.5, floor=0.0, warn=False)                   # the trial's resolution
        self.assertSolid(fine)
        with self.assertRaises(ValueError):
            sdf.to_manifold(part, 1.0, floor=50.0)


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class BuildIntegration(unittest.TestCase):
    def test_generator_imports_sdf_and_hash_covers_it(self):
        import build
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "gen.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write("import sdf\n"
                        "def build(p):\n"
                        "    return {'blob': sdf.to_manifold(sdf.sphere(p['r'], [0, 0, p['r']]), 0.5, warn=False)}\n")
            prm = os.path.join(d, "params.json")
            with open(prm, "w", encoding="utf-8") as f:
                json.dump({"_parts": {"blob": {"expect": [20, 20, 20]}}, "r": 10}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build.main(["run", src, "--params", prm, "--out", os.path.join(d, "out"), "--no-wall-check"])
            out = json.loads(buf.getvalue())
            self.assertEqual(code, 0, out.get("errors"))
            names = [os.path.basename(s) for s in out["sources"]]
            self.assertIn("sdf.py", names)
            self.assertIn("parts.py", names)                                  # sdf imports parts
            checks = out["parts"][0]["validate"]["files"][0]["checks"]
            self.assertEqual(checks["D1"]["state"], "PASS")
            self.assertEqual(checks["M1"]["state"], "PASS")
            self.assertEqual(checks["M3"]["state"], "PASS")
            self.assertEqual(checks["R3"]["state"], "PASS")


if __name__ == "__main__":
    unittest.main()
