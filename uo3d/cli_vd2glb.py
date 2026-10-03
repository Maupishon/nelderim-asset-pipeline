"""uo3d/cli_vd2glb.py - turn an item .vd (UO sprites) into a 3D model (.glb) for trying on in the Fit Lab.

    python nelderim.py vd2glb --body UO_Body_0x190.glb --vd anim_0469.vd --out szata.glb [--action 4] [--frame 0]
                          [--voxel 0.02] [--no-mirror] [--dilate 0] [--kind robe]

Prints "RESULT_GLB <path>". The .glb is already placed on the body (rest pose); the Fit Lab loads it without auto-scaling.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # program root (uo3d package)
from uo3d import fromvd


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--body", required=True); ap.add_argument("--vd", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--action", type=int, default=4); ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--voxel", type=float, default=0.02, help="voxel size in metres (smaller = finer, slower)")
    ap.add_argument("--no-mirror", action="store_true", help="do not use the mirrored directions 5-7")
    ap.add_argument("--dilate", type=int, default=0, help="silhouette tolerance in pixels")
    ap.add_argument("--kind", default="")
    a = ap.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    fromvd.vd_to_glb(a.body, a.vd, a.out, a.action, a.frame, a.voxel, not a.no_mirror, a.dilate, a.kind)
    print("RESULT_GLB " + os.path.abspath(a.out), flush=True)


if __name__ == "__main__":
    main()
