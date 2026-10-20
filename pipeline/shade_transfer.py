#!/usr/bin/env python3
"""
shade_transfer.py - give a robe the shadows of the original (post-processing of a build_item lab).

    python shade_transfer.py --lab <lab folder> [--strength 1.5] [--force]

WHY
  build_item paints the design with a flat light (.65 + .55 * luminance), so a new robe has weak shadows under the
  arms, on the inner side of the sleeves and at the waist, and looks slimmer / flatter than the original, which
  carries a hard shadow there (measured: spread of the local brightness 0.26 in the original, 0.21 in a built robe).

WHAT IT DOES (per frame of every atlas in <lab>/atlases, rows: 0 body, 512 original, 768 new item)
  1. shade map of the ORIGINAL item = its brightness (grain removed, 3x3 blur) divided by the brightness of the cloth
     around it (19x19 blur): below 1 in the shadows, above 1 in the lights.
  2. the same map of the NEW item (its own flat shading), so the shadow is not counted twice.
  3. new = new * (original map / new map) ** strength, factor limited to 0.35 .. 1.8. Colours and patterns stay.
  strength 1.5 matches the contrast of the original (std of the local brightness), 2.5 and more is too blotchy.
Writes the "new" row of every atlas in place and drops shade_transfer.json into the lab (refuses a second run unless
--force: a second pass would count the shadow twice). Run it after hood_blend, pack the lab afterwards (atlas_to_vd.py).
Needs numpy + Pillow.
"""
from __future__ import annotations
import argparse, json, os, re, sys

import numpy as np
from PIL import Image

CELL = 256
ROW_ORIG, ROW_NEW = 512, 768
MARK = "shade_transfer.json"
DEFAULT_STRENGTH = 1.5


def _box(a, r):
    k = 2 * r + 1
    c = np.pad(np.pad(a, r).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def _nblur(L, m, r, it=1):
    """blur that ignores transparent pixels (normalised convolution)"""
    L, w = L * m, m.astype(np.float64)
    for _ in range(it):
        L = _box(L, r) / np.maximum(_box(w, r), 1e-6) * m
    return L


def _lum(rgba):
    return 0.299 * rgba[..., 0] + 0.587 * rgba[..., 1] + 0.114 * rgba[..., 2]


def shade_map(rgba):
    m = rgba[..., 3] >= 128
    L = _lum(rgba.astype(np.float64))
    s = np.where(m, _nblur(L, m, 1, 2) / np.maximum(_nblur(L, m, 9, 2), 8), 1.0)
    return np.clip(s, 0.3, 1.6)


def transfer_frame(orig, new, strength=DEFAULT_STRENGTH):
    """orig, new: (256,256,4) uint8 of one frame. Returns the shaded copy of `new`, or None when there is nothing to do."""
    both = (new[..., 3] >= 128) & (orig[..., 3] >= 128)
    if both.sum() < 20:
        return None
    f = np.where(both, (shade_map(orig) / shade_map(new)) ** strength, 1.0)
    f = np.clip(f, 0.35, 1.8)
    out = new.copy()
    out[..., :3] = np.clip(new[..., :3].astype(np.float32) * f[..., None], 0, 255).astype(np.uint8)
    return out


def run(lab_dir, strength=DEFAULT_STRENGTH, force=False):
    atl = os.path.join(lab_dir, "atlases")
    if not os.path.isdir(atl):
        raise SystemExit(f"[BŁĄD] brak {atl}")
    mark = os.path.join(lab_dir, MARK)
    if os.path.exists(mark) and not force:
        raise SystemExit("[BŁĄD] ta przymiarka ma już przeniesione cieniowanie (shade_transfer.json). Zbuduj ją od nowa albo użyj --force.")
    done = skipped = 0
    for fn in sorted(os.listdir(atl)):
        if not re.fullmatch(r"a(\d+)_d(\d+)\.png", fn):
            continue
        im = np.array(Image.open(os.path.join(atl, fn)).convert("RGBA"))
        for f in range(im.shape[1] // CELL):
            cell = slice(f * CELL, (f + 1) * CELL)
            res = transfer_frame(im[ROW_ORIG:ROW_ORIG + CELL, cell], im[ROW_NEW:ROW_NEW + CELL, cell], strength)
            if res is None:
                skipped += 1
                continue
            im[ROW_NEW:ROW_NEW + CELL, cell] = res
            done += 1
        Image.fromarray(im).save(os.path.join(atl, fn))
    with open(mark, "w", encoding="utf-8") as fh:
        json.dump({"frames": done, "skipped": skipped, "strength": strength}, fh)
    return done, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lab", required=True)
    ap.add_argument("--strength", type=float, default=DEFAULT_STRENGTH)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    done, skipped = run(a.lab, a.strength, a.force)
    print(f"[OK     ] cieniowanie przeniesione w {done} klatkach ({skipped} pominięto)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
