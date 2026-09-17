#!/usr/bin/env python3
"""
vd_inject.py - inject a .vd monster-animation container into anim.mul / anim.idx.

.vd FORMAT (reverse-engineered and cross-checked against UOFiddler's anim
reader; identical on all four sample files):

    int32   fileType            (6 in every sample = anim.mul family)
    110 x   record (12 bytes)   lookup:int32, length:int32, extra:int32
                                lookup is an ABSOLUTE offset into THIS file,
                                length is the data-block size, extra == 0.
                                Empty slot = lookup==-1.
    <data>  starting at offset 4 + 110*12 = 1324

Each populated data block is a native UO animation group:
    256 x uint16   palette (each stored XOR 0x8000)
    int32          frame count
    frameCount x int32   frame offsets
    <frame pixel data>

110 = 22 actions * 5 directions = the MONSTER/SEA_MONSTER stride. The target
body must resolve to one of those two mobtypes for the record count to line
up with the container.

anim.idx OFFSET MODEL (critical, and easy to get wrong):
    Record offsets are NOT body*constant. The client computes them by
    walking bodies 0..2047 in order and summing each body's own stride
    (action_count * 5), where action_count depends on that body's mobtype
    (MONSTER/SEA_MONSTER=22, HUMAN/EQUIPMENT=35, ANIMAL=13, from
    mobtypes.txt, falling back to the id-range heuristic when unlisted).
    This is byte-for-byte the same algorithm as uopatch.py's AnimIdx.

    Declaring a new body as MONSTER changes ITS OWN stride, which shifts
    the computed offset of every body AFTER it in the table. If anything
    already deployed (e.g. a wearable recycling a body id) sits after our
    new target, its offset would desync from what's actually stored in the
    live anim.idx. The only fully safe rule: pick a target body id STRICTLY
    HIGHER than every id already listed in mobtypes.txt. Nothing exists
    after it yet, so nothing can desync.

SAFETY (same discipline as uopatch.py / uop_gump_patch.py):
  * Reads from --client, writes to --out. Live folder untouched.
  * Dry-run by default; --apply required to write.
  * anim.mul is only ever APPENDED to; existing bytes never move.
  * Backs up live anim.idx / anim.mul / mobtypes.txt into out/backup/<ts>/.
  * Verifies after writing: re-reads every injected record from the output
    files and confirms the bytes round-trip.
  * Auto-appends the MONSTER mobtypes.txt entry the offset math relied on,
    so the deployed files and the deployed metadata always agree.
"""

from __future__ import annotations
import argparse, hashlib, os, shutil, struct, sys, time

IDX_REC = 12
VD_RECORDS = 110                                   # 22 actions * 5 directions
VD_HEADER = 4
VD_DATA_START = VD_HEADER + VD_RECORDS * IDX_REC   # 1324

GROUP = {"MONSTER": 22, "SEA_MONSTER": 22, "HUMAN": 35,
         "EQUIPMENT": 35, "ANIMAL": 13}
DIRS = 5


class Problem(Exception):
    pass


def find(directory, name):
    for e in os.listdir(directory):
        if e.lower() == name.lower():
            return os.path.join(directory, e)
    return None


def need(directory, name):
    p = find(directory, name)
    if not p:
        raise Problem(f"missing required file: {name} in {directory}")
    return p


# --- .vd reader -------------------------------------------------------

def read_vd(path):
    """Return (file_type, [(lookup,length,extra) x110], raw_bytes)."""
    d = open(path, "rb").read()
    if len(d) < VD_DATA_START:
        raise Problem(f"{path}: too small to be a .vd container")
    file_type = struct.unpack_from("<i", d, 0)[0]
    recs = [struct.unpack_from("<iii", d, VD_HEADER + i * IDX_REC)
            for i in range(VD_RECORDS)]
    for i, (lk, ln, ex) in enumerate(recs):
        if lk != -1 and ln > 0:
            if lk < VD_DATA_START or lk + ln > len(d):
                raise Problem(
                    f"{path}: record {i} data block out of bounds "
                    f"(lookup={lk}, length={ln}, filesize={len(d)})")
    return file_type, recs, d


def vd_populated_count(recs):
    return sum(1 for lk, ln, ex in recs if lk != -1 and ln > 0)


# --- mobtypes / cumulative offset model --------------------------------

def load_mobtypes(path):
    d = {}
    if not path or not os.path.exists(path):
        return d
    for line in open(path, encoding="latin-1"):
        s = line.split("#")[0].strip()
        if not s:
            continue
        p = s.split()
        if len(p) < 2:
            continue
        try:
            d[int(p[0])] = p[1].upper()
        except ValueError:
            pass
    return d


def default_type(b):
    return "MONSTER" if b < 200 else ("ANIMAL" if b < 400 else "HUMAN")


# --- anim.idx OFFSET MODEL --------------------------------------------
#
# CORRECTED against the actual game client source (ClassicUO,
# src/ClassicUO.Assets/AnimationsLoader.cs, CalculateOffset/
# CalculateHighGroupOffset). This does NOT match a cumulative walk over
# mobtypes.txt - that model (borrowed from uopatch.py) is only valid for
# EQUIPMENT/HUMAN bodies (the "People" group), where it happens to equal a
# closed-form formula because the client hardcodes the low bands as fixed
# constants rather than re-summing them. For MONSTER type with no special
# flags (our case - a .vd container is always High/Monster group), the
# client uses a FLAT formula that depends only on the body's own number:
#
#     record_offset = graphic * 110          (HighAnimationGroup, 22 actions)
#
# This was discovered the hard way: an earlier version of this tool used
# the cumulative model, which computed a plausible-looking but WRONG
# offset. The patch verified clean, no server errors, nameplate/healthbar
# rendered (server-side, unrelated to anim.idx) - but the sprite never
# appeared, because the client was reading a completely different offset
# than the one we wrote to. No exception, no warning: silently wrong.
#
# Consequence: offset depends ONLY on the target body's own id, not on any
# other body's mobtypes.txt entry or ordering. The earlier "must be above
# every existing mobtypes.txt id" safety rule is therefore unnecessary for
# monster bodies (nothing to desync) and has been removed for this path -
# we still verify the real byte range is actually empty, which is the
# check that matters.

HIGH_GROUP_ACTIONS = 22  # HighAnimationGroup.AnimationCount in the client


def monster_record_offset(graphic):
    return graphic * HIGH_GROUP_ACTIONS * DIRS


def cumulative_offsets(mob):
    """Kept for reference/compat only - this is the EQUIPMENT/People-group
    model (uopatch.py), NOT valid for MONSTER bodies. Do not use this for
    picking or verifying a .vd injection target."""
    out, tot = [], 0
    for b in range(2048):
        out.append(tot)
        t = mob.get(b, default_type(b))
        tot += GROUP.get(t, 13) * DIRS
    return out


# --- anim.idx read/write --------------------------------------------------

class AnimIdxFile:
    def __init__(self, path):
        self.path = path
        self.idx = bytearray(open(path, "rb").read())
        self.count = len(self.idx) // IDX_REC

    def span_free(self, start, length):
        """True if every record in [start, start+length) is either beyond
        the current file (nothing written there yet) or explicitly empty
        (lookup == -1)."""
        for i in range(start, start + length):
            if i < self.count:
                lk = struct.unpack_from("<i", self.idx, i * IDX_REC)[0]
                if lk != -1:
                    return False
        return True

    def record(self, i):
        if i >= self.count:
            return (-1, -1, 0)
        return struct.unpack_from("<iii", self.idx, i * IDX_REC)

    def set_record(self, i, lookup, length, extra):
        need_len = (i + 1) * IDX_REC
        if len(self.idx) < need_len:
            grow_from = self.count
            self.idx.extend(b"\x00" * (need_len - len(self.idx)))
            for j in range(grow_from, i + 1):
                struct.pack_into("<iii", self.idx, j * IDX_REC, -1, -1, 0)
            self.count = i + 1
        struct.pack_into("<iii", self.idx, i * IDX_REC, lookup, length, extra)

    def write(self, path):
        open(path, "wb").write(bytes(self.idx))


# --- collision sources: body.def, Bodyconv.def, AnimationFrame*.uop -------

def load_bodyconv_bodies(path):
    out = set()
    for line in open(path, encoding="latin-1"):
        s = line.split("#")[0].strip()
        if not s:
            continue
        p = s.split()
        try:
            out.add(int(p[0]))
        except ValueError:
            pass
    return out


def load_bodydef_bodies(path):
    """body.def rewrites a body id to a DIFFERENT one before the client ever
    looks at anim.idx (resolution order: body.def -> UOP -> Bodyconv.def ->
    anim.mul). Format per line: `original {newBody} newHue`. Any original id
    listed here is unusable - the client always resolves to newBody instead."""
    out = set()
    for line in open(path, encoding="latin-1"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            i1 = s.index("{")
            out.add(int(s[:i1].strip()))
        except (ValueError, IndexError):
            continue
    return out


def animframe_uop_bodies(client, lo, hi):
    sys.path.insert(0, client)
    try:
        from uop_probe import read_uop_hashes, uop_hash
    except ImportError:
        return set()
    import glob
    out = set()
    for p in glob.glob(os.path.join(client, "AnimationFrame*.uop")):
        hs = read_uop_hashes(p)
        for body in range(lo, hi):
            for g in range(5):
                if uop_hash(f"build/animationlegacyframe/{body:06d}/{g:02d}.bin") in hs:
                    out.add(body)
                    break
    return out


# --- centralized collision check, used by BOTH the auto-pick loop and
# the explicit --body path, so they can never again drift apart the way
# they just did (auto-pick checked all four sources; explicit --body
# only checked mobtypes.txt after the previous fix, silently missing
# body.def/Bodyconv.def/AnimationFrame*.uop for a manually-typed id). ---

def body_collision_reasons(client, body, mob, bodydef_bodies=None,
                           bodyconv_bodies=None, animframe_bodies=None):
    """Returns a list of plain-language reasons this body is unsafe to
    use as a MONSTER target, checking all four known sources. Empty list
    means clean. The three *_bodies sets can be pre-loaded/pre-scanned
    and passed in to avoid re-reading the same files on every call (used
    by the auto-pick scan, which may check hundreds of candidates); left
    None, each is computed fresh for just this one body - fine for a
    single explicit --body check, too slow to do per-candidate in a
    scan loop."""
    reasons = []

    if bodydef_bodies is None:
        bd = find(client, "body.def")
        bodydef_bodies = load_bodydef_bodies(bd) if bd else set()
    if body in bodydef_bodies:
        reasons.append("body.def redirects this id elsewhere - the client "
                       "never reaches anim.idx for it")

    if bodyconv_bodies is None:
        bc = find(client, "Bodyconv.def")
        bodyconv_bodies = load_bodyconv_bodies(bc) if bc else set()
    if body in bodyconv_bodies:
        reasons.append("Bodyconv.def claims this id (legacy multi-file "
                       "anim routing)")

    if animframe_bodies is None:
        animframe_bodies = animframe_uop_bodies(client, body, body + 1)
    if body in animframe_bodies:
        reasons.append("AnimationFrame*.uop already has this body - UOP "
                       "beats anim.mul, a write here would be ignored")

    existing_type = mob.get(body)
    if existing_type is not None and existing_type != "MONSTER":
        reasons.append(
            f"mobtypes.txt already declares this body {existing_type}, "
            f"not MONSTER - the client uses the {existing_type} offset "
            f"formula for it, never the flat MONSTER one")

    return reasons


# --- slot selection --------------------------------------------------

def find_free_monster_body(client, lo, hi, anim_idx, mob):
    """First graphic in [lo,hi) that is clean on all four collision
    sources (see body_collision_reasons) AND whose High-group span
    (graphic*110) is empty in the real anim.idx bytes.
    Returns (body, span_start)."""
    bd = find(client, "body.def")
    bodydef_bodies = load_bodydef_bodies(bd) if bd else set()
    bc = find(client, "Bodyconv.def")
    bodyconv_bodies = load_bodyconv_bodies(bc) if bc else set()
    animframe_bodies = animframe_uop_bodies(client, lo, hi)

    for body in range(lo, hi):
        if body_collision_reasons(client, body, mob, bodydef_bodies,
                                  bodyconv_bodies, animframe_bodies):
            continue
        span_start = monster_record_offset(body)
        if anim_idx.span_free(span_start, VD_RECORDS):
            return body, span_start

    raise Problem(f"no free monster body found in [{lo},{hi}) after "
                  "excluding body.def / Bodyconv.def / UOP / mobtypes.txt "
                  "collisions")


# --- driver -------------------------------------------------------------

def run(client, vd_path, out, target_body, lo, hi, apply_changes):
    log = []

    def say(kind, msg):
        log.append((kind, msg))
        print(f"[{kind:7}] {msg}")

    file_type, recs, vd_bytes = read_vd(vd_path)
    npop = vd_populated_count(recs)
    say("VD", f"{os.path.basename(vd_path)}: fileType={file_type}, "
              f"{npop}/{VD_RECORDS} action/direction slots populated")

    anim_idx_path = need(client, "anim.idx")
    anim_mul_path = need(client, "anim.mul")
    mobtypes_path = find(client, "mobtypes.txt")
    mob = load_mobtypes(mobtypes_path) if mobtypes_path else {}
    anim_idx = AnimIdxFile(anim_idx_path)
    mul_size = os.path.getsize(anim_mul_path)

    if target_body is None:
        target_body, span_start = find_free_monster_body(client, lo, hi, anim_idx, mob)
        say("SLOT", f"auto-selected body {target_body} (graphic*110 offset "
                    f"{span_start}) - clear of body.def, Bodyconv.def, "
                    f"AnimationFrame*.uop, and mobtypes.txt")
    else:
        reasons = body_collision_reasons(client, target_body, mob)
        if reasons:
            bullets = "\n  - ".join(reasons)
            raise Problem(
                f"body {target_body} is not safe to use:\n  - {bullets}\n"
                f"Pick a different body id, or use auto-pick (omit "
                f"--body) to get one that's genuinely clean on all four "
                f"fronts.")
        span_start = monster_record_offset(target_body)
        if not anim_idx.span_free(span_start, VD_RECORDS):
            say("WARN", f"body {target_body}'s computed span is not empty "
                        "in the live anim.idx; it will be overwritten "
                        "(original bytes are backed up)")
        say("SLOT", f"using requested body {target_body}")

    say("PLAN", f"body {target_body}: anim.idx records "
                f"{span_start}..{span_start+VD_RECORDS-1}, "
                f"{npop} data blocks to append to anim.mul "
                f"(current size {mul_size})")
    say("PLAN", f"mobtypes.txt will get: {target_body}\\tMONSTER\\t0")

    if not apply_changes:
        say("PLAN", "dry run - nothing written. Re-run with --apply.")
        return log, target_body

    os.makedirs(out, exist_ok=True)

    # backup live originals
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(out, "backup", stamp)
    os.makedirs(bdir, exist_ok=True)
    shutil.copyfile(anim_idx_path, os.path.join(bdir, "anim.idx"))
    shutil.copyfile(anim_mul_path, os.path.join(bdir, "anim.mul"))
    if mobtypes_path:
        shutil.copyfile(mobtypes_path, os.path.join(bdir, "mobtypes.txt"))
    say("BACKUP", f"live anim.idx / anim.mul / mobtypes.txt saved to {bdir}")

    # anim.mul: copy then append each populated block
    out_mul = os.path.join(out, "anim.mul")
    shutil.copyfile(anim_mul_path, out_mul)
    injected = []  # (rec_index, new_offset, length, block_bytes)
    with open(out_mul, "r+b") as mo:
        mo.seek(0, os.SEEK_END)
        for slot in range(VD_RECORDS):
            lk, ln, ex = recs[slot]
            rec_i = span_start + slot
            if lk == -1 or ln <= 0:
                anim_idx.set_record(rec_i, -1, -1, 0)
                continue
            block = vd_bytes[lk:lk + ln]
            new_off = mo.tell()
            mo.write(block)
            anim_idx.set_record(rec_i, new_off, ln, 0)
            injected.append((rec_i, new_off, ln, block))

    out_idx = os.path.join(out, "anim.idx")
    anim_idx.write(out_idx)
    say("OK", f"wrote {len(injected)} blocks; anim.mul "
              f"{mul_size} -> {os.path.getsize(out_mul)} bytes")

    # mobtypes.txt: copy existing + append our entry, but ONLY if this
    # body isn't already declared. Re-running the tool on the same body
    # (e.g. after fixing a bug and re-injecting, as happened once on this
    # shard) must not silently duplicate the line.
    out_mob = os.path.join(out, "mobtypes.txt")
    if mobtypes_path:
        shutil.copyfile(mobtypes_path, out_mob)
    else:
        open(out_mob, "w", encoding="latin-1").close()

    already = mob.get(target_body)
    if already == "MONSTER":
        say("OK", f"mobtypes.txt already declares body {target_body} as "
                  "MONSTER - not duplicating the entry")
    elif already is not None:
        say("WARN", f"mobtypes.txt already declares body {target_body} as "
                    f"{already}, not MONSTER - leaving it untouched rather "
                    "than silently overriding; fix by hand if this is wrong")
    else:
        with open(out_mob, "a", encoding="latin-1", newline="\r\n") as f:
            f.write(f"\r\n# --- added by vd_inject.py ---\r\n")
            f.write(f"{target_body}\tMONSTER\t0\t# {os.path.basename(vd_path)}\r\n")
        say("OK", f"mobtypes.txt: appended '{target_body}\\tMONSTER\\t0'")

    # ---- verify: re-read output files, confirm round-trip -----------
    say("VERIFY", "re-reading output files")
    v_idx = AnimIdxFile(out_idx)
    v_mob = load_mobtypes(out_mob)
    ok = True

    if v_mob.get(target_body) != "MONSTER":
        say("ERROR", "  mobtypes.txt entry did not survive the write")
        ok = False

    v_expected_offset = monster_record_offset(target_body)
    if v_expected_offset != span_start:
        say("ERROR", f"  recomputed graphic*110 offset "
                      f"({v_expected_offset}) != planned offset "
                      f"({span_start}) - internal inconsistency")
        ok = False

    vmul = open(out_mul, "rb")
    for rec_i, new_off, ln, block in injected:
        lk, l2, ex = v_idx.record(rec_i)
        if lk != new_off or l2 != ln:
            say("ERROR", f"  record {rec_i} idx mismatch")
            ok = False
            continue
        vmul.seek(lk)
        if vmul.read(ln) != block:
            say("ERROR", f"  record {rec_i} data mismatch")
            ok = False
    vmul.close()
    say("VERIFY", "all checks passed" if ok else "FAILURES - do not ship")

    print("\n--- SHA1 of written files ---")
    for nm in ("anim.idx", "anim.mul", "mobtypes.txt"):
        p = os.path.join(out, nm)
        print(f"  {hashlib.sha1(open(p,'rb').read()).hexdigest()}  {nm}")
    print(f"\nWritten to {out}. Live client folder NOT modified.")
    print(f"Injected as MONSTER body {target_body}. Deploy:")
    print(f"  1. copy anim.idx, anim.mul, mobtypes.txt into "
          f"{os.path.abspath(client)}")
    print(f"  2. restart server + client")
    print(f"  3. spawn/add a mob with Body = {target_body} and check "
          f"it renders")
    return log, target_body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="live client folder (read only)")
    ap.add_argument("--vd", required=True, help=".vd animation container")
    ap.add_argument("--out", default="patched_vd", help="output folder")
    ap.add_argument("--body", type=int, default=None,
                    help="target body id. Omit to auto-pick. Must be higher "
                         "than every id already in mobtypes.txt.")
    ap.add_argument("--range", default="900-2000",
                    help="search band for auto-pick (default clears typical "
                         "custom-item ranges; raise the floor if you have "
                         "mobtypes.txt entries above 2000)")
    ap.add_argument("--apply", action="store_true", help="actually write")
    a = ap.parse_args()

    lo, _, hi = a.range.partition("-")
    try:
        run(a.client, a.vd, a.out, a.body, int(lo), int(hi), a.apply)
    except Problem as e:
        print(f"[ERROR  ] {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
