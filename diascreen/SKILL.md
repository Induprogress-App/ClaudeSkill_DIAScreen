---
name: diascreen
description: Odczyt i edycja projektów HMI Delta DIAScreen (.dpa) bez GUI – rozkładanie projektu na pliki tekstowe (osobny plik na każdy ekran, programy Lua jako zwykłe pliki .lua, ustawienia globalne, baza SQLite) i składanie z powrotem do .dpa. Używaj zawsze, gdy rozmowa dotyczy projektu DIAScreen, pliku .dpa, panelu HMI Delta (np. seria AX-8, DOP) albo elementów ekranów HMI (pola tekstowe, wyświetlacze numeryczne, Lua w HMI).
---

# Projekty DIAScreen (.dpa)

Narzędzie `dpa_tool.py` leży w katalogu tego skilla (podanym przy jego wczytaniu jako katalog bazowy).
Wymaga tylko Pythona 3 – uruchamiaj je jako `python "<katalog skilla>/dpa_tool.py" ...`
(jeśli polecenie `python` nie działa, spróbuj `py -3`). Pełny opis poleceń: `README.md`, opis formatu pliku:
`FORMAT_DPA.md`, znaczenie parametrów elementów: `PARAMETRY.md` – wszystkie w katalogu skilla; czytaj je tylko
wtedy, gdy potrzebujesz szczegółów.

## Zasady pracy
1. **Projekt musi być zamknięty w DIAScreen**, zanim zapiszesz `.dpa`. Zapytaj użytkownika, jeśli nie wiesz.
   Domyślnie zapisuj wynik do **nowego pliku** (`encode KATALOG WYJSCIE.dpa`), nie nadpisuj oryginału bez zgody.
2. `decode PROJEKT.dpa` rozkłada projekt do folderu o tej samej nazwie obok pliku. Ponowny `decode` nadpisuje
   ten folder – jeśli są w nim niezapisane zmiany, najpierw `encode` albo zapytaj użytkownika.
3. Czytaj tylko potrzebne pliki – to oszczędza kontekst:
   - `screens/NNN_Nazwa.txt` – jeden ekran ze wszystkimi elementami (`[Element]`, `[State]`),
   - `lua/*.lua` – programy Lua, `lua/_lua_files.xml` – ich atrybuty,
   - `project.txt` – ustawienia globalne (komunikacja, panel, alarmy, klawiatury) i lista ekranów (`@@screen`).
   Konkretny parametr najszybciej znajdziesz wyszukiwaniem (np. `ReadVar=`, `nPartsID=`).
4. Edytuj wartości bezpośrednio w plikach. Teksty `@@u16 KLUCZ="..."` zmieniaj tylko w cudzysłowie (długość liczy
   narzędzie). Nie zmieniaj linii `@@blob32`, `@@hex`, `@@lenhex`, `GUID`, `thumbnail.bin`, `meta.json`.
5. Nowy element / ekran: skopiuj istniejący blok (`[Element]` z jego `[State]`, albo cały plik ekranu) i popraw
   pola – w elemencie `nPartsID` (kolejny numer na ekranie), `X`/`Y`, opis `wDescTextLen0`; w nowym ekranie `ID`,
   nazwę `wTextLen` i linię `@@screen` w `project.txt` (kolejność linii = kolejność ekranów).
6. Po zmianach `encode`, a potem poproś użytkownika o otwarcie projektu w DIAScreen i **kompilację** – tylko ona
   potwierdza poprawność. Zgłoszone błędy poprawiaj w plikach tekstowych.
7. Znaczenie parametrów sprawdzaj w `PARAMETRY.md` (✅ potwierdzone, 🔶 przypuszczenie). Gdy użytkownik potwierdzi
   nowe znaczenie (np. zdjęciem okna nastaw albo testem w DIAScreen), zaproponuj dopisanie go do `PARAMETRY.md`.

## Lua
Programy Lua są w `lua/<nazwa>.lua` jako zwykły tekst (UTF-8, końce linii jak w projekcie). Przed pisaniem kodu
przeczytaj istniejący program i naśladuj jego styl; nie zakładaj składni spoza standardowego Lua i funkcji
`sys.*` używanych w projekcie, jeśli użytkownik ich nie potwierdzi.

## Ograniczenia
Sprawdzone na projektach DIAScreen dla panelu serii AX-8 (`Version=6.6.2.48` w `project.txt`). Dla innej wersji
lub panelu najpierw: `verify PROJEKT.dpa` (decode → encode bez zmian, plik identyczny bajt w bajt) → otwarcie
w DIAScreen. Zbadane elementy: pole tekstowe, wyświetlacz numeryczny; pozostałe rozpoznawaj z istniejących
projektów użytkownika.
