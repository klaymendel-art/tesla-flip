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

def strip_ground_rows(im, frac=0.35, max_rows=10):
    """leftover ground line: bottom rows whose opaque width exceeds `frac` of the sprite width (tyre contact
    patches never do) are cleared together with every row below them, then the sprite is re-trimmed so the
    wheels end exactly on the bottom edge"""
    a = np.asarray(im).copy(); h, w = a.shape[:2]
    line_rows = [y for y in range(h - 1, h - 1 - max_rows, -1) if (a[y, :, 3] > 8).sum() > frac * w]
    if not line_rows: return im
    top = min(line_rows); a[top:, :, 3] = 0
    out = Image.fromarray(a, "RGBA").crop(Image.fromarray(a, "RGBA").getbbox())
    print(f"  stripped ground line: rows {top}..{h-1} cleared, new height {out.height}")
    return out

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
ride = Image.open(RAW / "musk_ride3_cut.png").convert("RGBA")  # v3 skate stance (pro model), feet levelled
s_ride = 900 / ride.height
ride = ride.resize((round(ride.width * s_ride), 900), L)
air = Image.open(RAW / "musk_air3_cut.png").convert("RGBA")  # v3 tuck
# enclosed white between the tucked legs -> transparent; keep the white shoe soles (components reaching the bottom 10%)
import sys; sys.path.insert(0, "tools"); from cutout import enclosed_bottom_components, border_flood
_a = np.asarray(air).astype(np.int16); _nw = (_a[..., 3] > 128) & (_a[..., :3].min(axis=2) >= 225)
_bg = np.zeros_like(_nw); _m = enclosed_bottom_components(_nw, _bg, bottom_frac=1.0, min_px=40)
_h = _nw.shape[0]; _keep = np.zeros_like(_m)
from collections import deque as _dq
_seen = np.zeros_like(_m)
for _y0, _x0 in zip(*np.nonzero(_m)):
    if _seen[_y0, _x0]: continue
    _q = _dq([(_y0, _x0)]); _seen[_y0, _x0] = True; _c = []
    while _q:
        _y, _x = _q.popleft(); _c.append((_y, _x))
        for _ny, _nx in ((_y-1,_x),(_y+1,_x),(_y,_x-1),(_y,_x+1)):
            if 0 <= _ny < _h and 0 <= _nx < _m.shape[1] and _m[_ny, _nx] and not _seen[_ny, _nx]: _seen[_ny, _nx] = True; _q.append((_ny, _nx))
    if max(c[0] for c in _c) >= _h * 0.9 or min(c[0] for c in _c) < _h * 0.62:  # soles, and anything above the legs (shirt print)
        for _y, _x in _c: _keep[_y, _x] = True
_m &= ~_keep
_arr = np.asarray(air).copy(); _arr[..., 3][_m] = 0; air = Image.fromarray(_arr, "RGBA")
print(f"musk_air: cleared {int(_m.sum())} enclosed white px between the legs, kept {int(_keep.sum())} sole px")
s_air = s_ride * 0.925  # v3 air head is ~8% larger than v3 ride head -> equalise
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
side = strip_ground_rows(side)
bot = Image.open(RAW / "roadster_bottom_cut.png").convert("RGBA")
bot = bot.resize((900, round(bot.height * 900 / bot.width)), L)
save(side, "tesla_side.png", quant=True); save(bot, "tesla_bottom.png", quant=True)
# top view: 900 wide, padded (transparent, centred) to the bottom view's height so dev can swap top/bottom 1:1
top = Image.open(RAW / "roadster_top_cut.png").convert("RGBA")
top = top.resize((900, round(top.height * 900 / top.width)), L)
canvas = Image.new("RGBA", (900, bot.height), (0, 0, 0, 0)); canvas.alpha_composite(top, (0, (bot.height - top.height) // 2))
save(canvas, "tesla_top.png", quant=True)
print(f"tesla_top: car body rows {(bot.height - top.height) // 2}..{(bot.height - top.height) // 2 + top.height - 1} inside {bot.height} tall canvas")
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
def clean_bottom_rows(im, rows=8, thr=200):
    """QA D1: no light pixels may survive under the tyres (ground-line remnants) -> clear pale pixels in the last rows"""
    a = np.asarray(im).copy(); band = a[-rows:]
    pale = band[..., :3].min(axis=2) >= thr
    band[..., 3][pale] = 0; a[-rows:] = band
    return Image.fromarray(a, "RGBA")

def paint_enclosed_white(im, top_frac=0.6, min_px=1500):
    """repaint large enclosed near-white regions in the upper body (e.g. a window the generator left white)
    with the sprite's own glass colour (median of neutral light-grey opaque pixels)"""
    a = np.asarray(im).copy(); h, w = a.shape[:2]
    rgb = a[..., :3].astype(int); al = a[..., 3]
    nw = (al > 128) & (rgb.min(axis=2) >= 225); nw[int(h * top_frac):] = False
    glass_sel = (al == 255) & (rgb.min(axis=2) >= 150) & (rgb.min(axis=2) <= 215) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 30)
    if not nw.any() or not glass_sel.any(): return im
    glass = np.median(rgb[glass_sel], axis=0).astype(np.uint8)
    from collections import deque
    seen = np.zeros_like(nw); painted = 0
    for y0, x0 in zip(*np.nonzero(nw)):
        if seen[y0, x0]: continue
        q = deque([(y0, x0)]); seen[y0, x0] = True; comp = []
        while q:
            y, x = q.popleft(); comp.append((y, x))
            for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                if 0 <= ny < h and 0 <= nx < w and nw[ny, nx] and not seen[ny, nx]: seen[ny, nx] = True; q.append((ny, nx))
        if len(comp) >= min_px:
            for y, x in comp: a[y, x, :3] = glass
            painted += len(comp)
    if painted: print(f"  repainted {painted} enclosed white px with glass colour {tuple(int(v) for v in glass)}")
    return Image.fromarray(a, "RGBA")

for n, w in (("obst_muscle", 940), ("obst_pickup", 1000), ("obst_sedan", 900)):
    im = clean_bottom_rows(drop_ground_line(Image.open(RAW / f"{n}_cut.png").convert("RGBA")))
    if n == "obst_muscle": im = paint_enclosed_white(im)
    im = strip_ground_rows(im.resize((w, round(im.height * w / im.width)), L))
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
