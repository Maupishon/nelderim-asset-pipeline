"""hood_blend: hood pixels come from the robe's own cloth; seam rows blended; second pass refused."""
import json
import numpy as np
import pytest
from PIL import Image

import hood_blend as H


def make_lab(tmp_path):
    lab, masks = tmp_path / "lab", tmp_path / "masks"
    (lab / "atlases").mkdir(parents=True); masks.mkdir()
    atlas = np.zeros((1024, 256, 4), np.uint8)
    orig = atlas[512:768]
    orig[40:200, 100:156] = (230, 230, 230, 255)            # bright shroud, hood on top
    new = atlas[768:1024]
    new[40:200, 100:156] = (60, 50, 40, 255)                # dark brown robe as built
    new[40:70, 100:156] = (250, 250, 250, 255)              # the picture's face/cowl: wrong tone on the hood rows
    lab_ids = np.zeros((256, 256), np.uint8)
    lab_ids[60:70, 120:136] = 1                             # face
    Image.fromarray(atlas).save(lab / "atlases" / "a04_d3.png")
    Image.fromarray(lab_ids).save(masks / "a04_d3_f00_region_ids.png")
    return lab, masks


def test_hood_takes_robe_tone_and_keeps_silhouette(tmp_path):
    lab, masks = make_lab(tmp_path)
    done, skipped = H.run(str(lab), str(masks))
    assert (done, skipped) == (1, 0)
    out = np.array(Image.open(lab / "atlases" / "a04_d3.png"))
    new, orig = out[768:1024], out[512:768]
    zone = (orig[..., 3] >= 128)
    hood = new[45:60, 105:150, :3].astype(int)
    assert hood.max() < 120                                  # no more bright picture pixels on the hood
    assert (new[..., 3] > 0).sum() >= zone[:200].sum() - 0   # silhouette not shrunk
    assert new[150, 120, :3].tolist() == [60, 50, 40]        # far below the hood: untouched
    assert (new[62, 125, 3]) == 255                          # face opening is closed
    assert json.loads((lab / "hood_blend.json").read_text())["frames"] == 1


def test_second_pass_refused_without_force(tmp_path):
    lab, masks = make_lab(tmp_path)
    H.run(str(lab), str(masks))
    with pytest.raises(SystemExit):
        H.run(str(lab), str(masks))
    H.run(str(lab), str(masks), force=True)
