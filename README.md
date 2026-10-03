# Nelderim Asset Pipeline

Tools for adding custom art, gumps, and monster animations to the
Nelderim UO shard (ServUO + ClassicUO, client 7.0.95) without hand-editing
`.mul`/`.uop` binaries.

Everything here follows one rule: **nothing ships without being proven
in-game.** Every format assumption in this repo was either confirmed
against the actual ClassicUO client source, or verified end-to-end on a
live server. Where that history matters for correctness, it's documented
in the code, not just in a commit message.

## Jak uruchomić (dla początkujących)

Jeden program: **Nelderim Lab** (hub + pipeline razem). Otwiera się w przeglądarce, ale działa tylko na Twoim komputerze (nic nie wysyła do internetu).

| Jak uruchomić | Plik |
|---|---|
| **Windows (najprościej, bez Pythona)** | `Nelderim.exe` z paczki **Nelderim-windows.zip** (niżej) |
| Windows, z Pythonem | dwuklik `run_nelderim.bat` |
| Linux / macOS | `./run_nelderim.sh` |

(`run_hub.bat` / `run_hub.sh` robią to samo. Stare okno Tk: `python nelderim.py --classic`.)

### 1. Pobranie (na dowolny komputer)
**Windows – paczka gotowa do uruchomienia:**
1. Pobierz **[Nelderim-windows.zip](https://github.com/Maupishon/nelderim-asset-pipeline/releases/latest/download/Nelderim-windows.zip)** (albo strona [Releases](https://github.com/Maupishon/nelderim-asset-pipeline/releases) → najnowsza → *Assets*). Konto GitHub nie jest potrzebne.
2. Kliknij zip prawym → **Wyodrębnij wszystkie…** (nie uruchamiaj z wnętrza zipa).
3. Wejdź do folderu `Nelderim` i uruchom **`Nelderim.exe`**. Ostrzeżenie Windows → **Więcej informacji → Uruchom mimo to** (program nie jest podpisany).
4. Trzymaj cały folder razem (`Nelderim.exe` obok `app`, `uo3d` i skryptów `.py`). Folder możesz przenieść gdziekolwiek, np. na pendrive.

Python **nie jest potrzebny**: exe ma w środku Pythona, numpy i Pillow i sam uruchamia też skrypty Levy'ego z toolkitu. Jeśli toolkit ma własne `.venv` albo w systemie jest Python z numpy i Pillow, program użyje ich.

**Bez exe (Windows/Linux/macOS):** zielony przycisk **Code → Download ZIP**, rozpakuj, uruchom `run_nelderim.bat` / `./run_nelderim.sh`. Potrzebny Python 3.10+ (<https://www.python.org/downloads/>, zaznacz **„Add Python to PATH"**); Pillow i numpy doinstalują się same.

### 2. Co jeszcze musisz mieć (pliki, nie programy)
- **Kopię klienta gry** (folder z `anim.idx`, `anim.mul`, `tiledata.mul`, `*.def`). **Zawsze kopia**, nigdy jedyny egzemplarz.
- Do metod 2D (ubranie/broń z obrazka, gump, zestaw): folder **SpriteMotion-UO-Toolkit** z rozpakowaną paczką Levy'ego (`SpriteMotion_skrypty_Nelderim_1.zip`, z nadpisaniem). Instalowanie toolkitu (`pip install -e`) nie jest potrzebne – wystarczą pliki.
- Do modelu 3D: folder projektu **UO_Model3D** (z `model/UO_Body_0x190.glb`; obok folder `pipeline` z `body400.vd`, `horse200.vd`, `weapon_motion.json`, `uo_shield_keys.py`). Blender niepotrzebny.

Nic nie musi leżeć w konkretnym miejscu ani na konkretnym dysku. Przy pierwszym uruchomieniu kliknij **Ustawienia → Wykryj automatycznie**: program przeszuka Pulpit, Pobrane, Dokumenty, folder obok siebie i wszystkie dyski (do 4 poziomów w głąb) i rozpozna foldery po zawartości, nie po nazwie. Czego nie znajdzie, wskażesz przyciskiem **Wybierz…**. Ustawienia zapisują się dla użytkownika komputera (`~/.nelderim_hub.json`), więc na innym komputerze przechodzisz to raz od nowa.

### 3. Praca
1. Uruchom. Otworzy się karta przeglądarki **Nelderim Lab**. Czarne okno w tle = program; zamknięcie go (albo przycisk **⏻ zamknij**) wyłącza program.
2. **Ustawienia → Wykryj automatycznie** (albo **Wybierz…** przy każdym polu). Zielona kropka = OK.
3. **Start** → wybierz zadanie i idź od kroku 1. Znak **?** i najechanie myszą pokazują podpowiedzi.
   - **🧊 Model 3D (Fit Lab)**: wczytaj `.glb` / `.fbx` (binarny) / `.obj`, dopasuj suwakami (przesunięcie, obrót, skala), obejrzyj 3D i podglądy kamerą UO na żywo (z liczbą „poke px" – gdzie ciało przebija przez przedmiot), **Zmierz**, potem **▶ Próba** → **Wszystkie**. Cofnij/Ponów (Ctrl+Z / Ctrl+Y), **Zapisz ustawienia**. Obok modelu ciała folder `pipeline` z UO_Model3D daje: dokładną sylwetkę (`body400.vd`), konia (`horse200.vd`), broń (`weapon_motion.json`), tarczę (`uo_shield_keys.py`).
   - **Nie masz modelu 3D?** W Fit Labie **🎞 Z pliku .vd…** (albo w **Podgląd .vd → 🧊 Przymierz w 3D**): program odtworzy z klatek „stój” oryginalnego przedmiotu przybliżoną bryłę 3D z kolorami, już założoną na ciało (zapis `…_z_vd.glb`). Dobra do przymiarki i poprawek; kształt pochodzi z sylwetek, więc bez ukrytych fałd.
   - **Ubranie 2D / Broń 2D / Gump / Zestaw**: metody Levy'ego (toolkit). Najpierw kilka akcji na próbę, potem 35.
   - **Spakuj do .vd**: z kopią poprzedniej wersji i testem konwertera. **Podgląd .vd**: klatki z ciałem pod spodem.
   - **Dodawanie do klienta**: receptura (przedmioty, potwory z `.vd`), szukanie, wolne ID. Zawsze **Na sucho** najpierw; **Zastosuj** pyta o potwierdzenie.
   - **Dodawanie do klienta → krok 4 „Nieprzypisane animacje”**: wybierz `anim2–5.mul`, **Szukaj** pokaże animacje, których żadne body jeszcze nie używa (z miniaturą i proponowanym wolnym body). Zaznacz, nadaj nazwy, **Podepnij** – program dopisze wpisy do `Bodyconv.def` i `mobtypes.txt` w folderze wyników (z kopią obecnych). Skopiuj je do kopii klienta i sprawdź najpierw jedno body w grze.
4. Gotowy `.vd` importujesz w UOFiddlerze (Animations → Animation Edit → Import from VD), na kopii klienta.

### 4. Gdy coś nie działa
- „Python not found" → użyj `Nelderim.exe` (nie potrzebuje Pythona) albo zainstaluj Pythona z „Add Python to PATH".
- Przy kopiowaniu `.vd`: „plik jest używany przez inny proces" → program sam czeka kilka sekund; gdy plik dalej jest otwarty (np. w UOFiddlerze), zapisze go pod nową nazwą `…_nowy_<godzina>.vd` i powie, co zrobić.
- „Wykryj automatycznie" nie znalazł folderu → wskaż go ręcznie (**Wybierz…**); najedź na **?** przy polu, żeby zobaczyć, czego program w nim szuka.
- Brak modułu (`numpy`, `PIL`, `scipy`) → **Start** pokaże przycisk instalacji. Ręcznie: `python -m pip install numpy pillow scipy` (w `.venv` toolkitu, jeśli go używasz).
- Toolkit ma starą wersję skryptów → rozpakuj paczkę Levy'ego v2 z nadpisaniem.
- Inny błąd → **Szczegóły ▸** na dole strony i wklej treść osobie, która pomaga.
- Przycisk **Wybierz…** nic nie otwiera (Linux) → `sudo apt install python3-tk` albo wpisz ścieżkę ręcznie.

> **Ścieżki:** wszystkie ścieżki w dalszej części tego README (`C:\Nelderim\...`) to tylko przykłady –
> użyj własnych. `CLAUDE.md` opisuje układ folderów autora (dysk `F:`); na innym komputerze Claude Code
> zapyta Cię o ścieżki.

### English summary
One app, **Nelderim Lab** (`Nelderim.exe`, `run_nelderim.bat`, `./run_nelderim.sh` or `python nelderim.py`): a local
web UI (127.0.0.1 only) that merges the hub and the pipeline: 3D Fit Lab (no Blender), Levy's 2D methods, gumps,
`.vd` packing and viewing, and client patching from a JSON recipe (dry run first). Folders are asked on first run
and stored in `~/.nelderim_hub.json`. The Windows exe (no Python needed; it also runs Levy's toolkit
scripts) is published on GitHub Releases as `Nelderim-windows.zip` by the `build-exe` workflow, or built with
`build_exe.bat`. Folders are auto-detected by content on any drive. Always work on a COPY of the client.

## Requirements

- Python 3.10+ (tested on the Windows client install)
- Pillow + numpy (`pip install -r requirements.txt`)
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
python nelderim.py
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
| `nelderim.py` | The one entry point: starts Nelderim Lab (`nelderim_app.py` server + `app/` web UI); `--classic` opens the older Tk hub. |
| `nelderim_app.py`, `app/` | Local web app (stdlib HTTP server on 127.0.0.1, three.js vendored in `app/vendor`, MIT). Only builds commands and calls the tools; no format logic. |
| `nelderim_hub.py` | Command builders for Levy's toolkit scripts and the pipeline tools (shared by the app and the Tk hub). |
| `uo3d/`, `uo3d_py.py` | 3D renderer without Blender (numpy + Pillow): glTF/FBX/OBJ, skinning, UO camera, `.vd` writer. |
| `nelderim_gui.py` | Older Tkinter recipe front-end. No format logic - only builds a recipe and shells out to the CLI tools above. |
| `uopatch.py` | Wearable/item patcher: art, gump (MUL side), tiledata, optional `mobtypes.txt`/`body.def` entries. |
| `uop_gump_patch.py` | Patches a gump directly inside `gumpartLegacyMUL.uop` in place, for items whose gump id already lives there. |
| `vd_inject.py` | Imports a `.vd` monster-animation container into `anim.mul`/`anim.idx`, auto-picking (or taking) a target body id. |
| `anim_wire.py` | Finds animations in anim2..5.mul that no body uses yet (diff against Bodyconv.def) and wires them: free body id clean on all collision sources, Bodyconv.def + mobtypes.txt entries written to `--out` (dry run by default). |
| `uop_probe.py` | Thin compatibility shim - re-exports `uop_hash`/`read_uop_hashes` from `nelderim_core` under the name the other tools optionally import. Keep it alongside the other tools **in the client folder** so the `AnimationFrame*.uop` collision check is never silently skipped. |
| `run_nelderim.bat` / `run_nelderim.sh` | Idiot-proof launchers for Windows / Linux+macOS - check Python/Pillow/numpy, install what's missing, launch Nelderim Lab, and never let the window vanish before an error can be read. |
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
