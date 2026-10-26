"""uo3d/cli_tattoo.py - decor tattoos (layers 0x20-0x25 of the ClassicUO fork): decal on a limb, relief on the torso, paperdoll gumps, icon.

    python nelderim.py tattoo arm   --model arm.glb --body UO_Body_0x190.glb --anim 853 --gump-m g12.png --gump-f g13.png --out DIR
    python nelderim.py tattoo torso --design tygrys.jpg --body UO_Body_0x190.glb --anim 854 --gump-m g12.png --gump-f g13.png --out DIR
                                    [--width 0.24 --centre-y 1.30 --centre-x 91 --grid 200]

arm    a right-arm model with a tattoo texture -> DIR/tatuaz_decal.glb (render: `nelderim.py uo3d --item DIR/tatuaz_decal.glb --kind arms
       --adjust '{"fit": false}' --own-side R --occlude-torso ...`) and the gumps gump_<50000+anim>_meski.png / gump_<60000+anim>_damski.png.
torso  a 2D design on a white card -> the relief DIR/tatuaz_tors.glb (+ _render.glb without the back: `--kind plate --occlude-torso`), the texture,
       the gumps (the female one hides the tattoo under the bra) and the 44 px icon art_<anim>.png.
--gump-m / --gump-f: the body gumps 12 and 13 as RGBA PNG (260 x 237). Every output goes to DIR; the client is never touched.
Each command prints RESULT_JSON {...}. Needs scipy.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    from PIL import Image
    from uo3d import tattoo as T
    from uo3d.glbmodel import GLB
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("arm", "torso", "sleeve", "leg"):
        p = sub.add_parser(name)
        p.add_argument("--body", required=True, help="UO_Body_0x190.glb")
        p.add_argument("--anim", type=int, required=True, help="body id of the item animation (the gump is 50000 / 60000 + this)")
        p.add_argument("--gump-m", required=True); p.add_argument("--gump-f", required=True)
        p.add_argument("--out", required=True)
        if name == "leg":
            p.add_argument("--design", required=True, help="a coloured design on white; white (also inside it) is the skin")
            p.add_argument("--crop", default="", help="x0,y0,x1,y1 in the design")
            p.add_argument("--side", choices=["L", "R"], default="L", help="the leg (the polylines of both are in LEG_POLY)")
            p.add_argument("--span", type=float, default=260.0, help="degrees of the leg's circumference the design's width covers (front in the middle)")
            p.add_argument("--t0", type=float, default=0.05, help="where the design's top lies on the leg: 0 = hip joint, 1 = ankle")
            p.add_argument("--t1", type=float, default=1.0, help="where its bottom lies")
            p.add_argument("--offset", type=float, default=0.004, help="m the decal lies off the skin")
            p.add_argument("--tex-len", type=int, default=256, help="texels along the leg in the render texture (a sprite pixel is ~3 cm)")
            p.add_argument("--cover", type=float, default=0.45, help="share of ink under a pixel that makes it ink (lower = bolder)")
        elif name == "sleeve":
            p.add_argument("--design", required=True, help="black ink on white (e.g. a flash sheet); only the biggest pattern is used")
            p.add_argument("--crop", default="", help="x0,y0,x1,y1 in the design: one sleeve of a sheet (without the titles)")
            p.add_argument("--side", choices=["L", "R"], default="L")
            p.add_argument("--offset", type=float, default=0.004, help="m the decal lies off the skin")
            p.add_argument("--tex-len", type=int, default=200, help="texels along the arm in the render texture (a sprite pixel is ~3 cm)")
            p.add_argument("--cover", type=float, default=0.42, help="share of ink under a gump / texture pixel that makes it black (lower = darker, higher = more skin shows)")
        elif name == "arm":
            p.add_argument("--model", required=True)
            p.add_argument("--scale", type=float, default=0.205, help="model units -> m (shoulder joint to wrist of the body arm)")
            p.add_argument("--wrist-x", type=float, default=1.45, help="x of the wrist in the model (the hand is cut off there)")
            p.add_argument("--offset", type=float, default=0.004, help="m the decal lies off the skin")
            p.add_argument("--threshold", type=float, default=0.12, help="colour distance from the skin tone of the model that counts as ink")
        else:
            p.add_argument("--design", required=True)
            p.add_argument("--width", type=float, default=0.24, help="m, width of the tattoo on the chest")
            p.add_argument("--centre-y", type=float, default=1.30, help="m, height of its centre (sternum)")
            p.add_argument("--centre-x", type=float, default=91.0, help="px, the torso's midline on the gump")
            p.add_argument("--grid", type=int, default=200, help="cells across the relief (200 = 110k triangles, 120 = 40k)")
    sh = sub.add_parser("shade", help="finish a rendered tattoo .vd: the ink takes the shading of the skin, a soft edge (render it with --outline 1)")
    sh.add_argument("--item-vd", required=True); sh.add_argument("--body-vd", required=True, help="body400.vd (the original body 400)")
    sh.add_argument("--out", required=True, help="the shaded .vd")
    sh.add_argument("--lift", type=float, default=0.12, help="share of the skin colour mixed into the ink (a black ink becomes dark grey)")
    sh.add_argument("--edge", type=float, default=0.5, help="how much the edge pixels fade into the skin (0 = not at all)")
    a = ap.parse_args(argv)
    if a.cmd == "shade":
        from uo3d.tattoo_shade import shade_vd
        n = shade_vd(a.item_vd, a.body_vd, a.out, lift=a.lift, edge=a.edge)
        print("RESULT_JSON " + json.dumps({"vd": a.out, "frames": n}))
        return 0
    os.makedirs(a.out, exist_ok=True)
    g = GLB(a.body)
    gm = os.path.join(a.out, f"gump_{50000 + a.anim}_meski.png"); gf = os.path.join(a.out, f"gump_{60000 + a.anim}_damski.png")
    res = {"gump_male": gm, "gump_female": gf}
    if a.cmd == "leg":
        pt = T.patch_prepare(Image.open(a.design), [int(v) for v in a.crop.split(",")] if a.crop else None)
        glb = os.path.join(a.out, "tatuaz_decal.glb"); tr = (a.t0, a.t1)
        d = T.patch_decal(pt, g, a.side, glb, tr, a.span, a.offset, a.tex_len, a.cover)
        n1 = T.patch_gump(pt, a.side, "12", a.gump_m, gm, tr, a.span, cover=a.cover); n2 = T.patch_gump(pt, a.side, "13", a.gump_f, gf, tr, a.span, cover=a.cover)
        res.update(decal=glb, ink_px=[n1, n2], **{k: v for k, v in d.items() if k != "length"})
        T.preview(a.gump_m, gm, gm.replace(".png", "_podglad.png"), box=(50, 120, 140, 226), zoom=6)
        T.preview(a.gump_f, gf, gf.replace(".png", "_podglad.png"), box=(50, 120, 140, 226), zoom=6)
    elif a.cmd == "sleeve":
        sl = T.sleeve_prepare(Image.open(a.design), [int(v) for v in a.crop.split(",")] if a.crop else None)
        glb = os.path.join(a.out, "tatuaz_decal.glb")
        d = T.sleeve_decal(sl, g, a.side, glb, a.offset, a.tex_len, a.cover)
        n1 = T.sleeve_gump(sl, a.side, "12", a.gump_m, gm, cover=a.cover); n2 = T.sleeve_gump(sl, a.side, "13", a.gump_f, gf, cover=a.cover)
        res.update(decal=glb, ink_px=[n1, n2], **{k: v for k, v in d.items() if k != "length"})
        T.preview(a.gump_m, gm, gm.replace(".png", "_podglad.png"), box=(60, 70, 150, 140))
        T.preview(a.gump_f, gf, gf.replace(".png", "_podglad.png"), box=(60, 70, 150, 140))
    elif a.cmd == "arm":
        glb = os.path.join(a.out, "tatuaz_decal.glb")
        d = T.arm_decal(a.model, g, glb, a.scale, a.wrist_x, a.offset, a.threshold)
        n1 = T.arm_gump(d, a.gump_m, "12", gm); n2 = T.arm_gump(d, a.gump_f, "13", gf)
        res.update(decal=glb, ink_vertices=d["ink_vertices"], decal_triangles=d["decal_triangles"], ink_px=[n1, n2])
        T.preview(a.gump_m, gm, gm.replace(".png", "_podglad.png"), box=(30, 70, 110, 135))
        T.preview(a.gump_f, gf, gf.replace(".png", "_podglad.png"), box=(30, 70, 110, 135))
    else:
        surf = T.front_surface(g)
        glb = os.path.join(a.out, "tatuaz_tors.glb"); top = os.path.join(a.out, "tatuaz_tors_render.glb")
        tex, st = T.relief(Image.open(a.design), surf, glb, a.width, (0.0, a.centre_y), a.grid, top_only_glb=top)
        tex_png = os.path.join(a.out, "tatuaz_tors_tekstura.png"); Image.fromarray(tex, "RGBA").save(tex_png)
        bra = T.bra_mask(Image.open(a.gump_f))
        c = (a.centre_x, T.FEET_Y - a.centre_y * T.PXM)
        n1 = T.torso_gump(tex, a.gump_m, gm, c, a.width); n2 = T.torso_gump(tex, a.gump_f, gf, c, a.width, bra)
        art = os.path.join(a.out, f"art_{a.anim}.png"); T.icon(tex).save(art)
        T.preview(a.gump_m, gm, gm.replace(".png", "_podglad.png")); T.preview(a.gump_f, gf, gf.replace(".png", "_podglad.png"), bra=bra)
        res.update(relief=glb, relief_render=top, texture=tex_png, icon=art, ink_px=[n1, n2], **st)
    print("RESULT_JSON " + json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
