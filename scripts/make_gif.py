#!/usr/bin/env python3
"""
make_gif.py — the profile centerpiece: a tesseract rotating through the
4th dimension, drawn as ASCII, colored by its w coordinate, looping
forever. Runs locally, commits the GIF; the nightly action never needs
to touch it.

The pipeline: rotate the 16 vertices in 4D -> project 4D->3D (perspective
from a w-camera) -> project 3D->2D -> splat the 32 edges onto a coarse
character grid, accumulating brightness and mean w per cell -> map
brightness to a 13-character ramp and w to the thermal palette
(blue = behind in w, red = ahead), exactly like HYPERSHAPE.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

# ── the tesseract ──────────────────────────────────────────────────────────
VERTS = [[(i >> b & 1) * 2 - 1 for b in range(4)] for i in range(16)]
EDGES = [(i, j) for i in range(16) for j in range(i + 1, 16)
         if sum(a != b for a, b in zip(VERTS[i], VERTS[j])) == 1]

RAMP = " .`:-=+*cs#%@"
COLS, ROWS = 76, 40
CELL_W, CELL_H = 9, 15
FRAMES = 90
TAU = math.tau


def rot(plane_a, plane_b, theta, v):
    c, s = math.cos(theta), math.sin(theta)
    v = list(v)
    v[plane_a], v[plane_b] = c * v[plane_a] - s * v[plane_b], s * v[plane_a] + c * v[plane_b]
    return v


def thermal(w):
    """w in [-1, 1] -> blue / warm gray / red, HYPERSHAPE's palette."""
    t = max(-1.0, min(1.0, w))
    if t < 0:
        f = -t
        return (int(158 - 107 * f), int(158 - 69 * f), int(168 + 74 * f))
    f = t
    return (int(158 + 84 * f), int(158 - 94 * f), int(168 - 127 * f))


def project(v, t):
    # 4D rotation: one full turn in XW and ZW per loop -> seamless
    v = rot(0, 3, TAU * t, v)
    v = rot(2, 3, TAU * t, v)
    # 4D -> 3D perspective from a camera on the w axis
    d4 = 3.0
    s = d4 / max(d4 - v[3], 0.4)
    x, y, z = v[0] * s, v[1] * s, v[2] * s
    # slow full-turn 3D yaw, fixed pitch
    yaw, pitch = TAU * t + 0.5, 0.42
    x, z = math.cos(yaw) * x + math.sin(yaw) * z, -math.sin(yaw) * x + math.cos(yaw) * z
    y, z = math.cos(pitch) * y - math.sin(pitch) * z, math.sin(pitch) * y + math.cos(pitch) * z
    # 3D -> 2D perspective
    d3 = 6.0
    p = d3 / max(d3 - z, 1.0)
    return x * p, y * p, v[3]


def frame_grid(t):
    bright = [[0.0] * COLS for _ in range(ROWS)]
    wsum = [[0.0] * COLS for _ in range(ROWS)]
    pts = [project(v, t) for v in VERTS]
    W, H = COLS * CELL_W, ROWS * CELL_H
    scale = 0.155  # NDC scale chosen so the far-w "outer cube" always fits

    def splat(x, y, w, amount):
        # map through pixel space so the character aspect handles itself,
        # then deposit bilinearly across the 2x2 neighboring cells
        px = (x * scale + 0.5) * W / CELL_W - 0.5
        py = (y * scale + 0.5) * H / CELL_H - 0.5
        ci, ri = int(math.floor(px)), int(math.floor(py))
        fx, fy = px - ci, py - ri
        for dr, dc, wgt in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)),
                            (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
            r, c = ri + dr, ci + dc
            if 0 <= r < ROWS and 0 <= c < COLS:
                bright[r][c] += amount * wgt
                wsum[r][c] += w * amount * wgt

    for a, b in EDGES:
        (x0, y0, w0), (x1, y1, w1) = pts[a], pts[b]
        n = 150
        for k in range(n + 1):
            f = k / n
            splat(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, w0 + (w1 - w0) * f, 1.0)
    for x, y, w in pts:
        splat(x, y, w, 10.0)
    return bright, wsum


def render(font):
    images = []
    for fi in range(FRAMES):
        t = fi / FRAMES
        bright, wsum = frame_grid(t)
        img = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H), (6, 6, 6))
        drw = ImageDraw.Draw(img)
        for r in range(ROWS):
            for c in range(COLS):
                b = bright[r][c]
                if b <= 0.6:
                    continue
                idx = min(int(b / 1.5), len(RAMP) - 1)
                ch = RAMP[idx]
                if ch == " ":
                    continue
                w = wsum[r][c] / b
                drw.text((c * CELL_W, r * CELL_H), ch, fill=thermal(w), font=font)
        images.append(img)
    return images


def main():
    font = None
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/System/Library/Fonts/Monaco.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, 13)
            break
    if font is None:
        font = ImageFont.load_default()

    images = render(font)
    out = os.path.join(os.path.dirname(__file__), "..", "assets", "tesseract.gif")
    images[0].save(
        out, save_all=True, append_images=images[1:],
        duration=55, loop=0, optimize=True,
    )
    print(f"wrote {out}: {FRAMES} frames, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
