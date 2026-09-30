# CLAUDE.md — Nelderim Asset Pipeline + SpriteMotion

## Ścieżki (Windows, dysk F:)

| Co | Ścieżka |
|---|---|
| Klient UO (`anim*.idx/mul`, `*.uop`, `Body.def`, `Bodyconv.def`, `Equipconv.def`, `tiledata.mul`) | `F:\Nelderim` |
| Ten pipeline | `F:\nelderim-asset-pipeline\nelderim-asset-pipeline` |
| SpriteMotion-UO-Toolkit (+ nakładka Levy'ego) | `F:\SpriteMotion` |
| ServUO (C#) | `F:\ServUO-master\ServUO-master` |
| vdtool | `F:\vdtool\vdtool` |
| UO Fiddler | `F:\UO Fiddler\UOFiddler-4.24.0` |
| Wyjście | `F:\OUTPUT FIDDLERA` |

## Instalacja

SpriteMotion (Python 3.10+), w `F:\SpriteMotion` (tam gdzie `pyproject.toml`):
```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
python -m pip install scipy
```
Nakładkę `SpriteMotion_skrypty_Nelderim.zip` rozpakować w root toolkitu z nadpisaniem.
Blender i Godot instalowane osobno.

Pipeline:
```
cd /d F:\nelderim-asset-pipeline\nelderim-asset-pipeline
python -m pip install -r requirements.txt
```
`uop_probe.py` musi leżeć obok skryptów (kolizje w `AnimationFrame*.uop`).

## Nakładka Levy'ego (`SpriteMotion_skrypty_Nelderim`) — przeczytać przed pracą nad animacjami

Pliki (względem `F:\SpriteMotion`):
- `games/ultima-online/region-masks/uo.py` — `UOReader`: dekoder MUL, obsługa `Bodyconv.def` → `anim2..5.mul`.
- `games/ultima-online/outfit-lab/build.py` — zestaw z arkusza wzorów (`--config`).
- `games/ultima-online/outfit-lab/build_item.py` — jeden przedmiot (`--graphic`, `--hide-labels`).
- `games/ultima-online/outfit-lab/atlas_to_vd.py` — atlas → `.vd` (`--body`, `--outline`, `--original` = round-trip).
- `games/ultima-online/outfit-lab/uo_vd_writer.py`, `vd.py` — zapis/odczyt `.vd`.
- `games/ultima-online/outfit-lab/verify.py`, `viewer.js` — walidacja, podgląd.
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
   `python nelderim_search.py --client "F:\Nelderim" --item "<nazwa_lub_id>"`
   Sprawdź `body.def`, `Bodyconv.def`, `AnimationFrame*.uop`, `gump.def`, `art.def`, `mobtypes.txt`.
3. Klatki: SpriteMotion / outfit-lab → `.vd` (`atlas_to_vd.py` lub `vdtool.py pack`). Zawsze PNG (BMP gubi alfę).
4. Dry-run:
   `python nelderim_patch.py --client "F:\Nelderim" --recipe "<receptura.json>" --out "F:\OUTPUT FIDDLERA"`
5. Raport wyniku + `WARN`. Pytaj przy niejasnościach. `--apply` tylko po wyraźnej zgodzie.
6. Zmiany serwerowe → C# w `F:\ServUO-master\ServUO-master`.

## Landmines

- Zero halucynacji: ID, ścieżki, formaty tylko z plików na dysku lub kodu ClassicUO/ServUO.
- UOP > MUL: zapis do `.mul` zasobu istniejącego w `.uop` (np. `gumpartLegacyMUL.uop`) klient ignoruje → `uop_gump_patch.py`.
- Kolejność rozwiązywania: `body.def` → `AnimationFrame*.uop` → `Bodyconv.def` → `anim.mul`.
- Offsety w `anim.mul`:
  - People (≥400): `(graphic - 400) * 175 + 35000`
  - High (<200): `graphic * 110`
  - Low (200–399): `22000 + (graphic - 200) * 65`
- Nie edytuj ręcznie plików generowanych.
- Licencja MIT toolkitu nie daje praw do grafik gry; zachowaj `ASSET-SCOPE.md`, `LICENSE`.
- SpriteMotion: 1680 póz szacowanych ≠ zatwierdzonych. Zatwierdzonych 6 (akcja 22, SE).
