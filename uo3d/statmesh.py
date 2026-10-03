"""Static mesh loading for the item (glTF/GLB with embedded or external textures, OBJ) - numpy + Pillow only."""
import io, json, os, re, struct, base64
import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Material:
    def __init__(self, color=(0.8, 0.8, 0.8, 1.0), tex=None, metal=0.0):
        self.color = np.array(color, float)
        self.tex = tex                  # (H,W,4) float 0..1 or None
        self.metal = metal


class Mesh:
    def __init__(self):
        self.pos = np.zeros((0, 3)); self.nrm = np.zeros((0, 3)); self.uv = np.zeros((0, 2))
        self.tri = np.zeros((0, 3), int); self.mat_of_tri = np.zeros(0, int); self.mats = []
        self.names = []


def _acc(js, buf, i):
    a = js["accessors"][i]
    dt = np.dtype(CT[a["componentType"]]); n = NC[a["type"]]
    if "bufferView" not in a:
        return np.zeros((a["count"], n), dt)
    bv = js["bufferViews"][a["bufferView"]]
    b = buf[bv["buffer"]] if isinstance(buf, list) else buf
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    if stride and stride != dt.itemsize*n:
        raw = np.frombuffer(b, np.uint8, count=stride*a["count"], offset=start).reshape(a["count"], stride)
        arr = np.frombuffer(np.ascontiguousarray(raw[:, :dt.itemsize*n]).tobytes(), dt).reshape(a["count"], n)
    else:
        arr = np.frombuffer(b, dt, count=a["count"]*n, offset=start).reshape(a["count"], n)
    if a.get("normalized") and dt != np.float32:
        arr = arr.astype(float) / np.iinfo(dt).max
    return arr


def _node_matrix(n):
    if "matrix" in n:
        return np.array(n["matrix"], float).reshape(4, 4).T
    M = np.eye(4)
    t = n.get("translation", [0, 0, 0]); r = n.get("rotation", [0, 0, 0, 1]); s = n.get("scale", [1, 1, 1])
    x, y, z, w = r
    R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                  [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                  [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    M[:3, :3] = R * np.array(s)[None, :]; M[:3, 3] = t
    return M


def _image(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    if max(im.size) > 1024:
        im.thumbnail((1024, 1024))
    return np.asarray(im, float) / 255.0


def load_gltf(path, skip=()):
    raw = open(path, "rb").read()
    base = os.path.dirname(os.path.abspath(path))
    if raw[:4] == b"glTF":
        off, ch = 12, []
        while off < len(raw):
            n, t = struct.unpack_from("<I4s", raw, off); ch.append(raw[off+8:off+8+n]); off += 8+n
        js = json.loads(ch[0]); bufs = [ch[1]] if len(ch) > 1 else []
    else:
        js = json.loads(raw.decode("utf-8")); bufs = []
    for b in js.get("buffers", [])[len(bufs):]:
        uri = b.get("uri", "")
        bufs.append(base64.b64decode(uri.split(",", 1)[1]) if uri.startswith("data:") else open(os.path.join(base, uri), "rb").read())
    tex_cache = {}

    def texture(ti):
        if ti in tex_cache:
            return tex_cache[ti]
        img = js["images"][js["textures"][ti]["source"]]
        if "bufferView" in img:
            bv = js["bufferViews"][img["bufferView"]]; b = bufs[bv["buffer"]]; o = bv.get("byteOffset", 0)
            data = b[o:o+bv["byteLength"]]
        elif img.get("uri", "").startswith("data:"):
            data = base64.b64decode(img["uri"].split(",", 1)[1])
        else:
            data = open(os.path.join(base, img["uri"]), "rb").read()
        tex_cache[ti] = _image(data)
        return tex_cache[ti]

    mats = []
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        tex = None
        if "baseColorTexture" in pbr:
            try:
                tex = texture(pbr["baseColorTexture"]["index"])
            except Exception:  # noqa: BLE001
                tex = None
        mats.append(Material(pbr.get("baseColorFactor", [1, 1, 1, 1]), tex, pbr.get("metallicFactor", 0.0)))
    mats.append(Material())                         # default material
    default = len(mats)-1
    out = Mesh(); out.mats = mats
    P, N, U, T, MT = [], [], [], [], []
    skipl = [s.lower() for s in skip if s]
    scene = js["scenes"][js.get("scene", 0)]

    def walk(i, M):
        n = js["nodes"][i]
        W = M @ _node_matrix(n)
        nm = (n.get("name") or "").lower()
        mname = (js["meshes"][n["mesh"]].get("name") or "").lower() if "mesh" in n else ""
        if "mesh" in n and not any(s in nm or s in mname for s in skipl):
            for p in js["meshes"][n["mesh"]]["primitives"]:
                if p.get("mode", 4) != 4:
                    continue
                a = p["attributes"]
                pos = _acc(js, bufs, a["POSITION"]).astype(float)
                idx = _acc(js, bufs, p["indices"]).astype(int).reshape(-1, 3) if "indices" in p else np.arange(len(pos)).reshape(-1, 3)
                if "NORMAL" in a:
                    nr = _acc(js, bufs, a["NORMAL"]).astype(float)
                else:
                    nr = np.zeros_like(pos)
                uv = _acc(js, bufs, a["TEXCOORD_0"]).astype(float) if "TEXCOORD_0" in a else np.zeros((len(pos), 2))
                posw = pos @ W[:3, :3].T + W[:3, 3]
                nrw = nr @ np.linalg.inv(W[:3, :3]).T
                base = sum(len(x) for x in P)
                P.append(posw); N.append(nrw); U.append(uv); T.append(idx + base)
                MT.append(np.full(len(idx), p.get("material", default) if p.get("material") is not None else default))
                out.names.append(nm or mname)
        for c in n.get("children", []):
            walk(c, W)

    for r in scene["nodes"]:
        walk(r, np.eye(4))
    if not P:
        raise ValueError("Model nie zawiera żadnej siatki (albo wszystkie elementy pominięto).")
    out.pos = np.concatenate(P); out.nrm = np.concatenate(N); out.uv = np.concatenate(U)
    out.tri = np.concatenate(T); out.mat_of_tri = np.concatenate(MT)
    return finish(out)


def load_obj(path, skip=()):
    vs, vts, vns, faces, mats_of = [], [], [], [], []
    kd = {}
    cur = 0; matnames = ["default"]
    base = os.path.dirname(os.path.abspath(path))
    for line in open(path, encoding="utf-8", errors="replace"):
        t = line.split()
        if not t:
            continue
        if t[0] == "v":
            vs.append([float(x) for x in t[1:4]])
        elif t[0] == "vt":
            vts.append([float(x) for x in t[1:3]])
        elif t[0] == "vn":
            vns.append([float(x) for x in t[1:4]])
        elif t[0] == "mtllib":
            try:
                name = None
                for ml in open(os.path.join(base, " ".join(t[1:])), encoding="utf-8", errors="replace"):
                    q = ml.split()
                    if q and q[0] == "newmtl":
                        name = " ".join(q[1:])
                    elif q and q[0] == "Kd" and name:
                        kd[name] = [float(x) for x in q[1:4]]
            except OSError:
                pass
        elif t[0] == "usemtl":
            nm = " ".join(t[1:])
            if nm not in matnames:
                matnames.append(nm)
            cur = matnames.index(nm)
        elif t[0] == "f":
            ids = []
            for tok in t[1:]:
                p = tok.split("/")
                ids.append((int(p[0]), int(p[1]) if len(p) > 1 and p[1] else 0, int(p[2]) if len(p) > 2 and p[2] else 0))
            for k in range(1, len(ids)-1):
                faces.append((ids[0], ids[k], ids[k+1])); mats_of.append(cur)
    if not faces:
        raise ValueError("Plik OBJ nie zawiera powierzchni.")
    V = np.array(vs, float)
    pos, uv, nr, tri = [], [], [], []
    seen = {}
    for f in faces:
        row = []
        for (vi, ti, ni) in f:
            vi = vi-1 if vi > 0 else len(V)+vi
            key = (vi, ti, ni)
            if key not in seen:
                seen[key] = len(pos)
                pos.append(V[vi])
                uv.append(vts[ti-1] if ti > 0 and ti <= len(vts) else [0, 0])
                nr.append(vns[ni-1] if ni > 0 and ni <= len(vns) else [0, 0, 0])
            row.append(seen[key])
        tri.append(row)
    m = Mesh()
    m.pos = np.array(pos, float); m.nrm = np.array(nr, float); m.uv = np.array(uv, float); m.tri = np.array(tri, int)
    m.mats = [Material(list(kd.get(n, [0.75, 0.75, 0.75])) + [1.0]) for n in matnames]
    m.mat_of_tri = np.array(mats_of, int)
    return finish(m)


def finish(m):
    """compute missing normals; weld nothing."""
    bad = np.linalg.norm(m.nrm, axis=1) < 1e-6
    if bad.any():
        a, b, c = m.pos[m.tri[:, 0]], m.pos[m.tri[:, 1]], m.pos[m.tri[:, 2]]
        fn = np.cross(b-a, c-a)
        acc = np.zeros_like(m.pos)
        for k in range(3):
            np.add.at(acc, m.tri[:, k], fn)
        acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
        m.nrm[bad] = acc[bad]
    m.nrm /= np.maximum(np.linalg.norm(m.nrm, axis=1, keepdims=True), 1e-12)
    return m


def load(path, skip=()):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        return load_gltf(path, skip)
    if ext == ".obj":
        return load_obj(path, skip)
    raise ValueError(f"Format {ext} nie jest obsługiwany bez Blendera. Zamień model na .glb (np. darmowym konwerterem online) albo .obj.")
