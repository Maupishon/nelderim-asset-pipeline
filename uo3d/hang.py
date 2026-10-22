"""Loose garments on a body without cloth chains (UO_Model3D v13+): robe / skirt hang from the pelvis and the legs push them out,
a cloak bends back about the shoulders per action. numpy only.

Ported from UO_Model3D (Kserian) pipeline/cloth_lib.py, uo_bind_item.py (mark_cloth / mark_cloak) and render_uo_layer.py (cloth_push),
used with the author's permission. The numbers (margin, kappa, cloak pitch per action) were calibrated there on the original robes
469 / 455 / 971 and the original cloak 468. Everything here works in Blender's frame (metres, Z up, the character faces -Y):
to_blender / to_gltf convert the uo3d (glTF, Y up) arrays.

Lower-body IoU of a robe against the original 469 with the leg hull alone: 0.641 -> 0.757 (UO_Model3D measurement, not repeated here).
"""
import json, os

import numpy as np

LEG_BONES = ("thigh.L", "shin.L", "foot.L", "thigh.R", "shin.R", "foot.R")
CLOTH_MARGIN, CLOTH_KAPPA = 0.05, 0.8                  # long robe (hem below 0.15 m)
CLOTH_MARGIN_SHORT, CLOTH_KAPPA_SHORT = 0.02, 0.5      # garment that ends at the knee or above (kilt, short skirt)
CLOTH_DROP = 1.0
CLOTH_MOUNTED = 1.0                                    # mounted actions 23-29: the hanging part lies along the legs
MOUNTED = range(23, 30)
CP = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1.0]])   # glTF (Y up) -> Blender (Z up)
CPI = np.linalg.inv(CP)
_PITCH = None


def to_blender(P):
    return np.c_[P[:, 0], -P[:, 2], P[:, 1]]


def to_gltf(P):
    return np.c_[P[:, 0], P[:, 2], -P[:, 1]]


def mat_blender(M):
    return CP @ M @ CPI


def cloak_table():
    global _PITCH
    if _PITCH is None:
        _PITCH = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cloak_pitch.json")))
    return _PITCH


# ---------------------------------------------------------------- legs as capsules
def seg_closest(X, A, B):
    ab = B - A
    t = np.clip(((X - A) @ ab) / max(ab @ ab, 1e-12), 0.0, 1.0)
    return A + t[:, None] * ab, t


def capsule_radius(head, tail, verts, percentile=50):
    """radius of a limb: median distance of the skin dominated by the bone to its axis"""
    if len(verts) == 0:
        return 0.05
    _, t = seg_closest(verts, head, tail)
    return float(np.percentile(np.linalg.norm(verts - (head + t[:, None] * (tail - head)), axis=1), percentile))


def sample_capsules(heads, tails, radius, step=0.03):
    C, R = [], []
    for A, B, r in zip(heads, tails, radius):
        n = max(int(np.linalg.norm(B - A) / step), 1) + 1
        t = np.linspace(0, 1, n)[:, None]
        C.append(A + t * (B - A)); R.append(np.full(n, r))
    return np.concatenate(C), np.concatenate(R)


def hull_field(centres, radii, zs, centre_xy, nth=48):
    th = np.linspace(0, 2 * np.pi, nth, endpoint=False)
    U = np.stack([np.cos(th), np.sin(th)], 1)
    H = np.zeros((nth, len(zs)))
    q_all = centres[:, :2] - np.asarray(centre_xy)
    for k, z in enumerate(zs):
        hz = centres[:, 2] - z
        m = np.abs(hz) < radii
        if not m.any():
            continue
        rho = np.sqrt(radii[m] ** 2 - hz[m] ** 2)
        H[:, k] = (U @ q_all[m].T + rho[None, :]).max(1)
    return th, H


def smooth_field(H, passes_th=3, passes_z=2):
    for _ in range(passes_th):
        H = 0.25 * np.roll(H, 1, 0) + 0.5 * H + 0.25 * np.roll(H, -1, 0)
    for _ in range(passes_z):
        P = np.pad(H, ((0, 0), (1, 1)), mode="edge")
        H = 0.25 * P[:, :-2] + 0.5 * P[:, 1:-1] + 0.25 * P[:, 2:]
    return H


def tent(hm, zs, z_top, rho_top, drop=0.15):
    """one sheet from the waist: a push low down pushes every height above it out too, on the line from the waist; below a push the
    cloth hangs down from it, narrowing by at most `drop` m per m of height"""
    out = hm.copy()
    for k in range(len(zs)):
        for j in range(k):
            w = (z_top - zs[k]) / max(z_top - zs[j], 1e-9)
            line = rho_top + (hm[:, j] - rho_top) * w
            out[:, k] = np.where(hm[:, j] > rho_top, np.maximum(out[:, k], line), out[:, k])
    for k in range(len(zs) - 2, -1, -1):
        out[:, k] = np.where(out[:, k + 1] > rho_top, np.maximum(out[:, k], out[:, k + 1] - drop * (zs[k + 1] - zs[k])), out[:, k])
    return out


def hull_push(Vrest, S_pelvis, heads, tails, radius, centre_xy=(0.0, -0.02), margin=0.03, kappa=0.6, z_top=1.02, z_hem=0.05, ramp=0.15,
              nth=48, nz=36, use_tent=True, rho_top=None, drop=0.15):
    """displacement of the garment vertices (rest coordinates, rest frame of the pelvis) in the posed frame: the hanging cloth is pushed
    out, around the vertical axis of the waist, to where the legs reach at that height (their "shadow", not their contact)"""
    Sinv = np.linalg.inv(S_pelvis)
    C, R = sample_capsules(heads, tails, radius)
    Cr = (np.c_[C, np.ones(len(C))] @ Sinv.T)[:, :3]
    zs = np.linspace(z_hem, z_top, nz)
    th, H = hull_field(Cr, R, zs, centre_xy, nth)
    H = smooth_field(H)
    u = Vrest[:, :2] - np.asarray(centre_xy); rho = np.linalg.norm(u, axis=1); ang = np.mod(np.arctan2(u[:, 1], u[:, 0]), 2 * np.pi)
    if use_tent:
        top = np.nonzero((Vrest[:, 2] > z_top - 0.14) & (Vrest[:, 2] <= z_top))[0]
        rt = rho_top if rho_top is not None else (float(np.median(rho[top])) if len(top) else 0.2)
        H = smooth_field(tent(np.where(H > 0, H + margin, 0.0), zs, z_top, rt, drop), 2, 1) - margin * (H > -1)
        H = np.where(H > margin + 1e-9, H, 0.0)
    fa = ang / (2 * np.pi) * nth; i0 = np.floor(fa).astype(int) % nth; i1 = (i0 + 1) % nth; wa = fa - np.floor(fa)
    fz = np.clip((Vrest[:, 2] - z_hem) / (z_top - z_hem), 0, 1) * (nz - 1); k0 = np.minimum(np.floor(fz).astype(int), nz - 2); wz = fz - k0
    h = (H[i0, k0] * (1 - wa) * (1 - wz) + H[i1, k0] * wa * (1 - wz) + H[i0, k0 + 1] * (1 - wa) * wz + H[i1, k0 + 1] * wa * wz)
    free = np.clip((z_top - Vrest[:, 2]) / ramp, 0, 1)
    push = kappa * np.maximum(0.0, np.where(h > 0, h + margin, 0.0) - rho) * free
    d_rest = np.zeros((len(Vrest), 3)); d_rest[:, :2] = push[:, None] * u / np.maximum(rho, 1e-9)[:, None]
    return d_rest @ S_pelvis[:3, :3].T


def cloak_bend(V, z_top, z_hem, y_top, d0, d1):
    """cape tilted back (+Y) about the shoulder line by d0 rad at the shoulders and d1 at the hem; the centre line is the integral of the
    turn, so the cape bends instead of swinging as a plank"""
    L = max(z_top - z_hem, 1e-3)
    s = np.clip(z_top - V[:, 2], 0.0, None)
    k = (d1 - d0) / L
    sc = np.minimum(s, L)
    ph = d0 + k * sc
    if abs(k) > 1e-6:
        Cy = (np.cos(d0) - np.cos(ph)) / k; Cz = (np.sin(ph) - np.sin(d0)) / k
    else:
        Cy = sc * np.sin(d0); Cz = sc * np.cos(d0)
    tail = s - sc
    Cy = Cy + tail * np.sin(ph); Cz = Cz + tail * np.cos(ph)
    e = V[:, 1] - y_top
    Vn = np.empty_like(V)
    Vn[:, 0] = V[:, 0]
    Vn[:, 1] = y_top + Cy + e * np.cos(ph)
    Vn[:, 2] = z_top - Cz + e * np.sin(ph)
    out = Vn - V
    out[s <= 0] = 0.0
    return out


# ---------------------------------------------------------------- one garment on one body
class Hang:
    """per-frame displacement of a loose garment (glTF space), added after skinning"""

    def __init__(self, body, item_rest, kind, leg_w):
        g = body.g
        self.kind = kind
        self.names = body.names
        self.j = {n: k for k, n in enumerate(body.names)}
        V = to_blender(item_rest)
        self.V = V
        self.leg_w = leg_w                                               # (n, 6) skin weights of the legs before they went to the pelvis
        if kind == "cloak":
            z_top = float(V[:, 2].max()); top = V[V[:, 2] > z_top - 0.06]
            self.prm = dict(y_top=float(top[:, 1].mean()), z_top=z_top, z_hem=float(V[:, 2].min()))
            return
        bones = g.bones
        pel = np.array(bones["pelvis"]["head"]) if "pelvis" in bones else np.linalg.inv(g.ibm[self.j["pelvis"]])[:3, 3]
        z_top = float(to_blender(pel[None, :])[0, 2]) + 0.04
        band = V[(V[:, 2] > 0.4) & (V[:, 2] < 0.9)]
        centre = band[:, :2].mean(0) if len(band) else V[:, :2].mean(0)
        z_hem = float(V[:, 2].min())
        t = min(max((z_hem - 0.15) / 0.15, 0.0), 1.0)
        self.prm = dict(centre=centre, z_top=z_top, z_hem=z_hem, ramp=0.15, drop=CLOTH_DROP,
                        margin=CLOTH_MARGIN + (CLOTH_MARGIN_SHORT - CLOTH_MARGIN) * t, kappa=CLOTH_KAPPA + (CLOTH_KAPPA_SHORT - CLOTH_KAPPA) * t)
        self.legs = [n for n in LEG_BONES if n in self.j and n in bones]
        Pb = to_blender(g.pos)
        dom = np.array(body.dom_name)
        self.head = np.array([to_blender(np.array([bones[n]["head"]]))[0] for n in self.legs])
        self.tail = np.array([to_blender(np.array([bones[n]["tail"]]))[0] for n in self.legs])
        self.radius = np.array([capsule_radius(h, t_, Pb[dom == n]) for n, h, t_ in zip(self.legs, self.head, self.tail)])

    def displacement(self, action, k, SM):
        """(n, 3) glTF-space offset of the skinned garment at UO frame k of `action`; SM = skinning matrices of the body joints"""
        S = {n: mat_blender(SM[self.j[n]]) for n in ("pelvis", "chest") + tuple(LEG_BONES) if n in self.j}
        V = self.V
        if self.kind == "cloak":
            rows = cloak_table()["actions"].get(str(action))
            if not rows:
                return np.zeros_like(V)
            d0, d1 = (np.radians(x) for x in rows[min(k, len(rows) - 1)])
            d = cloak_bend(V, self.prm["z_top"], self.prm["z_hem"], self.prm["y_top"], d0, d1)
            return to_gltf(d @ S["chest"][:3, :3].T)
        if action in MOUNTED and self.leg_w is not None:               # riding: the hanging part lies along the legs as the skin under it would
            Vh = np.c_[V, np.ones(len(V))]
            Pp = (Vh @ S["pelvis"].T)[:, :3]
            d = np.zeros_like(V)
            for c, n in enumerate(LEG_BONES):
                if n in S:
                    d += self.leg_w[:, c:c + 1] * ((Vh @ S[n].T)[:, :3] - Pp)
            return to_gltf(d * CLOTH_MOUNTED)
        if not self.legs:
            return np.zeros_like(V)
        heads = np.array([(S[n] @ np.append(h, 1))[:3] for n, h in zip(self.legs, self.head)])
        tails = np.array([(S[n] @ np.append(t, 1))[:3] for n, t in zip(self.legs, self.tail)])
        p = self.prm
        d = hull_push(V, S["pelvis"], heads, tails, self.radius, centre_xy=tuple(p["centre"]), margin=p["margin"], kappa=p["kappa"],
                      z_top=p["z_top"], z_hem=p["z_hem"], ramp=p["ramp"], drop=p["drop"])
        return to_gltf(d)
