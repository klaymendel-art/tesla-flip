#!/usr/bin/env python3
"""Crude placeholder sprites so the game is testable before real art lands.

Writes PNGs into assets/img/ at the sizes from docs/DESIGN.md.
NEVER overwrites an existing file (the Art agent owns the real assets).

Usage:  python tools/placeholders.py [--out assets/img]
"""
import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = (27, 20, 48, 255)
SKIN = (240, 200, 160, 255)
HAIR = (60, 40, 30, 255)
TEE = (30, 30, 40, 255)
JEANS = (50, 70, 120, 255)
SHOE = (240, 240, 245, 255)
# Tesla Roadster: pearl white, low wedge, dark sill
CAR_BODY = (240, 240, 236, 255)
CAR_SILL = (40, 38, 50, 255)
CAR_GLASS = (40, 55, 80, 255)
TYRE = (28, 26, 34, 255)
HUB = (170, 170, 180, 255)


def limb(d, pts, width, fill):
    """Thick polyline with round joints."""
    d.line(pts, fill=OUTLINE, width=width + 10, joint="curve")
    for p in pts:
        d.ellipse([p[0] - width // 2 - 5, p[1] - width // 2 - 5, p[0] + width // 2 + 5, p[1] + width // 2 + 5], fill=OUTLINE)
    d.line(pts, fill=fill, width=width, joint="curve")
    for p in pts:
        d.ellipse([p[0] - width // 2, p[1] - width // 2, p[0] + width // 2, p[1] + width // 2], fill=fill)


def musk(air: bool) -> Image.Image:
    W, H = 520, 900
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    hip_l, hip_r = (220, 520), (300, 520)
    if air:  # knees tucked up, feet still at the bottom edge of the sprite box
        limb(d, [hip_l, (130, 640), (190, 850)], 70, JEANS)
        limb(d, [hip_r, (330, 650), (370, 850)], 70, JEANS)
        feet = [(150, 850), (340, 850)]
    else:  # skate stance, knees slightly bent
        limb(d, [hip_l, (170, 700), (160, 850)], 70, JEANS)
        limb(d, [hip_r, (340, 700), (350, 850)], 70, JEANS)
        feet = [(120, 850), (310, 850)]
    for fx, fy in feet:
        d.rounded_rectangle([fx, fy - 10, fx + 120, H - 2], radius=18, fill=SHOE, outline=OUTLINE, width=6)
    # torso
    d.rounded_rectangle([150, 260, 370, 545], radius=50, fill=TEE, outline=OUTLINE, width=8)
    # arms
    if air:
        limb(d, [(165, 300), (60, 360), (40, 440)], 55, SKIN)
        limb(d, [(355, 300), (470, 330), (500, 420)], 55, SKIN)
    else:
        limb(d, [(165, 300), (120, 420), (130, 520)], 55, SKIN)
        limb(d, [(355, 300), (400, 420), (420, 500)], 55, SKIN)
    # head (facing right)
    d.ellipse([170, 40, 360, 270], fill=SKIN, outline=OUTLINE, width=8)
    d.chord([165, 30, 365, 170], 180, 360, fill=HAIR, outline=OUTLINE, width=8)
    d.ellipse([300, 130, 322, 156], fill=OUTLINE)  # eye
    d.arc([270, 170, 340, 230], 10, 120, fill=OUTLINE, width=6)  # smirk
    return im


def tesla_side() -> Image.Image:
    W, H = 900, 330
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    body = [(30, 240), (70, 190), (210, 165), (340, 95), (560, 85), (760, 130), (870, 190), (885, 250), (850, 285), (80, 285), (40, 270)]
    d.polygon(body, fill=CAR_BODY, outline=OUTLINE)
    d.line(body + [body[0]], fill=OUTLINE, width=8, joint="curve")
    d.polygon([(80, 285), (850, 285), (840, 262), (90, 262)], fill=CAR_SILL)  # dark sill
    d.polygon([(300, 170), (360, 110), (545, 100), (660, 160)], fill=CAR_GLASS, outline=OUTLINE)
    d.line([(300, 170), (360, 110), (545, 100), (660, 160)], fill=OUTLINE, width=6, joint="curve")
    d.polygon([(800, 170), (865, 195), (870, 215), (790, 195)], fill=(255, 235, 170, 255))  # headlight
    d.polygon([(40, 210), (75, 205), (70, 235), (40, 235)], fill=(230, 60, 60, 255))  # tail light
    for cx in (225, 685):  # wheels, bottom edge = ground
        d.ellipse([cx - 64, 326 - 128, cx + 64, 326], fill=TYRE, outline=OUTLINE, width=8)
        d.ellipse([cx - 30, 262 - 30, cx + 30, 262 + 30], fill=HUB, outline=OUTLINE, width=5)
    return im


def tesla_bottom() -> Image.Image:
    W, H = 900, 330
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for cx in (255, 715):  # far-side wheels
        d.ellipse([cx - 56, 240 - 56, cx + 56, 240 + 56], fill=(70, 68, 80, 255), outline=OUTLINE, width=6)
    d.rounded_rectangle([40, 120, 880, 290], radius=70, fill=(62, 60, 74, 255), outline=OUTLINE, width=8)
    d.rounded_rectangle([170, 150, 760, 250], radius=20, fill=(40, 38, 50, 255), outline=OUTLINE, width=5)  # battery pan
    d.rectangle([410, 150, 520, 250], fill=(90, 86, 100, 255))
    for cx in (225, 685):  # near-side wheels
        d.ellipse([cx - 64, 326 - 128, cx + 64, 326], fill=TYRE, outline=OUTLINE, width=8)
        d.ellipse([cx - 22, 262 - 22, cx + 22, 262 + 22], fill=(95, 95, 110, 255), outline=OUTLINE, width=4)
    return im


def mirrored(half: Image.Image) -> Image.Image:
    """Make a horizontally tileable 2048-wide strip from a 1024-wide half."""
    out = Image.new("RGBA", (half.width * 2, half.height), (0, 0, 0, 0))
    out.paste(half, (0, 0))
    out.paste(half.transpose(Image.FLIP_LEFT_RIGHT), (half.width, 0))
    return out


def bg_far() -> Image.Image:
    rnd = random.Random(1)
    W, H = 1024, 600
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0
    while x < W:
        w = rnd.randint(40, 120)
        h = rnd.randint(120, 430)
        c = (88 + rnd.randint(-8, 8), 76 + rnd.randint(-8, 8), 150 + rnd.randint(-10, 10), 255)
        d.rectangle([x, H - h, x + w, H], fill=c)
        if rnd.random() < 0.3:
            d.line([(x + w // 2, H - h), (x + w // 2, H - h - 40)], fill=c, width=4)
        x += w + rnd.randint(0, 12)
    return mirrored(im)


def bg_mid() -> Image.Image:
    rnd = random.Random(2)
    W, H = 1024, 700
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0
    while x < W:
        w = rnd.randint(90, 200)
        h = rnd.randint(220, 620)
        c = (58 + rnd.randint(-10, 10), 48 + rnd.randint(-8, 8), 98 + rnd.randint(-12, 12), 255)
        d.rectangle([x, H - h, x + w, H], fill=c, outline=OUTLINE, width=4)
        for wy in range(H - h + 30, H - 40, 46):
            for wx in range(x + 18, x + w - 24, 34):
                if rnd.random() < 0.6:
                    d.rectangle([wx, wy, wx + 16, wy + 24], fill=(255, 214, 120, 255))
        x += w + rnd.randint(8, 30)
    return mirrored(im)


def bg_near() -> Image.Image:
    W, H = 1024, 300
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 190, W, H], fill=(120, 115, 140, 255))
    d.rectangle([0, 190, W, 202], fill=(170, 165, 190, 255))
    for px in (120, 460, 800):
        d.rectangle([px - 6, 30, px + 6, 192], fill=(40, 36, 56, 255))
        d.ellipse([px - 22, 10, px + 22, 54], fill=(255, 225, 150, 255), outline=OUTLINE, width=4)
    for bx in (290, 630, 960):
        d.ellipse([bx - 45, 140, bx + 45, 200], fill=(60, 110, 70, 255), outline=OUTLINE, width=4)
    return mirrored(im)


def icon() -> Image.Image:
    im = Image.new("RGBA", (512, 512), (36, 26, 77, 255))
    d = ImageDraw.Draw(im)
    car = tesla_side().resize((440, 161), Image.LANCZOS)
    im.alpha_composite(car, (36, 300))
    d.ellipse([170, 70, 340, 270], fill=SKIN, outline=OUTLINE, width=10)
    d.chord([165, 60, 345, 180], 180, 360, fill=HAIR, outline=OUTLINE, width=10)
    d.ellipse([285, 150, 305, 175], fill=OUTLINE)
    return im


def obstacle(kind: str) -> Image.Image:
    """Old V8 gas car placeholders, facing LEFT (nose at x=0), wheels on the bottom edge."""
    if kind == "pickup":
        W, H = 1000, 420
        body = (110, 125, 85, 255)
        hood = [(20, 300), (40, 230), (330, 215), (330, 300)]
        cab = [(330, 215), (400, 90), (600, 90), (620, 215)]
        bed = [(620, 215), (980, 200), (985, 300), (620, 300)]
        glass = [(410, 110), (590, 110), (600, 200), (360, 200)]
        wheels, r = (220, 790), 72
    elif kind == "sedan":
        W, H = 900, 340
        body = (175, 150, 110, 255)
        hood = [(20, 240), (40, 170), (260, 160), (260, 240)]
        cab = [(260, 160), (320, 70), (600, 70), (660, 160)]
        bed = [(660, 160), (870, 170), (885, 240), (660, 240)]
        glass = [(330, 90), (590, 90), (630, 155), (290, 155)]
        wheels, r = (200, 700), 62
    else:  # muscle
        W, H = 900, 330
        body = (240, 130, 30, 255)
        hood = [(15, 230), (35, 150), (310, 140), (310, 230)]
        cab = [(310, 140), (380, 70), (620, 70), (700, 150)]
        bed = [(700, 150), (880, 165), (890, 230), (700, 230)]
        glass = [(390, 90), (610, 90), (670, 145), (340, 145)]
        wheels, r = (210, 690), 64
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    floor = H - r  # wheel centre line; wheels touch the bottom edge
    for poly in (hood, cab, bed):
        d.polygon(poly, fill=body, outline=OUTLINE)
        d.line(poly + [poly[0]], fill=OUTLINE, width=8, joint="curve")
    d.rectangle([hood[0][0] + 10, hood[0][1] + 40, bed[2][0] - 10, floor + 10], fill=body, outline=OUTLINE, width=6)
    d.polygon(glass, fill=CAR_GLASS, outline=OUTLINE)
    d.rectangle([hood[0][0] + 10, hood[0][1] - 10, hood[0][0] + 50, hood[0][1] + 25], fill=(255, 235, 170, 255), outline=OUTLINE, width=4)
    d.rectangle([bed[2][0] - 20, bed[2][1] - 70, bed[2][0] + 12, bed[2][1] - 30], fill=(60, 60, 70, 255), outline=OUTLINE, width=4)  # exhaust
    for cx in wheels:
        d.ellipse([cx - r, floor - r, cx + r, H - 2], fill=TYRE, outline=OUTLINE, width=8)
        d.ellipse([cx - r // 2, floor - r // 2, cx + r // 2, floor + r // 2], fill=HUB, outline=OUTLINE, width=5)
    return im


GENERATORS = {
    "musk_ride.png": lambda: musk(False),
    "musk_air.png": lambda: musk(True),
    "tesla_side.png": tesla_side,
    "tesla_bottom.png": tesla_bottom,
    "bg_far.png": bg_far,
    "bg_mid.png": bg_mid,
    "bg_near.png": bg_near,
    "icon.png": icon,
    "obst_muscle.png": lambda: obstacle("muscle"),
    "obst_pickup.png": lambda: obstacle("pickup"),
    "obst_sedan.png": lambda: obstacle("sedan"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "assets" / "img"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, gen in GENERATORS.items():
        path = out / name
        if path.exists():
            print(f"skip   {path} (exists)")
            continue
        img = gen()
        # Re-check right before writing: the Art agent may have landed the file meanwhile.
        if path.exists():
            print(f"skip   {path} (appeared)")
            continue
        img.save(path, optimize=True)
        print(f"create {path} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
