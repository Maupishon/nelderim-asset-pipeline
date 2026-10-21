"""uo3d/cli_creature.py - an animated, skinned creature .glb -> UO animation (.vd type 0 High / 1 Low), 5 directions.

    python nelderim.py creature --model smok.glb --actions mapa_akcji.json --out smok.vd [--type high|low]
                                [--height 2.4] [--face +z|-z|+x|-x] [--yaw 0] [--smooth 1] [--min-dark 24]
    python nelderim.py creature --model smok.glb --list          # animations found in the model
    python nelderim.py creature --template high --out mapa.json   # every UO action with a prompt, frames, loop (examples/creature_prompts.json)

mapa_akcji.json: {"0": {"clip": "Walk", "frames": 10, "loop": true}, "1": "Idle", "4": {"clip": "Bite", "frames": 7}}
(klucz = numer akcji UO, clip = nazwa animacji w modelu, frames = liczba klatek UO, loop = pętla; chód „w miejscu”).
Prints "RESULT_VD <path>". The .vd goes to vd_inject / anim_import (anim.mul or anim2-5.mul) like any other.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # program root (uo3d package)
from uo3d import creature as C


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="zrigowany i animowany .glb")
    ap.add_argument("--actions", help="JSON: akcja UO -> animacja w modelu")
    ap.add_argument("--out")
    ap.add_argument("--type", choices=list(C.TYPES), default="high", help="high = 22 akcje (anim.mul 0-199), low = 13 akcji (200-399)")
    ap.add_argument("--height", type=float, default=1.8, help="wysokość modelu w metrach (UO: 36 px = 1 m; człowiek ok. 1.8)")
    ap.add_argument("--face", choices=list(C.FACE_YAW), default="+z", help="w którą stronę model patrzy w pliku")
    ap.add_argument("--yaw", type=float, default=0.0, help="dodatkowy obrót wokół pionu (stopnie)")
    ap.add_argument("--smooth", type=int, default=0)
    ap.add_argument("--outline", type=float, default=0.38)
    ap.add_argument("--min-dark", type=int, default=0)
    ap.add_argument("--list", action="store_true", help="tylko wypisz animacje modelu")
    ap.add_argument("--template", choices=list(C.TYPES), help="zapisz do --out szablon mapy akcji (akcje UO z promptami), nic nie renderuj")
    a = ap.parse_args(argv)
    if a.template:
        if not a.out:
            ap.error("--template wymaga --out")
        import json
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(C.action_template(a.template), fh, ensure_ascii=False, indent=1)
        print(f"zapisano szablon {a.template}: {a.out} (zmień „clip” na nazwy animacji z modelu, usuń akcje, których nie masz)")
        return 0
    if not a.model:
        ap.error("--model jest wymagany")
    if a.list:
        g = C.GLB(a.model)
        for name in g.anims:
            print(f"{name}\t{g.duration(name):.2f} s")
        return 0
    if not a.actions or not a.out:
        ap.error("--actions i --out są wymagane (albo --list)")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    C.render(a.model, C.load_actions(a.actions), a.out, a.type, a.height, a.face, a.yaw, a.smooth, a.outline, a.min_dark)
    print("RESULT_VD " + os.path.abspath(a.out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
