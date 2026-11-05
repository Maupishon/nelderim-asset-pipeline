"""uop_gump_patch: a full final block table is extended with a new linked block table."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import uop_gump_patch as G  # noqa: E402
from conftest import myp  # noqa: E402


def test_full_block_table_is_extended_and_the_chain_is_readable(tmp_path):
    p = tmp_path / "g.uop"
    myp(p, [(G.uop_hash(G.gump_path(i)), b"x" * 8, 0) for i in (1, 2)])            # capacity 2, both used
    u = G.UopFile(str(p))
    assert u.free_slots() == 0
    h1, h2, h3 = (G.uop_hash(G.gump_path(i)) for i in (3, 4, 5))
    for h, pl in ((h1, b"aaaa"), (h2, b"bbbbbb"), (h3, b"cc")):                   # 3 new entries: one block of capacity 2 + one more extension
        u.add_payload(h, pl)
    u.close()
    v = G.UopFile(str(p))
    assert len(v.entries) == 5 and v.cnt == 5
    assert v.read_payload(h1) == b"aaaa" and v.read_payload(h2) == b"bbbbbb" and v.read_payload(h3) == b"cc"
    assert v.read_payload(G.uop_hash(G.gump_path(1))) == b"x" * 8                   # the old entries are untouched
    v.close()
