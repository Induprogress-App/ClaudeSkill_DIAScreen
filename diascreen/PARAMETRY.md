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
| `Type` / `SubType` | rodzaj elementu – lista: polecenie `types` (`dane/elementy.csv`) |
| `X`, `Y`, `Width`, `Height` | zakładka Coord. ✅ |
| `nPartsID` | numer elementu na ekranie (kolejny) ✅ |
| `@@u16 wDescTextLen0` | Element Description (np. „Numeric Display_001”) ✅ |
| `AutoResizeByText`, `AutoResizeMargin` | „Automatically resized based” / Margin ✅ |
| `Style` | styl ramki: `2` = Sunken (Numeric Display) ✅; `32768` u pola Text 🔶 |
| `BorderColor` | Border Color ✅ |
| `EnableShadowEffect`, `ShadowOffsetX/Y`, `ShadowColor`, `ShadowBlurRadius` | Show shadow / Offset X/Y / Shadow color / blur radius ✅ |
| `VisibleLink`, `VisibleVar`, `VisibleCondition` | Operating conds. – widoczność 🔶 |

## Adresy (`ReadVar`, `WriteVar`, `VisibleVar`, `TriggerVar`, `InterLockVar`…)

| Zapis | Znaczenie |
|---|---|
| `None` | brak adresu |
| `$100` | słowo pamięci wewnętrznej HMI 🔶 |
| `$100.3` | bit 3 słowa wewnętrznego 🔶 |
| `CODESYS@Application.GVL.Zmienna` | zmienna sterownika z zaimportowanych tagów; tablice `[i]`, bit `.n` 🔶 |
| `ENRCPNO`, `ENRCPNONAME` | numer / nazwa receptury (rejestry specjalne) 🔶 |

Przy adresie klucz `…Link` (np. `ReadLink`) ma wartość `1`; `…Link=None` przy braku adresu 🔶.
Opis elementu (`wDescTextLen0`) nadaje użytkownik/DIAScreen – nie musi odpowiadać rodzajowi; rodzaj ustala się
tylko z `Type`/`SubType`.

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
| `ModelName` | model panelu: liczba = kod szesnastkowy z `ScrEditApp\PanelList.ini` `[Inquire]` (np. `0x20000002` = AX-8_Linux, `0x10010705` = DOP-107EG) ✅ |
| `…N` (`ControllerNameN`, `CommNameN`, `PLCIPN`…) | N = numer łącza; kilka sterowników = kilka zestawów kluczy ✅ |
| `InterfaceN` | interfejs łącza: `128` = Ethernet, `0` = port szeregowy 🔶 |
| `PortNrN`, `HMIPortNrN` | port szeregowy (np. COM2) / `255` przy Ethernet 🔶 |
| `baudN`, `databitsN`, `stopbitsN`, `parityN` | parametry portu szeregowego (np. 9600, 7, 1, `2` = Even 🔶) |
| `EthIP` | IP panelu jako liczba bez znaku, big-endian: `168496141` = 10.11.12.13 ✅ |

## Elementy, których nie ruszać ręcznie

`@@blob32 MeMeCode` (DIAScreen zmienia go przy każdym zapisie, ale akceptuje stary), `GUID`, `thumbnail.bin`.
Przy ponownym zapisie DIAScreen sam zmienia też m.in. `SmtpHWInf`/`FTPHWInf` (-1 → 255) i `*SyncConfirm` – to normalne.
