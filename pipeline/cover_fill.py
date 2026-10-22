#!/usr/bin/env python3
"""
cover_fill.py - a new robe must cover everything the original robe covered (post-processing of a build_item lab).

    python cover_fill.py --lab <lab folder> [--reach 10] [--force]

WHY
  build_item cuts the hands and the face out of the design and samples the design row by row, so the new robe has transparent
  pixels where the ORIGINAL robe of the base item had cloth. The client then shows the body through them (measured with
  `nelderim.py holes`: a robe built this way had 3x the arm / torso / leg holes of the original animation, plus larger hand cut-outs).

WHAT IT DOES (per frame of every atlas in <lab>/atlases, rows: 0 body, 512 original, 768 new item)
  Every pixel that is opaque in the ORIGINAL item and transparent in the new one gets the colour of the nearest opaque pixel of the new
  item (at most `reach` px away, grown one ring at a time). The new silhouette ends up a superset of the original one; what the original
  left open (its own hand and face openings, slits) stays open. Writes the "new" row in place and drops cover_fill.json into the lab
  (refuses a second run unless --force). Pack the lab afterwards (atlas_to_vd.py). Needs numpy + Pillow.
"""
from __future__ import annotations
import argparse, json, os, re, sys

import numpy as np
from PIL import Image

CELL = 256
ROW_ORIG, ROW_NEW = 512, 768
MARK = "cover_fill.json"


def fill_frame(orig, new, reach=10):
    """orig, new: (256,256,4) uint8 of one frame. Returns (filled copy of new, number of pixels added) or (None, 0)."""
    o = orig[..., 3] >= 128
    have = new[..., 3] >= 128
    need = o & ~have
    if not need.any() or not have.any():
        return None, 0
    out = new.copy()
    col = new[..., :3].astype(np.float32)
    done = have.copy()
    added = 0
    for _ in range(int(reach)):
        grow = need & ~done
        if not grow.any():
            break
        p = np.pad(done, 1)
        pc = np.pad(col * done[..., None], ((1, 1), (1, 1), (0, 0)))
        s = np.zeros_like(col); n = np.zeros(done.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                sl = (slice(1 + dy, 1 + dy + CELL), slice(1 + dx, 1 + dx + CELL))
                s += pc[sl]; n += p[sl]
        ring = grow & (n > 0)
        if not ring.any():
            break
        col[ring] = s[ring] / n[ring][:, None]
        out[ring, :3] = col[ring].astype(np.uint8)
        out[ring, 3] = 255
        done |= ring
        added += int(ring.sum())
    return (out if added else None), added


def run(lab_dir, reach=10, force=False):
    atl = os.path.join(lab_dir, "atlases")
    if not os.path.isdir(atl):
        raise SystemExit(f"[BŁĄD] brak {atl}")
    mark = os.path.join(lab_dir, MARK)
    if os.path.exists(mark) and not force:
        raise SystemExit("[BŁĄD] ta przymiarka ma już uzupełnione dziury (cover_fill.json). Zbuduj ją od nowa albo użyj --force.")
    frames = pixels = 0
    for fn in sorted(os.listdir(atl)):
        if not re.fullmatch(r"a(\d+)_d(\d+)\.png", fn):
            continue
        im = np.array(Image.open(os.path.join(atl, fn)).convert("RGBA"))
        for f in range(im.shape[1] // CELL):
            cell = slice(f * CELL, (f + 1) * CELL)
            res, n = fill_frame(im[ROW_ORIG:ROW_ORIG + CELL, cell], im[ROW_NEW:ROW_NEW + CELL, cell], reach)
            if res is not None:
                im[ROW_NEW:ROW_NEW + CELL, cell] = res
                frames += 1; pixels += n
        Image.fromarray(im).save(os.path.join(atl, fn))
    with open(mark, "w", encoding="utf-8") as fh:
        json.dump({"frames": frames, "pixels": pixels, "reach": reach}, fh)
    return frames, pixels


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lab", required=True)
    ap.add_argument("--reach", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    frames, pixels = run(a.lab, a.reach, a.force)
    print(f"[OK     ] uzupełniono {pixels} px w {frames} klatkach")
    return 0


if __name__ == "__main__":
    sys.exit(main())
