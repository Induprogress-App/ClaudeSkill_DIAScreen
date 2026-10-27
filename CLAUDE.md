# dpa_tool – narzędzie i skill do projektów Delta DIAScreen

Repozytorium narzędzia `dpa_tool.py`, które odczytuje i edytuje projekty HMI Delta DIAScreen (`.dpa`) bez GUI,
oraz skilla `diascreen` dla Claude Code, który z niego korzysta. Narzędzie trafia do wielu osób.

## Struktura
| Plik / folder | Zawartość |
|---|---|
| `diascreen/` | **zawartość paczki skilla 1:1** – wszystko, co tu jest, trafia do paczki |
| `diascreen/SKILL.md`, `diascreen/INSTALACJA.md` | skill dla Claude i instrukcja instalacji dla ludzi |
| `diascreen/dpa_tool.py` | całe narzędzie: jeden plik, tylko biblioteka standardowa Pythona 3 |
| `diascreen/README.md` | instrukcja poleceń dla użytkowników |
| `diascreen/FORMAT_DPA.md` | opis formatu pliku `.dpa` – wszystko, co ustalono o zapisie projektu |
| `diascreen/PARAMETRY.md` | słownik parametrów wspólnych: ekran, adresy, kolory, komunikacja (potwierdzone / przypuszczenia) |
| `diascreen/dane/` | `parametry.csv` (słownik kluczy), `elementy.csv` (rodzaje, wymagane/opcjonalne), `wzorce/T_S.txt` |
| `diascreen/szablony/*.dpa` | puste projekty dla polecenia `new` (wyjątek od zasady „.dpa tylko w `_ns_`”) |
| `generuj_slownik.py` | generuje `diascreen/dane/` z rozłożonych projektów testowych; opisy kluczy w słowniku `OPISY` |
| `zbuduj_skill.py` | pakuje `diascreen/` do `_ns_dist/diascreen.zip` (+ `WERSJA.txt`) |
| `aktualizuj_skill.py` | buduje paczkę i instaluje skill lokalnie |
| `CLAUDE.md`, `.gitignore`, `.gitattributes` | ten plik i reguły repozytorium (`* -text` – bez konwersji końców linii) |

Wszystko, co nie ma trafić do repozytorium, leży w plikach lub folderach o nazwie zaczynającej się od `_ns_`
(NoSynch), np. `_ns_dist` (wyniki budowania), `_ns_tests` (projekty testowe), `_ns_analiza`, `_ns_smietnik`
(rzeczy usunięte przy porządkach – zamiast kasowania). Projekty HMI (`.dpa`) i zrzuty ekranu z DIAScreen trzymać
wyłącznie w folderach `_ns_`. Uruchamianie narzędzia z repozytorium: `python diascreen/dpa_tool.py ...`.

Dane użytkownika (poza repozytorium): `%USERPROFILE%\.claude\skills\diascreen\` – zainstalowany skill.

## Zasady pracy (ustalone z użytkownikiem)
- W folderze repozytorium wolno bez pytania czytać pliki, tworzyć i zmieniać pliki oraz uruchamiać polecenia
  (także skrypty Pythona). Poza nim – najpierw zapytać (wyjątek: instalacja skilla przez `aktualizuj_skill.py`,
  gdy zmiany działają).
- Projektów `.dpa` użytkownika nie zmieniać bez zgody. Do testów tworzyć kopie albo zapisywać wynik `encode`
  pod nową nazwą (np. `..._TEST_<co>.dpa`) w `_ns_tests/`.
- Ostateczny test to otwarcie i kompilacja w DIAScreen – robi to użytkownik. Po zmianie narzędzia: `verify` na
  wszystkich projektach w `_ns_tests/` (decode → encode bez zmian, plik identyczny bajt w bajt), potem plik
  z przykładową edycją do sprawdzenia w DIAScreen.
- Nowe znaczenia parametrów ustalać na podstawie zdjęć okien nastaw od użytkownika i porównania projektów
  zapisanych przed i po zmianie jednej nastawy; w `PARAMETRY.md` oznaczać ✅ (potwierdzone) albo 🔶 (przypuszczenie).

## Gałęzie git
- Prace i testy commitować do lokalnej gałęzi `tests` (utworzyć ją z `main`, jeśli nie istnieje).
  Gałęzi `tests` **nie wysyłać na serwer** (żadnego `git push` tej gałęzi).
- Do `main` trafiają tylko zmiany przetestowane i działające (po `verify` i sprawdzeniu w DIAScreen przez
  użytkownika) – przeniesione z `tests` dopiero po potwierdzeniu, **jednym commitem**:
  `git checkout main && git merge --squash tests && git commit` (nie `merge --no-ff` – przenosi całą historię `tests`).
- Wysyłać na serwer (GitHub) wyłącznie `main`, i tylko na prośbę użytkownika.

## Poufność i zakres analizy
- W narzędziu, dokumentacji, przykładach i opisach commitów **nie umieszczać szczegółów z rzeczywistych
  projektów**: nazw projektów, ekranów, tekstów, adresów, haseł ani ogólnej struktury aplikacji HMI.
  Przykłady mają być ogólne (np. `Projekt.dpa`, `Screen_2`, `$100`).
- Przy rozwijaniu narzędzia i skilla projekty użytkownika analizować **tylko pod kątem formatu zapisu**
  (budowa pliku, rodzaje elementów, parametry), bez analizowania, czym aplikacja steruje – chyba że użytkownik
  wprost o to poprosi.
- Paczka dla innych osób powstaje wyłącznie z plików repozytorium; przed wydaniem przejrzeć je pod tym kątem.

## Wydanie nowej wersji
1. Commit zmian (numer wersji paczki = numer commitu; niezacommitowane zmiany dają dopisek `-dirty`).
2. `python aktualizuj_skill.py` – budowanie paczki (z kontrolą zakazanych słów z `_ns_zakazane_slowa.txt`)
   i instalacja skilla.
3. Paczka do wysłania: `_ns_dist/diascreen.zip`.

## Konwencje kodu
- `dpa_tool.py`: jeden plik, bez zależności, komunikaty i komentarze po polsku bez polskich znaków.
  Nie czytać go w całości: spis sekcji jest w docstringu na początku, sekcje zaczynają się od `# ----`;
  miejsce znaleźć Grepem (`^# ----`, `^def `), czytać tylko potrzebny zakres linii. Nowa sekcja → dopisać do spisu.
  Dokumentacja (`.md`) z polskimi znakami.
- Pliki tekstowe po `decode`: UTF-8, końce linii LF (w `.dpa` CRLF); pliki `.lua` – bajty 1:1 z projektu.
- Każda zmiana formatu musi zachować bezstratność: `decode` sprawdza, że podział treści jest bezstratny,
  `verify` – że cały plik wraca bajt w bajt.
- Przy edycji kodu skryptami uważać na sekwencje `\r\n` i `\` w napisach – bezpieczniej Edit/Write
  albo surowe napisy w pliku skryptu.
- Nowe ustalenia o formacie dopisywać do `diascreen/FORMAT_DPA.md`, znaczenia parametrów do
  `OPISY`/`NAZWY`/`WYMAGANE` w `generuj_slownik.py` (potem ponowne generowanie) lub `diascreen/PARAMETRY.md`, nowe polecenia do `diascreen/README.md` i `diascreen/SKILL.md`.

## Otwarte sprawy
- Brak ochrony przed utratą pracy jak w `isp_codec` (kontrola, czy `.dpa` zapisano w DIAScreen po `decode`,
  i czy folder ma niezapisane zmiany) – `decode` nadpisuje folder bez pytania.
- Niezbadane: obrazy (`[Picture]`, `[Background]`), znaczenie nagłówków i flag poleceń makr, `[SubMacro]`, receptury, alarmy, kodowanie znaków spoza ASCII
  w zwykłych liniach, inne panele niż AX-8. Wzorce ze skilla pochodzą z różnych wersji DIAScreen (6.6.0–6.6.2). Klucz pola „Read Offset Address” wyświetlacza numerycznego nieznany.
