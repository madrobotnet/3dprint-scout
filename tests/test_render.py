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
                                    label="x", exe="/x/blender", overwrite=True)
        self.assertEqual(cmd[:7], ["/x/blender", "--background", "--factory-startup", "--python-exit-code", "1",
                                   "--python", render.BUILDER])
        self.assertEqual(cmd[7:], ["--", "render", self.stl, "-o", self.png, "--views", "iso,top", "--size", "800x600",
                                   "--engine", "workbench", "--color", "body=black", "--label", "x", "--overwrite"])
        cmd = render.render_command([self.stl], self.png, ["iso"], (400, 300), "workbench", [], exe="/x/blender")
        self.assertNotIn("--overwrite", cmd)
        cmd = render.render_command([self.stl], self.png, ["iso"], (400, 300), "cycles", [], python="/x/python")
        self.assertEqual(cmd[:3], ["/x/python", render.BUILDER, "--"])
        self.assertNotIn("--lang", cmd)
        cmd = render.render_command([self.stl], self.png, ["iso"], (400, 300), "workbench", [], python="/x/python",
                                    lang="ko")
        self.assertEqual(cmd[-2:], ["--lang", "ko"])
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
            self.assertIn("--color", out["errors"][0])                          # a part that is not rendered
            code, out = run(self.stl, "-o", os.path.join(self.d, "y.png"), "--views", "sideways")
            self.assertIn("unknown view", out["errors"][0])
            code, out = run(self.stl, "-o", os.path.join(self.d, "y.png"), "--engine", "octane")
            self.assertIn("--engine", out["errors"][0])
            code, out = run(self.stl, "-o", os.path.join(self.d, "y.png"), "--lang", "fr")
            self.assertIn("--lang must be one of en, ko", out["errors"][0])
            empty = os.path.join(self.d, "empty.stl")
            open(empty, "wb").close()
            code, out = run(empty, "-o", os.path.join(self.d, "y.png"))          # G4 on the input
            self.assertIn("0 bytes", out["errors"][0])
        self.assertFalse(sub.called)                                            # Blender never ran
        self.assertEqual(code, 1)

    def test_unknown_colour_is_a_warning_and_no_background_is_not_sane(self):
        """An unknown filament name never aborts (neutral grey, a warning); a render whose pixels
        nearly all differ from the background (a black world) is not sane: exit 2."""
        os.makedirs(os.path.dirname(self.png))
        with open(self.png, "wb") as f:                                        # a real PNG header, like Blender writes
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00\x00\x01\x90\x00\x00\x01\x2c" + b"\x08\x02\x00\x00\x00" + b"\0" * 32)
        rep = {"path": self.png, "fg": 0.99, "size_mm": [40, 30, 6], "renderer": "Blender x workbench", "views": ["iso"],
               "parts": [{"name": "body", "colour": "#808080", "drawn": "#808080"}], "warnings": []}
        done = build.subprocess.CompletedProcess([], 0, "@@3DPS " + json.dumps(rep) + "\n", "")
        with mock.patch.object(render, "choose_blender", return_value=("/x/blender", None, "4.5.0")), \
                mock.patch.object(build.subprocess, "run", return_value=done) as sub:
            code, out = run(self.stl, "-o", self.png, "--overwrite", "--color", "body=Ice Blue")
        self.assertEqual(code, 2)
        self.assertTrue(out["ran"])
        self.assertFalse(out["sane"])
        self.assertIn("no background", out["files"][0]["note"])
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("unknown filament colour 'Ice Blue'", out["warnings"][0])
        self.assertIn("approximate", out["colour_note"])
        self.assertIn("--overwrite", sub.call_args[0][0])
        rep["fg"] = 0.2
        done = build.subprocess.CompletedProcess([], 0, "@@3DPS " + json.dumps(rep) + "\n", "")
        with mock.patch.object(render, "choose_blender", return_value=("/x/blender", None, "4.5.0")), \
                mock.patch.object(build.subprocess, "run", return_value=done):
            code, out = run(self.stl, "-o", self.png, "--overwrite")
        self.assertEqual((code, out["sane"], out["warnings"]), (0, True, []))

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
        self.assertEqual(sorted(out["files"][0]["fg_views"]), ["front", "iso", "right", "top"])   # per view, for the agent
        self.assertTrue(all(0.0005 < f < 0.95 for f in out["files"][0]["fg_views"].values()), out["files"][0])
        self.assertAlmostEqual(out["files"][0]["fg"], sum(out["files"][0]["fg_views"].values()) / 4, delta=0.02)
        self.assertEqual(out["parts"][1]["drawn"], "#e6e6e6")               # white taken down a little, off the background
        self.assertEqual(out["size_mm"], [40.0, 30.0, 8.0])
        self.assertEqual([p["name"] for p in out["parts"]], ["body", "lid"])
        self.assertEqual(out["parts"][1]["colour"], "#ffffff")
        self.assertEqual(out["warnings"], [])
        self.assertIn("approximate", out["colour_note"])
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
        # 0.7.0 step 3: Korean view names, and the sidecar that ties the image to its parts.
        import validate
        ko = os.path.join(self.d, "out", "ko.png")
        with mock.patch.object(build, "find_blender", return_value=None):
            code, out = run(self.stl, "-o", ko, "--views", "iso,top", "--size", "400x300", "--lang", "ko",
                            "--blender-python", sys.executable)
        self.assertEqual((code, out["sane"]), (0, True), out.get("errors"))
        with open(out["files"][0]["sidecar"], encoding="utf-8") as fh:
            side = json.load(fh)
        self.assertEqual((side["lang"], side["views"]), ("ko", ["iso", "top"]))
        self.assertEqual(side["image_sha256"], validate.file_sha256(ko))
        self.assertEqual(side["stls"], [{"path": self.stl, "sha256": validate.file_sha256(self.stl)}])


if __name__ == "__main__":
    unittest.main()
