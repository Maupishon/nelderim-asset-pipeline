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
        print(f"  gump {label} (id {aid + (core.GUMP_MALE_BASE if key=='gump_male' else core.GUMP_FEMALE_BASE)}): {where}")
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

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True)
    ap.add_argument("--item", help="search tiledata by name substring or id (0x.. or decimal)")
    ap.add_argument("--anim", type=int, help="describe one anim id")
    ap.add_argument("--body", type=int, help="describe one body id")
    ap.add_argument("--limit", type=int, default=50, help="max --item results")
    a = ap.parse_args()

    if not any([a.item, a.anim is not None, a.body is not None]):
        ap.error("give at least one of --item / --anim / --body")

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


if __name__ == "__main__":
    main()
