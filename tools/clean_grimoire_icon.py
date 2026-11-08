"""One-off: turns a screenshot-style book icon into a clean transparent 64x64 base for the grimoire icons.
    python tools/clean_grimoire_icon.py "C:/path/New Project(11).png"   ->  tools/assets/grimoire_base.png
"""
import colorsys
import os
import sys
from collections import deque

from PIL import Image

src = sys.argv[1]
im = Image.open(src).convert("RGBA")
w, h = im.size
px = im.load()


def bg_like(p):
    r, g, b, a = p
    hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return a == 0 or (s < 0.45 and v < 0.42) or (s < 0.2 and v > 0.4)  # dark navy backdrop or grey/white frame lines


seen = [[False] * w for _ in range(h)]
q = deque()
for x in range(w):
    for y in (0, h - 1):
        q.append((x, y))
for y in range(h):
    for x in (0, w - 1):
        q.append((x, y))
while q:
    x, y = q.popleft()
    if not (0 <= x < w and 0 <= y < h) or seen[y][x] or not bg_like(px[x, y]):
        continue
    seen[y][x] = True
    px[x, y] = (0, 0, 0, 0)
    q.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

im = im.crop(im.getbbox())
side = max(im.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
out = canvas.resize((64, 64), Image.LANCZOS)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"), exist_ok=True)
out.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "grimoire_base.png"))
print("cropped", im.size, "-> 64x64")
