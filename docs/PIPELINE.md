# Nelderim pipeline - technical notes

User guide (Polish): see the main `README.md`. Rules for working with Claude Code: `CLAUDE.md`.

## Requirements

- Python 3.10+ with Pillow + numpy (`pip install -r requirements.txt`) - or just `Nelderim.exe`, which has both inside.
- The tools read the client from `--client` and write only to `--out`; they never assume a working directory and never
  write into the client folder.

## Command line

Every tool runs through the one entry point (same with `Nelderim.exe` instead of `python nelderim.py`):

```bash
python nelderim.py search --client "C:\Klient" --item staff          # tiledata by name / ItemID
python nelderim.py search --client "C:\Klient" --body 32             # one body: type + collisions (defs, UOP, anim.mul)
python nelderim.py patch  --client "C:\Klient" --recipe r.json --out wyniki          # dry run
python nelderim.py patch  --client "C:\Klient" --recipe r.json --out wyniki --apply  # write to wyniki/
python nelderim.py inject --client "C:\Klient" --vd potwor.vd --out wyniki [--apply]
python nelderim.py wire   --client "C:\Klient" --file 5 [--slots 196] [--apply] [--check-body 32]
python nelderim.py uo3d   --body UO_Body_0x190.glb --item model.glb --kind shirt --out dir --name x
python nelderim.py vd2glb --body UO_Body_0x190.glb --vd anim_0469.vd --out szata.glb
```

The scripts can also be run directly (`python pipeline/nelderim_search.py ...`).

`pipeline/nelderim_patch.py` reads one recipe, classifies each item, and routes it to whichever engine actually needs to
touch it - `uopatch.py` for wearable art/gump/tiledata, `uop_gump_patch.py` when a gump id already lives in
`gumpartLegacyMUL.uop` (UOP beats MUL - a MUL-only write there is silently ignored by the client), or `vd_inject.py` for
a brand-new monster animation. Dry run is the default; `--apply` is required to write anything.

## Layout

| Path | Purpose |
|---|---|
| `nelderim.py` | The one entry point: Nelderim Lab (no arguments) or a tool (`search`, `patch`, `inject`, `wire`, `uopatch`, `gumppatch`, `uo3d`, `vd2glb`). Also the helper modes the app and the exe use (`--run-script`, `--py`, `--pick`, `--deps-ok`). |
| `run_nelderim.bat` / `.sh` | Launchers: check Python/Pillow/numpy, install what is missing, start the app, keep the window open on errors. |
| `app/` | Web UI (HTML/JS/CSS; three.js 0.160 vendored in `app/vendor`, MIT). |
| `lab/nelderim_app.py` | Local server (127.0.0.1): jobs, 3D session, `.vd` preview. No format logic. |
| `lab/nelderim_hub.py` | Folder settings (`~/.nelderim_hub.json`), autodetect, command builders `cmd_*` for the toolkit and pipeline scripts. |
| `pipeline/nelderim_core.py` | Shared, proven building blocks - binary codecs, offset models, collision checks. Read its section comments before touching format logic anywhere. |
| `pipeline/nelderim_patch.py` | Recipe router - classifies recipe items and runs the engines below as subprocesses. |
| `pipeline/nelderim_search.py` | Read-only lookup: items by name/id, one anim id (gump/UOP status), one body id (collisions, type), free anim ids. |
| `pipeline/uopatch.py` | Wearable/item patcher: art, gump (MUL side), tiledata, optional `mobtypes.txt`/`body.def` entries. |
| `pipeline/uop_gump_patch.py` | Patches a gump directly inside `gumpartLegacyMUL.uop`, for gump ids that already live there. |
| `pipeline/vd_inject.py` | Imports a monster `.vd` into `anim.mul`/`anim.idx`, auto-picking (or taking) a body id. |
| `pipeline/anim_wire.py` | Finds animations in anim2..5.mul that no body uses yet and wires them into `Bodyconv.def` + `mobtypes.txt`. |
| `pipeline/uop_probe.py` | Compatibility shim re-exporting `uop_hash` / `read_uop_hashes` from `nelderim_core` (kept next to the scripts). |
| `uo3d/` | 3D route without Blender (numpy + Pillow): glTF/FBX/OBJ, skinning, UO camera, cloth, weapons, `.vd` read/write, `.vd` -> `.glb`; CLIs `cli_render.py`, `cli_vd2glb.py`. |
| `tests/` | pytest suite on a synthetic client (no game files); runs in CI before the exe build. |
| `client-config/` | Reference snapshot of this shard's live `.def`/`mobtypes.txt` files - see its own README. Not deployed automatically. |
| `build_exe.bat`, `.github/workflows/build-exe.yml` | PyInstaller build of `Nelderim.exe`; CI: tests, exe smoke test, release `Nelderim-windows.zip`. |

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

## Security notes

- The app server listens on 127.0.0.1 only. `Handler.guard()` (lab/nelderim_app.py) additionally requires Host `127.0.0.1`/`localhost`,
  no foreign `Origin`, and `Content-Type: application/json` on every POST, so no other web page (CSRF, DNS rebinding) can drive the tools
  while the app is running. Files are served/opened only from the configured folders (`allowed()` = real path containment).
- Nothing in the repo is secret: no tokens, keys or credentials (history scanned). Game data (`*.mul`, `*.uop`, `*.idx`, `*.vd`) is
  git-ignored and tests use a synthetic client; `UO_Body_0x190.glb` / `body400.vd` of UO_Model3D contain original client frames and
  must never be committed.
- CI: read-only token by default; only the exe job has `contents: write` (to publish the release).
- Report security problems privately to the repository owner, not in a public issue.

