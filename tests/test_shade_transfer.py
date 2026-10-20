import os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import shade_transfer as S


def _frames():
    yy, xx = np.mgrid[:S.CELL, :S.CELL]
    m = (abs(xx - 128) < 30) & (yy > 60) & (yy < 200)
    orig = np.zeros((S.CELL, S.CELL, 4), np.uint8)
    orig[..., :3] = 200
    orig[..., 3] = np.where(m, 255, 0)
    orig[m & (abs(xx - 128) > 20), :3] = 90                 # a dark strip along both sides (inner sleeve shadow)
    new = np.zeros_like(orig)
    new[..., :3] = (90, 70, 50)
    new[..., 3] = orig[..., 3]
    return orig, new, m


def test_shadow_moves_to_the_new_robe_and_colour_stays():
    orig, new, m = _frames()
    out = S.transfer_frame(orig, new, 1.5)
    side = m & (abs(np.mgrid[:S.CELL, :S.CELL][1] - 128) > 20)
    mid = m & ~side
    assert out[side, :3].mean() < new[side, :3].mean() * 0.95      # darker where the original is dark
    r = out[mid, :3].mean(0) / new[mid, :3].mean(0)
    assert (r[0] > 0.95).all() or r.max() > 0.95                  # lights not crushed
    assert (out[..., 3] == new[..., 3]).all()
    assert (out[~m] == new[~m]).all()                              # outside the robe untouched
    hue_new = new[mid, :3].mean(0); hue_out = out[mid, :3].mean(0)
    assert np.allclose(hue_out / hue_out.sum(), hue_new / hue_new.sum(), atol=0.03)


def test_strength_zero_is_identity_and_empty_frame_is_skipped():
    orig, new, _ = _frames()
    assert (S.transfer_frame(orig, new, 0) == new).all()
    assert S.transfer_frame(np.zeros_like(orig), new) is None


def test_run_on_lab_and_refuses_second_pass(tmp_path):
    orig, new, _ = _frames()
    atl = tmp_path / "atlases"; atl.mkdir()
    im = np.zeros((1024, S.CELL * 2, 4), np.uint8)
    for f in range(2):
        im[S.ROW_ORIG:S.ROW_ORIG + S.CELL, f * S.CELL:(f + 1) * S.CELL] = orig
        im[S.ROW_NEW:S.ROW_NEW + S.CELL, f * S.CELL:(f + 1) * S.CELL] = new
    Image.fromarray(im).save(atl / "a04_d0.png")
    done, skipped = S.run(str(tmp_path), 1.5)
    assert (done, skipped) == (2, 0)
    got = np.array(Image.open(atl / "a04_d0.png"))
    assert (got[:S.ROW_NEW] == im[:S.ROW_NEW]).all()               # body and original rows untouched
    assert not (got[S.ROW_NEW:] == im[S.ROW_NEW:]).all()
    try:
        S.run(str(tmp_path), 1.5)
        assert False
    except SystemExit:
        pass
