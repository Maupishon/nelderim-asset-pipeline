#!/usr/bin/env python3
"""
nelderim_hub.py - one launcher for every Nelderim tool, on any machine.

Like nelderim_gui.py this file has NO format logic. It only asks where each
tool lives, remembers the answers (per user, in ~/.nelderim_hub.json - never
in the repo) and runs the existing scripts exactly as you would in a terminal:

    SpriteMotion toolkit + Levy overlay : build.py, build_item.py, verify.py,
                                          mul2vd.py, atlas_to_vd.py, vdtool.py
    Nelderim pipeline                   : nelderim_gui.py, nelderim_search.py,
                                          nelderim_patch.py (dry-run first)
    Viewers                             : Outfit Lab (local http server),
                                          vd-viewer.html, UOFiddler

Standard library only (tkinter). Run:  python nelderim_hub.py
Headless helpers:  python nelderim_hub.py --show-config
"""

from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
# frozen (PyInstaller) exe: the pipeline scripts sit next to the exe, __file__ points to a temp dir
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".nelderim_hub.json"
PORT = 8772

# key -> (label, kind, marker that proves the folder/file is right, required)
PATHS = {
    "client":   ("UO client folder (anim.idx, anim.mul, tiledata.mul, *.def)", "dir", "anim.idx", True),
    "toolkit":  ("SpriteMotion-UO-Toolkit folder (has pyproject.toml, with Levy overlay)", "dir",
                 "games/ultima-online/outfit-lab/build_item.py", True),
    "pipeline": ("nelderim-asset-pipeline folder (has nelderim_patch.py)", "dir", "nelderim_patch.py", True),
    "output":   ("Output folder for patched files", "dir", None, True),
    "vdviewer": ("vd-viewer.html (VD Animation Viewer)", "file", None, False),
    "fiddler":  ("UOFiddler folder (has UOFiddler.exe)", "dir", None, False),
    "serv":     ("ServUO folder (C# scripts)", "dir", None, False),
    "vdtool":   ("vdtool folder (optional; the toolkit's tools/vd is used otherwise)", "dir", None, False),
    "blender":  ("Blender executable (blender.exe; for the 3D model, Blender 4.2 - 5.2)", "file", None, False),
    "model3d":  ("UO_Model3D folder (has pipeline/render_uo_layer.py and model/UO_Body_0x190.blend)", "dir",
                 "pipeline/render_uo_layer.py", False),
}


# ----------------------------------------------------------------- config
def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def path_ok(key: str, value: str | None) -> bool:
    if not value:
        return False
    _, kind, marker, _ = PATHS[key]
    p = Path(value)
    if kind == "file":
        return p.is_file()
    if key == "output":
        return p.is_dir() or p.parent.is_dir()
    return p.is_dir() and (marker is None or (p / marker).exists())


def missing(cfg: dict, only_required: bool = True) -> list[str]:
    return [k for k, (_, _, _, req) in PATHS.items()
            if (req or not only_required) and not path_ok(k, cfg.get(k))]


def guesses(key: str) -> list[str]:
    """Where to open the folder dialog first: siblings of this repo, never assumed to exist."""
    if key == "pipeline":
        return [str(HERE)]
    if key == "blender":
        return find_blender()
    names = {"model3d": ["UO_Model3D-main", "UO_Model3D"], "client": ["Nelderim"], "toolkit": ["SpriteMotion-UO-Toolkit", "SpriteMotion"],
             "fiddler": ["UO Fiddler"], "serv": ["ServUO-master"], "vdtool": ["vdtool"]}.get(key, [])
    out = []
    for base in (HERE.parent, HERE.parent.parent, Path.home()):
        for n in names:
            for cand in (base / n, base / n / n):
                if cand.is_dir():
                    out.append(str(cand))
    return out


def find_blender() -> list[str]:
    """Plausible Blender executables on this machine (never assumed: the user confirms in Settings)."""
    import glob
    import shutil
    out = []
    w = shutil.which("blender")
    if w:
        out.append(w)
    pats = [r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
            "/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender", "/snap/bin/blender"]
    for pat in pats:
        out += sorted(glob.glob(pat), reverse=True)
    return [p for p in out if os.path.isfile(p)]


# --------------------------------------------------------- command builders
def system_python() -> str:
    """Interpreter for helper scripts. In the frozen exe sys.executable is the exe itself, so look for a real Python."""
    if not FROZEN:
        return sys.executable
    import shutil
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p:
            return p
    raise SystemExit("Python 3.10+ not found on PATH (needed to run the toolkit / pipeline scripts).")


def toolkit_python(cfg: dict) -> str:
    tk = Path(cfg["toolkit"])
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python", ".venvs/spritemotion/Scripts/python.exe"):
        if (tk / rel).is_file():
            return str(tk / rel)
    return system_python()


def tk_env(cfg: dict) -> dict:
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    env["SPRITEMOTION_UO_SOURCE"] = cfg["client"]
    return env


def workdir(cfg: dict) -> Path:
    return Path(cfg["toolkit"]) / "workspace" / "ultima-online" / "vd"


def vd_original(cfg: dict, anim_id: int) -> Path:
    return workdir(cfg) / f"anim_{anim_id:04d}.vd"


def _tk(cfg, *args):
    """Command run with the toolkit's python from the toolkit root."""
    return {"argv": [toolkit_python(cfg), *map(str, args)], "cwd": cfg["toolkit"], "env": tk_env(cfg)}


def cmd_build_set(cfg, out, design, sword, config, actions):
    a = ["games/ultima-online/outfit-lab/build.py", "--source", cfg["client"], "--out", out,
         "--design", design, "--lightsaber", sword, "--config", config]
    if actions.strip():
        a += ["--actions", *actions.split()]
    return _tk(cfg, *a)


def cmd_build_item(cfg, graphic, design, out, key, title, hide, actions):
    a = ["games/ultima-online/outfit-lab/build_item.py", "--source", cfg["client"], "--graphic", graphic,
         "--design", design, "--out", out, "--key", key]
    if title.strip():
        a += ["--title", title]
    if actions.strip():
        a += ["--actions", *actions.split()]
    if hide.strip():
        a += ["--hide-labels", *hide.split()]
    return _tk(cfg, *a)


def cmd_verify(cfg, lab):
    """Exit code 1 also happens when item pixels differ from the original (normal): read the JSON, not the code."""
    c = _tk(cfg, "games/ultima-online/outfit-lab/verify.py", lab)
    c["ok"] = (0, 1)
    return c


def cmd_mul2vd(cfg, anim_id):
    return _tk(cfg, "tools/vd/mul2vd.py", Path(cfg["client"]) / "anim.idx", Path(cfg["client"]) / "anim.mul",
               workdir(cfg), anim_id)


def cmd_atlas_to_vd(cfg, lab, key, orig_vd, out_vd, body_vd, outline):
    a = ["games/ultima-online/outfit-lab/atlas_to_vd.py", lab, key, orig_vd, out_vd]
    if body_vd:
        a += ["--body", body_vd]
    if outline:
        a += ["--outline", outline]
    return _tk(cfg, *a)


def cmd_vd_info(cfg, vd):
    return _tk(cfg, "tools/vd/vdtool.py", "info", vd)


def cmd_conv_check(cfg, anim_id):
    """Prints 'INMUL' if anim_id lives in anim.mul, else 'CONV <n> <id>' (anim2..5.mul: use UOFiddler)."""
    code = ("import sys;sys.path.insert(0,'games/ultima-online/region-masks');from uo import UOReader;"
            "r=UOReader(sys.argv[1]);i=int(sys.argv[2]);c=r.conv.get(i);"
            "print('INMUL' if c is None else 'CONV %d %d'%c)")
    return _tk(cfg, "-c", code, cfg["client"], anim_id)


def cmd_serve(cfg, lab):
    return _tk(cfg, "-m", "http.server", PORT, "--bind", "127.0.0.1", "--directory", lab)


def _pl(cfg, script, *args):
    return {"argv": [system_python(), str(Path(cfg["pipeline"]) / script), *map(str, args)],
            "cwd": cfg["pipeline"], "env": dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")}


def cmd_search(cfg, query):
    return _pl(cfg, "nelderim_search.py", "--client", cfg["client"], "--item", query)


def cmd_patch(cfg, recipe, apply):
    a = ["--client", cfg["client"], "--recipe", recipe, "--out", cfg["output"]]
    if apply:
        a.append("--apply")
    return _pl(cfg, "nelderim_patch.py", *a)


def cmd_pipeline_gui(cfg):
    return _pl(cfg, "nelderim_gui.py")


def lab_items(lab: str) -> list[tuple[str, int]]:
    """(key, animId) of every item in a built lab's manifest.json."""
    m = json.loads((Path(lab) / "manifest.json").read_text(encoding="utf-8"))
    return [(i["key"], int(i["animId"])) for i in m["items"]]


def equip_target(cfg, anim_id: int) -> int:
    """Animation id actually used for body 400 (Equipconv.def). Falls back to anim_id."""
    try:
        for line in (Path(cfg["client"]) / "Equipconv.def").read_text(errors="replace").splitlines():
            v = line.split("#")[0].split()
            if len(v) >= 3 and v[0] == "400" and int(v[1]) == anim_id:
                return int(v[2])
    except (OSError, ValueError):
        pass
    return anim_id


def noop() -> dict:
    return {"noop": True, "argv": ["noop"], "cwd": str(HERE), "env": dict(os.environ)}


def cmd_vd_verify(cfg, a, b):
    """vdtool verify: expect 'OBRAZ IDENTYCZNY' for an --original round trip."""
    return _tk(cfg, "tools/vd/vdtool.py", "verify", a, b)


def cmd_atlas_roundtrip(cfg, lab, key, orig_vd, out_vd):
    return _tk(cfg, "games/ultima-online/outfit-lab/atlas_to_vd.py", lab, key, orig_vd, out_vd, "--original")


def cmd_item_lookup(cfg, graphic):
    """ItemID -> animId / layer / label (tiledata) -> Equipconv target -> Bodyconv (anim2..5.mul?)."""
    code = ("import sys;sys.path.insert(0,'games/ultima-online/region-masks');from uo import UOReader;"
            "r=UOReader(sys.argv[1]);g=int(sys.argv[2],0);it=r.item(g);a=it['animId'];"
            "t=r.equip.get((400,a),(a,0))[0];print('item %#x %r animId %d layer %d'%(g,it['label'],a,it['layer']));"
            "print('animation used for body 400:',t,'| Equipconv hue:',r.equip.get((400,a),(a,0))[1]);"
            "print('Bodyconv:',r.conv.get(t) or 'none -> anim.mul (mul2vd works)');"
            "print('Body.def hard redirect (unsupported by reader):',t in r.unsupported)")
    return _tk(cfg, "-c", code, cfg["client"], graphic)


def gump_ids(anim_id: int) -> tuple[int, int]:
    """Paperdoll gump: male = AnimID + 50000, female = male + 10000 (Levy's rule; check Equipconv for a literal one)."""
    return anim_id + 50000, anim_id + 60000


def backup_file(path: Path) -> Path | None:
    """Copy an existing file to <name>_BACKUP_<timestamp>.vd before it is overwritten."""
    import shutil
    import time
    if not path.is_file():
        return None
    dst = path.with_name(f"{path.stem}_BACKUP_{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
    shutil.copy2(path, dst)
    return dst


def write_json(path: Path, obj) -> None:
    """UTF-8 without BOM (PowerShell 5.1 Set-Content would add one)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def placeholder_png(path: Path, w: int = 16, h: int = 12) -> None:
    """Opaque RGBA PNG (stdlib only). build.py insists on --design/--lightsaber even for axis-only weapons."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * w for _ in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def weapon_config(key, graphic, image, thickness, hide, continuity, torso, title) -> dict:
    """build.py --config for a narrow held weapon on the axis-fit path (Levy's newer build.py)."""
    cfg = {"title": title or key, "items": [[key, graphic]], "cells": {key: 0}, "props": [],
           "hide": {key: [int(x) for x in hide.split()]}, "drawOrder": [key], "defaultOff": [], "exclusive": [],
           "axisFit": [key], "axisImages": {key: image}, "displayNames": {key: title or key}}
    if str(thickness).strip():
        cfg["axisThickness"] = {key: int(thickness)}
    if continuity:
        cfg["axisContinuity"] = [key]
    cfg["axisTorsoRule"] = bool(torso)     # build.py defaults to True when the key is missing
    return cfg


def cmd_make_gump(cfg, anim, image, out, thickness, ratio, butt, shift, front_below, outline, gump_id):
    """Paperdoll gump for a hand-held item (make_gump.py from Levy's v2 package)."""
    a = ["games/ultima-online/outfit-lab/make_gump.py", "--client", cfg["client"], "--anim", anim,
         "--image", image, "--out", out]
    if str(thickness).strip():
        a += ["--thickness", thickness]
    elif str(ratio).strip():
        a += ["--ratio", ratio]
    if butt:
        a += ["--butt", butt]
    if str(shift).strip():
        a += ["--shift", shift]
    if str(front_below).strip():
        a += ["--front-below", front_below]
    if outline:
        a.append("--outline")
    if str(gump_id).strip():
        a += ["--gump-id", gump_id]
    return _tk(cfg, *a)


def toolkit_has_gump(cfg) -> bool:
    return (Path(cfg["toolkit"]) / "games/ultima-online/outfit-lab/make_gump.py").is_file()


def toolkit_has_axisfit(cfg) -> bool:
    try:
        return "axisFit" in (Path(cfg["toolkit"]) / "games/ultima-online/outfit-lab/build.py").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False


CHECKLIST = """Checklist before hand-off:
 [ ] verify: "errors": [] and missingSequences 0, ALL actions built (not just the pilot ones)
 [ ] look at all 35 actions in 3 directions (ball/hilt on the right end, weapon not painted on the body)
 [ ] vdtool info: type 2, 35 actions x 5 directions, frame counts equal to the original
 [ ] backup of the previous .vd kept (done automatically as *_BACKUP_*.vd)
 [ ] show the user the HTML preview; ask about thickness / orientation
 Not verified by these tools: import into UOFiddler, in-game look, item icon, ItemData/bodyTable/C# scripts,
 body 401, animations only in .uop."""


def open_path(p: str) -> None:
    if os.name == "nt":
        os.startfile(p)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


def workroot(cfg) -> Path:
    """Where finished work folders go: <toolkit>/workspace/ultima-online."""
    return Path(cfg["toolkit"]) / "workspace" / "ultima-online"


def slugify(name: str) -> str:
    import re
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    return s or "praca"


def cmd_deps_check(cfg):
    """Prints DEPS_OK when the toolkit's python can import numpy and PIL."""
    return _tk(cfg, "-c", "import numpy, PIL; print('DEPS_OK')")


def cmd_pip_install(cfg):
    """Installs what the toolkit scripts import into the python the hub uses for the toolkit."""
    return _tk(cfg, "-m", "pip", "install", "numpy", "pillow", "scipy")


# ---- 3D model route (UO_Model3D in Blender); label, uo_import_item KIND, uo_bind_item PART, place, fit, needs SCALE, note
KINDS3D = [
    ("Koszula / tunika", "shirt", "chest", "", True, False, ""),
    ("Zbroja piersiowa", "plate", "chest", "", True, False, ""),
    ("Rękawy / naramienniki", "arms", "arms", "", True, False, ""),
    ("Spodnie", "pants", "legs", "", True, False, ""),
    ("Nogawice / pancerz nóg", "legs", "legs", "", True, False, ""),
    ("Buty", "boots", "boots", "", True, False, ""),
    ("Rękawice", "gloves", "gloves", "", True, False, ""),
    ("Hełm", "helm", "helm", "", True, False, ""),
    ("Szata / suknia", "robe", "robe", "", False, False, "Tkanina bez symulacji (symulacja 30-60 min: robi się ją ręcznie w Blenderze, uo_cloth_bake.py)."),
    ("Spódnica", "skirt", "skirt", "", False, False, ""),
    ("Peleryna", "cloak", "cloak", "", False, False, ""),
    ("Włosy", "hair", "hair", "", False, False, "Długie fryzury: podaj skalę ręcznie."),
    ("Broda", "beard", "beard", "", False, False, ""),
    ("Czapka / kaptur", "hat", "hat", "", False, False, ""),
    ("Miecz / maczuga / topór jednoręczny", "", "weapon1h", "weapon", False, True, "Model ustaw pionowo: trzon wzdłuż osi Z, czubek w górę."),
    ("Laska / włócznia / halabarda", "", "polearm", "weapon", False, True, "Model ustaw pionowo: trzon wzdłuż osi Z, czubek w górę."),
    ("Topór dwuręczny", "", "axe2h", "weapon", False, True, "Model ustaw pionowo: trzon wzdłuż osi Z, czubek w górę."),
    ("Łuk / kusza", "", "bow", "weapon", False, True, "Model ustaw pionowo: trzon wzdłuż osi Z, czubek w górę."),
    ("Tarcza", "", "shield", "shield", False, True, "Przodem do widoku z przodu, górą do góry."),
]
ACTION_NAMES = ["walk_unarmed", "walk_armed", "run_unarmed", "run_armed", "stand", "fidget_1", "fidget_2",
                "combat_idle_1h", "combat_idle_2h", "attack_1h_slash", "attack_1h_pierce", "attack_1h_bash",
                "attack_2h_bash", "attack_2h_slash", "attack_2h_pierce", "combat_advance", "spell_directed",
                "spell_area", "attack_bow", "attack_crossbow", "get_hit", "die_forward", "die_backward",
                "mounted_walk", "mounted_run", "mounted_stand", "mounted_attack_1h", "mounted_attack_bow",
                "mounted_attack_crossbow", "mounted_attack_2h", "block", "punch", "bow", "salute", "eat"]


def action_ids(text: str) -> list[str]:
    """'0 4 9' -> ['00_walk_unarmed', '04_stand', '09_attack_1h_slash'] (render_uo_layer.py ONLY names). Raises ValueError."""
    out = []
    for t in text.split():
        n = int(t)
        if not 0 <= n < len(ACTION_NAMES):
            raise ValueError(f"akcja {n} (dozwolone 0-34)")
        out.append(f"{n:02d}_{ACTION_NAMES[n]}")
    return out


def blend_path(cfg) -> Path:
    return Path(cfg["model3d"]) / "model" / "UO_Body_0x190.blend"


def job3d_script() -> Path:
    return HERE / "uo3d_job.py"


def model3d_problems(cfg) -> list[str]:
    """What is missing for the 3D route (empty list = ready)."""
    out = []
    if not path_ok("blender", cfg.get("blender")):
        out.append("Nie wskazano Blendera (Ustawienia → Blender).")
    if not path_ok("model3d", cfg.get("model3d")):
        out.append("Nie wskazano folderu UO_Model3D (Ustawienia).")
    elif not blend_path(cfg).is_file():
        out.append(f"Brak pliku {blend_path(cfg)}.")
    if not job3d_script().is_file():
        out.append(f"Brak pliku {job3d_script().name} obok programu.")
    return out


def cmd_blender_job(cfg, spec: dict):
    """Headless Blender run of uo3d_job.py with a spec.json written next to the output."""
    out = Path(spec["out"])
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "spec.json", spec)
    return {"argv": [cfg["blender"], "-b", "--python", str(job3d_script()), "--", str(out / "spec.json")],
            "cwd": cfg["model3d"], "env": dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")}


def cmd_image_check(cfg, image):
    """Prints SIZE w h / ALPHA min max / BBOX (bounding box of pixels with alpha >= 64)."""
    code = ("import sys;from PIL import Image;im=Image.open(sys.argv[1]).convert('RGBA');a=im.getchannel('A');"
            "print('SIZE %d %d'%im.size);print('ALPHA %d %d'%a.getextrema());"
            "print('BBOX %s'%(a.point(lambda v:255 if v>=64 else 0).getbbox(),))")
    return _tk(cfg, "-c", code, image)



def main(argv) -> int:
    if "--show-config" in argv:
        cfg = load_config()
        for k, (label, _, _, req) in PATHS.items():
            print(f"{k:9} {'OK ' if path_ok(k, cfg.get(k)) else ('MISSING' if req else '-')}  {cfg.get(k, '')}")
        return 0
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter is missing. Linux: install python3-tk (Debian/Ubuntu) or python3-tkinter (Fedora).")
        return 1
    from nelderim_hub_ui import run_gui
    run_gui(sys.modules[__name__])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
