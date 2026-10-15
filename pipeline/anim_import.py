#!/usr/bin/env python3
"""
anim_import.py - put a People (.vd, 35 actions x 5 directions) animation into an EMPTY slot of anim2..5.mul and wire it up
(Bodyconv.def + mobtypes.txt), the same way anim_wire.py wires slots that already hold data.

    python anim_import.py --client <KOPIA klienta> --vd robe.vd                         # dry run: which slot / body
    python anim_import.py --client <klient> --vd robe.vd --file 5 --slot 492 --body 1992 --name "Szata alchemika" \
                          --out <wyjscie> --apply

WHAT IT DOES
  1. Reads the .vd (header int32, 175 records <lookup,length,extra> with ABSOLUTE offsets inside the .vd, then the blocks).
  2. Picks the lowest EMPTY People slot of anim<N>.idx (all 175 records unused, no Bodyconv.def line points at it) or
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


def run(client, vd, n, slot, body, name, out, apply_, overwrite=False):
    say = lambda k, m: print(f"[{k:7}] {m}", flush=True)       # noqa: E731
    d, recs = read_vd(vd)
    npop = sum(1 for lk, ln, _ in recs if lk >= 0 and ln > 0)
    say("VD", f"{os.path.basename(vd)}: {npop}/{PEOPLE_RECS} bloków akcja/kierunek")
    ip, mp = C.find(client, f"anim{n}.idx"), C.find(client, f"anim{n}.mul")
    if not ip or not mp:
        raise Problem(f"Brak anim{n}.idx / anim{n}.mul w kliencie.")
    idx = bytearray(open(ip, "rb").read())
    count = len(idx) // REC
    refs = W.bodyconv_refs(C.find(client, "Bodyconv.def"))[n]

    if slot is None:
        s = 400
        while W.slot_layout(n, s)[0] + PEOPLE_RECS <= count:
            if slot_empty(idx, count, s, n) and not refs.get(s):
                slot = s
                break
            s += 1
        if slot is None:
            raise Problem(f"anim{n}.idx nie ma pustego slotu people.")
        say("SLOT", f"anim{n}: pierwszy pusty slot people = {slot}")
    else:
        if refs.get(slot):
            raise Problem(f"slot {slot} jest już podpięty w Bodyconv.def do body {refs[slot]}")
        if not slot_empty(idx, count, slot, n) and not overwrite:
            raise Problem(f"slot {slot} w anim{n} ma już dane (--overwrite, jeśli to ma być nadpisane; kopia zapasowa jest)")
        say("SLOT", f"anim{n}: wybrany slot {slot}")
    start, _ = W.slot_layout(n, slot)

    uop = W.UopIndex(client)
    if body is None:
        body = next(W.free_bodies(client, "HUMAN", set(), uop=uop), None)
        if body is None:
            raise Problem("Brak wolnego body (HUMAN).")
        say("BODY", f"wolne body = {body}")
    else:
        gen = W.free_bodies(client, "HUMAN", set(), lo=body, hi=body + 1, uop=uop)
        if next(gen, None) != body:
            raise Problem(f"body {body} jest zajęte (body.def / Bodyconv.def / mobtypes.txt / UOP / tiledata) albo ma dane w anim.mul")
        say("BODY", f"body {body} wolne")
    say("PLAN", f"anim{n}.idx rekordy {start}..{start + PEOPLE_RECS - 1}, {npop} bloków dopisanych na końcu anim{n}.mul; "
                f"Bodyconv.def: {body} -> anim{n} slot {slot}; mobtypes.txt: {body} HUMAN")
    if not apply_:
        say("PLAN", "na sucho - nic nie zapisano (--apply)")
        return {"slot": slot, "body": body}

    os.makedirs(out, exist_ok=True)
    bdir = C.backup_client_files(client, out, [f"anim{n}.idx"])         # the big .mul is only appended to; idx backup is enough
    out_mul, out_idx = os.path.join(out, f"anim{n}.mul"), os.path.join(out, f"anim{n}.idx")
    shutil.copyfile(mp, out_mul)
    new = []
    with open(out_mul, "r+b") as mo:
        mo.seek(0, os.SEEK_END)
        for k, (lk, ln, _e) in enumerate(recs):
            if lk < 0 or ln <= 0:
                struct.pack_into("<iii", idx, (start + k) * REC, -1, -1, 0)
                continue
            off = mo.tell()
            mo.write(d[lk:lk + ln])
            struct.pack_into("<iii", idx, (start + k) * REC, off, ln, 0)
            new.append((k, off, ln))
    open(out_idx, "wb").write(idx)

    # verify: every record points at bytes equal to the .vd block
    chk = open(out_idx, "rb").read()
    with open(out_mul, "rb") as f:
        for k, off, ln in new:
            lk, l2, _ = struct.unpack_from("<iii", chk, (start + k) * REC)
            f.seek(lk)
            if (lk, l2) != (off, ln) or f.read(ln) != d[recs[k][0]:recs[k][0] + ln]:
                raise Problem(f"weryfikacja nie przeszła: rekord {k}")
    say("OK", f"zapisano {len(new)} bloków; anim{n}.mul {os.path.getsize(mp)} -> {os.path.getsize(out_mul)} B; weryfikacja OK")

    row = {"slot": slot, "body": body, "type": "HUMAN", "name": name or ""}
    bd2, _man, ver = W.apply_plan(client, n, [row], out)
    C.update_manifest(client, out, [f"anim{n}.idx", f"anim{n}.mul"])
    say("OK", f"Bodyconv.def + mobtypes.txt w {out} (manifest v{ver}); kopie: {bdir or bd2}")
    return {"slot": slot, "body": body, "out": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True)
    ap.add_argument("--vd", required=True)
    ap.add_argument("--file", type=int, choices=[2, 3, 4, 5], default=5)
    ap.add_argument("--slot", type=int)
    ap.add_argument("--body", type=int)
    ap.add_argument("--name", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.apply and not a.out:
        ap.error("--apply wymaga --out")
    try:
        r = run(a.client, a.vd, a.file, a.slot, a.body, a.name, a.out, a.apply, a.overwrite)
    except Problem as e:
        print(f"[BŁĄD  ] {e}")
        return 1
    if a.json:
        print("RESULT_JSON " + json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
