"""anim_import: People .vd -> empty slot of anim5.mul + Bodyconv.def / mobtypes.txt, on the synthetic client."""
import struct
import pytest

import anim_import as I
import anim_wire as A
from conftest import group_block

PEOPLE_FIRST = 35000
N_SLOTS = 120                                   # People slots 400..519 exist in the synthetic anim5.idx


@pytest.fixture
def people_client(client):
    """client whose anim5.idx reaches into the People band; slot 450 holds data, nothing else does."""
    idx = bytearray((client / "anim5.idx").read_bytes())
    total = PEOPLE_FIRST + N_SLOTS * 175
    idx += struct.pack("<iii", -1, -1, 0) * (total - len(idx) // 12)
    mul = bytearray((client / "anim5.mul").read_bytes())
    blk = group_block(0x03E0)
    for k in range(175):
        struct.pack_into("<iii", idx, (PEOPLE_FIRST + 50 * 175 + k) * 12, len(mul), len(blk), 0)
        mul.extend(blk)
    (client / "anim5.idx").write_bytes(bytes(idx))
    (client / "anim5.mul").write_bytes(bytes(mul))
    return client


def make_vd(path, blocks=175, hdr=(2 << 16) | 6):
    data, recs, base = b"", [], 4 + 175 * 12
    for i in range(175):
        if i < blocks:
            blk = group_block(0x7C00 + i % 7)
            recs.append((base + len(data), len(blk), 0)); data += blk
        else:
            recs.append((-1, -1, 0))
    path.write_bytes(struct.pack("<i", hdr) + b"".join(struct.pack("<iii", *r) for r in recs) + data)
    return path


def test_dry_run_picks_clean_slot_and_writes_nothing(people_client, tmp_path):
    vd = make_vd(tmp_path / "r.vd")
    before = (people_client / "anim5.mul").read_bytes()
    r = I.run(str(people_client), str(vd), 5, None, None, "Szata", str(tmp_path / "out"), False)
    assert r["slot"] >= 432 and r["slot"] != 450            # skips the gargoyle band and the used slot
    assert r["body"] >= 400
    assert not (tmp_path / "out").exists()
    assert (people_client / "anim5.mul").read_bytes() == before


def test_apply_appends_blocks_and_wires(people_client, tmp_path):
    vd = make_vd(tmp_path / "r.vd")
    live = (people_client / "anim5.mul").read_bytes()
    out = tmp_path / "out"
    r = I.run(str(people_client), str(vd), 5, 470, None, "Szata alchemika", str(out), True)
    slot, body = r["slot"], r["body"]
    assert slot == 470
    mul, idx, d = (out / "anim5.mul").read_bytes(), (out / "anim5.idx").read_bytes(), vd.read_bytes()
    assert mul[:len(live)] == live                           # existing bytes never move
    assert len(mul) > len(live)
    start = PEOPLE_FIRST + (470 - 400) * 175
    for k in range(175):
        lk, ln, _ = struct.unpack_from("<iii", idx, (start + k) * 12)
        vl, vn, _ = struct.unpack_from("<iii", d, 4 + k * 12)
        assert lk >= len(live) and mul[lk:lk + ln] == d[vl:vl + vn]
    bc = (out / "Bodyconv.def").read_text(encoding="latin-1")
    mob = (out / "mobtypes.txt").read_text(encoding="latin-1")
    assert f"{body}\t-1\t-1\t-1\t470\t-1\t# anim5 slot 470 - Szata alchemika" in bc
    assert f"{body}\tHUMAN\t0" in mob
    assert body in A.bodyconv_refs(str(out / "Bodyconv.def"))[5][470]
    assert (out / "Nelderim_manifest.json").is_file() and any((out / "backup").iterdir())


def test_empty_directions_stay_empty(people_client, tmp_path):
    vd = make_vd(tmp_path / "r.vd", blocks=100)
    out = tmp_path / "out"
    r = I.run(str(people_client), str(vd), 5, 471, None, "", str(out), True)
    idx = (out / "anim5.idx").read_bytes()
    start = PEOPLE_FIRST + (471 - 400) * 175
    assert struct.unpack_from("<ii", idx, (start + 99) * 12)[1] > 0
    assert struct.unpack_from("<ii", idx, (start + 100) * 12) == (-1, -1)
    assert r["slot"] == 471


def test_refuses_used_slot_wired_slot_and_wrong_vd(people_client, tmp_path):
    vd = make_vd(tmp_path / "r.vd")
    with pytest.raises(I.Problem, match="ma już dane"):
        I.run(str(people_client), str(vd), 5, 450, None, "", str(tmp_path / "o"), False)
    wired = next(s for s in A.bodyconv_refs(str(people_client / "Bodyconv.def"))[5] if s >= 400)
    if wired - 400 < N_SLOTS:
        with pytest.raises(I.Problem, match="podpięty"):
            I.run(str(people_client), str(vd), 5, wired, None, "", str(tmp_path / "o"), False)
    bad = make_vd(tmp_path / "m.vd", hdr=(1 << 16) | 6)
    with pytest.raises(I.Problem, match="people"):
        I.run(str(people_client), str(bad), 5, None, None, "", str(tmp_path / "o"), False)


def test_refuses_taken_body(people_client, tmp_path):
    vd = make_vd(tmp_path / "r.vd")
    with pytest.raises(I.Problem, match="zajęte"):
        I.run(str(people_client), str(vd), 5, 470, 1975, "", str(tmp_path / "o"), False)   # 1975 is listed in AnimationSequence.uop
