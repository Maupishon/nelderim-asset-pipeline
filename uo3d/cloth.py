"""A small position-based cloth simulation for robe / skirt / cloak (numpy only), in the spirit of UO_Model3D's uo_cloth_bake.py.

The lower part of the item (where the weights follow the cloth chains of the model) becomes cloth: it falls, swings and collides with the body.
It is pulled towards the shape of the chains fitted to the original UO frames (GOAL), so it never drifts far. Every action is simulated on its
own: the cloth first settles (PREROLL steps in the first pose); loops (walk, run) run LOOP_CYCLES times and the last cycle is kept.
One simulation step = one scene frame (1/24 s); a UO frame is 3 steps.
"""
import numpy as np

from . import engine

GOAL = 0.35            # how strongly every step pulls the cloth towards the chains (0 = free cloth, 1 = chains only)
GRAVITY = 9.8
DAMPING = 0.92
ITER = 5               # edge-length constraint rounds per step
GAP = 0.006            # m kept between cloth and skin
PREROLL = 8
LOOP_CYCLES = 2
LOOPS = {0, 1, 2, 3, 4, 7, 8, 15, 23, 24, 25}
PIN_BELOW = 0.05       # vertices with cloth share below this stay on the chains


def make_sim(body, item):
    g = body.g
    t = item.cloth_t
    free = t > PIN_BELOW
    if not free.any():
        return None
    tri = item.tri
    e = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    e = np.unique(np.sort(e, axis=1), axis=0)
    rest = np.linalg.norm(item.pos[e[:, 0]] - item.pos[e[:, 1]], axis=1)
    inv = free.astype(float)                                    # 0 = pinned
    deg = np.maximum(np.bincount(e.ravel(), minlength=len(item.pos)), 1).astype(float)
    wsum = inv[e[:, 0]] + inv[e[:, 1]]
    ok = wsum > 0
    e, rest, wsum = e[ok], rest[ok], wsum[ok]
    sub = np.arange(0, len(g.pos), 3)                           # a third of the body vertices is enough for collisions
    sim_idx = np.flatnonzero(free)

    def goal_at(action, tt):
        W = g.pose(body.action_names[action], tt)
        SM = g.skin_matrices(W)
        P, _ = item.skin(SM)
        return P, SM

    def body_at(SM):
        P, N = body.skin_body(SM)
        return P[sub], N[sub]

    def collide(x, SMb):
        bp, bn = SMb
        r2 = (bp ** 2).sum(1)
        xs = x[sim_idx]
        d = (xs ** 2).sum(1)[:, None] + r2[None, :] - 2 * xs @ bp.T
        i = np.argmin(d, axis=1)
        nd = np.sqrt(np.maximum(d[np.arange(len(xs)), i], 0))
        s = ((xs - bp[i]) * bn[i]).sum(1)
        hit = (nd < 0.12) & (s < GAP)
        if hit.any():
            xs[hit] = xs[hit] + bn[i][hit] * (GAP - s[hit])[:, None]
            x[sim_idx] = xs
        return x

    def step(x, xp, action, tt):
        G, SM = goal_at(action, tt)
        v = (x - xp) * DAMPING
        xn = x + v
        xn[:, 1] -= GRAVITY / (24.0 ** 2)
        xn += (G - xn) * GOAL * free[:, None]
        xn[~free] = G[~free]
        for _ in range(ITER):                                   # edge lengths (Jacobi, relaxed)
            d = xn[e[:, 1]] - xn[e[:, 0]]
            L = np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            c = d * ((L[:, 0] - rest) / L[:, 0] / wsum)[:, None]
            acc = np.zeros_like(xn)
            np.add.at(acc, e[:, 0], c * inv[e[:, 0]][:, None])
            np.add.at(acc, e[:, 1], -c * inv[e[:, 1]][:, None])
            xn += acc / deg[:, None] * 1.5
        xn = collide(xn, body_at(SM))
        return xn, G

    def sim(action):
        n = engine.ACTION_FRAMES[action]
        times = [(1 + f) / 24.0 for f in range(3 * n)]
        G0, _ = goal_at(action, times[0])
        x = G0.copy(); xp = G0.copy()
        for _ in range(PREROLL):                                # settle in the first pose
            x, _g = step(x, xp, action, times[0]); xp = x
            xp = x.copy()
        cycles = LOOP_CYCLES if action in LOOPS else 1
        keep = {}
        for c in range(cycles):
            for f, tt in enumerate(times):
                xn, _g = step(x, xp, action, tt)
                xp, x = x, xn
                if c == cycles - 1 and f % 3 == 0:
                    keep[(action, f // 3)] = x.copy()
        item.cloth.update(keep)
        if not np.isfinite(x).all() or np.abs(x).max() > 10:
            raise RuntimeError("symulacja tkaniny rozbiegła się (akcja %d)" % action)

    item.cloth = {}
    return sim
