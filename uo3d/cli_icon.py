"""uo3d/cli_icon.py - inventory icon (static art) from a 3D model, no Blender (numpy + Pillow only).

    python nelderim.py icon --item model.glb --out icon.png [--size 44] [--yaw -35] [--skip a,b] [--outline 0.55]

Writes a PNG with binary alpha (<= size px on the long side) and prints "RESULT_PNG <path>".
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # program root (uo3d package)
from uo3d import icon


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--item", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=44)
    ap.add_argument("--yaw", type=float, default=-35.0, help="obrót wokół pionu w stopniach")
    ap.add_argument("--skip", default="")
    ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--outline", type=float, default=0.55, help="1 = bez ciemnej krawędzi")
    ap.add_argument("--align", action="store_true", help="broń: ustaw długą oś pionowo, rękojeścią w dół")
    ap.add_argument("--flip", action="store_true", help="odwróć rękojeść i czubek")
    ap.add_argument("--fatten", type=float, default=1.0, help="pogrub smukły przedmiot (np. 2.6)")
    ap.add_argument("--head-scale", type=float, default=1.0, help="zmniejsz szeroką głowicę laski (np. 0.4), trzon zostaje")
    ap.add_argument("--fatten-thin", action="store_true", help="pogrub tylko cienki trzon (głowica laski zostaje)")
    ap.add_argument("--tilt", type=float, default=0.0, help="przechyl o kąt (-45 = klasyczna ukośna ikona)")
    ap.add_argument("--face", action="store_true", help="patrz prosto z przodu (bez nachylenia kamery)")
    a = ap.parse_args(argv)
    if not 8 <= a.size <= 256:
        sys.exit("[icon] --size: 8-256")
    im = icon.render_icon(a.item, size=a.size, yaw=a.yaw, skip=[s for s in a.skip.split(",") if s],
                          saturation=a.saturation, outline=a.outline,
                          align=a.align, fatten=a.fatten, flip=a.flip, tilt=a.tilt, face=a.face, fatten_thin=a.fatten_thin, head_scale=a.head_scale)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    im.save(a.out)
    print(f"[icon] {im.width}x{im.height} -> {a.out}")
    print("RESULT_PNG " + os.path.abspath(a.out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
