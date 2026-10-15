# DIAScreen (.dpa) – słownik parametrów

Oznaczenia: ✅ potwierdzone (zmiana w pliku → efekt w DIAScreen albo zgodność z oknem nastaw), 🔶 prawdopodobne (wnioskowane z nazw/zdjęć, do sprawdzenia).

## Kolory

Pliki zapisują kolor jako Windows COLORREF w postaci dziesiętnej: `R + G*256 + B*65536` (kolejność bajtów 0x00BBGGRR).

| Wartość w pliku | RGB | Uwagi |
|---|---|---|
| 11842740 | 180,180,180 | szary (Border / Background / Shadow) ✅ |
| 16579836 | 252,252,252 | domyślne tło ekranu ✅ |
| 16777215 | 255,255,255 | biały |
| 8421504 | 128,128,128 | koniec gradientu (`*FillEndColor`) |
| 0 | 0,0,0 | czarny (FontColor) |

Pole „HMI Colors – Decimal” w oknie wyboru koloru (np. 46518) to **RGB565** tego samego koloru: `(R>>3)<<11 | (G>>2)<<5 | (B>>3)`. W pliku jest zawsze 24-bitowy COLORREF, nie RGB565 ✅.

## Ekran – `[Screen]` (plik `screens/NNN_Nazwa.txt`)

| Klucz | Znaczenie |
|---|---|
| `ID` | numer ekranu (Screen No.) ✅ |
| `@@u16 wTextLen` | nazwa ekranu ✅ |
| `@@u16 wScreenDESCTextLen000` | opis ekranu |
| `DocSizeX/Y`, `PanelSizeX/Y` | rozdzielczość (1024×768) ✅ |
| `BgColor` | kolor tła ekranu (COLORREF) |
| `IsSubScreen`, `IsKeypadScreen`, `IsTemplateScreen`… | typ ekranu 🔶 |
| `BaseScreenID` | ekran bazowy (0 = brak) 🔶 |
| `OpenMacroLen` / `CloseMacroLen` / `CycleMacroLen` | długość makr ekranu (0 = brak) 🔶 |

Po nagłówku ekranu: `[AuxKeyElement]`, potem kolejne `[Element]`, każdy z jedną lub kilkoma sekcjami `[State]`.

## Element – wspólne

| Klucz | Znaczenie |
|---|---|
| `Type` / `SubType` | rodzaj elementu: `10/6` = Text (pole tekstowe) ✅, `5/1` = Numeric Display ✅ |
| `X`, `Y`, `Width`, `Height` | zakładka Coord. ✅ |
| `nPartsID` | numer elementu na ekranie (kolejny) ✅ |
| `@@u16 wDescTextLen0` | Element Description (np. „Numeric Display_001”) ✅ |
| `AutoResizeByText`, `AutoResizeMargin` | „Automatically resized based” / Margin ✅ |
| `Style` | styl ramki: `2` = Sunken (Numeric Display) ✅; `32768` u pola Text 🔶 |
| `BorderColor` | Border Color ✅ |
| `EnableShadowEffect`, `ShadowOffsetX/Y`, `ShadowColor`, `ShadowBlurRadius` | Show shadow / Offset X/Y / Shadow color / blur radius ✅ |
| `VisibleLink`, `VisibleVar`, `VisibleCondition` | Operating conds. – widoczność 🔶 |

## Numeric Display (`Type=5`, `SubType=1`) – zakładka Main

| Klucz | Pole w oknie | Wartości |
|---|---|---|
| `ReadVar` | Read Address | `$0` ✅ |
| `ReadLink`, `ReadMemType` | link / typ pamięci adresu 🔶 (`ReadLink=1` dla `$` wewn.) |
| `OffsetLength` | Offset length | `0` = Same value unit ✅ |
| `MemLen` | Data Type | `1` = Word ✅ (2 = Double Word 🔶) |
| `MemFmt` | Data Format | `2` = Unsigned Decimal ✅ |
| `IntNum` | Integer Digits | liczba cyfr, np. `5` ✅ (potwierdzone edycją) |
| `DotNum` | Fractional | miejsca po przecinku ✅ |
| `LeadingZero` | zera wiodące 🔶 |
| `DisplayDotVar` | Display Dot | `None` ✅ |
| `GainValue` / `OffsetValue` | Gain / Offset | `1.0` / `0.000000` ✅ |
| `Roundoff` | Round off | 0/1 ✅ |
| `Unit*`, `ShowUnit` | zakładka Unit conversion 🔶 |

Read Offset Address („None” na zdjęciu) – nie znaleziono jeszcze jednoznacznego klucza.

## Stan – `[State]`

Sufiks `0` w `FontSize0`, `FontName0`, `wTextLen0` = numer języka (Language1 = 0) 🔶.

| Klucz | Znaczenie |
|---|---|
| `Value` | numer stanu (State) ✅ |
| `@@u16 wTextLen0` | tekst wyświetlany (pole Text) ✅ (potwierdzone edycją) |
| `FontName0`, `FontSize0`, `FontColor`, `FontBold/Italic/Underline` | czcionka ✅ |
| `FontAlign` | wyrównanie: `33` (Text), `34` (Numeric) 🔶 |
| `BgFillType` | rodzaj wypełnienia tła: `6` = Gradient Fill (Numeric Display) 🔶 |
| `BgFillStyle` | styl gradientu: `1` = Mono Gradient 🔶 |
| `BgFillColor` | kolor gradientu (180,180,180) ✅ |
| `BgFillEndColor`, `BgFillStopPos0..4`, `BgFillStopColor0..4` | punkty gradientu (`-1` = nieużywany) 🔶 |
| `FgFill*` | to samo dla pierwszego planu (pole Text: `FgFillType=1`) 🔶 |

## Komunikacja (`project.txt`, `[Application]`)

| Klucz | Znaczenie |
|---|---|
| `ControllerName0` | „Delta AS series PLC TCP” ✅ |
| `CommName0` | nazwa linku `EtherLink1_1` ✅ |
| `HMIStationNr0`, `DefPLCStationNr0` | HMI Station / PLC Station ✅ |
| `PLCIP0` | IP sterownika jako int32 ze znakiem, big-endian: `-1062731775` = 192.168.0.1 ✅ |
| `PLCPort0` | port 502 ✅ |
| `CommPLCPassword0` | hasło sterownika ✅ |
| `CommDelayTime0`, `CommTimeout0`, `CommRetry0` | Comm. Delay / Connection Timeout / Retries ✅ |
| `CommOptEnable0` | Optimize ✅ |
| `PanelResWidth/Height`, `Name`, `DefaultScreen` | z kreatora projektu ✅ |

## Elementy, których nie ruszać ręcznie

`@@blob32 MeMeCode` (DIAScreen zmienia go przy każdym zapisie, ale akceptuje stary), `GUID`, `thumbnail.bin`.
Przy ponownym zapisie DIAScreen sam zmienia też m.in. `SmtpHWInf`/`FTPHWInf` (-1 → 255) i `*SyncConfirm` – to normalne.
