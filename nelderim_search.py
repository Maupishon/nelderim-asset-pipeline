#!/usr/bin/env python3
"""
nelderim_search.py - find existing art/gump/animation by id, name, or type.
Read-only: never writes anything. Built entirely on nelderim_core's already-
proven readers - no new binary parsing here, just querying.

Three lookup modes:

  --item QUERY   search tiledata.mul (all 2048*32 entries) by name substring
                 or exact item id (hex 0x.. or decimal). Reports layer,
                 anim, flags, weight, height for each match.

  --anim ID      full picture for one anim id: does it have a male/female
                 gump, and is that gump in Gumpart.mul or gumpartLegacyMUL.uop
                 (MUL vs UOP matters - see uop_gump_patch.py); which tiledata
                 entries point at this anim (candidates for recycling).

  --body ID      full picture for one body id: mobtypes.txt type, whether
                 body.def redirects it elsewhere, whether Bodyconv.def
                 claims it, whether AnimationFrame*.uop has it, and whether
                 anim.idx has data there under BOTH offset models (cumulative
                 "People" group and flat "High" group) since which one
                 applies depends on the resolved type.

Every answer states which file(s) it came from, so results can be checked
against the actual client rather than trusted blindly.
"""

from __future__ import annotations
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nelderim_core as core


# ===========================================================================
# --item : tiledata.mul search
# ===========================================================================

def _parse_id_query(q):
    q = q.strip()
    try:
        return int(q, 16) if q.lower().startswith("0x") else int(q)
    except ValueError:
        return None


def search_items(client, query, limit=50):
    td_path = core.need(client, "tiledata.mul")
    td = core.TileData(td_path)

    as_id = _parse_id_query(query)
    needle = query.strip().lower()

    hits = []
    for iid in range(2048 * 32):
        r = td.read(iid)
        if as_id is not None:
            if iid != as_id:
                continue
        else:
            if needle not in r["name"].lower():
                continue
        hits.append((iid, r))
        if len(hits) >= limit:
            break
    return hits


def print_item_hits(hits, query, limit):
    if not hits:
        print(f"no tiledata entries match '{query}'")
        return
    print(f"{len(hits)} match(es) for '{query}'"
          + (f" (showing first {limit})" if len(hits) == limit else "") + ":")
    for iid, r in hits:
        flags_on = [n for n, bit in core.FLAG_BITS.items() if r["flags"] & bit]
        print(f"  0x{iid:04X} ({iid:5d})  \"{r['name']}\"  "
              f"layer={r['layer']} anim={r['anim']} height={r['height']}  "
              f"flags={','.join(flags_on) or '-'}")


# ===========================================================================
# --anim : gump + tiledata cross-reference for one anim id
# ===========================================================================

def describe_anim(client, aid):
    out = {"anim": aid}

    # gump presence: MUL side
    gumpidx = core.find(client, "Gumpidx.mul")
    mul_male = mul_female = False
    if gumpidx:
        idx = open(gumpidx, "rb").read()
        n = len(idx) // core.IDX_REC

        def occ(gid):
            if gid >= n:
                return False
            lk = struct.unpack_from("<i", idx, gid * core.IDX_REC)[0]
            return lk != -1

        mul_male = occ(aid + core.GUMP_MALE_BASE)
        mul_female = occ(aid + core.GUMP_FEMALE_BASE)

    # gump presence: UOP side (this is the one that actually renders if set)
    uop_male = uop_female = False
    uop_path = core.find(client, "gumpartLegacyMUL.uop")
    if uop_path:
        hs = core.read_uop_hashes(uop_path)
        uop_male = core.uop_hash(core.gump_path(aid + core.GUMP_MALE_BASE)) in hs
        uop_female = core.uop_hash(core.gump_path(aid + core.GUMP_FEMALE_BASE)) in hs

    out["gump_male"] = {"mul": mul_male, "uop": uop_male}
    out["gump_female"] = {"mul": mul_female, "uop": uop_female}

    # gump.def redirect: a gump id listed here may not render what's
    # actually stored at it, regardless of MUL/UOP state above
    gumpdef_path = core.find(client, "gump.def")
    gumpdef_ids = core.load_gumpdef_ids(gumpdef_path) if gumpdef_path else set()
    out["gumpdef_male"] = (aid + core.GUMP_MALE_BASE) in gumpdef_ids
    out["gumpdef_female"] = (aid + core.GUMP_FEMALE_BASE) in gumpdef_ids

    # which tiledata entries already use this anim (recycling candidates,
    # or "this is already spoken for")
    td_path = core.find(client, "tiledata.mul")
    users = []
    if td_path:
        td = core.TileData(td_path)
        for iid in range(2048 * 32):
            r = td.read(iid)
            if r["anim"] == aid and r["name"]:
                users.append((iid, r["name"], r["layer"]))
    out["tiledata_users"] = users

    return out


def print_anim_report(rep):
    aid = rep["anim"]
    print(f"anim {aid}:")
    for label, key in (("male", "gump_male"), ("female", "gump_female")):
        g = rep[key]
        if g["uop"]:
            where = "gumpartLegacyMUL.uop (THIS is what renders - UOP beats MUL)"
        elif g["mul"]:
            where = "Gumpart.mul only"
        else:
            where = "absent"
        gid = aid + (core.GUMP_MALE_BASE if key == "gump_male" else core.GUMP_FEMALE_BASE)
        print(f"  gump {label} (id {gid}): {where}")
        redirect_key = "gumpdef_male" if key == "gump_male" else "gumpdef_female"
        if rep.get(redirect_key):
            print(f"    WARN: gump.def redirects id {gid} elsewhere - the "
                  "client may not show what's stored here. Check in-game.")
    if rep["tiledata_users"]:
        print(f"  used by {len(rep['tiledata_users'])} tiledata entr"
              f"{'y' if len(rep['tiledata_users'])==1 else 'ies'}:")
        for iid, name, layer in rep["tiledata_users"][:20]:
            print(f"    0x{iid:04X}  \"{name}\"  layer={layer}")
        if len(rep["tiledata_users"]) > 20:
            print(f"    ... and {len(rep['tiledata_users'])-20} more")
    else:
        print("  not referenced by any tiledata entry (free to recycle, or unused)")


# ===========================================================================
# --body : full collision + type + animation picture for one body id
# ===========================================================================

def describe_body(client, body):
    out = {"body": body}

    mobtypes_path = core.find(client, "mobtypes.txt")
    mob = core.load_mobtypes(mobtypes_path) if mobtypes_path else {}
    out["mob_type"] = mob.get(body)
    out["mob_default_type"] = core.AnimIdx._dt(body)

    bd_path = core.find(client, "body.def")
    bd = core.load_bodydef_bodies(bd_path) if bd_path else set()
    out["in_bodydef"] = body in bd

    bc_path = core.find(client, "Bodyconv.def")
    bc = core.load_bodyconv_bodies(bc_path) if bc_path else set()
    out["in_bodyconv"] = body in bc

    out["in_animframe_uop"] = body in core.animframe_uop_bodies(client, body, body + 1)

    # anim.idx occupancy under BOTH models - only one is "correct" depending
    # on resolved type, but showing both avoids re-deriving this by hand
    anim_idx_path = core.find(client, "anim.idx")
    out["monster_span_populated"] = None
    out["people_span_populated"] = None
    if anim_idx_path:
        idx = core.AnimIdxFile(anim_idx_path)
        m_start = core.monster_record_offset(body)
        out["monster_span_populated"] = not idx.span_free(m_start, core.MONSTER_RECORDS)
        out["monster_offset"] = m_start

        resolved = out["mob_type"] or out["mob_default_type"]
        if resolved in ("HUMAN", "EQUIPMENT"):
            ai = core.AnimIdx(anim_idx_path, mob)
            out["people_span_populated"] = ai.populated(body)
            out["people_offset"] = ai.span(body)[0]

    return out


def print_body_report(rep):
    b = rep["body"]
    print(f"body {b}:")
    mob_line = rep["mob_type"] or f"(not listed - defaults to {rep['mob_default_type']} by id range)"
    print(f"  mobtypes.txt: {mob_line}")

    problems = []
    if rep["in_bodydef"]:
        problems.append("body.def redirects this id elsewhere - anim.idx here is never read")
    if rep["in_bodyconv"]:
        problems.append("Bodyconv.def claims this id (legacy multi-file anim index)")
    if rep["in_animframe_uop"]:
        problems.append("AnimationFrame*.uop has this body - UOP beats anim.mul")
    if problems:
        print("  COLLISIONS:")
        for p in problems:
            print(f"    - {p}")
    else:
        print("  no body.def / Bodyconv.def / AnimationFrame*.uop collisions")

    if rep["monster_span_populated"] is not None:
        state = "POPULATED" if rep["monster_span_populated"] else "empty"
        print(f"  MONSTER-model span (offset {rep['monster_offset']}, "
              f"graphic*110): {state}")
    if rep["people_span_populated"] is not None:
        state = "POPULATED" if rep["people_span_populated"] else "empty"
        print(f"  PEOPLE-model span (offset {rep['people_offset']}, "
              f"resolved type {rep['mob_type'] or rep['mob_default_type']}): {state}")


# ===========================================================================

# ===========================================================================
# --free-anim : batch search for anim ids safe to use for NEW gump art
# ===========================================================================

def find_free_anim_ids(client, count, lo=None, hi=100000):
    """Find `count` anim ids whose gump slots (aid+50000/+60000) are clear
    for a brand-new paperdoll texture: not occupied in Gumpidx.mul, not
    present in gumpartLegacyMUL.uop, and not redirected by gump.def.

    body.def/Bodyconv.def are deliberately NOT checked here - those affect
    a living mobile's animated body, not a worn item's paperdoll gump
    lookup (aid+50000/60000 is a flat, direct lookup independent of a
    mobile's body redirect chain). Checking them would exclude perfectly
    usable ids for this purpose.

    Default floor: one above the highest id already in mobtypes.txt, the
    same convention used for monster body picking - not because gump ids
    have the cumulative-offset problem monster bodies do (they don't,
    aid+50000 is a flat offset with no ordering dependency), but because
    ids above that point are reliably unused by anything else on this
    shard, giving clean, low-surprise results.

    Returns a list of ints, in ascending order, up to `count` long (may
    be shorter if the range runs out).
    """
    if lo is None:
        mobtypes_path = core.find(client, "mobtypes.txt")
        mob = core.load_mobtypes(mobtypes_path) if mobtypes_path else {}
        lo = (max(mob.keys()) + 1) if mob else 1

    gumpidx_path = core.need(client, "Gumpidx.mul")
    idx = open(gumpidx_path, "rb").read()
    n = len(idx) // core.IDX_REC

    uop_hashes = set()
    uop_path = core.find(client, "gumpartLegacyMUL.uop")
    if uop_path:
        uop_hashes = core.read_uop_hashes(uop_path)

    gumpdef_path = core.find(client, "gump.def")
    gumpdef_ids = core.load_gumpdef_ids(gumpdef_path) if gumpdef_path else set()

    def mul_occupied(gid):
        if gid >= n:
            return False
        lk = struct.unpack_from("<i", idx, gid * core.IDX_REC)[0]
        return lk != -1

    def uop_occupied(gid):
        return core.uop_hash(core.gump_path(gid)) in uop_hashes

    found = []
    aid = lo
    while len(found) < count and aid < hi:
        m_gid = aid + core.GUMP_MALE_BASE
        f_gid = aid + core.GUMP_FEMALE_BASE
        clear = (
            not mul_occupied(m_gid) and not mul_occupied(f_gid)
            and not uop_occupied(m_gid) and not uop_occupied(f_gid)
            and m_gid not in gumpdef_ids and f_gid not in gumpdef_ids
        )
        if clear:
            found.append(aid)
        aid += 1
    return found


def print_free_anim_ids(ids, requested, lo):
    if not ids:
        print(f"no free anim ids found starting from {lo}")
        return
    print(f"{len(ids)} free anim id(s) starting from {lo} "
          f"(gump slots clear in Gumpidx.mul, gumpartLegacyMUL.uop, "
          f"and gump.def):")
    print(", ".join(str(i) for i in ids))
    if len(ids) < requested:
        print(f"\n(asked for {requested}, only found {len(ids)} in range - "
              "raise --hi or lower --lo if you need more)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True)
    ap.add_argument("--item", help="search tiledata by name substring or id (0x.. or decimal)")
    ap.add_argument("--anim", type=int, help="describe one anim id")
    ap.add_argument("--body", type=int, help="describe one body id")
    ap.add_argument("--limit", type=int, default=50, help="max --item results")
    ap.add_argument("--free-anim", type=int, metavar="N",
                    help="find N anim ids with clear gump slots (for "
                         "batches of new paperdoll art) - safe to use "
                         "together with --lo/--hi")
    ap.add_argument("--lo", type=int, default=None,
                    help="--free-anim search floor (default: one above "
                         "the highest id in mobtypes.txt)")
    ap.add_argument("--hi", type=int, default=100000,
                    help="--free-anim search ceiling (default 100000)")
    a = ap.parse_args()

    if not any([a.item, a.anim is not None, a.body is not None,
               a.free_anim is not None]):
        ap.error("give at least one of --item / --anim / --body / --free-anim")

    if a.item:
        hits = search_items(a.client, a.item, a.limit)
        print_item_hits(hits, a.item, a.limit)
        print()

    if a.anim is not None:
        print_anim_report(describe_anim(a.client, a.anim))
        print()

    if a.body is not None:
        print_body_report(describe_body(a.client, a.body))
        print()

    if a.free_anim is not None:
        lo = a.lo
        if lo is None:
            mobtypes_path = core.find(a.client, "mobtypes.txt")
            mob = core.load_mobtypes(mobtypes_path) if mobtypes_path else {}
            lo = (max(mob.keys()) + 1) if mob else 1
        ids = find_free_anim_ids(a.client, a.free_anim, lo=lo, hi=a.hi)
        print_free_anim_ids(ids, a.free_anim, lo)
        print()


if __name__ == "__main__":
    main()
