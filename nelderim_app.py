"""
nelderim_app.py - Nelderim Lab: ONE local web app for the whole pipeline (hub + client patcher + 3D fit lab).

Runs a small HTTP server on 127.0.0.1 and opens the browser. The page (app/index.html) talks to this server only.
No format logic lives here either: tasks are the command builders of nelderim_hub.py (toolkit scripts, pipeline scripts,
uo3d_py.py), and the live 3D fit uses the uo3d package in-process.

    python nelderim.py            (or run_nelderim.bat / run_nelderim.sh / Nelderim.exe)
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import nelderim_hub as H

APP_DIR = H.HERE / "app"
NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}
PL = {"client": "Folder klienta UO (kopia!)", "toolkit": "Folder toolkitu SpriteMotion", "pipeline": "Folder programu (pipeline)",
      "output": "Folder na wyniki dodawania", "vdviewer": "Plik vd-viewer.html", "fiddler": "Folder UOFiddlera", "serv": "Folder ServUO",
      "vdtool": "Folder vdtool", "bodyglb": "Plik UO_Body_0x190.glb"}
PATH_HELP = {
    "client": "Folder z grą (KOPIA klienta!), gdzie leżą anim.idx, anim.mul, tiledata.mul, Equipconv.def.",
    "toolkit": "Folder SpriteMotion-UO-Toolkit (tam gdzie pyproject.toml) z paczką Levy'ego v2. Potrzebny do metod 2D.",
    "pipeline": "Folder tego programu (nelderim_patch.py). Wykrywa się sam.",
    "output": "Gdzie zapisywać wyniki dodawania do klienta.",
    "vdviewer": "vd-viewer.html (przeglądarka .vd Levy'ego) – opcjonalnie; aplikacja ma własny podgląd .vd.",
    "fiddler": "Folder UOFiddlera (opcjonalnie).", "serv": "Folder serwera ServUO (opcjonalnie).",
    "vdtool": "Osobny vdtool (opcjonalnie).",
    "bodyglb": "UO_Body_0x190.glb z projektu UO_Model3D (folder model). Potrzebny do metody 3D. Blender nie jest potrzebny."}


def self_cmd(*args) -> list[str]:
    """Run nelderim.py itself (or the frozen exe) in a helper mode."""
    if H.FROZEN:
        return [sys.executable, *map(str, args)]
    return [sys.executable, str(H.HERE / "nelderim.py"), *map(str, args)]


def wstate():
    return {"python": sys.version.split()[0], "frozen": H.FROZEN}


# ------------------------------------------------------------------ jobs
class Job:
    def __init__(self, title):
        self.id = uuid.uuid4().hex[:10]
        self.title = title
        self.lines: list[str] = []
        self.status = "running"            # running | ok | fail | stopped
        self.result: dict = {}
        self.proc = None
        self.stop = False
        self.hints: list[str] = []
        self.t0 = time.time()

    def say(self, s):
        for line in str(s).splitlines() or [""]:
            self.lines.append(line)
            for pat, msg in H.HINTS:
                if re.search(pat, line) and msg not in self.hints:
                    self.hints.append(msg)

    def info(self):
        return {"id": self.id, "title": self.title, "status": self.status, "result": self.result, "hints": self.hints,
                "elapsed": round(time.time() - self.t0, 1)}


JOBS: dict[str, Job] = {}


def run_job(title, steps, finish=None):
    """steps: callables -> cmd dict (subprocess), None (stop, ok=False), or a python callable result {"py": fn}."""
    job = Job(title)
    JOBS[job.id] = job

    def work():
        ok = True
        try:
            for st in steps:
                if job.stop:
                    ok = False; job.status = "stopped"; break
                cmd = st(job)
                if cmd is None:
                    ok = False; break
                if cmd.get("noop"):
                    continue
                job.say("$ " + " ".join(f'"{a}"' if " " in str(a) else str(a) for a in cmd["argv"]))
                try:
                    p = subprocess.Popen(cmd["argv"], cwd=cmd.get("cwd"), env=cmd.get("env"), stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **NOWIN)
                except OSError as e:
                    job.say(f"[BŁĄD] {e}"); ok = False; break
                job.proc = p
                cap = []
                for line in p.stdout:
                    line = line.rstrip("\n")
                    cap.append(line); job.say(line)
                rc = p.wait()
                job.proc = None
                if "on_output" in cmd:
                    cmd["on_output"](job, cap)
                if rc not in cmd.get("ok", (0,)):
                    job.say(f"[BŁĄD] kod wyjścia {rc}"); ok = False; break
            if ok and finish:
                finish(job)
        except Exception as e:  # noqa: BLE001
            job.say("[BŁĄD] " + "".join(traceback.format_exception_only(type(e), e)).strip()); ok = False
        if job.status == "running":
            job.status = "ok" if ok else "fail"
    threading.Thread(target=work, daemon=True).start()
    return job


def noop():
    return {"noop": True}


def py(fn):
    """step that runs python code in-process (fn(job))."""
    def st(job):
        fn(job)
        return noop()
    return st


# ------------------------------------------------------------------ 3D session (live fit)
class M3D:
    lock = threading.RLock()
    body = None
    body_path = None
    item = None
    fr = None
    params: dict = {}
    masks: dict = {}

    @classmethod
    def engine(cls):
        from uo3d import engine
        return engine

    @classmethod
    def load_body(cls, cfg):
        E = cls.engine()
        p = cfg.get("bodyglb")
        if not p or not Path(p).is_file():
            raise ValueError("Wskaż plik UO_Body_0x190.glb w Ustawieniach.")
        if cls.body is None or cls.body_path != p:
            cls.body = E.Body(p); cls.body_path = p; cls.masks = {}
        return cls.body

    @classmethod
    def mask(cls, path):
        if not path:
            return None
        if path not in cls.masks:
            from uo3d import vdread
            cls.masks[path] = vdread.alpha_masks(str(path))
        return cls.masks[path]

    @classmethod
    def build(cls, cfg, P):
        E = cls.engine()
        from uo3d import weapons as wp
        with cls.lock:
            body = cls.load_body(cfg)
            ex = H.model3d_extras(cfg)
            motion = json.load(open(ex["motion"], encoding="utf-8")) if ex["motion"] else None
            keys = wp.load_shield_keys(str(ex["shield"])) if ex["shield"] else None
            adj = {"off": [float(v) / 100 for v in P.get("off", [0, 0, 0])], "rot": [float(v) for v in P.get("rot", [0, 0, 0])],
                   "scl": float(P.get("scl", 100)) / 100, "fit": bool(P.get("fit", True))}
            item = E.Item(P["item"], P["kind"], body, turn=float(P.get("turn", 0) or 0), scale=float(P.get("scale", 0) or 0),
                          skip=[s.strip() for s in str(P.get("skip", "")).split(",") if s.strip()],
                          saturation=float(P.get("sat", 1) or 1), motion=motion, shield_keys=keys,
                          roll_deg=float(P["roll"]) if str(P.get("roll", "")).strip() else None, adjust=adj)
            bm = cls.mask(ex["body_vd"]) if P.get("exact", True) else None
            hm = cls.mask(ex["horse_vd"]) if P.get("horse", True) else None
            cls.item = item
            cls.fr = E.FrameRenderer(body, item, body_masks=bm, horse_masks=hm)
            cls.params = dict(P)
            if P.get("cloth") and P["kind"] in ("robe", "skirt", "cloak"):
                from uo3d import cloth
                cls.sim = cloth.make_sim(body, item); cls.sim_done = set()
            else:
                cls.sim = None
            return {"scale": round(item.scale, 3), "verts": int(len(item.pos)), "tris": int(len(item.tri)),
                    "worn": sorted(item.worn), "frames": E.ACTION_FRAMES, "exact": bm is not None, "horse": hm is not None}

    @classmethod
    def ensure_cloth(cls, a):
        if getattr(cls, "sim", None) is not None and a not in cls.sim_done:
            cls.sim(a); cls.sim_done.add(a)

    @classmethod
    def colors(cls):
        """per-vertex colours of the item (material colour x texture average)."""
        import numpy as np
        m = cls.item.mesh
        col = np.zeros((len(cls.item.pos), 3)) + 0.7
        for mi, mat in enumerate(m.mats):
            sel = m.mat_of_tri == mi
            if not sel.any():
                continue
            c = mat.color[:3].copy()
            if mat.tex is not None:
                vi = np.unique(m.tri[sel])
                th, tw = mat.tex.shape[:2]
                u = np.mod(m.uv[vi, 0], 1.0); v = np.mod(m.uv[vi, 1], 1.0)
                col[vi] = c * mat.tex[np.minimum((v * th).astype(int), th - 1), np.minimum((u * tw).astype(int), tw - 1)][:, :3]
            else:
                col[np.unique(m.tri[sel])] = c
        if m.vcol is not None and len(m.vcol) == len(col):
            col = col * m.vcol[:, :3]
        return col


def png_bytes(arr):
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "PNG")
    return b.getvalue()


def composite(base, top):
    import numpy as np
    a = top[..., 3:4] / 255.0
    out = base.astype(float).copy()
    out[..., :3] = top[..., :3] * a + out[..., :3] * (1 - a)
    out[..., 3] = np.maximum(base[..., 3], top[..., 3])
    return out.astype(np.uint8)


VD_CACHE: dict = {}


def vd_frames(path):
    from uo3d import vdread
    st = os.stat(path)
    key = (path, st.st_mtime)
    if key not in VD_CACHE:
        VD_CACHE.clear() if len(VD_CACHE) > 6 else None
        VD_CACHE[key] = vdread.read_vd(path)
    return VD_CACHE[key]


def body_underlay(cfg, a, d, k):
    from uo3d import vdread
    import numpy as np
    ex = H.model3d_extras(cfg)
    cands = [ex["body_vd"]]
    if cfg.get("toolkit"):
        cands.append(H.vd_original(cfg, 400))
    for c in cands:
        if c and Path(c).is_file():
            _, _, A = vd_frames(str(c))
            fr = A.get((a, d))
            if fr:
                return vdread.canvas(fr[min(k, len(fr) - 1)])
    return np.zeros((256, 256, 4), np.uint8)


def crop(img, scale=2):
    from PIL import Image
    im = Image.fromarray(img).crop((68, 84, 188, 214))  # anchor (128,192); room for weapons and capes
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


def themed_bg(img):
    import numpy as np
    bg = np.zeros_like(img); bg[..., :3] = (17, 20, 26); bg[..., 3] = 255
    return composite(bg, img)


# ------------------------------------------------------------------ flows (tasks)
def lab_dir(cfg, name):
    return H.workroot(cfg) / H.slugify(name) / "lab"


def task(cfg, name, p):
    """-> Job"""
    need = lambda *keys: [k for k in keys if not H.path_ok(k, cfg.get(k))]  # noqa: E731

    def require(*keys):
        m = need(*keys)
        if m:
            raise ValueError("Najpierw ustaw w Ustawieniach: " + ", ".join(PL[k] for k in m))

    if name == "lookup":
        require("toolkit", "client")
        g = norm_item(p["graphic"])
        return run_job("Sprawdzanie przedmiotu", [lambda j: H.cmd_item_lookup(cfg, g)])
    if name == "image_check":
        require("toolkit")
        return run_job("Sprawdzanie obrazka", [lambda j: H.cmd_image_check(cfg, p["image"])])
    if name == "deps_toolkit":
        require("toolkit")
        return run_job("Instalacja bibliotek (toolkit)", [lambda j: H.cmd_pip_install(cfg)])
    if name == "deps_self":
        return run_job("Instalacja bibliotek", [lambda j: H.cmd_pip_install_sys(cfg)])
    if name == "build_item":
        require("toolkit", "client")
        out = lab_dir(cfg, p["name"]); key = H.slugify(p["name"])
        return run_job("Budowanie przymiarki", [lambda j: H.cmd_build_item(cfg, norm_item(p["graphic"]), p["image"], str(out), key,
                                                                             p.get("title", ""), p.get("hide", ""), p.get("actions", ""))],
                       finish=lambda j: j.result.update(lab=str(out)))
    if name == "weapon2d":
        require("toolkit", "client")
        if not H.toolkit_has_axisfit(cfg):
            raise ValueError("Toolkit ma starą wersję build.py (bez obsługi broni). Skopiuj paczkę Levy'ego v2.")
        key = "sword" if p.get("type", "sword") == "sword" else "staff"
        out = lab_dir(cfg, p["name"]); work = out.parent / "work"
        conf, dz, sw = work / "config.json", work / "placeholder_design.png", work / "placeholder_sword.png"
        H.write_json(conf, H.weapon_config(key, norm_item(p["graphic"]), p["image"], str(p.get("thick", "")).strip(), p.get("hide", "5"),
                                           bool(p.get("cont", True)), bool(p.get("torso", True)), p["name"]))
        H.placeholder_png(dz); H.placeholder_png(sw)
        if key == "sword":
            sw = Path(p["image"])
        return run_job("Budowanie broni", [lambda j: H.cmd_build_set(cfg, str(out), str(dz), str(sw), str(conf), p.get("actions", "")),
                                           lambda j: H.cmd_verify(cfg, str(out))], finish=lambda j: j.result.update(lab=str(out)))
    if name == "build_set":
        require("toolkit", "client")
        return run_job("Budowanie zestawu", [lambda j: H.cmd_build_set(cfg, p["out"], p["design"], p["sword"], p["config"], p.get("actions", ""))],
                       finish=lambda j: j.result.update(lab=p["out"]))
    if name == "verify":
        require("toolkit", "client")
        return run_job("Sprawdzanie (verify)", [lambda j: H.cmd_verify(cfg, p["lab"])])
    if name == "pack":
        require("toolkit", "client")
        return pack_job(cfg, p)
    if name == "roundtrip":
        require("toolkit", "client")
        key, aid = p["key"], int(p["anim"])
        target = H.equip_target(cfg, aid); orig = H.vd_original(cfg, target)
        tmp = H.workdir(cfg) / f"test_{target:04d}.vd"
        return run_job("Test konwertera", [lambda j: noop() if orig.exists() else H.cmd_mul2vd(cfg, target),
                                           lambda j: H.cmd_atlas_roundtrip(cfg, p["lab"], key, str(orig), str(tmp)),
                                           lambda j: H.cmd_vd_verify(cfg, str(orig), str(tmp))])
    if name == "gump":
        require("toolkit", "client")
        if not H.toolkit_has_gump(cfg):
            raise ValueError("Brak make_gump.py w toolkicie – skopiuj paczkę Levy'ego v2.")
        out = H.workroot(cfg) / H.slugify(p["name"]) / "gump"
        pr = p.get("preset", "sabre")
        th, ra, sh, fb, ol = p.get("thick", ""), p.get("ratio", "0.15"), p.get("shift", "0,0"), p.get("front", ""), bool(p.get("outline"))
        if pr == "staff":
            th, ra, sh, fb, ol = "26", "", "0,0", "", False
        elif pr == "sabre":
            th, ra, sh, fb, ol = "", "0.15", "3,-9", "106", True
        return run_job("Tworzenie gumpu", [lambda j: H.cmd_make_gump(cfg, str(p["anim"]), p["image"], str(out), th, ra, "bottom", sh, fb, ol,
                                                                     p.get("gid", ""))],
                       finish=lambda j: j.result.update(dir=str(out), image=str(out / "porownanie.png")))
    if name == "search":
        require("pipeline", "client")
        return run_job("Wyszukiwanie", [lambda j: H.cmd_search(cfg, p["query"])])
    if name == "free_anim":
        require("pipeline", "client")
        return run_job("Wolne ID animacji", [lambda j: H._pl(cfg, "nelderim_search.py", "--client", cfg["client"], "--free-anim", str(p.get("count", 5)))])
    if name == "suggest_slot":
        require("pipeline", "client")

        def parse(j, cap):
            m = re.search(r"auto-selected body (\d+)", "\n".join(cap))
            if m:
                j.result["body"] = int(m.group(1))
        c = H._pl(cfg, "vd_inject.py", "--client", cfg["client"], "--vd", p["vd"]); c["on_output"] = parse; c["ok"] = (0, 1, 2)
        return run_job("Szukanie wolnego slotu", [lambda j: c])
    if name == "patch":
        require("pipeline", "client", "output")
        a = ["--client", cfg["client"], "--recipe", p["recipe"], "--out", cfg["output"], "--missing", p.get("missing", "stop")]
        if p.get("apply"):
            a.append("--apply")
        return run_job("Zastosowanie zmian" if p.get("apply") else "Przebieg na sucho", [lambda j: H._pl(cfg, "nelderim_patch.py", *a)])
    if name == "uo3d_render":
        probs = H.model3d_problems(cfg)
        if probs:
            raise ValueError(" ".join(probs))
        ex = H.model3d_extras(cfg)
        out = works_root(cfg) / H.slugify(p["name"]) / "model3d"
        acts = [int(x) for x in str(p.get("actions", "")).split()]
        spec = dict(item=p["item"], kind=p["kind"], out=str(out), name=H.slugify(p["name"]), actions=acts, turn=p.get("turn", 0),
                    scale=p.get("scale", 0), saturation=p.get("sat", 1), skip=[s.strip() for s in str(p.get("skip", "")).split(",") if s.strip()],
                    body_vd=ex["body_vd"] if p.get("exact", True) else None, horse_vd=ex["horse_vd"] if p.get("horse", True) else None,
                    cloth=bool(p.get("cloth")) and p["kind"] in ("robe", "skirt", "cloak"), roll=p.get("roll") or None,
                    adjust={"off": [float(v) / 100 for v in p.get("off", [0, 0, 0])], "rot": [float(v) for v in p.get("rot", [0, 0, 0])],
                            "scl": float(p.get("scl", 100)) / 100, "fit": bool(p.get("fit", True))})
        def parse(j, cap):
            m = [x for x in cap if "RESULT_VD" in x]
            if m:
                j.result["vd"] = m[-1].split("RESULT_VD", 1)[1].strip()
        c = H.cmd_uo3d(cfg, spec); c["on_output"] = parse
        return run_job("Render modelu 3D", [lambda j: c])
    if name == "vd2glb":
        probs = H.model3d_problems(cfg)
        if probs:
            raise ValueError(" ".join(probs))
        vd = Path(p["vd"])
        if not vd.is_file():
            raise ValueError("Nie ma takiego pliku .vd: " + str(vd))
        nm = H.slugify(p.get("name") or vd.stem)
        out = works_root(cfg) / nm / "model3d" / f"{H.slugify(vd.stem)}_z_vd.glb"

        def parse(j, cap):
            m = [x for x in cap if "RESULT_GLB" in x]
            if m:
                j.result["glb"] = m[-1].split("RESULT_GLB", 1)[1].strip()
        c = H.cmd_vd2glb(cfg, str(vd), str(out), p.get("kind", ""), int(p.get("action", 4) or 4)); c["on_output"] = parse
        return run_job("Model 3D z pliku .vd", [lambda j: c], finish=lambda j: j.result.update(name=nm))
    if name == "vd_info":
        require("toolkit")
        return run_job("Sprawdzanie .vd", [lambda j: H.cmd_vd_info(cfg, p["vd"])])
    if name == "copy_to_toolkit":
        require("toolkit")

        def cp(j):
            src = Path(p["vd"]); dst = H.workdir(cfg) / (p.get("dst") or src.name)
            out, b, note = H.safe_copy(src, dst)
            j.say(f"Gotowe: {out}" + (f" (kopia poprzedniego: {b})" if b else "") + (f"\n[!] {note}" if note else ""))
            j.result["vd"] = str(out)
        return run_job("Kopiowanie .vd", [py(cp), lambda j: H.cmd_vd_info(cfg, j.result["vd"])])
    raise ValueError("Nieznane zadanie: " + name)


def pack_job(cfg, p):
    lab = p["lab"]
    items = H.lab_items(lab)
    key, aid = next(((k, a) for k, a in items if k == p.get("key")), items[0])
    target = H.equip_target(cfg, aid)
    orig = H.vd_original(cfg, target)
    body = Path(p["body"]) if p.get("body") else H.vd_original(cfg, 400)
    out = p.get("out") or str(H.workdir(cfg) / f"nowy_{target:04d}.vd")

    def check(job):
        c = H.cmd_conv_check(cfg, target)
        r = subprocess.run(c["argv"], cwd=c["cwd"], env=c["env"], capture_output=True, text=True, **NOWIN)
        if "INMUL" not in r.stdout and not orig.exists():
            job.say(f"[!] Animacja {target} leży w innym pliku niż anim.mul. Wyciągnij ją UOFiddlerem (Animation Edit → ID {target} → "
                    f"Export to VD) i zapisz jako: {orig}")
            job.result["need_fiddler"] = str(orig)
            return None
        return noop()

    def backup(job):
        b = H.backup_file(Path(out))
        if b:
            job.say(f"Kopia poprzedniego wyniku: {b}")

    return run_job("Pakowanie do .vd", [check, lambda j: noop() if orig.exists() else H.cmd_mul2vd(cfg, target),
                                        lambda j: noop() if body.exists() else H.cmd_mul2vd(cfg, 400), py(backup),
                                        lambda j: H.cmd_atlas_to_vd(cfg, lab, key, str(orig), out, str(body), str(p.get("outline", ""))),
                                        lambda j: H.cmd_vd_info(cfg, out)],
                   finish=lambda j: (j.result.update(vd=out, anim=target), j.say(H.CHECKLIST)))


def norm_item(text):
    t = str(text).strip()
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", t):
        return "0x" + t[2:].upper()
    if re.fullmatch(r"\d+", t):
        return hex(int(t))
    raise ValueError("Numer przedmiotu wygląda nieprawidłowo. Wpisz go tak: 0x2683 (zero, iks, cyfry/litery A–F) albo zwykłą liczbą.")


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "NelderimLab/1"

    def log_message(self, *a):
        pass

    # helpers
    def send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def q(self):
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}

    def static(self, path: Path):
        if not path.is_file():
            return self.send(404, {"error": "brak pliku"})
        ct = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".js":
            ct = "text/javascript; charset=utf-8"
        self.send(200, path.read_bytes(), ct)

    def allowed(self, p: Path) -> bool:
        """files the app may hand to the browser: under configured folders or the work root."""
        cfg = H.load_config()
        roots = [cfg.get(k) for k in ("client", "toolkit", "pipeline", "output", "serv", "vdtool", "fiddler")]
        if cfg.get("bodyglb"):
            roots.append(str(Path(cfg["bodyglb"]).parent.parent))
        roots += [str(H.HERE)] + LAB_ROOTS
        try:
            rp = p.resolve()
        except OSError:
            return False
        return any(r and (str(rp).lower().startswith(str(Path(r).resolve()).lower())) for r in roots)

    # routing
    def do_GET(self):
        try:
            self.route_get()
        except Exception as e:  # noqa: BLE001
            self.send(500, {"error": str(e), "trace": traceback.format_exc()[-1500:]})

    def do_POST(self):
        try:
            self.route_post()
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self.send(500, {"error": str(e), "trace": traceback.format_exc()[-1500:]})

    def route_get(self):
        path = urllib.parse.urlparse(self.path).path
        q = self.q()
        cfg = H.load_config()
        if path in ("/", "/index.html"):
            return self.static(APP_DIR / "index.html")
        if path.startswith("/app/"):
            p = (APP_DIR / path[5:]).resolve()
            if not str(p).startswith(str(APP_DIR.resolve())):
                return self.send(403, {"error": "zabronione"})
            return self.static(p)
        if path.startswith("/lab/"):
            parts = path.split("/", 3)
            idx = int(parts[2]); rest = parts[3] if len(parts) > 3 else "index.html"
            root = Path(LAB_ROOTS[idx])
            p = (root / (rest or "index.html")).resolve()
            if not str(p).startswith(str(root.resolve())):
                return self.send(403, {"error": "zabronione"})
            return self.static(p)
        if path == "/api/state":
            return self.send(200, state(cfg))
        if path == "/api/job":
            j = JOBS.get(q.get("id", ""))
            if not j:
                return self.send(404, {"error": "brak zadania"})
            n = int(q.get("from", 0))
            return self.send(200, {**j.info(), "lines": j.lines[n:], "next": len(j.lines)})
        if path == "/api/file":
            p = Path(q["path"])
            if not self.allowed(p):
                return self.send(403, {"error": "plik poza folderami aplikacji"})
            return self.static(p)
        if path == "/api/m3d/static":
            return self.m3d_static()
        if path == "/api/m3d/pose":
            return self.m3d_pose(int(q.get("a", 4)), int(q.get("k", 0)))
        if path == "/api/m3d/preview":
            return self.m3d_preview(int(q.get("a", 4)), int(q.get("k", 0)), int(q.get("d", 0)), int(q.get("s", 2)))
        if path == "/api/m3d/works":
            return self.send(200, list_works(cfg))
        if path == "/api/vd/info":
            at, n, A = vd_frames(q["path"])
            acts = {str(a): len(A[(a, 0)]) for a in range(n) if (a, 0) in A}
            return self.send(200, {"type": at, "actions": n, "frames": acts})
        if path == "/api/vd/frame":
            return self.vd_frame(cfg, q)
        if path == "/api/recipe":
            p = Path(q["path"])
            return self.send(200, json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"items": []})
        return self.send(404, {"error": "nie ma takiego adresu"})

    def route_post(self):
        path = urllib.parse.urlparse(self.path).path
        data = self.body_json()
        cfg = H.load_config()
        if path == "/api/config":
            for k, v in data.items():
                if k in H.PATHS or k in ("theme",):
                    if v:
                        cfg[k] = str(v).strip()
                    else:
                        cfg.pop(k, None)
            if cfg.get("output"):
                Path(cfg["output"]).mkdir(parents=True, exist_ok=True)
            H.save_config(cfg)
            return self.send(200, state(cfg))
        if path == "/api/autodetect":
            todo = [k for k in H.PATHS if not H.path_ok(k, cfg.get(k))]
            found = {k: v for k, v in H.scan_paths(todo).items() if H.path_ok(k, v)}
            if "pipeline" in todo:
                found["pipeline"] = str(H.HERE)
            if "output" in todo:
                found["output"] = str(Path.home() / "Nelderim-wyniki")
            cfg.update(found); H.save_config(cfg)
            return self.send(200, {"found": found, "state": state(cfg)})
        if path == "/api/pick":
            return self.send(200, {"path": pick(data.get("kind", "file"), data.get("title", "Wybierz"), data.get("filter", ""))})
        if path == "/api/deps":
            return self.send(200, deps(cfg))
        if path == "/api/task":
            j = task(cfg, data["task"], data.get("params", {}))
            return self.send(200, j.info())
        if path == "/api/job/stop":
            j = JOBS.get(data.get("id", ""))
            if j:
                j.stop = True
                if j.proc and j.proc.poll() is None:
                    j.proc.terminate()
                j.status = "stopped"
            return self.send(200, {"ok": True})
        if path == "/api/lab/open":
            p = str(Path(data["path"]).resolve())
            if not (Path(p) / "index.html").is_file():
                raise ValueError("W tym folderze nie ma podglądu (index.html). Najpierw zbuduj przymiarkę.")
            if p not in LAB_ROOTS:
                LAB_ROOTS.append(p)
            return self.send(200, {"url": f"/lab/{LAB_ROOTS.index(p)}/"})
        if path == "/api/open":
            p = Path(data["path"])
            if p.exists():
                H.open_path(str(p if p.is_dir() else p.parent) if data.get("folder") else str(p))
            return self.send(200, {"ok": p.exists()})
        if path == "/api/m3d/load":
            info = M3D.build(cfg, data)
            return self.send(200, info)
        if path == "/api/m3d/measure":
            return self.send(200, measure(data.get("actions", [4])))
        if path == "/api/m3d/save":
            out = works_root(cfg) / H.slugify(data["name"]) / "model3d"
            out.mkdir(parents=True, exist_ok=True)
            data["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")
            hist = out / "history"
            hist.mkdir(exist_ok=True)
            if (out / "work.json").is_file():
                shutil.copy2(out / "work.json", hist / time.strftime("work_%Y%m%d-%H%M%S.json"))
                olds = sorted(hist.glob("work_*.json"))
                for o in olds[:-3]:
                    o.unlink()
            H.write_json(out / "work.json", data)
            return self.send(200, {"ok": True, "path": str(out / "work.json"), "saved": data["saved"],
                                   "versions": [o.name for o in sorted(hist.glob("work_*.json"))]})
        if path == "/api/recipe":
            p = Path(data["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            H.write_json(p, {"items": data.get("items", [])})
            return self.send(200, {"ok": True, "path": str(p)})
        if path == "/api/quit":
            self.send(200, {"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        return self.send(404, {"error": "nie ma takiego adresu"})

    # 3D
    def m3d_static(self):
        import numpy as np
        with M3D.lock:
            if M3D.item is None:
                return self.send(409, {"error": "Najpierw wczytaj model."})
            g = M3D.body.g
            out = {"body_tri": base64.b64encode(g.tri.astype(np.uint32).tobytes()).decode(),
                   "body_n": int(len(g.pos)),
                   "item_tri": base64.b64encode(M3D.item.tri.astype(np.uint32).tobytes()).decode(),
                   "item_n": int(len(M3D.item.pos)),
                   "item_col": base64.b64encode(M3D.colors().astype(np.float32).tobytes()).decode()}
        return self.send(200, out)

    def m3d_pose(self, a, k):
        import numpy as np
        with M3D.lock:
            if M3D.item is None:
                return self.send(409, {"error": "Najpierw wczytaj model."})
            M3D.ensure_cloth(a)
            Wp, Pb, Nb, Pi, Ni = M3D.fr.posed(a, k)
            buf = np.concatenate([Pb.ravel(), Pi.ravel()]).astype(np.float32).tobytes()
        return self.send(200, buf, "application/octet-stream")

    def m3d_preview(self, a, k, d, s):
        with M3D.lock:
            if M3D.item is None:
                return self.send(409, {"error": "Najpierw wczytaj model."})
            M3D.ensure_cloth(a)
            img, poke = M3D.fr.frame(a, k, d, poke=True)
        base = body_underlay(H.load_config(), a, d, k)
        comp = themed_bg(composite(base, img))
        im = crop(comp, max(1, min(4, s)))
        b = io.BytesIO(); im.save(b, "PNG")
        return self.send(200, b.getvalue(), "image/png", {"X-Poke": str(poke or 0)})

    def vd_frame(self, cfg, q):
        from uo3d import vdread
        import numpy as np
        a, d, k = int(q.get("a", 4)), int(q.get("d", 0)), int(q.get("k", 0))
        _, _, A = vd_frames(q["path"])
        fr = A.get((a, d))
        top = vdread.canvas(fr[min(k, len(fr) - 1)]) if fr else np.zeros((256, 256, 4), np.uint8)
        base = body_underlay(cfg, a, d, k) if q.get("body", "1") == "1" else np.zeros_like(top)
        im = crop(themed_bg(composite(base, top)), int(q.get("s", 2)))
        b = io.BytesIO(); im.save(b, "PNG")
        return self.send(200, b.getvalue(), "image/png")


LAB_ROOTS: list[str] = []


def measure(actions):
    out = {}
    with M3D.lock:
        if M3D.item is None:
            raise ValueError("Najpierw wczytaj model.")
        E = M3D.engine()
        total = 0
        for a in actions:
            a = int(a)
            M3D.ensure_cloth(a)
            n = 0
            for k in range(E.ACTION_FRAMES[a]):
                posed = M3D.fr.posed(a, k)
                for d in range(5):
                    n += M3D.fr.frame(a, k, d, posed, poke=True)[1] or 0
            out[str(a)] = n; total += n
    return {"per_action": out, "total": total}


def works_root(cfg):
    """3D works: inside the toolkit workspace when it is set, otherwise in the output folder (or the home folder)."""
    if H.path_ok("toolkit", cfg.get("toolkit")):
        return H.workroot(cfg)
    if cfg.get("output"):
        return Path(cfg["output"]) / "prace3d"
    return Path.home() / "NelderimLab" / "prace3d"


def list_works(cfg):
    root = works_root(cfg)
    out = []
    if root.is_dir():
        for w in sorted(root.glob("*/model3d/work.json")):
            try:
                d = json.loads(w.read_text(encoding="utf-8"))
                out.append({"name": d.get("name", w.parent.parent.name), "kind": d.get("kind"), "item": d.get("item"),
                            "saved": d.get("saved"), "data": d})
            except (OSError, ValueError):
                pass
    return out


def state(cfg):
    paths = [{"key": k, "label": PL[k], "help": PATH_HELP[k], "kind": kind, "req": req, "value": cfg.get(k, ""),
              "ok": H.path_ok(k, cfg.get(k))} for k, (lab, kind, marker, req) in H.PATHS.items()]
    ex = H.model3d_extras(cfg) if cfg.get("bodyglb") else {}
    return {"paths": paths, "missing": H.missing(cfg), "extras": {k: (str(v) if v else None) for k, v in ex.items()},
            "toolkit": {"axisfit": H.path_ok("toolkit", cfg.get("toolkit")) and H.toolkit_has_axisfit(cfg),
                        "gump": H.path_ok("toolkit", cfg.get("toolkit")) and H.toolkit_has_gump(cfg)},
            "kinds3d": [{"label": l, "kind": k, "note": n} for l, k, n in H.KINDS3D], "held": sorted(H.HELD_KINDS),
            "actions": H.ACTION_NAMES, "frames": [10, 10, 10, 10, 1, 5, 5, 1, 1, 7, 7, 7, 7, 7, 7, 10, 7, 7, 7, 7, 5, 6, 6, 5, 5, 1, 5, 5, 7, 5, 5, 7, 5, 5, 5],
            "workroot": str(works_root(cfg)),
            "config_file": str(H.CONFIG_FILE), "theme": cfg.get("theme", "dark"), **wstate()}


def deps(cfg):
    def ok(cmd):
        try:
            r = subprocess.run(cmd["argv"], cwd=cmd["cwd"], env=cmd["env"], capture_output=True, text=True, timeout=60, **NOWIN)
            return "DEPS_OK" in r.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    out = {"self": ok(H.cmd_deps_check_sys(cfg))}
    out["toolkit"] = ok(H.cmd_deps_check(cfg)) if H.path_ok("toolkit", cfg.get("toolkit")) else None
    return out


def pick(kind, title, filt):
    """Native file / folder dialog in a helper process (tkinter)."""
    try:
        r = subprocess.run(self_cmd("--pick", kind, title, filt), capture_output=True, text=True, timeout=600, **NOWIN)
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def free_port(start=8774):
    for p in range(start, start + 30):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p)); return p
            except OSError:
                continue
    return 0


def serve(open_browser=True, port=None):
    cfg = H.load_config()
    if not cfg.get("pipeline"):
        cfg["pipeline"] = str(H.HERE); H.save_config(cfg)
    port = port or free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Nelderim Lab: {url}  (zamknij to okno, aby wyłączyć)", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: __import__("webbrowser").open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
