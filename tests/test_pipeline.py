"""Client tools on a synthetic client: anim_wire, UOP collision checks, vd_inject."""
import struct, subprocess, sys
from pathlib import Path

import nelderim_core as C
import anim_wire as A

ROOT = Path(__file__).resolve().parent.parent


def test_uop_check_sees_late_action_groups(client):
    # body 32 has UOP data only in action group 22 - the old 0..4 probe missed it (UOP dragon in game)
    assert 32 in C.animframe_uop_bodies(str(client), 0, 100)
    u = A.UopIndex(str(client))
    assert u.frame_groups(32) == [22]
    assert 1975 in u.sequence and u.used(1975)
    assert not u.used(31)


def test_anim_wire_plan_skips_uop_bodies(client):
    found, rows = A.plan(str(client), 5)
    slots = {r["slot"]: r for r in rows}
    assert 15 not in slots                                   # already wired in Bodyconv.def (256 -> 15)
    assert slots[32]["type"] == "MONSTER" and slots[32]["actions"] == 22
    assert slots[211]["type"] == "ANIMAL" and slots[211]["actions"] == 13
    taken = {r["body"] for r in rows}
    assert 32 not in taken and 1975 not in taken and 0 not in taken
    assert len(taken) == len(rows)                           # never the same body twice


def test_anim_wire_apply_writes_and_verifies(client, tmp_path):
    _, rows = A.plan(str(client), 5, slots={32}, names={32: "Wilkołak żółty"})
    out = tmp_path / "out"
    A.apply_plan(str(client), 5, rows, str(out))
    body = rows[0]["body"]
    bc = (out / "Bodyconv.def").read_text(encoding="latin-1")
    mob = (out / "mobtypes.txt").read_text(encoding="latin-1")
    assert f"{body}\t-1\t-1\t-1\t32\t-1\t# anim5 slot 32 - Wilkolak zolty" in bc
    assert f"{body}\tMONSTER\t0\t# anim5 slot 32 - Wilkolak zolty" in mob
    assert (out / "Nelderim_manifest.json").is_file()
    assert any((out / "backup").iterdir())
    assert A.check_body(str(client), 32)                     # UOP reason reported
    assert body in A.bodyconv_refs(str(out / "Bodyconv.def"))[5][32]


def test_vd_inject_round_trip(client, tmp_path):
    # monster .vd (fileType 6 + 110 records) taken from anim5 slot 32
    idx = (client / "anim5.idx").read_bytes(); mul = (client / "anim5.mul").read_bytes()
    recs, data, base = [], b"", 4 + 110 * 12
    for i in range(110):
        lk, ln, _ = struct.unpack_from("<iii", idx, (32 * 110 + i) * 12)
        recs.append((base + len(data), ln, 0)); data += mul[lk:lk + ln]
    vd = tmp_path / "m.vd"
    vd.write_bytes(struct.pack("<i", 6) + b"".join(struct.pack("<iii", *r) for r in recs) + data)
    out = tmp_path / "vi"
    r = subprocess.run([sys.executable, str(ROOT / "pipeline" / "vd_inject.py"), "--client", str(client), "--vd", str(vd),
                        "--out", str(out), "--apply"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout
    assert "MONSTER" in (out / "mobtypes.txt").read_text(encoding="latin-1")


def test_cli_entry_points():
    for tool in ("search", "patch", "inject", "wire", "uo3d", "vd2glb"):
        r = subprocess.run([sys.executable, str(ROOT / "nelderim.py"), tool, "--help"], capture_output=True, text=True)
        assert r.returncode == 0, (tool, r.stderr[-400:])
    r = subprocess.run([sys.executable, str(ROOT / "nelderim.py"), "nope"], capture_output=True, text=True)
    assert r.returncode == 2
