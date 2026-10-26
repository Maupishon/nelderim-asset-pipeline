"""uo3d/tattoo.py on synthetic data (no body model needed)."""
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("scipy")
from uo3d import tattoo as T, statmesh   # noqa: E402


def design(tmp=None):
    """a red disc with a black ring and a white (cream-free) hole on a white card with a grey shadow strip at the right edge"""
    im = np.full((200, 300, 3), 255, np.uint8)
    yy, xx = np.mgrid[0:200, 0:300]
    r = np.hypot(xx - 150, yy - 100)
    im[r < 70] = (200, 40, 30)
    im[(r >= 60) & (r < 70)] = (10, 10, 10)
    im[r < 20] = (255, 255, 255)                      # a white pocket INSIDE the design: must stay part of it
    im[:, 292:] = (225, 228, 232)                     # the card's shadow, far from the design
    return Image.fromarray(im)


def test_cutout_keeps_inner_white_and_drops_card():
    rgb, al = T.cutout(design())
    assert al.shape[0] >= 130 and al.shape[0] <= 145 and al.shape[1] >= 130 and al.shape[1] <= 145      # the disc only (the shadow strip is gone)
    h, w = al.shape
    assert al[h // 2, w // 2]                          # the white pocket is not background
    assert not al[0, 0]


def test_front_surface_and_relief_roundtrip(tmp_path):
    class G:                                           # a tilted plane facing +Z in the chest area
        pos = np.array([[-0.3, 0.8, 0.1], [0.3, 0.8, 0.1], [0.3, 1.7, 0.2], [-0.3, 1.7, 0.2]], float)
        tri = np.array([[0, 1, 2], [0, 2, 3]])
    surf = T.front_surface(G)
    gx, gy, Z = surf
    assert abs(Z[np.searchsorted(gy, 1.0), np.searchsorted(gx, 0.0)] - (0.1 + 0.1 * (1.0 - 0.8) / 0.9)) < 0.01
    out = tmp_path / "r.glb"; top = tmp_path / "r_top.glb"
    tex, st = T.relief(design(), surf, str(out), width=0.2, centre=(0.0, 1.3), grid=60, top_only_glb=str(top))
    assert st["triangles"] > 1000 and tex.shape[2] == 4 and 3.0 < st["relief_mm"] < 4.0
    m = statmesh.load(str(out)); mt = statmesh.load(str(top))
    assert len(m.tri) == 2 * len(mt.tri)               # the back is the second primitive
    assert m.mats[0].tex is not None and m.extras.get("uo3d_rest")
    # the top lies off the surface by 0.4 mm .. 4.1 mm, the centre of the design near x = 0
    assert abs(float(mt.pos[:, 0].mean())) < 0.01
    ic = T.icon(tex, 44)
    assert ic.height == 44 and np.array(ic)[..., 3].max() == 255


def test_bra_mask_finds_the_cloth_not_the_skin():
    g = np.zeros((237, 260, 4), np.uint8)
    g[60:200, 40:140] = (150, 150, 150, 255)           # neutral grey skin
    g[94:110, 76:106] = (168, 168, 152, 255)            # slightly yellow cloth
    m = T.bra_mask(Image.fromarray(g))
    assert m[100, 90] and not m[130, 90] and not m[70, 90]


def test_torso_gump_is_shaded_wrapped_and_hidden_under_the_bra(tmp_path):
    H, W = 237, 260
    body = np.zeros((H, W, 4), np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    body[60:200, 60:125] = (200, 200, 200, 255)
    body[..., :3][(xx > 100) & (body[..., 3] > 0)] = (110, 110, 110)       # the right half is in shadow
    Image.fromarray(body).save(tmp_path / "b.png")
    tex = np.zeros((100, 100, 4), np.uint8); tex[..., :3] = (230, 40, 30); tex[..., 3] = 255
    out = tmp_path / "g.png"
    n = T.torso_gump(tex, str(tmp_path / "b.png"), str(out), centre=(92.0, 103.0), width=0.24)
    g = np.array(Image.open(out))
    assert 300 < n < 600 and g[103, 92, 3] == 255
    assert g[103, 85, :3].sum() > g[103, 100, :3].sum()                     # the shadow of the body shows through the ink
    bra = np.zeros((H, W), bool); bra[96:110, 80:110] = True
    n2 = T.torso_gump(tex, str(tmp_path / "b.png"), str(tmp_path / "g2.png"), centre=(92.0, 103.0), width=0.24, bra=bra)
    g2 = np.array(Image.open(tmp_path / "g2.png"))
    assert n2 < n and g2[103, 92, 3] == 0
