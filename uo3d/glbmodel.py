"""Minimal glTF 2.0 (.glb) reader + skinning + animation sampling (numpy only)."""
import json, struct
import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def quat_mat(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def slerp(a, b, t):
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        r = a + t*(b-a)
        return r/np.linalg.norm(r)
    th = np.arccos(d)
    return (np.sin((1-t)*th)*a + np.sin(t*th)*b)/np.sin(th)


class GLB:
    def __init__(self, path):
        d = open(path, "rb").read()
        magic, ver, _ = struct.unpack_from("<4sII", d, 0)
        if magic != b"glTF":
            raise ValueError("not a .glb file")
        off, ch = 12, []
        while off < len(d):
            n, t = struct.unpack_from("<I4s", d, off)
            ch.append(d[off+8:off+8+n]); off += 8+n
        self.js = js = json.loads(ch[0]); self.bin = ch[1]
        self.nodes = js["nodes"]
        self.parent = [-1]*len(self.nodes)
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.order = self._topo()
        self.rest = [(np.array(n.get("translation", [0, 0, 0]), float), np.array(n.get("rotation", [0, 0, 0, 1]), float),
                      np.array(n.get("scale", [1, 1, 1]), float)) for n in self.nodes]
        skin = js["skins"][0]
        self.joints = skin["joints"]
        self.ibm = self.acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)   # column-major -> row-major
        self.joint_names = [self.nodes[j].get("name", "") for j in self.joints]
        prim = js["meshes"][0]["primitives"][0]
        a = prim["attributes"]
        self.pos = self.acc(a["POSITION"]).astype(float)
        self.nrm = self.acc(a["NORMAL"]).astype(float)
        self.uv = self.acc(a["TEXCOORD_0"]).astype(float) if "TEXCOORD_0" in a else None
        self.jnt = self.acc(a["JOINTS_0"]).astype(int)
        w = self.acc(a["WEIGHTS_0"]).astype(float)
        self.wgt = w / np.maximum(w.sum(1, keepdims=True), 1e-9)
        self.tri = self.acc(prim["indices"]).astype(int).reshape(-1, 3)
        self.anims = {an["name"]: an for an in js["animations"]}
        self._cache = {}

    def _topo(self):
        out, seen = [], set()
        def go(i):
            if i in seen:
                return
            if self.parent[i] >= 0:
                go(self.parent[i])
            seen.add(i); out.append(i)
        for i in range(len(self.nodes)):
            go(i)
        return out

    def acc(self, i):
        a = self.js["accessors"][i]
        bv = self.js["bufferViews"][a["bufferView"]]
        dt = np.dtype(CT[a["componentType"]]); n = NC[a["type"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0)
        if stride and stride != dt.itemsize*n:
            raw = np.frombuffer(self.bin, np.uint8, count=stride*a["count"], offset=start).reshape(a["count"], stride)
            arr = np.frombuffer(np.ascontiguousarray(raw[:, :dt.itemsize*n]).tobytes(), dt).reshape(a["count"], n)
        else:
            arr = np.frombuffer(self.bin, dt, count=a["count"]*n, offset=start).reshape(a["count"], n)
        return arr if n > 1 else arr[:, 0]

    def texture_png(self):
        im = self.js.get("images")
        if not im:
            return None
        bv = self.js["bufferViews"][im[0]["bufferView"]]
        o = bv.get("byteOffset", 0)
        return self.bin[o:o+bv["byteLength"]]

    def _sampler(self, anim, ch):
        s = anim["samplers"][ch["sampler"]]
        key = (id(anim), ch["sampler"])
        if key not in self._cache:
            self._cache[key] = (self.acc(s["input"]).astype(float), self.acc(s["output"]).astype(float), s.get("interpolation", "LINEAR"))
        return self._cache[key]

    def duration(self, name):
        a = self.anims[name]
        return max(self._sampler(a, c)[0][-1] for c in a["channels"])

    def pose(self, name, t):
        """world matrices (4x4, row-major) of all nodes at time t of animation `name` (None = rest)."""
        trs = [[r[0].copy(), r[1].copy(), r[2].copy()] for r in self.rest]
        if name is not None:
            an = self.anims[name]
            for ch in an["channels"]:
                tg = ch["target"]
                times, out, mode = self._sampler(an, ch)
                path = tg["path"]
                if t <= times[0]:
                    k0 = k1 = 0; u = 0.0
                elif t >= times[-1]:
                    k0 = k1 = len(times)-1; u = 0.0
                else:
                    k1 = int(np.searchsorted(times, t)); k0 = k1-1
                    u = (t-times[k0])/(times[k1]-times[k0])
                if mode == "STEP":
                    u = 0.0
                if path == "rotation":
                    v = slerp(out[k0], out[k1], u) if k0 != k1 and u > 0 else out[k0]
                    trs[tg["node"]][1] = v/np.linalg.norm(v)
                else:
                    v = out[k0] + u*(out[k1]-out[k0])
                    trs[tg["node"]][0 if path == "translation" else 2] = v
        W = [None]*len(self.nodes)
        for i in self.order:
            T, Q, S = trs[i]
            M = np.eye(4); M[:3, :3] = quat_mat(Q) * S[None, :]; M[:3, 3] = T
            W[i] = M if self.parent[i] < 0 else W[self.parent[i]] @ M
        return W

    def skin_matrices(self, W):
        return np.stack([W[j] @ self.ibm[k] for k, j in enumerate(self.joints)])

    def skinned(self, name, t):
        """(positions, normals) in glTF space (Y up) after skinning."""
        W = self.pose(name, t)
        SM = self.skin_matrices(W)                       # (J,4,4)
        P = np.zeros_like(self.pos); N = np.zeros_like(self.nrm)
        ph = np.c_[self.pos, np.ones(len(self.pos))]
        for k in range(self.jnt.shape[1]):
            w = self.wgt[:, k:k+1]
            if not np.any(w):
                continue
            M = SM[self.jnt[:, k]]
            P += w * np.einsum("nij,nj->ni", M[:, :3, :], ph)
            N += w * np.einsum("nij,nj->ni", M[:, :3, :3], self.nrm)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        return P, N
