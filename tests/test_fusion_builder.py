"""references/engines/fusion_builder.py: compiles, its pure helpers work, and the Builder's control
flow (parameters, frames, join / cut guards, export) runs against a small stand-in for the
Fusion API. Fusion itself cannot run here, so the API calls are only exercised, not proven."""
import json
import os
import sys
import tempfile
import types
import unittest
from importlib.util import module_from_spec, spec_from_file_location

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "references", "engines", "fusion_builder.py")


def load(with_fake):
    """Import the file fresh, with or without a fake `adsk` package in sys.modules."""
    for name in ("adsk", "adsk.core", "adsk.fusion", "fusion_builder_under_test"):
        sys.modules.pop(name, None)
    if with_fake:
        core, fusion = fake_adsk()
        pkg = types.ModuleType("adsk")
        pkg.core, pkg.fusion = core, fusion
        sys.modules["adsk"], sys.modules["adsk.core"], sys.modules["adsk.fusion"] = pkg, core, fusion
    spec = spec_from_file_location("fusion_builder_under_test", PATH)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# A tiny Fusion stand-in: cm units, bounding boxes, combine that only removes tools that
# overlap the target (what Fusion does), STL export that writes a file.
# --------------------------------------------------------------------------- #
def fake_adsk():
    core, fusion = types.ModuleType("adsk.core"), types.ModuleType("adsk.fusion")

    class P:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

    class Point3D:
        @staticmethod
        def create(x, y, z):
            return P(x, y, z)

    class Vector3D(Point3D):
        pass

    class ValueInput:
        def __init__(self, text):
            self.text = text

        @staticmethod
        def createByString(text):
            return ValueInput(text)

        @staticmethod
        def createByReal(v):
            return ValueInput(v)

    class Matrix3D:
        @staticmethod
        def create():
            return Matrix3D()

        def setWithCoordinateSystem(self, origin, x, y, z):
            self.origin, self.axes = origin, (x, y, z)

    class ObjectCollection(list):
        @staticmethod
        def create():
            return ObjectCollection()

        def add(self, item):
            self.append(item)

        @property
        def count(self):
            return len(self)

    core.Point3D, core.Vector3D, core.ValueInput, core.Matrix3D, core.ObjectCollection = Point3D, Vector3D, ValueInput, Matrix3D, ObjectCollection

    class BBox:
        def __init__(self, lo, hi):
            self.minPoint, self.maxPoint = P(*lo), P(*hi)

    class Body:
        def __init__(self, name, lo, hi, root):
            self.name, self.boundingBox, self.root, self.isValid = name, BBox(lo, hi), root, True

        @property
        def volume(self):
            lo, hi = self.boundingBox.minPoint, self.boundingBox.maxPoint
            return (hi.x - lo.x) * (hi.y - lo.y) * (hi.z - lo.z)

    class Bodies(list):
        @property
        def count(self):
            return len(self)

        def item(self, i):
            return self[i]

    class Combine:
        def __init__(self, root):
            self.root = root

        def createInput(self, target, tools):
            return types.SimpleNamespace(target=target, tools=tools)

        def add(self, inp):
            t = inp.target.boundingBox
            for tool in inp.tools:
                b = tool.boundingBox
                touches = all(t.minPoint.__dict__[a] <= b.maxPoint.__dict__[a] and b.minPoint.__dict__[a] <= t.maxPoint.__dict__[a]
                              for a in "xyz")
                if touches:                        # Fusion absorbs a touching tool, keeps a distant one
                    self.root.bRepBodies.remove(tool)
                    tool.isValid = False

    class Export:
        def createSTLExportOptions(self, body, path):
            return types.SimpleNamespace(body=body, path=path)

        def execute(self, opt):
            with open(opt.path, "wb") as f:
                f.write(b"\0" * 84)

    class Params(dict):
        def itemByName(self, name):
            return self.get(name)

        def add(self, name, value, unit, comment):
            self[name] = types.SimpleNamespace(expression=value.text, unit=unit, comment=comment)

    class Timeline:
        def __init__(self):
            self.items = []

        @property
        def count(self):
            return len(self.items)

        def item(self, i):
            return self.items[i]

    root = types.SimpleNamespace(bRepBodies=Bodies(), xYConstructionPlane="XY")
    root.features = types.SimpleNamespace(combineFeatures=Combine(root))
    design = types.SimpleNamespace(rootComponent=root, userParameters=Params(), timeline=Timeline(), exportManager=Export())
    fusion.FeatureOperations = types.SimpleNamespace(NewBodyFeatureOperation="new", JoinFeatureOperation="join",
                                                     CutFeatureOperation="cut", IntersectFeatureOperation="intersect")
    fusion.MeshRefinementSettings = types.SimpleNamespace(MeshRefinementHigh="high", MeshRefinementMedium="medium",
                                                          MeshRefinementLow="low")
    fusion.Design = types.SimpleNamespace(cast=lambda x: x)
    fusion._design, fusion._Body = design, Body
    return core, fusion


class PureHelpers(unittest.TestCase):
    def setUp(self):
        self.fb = load(with_fake=False)

    def test_imports_without_fusion(self):
        self.assertIsNone(self.fb.adsk)
        with self.assertRaisesRegex(RuntimeError, "inside Fusion"):
            self.fb.Builder(None)

    def test_units_and_names(self):
        self.assertEqual(self.fb.cm(25.0), 2.5)
        self.assertEqual(self.fb.mm(2.5), 25.0)
        self.assertEqual(self.fb.param_name("wall"), "p_wall")
        self.assertEqual(self.fb.param_name("x2", prefix="xa_"), "xa_x2")
        for bad in ("a-b", "a b", "", "1x"):
            with self.assertRaises(ValueError, msg=bad):
                self.fb.param_name(bad, prefix="")
        self.assertEqual(self.fb.expression(2.5), "2.5 mm")
        self.assertEqual(self.fb.expression("p_w / 2"), "p_w / 2")
        for bad in (True, None, float("nan")):
            with self.assertRaises(ValueError):
                self.fb.expression(bad)

    def test_right_handed_frames(self):
        x, y, z = self.fb.right_handed((0, 0, 1), (1, 0, 0))
        self.assertEqual((x, y, z), ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        x, y, z = self.fb.right_handed((2, 0, 0), (0, 3, 0))          # normalised
        self.assertEqual(z, (0.0, 0.0, 1.0))
        with self.assertRaisesRegex(ValueError, "perpendicular"):
            self.fb.right_handed((1, 0, 0), (1, 1, 0))
        with self.assertRaises(ValueError):
            self.fb.right_handed((1, 0, 0), (0, 0, 0))

    def test_boxes_touch(self):
        a = {"min": [0, 0, 0], "max": [10, 10, 10]}
        self.assertTrue(self.fb.boxes_touch(a, {"min": [10, 0, 0], "max": [20, 10, 10]}))      # shared face
        self.assertTrue(self.fb.boxes_touch(a, {"min": [10.005, 0, 0], "max": [20, 10, 10]}))  # within margin
        self.assertFalse(self.fb.boxes_touch(a, {"min": [10.5, 0, 0], "max": [20, 10, 10]}))
        self.assertFalse(self.fb.boxes_touch(a, {"min": [0, 0, 11], "max": [5, 5, 12]}))

    def test_summary_is_json(self):
        text = self.fb.summary({"body": {"size": [1, 2, 3]}}, "/x")
        data = json.loads(text)
        self.assertEqual(data["schema"], "3dprint-scout.fusion_builder/1")
        self.assertEqual(data["bodies"]["body"]["size"], [1, 2, 3])


class WithFakeFusion(unittest.TestCase):
    def setUp(self):
        self.fb = load(with_fake=True)
        self.fusion = sys.modules["adsk.fusion"]
        self.design = self.fusion._design
        self.B = self.fb.Builder(self.design)

    def body(self, name, lo, hi):
        """A body with a box in mm (stored in cm like the API)."""
        b = self.fusion._Body(name, [v / 10 for v in lo], [v / 10 for v in hi], self.design.rootComponent)
        self.design.rootComponent.bRepBodies.append(b)
        return b

    def test_params_become_user_parameters_in_mm(self):
        names = self.B.params({"w": 60, "wall": 2.5, "half": "p_w / 2"})
        self.assertEqual(names, {"w": "p_w", "wall": "p_wall", "half": "p_half"})
        ups = self.design.userParameters
        self.assertEqual(ups["p_w"].expression, "60 mm")
        self.assertEqual(ups["p_half"].expression, "p_w / 2")
        self.B.params({"w": 70})                                        # update, not duplicate
        self.assertEqual(ups["p_w"].expression, "70 mm")
        self.assertEqual(len(ups), 3)

    def test_frame_is_right_handed_and_in_cm(self):
        m = self.B.frame((10, 20, 30), (0, 0, 1), (1, 0, 0))
        self.assertEqual((m.origin.x, m.origin.y, m.origin.z), (1.0, 2.0, 3.0))
        self.assertEqual((m.axes[2].x, m.axes[2].y, m.axes[2].z), (0.0, 1.0, 0.0))
        with self.assertRaisesRegex(ValueError, "perpendicular"):
            self.B.frame((0, 0, 0), (1, 0, 0), (1, 1, 0))

    def test_join_refuses_a_tool_that_does_not_touch(self):
        body = self.body("body", [0, 0, 0], [60, 40, 3])
        far = self.body("far", [0, 0, 10], [5, 5, 11])
        with self.assertRaisesRegex(ValueError, "does not touch"):
            self.B.join(body, [far])
        self.assertIn("far", self.B.bodies())                           # nothing was combined
        lip = self.body("lip", [0, 0, 3], [10, 5, 5])                   # shares a face
        self.assertIs(self.B.join(body, [lip]), body)
        self.assertNotIn("lip", self.B.bodies())

    def test_cut_reports_leftover_tool_bodies(self):
        """A tool whose box touches (so the guard passes) but that Fusion still leaves behind."""
        body = self.body("body", [0, 0, 0], [60, 40, 3])
        ghost = self.body("ghost", [60, 0, 0], [70, 40, 3])             # touches at x = 60 only
        self.fusion._design.rootComponent.features.combineFeatures.add = lambda inp: None   # Fusion did nothing
        with self.assertRaisesRegex(ValueError, "still there"):
            self.B.cut(body, [ghost])

    def test_export_writes_one_stl_per_body_and_a_summary(self):
        self.body("body", [0, 0, 0], [60, 40, 3])
        self.body("lid", [0, 0, 0], [60, 40, 2])
        with tempfile.TemporaryDirectory() as d:
            text = self.B.export(d, ["body", "lid"])
            data = json.loads(text)
            self.assertEqual(sorted(data["bodies"]), ["body", "lid"])
            self.assertEqual(data["bodies"]["body"]["size"], [60.0, 40.0, 3.0])
            self.assertEqual(data["bodies"]["body"]["volume_mm3"], 7200.0)
            self.assertTrue(os.path.isfile(os.path.join(d, "body.stl")))
            self.assertTrue(os.path.isfile(os.path.join(d, "summary.json")))
            with self.assertRaisesRegex(ValueError, "no body named"):
                self.B.export(d, ["nope"])


if __name__ == "__main__":
    unittest.main()
