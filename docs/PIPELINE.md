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
python nelderim.py gump3d --body UO_Body_0x190.glb --item miecz.glb --kind weapon1h --out dir --anim 1992 --client "C:\Klient"
python nelderim.py holes  --item-vd szata.vd --body-vd body400.vd --body UO_Body_0x190.glb --auto-sheets 3
python uo3d/body_export.py --blend UO_Body_0x190.blend --out UO_Body_0x190.glb      # needs bpy 4.2 (or: blender -b X.blend -P uo3d/body_export.py -- --out X.glb)
```

The scripts can also be run directly (`python pipeline/nelderim_search.py ...`).

`pipeline/nelderim_patch.py` reads one recipe, classifies each item, and routes it to whichever engine actually needs to
touch it - `uopatch.py` for wearable art/gump/tiledata, `uop_gump_patch.py` when a gump id already lives in
`gumpartLegacyMUL.uop` (UOP beats MUL - a MUL-only write there is silently ignored by the client; with `MainMisc.uop`
present that is true for every gump id, so all of them are routed here and new ones are added to the UOP), or
`vd_inject.py` for a brand-new monster animation. Dry run is the default; `--apply` is required to write anything.

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
| `uo3d/` | 3D route without Blender (numpy + Pillow): glTF/FBX/OBJ, skinning, UO camera, cloth, weapons, `.vd` read/write, `.vd` -> `.glb`; CLIs `cli_render.py`, `cli_vd2glb.py`, `cli_gump.py`, `cli_holes.py`; `body_export.py` (runs inside Blender), `hang.py` (loose garments on a body without cloth chains), `data/cloak_pitch.json`. |
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
   **It is stronger than that for gumps:** when `MainMisc.uop` is present
   (and the client is >= 7.0.0) ClassicUO's `GumpsLoader` reads gumps ONLY
   from `gumpartLegacyMUL.uop` and never opens `Gumpart.mul`/`Gumpidx.mul`.
   A *new* gump id written to the MUL pair is therefore invisible too, not
   just ids that are already UOP-resident. Found 2026-10-14: the item showed
   its worn animation in the world, but the paperdoll stayed bare.
   `uop_gump_patch.py` now ADDS missing entries to the UOP (payload appended
   at the end of the file, record written into a free slot of the last
   block table, file count + header count bumped; room for `blkcap - used`
   entries, 52 in this shard's file), and `nelderim_patch.py` routes every
   gump there when `MainMisc.uop` exists. Art is the other way round: this
   client has no `artLegacyMUL.uop` (only `tileart.uop`), so `art.mul` is read.
   Verified on a copy of the UOP (all original entries byte-identical, new
   ones decode correctly) and **in game (2026-10-14): the paperdoll shows the
   new gump after the UOP entry was added.**
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

## robe_from_gump.py + batch anim_import + hair-hiding classes (2026-10-15)

* `python nelderim.py robe --gump g.png --toolkit TK --client CL --key szata_x [--graphic 0x2684 --base-anim 970]`:
  gump -> design (alpha bbox x4, LANCZOS) -> build_item (35 actions, face/hands cut) -> hood_blend -> `.vd`
  (`<toolkit>/workspace/ultima-online/vd/<key>_<base>.vd`). The .vd is a copy of the base slot layout: import it into an
  EMPTY slot, never into the base slot.
* GUI: Ubranie 2D, step 6 "Szata z gumpu" (task `robe`) runs the same tool.
* GUI: Dodawanie do klienta, step 5 takes a list of `.vd` files ("Dodaj plik .vd"): each gets its own slot and body; one
  result folder. Slot/body can be typed by hand only for a single file.
* `anim_import.py` takes `--vd` / `--name` repeatedly: every file gets the next empty slot (from `--first-slot`, default 432)
  and the next free body; one cumulative `anim<N>.mul/.idx`, `Bodyconv.def`, `mobtypes.txt`. A body is skipped when its
  paperdoll gumps (+50000 / +60000) already exist in `gumpartLegacyMUL.uop` (the gump patch would overwrite another item's gump).
* `servuo_item.py --hide-hair` (recipe key `hide_hair`): hooded robes remove the hair while worn and restore it on removal.
* Art: a client whose `art.mul` has 2-byte stubs for an item has NO icon (this client reads `art.mul`, `tileart.uop` is not
  used by ClassicUO). The recipe's `art` + `overwrite: true` writes it; the icons made from the gump are approximations.

## hood_blend.py - hood matched to the robe (2026-10-15)

`python nelderim.py hood --lab <lab> --masks <region_ids frames>`; in the app: Ubranie 2D -> Zaawansowane -> "Kaptur".
Post-processes the build_item atlases in place: the hood keeps the original silhouette and folds, its tone and grain
come from plain cloth just under the hood (brightness only, same .65 + .55 L shading as `fit_texture`), the seam is
blended over 6 rows and the face opening is filled dark. Result checked by eye on the alchemist robe (Hooded Shroud);
`hood_blend.json` in the lab blocks a second pass. Needs the toolkit's region masks (label 1 = face, 5 = hands).

## anim_import.py - People .vd into an empty anim2..5.mul slot (2026-10-15)

`python nelderim.py animimport --client <copy> --vd robe.vd --file 5 [--slot N] [--body N] --out DIR [--apply]`.
Picks the first empty People slot (all 175 idx records unused, no Bodyconv.def line) or `--slot`, a free body
(`anim_wire.free_bodies`), appends the 175 blocks to the end of `anim<N>.mul`, rewrites the idx records, then writes
Bodyconv.def + mobtypes.txt via `anim_wire.apply_plan`. Writes only to `--out`; re-reads every record and compares bytes.
Slots 400-431 are the gargoyle range (wired in Bodyconv.def though empty) - prefer a slot far from wired ones.
Worn item needs no Equipconv.def: tiledata `anim` = body id, paperdoll gump = body + 50000 / 60000.
Not verified in game for a freshly appended slot.

## ServUO class generator, Content Studio bridge, 3D icon (2026-10-15)

* `pipeline/servuo_item.py` - one `<Class>.cs` per wearable of a recipe, written to the output folder (never to the server).
  Base class by layer (BaseOuterTorso, BaseCloak, BaseHat, ... of ServUO 5.8). Checked: compiles against this shard's
  `Server.dll` / `Scripts.dll`. Not tested in game.
* Content Studio bridge (`lab/nelderim_hub.py: cmd_studio_*`, page "Model 3D (Blender)"): runs
  `tools/uo-content/pipeline.py` of a separate SpriteMotion checkout with `SPRITEMOTION_BLENDER` set and copies
  `item.vd` + review into `<output>/studio/<name>/`. Settings keys `studio` and `blender`. Verified with Blender 5.2.2
  and the example helmet preview (125 frames, validation passed); `third_party/UO_Model3D_v13` stays in that checkout.
* `uo3d/icon.py` / `cli_icon.py` - inventory icon from a 3D model with the animation renderer's rasterizer and lighting;
  ignores a nearly-all-zero `COLOR_0` layer (CC0 starter models carry one). SpriteMotion's own `inventory.png` is only the
  idle frame shrunk to 44 px, so this is new.

## UO_Model3D v13.5 in uo3d (2026-10-21)

Ported with the author's permission (Kserian / Levy): see `docs/UO_MODEL3D.md` for the full list and what is done.

* The v13 body must be exported with `uo3d/body_export.py`: Blender's glTF exporter re-expresses bones that do not inherit
  scale in their non-uniformly scaled parent's space and loses the shear (measured: mean 1.8-11 mm, max 17-73 mm against
  Blender's evaluated mesh). The script appends `extras.uo3d` = Blender's joint world matrices per scene frame of every action,
  non-deforming bones (clavicles; Blender ignores their groups, the exporter does not), rest heads / tails of the bones; all
  skin influences are exported (5 on 207 vertices). Self-check against the evaluated mesh: 0.00 mm.
* Body silhouette IoU (uo3d raster vs `body400.vd`, all 35 actions x 5 dirs): 0.883; actions 0-22 and 30-34 0.86-0.94,
  mounted 23-29 0.74-0.80.
* `uo3d/hang.py`: robe / skirt / cloak without cloth chains (v13 has none): pelvis-hung + leg hull push per frame, mounted lie
  along the legs, cloak pitch per action. Verified on a synthetic cone robe (walk spreads the hem, mounted lies on the legs);
  not compared with an original robe here.
* `uo3d/gump.py` + `cli_gump.py`: paperdoll gump (90.5 px/m, feet y 221, axis x 94.5) and art from the 3D model; weapons in
  the right hand on the mace haft line (48, 114.5), fist of body gump 12 cuts the haft (read from `gumpartLegacyMUL.uop`, then MUL:
  `nelderim_core.read_gump`, read-only). Checked by eye on UO_Model3D's picture of body gump 12; not in game.
* `uo3d/holes.py` + `cli_holes.py`: original body 400 seen through the item (UO_Model3D `item_body_holes.py` rules).
* `uo3d/tattoo.py` + `cli_tattoo.py` (`nelderim.py tattoo arm|torso`): decor tattoos for the layers 0x20-0x25 of the ClassicUO fork (`feature/decor-layers`).
  `arm`: a textured right-arm model -> a decal (the body's own arm skin 4 mm out, vertex RGBA, alpha = ink) + the paperdoll gumps (ink unrolled along
  the arm onto gump 12 / 13). `torso`: a 2D design on a white card -> a relief `.glb` (linework high, bevelled, the base follows the true front surface of
  the body), the texture, gumps (shaded by the body gump, wrapped on the chest, the female one UNDER the bra of gump 13) and the 44 px icon.
  Render the animation with `nelderim.py uo3d --kind arms --adjust '{"fit": false}' --own-side R --occlude-torso` (arm) or `--kind plate --adjust
  '{"fit": false}' --occlude-torso` on the `_render.glb` (torso); then `animimport`, `patch` (tiledata layer 32..37 + art), `gumppatch`, the C# class.
  Limits: the model must be in the pose / axes of `arm_for_tattoo.glb` (shoulder at the lowest X, thumb towards -Z); the 5 stored directions are mirrored by
  the client for the other 3, so a one-sided tattoo shows on the other arm there (as shields do). Needs scipy. Checked in game: arm 0x5389, torso 0x538A.

## Aktualizacja toolkitu 2D (SpriteMotion upstream)

The toolkit used by the 2D tabs (`Ubranie 2D`, `Broń 2D`, `Gump`) is a snapshot of
[DatMoshu/SpriteMotion](https://github.com/DatMoshu/SpriteMotion) plus Levy's overlay. Upstream `outfit-lab` is newer.
Updated on 2026-10-15 (in the toolkit, **not** in this repo; old files backed up to
`<toolkit>/_backup_before_upstream_20261015/`):

* replaced: `outfit-lab/build.py`, `build_item.py`, `make_gump.py`, `region-masks/uo.py`;
* added: `merge_items.py`, `make_gump_cloak.py`, `build_plate_armor.py`, `build_overalls.py`, `ITEMS.md`;
* `build.py` got a local compatibility patch: `--lightsaber` is still accepted next to `--energy-blade` and
  `fit_lightsaber = fit_energy_blade`, so the hub and the older `build_spartan.py` / `build_tracksuit.py` keep working;
* new `build_item.py` options exposed in the app (Ubranie 2D, advanced): `--cut`, `--fray`, `--fray-only`, `--planar`, `--back`;
* `make_gump.py` now names its files `gump_<id>_male.png`, `gump_<id>_female.png`, `comparison.png` (the app accepts both
  these and the old `porownanie.png`).

Inventory art: upstream's `inventory.png` is the idle frame cropped, shrunk to 44 px and alpha-thresholded - the same
approach as `pipeline/anim_art.py`, so there was nothing to port. `nelderim_patch.py` now warns when the client has
`artLegacyMUL.uop` (art would be read from the UOP, `art.mul` ignored). SpriteMotion's own license is MIT; its
`third_party/UO_Model3D_v13` is **not** and is not copied here.
