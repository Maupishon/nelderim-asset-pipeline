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

HERE = Path(__file__).resolve().parent
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
    names = {"client": ["Nelderim"], "toolkit": ["SpriteMotion-UO-Toolkit", "SpriteMotion"],
             "fiddler": ["UO Fiddler"], "serv": ["ServUO-master"], "vdtool": ["vdtool"]}.get(key, [])
    out = []
    for base in (HERE.parent, HERE.parent.parent, Path.home()):
        for n in names:
            for cand in (base / n, base / n / n):
                if cand.is_dir():
                    out.append(str(cand))
    return out


# --------------------------------------------------------- command builders
def toolkit_python(cfg: dict) -> str:
    tk = Path(cfg["toolkit"])
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python", ".venvs/spritemotion/Scripts/python.exe"):
        if (tk / rel).is_file():
            return str(tk / rel)
    return sys.executable


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
    return _tk(cfg, "games/ultima-online/outfit-lab/verify.py", lab)


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
    return {"argv": [sys.executable, str(Path(cfg["pipeline"]) / script), *map(str, args)],
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


def open_path(p: str) -> None:
    if os.name == "nt":
        os.startfile(p)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


# ------------------------------------------------------------------- GUI
def run_gui() -> None:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext

    cfg = load_config()
    root = tk.Tk()
    root.title("Nelderim Hub")
    root.geometry("1000x760")
    logq: queue.Queue = queue.Queue()
    server = {"proc": None}
    busy = {"on": False}

    log = scrolledtext.ScrolledText(root, height=16, state="disabled", font=("Consolas", 9))

    def say(text):
        logq.put(text)

    def pump():
        try:
            while True:
                t = logq.get_nowait()
                log.configure(state="normal")
                log.insert("end", t if t.endswith("\n") else t + "\n")
                log.see("end")
                log.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(80, pump)

    def stream(cmd, capture=None) -> int:
        say("$ " + " ".join(f'"{a}"' if " " in a else a for a in cmd["argv"]))
        try:
            p = subprocess.Popen(cmd["argv"], cwd=cmd["cwd"], env=cmd["env"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            say(f"[ERROR] {e}")
            return 1
        for line in p.stdout:
            if capture is not None:
                capture.append(line)
            say(line.rstrip("\n"))
        return p.wait()

    def run_steps(steps):
        """steps: callables returning a cmd dict, or None to stop; run one after another off the UI thread."""
        if busy["on"]:
            messagebox.showinfo("Busy", "Wait for the current job to finish.")
            return
        if not ready():
            return

        def work():
            busy["on"] = True
            try:
                for s in steps:
                    cmd = s()
                    if cmd is None:
                        say("[STOPPED]")
                        return
                    rc = stream(cmd)
                    if rc != 0:
                        say(f"[FAILED] exit code {rc}")
                        return
                say("[DONE]")
            except Exception as e:  # noqa: BLE001
                say(f"[ERROR] {e}")
            finally:
                busy["on"] = False

        threading.Thread(target=work, daemon=True).start()

    def ready(keys=None):
        bad = [k for k in (keys or missing(cfg)) if not path_ok(k, cfg.get(k))]
        if bad:
            messagebox.showwarning("Paths", "Set these on the Paths tab first:\n" +
                                   "\n".join("- " + PATHS[k][0] for k in bad))
            nb.select(0)
            return False
        return True

    # ---- widgets helpers
    def field(parent, row, label, var, browse=None, width=60):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
        e = ttk.Entry(parent, textvariable=var, width=width)
        e.grid(row=row, column=1, sticky="we", padx=6, pady=3)
        if browse:
            def pick():
                if browse == "dir":
                    v = filedialog.askdirectory(title=label)
                elif browse == "save":
                    v = filedialog.asksaveasfilename(title=label)
                else:
                    v = filedialog.askopenfilename(title=label)
                if v:
                    var.set(v)
            ttk.Button(parent, text="Browse...", command=pick).grid(row=row, column=2, padx=6)
        parent.columnconfigure(1, weight=1)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=8)
    log.pack(fill="both", expand=False, padx=8, pady=(0, 8))

    # ---- tab 0: paths
    tp = ttk.Frame(nb)
    nb.add(tp, text="Paths")
    pvars = {k: tk.StringVar(value=cfg.get(k, "")) for k in PATHS}
    stat = {}
    ttk.Label(tp, text="Where is each tool on THIS machine? Saved per user in " + str(CONFIG_FILE),
              foreground="#555").grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=6)
    for r, (k, (label, kind, marker, req)) in enumerate(PATHS.items(), start=1):
        field(tp, r, label + ("" if req else "  (optional)"), pvars[k], browse=kind)
        stat[k] = ttk.Label(tp, text="")
        stat[k].grid(row=r, column=3, padx=6)

    def refresh_status():
        for k in PATHS:
            ok = path_ok(k, pvars[k].get().strip())
            stat[k].configure(text="OK" if ok else ("missing" if PATHS[k][3] else "-"),
                              foreground="#187a2f" if ok else ("#a8322d" if PATHS[k][3] else "#888"))

    def save_paths():
        for k in PATHS:
            v = pvars[k].get().strip()
            if v:
                cfg[k] = v
            else:
                cfg.pop(k, None)
        if cfg.get("output"):
            try:
                Path(cfg["output"]).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Output", str(e))
        save_config(cfg)
        refresh_status()
        say("Paths saved.")

    def ask_missing():
        """Wizard: one folder dialog per missing path (Cancel skips)."""
        for k in list(PATHS):
            if path_ok(k, pvars[k].get().strip()):
                continue
            label, kind, marker, req = PATHS[k]
            if k == "pipeline" and path_ok(k, str(HERE)):
                pvars[k].set(str(HERE))
                continue
            if not req:
                continue
            g = guesses(k)
            messagebox.showinfo("Where is it?", f"Select: {label}")
            v = (filedialog.askdirectory(title=label, initialdir=g[0] if g else str(Path.home()))
                 if kind == "dir" else filedialog.askopenfilename(title=label))
            if v:
                pvars[k].set(v)
        save_paths()

    bt = ttk.Frame(tp)
    bt.grid(row=len(PATHS) + 1, column=0, columnspan=4, pady=10)
    ttk.Button(bt, text="Save", command=save_paths).pack(side="left", padx=6)
    ttk.Button(bt, text="Ask me for missing paths", command=ask_missing).pack(side="left", padx=6)

    # ---- tab 1: outfit lab (whole set)
    t1 = ttk.Frame(nb)
    nb.add(t1, text="Outfit set")
    v1 = {k: tk.StringVar() for k in ("design", "sword", "config", "out", "actions")}
    v1["actions"].set("0 4 9 16")
    v1["out"].set("")
    field(t1, 0, "Design sheet PNG (4x3 cells, alpha)", v1["design"], "file")
    field(t1, 1, "Sword PNG (horizontal, hilt on the left)", v1["sword"], "file")
    field(t1, 2, "Config JSON (items, cells, ...)", v1["config"], "file")
    field(t1, 3, "Output lab folder", v1["out"], "dir")
    field(t1, 4, "Actions (space separated, empty = all 35)", v1["actions"])
    ttk.Label(t1, text="Example inputs: <toolkit>/workspace/ultima-online/witcher-lab/",
              foreground="#555").grid(row=5, column=0, columnspan=3, sticky="w", padx=6)

    def use_example():
        base = Path(cfg.get("toolkit", "")) / "workspace/ultima-online/witcher-lab"
        v1["design"].set(str(base / "witcher_design.png"))
        v1["sword"].set(str(base / "witcher_sword.png"))
        v1["config"].set(str(base / "witcher.json"))
        v1["out"].set(str(base / "lab"))

    def do_build_set():
        if not all(v1[k].get().strip() for k in ("design", "sword", "config", "out")):
            messagebox.showwarning("Build", "Fill design, sword, config and output.")
            return
        run_steps([lambda: cmd_build_set(cfg, v1["out"].get(), v1["design"].get(), v1["sword"].get(),
                                         v1["config"].get(), v1["actions"].get())])

    fr = ttk.Frame(t1)
    fr.grid(row=6, column=0, columnspan=3, pady=10)
    ttk.Button(fr, text="Fill Witcher example", command=use_example).pack(side="left", padx=6)
    ttk.Button(fr, text="Build", command=do_build_set).pack(side="left", padx=6)
    ttk.Button(fr, text="Verify", command=lambda: run_steps([lambda: cmd_verify(cfg, v1["out"].get())])
               ).pack(side="left", padx=6)
    ttk.Button(fr, text="Preview in browser", command=lambda: start_preview(v1["out"].get())
               ).pack(side="left", padx=6)

    # ---- tab 2: single item
    t2 = ttk.Frame(nb)
    nb.add(t2, text="Single item")
    v2 = {k: tk.StringVar() for k in ("graphic", "design", "key", "title", "hide", "actions", "out")}
    v2["key"].set("item")
    field(t2, 0, "ItemID (e.g. 0x2684)", v2["graphic"])
    field(t2, 1, "Design PNG (front view, alpha)", v2["design"], "file")
    field(t2, 2, "Key (short name)", v2["key"])
    field(t2, 3, "Viewer title (optional)", v2["title"])
    field(t2, 4, "Hide region ids (e.g. 1 5 = face and hands)", v2["hide"])
    field(t2, 5, "Actions (empty = all)", v2["actions"])
    field(t2, 6, "Output lab folder", v2["out"], "dir")

    def do_build_item():
        if not all(v2[k].get().strip() for k in ("graphic", "design", "key", "out")):
            messagebox.showwarning("Build", "Fill ItemID, design, key and output.")
            return
        run_steps([lambda: cmd_build_item(cfg, v2["graphic"].get(), v2["design"].get(), v2["out"].get(),
                                          v2["key"].get(), v2["title"].get(), v2["hide"].get(),
                                          v2["actions"].get())])

    ttk.Button(t2, text="Build item", command=do_build_item).grid(row=7, column=1, pady=10, sticky="w")
    ttk.Button(t2, text="Preview in browser", command=lambda: start_preview(v2["out"].get())
               ).grid(row=7, column=1, pady=10)

    # ---- tab 3: pack to .vd
    t3 = ttk.Frame(nb)
    nb.add(t3, text="Pack to .vd")
    v3 = {"lab": tk.StringVar(), "item": tk.StringVar(), "body": tk.StringVar(), "outline": tk.StringVar(value="1"),
          "out": tk.StringVar()}
    field(t3, 0, "Built lab folder (has manifest.json)", v3["lab"], "dir")
    ttk.Label(t3, text="Item").grid(row=1, column=0, sticky="w", padx=6, pady=3)
    combo = ttk.Combobox(t3, textvariable=v3["item"], state="readonly", width=40)
    combo.grid(row=1, column=1, sticky="w", padx=6)
    items_cache = {}

    def load_items():
        try:
            its = lab_items(v3["lab"].get())
        except (OSError, ValueError, KeyError) as e:
            messagebox.showwarning("Lab", f"Cannot read manifest.json: {e}")
            return
        items_cache.clear()
        for k, a in its:
            items_cache[f"{k}  (animId {a})"] = (k, a)
        combo["values"] = list(items_cache)
        if items_cache:
            combo.current(0)

    ttk.Button(t3, text="Load items", command=load_items).grid(row=1, column=2, padx=6)
    field(t3, 2, "Body .vd (empty = extract body 400 from client)", v3["body"], "file")
    field(t3, 3, "Outline px (0 = none; 1 for weapons)", v3["outline"])
    field(t3, 4, "Output .vd (empty = <toolkit>/workspace/ultima-online/vd/new_<id>.vd)", v3["out"], "save")

    def do_pack():
        sel = items_cache.get(v3["item"].get())
        if not sel or not v3["lab"].get().strip():
            messagebox.showwarning("Pack", "Choose a lab folder and click Load items.")
            return
        key, aid = sel
        target = equip_target(cfg, aid)          # animation actually used for body 400
        orig = vd_original(cfg, target)
        body = Path(v3["body"].get().strip()) if v3["body"].get().strip() else vd_original(cfg, 400)
        out = v3["out"].get().strip() or str(workdir(cfg) / f"new_{target:04d}.vd")
        def check():
            cap = []
            rc = stream(cmd_conv_check(cfg, target), cap)
            txt = "".join(cap)
            if rc != 0 or "INMUL" not in txt:
                say(f"[!] Animation {target} is not in anim.mul (Bodyconv -> anim2..5.mul). "
                    f"Extract it with UOFiddler to {orig}, then run again.")
                return None if not orig.exists() else {"argv": [sys.executable, "-c", "pass"],
                                                       "cwd": str(HERE), "env": dict(os.environ)}
            return {"argv": [sys.executable, "-c", "pass"], "cwd": str(HERE), "env": dict(os.environ)}

        def extract_orig():
            if orig.exists():
                say(f"Using existing {orig}")
                return {"argv": [sys.executable, "-c", "pass"], "cwd": str(HERE), "env": dict(os.environ)}
            return cmd_mul2vd(cfg, target)

        def extract_body():
            if body.exists():
                return {"argv": [sys.executable, "-c", "pass"], "cwd": str(HERE), "env": dict(os.environ)}
            return cmd_mul2vd(cfg, 400)

        def pack():
            return cmd_atlas_to_vd(cfg, v3["lab"].get(), key, str(orig), out, str(body), v3["outline"].get().strip())

        run_steps([check, extract_orig, extract_body, pack, lambda: cmd_vd_info(cfg, out)])

    ttk.Button(t3, text="Extract original + pack", command=do_pack).grid(row=5, column=1, pady=10, sticky="w")
    ttk.Label(t3, text="Import result: UOFiddler > Animations > Animation Edit > Import from VD > Save "
                       "(on a COPY of the client).", foreground="#555").grid(row=6, column=0, columnspan=3, padx=6)

    # ---- tab 4: viewers
    t4 = ttk.Frame(nb)
    nb.add(t4, text="Viewers / tools")

    def start_preview(lab):
        if not ready(["toolkit", "client"]):
            return
        if not lab.strip() or not (Path(lab) / "index.html").is_file():
            messagebox.showwarning("Preview", "Build the lab first (no index.html in the output folder).")
            return
        stop_preview()
        cmd = cmd_serve(cfg, lab)
        server["proc"] = subprocess.Popen(cmd["argv"], cwd=cmd["cwd"], env=cmd["env"],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        say(f"Preview server: http://127.0.0.1:{PORT}  ({lab})")
        root.after(700, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}"))

    def stop_preview():
        p = server["proc"]
        if p and p.poll() is None:
            p.terminate()
        server["proc"] = None

    def open_viewer():
        p = cfg.get("vdviewer")
        if not p or not Path(p).is_file():
            messagebox.showwarning("VD viewer", "Set vd-viewer.html on the Paths tab.")
            return
        webbrowser.open(Path(p).as_uri())

    def open_fiddler():
        d = Path(cfg.get("fiddler", ""))
        exe = next(iter(d.glob("UOFiddler*.exe")), None) if d.is_dir() else None
        if not exe:
            messagebox.showwarning("UOFiddler", "Set the UOFiddler folder on the Paths tab.")
            return
        subprocess.Popen([str(exe)], cwd=str(d))

    def open_dir(key):
        p = cfg.get(key)
        if p and Path(p).exists():
            open_path(p)
        else:
            messagebox.showwarning("Open", f"Path '{key}' not set.")

    for r, (txt, fn) in enumerate([
        ("Stop preview server", stop_preview),
        ("Open vd-viewer.html", open_viewer),
        ("Open UOFiddler", open_fiddler),
        ("Open output folder", lambda: open_dir("output")),
        ("Open ServUO folder", lambda: open_dir("serv")),
    ]):
        ttk.Button(t4, text=txt, command=fn, width=28).grid(row=r, column=0, padx=10, pady=6, sticky="w")

    # ---- tab 5: pipeline
    t5 = ttk.Frame(nb)
    nb.add(t5, text="Pipeline (patch)")
    v5 = {"query": tk.StringVar(), "recipe": tk.StringVar()}
    field(t5, 0, "Search item / id / name", v5["query"])
    ttk.Button(t5, text="Search", command=lambda: run_steps([lambda: cmd_search(cfg, v5["query"].get())])
               ).grid(row=0, column=2, padx=6)
    field(t5, 1, "Recipe JSON", v5["recipe"], "file")

    def do_patch(apply):
        if not v5["recipe"].get().strip():
            messagebox.showwarning("Patch", "Pick a recipe JSON.")
            return
        if apply and not messagebox.askyesno("Apply", "Write changes to the client?\n"
                                             "Did you review the dry run and use a COPY of the client?"):
            return
        run_steps([lambda: cmd_patch(cfg, v5["recipe"].get(), apply)])

    fp = ttk.Frame(t5)
    fp.grid(row=2, column=0, columnspan=3, pady=10)
    ttk.Button(fp, text="Dry run (safe)", command=lambda: do_patch(False)).pack(side="left", padx=6)
    ttk.Button(fp, text="Apply...", command=lambda: do_patch(True)).pack(side="left", padx=6)
    def open_pipeline_gui():
        if ready(["pipeline"]):
            c = cmd_pipeline_gui(cfg)
            subprocess.Popen(c["argv"], cwd=c["cwd"], env=c["env"])

    ttk.Button(fp, text="Open full pipeline GUI", command=open_pipeline_gui).pack(side="left", padx=6)

    def on_close():
        stop_preview()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_status()
    pump()
    if missing(cfg):
        root.after(300, lambda: (messagebox.showinfo(
            "Welcome", "First run: I need to know where your tools live.\nYou will be asked for each missing "
                       "folder (Cancel skips one)."), ask_missing()))
    root.mainloop()


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
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
