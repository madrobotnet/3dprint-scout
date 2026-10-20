"""Tests for scripts/parts.py (needs manifold3d; text needs matplotlib or fontTools)."""
import json
import math
import os
import sys
import tempfile
import unittest
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import validate  # noqa: E402

HAS_M3D = find_spec("manifold3d") is not None
if HAS_M3D:
    import manifold3d as m3d  # noqa: E402
    import parts  # noqa: E402

TOPOLOGY = ("open_edges", "nonmanifold_edges", "flipped_edges", "degenerate_faces", "duplicate_faces")


def metrics(man):
    """validate.py's own analysis of the exported triangles (what build.py would write)."""
    V, F = parts.mesh_arrays(man)
    tris = [(tuple(V[a]), tuple(V[b]), tuple(V[c])) for a, b, c in F]
    return validate.analyse(tris)


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class PartCase(unittest.TestCase):
    def assertSolid(self, man, shells=1, bbox=None, volume=None, rel=0.02):
        """Hard checks M1-M5 and D3 as validate.py decides them, plus size and volume."""
        self.assertEqual(man.status(), m3d.Error.NoError)
        m = metrics(man)
        bad = {k: m[k] for k in TOPOLOGY if m[k]}
        self.assertEqual(bad, {}, f"topology: {bad}")
        self.assertEqual(m["shells"], shells, "number of bodies")
        self.assertGreater(m["volume_mm3"], 0)
        if bbox is not None:
            for got, want in zip(m["bbox_mm"], bbox):
                self.assertAlmostEqual(got, want, delta=0.05)
        if volume is not None:
            self.assertAlmostEqual(m["volume_mm3"], volume, delta=abs(volume) * rel)
        return m


class Boxes(PartCase):
    def test_rounded_box_vertical(self):
        m = self.assertSolid(parts.rounded_box([60, 40, 25], 3), bbox=[60, 40, 25])
        corner = (4 - math.pi) * 9                                   # area lost at four r=3 corners
        self.assertAlmostEqual(m["volume_mm3"], (60 * 40 - corner) * 25, delta=5)
        self.assertGreater(m["bed_contact_mm2"], 2300)                 # flat bottom (P1)

    def test_rounded_box_top_keeps_a_sharp_bed_edge(self):
        m = self.assertSolid(parts.rounded_box([60, 40, 25], 3, "top"), bbox=[60, 40, 25])
        self.assertGreater(m["bed_contact_mm2"], 2300)                 # full footprint on the bed
        self.assertLess(m["volume_mm3"], 60 * 40 * 25)

    def test_rounded_box_all(self):
        self.assertSolid(parts.rounded_box([60, 40, 25], 3, "all"), bbox=[60, 40, 25])
        with self.assertRaises(ValueError):
            parts.rounded_box([10, 10, 4], 3, "all")

    def test_chamfered_box_variants(self):
        for edges in ("bottom", "top", "vertical", "all"):
            self.assertSolid(parts.chamfered_box([60, 40, 25], 1.0, edges), bbox=[60, 40, 25])
        m = metrics(parts.chamfered_box([60, 40, 25], 0.5, "bottom"))
        self.assertAlmostEqual(m["bed_contact_mm2"], 59 * 39, delta=1)  # inset by the chamfer
        self.assertEqual(m["overhang_pct"], 0.0)                         # 45 deg is not an overhang

    def test_bottom_chamfer_on_round_concave_and_hollow_parts(self):
        cyl = m3d.Manifold.cylinder(20, 10, 10, 64)
        m = self.assertSolid(parts.bottom_chamfer(cyl, 0.5), bbox=[20, 20, 20])
        self.assertLess(m["volume_mm3"], cyl.volume())
        self.assertAlmostEqual(m["bed_contact_mm2"], math.pi * 9.5 ** 2, delta=3)
        L = m3d.Manifold.cube([30, 30, 10]) - m3d.Manifold.cube([15, 15, 12]).translate([15, 15, -1])
        self.assertSolid(parts.bottom_chamfer(L, 0.5), bbox=[30, 30, 10])
        tube = cyl - m3d.Manifold.cylinder(22, 6, 6, 64).translate([0, 0, -1])
        m = self.assertSolid(parts.bottom_chamfer(tube, 0.5), bbox=[20, 20, 20])
        self.assertAlmostEqual(m["bed_contact_mm2"], math.pi * (9.5 ** 2 - 6.5 ** 2), delta=3)   # both edges
        lifted = m3d.Manifold.cube([20, 20, 20]).translate([5, 5, 7])
        self.assertSolid(parts.bottom_chamfer(lifted, 0.5), bbox=[20, 20, 20])
        with self.assertRaises(ValueError):
            parts.bottom_chamfer(m3d.Manifold.cube([20, 20, 0.3]), 0.5)


class Clean(PartCase):
    def test_flush_union_slivers_are_repaired(self):
        """A tab unioned flush with a box face leaves collinear T-junction triangles that fail
        M1/M3 once the STL is welded; clean() splits the neighbours and drops them."""
        plate = m3d.Manifold.cube([70, 45, 3]) + m3d.Manifold.cube([65.6, 40.6, 5.1]).translate([2.2, 2.2, 2.9])
        hook = parts.snap_hook(length=16, thickness=1.6, width=6, undercut=0.5)
        hook = hook.mirror([0, 1, 0]).rotate([0, -90, 0]).translate([38, 3.8, 3])   # outer face flush with the plug
        raw = plate + hook
        m = metrics(raw)
        self.assertGreater(m["degenerate_faces"] + m["open_edges"], 0)   # the problem exists
        fixed = parts.clean(raw)
        self.assertSolid(fixed, bbox=[70, 45, 19], volume=raw.volume(), rel=1e-6)
        cube = m3d.Manifold.cube([5, 5, 5])
        self.assertEqual(parts.clean(cube).num_tri(), cube.num_tri())       # nothing to fix: unchanged


class Holes(PartCase):
    def test_screw_hole_kinds_cut_cleanly(self):
        box = m3d.Manifold.cube([30, 30, 10])
        for kind in ("clearance", "tap", "insert", "countersunk", "counterbore"):
            m = self.assertSolid(box - parts.screw_hole("M3", 8, kind).translate([15, 15, 10]), bbox=[30, 30, 10])
            self.assertLess(m["volume_mm3"], 9000)
        with self.assertRaises(ValueError):
            parts.screw_hole("M7", 8)

    def test_hole_sizes_follow_the_tables(self):
        box = m3d.Manifold.cube([30, 30, 10])
        for size, d in (("M3", 3.4), ("M4", 4.5), ("M5", 5.5)):            # ISO 273 medium
            cut = box - parts.screw_hole(size, 12, "clearance").translate([15, 15, 10])
            self.assertAlmostEqual(box.volume() - cut.volume(), math.pi * (d / 2) ** 2 * 10, delta=8)
        cut = box - parts.screw_hole("M3", 12, "insert", insert_d=4.2).translate([15, 15, 10])
        self.assertAlmostEqual(box.volume() - cut.volume(), math.pi * 2.1 ** 2 * 10, delta=8)
        cut = box - parts.screw_hole("M3", 12, "clearance", comp=0.1).translate([15, 15, 10])   # F1: model-side
        self.assertAlmostEqual(box.volume() - cut.volume(), math.pi * 1.8 ** 2 * 10, delta=8)

    def test_measured_head_overrides_the_table(self):
        """S2-F05: a wood screw's caliper head (8.0 mm) replaces ISO 10642's 8.96 mm dk; the
        radial head clearance and comp still apply, as for the table value."""
        box = m3d.Manifold.cube([30, 30, 10])
        iso = parts.screw_hole("M4", 8, "countersunk")
        wood = parts.screw_hole("M4", 8, "countersunk", head_d=8.0)
        self.assertAlmostEqual(wood.bounding_box()[3] - wood.bounding_box()[0], 8.0 + 2 * 0.3 + 2 * 0.1, delta=0.05)
        self.assertLess(wood.volume(), iso.volume())
        self.assertSolid(box - wood.translate([15, 15, 10]), bbox=[30, 30, 10])
        bore = parts.screw_hole("M4", 8, "counterbore", head_d=9.0, head_h=3.0, comp=0.1)
        self.assertAlmostEqual(bore.bounding_box()[3] - bore.bounding_box()[0], 9.0 + 2 * 0.3 + 2 * 0.1, delta=0.05)
        self.assertAlmostEqual(bore.bounding_box()[5], 0.1, delta=1e-6)       # the recess overshoots the mouth
        cut = box - bore.translate([15, 15, 10])
        recess = math.pi * (9.6 / 2) ** 2 * 3.3                               # head_h + head_clearance deep
        shank = math.pi * (4.5 / 2 + 0.1) ** 2 * (8 - 3.3)
        self.assertAlmostEqual(box.volume() - cut.volume(), recess + shank, delta=25)
        for kw in (dict(head_d=8.0), dict(kind="insert", head_d=8.0), dict(kind="countersunk", head_h=2.0),
                   dict(kind="counterbore", head_d=4.0), dict(kind="counterbore", head_h=0)):
            with self.assertRaises(ValueError, msg=kw):
                parts.screw_hole("M4", 8, **kw)

    def test_through_hole_overshoots_both_faces(self):
        box = m3d.Manifold.cube([30, 30, 10])
        m = self.assertSolid(box - parts.screw_hole("M4", 10).translate([15, 15, 10]), bbox=[30, 30, 10])
        self.assertEqual((box - parts.screw_hole("M4", 10).translate([15, 15, 10])).genus(), 1)
        self.assertAlmostEqual(m["volume_mm3"], 9000 - math.pi * 2.25 ** 2 * 10, delta=8)

    def test_teardrop_hole_points_up(self):
        for axis, bbox in (("x", [10.2, 6, 3 + 3 * math.sqrt(2)]), ("y", [6, 10.2, 3 + 3 * math.sqrt(2)])):
            cut = parts.teardrop_hole(6, 10, axis)
            m = self.assertSolid(cut, bbox=bbox)
            self.assertAlmostEqual(m["bbox_min_mm"][2], -3, delta=0.01)        # round side down, point up
        wall = m3d.Manifold.cube([10, 30, 30]) - parts.teardrop_hole(6, 10, "x").translate([5, 15, 15])
        m = self.assertSolid(wall, bbox=[10, 30, 30])
        self.assertEqual(wall.genus(), 1)
        self.assertEqual(m["overhang_pct"], 0.0)                              # the roof is 45 deg


class Bosses(PartCase):
    def test_standoff(self):
        m = self.assertSolid(parts.standoff(10, "M3", "insert", foot=1.0), bbox=[10, 10, 10])
        self.assertEqual(m["overhang_pct"], 0.0)                              # the flare is 45 deg
        self.assertSolid(parts.standoff(12, "M3", "tap"), bbox=[6.5, 6.5, 12])
        with self.assertRaises(ValueError):
            parts.standoff(5, "M3", "insert")                                 # no floor left


class SnapFits(PartCase):
    def test_strain_formula_and_limits(self):
        self.assertAlmostEqual(parts.snap_fit_strain(16, 1.6, 0.8), 1.5 * 1.6 * 0.8 / 256)
        ok = parts.snap_fit_check(16, 1.6, 0.8, "PLA")
        self.assertTrue(ok["ok"])
        bad = parts.snap_fit_check(12, 1.6, 1.2, "PLA")
        self.assertFalse(bad["ok"])
        self.assertAlmostEqual(parts.snap_fit_check(16, 1.6, 0.8, "pla", repeated=True)["limit"], 0.006)
        with self.assertRaises(ValueError):
            parts.snap_fit_check(10, 1, 1, "wood")

    def test_hook_and_window(self):
        hook = parts.snap_hook()
        m = self.assertSolid(hook, bbox=[16.5, 2.4, 6])
        self.assertAlmostEqual(m["bbox_min_mm"][0], -0.5)                     # root overlap into the wall
        with self.assertRaises(ValueError):
            parts.snap_hook(length=8, thickness=2.0, undercut=1.5)            # over the strain limit
        with self.assertRaises(ValueError):
            parts.snap_hook(thickness=1.0)                                    # below 1.2 mm
        wall = m3d.Manifold.cube([24, 2, 10]).translate([-2, 1.6 + 0.2, -2])
        cut = wall - parts.snap_window()
        self.assertSolid(cut, bbox=[24, 2, 10])
        self.assertEqual(cut.genus(), 1)                                      # one window through the wall
        self.assertEqual((hook ^ cut).volume(), 0.0)                          # hook and wall never overlap


class Hinges(PartCase):
    def test_duty_is_keyword_only(self):
        """A duty passed where `segments` sits must fail clearly, never build a latch hinge."""
        import inspect
        self.assertEqual(inspect.signature(parts.hinge).parameters["duty"].kind, inspect.Parameter.KEYWORD_ONLY)
        with self.assertRaises(TypeError) as cm:
            parts.hinge(16, 7.4, 2.4, 10, 1.6, 5, 0.3, "lid")
        self.assertIn("keyword-only", str(cm.exception))
        h = parts.hinge(16, 7.4, 2.4, 10, 1.6, 5, 0.3, duty="lid")
        self.assertEqual(set(h), {"leaf_a", "leaf_b"})

    def test_print_in_place_hinge(self):
        h = parts.hinge()
        a = self.assertSolid(h["leaf_a"], bbox=[30, 22.1, 9.8])
        b = self.assertSolid(h["leaf_b"], bbox=[30, 22.1, 9.8])
        self.assertSolid(h["leaf_a"] + h["leaf_b"], shells=2, bbox=[30, 34.4, 9.8])
        # The wall above the teardrop's point: slice leaf B at the axis plane and look at the
        # lowest hole-roof point against the knuckle top (design.md: 2.2 mm all round).
        import numpy as np
        V, F = parts.mesh_arrays(h["leaf_b"])
        knuckle = V[(np.abs(V[:, 1]) < 4.9 + 1e-6) & (V[:, 0] > 10.0) & (V[:, 0] < 20.0)]     # the middle knuckle (B)
        roof = knuckle[(np.abs(knuckle[:, 1]) < 1e-6) & (knuckle[:, 2] > 4.9) & (knuckle[:, 2] < 9.0)]
        self.assertTrue(len(roof))
        self.assertGreaterEqual(9.8 - roof[:, 2].max(), 2.2 - 1e-6)
        self.assertEqual((h["leaf_a"] ^ h["leaf_b"]).volume(), 0.0)
        self.assertAlmostEqual(h["leaf_a"].min_gap(h["leaf_b"], 1.0), 0.3, delta=0.01)   # tolerances.md
        self.assertEqual(a["bbox_min_mm"][2], 0.0)                                      # both on the bed
        self.assertEqual(b["bbox_min_mm"][2], 0.0)

    def test_mechanism_minimums(self):
        """design.md, Mechanisms that carry load: a pin wall under 2.2 mm, a leaf under 2.5 mm, a
        knuckle under 4 mm or a pin under 3.2 mm is refused with the source named."""
        cases = {"wall": dict(knuckle_d=8.4, pin_d=3.2),            # 4.2 - 1.9 x sqrt(2) = 1.51 mm above the point
                 "pin": dict(pin_d=2.6, knuckle_d=9.8),
                 "leaf": dict(leaf_t=2.0),
                 "knuckles": dict(length=12.0, knuckles=3)}         # (12 - 0.6) / 3 = 3.8 mm
        for name, kw in cases.items():
            with self.assertRaisesRegex(ValueError, "design.md", msg=name):
                parts.hinge(**kw)
        self.assertEqual(parts.MECHANISM, {"pin_d": 3.2, "pin_wall": 2.2, "member": 2.5, "knuckle_len": 4.0})
        # The failed field latch's numbers: a 2.6 mm pin in a 6.0 mm knuckle is refused outright.
        with self.assertRaisesRegex(ValueError, "minimum"):
            parts.hinge(knuckle_d=6.0, pin_d=2.6)
        # A hinge that carries nothing may go down to what still prints.
        h = parts.hinge(length=16, knuckle_d=6.2, pin_d=2.0, leaf_t=1.6, knuckles=3, decorative=True)
        self.assertSolid(h["leaf_a"] + h["leaf_b"], shells=2)
        with self.assertRaisesRegex(ValueError, "tolerances.md"):
            parts.hinge(knuckle_d=5.2, pin_d=2.0, decorative=True)       # 0.97 mm above the point: does not print

    def test_hinge_duties(self):
        """design.md, Mechanisms that carry load, by duty: the lid duty accepts the field test's 2.4 mm pin in
        7.4 mm knuckles (1.58 mm above the point; strength.py hinge sizes it), the default (latch) refuses it,
        decorative=True is the old spelling of duty='decorative', and the floors have one copy in strength.py."""
        import strength
        from types import MappingProxyType
        # One copy of the numbers, but read-only views of copies here: nothing in parts can change strength.DUTIES.
        self.assertEqual(parts.MECHANISM, strength.DUTIES["latch"]["floors"])
        self.assertEqual(parts.DECORATIVE, strength.DUTIES["decorative"]["floors"])
        self.assertIsNot(parts.MECHANISM, strength.DUTIES["latch"]["floors"])
        self.assertIsInstance(parts.MECHANISM, MappingProxyType)
        self.assertIsInstance(parts.DECORATIVE, MappingProxyType)
        with self.assertRaises(TypeError):
            parts.MECHANISM["pin_d"] = 1.0
        self.assertEqual(parts.DECORATIVE, {"pin_d": 2.0, "pin_wall": 1.2, "member": 1.2, "knuckle_len": 2.0})
        self.assertEqual(parts.DUTIES["lid"]["min_knuckles"], 3)
        sd = dict(length=36, knuckle_d=7.4, pin_d=2.4, leaf_t=1.6, knuckles=5)
        h = parts.hinge(duty="lid", **sd)
        self.assertEqual(set(h), {"leaf_a", "leaf_b"})
        self.assertSolid(h["leaf_a"] + h["leaf_b"], shells=2, bbox=[36, 2 * (3.7 + 0.3 + 12), 7.4])
        self.assertEqual((h["leaf_a"] ^ h["leaf_b"]).volume(), 0.0)
        self.assertAlmostEqual(h["leaf_a"].min_gap(h["leaf_b"], 1.0), 0.3, delta=0.01)
        with self.assertRaisesRegex(ValueError, "duty latch.*field minimums"):
            parts.hinge(**sd)                                                  # the default stays the latch values
        with self.assertRaisesRegex(ValueError, "duty latch"):
            parts.hinge(duty="latch", **sd)
        with self.assertRaisesRegex(ValueError, "strength.py hinge.*coupon"):
            parts.hinge(duty="lid", **dict(sd, leaf_t=1.0))                    # under what prints, the lid source named
        with self.assertRaisesRegex(ValueError, "duty lid"):
            parts.hinge(duty="lid", **dict(sd, knuckle_d=5.2, pin_d=2.0))
        # A lid hinge needs 3 or more knuckles (odd recommended, not enforced); latch and decorative keep 2.
        with self.assertRaisesRegex(ValueError, "a lid hinge needs at least 3 knuckles"):
            parts.hinge(duty="lid", **dict(sd, knuckles=2))
        four = parts.hinge(duty="lid", **dict(sd, knuckles=4))
        self.assertSolid(four["leaf_a"] + four["leaf_b"], shells=2)
        self.assertEqual(set(parts.hinge(duty="decorative", **dict(sd, knuckles=2))), {"leaf_a", "leaf_b"})
        self.assertEqual(set(parts.hinge(knuckles=2, length=20)), {"leaf_a", "leaf_b"})
        # decorative=True is duty="decorative"; the two together are fine, another duty with it is not.
        a = parts.hinge(decorative=True, **sd)
        b = parts.hinge(duty="decorative", **sd)
        c = parts.hinge(decorative=True, duty="decorative", **sd)
        self.assertAlmostEqual(a["leaf_b"].volume(), b["leaf_b"].volume(), places=6)
        self.assertAlmostEqual(a["leaf_b"].volume(), c["leaf_b"].volume(), places=6)
        with self.assertRaisesRegex(ValueError, "decorative=True means duty='decorative'"):
            parts.hinge(decorative=True, duty="lid", **sd)
        with self.assertRaisesRegex(ValueError, "decorative=True means duty='decorative'"):
            parts.hinge(decorative=True, duty="latch")
        with self.assertRaisesRegex(ValueError, "unknown hinge duty 'lever'"):
            parts.hinge(duty="lever")
        with self.assertRaisesRegex(ValueError, "unknown hinge duty"):
            parts.hinge(duty="", **sd)
        # The same numbers strength.py sees: wall above the point and knuckle length.
        self.assertAlmostEqual(strength.hinge_wall(7.4, 2.4, 0.3, "teardrop"), 1.5787, places=4)
        self.assertAlmostEqual((36 - 4 * 0.3) / 5, 6.96)

    def test_strength_is_loaded_by_path_not_by_name(self):
        """A project's own strength.py earlier on sys.path (build.py puts the generator's folder first) must not
        shadow the skill's: parts loads its sibling by file path under a private module name and leaves sys.path
        alone."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "strength.py"), "w", encoding="utf-8") as f:
                f.write("DUTIES = {'latch': {'floors': {'pin_d': 0.1}}}\nDECOY = True\n")
            code = (
                "import sys, json\n"
                f"sys.path.insert(0, {d!r})\n"
                f"sys.path.insert(1, {os.path.join(HERE, '..', 'scripts')!r})\n"
                "before = list(sys.path)\n"
                "import strength, parts\n"
                "print(json.dumps({'decoy_seen_by_name': getattr(strength, 'DECOY', False),"
                " 'parts_pin_d': parts.MECHANISM['pin_d'], 'private': '_3dps_strength' in sys.modules,"
                " 'private_file': sys.modules['_3dps_strength'].__file__, 'sys_path_unchanged': sys.path == before}))\n")
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        got = json.loads(out.stdout)
        self.assertTrue(got["decoy_seen_by_name"])                               # `import strength` finds the decoy...
        self.assertEqual(got["parts_pin_d"], 3.2)                                # ...parts does not
        self.assertTrue(got["private"])
        self.assertEqual(os.path.realpath(got["private_file"]), os.path.realpath(os.path.join(HERE, "..", "scripts", "strength.py")))
        self.assertTrue(got["sys_path_unchanged"])


class Text(PartCase):
    def test_backends_or_clear_error(self):
        backends = parts.text_backends()
        if backends:
            return
        with self.assertRaises(ImportError) as cm:
            parts.text("A", 6, 1)
        self.assertIn("matplotlib", str(cm.exception))

    def test_no_backend_message(self):
        orig = parts.text_backends
        parts.text_backends = lambda: []
        try:
            with self.assertRaises(ImportError) as cm:
                parts.text("A", 6, 1)
        finally:
            parts.text_backends = orig
        self.assertIn("pip install matplotlib", str(cm.exception))

    @unittest.skipUnless(HAS_M3D and find_spec("matplotlib") is not None, "matplotlib not installed")
    def test_text_matplotlib(self):
        t = parts.text("AB8", 6, 1)
        m = self.assertSolid(t, shells=3)                                     # three letters, three bodies
        self.assertAlmostEqual(m["bbox_mm"][2], 1.0)
        self.assertAlmostEqual(m["bbox_min_mm"][0], 0.0, delta=1e-3)         # left aligned
        self.assertAlmostEqual(m["bbox_min_mm"][1] + m["bbox_mm"][1], 6.0, delta=0.4)   # top of the caps at 6 mm
        c = parts.text("AB8", 6, 1, align="center")
        mc = metrics(c)
        self.assertAlmostEqual(mc["bbox_min_mm"][0] + mc["bbox_mm"][0] / 2, 0.0, delta=1e-3)
        plate = m3d.Manifold.cube([30, 12, 3])
        self.assertSolid(plate + parts.text("OK", 6, 1).translate([3, 3, 3]), bbox=[30, 12, 4])    # embossed
        self.assertSolid(plate - parts.text("OK", 6, 1).translate([3, 3, 2]), bbox=[30, 12, 3])    # engraved
        with self.assertRaises(ValueError):
            parts.text("   ", 6, 1)

    @unittest.skipUnless(HAS_M3D and find_spec("fontTools") is not None, "fontTools not installed")
    def test_text_fonttools(self):
        font = parts.find_font()
        if not font:
            self.skipTest("no font file found on this machine")
        outlines = parts._outlines_fonttools("B8", font, "bold")
        self.assertGreaterEqual(len(outlines), 4)                            # B has two holes, 8 has two
        cs = m3d.CrossSection([[list(p) for p in c] for c in outlines], m3d.FillRule.NonZero)
        self.assertSolid(m3d.Manifold.extrude(cs, 1), shells=2)

    @unittest.skipUnless(HAS_M3D and (find_spec("fontTools") or find_spec("matplotlib")), "no outline backend")
    def test_characters_the_font_cannot_draw_are_refused(self):
        """S5-F1: Hangul in a Latin font must raise, naming the character and its code point,
        not print placeholder glyphs; find_font(text=) picks a font that covers the text."""
        import glob
        latin = next(iter(glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)), None)
        if latin:
            self.assertEqual(parts.font_missing(latin, "고양이 H"), [("고", "U+ACE0"), ("양", "U+C591"), ("이", "U+C774")])
            self.assertEqual(parts.font_missing(latin, "ABC 8"), [])
            self.assertEqual(parts.find_font(text="ABC"), parts.find_font())  # Latin text: the Latin font, as before
            with self.assertRaises(ValueError) as cm:
                parts.text("고양이", 8, 1, font=latin)
            self.assertIn("'고' (U+ACE0)", str(cm.exception))
            self.assertIn("Noto Sans CJK", str(cm.exception))
            self.assertIn("DejaVuSans-Bold.ttf", str(cm.exception))
            for backend in parts.text_backends():
                fn = parts._outlines_matplotlib if backend == "matplotlib" else parts._outlines_fonttools
                with self.assertRaises(ValueError) as cm:
                    fn("고양이", latin, "bold")
                self.assertIn("U+ACE0", str(cm.exception))
        if find_spec("matplotlib") is not None:
            with self.assertRaises(ValueError) as cm:                          # an unknown family: matplotlib's default
                parts.text("고양이", 8, 1, font="No Such Font Family")
            self.assertIn("U+ACE0", str(cm.exception))
            self.assertIn("not installed", str(cm.exception))
        cjk = parts.find_font(text="고양이")
        if not cjk:
            self.assertIsNone(parts.find_font(text="고양이"))                  # no covering font: None, not a Latin one
            self.skipTest("no CJK font on this machine")
        self.assertRegex(os.path.basename(cjk), r"(?i)cjk|nanum|malgun|gothic")
        self.assertEqual(parts.font_missing(cjk, "고양이"), [])
        t = parts.text("고양이", 8, 1)                                         # no font given: find_font(text=) picks one
        m = metrics(t)
        self.assertEqual(m["open_edges"], 0)
        self.assertGreaterEqual(m["shells"], 3)                                 # jamo pieces, not one body per syllable
        self.assertAlmostEqual(m["bbox_mm"][1], 8.0, delta=2.5)                 # cap height 8 mm; Hangul runs taller
        self.assertAlmostEqual(m["bbox_mm"][2], 1.0)


class Threads(PartCase):
    def test_external_thread_is_right_handed_and_sized(self):
        t = parts.thread(6, length=4, lead_in=False)
        m = self.assertSolid(t, bbox=[6, 6, 4])
        minor = 6 - 2 * parts.THREAD_DEPTH * 1.0                             # 4.917 mm, as ISO 68-1 gives
        self.assertGreater(m["volume_mm3"], math.pi * (minor / 2) ** 2 * 4)
        self.assertLess(m["volume_mm3"], math.pi * 3 ** 2 * 4)

        def crest_angle(z):
            pts = max(t.slice(z).to_polygons(), key=len)
            best = max(pts, key=lambda p: math.hypot(p[0], p[1]))
            return math.degrees(math.atan2(best[1], best[0])) % 360
        turn = (crest_angle(1.5) - crest_angle(1.0)) % 360                    # half a pitch up
        self.assertAlmostEqual(turn, 180, delta=25)                           # counter-clockwise going up
        self.assertSolid(parts.thread(6, length=4), bbox=[6, 6, 4])           # with lead-in chamfers

    def test_internal_cutter_leaves_clearance(self):
        bolt = parts.thread(6, length=8, lead_in=False)
        nut = m3d.Manifold.cylinder(5, 6, 6, 64) - parts.thread(6, length=5, internal=True, lead_in=False)
        self.assertSolid(nut, bbox=[12, 12, 5])
        self.assertEqual(nut.genus(), 1)
        self.assertEqual((bolt ^ nut).volume(), 0.0)
        gap = bolt.min_gap(nut, 1.0)
        self.assertGreater(gap, 0.08)                                         # about clearance * sin(30)
        self.assertLess(gap, 0.25)
        with self.assertRaises(ValueError):
            parts.thread(7, length=5)                                         # no default pitch


@unittest.skipUnless(HAS_M3D, "manifold3d not installed")
class BuildIntegration(unittest.TestCase):
    """A generator imports parts by name; build.py hashes parts.py into the manifest (R3)."""

    def test_generator_can_import_parts(self):
        import build
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "gen.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write("import parts\n"
                        "def build(p):\n"
                        "    box = parts.rounded_box([p['w'], 30, 20], 3)\n"
                        "    box -= parts.screw_hole('M3', 8, 'insert').translate([10, 10, 20])\n"
                        "    return {'box': box}\n")
            prm = os.path.join(d, "params.json")
            with open(prm, "w", encoding="utf-8") as f:
                json.dump({"_parts": {"box": {"expect": [40, 30, 20]}}, "w": 40}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build.main(["run", src, "--params", prm, "--out", os.path.join(d, "out"), "--no-wall-check"])
            out = json.loads(buf.getvalue())
            self.assertEqual(code, 0, out.get("errors"))
            self.assertEqual(out["gate"], "INCOMPLETE")                    # no printer: D2 unverified
            self.assertIn("parts.py", [os.path.basename(s) for s in out["sources"]])
            checks = out["parts"][0]["validate"]["files"][0]["checks"]
            self.assertEqual(checks["D1"]["state"], "PASS")
            self.assertEqual(checks["M1"]["state"], "PASS")
            self.assertEqual(checks["R3"]["state"], "PASS")


@unittest.skipUnless(HAS_M3D, "manifold3d not installed (parts.py imports it)")
class DocumentedSignatures(unittest.TestCase):
    """engines/python.md lists parts.py calls with their arguments; the order must be the real one,
    or a caller who follows the table positionally binds values to the wrong argument."""

    def test_python_md_table_matches_the_code(self):
        import inspect
        import re
        with open(os.path.join(HERE, "..", "references", "engines", "python.md"), encoding="utf-8") as f:
            table = f.read()
        rows = re.findall(r"^\| `(\w+)\(([^`]*)\)` \|", table, re.M)
        self.assertGreaterEqual(len(rows), 10)
        for name, args in rows:
            with self.subTest(call=name):
                self.assertTrue(hasattr(parts, name), f"{name} is not in parts.py")
                params = inspect.signature(getattr(parts, name)).parameters
                tokens = [t.strip() for t in args.replace("\\|", "|").split(",") if t.strip()]
                positional, rest, mode = [], [], "pos"
                for t in tokens:
                    if t in ("...", "*"):
                        mode = t
                        continue
                    key = t.split("=")[0].strip()
                    if mode == "pos":
                        positional.append(key)
                    else:
                        rest.append((mode, key))
                real = list(params)
                self.assertEqual(positional, real[:len(positional)], f"{name}: listed order is not the real order")
                for mode, key in rest:
                    self.assertIn(key, params, f"{name}: no argument {key}")
                    if mode == "*":
                        self.assertEqual(params[key].kind, inspect.Parameter.KEYWORD_ONLY, f"{name}: {key} is not keyword-only")


if __name__ == "__main__":
    unittest.main()
