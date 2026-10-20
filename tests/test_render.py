"""Tests for scripts/render.py: the command line it builds, its refusals before Blender starts,
and a real render when the bpy module is there."""
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.util import find_spec
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import build   # noqa: E402
import render  # noqa: E402
from test_validate import box, write_stl  # noqa: E402

HAS_BPY = find_spec("bpy") is not None


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = render.main(list(argv))
    return code, json.loads(buf.getvalue())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.stl = os.path.join(self.d, "body.stl")
        write_stl(self.stl, box(40, 30, 6))
        self.png = os.path.join(self.d, "out", "render.png")

    def tearDown(self):
        self.tmp.cleanup()


class CommandLine(Base):
    def test_binary_and_bpy_commands(self):
        cmd = render.render_command([self.stl], self.png, ["iso", "top"], (800, 600), "workbench", ["body=black"],
                                    label="x", exe="/x/blender")
        self.assertEqual(cmd[:7], ["/x/blender", "--background", "--factory-startup", "--python-exit-code", "1",
                                   "--python", render.BUILDER])
        self.assertEqual(cmd[7:], ["--", "render", self.stl, "-o", self.png, "--views", "iso,top", "--size", "800x600",
                                   "--engine", "workbench", "--color", "body=black", "--label", "x"])
        cmd = render.render_command([self.stl], self.png, ["iso"], (400, 300), "cycles", [], python="/x/python")
        self.assertEqual(cmd[:3], ["/x/python", render.BUILDER, "--"])
        self.assertTrue(os.path.isfile(render.BUILDER))

    def test_no_blender_is_a_clear_error(self):
        with mock.patch.object(build, "find_blender", return_value=None), mock.patch.object(build, "bpy_info", return_value=None):
            code, out = run(self.stl, "-o", self.png)
        self.assertEqual(code, 1)
        self.assertFalse(out["ran"])
        self.assertIn("Blender not found", out["errors"][0])
        self.assertIn("preview.py", out["errors"][0])
        self.assertFalse(os.path.exists(self.png))

    def test_refusals_before_blender_starts(self):
        os.makedirs(os.path.dirname(self.png))
        open(self.png, "wb").close()
        with mock.patch.object(build.subprocess, "run") as sub:
            code, out = run(self.stl, "-o", self.png)                           # exists, no --overwrite
            self.assertIn("already exists", out["errors"][0])
            code, out = run(self.stl, "-o", os.path.join(self.d, "x.jpg"))
            self.assertIn(".png", out["errors"][0])
            code, out = run(self.stl, "-o", os.path.join(self.d, "y.png"), "--color", "lid=black")
            self.assertIn("--color", out["errors"][0])
            code, out = run(self.stl, "-o", os.path.join(self.d, "y.png"), "--views", "sideways")
            self.assertIn("unknown view", out["errors"][0])
            code, out = run(self.stl, "-o", os.path.join(self.d, "y.png"), "--engine", "octane")
            self.assertIn("--engine", out["errors"][0])
            empty = os.path.join(self.d, "empty.stl")
            open(empty, "wb").close()
            code, out = run(empty, "-o", os.path.join(self.d, "y.png"))          # G4 on the input
            self.assertIn("0 bytes", out["errors"][0])
        self.assertFalse(sub.called)                                            # Blender never ran
        self.assertEqual(code, 1)

    def test_failed_render_keeps_the_json_contract(self):
        done = build.subprocess.CompletedProcess([], 1, "", "Traceback: boom")
        with mock.patch.object(render, "choose_blender", return_value=("/x/blender", None, "4.2.0")), \
                mock.patch.object(build.subprocess, "run", return_value=done):
            code, out = run(self.stl, "-o", self.png)
        self.assertEqual(code, 1)
        self.assertIn("boom", out["errors"][0])
        with mock.patch.object(render, "choose_blender", return_value=("/x/blender", None, "4.2.0")), \
                mock.patch.object(build.subprocess, "run", side_effect=build.subprocess.TimeoutExpired("blender", 3)):
            code, out = run(self.stl, "-o", self.png, "--timeout", "3")
        self.assertIn("timed out after 3s", out["errors"][0])


@unittest.skipUnless(HAS_BPY, "bpy module not installed")
class WithBlender(Base):
    def test_renders_a_sane_grid(self):
        lid = os.path.join(self.d, "lid.stl")
        write_stl(lid, box(40, 30, 2, 0, 0, 6))
        with mock.patch.object(build, "find_blender", return_value=None):
            code, out = run(self.stl, lid, "-o", self.png, "--size", "640x480", "--color", "lid=Jade White",
                            "--blender-python", sys.executable)
        self.assertEqual(code, 0, out.get("errors"))
        self.assertTrue(out["ran"] and out["sane"])
        self.assertEqual(out["files"][0]["views"], ["iso", "front", "right", "top"])
        self.assertIn("of the pixels show the part", out["files"][0]["note"])
        self.assertEqual(out["size_mm"], [40.0, 30.0, 8.0])
        self.assertEqual([p["name"] for p in out["parts"]], ["body", "lid"])
        self.assertEqual(out["parts"][1]["colour"], "#ffffff")
        self.assertIn("Blender", out["renderer"])
        self.assertIn("bpy module", out["renderer"])
        with open(self.png, "rb") as f:
            head = f.read(24)
        self.assertTrue(head.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", head[16:24]), (640, 480))
        # A second run refuses to overwrite; --overwrite and a single view work.
        code, out = run(self.stl, "-o", self.png, "--blender-python", sys.executable)
        self.assertEqual(code, 1)
        with mock.patch.object(build, "find_blender", return_value=None):
            code, out = run(self.stl, "-o", self.png, "--views", "iso", "--size", "400x300", "--overwrite",
                            "--blender-python", sys.executable)
        self.assertEqual((code, out["sane"], out["files"][0]["views"]), (0, True, ["iso"]))


if __name__ == "__main__":
    unittest.main()
