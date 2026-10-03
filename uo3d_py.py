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
    ap.add_argument("--kind", required=True, choices=sorted(engine.EXTENTS)); ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="item"); ap.add_argument("--actions", nargs="*", type=int, default=[])
    ap.add_argument("--turn", type=float, default=0); ap.add_argument("--scale", type=float, default=0)
    ap.add_argument("--skip", default=""); ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--outline", type=float, default=0.38); ap.add_argument("--margin", type=float, default=0.01)
    ap.add_argument("--metal", choices=["auto", "yes", "no"], default="auto")
    a = ap.parse_args(argv)
    acts = a.actions or [i for i in range(35) if i not in engine.MOUNTED]
    if any(not 0 <= x < 35 for x in acts):
        sys.exit("[uo3d] akcje: 0-34")
    os.makedirs(a.out, exist_ok=True)
    engine.say("wczytuję ciało " + a.body)
    body = engine.Body(a.body)
    engine.say("wczytuję model " + a.item)
    item = engine.Item(a.item, a.kind, body, turn=a.turn, scale=a.scale, skip=[s for s in a.skip.split(",") if s],
                       saturation=a.saturation, metal={"auto": None, "yes": True, "no": False}[a.metal])
    engine.say(f"skala {item.scale:.3f}, wierzchołków {len(item.pos)}, trójkątów {len(item.tri)}")
    last = [-1]

    def prog(d, t):
        pct = int(100 * d / t)
        if pct // 5 != last[0] // 5:
            last[0] = pct; engine.say(f"postęp {pct}%")
    out = os.path.join(a.out, a.name + ".vd")
    engine.render_layer(body, item, acts, out, outline_f=a.outline, margin=a.margin, progress=prog)
    print("RESULT_VD " + out, flush=True)


if __name__ == "__main__":
    main()
