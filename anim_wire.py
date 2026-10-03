#!/usr/bin/env python3
"""
anim_wire.py - find animations in anim2..5.mul that no body uses yet and wire them up
(Bodyconv.def + mobtypes.txt), the same way the rest of this pipeline works.

    python anim_wire.py --client <KOPIA klienta> --file 5                    # dry run: list + plan
    python anim_wire.py --client <klient> --file 5 --slots 30 31 --out <wyjście> --apply
    python anim_wire.py --client <klient> --file 5 --json                     # machine-readable (Nelderim Lab)

WHAT IT DOES
  1. Walks anim<N>.idx slot by slot (record layout per file below) and keeps the slots
     that have animation data (any record with lookup >= 0 and length > 0).
  2. Diff against Bodyconv.def: a slot is "unassigned" when no Bodyconv.def line points
     at it in the anim<N> column (live or inert lines alike - every non-comment line counts).
  3. For each unassigned slot picks a free body id, clean on all four collision sources
     (body.def, Bodyconv.def, mobtypes.txt, AnimationFrame*.uop for action groups 0-99, AnimationSequence.uop),
     not used as an item
     animation (tiledata.mul animId, Equipconv.def), never 0, and with an empty anim.mul span, preferring the id band whose default type equals the slot's type
     (MONSTER 0-199, ANIMAL 200-399, HUMAN 400+). Outside the band only ids ABOVE every
     id already in mobtypes.txt are used, so the cumulative People-group model of
     uopatch.py (AnimIdx) cannot shift for anything already deployed.
  4. --apply: writes to --out (never to the client): Bodyconv.def and mobtypes.txt =
     live copy + an appended "# --- added by anim_wire.py ---" block, backups of the live
     files in out/backup/<time>/, Nelderim_manifest.json, then re-reads and verifies.

RECORD LAYOUT inside anim2..5.idx (first record of slot b; source: SpriteMotion overlay
uo.py UOReader._base, "UOFiddler layouts"):
    anim2: b<200 -> b*110 (High, 22 actions)            else 22000+(b-200)*65 (Low, 13)
    anim3: b<300 -> b*65  (Low)   b<400 -> 33000+(b-300)*110 (High)   else 35000+(b-400)*175 (People, 35)
    anim4, anim5: like anim.mul: b<200 High, b<400 Low (22000+(b-200)*65), else People (35000+(b-400)*175)
Group -> mobtypes TYPE: High = MONSTER, Low = ANIMAL, People = HUMAN.

Bodyconv.def line written (format from the live file's header: "<body> <anim2> <anim3>
<anim4> <anim5>", -1 = not in that file, a 6th column is ignored by the client):
    <body>  -1  -1  -1  <slot>  -1   # anim5 slot <slot>  (example for --file 5)

NOT VERIFIED IN GAME: this project had no in-game-tested Bodyconv.def addition before this
tool (nelderim_core keeps Bodyconv.def read-only for that reason). Dry run is the default;
check one wired body in game before wiring many.
"""
from __future__ import annotations
import argparse, json, os, shutil, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nelderim_core as C

IDX_REC = 12
FILES = (2, 3, 4, 5)
TYPE_OF_GROUP = {110: "MONSTER", 65: "ANIMAL", 175: "HUMAN"}
COL = {2: 1, 3: 2, 4: 3, 5: 4}                          # Bodyconv.def column of anim<N>
MAX_BODY = 2048


class Problem(Exception):
    pass


# ---------------------------------------------------------------- layout
def slot_layout(n, b):
    """(first record, record count) of slot b inside anim<n>.idx."""
    if n == 2:
        return (b * 110, 110) if b < 200 else (22000 + (b - 200) * 65, 65)
    if n == 3:
        if b < 300:
            return b * 65, 65
        if b < 400:
            return 33000 + (b - 300) * 110, 110
        return 35000 + (b - 400) * 175, 175
    if b < 200:
        return b * 110, 110
    if b < 400:
        return 22000 + (b - 200) * 65, 65
    return 35000 + (b - 400) * 175, 175


def anim_mul_span(body, typ):
    """anim.mul (main file) span for a body of the given mobtypes TYPE (CLAUDE.md landmines / nelderim_core)."""
    if typ in ("MONSTER", "SEA_MONSTER"):
        return C.monster_record_offset(body), 110
    if typ == "ANIMAL":
        return 22000 + (body - 200) * 65, 65
    return 35000 + (body - 400) * 175, 175


def read_idx(path):
    d = open(path, "rb").read()
    return d, len(d) // IDX_REC


def populated(idx, count, start, n):
    """number of records with data and number of actions (5 directions each) with any data."""
    recs = acts = 0
    for a in range(n // 5):
        any_a = False
        for k in range(5):
            i = start + a * 5 + k
            if i >= count:
                break
            lk, ln = struct.unpack_from("<ii", idx, i * IDX_REC)
            if lk >= 0 and ln > 0:
                recs += 1; any_a = True
        acts += any_a
    return recs, acts


def scan_slots(client, n):
    p = C.find(client, f"anim{n}.idx")
    if not p or not C.find(client, f"anim{n}.mul"):
        raise Problem(f"Brak anim{n}.idx / anim{n}.mul w folderze klienta.")
    idx, count = read_idx(p)
    out = []
    b = 0
    while True:
        start, nrec = slot_layout(n, b)
        if start >= count:
            # anim3 has a gap between bands; keep walking into the next band if it exists
            nxt = {2: [200], 3: [300, 400], 4: [200, 400], 5: [200, 400]}[n]
            later = [x for x in nxt if x > b and slot_layout(n, x)[0] < count]
            if not later:
                break
            b = later[0]
            continue
        recs, acts = populated(idx, count, start, nrec)
        if recs:
            out.append({"slot": b, "first_record": start, "records": nrec, "type": TYPE_OF_GROUP[nrec],
                        "populated_records": recs, "actions": acts, "actions_total": nrec // 5})
        b += 1
    return out


# ---------------------------------------------------------------- Bodyconv.def
def bodyconv_refs(path):
    """{n: {slot: [bodies]}} for every non-comment Bodyconv.def line."""
    refs = {n: {} for n in FILES}
    if not path:
        return refs
    for line in open(path, encoding="latin-1"):
        v = line.split("#")[0].split()
        if len(v) < 2:
            continue
        try:
            body = int(v[0])
        except ValueError:
            continue
        for n in FILES:
            c = COL[n]
            if c < len(v):
                try:
                    s = int(v[c])
                except ValueError:
                    continue
                if s >= 0:
                    refs[n].setdefault(s, []).append(body)
    return refs


# ---------------------------------------------------------------- free bodies
UOP_GROUPS = 100            # action groups probed per body in AnimationFrame*.uop (not only 0-4)


def _uop_entries(path):
    """read-only list of (hash, offset, header len, compressed len, decompressed len, flag) of a MYP (.uop) file."""
    out = []
    with open(path, "rb") as f:
        if f.read(4) != b"MYP\x00":
            return out
        _ver, _sig, nxt, _cap, _cnt = struct.unpack("<II q i i", f.read(24))
        while nxt:
            f.seek(nxt)
            n, nxt = struct.unpack("<i q", f.read(12))
            for _ in range(n):
                off, hlen, clen, dlen, h, _ad, flag = struct.unpack("<q i i i Q I h", f.read(34))
                if off:
                    out.append((h, off, hlen, clen, dlen, flag))
    return out


class UopIndex:
    """What the client's UOP animation files already use (UOP beats Bodyconv.def / anim*.mul).
    frames: hashes of AnimationFrame*.uop, probed per body for action groups 0..UOP_GROUPS-1.
    sequence: animation ids listed in AnimationSequence.uop (first uint32 of each entry, zlib when flag 1)."""

    def __init__(self, client):
        import glob, zlib
        self.frames = set()
        for p in glob.glob(os.path.join(client, "AnimationFrame*.uop")):
            self.frames |= {e[0] for e in _uop_entries(p)}
        self.sequence = set()
        sp = C.find(client, "AnimationSequence.uop")
        if sp:
            with open(sp, "rb") as f:
                for h, off, hlen, clen, dlen, flag in _uop_entries(sp):
                    f.seek(off + hlen)
                    data = f.read(clen)
                    if flag == 1:
                        try:
                            data = zlib.decompress(data)
                        except zlib.error:
                            continue
                    if len(data) >= 4:
                        self.sequence.add(struct.unpack_from("<I", data, 0)[0])

    def frame_groups(self, body):
        return [g for g in range(UOP_GROUPS) if C.uop_hash(C.animframe_path(body, g)) in self.frames]

    def used(self, body):
        return body in self.sequence or bool(self.frame_groups(body))


def free_bodies(client, typ, taken, max_body=MAX_BODY, lo=None, hi=None, uop=None):
    """generator of clean body ids for a TYPE (see module doc for the order)."""
    mob = C.load_mobtypes(C.find(client, "mobtypes.txt"))
    bd = C.find(client, "body.def"); bc = C.find(client, "Bodyconv.def")
    bodydef = C.load_bodydef_bodies(bd) if bd else set()
    bconv = C.load_bodyconv_bodies(bc) if bc else set()
    uop = uop or UopIndex(client)
    aidx = C.find(client, "anim.idx")
    main = C.AnimIdxFile(aidx) if aidx else None
    used_anim = set()                                             # animation ids already used by worn items
    td = C.find(client, "tiledata.mul")
    if td:
        try:
            t = C.TileData(td)
            used_anim = {t.read(i)["anim"] for i in range(2048 * 32)} - {0}
        except C.Problem:
            pass
    ec = C.find(client, "Equipconv.def")
    if ec:
        for _bt, eq, conv, _g, _h, _c in C.load_equipconv(ec):
            used_anim.update((eq, conv))
    top = max(mob) if mob else -1
    if lo is not None:
        order = range(lo, min(hi or max_body, max_body))
    else:
        band = {"MONSTER": range(0, 200), "ANIMAL": range(200, 400), "HUMAN": range(400, max_body)}[typ]
        order = list(band) + [b for b in range(top + 1, max_body) if b not in band]
    for b in order:
        if b <= 0 or b in taken or b in bodydef or b in bconv or b in mob or b in used_anim or uop.used(b):
            continue
        if typ == "ANIMAL" and b < 200 or typ == "HUMAN" and b < 400:
            continue                                              # main-file formula undefined there
        if main is not None:
            s, ln = anim_mul_span(b, typ)
            if not main.span_free(s, ln):
                continue
        yield b


def plan(client, n, slots=None, names=None, lo=None, hi=None):
    found = scan_slots(client, n)
    refs = bodyconv_refs(C.find(client, "Bodyconv.def"))[n]
    rows, taken, gens = [], set(), {}
    uop = UopIndex(client)
    for s in found:
        s["assigned_to"] = refs.get(s["slot"], [])
        if s["assigned_to"] or (slots and s["slot"] not in slots):
            continue
        typ = s["type"]
        g = gens.setdefault(typ, free_bodies(client, typ, taken, lo=lo, hi=hi, uop=uop))
        body = next(g, None)
        s["body"] = body
        s["name"] = (names or {}).get(s["slot"], "")
        if body is not None:
            taken.add(body)
        rows.append(s)
    return found, rows


# ---------------------------------------------------------------- write
def ascii_note(text):
    """comments in .def / mobtypes.txt stay plain ASCII (the files are latin-1; Polish letters like ł do not fit)."""
    import unicodedata
    text = text.translate(str.maketrans({"ł": "l", "Ł": "L"}))
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _append(path_in, path_out, header, lines):
    if path_in:
        shutil.copyfile(path_in, path_out)
    else:
        open(path_out, "w", encoding="latin-1").close()
    with open(path_out, "a", encoding="latin-1", newline="") as f:
        f.write(f"\r\n# --- added by anim_wire.py ({ascii_note(header)}) ---\r\n")
        for ln in lines:
            f.write(ln + "\r\n")


def apply_plan(client, n, rows, out):
    rows = [r for r in rows if r.get("body") is not None]
    if not rows:
        raise Problem("Nic do zapisania (brak wolnych slotów albo body).")
    os.makedirs(out, exist_ok=True)
    bdir = C.backup_client_files(client, out, ["Bodyconv.def", "mobtypes.txt"])
    stamp = time.strftime("%Y-%m-%d %H:%M")
    bc_lines, mob_lines = [], []
    for r in rows:
        cols = ["-1"] * 4
        cols[COL[n] - 1] = str(r["slot"])
        note = ascii_note(f"anim{n} slot {r['slot']}" + (f" - {r['name']}" if r.get("name") else ""))
        bc_lines.append("\t".join([str(r["body"]), *cols, "-1"]) + f"\t# {note}")
        mob_lines.append(f"{r['body']}\t{r['type']}\t0\t# {note}")
    _append(C.find(client, "Bodyconv.def"), os.path.join(out, "Bodyconv.def"), f"anim{n}.mul, {stamp}", bc_lines)
    _append(C.find(client, "mobtypes.txt"), os.path.join(out, "mobtypes.txt"), f"anim{n}.mul, {stamp}", mob_lines)
    # verify: re-read what was written
    refs = bodyconv_refs(os.path.join(out, "Bodyconv.def"))[n]
    mob = C.load_mobtypes(os.path.join(out, "mobtypes.txt"))
    bad = [r for r in rows if r["body"] not in refs.get(r["slot"], []) or mob.get(r["body"]) != r["type"]]
    if bad:
        raise Problem("Weryfikacja nie przeszła dla slotów: " + ", ".join(str(r["slot"]) for r in bad))
    man, ver = C.update_manifest(client, out, ["Bodyconv.def", "mobtypes.txt"])
    return bdir, man, ver


# ---------------------------------------------------------------- thumbnail (Nelderim Lab)
def thumbnail(client, n, slot, size=96):
    """PNG bytes of the first frame of the first populated action/direction of a slot (to recognise the creature)."""
    from PIL import Image
    import io
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from uo3d import vdread
    idx, count = read_idx(C.find(client, f"anim{n}.idx"))
    start, nrec = slot_layout(n, slot)
    mul = C.find(client, f"anim{n}.mul")
    for a in range(nrec // 5):
        for d in (2, 1, 3, 0, 4):
            i = start + a * 5 + d
            if i >= count:
                continue
            lk, ln = struct.unpack_from("<ii", idx, i * IDX_REC)
            if lk < 0 or ln <= 0:
                continue
            with open(mul, "rb") as fh:
                fh.seek(lk); data = fh.read(ln)
            frames = vdread.decode_group(data, 0)
            fr = next((f for f in frames if f["w"] and f["h"]), None)
            if fr is None:
                continue
            im = Image.fromarray(fr["img"])
            im.thumbnail((size, size), Image.NEAREST)
            b = io.BytesIO(); im.save(b, "PNG")
            return b.getvalue()
    return None


def check_body(client, b):
    """plain-language list of everything that already uses body b (empty = free)."""
    out = []
    mob = C.load_mobtypes(C.find(client, "mobtypes.txt"))
    if b in mob:
        out.append(f"mobtypes.txt: {mob[b]}")
    bd = C.find(client, "body.def")
    if bd and b in C.load_bodydef_bodies(bd):
        out.append("body.def przekierowuje to body")
    bc = C.find(client, "Bodyconv.def")
    if bc and b in C.load_bodyconv_bodies(bc):
        out.append("Bodyconv.def ma to body")
    u = UopIndex(client)
    g = u.frame_groups(b)
    if g:
        out.append(f"AnimationFrame*.uop: akcje {g[:12]}{'...' if len(g) > 12 else ''} (UOP wygrywa z Bodyconv.def)")
    if b in u.sequence:
        out.append("AnimationSequence.uop: jest na liście (UOP wygrywa z Bodyconv.def)")
    aidx = C.find(client, "anim.idx")
    if aidx:
        for typ in ("MONSTER", "ANIMAL", "HUMAN"):
            if (typ == "ANIMAL" and b < 200) or (typ == "HUMAN" and b < 400):
                continue
            st, ln = anim_mul_span(b, typ)
            if not C.AnimIdxFile(aidx).span_free(st, ln):
                out.append(f"anim.mul: są dane w zakresie typu {typ}")
    return out


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True, help="client folder (a COPY) - read only")
    ap.add_argument("--file", type=int, default=None, choices=FILES, help="which animN.mul to scan (2-5)")
    ap.add_argument("--slots", nargs="*", type=int, default=None, help="only these slots (default: all unassigned)")
    ap.add_argument("--names", default="", help='JSON {"slot": "name"} for comments in the .def files')
    ap.add_argument("--range", default="", help="body id range lo-hi to pick from (default: by type band, see doc)")
    ap.add_argument("--out", default="patched_anim_wire", help="output folder (never the client)")
    ap.add_argument("--apply", action="store_true", help="write Bodyconv.def + mobtypes.txt to --out")
    ap.add_argument("--json", action="store_true", help="print RESULT_JSON <json> (for Nelderim Lab)")
    ap.add_argument("--check-body", type=int, default=None, help="only report what already uses this body id")
    a = ap.parse_args(argv)
    if a.check_body is not None:
        why = check_body(a.client, a.check_body)
        print(f"[BODY   ] {a.check_body}: " + ("wolne" if not why else "ZAJĘTE"))
        for w in why:
            print("          - " + w)
        return 0
    if a.file is None:
        ap.error("--file 2|3|4|5 jest wymagane")
    names = {int(k): v for k, v in json.loads(a.names).items()} if a.names else {}
    lo = hi = None
    if a.range:
        lo, hi = (int(x) for x in a.range.split("-"))
    try:
        found, rows = plan(a.client, a.file, set(a.slots) if a.slots else None, names, lo, hi)
        res = {"file": a.file, "slots_with_data": len(found), "assigned": sum(1 for s in found if s["assigned_to"]),
               "unassigned": rows, "applied": False}
        print(f"[SCAN   ] anim{a.file}.mul: {len(found)} slotów z danymi, {res['assigned']} przypisanych w Bodyconv.def, "
              f"{len(rows)} do podpięcia")
        for r in rows:
            b = r["body"] if r["body"] is not None else "BRAK WOLNEGO"
            print(f"[PLAN   ] slot {r['slot']:4d}  {r['type']:8s} akcje {r['actions']}/{r['actions_total']}  -> body {b}"
                  + (f"  ({r['name']})" if r["name"] else ""))
        if any(r["body"] is None for r in rows):
            print("[WARN   ] dla części slotów zabrakło wolnych body w zakresie - podaj --range")
        if a.apply:
            bdir, man, ver = apply_plan(a.client, a.file, rows, a.out)
            res["applied"] = True; res["out"] = os.path.abspath(a.out)
            print(f"[BACKUP ] kopie żywych plików: {bdir}")
            print(f"[OK     ] zapisano {a.out}/Bodyconv.def i mobtypes.txt (manifest v{ver}); weryfikacja OK")
            print("[NEXT   ] skopiuj oba pliki do KOPII klienta, zrestartuj klienta, sprawdź jedno body w grze "
                  "(np. [set Body <id>] na stworzeniu). Dopisanie do Bodyconv.def NIESPRAWDZONE w grze na tym shardzie.")
        else:
            print("[PLAN   ] na sucho - nic nie zapisano. Dodaj --apply, żeby zapisać do --out.")
        if a.json:
            print("RESULT_JSON " + json.dumps(res, ensure_ascii=False), flush=True)
        return 0
    except (Problem, C.Problem) as e:
        print(f"[ERROR  ] {e}")
        if a.json:
            print("RESULT_JSON " + json.dumps({"error": str(e)}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
