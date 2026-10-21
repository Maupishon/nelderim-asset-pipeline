"""uo3d/cli_holes.py - holes of an item .vd over the ORIGINAL body 400 (what the player sees through the item), no Blender.

    python nelderim.py holes --item-vd szata.vd --body-vd body400.vd [--body UO_Body_0x190.glb] [--actions 0 4 21] [--sheet 0:2 21:1] [--out DIR]

Prints per action the hole pixels by body part (hand / head: drawn over the item on purpose; arm / torso / leg: a fault) and the frames
with faults; --sheet writes holes_<action>_<dir>.png (every frame as the client shows it, x3, holes painted: black = arm, orange = torso,
blue = leg, white = hand / head). Without --body the parts are not told apart. Last line: RESULT_JSON {...}.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uo3d import holes as Hh        # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--item-vd", required=True); ap.add_argument("--body-vd", required=True)
    ap.add_argument("--body", default="", help="UO_Body_0x190.glb: części ciała w dziurach (dłoń, głowa, ramię, tułów, noga)")
    ap.add_argument("--actions", type=int, nargs="*")
    ap.add_argument("--sheet", nargs="*", default=[], help="akcja:kierunek, np. 0:2")
    ap.add_argument("--auto-sheets", type=int, default=0, help="arkusze dla N bloków (akcja, kierunek) z największymi błędnymi dziurami")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    glb = a.body if a.body and os.path.isfile(a.body) else None
    r = Hh.analyse(a.item_vd, a.body_vd, glb, a.actions)
    print("akcja  " + "  ".join("%6s" % p for p in Hh.PARTS) + ("" if glb else "   cialo"))
    for act, row in r["per_action"].items():
        print("%5d  " % act + "  ".join("%6d" % row[p] for p in Hh.PARTS) + ("" if glb else "  %6d" % row["body"]))
    bad = sum(r["total"][p] for p in Hh.FAULT)
    print("razem: dziury z ramieniem/tułowiem/nogą %d px w %d klatkach (dłoń/głowa %d px: zwykle celowo)" %
          (bad, len(r["fault_frames"]), r["total"]["hand"] + r["total"]["head"]) if glb else "razem: %d px dziur" % r["total"]["body"])
    files = []
    if not a.sheet and a.auto_sheets > 0 and r["fault_frames"]:
        by = {}
        for act, d, k, px in r["fault_frames"]:
            by[(act, d)] = by.get((act, d), 0) + px
        a.sheet = ["%d:%d" % ad for ad, _ in sorted(by.items(), key=lambda x: -x[1])[:a.auto_sheets]]
    if a.sheet:
        out = a.out or os.path.dirname(os.path.abspath(a.item_vd))
        os.makedirs(out, exist_ok=True)
        for s in a.sheet:
            act, d = (int(x) for x in s.split(":"))
            p = os.path.join(out, f"holes_{act}_{d}.png")
            Hh.sheet(a.item_vd, a.body_vd, glb, act, d).save(p); files.append(p)
            print("zapisano " + p)
    r["sheets"] = files
    r["fault_px"] = bad if glb else None
    print("RESULT_JSON " + json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
