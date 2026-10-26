"""uo3d/tattoo_shade.py - finishing of a tattoo animation (.vd): the ink takes the shading of the skin under it, the edge is soft.

A tattoo is drawn over the body, but it is ink IN the skin: where the muscle is in shadow the ink is darker, where the light falls it is lighter, and
its edge is not a hard outline. Render the item with `--outline 1` (no dark edge), then run this over the .vd:

    python nelderim.py tattoo shade --item-vd tat.vd --body-vd body400.vd --out tat_shaded.vd

Per pixel of the tattoo (lone pixels are dropped): colour = ink * f + a little of the skin colour under it (a black ink is then a dark grey that shows the muscles), with
f = the skin's brightness there relative to the bright skin of the frame; a pixel on the edge of the tattoo is mixed half and half with the skin.
"""
import numpy as np

from . import vdread
from .vdwrite import write_vd


def _blur(a, s=1):
    """cheap separable [1 2 1] blur of a 2D array, s passes"""
    for _ in range(s):
        p = np.pad(a, 1, mode="edge")
        a = (p[:-2, 1:-1] + 2 * p[1:-1, 1:-1] + p[2:, 1:-1]) / 4
        p = np.pad(a, 1, mode="edge")
        a = (p[1:-1, :-2] + 2 * p[1:-1, 1:-1] + p[1:-1, 2:]) / 4
    return a


def shade_frame(item, skin, lift=0.12, edge=0.5, gamma=1.3, despeckle=True):
    """item, skin: (256, 256, 4) uint8 canvases of one frame (the tattoo, the original body). Returns the shaded tattoo canvas."""
    out = item.copy()
    a = item[..., 3] > 0
    if despeckle:                                                                 # a lone pixel or a 1 px thread is noise at this size
        p8 = np.pad(a, 1)
        nb = sum(p8[1 + dy:p8.shape[0] - 1 + dy, 1 + dx:p8.shape[1] - 1 + dx].astype(int) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))
        a = a & (nb >= 2)
    if not a.any():
        out[..., 3] = 0
        return out
    sk = skin[..., :3].astype(float)
    lum = sk.mean(2)
    has = skin[..., 3] > 0
    bright = np.percentile(lum[has], 85) if has.any() else 200.0
    f = np.clip((_blur(lum, 1) / max(bright, 1.0)) ** gamma, 0.45, 1.15)
    ink = item[..., :3].astype(float)
    rgb = ink * f[..., None] * (1 - lift) + lift * sk
    rgb = np.where(has[..., None], rgb, ink)                                      # no skin under the pixel (a hand-held or overhanging part): as is
    p = np.pad(a, 1)
    inner = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    edge_px = a & ~inner & has
    rgb[edge_px] = (1 - edge) * rgb[edge_px] + edge * sk[edge_px] * 0.8             # the edge fades into the skin
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[~a] = 0
    return out


def shade_vd(item_vd, body_vd, out_vd, **kw):
    """reads both .vd files (anim type 2, 35 actions x 5 directions), shades every frame of the item, writes out_vd; returns the number of frames"""
    _, _, items = vdread.read_vd(item_vd)
    _, _, bodies = vdread.read_vd(body_vd)
    blocks, n = {}, 0
    for (a, d), frames in items.items():
        bf = bodies.get((a, d))
        out = []
        for k, fr in enumerate(frames):
            canvas = vdread.canvas(fr)
            skin = vdread.canvas(bf[min(k, len(bf) - 1)]) if bf else np.zeros_like(canvas)
            out.append(shade_frame(canvas, skin, **kw)); n += 1
        blocks[(a, d)] = out
    write_vd(out_vd, blocks, anim_type=2, anchor=vdread.ANCHOR)
    return n
