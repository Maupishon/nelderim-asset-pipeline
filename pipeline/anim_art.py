#!/usr/bin/env python3
"""
anim_art.py - make a paperdoll gump (male + female) and an icon (art) PNG for an animation that
already lives in anim2..5.mul, straight from its idle frame.

    python anim_art.py --client <klient> --file 5 --slot 489 --body 429 [--name "Szata nekro"] --out <dir>
    python anim_art.py --client <klient> --file 5 --slot 489 --body 429 --have-dir <workspace/ultima-online> --json

WHAT IT DOES (read-only on the client; writes only PNGs + a recipe snippet into --out)
  1. Reads the idle frame (action 4, else first populated action) of the slot from anim<N>.idx/.mul.
  2. Registers the item frame onto the paperdoll: the same 256x256 UO canvas is used for the body
     frame (body 400 male / 401 female, anim.mul) and the item frame, so the item keeps its place
     relative to the body. The body frame is fitted (uniform scale + shift, best of 5 directions x
     mirror by silhouette IoU) onto the real paperdoll body gump (12 male / 13 female, 260x237) and the
     very same transform is applied to the item frame.
  3. Writes gump_<body+50000>_meski.png, gump_<body+60000>_damski.png (the AnimID+50000 / +10000
     rule used by this project), art_<body>.png, porownanie.png (body gump with the item on top)
     and recipe_anim_art.json (items with anim + gump_male/gump_female, ready for the patch step).
  4. SKIPPED when a gump for this body was already provided by another module (a
     gump_<body+50000>_meski.png under any --have-dir/*/gump/), so nothing hand-made is replaced.

QUALITY: an animation frame is ~60 px tall, the paperdoll ~200 px, so the result is an upscaled
approximation - good for robes/clothes (body covered), a starting point for hand-held items.
Not verified in game. Dry by nature: nothing in the client is touched.
"""
from __future__ import annotations
import argparse, json, os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))          # program root (uo3d package)
import nelderim_core as C
from anim_wire import slot_layout, IDX_REC

GUMP_W, GUMP_H = 260, 237
IDLE_ACTION = 4
ART_MAX = 44


def _frames(client, stem, n, slot, action, direction):
    from uo3d import vdread
    idxp, mulp = C.find(client, stem + ".idx"), C.find(client, stem + ".mul")
    if not idxp or not mulp:
        return None
    idx = open(idxp, "rb").read()
    start, nrec = slot_layout(n, slot)
    i = start + action * 5 + direction
    if (i + 1) * IDX_REC > len(idx) or action * 5 + direction >= nrec:
        return None
    lk, ln = struct.unpack_from("<ii", idx, i * IDX_REC)
    if lk < 0 or ln <= 0:
        return None
    with open(mulp, "rb") as fh:
        fh.seek(lk); data = fh.read(ln)
    fr = [f for f in vdread.decode_group(data, 0) if f["w"] and f["h"]]
    return fr or None


def _canvas(fr):
    from uo3d import vdread
    return vdread.canvas(fr)


def _bbox(a):
    ys, xs = np.nonzero(a[..., 3] > 0)
    if not len(ys):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def read_gump_rgba(client, gid):
    """paperdoll body gump from Gumpidx/Gumpart.mul -> RGBA array (H, W, 4) or None."""
    ip, mp = C.find(client, "Gumpidx.mul"), C.find(client, "Gumpart.mul")
    if not ip or not mp:
        return None
    pair = C.MulPair(ip, mp)
    r = pair.raw(gid)
    if not r:
        return None
    data, extra = r
    w, h = (extra >> 16) & 0xFFFF, extra & 0xFFFF
    if not w or not h:
        return None
    px = C.decode_gump(data, w, h)
    out = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        for x in range(w):
            out[y, x] = C.v1555_to_rgba(px[y][x])
    return out


def _fit(body_rgba, gump_rgba):
    """uniform scale + shift mapping the body silhouette's bbox onto the gump silhouette's bbox."""
    bb, gb = _bbox(body_rgba), _bbox(gump_rgba)
    if not bb or not gb:
        return None
    s = (gb[3] - gb[1]) / float(bb[3] - bb[1])
    cx_b, cx_g = (bb[0] + bb[2]) / 2.0, (gb[0] + gb[2]) / 2.0
    return dict(s=s, tx=cx_g - s * cx_b, ty=gb[1] - s * bb[1])


def _warp(rgba, fit, flip, size=(GUMP_W, GUMP_H)):
    """apply the fit transform to a 256x256 RGBA canvas -> size canvas, alpha thresholded to 0/255."""
    from PIL import Image
    im = Image.fromarray(rgba, "RGBA")
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    s = fit["s"]
    w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
    # premultiplied resize so transparent pixels do not bleed colour
    a = np.asarray(im).astype(np.float32)
    al = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * al, a[..., 3:4]], axis=2)
    chans = [Image.fromarray(pm[..., k].astype(np.float32), "F").resize((w, h), Image.BICUBIC) for k in range(4)]
    r = np.stack([np.asarray(c) for c in chans], axis=2)
    alpha = r[..., 3]
    rgb = np.where(alpha[..., None] > 1, r[..., :3] / np.maximum(alpha[..., None] / 255.0, 1e-3), 0)
    out = np.zeros((size[1], size[0], 4), np.uint8)
    ox, oy = int(round(fit["tx"])), int(round(fit["ty"]))
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + w, size[0]), min(oy + h, size[1])
    if x1 > x0 and y1 > y0:
        sub_rgb = np.clip(rgb[y0 - oy:y1 - oy, x0 - ox:x1 - ox], 0, 255).astype(np.uint8)
        sub_a = alpha[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        out[y0:y1, x0:x1, :3] = sub_rgb
        out[y0:y1, x0:x1, 3] = np.where(sub_a >= 128, 255, 0).astype(np.uint8)
    out[..., :3] = np.where(out[..., 3:4] > 0, out[..., :3], 0)
    return out


def _iou(a, b):
    ma, mb = a[..., 3] > 0, b[..., 3] > 0
    u = (ma | mb).sum()
    return float((ma & mb).sum()) / u if u else 0.0


def _best_registration(client, body_slot, gump_id):
    """-> (direction, flip, fit, iou, body_rgba_canvas) for body 400/401 vs paperdoll gump 12/13."""
    g = read_gump_rgba(client, gump_id)
    if g is None:
        return None
    best = None
    for d in range(5):
        fr = _frames(client, "anim", 4, body_slot, IDLE_ACTION, d)
        if not fr:
            continue
        cv = _canvas(fr[0])
        for flip in (False, True):
            src = cv[:, ::-1].copy() if flip else cv
            fit = _fit(src, g)
            if not fit:
                continue
            warped = _warp(cv, fit, flip, (g.shape[1], g.shape[0]))
            v = _iou(warped, g)
            if best is None or v > best[3]:
                best = (d, flip, fit, v)
    return (best + (g,)) if best else None


ART_STATIC_BASE = 0x4000


def _art_slot_free(client, item_id):
    ip, mp = C.find(client, "artidx.mul"), C.find(client, "art.mul")
    if not ip or not mp:
        return True
    return not C.MulPair(ip, mp).occupied(ART_STATIC_BASE + item_id)


def _gump_in_client(client, gid):
    ip, mp = C.find(client, "Gumpidx.mul"), C.find(client, "Gumpart.mul")
    return bool(ip and mp and C.MulPair(ip, mp).occupied(gid))


def make(client, n, slot, body, name, out, have_dirs=(), item_id=None, art_policy="free"):
    from PIL import Image
    gid_m, gid_f = body + 50000, body + 60000
    res = {"slot": slot, "body": body, "name": name, "gump_male_id": gid_m, "gump_female_id": gid_f}

    for root in have_dirs:
        if not root or not os.path.isdir(root):
            continue
        for d in os.listdir(root):
            p = os.path.join(root, d, "gump", f"gump_{gid_m}_meski.png")
            if os.path.isfile(p):
                res.update(skipped=True, reason=f"gump {gid_m} już przygotowany w innym module: {p}")
                return res

    fr = None
    for a in [IDLE_ACTION] + [x for x in range(35) if x != IDLE_ACTION]:
        for d in (1, 2, 3, 0, 4):
            fr = _frames(client, f"anim{n}", n, slot, a, d) if n != 1 else None
            if fr:
                res["action"], res["dir_item"] = a, d
                break
        if fr:
            break
    if not fr:
        res["error"] = f"Slot {slot} w anim{n}.mul nie ma klatek."
        return res

    os.makedirs(out, exist_ok=True)
    made = {}
    for gender, bslot, gid, gname in (("male", 400, 12, gid_m), ("female", 401, 13, gid_f)):
        reg = _best_registration(client, bslot, gid)
        if reg is None:
            res.setdefault("warnings", []).append(
                f"Brak gumpu ciała {gid} w Gumpart.mul albo klatek body {bslot} - pomijam wersję {gender}.")
            continue
        d_body, flip, fit, iou, g = reg
        # item frame: same direction as the body that fit best, so both share the 256x256 canvas pose
        ifr = _frames(client, f"anim{n}", n, slot, res["action"], d_body) or fr
        cv = _canvas(ifr[0])
        item = _warp(cv, fit, flip, (g.shape[1], g.shape[0]))
        suffix = "meski" if gender == "male" else "damski"
        path = os.path.join(out, f"gump_{gname}_{suffix}.png")
        Image.fromarray(item, "RGBA").save(path)
        cmp_im = Image.fromarray(g, "RGBA")
        cmp_im.alpha_composite(Image.fromarray(item, "RGBA"))
        cmp_im.save(os.path.join(out, f"porownanie_{suffix}.png"))
        made[gender] = path
        res[f"{gender}_registration_iou"] = round(iou, 3)
        res[f"{gender}_body_direction"] = d_body
        res[f"{gender}_mirrored"] = flip

    # art: crop the item's frame, shrink to fit 44x44 (never enlarge)
    cv = _canvas(fr[0])
    bb = _bbox(cv)
    if bb:
        crop = Image.fromarray(cv[bb[1]:bb[3], bb[0]:bb[2]], "RGBA")
        k = min(1.0, ART_MAX / max(crop.size))
        if k < 1.0:
            crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
        arr = np.asarray(crop).copy()
        arr[..., 3] = np.where(arr[..., 3] >= 128, 255, 0)
        art = os.path.join(out, f"art_{body}.png")
        Image.fromarray(arr, "RGBA").save(art)
        res["art"] = art

    item = {"name": name or f"anim {body}", "anim": body}
    if "male" in made:
        item["gump_male"] = os.path.basename(made["male"])
    if "female" in made:
        item["gump_female"] = os.path.basename(made["female"])
    res["gump_in_client"] = {"male": _gump_in_client(client, gid_m), "female": _gump_in_client(client, gid_f)}
    if item_id is None:
        res.setdefault("warnings", []).append(
            "Nie podano ID przedmiotu - receptura nie ma item_id, a uopatch.py go wymaga. "
            "Uzupełnij „item_id” w kroku 2 (przedmiot, który używa tej animacji).")
    else:
        item["item_id"] = hex(item_id)
        if res.get("art"):
            if art_policy == "always" or (art_policy == "free" and _art_slot_free(client, item_id)):
                item["art"] = os.path.basename(res["art"])
            elif art_policy == "free":
                res.setdefault("warnings", []).append(
                    f"Art dla przedmiotu {hex(item_id)} już istnieje w kliencie - nie dopisuję go do receptury "
                    "(PNG leży obok; dopisz pole „art” i „overwrite”: true, jeśli chcesz podmienić).")
    rp = os.path.join(out, "recipe_anim_art.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump({"items": [item]}, f, indent=2, ensure_ascii=False)
    res.update(out=out, recipe=rp, gumps=made, skipped=False)
    return res


def list_wired(client, n):
    """animations of anim<n>.mul that Bodyconv.def already points at: [{slot, body, name, type, actions}]."""
    import anim_wire as W
    path = C.find(client, "Bodyconv.def")
    if not path:
        raise ValueError("Brak Bodyconv.def w folderze klienta.")
    col = W.COL[n]
    data = {r["slot"]: r for r in W.scan_slots(client, n)}
    rows = []
    for line in open(path, encoding="latin-1"):
        head, _, comment = line.partition("#")
        v = head.split()
        if len(v) <= col:
            continue
        try:
            body, slot = int(v[0]), int(v[col])
        except ValueError:
            continue
        if slot < 0 or slot not in data:
            continue
        nm = comment.split(" - ", 1)[1].strip() if " - " in comment else comment.strip()
        d = data[slot]
        rows.append({"slot": slot, "body": body, "name": nm, "type": d["type"], "actions": d["actions"],
                     "actions_total": d["actions_total"], "wired": True})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="gump + art z klatki animacji (tylko PNG-i do --out)")
    ap.add_argument("--client", required=True)
    ap.add_argument("--file", type=int, default=5, choices=(2, 3, 4, 5))
    ap.add_argument("--list-wired", action="store_true", help="wypisz animacje już podpięte w Bodyconv.def i wyjdź")
    ap.add_argument("--slot", type=int)
    ap.add_argument("--body", type=int, help="body, pod którym animacja jest podpięta (gump = body+50000)")
    ap.add_argument("--item-id", default="", help="ID przedmiotu (0x2684 lub liczba) - potrzebne do wpisania w recepturze i do artu")
    ap.add_argument("--art", choices=("free", "always", "never"), default="free",
                    help="czy dopisać art do receptury: free = tylko gdy slot artu jest wolny")
    ap.add_argument("--name", default="")
    ap.add_argument("--out")
    ap.add_argument("--have-dir", action="append", default=[], help="folder z pracami (workspace/ultima-online); gump tam = pomiń")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.list_wired:
        try:
            rows = list_wired(a.client, a.file)
        except Exception as e:   # noqa: BLE001
            print("[BŁĄD  ] " + str(e)); print("RESULT_JSON " + json.dumps({"error": str(e)})); return 1
        for r in rows:
            print(f"[WIRED ] slot {r['slot']:>4} {r['type']:<8} body {r['body']:<5} {r['name']}")
        print("RESULT_JSON " + json.dumps({"wired": rows}, ensure_ascii=False))
        return 0
    if a.slot is None or a.body is None or not a.out:
        ap.error("--slot, --body i --out są wymagane (poza --list-wired)")
    try:
        iid = C.as_int(a.item_id) if str(a.item_id).strip() else None
        r = make(a.client, a.file, a.slot, a.body, a.name, a.out, a.have_dir, iid, a.art)
    except Exception as e:   # noqa: BLE001
        r = {"error": f"{type(e).__name__}: {e}"}
    if r.get("error"):
        print("[BŁĄD  ] " + r["error"])
    elif r.get("skipped"):
        print("[POMIŃ ] " + r["reason"])
    else:
        for g in r.get("gumps", {}).values():
            print("[GUMP  ] " + g)
        if r.get("art"):
            print("[ART   ] " + r["art"])
        for k in ("male_registration_iou", "female_registration_iou"):
            if k in r:
                print(f"[DOPASOWANIE] {k.split('_')[0]}: IoU ciała {r[k]}")
        for w in r.get("warnings", []):
            print("[WARN  ] " + w)
        print("[RECEPTURA] " + r.get("recipe", ""))
    if a.json:
        print("RESULT_JSON " + json.dumps(r, ensure_ascii=False))
    return 1 if r.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
