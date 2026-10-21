"""Paperdoll gump (260 x 237) and item art of a 3D item, from the same model as its animation - numpy + Pillow only.

The numbers come from UO_Model3D (Kserian; uo_render_paperdoll.py, uo_render_weapon_gump.py, uo_render_gump_fit.py), used with the
author's permission. They were measured there on this shard's client:
  * body gump 12 (male): 90.5 px per metre, top of the head y 54 .. feet y 221 (1.855 m), body axis x 94.5; front view, orthographic;
  * one-handed weapon gumps: the haft upright in the right hand (left of the picture) on the haft line of the client's maces (x 48), the
    middle of the fist at y 114.5 (female body 13: 113), held 0.22 m above the butt, the top leaning TILT degrees out from the body;
    the haft is cut out where the body gump's fist lies over it, except its lowest HOLD_SHOW rows (the fist holds it);
  * the client has no female weapon gumps (60000 + AnimID does not exist for them).
What is NOT ported: posing the arms like the drawn paperdoll bodies (robes: uo_render_gump_fit.py searches the arm angles against an
original gump). Here a worn item is drawn on the 3D body's rest pose (arms down, 40 deg out) and, when an ORIGINAL gump of the same kind of
item is given as a reference, scaled / moved so that its outline box matches that gump's, and its greys mapped to that gump's levels.
"""
import math

import numpy as np

from . import engine as E
from . import raster as R

GW, GH = 260, 237
PXM = 90.5
X_AXIS, Y_FEET = 94.5, 221.0
GRIP = {"male": (48.0, 114.5), "female": (48.0, 113.0)}
GRIP_AT = 0.22
TILT = 20.0
HOLD_CUT = (8, 9, 6)                  # fist window around the grip: x +-8 px, y from 9 above to 6 below
HOLD_SHOW = {"male": 2, "female": 3}  # the haft shows through this many bottom rows of the fist
LEVEL_MAX = 210.0


def _front(P, ss, x_axis=X_AXIS, y_feet=Y_FEET, pxm=PXM):
    """glTF points -> supersampled gump pixels (front view: character faces +Z = the viewer) and depth (smaller = nearer)"""
    xy = np.stack([(x_axis + pxm * P[:, 0]) * ss, (y_feet - pxm * P[:, 1]) * ss], 1)
    return xy, -P[:, 2]


class _View:
    def __init__(self, mesh, tri, saturation=1.0, metal=None):
        self.mesh, self.tri, self.saturation, self.metal = mesh, tri, saturation, metal


def box_down(img, k):
    """supersampled uint8 RGBA -> k x smaller, premultiplied box filter, binary alpha"""
    a = img.astype(np.float32)
    h, w = a.shape[0] // k, a.shape[1] // k
    a = a[:h * k, :w * k].reshape(h, k, w, k, 4)
    al = a[..., 3].mean((1, 3)) / 255.0
    rgb = (a[..., :3] * a[..., 3:] / 255.0).sum((1, 3)) / np.maximum((a[..., 3] / 255.0).sum((1, 3)), 1e-6)[..., None]
    out = np.zeros((h, w, 4), np.uint8)
    on = al >= 0.5
    out[on, :3] = np.clip(rgb[on] + 0.5, 0, 255).astype(np.uint8)
    out[on, 3] = 255
    return out


def render(P, N, tri, view, ss=3, hold=None, margin=0.01, place=None):
    """item (glTF points P, normals N) -> uint8 RGBA (GH, GW). hold = (body points, body triangles): the body hides what is behind
    it by more than `margin` (the back of a belt). place(P) -> (xy, depth) overrides the standard front placement."""
    W, H = GW * ss, GH * ss
    xy, dep = place(P) if place else _front(P, ss)
    tid, d = R.raster(xy, dep, tri, W, H)
    img = E.shade(view, tid, W, H, xy, R.rotate_normals(N, 0))
    if hold is not None:
        bxy, bdep = place(hold[0]) if place else _front(hold[0], ss)
        _, bd = R.raster(bxy, bdep, hold[1], W, H)
        img[(bd < d - margin) & (tid >= 0)] = 0
    return box_down(img, ss)


def bbox(a):
    ys, xs = np.nonzero(a)
    return (xs.min(), xs.max() + 1, ys.min(), ys.max() + 1) if len(xs) else None


def fit_to(img, ref):
    """scale / move the item so that its outline box matches the outline box of an original gump `ref` (RGBA, same canvas)"""
    from PIL import Image
    s, r = bbox(img[..., 3] > 0), bbox(ref[..., 3] > 0)
    if s is None or r is None:
        return img
    kx, ky = (r[1] - r[0]) / max(s[1] - s[0], 1), (r[3] - r[2]) / max(s[3] - s[2], 1)
    crop = Image.fromarray(img[s[2]:s[3], s[0]:s[1]])
    nw, nh = max(1, int(round((s[1] - s[0]) * kx))), max(1, int(round((s[3] - s[2]) * ky)))
    a = np.asarray(crop.resize((nw, nh), Image.NEAREST))
    out = np.zeros_like(img)
    x0, y0 = int(r[0]), int(r[2])
    hh, ww = min(nh, GH - y0), min(nw, GW - x0)
    out[y0:y0 + hh, x0:x0 + ww] = a[:hh, :ww]
    return out


def match_levels(img, ref):
    """map the item's grey (luma p5 / p50 / p95) to the levels of the original gump; coloured pixels keep their colour"""
    a, b = img[..., 3] > 0, ref[..., 3] > 0
    if not a.any() or not b.any():
        return img
    y = img[..., :3].astype(np.float32).mean(-1)
    yr = ref[..., :3].astype(np.float32).mean(-1)
    src = np.percentile(y[a], [5, 50, 95]); dst = np.percentile(yr[b], [5, 50, 95])
    xs = [0.0, *src, 255.0]; ys = [0.0, *dst, min(255.0, dst[2] + (255.0 - src[2]))]
    out = img.copy()
    k = np.interp(y, np.maximum.accumulate(xs), ys) / np.maximum(y, 1.0)
    rgb = img[..., :3].astype(np.float32)
    grey = (rgb.max(-1) - rgb.min(-1)) <= 24
    sel = a & grey
    out[sel, :3] = np.clip(rgb[sel] * k[sel, None], 0, LEVEL_MAX).astype(np.uint8)
    return out


def outline(img, factor=0.45):
    return E.outline(img, factor)


def worn(item, body, refs=None, ss=3):
    """gump of a worn item: {"male": RGBA, "female": RGBA}; refs = {"male": RGBA, "female": RGBA} original gumps of the same kind"""
    g = body.g
    view = _View(item.mesh, item.tri, item.saturation, item.metal)
    base = render(item.pos, item.nrm, item.tri, view, ss, hold=(g.pos, g.tri))
    out = {}
    for gender in ("male", "female"):
        ref = (refs or {}).get(gender)
        img = base
        if ref is not None:
            img = match_levels(fit_to(base, ref), ref)
        out[gender] = outline(img)
    return out


def held(item, body_gumps=None, ss=3, tilt=TILT, grip_at=GRIP_AT):
    """gump of a one-handed weapon: the model upright (butt lowest) in the right hand of the paperdoll; male only (the client has no
    female weapon gumps). body_gumps = {"male": RGBA} body gump 12: its fist cuts the haft."""
    m = item.mesh
    P = item.raw_pos.copy(); N = item.raw_nrm.copy()
    P[:, 1] -= P[:, 1].min()
    if grip_at is None or grip_at <= 0:
        grip_at = auto_grip(P, item.tri)
    grip = np.array([(P[:, 0].min() + P[:, 0].max()) / 2, grip_at, (P[:, 2].min() + P[:, 2].max()) / 2])
    th = math.radians(tilt)                                         # top to the left of the picture (away from the body)
    Rz = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    P = (P - grip) @ Rz.T; N = N @ Rz.T
    gx, gy = GRIP["male"]

    def place(Q):
        return np.stack([(gx + PXM * Q[:, 0]) * ss, (gy - PXM * Q[:, 1]) * ss], 1), -Q[:, 2]
    img = outline(render(P, N, item.tri, _View(m, item.tri, item.saturation, item.metal), ss, place=place))
    bg = (body_gumps or {}).get("male")
    if bg is not None:
        img = cut_fist(img, bg, (gx, gy), HOLD_SHOW["male"])
    return {"male": img}


def auto_grip(P, tri=None, n=24):
    """height of the hand on an upright weapon (butt at y 0): halfway between the butt and the guard (the widest slab in the lower
    half: a sword's cross-guard), else GRIP_AT (a mace / staff: no guard) but never above a third of the length"""
    L = float(P[:, 1].max())
    if tri is not None and len(tri):                            # points spread over the faces (a low-poly box has vertices at its corners only)
        u = np.linspace(0, 1, 5)
        bu, bv = [x.ravel() for x in np.meshgrid(u, u)]
        ok = bu + bv <= 1
        bu, bv = bu[ok], bv[ok]
        A, B, Cc = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
        P = (A[:, None] + bu[None, :, None] * (B - A)[:, None] + bv[None, :, None] * (Cc - A)[:, None]).reshape(-1, 3)
    edges = np.linspace(0, L / 2, n + 1)
    w = []
    for i in range(n):
        s = (P[:, 1] >= edges[i]) & (P[:, 1] <= edges[i + 1])
        w.append(float(max(np.ptp(P[s, 0]), np.ptp(P[s, 2]))) if s.sum() >= 3 else 0.0)
    w = np.array(w)
    if len(w) and w.max() > 1.8 * np.median(w[w > 0]) if (w > 0).any() else False:
        guard = 0.5 * (edges[int(np.argmax(w))] + edges[int(np.argmax(w)) + 1])
        return guard / 2
    return min(GRIP_AT, L / 3)


def cut_fist(img, body_gump, grip, show):
    """remove the haft where the body gump's fist lies over it, except the lowest `show` rows of the fist in every column"""
    H, W = img.shape[:2]
    body = np.zeros((H, W), bool)
    h, w = min(H, body_gump.shape[0]), min(W, body_gump.shape[1])
    body[:h, :w] = body_gump[:h, :w, 3] > 0
    gx, gy = int(round(grip[0])), int(round(grip[1]))
    win = np.zeros((H, W), bool)
    win[max(gy - HOLD_CUT[1], 0):gy + HOLD_CUT[2] + 1, max(gx - HOLD_CUT[0], 0):gx + HOLD_CUT[0] + 1] = True
    cut = body & win
    for c in np.nonzero(cut.any(0))[0]:
        rows = np.nonzero(cut[:, c])[0]
        cut[rows[len(rows) - min(show, len(rows)):], c] = False
    out = img.copy()
    out[cut] = 0
    return out


def overlay(item_img, body_gump):
    """item drawn over the body gump (for checking by eye)"""
    from PIL import Image
    base = Image.new("RGBA", (GW, GH), (30, 30, 30, 255))
    if body_gump is not None:
        base.alpha_composite(Image.fromarray(body_gump[:GH, :GW]))
    base.alpha_composite(Image.fromarray(item_img))
    return base
