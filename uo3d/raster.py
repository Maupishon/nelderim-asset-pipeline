"""Orthographic z-buffer rasterizer (numpy only) with the UO camera."""
import math
import numpy as np

ELEV = math.radians(28.45)
PPM = 36.0                      # pixels per metre
ANCHOR_H = 0.07                 # world height (m) of the anchor pixel above the floor


def to_blender(P):
    """glTF (Y up, character faces +Z) -> Blender-like (Z up, character faces -Y)."""
    return np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)


def camera(P, d, canvas=(256, 256), anchor=(128, 192), sign=-1.0, yaw0=0.0):
    """P: (N,3) glTF points, d: UO direction 0..4 (or float degrees via yaw0). Returns screen xy (N,2) and depth (N,)."""
    B = to_blender(P)
    th = math.radians(sign * 45.0 * d + yaw0)
    c, s = math.cos(th), math.sin(th)
    x = B[:, 0]*c - B[:, 1]*s
    y = B[:, 0]*s + B[:, 1]*c
    z = B[:, 2] - ANCHOR_H
    v = z*math.cos(ELEV) + y*math.sin(ELEV)
    depth = y*math.cos(ELEV) - z*math.sin(ELEV)          # smaller = nearer to the camera
    return np.stack([anchor[0] + PPM*x, anchor[1] - PPM*v], 1), depth


def rotate_normals(N, d, sign=-1.0, yaw0=0.0):
    B = to_blender(N)
    th = math.radians(sign * 45.0 * d + yaw0)
    c, s = math.cos(th), math.sin(th)
    x = B[:, 0]*c - B[:, 1]*s
    y = B[:, 0]*s + B[:, 1]*c
    return np.stack([x, y, B[:, 2]], 1)


def _samples(xy, z, tri, W, H, tids):
    a, b, c = xy[tri[tids, 0]], xy[tri[tids, 1]], xy[tri[tids, 2]]
    za, zb, zc = z[tri[tids, 0]], z[tri[tids, 1]], z[tri[tids, 2]]
    lo = np.minimum(np.minimum(a, b), c); hi = np.maximum(np.maximum(a, b), c)
    x0 = np.maximum(np.ceil(lo[:, 0]-0.5), 0).astype(int); x1 = np.minimum(np.floor(hi[:, 0]-0.5), W-1).astype(int)
    y0 = np.maximum(np.ceil(lo[:, 1]-0.5), 0).astype(int); y1 = np.minimum(np.floor(hi[:, 1]-0.5), H-1).astype(int)
    ok = (x1 >= x0) & (y1 >= y0)
    return a, b, c, za, zb, zc, x0, x1, y0, y1, ok


def raster(xy, z, tri, W, H):
    """-> (tri_id[H,W] (-1 = empty), depth[H,W])"""
    area = (xy[tri[:, 1], 0]-xy[tri[:, 0], 0])*(xy[tri[:, 2], 1]-xy[tri[:, 0], 1]) - \
           (xy[tri[:, 2], 0]-xy[tri[:, 0], 0])*(xy[tri[:, 1], 1]-xy[tri[:, 0], 1])
    valid = np.flatnonzero(np.abs(area) > 1e-9)
    lo = np.minimum(np.minimum(xy[tri[valid, 0]], xy[tri[valid, 1]]), xy[tri[valid, 2]])
    hi = np.maximum(np.maximum(xy[tri[valid, 0]], xy[tri[valid, 1]]), xy[tri[valid, 2]])
    size = np.maximum(np.ceil(hi[:, 0]-lo[:, 0]).astype(int), np.ceil(hi[:, 1]-lo[:, 1]).astype(int)) + 1
    idxs, deps, tids_all = [], [], []
    lim = [2, 4, 8, 16, 32, 64, 10**9]
    prev = 0
    for L in lim:
        sel = valid[(size > prev) & (size <= L)]
        prev = L
        if not len(sel):
            continue
        S = min(L, 400)
        if L == 10**9:
            S = int(size[size > 64].max()) + 1 if np.any(size > 64) else 65
        for chunk in np.array_split(sel, max(1, len(sel)*S*S // 3_000_000 + 1)):
            a, b, c, za, zb, zc, x0, x1, y0, y1, ok = _samples(xy, z, tri, W, H, chunk)
            ch = chunk[ok]
            if not len(ch):
                continue
            a, b, c, za, zb, zc, x0, y0 = a[ok], b[ok], c[ok], za[ok], zb[ok], zc[ok], x0[ok], y0[ok]
            x1, y1 = x1[ok], y1[ok]
            o = np.arange(S)
            px = x0[:, None, None] + o[None, None, :]
            py = y0[:, None, None] + o[None, :, None]
            px = np.broadcast_to(px, (len(ch), S, S)); py = np.broadcast_to(py, (len(ch), S, S))
            inb = (px <= x1[:, None, None]) & (py <= y1[:, None, None])
            fx = px + 0.5; fy = py + 0.5
            ar = ((b[:, 0]-a[:, 0])*(c[:, 1]-a[:, 1]) - (c[:, 0]-a[:, 0])*(b[:, 1]-a[:, 1]))[:, None, None]
            w0 = ((b[:, 0, None, None]-fx)*(c[:, 1, None, None]-fy) - (c[:, 0, None, None]-fx)*(b[:, 1, None, None]-fy))/ar
            w1 = ((c[:, 0, None, None]-fx)*(a[:, 1, None, None]-fy) - (a[:, 0, None, None]-fx)*(c[:, 1, None, None]-fy))/ar
            w2 = 1.0 - w0 - w1
            e = -1e-6
            m = inb & (w0 >= e) & (w1 >= e) & (w2 >= e)
            dz = w0*za[:, None, None] + w1*zb[:, None, None] + w2*zc[:, None, None]
            tt = np.broadcast_to(ch[:, None, None], m.shape)
            idxs.append((py*W + px)[m]); deps.append(dz[m]); tids_all.append(tt[m])
    tri_id = np.full(W*H, -1, int); depth = np.full(W*H, np.inf)
    if idxs:
        idx = np.concatenate(idxs); dep = np.concatenate(deps); tid = np.concatenate(tids_all)
        order = np.argsort(-dep, kind="stable")             # far first, near last (last write wins)
        tri_id[idx[order]] = tid[order]; depth[idx[order]] = dep[order]
    return tri_id.reshape(H, W), depth.reshape(H, W)
