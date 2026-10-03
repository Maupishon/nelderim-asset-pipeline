"""Hand-held weapons and shields on the UO body without Blender.

The motion data (calibrated on the original UO weapons) is UO_Model3D's pipeline/weapon_motion.json (class line through a grip point of the
hand bone + a turn and shift per pose) and, for shields, the per-frame keys of shield.L (uo_shield_keys.py). A weapon is rigid on its own
bone, which is a child of the hand bone: the skinning matrix of that bone is
    W_hand_pose @ C @ basis @ C^-1 @ IBM_hand          (C = rest of the bone in the hand's axes, basis = T(shift) @ R(turn))
"""
import json
import math
import os
import re

import numpy as np

CLASS_OF_KIND = {"weapon1h": "weapon1h.R", "polearm": "polearm.L", "axe2h": "axe2h.L", "bow": "bow.L"}
# shield disc calibrated on the left forearm (uo_place_shield.py): centre and normal in the forearm's axes
SHIELD_CENTRE = np.array([-0.07, 0.21, -0.03])
SHIELD_NORMAL = np.array([-0.99622, -0.07987, 0.03415]); SHIELD_NORMAL /= np.linalg.norm(SHIELD_NORMAL)


def rot_axis(axis, ang):
    a = np.asarray(axis, float); a = a / np.linalg.norm(a)
    x, y, z = a; c, s = math.cos(ang), math.sin(ang); C = 1 - c
    return np.array([[c+x*x*C, x*y*C-z*s, x*z*C+y*s], [y*x*C+z*s, c+y*y*C, y*z*C-x*s], [z*x*C-y*s, z*y*C+x*s, c+z*z*C]])


def quat_axis(axis, ang):
    a = np.asarray(axis, float); a = a / np.linalg.norm(a)
    return np.array([math.cos(ang/2), *(a * math.sin(ang/2))])          # w, x, y, z


def qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])


def qmat(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def rv_quat(r):
    r = np.asarray(r, float); ang = np.linalg.norm(r)
    return quat_axis(r / ang, ang) if ang > 1e-9 else np.array([1.0, 0, 0, 0])


def T(v):
    M = np.eye(4); M[:3, 3] = v; return M


def M4(R3):
    M = np.eye(4); M[:3, :3] = R3; return M


def arc(a, b):
    """rotation matrix taking unit vector a to unit vector b (shortest arc)."""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(a @ b)
    if c < -0.999999:
        p = np.cross(a, [1, 0, 0]); p = p if np.linalg.norm(p) > 1e-6 else np.cross(a, [0, 0, 1])
        return rot_axis(p, math.pi)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def find_motion(body_glb):
    """pipeline/weapon_motion.json next to the project's model/ folder (UO_Model3D layout)."""
    base = os.path.dirname(os.path.abspath(body_glb))
    for cand in (os.path.join(base, "..", "pipeline", "weapon_motion.json"), os.path.join(base, "weapon_motion.json")):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


class RigidBone:
    """One rigid bone below a body joint: rest C (4x4 in the joint's axes), per-frame basis from `pose(action, k)`."""

    def __init__(self, body, parent_name, C):
        self.body = body
        self.j = body.names.index(parent_name)
        self.node = body.g.joints[self.j]
        self.ibm = body.g.ibm[self.j]                           # world bind -> joint axes
        self.Hbind = np.linalg.inv(self.ibm)                    # joint axes -> world bind
        self.C = C

    def matrix(self, W, basis):
        return W[self.node] @ self.C @ basis @ np.linalg.inv(self.C) @ self.ibm


class Weapon(RigidBone):
    def __init__(self, body, motion, cls):
        self.cls = cls
        self.WM = motion[cls]
        piv = np.array(self.WM["pivot"], float)
        super().__init__(body, self.WM["parent"], T(piv))
        self.piv = piv
        self.dirv = np.array(self.WM["dir"], float); self.dirv /= np.linalg.norm(self.dirv)
        self.roll = self.WM.get("roll")

    def class_length(self):
        L = [hi - lo for lo, hi in self.WM["anims"].values()]
        return float(np.median(L))

    def place(self, P, ref=None, roll_deg=None):
        """P (N,3): the weapon modelled upright (shaft along +Y, tip up, butt lowest) -> bind-space vertices on the class line."""
        H3 = self.Hbind[:3, :3]
        pw = self.Hbind[:3, :3] @ self.piv + self.Hbind[:3, 3]
        d = H3 @ self.dirv; d /= np.linalg.norm(d)
        R = arc(np.array([0.0, 1, 0]), d)
        ru = None
        if self.roll:
            delta = math.radians(roll_deg) if roll_deg is not None else self.roll["offsets"].get(str(ref if ref is not None else self.roll["ref"]), 0.0)
            ru = H3 @ (rot_axis(self.dirv, delta) @ np.array(self.roll["e1"], float)); ru /= np.linalg.norm(ru)
        ctr = np.array([(P[:, 0].min() + P[:, 0].max()) / 2, 0.0, (P[:, 2].min() + P[:, 2].max()) / 2])
        y0 = P[:, 1].min()
        Rr = np.eye(3)
        if ru is not None:
            x1 = R @ np.array([1.0, 0, 0])
            ang = math.atan2(float(d @ np.cross(x1, ru)), float(x1 @ ru))
            Rr = rot_axis(d, ang)
        start = pw + d * self.WM["butt"]
        Q = (P - np.array([ctr[0], y0, ctr[2]])) @ R.T @ Rr.T + start
        return Q

    def basis(self, action, k):
        p = self.WM["poses"].get("%d,%d" % (action, k))
        if p is None:
            return np.eye(4)
        q = rv_quat(p[:3])
        if self.roll is not None:
            q = qmul(q, quat_axis(self.dirv, self.roll["phi"].get("%d,%d" % (action, k), 0.0)))
        B = M4(qmat(q)); B[:3, 3] = p[3:]
        return B


class Shield(RigidBone):
    """shield.L: a bone on the left forearm; rest = disc centre/normal (uo_place_shield.py), keys per frame from uo_shield_keys.py."""

    def __init__(self, body, keys_json):
        n = SHIELD_NORMAL
        up = -np.cross(n, [0.0, 1, 0]); up /= np.linalg.norm(up)
        x = np.cross(up, n); x /= np.linalg.norm(x)
        C = np.eye(4); C[:3, 0], C[:3, 1], C[:3, 2] = x, up, n; C[:3, 3] = SHIELD_CENTRE
        super().__init__(body, "forearm.L", C)
        self.frames = keys_json

    def place(self, P, gap=0.01):
        """P: shield modelled with its face towards +Z (front view), top +Y. -> bind-space vertices on the left forearm."""
        c = self.Hbind[:3, :3] @ SHIELD_CENTRE + self.Hbind[:3, 3]
        Rw = self.Hbind[:3, :3] @ self.C[:3, :3]                    # bone axes in the world bind pose (X width, Y up, Z face)
        mid = (P.min(0) + P.max(0)) / 2
        Q = (P - mid) @ Rw.T + c
        # slide towards the arm until nothing is closer than `gap` to the forearm skin
        g = self.body.g
        arm = np.isin(g.jnt[np.arange(len(g.jnt)), np.argmax(g.wgt, 1)], [self.j, self.body.names.index("forearm_twist.L")] if "forearm_twist.L" in self.body.names else [self.j])
        if arm.any():
            A = g.pos[arm]; An = g.nrm[arm]
            from .engine import nearest
            ni, nd = nearest(Q, A)
            d = ((Q - A[ni]) * An[ni]).sum(1)
            near = nd < 0.12
            if near.any():
                t = max(0.0, gap - float(d[near].min()))
                Q = Q + (Rw[:, 2] * t)
        return Q

    def basis(self, action, k):
        rows = self.frames.get(str(action))
        if not rows or k >= len(rows):
            return np.eye(4)
        p = rows[k]
        B = M4(qmat(rv_quat(p[:3]))); B[:3, 3] = p[3:]
        return B


def load_shield_keys(path_or_dir):
    """FRAMES = json.loads('...') inside UO_Model3D's pipeline/uo_shield_keys.py."""
    p = path_or_dir
    if not p or not os.path.isfile(p):
        return None
    t = open(p, encoding="utf-8").read()
    m = re.search(r"FRAMES\s*=\s*json\.loads\('(.*?)'\)", t, re.S)
    return json.loads(m.group(1)) if m else None


def find_shield_keys(body_glb):
    base = os.path.dirname(os.path.abspath(body_glb))
    cand = os.path.join(base, "..", "pipeline", "uo_shield_keys.py")
    return os.path.abspath(cand) if os.path.isfile(cand) else None
