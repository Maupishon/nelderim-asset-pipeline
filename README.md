# Nelderim Asset Pipeline

Tools for adding custom art, gumps, and monster animations to the
Nelderim UO shard (ServUO + ClassicUO, client 7.0.95) without hand-editing
`.mul`/`.uop` binaries.

Everything here follows one rule: **nothing ships without being proven
in-game.** Every format assumption in this repo was either confirmed
against the actual ClassicUO client source, or verified end-to-end on a
live server. Where that history matters for correctness, it's documented
in the code, not just in a commit message.

## Requirements

- Python 3.10+ (tested on the Windows client install)
- Pillow (`pip install -r requirements.txt`)
- Run everything from **inside your live client folder** (the one with
  `tiledata.mul`, `anim.idx`, `Gumpart.mul`, ...) - the tools read from
  `--client` and never assume a working directory.

## Setup

```bash
git clone <this-repo-url>
cd nelderim-asset-pipeline
pip install -r requirements.txt --break-system-packages
```

Then copy every `.py` file in this repo into your client folder (e.g.
`C:\Nelderim\UO_70950\UO_70950`), or run the tools with paths pointing
back into the repo checkout - either works, but keeping `uop_probe.py`
**inside the client folder** matters (see below).

## Quick start (GUI)

```bash
python nelderim_gui.py
```

Pick your client folder, use Search to look up existing items/animations,
add recipe items in the editor, click **Dry run** first (writes nothing),
check the output, then **Apply**. Hover any field for an explanation.

## Quick start (CLI)

```bash
python nelderim_patch.py --client "C:\Nelderim\UO_70950\UO_70950" --recipe myrecipe.json --out patched --apply
python nelderim_search.py --client "C:\Nelderim\UO_70950\UO_70950" --item "staff"
```

`nelderim_patch.py` reads one recipe, classifies each item, and routes it
to whichever engine actually needs to touch it - `uopatch.py` for wearable
art/gump/tiledata, `uop_gump_patch.py` when a gump id already lives in
`gumpartLegacyMUL.uop` (UOP beats MUL - a MUL-only write there is silently
ignored by the client), or `vd_inject.py` for a brand-new monster
animation. Dry run is the default; `--apply` is required to write
anything.

## What's in this repo

| File | Purpose |
|---|---|
| `nelderim_core.py` | Shared, proven building blocks - binary codecs, offset models, collision checks. Every other tool either calls into this or duplicates a piece of it under test. Read this file's section comments before touching format logic anywhere. |
| `nelderim_patch.py` | Unified CLI - classifies recipe items and routes them to the three engines below as subprocesses. |
| `nelderim_search.py` | Read-only lookup: search items by name/id, inspect an anim id's gump/UOP status, inspect a body id's collisions and type. |
| `nelderim_gui.py` | Tkinter desktop front-end. No format logic - only builds a recipe and shells out to the CLI tools above. |
| `uopatch.py` | Wearable/item patcher: art, gump (MUL side), tiledata, optional `mobtypes.txt`/`body.def` entries. |
| `uop_gump_patch.py` | Patches a gump directly inside `gumpartLegacyMUL.uop` in place, for items whose gump id already lives there. |
| `vd_inject.py` | Imports a `.vd` monster-animation container into `anim.mul`/`anim.idx`, auto-picking (or taking) a target body id. |
| `uop_probe.py` | Thin compatibility shim - re-exports `uop_hash`/`read_uop_hashes` from `nelderim_core` under the name the other tools optionally import. Keep it alongside the other tools **in the client folder** so the `AnimationFrame*.uop` collision check is never silently skipped. |
| `client-config/` | Reference snapshot of this shard's live `.def`/`mobtypes.txt` files - see its own README. Not deployed automatically; a tool's own `--out` folder is always the real deploy source. |

## Recipe format

See `examples/recipe.example.json`. Two item shapes:

**Wearable/item** - `item_id`, `anim`, `layer`, `tile_name`, `art`,
`gump_male`, `gump_female` (any subset - only supplied fields get
touched). Paths are relative to the recipe file's own folder.

**Monster animation** - `vd` (path to the `.vd` container), optional
`body` (specific target id; omit to auto-pick a free, collision-free one).

## Safety model

- Every write is dry-run by default; `--apply` is required.
- Every engine backs up whatever it's about to touch before writing.
- Every engine re-reads its own output after writing and verifies it
  round-trips, before declaring success.
- `anim.mul` is only ever appended to - existing bytes never move.
- A target id is checked against `body.def`, `Bodyconv.def`,
  `AnimationFrame*.uop`/`gumpartLegacyMUL.uop`, `gump.def`, and `art.def`
  *before or during* writing, because each of those can silently redirect
  what the client actually shows, independent of what gets written to
  `anim.idx`/`Gumpart.mul`/`art.mul`. The `gump.def`/`art.def` checks are
  WARN-level (surfaced by `uopatch.py`, `uop_gump_patch.py`, and
  `nelderim_search.py --anim`) rather than hard blocks, since this
  project's exact knowledge of their resolution order relative to UOP is
  less battle-tested than `body.def`'s - treat a warning as "verify this
  one in-game," not as an error.
- Referenced assets (art/gump/`.vd` files) are checked for existence
  across the *whole* recipe before anything is written. Three policies:
  `stop` (default - list everything missing, write nothing), `skip`
  (drop just the missing field, process the rest of that item), `ask`
  (CLI: y/n prompt per file in the terminal; GUI: a Browse/Skip/Cancel
  dialog per file, resolved before the patch subprocess is even started).

## Landmines this project already found, so you don't have to

These cost real debugging time. They're also documented at the point of
use in `nelderim_core.py`, but worth having in one place:

1. **UOP beats MUL.** If a gump/animation id already has an entry in a
   `.uop` file, writing to the matching `.mul` file has no visible effect
   in-game. Check UOP residency before deciding where to write.
2. **Resolution order matters.** `body.def` (hard redirect) →
   `AnimationFrame*.uop` → `Bodyconv.def` → `anim.mul`. A body listed in
   any earlier stage never reaches your `anim.mul` write.
3. **anim.idx offsets are not one formula.** EQUIPMENT/HUMAN bodies
   ("People" group) use `(graphic-400)*175 + 35000`. MONSTER/SEA_MONSTER
   bodies ("High" group) use a flat `graphic * 110`. These are NOT
   interchangeable, and getting this wrong produces a patch that verifies
   cleanly, has no errors anywhere, and renders nothing - this happened
   once, on a real deploy, and cost a full diagnostic session using the
   actual ClassicUO client source (not a MUL/UOP editor) to find.
4. **Animation "linking" (copying anim.idx records to point at another
   body's frames) is unreliable.** The client can refuse to render a
   linked slot even with byte-identical data. Recycling (pointing an
   item's own `anim` tiledata field directly at a working body) is
   reliable; linking is opt-in and flagged as such.
5. **New body ids for anim.idx must not shift already-deployed data.**
   Declaring a body's mobtype after the fact can change the computed
   offset of every later id in the same offset model. Pick new ids above
   the highest one already declared, or use the flat (MONSTER) model,
   which doesn't have this problem.
6. **BMP silently drops alpha** (at least via Pillow's default encoder on
   this stack) - a BMP with an intended transparent cutout renders fully
   opaque in-game. `load_png()` warns when this is detected; prefer PNG
   for anything that needs a transparent background.
7. **`gump.def` and `art.def` redirect ids the same way `body.def` does**,
   just for gumps and static art instead of bodies. Discovered late
   (2026-08-11, once their real content was first reviewed) - a gump or
   art id listed as a redirect source there may not show what was just
   written to it. Checked and WARNed on by `uopatch.py`,
   `uop_gump_patch.py`, and `nelderim_search.py --anim`, but their exact
   position in the resolution order isn't as thoroughly verified as
   `body.def`'s - a WARN here means "check this one in-game," not "this
   is definitely broken."
