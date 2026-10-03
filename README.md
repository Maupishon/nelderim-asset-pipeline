# Nelderim Lab

Program do dodawania własnych animacji, ubrań, broni, gumpów i potworów do klienta **Ultima Online** serwera Nelderim
(ServUO + ClassicUO). Zastępuje ręczne grzebanie w plikach `.mul` / `.uop` / `.def`.

Działa **tylko na Twoim komputerze** (okno w przeglądarce, nic nie wysyła do internetu). Nie zmienia Twojego klienta, dopóki sam
nie skopiujesz gotowych plików.

---

## ⚠️ Trzy zasady, żeby nic nie zepsuć

1. **Pracuj zawsze na KOPII klienta** (cały folder gry skopiuj gdzieś indziej). Oryginału nie ruszaj.
2. **Najpierw „Na sucho”.** Program pokazuje, co zrobi, i niczego nie zapisuje. Dopiero potem **Zastosuj**.
3. Program **nigdy nie zapisuje do klienta**. Wyniki trafiają do folderu wyników, a Ty kopiujesz je do kopii klienta.
   Przed nadpisaniem robi kopię zapasową starych plików.

---

## 1. Uruchomienie (Windows, 3 kliknięcia)

1. Pobierz **[Nelderim-windows.zip](https://github.com/Maupishon/nelderim-asset-pipeline/releases/latest/download/Nelderim-windows.zip)**.
   Konto na GitHubie nie jest potrzebne.
2. Kliknij zip **prawym przyciskiem → Wyodrębnij wszystkie…** (nie uruchamiaj z wnętrza zipa).
3. Wejdź do folderu `Nelderim` i kliknij dwukrotnie **`Nelderim.exe`**.

Co zobaczysz:
- **Czarne okno** – to działa program. **Nie zamykaj go** podczas pracy (zamknięcie wyłącza program).
- Po chwili otworzy się **karta w przeglądarce** z napisem *Nelderim Lab*. Tam wszystko klikasz.
- Windows może ostrzec „nieznany wydawca” → **Więcej informacji → Uruchom mimo to** (program nie jest podpisany).

Python nie jest potrzebny. Cały folder `Nelderim` trzymaj razem; możesz go przenieść gdziekolwiek (np. na pendrive).

<details>
<summary>Linux / macOS albo Windows bez exe</summary>

Kliknij **Code → Download ZIP** na tej stronie, rozpakuj, a potem:
- Windows: dwukrotnie `run_nelderim.bat`
- Linux / macOS: w terminalu `./run_nelderim.sh`

Potrzebny jest Python 3.10+ (<https://www.python.org/downloads/>, przy instalacji zaznacz **„Add Python to PATH”**).
Biblioteki doinstalują się same.
</details>

---

## 2. Pierwsze uruchomienie: wskaż foldery (raz)

Wejdź w **Ustawienia** (lewe menu) i kliknij **🔍 Wykryj automatycznie**. Program sam przeszuka komputer i znajdzie foldery po zawartości
(nazwa i dysk nie mają znaczenia). Przy każdym polu ma być **zielona kropka**.

| Pole | Co to jest | Czy wymagane |
|---|---|---|
| Folder klienta UO | **Kopia** gry: folder, w którym leżą `anim.idx`, `anim.mul`, `tiledata.mul`, pliki `.def` | tak |
| Folder wyników | Gdzie program zapisuje gotowe pliki (tworzy się sam) | tak |
| Folder toolkitu SpriteMotion | Folder z narzędziami Levy'ego (do ubrań i broni z obrazka, gumpów) | tylko do metod 2D |
| `UO_Body_0x190.glb` | Model ciała 3D z projektu UO_Model3D | tylko do modelu 3D |

Czego program nie znajdzie, wskażesz przyciskiem **Wybierz…** (albo wpiszesz ścieżkę). Najedź myszą na **?**, żeby zobaczyć, czego szuka.
Ustawienia pamiętają się na tym komputerze.

---

## 3. Co chcę zrobić → gdzie kliknąć

### A. W kliencie jest animacja, ale żaden stwór jej nie używa (anim2–5.mul)
Najczęstsza sytuacja: ktoś wrzucił animację do `anim5.mul`, ale w grze jej nie widać.

1. **Dodawanie do klienta** → przewiń do **kroku 4 „Nieprzypisane animacje”**.
2. Wybierz plik (np. `anim5.mul`) → **🔍 Szukaj**. Program pokaże listę z **miniaturą**, typem i proponowanym wolnym body.
3. Zaznacz to, co chcesz, **wpisz nazwę** (np. Wilkolak, bez polskich znaków jest najbezpieczniej) → **🔗 Podepnij zaznaczone…**
4. W folderze wyników, w podfolderze `anim_wire`, pojawią się `Bodyconv.def` i `mobtypes.txt`. **Skopiuj oba do kopii klienta**
   (nadpisz) i uruchom grę.
5. **Sprawdź jedno body w grze**, np. `[set Body <numer>]` na stworzeniu. Jeśli wygląda dobrze, podpinaj resztę.

Coś wygląda inaczej niż w UOFiddlerze (np. smok zamiast wilkołaka)? Wpisz numer w **🩺 Sprawdź body**: program pokaże, co jeszcze używa
tego numeru (najczęściej pliki UOP).

### B. Mam gotowy plik `.vd` z nowym potworem
1. **Dodawanie do klienta** → krok 2: **+ Potwór (.vd)**, wybierz plik, nazwij. **Zaproponuj wolny slot** podpowie wolne body.
2. **Zapisz recepturę** → krok 3: **👁 Na sucho** → przeczytaj wynik → dopiero **✍ Zastosuj…**
3. Skopiuj pliki z folderu wyników do kopii klienta.

### C. Chcę zmienić wygląd ubrania lub broni z własnego obrazka
Zakładki **Ubranie 2D** / **Broń 2D** (wymagają toolkitu). Idziesz po kolei od kroku 1; przy każdym polu jest **?** z wyjaśnieniem.
Najpierw zbuduj kilka akcji na próbę, obejrzyj podgląd, dopiero potem wszystkie 35. Na końcu **Spakuj do .vd**.

### D. Mam model 3D przedmiotu i chcę zobaczyć, jak leży na postaci
**Model 3D (Fit Lab)**: wczytaj `.glb` / `.fbx` / `.obj`, dopasuj suwakami, **▶ Próba** → **Wszystkie**.
Nie masz modelu? Kliknij **🎞 Z pliku .vd…**: program odtworzy przybliżoną bryłę z oryginalnych klatek.

### E. Chcę tylko obejrzeć plik `.vd`
**Podgląd .vd** → wybierz plik. Pokaże 5 kierunków wybranej akcji z ciałem pod spodem.

### F. Import do gry
Gotowy `.vd` importujesz w **UOFiddlerze** (Animations → Animation Edit → Import from VD → Save), **na kopii klienta**.

---

## 4. Gdy coś nie działa

| Problem | Co zrobić |
|---|---|
| Nic się nie otwiera / karta jest pusta | Zobacz, czy czarne okno nadal działa. Jeśli nie, uruchom `Nelderim.exe` jeszcze raz |
| Przy polu jest czerwona kropka | **Wybierz…** i wskaż folder ręcznie; najedź na **?**, żeby zobaczyć, czego program tam szuka |
| „Plik jest używany przez inny proces” przy kopiowaniu | Program sam czeka kilka sekund. Gdy plik dalej jest otwarty (np. w UOFiddlerze), zapisze go pod nową nazwą `…_nowy_<godzina>.vd` |
| Brakuje bibliotek (numpy, Pillow) | Na ekranie **Start** kliknij **Zainstaluj** (tylko wersja bez exe) |
| W narzędziach 2D błąd o starej wersji skryptów | Rozpakuj paczkę Levy'ego v2 do folderu toolkitu **z nadpisaniem** |
| Przycisk **Wybierz…** nic nie robi (Linux) | `sudo apt install python3-tk` albo wpisz ścieżkę ręcznie |
| Inny błąd | Kliknij **Szczegóły ▸** na dole strony i wklej całą treść osobie, która pomaga |

---

## 5. Czego program NIE robi

- Nie zmienia klienta sam z siebie i nie modyfikuje skryptów serwera (C# w ServUO robisz osobno).
- Nie sprawdza, jak przedmiot wygląda w grze. To zawsze sprawdzasz sam (po skopiowaniu plików do kopii klienta).
- Nie obsługuje animacji leżących wyłącznie w plikach `.uop` ani body 401.

**Sprawdzone w grze:** podpinanie animacji z `anim5.mul` przez `Bodyconv.def` + `mobtypes.txt` (wilkołak).
**Jeszcze niesprawdzone w grze:** model 3D (przymiarka i `.vd` z 3D) oraz odtwarzanie 3D z `.vd`. Traktuj je jako podgląd i weryfikuj wynik.

---

## Dla twórców

- Komendy, układ folderów, format receptury, zasady bezpieczeństwa, pułapki formatów: [`docs/PIPELINE.md`](docs/PIPELINE.md)
- Zasady pracy z Claude Code (ścieżki, nakładka Levy'ego, model 3D): [`CLAUDE.md`](CLAUDE.md)
- Testy: `python -m pip install pytest numpy pillow && python -m pytest tests` (sztuczny klient, bez plików gry)
- Narzędzia z wiersza poleceń: `python nelderim.py search | patch | inject | wire | uo3d | vd2glb …` (też `Nelderim.exe …`); `--help` pokazuje opcje

<details>
<summary>English summary</summary>

**Nelderim Lab** adds custom animations, clothing, weapons, gumps and monsters to an Ultima Online client (ServUO + ClassicUO).
Download `Nelderim-windows.zip` from Releases, extract it, run `Nelderim.exe` (no Python needed), open the browser tab,
click *Ustawienia → Wykryj automatycznie*. It is a local-only web UI (127.0.0.1). Always work on a **copy** of the client;
dry run first; it never writes into the client folder (outputs go to the results folder, with backups of replaced files).
Features: unassigned `anim2..5.mul` animations wired into `Bodyconv.def`/`mobtypes.txt`, `.vd` monster injection from a recipe,
2D clothing/weapon/gump methods (SpriteMotion toolkit), a Blender-free 3D fit lab and `.vd` viewer.
Developer docs: `docs/PIPELINE.md`.
</details>
