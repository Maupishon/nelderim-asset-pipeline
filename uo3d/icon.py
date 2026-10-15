"""Inventory icon (static art) straight from a 3D model - numpy + Pillow only, same rasterizer and UO lighting as the
animation renderer (uo3d.engine.shade).

    from uo3d import icon
    im = icon.render_icon("robe.glb", size=44, yaw=-35)      # PIL RGBA, binary alpha, <= size px on the long side

The model is shown from the UO camera elevation (28.45 deg), turned `yaw` degrees around the vertical axis, fitted into
the icon and drawn at `supersample` x the size, then reduced with a premultiplied box filter. Alpha is 0/255 (UO art has
no partial transparency); an optional 1 px darker edge imitates the hand-drawn outline of the original icons.
"""
import numpy as np
from PIL import Image

from . import raster as R
from . import statmesh


class _View:
    """what engine.shade() needs from an `item`."""

    def __init__(self, mesh, saturation=1.0, metal=None):
        self.mesh = mesh
        self.tri = mesh.tri
        self.saturation = saturation
        self.metal = metal


def _reduce(img, size):
    """RGBA uint8 (big) -> cropped to the visible pixels and reduced so the long side is <= size (premultiplied)."""
    ys, xs = np.nonzero(img[..., 3] > 0)
    if not len(ys):
        raise ValueError("Model nie dał żadnych widocznych pikseli (pusta siatka albo cała poza kadrem).")
    img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = img.shape[:2]
    k = min(1.0, size / float(max(h, w)))
    nw, nh = max(1, int(round(w * k))), max(1, int(round(h * k)))
    a = img.astype(np.float32)
    al = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * al, a[..., 3:4]], axis=2)
    chans = [np.asarray(Image.fromarray(pm[..., c], "F").resize((nw, nh), Image.BOX)) for c in range(4)]
    r = np.stack(chans, axis=2)
    alpha = r[..., 3:4]
    rgb = np.where(alpha > 1.0, r[..., :3] / np.maximum(alpha / 255.0, 1e-3), 0.0)
    out = np.concatenate([np.clip(rgb, 0, 255), np.where(alpha >= 128, 255.0, 0.0)], axis=2).astype(np.uint8)
    out[..., :3] = np.where(out[..., 3:4] > 0, out[..., :3], 0)
    return out


def _edge(img, factor):
    """darken the pixels that touch transparency (1 px outline)."""
    if factor >= 1.0:
        return img
    m = img[..., 3] > 0
    pad = np.pad(m, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    edge = m & ~inner
    out = img.copy()
    out[edge, :3] = (out[edge, :3].astype(np.float32) * factor).astype(np.uint8)
    return out


def render_icon(path, size=44, yaw=-35.0, skip=(), supersample=8, saturation=1.0, outline=0.55,
                align=False, fatten=1.0, flip=False, tilt=0.0, face=False):
    """align: stand a long object (weapon) along +Y, hilt down; fatten: thicken it; flip: swap hilt and tip;
    tilt: lay it over by this many degrees about the view axis (-45 = the classic diagonal item icon);
    face: look at it straight from the front (the camera's elevation is cancelled)."""
    from . import engine          # shade(); imported late, engine pulls in the whole skinning stack
    m = statmesh.load(path, tuple(skip))
    if align:
        engine.align_long_axis(m)
    if flip:
        m.pos = m.pos * np.array([-1.0, -1.0, 1.0]); m.nrm = m.nrm * np.array([-1.0, -1.0, 1.0])
    if fatten and abs(float(fatten) - 1.0) > 1e-9:
        engine.fatten(m, float(fatten))
    if tilt:
        th = np.radians(tilt)
        Rz = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
        m.pos = m.pos @ Rz.T; m.nrm = m.nrm @ Rz.T
    if face:
        e = np.radians(28.45)
        Rx = np.array([[1, 0, 0], [0, np.cos(e), np.sin(e)], [0, -np.sin(e), np.cos(e)]])
        m.pos = m.pos @ Rx.T; m.nrm = m.nrm @ Rx.T
    if len(m.tri) == 0:
        raise ValueError("Model nie zawiera żadnej siatki.")
    if m.vcol is not None and float(np.max(m.vcol)) < 0.05:
        m.vcol = None             # a (nearly) all-zero COLOR_0 layer - some exporters write one - would paint everything black and clear
    T = int(size) * int(supersample)
    xy, depth = R.camera(m.pos, 0, canvas=(T, T), anchor=(T / 2, T / 2), yaw0=float(yaw))
    lo, hi = xy.min(0), xy.max(0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1], 1e-6))
    k = (T - 2.0 * supersample) / span
    xy = (xy - (lo + hi) / 2.0) * k + T / 2.0
    tid, _dep = R.raster(xy, depth, m.tri, T, T)
    nrm_view = R.rotate_normals(m.nrm, 0, yaw0=float(yaw))
    big = engine.shade(_View(m, saturation), tid, T, T, xy, nrm_view)
    small = _edge(_reduce(big, int(size)), float(outline))
    return Image.fromarray(small, "RGBA")
