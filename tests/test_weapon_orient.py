"""uo3d weapon orientation helpers: align_long_axis (hilt down, tip +Y), fatten, flip (icon)."""
import numpy as np

from uo3d import engine, statmesh


class Mesh:
    """a slender blade along an arbitrary axis, with a wide guard near one end and a thin grip beyond it."""

    def __init__(self, axis, tip_sign=1.0):
        rng = np.random.default_rng(1)
        t = np.linspace(-1.0, 1.0, 400)
        w = np.where(np.abs(t + 0.7) < 0.05, 0.25, 0.04)               # guard (wide) at t = -0.7
        q = rng.normal(size=(400, 2)) * w[:, None]
        u = np.cross(axis, [0.3, 0.2, 0.9]); u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        self.pos = np.outer(t * tip_sign, axis) + q[:, :1] * u + q[:, 1:] * v
        self.nrm = np.tile(axis, (400, 1)).astype(float)
        self.tri = np.zeros((0, 3), int)


def test_align_puts_tip_up_and_hilt_down():
    axis = np.array([0.2, 0.1, 0.97]); axis /= np.linalg.norm(axis)
    m = Mesh(axis)                                                     # guard at t=-0.7 -> hilt end is t=-1
    hilt_pts = m.pos[:20].copy()
    engine.align_long_axis(m)
    assert np.ptp(m.pos[:, 1]) > 1.9 and np.ptp(m.pos[:, 0]) < 1.6 and np.ptp(m.pos[:, 2]) < 1.6
    assert m.pos[:20, 1].mean() < m.pos[-20:, 1].mean()                # the hilt end (first points) is the bottom


def test_align_is_independent_of_the_sign_of_the_axis():
    a = np.array([0.0, 0.0, 1.0])
    m1, m2 = Mesh(a), Mesh(-a)
    engine.align_long_axis(m1); engine.align_long_axis(m2)
    assert m1.pos[:20, 1].mean() < 0 and m2.pos[:20, 1].mean() < 0


def test_fatten_scales_only_the_cross_section():
    m = Mesh(np.array([0.0, 1.0, 0.0]))
    y0 = np.ptp(m.pos[:, 1]); x0 = np.ptp(m.pos[:, 0])
    engine.fatten(m, 3.0)
    assert abs(np.ptp(m.pos[:, 1]) - y0) < 1e-9 and np.ptp(m.pos[:, 0]) > 2.5 * x0


def _img(mask, rgb=(200, 100, 50)):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[mask, :3] = rgb
    img[mask, 3] = 255
    return img


def test_smooth_alpha_removes_spikes_and_fills_notches():
    m = np.zeros((20, 20), bool)
    m[5:15, 5:15] = True
    m[4, 9] = True                                   # 1 px spike on the top edge
    m[8, 5] = False                                  # 1 px notch in the left edge
    out = engine.smooth_alpha(_img(m), 1)
    a = out[..., 3] > 0
    assert not a[4, 9]                               # spike gone
    assert a[8, 5] and out[8, 5, :3].tolist() == [200, 100, 50]   # notch filled with the neighbours' colour
    assert a[10, 10] and a.sum() >= 95


def test_lift_dark_leaves_no_near_black_pixels_and_keeps_transparency():
    m = np.zeros((6, 6), bool); m[2:4, 2:4] = True
    out = engine.lift_dark(_img(m, (3, 5, 9)), 24)
    assert out[m][:, :3].min() >= 24 and (out[~m][:, 3] == 0).all()
    assert engine.lift_dark(_img(m, (3, 5, 9)), 0)[m][:, :3].max() == 9
