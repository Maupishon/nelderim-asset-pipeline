"""uo3d/cli_gump.py - paperdoll gump (male / female) and item art of a 3D item, no Blender (numpy + Pillow only).

    python nelderim.py gump3d --body UO_Body_0x190.glb --item model.glb --kind shirt --out DIR [--anim 1992] [--client KLIENT]
                              [--ref-male 50469.png --ref-female 60469.png]
    python nelderim.py gump3d --body UO_Body_0x190.glb --item miecz.glb --kind weapon1h --out DIR --anim 1992 --client KLIENT

Worn item: drawn on the 3D body's rest pose (the body hides what is behind it); with --ref-* (ORIGINAL gump of the same kind of item, PNG
260 x 237) its outline box is fitted to that gump and its greys mapped to its levels. Weapon (weapon1h/polearm/axe2h/bow): upright in the
paperdoll's right hand like the client's mace gumps, leaning out; with --client the fist of body gump 12 holds the haft. Art: the same model
(uo3d/icon.py), for a weapon diagonal plus its mirror (the client's weapons come in pairs).
Writes gump_<anim+50000>_meski.png, gump_<anim+60000>_damski.png (worn), art.png [art_mirror.png], porownanie_*.png; prints RESULT_DIR.
Numbers from UO_Model3D (uo_render_paperdoll.py / uo_render_weapon_gump.py, with the author's permission). Not checked in game.
"""
import argparse, json, os, sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from uo3d import engine, gump, icon        # noqa: E402


def body_gumps(client):
    if not client:
        return {}
    import nelderim_core as C
    out = {}
    for gender, gid in (("male", 12), ("female", 13)):
        r = C.read_gump(client, gid)
        if r:
            w, h, px = r
            a = np.zeros((h, w, 4), np.uint8)
            for y in range(h):
                for x in range(w):
                    a[y, x] = C.v1555_to_rgba(px[y][x])
            out[gender] = a
    return out


def load_png(path):
    from PIL import Image
    if not path:
        return None
    a = np.asarray(Image.open(path).convert("RGBA")).copy()
    canvas = np.zeros((gump.GH, gump.GW, 4), np.uint8)
    h, w = min(gump.GH, a.shape[0]), min(gump.GW, a.shape[1])
    canvas[:h, :w] = a[:h, :w]
    return canvas


def main(argv=None):
    from PIL import Image
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--body", required=True); ap.add_argument("--item", required=True); ap.add_argument("--kind", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anim", type=int, default=None, help="numer animacji (body): nazwy gump_<anim+50000>_meski.png / <anim+60000>_damski.png")
    ap.add_argument("--client", default="", help="folder klienta: ciała gumpów 12/13 (pięść trzyma broń, podgląd porownanie_*.png)")
    ap.add_argument("--ref-male", default=""); ap.add_argument("--ref-female", default="")
    ap.add_argument("--turn", type=float, default=0.0); ap.add_argument("--scale", type=float, default=0.0)
    ap.add_argument("--skip", default=""); ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--pre-rot", default=""); ap.add_argument("--flip", action="store_true"); ap.add_argument("--fatten", type=float, default=1.0)
    ap.add_argument("--adjust", default="")
    ap.add_argument("--tilt", type=float, default=gump.TILT, help="broń: odchylenie od pionu w stopniach (góra na zewnątrz)")
    ap.add_argument("--grip-at", type=float, default=0.0, help="broń: dłoń trzyma tyle m nad końcem rękojeści (0 = auto: pół rękojeści pod jelcem, buzdygan 0.22)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    body = engine.Body(a.body)
    motion = None
    mp = engine.wp.find_motion(a.body)
    if mp:
        motion = json.load(open(mp, encoding="utf-8"))
    keys = engine.wp.load_shield_keys(engine.wp.find_shield_keys(a.body))
    item = engine.Item(a.item, a.kind, body, turn=a.turn, scale=a.scale, skip=[s for s in a.skip.split(",") if s],
                       saturation=a.saturation, motion=motion, shield_keys=keys, adjust=json.loads(a.adjust) if a.adjust else None,
                       pre_rot=("auto" if a.pre_rot.strip().lower() == "auto" else [float(x) for x in a.pre_rot.split(",")]) if a.pre_rot else None,
                       fatten_k=a.fatten, flip=a.flip)
    bg = body_gumps(a.client)
    is_held = a.kind in engine.wp.CLASS_OF_KIND
    if is_held:
        res = gump.held(item, bg, tilt=a.tilt, grip_at=a.grip_at)
    else:
        res = gump.worn(item, body, {"male": load_png(a.ref_male), "female": load_png(a.ref_female)})
    ids = {"male": (a.anim + 50000) if a.anim is not None else None, "female": (a.anim + 60000) if a.anim is not None else None}
    names = {"male": "meski", "female": "damski"}
    for gender, img in res.items():
        fn = f"gump_{ids[gender]}_{names[gender]}.png" if ids[gender] else f"gump_{names[gender]}.png"
        Image.fromarray(img).save(os.path.join(a.out, fn))
        gump.overlay(img, bg.get(gender)).save(os.path.join(a.out, f"porownanie_{names[gender]}.png"))
        engine.say("zapisano " + fn)
    art = icon.render_icon(a.item, size=44, skip=[s for s in a.skip.split(",") if s], saturation=a.saturation,
                           align=is_held, flip=a.flip, fatten=a.fatten, tilt=-45.0 if is_held else 0.0, face=is_held)
    art.save(os.path.join(a.out, "art.png"))
    if is_held:
        art.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(a.out, "art_mirror.png"))
    if is_held:
        engine.say("broń: klient nie ma damskich gumpów broni (60000 + AnimID), zrobiony tylko męski")
    print("RESULT_DIR " + os.path.abspath(a.out), flush=True)


if __name__ == "__main__":
    main()
