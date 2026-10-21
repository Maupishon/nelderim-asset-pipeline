"""Holes of an item layer over the ORIGINAL body 400: what the client shows when the item .vd is drawn over the body - numpy only.

Idea and rules from UO_Model3D pipeline/item_body_holes.py (Kserian, used with permission): a pixel of the original body that the item
does not cover but that lies INSIDE the item's outline (the outline closed by 2 px, its holes filled) is a hole the player sees as the
body through the item. Each hole pixel is labelled with the body part of the 3D model there (nearest labelled pixel): a hand or the head
in front of a robe is drawn over it on purpose, an arm, the torso or a leg is a fault.
"""
import numpy as np

from . import vdread

CLOSE = 2
PARTS = ("hand", "head", "arm", "torso", "leg")
COLOURS = {"hand": (255, 255, 255), "head": (255, 255, 255), "arm": (0, 0, 0), "torso": (255, 140, 0), "leg": (40, 120, 255)}
FAULT = ("arm", "torso", "leg")
JOINT_PART = {"hand": "hand", "finger": "hand", "head": "head", "upper_arm": "arm", "forearm": "arm", "clavicle": "arm",
              "pelvis": "torso", "spine": "torso", "chest": "torso", "neck": "torso", "thigh": "leg", "shin": "leg", "foot": "leg", "toe": "leg"}


def _dil(m, n=1):
    for _ in range(n):
        p = np.pad(m, 1)
        m = m | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:]
    return m


def _ero(m, n=1):
    return ~_dil(~m, n)


def fill_holes(m):
    try:
        from scipy import ndimage
        return ndimage.binary_fill_holes(m)
    except Exception:  # noqa: BLE001
        out = np.zeros_like(m)
        out[0, :] = ~m[0, :]; out[-1, :] = ~m[-1, :]; out[:, 0] = ~m[:, 0]; out[:, -1] = ~m[:, -1]
        while True:
            p = np.pad(out, 1)
            nxt = (out | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~m
            if (nxt == out).all():
                return ~out
            out = nxt


def inside(item):
    """the item's outline closed by CLOSE px (a slit between two folds is not a hole), holes filled"""
    return fill_holes(_ero(_dil(item, CLOSE), CLOSE))


class Labeller:
    """body part of every pixel of the 3D body at (action, frame, direction), uo3d renderer"""

    def __init__(self, glb):
        from . import engine as E
        self.E = E
        self.body = E.Body(glb)
        names = self.body.names
        part = []
        for j in self.body.dom:
            base = E.jbase(names[j])
            part.append(PARTS.index(JOINT_PART.get(base, "torso")))
        self.vpart = np.array(part)

    def labels(self, a, k, d):
        from . import raster as R
        E = self.E
        _, SM = self.body.pose_matrices(a, k)
        P, _ = self.body.skin_body(SM)
        xy, z = R.camera(P, d, E.CANVAS, E.ANCHOR)
        tid, _ = R.raster(xy, z, self.body.g.tri, 256, 256)
        lab = np.full(tid.shape, -1, int)
        on = tid >= 0
        lab[on] = self.vpart[self.body.g.tri[tid[on], 0]]
        return lab


def nearest_label(lab, where, hand_reach=2):
    """label at `where` pixels: their own, else the nearest labelled pixel (8-neighbour growth). Pixels within `hand_reach` px of the 3D
    hand / head count as hand / head: the 3D hand stands a pixel or two off the original one, and the rim of a hand-shaped hole is the hand"""
    out = lab.copy()
    for part in ("hand", "head"):
        near = _dil(lab == PARTS.index(part), hand_reach) & where
        out[near] = PARTS.index(part)
    for _ in range(40):
        need = where & (out < 0)
        if not need.any():
            break
        grown = out.copy()
        p = np.pad(out, 1, constant_values=-1)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nb = p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
                grown = np.where((grown < 0) & (nb >= 0), nb, grown)
        out = np.where(need, grown, out)
    return out


def analyse(item_vd, body_vd, glb=None, actions=None):
    """-> {"per_action": {a: {part: px}}, "fault_frames": [[a, d, k, px]], "total": {part: px}}"""
    _, _, it = vdread.read_vd(item_vd)
    _, _, bd = vdread.read_vd(body_vd)
    lab_of = Labeller(glb) if glb else None
    per, faults, total = {}, [], {p: 0 for p in PARTS + ("body",)}
    acts = sorted({a for a, _ in it} if actions is None else set(actions))
    for a in acts:
        row = {p: 0 for p in PARTS + ("body",)}
        for d in range(5):
            frs, bfr = it.get((a, d), []), bd.get((a, d), [])
            for k in range(min(len(frs), len(bfr))):
                im = vdread.canvas(frs[k])[..., 3] > 0
                bo = vdread.canvas(bfr[k])[..., 3] > 0
                hole = bo & inside(im) & ~im
                n = int(hole.sum())
                if not n:
                    continue
                if lab_of is None:
                    row["body"] += n
                    continue
                lab = nearest_label(lab_of.labels(a, k, d), hole)
                bad = 0
                for i, p in enumerate(PARTS):
                    c = int((hole & (lab == i)).sum())
                    row[p] += c
                    if p in FAULT:
                        bad += c
                row["body"] += int((hole & (lab < 0)).sum())
                if bad:
                    faults.append([a, d, k, bad])
        per[a] = row
        for p in row:
            total[p] += row[p]
    return {"per_action": per, "fault_frames": faults, "total": total}


def sheet(item_vd, body_vd, glb, a, d, scale=3):
    """every frame of (action, direction) as the client shows it (item over the original body), x scale, hole pixels painted by part"""
    from PIL import Image
    _, _, it = vdread.read_vd(item_vd)
    _, _, bd = vdread.read_vd(body_vd)
    lab_of = Labeller(glb) if glb else None
    tiles = []
    for k in range(len(bd.get((a, d), []))):
        b = vdread.canvas(bd[(a, d)][k]); i = vdread.canvas(it[(a, d)][k]) if k < len(it.get((a, d), [])) else np.zeros_like(b)
        im = Image.new("RGBA", (256, 256), (40, 60, 40, 255))
        im.alpha_composite(Image.fromarray(b)); im.alpha_composite(Image.fromarray(i))
        arr = np.asarray(im).copy()
        hole = (b[..., 3] > 0) & inside(i[..., 3] > 0) & ~(i[..., 3] > 0)
        if hole.any():
            lab = nearest_label(lab_of.labels(a, k, d), hole) if lab_of else np.full(hole.shape, 2)
            for idx, p in enumerate(PARTS):
                arr[hole & (lab == idx), :3] = COLOURS[p]
        m = (arr[..., 3] > 0) & ((b[..., 3] > 0) | (i[..., 3] > 0))
        ys, xs = np.nonzero(m) if m.any() else (np.array([96, 224]), np.array([64, 192]))
        crop = arr[max(ys.min() - 4, 0):ys.max() + 5, max(xs.min() - 4, 0):xs.max() + 5]
        tiles.append(Image.fromarray(crop).resize((crop.shape[1] * scale, crop.shape[0] * scale), Image.NEAREST))
    W = sum(t.width for t in tiles) + 4 * len(tiles); H = max([t.height for t in tiles] or [1])
    out = Image.new("RGBA", (max(W, 1), H), (20, 20, 20, 255))
    x = 0
    for t in tiles:
        out.paste(t, (x, 0)); x += t.width + 4
    return out
