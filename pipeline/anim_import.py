#!/usr/bin/env python3
"""
anim_import.py - put a People (.vd, 35 actions x 5 directions) animation into an EMPTY slot of anim2..5.mul and wire it up
(Bodyconv.def + mobtypes.txt), the same way anim_wire.py wires slots that already hold data.

    python anim_import.py --client <KOPIA klienta> --vd robe.vd                         # dry run: which slot / body
    python anim_import.py --client <klient> --vd robe.vd --file 5 --slot 492 --body 1992 --name "Szata alchemika" \
                          --out <wyjscie> --apply

WHAT IT DOES
  1. Reads the .vd (header int32, 175 records <lookup,length,extra> with ABSOLUTE offsets inside the .vd, then the blocks).
  2. Picks the lowest EMPTY People slot from 432 up of anim<N>.idx (all 175 records unused, no Bodyconv.def line points at it) or
     takes --slot (refused when it holds data, unless --overwrite).
  3. Picks a free body id (anim_wire.free_bodies: body.def, Bodyconv.def, mobtypes.txt, AnimationFrame*.uop,
     AnimationSequence.uop, tiledata/Equipconv, empty anim.mul span) or takes --body (same checks).
  4. --apply: writes to --out only (never to the client): anim<N>.mul = copy + blocks APPENDED (existing bytes never move),
     anim<N>.idx = copy with the 175 records rewritten, Bodyconv.def and mobtypes.txt via anim_wire.apply_plan, backups of
     the live files in out/backup/<time>/, Nelderim_manifest.json; then re-reads every record and compares bytes.

Layout of a People slot: anim2/3 per anim_wire.slot_layout; anim4/5: first record 35000 + (slot-400)*175, 175 records.
Only People slots (slot >= 400) are handled; monsters/animals are vd_inject.py's job.
NOT VERIFIED IN GAME for a freshly appended slot (anim_wire's wiring of existing slots was).
"""
from __future__ import annotations
import argparse, json, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nelderim_core as C                       # noqa: E402
import anim_wire as W                           # noqa: E402
from nelderim_core import Problem               # noqa: E402

REC, PEOPLE_RECS = 12, 175


def read_vd(path):
    d = open(path, "rb").read()
    if len(d) < 4 + PEOPLE_RECS * REC:
        raise Problem(f"{path}: za mały jak na .vd ludzi (35 akcji x 5 kierunków)")
    hdr = struct.unpack_from("<i", d, 0)[0]
    if (hdr >> 16) != 2:
        raise Problem(f"{path}: to nie jest .vd typu people (typ {hdr >> 16}); potrzebne 35 akcji x 5 kierunków")
    recs = [struct.unpack_from("<iii", d, 4 + i * REC) for i in range(PEOPLE_RECS)]
    for i, (lk, ln, _e) in enumerate(recs):
        if lk >= 0 and (ln <= 0 or lk + ln > len(d)):
            raise Problem(f"{path}: rekord {i} wskazuje poza plik")
    return d, recs


def slot_empty(idx, count, slot, n):
    start, nrec = W.slot_layout(n, slot)
    if nrec != PEOPLE_RECS:
        return False
    if start + nrec > count:
        return False                         # index too short; would need extending - not done here
    for i in range(start, start + nrec):
        lk, ln = struct.unpack_from("<ii", idx, i * REC)
        if lk >= 0 and ln > 0:
            return False
    return True


def gump_hashes_in_use(client):
    """hashes of the paperdoll gumps already present in gumpartLegacyMUL.uop (None when there is none / it cannot be read)."""
    for nm in os.listdir(client):
        if nm.lower() == "gumpartlegacymul.uop":
            try:
                import uop_gump_patch as G
                u = G.UopFile(os.path.join(client, nm))
                ents = set(u.entries)
                u.close()
                return ents, G
            except (OSError, SystemExit, struct.error):
                return None
    return None


def run_batch(client, items, n, out, apply_, overwrite=False, first_slot=432):
    """items = [{"vd", "name", "slot"?, "body"?}, ...] -> one anim<N>.mul / .idx / Bodyconv.def / mobtypes.txt in `out`.
    Slots and bodies are chosen one after another, so every robe gets its own and the output stays cumulative."""
    say = lambda k, m: print(f"[{k:7}] {m}", flush=True)       # noqa: E731
    ip, mp = C.find(client, f"anim{n}.idx"), C.find(client, f"anim{n}.mul")
    if not ip or not mp:
        raise Problem(f"Brak anim{n}.idx / anim{n}.mul w kliencie.")
    idx = bytearray(open(ip, "rb").read())
    count = len(idx) // REC
    refs = W.bodyconv_refs(C.find(client, "Bodyconv.def"))[n]
    uop = W.UopIndex(client)
    taken_slots, taken_bodies, plan = set(), set(), []
    gumps = gump_hashes_in_use(client)

    def gump_free(b):
        """paperdoll gumps b+50000 / b+60000 must not exist yet, or the patch would overwrite another item's gump."""
        if not gumps:
            return True
        ents, G = gumps
        return not any(G.uop_hash(G.gump_path(b + base)) in ents for base in (50000, 60000))

    for it in items:
        d, recs = read_vd(it["vd"])
        npop = sum(1 for lk, ln, _ in recs if lk >= 0 and ln > 0)
        slot, body = it.get("slot"), it.get("body")
        replace = False
        if slot is not None and overwrite and refs.get(slot):           # redo an animation that is already imported
            if body is not None and body not in refs[slot]:
                raise Problem(f"slot {slot} jest podpięty do body {refs[slot]}, a podano body {body}")
            body, replace = refs[slot][0], True
        if slot is None:
            s = first_slot
            while W.slot_layout(n, s)[0] + PEOPLE_RECS <= count:
                if slot_empty(idx, count, s, n) and not refs.get(s) and s not in taken_slots:
                    slot = s
                    break
                s += 1
            if slot is None:
                raise Problem(f"anim{n}.idx nie ma pustego slotu people.")
        elif not replace:
            if refs.get(slot) or slot in taken_slots:
                raise Problem(f"slot {slot} jest już podpięty w Bodyconv.def do body {refs.get(slot)}")
            if not slot_empty(idx, count, slot, n) and not overwrite:
                raise Problem(f"slot {slot} w anim{n} ma już dane (--overwrite, jeśli to ma być nadpisane; kopia zapasowa jest)")
        if replace:
            pass                                                         # the body is already wired to this slot
        elif body is None:
            body = next((b for b in W.free_bodies(client, "HUMAN", taken_bodies, uop=uop) if gump_free(b)), None)
            if body is None:
                raise Problem("Brak wolnego body (HUMAN).")
        else:
            if not gump_free(body):
                raise Problem(f"body {body}: gumpy {body + 50000} / {body + 60000} już są w gumpartLegacyMUL.uop (nadpisałbyś cudzy paperdoll)")
            if body in taken_bodies or next(W.free_bodies(client, "HUMAN", taken_bodies, lo=body, hi=body + 1, uop=uop), None) != body:
                raise Problem(f"body {body} jest zajęte (body.def / Bodyconv.def / mobtypes.txt / UOP / tiledata) albo ma dane w anim.mul")
        taken_slots.add(slot); taken_bodies.add(body)
        say("PLAN", f"{os.path.basename(it['vd'])}: {npop} bloków -> anim{n} slot {slot}, body {body}"
                    + (f" ({it['name']})" if it.get("name") else "") + (" [ZASTĘPUJE istniejącą animację]" if replace else ""))
        plan.append((it, d, recs, slot, body, replace))
    if not apply_:
        say("PLAN", "na sucho - nic nie zapisano (--apply)")
        return [{"slot": p[3], "body": p[4], "name": p[0].get("name", ""), "replace": p[5]} for p in plan]

    os.makedirs(out, exist_ok=True)
    bdir = C.backup_client_files(client, out, [f"anim{n}.idx"])         # the big .mul is only appended to; idx backup is enough
    out_mul, out_idx = os.path.join(out, f"anim{n}.mul"), os.path.join(out, f"anim{n}.idx")
    import shutil
    shutil.copyfile(mp, out_mul)
    written = []
    with open(out_mul, "r+b") as mo:
        mo.seek(0, os.SEEK_END)
        for it, d, recs, slot, body, _rep in plan:
            start, _ = W.slot_layout(n, slot)
            for k, (lk, ln, _e) in enumerate(recs):
                if lk < 0 or ln <= 0:
                    struct.pack_into("<iii", idx, (start + k) * REC, -1, -1, 0)
                    continue
                off = mo.tell()
                mo.write(d[lk:lk + ln])
                struct.pack_into("<iii", idx, (start + k) * REC, off, ln, 0)
                written.append((start + k, off, ln, d[lk:lk + ln]))
    open(out_idx, "wb").write(idx)

    chk = open(out_idx, "rb").read()                                   # verify: every record points at its block
    with open(out_mul, "rb") as f:
        for rec, off, ln, blk in written:
            lk, l2, _ = struct.unpack_from("<iii", chk, rec * REC)
            f.seek(lk)
            if (lk, l2) != (off, ln) or f.read(ln) != blk:
                raise Problem(f"weryfikacja nie przeszła: rekord {rec}")
    say("OK", f"zapisano {len(written)} bloków ({len(plan)} animacji); anim{n}.mul {os.path.getsize(mp)} -> "
              f"{os.path.getsize(out_mul)} B; weryfikacja OK")

    rows = [{"slot": slot, "body": body, "type": "HUMAN", "name": it.get("name") or ""}
            for it, _d, _r, slot, body, rep in plan if not rep]           # replaced slots are already wired
    if rows:
        bd2, _man, ver = W.apply_plan(client, n, rows, out)
        C.update_manifest(client, out, [f"anim{n}.idx", f"anim{n}.mul"])
        say("OK", f"Bodyconv.def + mobtypes.txt w {out} (manifest v{ver}); kopie: {bdir or bd2}")
    else:
        C.update_manifest(client, out, [f"anim{n}.idx", f"anim{n}.mul"])
        say("OK", "animacje zastąpione w miejscu; Bodyconv.def i mobtypes.txt bez zmian (są już w kliencie)")
    return [{"slot": slot, "body": body, "name": it.get("name") or "", "out": out, "replace": rep}
            for it, _d, _r, slot, body, rep in plan]


def run(client, vd, n, slot, body, name, out, apply_, overwrite=False):
    r = run_batch(client, [{"vd": vd, "name": name, "slot": slot, "body": body}], n, out, apply_, overwrite)[0]
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True)
    ap.add_argument("--vd", required=True, action="append", help="may be given several times (one slot + body each)")
    ap.add_argument("--file", type=int, choices=[2, 3, 4, 5], default=5)
    ap.add_argument("--slot", type=int)
    ap.add_argument("--body", type=int)
    ap.add_argument("--name", action="append", default=[], help="one per --vd, same order")
    ap.add_argument("--first-slot", type=int, default=432, help="where the automatic slot search starts")
    ap.add_argument("--out", default="")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.apply and not a.out:
        ap.error("--apply wymaga --out")
    try:
        if len(a.vd) > 1 and (a.slot or a.body):
            ap.error("--slot / --body tylko przy jednym --vd")
        items = [{"vd": v, "name": (a.name[i] if i < len(a.name) else ""), "slot": a.slot, "body": a.body} for i, v in enumerate(a.vd)]
        r = run_batch(a.client, items, a.file, a.out, a.apply, a.overwrite, a.first_slot)
        r = r if len(r) > 1 else r[0]
    except Problem as e:
        print(f"[BŁĄD  ] {e}")
        return 1
    if a.json:
        print("RESULT_JSON " + json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
