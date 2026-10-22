"""Export the UO_Model3D body (v13+) to the .glb the uo3d renderer reads, with the exact bone poses baked in.

    python uo3d/body_export.py --blend UO_Body_0x190.blend --out UO_Body_0x190.glb        (pip bpy 4.2, Python 3.11)
    blender -b UO_Body_0x190.blend -P uo3d/body_export.py -- --out UO_Body_0x190.glb     (any Blender 4.2+)

Why: the v13 rig scales limbs per frame (X/Z scale of upper_arm, forearm, hand, thigh, shin, foot, head) and forearm, hand, shin,
foot and the weapon bones do not inherit their parent's scale. glTF has no such flag, so Blender's glTF exporter re-expresses those
bones in their parent's (non-uniformly scaled) space and the decomposition into T/R/S loses the shear: up to 7 cm (2 px) off the
Blender pose. This script exports the normal .glb (all skin influences) and then appends, as `extras.uo3d` of the glTF JSON plus one
binary block, the joint world matrices Blender itself computes at every scene frame of every UO action, the bones that do not deform
(clavicles: their weights are dropped, as Blender does), and the rest head/tail of every bone (leg capsules of loose garments).
glbmodel.GLB uses them when present. Self-check at the end: the skinned body against Blender's evaluated mesh (mm).
"""
import json, os, struct, sys

import numpy as np
import bpy

C = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1.0]])      # Blender (Z up) -> glTF (Y up)
CI = np.linalg.inv(C)


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    out = blend = None
    for i, a in enumerate(argv):
        if a == "--out":
            out = argv[i + 1]
        elif a == "--blend":
            blend = argv[i + 1]
    if not out:
        sys.exit("body_export: --out PLIK.glb")
    return blend, os.path.abspath(out)


def export_glb(out):
    rig = bpy.data.objects["UO_Rig"]
    rig["uo_direction"] = 0
    for m in bpy.data.materials:                     # exporters understand a plain Principled BSDF: bypass the "UO look" mix (as UO_Model3D's export.py)
        if m.use_nodes:
            nodes = m.node_tree.nodes
            o = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
            b = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
            if o and b:
                m.node_tree.links.new(b.outputs["BSDF"], o.inputs["Surface"])
    body = bpy.data.objects["UO_Body"]
    if body.data.shape_keys:
        body.shape_key_clear()
    bpy.ops.object.select_all(action="DESELECT")
    for name in ("UO_Rig", "UO_Body"):
        bpy.data.objects[name].select_set(True)
    bpy.context.view_layer.objects.active = rig
    rig.animation_data.action = bpy.data.actions.get("04_stand") or rig.animation_data.action
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_animations=True,
                              export_animation_mode="ACTIONS", export_skins=True, export_all_influences=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_cameras=False,
                              export_lights=False, export_yup=True, export_apply=False, export_force_sampling=True,
                              export_optimize_animation_size=False)


def read_glb(path):
    d = open(path, "rb").read()
    off, ch = 12, []
    while off < len(d):
        n, t = struct.unpack_from("<I4s", d, off)
        ch.append((t, d[off + 8:off + 8 + n])); off += 8 + n
    return json.loads(ch[0][1]), bytearray(ch[1][1])


def write_glb(path, js, binary):
    while len(binary) % 4:
        binary += b"\0"
    j = json.dumps(js, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)
    total = 12 + 8 + len(j) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(j), b"JSON")); f.write(j)
        f.write(struct.pack("<I4s", len(binary), b"BIN\0")); f.write(bytes(binary))


def bake(out):
    js, binary = read_glb(out)
    rig = bpy.data.objects["UO_Rig"]
    names = [js["nodes"][j]["name"] for j in js["skins"][0]["joints"]]
    acc = js["accessors"][js["skins"][0]["inverseBindMatrices"]]
    bv = js["bufferViews"][acc["bufferView"]]
    o = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    ibm = np.frombuffer(bytes(binary[o:o + 64 * acc["count"]]), np.float32).reshape(-1, 4, 4).transpose(0, 2, 1).astype(float)
    ibm_inv = np.linalg.inv(ibm)
    A0 = np.array(rig.matrix_world)
    pose, chunks, pos = {}, [], len(binary) + (-len(binary) % 4)
    binary += b"\0" * (-len(binary) % 4)
    acts = sorted([a for a in bpy.data.actions if "uo_action" in a], key=lambda a: int(a["uo_action"]))
    for act in acts:
        rig.animation_data.action = act
        f0, f1 = (int(round(x)) for x in act.frame_range)
        mats = []
        for f in range(f0, f1 + 1):
            bpy.context.scene.frame_set(f)
            A = np.array(rig.matrix_world)
            W = []
            for k, nm in enumerate(names):
                pb = rig.pose.bones[nm]
                S = A @ np.array(pb.matrix) @ np.linalg.inv(np.array(pb.bone.matrix_local)) @ np.linalg.inv(A0)
                W.append(C @ S @ CI @ ibm_inv[k])
            mats.append(W)
        arr = np.asarray(mats, np.float32)                       # (frames, joints, 4, 4) row-major
        raw = arr.tobytes()
        js["bufferViews"].append({"buffer": 0, "byteOffset": pos, "byteLength": len(raw)})
        pose[act.name] = {"bufferView": len(js["bufferViews"]) - 1, "first": f0, "count": f1 - f0 + 1}
        binary += raw; pos += len(raw)
    js["buffers"][0]["byteLength"] = len(binary)
    bones = {}
    for b in rig.data.bones:
        h = C @ (A0 @ np.append(np.array(b.head_local), 1))
        t = C @ (A0 @ np.append(np.array(b.tail_local), 1))
        bones[b.name] = {"head": [round(float(x), 5) for x in h[:3]], "tail": [round(float(x), 5) for x in t[:3]]}
    js.setdefault("extras", {})["uo3d"] = {
        "version": 1, "source": os.path.basename(bpy.data.filepath), "fps": 24,
        "nondeform": [b.name for b in rig.data.bones if not b.use_deform],
        "no_inherit_scale": [b.name for b in rig.data.bones if b.inherit_scale != "FULL"],
        "bones": bones, "pose": pose}
    write_glb(out, js, binary)
    return acts


def self_check(out, acts):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from uo3d.glbmodel import GLB
    g = GLB(out)
    rig, body = bpy.data.objects["UO_Rig"], bpy.data.objects["UO_Body"]
    rest = np.array([body.matrix_world @ v.co for v in body.data.vertices])
    rest = np.c_[rest[:, 0], rest[:, 2], -rest[:, 1]]
    idx = []
    for p in g.pos:                                              # glb vertices are split at UV seams: match by rest position
        idx.append(int(np.argmin(((rest - p) ** 2).sum(1))))
    idx = np.array(idx)
    worst = 0.0
    for act in acts[::7]:
        rig.animation_data.action = act
        f = int(round(act.frame_range[0])) + 3
        if f > act.frame_range[1]:
            f = int(round(act.frame_range[0]))
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get(); ev = body.evaluated_get(dg); me = ev.to_mesh()
        B = np.array([body.matrix_world @ v.co for v in me.vertices]); ev.to_mesh_clear()
        B = np.c_[B[:, 0], B[:, 2], -B[:, 1]][idx]
        P, _ = g.skinned(act.name, f / 24.0)
        e = np.linalg.norm(P - B, axis=1)
        worst = max(worst, float(e.max()))
        print("body_export: %-22s frame %3d  mean %.3f mm  max %.3f mm" % (act.name, f, e.mean() * 1000, e.max() * 1000))
    print("body_export: OK, najwiekszy blad %.2f mm" % (worst * 1000) if worst < 0.002 else
          "body_export: UWAGA, blad %.1f mm - sprawdz model" % (worst * 1000))


def main():
    blend, out = args()
    if blend:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    if "UO_Rig" not in bpy.data.objects or "UO_Body" not in bpy.data.objects:
        sys.exit("body_export: to nie jest plik UO_Model3D (brak UO_Rig / UO_Body)")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    export_glb(out)
    acts = bake(out)
    print("RESULT_GLB " + out)
    self_check(out, acts)


main()
