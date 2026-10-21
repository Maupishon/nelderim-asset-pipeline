# UO_Model3D v13.5 — co z niego weźmiemy (notatka do przyszłych sesji)

Źródło: <https://github.com/Kserian/UO_Model3D> (main `b212cee`, 2026-10-20), wydanie
[UO3DMv13.5](https://github.com/Kserian/UO_Model3D/releases/tag/UO3DMv13.5). Przejrzane 2026-10-21. Nic z tego nie jest jeszcze w repo.
Wydanie 13.5: ciało bez zmian; nowości to szaty/tkanina (presety tkanin), opcje renderu (kontrast, cienie styku), QA, dokumentacja.

## Najpierw: licencja i dane

- **W repo nie ma pliku LICENSE** (= domyślnie wszystkie prawa zastrzeżone). Siatka ciała MakeHuman jest CC0, ale skrypty nie mają licencji.
  README zabrania rozpowszechniania `.blend` i plików klienta. Przed kopiowaniem kodu: zapytać autora (Kserian/Levy) o licencję
  albo przenosić tylko pomysły i zmierzone liczby, pisząc własny kod.
- W repo są **oryginalne klatki klienta** (`client/`, `pipeline/body400.vd`, `horse200.vd`, `pipeline/body13/mul/*.vd`,
  `UO_Original_Atlas.png`). Nigdy nie kopiować ich do naszego repo.
- `.glb`/`.fbx` nie ma w repo; robi je `pipeline/export.py --blend model/UO_Body_0x190.blend` (bpy 4.2).

## Co się zmieniło względem tego, czego używa nasz `uo3d`

| | nasz opis w `CLAUDE.md` | v13.5 |
|---|---|---|
| Szkielet | „107 kości” (stary opis) | 54 kości: 19 UO + 30 palców + 5 kości broni/tarczy (`weapon1h.R`, `polearm.L`, `axe2h.L`, `bow.L`, `shield.L`) z kluczami we wszystkich 35 akcjach |
| Pozy | dopasowane do sylwetek | dodatkowo „naturalny ruch” (`pose_natural_fit.py`), IoU czystego modelu **0,899** (było 0,879) |
| Grubość kończyn | — | skala X/Z na kość na klatkę (`upper_arm`, `forearm`, `hand`, `thigh`, `shin`, `foot`, `head`), **Inherit Scale = None** na forearm/hand/shin/foot |
| Kotwica/kamera | 256×256, (128,192), 28,45°, 36 px/m | to samo |

Nazwy kości pasują do naszego `engine.PARTS`. **Ryzyko:** glTF nie zna „Inherit Scale = None”; nasz `glbmodel.py` mnoży skalę rodzica
w dół drzewa. Po eksporcie v13.5 sprawdzić IoU sylwetki (powinno być ~0,899). Jeśli wyjdzie gorzej: liczyć jak `pose_lib.py`
(macierz kości = macierz rodzica bez skali przy Inherit Scale = None @ offset @ T·R·S).

## Lista: co możemy wykorzystać

### Model i szkielet
1. **Nowe ciało v13.5 do `uo3d`**: eksport `.glb` → ustawienie „UO_Body_0x190.glb”. Lepsze pozy i kości broni. Potem test pętli i IoU.
2. **`pose_lib.py`**: rig w numpy (FK + LBS jak w Blenderze + raster pokrycia), „pixel-identical” z Blenderem. Eksport `npz` (spoczynek,
   wagi, trójkąty, kamera, klucze 35 akcji). Wzorzec do poprawki skali w `glbmodel.py` i do testów naszego skinningu.
3. **Kości broni z kluczami** zamiast naszej `weapon_motion.json` + macierzy: błąd 0,6–2,1 px względem 13 oryginalnych broni.
   Rodzaje: `weapon1h`, `polearm`, `axe2h`, `bow`/`crossbow`, `shield`, `quiver` (sztywno na `chest`), `weapon.L` (np. róg, latarnia
   w lewej ręce, lustrzany chwyt; przepis `model/items/horn/`).

### Wiązanie i dopasowanie (zasady do przeniesienia do `engine.py`)
4. **Tabela `PART` z `uo_bind_item.py`** (README §3): `chest`, `torso`, `shoulders`, `arms`, `gloves`, `legs`, `boots`, `helm`, `hood`,
   `neck`, `all`, `cloak`, `robe`/`skirt`, `hair`/`beard`/`hat`, broń. **BIND FOLD**: część wagi kończyny przechodzi na rodzica
   (hand→forearm→upper_arm→chest, foot→shin→thigh→pelvis, head→neck), np. `"thigh": (0.3, 0.1, 0.4)` = 30% przy biodrze, rampa wzdłuż kości.
   `MAP "under"`: skóra wzdłuż normalnej wierzchołka; `SMOOTH = 4` przejścia uśredniania.
5. **Dopasowanie**: `MIN_GAP` 15 mm (wypychanie z promieniem `RADIUS` 4 cm), `uo_conform_item.py` (rękawy na osie ramion, owinięcie
   1,5 cm od skóry, render trzyma 8 mm), `uo_autofit_item.py` (skala i położenie z kształtu skóry slotu, wymaga scipy),
   `uo_densify_item.py` (krawędź 2 cm rękawice, 3–5 cm reszta). U nas dopasowanie jest prostsze (`EXTENTS` + wypchnięcie).
6. **Cienkie części znikają przy 36 px/m**: `widen` 7 cm (paski), `skin_wrap` 8 mm, `thicken` 8,5 cm (pochwa z boku).
7. **Kaptur**: `uo_hood_cover.py` (kaptur na czaszkę, kołnierz na barki). U nas jest 2D `hood_blend.py`; to wersja 3D.
8. **Peleryna**: `cloak_pitch.json` = odchylenie peleryny do tyłu wokół barków na akcję, zmierzone na oryginale 468. Gotowe dane do `cloth.py`.

### Render (tani post-processing w numpy, do `engine.py`)
9. **Zasłanianie przez ciało**: `HOLDOUT_MARGIN` 1 cm; zasłaniają tylko ręce, dłonie, głowa i nogi, **nigdy tułów**; części, do których
   przedmiot jest przypięty, nie zasłaniają go (`OWN_PARTS_NEVER_HIDE`); `FILL_HOLES` 4 px; `MIN_PIECE` 8 px (zostaje największy
   kawałek); `BODY_GAP` 6 mm na klatkę.
10. **Kontrast** `uo_contrast` (k 1,5, środek 0,49): rozrzut jasności szaty 31 → 45–52 (oryginał 469: 54). Domyślnie dla robe/skirt.
11. **Cienie styku** `uo_shade_sleeve` 0,4 / `uo_shade_width` 4 px (rękaw–tułów), `uo_shade_body` (dłonie, ramiona, głowa).
12. **Pozostałe opcje**: `uo_edge_floor` 24 (bez czarnej obwódki na czarnym przedmiocie), `uo_hide_erode` 1 (mniej dziur przy mankietach
    i kołnierzu), `uo_legs_under` 1 (długa szata), `uo_cloth_lie` 1,0 (upadki 21/22: szata leży wzdłuż nóg), kontur 0,38 (szare szaty 0,6–0,8).
13. **Materiały**: kolor → światło UO, alfa ≥ 0,5 = piksel, **odblask metalu** zmierzony na płytach i hełmach (bez niego metal ~55/255
    za ciemny), `SATURATION = 0` = szary przedmiot do farbowania. `uo_hue_preview.py`, `uo_grey_metal.py`: podgląd hue
    (klient indeksuje 32 kolory hue kanałem czerwonym; z flagą PartialHue `0x00040000` tylko szare piksele).

### Szaty i tkanina
14. **`cloth_lib.py`** (numpy, bez Blendera): nogi jako kapsuły, wypychanie + więzy długości krawędzi, pas przypięty, osobno na każdą klatkę
    (bez skoków). IoU dołu szaty względem oryginału 469: 0,641 → 0,757. Do porównania z naszym PBD `cloth.py`.
15. **Presety tkanin** (masa / zginanie / tłumienie): silk 0,15/0,05/1, cotton 0,3/0,5/5, wool 0,5/2/10; sztywność w płaszczyźnie 5;
    margines kolizji 2 cm (0,6 cm przepuszcza nogi). Ustawienia „t1” dla siatki 24k (README §3a).
16. Znane braki szat: nogi widać w upadkach, dół ok. 1,7× szerszy niż oryginał 469, rękawy ok. 10% grubsze.

### Gump paperdolla i ikona z 3D (to, nad czym pracuje Monkey na Discordzie)
17. **`uo_render_paperdoll.py`**: gump 260×237 z przodu, **90,5 px/m**, czubek głowy y 54 … stopy y 221 (1,855 m), oś ciała x 94,5;
    ciało w pozie spoczynkowej zasłania tył paska. Ikona: przedmiot z góry pod 45°, w 44×32 px. Liczby gotowe do `uo3d/icon.py` i gumpów.
18. **`uo_render_gump_fit.py`**: gump szaty (M/K) dopasowany do oryginalnego gumpu tego rodzaju (50469/60469): ramiona ustawione jak na
    narysowanych ciałach 12/13 (ręce na boki, łokcie zgięte), skala x/y do sylwetki oryginału, szarość dopasowana do poziomów oryginału
    (p5/p50/p95), złote części zachowują kolor. U nas gump z 2D (`anim_art.py`, `make_gump.py`); to droga z 3D.
19. **`uo_render_weapon_gump.py`**: gump broni (męski 50000+AnimID; **damskiego broń w kliencie nie ma**), trzonek na linii x 47,5 jak
    gumpy 50631/50642/50633, pięść y 114 (damska ~1,5 px wyżej); ikona broni po przekątnej, **druga ikona = lustro** (para jak 0xF5C/0xF5D);
    metal szary, drewno brązowe (do PartialHue).
20. **`uo_render_gump_ragged.py`**: gump podartej szaty (dziury przezroczyste, kaptur na plecach).
21. **`docs/paperdoll/`**: obrysy ciał gumpów 12/13 (męskie, damskie): referencja do dopasowań.

### Kontrola jakości (do aplikacji jako „🩺 Sprawdź”)
22. **`item_body_holes.py`**: dziury, przez które klient pokaże ORYGINALNE ciało 400 pod przedmiotem, z podziałem na części
    (dłoń/głowa OK, noga/bark = błąd). Najbardziej przydatny test dla szat.
23. **`item_skin_check.py`** (skóra przez przedmiot, stopy), **`item_qa.py`** (wierzchołki w ciele w ruchu, grubość),
    **`item_clearance.py`**, **`item_gif.py`/`item_sheet.py`** (arkusz + GIF na oryginalnym ciele, auto-kadr).
24. **`docs/qa/baselines.md`**: progi i wyniki (test_items 0,723; ciało 0,899; autofit 13,6 mm; szata 0,757; peleryna 0,507).

### Dane i narzędzia klienta
25. **`extract_tiledata.py`**: przedmioty do noszenia + animacja + warstwa + `Bodyconv.def` (w którym animN leży) + zasięg. Układ
    tiledata „High Seas” (0x4000 × 30 B, 0x10000 × 41 B, 4 B nagłówka na 32). Porównać z `nelderim_core`.
26. **`uo_gump_art.py`**: odczyt/zapis gumpów i artów MUL (mamy własne w `nelderim_core`/`uopatch`, do porównania).
27. **`measure_equipment_extent.py`, `layer_analysis.json`** (385 oryginalnych animacji, akcja 4): statystyki slotów; plan
    `docs/plans/original_items_calibration.md` (priory per slot ze wszystkich oryginałów, bez poprawek per klatka).
28. **`uo_make_item.py`** (bez okna Blendera, `bpy==4.2`): GLB + przepis JSON → `item.blend` + `preview.png` (`--preview`) lub
    35 akcji → `clothing.vd` (`--vd`, 15–30 min CPU). Można podpiąć w aplikacji jak most do Content Studio (`cmd_studio_*`).

## Czego NIE bierzemy

- Oryginalnych klatek, `.vd` i `.blend` z repo (prawa do grafik gry, brak licencji).
- Zakazanych przez autora rzeczy: poprawek per klatka, strojenia replik `test_items`, zmian światła/AO/cienia na ziemi.
- Body 401: w `anim.mul` to prawie kopia męskiego; autor też nie ruszał.

## Kolejność, gdy zdecydujemy

1. Eksport v13.5 `.glb` → test IoU w `uo3d` (poprawka skali wg `pose_lib.py`, jeśli trzeba) → zmiana opisu w `CLAUDE.md` (107 → 54 kości).
2. Zasady zasłaniania i opcje renderu (pkt 9–12) w `engine.py` + test na szacie.
3. Liczby gumpu/ikony (pkt 17–19) w `icon.py` i nowym `uo3d` gumpie z 3D.
4. Test dziur na oryginalnym ciele (pkt 22) jako przycisk w aplikacji.
5. Opcjonalnie: most do `uo_make_item.py` jako trzecia droga obok `uo3d` i Content Studio.
Niesprawdzone: żaden skrypt UO_Model3D nie był tu uruchamiany (brak bpy 4.2 i klienta w tej sesji).
