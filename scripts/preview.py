#!/usr/bin/env python3
"""
preview.py - preview images of STL parts: iso, front, right and top views in one PNG.

A software renderer (numpy only: orthographic projection, z-buffer, flat shading, crease
and silhouette outlines) that works headless on Linux, Windows and macOS. No OpenGL, no
display, no fonts: labels use a built-in 5x7 bitmap font. The PNG is written with zlib.

  python3 preview.py out/body.stl -o out/preview.png
  python3 preview.py out/box.stl out/lid.stl -o out/assembly.png --views iso,top --size 1600x1200
  python3 preview.py out/body.stl -o out/body.png --separate      # one file per view

Several STLs are drawn together, each in its own colour (a legend is printed in the
caption), exactly where their coordinates put them: pass parts that are already placed.

Prints one JSON document with the files written and the G4 sanity check of each image
(non-empty file, valid PNG header, and some foreground pixels). Exit 0 = rendered and sane,
2 = an image came out blank (G4), 1 = usage or file error. Refuses to overwrite unless
--overwrite is given (out/ is the working folder, so pass it there).

Next to every image it writes a sidecar, `<image>.png.json` (schema 3dprint-scout.image/1):
the image's own sha256, the views, and each STL drawn with its sha256. finalize.py ties a
person's judgement of the image (`_verify.seen`) to the parts by it. The view names stay in
English: the 5x7 font has no other script (render.py --lang draws them in Korean).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate import ArtifactError, read_stl  # noqa: E402

SCHEMA = "3dprint-scout.preview/1"
IMAGE_SCHEMA = "3dprint-scout.image/1"
VIEWS = {
    # name: (camera direction, i.e. from the scene towards the eye; world up)
    "iso": ((1.0, -1.0, 0.8), (0.0, 0.0, 1.0)),
    "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "bottom": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
}
DEFAULT_VIEWS = ["iso", "front", "right", "top"]
PALETTE = [(70, 130, 180), (221, 120, 60), (90, 160, 90), (160, 100, 180), (200, 170, 50), (80, 170, 180)]
BACKGROUND = (246, 246, 246)
INK = (40, 40, 40)
LIGHT = (0.35, 0.60, -0.70)          # in view space (x right, y up, z away): upper right, from the viewer's side
MARGIN = 0.08                        # of the viewport, around the part
CREASE_DEG = 28.0                    # outline where neighbouring faces bend more than this
MAX_PIXELS = 4096 * 4096

# 5x7 bitmap font (columns, LSB = top row) for labels; digits, upper case, a few symbols.
FONT = {
    "0": (0x3E, 0x51, 0x49, 0x45, 0x3E), "1": (0x00, 0x42, 0x7F, 0x40, 0x00), "2": (0x42, 0x61, 0x51, 0x49, 0x46),
    "3": (0x21, 0x41, 0x45, 0x4B, 0x31), "4": (0x18, 0x14, 0x12, 0x7F, 0x10), "5": (0x27, 0x45, 0x45, 0x45, 0x39),
    "6": (0x3C, 0x4A, 0x49, 0x49, 0x30), "7": (0x01, 0x71, 0x09, 0x05, 0x03), "8": (0x36, 0x49, 0x49, 0x49, 0x36),
    "9": (0x06, 0x49, 0x49, 0x29, 0x1E), "A": (0x7E, 0x11, 0x11, 0x11, 0x7E), "B": (0x7F, 0x49, 0x49, 0x49, 0x36),
    "C": (0x3E, 0x41, 0x41, 0x41, 0x22), "D": (0x7F, 0x41, 0x41, 0x22, 0x1C), "E": (0x7F, 0x49, 0x49, 0x49, 0x41),
    "F": (0x7F, 0x09, 0x09, 0x09, 0x01), "G": (0x3E, 0x41, 0x49, 0x49, 0x7A), "H": (0x7F, 0x08, 0x08, 0x08, 0x7F),
    "I": (0x00, 0x41, 0x7F, 0x41, 0x00), "J": (0x20, 0x40, 0x41, 0x3F, 0x01), "K": (0x7F, 0x08, 0x14, 0x22, 0x41),
    "L": (0x7F, 0x40, 0x40, 0x40, 0x40), "M": (0x7F, 0x02, 0x0C, 0x02, 0x7F), "N": (0x7F, 0x04, 0x08, 0x10, 0x7F),
    "O": (0x3E, 0x41, 0x41, 0x41, 0x3E), "P": (0x7F, 0x09, 0x09, 0x09, 0x06), "Q": (0x3E, 0x41, 0x51, 0x21, 0x5E),
    "R": (0x7F, 0x09, 0x19, 0x29, 0x46), "S": (0x46, 0x49, 0x49, 0x49, 0x31), "T": (0x01, 0x01, 0x7F, 0x01, 0x01),
    "U": (0x3F, 0x40, 0x40, 0x40, 0x3F), "V": (0x1F, 0x20, 0x40, 0x20, 0x1F), "W": (0x3F, 0x40, 0x38, 0x40, 0x3F),
    "X": (0x63, 0x14, 0x08, 0x14, 0x63), "Y": (0x07, 0x08, 0x70, 0x08, 0x07), "Z": (0x61, 0x51, 0x49, 0x45, 0x43),
    " ": (0x00, 0x00, 0x00, 0x00, 0x00), ".": (0x00, 0x60, 0x60, 0x00, 0x00), "-": (0x08, 0x08, 0x08, 0x08, 0x08),
    "_": (0x40, 0x40, 0x40, 0x40, 0x40), ":": (0x00, 0x36, 0x36, 0x00, 0x00), "/": (0x20, 0x10, 0x08, 0x04, 0x02),
    "(": (0x00, 0x1C, 0x22, 0x41, 0x00), ")": (0x00, 0x41, 0x22, 0x1C, 0x00), ",": (0x00, 0x50, 0x30, 0x00, 0x00),
    "=": (0x14, 0x14, 0x14, 0x14, 0x14), "+": (0x08, 0x08, 0x3E, 0x08, 0x08), "#": (0x14, 0x7F, 0x14, 0x7F, 0x14),
}


class PreviewError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise PreviewError(f"usage error: {message}")


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def load_meshes(paths):
    """[(name, V (n,3), F (m,3))] from STLs; raises PreviewError on a broken file (G4)."""
    import numpy as np
    meshes = []
    for path in paths:
        try:
            tris = read_stl(path)
        except ArtifactError as exc:
            raise PreviewError(f"{path}: {exc}")
        T = np.asarray(tris, dtype=np.float64)                # (m, 3, 3)
        V = T.reshape(-1, 3)
        F = np.arange(len(V)).reshape(-1, 3)
        meshes.append((os.path.splitext(os.path.basename(path))[0], V, F))
    return meshes


def camera(direction, up):
    """Orthonormal (right, up, forward) for a camera looking along -direction."""
    import numpy as np
    d = np.asarray(direction, dtype=np.float64)
    d /= np.linalg.norm(d)
    u = np.asarray(up, dtype=np.float64)
    f = -d                                                  # looking from the eye into the scene
    r = np.cross(f, u)
    if np.linalg.norm(r) < 1e-9:
        u = np.array([0.0, 1.0, 0.0]) if abs(f[2]) > 0.9 else np.array([0.0, 0.0, 1.0])
        r = np.cross(f, u)
    r /= np.linalg.norm(r)
    u2 = np.cross(r, f)
    return r, u2, f


def project(V, cam):
    """World points -> (screen x, screen y, depth) with depth growing away from the eye."""
    import numpy as np
    r, u, f = cam
    return np.stack([V @ r, V @ u, V @ f], axis=1)


# --------------------------------------------------------------------------- #
# Rasterizer: z-buffer with per-pixel face ids, bucketed by triangle size
# --------------------------------------------------------------------------- #
def rasterize(P, F, width, height):
    """P: projected vertices (n,3) in pixel units (x right, y up, depth); F: (m,3).
    Returns (face (H,W) int32, -1 where empty; depth (H,W) float).

    Small triangles (up to SMALL px across) are rasterized in vectorized batches over
    their bounding boxes; larger ones one at a time by scanline, so the work is
    proportional to the pixels actually covered."""
    import numpy as np
    H, W = height, width
    face = np.full((H, W), -1, dtype=np.int32)
    depth = np.full((H, W), np.inf)
    if len(F) == 0:
        return face, depth
    tri = P[F]                                              # (m, 3, 3)
    x, z = tri[:, :, 0], tri[:, :, 2]
    y = (H - 1) - tri[:, :, 1]                              # image rows grow downwards
    area = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (y[:, 1] - y[:, 0]) * (x[:, 2] - x[:, 0])
    keep = np.abs(area) > 1e-12
    x0 = np.clip(np.floor(x.min(axis=1)), 0, W - 1).astype(np.int64)
    x1 = np.clip(np.ceil(x.max(axis=1)), 0, W - 1).astype(np.int64)
    y0 = np.clip(np.floor(y.min(axis=1)), 0, H - 1).astype(np.int64)
    y1 = np.clip(np.ceil(y.max(axis=1)), 0, H - 1).astype(np.int64)
    span = np.maximum(x1 - x0, y1 - y0) + 1
    small = np.nonzero(keep & (span <= SMALL))[0]
    large = np.nonzero(keep & (span > SMALL))[0]
    if len(small):
        order = small[np.argsort(span[small], kind="stable")]
        budget = 2_000_000
        s = 0
        while s < len(order):
            K = int(span[order[min(s + 256, len(order) - 1)]])
            K = max(K, int(span[order[s]]))
            step = max(1, budget // (K * K))
            batch = order[s:s + step]
            K = int(span[batch].max())
            _raster_small(batch, K, x, y, z, x0, y0, x1, y1, area, face, depth)
            s += step
    for t in large:
        _raster_scanline(int(t), x[t], y[t], z[t], area[t], face, depth)
    return face, depth


SMALL = 12   # px; triangles up to this span go through the batched path


def _raster_small(sel, K, x, y, z, x0, y0, x1, y1, area, face, depth):
    import numpy as np
    H, W = face.shape
    oy, ox = np.divmod(np.arange(K * K), K)
    px = x0[sel][:, None] + ox[None, :]                     # (M, K*K)
    py = y0[sel][:, None] + oy[None, :]
    inbox = (px <= x1[sel][:, None]) & (py <= y1[sel][:, None])
    fx, fy = px + 0.5, py + 0.5
    ax, ay = x[sel, 0][:, None], y[sel, 0][:, None]
    bx, by = x[sel, 1][:, None], y[sel, 1][:, None]
    cx, cy = x[sel, 2][:, None], y[sel, 2][:, None]
    inv = 1.0 / area[sel][:, None]
    w0 = ((bx - fx) * (cy - fy) - (by - fy) * (cx - fx)) * inv
    w1 = ((cx - fx) * (ay - fy) - (cy - fy) * (ax - fx)) * inv
    w2 = 1.0 - w0 - w1
    eps = -1e-7
    inside = inbox & (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
    if not inside.any():
        return
    zs = z[sel]
    d = (w0 * zs[:, 0][:, None] + w1 * zs[:, 1][:, None] + w2 * zs[:, 2][:, None])[inside]
    tri_ids = np.broadcast_to(sel[:, None], inside.shape)[inside]
    pix = (py[inside] * W + px[inside]).astype(np.int64)
    flat_depth = depth.reshape(-1)
    np.minimum.at(flat_depth, pix, d)
    winner = d <= flat_depth[pix]
    face.reshape(-1)[pix[winner]] = tri_ids[winner]


def _raster_scanline(t, xs, ys, zs, area, face, depth):
    """One triangle: per image row the covered column range, then depth by barycentrics on
    exactly the covered pixels."""
    import numpy as np
    H, W = face.shape
    r0 = max(int(math.ceil(ys.min() - 0.5)), 0)
    r1 = min(int(math.floor(ys.max() - 0.5)), H - 1)
    if r1 < r0:
        return
    yc = np.arange(r0, r1 + 1) + 0.5
    xl = np.full(len(yc), np.inf)
    xr = np.full(len(yc), -np.inf)
    for i in range(3):
        xa, ya, xb, yb = xs[i], ys[i], xs[(i + 1) % 3], ys[(i + 1) % 3]
        if ya == yb:
            continue
        m = (yc >= min(ya, yb)) & (yc <= max(ya, yb))
        if not m.any():
            continue
        xi = xa + (yc[m] - ya) * (xb - xa) / (yb - ya)
        xl[m] = np.minimum(xl[m], xi)
        xr[m] = np.maximum(xr[m], xi)
    c0 = np.clip(np.ceil(xl - 0.5), 0, W).astype(np.int64)
    c1 = np.clip(np.floor(xr - 0.5), -1, W - 1).astype(np.int64)
    n = c1 - c0 + 1
    ok = n > 0
    if not ok.any():
        return
    rows = np.repeat(np.arange(r0, r1 + 1)[ok], n[ok])
    starts = np.repeat(c0[ok], n[ok])
    total = int(n[ok].sum())
    offs = np.arange(total) - np.repeat(np.cumsum(n[ok]) - n[ok], n[ok])
    cols = starts + offs
    fx, fy = cols + 0.5, rows + 0.5
    ax, ay, bx, by, cx, cy = xs[0], ys[0], xs[1], ys[1], xs[2], ys[2]
    w0 = ((bx - fx) * (cy - fy) - (by - fy) * (cx - fx)) / area
    w1 = ((cx - fx) * (ay - fy) - (cy - fy) * (ax - fx)) / area
    w2 = 1.0 - w0 - w1
    d = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
    cur = depth[rows, cols]
    win = d < cur
    depth[rows[win], cols[win]] = d[win]
    face[rows[win], cols[win]] = t


# --------------------------------------------------------------------------- #
# Shading, outlines, text
# --------------------------------------------------------------------------- #
def shade_view(meshes, view, width, height, scale, centre):
    """Render one view into an (H, W, 3) uint8 image. All meshes share one projection."""
    import numpy as np
    cam = camera(*VIEWS[view])
    Vs, Fs, colour_of, normals = [], [], [], []
    offset = 0
    for i, (_name, V, F) in enumerate(meshes):
        P = project(V, cam)
        P[:, 0] = (P[:, 0] - centre[view][0]) * scale + width / 2
        P[:, 1] = (P[:, 1] - centre[view][1]) * scale + height / 2
        Vs.append(P)
        Fs.append(F + offset)
        offset += len(V)
        T = V[F]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
        normals.append(np.stack([n @ cam[0], n @ cam[1], n @ cam[2]], axis=1))     # view space
        colour_of.append(np.full(len(F), i, dtype=np.int32))
    P = np.concatenate(Vs)
    F = np.concatenate(Fs)
    N = np.concatenate(normals)
    C = np.concatenate(colour_of)
    face, depth = rasterize(P, F, width, height)
    img = np.empty((height, width, 3), dtype=np.uint8)
    img[:] = BACKGROUND
    hit = face >= 0
    if not hit.any():
        return img, 0.0
    light = np.asarray(LIGHT) / np.linalg.norm(LIGHT)
    lam = np.abs(N @ light)                                  # closed meshes show front faces; abs keeps open ones visible
    shade = 0.45 + 0.55 * lam
    base = np.asarray([PALETTE[c % len(PALETTE)] for c in range(len(meshes))], dtype=np.float64)
    fid = face[hit]
    rgb = base[C[fid]] * shade[fid][:, None]
    img[hit] = np.clip(rgb, 0, 255).astype(np.uint8)
    # Outlines: face id changes with a crease, a silhouette, or a depth jump that is larger
    # than the faces' own slopes explain (so grazing surfaces do not fill with ink).
    dz_floor = 0.005 * max(depth[hit].max() - depth[hit].min(), 1e-9) + 1e-6
    cos_limit = math.cos(math.radians(CREASE_DEG))
    slope = np.abs(N[:, :2]) / np.maximum(np.abs(N[:, 2:3]), 1e-3)      # depth change per pixel along x, y
    edge = np.zeros((height, width), dtype=bool)
    for dy, dx in ((0, 1), (1, 0)):
        a = face[:height - dy, :width - dx]
        b = face[dy:, dx:]
        da = depth[:height - dy, :width - dx]
        db = depth[dy:, dx:]
        differ = a != b
        both = (a >= 0) & (b >= 0)
        sil = differ & ~both                                 # object against background
        cr = np.zeros_like(differ)
        if both.any():
            ia, ib = a[both], b[both]
            dot = np.einsum("ij,ij->i", N[ia], N[ib])
            axis = 0 if dx else 1
            allowed = 2.5 * np.maximum(slope[ia, axis], slope[ib, axis]) + dz_floor
            jump = np.abs(da[both] - db[both]) > allowed
            cr[both] = (dot < cos_limit) | jump
        m = sil | (differ & cr)
        edge[:height - dy, :width - dx] |= m
    img[edge] = INK
    return img, float(hit.mean())


def draw_text(img, text, x, y, scale=2, colour=INK):
    """Draw `text` (upper-cased, unknown glyphs as a box) at (x, y) top-left in pixels."""
    import numpy as np
    H, W, _ = img.shape
    cx = x
    for ch in text.upper():
        cols = FONT.get(ch, (0x7F, 0x41, 0x41, 0x41, 0x7F))
        for ci, bits in enumerate(cols):
            for ri in range(7):
                if bits >> ri & 1:
                    y0, y1 = y + ri * scale, y + (ri + 1) * scale
                    x0, x1 = cx + ci * scale, cx + (ci + 1) * scale
                    if y1 <= H and x1 <= W and y0 >= 0 and x0 >= 0:
                        img[y0:y1, x0:x1] = colour
        cx += 6 * scale
    return cx


def text_width(text, scale=2):
    return 6 * scale * len(text)


def scene_frame(meshes, views):
    """Per view: the centre of the projected scene; plus the scale that fits every view."""
    import numpy as np
    centre, extent = {}, 0.0
    for v in views:
        cam = camera(*VIEWS[v])
        P = np.concatenate([project(V, cam) for _n, V, _f in meshes])
        lo, hi = P.min(axis=0), P.max(axis=0)
        centre[v] = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        extent = max(extent, hi[0] - lo[0], hi[1] - lo[1])
    return centre, max(extent, 1e-9)


def render(meshes, views, width, height, caption=None, separate=False):
    """Returns [(view_or_'grid', image (H,W,3) uint8, foreground fraction)]."""
    import numpy as np
    centre, extent = scene_frame(meshes, views)
    label_h = 14 * 2 + 8
    if separate:
        out = []
        for v in views:
            vw, vh = width, height - label_h
            scale = min(vw, vh) * (1 - 2 * MARGIN) / extent
            img, fg = shade_view(meshes, v, vw, vh, scale, centre)
            canvas = np.empty((height, width, 3), dtype=np.uint8)
            canvas[:] = BACKGROUND
            canvas[:vh] = img
            draw_text(canvas, v.upper(), 8, vh + 6)
            if caption:
                draw_text(canvas, caption, 8 + text_width(v.upper()) + 24, vh + 6)
            out.append((v, canvas, fg))
        return out
    n = len(views)
    cols = 2 if n > 1 else 1
    rows = int(math.ceil(n / cols))
    cw, ch = width // cols, (height - label_h) // rows
    scale = min(cw, ch) * (1 - 2 * MARGIN) / extent
    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[:] = BACKGROUND
    fg_total = 0.0
    for i, v in enumerate(views):
        r, c = divmod(i, cols)
        img, fg = shade_view(meshes, v, cw, ch, scale, centre)
        y0, x0 = r * ch, c * cw
        canvas[y0:y0 + ch, x0:x0 + cw] = img
        draw_text(canvas, v.upper(), x0 + 8, y0 + 8)
        fg_total += fg / n
    # thin separators
    for c in range(1, cols):
        canvas[:rows * ch, c * cw - 1:c * cw + 1] = (210, 210, 210)
    for r in range(1, rows):
        canvas[r * ch - 1:r * ch + 1, :] = (210, 210, 210)
    if caption:
        draw_text(canvas, caption, 8, rows * ch + 6)
    return [("grid", canvas, fg_total)]


def write_png(path, img):
    import numpy as np
    H, W, _ = img.shape
    raw = b"".join(b"\x00" + np.ascontiguousarray(img[r]).tobytes() for r in range(H))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def sidecar_path(image):
    return image + ".json"


def stl_hashes(stls):
    """{path: sha256} of the inputs, taken before they are read for drawing."""
    from validate import file_sha256
    return {s: file_sha256(s) if os.path.isfile(s) else None for s in stls}   # a missing one fails when read


def write_sidecar(image, stls, views, renderer, lang="en", hashes=None, proxies=None, extra=None):
    """`<image>.json`: what the image shows and the very bytes it is, so a judgement of it can be
    tied to the parts (finalize.py `_verify.seen`). Written after the image, from its bytes;
    `hashes` are the STLs' digests taken before drawing, and an STL that changed while it was
    drawn (rebuilt meanwhile) leaves the image without a sidecar: the image may show the old
    bytes, so nothing ties it to the new ones. `proxies` (render.py: stand-ins of a mating
    part drawn for context) are listed apart from `stls`, never as parts; `extra` adds keys."""
    from validate import file_sha256
    proxies = list(proxies or [])
    hashes = hashes or stl_hashes(list(stls) + proxies)
    changed = [s for s in list(stls) + proxies if file_sha256(s) != hashes[s]]
    if changed:
        raise ValueError(f"{', '.join(changed)} changed while the image was drawn; draw it again (no sidecar written)")
    data = {"schema": IMAGE_SCHEMA, "image": os.path.basename(image), "image_sha256": file_sha256(image),
            "views": list(views), "lang": lang, "renderer": renderer,
            "stls": [{"path": s, "sha256": hashes[s]} for s in stls]}
    if proxies:
        data["proxies"] = [{"path": s, "sha256": hashes[s], "role": "proxy: drawn for context, not a part"}
                           for s in proxies]
    data.update(extra or {})
    with open(sidecar_path(image), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return sidecar_path(image)


def png_sane(path, fg_fraction):
    """G4 for images: a real PNG with pixels, and something drawn in it."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(33)
    except OSError as exc:
        return False, f"cannot read back: {exc}"
    if size == 0:
        return False, "0-byte file"
    if not head.startswith(b"\x89PNG\r\n\x1a\n") or head[12:16] != b"IHDR":
        return False, "not a PNG"
    w, h = struct.unpack(">II", head[16:24])
    if w == 0 or h == 0:
        return False, "empty image"
    if fg_fraction <= 0.0005:
        return False, "blank image: nothing of the part is visible"
    return True, f"{w}x{h}, {fg_fraction * 100:.1f}% of the pixels show the part"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run(args) -> dict:
    try:
        import numpy  # noqa: F401
    except ImportError:
        raise PreviewError("preview.py needs numpy (pip install numpy)")
    views = [v.strip().lower() for v in args.views.split(",") if v.strip()]
    bad = [v for v in views if v not in VIEWS]
    if bad or not views:
        raise PreviewError(f"unknown view(s) {bad}; choose from {', '.join(VIEWS)}")
    try:
        width, height = (int(x) for x in args.size.lower().split("x"))
    except ValueError:
        raise PreviewError("--size WIDTHxHEIGHT, e.g. 1600x1200")
    if width < 200 or height < 200 or width * height > MAX_PIXELS:
        raise PreviewError("--size between 200x200 and 4096x4096")
    hashes = stl_hashes(args.stl)                     # before reading: the sidecar names the bytes drawn
    meshes = load_meshes(args.stl)
    stem, ext = os.path.splitext(args.out)
    if ext.lower() != ".png":
        raise PreviewError("-o must end in .png")
    targets = [f"{stem}_{v}.png" for v in views] if args.separate else [args.out]
    if not args.overwrite:
        for t in targets + [sidecar_path(t) for t in targets]:
            if os.path.exists(t):
                raise PreviewError(f"{t} already exists; pass --overwrite for a working file in out/, or choose a new name")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    import numpy as np
    allv = np.concatenate([V for _n, V, _f in meshes])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    size_mm = [round(float(hi[i] - lo[i]), 2) for i in range(3)]
    caption = args.label or ("%g x %g x %g mm" % tuple(size_mm))
    if len(meshes) > 1:
        caption += "   " + "  ".join(f"#{i + 1}={m[0]}" for i, m in enumerate(meshes))
    t0 = time.time()
    images = render(meshes, views, width, height, caption, args.separate)
    files, all_sane = [], True
    renderer = "numpy z-buffer (orthographic, flat shading, outlines)"
    for (view, img, fg), path in zip(images, targets):
        write_png(path, img)
        sane, note = png_sane(path, fg)
        all_sane &= sane
        shown = views if view == "grid" else [view]
        files.append({"path": path, "views": shown, "sane": sane, "note": note, "bytes": os.path.getsize(path),
                      "sidecar": write_sidecar(path, args.stl, shown, renderer, hashes=hashes)})
    return {"files": files, "parts": [{"name": m[0], "triangles": int(len(m[2])),
                                       "colour": "#%02x%02x%02x" % PALETTE[i % len(PALETTE)]} for i, m in enumerate(meshes)],
            "size_mm": size_mm, "renderer": renderer,
            "seconds": round(time.time() - t0, 2), "sane": all_sane}


def main(argv=None):
    out = {"schema": SCHEMA, "ran": False, "sane": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="preview images of STL parts (numpy software renderer)")
        ap.add_argument("stl", nargs="+")
        ap.add_argument("-o", "--out", required=True, help="PNG path (with --separate: <stem>_<view>.png)")
        ap.add_argument("--views", default=",".join(DEFAULT_VIEWS), help="comma list of " + ", ".join(VIEWS))
        ap.add_argument("--size", default="1600x1200")
        ap.add_argument("--separate", action="store_true", help="one file per view")
        ap.add_argument("--label", help="caption text (default: the size in mm)")
        ap.add_argument("--overwrite", action="store_true")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        out.update(run(args))
        out["ran"] = True
    except (PreviewError, OSError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if not out["ran"]:
        return 1
    return 0 if out["sane"] else 2


if __name__ == "__main__":
    sys.exit(main())
