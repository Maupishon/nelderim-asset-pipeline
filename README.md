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

Są dwa programy. Oba uruchamiasz dwuklikiem.

| Program | Do czego | Plik startowy |
|---|---|---|
| **Nelderim Hub** | Zmiana wyglądu ubrań i broni, gumpy, pakowanie do `.vd` – kreator krok po kroku, wszystko w jednym oknie | `run_hub.bat` (Windows) / `run_hub.sh` (Linux, macOS) albo `NelderimHub.exe` |
| **Nelderim Pipeline** | Dodawanie grafik, gumpów i animacji potworów do klienta gry (z receptury JSON) | `run_nelderim.bat` (Windows) / `run_nelderim.sh` (Linux, macOS) |

Hub ma też zakładkę „Dodawanie do klienta", która robi to samo co Pipeline, więc do zwykłej pracy wystarczy sam Hub.

### 1. Co musisz mieć
- **Python 3.10 lub nowszy** – pobierz z <https://www.python.org/downloads/>. Przy instalacji zaznacz **„Add Python to PATH"**.
- **Kopię klienta gry** (folder z plikami `anim.mul`, `tiledata.mul`, `*.def`). **Pracuj zawsze na kopii**, nigdy na jedynym egzemplarzu.
- Dla Huba dodatkowo **SpriteMotion-UO-Toolkit** z wgraną paczką skryptów Levy'ego (`SpriteMotion_skrypty_Nelderim_1.zip` rozpakowana do folderu toolkitu, z nadpisaniem plików). W folderze toolkitu warto mieć środowisko `.venv` (`python -m venv .venv`, potem `.venv\Scripts\activate` i `python -m pip install -e ".[test]"` oraz `python -m pip install scipy`).

### 2. Pobranie
Na stronie repozytorium kliknij zielony przycisk **Code → Download ZIP** i rozpakuj do dowolnego folderu. (Albo `git clone`, jeśli wiesz jak.)

### 3. Uruchomienie Huba
**Sposób A – plik `.exe` (Windows, bez instalowania czegokolwiek poza Pythonem):**
1. Wejdź w zakładkę **Actions** tego repozytorium → workflow **build-exe** → ostatni zielony przebieg → na dole pobierz **NelderimHub-windows** (to zip w zipie, rozpakuj oba).
2. Umieść `NelderimHub.exe` **w tym samym folderze co skrypty** (`nelderim_patch.py` itd. – w paczce leżą obok siebie).
3. Dwuklik `NelderimHub.exe`. Jeśli Windows ostrzeże o nieznanym wydawcy: **Więcej informacji → Uruchom mimo to** (program nie jest podpisany).

**Sposób B – bez `.exe`:** w folderze repozytorium dwuklik `run_hub.bat` (Windows) albo `./run_hub.sh` (Linux/macOS). Na Linuksie potrzebny jest jeszcze pakiet `tkinter` (`sudo apt install python3-tk`).

**Pierwsze uruchomienie:** Hub zapyta o foldery: klient UO, toolkit SpriteMotion, folder wyników (i opcjonalnie UOFiddler, ServUO, `vd-viewer.html`). Możesz kliknąć **Wykryj automatycznie** albo wskazać ręcznie – zielone „OK" oznacza poprawny folder. Ustawienia zapisują się w `~/.nelderim_hub.json` (na Windowsie w Twoim folderze użytkownika), więc na innym komputerze zapyta od nowa.

**Praca:** na ekranie **Start** wybierz zadanie (ubranie, broń, gump…) i idź po kolei od kroku 1. Każdy krok ma opis, a po najechaniu myszą na pole pojawia się podpowiedź. Najpierw buduj kilka akcji na próbę, oglądaj podgląd w przeglądarce, dopiero potem wszystkie 35. Wynik pakujesz do `.vd` i importujesz w UOFiddlerze (na kopii klienta).

Przycisk **jasny / ciemny** na górze przełącza motyw. Pełny zapis działania programu jest pod przyciskiem **Szczegóły** na dole.

### 4. Uruchomienie Nelderim Pipeline (samodzielnie)
1. Dwuklik `run_nelderim.bat` (Windows) albo `./run_nelderim.sh` (Linux/macOS).
2. Za pierwszym razem skrypt sprawdzi Pythona i sam doinstaluje bibliotekę Pillow. Gdy coś pójdzie źle, okno zostaje otwarte i wyświetla wyjaśnienie.
3. W oknie wskaż folder klienta gry, dodaj pozycje do receptury i kliknij **Dry run** (na sucho – nic nie zapisuje). Dopiero po sprawdzeniu wyniku kliknij **Apply**.

### 5. Gdy coś nie działa
- Okno się nie otwiera / „Python not found" → zainstaluj Pythona z zaznaczonym „Add Python to PATH".
- Komunikat o brakującym module (`numpy`, `PIL`, `scipy`) → Hub sam zaproponuje instalację (zgódź się). Możesz też kliknąć **Ustawienia → Zainstaluj biblioteki Pythona**. Ręcznie: `python -m pip install numpy pillow scipy` (w `.venv` toolkitu, jeśli go używasz).
- Hub pisze, że toolkit ma starą wersję skryptów → rozpakuj paczkę Levy'ego v2 do folderu toolkitu z nadpisaniem.
- Cokolwiek innego → kliknij **Szczegóły** na dole okna Huba i wklej treść błędu osobie, która Ci pomaga.

> **Ścieżki:** wszystkie ścieżki w dalszej części tego README (`C:\Nelderim\...`) to tylko przykłady –
> użyj własnych. `CLAUDE.md` opisuje układ folderów autora (dysk `F:`); na innym komputerze Claude Code
> zapyta Cię o ścieżki.

### English summary
Two entry points: **Nelderim Hub** (`run_hub.bat` / `./run_hub.sh` / `NelderimHub.exe`, all-in-one Polish wizard
UI for clothes, weapons, paperdoll gumps and `.vd` export; asks for your folders on first run and stores them in
`~/.nelderim_hub.json`) and **Nelderim Pipeline** (`run_nelderim.bat` / `./run_nelderim.sh`, patches a client
copy from a JSON recipe; dry run first). Needs Python 3.10+; the Hub also needs SpriteMotion-UO-Toolkit with
Levy's v2 overlay. The Windows exe is built by the `build-exe` GitHub Action (artifact `NelderimHub-windows`) or
locally with `build_exe.bat`. Always work on a COPY of the client.

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
| `run_nelderim.bat` / `run_nelderim.sh` | Idiot-proof launchers for Windows / Linux+macOS - check Python/Pillow/tkinter, install what's missing, launch the GUI, and never let the window vanish before an error can be read. |
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
