"""The real binary must remove material, not merely return a closed mesh."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


BLENDER = shutil.which("blender")
ENGINE = Path(__file__).resolve().parents[1] / "references" / "engines"


@unittest.skipUnless(BLENDER, "Blender binary unavailable")
class BinaryBooleanTests(unittest.TestCase):
    def test_default_solver_removes_through_hole_without_touching_user_scene(self):
        script = f"""
import sys, json, bmesh, bpy
sys.path.insert(0, {str(ENGINE)!r})
import blender_builder as bb
original = bpy.context.scene
bb.new_scene_mm()
body = bb.box([20, 20, 20], "body")
hole = bb.cylinder(3, 22, name="hole")
hole.location = (10, 10, -1)
bb.boolean(body, hole)
bm = bmesh.new()
bm.from_mesh(body.data)
volume = abs(bm.calc_volume(signed=True))
bm.free()
print("BOOLEAN_RESULT=" + json.dumps({{"volume": volume, "solver": bb.boolean_solver(),
    "same_scene": bpy.context.scene == original,
    "probe_scenes": [s.name for s in bpy.data.scenes if "boolean capability" in s.name]}}))
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.py"
            path.write_text(script)
            result = subprocess.run(
                [BLENDER, "-b", "-t", "1", "--python-exit-code", "1", "--python", str(path)],
                capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = [line.split("=", 1)[1] for line in result.stdout.splitlines()
                   if line.startswith("BOOLEAN_RESULT=")]
        self.assertEqual(len(records), 1, result.stdout)
        record = json.loads(records[0])
        self.assertAlmostEqual(record["volume"], 7435.42, delta=1.0)
        self.assertIn(record["solver"], ("MANIFOLD", "EXACT"))
        self.assertTrue(record["same_scene"])
        self.assertEqual(record["probe_scenes"], [])
