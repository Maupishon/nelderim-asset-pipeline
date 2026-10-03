"""Item .vd (2D sprites of the original UO item) -> 3D model (.glb) to try on in the Fit Lab.

How (no Blender, numpy + Pillow only):
1. The UO body (UO_Model3D .glb) is posed like the sprites (action 4 "stand", frame 0 by default).
2. Visual hull: a voxel grid around the body is carved with the item's silhouettes seen by the UO camera from
   the 5 stored directions plus the 3 mirrored ones the client draws (directions 5..7 = mirror of 3..1).
   A voxel survives a view when it falls on the item's pixels OR the body hides it there (sprites only show the
   visible part of the item). Voxels inside the body are dropped; a voxel needs at least one view that really sees it.
3. Surface of the voxels -> smoothed triangle mesh; colours sampled from the sprites (light divided out, so the
   renderer's UO light gives the original look back).
4. The mesh is moved from the stand pose back to the rest pose of the body (inverse skinning of the nearest body
   vertex) and saved as .glb with asset.extras.uo3d_rest = true: the Fit Lab then takes it as-is (no auto-scaling).

Limits: shape is a silhouette hull (no hidden folds / holes), registration of the 3D body against the original
sprites is IoU 0.879, colours only where some sprite sees the surface.
"""
import json, math, struct
import numpy as np

from . import raster as R
from . import vdread
from .engine import Body, ANCHOR, CANVAS, nearest, say, _vertex_normals

MIRROR = {5: 3, 6: 2, 7: 1}


def _dilate(m, n):
    out = m.copy()
    for _ in range(n):
        o = out.copy()
        o[1:] |= out[:-1]; o[:-1] |= out[1:]; o[:, 1:] |= out[:, :-1]; o[:, :-1] |= out[:, 1:]
        out = o
    return out


def _flip(img):
    """mirror around the anchor pixel column 128 (client draws directions 5..7 mirrored)."""
    out = np.zeros_like(img)
    out[:, 1:] = img[:, :0:-1]
    return out


def sprite_views(vd_path, action=4, frame=0, mirror=True):
    """{direction: RGBA canvas 256x256} for directions 0..4 (+5..7 mirrored)."""
    at, _, anims = vdread.read_vd(vd_path)
    if at != 2:
        raise ValueError("To nie jest animacja ludzi/ekwipunku (typ 2). Zamiana na 3D działa tylko dla przedmiotów noszonych przez postać.")
    views = {}
    for d in range(5):
        fr = anims.get((action, d))
        if not fr:
            raise ValueError(f"W pliku brak akcji {action} w kierunku {d}.")
        views[d] = vdread.canvas(fr[min(frame, len(fr) - 1)])
    if mirror:
        for d, src in MIRROR.items():
            views[d] = _flip(views[src])
    if not any((v[..., 3] > 0).any() for v in views.values()):
        raise ValueError("Klatki są puste (przezroczyste).")
    return views


def _proj(P, d):
    xy, z = R.camera(P, d, CANVAS, ANCHOR)
    px = np.floor(xy[:, 0]).astype(int); py = np.floor(xy[:, 1]).astype(int)
    ok = (px >= 0) & (px < CANVAS[0]) & (py >= 0) & (py < CANVAS[1])
    return np.clip(px, 0, CANVAS[0] - 1), np.clip(py, 0, CANVAS[1] - 1), z, ok


def carve(body, views, Pb, voxel=0.02, dilate=0, pad=0.35):
    """-> (occupancy grid bool (nx,ny,nz), origin (3,), voxel)"""
    lo = Pb.min(0) - pad; hi = Pb.max(0) + pad
    lo[1] = max(lo[1], Pb[:, 1].min() - 0.05)                      # nothing below the floor
    n = np.ceil((hi - lo) / voxel).astype(int)
    ix, iy, iz = np.meshgrid(np.arange(n[0]), np.arange(n[1]), np.arange(n[2]), indexing="ij")
    V = lo + (np.stack([ix.ravel(), iy.ravel(), iz.ravel()], 1) + 0.5) * voxel
    keep = np.ones(len(V), bool); inside = np.ones(len(V), bool); seen = np.zeros(len(V), bool)
    W, H = CANVAS
    for d, img in views.items():
        mask = img[..., 3] > 0
        mdil = _dilate(mask, dilate)
        xyb, zb = R.camera(Pb, d, CANVAS, ANCHOR)
        _, near = R.raster(xyb, zb, body.g.tri, W, H)
        _, farn = R.raster(xyb, -zb, body.g.tri, W, H)
        far = -farn
        px, py, z, ok = _proj(V, d)
        bn = near[py, px]; bf = far[py, px]
        occl = ok & (bn < z - 0.01)
        on = ok & mdil[py, px]
        keep &= on | occl
        inside &= ok & np.isfinite(bn) & (z >= bn - 0.005) & (z <= bf + 0.005)
        seen |= ok & mask[py, px] & ~occl
        say(f"kierunek {d}: zostaje {int(keep.sum())} wokseli")
    occ = (keep & ~inside & seen).reshape(n)
    return occ, lo, voxel


def _largest_parts(occ, min_frac=0.02):
    """drop small floating islands (6-connected labelling with numpy flood steps)."""
    lab = np.zeros(occ.shape, np.int32)
    idx = np.flatnonzero(occ.ravel())
    if not len(idx):
        return occ
    lab.ravel()[idx] = np.arange(1, len(idx) + 1)
    while True:                                                    # min-label propagation until stable
        prev = lab.copy()
        for ax in range(3):
            for sh in (1, -1):
                r = np.roll(lab, sh, axis=ax)
                edge = [slice(None)] * 3
                edge[ax] = slice(0, 1) if sh == 1 else slice(-1, None)
                r[tuple(edge)] = 0
                m = occ & (r > 0) & (r < lab)
                lab[m] = r[m]
        if np.array_equal(prev, lab):
            break
    ids, cnt = np.unique(lab[occ], return_counts=True)
    big = ids[cnt >= max(cnt.max() * min_frac, 20)]
    return occ & np.isin(lab, big)


def surface(occ, origin, voxel):
    """boundary faces of the voxels -> welded triangle mesh (P, tri), outward winding."""
    G = np.pad(occ, 1)
    nx, ny, nz = G.shape
    quads = []
    corners = {  # axis: (corner offsets of the face at +side, in CCW order seen from outside +axis)
        0: [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
        1: [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
        2: [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    }
    for ax in range(3):
        a = np.take(G, range(G.shape[ax] - 1), axis=ax); b = np.take(G, range(1, G.shape[ax]), axis=ax)
        for flip, sel in ((False, a & ~b), (True, b & ~a)):        # +side face of a voxel / -side face of the next
            cells = np.argwhere(sel)
            if not len(cells):
                continue
            if flip:
                cells = cells.copy(); cells[:, ax] += 1
            cs = np.array(corners[ax])
            if flip:                                               # face at the voxel's -side: shift and reverse
                cs = cs.copy(); cs[:, ax] = 0; cs = cs[::-1]
            quads.append(cells[:, None, :] + cs[None, :, :])
    Q = np.concatenate(quads)                                      # (nq, 4, 3) grid corners (padded coords)
    key = (Q[..., 0] * (ny + 1) + Q[..., 1]) * (nz + 1) + Q[..., 2]
    uk, inv = np.unique(key.ravel(), return_inverse=True)
    inv = inv.reshape(-1, 4)
    gx = uk // ((ny + 1) * (nz + 1)); gy = (uk // (nz + 1)) % (ny + 1); gz = uk % (nz + 1)
    P = origin + (np.stack([gx, gy, gz], 1) - 1) * voxel           # -1: undo the padding
    tri = np.concatenate([inv[:, [0, 1, 2]], inv[:, [0, 2, 3]]])
    return P.astype(float), tri


def smooth(P, tri, iters=30, lam=0.5, mu=-0.53):
    """Taubin smoothing (no shrinking) of the blocky voxel surface."""
    e = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    deg = np.bincount(e.ravel(), minlength=len(P)).astype(float)[:, None]
    deg = np.maximum(deg, 1)
    for _ in range(iters):
        for f in (lam, mu):
            acc = np.zeros_like(P)
            np.add.at(acc, e[:, 0], P[e[:, 1]]); np.add.at(acc, e[:, 1], P[e[:, 0]])
            P = P + f * (acc / deg - P)
    return P


def colours(P, tri, N, views, Pb, body):
    """per-vertex albedo from the sprites (visible, facing views; UO light divided out)."""
    W, H = CANVAS
    L = np.array([0.0, -math.cos(R.ELEV), math.sin(R.ELEV)])
    acc = np.zeros((len(P), 3)); wsum = np.zeros(len(P))
    for d, img in views.items():
        xy, z = R.camera(P, d, CANVAS, ANCHOR)
        _, zb = R.raster(xy, z, tri, W, H)                          # the item hides its own back side
        xyb, zbb = R.camera(Pb, d, CANVAS, ANCHOR)
        _, bn = R.raster(xyb, zbb, body.g.tri, W, H)
        px, py, _, ok = _proj(P, d)
        f = R.rotate_normals(N, d) @ L
        vis = ok & (z <= zb[py, px] + 0.02) & (z <= bn[py, px] + 0.01) & (img[py, px, 3] > 0) & (f > 0.05)
        lit = 0.08 + 0.92 * np.clip(f, 0, 1)
        rgb = img[py, px, :3] / 255.0 / lit[:, None]
        w = np.where(vis, f ** 2, 0.0)
        acc += w[:, None] * np.clip(rgb, 0, 1); wsum += w
    col = np.full((len(P), 3), 0.6)
    has = wsum > 1e-6
    col[has] = acc[has] / wsum[has, None]
    if has.any() and (~has).any():
        i, _ = nearest(P[~has], P[has])
        col[~has] = col[has][i]
    say(f"kolory z klatek: {int(has.sum())} z {len(P)} wierzchołków")
    return col


def unpose(P, Pb, body, SM):
    """stand pose -> rest pose: inverse of the blended skin matrix of the nearest body vertex."""
    g = body.g
    j, _ = nearest(P, Pb)
    M = np.zeros((len(P), 4, 4))
    for k in range(g.jnt.shape[1]):
        M += g.wgt[j, k][:, None, None] * SM[g.jnt[j, k]]
    Minv = np.linalg.inv(M)
    return np.einsum("nij,nj->ni", Minv[:, :3, :], np.c_[P, np.ones(len(P))])


def write_glb(path, P, N, C, tri, extras):
    P = P.astype(np.float32); N = N.astype(np.float32); C = np.c_[C, np.ones(len(C))].astype(np.float32)
    I = tri.astype(np.uint32).ravel()
    blobs = [P.tobytes(), N.tobytes(), C.tobytes(), I.tobytes()]
    views, off = [], 0
    for bl in blobs:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(bl)})
        off += (len(bl) + 3) // 4 * 4
    js = {
        "asset": {"version": "2.0", "generator": "Nelderim Lab uo3d.fromvd", "extras": extras},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": extras.get("name", "item")}],
        "materials": [{"name": "vd", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 1},
                       "doubleSided": True}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2}, "indices": 3, "material": 0}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3", "min": P.min(0).tolist(), "max": P.max(0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(N), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(C), "type": "VEC4"},
            {"bufferView": 3, "componentType": 5125, "count": len(I), "type": "SCALAR"}],
        "bufferViews": views, "buffers": [{"byteLength": off}],
    }
    bin_ = b"".join(bl + b"\0" * ((4 - len(bl) % 4) % 4) for bl in blobs)
    jb = json.dumps(js).encode("utf-8"); jb += b" " * ((4 - len(jb) % 4) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(bin_)))
        fh.write(struct.pack("<I4s", len(jb), b"JSON")); fh.write(jb)
        fh.write(struct.pack("<I4s", len(bin_), b"BIN\0")); fh.write(bin_)


def vd_to_glb(body_glb, vd_path, out_path, action=4, frame=0, voxel=0.02, mirror=True, dilate=0, kind=""):
    body = body_glb if isinstance(body_glb, Body) else Body(body_glb)
    views = sprite_views(vd_path, action, frame, mirror)
    _, SM = body.pose_matrices(action, frame)
    Pb, _ = body.skin_body(SM)
    say("rzeźbię bryłę z sylwetek (kamera UO, %d kierunków)" % len(views))
    occ, origin, vox = carve(body, views, Pb, voxel, dilate)
    occ = _largest_parts(occ)
    if occ.sum() < 20:
        raise ValueError("Z sylwetek nie da się zbudować bryły (przedmiot za mały albo ukryty pod ciałem).")
    P, tri = surface(occ, origin, vox)
    P = smooth(P, tri)
    N = _vertex_normals(smooth(P, tri, iters=60), tri)            # extra-smooth normals: no voxel ripples in the light
    say(f"siatka: {len(P)} wierzchołków, {len(tri)} trójkątów")
    C = colours(P, tri, N, views, Pb, body)
    Pr = unpose(P, Pb, body, SM)
    Nr = _vertex_normals(smooth(Pr, tri, iters=60), tri)
    import os
    name = os.path.splitext(os.path.basename(vd_path))[0]
    write_glb(out_path, Pr, Nr, C, tri, {"uo3d_rest": True, "source_vd": os.path.basename(vd_path), "action": action,
                                          "frame": frame, "voxel": vox, "kind": kind, "name": name})
    say("zapisano " + out_path)
    return out_path
