#!/usr/bin/env python3
"""
nelderim.py - the one entry point of the Nelderim asset pipeline (Nelderim Lab).

    python nelderim.py                 start the app (local web page in your browser)
    python nelderim.py --no-browser    start without opening the browser
    python nelderim.py --port 8774     fixed port

Tools from the command line (same scripts the app runs; `<tool> --help` for options):
    python nelderim.py search  --client <klient> --item staff        (nelderim_search.py)
    python nelderim.py patch   --client <klient> --recipe r.json --out wyniki [--apply]   (nelderim_patch.py)
    python nelderim.py inject  --client <klient> --vd potwor.vd [--apply]               (vd_inject.py)
    python nelderim.py wire    --client <klient> --file 5 [--apply]                      (anim_wire.py)
    python nelderim.py uopatch | gumppatch ...                                          (uopatch.py, uop_gump_patch.py)
    python nelderim.py uo3d    --body ... --item ... --kind ...                          (uo3d/cli_render.py)
    python nelderim.py vd2glb  --body ... --vd ... --out ...                             (uo3d/cli_vd2glb.py)
The same works with Nelderim.exe instead of `python nelderim.py`.

Helper modes (used by the app itself, also inside the frozen exe):
    --run-script FILE.py [args]   run one of the pipeline's .py tools (pipeline/nelderim_patch.py, uo3d/cli_render.py, ...)
    --uo3d [args]                 the 3D renderer (uo3d/cli_render.py)
    --pick file|dir|save TITLE [FILTER]   native file dialog, prints the chosen path
    --deps-ok                     prints DEPS_OK when numpy and Pillow import
    --py [-c CODE | SCRIPT.py] [args]   acts as `python` for Levy's toolkit scripts (exe without Python installed)
"""
import os
import runpy
import sys
from pathlib import Path

HERE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
for _p in (HERE, HERE / "lab", HERE / "pipeline"):          # program root, app server, client tools
    sys.path.insert(0, str(_p))


def pick(kind, title, filt=""):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    types = [("Wszystkie pliki", "*.*")]
    if filt:
        types = [(filt, " ".join("*" + e.strip() for e in filt.split(","))), ("Wszystkie pliki", "*.*")]
    if kind == "dir":
        p = filedialog.askdirectory(title=title, parent=root)
    elif kind == "save":
        p = filedialog.asksaveasfilename(title=title, parent=root, filetypes=types)
    else:
        p = filedialog.askopenfilename(title=title, parent=root, filetypes=types)
    root.destroy()
    print(p or "", flush=True)


def _utf8_console():
    """child output is read as UTF-8 by the app; the frozen exe ignores PYTHONIOENCODING, so set it here."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


TOOLS = {"search": "pipeline/nelderim_search.py", "patch": "pipeline/nelderim_patch.py", "inject": "pipeline/vd_inject.py",
         "wire": "pipeline/anim_wire.py", "uopatch": "pipeline/uopatch.py", "gumppatch": "pipeline/uop_gump_patch.py",
         "uo3d": "uo3d/cli_render.py", "vd2glb": "uo3d/cli_vd2glb.py"}


def main(argv):
    _utf8_console()
    if argv[:1] and argv[0] in TOOLS:
        return main(["--run-script", str(HERE / TOOLS[argv[0]]), *argv[1:]])
    if argv[:1] == ["--run-script"]:
        script = Path(argv[1]).resolve()
        sys.argv = [str(script), *argv[2:]]
        sys.path.insert(0, str(script.parent))
        runpy.run_path(str(script), run_name="__main__")
        return 0
    if argv[:1] == ["--py"]:
        rest = argv[1:]
        if rest[:1] == ["-c"]:
            sys.argv = ["-c", *rest[2:]]
            sys.path.insert(0, os.getcwd())
            exec(compile(rest[1], "<string>", "exec"), {"__name__": "__main__"})
            return 0
        if rest[:1] == ["-m"]:
            print("Ten program (.exe) nie instaluje bibliotek – numpy i Pillow są już w środku.", file=sys.stderr)
            return 1
        return main(["--run-script", *rest])
    if argv[:1] == ["--uo3d"]:
        from uo3d import cli_render
        cli_render.main(argv[1:])
        return 0
    if argv[:1] == ["--pick"]:
        pick(argv[1] if len(argv) > 1 else "file", argv[2] if len(argv) > 2 else "Wybierz", argv[3] if len(argv) > 3 else "")
        return 0
    if argv[:1] == ["--deps-ok"]:
        import numpy  # noqa: F401,F811
        import PIL  # noqa: F401,F811
        print("DEPS_OK")
        return 0
    if argv[:1] and not argv[0].startswith("-"):
        print(f"Nieznana komenda: {argv[0]}. Dostępne: {', '.join(TOOLS)} (albo bez argumentów = aplikacja).", file=sys.stderr)
        return 2
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else None
    import nelderim_app
    nelderim_app.serve(open_browser="--no-browser" not in argv, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
