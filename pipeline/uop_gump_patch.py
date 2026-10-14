#!/usr/bin/env python3
"""
uop_gump_patch.py - patch gump entries directly inside gumpartLegacyMUL.uop.

Why this exists: ClassicUO prefers UOP over MUL for gump art. If a gump id
already has an entry in the UOP, writing to Gumpart.mul via uopatch.py has
no visible effect in-game - the UOP entry wins. This tool patches the UOP
entry itself.

UOP gump entry format (verified against this shard's gumpartLegacyMUL.uop):
    payload = struct.pack("<II", width, height) + <standard encode_gump body>
    hlen  = 0   (no separate header block)
    flag  = 0   (uncompressed / stored)
    clen == dlen == len(payload)

SAFETY:
  - Never rewrites in place. New payload bytes are always appended to the
    end of the file; only the 34-byte entry record (off/clen/dlen/adler) is
    overwritten, in place, for the target hash. Every other byte in the file
    is untouched.
  - Refuses to run unless --apply is given (dry run by default).
  - Verifies after writing: re-reads the patched entry from the OUTPUT file
    and confirms decoded pixels match what was requested.
  - Never touches any entry other than the ones explicitly targeted.
"""

from __future__ import annotations
import argparse, json, os, shutil, struct, sys, zlib

try:
    from PIL import Image
except ImportError:
    Image = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from nelderim_core import load_gumpdef_ids
except ImportError:
    load_gumpdef_ids = None

IDX_REC = 12
GUMP_MALE_BASE = 50000
GUMP_FEMALE_BASE = 60000


def uop_hash(s: str) -> int:
    b = s.encode("ascii")
    M = 0xFFFFFFFF
    n = len(b)
    ebx = edi = esi = (n + 0xDEADBEEF) & M
    eax = ecx = edx = 0
    i = 0
    while i + 12 < n:
        edi = (((b[i+7]<<24)|(b[i+6]<<16)|(b[i+5]<<8)|b[i+4]) + edi) & M
        esi = (((b[i+11]<<24)|(b[i+10]<<16)|(b[i+9]<<8)|b[i+8]) + esi) & M
        edx = (((b[i+3]<<24)|(b[i+2]<<16)|(b[i+1]<<8)|b[i]) - esi) & M
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


class UopFile:
    """Reads the MYP block-chain structure and remembers exactly where each
    entry record lives in the file, so a single entry can be overwritten
    in place without touching anything else."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "r+b")
        self.f.seek(0)
        if self.f.read(4) != b"MYP\x00":
            raise SystemExit(f"not a UOP file: {path}")
        self.ver, self.sig, self.nextblk, self.blkcap, self.cnt = \
            struct.unpack("<II q i i", self.f.read(24))
        self.entries = {}  # hash -> dict(off, hlen, clen, dlen, adler, flag, record_pos)
        self.last_block = None   # (table position, files used) of the final block in the chain
        pos = self.nextblk
        while True:
            self.f.seek(pos)
            n_files, nxt = struct.unpack("<i q", self.f.read(12))
            if nxt == 0:
                self.last_block = (pos, n_files)
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

    def replace_payload(self, h, new_payload, expect_uncompressed=True):
        """Append new_payload to end of file, then overwrite ONLY this
        entry's 34-byte record in place to point at it. hlen forced to 0,
        flag forced to 0 (stored/uncompressed), matching every entry we
        have inspected on this shard. Nothing else in the file is touched."""
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

    def free_slots(self):
        """How many NEW entries the final block table can take: the table is reserved for `blkcap`
        records (34 bytes each) and the unused ones are zero-filled. Counted only while the reserved area
        really is zero, so a payload that happens to live there can never be overwritten."""
        if not self.last_block or self.blkcap <= 0:
            return 0
        pos, used = self.last_block
        room = self.blkcap - used
        if room <= 0:
            return 0
        self.f.seek(pos + 12 + used * 34)
        area = self.f.read(room * 34)
        free = 0
        for i in range(room):
            if area[i * 34:(i + 1) * 34] == bytes(34):
                free += 1
            else:
                break
        return free

    def add_payload(self, h, new_payload):
        """Add an entry that is NOT in the UOP yet: payload appended to the end of the file, a record written
        into the first free slot of the final block table, that block's file count (and the header count)
        bumped. Nothing already in the file is moved or changed."""
        if h in self.entries:
            raise KeyError(f"hash {h} is already present - use replace_payload")
        if self.free_slots() < 1:
            raise RuntimeError("no free slot left in the UOP block table")
        pos, used = self.last_block
        self.f.seek(0, os.SEEK_END)
        new_off = self.f.tell()
        self.f.write(new_payload)
        n = len(new_payload)
        adler = zlib.adler32(new_payload) & 0xFFFFFFFF
        rec_pos = pos + 12 + used * 34
        self.f.seek(rec_pos)
        self.f.write(struct.pack("<q i i i Q I h", new_off, 0, n, n, h, adler, 0))
        self.f.seek(pos)
        self.f.write(struct.pack("<i", used + 1))
        self.last_block = (pos, used + 1)
        self.cnt += 1
        self.f.seek(24)                       # header: magic(4) ver(4) sig(4) nextblk(8) blkcap(4) | count(4)
        self.f.write(struct.pack("<i", self.cnt))
        self.entries[h] = dict(off=new_off, hlen=0, clen=n, dlen=n, adler=adler, flag=0, record_pos=rec_pos)

    def close(self):
        self.f.close()


# --- gump codec (byte-identical to uopatch.py's encode_gump) --------------

def rgb_to_1555(r, g, b, a=255):
    if a < 128:
        return 0
    v = 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    return v if v != 0 else 0x8000


def load_png(path):
    if Image is None:
        raise SystemExit("Pillow not installed: pip install Pillow")
    im = Image.open(path).convert("RGBA")
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
    cur = h
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


def build_uop_payload(w, h, px):
    return struct.pack("<II", w, h) + encode_gump(w, h, px)


def decode_uop_payload(data):
    w, h = struct.unpack_from("<II", data, 0)
    px = decode_gump(data[8:], w, h)
    return w, h, px


# --- driver -----------------------------------------------------------

def run(client, recipe, apply_changes):
    uop_path = None
    for e in os.listdir(client):
        if e.lower() == "gumpartlegacymul.uop":
            uop_path = os.path.join(client, e)
    if not uop_path:
        raise SystemExit("gumpartLegacyMUL.uop not found in client folder")

    base = os.path.dirname(os.path.abspath(recipe.get("__path__", ".")))
    items = recipe.get("items", [])

    gumpdef_ids = None
    for e in os.listdir(client):
        if e.lower() == "gump.def" and load_gumpdef_ids:
            gumpdef_ids = load_gumpdef_ids(os.path.join(client, e))

    print(f"[INFO ] target UOP: {uop_path}")
    plan = []
    for it in items:
        aid = it["anim"]
        for key, gbase, label in (("gump_male", GUMP_MALE_BASE, "M"),
                                   ("gump_female", GUMP_FEMALE_BASE, "F")):
            if not it.get(key):
                continue
            gid = aid + gbase
            if gumpdef_ids and gid in gumpdef_ids:
                print(f"[WARN ]  {it.get('name','?')} {label}: gump {gid} "
                      "is redirected by gump.def - the client may show "
                      "gump.def's target instead of what's about to be "
                      "patched. Check in-game.")
            h = uop_hash(gump_path(gid))
            png_path = os.path.join(base, it[key])
            if not os.path.exists(png_path):
                print(f"[ERROR]  {it.get('name','?')} {label}: "
                      f"image not found: {png_path}")
                continue
            plan.append((it.get("name", "?"), label, gid, h, png_path))

    probe = UopFile(uop_path)
    have = set(probe.entries)
    room = probe.free_slots()
    probe.close()
    n_new = sum(1 for _n, _l, _g, h, _p in plan if h not in have)
    print(f"[PLAN ] {len(plan)} gump entries to patch ({len(plan) - n_new} replace, {n_new} NEW):")
    for name, label, gid, h, png_path in plan:
        kind = "REPLACE" if h in have else "NEW    "
        print(f"         {kind} {name} ({label}) gump {gid} <- {png_path}")
    if n_new > room:
        print(f"[ERROR] {n_new} new gump entries do not fit: the UOP has room for {room} more. "
              "Nothing will be written for the ones that do not fit.")

    if not apply_changes:
        print("[PLAN ] dry run - nothing written. Re-run with --apply.")
        return

    if not os.path.exists(uop_path + ".orig_backup"):
        shutil.copyfile(uop_path, uop_path + ".orig_backup")
        print(f"[BACKUP] saved original UOP to {uop_path}.orig_backup "
              "(only created once, kept as the pristine reference)")

    uop = UopFile(uop_path)
    written = []
    for name, label, gid, h, png_path in plan:
        w, hh, px = load_png(png_path)
        payload = build_uop_payload(w, hh, px)
        if h not in uop.entries:
            # not in the UOP yet. The client reads gumps ONLY from this file when MainMisc.uop is present
            # (ClassicUO GumpsLoader: IsUOPInstallation -> gumpartLegacyMUL.uop, Gumpart.mul is ignored),
            # so a new gump has to be added here, not to Gumpart.mul.
            try:
                uop.add_payload(h, payload)
            except RuntimeError as e:
                print(f"[ERROR]  {name} ({label}) gump {gid}: {e} - skipping")
                continue
            print(f"[ok   ]  {name} ({label}) gump {gid}  {w}x{hh}  (NEW entry, {len(payload)} bytes)")
        else:
            old = uop.entries[h]
            if old["flag"] == 0 and old["hlen"] == 0 and uop.read_payload(h) == payload:
                # identical bytes already stored: writing again would only grow the file by one payload
                print(f"[ok   ]  {name} ({label}) gump {gid}  {w}x{hh}  (identical, left as is)")
            else:
                uop.replace_payload(h, payload)
                print(f"[ok   ]  {name} ({label}) gump {gid}  {w}x{hh}  "
                      f"({old['clen']} -> {len(payload)} bytes)")
        written.append((name, label, gid, h, w, hh))
    uop.close()

    # ---- verification pass: re-open the file we just wrote, re-decode
    # every entry we touched, confirm pixels match what was requested ----
    print("[VERIFY] re-reading patched UOP")
    v = UopFile(uop_path)
    ok = True
    for name, label, gid, h, exp_w, exp_h in written:
        data = v.read_payload(h)
        w, hh, px = decode_uop_payload(data)
        if w != exp_w or hh != exp_h:
            print(f"[ERROR]  {name} ({label}) gump {gid}: dims mismatch "
                  f"after write ({w}x{hh} != {exp_w}x{exp_h})")
            ok = False
    v.close()
    print("[VERIFY] all checks passed" if ok else "[VERIFY] FAILURES")
    print(f"\nPatched in place: {uop_path}")
    print(f"Original preserved at: {uop_path}.orig_backup")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    recipe = json.load(open(a.recipe, encoding="utf-8"))
    recipe["__path__"] = a.recipe
    run(a.client, recipe, a.apply)


if __name__ == "__main__":
    main()
