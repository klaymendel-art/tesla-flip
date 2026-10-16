#!/usr/bin/env python
"""Art QA contact sheet: scene mock (portrait 1080x1920) + sprite strip. Output qa/screenshots/art_contact_sheet.png"""
from PIL import Image, ImageDraw
import pathlib
IMG = pathlib.Path("assets/img"); L = Image.LANCZOS
def load(n): return Image.open(IMG / n).convert("RGBA")
W, H = 1080, 1920
scene = Image.new("RGBA", (W, H))
d = ImageDraw.Draw(scene)
# dusk sky gradient: violet top -> warm orange at horizon
top, bot = (58, 32, 92), (242, 140, 72)
horizon = int(H * 0.62); ground = int(H * 0.78)
for y in range(ground):
    t = min(1, y / horizon); c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)); d.line([(0, y), (W, y)], fill=c + (255,))
# road
d.rectangle([0, ground, W, H], fill=(52, 52, 64, 255))
d.rectangle([0, ground, W, ground + 6], fill=(36, 36, 46, 255))
for x in range(0, W, 120): d.rectangle([x, ground + 90, x + 60, ground + 100], fill=(230, 210, 120, 255))
def tile(n, bottom_y, scale, dx=0):
    im = load(n); im = im.resize((round(im.width * scale), round(im.height * scale)), L)
    x = -dx % im.width - im.width
    while x < W:
        scene.alpha_composite(im, (x, bottom_y - im.height)); x += im.width
tile("bg_far.png", horizon + 10, 0.8, dx=200)
tile("bg_mid.png", ground + 2, 0.9, dx=600)
tile("bg_near.png", ground + 4, 0.55, dx=100)
# player: Musk height 20% of H, car width = 1.25 * musk height
ride, air, side, bottom = load("musk_ride.png"), load("musk_air.png"), load("tesla_side.png"), load("tesla_bottom.png")
mh = int(H * 0.20); s_m = mh / ride.height
ride_s = ride.resize((round(ride.width * s_m), mh), L)
air_s = air.resize((round(air.width * s_m), round(air.height * s_m)), L)
cw = int(mh * 1.25); s_c = cw / side.width
side_s = side.resize((cw, round(side.height * s_c)), L)
bottom_s = bottom.resize((cw, round(bottom.height * s_c)), L)
px = int(W * 0.30)  # player centre x
car_x = px - cw // 2; car_y = ground - side_s.height
scene.alpha_composite(side_s, (car_x, car_y))
roof_y = car_y + 1 * s_c  # Roadster roof row from build_assets (y=1 at canopy peak, x 363..500 of 900)
scene.alpha_composite(ride_s, (int(px - cw/2 + 430 * s_c) - ride_s.width // 2, int(round(roof_y)) - ride_s.height + 8))
# airborne ghost to the right: car at mid flip (bottom view squashed) + air pose
ax = int(W * 0.72); jump = int(cw * 0.33)
bs = bottom_s.resize((cw, max(1, int(bottom_s.height * 0.75))), L).transpose(Image.FLIP_TOP_BOTTOM)
scene.alpha_composite(bs, (ax - cw // 2, ground - jump - bs.height // 2 - side_s.height // 2))
scene.alpha_composite(air_s, (ax - air_s.width // 2, ground - jump - side_s.height - air_s.height + 10))
# obstacles on the road ahead, same scale as the car (s_c)
ox = int(W * 0.78)
for n in ("obst_muscle.png", "obst_pickup.png", "obst_sedan.png"):
    o = load(n); o = o.resize((round(o.width * s_c), round(o.height * s_c)), L)
    scene.alpha_composite(o, (ox - o.width // 2, ground - o.height)); ox += int(o.width * 0.55)
d = ImageDraw.Draw(scene); d.text((20, 20), "Tesla Flip - art contact sheet (scene mock 1080x1920)", fill=(255, 255, 255, 255))
# sprite strip on dusk colour
items = ["musk_ride.png", "musk_air.png", "tesla_side.png", "tesla_bottom.png", "obst_muscle.png", "obst_pickup.png", "obst_sedan.png", "icon.png"]
sh = 300; ims = []
for n in items:
    im = load(n); s = min(sh / im.height, 520 / im.width); ims.append(im.resize((round(im.width * s), round(im.height * s)), L))
strip = Image.new("RGBA", (sum(i.width for i in ims) + 30 * (len(ims) + 1), sh + 60), (0x20, 0x20, 0x40, 255))
x = 30
for im in ims: strip.alpha_composite(im, (x, sh - im.height + 30)); x += im.width + 30
bgs = [load("bg_far.png"), load("bg_mid.png"), load("bg_near.png")]
# 2-tile seam strips, scaled to strip width
bw = strip.width; seam = Image.new("RGBA", (bw, sum(round(b.height * bw / (2 * b.width)) for b in bgs) + 40), (0x20, 0x20, 0x40, 255))
y = 10
for b in bgs:
    two = Image.new("RGBA", (b.width * 2, b.height)); two.paste(b, (0, 0)); two.paste(b, (b.width, 0))
    t = two.resize((bw, round(b.height * bw / two.width)), L); seam.alpha_composite(t, (0, y)); y += t.height + 10
sheet = Image.new("RGB", (max(W + 40 + strip.width, 10), max(H, strip.height + seam.height + 40)), (24, 24, 32))
sheet.paste(scene.convert("RGB"), (0, 0)); sheet.paste(strip.convert("RGB"), (W + 40, 0)); sheet.paste(seam.convert("RGB"), (W + 40, strip.height + 20))
sheet.save("qa/screenshots/art_contact_sheet.png", optimize=True)
scene.convert("RGB").resize((390, 693), L).save("qa/screenshots/art_scene_phone.png")
print("ok", sheet.size)
