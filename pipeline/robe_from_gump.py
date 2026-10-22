#!/usr/bin/env python3
"""
robe_from_gump.py - a hooded robe animation (.vd, 35 actions x 5 directions) straight from a paperdoll gump PNG.

    python robe_from_gump.py --gump gump_50403_m.png --toolkit <SpriteMotion-UO-Toolkit> --client <klient> \
                             --key szata_arcymaga --title "Szata Arcymaga" [--graphic 0x2684] [--base-anim 970] [--no-hood] [--shade-transfer 1.5]

WHAT IT DOES (the route that produced the alchemist robe)
  1. design    = the robe cut out of the gump (alpha bbox) enlarged x4 with LANCZOS -> <toolkit>/workspace/ultima-online/<key>/design.png
  2. build     = outfit-lab/build_item.py on the base item (default 0x2684 Hooded Shroud), all 35 actions, face + hands cut out
  3. hood      = hood_blend.py (hood takes the robe's tone and grain; skip with --no-hood)
  3a. cover    = cover_fill.py: the robe covers everything the original robe covered (no body showing through); off with --no-cover-fill
  3b. shade    = shade_transfer.py when --shade-transfer K is given (shadows of the original robe, K = 1.5 matches its contrast)
  4. pack      = outfit-lab/atlas_to_vd.py with the original animation of the base item (extracted from anim.mul when missing)
  5. verify    = outfit-lab/verify.py (errors must be [] and missingSequences 0; exit code 1 is normal)
Result: <toolkit>/workspace/ultima-online/vd/<key>_<base-anim>.vd; the path is printed as RESULT_VD.
The .vd is a copy of the BASE animation slot's layout (body 400 rig): import it into an EMPTY slot with anim_import.py,
never into the base slot. Needs numpy + Pillow and the toolkit's region masks.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hood_blend                                   # noqa: E402
import shade_transfer                               # noqa: E402
import cover_fill                                   # noqa: E402


def run(cmd, cwd, env, ok=(0,)):
    print("[RUN    ] " + " ".join(str(c) for c in cmd[1:3]) + " ...", flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in ok:
        print(r.stdout[-1500:] + r.stderr[-1500:])
        raise SystemExit(f"[BŁĄD  ] {os.path.basename(str(cmd[1]))} zakończył się kodem {r.returncode}")
    return r.stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gump", required=True, help="PNG paperdoll gump with transparent background (robe only)")
    ap.add_argument("--toolkit", required=True)
    ap.add_argument("--client", required=True, help="client folder (anim.idx/anim.mul, tiledata.mul)")
    ap.add_argument("--key", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--graphic", default="0x2684")
    ap.add_argument("--base-anim", type=int, default=970)
    ap.add_argument("--hide-labels", nargs="*", default=["1", "5"])
    ap.add_argument("--actions", nargs="*", default=[], help="only these actions (a test run); default all 35")
    ap.add_argument("--no-hood", action="store_true")
    ap.add_argument("--no-cover-fill", action="store_true", help="nie uzupełniaj dziur, w których oryginalna szata miała materiał")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--shade-transfer", type=float, default=0.0, metavar="K",
                    help="przenieś cieniowanie z oryginalnej szaty (pachy, wnętrze rękawów, pas); 1.5 = kontrast oryginału, 0 = wyłączone")
    a = ap.parse_args(argv)

    tk = os.path.abspath(a.toolkit)
    ws = os.path.join(tk, "workspace", "ultima-online")
    work, vdd = os.path.join(ws, a.key), os.path.join(ws, "vd")
    lab = os.path.join(work, "lab")
    os.makedirs(lab, exist_ok=True); os.makedirs(vdd, exist_ok=True)
    env = dict(os.environ, SPRITEMOTION_UO_SOURCE=a.client, PYTHONIOENCODING="utf-8")
    py, of = sys.executable, os.path.join(tk, "games", "ultima-online", "outfit-lab")

    g = Image.open(a.gump).convert("RGBA")
    box = g.getchannel("A").point(lambda v: 255 if v >= 64 else 0).getbbox()
    if not box:
        raise SystemExit("[BŁĄD  ] gump jest pusty (cały przezroczysty)")
    c = g.crop(box)
    design = os.path.join(work, "design.png")
    c.resize((c.width * a.scale, c.height * a.scale), Image.LANCZOS).save(design)
    print(f"[DESIGN ] {c.width}x{c.height} -> {c.width * a.scale}x{c.height * a.scale}  {design}")

    cmd = [py, os.path.join(of, "build_item.py"), "--source", a.client, "--graphic", a.graphic, "--design", design,
           "--out", lab, "--key", a.key, "--title", a.title or a.key]
    if a.hide_labels:
        cmd += ["--hide-labels", *a.hide_labels]
    if a.actions:
        cmd += ["--actions", *a.actions]
    run(cmd, tk, env)

    if not a.no_hood:
        masks = os.path.join(ws, "region-audit", "all-actions-region-pass", "frames")
        mark = os.path.join(lab, hood_blend.MARK)
        if os.path.exists(mark):
            os.remove(mark)
        done, skipped = hood_blend.run(lab, masks)
        print(f"[HOOD   ] {done} klatek, {skipped} pominięto")

    if not a.no_cover_fill:
        mark = os.path.join(lab, cover_fill.MARK)
        if os.path.exists(mark):
            os.remove(mark)
        frames, pixels = cover_fill.run(lab)
        print(f"[COVER  ] uzupełniono {pixels} px w {frames} klatkach")

    if a.shade_transfer > 0:
        mark = os.path.join(lab, shade_transfer.MARK)
        if os.path.exists(mark):
            os.remove(mark)
        done, skipped = shade_transfer.run(lab, a.shade_transfer)
        print(f"[SHADE  ] cieniowanie x{a.shade_transfer:g}: {done} klatek, {skipped} pominięto")

    orig = os.path.join(vdd, f"anim_{a.base_anim:04d}.vd")
    if not os.path.exists(orig):
        run([py, os.path.join(tk, "tools", "vd", "mul2vd.py"), os.path.join(a.client, "anim.idx"),
             os.path.join(a.client, "anim.mul"), vdd, a.base_anim], tk, env)
    out_vd = os.path.join(vdd, f"{a.key}_{a.base_anim:04d}.vd")
    run([py, os.path.join(of, "atlas_to_vd.py"), lab, a.key, orig, out_vd], tk, env)
    v = run([py, os.path.join(of, "verify.py"), lab], tk, env, ok=(0, 1))
    try:
        rep = json.loads(v[v.index("{"):])
        print(f"[VERIFY ] errors={rep.get('errors')} missingSequences={rep.get('missingSequences')}")
    except (ValueError, KeyError):
        print("[VERIFY ] (nie odczytano raportu)")
    print("RESULT_VD " + out_vd, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
