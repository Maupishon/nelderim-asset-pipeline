#!/usr/bin/env python3
"""
nelderim_core.py - shared, already-proven building blocks for the Nelderim
asset pipeline (uopatch.py, uop_gump_patch.py, vd_inject.py).

This module does not introduce new logic. Every function here is an exact
extraction of code that has already been tested end-to-end in-game on this
shard (kostur, six robes, Fire Giant Hammer). Where a piece of logic turned
out to be WRONG during testing (the anim.idx offset model, twice), the
correction is documented in place rather than silently folded in, because
that history is exactly what stops the same mistake from recurring.

Sections:
  1. Errors & directory helpers
  2. UOP (MYP container) hash + reader/writer
  3. Colour conversion + gump/art pixel codecs
  4. MulPair - streaming idx/mul container (art.mul, Gumpart.mul, ...)
  5. TileData - tiledata.mul field access
  6. mobtypes.txt / body.def / Bodyconv.def / AnimationFrame*.uop loaders
     (collision sources - checked BEFORE picking any target id), plus a
     writer for Equipconv.def (per-bodyType equipment art override - fully
     documented format, purely additive). Bodyconv.def stays READ-ONLY:
     we have no in-game-verified example of a correct new entry there, and
     this project does not ship guessed binary/def formats without proof.
  7. Two DIFFERENT, non-interchangeable anim.idx offset models:
       - cumulative_offsets(): valid ONLY for EQUIPMENT/HUMAN ("People"
         group) bodies, e.g. worn items recycling an existing animation.
       - monster_record_offset(): valid ONLY for MONSTER/SEA_MONSTER
         ("High" group) bodies, e.g. a brand-new mobile animation from a
         .vd container. This is a flat graphic*110 multiply, NOT a walk
         over mobtypes.txt. Mixing these up produces a patch that verifies
         perfectly and renders nothing, with no error anywhere - this
         happened once already (Fire Giant Hammer, 2026-08-07) and cost a
         full diagnostic session to find, using the actual ClassicUO
         client source as the ground truth, not the UOFiddler editor.
  8. Backup + Nelderim_manifest.json helpers
"""

from __future__ import annotations
import glob, hashlib, json, os, shutil, struct, sys, time, zlib

try:
    from PIL import Image
except ImportError:
    Image = None


# ===========================================================================
# 1. Errors & directory helpers
# ===========================================================================

class Problem(Exception):
    pass


def find(directory, name):
    for e in os.listdir(directory):
        if e.lower() == name.lower():
            return os.path.join(directory, e)
    return None


def need(directory, name):
    p = find(directory, name)
    if not p:
        raise Problem(f"missing required file: {name} in {directory}")
    return p


# --- preflight: detect missing recipe assets BEFORE any write ------------
#
# A recipe references image files (art / gump_male / gump_female) and .vd
# containers by relative path. If one is missing, the old tools reacted
# inconsistently: uopatch.py raised mid-run (after already staging other
# items), vd_inject.py raised at read time. That means a typo in item #5
# could leave items #1-4 half-processed in the output folder. Preflight
# fixes that: scan the WHOLE recipe first, collect every missing asset,
# and resolve them all up front under one policy - so a run either has
# everything it needs or stops before touching anything.
#
# "Create the missing file" only makes sense for TEXT assets (def/mobtypes
# rows), which the pipeline already generates. You cannot conjure art or
# animation pixels from nothing, so for image/.vd assets the only honest
# options are: stop, skip, or ask. That is what these three modes are.

MISSING_STOP = "stop"          # default: report all, raise, write nothing
MISSING_SKIP = "skip"          # drop the missing field, process the rest
MISSING_ASK = "ask"            # prompt y/n per asset (interactive / GUI)

# recipe fields that point at an on-disk image asset
_IMAGE_FIELDS = ("art", "gump_male", "gump_female")


def _resolve_asset_path(base, rel):
    """Recipe paths are relative to the recipe file's own directory."""
    return rel if os.path.isabs(rel) else os.path.join(base, rel)


def scan_missing_assets(recipe, base):
    """Return a list of (item_index, item_name, field, resolved_path) for
    every image/vd asset referenced by the recipe that does not exist on
    disk. Pure inspection - never writes, never prompts."""
    missing = []
    for idx, it in enumerate(recipe.get("items", [])):
        name = it.get("name", f"item#{idx}")
        for field in _IMAGE_FIELDS:
            rel = it.get(field)
            if not rel:
                continue
            path = _resolve_asset_path(base, rel)
            if not os.path.exists(path):
                missing.append((idx, name, field, path))
        vd = it.get("vd")
        if vd:
            path = _resolve_asset_path(base, vd)
            if not os.path.exists(path):
                missing.append((idx, name, "vd", path))
    return missing


def resolve_missing_assets(recipe, base, mode=MISSING_STOP,
                           ask_fn=None, log_fn=print):
    """Apply the chosen policy to any missing assets.

    mode=MISSING_STOP  -> if anything is missing, raise Problem listing all.
    mode=MISSING_SKIP  -> delete the missing field from its item (so the
                          rest of that item still processes), warn per drop.
    mode=MISSING_ASK   -> call ask_fn(item_name, field, path) -> bool for
                          each; True keeps waiting on the user to supply it
                          (re-checks existence), False drops the field like
                          SKIP. Falls back to STOP behaviour for a missing
                          file the user says they do have but still isn't
                          there, to avoid an infinite loop.

    Returns the (possibly mutated) recipe. Does not write any client files.
    """
    missing = scan_missing_assets(recipe, base)
    if not missing:
        return recipe

    if mode == MISSING_STOP:
        lines = "\n".join(f"    [{name}] {field}: {path}"
                          for _, name, field, path in missing)
        raise Problem(
            f"{len(missing)} referenced asset(s) not found on disk:\n{lines}\n"
            "  Fix the paths, supply the files, or re-run with a missing-"
            "asset policy (skip / interactive).")

    items = recipe.get("items", [])
    for idx, name, field, path in missing:
        if mode == MISSING_SKIP:
            log_fn(f"[SKIP  ] {name}: {field} missing ({path}) - "
                   "dropping this field, processing the rest of the item")
            items[idx].pop(field, None)
            continue

        if mode == MISSING_ASK:
            if ask_fn is None:
                raise Problem("MISSING_ASK requires an ask_fn callback")
            have_it = ask_fn(name, field, path)
            if have_it and os.path.exists(path):
                log_fn(f"[OK    ] {name}: {field} now present ({path})")
            elif have_it:
                # user claims to have it but it's still not there
                raise Problem(
                    f"{name}: {field} still not found at {path} after the "
                    "user confirmed it exists - aborting rather than guess.")
            else:
                log_fn(f"[SKIP  ] {name}: {field} dropped by user choice")
                items[idx].pop(field, None)

    return recipe


# ===========================================================================
# 2. UOP (MYP container) hash + reader/writer
#    Extracted verbatim from uop_gump_patch.py. Verified against
#    ClassicUO's own UopUtils.HashFileName (rotate-combine identity holds;
#    see uop_gump_patch.py history for the side-by-side derivation) and
#    against ClassicUO's FileIndex.cs UOP-with-extra reader (8-byte
#    width/height prefix inside clen/dlen, hlen=0, flag=0/uncompressed).
# ===========================================================================

def uop_hash(s: str) -> int:
    b = s.encode("ascii")
    M = 0xFFFFFFFF
    n = len(b)
    ebx = edi = esi = (n + 0xDEADBEEF) & M
    eax = ecx = edx = 0
    i = 0
    while i + 12 < n:
        edi = (((b[i+7] << 24) | (b[i+6] << 16) | (b[i+5] << 8) | b[i+4]) + edi) & M
        esi = (((b[i+11] << 24) | (b[i+10] << 16) | (b[i+9] << 8) | b[i+8]) + esi) & M
        edx = (((b[i+3] << 24) | (b[i+2] << 16) | (b[i+1] << 8) | b[i]) - esi) & M
        edx = (edx + ebx) & M ^ ((esi >> 28) | (esi << 4) & M) & M
        edx &= M
        esi = (esi + edi) & M
        edi = ((edi - edx) & M) ^ (((edx >> 26) | ((edx << 6) & M)) & M)
        edi &= M
        edx = (edx + esi) & M
        esi = ((esi - edi) & M) ^ (((edi >> 24) | ((edi << 8) & M)) & M)
        esi &= M
        edi = (edi + edx) & M
        ebx = ((edx - esi) & M) ^ (((esi >> 16) | ((esi << 16) & M)) & M)
        ebx &= M
        esi = (esi + edi) & M
        edi = ((edi - ebx) & M) ^ (((ebx >> 13) | ((ebx << 19) & M)) & M)
        edi &= M
        ebx = (ebx + esi) & M
        esi = ((esi - edi) & M) ^ (((edi >> 28) | ((edi << 4) & M)) & M)
        esi &= M
        edi = (edi + ebx) & M
        i += 12
    rem = n - i
    if rem > 0:
        if rem >= 12: esi = (esi + (b[i+11] << 24)) & M
        if rem >= 11: esi = (esi + (b[i+10] << 16)) & M
        if rem >= 10: esi = (esi + (b[i+9] << 8)) & M
        if rem >= 9:  esi = (esi + b[i+8]) & M
        if rem >= 8:  edi = (edi + (b[i+7] << 24)) & M
        if rem >= 7:  edi = (edi + (b[i+6] << 16)) & M
        if rem >= 6:  edi = (edi + (b[i+5] << 8)) & M
        if rem >= 5:  edi = (edi + b[i+4]) & M
        if rem >= 4:  ebx = (ebx + (b[i+3] << 24)) & M
        if rem >= 3:  ebx = (ebx + (b[i+2] << 16)) & M
        if rem >= 2:  ebx = (ebx + (b[i+1] << 8)) & M
        if rem >= 1:  ebx = (ebx + b[i]) & M
        esi = (esi ^ edi) & M
        esi = (esi - (((edi >> 18) | ((edi << 14) & M)) & M)) & M
        ecx = (esi ^ ebx) & M
        ecx = (ecx - (((esi >> 21) | ((esi << 11) & M)) & M)) & M
        edi = (edi ^ ecx) & M
        edi = (edi - (((ecx >> 7) | ((ecx << 25) & M)) & M)) & M
        esi = (esi ^ edi) & M
        esi = (esi - (((edi >> 16) | ((edi << 16) & M)) & M)) & M
        edx = (esi ^ ecx) & M
        edx = (edx - (((esi >> 28) | ((esi << 4) & M)) & M)) & M
        edi = (edi ^ edx) & M
        edi = (edi - (((edx >> 18) | ((edx << 14) & M)) & M)) & M
        eax = (esi ^ edi) & M
        eax = (eax - (((edi >> 8) | ((edi << 24) & M)) & M)) & M
        return ((edi << 32) | eax) & 0xFFFFFFFFFFFFFFFF
    return ((esi << 32) | eax) & 0xFFFFFFFFFFFFFFFF


def gump_path(gid):
    return f"build/gumpartlegacymul/{gid:08d}.tga"


def animframe_path(body, group):
    return f"build/animationlegacyframe/{body:06d}/{group:02d}.bin"


def read_uop_hashes(path):
    """Fast path: just the set of populated hashes (collision checks)."""
    f = open(path, "rb")
    if f.read(4) != b"MYP\x00":
        raise Problem(f"not a UOP file: {path}")
    ver, sig, nextblk, blkcap, cnt = struct.unpack("<II q i i", f.read(24))
    hashes = set()
    f.seek(nextblk)
    while True:
        n_files, nxt = struct.unpack("<i q", f.read(12))
        for _ in range(n_files):
            off, hlen, clen, dlen, h, adler, flag = struct.unpack(
                "<q i i i Q I h", f.read(34))
            if off:
                hashes.add(h)
        if nxt == 0:
            break
        f.seek(nxt)
    return hashes


class UopFile:
    """Full read/write access to a MYP container: remembers exactly where
    each entry's 34-byte record lives, so a single entry can be repointed
    at freshly-appended data without touching anything else in the file.
    Extracted verbatim from uop_gump_patch.py (tested on the real, 142MB
    gumpartLegacyMUL.uop: 4391 entries before/after, only targeted entries
    changed, 20 random unrelated entries payload-identical)."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "r+b")
        self.f.seek(0)
        if self.f.read(4) != b"MYP\x00":
            raise Problem(f"not a UOP file: {path}")
        self.ver, self.sig, self.nextblk, self.blkcap, self.cnt = \
            struct.unpack("<II q i i", self.f.read(24))
        self.entries = {}  # hash -> dict(off, hlen, clen, dlen, adler, flag, record_pos)
        pos = self.nextblk
        while True:
            self.f.seek(pos)
            n_files, nxt = struct.unpack("<i q", self.f.read(12))
            for _ in range(n_files):
                record_pos = self.f.tell()
                off, hlen, clen, dlen, h, adler, flag = struct.unpack(
                    "<q i i i Q I h", self.f.read(34))
                if off:
                    self.entries[h] = dict(off=off, hlen=hlen, clen=clen,
                                            dlen=dlen, adler=adler, flag=flag,
                                            record_pos=record_pos)
            if nxt == 0:
                break
            pos = nxt

    def read_payload(self, h):
        e = self.entries[h]
        self.f.seek(e["off"] + e["hlen"])
        return self.f.read(e["clen"])

    def replace_payload(self, h, new_payload):
        """Append new_payload to end of file, then overwrite ONLY this
        entry's 34-byte record in place to point at it. hlen forced to 0,
        flag forced to 0 (stored/uncompressed) - matches every entry
        inspected on this shard. Nothing else in the file is touched."""
        if h not in self.entries:
            raise KeyError(f"hash {h} not present in this UOP")
        e = self.entries[h]
        self.f.seek(0, os.SEEK_END)
        new_off = self.f.tell()
        self.f.write(new_payload)
        new_len = len(new_payload)
        new_adler = zlib.adler32(new_payload) & 0xFFFFFFFF
        self.f.seek(e["record_pos"])
        self.f.write(struct.pack("<q i i i Q I h",
                                  new_off, 0, new_len, new_len, h,
                                  new_adler, 0))
        e.update(off=new_off, hlen=0, clen=new_len, dlen=new_len,
                 adler=new_adler, flag=0)

    def close(self):
        self.f.close()


# ===========================================================================
# 3. Colour conversion + gump/art pixel codecs
#    Extracted verbatim from uopatch.py. Verified byte-exact against this
#    client's real gump data (7/7 samples) and round-trip clean for art.
# ===========================================================================

def rgb_to_1555(r, g, b, a=255):
    if a < 128:
        return 0
    v = 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    return v if v != 0 else 0x8000  # never emit 0 for a visible pixel


def v1555_to_rgba(v):
    if v == 0:
        return (0, 0, 0, 0)
    r = ((v >> 10) & 0x1F) << 3
    g = ((v >> 5) & 0x1F) << 3
    b = (v & 0x1F) << 3
    return (r, g, b, 255)


def load_png(path):
    """Accepts PNG, BMP, or anything Pillow can open.

    CAVEAT, confirmed by direct test: a standard BMP has no alpha channel
    (Pillow's own BMP encoder silently drops it on save - verified: an
    RGBA image with a transparent half, saved as .bmp and reopened, comes
    back as mode 'RGB' with every pixel's alpha effectively 255 after
    convert("RGBA")). A BMP with an intended transparent cutout will
    therefore render as a solid, fully opaque rectangle in-game - not a
    codec bug, just what the BMP format is. This function warns rather
    than silently accepting it, because "the file loaded fine" and "the
    file will look right in-game" are not the same claim, and this
    project does not ship that gap quietly."""
    if Image is None:
        raise Problem("Pillow is not installed: pip install Pillow")
    if not os.path.exists(path):
        raise Problem(f"image not found: {path}")
    im_raw = Image.open(path)
    if im_raw.format == "BMP" and "A" not in im_raw.getbands():
        sys.stderr.write(
            f"[WARN] {path}: BMP has no alpha channel - it will render "
            "fully opaque (no transparent cutout) in-game. Use PNG if "
            "this asset needs a transparent background.\n")
    im = im_raw.convert("RGBA")
    w, h = im.size
    px = im.load()
    grid = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            grid[y][x] = rgb_to_1555(r, g, b, a)
    return w, h, grid


def encode_gump(w, h, px):
    body = bytearray()
    offs = []
    cur = h  # offsets are in dwords, measured from start of the table
    for y in range(h):
        offs.append(cur)
        x = 0
        while x < w:
            c = px[y][x]
            n = 1
            while x + n < w and px[y][x + n] == c:
                n += 1
            body += struct.pack("<HH", c, n)
            cur += 1
            x += n
    return struct.pack(f"<{h}I", *offs) + bytes(body)


def decode_gump(d, w, h):
    offs = struct.unpack_from(f"<{h}I", d, 0)
    px = [[0] * w for _ in range(h)]
    for y in range(h):
        p = offs[y] * 4
        x = 0
        while x < w:
            c, n = struct.unpack_from("<HH", d, p)
            p += 4
            if n == 0:
                break
            for _ in range(n):
                if x < w:
                    px[y][x] = c
                    x += 1
    return px


def build_uop_gump_payload(w, h, px):
    """UOP gump entry = 8-byte (width,height) header + encode_gump body.
    Confirmed against ClassicUO's FileIndex.cs UOP-with-extra reader."""
    return struct.pack("<II", w, h) + encode_gump(w, h, px)


def decode_uop_gump_payload(data):
    w, h = struct.unpack_from("<II", data, 0)
    return w, h, decode_gump(data[8:], w, h)


def encode_art(w, h, px, flag=1234):
    body = bytearray()
    lk = []
    cur = 0
    for y in range(h):
        lk.append(cur // 2)
        prev = 0
        x = 0
        while x < w:
            while x < w and px[y][x] == 0:
                x += 1
            if x >= w:
                break
            s = x
            while x < w and px[y][x] != 0:
                x += 1
            body += struct.pack("<HH", s - prev, x - s)
            for c in px[y][s:x]:
                body += struct.pack("<H", c)
            prev = x
            cur += 4 + 2 * (x - s)
        body += struct.pack("<HH", 0, 0)
        cur += 4
    return (struct.pack("<Ihh", flag, w, h)
            + struct.pack(f"<{h}H", *lk) + bytes(body))


def decode_art(d):
    flag, w, h = struct.unpack_from("<Ihh", d, 0)
    lk = struct.unpack_from(f"<{h}H", d, 8)
    base = 8 + h * 2
    px = [[0] * w for _ in range(h)]
    for y in range(h):
        p = base + lk[y] * 2
        x = 0
        while True:
            xo, rl = struct.unpack_from("<HH", d, p)
            p += 4
            if xo == 0 and rl == 0:
                break
            x += xo
            for _ in range(rl):
                px[y][x] = struct.unpack_from("<H", d, p)[0]
                p += 2
                x += 1
    return flag, w, h, px


# ===========================================================================
# 4. MulPair - streaming idx/mul container (art.mul, Gumpart.mul, ...)
#    Extracted verbatim from uopatch.py.
# ===========================================================================

IDX_REC = 12
ART_STATIC_BASE = 0x4000
GUMP_MALE_BASE = 50000
GUMP_FEMALE_BASE = 60000


class MulPair:
    def __init__(self, idx_path, mul_path):
        self.idx_path, self.mul_path = idx_path, mul_path
        self.idx = bytearray(open(idx_path, "rb").read())
        self.count = len(self.idx) // IDX_REC
        self._mul = open(mul_path, "rb")
        self.new = {}   # id -> (bytes, extra)

    def entry(self, i):
        if i < 0 or i >= self.count:
            return None
        lk, ln, ex = struct.unpack_from("<iii", self.idx, i * IDX_REC)
        return lk, ln, ex

    def raw(self, i):
        e = self.entry(i)
        if not e or e[0] == -1 or e[0] < 0:
            return None
        self._mul.seek(e[0])
        return self._mul.read(e[1]), e[2]

    def occupied(self, i):
        e = self.entry(i)
        return bool(e and e[0] != -1 and e[0] >= 0 and e[1] > 0)

    def stage(self, i, data, extra):
        self.new[i] = (data, extra)

    def write(self, out_idx, out_mul):
        top = max([self.count - 1] + list(self.new)) + 1
        idx_out = bytearray(top * IDX_REC)
        with open(out_mul, "wb") as mo:
            for i in range(top):
                if i in self.new:
                    data, extra = self.new[i]
                    pos = mo.tell()
                    mo.write(data)
                    struct.pack_into("<iii", idx_out, i * IDX_REC,
                                     pos, len(data), extra)
                    continue
                r = self.raw(i)
                if r is None:
                    struct.pack_into("<iii", idx_out, i * IDX_REC, -1, -1, 0)
                else:
                    data, extra = r
                    pos = mo.tell()
                    mo.write(data)   # verbatim copy, never re-encoded
                    struct.pack_into("<iii", idx_out, i * IDX_REC,
                                     pos, len(data), extra)
        open(out_idx, "wb").write(bytes(idx_out))


# ===========================================================================
# 5. TileData - tiledata.mul field access
#    Extracted verbatim from uopatch.py. Field offsets cross-checked
#    against UOFiddler's TileData.cs NewItemTileDataMul struct: anim@14
#    confirmed exact, height@20/name@21 confirmed exact. The "layer" field
#    here is called "quality" in the canonical struct - same byte, this
#    shard's items use it as equip layer, which is standard UO server
#    practice, not a mismatch.
# ===========================================================================

TD_LAND_BLOCKS = 512
TD_LAND_ENTRY = 30
TD_STATIC_ENTRY = 41

FLAG_BITS = {
    "Background": 0x1, "Weapon": 0x2, "Transparent": 0x4, "Translucent": 0x8,
    "Wall": 0x10, "Damaging": 0x20, "Impassable": 0x40, "Wet": 0x80,
    "Surface": 0x200, "Bridge": 0x400, "Generic": 0x800, "Window": 0x1000,
    "NoShoot": 0x2000, "ArticleA": 0x4000, "ArticleAn": 0x8000,
    "Internal": 0x10000, "Foliage": 0x20000, "PartialHue": 0x40000,
    "Map": 0x100000, "Container": 0x200000, "Wearable": 0x400000,
    "LightSource": 0x800000, "Animation": 0x1000000, "NoDiagonal": 0x2000000,
    "Armor": 0x8000000, "Roof": 0x10000000, "Door": 0x20000000,
    "StairBack": 0x40000000, "StairRight": 0x80000000,
}


class TileData:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        self.land = TD_LAND_BLOCKS * (4 + 32 * TD_LAND_ENTRY)
        expect = self.land + 2048 * (4 + 32 * TD_STATIC_ENTRY)
        if len(self.data) != expect:
            raise Problem(
                f"tiledata.mul is {len(self.data)} bytes, expected {expect} "
                "for the post-7.0.9 format; refusing to guess")

    def _off(self, i):
        return (self.land + (i >> 5) * (4 + 32 * TD_STATIC_ENTRY)
                + 4 + (i & 31) * TD_STATIC_ENTRY)

    def read(self, i):
        o = self._off(i)
        flags, weight, layer, misc, unk2, qty, anim = struct.unpack_from(
            "<QBBHBBH", self.data, o)
        height = self.data[o + 20]
        name = self.data[o + 21:o + 41].split(b"\x00")[0].decode(
            "latin-1", "ignore")
        return {"flags": flags, "weight": weight, "layer": layer,
                "anim": anim, "height": height, "name": name}

    def update(self, i, flags=None, weight=None, layer=None, anim=None,
               name=None, height=None):
        o = self._off(i)
        if flags is not None:
            struct.pack_into("<Q", self.data, o, flags)
        if weight is not None:
            struct.pack_into("<B", self.data, o + 8, weight & 0xFF)
        if layer is not None:
            struct.pack_into("<B", self.data, o + 9, layer & 0xFF)
        if anim is not None:
            struct.pack_into("<H", self.data, o + 14, anim & 0xFFFF)
        if height is not None:
            struct.pack_into("<B", self.data, o + 20, height & 0xFF)
        if name is not None:
            # Static entry is 41 bytes: 21 bytes of fields, then a 20-byte
            # name at offset 21. Writing at offset 20 clobbers the height
            # byte and shifts the name by one character - this was a real
            # bug once (corrupted item names/heights), fixed, keep the note.
            raw = name.encode("latin-1", "ignore")[:20]
            self.data[o + 21:o + 41] = raw + b"\x00" * (20 - len(raw))

    def write(self, path):
        open(path, "wb").write(bytes(self.data))


def as_int(v):
    if isinstance(v, int):
        return v
    v = str(v).strip()
    return int(v, 16) if v.lower().startswith("0x") else int(v)


# ===========================================================================
# 6. Collision sources: mobtypes.txt, body.def, Bodyconv.def,
#    AnimationFrame*.uop / gumpartLegacyMUL.uop.
#    A target id/slot must be checked against ALL of these before use -
#    each one has independently caused a "verifies fine, invisible in
#    game" failure this session (kostur: Bodyconv.def; giant: body.def
#    plus, separately, the wrong offset model - see section 7).
# ===========================================================================

def load_mobtypes(path):
    d = {}
    if not path or not os.path.exists(path):
        return d
    for line in open(path, encoding="latin-1"):
        s = line.split("#")[0].strip()
        if not s:
            continue
        p = s.split()
        if len(p) < 2:
            continue
        try:
            d[int(p[0])] = p[1].upper()
        except ValueError:
            pass
    return d


def load_bodyconv_bodies(path):
    out = set()
    for line in open(path, encoding="latin-1"):
        s = line.split("#")[0].strip()
        if not s:
            continue
        p = s.split()
        try:
            out.add(int(p[0]))
        except ValueError:
            pass
    return out


def _load_brace_redirect_ids(path):
    """Shared parser for the `<ORIG> {<NEW>} <HUE>` redirect format used
    by body.def, gump.def, and art.def alike. Returns the set of ORIG ids
    - each one means the client resolves to something else instead, so
    writing to the original id's own slot may render nothing."""
    out = set()
    for line in open(path, encoding="latin-1"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            i1 = s.index("{")
            out.add(int(s[:i1].strip()))
        except (ValueError, IndexError):
            continue
    return out


def load_bodydef_bodies(path):
    """body.def rewrites a body id to a DIFFERENT one before the client
    ever looks at anim.idx (resolution order: body.def -> UOP ->
    Bodyconv.def -> anim.mul). Format per line: `original {newBody}
    newHue`. Any original id listed here is unusable as an injection
    target - the client always resolves to newBody instead."""
    return _load_brace_redirect_ids(path)


def load_gumpdef_ids(path):
    """gump.def redirects a paperdoll gump id to a different one, same
    `<ORIG> {<NEW>} <HUE>` syntax as body.def. If a gump id being patched
    is listed here as an ORIG, the client may show the {NEW} gump instead
    of whatever was just written - the same silent-redirect risk as
    body.def, just for gumps instead of bodies. This project only
    discovered gump.def's real content late (2026-08-11); until its exact
    position in the resolution order relative to gumpartLegacyMUL.uop is
    verified against client source, treat any match as a WARN, not a
    hard block - the write may still be fine, but check in-game."""
    return _load_brace_redirect_ids(path)


def load_artdef_ids(path):
    """art.def redirects a static/item art id, same `<ORIG> {<NEW>}
    <HUE>` syntax. Same caveat as load_gumpdef_ids: flagged as a WARN
    when a target art id matches, not silently avoided or blocked."""
    return _load_brace_redirect_ids(path)


# --- Equipconv.def: per-bodyType equipment art override -------------------
#
# Format (confirmed against this shard's own file header AND against
# ClassicUO's ProcessEquipConvDef, which reads exactly 5 whitespace-
# separated fields via DefReader(file, 5)):
#
#     bodyType   equipmentID   convertToID   gumpID   hue
#
#     gumpID  0      -> equipmentID + 50000   (client: `gump = graphic`,
#                        the +50000 offset is applied at gump-id lookup
#                        time using the same convention as GUMP_MALE_BASE)
#     gumpID  -1     -> convertToID  + 50000   (`gump = newGraphic`)
#     gumpID  else   -> used literally (female art = male + 10000)
#
# Purpose: makes a wearable show DIFFERENT art on a different bodyType
# (e.g. so human clothing isn't shown, unmodified, on the slimmer elf/
# gargoyle body) without touching the item's own tiledata anim field.
#
# UNLIKE Bodyconv.def, this format is fully documented (this shard's own
# header comment matches the real client parser field-for-field) and is
# purely ADDITIVE - it only adds a per-bodyType lookup entry, it does not
# redirect a body's fundamental animation resolution. That is why this
# one gets a writer and Bodyconv.def (below, still read-only) does not:
# we have no tested, in-game-verified example of a correct NEW
# Bodyconv.def entry, and guessing at that format after today's offset
# lesson is exactly the mistake this project is trying to stop making.

def load_equipconv(path):
    """Returns list of (bodyType, equipmentID, convertToID, gumpID, hue,
    comment) tuples, in file order."""
    out = []
    for line in open(path, encoding="latin-1"):
        raw = line.rstrip("\r\n")
        s = raw.split("#")[0].strip()
        if not s:
            continue
        parts = s.split()
        if len(parts) < 5:
            continue
        try:
            bodyType, equipID, convID, gumpID, hue = (int(p) for p in parts[:5])
        except ValueError:
            continue
        comment = raw.split("#", 1)[1].strip() if "#" in raw else ""
        out.append((bodyType, equipID, convID, gumpID, hue, comment))
    return out


def equipconv_entries_for(path, equipment_id):
    """Existing entries for a given equipmentID, keyed by bodyType - used
    to detect a collision (an entry already exists for this item+bodyType)
    before appending a duplicate."""
    out = {}
    for bodyType, equipID, convID, gumpID, hue, comment in load_equipconv(path):
        if equipID == equipment_id:
            out[bodyType] = (convID, gumpID, hue, comment)
    return out


def add_equipconv_entries(client, out, entries, source_label=""):
    """Append new Equipconv.def rows. `entries` is a list of
    (bodyType, equipmentID, convertToID, gumpID, hue, comment) tuples.
    Refuses to add a row for a (bodyType, equipmentID) pair that already
    exists - that is a collision to resolve by hand, not overwrite
    silently. Returns (written_filename_or_None, skipped_collisions)."""
    src = need(client, "Equipconv.def")
    existing = load_equipconv(src)
    existing_keys = {(e[0], e[1]) for e in existing}

    to_write = []
    skipped = []
    for bodyType, equipID, convID, gumpID, hue, comment in entries:
        if (bodyType, equipID) in existing_keys:
            skipped.append((bodyType, equipID))
            continue
        to_write.append((bodyType, equipID, convID, gumpID, hue, comment))

    if not to_write:
        return None, skipped

    dst = os.path.join(out, "Equipconv.def")
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(src, dst)
    with open(dst, "a", encoding="latin-1", newline="\r\n") as f:
        f.write(f"\r\n# --- added by nelderim_core.py"
                + (f" ({source_label})" if source_label else "") + " ---\r\n")
        for bodyType, equipID, convID, gumpID, hue, comment in to_write:
            line = f"{bodyType}\t{equipID}\t{convID}\t{gumpID}\t{hue}"
            if comment:
                line += f"\t# {comment}"
            f.write(line + "\r\n")
    return "Equipconv.def", skipped


def gump_uop_bodies(client, gids):
    """Which of the given gump ids already exist in gumpartLegacyMUL.uop.
    UOP beats MUL - a gump id present here means writing to Gumpart.mul
    alone has no visible effect; use UopFile/build_uop_gump_payload."""
    up = find(client, "gumpartLegacyMUL.uop")
    if not up:
        return set()
    hs = read_uop_hashes(up)
    return {g for g in gids if uop_hash(gump_path(g)) in hs}


def animframe_uop_bodies(client, lo=0, hi=2048):
    """Bodies present in AnimationFrame*.uop (any of the 5 direction
    groups) within [lo,hi)."""
    out = set()
    for p in glob.glob(os.path.join(client, "AnimationFrame*.uop")):
        hs = read_uop_hashes(p)
        for body in range(lo, hi):
            for g in range(5):
                if uop_hash(animframe_path(body, g)) in hs:
                    out.add(body)
                    break
    return out


# ===========================================================================
# 7. anim.idx offset models - TWO, NOT interchangeable.
# ===========================================================================

class AnimIdx:
    """Cumulative-offset model. Client walks bodies 0..2047 in order,
    summing each body's stride (action_count*5) by mobtype. VALID ONLY for
    the "People" group (EQUIPMENT/HUMAN types, e.g. worn-item animation
    recycling like the kostur at body 1011/anim 617).

    Why this is fragile, precisely: for graphic>=400, the real client
    formula is CalculatePeopleGroupOffset(g) = (g-400)*175 + 35000. That
    "+35000" is a HARDCODED constant assuming exactly 200 MONSTER-band +
    200 ANIMAL-band bodies precede it - the client does NOT dynamically
    re-sum the <400 bands from mobtypes.txt. This cumulative walk only
    produces the same number because, so far, nothing on this shard has
    ever overridden a body <400's mobtype. If that ever changes, this
    class's numbers and the real client's numbers will silently diverge
    for every People-group item. Do not extend this class's territory
    to bodies <400 without re-deriving against the real formula first.

    NEVER use this for MONSTER/SEA_MONSTER ("High"/"Low" group) bodies -
    see monster_record_offset() instead. Mixing these up is exactly what
    made the Fire Giant Hammer invisible on the first injection attempt:
    data written at the cumulative-model offset, client reading from the
    flat graphic*110 offset, zero errors anywhere, zero sprite.
    """

    GROUP = {"MONSTER": 22, "SEA_MONSTER": 22, "HUMAN": 35,
             "EQUIPMENT": 35, "ANIMAL": 13}
    DIRS = 5

    def __init__(self, path, mobtypes):
        self.path = path
        self.idx = bytearray(open(path, "rb").read())
        self.count = len(self.idx) // IDX_REC
        self.mob = mobtypes
        self.offsets = self._build()

    @staticmethod
    def _dt(b):
        return "MONSTER" if b < 200 else ("ANIMAL" if b < 400 else "HUMAN")

    def _type(self, b):
        return self.mob.get(b, self._dt(b))

    def _build(self):
        out, tot = [], 0
        for b in range(2048):
            out.append(tot)
            tot += self.GROUP.get(self._type(b), 13) * self.DIRS
        return out

    def span(self, body):
        start = self.offsets[body]
        return start, self.GROUP.get(self._type(body), 13) * self.DIRS

    def populated(self, body):
        s, n = self.span(body)
        if s >= self.count:
            return False
        for i in range(s, min(s + n, self.count)):
            lk = struct.unpack_from("<i", self.idx, i * IDX_REC)[0]
            if lk != -1:
                return True
        return False

    def link(self, dst_body, src_body):
        """Copies anim.idx RECORDS (not pixel data) from src to dst.
        Byte-identical on disk, but the client was observed to refuse to
        render a slot populated this way (kostur test, body 1011->617
        link failed; direct anim=617 recycling worked). Kept only for
        --allow-link opt-in compatibility; prefer recycling instead."""
        ss, sn = self.span(src_body)
        ds, dn = self.span(dst_body)
        if sn != dn:
            raise Problem(
                f"anim {src_body} and {dst_body} have different action "
                f"counts ({sn} vs {dn}); give them the same mobtype first")
        need_len = (ds + dn) * IDX_REC
        if len(self.idx) < need_len:
            self.idx.extend(b"\xff" * (need_len - len(self.idx)))
            for i in range(self.count, ds + dn):
                struct.pack_into("<iii", self.idx, i * IDX_REC, -1, -1, 0)
            self.count = ds + dn
        copied = 0
        for k in range(dn):
            src = ss + k
            if src >= self.count:
                break
            rec = self.idx[src * IDX_REC:(src + 1) * IDX_REC]
            self.idx[(ds + k) * IDX_REC:(ds + k + 1) * IDX_REC] = rec
            if struct.unpack_from("<i", rec, 0)[0] != -1:
                copied += 1
        return copied

    def write(self, path):
        open(path, "wb").write(bytes(self.idx))


# --- MONSTER / "High group" offset model --------------------------------
# Extracted from ClassicUO's actual client source
# (src/ClassicUO.Assets/AnimationsLoader.cs, CalculateHighGroupOffset),
# not derived or guessed. This is the formula the real client uses for
# MONSTER-type bodies with no CalculateOffsetByPeopleGroup/ByLowGroup
# flag set in mobtypes.txt (i.e. plain "BODY\tMONSTER\t0" entries, which
# is what this pipeline writes).

HIGH_GROUP_ACTIONS = 22   # HighAnimationGroup.AnimationCount in the client
MONSTER_DIRS = 5
MONSTER_RECORDS = HIGH_GROUP_ACTIONS * MONSTER_DIRS  # 110


def monster_record_offset(graphic):
    """anim.idx RECORD index (not byte offset) where a MONSTER-type body's
    22 actions * 5 directions begin. Flat multiply - depends ONLY on the
    graphic's own number, independent of every other body's mobtypes.txt
    entry or ordering. Do not replace this with a cumulative walk."""
    return graphic * MONSTER_RECORDS


class AnimIdxFile:
    """Raw record read/write for anim.idx, used with monster_record_offset.
    Deliberately does not compute offsets itself (see monster_record_offset
    above) - keeps this class honest about which model it's for."""

    def __init__(self, path):
        self.path = path
        self.idx = bytearray(open(path, "rb").read())
        self.count = len(self.idx) // IDX_REC

    def span_free(self, start, length):
        for i in range(start, start + length):
            if i < self.count:
                lk = struct.unpack_from("<i", self.idx, i * IDX_REC)[0]
                if lk != -1:
                    return False
        return True

    def record(self, i):
        if i >= self.count:
            return (-1, -1, 0)
        return struct.unpack_from("<iii", self.idx, i * IDX_REC)

    def set_record(self, i, lookup, length, extra):
        need_len = (i + 1) * IDX_REC
        if len(self.idx) < need_len:
            grow_from = self.count
            self.idx.extend(b"\x00" * (need_len - len(self.idx)))
            for j in range(grow_from, i + 1):
                struct.pack_into("<iii", self.idx, j * IDX_REC, -1, -1, 0)
            self.count = i + 1
        struct.pack_into("<iii", self.idx, i * IDX_REC, lookup, length, extra)

    def write(self, path):
        open(path, "wb").write(bytes(self.idx))


# ===========================================================================
# 8. Backup + Nelderim_manifest.json helpers
#    Extracted verbatim from uopatch.py.
# ===========================================================================

MANIFEST_NAME = "Nelderim_manifest.json"


def backup_client_files(client, out, names):
    """Copy the *current live* versions of the given files into out/backup/
    with a timestamp, before generating replacements. Non-fatal if a file
    is missing (e.g. first run). Returns the backup dir, or None."""
    if not names:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(out, "backup", stamp)
    saved = []
    for nm in names:
        src = find(client, nm)
        if src and os.path.exists(src):
            os.makedirs(bdir, exist_ok=True)
            shutil.copyfile(src, os.path.join(bdir, nm))
            saved.append(nm)
    return bdir if saved else None


def update_manifest(client, out, written):
    """Write/refresh Nelderim_manifest.json in out/, recording the SHA1 of
    every file just written. Carries forward existing manifest entries."""
    manifest = {"version": 1, "files": {}}
    existing = find(client, MANIFEST_NAME)
    if existing and os.path.exists(existing):
        try:
            old = json.load(open(existing, encoding="utf-8"))
            if isinstance(old, dict):
                manifest["version"] = old.get("version", 1)
                manifest["files"] = dict(old.get("files", {}))
        except (ValueError, OSError):
            pass
    manifest["version"] = int(manifest["version"]) + 1
    for w in written:
        p = os.path.join(out, w)
        manifest["files"][w] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    dst = os.path.join(out, MANIFEST_NAME)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return dst, manifest["version"]
