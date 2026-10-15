# dpa_tool – edycja projektów DIAScreen bez GUI

Jeden plik `dpa_tool.py`, wymaga tylko Pythona 3 (bez dodatkowych bibliotek).
Sprawdzone na projektach DIAScreen dla panelu serii AX-8. Opis formatu pliku `.dpa`: [FORMAT_DPA.md](FORMAT_DPA.md),
znaczenie parametrów: [PARAMETRY.md](PARAMETRY.md).

## Zasada pracy
1. Zamknij projekt w DIAScreen.
2. `decode` rozkłada `PROJEKT.dpa` na pliki tekstowe w folderze `PROJEKT` obok projektu.
3. Edytujesz pliki tekstowe (dowolnym edytorem).
4. `encode` składa folder z powrotem do pliku `.dpa` (domyślnie `PROJEKT_edited.dpa` – oryginał zostaje).
5. Otwierasz projekt w DIAScreen i **kompilujesz** – to jest ostateczna kontrola poprawności.

## Polecenia
```
python dpa_tool.py decode PROJEKT.dpa [KATALOG]
python dpa_tool.py encode KATALOG [WYJSCIE.dpa]
python dpa_tool.py verify PROJEKT.dpa [PROJEKT2.dpa ...]
```
- `decode` – rozkłada projekt (domyślnie do folderu o nazwie projektu). Sprawdza, że rozkład i złożenie dają
  tę samą treść. Foldery `screens/` i `lua/` są przy każdym `decode` tworzone od nowa.
- `encode` – składa folder do `.dpa`; długości tekstów, bloku Lua i całej treści liczy sam.
- `verify` – test bez zmian treści: `decode` → `encode` do folderu tymczasowego i porównanie bajt w bajt
  z oryginałem. Uruchamiaj po każdej zmianie narzędzia na wszystkich dostępnych projektach.

Przykład:
```
python dpa_tool.py decode Projekt.dpa
#  ... edycja Projekt/screens/002_Screen_2.txt i Projekt/lua/Main.lua ...
python dpa_tool.py encode Projekt Projekt_v2.dpa
```

## Układ folderu po `decode`
| Plik | Zawartość |
|---|---|
| `project.txt` | ustawienia globalne (aplikacja, komunikacja, klawiatury, alarmy…) + linie `@@screen` |
| `screens/NNN_Nazwa.txt` | jeden ekran: `[Screen]`, `[AuxKeyElement]`, elementy `[Element]` ze stanami `[State]` |
| `lua/<nazwa>.lua` | programy Lua jako zwykły tekst |
| `lua/_lua_files.xml` | atrybuty programów Lua (`name`, `protect`, `password`, `path`) |
| `sram_data.db` | baza SQLite zapisana w projekcie (hasła, sieć, kontakty…) – można ją otworzyć np. w DB Browser for SQLite |
| `thumbnail.bin`, `meta.json` | miniatura i dane techniczne – nie edytować |

Zapis wartości w plikach tekstowych:
- `KLUCZ=wartość` – zwykła linia, edytujesz wprost (np. `X=200`, `IntNum=5`).
- `@@u16 KLUCZ="tekst"` – tekst UTF-16 (napisy, nazwy, opisy); zmieniasz tylko tekst w cudzysłowie, polskie
  znaki są dozwolone, długość liczy narzędzie.
- `@@screen screens/…` – miejsce ekranu w projekcie; kolejność linii = kolejność ekranów.
- `@@blob32`, `@@lenhex`, `@@hex`, `@@sqlite`, `@@luaxml` – dane binarne i odnośniki do plików – nie edytować.

## Ograniczenia
- Sprawdzone na panelu AX-8 (projekt `Version=6.6.2.48`); inna wersja lub panel – najpierw `verify` → otwarcie
  w DIAScreen bez zmian.
- Obrazy (`[Picture]`, `[Background]`) i makra nie były jeszcze badane – zostają zapisane bez zmian, ale nie
  są rozpisywane na osobne pliki.
- DIAScreen przy ponownym zapisie zmienia sam kilka pól (`MeMeCode`, `SmtpHWInf`, `FTPHWInf`, `*SyncConfirm`) –
  to normalne.
