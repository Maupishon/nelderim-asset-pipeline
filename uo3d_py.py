"""uo3d_py.py - render a 3D item onto the UO body WITHOUT Blender (numpy + Pillow only).

    python uo3d_py.py --body UO_Body_0x190.glb --item model.glb --kind shirt --out DIR --name NAME [--actions 0 4 9] [--turn 0]
                      [--scale 0] [--skip eyes,body] [--saturation 1] [--outline 0.38]

Writes DIR/NAME.vd (UOFiddler animation, type 2, 35 actions x 5 directions) and prints "RESULT_VD <path>".
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uo3d import engine


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--body", required=True); ap.add_argument("--item", required=True)
    ap.add_argument("--kind", required=True, choices=sorted(set(engine.EXTENTS) | set(engine.wp.CLASS_OF_KIND) | {"shield"})); ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="item"); ap.add_argument("--actions", nargs="*", type=int, default=[])
    ap.add_argument("--turn", type=float, default=0); ap.add_argument("--scale", type=float, default=0)
    ap.add_argument("--skip", default=""); ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--outline", type=float, default=0.38); ap.add_argument("--margin", type=float, default=0.01)
    ap.add_argument("--metal", choices=["auto", "yes", "no"], default="auto")
    ap.add_argument("--body-vd", default="", help="original body anim 400 .vd: the body hides the item exactly along its outline (EXACT_BODY)")
    ap.add_argument("--horse-vd", default="", help="original horse (body 0xC8) .vd: mounted actions 23-29 with the horse hiding the item")
    ap.add_argument("--motion", default="", help="UO_Model3D pipeline/weapon_motion.json (weapons); default: found next to the .glb")
    ap.add_argument("--shield-keys", default="", help="UO_Model3D pipeline/uo_shield_keys.py (shields); default: found next to the .glb")
    ap.add_argument("--weapon-ref", type=int, default=None, help="original weapon whose head orientation to copy (anim id)")
    ap.add_argument("--roll", type=float, default=None, help="weapon roll offset in degrees (overrides --weapon-ref)")
    ap.add_argument("--cloth", action="store_true", help="simulate the cloth of robe / skirt / cloak (slower)")
    a = ap.parse_args(argv)
    horse = os.path.isfile(a.horse_vd) if a.horse_vd else False
    acts = a.actions or [i for i in range(35) if horse or i not in engine.MOUNTED]
    if any(not 0 <= x < 35 for x in acts):
        sys.exit("[uo3d] akcje: 0-34")
    os.makedirs(a.out, exist_ok=True)
    engine.say("wczytuję ciało " + a.body)
    body = engine.Body(a.body)
    engine.say("wczytuję model " + a.item)
    import json
    motion = None
    mpath = a.motion or engine.wp.find_motion(a.body)
    if mpath and os.path.isfile(mpath):
        motion = json.load(open(mpath, encoding="utf-8"))
    keys = engine.wp.load_shield_keys(a.shield_keys or engine.wp.find_shield_keys(a.body))
    item = engine.Item(a.item, a.kind, body, turn=a.turn, scale=a.scale, skip=[s for s in a.skip.split(",") if s],
                       saturation=a.saturation, metal={"auto": None, "yes": True, "no": False}[a.metal], motion=motion,
                       shield_keys=keys, ref=a.weapon_ref, roll_deg=a.roll)
    body_masks = engine.vdread.alpha_masks(a.body_vd) if a.body_vd and os.path.isfile(a.body_vd) else None
    horse_masks = engine.vdread.alpha_masks(a.horse_vd) if horse else None
    engine.say("ciało: " + ("dokładna sylwetka z oryginału (EXACT_BODY)" if body_masks else "tylko model 3D") + "; koń: " + ("tak" if horse_masks else "nie"))
    sim = None
    if a.cloth and a.kind in ("robe", "skirt", "cloak"):
        from uo3d import cloth
        sim = cloth.make_sim(body, item)
    engine.say(f"skala {item.scale:.3f}, wierzchołków {len(item.pos)}, trójkątów {len(item.tri)}")
    last = [-1]

    def prog(d, t):
        pct = int(100 * d / t)
        if pct // 5 != last[0] // 5:
            last[0] = pct; engine.say(f"postęp {pct}%")
    out = os.path.join(a.out, a.name + ".vd")
    engine.render_layer(body, item, acts, out, outline_f=a.outline, margin=a.margin, progress=prog, body_masks=body_masks,
                        horse_masks=horse_masks, cloth_sim=sim)
    print("RESULT_VD " + out, flush=True)


if __name__ == "__main__":
    main()
