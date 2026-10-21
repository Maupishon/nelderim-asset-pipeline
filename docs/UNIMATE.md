# UniMate — co z niego weźmiemy (notatka do przyszłych sesji)

Źródło: <https://github.com/Friedrich-M/UniMate> (SIGGRAPH Asia 2026, przejrzane 2026-10-20, commit HEAD z `--depth 1`).
Co to jest: model tekst → ruch dla **dowolnego szkieletu** (dwunogi, czworonogi, ptaki, ryby, owady, węże, obiekty).
Wejście: zrigowany GLB/glTF/FBX + prompt („An object walks forward.”). Wyjście: ruch (NPZ, 60 klatek) + animowany GLB/FBX.
Zrobione: punkt 1 w części renderu — `python nelderim.py creature` (`uo3d/cli_creature.py`, `uo3d/creature.py`): animowany, zeskinowany GLB
→ `.vd` typ 0/1, 5 kierunków, mapa akcji w JSON. Sprawdzone na syntetycznym modelu i na ciele UO_Body_0x190 jako „stworze”;
NIE sprawdzone na prawdziwym potworze ani w grze. Reszta to lista pomysłów.

## Licencje (sprawdzić przed użyciem)

| Co | Licencja | Wniosek |
|---|---|---|
| Kod | MIT | wolno kopiować fragmenty (zachować nagłówek licencji) |
| Wagi (checkpointy HF `Linzhan/UniMate`) | **CC BY-NC 4.0** | tylko niekomercyjnie; shard z płatnościami = problem. Nie pakować wag do exe ani repo |
| Zbiór UniML3D / Mixamo / Objaverse / Truebones | licencje źródeł; Truebones komercyjny | nie potrzebujemy zbioru do własnych modeli |

## Wymagania (dlaczego NIE w `Nelderim.exe`)

Python 3.10, PyTorch 2.5.1 + CUDA 12.4 (GPU zalecane), `bpy==4.0.0` z pip, transformers, torch-geometric, spaCy, ~kilka GB.
Etykiety kości domyślnie przez LLM (`DEEPSEEK_API_KEY` / `OPENAI_API_KEY`); bez klucza tryb `rule` (offline, deterministyczny)
albo ręcznie `--face_r/--face_l`. Wniosek: UniMate = **osobne środowisko, krok offline**; nasz program tylko czyta wynikowy GLB.

## Lista: co możemy wykorzystać

1. **Nowe potwory z modelu 3D (główny zysk).** Zrigowany GLB stwora (smok, wilk, pająk, ptak, ryba) + prompty per akcja UO
   → animowane GLB → render kamerą UO (nasz `uo3d/raster.py`, kamera 28,45°, 36 px/m, kotwica 128.5,192) → `.vd` typ 0 (High, 22 akcje)
   lub 1 (Low, 13 akcji) → `vd_inject.py` (anim.mul) albo `anim_import.py`/`anim_wire.py` (anim2–5). Dziś `uo3d` umie tylko
   body 400 + przedmiot; brakuje: renderu dowolnego skinowanego GLB w 5 kierunkach (`glbmodel.py` ma już skinning) i zapisu
   `.vd` typu 0/1 (`vdwrite.py` — sprawdzić, czy obsługuje inne typy niż 2).
2. **Tabela akcja UO → prompt** — GOTOWA: `examples/creature_prompts.json` (`python nelderim.py creature --template high|low --out mapa.json`
   zapisuje ją jako mapę akcji do `creature`). Nazwy i numery grup sprawdzone w ClassicUO (`AnimationsLoader.cs`, 2026-10-21);
   lista z pamięci, którą tu wcześniej miałem, była błędna (np. 7–9 to Misc1–3, nie ataki; 10 to Stumble, nie GetHit).
   - High (22): 0 Walk, 1 Stand, 2 Die1, 3 Die2, 4 Attack1, 5 Attack2, 6 Attack3, 7 Misc1, 8 Misc2, 9 Misc3, 10 Stumble, 11 SlapGround,
     12 Cast, 13 GetHit1, 14 Misc4, 15 GetHit2, 16 GetHit3, 17 Fidget1, 18 Fidget2, 19 Fly, 20 Land, 21 DieInFlight.
   - Low (13): 0 Walk, 1 Run, 2 Stand, 3 Eat, 4 Unknown (czujność), 5 Attack1, 6 Attack2, 7 Attack3, 8 Die1, 9 Fidget1, 10 Fidget2, 11 LieDown, 12 Die2.
   - Z kodu gry: atak potwora używa grup 4/5/6 (wg trybu), zamach „czar” grupy 12; trafienie potwora grup 15/16.
     Czego NIE sprawdzono: do czego serwer używa Misc1–4 i Unknown, oraz liczby klatek oryginałów (w tabeli są domyślne).
   - Prompty w stylu zbioru: krótkie, „An object …”, jeden ruch. Chód i bieg: **„in place”** (UO przesuwa postać sam).
3. **Pętle chodu/biegu bez szwu** — *motion in-betweening* (`--keep_frames "0,-1"`) albo *motion expansion*: wymusić, by
   pierwsza i ostatnia poza się zgadzały. Potem próbkowanie 60 klatek → liczba klatek UO (np. 10 dla Walk, ~5–8 dla ataków).
4. **Edycja ruchu z blokadą kości** (`--keep_joints`): np. zachować tułów/głowę z istniejącej animacji, przegenerować łapy.
   Przydatne do wariantów (Attack2/3 z Attack1).
5. **Łańcuch akcji** (*motion expansion*): Stand → Attack → Stand jako jeden płynny klip, pocięty na grupy UO.
6. **`rig_preprocess`** — sam w sobie użyteczny bez modelu AI: przycina pomocnicze kości, normalizuje kierunek (przód +Z,
   Y-up, średnica 2, na ziemi), mapuje nazwy kości na wspólny słownik (`Bip01_L_Thigh` → `Left Thigh`). Dla nas: pewny
   „przód” stwora = poprawne 5 kierunków UO. Uwaga konwersja osi: ich Y-up/+Z przód → nasze Z-up; skala w metrach do ustalenia
   (rozmiar stwora w px vs oryginały z klienta).
7. **`data_process/mesh_animation/animate_lbs.py`** — referencyjny LBS w NumPy (`v = Σ w·(G·bind⁻¹)·v_rest`); do porównania
   z naszym `glbmodel.py` przy błędach skinningu.
8. **`data_process/tools/character_fbx2glb.py`, `utils/fbx2glb.py`** — FBX → GLB przez bpy. Nasz `statmesh` czyta tylko binarny
   FBX bez animacji; to droga dla animowanych FBX (Mixamo itp.) → GLB, który potem czytamy.
9. **Animowane GLB z gotowymi klipami** (bez AI): `rig_preprocess --save_clips` zapisuje istniejące animacje modelu
   (np. kupiony stwór z chodem/atakiem) jako klipy — można je od razu renderować do `.vd`, UniMate tylko dorabia brakujące akcje.
10. **Nowi ludzie/NPC (People, 35 akcji)** — możliwe, ale słabe: ruch nie będzie zgodny z oryginalnymi klatkami body 400, więc
    istniejące ubrania nie będą pasować. Tylko dla osobnych body bez ekwipunku.

## Czego NIE bierzemy

- Trening, zbiór UniML3D (88 GB), napisy VLM (Qwen/Gemini), metryki — niepotrzebne do własnych stworów.
- Animacje przedmiotów na body 400 — muszą trzymać się oryginalnych klatek UO (to robi `uo3d` + UO_Model3D), UniMate generuje nowy ruch.

## Plan minimalny (gdy zdecydujemy)

1. Poza aplikacją: środowisko UniMate (GPU), `rig_preprocess` na GLB stwora, `sample` z promptami z tabeli → `run_animate_motion.sh` → GLB per akcja.
2. W repo: `uo3d/cli_creature.py` — wczytaj animowane GLB (bez body 400), skala do zadanej wysokości w px, 5 kierunków
   (obrót −45°·d), klatki wg tabeli, kontur/światło jak `engine.shade`, zapis `.vd` typ 0/1.
3. Import istniejącymi narzędziami (`vd_inject` / `anim_import` + `anim_wire`), sprawdzenie jednego body w grze.
Niesprawdzone: jakość ruchu UniMate na stworach UO, czas na CPU, zgodność skali z oryginalnymi potworami.
