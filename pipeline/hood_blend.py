#!/usr/bin/env python3
"""
hood_blend.py - make the hood of a hooded robe match the rest of the robe (post-processing of a build_item lab).

    python hood_blend.py --lab <lab folder> --masks <region_ids frames folder> [--ramp 6] [--band 14] [--force]

WHY
  build_item transfers the design row by row, so on a hooded base (Hooded Shroud 0x2684) the hood rows get whatever the
  top rows of the picture hold (a face, the inside of a cowl, a different scale). The result is a hood with another
  tone, another grain and a visible seam against the shoulders.

WHAT IT DOES (per frame of every atlas in <lab>/atlases, rows: 0 body, 512 original, 768 new item)
  1. Hood zone = pixels of the ORIGINAL item from its top down to the bottom of the face region (label 1) + `ramp`
     rows, without the hands (label 5). The hood keeps the original silhouette and folds.
  2. Texture = plain cloth of the robe as built, taken from a band of `band` rows just under the zone (the shoulders),
     with straps / belt / accents filtered out (colour close to the median), walked down the column of the band.
     Brightness only: tone = median robe colour * texture brightness * original fold shading
     (the same .65 + .55 * luminance rule as build.fit_texture).
  3. The seam is blended over `ramp` rows; the opening where the face was is filled dark so the head never shows.
Writes the "new" row of every atlas in place and drops hood_blend.json into the lab (refuses a second run on the same
lab unless --force, because the second pass would blend an already blended hood). Pack the lab afterwards
(atlas_to_vd.py). Needs numpy + Pillow; the masks are the toolkit's region-audit frames (aXX_dF_fYY_region_ids.png).
"""
from __future__ import annotations
import argparse, json, os, re, sys

import numpy as np
from PIL import Image

CELL = 256
ROW_ORIG, ROW_NEW = 512, 768
MARK = "hood_blend.json"
DEFAULT_MASKS = os.path.join("workspace", "ultima-online", "region-audit", "all-actions-region-pass", "frames")


def _shade(lum):
    return .65 + .55 * lum / 255.0                         # build.fit_texture


def blend_frame(orig, new, lab, ramp=6, band=14):
    """orig, new: (256,256,4) uint8 views of one frame; lab: (256,256) region ids. Returns the new frame or None."""
    ys = np.where(lab == 1)[0]
    if not len(ys):
        return None
    lim = int(ys.max()) + 1
    rows = np.arange(CELL)[:, None]
    o = orig[..., 3] >= 128
    lum = orig[..., :3].astype(np.float32).mean(2)
    ok = (new[..., 3] >= 128) & o & ~np.isin(lab, [1, 5])
    y0 = lim + ramp
    bnd = ok & (rows >= y0) & (rows < y0 + band)
    if bnd.sum() < 10:
        return None
    mean = np.median(new[bnd][:, :3].astype(np.float32), axis=0)
    near = np.abs(new[..., :3].astype(np.float32) - mean).sum(2) < 70
    pool = bnd & near                                      # plain cloth only: no straps, belt, potions, accents
    if pool.sum() < 10:
        pool = bnd
    zone = o & (rows <= lim + ramp) & (lab != 5)
    yy, xx = np.where(zone)
    if not len(yy):
        return None
    top = yy.min()
    poolx = [np.where(pool[:, x])[0] for x in range(CELL)]
    cols = np.array([x for x in range(CELL) if len(poolx[x])])
    out = new.copy()
    for y, x in zip(yy, xx):
        c = x if len(poolx[x]) else int(cols[np.argmin(np.abs(cols - x))])
        r = poolx[c]
        sy = r[(y - top) % max(len(r), 1)]                 # walk down the cloth column of the band
        ya, yb, xa, xb = max(sy - 1, 0), sy + 2, max(c - 1, 0), c + 2
        m = pool[ya:yb, xa:xb]
        src = (new[ya:yb, xa:xb, :3].astype(np.float32) * m[..., None]).sum((0, 1)) / max(m.sum(), 1)
        k = np.clip(_shade(lum[y, x]) / _shade(lum[sy, c]), 0.65, 1.35)
        col = np.clip(src * k, 0, 255)
        w = np.clip((lim + ramp - y) / float(ramp), 0, 1)
        if new[y, x, 3] >= 128 and y > lim:
            col = w * col + (1 - w) * new[y, x, :3]
        out[y, x, :3] = col.astype(np.uint8)
        out[y, x, 3] = 255
    hole = (lab == 1) & (rows <= lim) & (out[..., 3] < 128)
    out[hole, :3] = (mean * 0.5).astype(np.uint8)
    out[hole, 3] = 255
    return out


def run(lab_dir, masks, ramp=6, band=14, force=False):
    atl = os.path.join(lab_dir, "atlases")
    if not os.path.isdir(atl):
        raise SystemExit(f"[BŁĄD] brak {atl}")
    mark = os.path.join(lab_dir, MARK)
    if os.path.exists(mark) and not force:
        raise SystemExit("[BŁĄD] ta przymiarka ma już wtopiony kaptur (hood_blend.json). Zbuduj ją od nowa albo użyj --force.")
    if not os.path.isdir(masks):
        raise SystemExit(f"[BŁĄD] brak masek regionów: {masks}")
    done = skipped = 0
    for fn in sorted(os.listdir(atl)):
        m = re.fullmatch(r"a(\d+)_d(\d+)\.png", fn)
        if not m:
            continue
        a, d = int(m.group(1)), int(m.group(2))
        im = np.array(Image.open(os.path.join(atl, fn)).convert("RGBA"))
        for f in range(im.shape[1] // CELL):
            mp = os.path.join(masks, f"a{a:02}_d{d}_f{f:02}_region_ids.png")
            if not os.path.exists(mp):
                skipped += 1
                continue
            lab = np.array(Image.open(mp))
            cell = slice(f * CELL, (f + 1) * CELL)
            res = blend_frame(im[ROW_ORIG:ROW_ORIG + CELL, cell], im[ROW_NEW:ROW_NEW + CELL, cell], lab, ramp, band)
            if res is None:
                skipped += 1
                continue
            im[ROW_NEW:ROW_NEW + CELL, cell] = res
            done += 1
        Image.fromarray(im).save(os.path.join(atl, fn))
    with open(mark, "w", encoding="utf-8") as fh:
        json.dump({"frames": done, "skipped": skipped, "ramp": ramp, "band": band}, fh)
    return done, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lab", required=True)
    ap.add_argument("--masks", default=DEFAULT_MASKS)
    ap.add_argument("--ramp", type=int, default=6)
    ap.add_argument("--band", type=int, default=14)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    done, skipped = run(a.lab, a.masks, a.ramp, a.band, a.force)
    print(f"[OK     ] kaptur dopasowany w {done} klatkach ({skipped} pominięto: brak maski albo twarzy w klatce)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
