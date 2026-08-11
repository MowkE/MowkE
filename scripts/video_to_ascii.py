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
COLS = 84
CELL_W, CELL_H = 8, 15
FPS = 12.5
BG = (8, 8, 8)
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


def frame_to_cells(img, keys):
    w, h = img.size
    rows = round(COLS * (h / w) * (CELL_W / CELL_H))
    small = img.resize((COLS, rows), Image.LANCZOS)
    cells = []
    for r in range(rows):
        row = []
        for c in range(COLS):
            px = small.getpixel((c, r))[:3]
            if any(dist(px, k) < KEY_DIST for k in keys):
                row.append(None)
                continue
            lum = (0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2]) / 255
            ink = (1 - lum) ** INK
            idx = max(MIN_GLYPH, min(int(ink * (len(RAMP) - 1) + 0.5), len(RAMP) - 1))
            # lift fills hard so black ink reads pale-bright on the dark page
            lift = 110
            fill = tuple(min(255, int(v + (lift * (1 - v / 255)))) for v in px)
            row.append((RAMP[idx], fill))
        cells.append(row)
    return cells


def render(cells_list, font):
    rows = len(cells_list[0])
    images = []
    for cells in cells_list:
        img = Image.new("RGB", (COLS * CELL_W, rows * CELL_H), BG)
        drw = ImageDraw.Draw(img)
        for r, row in enumerate(cells):
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                ch, fill = cell
                if ch != " ":
                    drw.text((c * CELL_W, r * CELL_H), ch, fill=fill, font=font)
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
        frames = sorted(os.listdir(tmp))
        first = Image.open(os.path.join(tmp, frames[0])).convert("RGB")
        keys = bg_colors(first)
        cells_list = [frame_to_cells(Image.open(os.path.join(tmp, f)).convert("RGB"), keys)
                      for f in frames]

    images = render(cells_list, font)
    images[0].save(out, save_all=True, append_images=images[1:],
                   duration=int(1000 / FPS), loop=0, optimize=True)
    print(f"wrote {out}: {len(images)} frames, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
