#!/usr/bin/env python3
"""
video_to_ascii.py — turn a short clip into a looping ASCII-art GIF.

Tuned for cartoons: the background is removed by color-keying against
the dominant corner colors (flat cel backgrounds key cleanly — no ML
model needed), character density follows luminance through a darkening
curve, and each glyph is filled with its cell's own color, floored so
dark features (outlines, ears) stay visible on the dark page.

usage: python3 scripts/video_to_ascii.py input.mp4 assets/out.gif
"""

import math
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

RAMP = " .`:-=+*cs#%@"
COLS = 104
CELL_W, CELL_H = 8, 15
FPS = 12.5
BG = None  # taken from the source background — the cel keeps its wall
KEY_DIST = 58          # color distance below which a pixel is "background"
MIN_GLYPH = 1          # foreground cells never drop off the ramp entirely
INK = 0.85             # density follows darkness — cartoons are ink drawings


def bg_colors(img):
    """Sample the frame's corners; cartoons have 1–2 flat background colors."""
    w, h = img.size
    pts = [(4, 4), (w - 5, 4), (4, h - 5), (w - 5, h - 5),
           (w // 2, 4), (4, h // 2), (w - 5, h // 2)]
    cols = [img.getpixel(p)[:3] for p in pts]
    keys = []
    for c in cols:
        if all(dist(c, k) > 40 for k in keys):
            keys.append(c)
    return keys[:3]


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def subject_bbox(frames, keys):
    """The figure should fill the grid: union bounding box of the
    non-background pixels across every frame, plus a little air."""
    x0 = y0 = 10**9
    x1 = y1 = -1
    for img in frames:
        small = img.resize((120, round(120 * img.size[1] / img.size[0])), Image.LANCZOS)
        w, h = small.size
        for y in range(h):
            for x in range(w):
                if not any(dist(small.getpixel((x, y))[:3], k) < KEY_DIST for k in keys):
                    x0, y0 = min(x0, x), min(y0, y)
                    x1, y1 = max(x1, x), max(y1, y)
        # sampling a few frames is enough for a stable box
    W, H = frames[0].size
    sx, sy = W / w, H / h
    pad = 0.05
    bx0 = max(0, int(x0 * sx - W * pad))
    by0 = max(0, int(y0 * sy - H * pad))
    bx1 = min(W, int((x1 + 1) * sx + W * pad))
    by1 = min(H, int((y1 + 1) * sy + H * pad))
    return bx0, by0, bx1, by1


def saturate(px, f=1.6):
    lum = 0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2]
    return tuple(max(0, min(255, int(lum + (v - lum) * f))) for v in px)


def frame_to_cells(img, keys, box):
    img = img.crop(box)
    w, h = img.size
    rows = round(COLS * (h / w) * (CELL_W / CELL_H))
    small = img.resize((COLS, rows), Image.NEAREST)  # point-sample: cel colors stay pure
    cells = []
    for r in range(rows):
        row = []
        for c in range(COLS):
            px = small.getpixel((c, r))[:3]
            if any(dist(px, k) < KEY_DIST for k in keys):
                row.append(None)
                continue
            # the silhouette is the message: every foreground cell is dense,
            # and COLOR does the drawing — white body, dark ear, red cap
            lum = (0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2]) / 255
            idx = 7 + min(5, round(lum * 5))
            sat = max(px) - min(px)
            if lum < 0.24:
                fill = (24, 24, 28)            # true black ink — it pops on the wall
                idx = 12
            elif px[0] > px[1] + 26 and px[0] > px[2] + 26:
                fill = (235, 48, 52)           # the cap: unmistakably red
                idx = 11
            elif sat < 46 and lum > 0.55:
                fill = (240, 240, 240)         # the body: pure Snoopy white
            else:
                fill = saturate(px)
            row.append((RAMP[idx], fill))
        cells.append(row)
    # despeckle: a cell with no foreground neighbors is keying noise
    for r in range(rows):
        for c in range(COLS):
            if cells[r][c] is None:
                continue
            n = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr or dc) and 0 <= r + dr < rows and 0 <= c + dc < COLS \
                            and cells[r + dr][c + dc] is not None:
                        n += 1
            if n <= 1:
                cells[r][c] = None
    return cells


def render(cells_list, font, wall):
    rows = len(cells_list[0])
    images = []
    for cells in cells_list:
        img = Image.new("RGB", (COLS * CELL_W, rows * CELL_H), wall)
        drw = ImageDraw.Draw(img)
        for r, row in enumerate(cells):
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                ch, fill = cell
                if ch != " ":
                    # double-strike: thin glyph strokes read as mass, not mist
                    drw.text((c * CELL_W, r * CELL_H), ch, fill=fill, font=font)
                    drw.text((c * CELL_W + 1, r * CELL_H), ch, fill=fill, font=font)
        images.append(img)
    return images


def main():
    src, out = sys.argv[1], sys.argv[2]
    font = None
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, 13)
            break
    if font is None:
        font = ImageFont.load_default()

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
             "-vf", f"fps={FPS}", os.path.join(tmp, "f%04d.png")],
            check=True,
        )
        names = sorted(os.listdir(tmp))
        frames = [Image.open(os.path.join(tmp, f)).convert("RGB") for f in names]
        keys = bg_colors(frames[0])
        box = subject_bbox(frames[::6] or frames[:1], keys)
        cells_list = [frame_to_cells(f, keys, box) for f in frames]

    wall = tuple(int(v * 0.66) for v in keys[0])
    images = render(cells_list, font, wall)
    images[0].save(out, save_all=True, append_images=images[1:],
                   duration=int(1000 / FPS), loop=0, optimize=True)
    print(f"wrote {out}: {len(images)} frames, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
