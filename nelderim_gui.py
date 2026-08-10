#!/usr/bin/env python3
"""
nelderim_gui.py - desktop front-end for the Nelderim asset pipeline.

DESIGN RULE (the whole reason this project works): this GUI contains NO
format logic whatsoever. It does not encode a gump, compute an offset,
parse a .vd, or touch a .mul byte. It only:
    * collects paths and ids from the user,
    * assembles a recipe dict (identical shape to the hand-written JSON),
    * shells out to the already-tested tools (nelderim_patch.py,
      nelderim_search.py) exactly as the user would from the terminal,
    * streams their stdout/stderr back into a log pane.

Every actual change still goes through nelderim_patch.py, which routes to
uopatch.py / uop_gump_patch.py / vd_inject.py - each with its own backup,
verification, and --apply gate. The GUI's "Apply" button simply passes
--apply through. A dry run is always one click away and is the default.

Requires only the Python standard library (tkinter). No pip installs.
"""

from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_TOOL = os.path.join(HERE, "nelderim_patch.py")
SEARCH_TOOL = os.path.join(HERE, "nelderim_search.py")


# ---------------------------------------------------------------------------
# Tooltip: tkinter has no built-in tooltip widget. Small, dependency-free
# implementation - shows a label near the cursor after a short hover delay.
# ---------------------------------------------------------------------------

class Tooltip:
    DELAY_MS = 500

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _evt=None):
        self._cancel()
        self.after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tip, text=self.text, justify="left",
                         background="#ffffe0", relief="solid", borderwidth=1,
                         wraplength=340, font=("Segoe UI", 9), padx=6, pady=4)
        label.pack()

    def _hide(self, _evt=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


def tip(widget, text):
    """Convenience wrapper - attaches a Tooltip and returns the widget,
    so it can be chained inline where widgets are created."""
    Tooltip(widget, text)
    return widget


# ---------------------------------------------------------------------------
# Subprocess runner: streams output into a thread-safe queue so the UI stays
# responsive while a tool runs.
# ---------------------------------------------------------------------------

class ToolRunner:
    def __init__(self, on_line, on_done):
        self.on_line = on_line
        self.on_done = on_done
        self.q: queue.Queue = queue.Queue()
        self.proc = None

    def run(self, argv):
        def worker():
            try:
                self.proc = subprocess.Popen(
                    argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1)
                for line in self.proc.stdout:
                    self.q.put(("line", line.rstrip("\n")))
                self.proc.wait()
                self.q.put(("done", self.proc.returncode))
            except Exception as e:  # noqa: BLE001 - surface any launch error
                self.q.put(("line", f"[GUI ERROR] {e}"))
                self.q.put(("done", -1))

        threading.Thread(target=worker, daemon=True).start()

    def pump(self, root):
        """Called on the Tk main loop to drain queued output."""
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "line":
                    self.on_line(payload)
                elif kind == "done":
                    self.on_done(payload)
        except queue.Empty:
            pass
        root.after(80, lambda: self.pump(root))


# ---------------------------------------------------------------------------
# One recipe item, as edited in the UI. Mirrors the recipe JSON fields.
# ---------------------------------------------------------------------------

class ItemRow:
    KINDS = ("wearable/item", "monster anim (.vd)")

    def __init__(self):
        self.name = ""
        self.kind = self.KINDS[0]
        self.item_id = ""
        self.anim = ""
        self.layer = ""
        self.tile_name = ""
        self.art = ""
        self.gump_male = ""
        self.gump_female = ""
        self.vd = ""
        self.body = ""

    def to_recipe_item(self, base_dir):
        """Produce the recipe dict for this row. Paths are stored relative
        to base_dir when possible (the recipe's own directory), matching
        how the hand-written recipes referenced assets."""
        def rel(p):
            if not p:
                return p
            try:
                return os.path.relpath(p, base_dir)
            except ValueError:
                return p  # different drive on Windows - keep absolute

        it = {}
        if self.name:
            it["name"] = self.name
        if self.kind == "monster anim (.vd)":
            if self.vd:
                it["vd"] = rel(self.vd)
            if self.body.strip():
                it["body"] = int(self.body)
            return it

        # wearable/item
        if self.item_id:
            it["item_id"] = self.item_id
        if self.anim.strip():
            it["anim"] = int(self.anim)
        if self.layer.strip():
            it["layer"] = int(self.layer)
        if self.tile_name:
            it["tile_name"] = self.tile_name
        if self.art:
            it["art"] = rel(self.art)
        if self.gump_male:
            it["gump_male"] = rel(self.gump_male)
        if self.gump_female:
            it["gump_female"] = rel(self.gump_female)
        return it


# ---------------------------------------------------------------------------
# Main application window.
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root):
        self.root = root
        root.title("Nelderim Asset Pipeline")
        root.geometry("980x720")

        self.client_dir = tk.StringVar()
        self.items: list[ItemRow] = []
        self.runner = ToolRunner(self._log_line, self._on_done)
        self.runner.pump(root)

        self._build_top()
        self._build_middle()
        self._build_log()

    # ---- top: client folder + search -----------------------------------

    def _build_top(self):
        f = ttk.LabelFrame(self.root, text="Client folder")
        f.pack(fill="x", padx=8, pady=(8, 4))
        entry = ttk.Entry(f, textvariable=self.client_dir)
        entry.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        tip(entry, "Path to the UO client folder that holds the .mul/.uop "
                   "files (tiledata.mul, anim.idx, Gumpart.mul, ...). This "
                   "is the SAME folder you run the command-line tools from.")
        btn = ttk.Button(f, text="Browse...", command=self._pick_client)
        btn.pack(side="left", padx=4)
        tip(btn, "Open a folder picker to choose the client folder.")

        s = ttk.LabelFrame(self.root, text="Search (read-only)")
        s.pack(fill="x", padx=8, pady=4)
        self.search_kind = tk.StringVar(value="item")
        radio_help = {
            "item": "Search tiledata.mul by item name (partial match) or "
                   "exact ID (0x5384 or 21380). Shows layer, anim, flags.",
            "anim": "Look up one animation ID: does it have a male/female "
                   "gump, is that gump in Gumpart.mul or the .uop file, and "
                   "which items already use it.",
            "body": "Look up one monster body ID: its type, whether "
                   "body.def/Bodyconv.def/AnimationFrame*.uop redirects or "
                   "claims it, and whether it already has animation data.",
        }
        for label, val in (("item", "item"), ("anim", "anim"), ("body", "body")):
            rb = ttk.Radiobutton(s, text=label, variable=self.search_kind, value=val)
            rb.pack(side="left", padx=2)
            tip(rb, radio_help[val])
        self.search_query = tk.StringVar()
        qe = ttk.Entry(s, textvariable=self.search_query, width=30)
        qe.pack(side="left", padx=4)
        tip(qe, "What to search for: a name fragment (e.g. 'staff'), or an "
               "exact ID (0x5384) for item search; a plain number for anim/"
               "body search.")
        sb = ttk.Button(s, text="Search", command=self._do_search)
        sb.pack(side="left", padx=4)
        tip(sb, "Run the search. This never changes any file - it only "
               "reads and reports.")

    # ---- middle: item list + editor ------------------------------------

    def _build_middle(self):
        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.LabelFrame(mid, text="Recipe items")
        left.pack(side="left", fill="both", expand=False, padx=(0, 4))
        self.listbox = tk.Listbox(left, width=32, height=14)
        self.listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        tip(self.listbox, "Everything you're about to patch, in one list. "
                          "Click an item to edit it on the right.")
        btns = ttk.Frame(left)
        btns.pack(fill="x")
        add_btn = ttk.Button(btns, text="Add", command=self._add_item)
        add_btn.pack(side="left", padx=2)
        tip(add_btn, "Add a new, blank item to the recipe.")
        rm_btn = ttk.Button(btns, text="Remove", command=self._remove_item)
        rm_btn.pack(side="left", padx=2)
        tip(rm_btn, "Delete the item currently selected on the left.")

        right = ttk.LabelFrame(mid, text="Item editor")
        right.pack(side="left", fill="both", expand=True)
        self.editor = ItemEditor(right, on_change=self._refresh_list)
        self.editor.pack(fill="both", expand=True, padx=4, pady=4)

        actions = ttk.Frame(self.root)
        actions.pack(fill="x", padx=8, pady=4)
        dry_btn = ttk.Button(actions, text="Dry run",
                             command=lambda: self._run_patch(apply=False))
        dry_btn.pack(side="left", padx=4)
        tip(dry_btn, "Show exactly what would happen - which files would "
                     "be touched and how - WITHOUT writing anything. "
                     "Always safe to click. Do this before Apply.")
        apply_btn = ttk.Button(actions, text="APPLY (writes files)",
                               command=lambda: self._run_patch(apply=True))
        apply_btn.pack(side="left", padx=4)
        tip(apply_btn, "Actually write the changes to disk. Each tool "
                       "keeps its own backup first, but only click this "
                       "after a Dry run looks correct.")
        json_btn = ttk.Button(actions, text="Show recipe JSON",
                              command=self._show_recipe)
        json_btn.pack(side="left", padx=4)
        tip(json_btn, "See the exact instructions (recipe) that will be "
                      "sent to the patch tools, in raw form.")
        self.missing_mode = tk.StringVar(value="stop")
        ml = ttk.Label(actions, text="  missing assets:")
        ml.pack(side="left")
        tip(ml, "What to do if an image/.vd file listed in an item can't "
               "be found on disk.")
        mc = ttk.Combobox(actions, textvariable=self.missing_mode, width=6,
                          values=("stop", "skip"), state="readonly")
        mc.pack(side="left")
        tip(mc, "stop = check everything first and refuse to run if "
               "anything is missing (safest, default).\n"
               "skip = leave out just the missing piece and still process "
               "the rest of that item.")

    # ---- bottom: log ----------------------------------------------------

    def _build_log(self):
        lf = ttk.LabelFrame(self.root, text="Output")
        lf.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log = scrolledtext.ScrolledText(lf, height=12, state="disabled",
                                             font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    # ---- helpers --------------------------------------------------------

    def _pick_client(self):
        d = filedialog.askdirectory(title="Select client folder")
        if d:
            self.client_dir.set(d)

    def _log_line(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _on_done(self, rc):
        self._log_line(f"\n[finished, exit code {rc}]")

    def _require_client(self):
        c = self.client_dir.get().strip()
        if not c or not os.path.isdir(c):
            messagebox.showerror("No client folder",
                                 "Pick a valid client folder first.")
            return None
        return c

    # ---- item list management ------------------------------------------

    def _add_item(self):
        it = ItemRow()
        it.name = f"item{len(self.items)+1}"
        self.items.append(it)
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set("end")
        self.editor.load(it)

    def _remove_item(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        del self.items[sel[0]]
        self.editor.load(None)
        self._refresh_list()

    def _on_select(self, _evt):
        sel = self.listbox.curselection()
        if sel:
            self.editor.load(self.items[sel[0]])

    def _refresh_list(self):
        keep = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for it in self.items:
            tag = "vd" if it.kind.startswith("monster") else "item"
            self.listbox.insert("end", f"[{tag}] {it.name or '(unnamed)'}")
        if keep:
            try:
                self.listbox.selection_set(keep[0])
            except tk.TclError:
                pass

    # ---- recipe assembly + running -------------------------------------

    def _base_dir(self):
        # recipe is written into the client folder, so asset paths are
        # relative to it - same convention as the hand-written recipes.
        return self.client_dir.get().strip()

    def _build_recipe(self):
        base = self._base_dir()
        return {"items": [it.to_recipe_item(base) for it in self.items]}

    def _show_recipe(self):
        try:
            recipe = self._build_recipe()
        except ValueError as e:
            messagebox.showerror("Invalid field",
                                 f"A numeric field has bad input: {e}")
            return
        win = tk.Toplevel(self.root)
        win.title("Recipe JSON")
        txt = scrolledtext.ScrolledText(win, width=70, height=30,
                                        font=("Consolas", 9))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", json.dumps(recipe, indent=2, ensure_ascii=False))
        txt.configure(state="disabled")

    def _write_recipe_file(self, client):
        recipe = self._build_recipe()
        path = os.path.join(client, "_nelderim_gui_recipe.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recipe, f, indent=2, ensure_ascii=False)
        return path

    def _run_patch(self, apply):
        client = self._require_client()
        if not client:
            return
        if not self.items:
            messagebox.showinfo("No items", "Add at least one recipe item.")
            return
        try:
            recipe_path = self._write_recipe_file(client)
        except ValueError as e:
            messagebox.showerror("Invalid field",
                                 f"A numeric field has bad input: {e}")
            return

        if apply:
            if not messagebox.askyesno(
                    "Confirm apply",
                    "This will run the patch tools with --apply and write "
                    "files.\nEach engine keeps its own backup, but proceed "
                    "only if you have tested a dry run first.\n\nContinue?"):
                return

        argv = [sys.executable, PATCH_TOOL,
                "--client", client, "--recipe", recipe_path,
                "--out", os.path.join(client, "patched_gui"),
                "--missing", self.missing_mode.get()]
        if apply:
            argv.append("--apply")

        self._clear_log()
        self._log_line(">>> " + " ".join(argv) + "\n")
        self.runner.run(argv)

    def _do_search(self):
        client = self._require_client()
        if not client:
            return
        q = self.search_query.get().strip()
        if not q:
            messagebox.showinfo("Empty query", "Type something to search for.")
            return
        argv = [sys.executable, SEARCH_TOOL, "--client", client,
                "--" + self.search_kind.get(), q]
        self._clear_log()
        self._log_line(">>> " + " ".join(argv) + "\n")
        self.runner.run(argv)


# ---------------------------------------------------------------------------
# Item editor sub-panel.
# ---------------------------------------------------------------------------

class ItemEditor(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.on_change = on_change
        self.item: ItemRow | None = None
        self.vars = {}

        r = 0
        self._row("name", "Name", r,
                  "A label just for you, to tell items apart in the list "
                  "on the left. Not written into the game.")
        r += 1

        kind_lbl = ttk.Label(self, text="Kind")
        kind_lbl.grid(row=r, column=0, sticky="w", padx=4, pady=2)
        tip(kind_lbl, "What this item is:\n"
                      "wearable/item = an equippable object (weapon, robe, "
                      "hat...) with its own icon/paperdoll.\n"
                      "monster anim (.vd) = a brand-new monster animation "
                      "imported from a .vd file.")
        self.kind_var = tk.StringVar()
        self.kind_box = ttk.Combobox(self, textvariable=self.kind_var, width=22,
                                     values=ItemRow.KINDS, state="readonly")
        self.kind_box.grid(row=r, column=1, sticky="w", padx=4, pady=2)
        self.kind_box.bind("<<ComboboxSelected>>", lambda e: self._commit())
        tip(self.kind_box, "Pick one - the fields below change meaning "
                           "depending on this choice.")
        r += 1

        self._row("item_id", "Item ID (0x..)", r,
                  "The item's own hex ID in the game, e.g. 0x5384. This is "
                  "how the server and client identify the item type.")
        r += 1
        self._row("anim", "Anim id", r,
                  "Which animation/paperdoll this item uses. Reusing an "
                  "existing, working anim id (recycling) is far more "
                  "reliable than inventing a new one - use Search (anim) "
                  "to check what an id already has before choosing it.")
        r += 1
        self._row("layer", "Layer", r,
                  "The equip slot number: 2 = one-handed weapon, "
                  "22 = outer torso (robes), and so on. Look at a similar, "
                  "already-working item with Search (item) to find the "
                  "right number.")
        r += 1
        self._row("tile_name", "Tile name", r,
                  "The name players see in-game for this item. Kept short "
                  "(around 20 characters) - longer names get cut off.")
        r += 1
        self._file_row("art", "Art PNG/BMP", r,
                       "The icon shown in the backpack/on the ground. "
                       "Needs a transparent background outside the icon "
                       "shape - PNG preserves transparency, plain BMP "
                       "usually does not (you'll get a warning if so).")
        r += 1
        self._file_row("gump_male", "Gump male", r,
                       "The paperdoll picture for a male character wearing "
                       "this item. Leave empty if you're only fixing/adding "
                       "the female one.")
        r += 1
        self._file_row("gump_female", "Gump female", r,
                       "The paperdoll picture for a female character "
                       "wearing this item. Leave empty if you're only "
                       "fixing/adding the male one.")
        r += 1
        self._file_row("vd", "VD file", r,
                       [("VD", "*.vd"), ("All", "*.*")],
                       "The .vd container holding the new monster's "
                       "animation frames (walk, attack, stand still...).")
        r += 1
        self._row("body", "Body (vd, optional)", r,
                  "Which body id the new monster should use. Leave this "
                  "empty to have the tool automatically pick a free, "
                  "collision-free id for you - the safer default.")
        r += 1

        self.load(None)

    def _row(self, key, label, r, tooltip=""):
        lbl = ttk.Label(self, text=label)
        lbl.grid(row=r, column=0, sticky="w", padx=4, pady=2)
        v = tk.StringVar()
        e = ttk.Entry(self, textvariable=v, width=40)
        e.grid(row=r, column=1, sticky="we", padx=4, pady=2)
        e.bind("<FocusOut>", lambda ev: self._commit())
        self.vars[key] = v
        if tooltip:
            tip(lbl, tooltip)
            tip(e, tooltip)

    def _file_row(self, key, label, r, types=None, tooltip=""):
        # allow calling with either (types) or (tooltip) as 4th positional
        if isinstance(types, str) and not tooltip:
            tooltip, types = types, None
        lbl = ttk.Label(self, text=label)
        lbl.grid(row=r, column=0, sticky="w", padx=4, pady=2)
        v = tk.StringVar()
        e = ttk.Entry(self, textvariable=v, width=30)
        e.grid(row=r, column=1, sticky="we", padx=4, pady=2)
        e.bind("<FocusOut>", lambda ev: self._commit())
        self.vars[key] = v
        ft = types or [("Images", "*.png *.bmp"), ("All", "*.*")]
        btn = ttk.Button(self, text="...", width=3,
                         command=lambda: self._pick(key, ft))
        btn.grid(row=r, column=2, padx=2)
        if tooltip:
            tip(lbl, tooltip)
            tip(e, tooltip)
            tip(btn, "Browse for the file instead of typing the path.")

    def _pick(self, key, filetypes):
        p = filedialog.askopenfilename(filetypes=filetypes)
        if p:
            self.vars[key].set(p)
            self._commit()

    def load(self, item):
        self.item = item
        if item is None:
            for v in self.vars.values():
                v.set("")
            self.kind_var.set(ItemRow.KINDS[0])
            return
        self.kind_var.set(item.kind)
        for key, var in self.vars.items():
            var.set(getattr(item, key, "") or "")

    def _commit(self):
        if self.item is None:
            return
        self.item.kind = self.kind_var.get()
        for key, var in self.vars.items():
            setattr(self.item, key, var.get())
        self.on_change()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
