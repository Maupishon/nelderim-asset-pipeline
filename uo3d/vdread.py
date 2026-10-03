"""Reader of UOFiddler .vd animation files (adapted from the SpriteMotion-UO-Toolkit overlay, vd.py, MIT)."""
import struct
import numpy as np

ANCHOR = (128, 192)


def c16(c):
    r = (c >> 10) & 0x1f; g = (c >> 5) & 0x1f; b = c & 0x1f
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def read_vd(path):
    """-> (anim_type, n_actions, {(action, direction): [frame dict(cx, cy, w, h, img RGBA)]})"""
    d = open(path, "rb").read()
    magic, at = struct.unpack_from("<hh", d, 0)
    if magic != 6:
        raise ValueError(f"{path}: to nie jest plik .vd")
    nact = {0: 22, 1: 13, 2: 35}[at]
    anims = {}
    for i in range(nact * 5):
        off, ln, _ = struct.unpack_from("<iii", d, 4 + 12 * i)
        a, dr = divmod(i, 5)
        if off <= 0 or ln <= 0:
            continue
        pal = [c16(v) for v in struct.unpack_from("<256H", d, off)]
        start = off + 512
        (fc,) = struct.unpack_from("<i", d, start)
        offs = struct.unpack_from("<%di" % fc, d, start + 4)
        frames = []
        for fo in offs:
            p = start + fo
            cx, cy, w, h = struct.unpack_from("<hhHH", d, p); p += 8
            img = np.zeros((h, w, 4), np.uint8)
            xb = cx - 0x200; yb = cy + h - 0x200
            while True:
                (hdr,) = struct.unpack_from("<I", d, p); p += 4
                if hdr == 0x7FFF7FFF:
                    break
                hdr ^= (0x200 << 22) | (0x200 << 12)
                x = xb + ((hdr >> 22) & 0x3ff); y = yb + ((hdr >> 12) & 0x3ff); n = hdr & 0xfff
                idx = d[p:p + n]; p += n
                if 0 <= y < h and x >= 0 and x + n <= w:
                    img[y, x:x + n, :3] = np.array(pal, np.uint8)[np.frombuffer(idx, np.uint8)]
                    img[y, x:x + n, 3] = 255
            frames.append(dict(cx=cx, cy=cy, w=w, h=h, img=img))
        anims[(a, dr)] = frames
    return at, nact, anims


def canvas(fr, size=(256, 256), anchor=ANCHOR):
    """frame -> RGBA canvas (size) with the UO anchor at `anchor`."""
    W, H = size
    out = np.zeros((H, W, 4), np.uint8)
    x = anchor[0] - fr["cx"]; y = anchor[1] - fr["h"] - fr["cy"]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + fr["w"], W), min(y + fr["h"], H)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = fr["img"][y0 - y:y1 - y, x0 - x:x1 - x]
    return out


def alpha_masks(path):
    """{(action, direction): [bool mask (256,256)]} of every frame of a .vd (silhouettes)."""
    _, _, anims = read_vd(path)
    return {k: [canvas(f)[..., 3] > 0 for f in v] for k, v in anims.items()}
