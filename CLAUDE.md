# CLAUDE.md — Nelderim Asset Pipeline + SpriteMotion

## Ścieżki

Poniższe ścieżki to **lokalny laptop właściciela** (Windows, dysk F:). Na innym urządzeniu (inny komputer, chmura, Linux) NIE zakładaj ich: na początku sesji sprawdź, czy istnieją. Jeśli nie — zapytaj użytkownika o każdą potrzebną ścieżkę (klient UO, pipeline, toolkit, vdtool, ServUO, wyjście) i użyj podanych. Nie zgaduj i nie twórz własnych. W komendach poniżej podmień `F:\...` na ścieżki użytkownika.

| Co | Ścieżka |
|---|---|
| Klient UO (`anim*.idx/mul`, `*.uop`, `Body.def`, `Bodyconv.def`, `Equipconv.def`, `tiledata.mul`) | `F:\Nelderim` |
| Ten pipeline | `F:\nelderim-asset-pipeline\nelderim-asset-pipeline` |
| SpriteMotion-UO-Toolkit (+ nakładka Levy'ego) | `F:\SpriteMotion-UO-Toolkit\SpriteMotion-UO-Toolkit` |
| ServUO (C#) | `F:\ServUO-master\ServUO-master` |
| vdtool | `F:\vdtool\vdtool` |
| UO Fiddler | `F:\UO Fiddler\UOFiddler-4.24.0` |
| Wyjście | `F:\OUTPUT FIDDLERA` |

## Instalacja

SpriteMotion (Python 3.10+), w `F:\SpriteMotion-UO-Toolkit\SpriteMotion-UO-Toolkit` (tam gdzie `pyproject.toml`):
```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
python -m pip install scipy
```
Nakładkę (aktualnie v2: `SpriteMotion_skrypty_Nelderim_1.zip`) rozpakować w root toolkitu z nadpisaniem.
Blender i Godot instalowane osobno.

Pipeline:
```
cd /d F:\nelderim-asset-pipeline\nelderim-asset-pipeline
python -m pip install -r requirements.txt
```
Układ: `nelderim.py` (wejście), `app/` (UI), `lab/` (serwer + `cmd_*`), `pipeline/` (narzędzia klienta: `nelderim_core`, `nelderim_patch`, `nelderim_search`, `uopatch`, `uop_gump_patch`, `uop_probe`, `vd_inject`, `anim_wire`), `uo3d/` (3D + `cli_render.py`, `cli_vd2glb.py`), `tests/` (pytest, sztuczny klient), `docs/PIPELINE.md` (szczegóły techniczne). `uop_probe.py` leży w `pipeline/` obok skryptów; `vd_inject.py` korzysta z `nelderim_core` (nie szuka już `uop_probe.py` w folderze klienta).

## Nakładka Levy'ego (`SpriteMotion_skrypty_Nelderim`) — przeczytać przed pracą nad animacjami

Pliki (względem `F:\SpriteMotion-UO-Toolkit\SpriteMotion-UO-Toolkit`):
- `games/ultima-online/region-masks/uo.py` — `UOReader`: dekoder MUL, obsługa `Bodyconv.def` → `anim2..5.mul`.
- `games/ultima-online/outfit-lab/build.py` — zestaw z arkusza wzorów (`--config`).
- `games/ultima-online/outfit-lab/build_item.py` — jeden przedmiot (`--graphic`, `--hide-labels`).
- `games/ultima-online/outfit-lab/atlas_to_vd.py` — atlas → `.vd` (`--body`, `--outline`, `--original` = round-trip).
- `games/ultima-online/outfit-lab/uo_vd_writer.py`, `vd.py` — zapis/odczyt `.vd`.
- `games/ultima-online/outfit-lab/verify.py`, `viewer.js` — walidacja, podgląd.
- `games/ultima-online/outfit-lab/make_gump.py` — gump paperdolla (v2). `build_spartan.py`, `build_tracksuit.py` — wzorce (hełm z widokami, łańcuch).
- `docs/NELDERIM_PRZEDMIOTY_INSTRUKCJA.md` — pełna instrukcja Levy'ego (v2 paczki; ma pierwszeństwo nad skrótem poniżej).
- `tools/vd/mul2vd.py` — wyciąg animacji z `anim.mul` do `.vd`.
- `tools/vd/vdtool.py` — `info | extract | pack | verify` dla `.vd`.
- `workspace/ultima-online/witcher-lab/` — przykład (`witcher.json`, wzór, miecz).

Env: `$env:SPRITEMOTION_UO_SOURCE = "F:\Nelderim"` (PowerShell, raz na okno).

Komendy (root toolkitu, jedna linia każda):
```
python games/ultima-online/outfit-lab/build.py --out workspace/ultima-online/witcher-lab/lab --design workspace/ultima-online/witcher-lab/witcher_design.png --lightsaber workspace/ultima-online/witcher-lab/witcher_sword.png --config workspace/ultima-online/witcher-lab/witcher.json --actions 0 4 9 16
python -m http.server 8772 --bind 127.0.0.1 --directory workspace/ultima-online/witcher-lab/lab
python games/ultima-online/outfit-lab/build_item.py --source "F:\Nelderim" --graphic 0x2684 --design szata.png --out workspace/ultima-online/moja-szata --key szata --title "Moja szata"
python tools/vd/mul2vd.py "F:\Nelderim\anim.idx" "F:\Nelderim\anim.mul" workspace/ultima-online/vd 970
python games/ultima-online/outfit-lab/atlas_to_vd.py workspace/ultima-online/moja-szata szata workspace/ultima-online/vd/anim_0970.vd workspace/ultima-online/vd/nowa_0970.vd
```
Broń: dodaj `--body workspace/ultima-online/vd/anim_0400.vd --outline 1`.
Import: UOFiddler → Animations → Animation Edit → Import from VD → Save. Tylko na KOPII klienta.

Fakty techniczne z kodu nakładki:
- Tylko body 400 (męski człowiek). Maski regionów: `workspace/ultima-online/region-audit/all-actions-region-pass/frames/aXX_dF_fYY_region_ids.png` (z toolkitu). Region 1 = twarz, 5 = dłonie (`--hide-labels 1 5`).
- Kierunki zapisane 0..4 = widoki 3..7 (SE..NW); widoki 0..2 = lustro 6,5,4.
- Atlas: komórka 256×256, kotwica (128,192); wiersze: body, maska, potem (UO, New) na przedmiot.
- Wzór: PNG z alfą, siatka 4×3, kolejność komórek w `cells`. Miecz: osobny PNG, poziomo, rękojeść z lewej.
- `animId` z `tiledata.mul` (offset +14), przekierowanie przez `Equipconv.def` dla body 400.
- `UOReader` wymaga 64-bit `tiledata.mul` (3188736 B). `static_art` czyta `artidx.mul/art.mul` (nie UOP).
- `UOReader` NIE czyta `AnimationFrame*.uop`; body z `Body.def` odrzuca jako nieobsługiwane.
- `mul2vd.py` czyta tylko `anim.mul`. Animacje z `anim2..5` (np. 420 Cloth Hood → anim4, 422 plecak → anim3) wyciągać UOFiddlerem.
- Layout rekordów `anim2..5` (`UOReader._base`): anim2: `<200: b*110`, else `22000+(b-200)*65`; anim3: `<300: b*65`, `<400: 33000+(b-300)*110`, else `35000+(b-400)*175`; anim4/5: jak anim.mul.
- Kolor 15-bit: `0x0000` = przezroczysty → zamieniany na `0x0001`. Alfa progowana na 128.
- Liczba akcji wg typu `.vd`: 0 high = 22, 1 low = 13, 2 people = 35.

## Algorytm zadania (animacja / nowy asset)

1. Przeczytaj nakładkę Levy'ego (wyżej) — reguły konwersji, rig, klipy.
2. Wolne ID / kolizje:
   `python nelderim.py search --client "F:\Nelderim" --item "<nazwa_lub_id>"` (albo `--anim N` / `--body N`)
   Sprawdź `body.def`, `Bodyconv.def`, `AnimationFrame*.uop`, `gump.def`, `art.def`, `mobtypes.txt`.
3. Klatki: SpriteMotion / outfit-lab → `.vd` (`atlas_to_vd.py` lub `vdtool.py pack`). Zawsze PNG (BMP gubi alfę).
4. Dry-run:
   `python nelderim.py patch --client "F:\Nelderim" --recipe "<receptura.json>" --out "F:\OUTPUT FIDDLERA"`
5. Raport wyniku + `WARN`. Pytaj przy niejasnościach. `--apply` tylko po wyraźnej zgodzie.
6. Zmiany serwerowe → C# w `F:\ServUO-master\ServUO-master`.

## Landmines

- Zero halucynacji: ID, ścieżki, formaty tylko z plików na dysku lub kodu ClassicUO/ServUO.
- UOP > MUL: zapis do `.mul` zasobu istniejącego w `.uop` (np. `gumpartLegacyMUL.uop`) klient ignoruje → `uop_gump_patch.py`.
- Kolejność rozwiązywania: `body.def` → `AnimationFrame*.uop` → `Bodyconv.def` → `anim.mul`.
- `AnimationFrame*.uop`: jeden plik na body na AKCJĘ (grupy 0–99), nie na kierunek. Sprawdzanie tylko 0–4 przepuściło body 32 (smok z UOP w grze). `nelderim_core.animframe_uop_bodies`, `vd_inject.py`, `uopatch.py`, `anim_wire.py` sprawdzają 0–99.
- Offsety w `anim.mul`:
  - People (≥400): `(graphic - 400) * 175 + 35000`
  - High (<200): `graphic * 110`
  - Low (200–399): `22000 + (graphic - 200) * 65`
- Nie edytuj ręcznie plików generowanych.
- Licencja MIT toolkitu nie daje praw do grafik gry; zachowaj `ASSET-SCOPE.md`, `LICENSE`.
- SpriteMotion: 1680 póz szacowanych ≠ zatwierdzonych. Zatwierdzonych 6 (akcja 22, SE).

## Podgląd `.vd` — `F:\anim_browser\anim_browser`

`vd-viewer.html` (VD Animation Viewer): jeden plik HTML, otwierany w przeglądarce, offline (poza fontami Google). Używać do sprawdzania `.vd` po `atlas_to_vd.py` / `vdtool.py pack` / `mul2vd.py`.
- Przeciągnij `.vd` na okno → warstwa. Wiele warstw naraz (np. ciało `anim_0400.vd` + nowy przedmiot); góra listy = wierzch, przesuwanie myszą lub offset w px.
- Akcje i kierunki jak w `.vd`; podgląd klatek, odtwarzanie.
- Kolory: oryginał / tint / UO hue (wczytaj `hues.mul` z `F:\Nelderim`), tylko szare piksele (hue częściowy), edycja palety (przemalowanie koloru we wszystkich klatkach modelu).
- Parser: kolor 15-bit (1-5-5-5), paleta 256, ten sam format co `vdtool.py`.

## Nelderim Lab (hub + pipeline w jednym)

Jedno wejście: `nelderim.py` (`run_nelderim.bat/.sh`, `Nelderim.exe`). Narzędzia z linii poleceń: `nelderim.py search|patch|inject|wire|uopatch|gumppatch|uo3d|vd2glb …` (= odpowiednie skrypty `.py`, które nadal działają też bezpośrednio). Stare okna Tk (`nelderim_gui.py`, `nelderim_hub_ui.py`, `--classic`) usunięte; skrypty pipeline'u leżą zawsze obok programu (bez ustawienia „pipeline”); ustawienia: klient, toolkit, wyjście, UO_Body_0x190.glb. Uruchamia `lab/nelderim_app.py`: serwer stdlib na 127.0.0.1 (port 8774+) i UI w przeglądarce (`app/index.html`, `app/app.js`, `app/style.css`; three.js 0.160 w `app/vendor`, MIT). Styl ciemny „Fit Lab": lewa lista stron i prac, środek widok 3D + pasek (akcja, kierunki 0–7, klatka, Play, kamera UO) + podglądy na żywo z „poke px", prawy panel (historia Cofnij/Ponów, Slot fit: offset/rotate/skala, opcje, Mierz, Zbuduj .vd, Zapisz/Reset). Pozostałe strony: Ubranie 2D, Broń 2D, Gump, Spakuj do .vd, Zestaw, Podgląd .vd, Dodawanie do klienta (receptura, szukanie, wolne ID, na sucho / zastosuj z potwierdzeniem), Ustawienia, Pomoc.
- `lab/nelderim_hub.py`: logika i budowniczowie komend `cmd_*` (wspólne z UI), ścieżki w `~/.nelderim_hub.json`. Zmieniając argumenty skryptów Levy'ego, popraw `cmd_*`.
- `lab/nelderim_app.py`: zadania (`task()` → Job z krokami-podprocesami, log w `/api/job`), sesja 3D (`M3D`: `/api/m3d/load|static|pose|preview|measure|save`), podgląd `.vd` (`/api/vd/*`). Bez logiki formatów.
- Tryby pomocnicze `nelderim.py` (też w exe): `--run-script PLIK.py`, `--py [-c KOD | SKRYPT.py]` (exe udaje `python` dla skryptów Levy'ego: potrzebują tylko numpy + Pillow + stdlib), `--uo3d`, `--pick`, `--deps-ok`.
- Python dla toolkitu (`toolkit_argv`): `.venv` toolkitu → systemowy Python z numpy+Pillow (pomija atrapę WindowsApps) → exe `--py`.
- „Wykryj automatycznie” (`scan_paths`): Pulpit/Pobrane/Dokumenty, folder obok programu, wszystkie dyski, do 4 poziomów; rozpoznaje po zawartości (`_MARKS`), max ~8 s.
- Kopiowanie `.vd`: `safe_copy` (ten sam plik → nic; WinError 32 → ponawia ~6 s, potem zapis jako `<nazwa>_nowy_<czas>.vd`).
- Prace 3D: `<toolkit>/workspace/ultima-online/<nazwa>/model3d/` (bez toolkitu: `<wyjście>/prace3d/`), `work.json` + 3 poprzednie wersje w `history/`.
- Exe: `build_exe.bat` (PyInstaller, konsola) → `dist\Nelderim\` (exe + `app/`, `uo3d/`, skrypty); CI `build-exe`: smoke test exe, artefakt `Nelderim-windows`, Release (`main` → tag `najnowsza`, latest; inna gałąź przy ręcznym uruchomieniu → prerelease `test-<gałąź>`). Link: `releases/latest/download/Nelderim-windows.zip`.

## Nieprzypisane animacje anim2–5.mul → Bodyconv.def + mobtypes.txt (`anim_wire.py`)

`python nelderim.py wire --client <KOPIA> --file 5 [--slots 32 33] [--names '{"32":"Smok"}'] [--range lo-hi] [--out DIR] [--apply] [--json]`; w aplikacji: Dodawanie do klienta → krok 4 (miniatury, nazwy, „Podepnij zaznaczone”).
- Sloty z danymi wg układu `UOReader._base` (wyżej); typ z grupy: 110 → MONSTER, 65 → ANIMAL, 175 → HUMAN.
- „Nieprzypisany” = żadna niezakomentowana linia `Bodyconv.def` nie wskazuje go w kolumnie animN (kolumny: body, anim2, anim3, anim4, anim5).
- Wolne body: nie w body.def / Bodyconv.def / mobtypes.txt / AnimationFrame*.uop (akcje 0–99, nie tylko 0–4) / AnimationSequence.uop (pierwszy uint32 wpisu = animId, zlib przy flag 1), nie `animId` w tiledata.mul ani w Equipconv.def, ≠ 0, pusty zakres w anim.mul; najpierw pasmo typu (MONSTER 1–199, ANIMAL 200–399, HUMAN 400+), poza nim tylko powyżej najwyższego id w mobtypes.txt (model `AnimIdx` się nie przesuwa).
- Zapis tylko do `--out` (w aplikacji `<wyjście>/anim_wire`): kopia + blok `# --- added by anim_wire.py ---` w Bodyconv.def (`body -1 -1 -1 slot -1 # opis`) i mobtypes.txt (`body TYP 0`), backup, manifest, weryfikacja ponownym odczytem.
- `--check-body N` (w aplikacji „🩺 Sprawdź”): co już używa body N. Lekcja z gry: body 32 przypięte do anim5 slot 196 (wilkołak) pokazało smoka z UOP — UOP ma pierwszeństwo, a stara wersja sprawdzała w UOP tylko akcje 0–4.
- NIESPRAWDZONE w grze: wcześniej Bodyconv.def był tylko do odczytu (`nelderim_core`); przed hurtowym podpinaniem sprawdzić jedno body. Testowane na sztucznym kliencie (`tests/`) i w grze (wilkołak, anim5 slot 196, po poprawce UOP).

## Przedmioty i broń — instrukcja Levy'ego (NELDERIM_PRZEDMIOTY_INSTRUKCJA)

Sprawdzone na: szabla 0xF5E→618, BlackStaff 0xDF0→617, Hooded Shroud 0x2684→970, kusza 0x13FD→616, rękawice 0x1414→530, ClothHood 0xA706→420 (anim4), plecak 0xE75→422 (anim3).

Zasady: odpowiedzi po polsku, krótko. Przed wyborem „której starej wersji" zapytaj. Zawsze backup poprzedniego `.vd` przed nadpisaniem (`..._BACKUP_opis.vd`; hub robi to sam). Klient = KOPIA, oryginału nie ruszać. Wyniki w `workspace/ultima-online/<praca>/`. Body 401 i stwory: brak masek, nieobsługiwane.

1. **Animacja przedmiotu**: ItemID → `tiledata` (`animId`, `layer`, `label`) → `Equipconv.def` (`400 <id> <conv> <gump> <hue>`) → `Bodyconv.def`. Hub: Viewers/tools → „Look up animation". Animacje tylko w `.uop` nieobsługiwane.
2. **Metoda**: ubranie/szata/pancerz (zmiana materiału) → `build_item.py` lub `build.py` (`fit_texture`). Wąska broń trzymana w dłoni (miecz, laska, włócznia) → `build.py --config` z `axisFit` (`fit_lightsaber`). Hełm z widokami → wzór `build_spartan.py`. Kusza/tarcza/łuk: ścieżka osi nietestowana.
3. **Grafika**: PNG RGBA. Białe tło wyciąć flood-fillem od krawędzi; `.webp` często ma już alfę (sprawdź `Image.mode`). Alfa: piksel = `>=128`, kadruj po `>=64`. Broń dla `axisFit`: POZIOMO, rękojeść LEWO, czubek PRAWO (obraz pionowy `build.py` obraca sam). Ubranie: front, płaskie światło. Arkusz: 4×3, pusta komórka = `Empty design`. `.vd`: bez półprzezroczystości, jedna paleta 256 (15-bit) na blok akcja+kierunek.
4. **Config JSON (UTF-8 bez BOM)**: `title`, `items` [[klucz, ItemID]], `cells`, `props`, `hide` (5 = dłonie, 1 = twarz), `drawOrder`, `defaultOff`, `exclusive`, `displayNames`, oraz dla broni: `axisFit`, `axisImages`, `axisRatio`, `axisThickness` (px, stała), `axisContinuity`, `axisTorsoRule`. PowerShell 5.1 `Set-Content -Encoding utf8` dopisuje BOM: użyj `[IO.File]::WriteAllText(path, text, (New-Object Text.UTF8Encoding($false)))`. Klucze `axis*` są w paczce v2 (`SpriteMotion_skrypty_Nelderim_1.zip`); hub sprawdza to przed budową broni. Uwaga: klucz `sword` bierze obraz z `--lightsaber` (nie z `axisImages`); `axisTorsoRule` domyślnie `true` gdy brak klucza (hub zapisuje go zawsze jawnie).
5. **Budowa**: najpierw pilot `--actions 0 4 9 13 16`, potem wszystkie 35. `verify.py` → `"errors": []`, `missingSequences: 0` (kod wyjścia 1 jest normalny, gdy piksele przedmiotu różnią się od oryginału). `--design` i `--lightsaber` wymagane nawet bez miecza (dowolne istniejące pliki; hub podstawia placeholdery).
6. **Strojenie broni**: grubość stała w px (`axisThickness`), nie % długości (oryginalna laska ≈3 px; mierz medianę szerokości wierszy i bbox na klatce idle z pionową bronią, porównaj z oryginałem). Kula skacze między końcami → `axisContinuity` + `axisTorsoRule`; sprawdź akcje 7, 10, 14, 18, 22. `--body anim_0400.vd` przycina do ciała (widoczne poza ciałem lub ≤2 px od oryginału). `--outline 1` dla cienkiej klingi; nie dodawaj, gdy obraz ma już ciemny kontur.
7. **Zapis `.vd`**: `mul2vd.py` (oryginał + ciało 400) → `atlas_to_vd.py <lab> <klucz> anim_<id>.vd <wynik>.vd --body anim_0400.vd [--outline 1]` → `vdtool.py info`. Self-check: `atlas_to_vd.py ... --original` + `vdtool verify` musi dać `OBRAZ IDENTYCZNY`. Widoki atlasu 3..7 = `dir0..dir4`; kotwica (128,192). `anim3/4/5.mul` → UOFiddler (Animation Edit → Export to VD). Import: typ pliku = typ celu (ludzie/broń: typ 2, 35 akcji).
8. **Gump paperdolla**: męski = AnimID + 50000, damski = męski + 10000 (zawsze wg formuły, nie wg Fiddlera; sprawdź `Equipconv.def` pod literalny gump). Ciało: gumpy 12 (M) i 13 (F), 260×237, RLE, RGB555, 0 = przezroczysty. Damskiego często brak w kliencie → w UOFiddlerze Insert, nie Replace. Skrypt `make_gump.py` (v2) wyciąga gump z `Gumpidx/Gumpart.mul`, dopasowuje broń do osi, przycina do ciał 12/13, zapisuje `gump_<id>_meski.png`, `gump_<id+10000>_damski.png`, `orig_<id>.png`, `porownanie.png`:
   - laska (617): `make_gump.py --client <klient> --anim 617 --image laska.png --thickness 26 --out <katalog>` (obraz poziomo, kula po prawej)
   - szabla (618): `... --anim 618 --image szabla.png --ratio 0.15 --shift 3,-9 --front-below 106 --outline --out <katalog>`
   - opcje: `--thickness` px lub `--ratio`, `--butt bottom|top|left|right` (koniec-rękojeść oryginalnego gumpu), `--shift dx,dy`, `--front-below Y`, `--outline`, `--gump-id`. Oceniaj na `porownanie.png`, przesunięcie stroj na powiększeniu dłoni. Alfa 0/1. Czyta `Gumpidx/Gumpart.mul` (nie UOP: gump w `gumpartLegacyMUL.uop` → `uop_gump_patch.py`).
9. **Przed oddaniem**: verify czysty na wszystkich akcjach; obejrzeć 35 akcji w 3 kierunkach; `vdtool info` = typ 2, 35×5, liczby klatek jak oryginał; backup; pokazać użytkownikowi podgląd HTML i zapytać o grubość/orientację.
10. **Nie sprawdzono**: import do UOFiddlera i wygląd w grze, ikona przedmiotu (art), `ItemData.csv`/`bodyTable.cfg`/skrypty C#, `.uop`.
11. **Pułapki**: pusta komórka → `Empty design`; półprzezroczysty szum w komórce → kadruj po `alfa>=64`; po zmianie `build.py` stare paczki są nieaktualne (`build.py`, `viewer.js`, `verify.py`, `uo.py`); `Remove-Item` z `C:\` w jednym poleceniu bywa blokowane.

Nelderim Lab pokrywa: lookup, budowę zestawu/przedmiotu/broni (config + placeholdery), verify, pakowanie z backupem i self-checkiem, gump paperdolla (`make_gump.py`), listę kontrolną. Nie pokrywa: `build_spartan.py`, `build_tracksuit.py` (wzorce, ścieżki zaszyte w skrypcie).

## Model 3D bez Blendera — zakładka „Model 3D" w hubie (`uo3d/cli_render.py` + pakiet `uo3d/`)

Źródło: projekt `UO_Model3D` (MakeHuman, szkielet 107 kości, 35 akcji × 5 kierunków dopasowanych do klatek oryginału). Hub NIE używa Blendera: czyta `model/UO_Body_0x190.glb` (ciało + szkielet + animacje) własnym kodem (numpy + Pillow) i renderuje kamerą UO.
Zmierzone na `body400.vd` (oryginał): kamera ortogonalna, elewacja 28,45°, 36 px/m, kotwica w świecie (0,0,0.07 m) na pikselu (128.5, 192) płótna 256×256; kierunek d=0..4 = obrót modelu o −45°·d wokół Z; klatka UO k = czas (1+3k)/24 s (24 fps, 3 klatki sceny na klatkę UO); IoU sylwetki 0,879 (zgodne z README projektu).
Liczba klatek akcji (anim 400): `[10,10,10,10,1,5,5,1,1,7,7,7,7,7,7,10,7,7,7,7,5,6,6,5,5,1,5,5,7,5,5,7,5,5,5]`; w pętlach (chód/bieg) `.glb` ma 3 klatki więcej, niebędące klatkami UO.
Moduły: `uo3d/glbmodel.py` (glTF + skinning + animacje), `uo3d/raster.py` (kamera + z-bufor numpy), `uo3d/statmesh.py` (model przedmiotu: .glb/.gltf/.obj; .fbx nieobsługiwany), `uo3d/engine.py` (dopasowanie rozmiaru z `EXTENTS`, wypchnięcie z ciała, wagi z najbliższej skóry z ograniczeniem do kości `PARTS`, łańcuchy tkaniny dla skirt/cloak/robe, światło UO 0,08+0,92·N·L, kontur, hold-out ciała), `uo3d/vdwrite.py` (zapis `.vd`, skopiowany z overlayu Levy'ego, MIT).
Rodzaje: shirt, plate, arms, pants, legs, boots, gloves, helm, robe, skirt, cloak, hair, beard, hat. CLI: `python nelderim.py uo3d --body UO_Body_0x190.glb --item model.glb --kind shirt --out DIR --name NAZWA [--actions 0 4 9] [--turn] [--scale] [--skip a,b]`.
Dodatki (dane z folderu `pipeline/` obok modelu ciała, wykrywane automatycznie): `body400.vd` → EXACT_BODY (ciało zasłania przedmiot dokładnie wzdłuż oryginalnych sylwetek; `uo3d/vdread.py`), `horse200.vd` → akcje konne 23–29 (koń z oryginalnych klatek; mapowanie 23→0 chód, 24→1 bieg, 25–29→2 stanie; część przedmiotu za osią miednicy i pod sylwetką konia jest ukrywana, heurystyka), `weapon_motion.json` → broń (`uo3d/weapons.py`: klasy weapon1h.R / polearm.L / axe2h.L / bow.L; macierz skinningu = `W_dłoń_poza @ C @ basis @ C⁻¹ @ IBM_dłoń`, basis = T(shift)·R(turn)·R_roll; model broni pionowo wzdłuż +Y, tył na dole; skala domyślna = mediana długości klasy), `uo_shield_keys.py` → tarcza (kość shield.L założona na tarczy kalibracyjnej z `uo_place_shield.py`: CENTRE/NORMAL na przedramieniu; spoczynek kości w `.blend` nie jest w `.glb`, więc położenie NIEZWERYFIKOWANE).
Tkanina: `uo3d/cloth.py` (PBD: grawitacja, więzy długości krawędzi, przyciąganie do łańcuchów GOAL=0,35, kolizje z ciałem, PREROLL, pętle ×2); włączana `--cloth` (hub: domyślnie dla szaty/spódnicy/peleryny). Wczytywanie modeli: `.glb/.gltf/.obj/.fbx` (binarny FBX: geometria, transformacje węzłów, kolor Diffuse; bez tekstur; ASCII FBX nie). Test: `UO_Body_0x190.fbx` wczytuje się do 14 517 wierzchołków / 26 756 trójkątów, jak `.glb`.
Rodzaje: shirt, plate, arms, pants, legs, boots, gloves, helm, robe, skirt, cloak, hair, beard, hat, weapon1h, polearm, axe2h, bow, shield.
`.vd` → `.glb` (`uo3d/fromvd.py`, CLI `python nelderim.py vd2glb --body --vd --out [--action 4] [--voxel 0.02] [--dilate 0] [--no-mirror]`; w aplikacji: Fit Lab „Z pliku .vd…”, Podgląd .vd „Przymierz w 3D”): ciało w pozie akcji 4 klatka 0; bryła z sylwetek (wizualny kadłub) z kierunków 0–4 + lustrzanych 5–7 (= odbicie 3,2,1 wokół kolumny 128); woksel zostaje, gdy trafia w piksel przedmiotu ALBO zasłania go ciało; wnętrze ciała usuwane; potrzebny co najmniej jeden widok, który go naprawdę widzi; małe wyspy (<2%) usuwane; powierzchnia wokseli → wygładzanie Taubina; kolory z klatek z podzielonym światłem UO; powrót do pozy spoczynkowej odwrotnym skinningiem najbliższego wierzchołka ciała; zapis `.glb` z `asset.extras.uo3d_rest = true` (Item pomija wtedy automatyczne skalowanie/położenie) i `COLOR_0` (statmesh czyta, shade mnoży). Test pętli (render własnego silnika → `.glb` → render): IoU sylwetek 0,75–0,91 (akcje 4, 0, 9, 16). Na prawdziwych `.vd` z klienta NIESPRAWDZONE (rejestracja ciała IoU 0,879).
Ograniczenia: nie porównano z żadnym prawdziwym przedmiotem z klienta ani z wynikiem Blendera; broń/tarcza/koń/tkanina sprawdzone tylko wizualnie na syntetycznych kształtach (pudełko, tuba, skorupa z ciała); nie importowano do UOFiddlera/gry.
