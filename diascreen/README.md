# dpa_tool – edycja projektów DIAScreen bez GUI

Jeden plik `dpa_tool.py`, wymaga tylko Pythona 3 (bez dodatkowych bibliotek).
Sprawdzone na projektach DIAScreen dla panelu serii AX-8. Opis formatu pliku `.dpa`: [FORMAT_DPA.md](FORMAT_DPA.md),
znaczenie parametrów: polecenia `params` i `types` (dane w `dane/parametry.csv`, `dane/elementy.csv`)
oraz [PARAMETRY.md](PARAMETRY.md) (kolory, komunikacja).

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

### Przeglądanie (krótkie wyniki zamiast czytania całych plików)
```
python dpa_tool.py screens KATALOG|PROJEKT.dpa
python dpa_tool.py list    KATALOG|PROJEKT.dpa EKRAN [--xy]
python dpa_tool.py show    KATALOG|PROJEKT.dpa EKRAN ELEMENT [--all]
python dpa_tool.py find    KATALOG|PROJEKT.dpa TEKST
```
`EKRAN` = numer (ID), nazwa albo nazwa pliku ekranu; `ELEMENT` = `nPartsID` albo opis elementu.
Zamiast katalogu można podać plik `.dpa` (zostanie rozłożony do folderu tymczasowego).
- `screens` – lista ekranów: ID, nazwa, plik, liczba elementów, ekran bazowy.
- `list` – jedna linia na element: `nPartsID`, rodzaj, adresy (`R`=odczyt, `W`=zapis, `Trg`, `Vis`=widoczność,
  `Lock`=blokada, `Scr`=ekran docelowy), znacznik `macro`, liczba stanów i teksty. `--xy` dodaje pozycję i rozmiar.
- `show` – parametry jednego elementu bez wartości pustych/zerowych; stany od drugiego pokazane jako różnice
  względem poprzedniego, makra jako odczytany tekst. Podaje zakres linii w pliku ekranu. `--all` – cały blok
  z numerami linii.
- `find` – wyszukuje tekst (bez rozróżniania wielkości liter) w wartościach elementów wszystkich ekranów:
  adresach, tekstach, opisach.

### Projekty, słownik, ekrany
```
python dpa_tool.py files [FOLDER]
python dpa_tool.py new NOWY.dpa [--name=NAZWA] [--template=PLIK]
python dpa_tool.py types
python dpa_tool.py params [TEKST] [--type=RODZAJ] [--scope=ekran|element|stan|akcja]
python dpa_tool.py add-screen KATALOG ID NAZWA [--base=ID] [--sub|--confirm] [--size=SZERxWYS] [--pos=X,Y] [--title=TYTUL] [--from=EKRAN]
```
- `files` – pliki `.dpa` w folderze (z podfolderami): data, rozmiar, czy jest folder po `decode`
  i czy zmieniano go po rozłożeniu.
- `new` – nowy pusty projekt z szablonu z folderu `szablony/` (domyślnie AX-8 1024×768; też
  `DOP-107EG_800x600.dpa`, `DOP-110IS_1024x600.dpa` – `--template=`), od razu rozłożony do folderu o nazwie
  projektu; `--name` ustawia nazwę projektu. Błędna nazwa szablonu wypisuje dostępne.
- `types` – rodzaje elementów (`Type/SubType`), parametry wymagane przy dodawaniu i typowe opcjonalne.
- `params` – słownik parametrów: `zakres klucz = domyślna | spotykane wartości | opis`; filtr po tekście
  w nazwie/opisie, po rodzaju elementu i zakresie. `(?)` = znaczenie przypuszczalne. `#` w nazwie = numer
  (język, kolumna, punkt gradientu).
- `add-screen` – nowy pusty ekran: nagłówek kopiowany z istniejącego ekranu (`--from`) albo pierwszego
  zwykłego/podekranu (`--sub` ustawia `IsSubScreen=1`); `--base` = ekran bazowy. Okna: `--sub` = podekran, `--confirm` = ekran potwierdzenia; `--size` = rozmiar okna
  (domyślnie jak we wzorcu albo 430×260), `--pos=X,Y` = pozycja na panelu (bez niej okno na środku),
  `--title` = tytuł okna (pusty = bez paska tytułu). Ekran potwierdzenia (Confirmation screen, dla przycisków z `ConFirmWindow=3`; przyciski OK/Anuluj to `Keypad Key`
  z `ASCIIValue0=13`/`27`). Dopisuje ekran do `project.txt`.

### Dane z instalacji DIAScreen
```
python dpa_tool.py info KATALOG|PROJEKT.dpa
python dpa_tool.py lua-api [TEKST] [--full]
```
Oba polecenia czytają pliki zainstalowanego DIAScreen (domyślnie najnowszy
`Program Files (x86)\Delta Industrial Automation\DIAStudio\DIAScreen*`, inny katalog: zmienna `DIASCREEN_DIR`).
Gdy instalacji brak, używają kopii w skillu: `dane/panele.csv` (lista paneli z `PanelList.ini`)
i `dane/lua_api.xml` (kopia `ProgList_English.xml` z DIAScreen 1.6).
- `info` – nazwa projektu, wersja, model panelu (`ModelName` → `ScrEditApp\PanelList.ini`, sekcja `[Inquire]`),
  rozdzielczość, IP panelu, łącza (sterownik, IP:port albo port COM), liczba języków i ekranów, programy Lua.
- `lua-api` – funkcje Lua z `ScrEditApp\Language\ProgList_English.xml`: bez argumentu lista grup, z tekstem –
  sygnatury pasujących funkcji, pełny opis przy ≤ 3 trafieniach, dokładnej nazwie albo `--full`.

### Porównanie projektów
```
python dpa_tool.py diff STARY.dpa NOWY.dpa [--out=ROZNICE.dpa] [--all]
```
Działa na plikach `.dpa` i folderach po `decode`. Ekrany dopasowuje po `ID`, elementy po `nPartsID` + rodzaju + opisie
(`wDescTextLen0`) – DIAScreen nadaje nowemu elementowi numer usuniętego, a rodzaju i opisu nie da się zmienić.
Wiersz elementu kończy się opisem, np. `~   1 Numeric Entry  W=$10  "####"  "Numeric Entry_001"`. Wynik:
- `# Ustawienia projektu` – zmienione klucze `project.txt` (np. `Application0.SmtpHWInf: "-1" -> "255"`),
  baza `sram_data.db`, pliki Lua (dodane / usunięte / zmienione),
- `# ekran ID Nazwa (plik): N zm.` – zmiany nagłówka ekranu, potem elementy: `+` dodany, `~` zmieniony
  (pod nim `klucz: stara -> nowa`; klucze stanów z przedrostkiem, np. `State1.wTextLen0`), `-` usunięty,
- `+ ekran` / `- ekran` – ekran dodany / usunięty.

Bez `--all` pod elementem jest najwyżej 8 zmian. `MeMeCode` zmienia się przy każdym zapisie w DIAScreen.

`--out=ROZNICE.dpa` zapisuje kopię NOWEGO projektu, w której zostają tylko elementy dodane i zmienione
(z nowego ekranu – wszystkie). Zostają tylko ekrany ze zmianami oraz ich ekrany bazowe (`BaseScreenID`,
bez elementów, jeśli same się nie zmieniły). Przyciski przejścia mogą wskazywać ekrany, których w pliku nie ma.
Z `[Group]` zostają tylko grupy użyte przez pozostawione elementy. Elementów usuniętych tam nie ma.

### Edycja elementów
```
python dpa_tool.py set KATALOG EKRAN ELEMENT|- KLUCZ=WART ... [--state=N|all] [--lang=N]
python dpa_tool.py add KATALOG EKRAN RODZAJ|ZRODLO_EKRAN:ELEMENT [KLUCZ=WART ...] [--from=KATALOG2] [--state=N|all] [--lang=N] [--force]
```
`KLUCZ` to nazwa z pliku (lista: `params`) albo skrót: `text` (`wTextLen0`), `desc` (`wDescTextLen0`),
`read` (`ReadVar`), `write` (`WriteVar`), `visible` (`VisibleVar`), `screen` (`GoToScreenID`), `x`, `y`, `w`, `h`,
dla ekranu `name` (`wTextLen`), `base` (`BaseScreenID`). `--lang=N` – skróty `text`/`desc` dla języka N.
- `set` – zmienia istniejące klucze (nowych nie dodaje; wyjątek: brakujące `VisibleLink`/`VisibleVar` – DIAScreen
  pomija je w elementach bez adresu widoczności – są wstawiane przed `VisibleCondition`): najpierw w części wspólnej elementu, potem w stanach;
  przy kilku stanach `--state=N` (od 0) albo `--state=all`. `ELEMENT` = `-` zmienia nagłówek ekranu.
  Tekst dłuższy niż 256 znaków: uzupełnia kopię `Base64TextLenN`. Ostrzega, gdy adres ma `…Link=0`.
- `add RODZAJ` – nowy element (`RODZAJ` = nazwa z `types`, np. `"Numeric Display"`/`Numeric_Display`, albo `5/1`).
  Wzorzec: element tego rodzaju z projektu (adresy → `None`, teksty wyczyszczone) albo plik `dane/wzorce/T_S.txt`.
  Wymaga parametrów z kolumny „wymagane” w `types` (`--force` pomija), ustawia `…Link=1` przy podanym adresie,
  `GoToScreenName` przy `screen=`, dopasowuje wersje językowe do projektu.
- `add EKRAN:ELEMENT` – kopia istniejącego elementu (także z innego projektu, `--from=KATALOG2`); bez `x`/`y`
  przesunięta o 20 px.
- `--states=N` (`add`, `set`) – liczba stanów (Multistate): dopisuje kopie ostatniego stanu z kolejnym `Value`
  albo usuwa nadmiarowe. Dla Multistate z adresem `$N.b` `add` ustawia `MemLen=0` i 2 stany, z `$N` – `MemLen=1`.
- W tekstach `
` oznacza nową linię (zapisywaną jako CRLF).
- Oba `add`: nowy `nPartsID` (kolejny na ekranie), opis `<rodzaj>_<kolejny numer w projekcie>`, element na końcu
  ekranu; podane `KLUCZ=WART` stosowane do wszystkich stanów, jeśli nie podano `--state`.

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
