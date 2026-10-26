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


def sheet():
    """a black sleeve (tapering) with white linework, a caption above it and a thin outline stroke: a flash sheet in miniature"""
    im = np.full((260, 700, 3), 255, np.uint8)
    for x in range(60, 640):
        h = 40 + (x - 60) // 12
        im[130 - h:130 + h, x] = 0
        if x % 40 < 6:
            im[130 - h + 10:130 + h - 10, x] = 255                     # white lines across the sleeve
    im[10:22, 200:420:6] = 0                                           # caption letters
    im[40:43, 100:600] = 0                                             # a thin outline stroke above the sleeve
    return Image.fromarray(im)


def test_sleeve_prepare_ignores_text_and_thin_strokes():
    sl = T.sleeve_prepare(sheet())
    assert 55 <= sl["x0"] <= 70 and 630 <= sl["x1"] <= 645
    xi = 300
    assert 130 - (40 + (xi - 60) // 12) - 8 <= sl["top"][xi] <= 130 - (40 + (xi - 60) // 12) + 8     # the sleeve's edge, not the stroke / caption
    assert sl["alpha"][130, 301] > 0.9 and sl["alpha"][130, 62 + 0] >= 0
    assert sl["alpha"][15, 300] == 0 and sl["alpha"][41, 300] == 0


def test_sleeve_xy_wraps_the_circumference():
    sl = T.sleeve_prepare(sheet())
    x_sh, y_front = T.sleeve_xy(sl, np.array([0.0]), np.array([0.0]))
    x_wr, _ = T.sleeve_xy(sl, np.array([1.0]), np.array([0.0]))
    assert x_sh[0] > x_wr[0]                                           # the shoulder is the right end
    xi = int(round(x_sh[0]))
    assert abs(y_front[0] - (sl["top"][xi] + sl["bot"][xi]) / 2) < 1e-6    # the front = the middle of the design's height
    _, y_back = T.sleeve_xy(sl, np.array([0.0]), np.array([np.pi]))
    assert abs(y_back[0] - sl["bot"][xi]) < 1e-6                           # the back = the seam (the edge)


def coloured_design():
    """a tall coloured design (red / green / black) on white with a white hole inside"""
    im = np.full((300, 120, 3), 255, np.uint8)
    im[10:290, 40:80] = (20, 20, 20)
    im[10:60, 10:110] = (120, 20, 40)
    im[120:200, 50:70] = (255, 255, 255)               # skin inside the design
    im[220:280, 30:90] = (30, 80, 50)
    return Image.fromarray(im)


def test_patch_prepare_ink_is_everything_but_white():
    pt = T.patch_prepare(coloured_design())
    assert pt["y0"] <= 11 and pt["y1"] >= 288 and pt["x0"] <= 11 and pt["x1"] >= 108
    assert pt["alpha"][150, 60] == 0 and pt["alpha"][30, 20] == 1 and pt["alpha"][240, 50] == 1       # the white inside stays skin
    x, y = T.patch_xy(pt, np.array([0.05, 1.0]), np.array([0.0, 0.0]))
    assert abs(x[0] - (pt["x0"] + pt["x1"]) / 2) < 1e-6 and abs(y[0] - pt["y0"]) < 1e-6 and abs(y[1] - pt["y1"]) < 1e-6    # the front, top .. bottom


def test_patch_gump_colours_and_hides_under_cloth(tmp_path):
    body = np.zeros((237, 260, 4), np.uint8)
    body[120:222, 90:112] = (190, 190, 190, 255)
    body[124:150, 90:112] = (168, 168, 150, 255)       # underwear: slightly yellow
    Image.fromarray(body).save(tmp_path / "b.png")
    pt = T.patch_prepare(coloured_design())
    spec = ([(104, 132), (102, 172), (99, 196), (97, 208)], [7.0, 5.5, 5.0, 4.5])
    n = T.patch_gump(pt, "L", "12", str(tmp_path / "b.png"), str(tmp_path / "l.png"), spec=spec, cover=0.3)
    g = np.array(Image.open(tmp_path / "l.png"))
    assert n > 30 and g[..., 3].sum() // 255 == n
    assert not g[:150, :, 3].any()                      # under the underwear nothing is drawn
    ink = g[g[..., 3] > 0][:, :3]
    assert (ink[:, 0] > ink[:, 2] + 30).any() or (ink[:, 1] > ink[:, 0] + 20).any()      # red or green ink, not only black


def test_sleeve_gump_draws_ink_on_the_arm_only(tmp_path):
    body = np.zeros((237, 260, 4), np.uint8)
    body[60:200, 100:140] = (200, 200, 200, 255)
    Image.fromarray(body).save(tmp_path / "b.png")
    sl = T.sleeve_prepare(sheet())
    T.SLEEVE_POLY[("L", "99")] = [(112, 84), (115, 98), (119, 110), (134, 123)]
    n = T.sleeve_gump(sl, "L", "99", str(tmp_path / "b.png"), str(tmp_path / "s.png"), cover=0.3)
    g = np.array(Image.open(tmp_path / "s.png"))
    assert n > 20 and g[..., 3].sum() // 255 == n
    assert not g[:75, :, 3].any() and not g[:, :100, 3].any()          # only the arm region
