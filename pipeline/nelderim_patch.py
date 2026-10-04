#!/usr/bin/env python3
"""
nelderim_patch.py - one recipe, one command, routed to the three proven
engines (uopatch.py, uop_gump_patch.py, vd_inject.py) as SUBPROCESSES.

Design rule, learned the hard way this project: the three engines each use
a DIFFERENT and non-interchangeable low-level model (cumulative vs flat
anim.idx offsets; MUL vs UOP gump storage). Reimplementing them here from
memory is exactly how the Fire Giant Hammer ended up invisible. So this
tool does NOT reimplement anything. It:

    1. reads one combined recipe,
    2. runs preflight missing-asset detection (nelderim_core),
    3. classifies each item by the fields it carries,
    4. writes a minimal per-engine sub-recipe for the relevant items,
    5. invokes the existing, individually-tested tool as a subprocess,
    6. surfaces each tool's own output and exit code.

Each engine keeps its own backups, its own verification pass, and its own
--apply gate. This wrapper only routes.

ITEM CLASSIFICATION (an item may need more than one engine):

  * has "vd"                          -> vd_inject.py        (monster anim)
  * has "gump_male"/"gump_female" AND
    that gump id already lives in
    gumpartLegacyMUL.uop              -> uop_gump_patch.py   (gump-in-UOP)
  * has "art"/"anim"/tiledata fields
    (or a gump NOT in the UOP)        -> uopatch.py          (wearable/item)

The UOP check is what decides whether a gump goes to uop_gump_patch.py
(slot present in UOP, MUL write would be ignored) or stays with uopatch.py
(slot only in MUL). This mirrors exactly what we learned deploying the six
robes' female gump fix.

Because each engine writes to its OWN --out folder and patches a different
set of files, there is no cross-engine file contention:
    uopatch.py         -> Gumpart.mul, Gumpidx.mul, art.mul, artidx.mul,
                          tiledata.mul, (body.def/mobtypes.txt)
    uop_gump_patch.py  -> gumpartLegacyMUL.uop (in place, own backup)
    vd_inject.py       -> anim.mul, anim.idx, mobtypes.txt
The only shared file is mobtypes.txt (uopatch for People-group items,
vd_inject for monster anims); they are run sequentially and each reads the
latest copy, so appends stack rather than clobber - but see the deploy
notes printed at the end for the one manual ordering caveat.
"""

from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# import the shared core for preflight + UOP gump detection only
sys.path.insert(0, HERE)
try:
    import nelderim_core as core
except ImportError:
    core = None

UOPATCH = os.path.join(HERE, "uopatch.py")
UOP_GUMP = os.path.join(HERE, "uop_gump_patch.py")
VD_INJECT = os.path.join(HERE, "vd_inject.py")

GUMP_MALE_BASE = 50000
GUMP_FEMALE_BASE = 60000


def classify(item, client):
    """Return the set of engines this item needs: any of
    {'wearable', 'gump_uop', 'monster'}. Uses the shared core to decide
    whether a gump id is UOP-resident (-> gump_uop) or MUL-only
    (-> handled by uopatch as part of the wearable path)."""
    engines = set()

    if item.get("vd"):
        engines.add("monster")

    # does this item touch a gump, and if so is that gump in the UOP?
    gump_ids = []
    aid = item.get("anim")
    if aid is not None:
        if item.get("gump_male"):
            gump_ids.append(aid + GUMP_MALE_BASE)
        if item.get("gump_female"):
            gump_ids.append(aid + GUMP_FEMALE_BASE)

    uop_resident = set()
    if gump_ids and core is not None:
        uop_resident = core.gump_uop_bodies(client, gump_ids)

    if uop_resident:
        engines.add("gump_uop")

    # wearable/item path: art, anim recycling, tiledata, or a MUL-only gump
    if (item.get("art") or item.get("anim") is not None
            or item.get("tile_name") or item.get("layer") is not None):
        # if the ONLY thing here is a UOP-resident gump, don't also run
        # uopatch for it - but any art/anim/tiledata still needs uopatch
        engines.add("wearable")

    return engines, uop_resident


def sub_recipe(items, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2, ensure_ascii=False)


def run_tool(argv, dry):
    printable = " ".join(
        (a if " " not in a else f'"{a}"') for a in argv)
    print(f"\n>>> {printable}")
    if dry:
        print("    (dry run - not executed)")
        return 0
    return subprocess.call(argv)


def main():
    ap = argparse.ArgumentParser(
        description="Unified Nelderim asset patcher (routes to the three "
                    "existing engines as subprocesses).")
    ap.add_argument("--client", required=True,
                    help="live client folder (read only)")
    ap.add_argument("--recipe", required=True, help="combined JSON recipe")
    ap.add_argument("--out", default="patched_all",
                    help="parent output folder (per-engine subfolders inside)")
    ap.add_argument("--apply", action="store_true",
                    help="actually write (default is a dry run of every "
                         "routed subprocess)")
    ap.add_argument("--missing", choices=["stop", "skip", "ask"], default="stop",
                    help="policy for referenced assets not on disk: "
                         "stop = report all and abort (default), "
                         "skip = drop the missing field and continue, "
                         "ask = prompt y/n per asset in the terminal")
    ap.add_argument("--range", default="900-2000",
                    help="body-id search band passed to vd_inject for "
                         "monster anims")
    ap.add_argument("--allow-link", action="store_true",
                    help="pass through to uopatch (unreliable anim linking; "
                         "recycling is preferred)")
    a = ap.parse_args()

    recipe = json.load(open(a.recipe, encoding="utf-8"))
    recipe["__path__"] = a.recipe
    base = os.path.dirname(os.path.abspath(a.recipe))
    items = recipe.get("items", [])

    if not items:
        print("[nelderim] recipe has no items")
        return 1

    # ---- preflight: missing assets across the WHOLE recipe --------------
    if core is not None:
        if a.missing == "stop":
            mode = core.MISSING_STOP
            ask_fn = None
        elif a.missing == "skip":
            mode = core.MISSING_SKIP
            ask_fn = None
        else:  # ask
            mode = core.MISSING_ASK

            def ask_fn(name, field, path):
                reply = input(f"[nelderim] {name}: {field} not found at "
                              f"{path}\n  Do you have this file now? "
                              "(y/n): ").strip().lower()
                return reply.startswith("y")
        try:
            core.resolve_missing_assets(recipe, base, mode=mode, ask_fn=ask_fn)
        except core.Problem as e:
            print(f"[nelderim] preflight: {e}")
            return 2
    else:
        print("[nelderim] WARNING: nelderim_core not found - skipping "
              "preflight missing-asset check")

    # ---- classify every item -------------------------------------------
    # Asset paths (art/gump_male/gump_female) in the ORIGINAL recipe are
    # relative to `base` (the original recipe's own directory). Each
    # engine gets its own sub-recipe JSON written into a DIFFERENT
    # directory (tmpdir, under --out) - so those paths must be resolved
    # to ABSOLUTE before being copied into a sub-recipe, or the target
    # engine resolves them relative to the wrong directory and fails to
    # find a file that actually exists. (Found via a real --apply run
    # against the live client, 2026-08-11 - the exact bug this project
    # keeps trying to catch before it reaches a live client.)
    _ASSET_FIELDS = ("art", "gump_male", "gump_female")

    def _absolutize_assets(d):
        out = dict(d)
        for f in _ASSET_FIELDS:
            if out.get(f) and not os.path.isabs(out[f]):
                out[f] = os.path.abspath(os.path.join(base, out[f]))
        return out

    wearable_items, gump_uop_items, monster_items = [], [], []
    for it in items:
        engines, uop_resident = classify(it, a.client)
        tag = it.get("name", "?")
        print(f"[route] {tag}: {', '.join(sorted(engines)) or 'nothing to do'}")

        if "monster" in engines:
            monster_items.append(it)
        if "gump_uop" in engines:
            # only the gump fields go to the UOP tool
            g = {"name": it.get("name"), "anim": it.get("anim")}
            if it.get("gump_male") and (it.get("anim") + GUMP_MALE_BASE) in uop_resident:
                g["gump_male"] = it["gump_male"]
            if it.get("gump_female") and (it.get("anim") + GUMP_FEMALE_BASE) in uop_resident:
                g["gump_female"] = it["gump_female"]
            gump_uop_items.append(_absolutize_assets(g))
        if "wearable" in engines:
            # strip any UOP-resident gump fields (they're handled above; a
            # MUL write to them would be ignored by the client anyway)
            w = dict(it)
            if it.get("anim") is not None:
                if (it.get("anim") + GUMP_MALE_BASE) in uop_resident:
                    w.pop("gump_male", None)
                if (it.get("anim") + GUMP_FEMALE_BASE) in uop_resident:
                    w.pop("gump_female", None)
            wearable_items.append(_absolutize_assets(w))

    os.makedirs(a.out, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="nelderim_recipes_", dir=a.out)
    rc_total = 0

    # ---- 1. wearable/item -> uopatch.py --------------------------------
    if wearable_items:
        rp = os.path.join(tmpdir, "wearable.json")
        sub_recipe(wearable_items, rp)
        argv = [sys.executable, UOPATCH,
                "--client", a.client, "--recipe", rp,
                "--out", os.path.join(a.out, "wearable")]
        if a.apply:
            argv.append("--apply")
        if a.allow_link:
            argv.append("--allow-link")
        rc_total |= run_tool(argv, dry=not a.apply) or 0

    # ---- 2. gump-in-UOP -> uop_gump_patch.py ---------------------------
    if gump_uop_items:
        rp = os.path.join(tmpdir, "gump_uop.json")
        sub_recipe(gump_uop_items, rp)
        argv = [sys.executable, UOP_GUMP,
                "--client", a.client, "--recipe", rp]
        if a.apply:
            argv.append("--apply")
        rc_total |= run_tool(argv, dry=not a.apply) or 0

    # ---- 3. monster anim -> vd_inject.py (one call per .vd) ------------
    for it in monster_items:
        vd_rel = it["vd"]
        vd_path = vd_rel if os.path.isabs(vd_rel) else os.path.join(base, vd_rel)
        argv = [sys.executable, VD_INJECT,
                "--client", a.client, "--vd", vd_path,
                "--out", os.path.join(a.out, "monster"),
                "--range", a.range]
        if it.get("body") is not None:
            argv += ["--body", str(it["body"])]
        if a.apply:
            argv.append("--apply")
        rc_total |= run_tool(argv, dry=not a.apply) or 0

    # ---- deploy notes ---------------------------------------------------
    print("\n" + "=" * 68)
    if not a.apply:
        print("DRY RUN complete. Nothing was written. Re-run with --apply.")
    elif rc_total:
        print("ONE OR MORE ENGINES FAILED (see [ERROR]/traceback output "
              "above). Nothing further to deploy - fix the failure and "
              "re-run before touching the live client with any output "
              "that WAS produced.")
    else:
        print("All routed engines finished. Per-engine outputs are under:")
        print(f"  {os.path.join(a.out, 'wearable')}   (Gumpart/tiledata/art .mul)")
        print(f"  {os.path.join(a.out, 'monster')}    (anim.mul/idx, mobtypes.txt)")
        print(f"  gumpartLegacyMUL.uop was patched IN PLACE (own .orig_backup)")
        print("\nDEPLOY ORDER (matters for the one shared file, mobtypes.txt):")
        print("  1. copy the wearable/ .mul files into the client")
        print("  2. copy the monster/ anim.mul + anim.idx into the client")
        print("  3. mobtypes.txt: if BOTH engines wrote one, merge them -")
        print("     each appended only its own lines, so concatenating the")
        print("     appended blocks onto the live file is safe. Check the")
        print("     tail of each before copying.")
        print("  4. gumpartLegacyMUL.uop is already patched in place.")
        print("  5. restart server + client, verify in-game.")
    print("=" * 68)
    return 2 if rc_total else 0


if __name__ == "__main__":
    sys.exit(main())
