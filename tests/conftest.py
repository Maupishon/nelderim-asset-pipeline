"""Shared fixtures: a tiny synthetic UO client (no game art) built in a temp folder."""
import os, shutil, struct, sys, zlib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "lab", ROOT / "pipeline"):
    sys.path.insert(0, str(p))

import nelderim_core as C  # noqa: E402


def group_block(color=0x7C00, w=4, h=6):
    """one UO animation group (palette + 1 frame, solid w x h rectangle, anchor 0,0) - the layout of anim*.mul
    records and .vd blocks (decoded by uo3d.vdread.decode_group)."""
    pal = [0] * 256
    pal[1] = color
    frame = bytearray(struct.pack("<hhHH", 0, 0, w, h))
    for row in range(h):
        X, Y = 0x200, row + 0x200 - h                                  # x = 0, y = row (see vdread.decode_group)
        frame += struct.pack("<I", ((X << 22) | (Y << 12) | w) ^ ((0x200 << 22) | (0x200 << 12)))
        frame += bytes([1]) * w
    frame += struct.pack("<I", 0x7FFF7FFF)
    return struct.pack("<256H", *pal) + struct.pack("<i", 1) + struct.pack("<i", 8) + bytes(frame)   # frame offset: from the count field


def myp(path, entries):
    """minimal MYP (.uop) container: entries = [(hash, payload, flag)]."""
    data, recs, base = b"", [], 28
    for h, pl, fl in entries:
        recs.append((base + len(data), 0, len(pl), len(pl), h, 0, fl)); data += pl
    tbl = base + len(data)
    out = b"MYP\x00" + struct.pack("<II q i i", 5, 0xFD23EC43, tbl, len(entries), len(entries)) + data
    out += struct.pack("<i q", len(entries), 0) + b"".join(struct.pack("<q i i i Q I h", *r) for r in recs)
    Path(path).write_bytes(out)


@pytest.fixture
def client(tmp_path):
    """client copy: real .def files from client-config, anim5 with slots 15 (wired), 32 (high), 211 (low),
    UOP frames for body 32 at action group 22 and AnimationSequence.uop listing animation 1975."""
    cl = tmp_path / "client"
    cl.mkdir()
    for f in ("Bodyconv.def", "mobtypes.txt", "body.def", "Equipconv.def"):
        shutil.copy(ROOT / "client-config" / f, cl / f)
    blk = group_block()
    recs, mul = {}, bytearray()

    def put(slot, start, nrec, actions):
        for a in range(actions):
            for d in range(5):
                recs[start + a * 5 + d] = (len(mul), len(blk)); mul.extend(blk)
    put(15, 15 * 110, 110, 3)
    put(32, 32 * 110, 110, 22)
    put(211, 22000 + 11 * 65, 65, 13)
    n = max(recs) + 1
    (cl / "anim5.idx").write_bytes(b"".join(struct.pack("<iii", *recs.get(i, (-1, -1)), 0) for i in range(n)))
    (cl / "anim5.mul").write_bytes(bytes(mul))
    (cl / "anim.idx").write_bytes(struct.pack("<iii", -1, -1, 0) * 3000)
    (cl / "anim.mul").write_bytes(b"\0" * 16)
    myp(cl / "AnimationFrame1.uop", [(C.uop_hash(C.animframe_path(32, 22)), b"x" * 8, 0)])
    myp(cl / "AnimationSequence.uop", [(123, zlib.compress(struct.pack("<I", 1975) + b"\0" * 16), 1)])
    return cl
