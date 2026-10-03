"""
uo3d_job.py - runs INSIDE Blender (headless) for nelderim_hub: brings a 3D model onto the UO body of UO_Model3D,
binds it to the skeleton and renders the layer to a .vd.

    blender -b --python uo3d_job.py -- spec.json

It contains no format logic. It only chains the scripts of UO_Model3D/pipeline exactly like their own tests do
(test_import_item.py, run_render_headless.py): uo_import_item -> uo_materials -> uo_fit_item -> uo_bind_item
(weapons: uo_place_weapon, shields: uo_place_shield first) -> render_uo_layer. The scripts are read from files, and
their constants are replaced by regex (the same way run_render_headless.py does it), so nothing is edited on disk.

spec.json keys: blend, pipeline, out, name, file, kind (uo_import_item KIND, "" for weapons), part (uo_bind_item PART),
place (""|"weapon"|"shield"), fit (bool), scale (0 = from KIND), turn, skip [names], saturation, metal (null|true|false),
only [actions "NN_name"], outline, body_gap (null = default), save_blend (bool), weapon_part (place_weapon PART).
"""
import json
import os
import re
import shutil
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
S = json.load(open(argv[0], encoding="utf-8"))
PIPE = S["pipeline"]
OUT = os.path.abspath(S["out"])
os.makedirs(OUT, exist_ok=True)


def say(msg):
    print("[uo3d] " + msg, flush=True)


def run(script, **over):
    """Run a pipeline script with some top-level constants replaced (^NAME = ... lines)."""
    path = os.path.join(PIPE, script)
    if not os.path.isfile(path):
        sys.exit("[uo3d] script not found: " + path)
    text = open(path, encoding="utf-8").read()
    for k, v in over.items():
        text, n = re.subn(r"^%s\s*=.*$" % re.escape(k), lambda m, k=k, v=v: "%s = %r" % (k, v), text, count=1, flags=re.M)
        if n != 1:
            sys.exit("[uo3d] setting %s not found in %s (a different version of UO_Model3D?)" % (k, script))
    say("running " + script + ("  " + ", ".join("%s=%r" % kv for kv in over.items() if kv[0] != "FILE") if over else ""))
    exec(compile(text, path, "exec"), {"__name__": "__main__", "__file__": path, "bpy": bpy})


say("opening " + S["blend"])
bpy.ops.wm.open_mainfile(filepath=S["blend"])
rig = bpy.data.objects["UO_Rig"]
rig.data.pose_position = "REST"                       # items are fitted in the rest pose
for o in list(bpy.data.collections["Clothing"].all_objects):          # the example shirt and anything left over
    bpy.data.objects.remove(o, do_unlink=True)
bpy.context.view_layer.objects.active = None

# 1. import (size and place from the KIND; weapons: KIND "" and SCALE given)
imp = dict(FILE=S["file"], KIND=S.get("kind", ""), TURN=int(S.get("turn", 0)), SKIP=tuple(S.get("skip", ())))
if float(S.get("scale", 0) or 0) > 0:
    imp["SCALE"] = float(S["scale"])
if S.get("name"):
    imp["NAME"] = S["name"]
run("uo_import_item.py", **imp)

# 2. materials into the UO look
mat = dict(SATURATION=float(S.get("saturation", 1.0)))
if S.get("metal") is not None:
    mat["METAL"] = bool(S["metal"])
run("uo_materials.py", **mat)

# 3. fit to the body (clothes and armour only) and placing (weapons, shields)
if S.get("fit"):
    run("uo_fit_item.py", KIND=S.get("kind", ""))
if S.get("place") == "weapon":
    run("uo_place_weapon.py", PART=S["weapon_part"])
elif S.get("place") == "shield":
    run("uo_place_shield.py")

# 4. bind to the skeleton
run("uo_bind_item.py", PART=S["part"])

if S.get("save_blend"):
    p = os.path.join(OUT, (S.get("name") or "item") + "_bound.blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, copy=True)
    say("saved " + p)

# 5. render the layer to frames and a .vd
over = dict(LAYER="clothing", ONLY=list(S.get("only", [])), OUT_DIR=OUT + "/", VD_FILE=OUT + "/%s.vd",
            OUTLINE=float(S.get("outline", 0.38)), WRITE_VD=True)
if S.get("body_gap") is not None:
    over["BODY_GAP"] = float(S["body_gap"])
run("render_uo_layer.py", **over)

vd = os.path.join(OUT, "clothing.vd")
if os.path.isfile(vd):
    final = os.path.join(OUT, (S.get("name") or "item") + ".vd")
    shutil.copy2(vd, final)
    say("RESULT_VD " + final)
else:
    say("no .vd was written - see the messages above")
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)                                           # the bpy module can crash while shutting down, after the work is done
