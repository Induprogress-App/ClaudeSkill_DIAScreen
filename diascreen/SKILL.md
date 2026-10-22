---
name: diascreen
description: Odczyt i edycja projektów HMI Delta DIAScreen (.dpa) bez GUI – nowy projekt z szablonu, lista ekranów i elementów, dodawanie ekranów i elementów (przyciski, teksty, wyświetlacze, pola wprowadzania…), zmiana parametrów, wyszukiwanie adresów i tekstów, słownik parametrów, programy Lua. Używaj zawsze, gdy rozmowa dotyczy projektu DIAScreen, pliku .dpa, panelu HMI Delta (np. seria AX-8, DOP) albo elementów ekranów HMI.
---

# Projekty DIAScreen (.dpa)

Uruchamiaj: `python "<katalog skilla>/dpa_tool.py" POLECENIE ...` (gdy `python` nie działa: `py -3`).
**Wszystko rób poleceniami – nie czytaj plików ekranów ani plików skilla** (ekran ma tysiące linii; słownik
parametrów i rodzajów jest dostępny przez `types` i `params`).

## Polecenia
| Polecenie | Wynik |
|---|---|
| `files [FOLDER]` | pliki `.dpa` (data, rozmiar, czy jest folder po `decode` i czy ma zmiany) |
| `new NOWY.dpa [--name=N] [--template=T]` | nowy pusty projekt + folder `NOWY/`; szablony: `AX8_1024x768.dpa` (domyślny), `DOP-107EG_800x600.dpa`, `DOP-110IS_1024x600.dpa` |
| `decode PROJEKT.dpa` | folder `PROJEKT/` obok pliku (nadpisuje go!) |
| `info KAT` | panel (model z instalacji DIAScreen), rozdzielczość, łącza i adresy IP, języki, programy Lua |
| `lua-api [TEKST] [--full]` | funkcje Lua DIAScreen (bez argumentu: grupy; np. `lua-api mem.inter`, `lua-api screen.Open`) |
| `screens KAT` | ekrany: ID, nazwa, plik, liczba elementów, ekran bazowy |
| `list KAT EKRAN [--xy]` | linia na element: nr, rodzaj, adresy (R/W/Trg/Vis/Lock/Scr), teksty |
| `show KAT EKRAN EL [--all]` | parametry elementu bez wartości pustych, stany jako różnice |
| `find KAT TEKST` | gdzie występuje adres/tekst (wszystkie ekrany) |
| `types` | rodzaje elementów `T/S`, parametry wymagane i typowe opcjonalne |
| `params [TEKST] [--type=RODZAJ] [--scope=ekran\|element\|stan\|akcja]` | słownik: klucz = domyślna \| wartości \| opis |
| `add KAT EKRAN RODZAJ klucz=wart …` | nowy element (np. `"Numeric Display" read=$10 x=20 y=60`) |
| `add KAT EKRAN ZR_EKRAN:EL klucz=wart … [--from=KAT2]` | kopia istniejącego elementu |
| `set KAT EKRAN EL klucz=wart … [--state=N\|all] [--lang=N] [--states=N]` | zmiana parametrów / liczby stanów |
| `set KAT EKRAN - klucz=wart …` | zmiana nagłówka ekranu (np. `name=`, `base=`, `BgColor=`) |
| `add-screen KAT ID NAZWA [--base=ID] [--sub\|--confirm] [--size=WxH] [--pos=X,Y] [--title=T] [--from=EKRAN]` | nowy ekran; okno (podekran / ekran potwierdzenia): rozmiar, pozycja (bez `--pos` – na środku), tytuł (`--title=` pusty = bez paska) |
| `encode KAT WYJSCIE.dpa` / `verify PROJEKT.dpa` | złożenie / test bajt w bajt |

`EKRAN` = ID, nazwa albo plik; `EL` = `nPartsID` albo opis; `RODZAJ` = nazwa z `types` (spacje albo `_`)
lub `T/S`. Przeglądanie działa też na samym `.dpa`.
Skróty kluczy: `text` (tekst, wszystkie stany), `desc`, `read`, `write`, `visible`, `screen` (cel Goto Screen),
`x`, `y`, `w`, `h`; w nagłówku ekranu `name`, `base`. Inne klucze – nazwy z `params`.

## Zasady
1. **Projekt musi być zamknięty w DIAScreen**, zanim zapiszesz `.dpa`; zapisuj do **nowego pliku**
   (`encode KAT WYJSCIE.dpa`), oryginał nadpisuj tylko za zgodą. `decode` nadpisuje folder – najpierw `files`
   (pokaże „zmiany po decode”).
2. `add RODZAJ` sam nadaje `nPartsID`, opis i łącza adresów (`…Link=1`); wzorzec bierze z elementu tego rodzaju
   w projekcie (bez jego adresów i tekstów), a gdy go brak – ze skilla. Brak wymaganych parametrów = błąd
   z listą (`--force` pomija). Wersje językowe dopasowuje do projektu.
3. Adresy: `$100` (słowo wewn.), `$100.3` (bit), zmienne sterownika w postaci używanej już w projekcie
   (sprawdź `find KAT @` albo `list`), np. `LACZE@Application.GVL.Zmienna` lub `{LACZE}0@Application.…`.
4. Multistate: `--states=N` (przy `add` i `set`) ustawia liczbę stanów, tekst stanu: `set … text="…" --state=N`.
   Typ danych `MemLen` musi pasować do adresu (0 = bit `$N.b`, 1 = Word `$N`) – `add` ustawia go sam dla
   adresów `$`; dla zmiennych sterownika sprawdź. Nowa linia w tekście: `
`.
   Wygląd (sprawdzone): `Style=3` = Invisible (Multistate), `Style=32768` = przezroczysty Text,
   `FgColor`/`FgFillColor` = kolor wypełnienia, `FgFillType` 1 = Solid / 6 = gradient, `FontColor`, `FontBold`,
   `Twinkles=1` = miganie, `FontAlign` = 1/2/4 (lewo/środek/prawo) + 16/32/64 (góra/środek/dół). Kolory COLORREF:
   R + G·256 + B·65536 (255 = czerwony, 65280 = zielony, 16711680 = niebieski).
5. Potwierdzenie przycisku: `ConFirmWindow` 1 = systemowe Yes/No, 2 = + ponowne logowanie, 3 = własny ekran:
   `add-screen KAT 65500 Nazwa --confirm`, na nim `Keypad Key` z `ASCIIValue0=13` (OK) / `27` (Anuluj),
   w przycisku `ConFirmWindow=3 ConfirmScreenID=65500 ConfirmScreenName=Nazwa`.
   Typ danych: `MemLen` 0 bit / 1 Word / 2 DWord / 6 QWord, `MemFmt` 1 = ze znakiem, 2 = bez znaku.
6. Teksty ponad 256 znaków: `set text=` sam uzupełnia kopię `Base64TextLen`. Nazwy ekranów/teksty mogą mieć
   polskie znaki; zwykłe wartości (`klucz=` bez `@@u16`) – tylko ASCII.
7. Makra (`…MacroLen`, linie `@@hex`) są binarne – `show` pokazuje ich tekst; zmieniaj je w DIAScreen.
8. Po zmianach `encode`, potem użytkownik otwiera projekt w DIAScreen i **kompiluje** – tylko to potwierdza
   poprawność. W `params` „(?)” = znaczenie przypuszczalne; gdy użytkownik je potwierdzi, zaproponuj poprawkę
   słownika.

## Lua
Programy są w `KAT/lua/<nazwa>.lua` (zwykły tekst) – to jedyne pliki, które czytasz i edytujesz bezpośrednio.
Naśladuj styl istniejącego programu. Składnię funkcji (`mem.*`, `screen.*`, `sys.*`, `recipe.*`…) sprawdzaj
`lua-api` – czyta dokumentację z zainstalowanego DIAScreen; nie zgaduj funkcji, których tam nie ma.

## Ograniczenia
Sprawdzone na panelach AX-8 (`Version` 6.6.0–6.6.2). Inna wersja/panel: najpierw `verify`, potem otwarcie
w DIAScreen. Szczegóły formatu (tylko przy rozwoju narzędzia): `FORMAT_DPA.md`, `README.md`.
