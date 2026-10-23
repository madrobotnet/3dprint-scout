"""Tests for scripts/preview.py (needs numpy)."""
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from importlib.util import find_spec

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import preview  # noqa: E402
from test_validate import box, cylinder, write_stl  # noqa: E402

HAS_NP = find_spec("numpy") is not None


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = preview.main(list(argv))
    return code, json.loads(buf.getvalue())


def read_png(path):
    """Minimal decoder for the PNGs preview.py writes (8-bit RGB, filter 0 on every row)."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, w, h = 8, None, None
    idat = b""
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) == (8, 2)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = 1 + 3 * w
    rows = []
    for r in range(h):
        line = raw[r * stride:(r + 1) * stride]
        assert line[0] == 0
        rows.append(line[1:])
    return w, h, rows


def colours(path):
    w, h, rows = read_png(path)
    seen = set()
    for line in rows:
        for i in range(0, len(line), 3):
            seen.add(tuple(line[i:i + 3]))
    return w, h, seen


@unittest.skipUnless(HAS_NP, "numpy not installed")
class Preview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.box = os.path.join(self.d, "box.stl")
        write_stl(self.box, box(60, 40, 25))
        self.peg = os.path.join(self.d, "peg.stl")
        write_stl(self.peg, cylinder(4, 30, 48))

    def tearDown(self):
        self.tmp.cleanup()

    def test_grid_of_four_views(self):
        out_png = os.path.join(self.d, "out", "preview.png")
        code, out = run(self.box, "-o", out_png)
        self.assertEqual(code, 0, out["errors"])
        self.assertTrue(out["ran"] and out["sane"])
        self.assertEqual(out["schema"], preview.SCHEMA)
        self.assertEqual(out["files"][0]["views"], ["iso", "front", "right", "top"])
        self.assertEqual(out["size_mm"], [60, 40, 25])
        self.assertGreater(out["files"][0]["bytes"], 1000)
        w, h, seen = colours(out_png)
        self.assertEqual((w, h), (1600, 1200))
        self.assertIn(preview.BACKGROUND, seen)
        self.assertIn(preview.INK, seen)                                           # outlines and labels
        blues = [c for c in seen if c[2] > c[0] + 30 and c not in (preview.BACKGROUND, preview.INK)]
        self.assertGreaterEqual(len(blues), 3)                                     # several shaded faces
        self.assertIn("numpy", out["renderer"])

    def test_two_parts_separate_files_and_views(self):
        stem = os.path.join(self.d, "two.png")
        code, out = run(self.box, self.peg, "-o", stem, "--separate", "--views", "iso,top", "--size", "600x400")
        self.assertEqual(code, 0, out["errors"])
        paths = [f["path"] for f in out["files"]]
        self.assertEqual(paths, [os.path.join(self.d, "two_iso.png"), os.path.join(self.d, "two_top.png")])
        self.assertTrue(all(f["sane"] for f in out["files"]))
        self.assertEqual([p["name"] for p in out["parts"]], ["box", "peg"])
        self.assertNotEqual(out["parts"][0]["colour"], out["parts"][1]["colour"])
        w, h, seen = colours(paths[0])
        self.assertEqual((w, h), (600, 400))
        oranges = [c for c in seen if c[0] > c[2] + 60 and c != preview.INK]
        self.assertTrue(oranges)                                                   # the peg's colour is present

    def test_blank_image_fails_g4(self):
        flat = os.path.join(self.d, "flat.stl")
        write_stl(flat, [((0, 0, 0), (0, 0, 0), (0, 0, 0))] * 4)                   # zero-area triangles only
        code, out = run(flat, "-o", os.path.join(self.d, "flat.png"))
        self.assertEqual(code, 2)
        self.assertTrue(out["ran"])
        self.assertFalse(out["sane"])
        self.assertIn("blank", out["files"][0]["note"])

    def test_refuses_to_overwrite_unless_asked(self):
        png = os.path.join(self.d, "p.png")
        self.assertEqual(run(self.box, "-o", png, "--views", "iso", "--size", "300x300")[0], 0)
        code, out = run(self.box, "-o", png, "--views", "iso", "--size", "300x300")
        self.assertEqual(code, 1)
        self.assertIn("already exists", out["errors"][0])
        code, out = run(self.box, "-o", png, "--views", "iso", "--size", "300x300", "--overwrite")
        self.assertEqual(code, 0)

    def test_a_sidecar_ties_each_image_to_its_parts(self):
        """0.7.0 step 3: next to each image, its sha256, the views and each STL drawn with its
        sha256; a sidecar left behind also stops a new image without --overwrite."""
        import validate
        stem = os.path.join(self.d, "s.png")
        code, out = run(self.box, self.peg, "-o", stem, "--separate", "--views", "iso,top", "--size", "300x300")
        self.assertEqual(code, 0, out["errors"])
        for f in out["files"]:
            self.assertEqual(f["sidecar"], f["path"] + ".json")
            with open(f["sidecar"], encoding="utf-8") as fh:
                side = json.load(fh)
            self.assertEqual(side["schema"], preview.IMAGE_SCHEMA)
            self.assertEqual(side["image_sha256"], validate.file_sha256(f["path"]))
            self.assertEqual(side["views"], f["views"])
            self.assertEqual([x["sha256"] for x in side["stls"]], [validate.file_sha256(self.box),
                                                                   validate.file_sha256(self.peg)])
        for f in out["files"]:
            os.remove(f["path"])                                                   # the sidecars are left behind
        code, out = run(self.box, self.peg, "-o", stem, "--separate", "--views", "iso,top", "--size", "300x300")
        self.assertEqual(code, 1)
        self.assertIn("s_iso.png.json already exists", out["errors"][0])

    def test_an_stl_that_changes_while_drawn_gets_no_sidecar(self):
        """Codex review of step 3 (P2): the sidecar names the bytes read for drawing; an STL
        rebuilt meanwhile leaves the image without a sidecar."""
        from unittest import mock
        png = os.path.join(self.d, "c.png")
        real = preview.render

        def rebuilt_meanwhile(*a, **k):
            images = real(*a, **k)
            write_stl(self.box, box(61, 40, 25))
            return images

        with mock.patch.object(preview, "render", side_effect=rebuilt_meanwhile):
            code, out = run(self.box, "-o", png, "--views", "iso", "--size", "300x300")
        self.assertEqual(code, 1)
        self.assertIn("changed while the image was drawn", out["errors"][0])
        self.assertFalse(os.path.exists(png + ".json"))

    def test_usage_and_file_errors_are_json(self):
        code, out = run(self.box, "-o", os.path.join(self.d, "x.png"), "--views", "diagonal")
        self.assertEqual(code, 1)
        self.assertIn("unknown view", out["errors"][0])
        code, out = run(self.box, "-o", os.path.join(self.d, "x.jpg"))
        self.assertIn(".png", out["errors"][0])
        code, out = run(os.path.join(self.d, "missing.stl"), "-o", os.path.join(self.d, "x.png"))
        self.assertIn("file not found", out["errors"][0])
        empty = os.path.join(self.d, "empty.stl")
        open(empty, "wb").close()
        code, out = run(empty, "-o", os.path.join(self.d, "x.png"))
        self.assertEqual(code, 1)
        self.assertIn("0 bytes", out["errors"][0])
        code, out = run(self.box, "-o", os.path.join(self.d, "x.png"), "--size", "big")
        self.assertIn("--size", out["errors"][0])

    def test_rasterizer_paths_agree(self):
        """A triangle rendered through the batched path and the scanline path covers the same pixels."""
        import numpy as np
        P = np.array([[2.0, 2.0, 5.0], [9.0, 3.0, 5.0], [4.0, 9.0, 5.0]])
        F = np.array([[0, 1, 2]])
        old = preview.SMALL
        try:
            preview.SMALL = 64
            f1, d1 = preview.rasterize(P, F, 12, 12)
            preview.SMALL = 1
            f2, d2 = preview.rasterize(P, F, 12, 12)
        finally:
            preview.SMALL = old
        self.assertGreater((f1 >= 0).sum(), 10)
        self.assertTrue(np.array_equal(f1, f2))
        self.assertTrue(np.allclose(np.where(np.isfinite(d1), d1, 0), np.where(np.isfinite(d2), d2, 0)))

    def test_text_and_cli(self):
        import numpy as np
        img = np.zeros((20, 80, 3), dtype=np.uint8)
        end = preview.draw_text(img, "ISO 9", 2, 2)
        self.assertEqual(end, 2 + 6 * 2 * 5)
        self.assertGreater(int((img == preview.INK[0]).sum()), 50)
        r = subprocess.run([sys.executable, "-I", "-B", os.path.join(SCRIPTS, "preview.py"), self.box, "-o",
                            os.path.join(self.d, "cli.png"), "--views", "iso", "--size", "320x240"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["sane"])


if __name__ == "__main__":
    unittest.main()
