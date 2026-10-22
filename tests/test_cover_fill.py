import os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import cover_fill as F


def _frames():
    orig = np.zeros((F.CELL, F.CELL, 4), np.uint8)
    orig[60:200, 80:180] = (200, 200, 200, 255)
    orig[100:110, 120:130, 3] = 0                                   # an opening the ORIGINAL leaves (hand)
    new = np.zeros_like(orig)
    new[60:200, 80:180] = (90, 70, 50, 255)
    new[140:150, 90:100, 3] = 0                                     # a hole the new robe has but the original does not
    new[100:110, 120:130, 3] = 0
    new[60:70, 170:180, 3] = 0                                      # corner cut out
    return orig, new


def test_fills_what_the_original_covered_and_keeps_its_openings():
    orig, new = _frames()
    out, n = F.fill_frame(orig, new, 10)
    assert n == 100 + 100 and (out[140:150, 90:100, 3] == 255).all() and (out[60:70, 170:180, 3] == 255).all()
    assert (out[100:110, 120:130, 3] == 0).all()                    # opening of the original stays open
    assert (out[145, 95, :3] == (90, 70, 50)).all()                 # colour of the new robe
    assert (out[:60, :, 3] == 0).all()                              # nothing outside the original silhouette


def test_nothing_to_do_and_reach_limit():
    orig, new = _frames()
    assert F.fill_frame(orig, orig.copy(), 10) == (None, 0)
    o2 = np.zeros_like(orig); o2[0:5, 0:5] = 255
    n2 = np.zeros_like(orig); n2[200:210, 200:210] = 255
    assert F.fill_frame(o2, n2, 4)[1] == 0                          # too far from any new pixel


def test_run_on_lab_refuses_second_pass(tmp_path):
    orig, new = _frames()
    atl = tmp_path / "atlases"; atl.mkdir()
    im = np.zeros((1024, F.CELL, 4), np.uint8)
    im[F.ROW_ORIG:F.ROW_ORIG + F.CELL] = orig; im[F.ROW_NEW:F.ROW_NEW + F.CELL] = new
    Image.fromarray(im).save(atl / "a00_d3.png")
    assert F.run(str(tmp_path)) == (1, 200)
    try:
        F.run(str(tmp_path)); assert False
    except SystemExit:
        pass
