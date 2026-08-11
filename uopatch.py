#!/usr/bin/env python3
"""
uopatch.py - automate adding wearables / art / gumps / animation links to a
UO client, driven by a JSON recipe instead of hand-clicking MulPatcher.

SAFETY DESIGN (this tool touches production art files, so it is paranoid):

  1. NEVER writes in place. Reads from --client, writes to --out. Your live
     folder is untouched until you copy files across yourself.
  2. NEVER re-encodes existing data. Every entry that is not being changed is
     copied byte-for-byte. Only genuinely new PNGs get encoded. This means a
     round-trip through this tool cannot corrupt art that it was not asked to
     modify.
  3. Dry-run by default. You must pass --apply to write anything.
  4. Verifies after writing: re-opens every output file, re-reads every entry
     it claims to have added, and checks dimensions and pixels survived.
  5. Warns when a target gump id already exists in gumpartLegacyMUL.uop,
     because ClassicUO prefers UOP over MUL and your MUL write would be
     silently ignored.
  6. Backs up the live version of every file it is about to regenerate into
     out/backup/<timestamp>/ before writing, so a bad patch is reversible.
  7. Writes/refreshes Nelderim_manifest.json with the SHA1 of every output,
     so the launcher's overwrite-guard recognises the patched files.

ANIMATION MODEL (important, learned by testing on this shard):

  The paperdoll gump is derived from the ANIM id, not the item id. So the
  reliable way to give a wearable an in-hand / paperdoll look is to RECYCLE
  an existing, working body:

      "anim": 617          # 617 = black staff. The item shares its frames
                           # AND its gump 50617 - it just works.

  Creating a brand-new anim slot by copying frame records ("anim_copy_from")
  is byte-for-byte correct on disk but the client was observed to refuse to
  render the new slot. That path is therefore OFF by default and only runs
  with --allow-link. Prefer recycling.

RECIPE FORMAT (JSON):

{
  "items": [
    {
      "name":        "Kostur Bialego Czarodzieja",
      "item_id":     "0x5384",
      "art":         "png/kostur_icon.png",   # ground / backpack icon
      "anim":            617,                  # RECYCLE a working body
      "layer":       2,
      "weight":      4,
      "flags":       ["Wearable", "Weapon", "ArticleA"],
      "mobtype":     "EQUIPMENT"
      # no gump_* and no anim_copy_from needed when recycling: the item
      # borrows body 617's paperdoll gump automatically.
    }
  ]
}

To instead give the item its OWN paperdoll art, supply gump_male/gump_female
AND point "anim" at a free id - but be aware the worn animation then needs a
body that renders, which on this client means recycling anyway.

Every field except name/item_id is optional; omit what you do not need.

USAGE:
    python uopatch.py --client "C:/Nelderim/Nelderim" --recipe robes.json --plan
    python uopatch.py --client "C:/Nelderim/Nelderim" --recipe robes.json \
                      --out patched --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys

try:
    from PIL import Image
except ImportError:
    Image = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from uop_probe import read_uop_hashes, uop_hash
except ImportError:
    read_uop_hashes = uop_hash = None

try:
    from nelderim_core import load_gumpdef_ids, load_artdef_ids
except ImportError:
    load_gumpdef_ids = load_artdef_ids = None

IDX_REC = 12
ART_STATIC_BASE = 0x4000
GUMP_MALE_BASE = 50000
GUMP_FEMALE_BASE = 60000

# tiledata (post-7.0.9 "new" format, confirmed against this client)
TD_LAND_BLOCKS = 512
TD_LAND_ENTRY = 30
TD_STATIC_ENTRY = 41
TD_STATIC_PER_BLOCK = 32

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


# ---------------------------------------------------------------------------
# Colour conversion. UO uses 16-bit ARGB1555.
# ---------------------------------------------------------------------------

def rgb_to_1555(r, g, b, a=255):
    if a < 128:
        return 0
    v = 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    return v if v != 0 else 0x8000  # never emit 0 for a visible pixel


def load_png(path):
    if Image is None:
        raise Problem("Pillow is not installed: pip install Pillow")
    if not os.path.exists(path):
        raise Problem(f"image not found: {path}")
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    grid = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            grid[y][x] = rgb_to_1555(r, g, b, a)
    return w, h, grid


# ---------------------------------------------------------------------------
# Codecs. Verified by round-trip against this client's real data:
#   gump  - byte-exact on 7/7 samples
#   art   - decode(encode(px)) == px on all samples (encoder is 2 bytes/row
#           tighter than OSI's, which is valid but not byte-identical, so this
#           tool never re-encodes existing art - only new images)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# idx/mul container. Rebuilt by streaming: unchanged entries are copied as raw
# bytes, so data this tool was not asked to touch cannot be altered.
# ---------------------------------------------------------------------------

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


class AnimIdx:
    """anim.idx only. Linking an animation = pointing a new slot at the frames
    an existing slot already uses. No pixel data is copied, which is exactly
    what MulPatcher's 'Copy existing Animation' does."""

    def __init__(self, path, mobtypes):
        self.path = path
        self.idx = bytearray(open(path, "rb").read())
        self.count = len(self.idx) // IDX_REC
        self.mob = mobtypes
        self.offsets = self._build()

    GROUP = {"MONSTER": 22, "SEA_MONSTER": 22, "HUMAN": 35,
             "EQUIPMENT": 35, "ANIMAL": 13}
    DIRS = 5

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
        ss, sn = self.span(src_body)
        ds, dn = self.span(dst_body)
        if sn != dn:
            raise Problem(
                f"anim {src_body} and {dst_body} have different action counts "
                f"({sn} vs {dn}); give them the same mobtype first")
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
            # byte and shifts the name by one character.
            raw = name.encode("latin-1", "ignore")[:20]
            self.data[o + 21:o + 41] = raw + b"\x00" * (20 - len(raw))

    def write(self, path):
        open(path, "wb").write(bytes(self.data))


def load_mobtypes(path):
    d = {}
    for line in open(path, encoding="latin-1"):
        s = line.split("#")[0].strip()
        if not s:
            continue
        p = s.split()
        if len(p) < 3:
            continue
        try:
            d[int(p[0])] = p[1].upper()
        except ValueError:
            pass
    return d


def as_int(v):
    if isinstance(v, int):
        return v
    v = str(v).strip()
    return int(v, 16) if v.lower().startswith("0x") else int(v)


# ---------------------------------------------------------------------------
# Backups + manifest. Learned the hard way: overwriting a live slot with no
# backup means a botched test can only be undone by hand-copying from a clean
# client. Every overwrite now snapshots the original bytes first.
# ---------------------------------------------------------------------------

MANIFEST_NAME = "Nelderim_manifest.json"


def backup_client_files(client, out, names):
    """Copy the *current live* versions of the given files into out/backup/
    with a timestamp, before we generate replacements. Non-fatal if a file is
    missing (e.g. first run). Returns the backup dir, or None if nothing saved."""
    import time
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
    every file we just wrote. Carries forward any existing manifest entries so
    the launcher's overwrite-guard sees a complete picture. This does not touch
    the live client copy; you copy the manifest across with the .mul files."""
    manifest = {"version": 1, "files": {}}
    existing = find(client, MANIFEST_NAME)
    if existing and os.path.exists(existing):
        try:
            old = json.load(open(existing, encoding="utf-8"))
            if isinstance(old, dict):
                manifest["version"] = old.get("version", 1)
                manifest["files"] = dict(old.get("files", {}))
        except (ValueError, OSError):
            pass  # corrupt/old format: start clean rather than crash
    manifest["version"] = int(manifest["version"]) + 1
    for w in written:
        p = os.path.join(out, w)
        manifest["files"][w] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    dst = os.path.join(out, MANIFEST_NAME)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return dst, manifest["version"]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(client, recipe, out, apply_changes, allow_link=False):
    log = []

    def say(kind, msg):
        log.append((kind, msg))
        print(f"[{kind:5}] {msg}")

    items = recipe.get("items", [])
    if not items:
        raise Problem("recipe has no 'items'")

    base = os.path.dirname(os.path.abspath(recipe.get("__path__", ".")))

    mob = load_mobtypes(need(client, "mobtypes.txt"))
    td = TileData(need(client, "tiledata.mul"))
    art = MulPair(need(client, "artidx.mul"), need(client, "art.mul"))
    gump = MulPair(need(client, "Gumpidx.mul"), need(client, "Gumpart.mul"))
    anim = AnimIdx(need(client, "anim.idx"), mob)

    uop_hashes = None
    up = find(client, "gumpartLegacyMUL.uop")
    if up and read_uop_hashes:
        uop_hashes = read_uop_hashes(up)

    gumpdef_ids, artdef_ids = None, None
    gd = find(client, "gump.def")
    if gd and load_gumpdef_ids:
        gumpdef_ids = load_gumpdef_ids(gd)
    ad = find(client, "art.def")
    if ad and load_artdef_ids:
        artdef_ids = load_artdef_ids(ad)

    mob_add, bodydef_add = [], []
    touched = {"art": False, "gump": False, "anim": False, "tiledata": False}

    for it in items:
        name = it.get("name", "?")
        iid = as_int(it["item_id"])
        say("ITEM", f"{name}  id=0x{iid:04X} ({iid})")

        # --- static art -------------------------------------------------
        if it.get("art"):
            slot = ART_STATIC_BASE + iid
            if artdef_ids and iid in artdef_ids:
                say("WARN", f"  art id {iid} is redirected by art.def - "
                            "the client may show art.def's target instead "
                            "of what's about to be written. Check in-game.")
            if art.occupied(slot) and not it.get("overwrite"):
                say("ERROR", f"  art slot {slot} already used; "
                             f"set \"overwrite\": true to replace")
            else:
                w, h, px = load_png(os.path.join(base, it["art"]))
                if w > 1024 or h > 1024:
                    say("ERROR", f"  art {w}x{h} is implausibly large")
                else:
                    art.stage(slot, encode_art(w, h, px), 0)
                    touched["art"] = True
                    say("ok", f"  art  slot {slot}  {w}x{h}")

        # --- paperdoll gumps --------------------------------------------
        aid = it.get("anim")
        for key, gbase, label in (("gump_male", GUMP_MALE_BASE, "M"),
                                  ("gump_female", GUMP_FEMALE_BASE, "F")):
            if not it.get(key):
                continue
            if aid is None:
                say("ERROR", f"  {key} given but no \"anim\"; "
                             "the gump slot is derived from the anim id")
                continue
            gid = aid + gbase
            if uop_hashes is not None and uop_hash is not None:
                h_ = uop_hash(f"build/gumpartlegacymul/{gid:08d}.tga")
                if h_ in uop_hashes:
                    say("WARN", f"  gump {gid} ({label}) already exists in "
                                "gumpartLegacyMUL.uop - ClassicUO prefers UOP, "
                                "so this MUL write will be IGNORED. Pick a "
                                "different anim id, or patch the UOP too.")
            if gumpdef_ids and gid in gumpdef_ids:
                say("WARN", f"  gump {gid} ({label}) is redirected by "
                            "gump.def - the client may show gump.def's "
                            "target instead of what's about to be written. "
                            "Check in-game.")
            if gump.occupied(gid) and not it.get("overwrite"):
                say("ERROR", f"  gump slot {gid} ({label}) already used; "
                             "set \"overwrite\": true to replace")
                continue
            w, h, px = load_png(os.path.join(base, it[key]))
            gump.stage(gid, encode_gump(w, h, px), (w << 16) | h)
            touched["gump"] = True
            say("ok", f"  gump {gid} ({label})  {w}x{h}")

        if it.get("gump_male") and it.get("gump_female"):
            a = os.path.join(base, it["gump_male"])
            b = os.path.join(base, it["gump_female"])
            if (os.path.exists(a) and os.path.exists(b)
                    and hashlib.md5(open(a, "rb").read()).hexdigest()
                    == hashlib.md5(open(b, "rb").read()).hexdigest()):
                say("WARN", "  male and female gump images are identical; "
                            "female characters will get the male paperdoll")

        # --- animation -----------------------------------------------------
        # Two strategies:
        #
        #  A) RECYCLE (default, proven): "anim" points straight at an existing,
        #     already-working body (e.g. 617 = black staff). Nothing is written
        #     to anim.idx at all - the item just shares that body's frames and,
        #     because the paperdoll gump is derived from the anim id, it also
        #     shares the gump. This is what actually renders in-game.
        #
        #  B) LINK (opt-in, unreliable): "anim_copy_from" copies an existing
        #     body's anim.idx records into a NEW slot. Verified byte-identical
        #     on disk yet the client still would not render the linked slot in
        #     testing, so it is gated behind --allow-link and never the default.
        src = it.get("anim_copy_from")
        if aid is not None and src is not None:
            if not allow_link:
                say("WARN", f"  \"anim_copy_from\": {src} ignored. Linking a new "
                            "anim slot is unreliable (the client may refuse to "
                            "render it even when the bytes are correct). The "
                            f"item will RECYCLE body {aid} directly instead. To "
                            "force the old link behaviour, pass --allow-link.")
                if not anim.populated(aid):
                    say("WARN", f"  note: body {aid} has no frames of its own; "
                                "for recycling, set \"anim\" to a body that "
                                "already works in-game (e.g. 617 = black staff).")
            elif anim.populated(aid) and not it.get("overwrite"):
                say("ERROR", f"  anim slot {aid} already has frames; "
                             "set \"overwrite\": true to replace")
            elif not anim.populated(src):
                say("ERROR", f"  source anim {src} has no frames in anim.mul; "
                             "nothing to link to")
            else:
                n = anim.link(aid, src)
                touched["anim"] = True
                say("ok", f"  anim {aid} -> LINKED to {src} ({n} frame slots) "
                          "[--allow-link: unreliable, verify in-game]")
        elif aid is not None:
            # Pure recycle path. Confirm the body actually has frames so the
            # user is not silently pointing at an empty slot.
            if anim.populated(aid):
                say("ok", f"  anim {aid} recycled (shares frames + gump of an "
                          "existing body)")
            else:
                say("WARN", f"  anim {aid} has no frames in anim.mul and is not "
                            "being linked; the item may be invisible when worn. "
                            "Point \"anim\" at a working body id.")

        # --- tiledata ----------------------------------------------------
        flags = 0
        for f in it.get("flags", ["Wearable"]):
            if f not in FLAG_BITS:
                say("ERROR", f"  unknown flag {f!r}")
            flags |= FLAG_BITS.get(f, 0)
        td.update(iid, flags=flags, weight=it.get("weight", 1),
                  layer=it.get("layer"), anim=aid,
                  height=it.get("height", 1),
                  name=it.get("tile_name", name).lower())
        touched["tiledata"] = True
        say("ok", f"  tiledata layer={it.get('layer')} anim={aid} "
                  f"flags=0x{flags:X}")

        # --- def-file additions -------------------------------------------
        if it.get("mobtype") and aid is not None:
            if aid in mob and mob[aid] != it["mobtype"]:
                say("WARN", f"  mobtypes already lists {aid} as {mob[aid]}, "
                            f"recipe says {it['mobtype']}")
            elif aid not in mob:
                mob_add.append((aid, it["mobtype"], name))
        if it.get("body_def") and aid is not None:
            bodydef_add.append((aid, as_int(it["body_def"]), name))

    if not apply_changes:
        say("PLAN", "dry run - nothing written. Re-run with --apply to write.")
        return log, None

    # -----------------------------------------------------------------
    os.makedirs(out, exist_ok=True)
    written = []

    # Snapshot the live versions of every file we are about to regenerate,
    # so a bad patch can always be rolled back from out/backup/<timestamp>/.
    to_backup = []
    if touched["art"]:
        to_backup += ["artidx.mul", "art.mul"]
    if touched["gump"]:
        to_backup += ["Gumpidx.mul", "Gumpart.mul"]
    if touched["anim"]:
        to_backup += ["anim.idx"]
    if touched["tiledata"]:
        to_backup += ["tiledata.mul"]
    if mob_add:
        to_backup += ["mobtypes.txt"]
    if bodydef_add:
        to_backup += ["body.def"]
    bdir = backup_client_files(client, out, to_backup)
    if bdir:
        say("BACKUP", f"live originals saved to {bdir}")

    if touched["art"]:
        art.write(os.path.join(out, "artidx.mul"), os.path.join(out, "art.mul"))
        written += ["artidx.mul", "art.mul"]
    if touched["gump"]:
        gump.write(os.path.join(out, "Gumpidx.mul"),
                   os.path.join(out, "Gumpart.mul"))
        written += ["Gumpidx.mul", "Gumpart.mul"]
    if touched["anim"]:
        anim.write(os.path.join(out, "anim.idx"))
        written += ["anim.idx"]
    if touched["tiledata"]:
        td.write(os.path.join(out, "tiledata.mul"))
        written += ["tiledata.mul"]

    if mob_add:
        src = need(client, "mobtypes.txt")
        dst = os.path.join(out, "mobtypes.txt")
        shutil.copyfile(src, dst)
        with open(dst, "a", encoding="latin-1", newline="\r\n") as f:
            f.write("\r\n# --- added by uopatch.py ---\r\n")
            for aid, t, nm in mob_add:
                f.write(f"{aid}\t{t}\t0\t# {nm}\r\n")
        written.append("mobtypes.txt")
    if bodydef_add:
        src = need(client, "body.def")
        dst = os.path.join(out, "body.def")
        shutil.copyfile(src, dst)
        with open(dst, "a", encoding="latin-1", newline="\r\n") as f:
            f.write("\r\n# --- added by uopatch.py ---\r\n")
            for aid, tgt, nm in bodydef_add:
                f.write(f"{aid}\t{{{tgt}}}\t0\t# {nm}\r\n")
        written.append("body.def")

    # ---- verification pass -------------------------------------------
    say("VERIFY", "re-reading output files")
    ok = True
    if touched["art"]:
        v = MulPair(os.path.join(out, "artidx.mul"),
                    os.path.join(out, "art.mul"))
        for i, (data, _) in art.new.items():
            r = v.raw(i)
            if r is None or r[0] != data:
                say("ERROR", f"  art slot {i} did not survive the write")
                ok = False
    if touched["gump"]:
        v = MulPair(os.path.join(out, "Gumpidx.mul"),
                    os.path.join(out, "Gumpart.mul"))
        for i, (data, extra) in gump.new.items():
            r = v.raw(i)
            if r is None or r[0] != data or r[1] != extra:
                say("ERROR", f"  gump slot {i} did not survive the write")
                ok = False
    if touched["tiledata"]:
        v = TileData(os.path.join(out, "tiledata.mul"))
        for it in items:
            iid = as_int(it["item_id"])
            t = v.read(iid)
            if it.get("layer") is not None and t["layer"] != it["layer"]:
                say("ERROR", f"  tiledata {iid} layer mismatch")
                ok = False
            want = it.get("tile_name", it.get("name", "")).lower()[:20]
            if t["name"] != want.rstrip("\x00"):
                say("ERROR", f"  tiledata {iid} name is {t['name']!r}, "
                             f"expected {want!r}")
                ok = False
    say("VERIFY", "all checks passed" if ok else "FAILURES - do not ship")

    print("\n--- SHA1 of written files ---")
    for w in written:
        p = os.path.join(out, w)
        print(f"  {hashlib.sha1(open(p,'rb').read()).hexdigest()}  {w}")

    if written:
        mpath, mver = update_manifest(client, out, written)
        say("MANIFEST", f"wrote {os.path.basename(mpath)} (version {mver}) - "
                        "copy it across with the .mul files so the launcher "
                        "guard sees the new hashes")

    print(f"\nWritten to {out}. Your live client folder was NOT modified.")
    if written:
        print("Deploy:  copy the listed files (and " + MANIFEST_NAME +
              ") into\n         " + os.path.abspath(client) +
              "\n         then restart the SERVER and the client.")
    return log, written


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

def animframe_uop_bodies(client):
    """Bodies present in AnimationFrame*.uop (any group)."""
    if uop_hash is None or read_uop_hashes is None:
        return set()
    out = set()
    import glob
    for p in glob.glob(os.path.join(client, "AnimationFrame*.uop")):
        hs = read_uop_hashes(p)
        for body in range(2048):
            for g in range(5):
                if uop_hash(f"build/animationlegacyframe/{body:06d}/{g:02d}.bin") in hs:
                    out.add(body)
                    break
    return out

def find_free(client, lo, hi, count):
    """Anim ids that are free on EVERY axis that matters:
    empty in anim.mul, both gump slots free in Gumpidx, and absent from
    gumpartLegacyMUL.uop (because UOP silently beats MUL)."""
    mob = load_mobtypes(need(client, "mobtypes.txt"))
    anim = AnimIdx(need(client, "anim.idx"), mob)
    gi = open(need(client, "Gumpidx.mul"), "rb").read()
    gn = len(gi) // IDX_REC
    hs = None
    up = find(client, "gumpartLegacyMUL.uop")
    if up and read_uop_hashes:
        hs = read_uop_hashes(up)
    bodyconv_bodies = set()
    bc = find(client, "Bodyconv.def")
    if bc:
        bodyconv_bodies = load_bodyconv_bodies(bc)
    animframe_bodies = animframe_uop_bodies(client)

    def gump_free(g):
        if g >= gn:
            return True
        return struct.unpack_from("<i", gi, g * IDX_REC)[0] == -1

    def uop_free(g):
        if hs is None or uop_hash is None:
            return True
        return uop_hash(f"build/gumpartlegacymul/{g:08d}.tga") not in hs

    out = []
    for a in range(lo, hi):
        if len(out) >= count:
            break
        if (not anim.populated(a)
                and a not in bodyconv_bodies
                and a not in animframe_bodies
                and gump_free(a + GUMP_MALE_BASE)
                and gump_free(a + GUMP_FEMALE_BASE)
                and uop_free(a + GUMP_MALE_BASE)
                and uop_free(a + GUMP_FEMALE_BASE)):
            out.append(a)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="live client folder (read only)")
    ap.add_argument("--recipe", help="JSON recipe")
    ap.add_argument("--free", action="store_true",
                    help="list anim ids free in anim.mul, Gumpidx AND the UOP")
    ap.add_argument("--range", default="400-1000", help="band for --free")
    ap.add_argument("--count", type=int, default=25, help="how many to list")
    ap.add_argument("--out", default="patched", help="output folder")
    ap.add_argument("--plan", action="store_true", help="dry run (default)")
    ap.add_argument("--apply", action="store_true", help="actually write")
    ap.add_argument("--allow-link", action="store_true",
                    help="permit the old anim_copy_from linking behaviour "
                         "(unreliable; the client may refuse to render a "
                         "linked slot). Default: recycle the anim id directly.")
    a = ap.parse_args()

    if a.free:
        lo, _, hi = a.range.partition("-")
        try:
            ids = find_free(a.client, int(lo), int(hi), a.count)
        except Problem as e:
            print(f"[ERROR] {e}")
            return 2
        print(f"Free anim ids in {a.range} "
              f"(anim.mul empty + both gump slots free + absent from UOP):")
        print("  " + ", ".join(str(i) for i in ids))
        print(f"\nFor anim id N the gump slots are N+{GUMP_MALE_BASE} (male) "
              f"and N+{GUMP_FEMALE_BASE} (female).")
        return 0

    if not a.recipe:
        print("[ERROR] need --recipe (or --free)")
        return 2
    recipe = json.load(open(a.recipe, encoding="utf-8"))
    recipe["__path__"] = a.recipe
    try:
        log, _ = run(a.client, recipe, a.out, a.apply and not a.plan,
                     allow_link=a.allow_link)
    except Problem as e:
        print(f"[ERROR] {e}")
        return 2
    return 1 if any(k == "ERROR" for k, _ in log) else 0


if __name__ == "__main__":
    sys.exit(main())
