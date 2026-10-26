"""uo3d/tattoo.py - decor tattoos for the decor layers (0x20-0x25): a decal on the body's own limb, a relief on the torso, their paperdoll gumps.

Everything is in the coordinates of UO_Body_0x190.glb (glTF: Y up, front +Z, metres; the character's right side is -X, the ".R" bones).

  arm_decal(model, body)        limb model (a textured arm with a tattoo) -> a decal: the body's own right-arm skin, 4 mm out, coloured from the
                                model, vertex RGBA (alpha = ink; the renderer cuts at 0.5). Render it with `nelderim.py uo3d --kind arms
                                --adjust '{"fit": false}' --own-side R --occlude-torso`.
  arm_gump(decal, body_gump)    the ink unrolled along the arm (t, phi) and drawn on the arm of the body gump 12 / 13.
  relief(design, body)          2D design (white background) -> relief .glb on the chest: black linework high, bevelled edge, the base follows the
                                true front surface of the body; also the top-only variant for rendering (`--kind plate --occlude-torso`).
  torso_gump(texture, gump)     the texture on the chest of the body gump, shaded by it, wrapped round the chest, UNDER the bra of gump 13.
Needs numpy, Pillow and scipy.
"""
from __future__ import annotations
import io, json, struct
import numpy as np
from PIL import Image


def _scipy():
    try:
        from scipy import ndimage as ndi
        from scipy.spatial import cKDTree
    except ImportError:
        raise SystemExit("[BŁĄD  ] tatuaże wymagają scipy: python -m pip install scipy")
    return ndi, cKDTree


# ---- paperdoll geometry of the body gumps 12 (male) / 13 (female), 260 x 237 -----------------------------------------------------------
PXM = 90.5                                                   # px per metre in the paperdoll (feet at y 221)
ARM_POLY = {"12": [(70, 84), (68.5, 99), (67.5, 112.5), (55, 113.5)], "13": [(73, 84), (71, 99), (70, 111), (53, 112.5)]}   # shoulder, elbow, wrist
ARM_HALF = 4.5                                               # px, half-width of the arm in the gump
R_CHEST = 0.17                                               # m, radius of the chest cylinder the tattoo wraps round
FEET_Y = 220.65                                              # px of y = 0 on the gump: calibrated so that 1.30 m (sternum) is row 103, as approved in game
GUMP_IDS = {"male": 50000, "female": 60000}                  # + anim body id


# ---- arm decal ------------------------------------------------------------------------------------------------------------------------
def joint_rest(g, name):
    """rest position (glTF space) of a joint of the body GLB"""
    k = g.joint_names.index(name)
    return np.linalg.inv(g.ibm[k])[:3, 3]


def sample_texture(tex, uv):
    """bilinear sample of an (H, W, 4) float texture at uv (glTF convention: v down from the top)"""
    H, W = tex.shape[:2]
    u = np.clip(uv[:, 0] % 1.0 * (W - 1), 0, W - 1); v = np.clip(uv[:, 1] % 1.0 * (H - 1), 0, H - 1)
    x0, y0 = np.floor(u).astype(int), np.floor(v).astype(int)
    x1, y1 = np.minimum(x0 + 1, W - 1), np.minimum(y0 + 1, H - 1)
    fx, fy = (u - x0)[:, None], (v - y0)[:, None]
    return tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy) + tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy


def arm_decal(model_path, body, out_glb, scale=0.205, wrist_x=1.45, offset=0.004, thr=0.12, reach=0.03):
    """model_path: a glb with a whole right arm lying along +X (shoulder at the lowest x, fingers at the highest, the thumb towards -Z) and a base
    colour texture. scale: model units -> metres (shoulder joint to wrist of the body arm = (wrist_x - x_min) * scale). thr: colour distance from the
    skin tone of the model from which a vertex counts as ink. Returns the arrays the gump needs."""
    from . import statmesh
    from .fromvd import write_glb
    ndi, cKDTree = _scipy()
    g = body.g if hasattr(body, "g") else body
    S = joint_rest(g, "upper_arm.R"); Hd = joint_rest(g, "hand.R")
    d = Hd - S; d[2] = 0; d /= np.linalg.norm(d)
    xb = d; zb = np.array([0, 0, -1.0]); yb = np.cross(zb, xb)
    Rm = np.stack([xb, yb, zb], 1)                                           # model axes -> body axes (thumb forward, a proper rotation)
    m = statmesh.load(model_path)
    P, N = m.pos.copy(), m.nrm.copy()
    w = P[np.abs(P[:, 0] - wrist_x) < 0.08]
    cw = np.array([wrist_x, w[:, 1].mean(), w[:, 2].mean()])
    Pb = ((P - cw) * scale) @ Rm.T + Hd
    keep = P[:, 0] <= wrist_x                                                # the hand is cut off
    C = sample_texture(m.mats[0].tex, m.uv)[:, :3]
    Pk, Ck = Pb[keep], C[keep]
    skin = np.median(Ck, 0)
    # the body's own right-arm skin
    names = g.joint_names
    want = {i for i, n in enumerate(names) if n in ("upper_arm.R", "upper_arm_twist.R", "forearm.R", "forearm_twist.R")}
    dom = g.jnt[np.arange(len(g.pos)), np.argmax(g.wgt, 1)]
    sel = np.isin(dom, list(want))
    tr = g.tri[sel[g.tri].all(1)]
    used = np.unique(tr); rm = -np.ones(len(g.pos), int); rm[used] = np.arange(len(used))
    Pd = g.pos[used] + g.nrm[used] * offset; Nd = g.nrm[used]
    dist, ix = cKDTree(Pk).query(Pd)
    col = Ck[ix]
    alpha = np.clip((np.linalg.norm(col - skin, axis=1) - thr * 0.6) / (thr * 0.8), 0, 1) * (dist < reach)   # soft ink strength per vertex
    tri = rm[tr]
    tri = tri[(alpha[tri] > 0.05).any(1)]
    u2 = np.unique(tri); r2 = -np.ones(len(used), int); r2[u2] = np.arange(len(u2))
    write_glb(out_glb, Pd[u2], Nd[u2], np.c_[col, alpha][u2], r2[tri], {"uo3d_rest": True, "name": "tatuaz_reka", "source": str(model_path)})
    L = float(np.linalg.norm(Hd - S))
    rel = Pd - S
    e1 = np.array([0, 0, 1.0]); e2 = np.cross(d, e1)
    perp = rel - np.outer(rel @ d, d)
    return {"t": rel @ d / L, "phi": np.arctan2(perp @ e2, perp @ e1), "col": col, "alpha": alpha, "length": L,
            "ink_vertices": int((alpha > 0.5).sum()), "decal_vertices": int(len(u2)), "decal_triangles": int(len(tri))}


def _seg_project(P, poly):
    """arc-length fraction, signed distance to the polyline (left normal) and distance of every point P (n, 2)"""
    seg = np.diff(poly, axis=0); ln = np.hypot(seg[:, 0], seg[:, 1]); cum = np.r_[0, np.cumsum(ln)]
    best = np.full(len(P), 1e9); a = np.zeros(len(P)); s = np.zeros(len(P))
    for i in range(len(seg)):
        u = seg[i] / ln[i]
        q = P - poly[i]
        along = np.clip(q @ u, 0, ln[i])
        dist_ = np.hypot(*(P - (poly[i] + np.outer(along, u))).T)
        sign = np.sign(q[:, 0] * (-u[1]) + q[:, 1] * u[0])
        better = dist_ < best
        best[better] = dist_[better]; a[better] = (cum[i] + along)[better]; s[better] = (sign * dist_)[better]
    return a / cum[-1], s, best


def arm_gump(decal, body_gump, gid, out_png, radius=0.04, half=ARM_HALF):
    """draw the ink of `decal` (arm_decal result) on the arm of the body gump (RGBA png / array); gid '12' or '13'"""
    ndi, cKDTree = _scipy()
    body = np.array(Image.open(body_gump).convert("RGBA")).astype(float) if not isinstance(body_gump, np.ndarray) else body_gump.astype(float)
    tree = cKDTree(np.c_[decal["t"] * decal["length"], decal["phi"] * radius])
    H, W = body.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    P = np.c_[xx.ravel() + 0.5, yy.ravel() + 0.5]
    a, s, dm = _seg_project(P, np.array(ARM_POLY[gid], float))
    mask = (body[..., 3].ravel() > 0) & (dm <= half + 1.5) & (a >= 0.0) & (a <= 1.0)
    ph = np.arcsin(np.clip(s[mask] / half, -0.97, 0.97))
    dd, ix = tree.query(np.c_[a[mask] * decal["length"], ph * radius], k=3)
    wgt = 1.0 / (dd + 1e-3); wgt /= wgt.sum(1, keepdims=True)
    A = (decal["alpha"][ix] * wgt).sum(1); Cc = (decal["col"][ix] * wgt[..., None]).sum(1)
    lum = body.reshape(-1, 4)[mask][:, :3].mean(1)
    f = np.clip(lum / np.median(lum), 0.55, 1.3)[:, None]
    out = np.zeros((H * W, 4)); idx = np.nonzero(mask)[0]; ink = A >= 0.5
    out[idx[ink], :3] = np.clip(Cc[ink] * f[ink] * 255 * 0.85, 0, 255); out[idx[ink], 3] = 255
    out = out.reshape(H, W, 4).astype(np.uint8)
    Image.fromarray(out).save(out_png)
    return int(ink.sum())


# ---- torso relief ---------------------------------------------------------------------------------------------------------------------
def cutout(rgb_img):
    """a design on a white card -> (rgb uint8, alpha bool) cropped to the design; only the white connected to the border is background"""
    ndi, _ = _scipy()
    im = np.array(rgb_img.convert("RGB")).astype(int)
    mx, mn = im.max(2), im.min(2)
    white = (mn >= 232) & ((mx - mn) <= 22)
    lab, n = ndi.label(white)
    edge = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    bg = np.isin(lab, edge[edge > 0])                                          # label 0 = not white: never background
    alpha = ndi.binary_opening(~bg, iterations=1)
    lab, n = ndi.label(alpha)
    if n == 0:
        raise SystemExit("[BŁĄD  ] w obrazie nie ma projektu (samo białe tło)")
    sz = ndi.sum(alpha, lab, range(1, n + 1))
    ys, xs = np.nonzero(lab == int(np.argmax(sz)) + 1)
    box = np.zeros_like(alpha); box[max(ys.min() - 25, 0):ys.max() + 26, max(xs.min() - 25, 0):xs.max() + 26] = True   # the card's edge / shadow lies farther
    alpha &= box
    lab, n = ndi.label(alpha); sz = ndi.sum(alpha, lab, range(1, n + 1))
    alpha = np.isin(lab, [i + 1 for i, s in enumerate(sz) if s > 200])
    ys, xs = np.nonzero(alpha)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb = im[y0:y1, x0:x1].astype(np.uint8)
    al = ndi.binary_erosion(alpha[y0:y1, x0:x1], iterations=1)               # no white JPEG fringe
    idx = ndi.distance_transform_edt(~al, return_distances=False, return_indices=True)
    return rgb[idx[0], idx[1]], al                                           # colour bleeds into the transparent pixels


def front_surface(g, cell=0.001, x_range=(-0.26, 0.26), y_range=(0.9, 1.6)):
    """the true front surface of the body (orthographic depth buffer, 1 mm per pixel, never below the skin): (gx, gy, Z[y, x])"""
    from . import raster as R
    ndi, _ = _scipy()
    gx = np.arange(x_range[0], x_range[1] + cell, cell); gy = np.arange(y_range[0], y_range[1] + cell, cell)
    XY = np.stack([(g.pos[:, 0] - gx[0]) / cell, (gy[-1] - g.pos[:, 1]) / cell], 1)
    tid, dep = R.raster(XY, -g.pos[:, 2], g.tri, len(gx), len(gy))
    Z = np.where(tid >= 0, -dep, np.nan)[::-1]                               # row 0 = lowest y
    ii = ndi.distance_transform_edt(np.isnan(Z), return_distances=False, return_indices=True)
    Zr = Z[ii[0], ii[1]]
    return gx, gy, np.maximum(ndi.gaussian_filter(ndi.grey_dilation(Zr, size=(3, 3)), 2.0), Zr)


def relief(design_img, surface, out_glb, width=0.24, centre=(0.0, 1.30), grid=200, base=0.0012, line_h=0.0025, top_only_glb=None):
    """design_img: PIL image (design on white); surface: front_surface(...) result. Writes the relief .glb (textured top + smooth back), optionally the
    top-only one for rendering. Returns the texture (RGBA uint8) and stats."""
    ndi, _ = _scipy()
    gx, gy, Z = surface
    cell = gx[1] - gx[0]
    dzdy, dzdx = np.gradient(Z, cell)
    rgb, al = cutout(design_img)
    tex = np.dstack([rgb, (al * 255).astype(np.uint8)])
    Hh, Ww = al.shape
    buf = io.BytesIO(); Image.fromarray(tex, "RGBA").save(buf, "PNG"); png = buf.getvalue()
    lum = rgb.astype(float).mean(2); sat = rgb.max(2).astype(int) - rgb.min(2).astype(int)
    line = ndi.gaussian_filter(((lum < 75) & (sat < 60)).astype(float), 0.8)         # black linework
    dist = ndi.distance_transform_edt(al)

    def surf(x, y):
        fx = (x - gx[0]) / cell; fy = (y - gy[0]) / cell
        z = ndi.map_coordinates(Z, [fy, fx], order=1, mode="nearest")
        ddx = ndi.map_coordinates(dzdx, [fy, fx], order=1, mode="nearest"); ddy = ndi.map_coordinates(dzdy, [fy, fx], order=1, mode="nearest")
        nrm = np.stack([-ddx, -ddy, np.ones_like(ddx)], -1); nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        return z, nrm

    NX = grid; NY = int(round(grid * Hh / Ww)); w_m = width; h_m = width * Hh / Ww
    U, V = np.meshgrid(np.linspace(0, 1, NX + 1), np.linspace(0, 1, NY + 1))          # V = 0 at the top of the design
    px = np.clip((U * (Ww - 1)).round().astype(int), 0, Ww - 1); py = np.clip((V * (Hh - 1)).round().astype(int), 0, Hh - 1)
    ins = al[py, px]
    bev = np.clip(dist[py, px] / 5.0, 0, 1); bev = bev * bev * (3 - 2 * bev)                    # 5 px bevel to the silhouette
    thick = (base + line_h * line[py, px]) * bev * ins
    X = centre[0] + (U - 0.5) * w_m; Y = centre[1] + (0.5 - V) * h_m
    zb, nb = surf(X, Y)
    P_back = np.stack([X, Y, zb], -1) + nb * 0.0004
    P_top = np.stack([X, Y, zb], -1) + nb * (0.0004 + thick[..., None])
    cellok = ins[:-1, :-1] & ins[1:, :-1] & ins[:-1, 1:] & ins[1:, 1:]
    used = np.zeros(U.shape, bool)
    for dy in (0, 1):
        for dx in (0, 1):
            used[dy:dy + NY, dx:dx + NX] |= cellok
    vid = -np.ones(U.shape, int); vid[used] = np.arange(used.sum())
    ii, jj = np.nonzero(cellok)
    a, b, c, d = vid[ii, jj], vid[ii, jj + 1], vid[ii + 1, jj + 1], vid[ii + 1, jj]
    tri = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    Pt, Pb = P_top[used], P_back[used]
    uv = np.stack([U[used] * (Ww - 1) / Ww + 0.5 / Ww, V[used] * (Hh - 1) / Hh + 0.5 / Hh], 1)

    def normals(P, T):
        fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]); acc = np.zeros_like(P)
        for k in range(3):
            np.add.at(acc, T[:, k], fn)
        return acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)

    if np.mean(normals(Pt, tri)[:, 2]) < 0:                                  # the top faces +Z (outwards)
        tri = tri[:, ::-1]
    Nt = normals(Pt, tri); Nb = normals(Pb, tri[:, ::-1])
    extras = {"uo3d_rest": True, "name": "tatuaz_tors", "frame": "UO_Body_0x190 body coordinates, Y up, front +Z, metres",
              "width_m": w_m, "height_m": h_m, "centre": list(centre)}
    for path, both in ((out_glb, True), (top_only_glb, False)):
        if path:
            _write_relief(path, Pt, Nt, uv, tri, Pb, Nb, png, extras, both)
    return tex, {"vertices": int(len(Pt) * 2), "triangles": int(len(tri) * 2), "width_m": w_m, "height_m": h_m, "relief_mm": float(thick.max()) * 1000}


def _write_relief(path, Pt, Nt, uv, tri, Pb, Nb, png, extras, with_back):
    blobs, views, accs = [], [], []

    def add(arr, ct, typ, target=None, mm=False):
        raw = np.ascontiguousarray(arr).tobytes(); off = sum((len(x) + 3) // 4 * 4 for x in blobs)
        blobs.append(raw); views.append({"buffer": 0, "byteOffset": off, "byteLength": len(raw), **({"target": target} if target else {})})
        ac = {"bufferView": len(views) - 1, "componentType": ct, "count": len(arr), "type": typ}
        if mm:
            ac["min"] = arr.min(0).tolist(); ac["max"] = arr.max(0).tolist()
        accs.append(ac); return len(accs) - 1

    f32 = np.float32
    ap = add(Pt.astype(f32), 5126, "VEC3", 34962, True); an = add(Nt.astype(f32), 5126, "VEC3", 34962); au = add(uv.astype(f32), 5126, "VEC2", 34962)
    ai = add(tri.astype(np.uint32).ravel(), 5125, "SCALAR", 34963)
    prims = [{"attributes": {"POSITION": ap, "NORMAL": an, "TEXCOORD_0": au}, "indices": ai, "material": 0}]
    if with_back:                                                            # the smooth back, 0.4 mm off the skin, its own flat material
        bp = add(Pb.astype(f32), 5126, "VEC3", 34962, True); bn = add(Nb.astype(f32), 5126, "VEC3", 34962)
        bi = add(tri[:, ::-1].astype(np.uint32).ravel(), 5125, "SCALAR", 34963)
        prims.append({"attributes": {"POSITION": bp, "NORMAL": bn}, "indices": bi, "material": 1})
    off = sum((len(x) + 3) // 4 * 4 for x in blobs); blobs.append(png); views.append({"buffer": 0, "byteOffset": off, "byteLength": len(png)})
    js = {"asset": {"version": "2.0", "generator": "Nelderim Lab uo3d.tattoo", "extras": extras},
          "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": extras["name"]}], "meshes": [{"primitives": prims}],
          "materials": [{"name": "tusz", "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": True,
                         "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 0.75}},
                        {"name": "tyl", "pbrMetallicRoughness": {"baseColorFactor": [0.30, 0.18, 0.12, 1], "metallicFactor": 0, "roughnessFactor": 0.9}}],
          "textures": [{"source": 0, "sampler": 0}], "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
          "images": [{"bufferView": len(views) - 1, "mimeType": "image/png"}],
          "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": sum((len(x) + 3) // 4 * 4 for x in blobs)}]}
    bin_ = b"".join(x + b"\0" * ((4 - len(x) % 4) % 4) for x in blobs)
    jb = json.dumps(js).encode(); jb += b" " * ((4 - len(jb) % 4) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(bin_))); fh.write(struct.pack("<I4s", len(jb), b"JSON")); fh.write(jb)
        fh.write(struct.pack("<I4s", len(bin_), b"BIN\0")); fh.write(bin_)


def icon(texture_rgba, size=44):
    """inventory icon (art): the texture box-filtered to `size` px high, binary alpha"""
    t = Image.fromarray(texture_rgba, "RGBA")
    W = max(1, round(t.width * size / t.height))
    a = np.array(t).astype(float); a[..., :3] *= a[..., 3:4] / 255
    s = np.array(Image.fromarray(a.astype(np.uint8), "RGBA").resize((W, size), Image.BOX)).astype(float)
    al = s[..., 3:4]
    rgb = np.where(al > 1, s[..., :3] / np.maximum(al / 255, 1e-6), 0)
    out = np.dstack([np.clip(rgb * 0.92, 0, 255), np.where(al >= 128, 255, 0)]).astype(np.uint8)
    out[out[..., 3] == 0] = 0
    return Image.fromarray(out, "RGBA")


# ---- torso gump -----------------------------------------------------------------------------------------------------------------------
def bra_mask(gump13):
    """the bandeau of the female body gump 13 (body value 401): cloth is slightly yellow (R > B), the skin is neutral grey"""
    ndi, _ = _scipy()
    b = np.array(gump13.convert("RGBA") if isinstance(gump13, Image.Image) else Image.open(gump13).convert("RGBA")).astype(int)
    cloth = ((b[..., 0] - b[..., 2]) >= 6) & (b[..., 3] > 0)
    box = np.zeros_like(cloth); box[88:118, 74:108] = True
    m = ndi.binary_closing(cloth & box, structure=np.ones((3, 3)), iterations=2)
    return ndi.binary_fill_holes(m) & box


def torso_gump(texture_rgba, body_gump, out_png, centre=(91.0, 103.0), width=0.24, bra=None, shade_gamma=1.25, warp=6.0, ss=4):
    """texture_rgba: (H, W, 4) uint8 (relief texture). centre (px): sternum on the gump (y = FEET_Y - 1.30 m * 90.5 = 103). bra: bool mask hidden under cloth
    of the gump (gump 13). Returns the number of ink pixels."""
    ndi, _ = _scipy()
    tex = texture_rgba.astype(float).copy(); tex[..., :3] *= tex[..., 3:4] / 255.0           # premultiplied: the edge does not bleed
    th, tw = tex.shape[:2]
    body = np.array(Image.open(body_gump).convert("RGBA")).astype(float) if not isinstance(body_gump, np.ndarray) else body_gump.astype(float)
    H, W = body.shape[:2]
    w_px = width * PXM; h_px = w_px * th / tw
    skin = body[..., 3] > 0
    lum = body[..., :3].mean(2)
    rows = np.arange(H)[:, None]
    ref = np.percentile(lum[skin & (rows > 88) & (rows < 125)], 85)
    hgt = ndi.gaussian_filter(lum, 1.6) / ref                                # a pseudo-relief of the muscles from the shading of the body gump
    gy_, gx_ = np.gradient(hgt)
    big = np.zeros((H * ss, W * ss, 4))
    yy, xx = np.mgrid[0:H * ss, 0:W * ss]
    px_ = (xx + 0.5) / ss; py_ = (yy + 0.5) / ss
    dxm = (px_ - centre[0]) / PXM + warp * ndi.zoom(gx_, ss, order=1)[:H * ss, :W * ss] / PXM
    dym = (py_ - centre[1]) / PXM + warp * ndi.zoom(gy_, ss, order=1)[:H * ss, :W * ss] / PXM
    s_arc = R_CHEST * np.arcsin(np.clip(dxm / R_CHEST, -0.985, 0.985))      # arc length on the chest cylinder
    u = (s_arc / width + 0.5) * tw
    v = (dym / (h_px / PXM) + 0.5) * th
    ok = (u >= 0) & (u < tw - 1) & (v >= 0) & (v < th - 1)
    ui = np.clip(u, 0, tw - 1.001); vi = np.clip(v, 0, th - 1.001)
    x0 = ui.astype(int); y0 = vi.astype(int); fx = (ui - x0)[..., None]; fy = (vi - y0)[..., None]
    smp = tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x0 + 1] * fx * (1 - fy) + tex[y0 + 1, x0] * (1 - fx) * fy + tex[y0 + 1, x0 + 1] * fx * fy
    big[ok] = smp[ok]
    small = big.reshape(H, ss, W, ss, 4).mean((1, 3))
    a = small[..., 3:4]
    rgb = np.where(a > 1, small[..., :3] / np.maximum(a / 255.0, 1e-6), 0)
    ink = (a[..., 0] >= 128) & skin
    if bra is not None:
        ink &= ~bra
    f = np.clip((ndi.gaussian_filter(lum, 0.7) / ref) ** shade_gamma, 0.3, 1.12)[..., None]   # the shading of the muscles / ribs shows through
    out = np.zeros((H, W, 4)); out[..., :3] = np.clip((0.9 * rgb + 0.1 * body[..., :3] * 0.5) * f, 0, 255); out[..., 3] = np.where(ink, 255, 0)
    out = out.astype(np.uint8); out[out[..., 3] == 0] = 0
    Image.fromarray(out).save(out_png)
    return int(ink.sum())


def preview(body_gump, tattoo_png, out_png, box=(50, 70, 135, 135), zoom=8, bra=None):
    """body gump + tattoo gump on a grey ground, enlarged (the bra is drawn over the tattoo)"""
    b = Image.open(body_gump).convert("RGBA")
    t = Image.new("RGBA", b.size, (70, 70, 76, 255)); t.alpha_composite(b); t.alpha_composite(Image.open(tattoo_png).convert("RGBA"))
    if bra is not None:
        t2 = np.array(t); bb = np.array(b); t2[bra] = bb[bra]; t = Image.fromarray(t2)
    t.crop(box).resize(((box[2] - box[0]) * zoom, (box[3] - box[1]) * zoom), Image.NEAREST).convert("RGB").save(out_png)


# ---- sleeve: a flat blackwork design wrapped round an arm -----------------------------------------------------------------------------
# polylines (shoulder, elbow, wrist) of the arm in the body gumps 12 / 13; "R" is the one on the viewer's left, "L" on the right
SLEEVE_POLY = {("R", "12"): ARM_POLY["12"], ("R", "13"): ARM_POLY["13"],
               ("L", "12"): [(112, 84), (115, 98), (119, 110), (134, 123)], ("L", "13"): [(112, 84), (117, 100), (122, 108), (136, 122)]}
INK_RGB = (22, 24, 30)                                       # faded black ink


def sleeve_prepare(img, crop=None, ink_lum=(150, 90)):
    """a flat design (black ink on white, e.g. a flash sheet) -> dict(alpha (H, W) float 0..1, x0, x1, top[x], bot[x]); thin outline strokes and text
    are not ink: the silhouette (per-column top / bottom) is the closed, filled and opened (9 px) mask"""
    ndi, _ = _scipy()
    g = img.convert("L")
    if crop:
        g = g.crop(tuple(crop))
    lum = np.array(g).astype(float)
    hi, lo = ink_lum
    ink = np.clip((hi - lum) / (hi - lo), 0, 1)                                  # soft ink: 0 at `hi` and above, 1 at `lo` and below
    disk = lambda r: np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r + 0.3
    filled = ndi.binary_fill_holes(ndi.binary_closing(lum < 110, structure=disk(5)))      # the solid silhouette of the sleeve (the white linework is inside)
    blob = ndi.binary_opening(filled, structure=disk(9))                                  # thin outline strokes and the text are not the sleeve
    lab, n = ndi.label(blob)
    if n == 0:
        raise SystemExit("[BŁĄD  ] w obrazie nie ma czarnego wzoru")
    sz = ndi.sum(blob, lab, range(1, n + 1))
    main = lab == int(np.argmax(sz)) + 1
    alpha = ink * ndi.binary_dilation(main, structure=disk(3), iterations=1)
    cols = np.nonzero(main.any(0))[0]
    x0, x1 = int(cols.min()), int(cols.max())
    top = np.full(main.shape[1], np.nan); bot = np.full(main.shape[1], np.nan)
    for x in cols:
        ys = np.nonzero(main[:, x])[0]
        top[x], bot[x] = ys.min(), ys.max()
    xs = np.arange(main.shape[1]); ok = ~np.isnan(top)
    top = np.interp(xs, xs[ok], top[ok]); bot = np.interp(xs, xs[ok], bot[ok])
    w = 31
    top = np.convolve(np.pad(top, w // 2, mode="edge"), np.ones(w) / w, mode="valid")
    bot = np.convolve(np.pad(bot, w // 2, mode="edge"), np.ones(w) / w, mode="valid")
    return {"alpha": alpha, "x0": x0, "x1": x1, "top": top, "bot": bot}


def sleeve_xy(sl, t, phi):
    """design pixel (x, y) of a point of the arm: t 0 = shoulder .. 1 = wrist (the shoulder is the right end of the design), phi = angle round the
    arm from the front, positive outwards; the design's height is the circumference (the top and bottom edges meet at the back of the arm)"""
    x = sl["x1"] - np.clip(t, 0, 1) * (sl["x1"] - sl["x0"])
    xi = np.clip(np.round(x).astype(int), 0, len(sl["top"]) - 1)
    v = 0.5 + phi / (2 * np.pi)
    return x, sl["top"][xi] + v * (sl["bot"][xi] - sl["top"][xi])


def sleeve_decal(sl, body, side, out_glb, offset=0.004, tex_len=200, cover=0.5):
    """the body's own `side` arm skin 4 mm out, with UVs into the (box-filtered) design texture; the seam at the back of the arm is not drawn.
    Returns dict(length, ...) for the gump."""
    ndi, _ = _scipy()
    g = body.g if hasattr(body, "g") else body
    S = joint_rest(g, f"upper_arm.{side}"); Hd = joint_rest(g, f"hand.{side}")
    d = Hd - S; d[2] = 0; d /= np.linalg.norm(d)
    e1 = np.array([0, 0, 1.0]); e2 = np.cross(d, e1)
    if e2[0] * (1 if side == "L" else -1) < 0:
        e2 = -e2                                                                    # e2 points away from the body
    L = float(np.linalg.norm(Hd - S))
    want = {i for i, n in enumerate(g.joint_names) if n in (f"upper_arm.{side}", f"upper_arm_twist.{side}", f"forearm.{side}", f"forearm_twist.{side}")}
    dom = g.jnt[np.arange(len(g.pos)), np.argmax(g.wgt, 1)]
    tr = g.tri[np.isin(dom, list(want))[g.tri].all(1)]
    used = np.unique(tr); rm = -np.ones(len(g.pos), int); rm[used] = np.arange(len(used))
    P = g.pos[used] + g.nrm[used] * offset; N = g.nrm[used]
    rel = P - S
    t = rel @ d / L
    perp = rel - np.outer(rel @ d, d)
    phi = np.arctan2(perp @ e2, perp @ e1)
    tri = rm[tr]
    tri = tri[((t[tri] >= -0.02) & (t[tri] <= 1.02)).all(1) & ((phi[tri].max(1) - phi[tri].min(1)) < np.pi)]
    u2 = np.unique(tri); r2 = -np.ones(len(used), int); r2[u2] = np.arange(len(u2))
    # the texture: the design box-filtered to ~tex_len texels along the arm (a sprite pixel is ~3 cm: sub-millimetre linework only makes noise)
    f = max(1, int(round((sl["x1"] - sl["x0"]) / tex_len)))
    a = ndi.uniform_filter(sl["alpha"], size=f)[::f, ::f]
    tex = np.zeros(a.shape + (4,), np.uint8); tex[..., :3] = INK_RGB; tex[..., 3] = (np.clip(0.5 + (a - cover) * 4.0, 0, 1) * 255).astype(np.uint8)   # the renderer cuts at 0.5: ink where the share of ink >= cover
    buf = io.BytesIO(); Image.fromarray(tex, "RGBA").save(buf, "PNG")
    x, y = sleeve_xy(sl, t[u2], phi[u2])
    uv = np.clip(np.stack([(x / f) / a.shape[1], (y / f) / a.shape[0]], 1), 0, 1)
    _write_relief(out_glb, P[u2], N[u2], uv, r2[tri], P[u2], N[u2], buf.getvalue(), {"uo3d_rest": True, "name": f"tatuaz_rekaw_{side}"}, False)
    return {"length": L, "side": side, "vertices": int(len(u2)), "triangles": int(len(tri)), "texture": list(tex.shape[:2])}


def sleeve_gump(sl, side, gid, body_gump, out_png, half=ARM_HALF, ss=5, cover=0.4):
    """draw the sleeve on the arm of the body gump (gid '12' / '13'); a gump pixel is black when the share of ink under its ss x ss sub-pixels >= cover"""
    body = np.array(Image.open(body_gump).convert("RGBA")).astype(float)
    H, W = body.shape[:2]
    poly = np.array(SLEEVE_POLY[(side, gid)], float)
    sgn = 1.0 if side == "R" else -1.0                                               # the polyline's left normal is outwards for the right arm
    yy, xx = np.mgrid[0:H, 0:W]
    near = _seg_project(np.c_[xx.ravel() + 0.5, yy.ravel() + 0.5], poly)[2].reshape(H, W) <= half + 2.0
    near &= body[..., 3] > 0
    ys, xs = np.nonzero(near)
    sub = (np.arange(ss) + 0.5) / ss
    ox, oy = np.meshgrid(sub, sub)
    PX = (xs[:, None] + ox.ravel()[None]).ravel(); PY = (ys[:, None] + oy.ravel()[None]).ravel()
    a, s, dm = _seg_project(np.c_[PX, PY], poly)
    inside = (np.abs(s) <= half) & (a >= 0) & (a <= 1)
    x, y = sleeve_xy(sl, a, np.arcsin(np.clip(sgn * s / half, -0.97, 0.97)))
    xi = np.clip(x.round().astype(int), 0, sl["alpha"].shape[1] - 1); yi = np.clip(y.round().astype(int), 0, sl["alpha"].shape[0] - 1)
    ink = np.where(inside, sl["alpha"][yi, xi], 0.0).reshape(-1, ss * ss)
    cnt = inside.reshape(-1, ss * ss).sum(1)
    ok = (cnt >= ss * ss * 0.3) & (ink.sum(1) / np.maximum(cnt, 1) >= cover)
    lum = body[..., :3].mean(2)
    f = np.clip(lum[ys, xs] / np.median(lum[ys, xs]), 0.6, 1.2)[:, None]
    out = np.zeros((H, W, 4)); out[ys[ok], xs[ok], :3] = np.clip(np.array(INK_RGB)[None] * f[ok], 0, 255); out[ys[ok], xs[ok], 3] = 255
    Image.fromarray(out.astype(np.uint8)).save(out_png)
    return int(ok.sum())


# ---- patch: a coloured design laid on the front of a limb ------------------------------------------------------------------------------
# polyline (hip, knee, shin, ankle) and the half-width (px) of each point of the LEFT leg on the body gumps; the leg on the viewer's right
LEG_POLY = {("L", "12"): ([(104, 132), (102, 172), (99, 196), (97, 208)], [7.0, 5.5, 5.0, 4.5]),
            ("L", "13"): ([(104, 132), (102, 172), (100, 196), (99, 208)], [7.5, 5.5, 5.0, 4.5]),
            ("R", "12"): ([(83, 132), (76, 172), (68, 196), (65, 208)], [7.5, 7.0, 5.0, 4.2]),
            ("R", "13"): ([(83, 132), (74, 172), (68, 196), (65, 208)], [7.5, 6.5, 4.8, 4.2])}


def patch_prepare(img, crop=None, white=235, soft=70):
    """a coloured design on white -> dict(rgb (H, W, 3) uint8, alpha (H, W) float, x0, x1, y0, y1 = the box of the ink); white (also inside the design)
    is the skin: only the ink is drawn"""
    ndi, _ = _scipy()
    im = img.convert("RGB")
    if crop:
        im = im.crop(tuple(crop))
    rgb = np.array(im)
    mn = rgb.min(2).astype(float)
    alpha = np.clip((white - mn) / soft, 0, 1)
    alpha = np.where(ndi.binary_opening(alpha > 0.3, structure=np.ones((2, 2))), alpha, 0)      # the speckles of the JPEG are not ink
    ys, xs = np.nonzero(alpha > 0.3)
    if not len(xs):
        raise SystemExit("[BŁĄD  ] w obrazie nie ma wzoru (samo białe tło)")
    return {"rgb": rgb, "alpha": alpha, "x0": int(xs.min()), "x1": int(xs.max()), "y0": int(ys.min()), "y1": int(ys.max())}


def patch_xy(pt, t, phi, t_range=(0.05, 1.0), span_deg=260.0):
    """design pixel of a point of the limb: the design's width is the arc `span_deg` round the front, its top is t_range[0], its bottom t_range[1]"""
    u = 0.5 + phi / np.radians(span_deg)
    v = (t - t_range[0]) / (t_range[1] - t_range[0])
    return pt["x0"] + u * (pt["x1"] - pt["x0"]), pt["y0"] + v * (pt["y1"] - pt["y0"])


def patch_decal(pt, body, side, out_glb, t_range=(0.05, 1.0), span_deg=260.0, offset=0.004, tex_len=256, cover=0.5):
    """the body's own `side` leg skin (thigh and shin) 4 mm out, UVs into the box-filtered design (padded with transparent margins); returns the
    numbers the log wants"""
    ndi, _ = _scipy()
    g = body.g if hasattr(body, "g") else body
    S = joint_rest(g, f"thigh.{side}"); E = joint_rest(g, f"foot.{side}")
    d = E - S; L = float(np.linalg.norm(d)); d /= L
    e1 = np.array([0, 0, 1.0]) - d[2] * d; e1 /= np.linalg.norm(e1)
    e2 = np.cross(d, e1)
    if e2[0] * (1 if side == "L" else -1) < 0:
        e2 = -e2                                                                    # away from the body
    want = {i for i, n in enumerate(g.joint_names) if n.endswith("." + side) and n.split(".")[0].split("_")[0] in ("thigh", "shin")}
    dom = g.jnt[np.arange(len(g.pos)), np.argmax(g.wgt, 1)]
    tr = g.tri[np.isin(dom, list(want))[g.tri].all(1)]
    used = np.unique(tr); rm = -np.ones(len(g.pos), int); rm[used] = np.arange(len(used))
    P = g.pos[used] + g.nrm[used] * offset; N = g.nrm[used]
    rel = P - S
    t = rel @ d / L
    perp = rel - np.outer(rel @ d, d)
    phi = np.arctan2(perp @ e2, perp @ e1)
    tri = rm[tr]
    tri = tri[((t[tri] >= t_range[0] - 0.05) & (t[tri] <= t_range[1] + 0.02)).all(1) & ((phi[tri].max(1) - phi[tri].min(1)) < np.pi)]
    u2 = np.unique(tri); r2 = -np.ones(len(used), int); r2[u2] = np.arange(len(u2))
    x, y = patch_xy(pt, t[u2], phi[u2], t_range, span_deg)
    f = max(1, int(round((pt["y1"] - pt["y0"]) / tex_len)))
    pad = 3 * f
    xa, xb = int(min(x.min(), pt["x0"])) - pad, int(max(x.max(), pt["x1"])) + pad                # the texture covers every vertex: no wrapping, transparent margins
    ya, yb = int(min(y.min(), pt["y0"])) - pad, int(max(y.max(), pt["y1"])) + pad
    H, W = pt["alpha"].shape
    canvas_a = np.zeros((yb - ya, xb - xa)); canvas_c = np.zeros((yb - ya, xb - xa, 3))
    sy0, sy1, sx0, sx1 = max(ya, 0), min(yb, H), max(xa, 0), min(xb, W)
    canvas_a[sy0 - ya:sy1 - ya, sx0 - xa:sx1 - xa] = pt["alpha"][sy0:sy1, sx0:sx1]
    canvas_c[sy0 - ya:sy1 - ya, sx0 - xa:sx1 - xa] = pt["rgb"][sy0:sy1, sx0:sx1]
    pa = canvas_a[..., None]
    pm = np.concatenate([canvas_c * pa, pa], 2)
    cut = (pm.shape[0] // f * f, pm.shape[1] // f * f)
    small = pm[:cut[0], :cut[1]].reshape(cut[0] // f, f, cut[1] // f, f, 4).mean((1, 3))
    a = small[..., 3:4]
    col = np.where(a > 1e-4, small[..., :3] / np.maximum(a, 1e-4), 0)
    tex = np.zeros(a.shape[:2] + (4,), np.uint8); tex[..., :3] = np.clip(col, 0, 255)
    tex[..., 3] = (np.clip(0.5 + (a[..., 0] - cover) * 4.0, 0, 1) * 255).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(tex, "RGBA").save(buf, "PNG")
    uv = np.stack([(x - xa) / (cut[1]), (y - ya) / (cut[0])], 1)
    uv = np.clip(uv, 0, 1)
    _write_relief(out_glb, P[u2], N[u2], uv, r2[tri], P[u2], N[u2], buf.getvalue(), {"uo3d_rest": True, "name": f"tatuaz_noga_{side}"}, False)
    return {"length": L, "side": side, "vertices": int(len(u2)), "triangles": int(len(tri)), "texture": list(tex.shape[:2])}


def patch_gump(pt, side, gid, body_gump, out_png, t_range=(0.05, 1.0), span_deg=260.0, spec=None, ss=5, cover=0.45):
    """draw the design on the leg of the body gump (gid '12' / '13'); spec = (polyline, half-widths) of the leg (LEG_POLY)"""
    poly, hw = spec or LEG_POLY[(side, gid)]
    poly = np.array(poly, float); hw = np.array(hw, float)
    seg = np.diff(poly, axis=0); cum = np.r_[0, np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))]; cum /= cum[-1]
    body = np.array(Image.open(body_gump).convert("RGBA")).astype(float)
    H, W = body.shape[:2]
    sgn = -1.0 if side == "L" else 1.0                                       # the polyline (hip -> ankle, downwards): its left normal is the viewer's right
    yy, xx = np.mgrid[0:H, 0:W]
    a0, s0, dm0 = _seg_project(np.c_[xx.ravel() + 0.5, yy.ravel() + 0.5], poly)
    near = (dm0 <= np.interp(a0, cum, hw) + 2.0).reshape(H, W) & (body[..., 3] > 0)
    ys, xs = np.nonzero(near)
    sub = (np.arange(ss) + 0.5) / ss
    ox, oy = np.meshgrid(sub, sub)
    PX = (xs[:, None] + ox.ravel()[None]).ravel(); PY = (ys[:, None] + oy.ravel()[None]).ravel()
    a, s, dm = _seg_project(np.c_[PX, PY], poly)
    half = np.interp(a, cum, hw)
    inside = (np.abs(s) <= half) & (a >= 0) & (a <= 1)
    phi = np.arcsin(np.clip(sgn * s / half, -0.97, 0.97))                    # positive = outwards (away from the body)
    # the paperdoll leg is shorter than the real one: t runs hip -> ankle over the polyline
    x, y = patch_xy(pt, t_range[0] + a * (1.0 - t_range[0]), phi, t_range, span_deg)
    ok_xy = (x >= 0) & (x < pt["alpha"].shape[1]) & (y >= 0) & (y < pt["alpha"].shape[0])
    xi = np.clip(x.round().astype(int), 0, pt["alpha"].shape[1] - 1); yi = np.clip(y.round().astype(int), 0, pt["alpha"].shape[0] - 1)
    al = np.where(inside & ok_xy, pt["alpha"][yi, xi], 0.0)
    cols = pt["rgb"][yi, xi].astype(float) * al[:, None]
    alr = al.reshape(-1, ss * ss); colr = cols.reshape(-1, ss * ss, 3)
    cnt = inside.reshape(-1, ss * ss).sum(1)
    share = alr.sum(1) / np.maximum(cnt, 1)
    ok = (cnt >= ss * ss * 0.3) & (share >= cover)
    ndi, _ = _scipy()                                                         # the tattoo goes UNDER the underwear of the body gump (slightly yellow cloth)
    cloth = ndi.binary_fill_holes(ndi.binary_closing(((body[..., 0] - body[..., 2]) >= 6) & (body[..., 3] > 0), structure=np.ones((3, 3)), iterations=2))
    ok &= ~cloth[ys, xs]
    ink_rgb = colr.sum(1) / np.maximum(alr.sum(1)[:, None], 1e-6)
    lum = body[..., :3].mean(2)
    f = np.clip(lum[ys, xs] / np.median(lum[ys, xs]), 0.6, 1.2)[:, None]
    out = np.zeros((H, W, 4)); out[ys[ok], xs[ok], :3] = np.clip(ink_rgb[ok] * f[ok], 0, 255); out[ys[ok], xs[ok], 3] = 255
    Image.fromarray(out.astype(np.uint8)).save(out_png)
    return int(ok.sum())
