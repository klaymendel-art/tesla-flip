#!/usr/bin/env python
"""Roll frames for the Roadster from the two generated 45-degree views.
For a car mirror-symmetric about its longitudinal vertical plane, roll(theta) flipped vertically == roll(180-theta):
  135 = gen135            045 = gen135 flipped vertically
  315 = gen315            225 = gen315 flipped vertically
All frames 900 px wide, alpha-bbox centred on the same x as tesla_side, quantised like the other sprites.
Also renders qa/screenshots/art_roll_strip.png (000 045 090 135 180 225 270 315 000 on the road colour)."""
import pathlib, numpy as np
from PIL import Image, ImageDraw
IMG = pathlib.Path("assets/img"); RAW = pathlib.Path("tools/_raw"); L = Image.LANCZOS
def load(p): return Image.open(p).convert("RGBA")
def bbox_cx(im):
    b = im.getbbox(); return (b[0] + b[2]) / 2
side = load(IMG / "tesla_side.png"); target_cx = bbox_cx(side)  # 900-wide sprite, body centre
def fit(im, scale=1.0):
    """scale to 900 wide (times an optional uniform tweak) and place on a 900-wide canvas with the body centre at target_cx"""
    b = im.getbbox(); im = im.crop(b)
    w = round(900 * scale); h = round(im.height * w / im.width)
    im = im.resize((w, h), L)
    canvas = Image.new("RGBA", (900, h), (0, 0, 0, 0))
    x = round(target_cx - w / 2); canvas.alpha_composite(im, (max(0, x), 0)) if x >= 0 else canvas.alpha_composite(im.crop((-x, 0, -x + 900, h)), (0, 0))
    return canvas
g135 = load(RAW / "roll_135_cut.png"); g315 = load(RAW / "roll_315_cut.png")
frames = {135: fit(g135), 45: fit(g135.transpose(Image.FLIP_TOP_BOTTOM)),
          315: fit(g315), 225: fit(g315.transpose(Image.FLIP_TOP_BOTTOM))}
for ang, fr in frames.items():
    p = IMG / f"tesla_roll_{ang:03d}.png"
    fr.quantize(256, method=Image.FASTOCTREE, dither=Image.FLOYDSTEINBERG).save(p, optimize=True)
    a = np.asarray(fr)[:, :, 3] > 128; rows = np.where(a.any(axis=1))[0]; cols = np.where(a.any(axis=0))[0]
    print(f"tesla_roll_{ang:03d}.png 900x{fr.height} {p.stat().st_size // 1024} KB  body rows {rows.min()}..{rows.max()} (centre y={(rows.min()+rows.max())/2:.1f})  body x {cols.min()}..{cols.max()} (cx={(cols.min()+cols.max())/2:.1f})")
# strip
seq = [("000", side), ("045", frames[45]), ("090", load(IMG / "tesla_bottom.png")), ("135", frames[135]),
       ("180", side.transpose(Image.FLIP_TOP_BOTTOM)), ("225", frames[225]), ("270", load(IMG / "tesla_top.png")), ("315", frames[315]), ("000", side)]
s = 0.36; cell = 340; H = 300
row = Image.new("RGBA", (cell * len(seq), H), (52, 52, 64, 255)); d = ImageDraw.Draw(row)
for i, (name, im) in enumerate(seq):
    im2 = im.resize((round(im.width * s), round(im.height * s)), L)
    row.alpha_composite(im2, (i * cell + (cell - im2.width) // 2, H // 2 - im2.height // 2)); d.text((i * cell + 8, 6), name, fill=(255, 255, 255, 255))
row.convert("RGB").save("qa/screenshots/art_roll_strip.png"); print("strip saved qa/screenshots/art_roll_strip.png", row.size)
