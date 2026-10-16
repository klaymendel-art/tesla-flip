#!/usr/bin/env python
"""Assemble final game sprites from tools/_raw/*_cut.png into assets/img/.
Scales, matches widths, mirrors background layers for seamless tiling, optimises PNGs.
Run after tools/cutout.py. Prints final sizes + the car roof row for the Dev."""
import pathlib, numpy as np
from PIL import Image

RAW = pathlib.Path("tools/_raw"); OUT = pathlib.Path("assets/img"); OUT.mkdir(parents=True, exist_ok=True)
L = Image.LANCZOS

def save(im, name, quant=False):
    p = OUT / name
    if quant:
        q = im.quantize(256, method=Image.FASTOCTREE, dither=Image.FLOYDSTEINBERG)
        q.save(p, optimize=True)
    else:
        im.save(p, optimize=True)
    print(f"{name:18s} {im.size[0]}x{im.size[1]}  {p.stat().st_size//1024} KB")
    return im

def strip_soft_bottom(im):
    """drop feathered bottom rows so a tiled ground layer has a hard base edge"""
    a = np.asarray(im)[:, :, 3]
    h = a.shape[0]
    while h > 0 and (a[h-1] == 255).mean() < 0.98: h -= 1
    return im.crop((0, 0, im.width, h))

def tile_mirror(im, width=2048):
    """append a horizontally mirrored copy -> seamless at both joins; resize to target width"""
    m = Image.new("RGBA", (im.width * 2, im.height))
    m.paste(im, (0, 0)); m.paste(im.transpose(Image.FLIP_LEFT_RIGHT), (im.width, 0))
    h = round(m.height * width / m.width)
    return m.resize((width, h), L)

# --- Musk: ride pose normalised to 900 px tall; air pose scaled so head size matches (measured face h 286 vs 252)
ride = Image.open(RAW / "musk_ride_cut.png").convert("RGBA")
s_ride = 900 / ride.height
ride = ride.resize((round(ride.width * s_ride), 900), L)
air = Image.open(RAW / "musk_air_cut.png").convert("RGBA")
s_air = s_ride * (286 / 252)
air = air.resize((round(air.width * s_air), round(air.height * s_air)), L)
save(ride, "musk_ride.png", quant=True); save(air, "musk_air.png", quant=True)

# --- Car: both views 900 px wide
def drop_ground_line(im, max_h=14):
    """generator sometimes draws a thin ground line under the wheels: drop a bottom component <= max_h rows tall separated by a gap"""
    a = np.asarray(im)[:, :, 3] > 40
    rows = a.any(axis=1); y = im.height - 1
    while y >= 0 and rows[y]: y -= 1
    run = im.height - 1 - y
    if 0 < run <= max_h and y > 0 and not rows[y]:
        gap = y
        while gap >= 0 and not rows[gap]: gap -= 1
        return im.crop((0, 0, im.width, gap + 1)).crop(im.crop((0, 0, im.width, gap + 1)).getbbox())
    return im
side = drop_ground_line(Image.open(RAW / "roadster_side_cut.png").convert("RGBA"))
side = side.resize((900, round(side.height * 900 / side.width)), L)
bot = Image.open(RAW / "roadster_bottom_cut.png").convert("RGBA")
bot = bot.resize((900, round(bot.height * 900 / bot.width)), L)
save(side, "tesla_side.png", quant=True); save(bot, "tesla_bottom.png", quant=True)
# roof row: first row with alpha>128 at the horizontal centre, and the flattest roof span
a = np.asarray(side)[:, :, 3] > 128
cx = side.width // 2
roof_center = int(np.argmax(a[:, cx]))
tops = np.array([np.argmax(a[:, x]) if a[:, x].any() else 10**6 for x in range(a.shape[1])])
flat = np.where(tops <= tops.min() + 4)[0]
print(f"tesla_side: roof row at centre x={cx}: y={roof_center}; highest point y={tops.min()} at x={int(np.argmin(tops))}; "
      f"flat roof (within 4px) spans x={flat.min()}..{flat.max()}; top y at x=300/450/600: {tops[300]}/{tops[450]}/{tops[600]}")
# wheel contact: last row with any alpha>128
print(f"tesla_side: wheel bottom row y={int(np.where(a.any(axis=1))[0].max())} of {side.height}")

# --- Obstacles (old gas cars, facing LEFT): widths chosen so the 900-wide Roadster stays the lowest/sleekest
for n, w in (("obst_muscle", 940), ("obst_pickup", 1000), ("obst_sedan", 900)):
    im = drop_ground_line(Image.open(RAW / f"{n}_cut.png").convert("RGBA"))
    im = im.resize((w, round(im.height * w / im.width)), L)
    save(im, f"{n}.png", quant=True)
    aa = np.asarray(im)[:, :, 3] > 128
    print(f"  {n}: wheel bottom row y={int(np.where(aa.any(axis=1))[0].max())} of {im.height}")

# --- Backgrounds: hard base edge, mirror-tile, 2048 wide
for n in ("bg_far", "bg_mid", "bg_near"):
    im = strip_soft_bottom(Image.open(RAW / f"{n}_cut.png").convert("RGBA"))
    save(tile_mirror(im), f"{n}.png", quant=True)

# --- Icon: square pad + 512
ic = Image.open(RAW / "icon_v2.png").convert("RGB")  # v2 fills the square edge to edge, opaque
save(ic.resize((512, 512), L), "icon.png", quant=True)

# musk feet row (last opaque row) for pivot info
for n, im in (("musk_ride", ride), ("musk_air", air)):
    aa = np.asarray(im)[:, :, 3] > 128
    cols = np.where(aa.any(axis=0))[0]
    print(f"{n}: feet bottom row y={int(np.where(aa.any(axis=1))[0].max())} of {im.height}; content x={cols.min()}..{cols.max()}")
