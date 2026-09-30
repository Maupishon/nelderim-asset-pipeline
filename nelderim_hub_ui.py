"""
nelderim_hub_ui.py - the beginner-friendly (Polish) window of nelderim_hub.

No format logic here either: every button builds a command with the helpers of nelderim_hub (H) and runs it.
Ideas: a start screen with plain-language tasks, numbered steps with a short explanation, tooltips on every field,
right-click menus, automatic folders (you only type a work name), friendly hints when a known error appears.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

MUTED, OKC, BADC, ACC = "muted", "ok", "bad", "acc"      # status levels -> ttk styles Muted/Ok/Bad/Acc.TLabel

# palette taken from Levy's vd-viewer (warm neutral + amber accent, light and dark)
THEMES = {
    "light": dict(bg="#eef0ee", panel="#f8f9f7", line="#d3d8d2", fg="#1d2420", muted="#5d6a62", accent="#a4661c",
                  accent_fg="#ffffff", btn="#ffffff", btnline="#bcc4bb", soft="#f2e2cb", stage="#26302a", stage_fg="#f2e2cb", ok="#2f7a45", bad="#a8322d"),
    "dark": dict(bg="#151a17", panel="#1c2320", line="#2f3a34", fg="#e3e8e4", muted="#93a198", accent="#e0a458",
                 accent_fg="#1d2420", btn="#28322d", btnline="#4b5d52", soft="#3a2d1c", stage="#0e1311", stage_fg="#e0a458", ok="#7fbf8f", bad="#f08a84"),
}
T = dict(THEMES["light"])
REG = {"canvas": [], "menu": [], "tk": []}       # widgets that ttk styles cannot reach: recolored on theme change


def sty(level):
    return {"muted": "Muted.TLabel", "ok": "Ok.TLabel", "bad": "Bad.TLabel", "acc": "Acc.TLabel"}.get(level, "Status.TLabel")


def system_theme():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except Exception:  # noqa: BLE001
        return "light"


def pick_font(root, names, default):
    from tkinter import font as tkfont
    have = {f.lower(): f for f in tkfont.families(root)}
    for n in names:
        if n.lower() in have:
            return have[n.lower()]
    return default

# known error text -> plain-language advice
HINTS = [
    (r"Empty design", "Któraś komórka arkusza wzoru jest pusta (albo obrazek jest w całości przezroczysty). "
                      "Każdy przedmiot musi leżeć na środku swojej komórki."),
    (r"unrecognized arguments: --config", "Masz starą wersję build.py w toolkicie. Skopiuj paczkę Levy'ego v2 "
                                          "(SpriteMotion_skrypty_Nelderim_1.zip) do folderu toolkitu, z nadpisaniem."),
    (r"No module named '?(numpy|PIL|scipy)", "Brakuje bibliotek w środowisku toolkitu. W PowerShellu, w folderze toolkitu: "
                                             ".venv\\Scripts\\activate  a potem  python -m pip install numpy pillow scipy"),
    (r"FileNotFoundError.*(anim\.idx|anim\.mul|tiledata|Gumpidx|Gumpart|Equipconv|Bodyconv|Body\.def)",
     "Nie znaleziono pliku klienta UO. W Ustawieniach wskaż folder, w którym leżą pliki .mul i .def klienta."),
    (r"region_ids\.png", "Brakuje masek regionów ciała w toolkicie (workspace/ultima-online/region-audit/...). "
                         "Rozpakuj kompletny toolkit SpriteMotion."),
    (r"Only human/equipment animation IDs", "To nie jest animacja ubrania (ID poniżej 400). Wybierz inny przedmiot."),
    (r"requires a DEF remapping", "Ta animacja jest przekierowana w Body.def. Ten program jej nie obsługuje."),
    (r"Truncated animation record|Invalid frame|Animation run outside", "Dane animacji w kliencie są nietypowe lub uszkodzone."),
    (r"PermissionError|Permission denied", "Brak uprawnień do zapisu. Zamknij programy używające pliku albo wybierz inny folder."),
    (r"Original gump \d+ not found", "Tego gumpu nie ma w Gumpidx/Gumpart.mul (może leży w pliku .uop)."),
]

PL = {"client": "Folder klienta UO (kopia!)", "toolkit": "Folder toolkitu SpriteMotion",
      "pipeline": "Folder tego programu (pipeline)", "output": "Folder na wyniki dodawania",
      "vdviewer": "Plik vd-viewer.html", "fiddler": "Folder UOFiddlera", "serv": "Folder ServUO", "vdtool": "Folder vdtool"}

HELP = """SŁOWNICZEK

ItemID – numer przedmiotu (np. 0x2684). Znajdziesz go w UOFiddlerze: zakładka Items, kolumna ID.
Animacja – to, jak przedmiot wygląda na ruszającej się postaci. Każdy przedmiot ma swój numer animacji.
.vd – plik animacji, który wczytujesz do UOFiddlera (Animation Edit → Import from VD).
Gump – obrazek przedmiotu na lalce postaci (okno Paperdoll).
PNG z przezroczystym tłem – obrazek bez tła (przezroczysty). Tło musi być wycięte, inaczej dostaniesz kwadrat.
Przymiarka / build – program dopasowuje Twój obrazek do oryginalnych klatek animacji (zachowuje kształt i fałdy, zmienia materiał).
Podgląd – strona w przeglądarce, na której porównujesz oryginał (UO) z wynikiem (New) na różnych akcjach i kierunkach.
Akcje – ruchy postaci: 0 chodzenie, 4 stanie, 9 cięcie, 13 cięcie dwuręczne, 16 czar. Wszystkich jest 35.
Kopia klienta – WSZYSTKIE zmiany rób na kopii folderu z grą, nigdy na jedynym egzemplarzu.
Dry run – „na sucho": pokazuje, co by się zmieniło, niczego nie zapisuje. Zawsze rób go przed „Zastosuj".

TYPOWA KOLEJNOŚĆ
1. Ustawienia: wskaż foldery (raz).
2. Wybierz zadanie na ekranie Start (ubranie, broń albo gump).
3. Idź krok po kroku. Każdy krok ma opis. Najedź myszą na pole, żeby zobaczyć podpowiedź.
4. Zbuduj na próbę kilka akcji, obejrzyj podgląd, popraw, dopiero potem zbuduj wszystkie 35.
5. Spakuj do .vd i zaimportuj w UOFiddlerze (na kopii klienta).

PRAWY PRZYCISK MYSZY w polach tekstowych: wklej, kopiuj, wybierz plik, otwórz folder.

CO ZNACZĄ KOMUNIKATY
„✓" – krok się udał. „✗" – coś nie tak, obok jest podpowiedź. Pełny zapis pracy programu: przycisk „Szczegóły" na dole.
"""


class Tip:
    """Small hover tooltip."""

    def __init__(self, w, text):
        self.w, self.text, self.tw, self.job = w, text, None, None
        w.bind("<Enter>", self._enter, add="+")
        w.bind("<Leave>", self._leave, add="+")
        w.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e):
        self.job = self.w.after(450, self._show)

    def _leave(self, _e=None):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
        if self.tw:
            self.tw.destroy()
            self.tw = None

    def _show(self):
        self.tw = tw = tk.Toplevel(self.w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{self.w.winfo_rootx() + 16}+{self.w.winfo_rooty() + self.w.winfo_height() + 4}")
        tk.Label(tw, text=self.text, justify="left", background=T["soft"], foreground=T["fg"], relief="solid", borderwidth=1,
                 wraplength=380, padx=6, pady=4).pack()


def popup(widget, items):
    """Right-click menu. items: [(label, callable) | None for a separator]."""
    m = tk.Menu(widget, tearoff=0)
    REG["menu"].append(m)
    m.configure(background=T["panel"], foreground=T["fg"], activebackground=T["soft"], activeforeground=T["fg"],
                borderwidth=1, relief="solid")
    for it in items:
        if it is None:
            m.add_separator()
        else:
            m.add_command(label=it[0], command=it[1])

    def show(e):
        try:
            widget.focus_set()
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
        return "break"

    for b in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
        widget.bind(b, show, add="+")


class Step(ttk.LabelFrame):
    def __init__(self, parent, num, title, text):
        super().__init__(parent, text=f"  Krok {num}: {title}  ", padding=10)
        self.pack(fill="x", padx=10, pady=6)
        ttk.Label(self, text=text, wraplength=700, justify="left", style=sty(MUTED)).pack(anchor="w")
        self.body = ttk.Frame(self)
        self.body.pack(fill="x", pady=(6, 0))
        self.result = ttk.Label(self, text="", wraplength=700, justify="left")
        self.result.pack(anchor="w", pady=(4, 0))

    def ok(self, msg):
        self.result.configure(text="✓ " + msg, style=sty(OKC))

    def bad(self, msg):
        self.result.configure(text="✗ " + msg, style=sty(BADC))

    def info(self, msg):
        self.result.configure(text=msg, style=sty(MUTED))


class Scroll(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=T["panel"])
        REG["canvas"].append(self.canvas)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(ev, self._wheel, add="+")

    def _wheel(self, e):
        if not self.winfo_ismapped():
            return
        num = getattr(e, "num", 0)
        d = -1 if num == 4 else 1 if num == 5 else (-1 if e.delta > 0 else 1)
        self.canvas.yview_scroll(d, "units")


class App:
    def __init__(self, H):
        self.H = H
        self.cfg = H.load_config()
        self.root = tk.Tk()
        self.root.title("Nelderim Hub – kreator")
        self.root.geometry("1180x820")
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.server = None
        self.last_lab = ""
        self.pages: dict[str, tuple] = {}
        self.current = None
        self.current_key = "start"
        self.navbtns: dict[str, ttk.Button] = {}
        pref = self.cfg.get("theme", "auto")
        self.theme = system_theme() if pref == "auto" else pref
        self.apply_theme(first=True)
        self._build_shell()
        self.apply_theme()
        self.root.after(80, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ------------------------------------------------------------ theme
    def apply_theme(self, first=False):
        r = self.root
        T.update(THEMES[self.theme])
        body = pick_font(r, ["IBM Plex Sans", "Segoe UI", "Helvetica Neue", "DejaVu Sans", "Arial"], "TkDefaultFont")
        disp = pick_font(r, ["Alegreya Sans SC", "Trebuchet MS", "Segoe UI Semibold", "DejaVu Sans"], body)
        mono = pick_font(r, ["IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono"], "TkFixedFont")
        self.fonts = dict(body=body, disp=disp, mono=mono)
        from tkinter import font as tkfont
        for n in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(n).configure(family=body, size=10)
        st = ttk.Style(r)
        st.theme_use("clam")
        bg, pn, ln, fg, mu, ac = T["bg"], T["panel"], T["line"], T["fg"], T["muted"], T["accent"]
        r.configure(background=bg)
        st.configure(".", background=pn, foreground=fg, bordercolor=ln, lightcolor=pn, darkcolor=pn, troughcolor=bg,
                     focuscolor=ac, fieldbackground=pn, insertcolor=fg, font=(body, 10))
        st.configure("TFrame", background=pn)
        st.configure("TLabel", background=pn, foreground=fg)
        for name, col in (("Muted", mu), ("Ok", T["ok"]), ("Bad", T["bad"]), ("Acc", ac), ("Status", fg)):
            st.configure(f"{name}.TLabel", background=pn, foreground=col)
        st.configure("Status.TLabel", background=bg, foreground=fg)
        st.configure("Title.TLabel", font=(disp, 20, "bold"), foreground=fg)
        st.configure("CardTitle.TLabel", font=(disp, 13, "bold"), foreground=fg)
        st.configure("TLabelframe", background=pn, bordercolor=ln, relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=pn, foreground=mu, font=(disp, 11, "bold"))
        st.configure("Card.TFrame", background=pn, bordercolor=ln, relief="solid", borderwidth=1)
        st.configure("CardHot.TFrame", background=pn, bordercolor=ac, relief="solid", borderwidth=1)
        st.configure("Nav.TFrame", background=bg)
        st.configure("TButton", background=T["btn"], foreground=fg, bordercolor=T["btnline"], relief="flat",
                     padding=(10, 5), borderwidth=1, lightcolor=T["btn"], darkcolor=T["btn"])
        st.map("TButton", bordercolor=[("active", ac), ("focus", ac)], background=[("active", T["btn"]), ("disabled", bg)],
               foreground=[("disabled", mu)])
        st.configure("Big.TButton", background=ac, foreground=T["accent_fg"], bordercolor=ac, padding=(14, 8),
                     font=(body, 10, "bold"))
        st.map("Big.TButton", background=[("active", ac), ("pressed", ac)], bordercolor=[("active", fg)],
               foreground=[("disabled", mu)])
        st.configure("Nav.TButton", background=bg, foreground=fg, bordercolor=bg, borderwidth=0, padding=(12, 8),
                     anchor="w", relief="flat")
        st.map("Nav.TButton", background=[("active", T["soft"])], bordercolor=[("active", T["soft"])])
        st.configure("NavSel.TButton", background=T["soft"], foreground=ac, bordercolor=ac, borderwidth=0,
                     padding=(12, 8), anchor="w", relief="flat", font=(body, 10, "bold"))
        st.map("NavSel.TButton", background=[("active", T["soft"])], bordercolor=[("active", ac)])
        st.configure("TEntry", fieldbackground=T["btn"], background=T["btn"], foreground=fg, bordercolor=T["btnline"], padding=4)
        st.map("TEntry", bordercolor=[("focus", ac)])
        st.configure("TCombobox", fieldbackground=T["btn"], background=T["btn"], foreground=fg, bordercolor=T["btnline"], arrowcolor=mu,
                     padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", T["btn"])], bordercolor=[("focus", ac)],
               foreground=[("readonly", fg)], selectbackground=[("readonly", T["btn"])], selectforeground=[("readonly", fg)])
        r.option_add("*TCombobox*Listbox.background", pn)
        r.option_add("*TCombobox*Listbox.foreground", fg)
        r.option_add("*TCombobox*Listbox.selectBackground", T["soft"])
        r.option_add("*TCombobox*Listbox.selectForeground", ac)
        st.configure("TCheckbutton", background=pn, foreground=fg, indicatorcolor=pn)
        st.map("TCheckbutton", indicatorcolor=[("selected", ac)], background=[("active", pn)])
        st.configure("Vertical.TScrollbar", background=ln, troughcolor=bg, bordercolor=bg, arrowcolor=mu)
        st.configure("TNotebook", background=pn)
        for c in REG["canvas"]:
            c.configure(background=pn)
        for m in REG["menu"]:
            m.configure(background=pn, foreground=fg, activebackground=T["soft"], activeforeground=fg)
        for w, kind in REG["tk"]:
            if kind == "header":
                w.configure(background=T["stage"])
            elif kind == "title":
                w.configure(background=T["stage"], foreground=T["stage_fg"], font=(disp, 18, "bold"))
            elif kind == "sub":
                w.configure(background=T["stage"], foreground="#9fb0a6", font=(body, 9))
            elif kind == "toggle":
                w.configure(background=T["stage"], foreground=T["stage_fg"], activebackground=T["stage"],
                            activeforeground="#ffffff")
            elif kind == "log":
                w.configure(background=T["stage"], foreground="#d7e2db", insertbackground="#d7e2db",
                            font=(mono, 9))
        if not first:
            self.show(self.current_key)

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.cfg["theme"] = self.theme
        self.H.save_config(self.cfg)
        self.apply_theme()

    # ------------------------------------------------------------ shell
    def _build_shell(self):
        r = self.root
        r.columnconfigure(1, weight=1)
        r.rowconfigure(1, weight=1)
        head = tk.Frame(r, padx=16, pady=10)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        REG["tk"].append((head, "header"))
        box = tk.Frame(head)
        box.pack(side="left")
        REG["tk"].append((box, "header"))
        t = tk.Label(box, text="Nelderim Hub", anchor="w")
        t.pack(anchor="w")
        REG["tk"].append((t, "title"))
        sub = tk.Label(box, text="animacje ubrań i broni do Ultima Online – krok po kroku", anchor="w")
        sub.pack(anchor="w")
        REG["tk"].append((sub, "sub"))
        tg = tk.Button(head, text="◐  jasny / ciemny", relief="flat", borderwidth=0, cursor="hand2",
                       command=self.toggle_theme)
        tg.pack(side="right")
        REG["tk"].append((tg, "toggle"))
        Tip(tg, "Przełącz jasny / ciemny motyw.")
        nav = ttk.Frame(r, padding=(8, 10), style="Nav.TFrame")
        nav.grid(row=1, column=0, sticky="ns")
        self.content = ttk.Frame(r)
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        for key, label in [("start", "🏠  Start"), ("cloth", "👕  Ubranie / szata"), ("weapon", "⚔  Broń"),
                           ("gump", "🖼  Obrazek na lalce (gump)"), ("pack", "📦  Spakuj do .vd"),
                           ("tools", "🔎  Podgląd i narzędzia"), ("set", "🧩  Zestaw z arkusza"),
                           ("patch", "🛠  Dodawanie do klienta"), ("settings", "⚙  Ustawienia"), ("help", "❓  Pomoc")]:
            b = ttk.Button(nav, text=label, style="Nav.TButton", width=26, command=lambda k=key: self.show(k))
            b.pack(fill="x", pady=1)
            self.navbtns[key] = b
        bottom = ttk.Frame(r, style="Nav.TFrame")
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.status = ttk.Label(bottom, text="Gotowy.", padding=(12, 6), style="Status.TLabel")
        self.status.grid(row=0, column=0, sticky="w")
        self.log_btn = ttk.Button(bottom, text="Szczegóły ▸", command=self._toggle_log)
        self.log_btn.grid(row=0, column=1, padx=10, pady=4)
        self.log = scrolledtext.ScrolledText(r, height=11, state="disabled", relief="flat", borderwidth=0, padx=8, pady=6)
        REG["tk"].append((self.log, "log"))
        self.log_shown = False
        popup(self.log, [("Kopiuj", lambda: self.log.event_generate("<<Copy>>")),
                         ("Zaznacz wszystko", lambda: self.log.tag_add("sel", "1.0", "end")),
                         ("Wyczyść", self._clear_log), ("Zapisz do pliku…", self._save_log)])

    def _toggle_log(self, force=None):
        show = (not self.log_shown) if force is None else force
        if show and not self.log_shown:
            self.log.grid(row=3, column=0, columnspan=2, sticky="ew")
        elif not show and self.log_shown:
            self.log.grid_remove()
        self.log_shown = show
        self.log_btn.configure(text="Szczegóły ▾" if show else "Szczegóły ▸")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _save_log(self):
        f = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="nelderim_log.txt")
        if f:
            Path(f).write_text(self.log.get("1.0", "end"), encoding="utf-8")

    def say(self, text):
        self.q.put(text)

    def set_status(self, text, color=None):
        self.q.put(("status", text, color))

    def _pump(self):
        try:
            while True:
                t = self.q.get_nowait()
                if isinstance(t, tuple) and t[0] == "status":
                    self.status.configure(text=t[1], style=sty(t[2]))
                elif isinstance(t, tuple) and t[0] == "call":
                    t[1]()
                else:
                    self.log.configure(state="normal")
                    self.log.insert("end", t if t.endswith("\n") else t + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def ui(self, fn):
        """Run fn on the UI thread (from workers)."""
        self.q.put(("call", fn))

    def show(self, key):
        if self.current:
            self.current.grid_remove()
        if key not in self.pages:
            frame = Scroll(self.content)
            frame.grid(row=0, column=0, sticky="nsew")
            getattr(self, "page_" + key)(frame.inner)
            self.pages[key] = (frame,)
        f = self.pages[key][0]
        f.grid()
        self.current = f
        self.current_key = key
        for k, b in self.navbtns.items():
            b.configure(style="NavSel.TButton" if k == key else "Nav.TButton")
        if key == "start":
            self.refresh_start()

    # ------------------------------------------------------------ helpers
    def ready(self, keys=None) -> bool:
        H = self.H
        bad = [k for k in (keys or H.missing(self.cfg)) if not H.path_ok(k, self.cfg.get(k))]
        if bad:
            messagebox.showwarning("Brakuje ustawień", "Najpierw uzupełnij w Ustawieniach:\n\n" +
                                   "\n".join("• " + PL[k] for k in bad))
            self.show("settings")
            return False
        return True

    def hint_for(self, line, shown):
        for pat, msg in HINTS:
            if re.search(pat, line) and msg not in shown:
                shown.add(msg)
                self.say("💡 PODPOWIEDŹ: " + msg)
                self.set_status("Coś poszło nie tak – zobacz podpowiedź w szczegółach.", BADC)
                self.ui(lambda: self._toggle_log(True))

    def stream(self, cmd, capture, shown) -> int:
        if cmd.get("noop"):
            return 0
        self.say("$ " + " ".join(f'"{a}"' if " " in a else a for a in cmd["argv"]))
        try:
            p = subprocess.Popen(cmd["argv"], cwd=cmd["cwd"], env=cmd["env"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            self.say(f"[BŁĄD] {e}")
            capture.append(str(e))
            return 1
        for line in p.stdout:
            line = line.rstrip("\n")
            capture.append(line)
            self.say(line)
            self.hint_for(line, shown)
        return p.wait()

    def run(self, steps, title, on_ok=None, on_fail=None, keys=None):
        """Run steps (callables returning a cmd dict, or None to stop) one after another in a thread."""
        if self.busy:
            messagebox.showinfo("Chwila", "Poprzednie zadanie jeszcze trwa. Poczekaj aż się skończy.")
            return
        if not self.ready(keys):
            return
        self.busy = True
        self.set_status(f"⏳ {title}…", ACC)

        def work():
            out: list[str] = []
            shown: set = set()
            ok = False
            try:
                for s in steps:
                    cmd = s()
                    if cmd is None:
                        break
                    rc = self.stream(cmd, out, shown)
                    if rc not in cmd.get("ok", (0,)):
                        self.say(f"[BŁĄD] polecenie zakończyło się kodem {rc}")
                        break
                else:
                    ok = True
            except Exception as e:  # noqa: BLE001
                self.say(f"[BŁĄD] {e}")
                out.append(str(e))
            finally:
                self.busy = False

            def done():
                if ok:
                    self.set_status(f"✓ {title}: gotowe.", OKC)
                    if on_ok:
                        on_ok(out)
                else:
                    if not self.status.cget("text").startswith("Coś poszło"):
                        self.set_status(f"✗ {title}: nie udało się. Zobacz „Szczegóły”.", BADC)
                    self._toggle_log(True)
                    if on_fail:
                        on_fail(out)
            self.ui(done)

        threading.Thread(target=work, daemon=True).start()

    def row(self, parent, label, var, help, kind=None, width=50, ftypes=None):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=2)
        lb = ttk.Label(f, text=label, width=30, anchor="w")
        lb.pack(side="left")
        hb = ttk.Button(f, text="?", width=2, command=lambda: messagebox.showinfo(label, help))
        hb.pack(side="right")
        pb = ttk.Button(f, text="Wybierz…") if kind else None
        if pb:
            pb.pack(side="right", padx=4)
        e = ttk.Entry(f, textvariable=var, width=width)
        e.pack(side="left", fill="x", expand=True)
        Tip(lb, help)
        Tip(e, help)

        def pick():
            v = (filedialog.askdirectory(title=label) if kind == "dir" else
                 filedialog.asksaveasfilename(title=label) if kind == "save" else
                 filedialog.askopenfilename(title=label, filetypes=ftypes or [("Wszystkie pliki", "*.*")]))
            if v:
                var.set(v)

        def open_folder():
            p = Path(var.get())
            target = p if p.is_dir() else p.parent
            if target.exists():
                self.H.open_path(str(target))

        items = [("Wklej", lambda: e.event_generate("<<Paste>>")), ("Kopiuj", lambda: e.event_generate("<<Copy>>")),
                 ("Wytnij", lambda: e.event_generate("<<Cut>>")), ("Wyczyść", lambda: var.set(""))]
        if kind:
            items += [None, ("Wybierz…", pick), ("Otwórz folder", open_folder)]
            pb.configure(command=pick)
        popup(e, items)
        return e

    def button(self, parent, text, cmd, help=None, big=False):
        b = ttk.Button(parent, text=text, command=cmd, style="Big.TButton" if big else "TButton")
        b.pack(side="left", padx=(0, 8), pady=2)
        if help:
            Tip(b, help)
        return b

    def advanced(self, parent, title="Ustawienia zaawansowane (nie musisz ich ruszać)"):
        holder = ttk.Frame(parent)
        holder.pack(fill="x", pady=(6, 0))
        inner = ttk.Frame(holder)
        state = {"open": False}
        btn = ttk.Button(holder, text="▸ " + title)

        def toggle():
            state["open"] = not state["open"]
            if state["open"]:
                inner.pack(fill="x", pady=4)
                btn.configure(text="▾ " + title)
            else:
                inner.pack_forget()
                btn.configure(text="▸ " + title)

        btn.configure(command=toggle)
        btn.pack(anchor="w")
        return inner

    def head(self, parent, title, text):
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w", padx=12, pady=(12, 2))
        ttk.Label(parent, text=text, wraplength=700, justify="left", style=sty(MUTED)).pack(anchor="w", padx=12,
                                                                                            pady=(0, 6))

    def lab_dir(self, name) -> Path:
        return self.H.workroot(self.cfg) / self.H.slugify(name) / "lab"

    def open_folder(self, p):
        p = Path(p)
        if p.exists():
            self.H.open_path(str(p if p.is_dir() else p.parent))
        else:
            messagebox.showinfo("Folder", f"Nie ma jeszcze: {p}")

    # ---- shared step logic
    def lookup_step(self, step, graphic_var, on_anim=None):
        H = self.H

        def go():
            g = graphic_var.get().strip()
            if not g:
                messagebox.showinfo("Numer przedmiotu", "Wpisz ItemID, np. 0x2684.")
                return
            step.info("Sprawdzam…")

            def ok(lines):
                txt = "\n".join(lines)
                m = re.search(r"item (0x[0-9a-fA-F]+) '(.*?)' animId (\d+) layer (\d+)", txt)
                t = re.search(r"animation used for body 400: (\d+)", txt)
                b = re.search(r"Bodyconv: (.*)", txt)
                if not (m and t):
                    step.bad("Nie znalazłem tego przedmiotu. Sprawdź numer ItemID.")
                    return
                anim = int(t.group(1))
                inmul = bool(b and b.group(1).startswith("none"))
                msg = f"To „{m.group(2)}”. Animacja numer {anim}. "
                if anim < 400:
                    step.bad(msg + "Ten przedmiot nie ma animacji ubrania (ID < 400), więc się nie nadaje.")
                    return
                msg += ("Da się przerobić ✓" if inmul else
                        "Da się zbudować podgląd, ale oryginalny plik .vd tej animacji wyciągnij z UOFiddlera "
                        "(Animation Edit → Export to VD) – leży w innym pliku niż anim.mul.")
                step.ok(msg)
                if on_anim:
                    on_anim(anim)

            self.run([lambda: H.cmd_item_lookup(self.cfg, g)], "Sprawdzanie przedmiotu", on_ok=ok,
                     on_fail=lambda o: step.bad("Nie udało się sprawdzić (zobacz Szczegóły)."),
                     keys=["toolkit", "client"])

        return go

    def image_check(self, step, image_var, weapon=False):
        H = self.H

        def go():
            img = image_var.get().strip()
            if not img or not Path(img).is_file():
                messagebox.showinfo("Obrazek", "Najpierw wskaż plik PNG.")
                return

            def ok(lines):
                txt = "\n".join(lines)
                size = re.search(r"SIZE (\d+) (\d+)", txt)
                al = re.search(r"ALPHA (\d+) (\d+)", txt)
                bb = re.search(r"BBOX \((\d+), (\d+), (\d+), (\d+)\)", txt)
                if not (size and al):
                    step.bad("Nie mogę odczytać obrazka. To na pewno PNG?")
                    return
                if not bb:
                    step.bad("Obrazek jest w całości przezroczysty (pusty).")
                    return
                w, h = int(bb.group(3)) - int(bb.group(1)), int(bb.group(4)) - int(bb.group(2))
                probs = []
                if int(al.group(1)) == 255:
                    probs.append("Obrazek NIE ma przezroczystego tła – wytnij tło (np. w GIMP/Photoshop), inaczej wyjdzie kwadrat.")
                if min(w, h) < 12:
                    probs.append("Obrazek jest bardzo mały/cienki – zobacz podgląd, czy nie wyszedł zbyt drobny.")
                if weapon and h > w:
                    probs.append("Broń jest ustawiona pionowo. Zadziała (obrócę ją), ale najlepiej: poziomo, rękojeść po LEWEJ.")
                msg = f"Rozmiar {size.group(1)}×{size.group(2)}, sam rysunek {w}×{h} px."
                if probs:
                    (step.bad if int(al.group(1)) == 255 else step.info)(msg + "\n" + "\n".join("⚠ " + p for p in probs))
                else:
                    step.ok(msg + " Wygląda dobrze.")

            self.run([lambda: H.cmd_image_check(self.cfg, img)], "Sprawdzanie obrazka", on_ok=ok,
                     on_fail=lambda o: step.bad("Nie udało się sprawdzić obrazka (zobacz Szczegóły)."),
                     keys=["toolkit"])

        return go

    def preview(self, lab):
        H = self.H
        if not self.ready(["toolkit", "client"]):
            return
        if not lab or not (Path(lab) / "index.html").is_file():
            messagebox.showinfo("Podgląd", "Najpierw zbuduj przymiarkę (nie ma jeszcze podglądu).")
            return
        self.stop_preview()
        c = H.cmd_serve(self.cfg, lab)
        self.server = subprocess.Popen(c["argv"], cwd=c["cwd"], env=c["env"], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        self.set_status(f"Podgląd działa: http://127.0.0.1:{H.PORT}", OKC)
        self.root.after(700, lambda: webbrowser.open(f"http://127.0.0.1:{H.PORT}"))

    def stop_preview(self):
        if self.server and self.server.poll() is None:
            self.server.terminate()
        self.server = None

    def pack(self, step, lab, outline, body="", out="", item=None):
        """Extract original + body, back up, pack. Works for any lab with at least one item."""
        H = self.H
        try:
            key, aid = item or H.lab_items(str(lab))[0]
        except (OSError, ValueError, KeyError, IndexError) as e:
            step.bad(f"Nie mogę odczytać zbudowanej pracy (brak lub uszkodzony manifest.json): {e}")
            return
        target = H.equip_target(self.cfg, aid)
        orig = H.vd_original(self.cfg, target)
        bodyp = Path(body) if body.strip() else H.vd_original(self.cfg, 400)
        outp = out.strip() or str(H.workdir(self.cfg) / f"nowy_{target:04d}.vd")

        def check():
            cap: list[str] = []
            rc = self.stream(H.cmd_conv_check(self.cfg, target), cap, set())
            if rc != 0 or "INMUL" not in "".join(cap):
                if not orig.exists():
                    self.say(f"[!] Animacja {target} leży w innym pliku niż anim.mul.")
                    self.ui(lambda: step.bad(
                        f"Oryginał animacji {target} trzeba wyciągnąć UOFiddlerem (Animation Edit → wpisz ID {target} → "
                        f"Export to VD) i zapisać jako:\n{orig}\nPotem kliknij ponownie."))
                    return None
            return H.noop()

        def backup():
            b = H.backup_file(Path(outp))
            if b:
                self.say(f"Kopia poprzedniego wyniku: {b}")
            return H.noop()

        steps = [check,
                 lambda: H.noop() if orig.exists() else H.cmd_mul2vd(self.cfg, target),
                 lambda: H.noop() if bodyp.exists() else H.cmd_mul2vd(self.cfg, 400),
                 backup,
                 lambda: H.cmd_atlas_to_vd(self.cfg, str(lab), key, str(orig), outp, str(bodyp), outline),
                 lambda: H.cmd_vd_info(self.cfg, outp)]

        def ok(_o):
            step.ok(f"Gotowe! Plik do UOFiddlera:\n{outp}\n"
                    f"Import: UOFiddler → Animations → Animation Edit → ID {target} → Import from VD → Save "
                    f"(na KOPII klienta).")
            self.say(H.CHECKLIST)

        self.run(steps, "Pakowanie do .vd", on_ok=ok, keys=["toolkit", "client"],
                 on_fail=lambda o: None if "Oryginał animacji" in step.result.cget("text")
                 else step.bad("Nie udało się. Zobacz Szczegóły."))

    # ------------------------------------------------------------ pages
    def page_start(self, p):
        self.head(p, "Co chcesz zrobić?", "Wybierz zadanie. Każde prowadzi krok po kroku i tłumaczy, co robić. "
                                          "Na dole widzisz, czy program jest gotowy do pracy.")
        self.pre = ttk.LabelFrame(p, text="  Czy wszystko jest gotowe?  ", padding=10)
        self.pre.pack(fill="x", padx=10, pady=6)
        grid = ttk.Frame(p)
        grid.pack(fill="x", padx=10, pady=6)
        cards = [("👕  Zmienić wygląd ubrania lub szaty",
                  "Masz obrazek szaty, koszuli, spodni, butów… Program dopasuje go do animacji chodzenia, walki itd.", "cloth"),
                 ("⚔  Zmienić wygląd broni",
                  "Miecz, laska, włócznia. Wystarczy obrazek broni ułożony poziomo.", "weapon"),
                 ("🖼  Zrobić obrazek broni na lalce postaci",
                  "Ten, który widać w oknie Paperdoll (gump). Męski i damski.", "gump"),
                 ("📦  Spakować gotową pracę do pliku .vd",
                  "Plik, który wczytujesz do UOFiddlera. Zwykle robi się to na końcu kreatora.", "pack"),
                 ("🔎  Podejrzeć animację lub sprawdzić przedmiot",
                  "Podgląd .vd, podgląd pracy w przeglądarce, wyszukiwanie ItemID, UOFiddler.", "tools"),
                 ("⚙  Ustawić foldery (pierwszy raz)", "Gdzie leży klient gry, toolkit i inne programy.", "settings")]
        for i, (t, d, k) in enumerate(cards):
            grid.columnconfigure(i % 2, weight=1, uniform="c")
            card = ttk.Frame(grid, style="Card.TFrame", padding=14)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            ttk.Label(card, text=t, style="CardTitle.TLabel", wraplength=330, justify="left").pack(anchor="w")
            ttk.Label(card, text=d, wraplength=330, style=sty(MUTED), justify="left").pack(anchor="w", pady=(4, 0))

            def hot(_e, c=card, on=True):
                c.configure(style="CardHot.TFrame" if on else "Card.TFrame")

            for w in [card, *card.winfo_children()]:
                w.bind("<Enter>", hot, add="+")
                w.bind("<Leave>", lambda e, c=card: hot(e, c, False), add="+")
                w.bind("<Button-1>", lambda e, k=k: self.show(k), add="+")
                w.configure(cursor="hand2")

    def refresh_start(self):
        H = self.H
        for w in self.pre.winfo_children():
            w.destroy()
        allok = True
        for k, (label, _, _, req) in H.PATHS.items():
            if not req:
                continue
            ok = H.path_ok(k, self.cfg.get(k))
            allok &= ok
            r = ttk.Frame(self.pre)
            r.pack(fill="x")
            ttk.Label(r, text=("✓ " if ok else "✗ ") + PL[k], style=sty(OKC if ok else BADC),
                      width=48).pack(side="left")
            if not ok:
                ttk.Button(r, text="Ustaw", command=lambda: self.show("settings")).pack(side="left")
        if H.path_ok("toolkit", self.cfg.get("toolkit")) and not H.toolkit_has_axisfit(self.cfg):
            ttk.Label(self.pre, text="⚠ Toolkit ma starą wersję skryptów (bez obsługi broni). Skopiuj paczkę Levy'ego v2.",
                      style=sty(BADC), wraplength=700).pack(anchor="w")
        if allok:
            ttk.Label(self.pre, text="Wszystko gotowe. Wybierz zadanie poniżej. 👇", style=sty(OKC)).pack(anchor="w")

    def page_settings(self, p):
        H = self.H
        self.head(p, "Ustawienia – gdzie co leży", "Wskaż foldery raz, program je zapamięta (na tym komputerze). "
                                                     "Zielone „OK” = folder jest poprawny. Prawy przycisk myszy w polu: wklej / wybierz.")
        self.pv = {k: tk.StringVar(value=self.cfg.get(k, "")) for k in H.PATHS}
        self.pst = {}
        help_txt = {
            "client": "Folder z grą (KOPIA klienta!), gdzie leżą pliki anim.idx, anim.mul, tiledata.mul, Equipconv.def.",
            "toolkit": "Folder SpriteMotion-UO-Toolkit (tam gdzie pyproject.toml), z wgraną paczką Levy'ego.",
            "pipeline": "Folder tego programu (tam gdzie nelderim_patch.py). Zwykle wykryje się sam.",
            "output": "Gdzie zapisywać wyniki dodawania do klienta (pusty folder, np. OUTPUT).",
            "vdviewer": "Plik vd-viewer.html – przeglądarka plików .vd (opcjonalnie).",
            "fiddler": "Folder programu UOFiddler (opcjonalnie, do szybkiego uruchamiania).",
            "serv": "Folder serwera ServUO z skryptami C# (opcjonalnie).",
            "vdtool": "Osobny folder vdtool (opcjonalnie; inaczej używam narzędzi z toolkitu)."}
        box = ttk.Frame(p, padding=10)
        box.pack(fill="x")
        for k, (label, kind, _, req) in H.PATHS.items():
            e = self.row(box, PL[k] + ("" if req else " (opcjonalnie)"), self.pv[k], help_txt[k], kind=kind,
                         width=46, ftypes=[("HTML", "*.html")] if kind == "file" else None)
            self.pst[k] = ttk.Label(e.master, text="", width=6)
            self.pst[k].pack(side="right", padx=4)
        b = ttk.Frame(p, padding=10)
        b.pack(fill="x")
        self.button(b, "💾 Zapisz", self._save_paths, "Zapisuje ustawienia.", big=True)
        self.button(b, "🔍 Wykryj automatycznie", self._autodetect,
                    "Szuka folderów obok tego programu i w katalogu domowym.")
        self.button(b, "Pokaż, gdzie zapisano ustawienia",
                    lambda: messagebox.showinfo("Plik ustawień", str(H.CONFIG_FILE)))
        self.st_note = ttk.Label(p, text="", style=sty(MUTED), wraplength=700)
        self.st_note.pack(anchor="w", padx=12)
        self._paths_status()
        for v in self.pv.values():
            v.trace_add("write", lambda *a: self._paths_status())

    def _paths_status(self):
        H = self.H
        for k, lab in self.pst.items():
            ok = H.path_ok(k, self.pv[k].get().strip())
            req = H.PATHS[k][3]
            lab.configure(text="OK" if ok else ("brak" if req else "-"),
                          style=sty(OKC if ok else (BADC if req else MUTED)))

    def _autodetect(self):
        H = self.H
        found = 0
        for k in H.PATHS:
            if H.PATHS[k][1] != "dir" or H.path_ok(k, self.pv[k].get().strip()):
                continue
            for g in H.guesses(k):
                if H.path_ok(k, g):
                    self.pv[k].set(g)
                    found += 1
                    break
        self.st_note.configure(text=f"Wykryto automatycznie: {found}. Resztę wskaż ręcznie (przycisk „Wybierz…”).")

    def _save_paths(self):
        H = self.H
        for k in H.PATHS:
            v = self.pv[k].get().strip()
            if v:
                self.cfg[k] = v
            else:
                self.cfg.pop(k, None)
        if self.cfg.get("output"):
            try:
                Path(self.cfg["output"]).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Folder wyjściowy", str(e))
        H.save_config(self.cfg)
        miss = H.missing(self.cfg)
        self.st_note.configure(text="Zapisano." if not miss else "Zapisano. Jeszcze brakuje: " +
                               ", ".join(PL[k] for k in miss))
        self.set_status("Ustawienia zapisane.", OKC)

    # ---- clothes
    def page_cloth(self, p):
        H = self.H
        self.head(p, "👕 Ubranie / szata", "Zmieniasz WYGLĄD (materiał, kolor, wzór) istniejącego ubrania. Kształt i fałdy "
                                           "zostają z oryginalnej animacji. Idź po kolei od kroku 1.")
        v = {k: tk.StringVar() for k in ("graphic", "image", "name", "hide", "actions", "title")}
        v["hide"].set("1 5")
        v["actions"].set("0 4 9 13 16")
        s1 = Step(p, 1, "Które ubranie zmieniasz?", "Wpisz numer przedmiotu (ItemID) z UOFiddlera (zakładka Items), np. 0x2684 "
                                                      "to Hooded Shroud. Program sprawdzi, czy da się je przerobić.")
        self.row(s1.body, "Numer przedmiotu (ItemID)", v["graphic"], "np. 0x2684. Skopiuj z UOFiddlera (Items → ID).")
        self.button(s1.body, "Sprawdź przedmiot", self.lookup_step(s1, v["graphic"]),
                    "Odczytuje nazwę i animację przedmiotu z klienta.")
        s2 = Step(p, 2, "Wskaż swój obrazek", "PNG z PRZEZROCZYSTYM tłem. Ubranie widziane z przodu, równe światło, bez "
                                              "mocnych cieni (fałdy weźmiemy z oryginału).")
        self.row(s2.body, "Obrazek (PNG)", v["image"], "Plik .png z wyciętym tłem.", kind="file",
                 ftypes=[("Obrazy", "*.png *.webp"), ("Wszystkie", "*.*")])
        self.button(s2.body, "Sprawdź obrazek", self.image_check(s2, v["image"]), "Czy ma przezroczyste tło i sensowny rozmiar.")
        s3 = Step(p, 3, "Nazwij swoją pracę", "Dowolna nazwa, np. moja-szata. Na jej podstawie sam utworzę folder na wyniki.")
        self.row(s3.body, "Nazwa pracy", v["name"], "Litery, cyfry, myślnik. Np. szata-wilka.")
        adv = self.advanced(s3.body)
        self.row(adv, "Odsłoń części ciała (numery)", v["hide"],
                 "1 = twarz, 5 = dłonie. Wpisz „1 5”, żeby kaptur nie zakrywał głowy i były widać ręce. Puste = nic nie odsłaniaj.")
        self.row(adv, "Które akcje zbudować", v["actions"],
                 "Numery ruchów: 0 chodzenie, 4 stanie, 9 cięcie, 13 cięcie 2h, 16 czar. Puste = wszystkie 35 (dłużej).")
        self.row(adv, "Tytuł w podglądzie", v["title"], "Tylko napis na stronie podglądu (nieobowiązkowe).")
        s4 = Step(p, 4, "Zbuduj przymiarkę", "Dopasowanie obrazka do klatek animacji. Na próbę robimy kilka akcji – to trwa chwilę.")
        s5 = Step(p, 5, "Obejrzyj w przeglądarce", "Porównaj „UO” (oryginał) i „New” (Twój). Sprawdź chodzenie, cięcie i różne kierunki.")
        s6 = Step(p, 6, "Zapisz do pliku .vd", "Pakuje wynik do pliku, który wczytujesz w UOFiddlerze. "
                                              "Poprzednia wersja pliku zostanie zachowana jako kopia.")

        def lab():
            return self.lab_dir(v["name"].get())

        def check_inputs():
            if not all(v[k].get().strip() for k in ("graphic", "image", "name")):
                messagebox.showinfo("Brakuje danych", "Uzupełnij kroki 1–3 (ItemID, obrazek, nazwa pracy).")
                return False
            return True

        def build(actions):
            if not check_inputs():
                return
            out = lab()
            key = H.slugify(v["name"].get())

            def ok(_o):
                self.last_lab = str(out)
                s4.ok(f"Zbudowane. Folder: {out}\nTeraz krok 5 (podgląd).")

            self.run([lambda: H.cmd_build_item(self.cfg, v["graphic"].get(), v["image"].get(), str(out), key,
                                               v["title"].get(), v["hide"].get(), actions)],
                     "Budowanie przymiarki", on_ok=ok, on_fail=lambda o: s4.bad("Nie udało się (zobacz podpowiedź)."),
                     keys=["toolkit", "client"])

        self.button(s4.body, "▶ Zbuduj (kilka akcji na próbę)", lambda: build(v["actions"].get()),
                    "Szybka próba na wybranych akcjach.", big=True)
        self.button(s4.body, "Zbuduj wszystkie 35 akcji", lambda: build(""), "Pełna wersja – trwa dłużej.")
        self.button(s5.body, "🌐 Otwórz podgląd", lambda: self.preview(str(lab()) if v["name"].get().strip() else ""),
                    "Uruchamia lokalną stronę i otwiera przeglądarkę.", big=True)
        self.button(s5.body, "Zatrzymaj podgląd", self.stop_preview)
        self.button(s5.body, "Otwórz folder pracy", lambda: self.open_folder(lab().parent))
        self.button(s6.body, "📦 Spakuj do .vd", lambda: check_inputs() and self.pack(s6, lab(), ""),
                    "Wyciąga oryginał, przycina i zapisuje plik .vd.", big=True)
        self.button(s6.body, "Otwórz folder z plikami .vd", lambda: self.open_folder(H.workdir(self.cfg)))

    # ---- weapon
    def page_weapon(self, p):
        H = self.H
        self.head(p, "⚔ Broń (miecz, laska, włócznia)", "Dla wąskiej, prostej broni trzymanej w ręku. Program dopasowuje "
                                                         "Twój obrazek do osi oryginalnej broni i chwytu dłoni.")
        v = {k: tk.StringVar() for k in ("kind", "graphic", "image", "name", "thick", "hide", "actions")}
        v["kind"].set("Miecz / szabla")
        v["hide"].set("5")
        v["actions"].set("0 4 9 13")
        cont, torso, outl = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        s1 = Step(p, 1, "Jaka to broń?", "Wybierz rodzaj i wpisz ItemID przedmiotu, który zastępujesz (np. 0xF5E szabla, "
                                         "0xDF0 BlackStaff).")
        f = ttk.Frame(s1.body)
        f.pack(fill="x", pady=2)
        ttk.Label(f, text="Rodzaj broni", width=30).pack(side="left")
        cb = ttk.Combobox(f, textvariable=v["kind"], state="readonly", width=28,
                          values=["Miecz / szabla", "Laska / kij / włócznia"])
        cb.pack(side="left")
        Tip(cb, "Miecz: trzymany za rękojeść na dole. Laska: trzymana pośrodku, ma kulę na jednym końcu.")
        self.row(s1.body, "Numer przedmiotu (ItemID)", v["graphic"], "np. 0xF5E (szabla) albo 0xDF0 (BlackStaff).")
        self.button(s1.body, "Sprawdź przedmiot", self.lookup_step(s1, v["graphic"]))
        s2 = Step(p, 2, "Wskaż obrazek broni", "PNG z przezroczystym tłem, broń POZIOMO: rękojeść (dół) po LEWEJ, czubek po PRAWEJ. "
                                               "Pamiętaj: w UO nie ma półprzezroczystości ani gładkich krawędzi.")
        self.row(s2.body, "Obrazek broni (PNG)", v["image"], "Poziomy obrazek broni z przezroczystym tłem.", kind="file",
                 ftypes=[("Obrazy", "*.png *.webp"), ("Wszystkie", "*.*")])
        self.button(s2.body, "Sprawdź obrazek", self.image_check(s2, v["image"], weapon=True))
        s3 = Step(p, 3, "Nazwa i grubość", "Nazwa pracy tworzy folder. Grubość: zacznij od pustej i popraw po obejrzeniu podglądu.")
        self.row(s3.body, "Nazwa pracy", v["name"], "Np. moja-szabla.")
        adv = self.advanced(s3.body)
        self.row(adv, "Grubość broni w pikselach", v["thick"],
                 "Stała grubość na ekranie. Oryginalna laska ma ok. 3 px. Za gruba? Zmniejsz. Za cienka? Zwiększ. "
                 "Pole puste = ustawienie domyślne.")
        self.row(adv, "Odsłoń części ciała", v["hide"], "5 = dłonie (żeby broń była w dłoni, a nie na niej). 1 = twarz.")
        self.row(adv, "Które akcje zbudować", v["actions"], "Numery ruchów oddzielone spacją: 0 chodzenie, 4 stanie, 9 cięcie, 13 cięcie 2h.\nJeśli zostawisz to pole PUSTE, program wygeneruje WSZYSTKIE 35 akcji (trwa dłużej).")
        for var, txt, h in ((cont, "Trzymaj ten sam koniec przez całą animację",
                             "Zapobiega „skakaniu” kuli/rękojeści z jednego końca na drugi."),
                            (torso, "Koniec roboczy = ten dalej od tułowia", "Pomaga wybrać, który koniec broni to czubek.")):
            c = ttk.Checkbutton(adv, text=txt, variable=var)
            c.pack(anchor="w")
            Tip(c, h)
        s4 = Step(p, 4, "Zbuduj przymiarkę", "Najpierw kilka akcji (szybko). Potem oglądasz podgląd i poprawiasz grubość.")
        s5 = Step(p, 5, "Obejrzyj w przeglądarce", "Sprawdź, czy kula lub rękojeść jest po dobrej stronie i czy broń nie „wchodzi” na postać. "
                                                   "Zwłaszcza w akcjach ataku i śmierci.")
        s6 = Step(p, 6, "Zapisz do pliku .vd", "Pakuje do pliku dla UOFiddlera i przycina broń do ciała.")
        o = ttk.Checkbutton(s6.body, text="Dodaj ciemny kontur 1 px (dla cienkiej klingi)", variable=outl)
        o.pack(anchor="w")
        Tip(o, "Pogrubia cienką klingę w stylu UO. Wyłącz, jeśli Twój obrazek ma już ciemny kontur (np. drewniana laska).")

        def lab():
            return self.lab_dir(v["name"].get())

        def ok_inputs():
            if not all(v[k].get().strip() for k in ("graphic", "image", "name")):
                messagebox.showinfo("Brakuje danych", "Uzupełnij kroki 1–3 (ItemID, obrazek, nazwa pracy).")
                return False
            if not H.path_ok("toolkit", self.cfg.get("toolkit")):
                self.ready(["toolkit"])
                return False
            if not H.toolkit_has_axisfit(self.cfg):
                messagebox.showwarning("Stara wersja toolkitu", "W toolkicie brakuje obsługi broni. Skopiuj paczkę "
                                       "Levy'ego v2 (SpriteMotion_skrypty_Nelderim_1.zip) z nadpisaniem.")
                return False
            return True

        def build(actions):
            if not ok_inputs():
                return
            key = "sword" if v["kind"].get().startswith("Miecz") else "staff"
            out = lab()
            work = out.parent / "work"
            conf, dz, sw = work / "config.json", work / "placeholder_design.png", work / "placeholder_sword.png"
            try:
                H.write_json(conf, H.weapon_config(key, v["graphic"].get().strip(), v["image"].get().strip(),
                                                   v["thick"].get().strip(), v["hide"].get(), cont.get(), torso.get(),
                                                   v["name"].get()))
                H.placeholder_png(dz)
                H.placeholder_png(sw)
            except (OSError, ValueError) as e:
                s4.bad(f"Nie mogę zapisać ustawień: {e}. Grubość musi być liczbą całkowitą.")
                return
            if key == "sword":                # the 'sword' key takes its picture from --lightsaber
                sw = Path(v["image"].get().strip())

            def ok(_o):
                self.last_lab = str(out)
                s4.ok(f"Zbudowane. Folder: {out}\nTeraz krok 5 (podgląd). W szczegółach jest raport kontrolny "
                      f"(szukaj: \"errors\": []).")

            self.run([lambda: H.cmd_build_set(self.cfg, str(out), str(dz), str(sw), str(conf), actions),
                      lambda: H.cmd_verify(self.cfg, str(out))],
                     "Budowanie broni", on_ok=ok, on_fail=lambda o: s4.bad("Nie udało się (zobacz podpowiedź)."),
                     keys=["toolkit", "client"])

        self.button(s4.body, "▶ Zbuduj (kilka akcji na próbę)", lambda: build(v["actions"].get()), big=True)
        self.button(s4.body, "Zbuduj wszystkie 35 akcji", lambda: build(""), "Pełna wersja – trwa dłużej.")
        self.button(s5.body, "🌐 Otwórz podgląd", lambda: self.preview(str(lab()) if v["name"].get().strip() else ""),
                    big=True)
        self.button(s5.body, "Zatrzymaj podgląd", self.stop_preview)
        self.button(s6.body, "📦 Spakuj do .vd", lambda: v["name"].get().strip() and self.pack(
            s6, lab(), "1" if outl.get() else ""), "Wyciąga oryginał, przycina i zapisuje plik .vd.", big=True)
        self.button(s6.body, "Otwórz folder z plikami .vd", lambda: self.open_folder(H.workdir(self.cfg)))

    # ---- gump
    def page_gump(self, p):
        H = self.H
        self.head(p, "🖼 Obrazek broni na lalce (gump)", "To obrazek w oknie Paperdoll. Męski numer = animacja + 50000, "
                                                           "damski = męski + 10000. Program dopasuje broń do oryginału.")
        v = {k: tk.StringVar() for k in ("graphic", "anim", "image", "name", "preset", "thick", "ratio", "shift",
                                         "front", "gid")}
        v["preset"].set("Szabla / miecz")
        s1 = Step(p, 1, "Która to broń?", "Wpisz ItemID i kliknij „Sprawdź” – numer animacji uzupełni się sam.")
        self.row(s1.body, "Numer przedmiotu (ItemID)", v["graphic"], "np. 0xDF0 (BlackStaff) albo 0xF5E (szabla).")
        self.row(s1.body, "Numer animacji", v["anim"], "Uzupełnia się po „Sprawdź”. np. 617 laska, 618 szabla.")
        self.button(s1.body, "Sprawdź przedmiot", self.lookup_step(s1, v["graphic"], lambda a: v["anim"].set(str(a))))
        s2 = Step(p, 2, "Wskaż obrazek broni", "PNG z przezroczystym tłem, broń POZIOMO: rękojeść po LEWEJ, czubek po PRAWEJ.")
        self.row(s2.body, "Obrazek broni (PNG)", v["image"], "Poziomy obrazek z przezroczystym tłem.", kind="file",
                 ftypes=[("Obrazy", "*.png *.webp"), ("Wszystkie", "*.*")])
        self.button(s2.body, "Sprawdź obrazek", self.image_check(s2, v["image"], weapon=True))
        s3 = Step(p, 3, "Rodzaj broni i nazwa", "Ustawienia dobiorę pod rodzaj broni. Nazwa pracy tworzy folder na wyniki.")
        f = ttk.Frame(s3.body)
        f.pack(fill="x", pady=2)
        ttk.Label(f, text="Rodzaj broni", width=30).pack(side="left")
        cb = ttk.Combobox(f, textvariable=v["preset"], state="readonly", width=28,
                          values=["Szabla / miecz", "Laska / kij", "Własne ustawienia"])
        cb.pack(side="left")
        Tip(cb, "Gotowe ustawienia sprawdzone przez Levy'ego: laska (grubość 26 px) i szabla (proporcja 0.15, przesunięcie 3,-9, "
                "palce przed rękojeścią).")
        self.row(s3.body, "Nazwa pracy", v["name"], "Np. moja-szabla. Wyniki trafią do folderu o tej nazwie.")
        adv = self.advanced(s3.body)
        v["ratio"].set("0.15")
        v["shift"].set("0,0")
        outl = tk.BooleanVar(value=False)
        self.row(adv, "Grubość w px (laska ≈ 26)", v["thick"], "Puste = użyj proporcji poniżej.")
        self.row(adv, "Proporcja grubości do długości", v["ratio"], "Szabla 0.15.")
        self.row(adv, "Przesunięcie po dopasowaniu", v["shift"], "dx,dy w pikselach, np. 3,-9 dla szabli.")
        self.row(adv, "Wiersz, od którego dłoń jest przed bronią", v["front"], "Szabla: 106. Puste = bez.")
        self.row(adv, "Własny numer gumpu męskiego", v["gid"], "Puste = animacja + 50000.")
        ttk.Checkbutton(adv, text="Ciemny kontur 1 px", variable=outl).pack(anchor="w")
        s4 = Step(p, 4, "Zrób gump", "Powstaną pliki PNG (męski i damski) oraz obrazek porównawczy: oryginał | męski | damski.")
        outdir = lambda: H.workroot(self.cfg) / H.slugify(v["name"].get()) / "gump"  # noqa: E731

        def make():
            if not all(v[k].get().strip() for k in ("anim", "image", "name")):
                messagebox.showinfo("Brakuje danych", "Uzupełnij numer animacji (krok 1), obrazek (2) i nazwę (3).")
                return
            if not H.path_ok("toolkit", self.cfg.get("toolkit")):
                self.ready(["toolkit"])
                return
            if not H.toolkit_has_gump(self.cfg):
                messagebox.showwarning("Stara wersja toolkitu", "Brakuje make_gump.py. Skopiuj paczkę Levy'ego v2 "
                                       "(SpriteMotion_skrypty_Nelderim_1.zip) z nadpisaniem.")
                return
            pr = v["preset"].get()
            th, ra, sh, fb, ol = v["thick"].get(), v["ratio"].get(), v["shift"].get(), v["front"].get(), outl.get()
            if pr.startswith("Laska"):
                th, ra, sh, fb, ol = "26", "", "0,0", "", False
            elif pr.startswith("Szabla"):
                th, ra, sh, fb, ol = "", "0.15", "3,-9", "106", True
            out = outdir()

            def ok(_o):
                s4.ok(f"Gotowe. Pliki: {out}\nObejrzyj „porownanie.png”. Damskiego gumpu często nie ma w kliencie – "
                      f"wtedy w UOFiddlerze użyj Insert, nie Replace.")

            self.run([lambda: H.cmd_make_gump(self.cfg, v["anim"].get().strip(), v["image"].get().strip(), str(out), th,
                                              ra, "bottom", sh, fb, ol, v["gid"].get().strip())],
                     "Tworzenie gumpu", on_ok=ok, on_fail=lambda o: s4.bad("Nie udało się (zobacz podpowiedź)."),
                     keys=["toolkit", "client"])

        self.button(s4.body, "▶ Zrób gump", make, big=True)
        self.button(s4.body, "🖼 Otwórz obrazek porównawczy",
                    lambda: (outdir() / "porownanie.png").is_file() and H.open_path(str(outdir() / "porownanie.png"))
                    or messagebox.showinfo("Porównanie", "Nie ma jeszcze obrazka – najpierw kliknij „Zrób gump”."))
        self.button(s4.body, "Otwórz folder", lambda: self.open_folder(outdir()))
        ttk.Label(s4.body, text="").pack()
        ttk.Label(p, text="Import: UOFiddler → Gumps → Replace (lub Insert, jeśli gumpu nie ma).", style=sty(MUTED)
                  ).pack(anchor="w", padx=14, pady=4)

    # ---- pack (any lab)
    def page_pack(self, p):
        H = self.H
        self.head(p, "📦 Spakuj do .vd", "Dla prac zbudowanych wcześniej (albo zestawów z arkusza). W kreatorach ubrania i "
                                          "broni ten krok jest już na końcu, tu robisz to ręcznie.")
        v = {k: tk.StringVar() for k in ("lab", "item", "body", "outline", "out")}
        v["outline"].set("1")
        s1 = Step(p, 1, "Wskaż zbudowaną pracę", "Folder „lab” (ten, w którym jest manifest.json i podgląd).")
        self.row(s1.body, "Folder pracy (lab)", v["lab"], "Folder utworzony przez kreator lub „Zestaw z arkusza”.", kind="dir")
        cache = {}
        f = ttk.Frame(s1.body)
        f.pack(fill="x", pady=2)
        ttk.Label(f, text="Przedmiot", width=30).pack(side="left")
        combo = ttk.Combobox(f, textvariable=v["item"], state="readonly", width=48)
        combo.pack(side="left")

        def load():
            try:
                its = H.lab_items(v["lab"].get())
            except (OSError, ValueError, KeyError) as e:
                s1.bad(f"Nie mogę odczytać manifest.json: {e}")
                return
            cache.clear()
            for k, a in its:
                gm, gf = H.gump_ids(H.equip_target(self.cfg, a))
                cache[f"{k}  (animacja {a}, gump M {gm} / K {gf})"] = (k, a)
            combo["values"] = list(cache)
            if cache:
                combo.current(0)
            s1.ok(f"Znalazłem przedmiotów: {len(cache)}.")

        self.button(s1.body, "Wczytaj listę przedmiotów", load)
        s2 = Step(p, 2, "Opcje", "Kontur pogrubia cienkie przedmioty (miecz). Ciało służy do przycięcia broni do postaci – "
                                 "jeśli nie masz własnego, wyciągnę je z klienta.")
        self.row(s2.body, "Kontur (px)", v["outline"], "1 = dodaj ciemny kontur, 0 lub puste = bez.")
        adv = self.advanced(s2.body)
        self.row(adv, "Własny plik ciała (.vd)", v["body"], "Puste = wyciągnę animację 400 z klienta.", kind="file")
        self.row(adv, "Plik wynikowy (.vd)", v["out"], "Puste = folder roboczy toolkitu.", kind="save")
        s3 = Step(p, 3, "Spakuj", "Wyciąga oryginał, robi kopię poprzedniego wyniku i zapisuje nowy .vd.")

        def go():
            sel = cache.get(v["item"].get())
            if not sel:
                messagebox.showinfo("Pakowanie", "Wskaż folder pracy i kliknij „Wczytaj listę przedmiotów”.")
                return
            self.pack(s3, v["lab"].get(), v["outline"].get().strip(), v["body"].get(), v["out"].get(), item=sel)

        def roundtrip():
            sel = cache.get(v["item"].get())
            if not sel:
                messagebox.showinfo("Test", "Najpierw wczytaj listę przedmiotów.")
                return
            key, aid = sel
            target = H.equip_target(self.cfg, aid)
            orig = H.vd_original(self.cfg, target)
            tmp = H.workdir(self.cfg) / f"test_{target:04d}.vd"
            self.run([lambda: H.noop() if orig.exists() else H.cmd_mul2vd(self.cfg, target),
                      lambda: H.cmd_atlas_roundtrip(self.cfg, v["lab"].get(), key, str(orig), str(tmp)),
                      lambda: H.cmd_vd_verify(self.cfg, str(orig), str(tmp))], "Test poprawności konwertera",
                     on_ok=lambda o: s3.ok("Test zakończony. W szczegółach powinno być: OBRAZ IDENTYCZNY.")
                     if any("IDENTYCZNY" in x for x in o) else s3.bad("Wynik inny niż oczekiwany (zobacz Szczegóły)."))

        self.button(s3.body, "📦 Spakuj do .vd", go, big=True)
        self.button(s3.body, "Test konwertera", roundtrip, "Pakuje NIEZMIENIONY oryginał i porównuje – "
                                                             "powinno wyjść „OBRAZ IDENTYCZNY”.")
        self.button(s3.body, "Otwórz folder z plikami .vd", lambda: self.open_folder(H.workdir(self.cfg)))

    # ---- tools
    def page_tools(self, p):
        H = self.H
        self.head(p, "🔎 Podgląd i narzędzia", "Szybkie skróty do programów i sprawdzanie przedmiotów.")
        s1 = Step(p, 1, "Sprawdź przedmiot po numerze", "Pokazuje nazwę, animację i to, czy da się ją przerobić.")
        g = tk.StringVar()
        self.row(s1.body, "Numer przedmiotu (ItemID)", g, "np. 0x2684")
        self.button(s1.body, "Sprawdź", self.lookup_step(s1, g))
        s2 = Step(p, 2, "Podgląd i programy", "Otwórz przeglądarkę plików .vd, UOFiddler albo podgląd ostatniej pracy.")

        def viewer():
            f = self.cfg.get("vdviewer")
            if not f or not Path(f).is_file():
                messagebox.showinfo("Przeglądarka .vd", "Wskaż plik vd-viewer.html w Ustawieniach.")
                return
            webbrowser.open(Path(f).as_uri())

        def fiddler():
            d = Path(self.cfg.get("fiddler", ""))
            exe = next(iter(d.glob("UOFiddler*.exe")), None) if d.is_dir() else None
            if not exe:
                messagebox.showinfo("UOFiddler", "Wskaż folder UOFiddlera w Ustawieniach.")
                return
            subprocess.Popen([str(exe)], cwd=str(d))

        for t, fn, h in (("Przeglądarka plików .vd", viewer, "Przeciągnij plik .vd na okno przeglądarki. Możesz nałożyć kilka warstw."),
                         ("Uruchom UOFiddler", fiddler, None),
                         ("Podgląd ostatniej pracy", lambda: self.preview(self.last_lab), None),
                         ("Zatrzymaj podgląd", self.stop_preview, None)):
            self.button(s2.body, t, fn, h)
        s3 = Step(p, 3, "Foldery", "Szybkie otwieranie.")
        for t, k in (("Folder wyników", "output"), ("Folder ServUO", "serv"), ("Folder klienta", "client"),
                     ("Folder toolkitu", "toolkit")):
            self.button(s3.body, t, lambda k=k: self.cfg.get(k) and self.open_folder(self.cfg[k]) or
                        messagebox.showinfo("Folder", "Nie ustawiono tego folderu w Ustawieniach."))

    # ---- set from sheet
    def page_set(self, p):
        H = self.H
        self.head(p, "🧩 Zestaw z arkusza (zaawansowane)", "Cały strój naraz: jeden arkusz PNG 4×3 (po jednym przedmiocie w komórce), "
                                                           "osobny miecz i plik konfiguracji (lista przedmiotów). Przykład: zestaw Wiedźmina.")
        v = {k: tk.StringVar() for k in ("design", "sword", "config", "out", "actions")}
        v["actions"].set("0 4 9 13 16")
        s1 = Step(p, 1, "Pliki", "Możesz wypełnić przykładem Wiedźmina (jest w toolkicie) i zobaczyć, jak to działa.")
        self.row(s1.body, "Arkusz wzorów (PNG)", v["design"], "PNG z przezroczystością, siatka 4 kolumny × 3 rzędy.", kind="file")
        self.row(s1.body, "Miecz (PNG)", v["sword"], "Osobny PNG, poziomo, rękojeść po lewej.", kind="file")
        self.row(s1.body, "Konfiguracja (JSON)", v["config"], "Lista przedmiotów, komórki arkusza, kolejność rysowania.", kind="file")
        self.row(s1.body, "Folder wynikowy (lab)", v["out"], "Gdzie zapisać zbudowaną pracę.", kind="dir")
        self.row(s1.body, "Akcje (puste = wszystkie)", v["actions"], "0 4 9 13 16 na próbę.")

        def example():
            if not self.ready(["toolkit"]):
                return
            b = H.workroot(self.cfg) / "witcher-lab"
            v["design"].set(str(b / "witcher_design.png"))
            v["sword"].set(str(b / "witcher_sword.png"))
            v["config"].set(str(b / "witcher.json"))
            v["out"].set(str(b / "lab"))

        self.button(s1.body, "Wypełnij przykładem Wiedźmina", example)
        s2 = Step(p, 2, "Zbuduj i obejrzyj", "Zbuduj, sprawdź poprawność (verify) i otwórz podgląd.")

        def build():
            if not all(v[k].get().strip() for k in ("design", "sword", "config", "out")):
                messagebox.showinfo("Brakuje danych", "Uzupełnij wszystkie cztery pliki/foldery.")
                return

            def ok(_o):
                self.last_lab = v["out"].get()
                s2.ok("Zbudowane. Możesz otworzyć podgląd albo przejść do „Spakuj do .vd”.")

            self.run([lambda: H.cmd_build_set(self.cfg, v["out"].get(), v["design"].get(), v["sword"].get(),
                                              v["config"].get(), v["actions"].get())], "Budowanie zestawu", on_ok=ok,
                     on_fail=lambda o: s2.bad("Nie udało się (zobacz podpowiedź)."), keys=["toolkit", "client"])

        self.button(s2.body, "▶ Zbuduj", build, big=True)
        self.button(s2.body, "Sprawdź poprawność (verify)", lambda: self.run(
            [lambda: H.cmd_verify(self.cfg, v["out"].get())], "Sprawdzanie",
            on_ok=lambda o: s2.info("Szukaj w szczegółach: \"errors\": [] i missingSequences 0. Kod 1 jest normalny, gdy "
                                    "przedmioty różnią się od oryginału."), keys=["toolkit", "client"]))
        self.button(s2.body, "🌐 Podgląd", lambda: self.preview(v["out"].get()))

    # ---- patch
    def page_patch(self, p):
        H = self.H
        self.head(p, "🛠 Dodawanie do klienta (patch)", "Dodaje nowe grafiki, gumpy i animacje potworów do klienta z pliku "
                                                       "receptury (JSON). ZAWSZE najpierw „na sucho” – nic nie zapisuje, tylko pokazuje plan.")
        v = {"q": tk.StringVar(), "r": tk.StringVar()}
        s1 = Step(p, 1, "Znajdź wolne ID / sprawdź kolizje", "Wpisz nazwę lub numer i zobacz, czy jest wolny w klientach.")
        self.row(s1.body, "Nazwa lub numer", v["q"], "np. staff albo 0xDF0.")
        self.button(s1.body, "Szukaj", lambda: v["q"].get().strip() and self.run(
            [lambda: H.cmd_search(self.cfg, v["q"].get())], "Wyszukiwanie", keys=["pipeline", "client"]))
        s2 = Step(p, 2, "Receptura", "Plik JSON z opisem tego, co dodać (przykład: examples/recipe.example.json).")
        self.row(s2.body, "Plik receptury", v["r"], "Wskaż plik JSON.", kind="file", ftypes=[("JSON", "*.json")])
        s3 = Step(p, 3, "Na sucho, potem zastosuj", "Najpierw „Na sucho”. Przeczytaj wynik i ostrzeżenia (WARN). "
                                                    "„Zastosuj” zapisuje zmiany w kliencie – rób to tylko na KOPII.")

        def go(apply):
            if not v["r"].get().strip():
                messagebox.showinfo("Receptura", "Wskaż plik receptury.")
                return
            if apply and not messagebox.askyesno("Zastosuj zmiany", "To ZAPISZE zmiany w kliencie.\n\nCzy to jest KOPIA "
                                                 "klienta i sprawdziłeś wynik „na sucho”?"):
                return
            self.run([lambda: H.cmd_patch(self.cfg, v["r"].get(), apply)],
                     "Zastosowanie zmian" if apply else "Przebieg na sucho", keys=["pipeline", "client", "output"],
                     on_ok=lambda o: self._toggle_log(True))

        self.button(s3.body, "👁 Na sucho (bezpieczne)", lambda: go(False), big=True)
        self.button(s3.body, "✍ Zastosuj…", lambda: go(True))
        self.button(s3.body, "Otwórz pełne okno pipeline'u", lambda: self.ready(["pipeline"]) and subprocess.Popen(
            H.cmd_pipeline_gui(self.cfg)["argv"], cwd=self.cfg["pipeline"], env=H.cmd_pipeline_gui(self.cfg)["env"]))

    def page_help(self, p):
        self.head(p, "❓ Pomoc", "Słowniczek i typowa kolejność pracy.")
        t = scrolledtext.ScrolledText(p, height=32, wrap="word", font=("Segoe UI", 10))
        t.insert("1.0", HELP)
        t.configure(state="disabled")
        t.pack(fill="both", expand=True, padx=12, pady=6)
        popup(t, [("Kopiuj", lambda: t.event_generate("<<Copy>>"))])

    # ------------------------------------------------------------ run
    def _close(self):
        self.stop_preview()
        self.root.destroy()

    def run_app(self):
        self.show("settings" if self.H.missing(self.cfg) else "start")
        if self.H.missing(self.cfg):
            self.root.after(300, self._first_run)
        self.root.mainloop()

    def _first_run(self):
        messagebox.showinfo("Witaj!", "Pierwsze uruchomienie: najpierw wskaż, gdzie leżą Twoje foldery "
                                      "(klient UO, toolkit, folder wyników).\n\nMożesz kliknąć „Wykryj automatycznie” "
                                      "albo wybierać ręcznie. Zielone „OK” obok pola = poprawnie.")
        self._autodetect()


def run_gui(H) -> None:
    App(H).run_app()
