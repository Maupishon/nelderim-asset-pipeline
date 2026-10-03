"""UO layer renderer without Blender: skin an item onto the UO body (UO_Model3D .glb), render it with the UO camera, write a .vd."""
import math, os, time
import numpy as np

from . import raster as R
from .glbmodel import GLB
from . import statmesh

# frames per action of the original body (anim 400); loop actions have 3 extra keys in the .glb that are not UO frames
ACTION_FRAMES = [10, 10, 10, 10, 1, 5, 5, 1, 1, 7, 7, 7, 7, 7, 7, 10, 7, 7, 7, 7, 5, 6, 6, 5, 5, 1, 5, 5, 7, 5, 5, 7, 5, 5, 5]
MOUNTED = {23, 24, 25, 26, 27, 28, 29}
CANVAS = (256, 256)
ANCHOR = (128.5, 192.0)          # measured: the UO anchor is the centre of pixel (128,192) horizontally (IoU 0.879 against the original body)

# z of the lowest / highest point of the ORIGINAL item in the rest pose (m), measured by UO_Model3D (uo_import_item.py)
EXTENTS = {"shirt": (0.999, 1.656), "plate": (0.651, 1.643), "arms": (0.929, 1.694), "pants": (0.057, 1.170),
           "legs": (-0.107, 1.138), "boots": (-0.069, 0.563), "gloves": (0.797, 1.245), "helm": (1.504, 1.903),
           "skirt": (0.026, 1.258), "cloak": (0.095, 1.675), "hair": (1.52, 1.89), "beard": (1.52, 1.72),
           "hat": (1.52, 1.92), "neck": (1.48, 1.64), "robe": (0.026, 1.719)}
GAP_BY_KIND = {"shirt": 0.015, "pants": 0.015, "boots": 0.015, "gloves": 0.015, "plate": 0.03, "legs": 0.03, "arms": 0.03,
               "helm": 0.03}
# kind -> (part, allowed joint name patterns). Weight of a joint that is not allowed moves to its nearest allowed ancestor.
PARTS = {
    "chest": ["pelvis", "spine", "chest", "neck", "clavicle", "upper_arm", "forearm"],
    "torso": ["pelvis", "spine", "chest", "neck"],
    "shoulders": ["chest", "upper_arm", "clavicle"],
    "arms": ["upper_arm", "forearm"],
    "gloves": ["forearm", "hand", "finger"],
    "legs": ["pelvis", "thigh", "shin"],
    "boots": ["shin", "foot", "toe"],
    "helm": ["head"], "hair": ["head"], "beard": ["head"], "hat": ["head"],
    "neck": ["neck", "chest", "head"],
    "all": ["pelvis", "spine", "chest", "neck", "head", "clavicle", "upper_arm", "forearm", "hand", "finger", "thigh", "shin", "foot", "toe"],
}
KIND_PART = {"shirt": "chest", "plate": "chest", "arms": "arms", "pants": "legs", "legs": "legs", "boots": "boots", "gloves": "gloves",
             "helm": "helm", "hair": "hair", "beard": "beard", "hat": "hat", "neck": "neck", "robe": "all", "skirt": "skirt", "cloak": "cloak"}
FIT_KINDS = {"shirt", "plate", "arms", "pants", "legs", "boots", "gloves", "helm"}
RIGID = {"hair", "beard", "hat", "helm"}               # every vertex 100% on the head (UO draws them rigid)
OCCLUDER_JOINTS = ("head", "upper_arm", "forearm", "hand", "finger", "thigh", "shin", "foot", "toe")
TORSO_JOINTS = ("pelvis", "spine", "chest", "neck", "clavicle")


def say(msg):
    print("[uo3d] " + msg, flush=True)


def jbase(name):
    return name.split(".")[0].split("-")[0]


class Body:
    def __init__(self, glb_path):
        self.g = GLB(glb_path)
        g = self.g
        self.names = g.joint_names
        self.parent = []                         # parent joint index (in joint list) or -1
        jn = {j: k for k, j in enumerate(g.joints)}
        for j in g.joints:
            p = g.parent[j]
            while p >= 0 and p not in jn:
                p = g.parent[p]
            self.parent.append(jn[p] if p >= 0 else -1)
        self.headpos = np.array([np.linalg.inv(m)[:3, 3] for m in g.ibm])      # joint head in bind space (glTF)
        # dominant joint of every body vertex -> kind of body part
        dom = g.jnt[np.arange(len(g.jnt)), np.argmax(g.wgt, axis=1)]
        self.dom_name = [self.names[k] for k in dom]
        self.dom = dom
        self.nframes = ACTION_FRAMES
        self.action_names = list(g.anims)

    def joint_mask(self, patterns):
        return np.array([any(jbase(n) == p or n.startswith(p) for p in patterns) for n in self.names])

    def pose_matrices(self, action, k):
        name = self.action_names[action]
        t = (1 + 3 * k) / 24.0
        return self.g.skin_matrices(self.g.pose(name, t))

    def skin_body(self, SM):
        g = self.g
        P = np.zeros_like(g.pos); N = np.zeros_like(g.nrm); ph = np.c_[g.pos, np.ones(len(g.pos))]
        for k in range(g.jnt.shape[1]):
            w = g.wgt[:, k:k+1]
            M = SM[g.jnt[:, k]]
            P += w * np.einsum("nij,nj->ni", M[:, :3, :], ph)
            N += w * np.einsum("nij,nj->ni", M[:, :3, :3], g.nrm)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        return P, N


def nearest(points, ref, chunk=2000):
    """index and distance of the nearest ref point for each point (brute force, chunked)."""
    out_i = np.zeros(len(points), int); out_d = np.zeros(len(points))
    r2 = (ref ** 2).sum(1)
    for s in range(0, len(points), chunk):
        p = points[s:s+chunk]
        d = (p ** 2).sum(1)[:, None] + r2[None, :] - 2 * p @ ref.T
        i = np.argmin(d, axis=1)
        out_i[s:s+chunk] = i; out_d[s:s+chunk] = np.sqrt(np.maximum(d[np.arange(len(p)), i], 0))
    return out_i, out_d


class Item:
    def __init__(self, path, kind, body, turn=0, scale=0.0, skip=(), saturation=1.0, metal=None, shift=(0.0, 0.0, 0.0)):
        self.kind = kind
        self.body = body
        m = statmesh.load(path, skip)
        self.mesh = m
        P = m.pos.copy()
        if kind not in EXTENTS:
            raise ValueError(f"Rodzaj '{kind}' nie jest obsługiwany bez Blendera.")
        lo, hi = EXTENTS[kind]
        # turn about the vertical axis (glTF Y up)
        th = math.radians(turn); c, s = math.cos(th), math.sin(th)
        Rm = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        P = P @ Rm.T; N = m.nrm @ Rm.T
        h0, h1 = np.percentile(P[:, 1], [0.5, 99.5])
        sc = float(scale) if scale and scale > 0 else (hi - lo) / max(h1 - h0, 1e-6)
        P = P * sc
        h0, h1 = np.percentile(P[:, 1], [0.5, 99.5])
        P[:, 1] += lo - h0                                   # lowest point at the original item's height
        # centre sideways and front-back on the body at that height
        g = body.g
        band = (g.pos[:, 1] >= lo) & (g.pos[:, 1] <= hi)
        cx = g.pos[band, 0].mean() if band.any() else 0.0
        cz = g.pos[band, 2].mean() if band.any() else 0.0
        P[:, 0] += cx - (P[:, 0].min() + P[:, 0].max()) / 2 + shift[0]
        P[:, 2] += cz - (P[:, 2].min() + P[:, 2].max()) / 2 + shift[2]
        P[:, 1] += shift[1]
        self.scale = sc
        self.pos = P; self.nrm = N
        self.tri = m.tri
        if kind in FIT_KINDS:
            self.fit(GAP_BY_KIND.get(kind, 0.015))
        self.bind_weights()
        self.prepare_materials(saturation, metal)

    # ---- keep the item out of the body (rest pose); smooth push like uo_fit_item.py but simpler
    def fit(self, gap, iters=6):
        g = self.body.g
        nb = [np.concatenate([self.tri[:, a], self.tri[:, b]]) for a, b in ((0, 1), (1, 2), (2, 0))]
        src = np.concatenate([self.tri[:, 1], self.tri[:, 2], self.tri[:, 0]])
        dst = np.concatenate([self.tri[:, 0], self.tri[:, 1], self.tri[:, 2]])
        cnt = np.maximum(np.bincount(np.concatenate([src, dst]), minlength=len(self.pos)), 1).astype(float)
        for _ in range(iters):
            ni, nd = nearest(self.pos, g.pos)
            n = g.nrm[ni]
            d = ((self.pos - g.pos[ni]) * n).sum(1)
            push = np.where((nd < 0.15) & (d < gap), gap - d, 0.0)
            if push.max() < 0.002:
                break
            vec = n * push[:, None]
            for _ in range(8):                                   # spread the push over the neighbourhood (no bumps)
                acc = vec.copy()
                np.add.at(acc, dst, vec[src]); np.add.at(acc, src, vec[dst])
                sm = acc / (cnt[:, None] + 1)
                vec = 0.5 * vec + 0.5 * sm
                along = (vec * n).sum(1)                         # never less than the push the vertex itself needs
                vec = vec + n * np.maximum(push - along, 0)[:, None]
            self.pos = self.pos + vec

    def bind_weights(self):
        b = self.body; g = b.g
        kind = self.kind
        J = len(b.names)
        if kind in RIGID:
            W = np.zeros((len(self.pos), J)); W[:, b.names.index("head")] = 1.0
        else:
            ni, nd = nearest(self.pos, g.pos)
            # weights of the nearest 3 body vertices
            W = np.zeros((len(self.pos), J))
            near3 = self._near_k(3)
            for kk in range(near3[0].shape[1]):
                idx = near3[0][:, kk]; wt = 1.0 / (near3[1][:, kk] + 0.01)
                for c in range(g.jnt.shape[1]):
                    np.add.at(W, (np.arange(len(W)), g.jnt[idx, c]), wt * g.wgt[idx, c])
            W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
            part = KIND_PART[kind]
            if part in ("skirt", "cloak"):
                W = self.cloth_weights(part, W)
            else:
                W = self.restrict(W, PARTS[part])
        # keep the 4 strongest
        top = np.argsort(-W, axis=1)[:, :4]
        wv = np.take_along_axis(W, top, 1)
        wv /= np.maximum(wv.sum(1, keepdims=True), 1e-9)
        self.jnt = top; self.wgt = wv
        # which body parts this item is skinned to (they never hide it)
        used = np.unique(top[wv > 0.2])
        self.worn = set(jbase(b.names[k]) for k in used)

    def _near_k(self, k):
        g = self.body.g; pts = self.pos
        idx = np.zeros((len(pts), k), int); dist = np.zeros((len(pts), k))
        r2 = (g.pos ** 2).sum(1)
        for s in range(0, len(pts), 2000):
            p = pts[s:s+2000]
            d = (p ** 2).sum(1)[:, None] + r2[None, :] - 2 * p @ g.pos.T
            part = np.argpartition(d, k, axis=1)[:, :k]
            dd = np.take_along_axis(d, part, 1)
            o = np.argsort(dd, axis=1)
            idx[s:s+2000] = np.take_along_axis(part, o, 1); dist[s:s+2000] = np.sqrt(np.maximum(np.take_along_axis(dd, o, 1), 0))
        return idx, dist

    def restrict(self, W, patterns):
        b = self.body
        allowed = b.joint_mask(patterns)
        remap = np.arange(len(b.names))
        for j in range(len(b.names)):
            k = j
            while k >= 0 and not allowed[k]:
                k = b.parent[k]
            remap[j] = k
        out = np.zeros_like(W)
        for j in range(W.shape[1]):
            if remap[j] >= 0:
                out[:, remap[j]] += W[:, j]
        s = out.sum(1)
        bad = s < 1e-6
        if bad.any():                                     # nothing allowed near: use the first allowed joint
            out[bad, np.flatnonzero(allowed)[0]] = 1.0
        return out / np.maximum(out.sum(1, keepdims=True), 1e-9)

    def cloth_weights(self, part, W_body):
        """skirt / cloak: follow the cloth chains of the model (skirt_K_S / cloak_K_S) by distance; above the chains: the body."""
        b = self.body
        pref = part + "_"
        ch = [k for k, n in enumerate(b.names) if n.startswith(pref)]
        if not ch:
            return self.restrict(W_body, PARTS["all"])
        hp = b.headpos[ch]
        top = hp[:, 1].max()
        band = 0.25
        Wc = np.zeros_like(W_body)
        d = np.linalg.norm(self.pos[:, None, :] - hp[None, :, :], axis=2)
        near = np.argsort(d, axis=1)[:, :3]
        wt = 1.0 / (np.take_along_axis(d, near, 1) + 0.02)
        for c in range(3):
            np.add.at(Wc, (np.arange(len(Wc)), np.array(ch)[near[:, c]]), wt[:, c])
        Wc /= np.maximum(Wc.sum(1, keepdims=True), 1e-9)
        t = np.clip((top - self.pos[:, 1]) / band, 0, 1)[:, None]
        Wb = self.restrict(W_body, ["pelvis", "spine", "chest", "neck", "clavicle"] if part == "cloak" else ["pelvis", "spine"])
        return (1 - t) * Wb + t * Wc

    def prepare_materials(self, saturation, metal):
        self.saturation = saturation
        self.metal = metal

    def skin(self, SM):
        P = np.zeros_like(self.pos); N = np.zeros_like(self.nrm)
        ph = np.c_[self.pos, np.ones(len(self.pos))]
        for k in range(4):
            w = self.wgt[:, k:k+1]
            M = SM[self.jnt[:, k]]
            P += w * np.einsum("nij,nj->ni", M[:, :3, :], ph)
            N += w * np.einsum("nij,nj->ni", M[:, :3, :3], self.nrm)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        return P, N


def shade(item, tid, W, H, xy, nrm_view, direction=None):
    """RGBA uint8 image of the item pixels (UO look: albedo x (0.08 + 0.92 * max(N.L, 0)); light at the camera)."""
    m = item.mesh
    ys, xs = np.nonzero(tid >= 0)
    t = tid[ys, xs]
    tri = item.tri[t]
    a, b, c = xy[tri[:, 0]], xy[tri[:, 1]], xy[tri[:, 2]]
    fx, fy = xs + 0.5, ys + 0.5
    ar = (b[:, 0]-a[:, 0])*(c[:, 1]-a[:, 1]) - (c[:, 0]-a[:, 0])*(b[:, 1]-a[:, 1])
    ar = np.where(np.abs(ar) < 1e-12, 1e-12, ar)
    w0 = ((b[:, 0]-fx)*(c[:, 1]-fy) - (c[:, 0]-fx)*(b[:, 1]-fy)) / ar
    w1 = ((c[:, 0]-fx)*(a[:, 1]-fy) - (a[:, 0]-fx)*(c[:, 1]-fy)) / ar
    w2 = 1 - w0 - w1
    n = w0[:, None]*nrm_view[tri[:, 0]] + w1[:, None]*nrm_view[tri[:, 1]] + w2[:, None]*nrm_view[tri[:, 2]]
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    # two-sided: flip the normal when it faces away from the camera
    L = np.array([0.0, -math.cos(R.ELEV), math.sin(R.ELEV)])
    ndl = n @ L
    ndl = np.abs(ndl)
    uv = w0[:, None]*m.uv[tri[:, 0]] + w1[:, None]*m.uv[tri[:, 1]] + w2[:, None]*m.uv[tri[:, 2]]
    col = np.ones((len(t), 4))
    mat_id = m.mat_of_tri[t]
    for mi in np.unique(mat_id):
        sel = mat_id == mi
        mat = m.mats[mi]
        cc = np.tile(mat.color, (sel.sum(), 1))
        if mat.tex is not None:
            th, tw = mat.tex.shape[:2]
            u = np.mod(uv[sel, 0], 1.0); v = np.mod(uv[sel, 1], 1.0)
            cc = cc * mat.tex[np.minimum((v*th).astype(int), th-1), np.minimum((u*tw).astype(int), tw-1)]
        col[sel] = cc
    rgb = col[:, :3]
    if item.saturation != 1.0:
        grey = rgb.mean(1, keepdims=True)
        rgb = grey + (rgb - grey) * item.saturation
    rgb = np.clip(rgb, 0.02, 0.98)
    lit = 0.08 + 0.92 * ndl
    metal = item.metal
    if metal is None:
        metal = np.array([m.mats[i].metal >= 0.5 for i in mat_id])
    spec = np.where(metal, ndl ** 16, 0.0)
    out = np.clip(rgb * lit[:, None] + (rgb * spec[:, None]), 0, 1)
    img = np.zeros((H, W, 4), np.uint8)
    img[ys, xs, :3] = (out ** (1/1.0) * 255 + 0.5).astype(np.uint8)
    img[ys, xs, 3] = np.where(col[:, 3] >= 0.5, 255, 0)
    return img


def outline(img, factor):
    """darken the pixels on the silhouette edge (UO-style 1 px outline)."""
    if factor >= 1.0:
        return img
    a = img[..., 3] > 0
    p = np.pad(a, 1)
    inner = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    edge = a & ~inner
    img = img.copy()
    img[edge, :3] = (img[edge, :3] * factor).astype(np.uint8)
    return img


def clean(img, fill=4, min_piece=8):
    """fill tiny holes, drop tiny detached bits (needs scipy for the second; skipped without it)."""
    a = img[..., 3] > 0
    try:
        from scipy import ndimage as ndi
    except Exception:  # noqa: BLE001
        return img
    if fill:
        holes = ndi.binary_fill_holes(a) & ~a
        lab, n = ndi.label(holes)
        if n:
            sizes = ndi.sum(holes, lab, range(1, n+1))
            for i, sz in enumerate(sizes, 1):
                if sz <= fill:
                    m = lab == i
                    k = ndi.binary_dilation(m) & a
                    if k.any():
                        img[m, :3] = img[k, :3].mean(0).astype(np.uint8); img[m, 3] = 255
    a = img[..., 3] > 0
    if min_piece:
        lab, n = ndi.label(a)
        if n > 1:
            sizes = ndi.sum(a, lab, range(1, n+1))
            keep = int(np.argmax(sizes)) + 1
            for i, sz in enumerate(sizes, 1):
                if i != keep and sz < min_piece:
                    img[lab == i] = 0
    return img


def render_layer(body, item, actions, out_path, outline_f=0.38, margin=0.01, progress=None):
    from .vdwrite import write_vd
    W, H = CANVAS
    blocks = {}
    kind = item.kind
    cloak = kind == "cloak"
    occl = body.joint_mask(OCCLUDER_JOINTS)
    worn = item.worn
    occ_vert = np.array([jbase(body.names[j]) not in worn and occl[j] for j in body.dom])
    torso_vert = np.array([body.names[j].split(".")[0] in TORSO_JOINTS for j in body.dom])
    g = body.g
    occ_tri = occ_vert[g.tri].all(1)
    tors_tri = torso_vert[g.tri].all(1)
    total = sum(5 * ACTION_FRAMES[a] for a in actions); done = 0; t0 = time.time()
    for a in actions:
        for k in range(ACTION_FRAMES[a]):
            SM = body.pose_matrices(a, k)
            Pb, Nb = body.skin_body(SM)
            Pi, Ni = item.skin(SM)
            for d in range(5):
                xyb, zb = R.camera(Pb, d, CANVAS, ANCHOR)
                xyi, zi = R.camera(Pi, d, CANVAS, ANCHOR)
                tid, dep = R.raster(xyi, zi, item.tri, W, H)
                if (tid >= 0).any():
                    nv = R.rotate_normals(Ni, d)
                    img = shade(item, tid, W, H, xyi, nv)
                    # the body hides the item where it is clearly in front of it (arms, hands, head, legs; never the worn parts)
                    _, bdep = R.raster(xyb, zb, g.tri[occ_tri], W, H)
                    hide = bdep < dep - margin
                    if cloak:
                        _, tdep = R.raster(xyb, zb, g.tri[tors_tri], W, H)
                        hide |= tdep < dep - 0.12
                    img[hide] = 0
                    img = clean(outline(img, outline_f))
                else:
                    img = np.zeros((H, W, 4), np.uint8)
                blocks.setdefault((a, d), []).append(img)
                done += 1
            if progress:
                progress(done, total)
    write_vd(out_path, blocks, anim_type=2, anchor=(128, 192))
    say(f"zapisano {out_path} ({done} klatek, {time.time()-t0:.0f} s)")
    return blocks
