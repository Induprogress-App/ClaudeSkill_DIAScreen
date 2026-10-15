# Format projektu DIAScreen (.dpa) – ustalenia

Narzędzie: `dpa_tool.py` (instrukcja: README.md). Znaczenie parametrów elementów: PARAMETRY.md.
Sprawdzone na projektach dla panelu AX-8 (`PanelSeries=AX-8 series`, `Version=6.6.2.48`).

## Kontener `.dpa`
| Część | Opis |
|---|---|
| miniatura | BMP 164×123, 24 bity: nagłówek `BM` + `0E000000` + `PDAB` + `36000000`, potem `BITMAPINFOHEADER` i piksele (wiersz 492 B). `biSizeImage` = 60544 obejmuje też 28 B trailera |
| trailer (28 B) | `FFFFFFFF 0600 0600 0200 3000 00000000 0200 0020 14000000 "ABPD"` – `0x20000002` = `ModelName` z projektu |
| strumień gzip | od końca trailera do końca pliku; nagłówek `1F8B 0800 00000000 00 0B`, deflate zlib poziom 6 (domyślny) – przy tych ustawieniach Python odtwarza go bajt w bajt |

Po rozpakowaniu gzip:
```
"Delta-HMI Screen Editor DOP V1010\t   "   nagłówek (37 B)
uint32 LE                                  długość treści
treść XOR 0x64                             tekst INI, końce linii CRLF, z wstawkami binarnymi
```
Brak sumy kontrolnej treści poza CRC gzip. Pole `MeMeCode` DIAScreen zmienia przy każdym zapisie, ale plik
z „nieaktualnym” `MeMeCode` (po edycji narzędziem) otwiera się i kompiluje poprawnie (sprawdzone 2026-10-14).

## Treść (INI)
Sekcje w kolejności (pusty projekt): `[Application]`, `[Multi-Language]`, `[Global-Camera]`, `[Event-Trigger]`,
`[Global-Keypad]`, `[Recipe]`, `[Recipe32]`, `[EnhanceRcp]`, `[Installment]`, `[Ethernet]`, `[Modbus_TCP_Server]`,
`[Modbus_COM_Server]`, `[WEB_OUTPUT]`, `[SIP]`, `[ExtendedMem]`, `[UerDefindDataTypeEnd]`, `[RemoteCtrl]`, `[VNCCtrl]`,
`[RTC]`, `[LOG]`, `[FTP]`, `[FTPFile]`, `[AdvDataExchange]`, `[AdvDataExchangeEnd]`, `[LuaData]`, `[ExtraZA_ZGSection]`,
ekrany, `[SubMacro]`, `[Global_Auxkey]`, `[Alarm]`, `[History]`, `[NewTextBank]`, `[Tag]`, `[100_SRAM_DATA]`,
`[SysMessage]`, `[Picture]`, `[Background]`, `[DIATag]`, `[DeviceTable]`, `[MQTTFile]`, `[END]`.

Brak licznika ekranów ani elementów – ekrany i elementy następują po sobie. Ekran: `[Screen]`, `[AuxKeyElement]`,
potem elementy `[Element]`, każdy z sekcjami `[State]`. Ostatni ekran kończy się na `[SubMacro]`.

### Wstawki binarne
| Zapis w treści | Gdzie | Reprezentacja w plikach tekstowych |
|---|---|---|
| `KLUCZ=n` CRLF + n bajtów UTF-16LE zakończonych `00 00` | klucze z `Len` w nazwie (`wTextLen`, `wDescTextLen0`, `UnitTextLen0`, …) | `@@u16 KLUCZ="tekst"` (JSON) |
| `KLUCZ=n` CRLF + n surowych bajtów | `SysKeyPwd` (8 B), inne `…Len` nie-UTF-16 | `@@lenhex KLUCZ=hex` |
| `KLUCZ=` + uint32 LE n + n bajtów | `MeMeCode` (176 B) | `@@blob32 KLUCZ=hex` |
| linia `[100_SRAM_DATA]`, potem uint32 LE n + baza SQLite | baza: hasła, sieć, SMTP, kontakty | `@@sqlite sram_data.db` |
| `<EXTENT>LuaXmlFileLen=n` CRLF + n bajtów XML | `[LuaData]` | `@@luaxml …=lua/_lua_files.xml` |
| inne linie z bajtami spoza ASCII | `CustomerPalette` (16 × 4 B), `[SysMessage]` + `00 00 00` | `@@hex hex` |

Po każdej wstawce następuje CRLF. Klucz z liczbą traktowany jest jako wstawka tylko wtedy, gdy ma `Len` w nazwie
(albo jest na liście wyjątków) i dane za nim nie są zwykłymi liniami tekstu – np. `AccountLen=16` to zwykła wartość.

### Lua
```
<EXTENT>LuaXmlFileLen=372
<?xml version="1.0" encoding="utf-8" ?>
<file name="Main" protect="0" password="" version="2" path="">
    <content>BASE64 kodu Lua (UTF-8, LF)</content>
</file>
<AddressList />
```
`LuaXmlFileLen` = długość XML w bajtach razem z końcowym CRLF. Narzędzie zapisuje każdy `<content>` do
`lua/<name>.lua`, w XML zostawia `<content>@@lua:<name>.lua</content>`. Base64 bez łamania linii. Projekt z kilkoma
programami Lua nie był jeszcze sprawdzony (zakładane: kilka elementów `<file>`).

## Zachowanie DIAScreen
- Edycja `X`, `IntNum`, tekstu pola i kodu Lua poza DIAScreen → projekt otwiera się i kompiluje, a po ponownym
  zapisie w DIAScreen zmiany zostają (sprawdzone 2026-10-14).
- Przy zapisie DIAScreen sam zmienia: `MeMeCode`, `SmtpHWInf`/`FTPHWInf` (-1 → 255), `BuiltInAXTagSyncConfirm`,
  `AutoSyncDIATagOptimize`, `DIATagSyncConfirm` (0 → 1), znaczniki czasu w bazie SQLite. `GUID` w `[Application]`
  zmienia się przy „Zapisz jako”.

## Niezbadane
- Obrazy (`[Picture] Size=n`, `[Background] Size=n` – przy n > 0 najpewniej n bajtów danych).
- Makra ekranów (`OpenMacroLen` itd. > 0), `[SubMacro]` z treścią, receptury, alarmy z wpisami, tagi.
- Projekty z wieloma językami (sufiksy `…0`, `…1` w kluczach czcionek i tekstów).
