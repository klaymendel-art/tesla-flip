#!/usr/bin/env python
"""Remove white background from a generated sprite.
Usage: python tools/cutout.py in.png out.png [--tol 35] [--feather 1] [--erode 0] [--no-trim] [--preview preview.png]
Flood-fills near-white pixels connected to the image border (so interior whites survive),
sets them to alpha 0, feathers the edge by distance, optionally erodes alpha by N px
(halo fix), un-premultiplies colour fringe, trims to bounding box."""
import argparse, numpy as np
from PIL import Image, ImageFilter
from collections import deque

def border_flood(near_white):
    h, w = near_white.shape
    mask = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near_white[y, x] and not mask[y, x]:
                mask[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near_white[y, x] and not mask[y, x]:
                mask[y, x] = True; q.append((y, x))
    # scanline-ish BFS using numpy row ops would be faster, but BFS is fine for 1-2k px
    while q:
        y, x = q.popleft()
        for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
            if 0 <= ny < h and 0 <= nx < w and near_white[ny, nx] and not mask[ny, nx]:
                mask[ny, nx] = True; q.append((ny, nx))
    return mask

def cutout(src, tol=35, feather=1, erode=0, trim=True, global_white=False, key=None):
    im = Image.open(src).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    if key is not None:
        # chroma key: distance to key colour (max channel diff) within tol
        near_white = (np.abs(a - np.array(key, np.int16)).max(axis=2) <= tol)
    else:
        near_white = (a.min(axis=2) >= 255 - tol)
    # chroma key is global (the key colour never legitimately occurs inside the art); white uses border flood
    bg = near_white if key is not None else border_flood(near_white)
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    if global_white:
        # layers with no legit interior white (e.g. glow strips): fade ALL pale pixels by paleness
        mn = a.min(axis=2)
        soft_a = np.clip((255 - mn) / float(tol), 0, 1)
        alpha = np.minimum(alpha, (soft_a * 255).astype(np.uint8))
    al = Image.fromarray(alpha, "L")
    if erode > 0:
        al = al.filter(ImageFilter.MinFilter(2 * erode + 1))
    if feather > 0:
        # soft 1px edge: blur then clamp so interior stays fully opaque
        blurred = al.filter(ImageFilter.GaussianBlur(feather * 0.7))
        al = Image.fromarray(np.minimum(np.asarray(blurred), np.asarray(al.filter(ImageFilter.MaxFilter(3)))).astype(np.uint8), "L")
    # darken edge colour slightly to kill light fringe: pull semi-transparent pixels toward the nearest opaque neighbours
    rgb = np.asarray(im).astype(np.float32)
    aa = np.asarray(al).astype(np.float32) / 255.0
    soft = (aa > 0) & (aa < 1)
    if soft.any():
        # replace colour of soft pixels with a 3x3 alpha-weighted average of opaque neighbours
        pad = np.pad(rgb, ((1,1),(1,1),(0,0)), mode="edge")
        pad_a = np.pad((aa >= 1).astype(np.float32), 1)
        acc = np.zeros_like(rgb); wsum = np.zeros(aa.shape, np.float32)
        for dy in (0,1,2):
            for dx in (0,1,2):
                wgt = pad_a[dy:dy+aa.shape[0], dx:dx+aa.shape[1]]
                acc += pad[dy:dy+aa.shape[0], dx:dx+aa.shape[1]] * wgt[...,None]
                wsum += wgt
        ok = soft & (wsum > 0)
        rgb[ok] = acc[ok] / wsum[ok][:,None]
    if key is not None:
        # de-spill: within 3px of transparency, kill the key tint (magenta -> lift G to min(R,B))
        near = np.asarray(al.filter(ImageFilter.MinFilter(7))) < 255
        r_, g_, b_ = rgb[...,0], rgb[...,1], rgb[...,2]
        spill = near & (r_ - g_ > 30) & (b_ - g_ > 30)
        g_[spill] = np.minimum(r_, b_)[spill]
    out = np.dstack([rgb.clip(0,255).astype(np.uint8), np.asarray(al)])
    res = Image.fromarray(out, "RGBA")
    if trim:
        bbox = res.getbbox()
        if bbox: res = res.crop(bbox)
    return res

def preview(res, path, bgc=(0x20,0x20,0x40)):
    canvas = Image.new("RGBA", res.size, bgc + (255,))
    canvas.alpha_composite(res)
    canvas.convert("RGB").save(path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--tol", type=int, default=35)
    ap.add_argument("--feather", type=float, default=1)
    ap.add_argument("--erode", type=int, default=0)
    ap.add_argument("--no-trim", action="store_true")
    ap.add_argument("--preview", default=None)
    ap.add_argument("--global-white", action="store_true", help="also fade pale pixels not connected to the border")
    ap.add_argument("--key", default=None, help="chroma key colour R,G,B instead of white, e.g. 255,0,255")
    a = ap.parse_args()
    key = tuple(int(v) for v in a.key.split(",")) if a.key else None
    res = cutout(a.src, a.tol, a.feather, a.erode, not a.no_trim, a.global_white, key)
    res.save(a.out, optimize=True)
    print(a.out, res.size)
    if a.preview:
        preview(res, a.preview); print("preview", a.preview)
