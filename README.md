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

Narzędzia bez okna: `python nelderim.py search | patch | inject | wire | uo3d | vd2glb …` (albo `Nelderim.exe …`); `--help` przy każdym pokazuje opcje.

### 1. Pobranie (na dowolny komputer)
**Windows – paczka gotowa do uruchomienia:**
1. Pobierz **[Nelderim-windows.zip](https://github.com/Maupishon/nelderim-asset-pipeline/releases/latest/download/Nelderim-windows.zip)** (albo strona [Releases](https://github.com/Maupishon/nelderim-asset-pipeline/releases) → najnowsza → *Assets*). Konto GitHub nie jest potrzebne.
2. Kliknij zip prawym → **Wyodrębnij wszystkie…** (nie uruchamiaj z wnętrza zipa).
3. Wejdź do folderu `Nelderim` i uruchom **`Nelderim.exe`**. Ostrzeżenie Windows → **Więcej informacji → Uruchom mimo to** (program nie jest podpisany).
4. Trzymaj cały folder razem (`Nelderim.exe` obok folderów `app`, `lab`, `pipeline`, `uo3d`). Folder możesz przenieść gdziekolwiek, np. na pendrive.

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

## Dla twórców

- Komendy, układ folderów, format receptury, zasady bezpieczeństwa i znane pułapki formatów: [`docs/PIPELINE.md`](docs/PIPELINE.md).
- Zasady pracy z Claude Code (ścieżki, nakładka Levy'ego, model 3D): [`CLAUDE.md`](CLAUDE.md).
- Testy: `python -m pip install pytest numpy pillow && python -m pytest tests` (sztuczny klient, bez plików gry).
