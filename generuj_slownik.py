"""Generuje slownik parametrow i wzorce elementow skilla z projektow testowych (_ns_tests/work/*).

Uzycie: python generuj_slownik.py KATALOG1 [KATALOG2 ...]   (katalogi po decode, pierwszy = najwazniejszy wzorzec)
Wynik:  diascreen/dane/parametry.csv, diascreen/dane/elementy.csv, diascreen/dane/wzorce/T_S.txt
Do wynikow trafiaja tylko liczby i wartosci techniczne - adresy i teksty z projektow sa zastepowane.
Opisy kluczy: OPISY ponizej (pewnosc: ok = potwierdzone, ? = przypuszczenie).
"""
import collections
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "diascreen"))
import dpa_tool as d  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diascreen", "dane")

# nazwy rodzajow (z opisow elementow w DIAScreen); "?" = niepotwierdzone
NAZWY = {
    (1, 1): "Set On", (1, 2): "Set Off", (1, 3): "Momentary", (1, 4): "Maintained",
    (1, 5): "Multistate Button", (1, 6): "Set Value", (1, 7): "Set Constant",
    (1, 8): "Increment", (1, 9): "Decrement", (1, 10): "Goto Screen", (1, 11): "Goto Screen 2?",
    (1, 14): "Multiple Actions", (2, 1): "Multistate Indicator", (3, 2): "Differential",
    (5, 1): "Numeric Display", (5, 2): "Character Display", (5, 3): "Date Display", (5, 4): "Time Display",
    (6, 1): "Numeric Entry", (6, 2): "Character Entry",
    (10, 1): "Line", (10, 2): "Rectangle", (10, 6): "Text",
    (11, 1): "Alarm History Table", (11, 2): "Active Alarm List",
    (12, 1): "System Date and Time", (12, 8): "Screen Capture", (12, 9): "Remove Storage",
    (12, 12): "Language Change", (19, 2): "ListBox", (19, 9): "Drop-down Menu", (19, 10): "Recipe Viewer",
    (15, 4): "Keypad Key", (23, 1): "Embedded Subscreen", (23, 5): "Invisible Frame",
}
# parametry, ktore trzeba podac przy dodawaniu elementu (klucz w pliku)
WYMAGANE = {
    (1, 1): ["WriteVar"], (1, 2): ["WriteVar"], (1, 3): ["WriteVar"], (1, 4): ["WriteVar"],
    (1, 5): ["WriteVar"], (1, 6): [],  # wzorzec Set Value bez adresu - brak kluczy Write*
    (1, 7): ["WriteVar", "SetValue"],
    (1, 8): ["WriteVar"], (1, 9): ["WriteVar"], (1, 10): ["GoToScreenID"], (1, 11): ["GoToScreenID"],
    (2, 1): ["ReadVar"], (5, 1): ["ReadVar"], (5, 2): ["ReadVar"], (6, 1): ["WriteVar"],
    (6, 2): ["WriteVar"], (10, 6): ["wTextLen0"],
}
# zawsze sensowne do ustawienia (poza wyliczonymi z roznic miedzy elementami)
ZAWSZE = ["X", "Y", "Width", "Height", "VisibleVar"]
POMIN_OPC = {"nPartsID", "wDescTextLen#", "Type", "SubType", "GroupID", "EventID", "RelatedFileBrowserPartID"}

# opisy kluczy po normalizacji (# = numer: jezyk, kolumna, punkt gradientu...)
OPISY = {
    # element - wspolne
    "Type": ("rodzaj elementu (grupa), patrz elementy.csv", "ok"),
    "SubType": ("podrodzaj elementu, patrz elementy.csv", "ok"),
    "X": ("pozycja X lewego gornego rogu [px]", "ok"), "Y": ("pozycja Y [px]", "ok"),
    "Width": ("szerokosc [px]", "ok"), "Height": ("wysokosc [px]", "ok"),
    "nPartsID": ("numer elementu na ekranie (unikalny, kolejny)", "ok"),
    "wDescTextLen#": ("opis elementu (Element Description), # = jezyk", "ok"),
    "Style": ("styl: Numeric Display 2 = Sunken; Multistate 0 = zwykly, 3 = Invisible (bez tla, widac tekst/obraz); Text 0 = z tlem (FgColor), 32768 = przezroczysty", "ok"),
    "BorderColor": ("kolor ramki (COLORREF R+G*256+B*65536)", "ok"),
    "AutoResizeByText": ("automatyczny rozmiar wg tekstu", "ok"),
    "AutoResizeMargin": ("margines automatycznego rozmiaru", "ok"),
    "CombineType": ("laczenie elementow", "?"), "Level": ("poziom (warstwa)", "?"),
    "antialiasing": ("wygladzanie krawedzi", "?"), "bFreeze": ("zablokowanie pozycji w edytorze", "?"),
    "RelatedFileBrowserPartID": ("powiazana przegladarka plikow (-1 = brak)", "?"),
    "EnableShadowEffect": ("cien elementu wl/wyl", "ok"), "ShadowColor": ("kolor cienia", "ok"),
    "ShadowOffsetX": ("przesuniecie cienia X", "ok"), "ShadowOffsetY": ("przesuniecie cienia Y", "ok"),
    "ShadowBlurRadius": ("rozmycie cienia", "ok"),
    "opacity": ("przezroczystosc", "?"), "nAngle": ("kat obrotu", "?"),
    "GroupID": ("grupa elementow (sekcja [Group] ekranu); 0/brak = bez grupy", "?"),
    "EventID": ("zdarzenie powiazane", "?"), "EventName": ("nazwa zdarzenia", "?"),
    # adresy
    "ReadVar": ("adres odczytu: None, $N, $N.b, LACZE@Application.Zmienna, {LACZE}st@...", "ok"),
    "ReadLink": ("lacze adresu odczytu (1 przy adresie)", "?"), "ReadMemType": ("typ pamieci adresu odczytu", "?"),
    "WriteVar": ("adres zapisu (skladnia jak ReadVar)", "?"), "WriteLink": ("lacze adresu zapisu", "?"),
    "WriteMemType": ("typ pamieci adresu zapisu", "?"),
    "VisibleVar": ("bit widocznosci elementu (None = zawsze widoczny)", "?"),
    "VisibleLink": ("lacze bitu widocznosci", "?"),
    "VisibleCondition": ("warunek widocznosci: 1 = widoczny przy ON, 0 = przy OFF", "?"),
    "InterLockVar": ("bit blokady dzialania", "?"), "InterLockLink": ("lacze bitu blokady", "?"),
    "InterLockLevel": ("stan bitu blokady zezwalajacy", "?"), "InterLockViewMode": ("wyglad zablokowanego elementu", "?"),
    "TriggerVar": ("bit ustawiany po wpisaniu/wykonaniu", "?"), "TriggerLink": ("lacze bitu Trigger", "?"),
    "OffsetWriteVar": ("adres przesuniecia zapisu (akcja)", "?"),
    "OffsetWriteMemType": ("typ pamieci przesuniecia", "?"),
    "OffsetMemLen": ("dlugosc danych przesuniecia", "?"), "OffsetMemFmt": ("format danych przesuniecia", "?"),
    # dane
    "MemLen": ("typ danych: 0 = Bit (adres $N.b), 1 = Word ($N), 2 = DWord, 6 = QWord - musi pasowac do adresu", "ok"),
    "MemFmt": ("format danych: 1 = Signed Decimal, 2 = Unsigned Decimal (inne: hex, BCD, float - nieustalone)", "ok"),
    "IntNum": ("liczba cyfr calkowitych", "ok"), "DotNum": ("liczba miejsc po przecinku", "ok"),
    "LeadingZero": ("zera wiodace", "?"), "Roundoff": ("zaokraglanie", "ok"),
    "GainValue": ("wzmocnienie (Gain)", "ok"), "OffsetValue": ("przesuniecie (Offset)", "ok"),
    "OffsetLength": ("Offset length: 0 = Same value unit", "ok"),
    "DisplayDotVar": ("adres liczby miejsc po przecinku (None = stala)", "ok"),
    "DisplayDotVariation": ("miejsca po przecinku ze stalej/adresu", "?"),
    "HiDwordFirst": ("kolejnosc slow DWord", "?"), "HiWordFirst": ("kolejnosc slow", "?"),
    "WordSwap": ("zamiana slow", "?"), "ByteSwap": ("zamiana bajtow", "?"),
    "StringLen": ("dlugosc tekstu w znakach", "?"), "StringLeadingZero": ("zera wiodace tekstu", "?"),
    "ExtendedAscii": ("rozszerzone ASCII", "?"),
    "MinValue": ("minimalna wartosc wpisu", "?"), "MaxValue": ("maksymalna wartosc wpisu", "?"),
    "MinMaxVariation": ("zakres ze stalych/adresu", "?"),
    "ShowRange": ("pokaz zakres przy wpisie", "?"), "ShowOverRange": ("sygnalizacja przekroczenia", "?"),
    "RangeFontColor": ("kolor podpowiedzi zakresu", "?"), "RangeFontSize": ("rozmiar podpowiedzi zakresu", "?"),
    "DispAsterisk": ("wyswietlanie gwiazdek (haslo)", "?"),
    "SetValue": ("wartosc zapisywana (Set Constant / akcja)", "?"),
    "StepValue": ("krok (Increment/Decrement)", "ok"), "LimitValue": ("granica (Decrement: dolna, Increment: gorna)", "ok"),
    "PushTime": ("czas przytrzymania", "?"), "ImpulsiveTime": ("czas impulsu", "?"),
    "WriteReadImmediately": ("odczyt zaraz po zapisie", "?"),
    "ConFirmWindow": ("potwierdzenie: 0 = brak, 1 = systemowe Yes/No, 2 = systemowe + ponowne logowanie, 3 = wlasny ekran (ConfirmScreenID)", "ok"), "ConfirmScreenID": ("ekran potwierdzenia (typu Confirmation screen) przy ConFirmWindow=3", "ok"),
    "ConfirmScreenName": ("nazwa ekranu potwierdzenia (zwykla linia ASCII)", "ok"),
    "KeypadScreenID": ("ekran klawiatury", "?"), "UseCustKeypad": ("wlasna klawiatura", "?"),
    "KeyPadLeft": ("klawiatura - pozycja", "?"), "KeyPadTop": ("klawiatura - pozycja", "?"),
    "KeyPadRight": ("klawiatura - pozycja", "?"), "KeyPadBottom": ("klawiatura - pozycja", "?"),
    "KPBkgndColor#": ("kolor tla klawisza klawiatury #", "?"), "KPFontColor#": ("kolor czcionki klawisza #", "?"),
    "KPFontName#-#": ("czcionka klawisza (klawisz-jezyk)", "?"), "KPFontSize#-#": ("rozmiar czcionki klawisza", "?"),
    "wKPFStringLen#-#": ("napis klawisza (klawisz-jezyk)", "?"),
    "Order": ("kolejnosc wprowadzania", "?"), "ReadOnly": ("tylko odczyt", "?"),
    "HotKey": ("skrot klawiszowy", "?"), "ModifierKey": ("modyfikator skrotu", "?"),
    "SetLowSecurity": ("niski poziom zabezpieczenia", "?"), "OffVoice": ("bez dzwieku", "?"),
    # ekrany w elementach
    "GoToScreenID": ("ekran docelowy (Goto Screen)", "?"), "GoToScreenName": ("nazwa ekranu docelowego", "?"),
    "CloseScreen": ("zamknij biezacy (pod)ekran", "?"), "SelectScreen": ("wybor ekranu", "?"),
    "SubScreenVar": ("adres numeru podekranu (Embedded Subscreen)", "?"), "SubScreenLink": ("lacze", "?"),
    # jednostki
    "ShowUnit": ("pokaz jednostke", "?"), "UnitTextLen#": ("tekst jednostki, # = jezyk", "?"),
    "UnitFontName#": ("czcionka jednostki", "?"), "UnitFontSize#": ("rozmiar czcionki jednostki", "?"),
    "UnitFontColor": ("kolor jednostki", "?"), "UnitBold": ("jednostka pogrubiona", "?"),
    "UnitItalic": ("jednostka kursywa", "?"), "UnitUnderline": ("jednostka podkreslona", "?"),
    "UnitDirection": ("polozenie jednostki", "?"), "UnitType": ("rodzaj przeliczenia jednostek", "?"),
    "UnitSrc": ("jednostka zrodlowa", "?"), "UnitDisplay": ("jednostka wyswietlana", "?"),
    "UnitSrcVar": ("adres jednostki zrodlowej", "?"), "UnitDisplayVar": ("adres jednostki wyswietlanej", "?"),
    "UnitPercent": ("przeliczenie procentowe", "?"), "UnitPercent#Var": ("granice przeliczenia %", "?"),
    "UnitCustom#Var_#": ("wspolczynniki wlasnego przeliczenia", "?"),
    "ConvertConstByUnit": ("przeliczanie stalych jednostka", "?"),
    "BackupUnitSrc": ("kopia jednostki", "?"), "BackupUnitDisplay": ("kopia jednostki", "?"),
    # makra
    "AfterExecMacroLen": ("makro po wykonaniu (binarne @@hex)", "?"),
    "BeforeExecMacroLen": ("makro przed wykonaniem (binarne)", "?"),
    "ButtonOnMacroLen": ("makro przy ON (binarne)", "?"), "ButtonOffMacroLen": ("makro przy OFF (binarne)", "?"),
    "LuaParam#": ("parametr Lua", "?"),
    # akcje (1/14 Multiple Actions, sekcje [PressedAction]/[ReleaseAction])
    "ActionID": ("numer akcji", "?"), "WaitEventFinish": ("czekaj na zakonczenie", "?"),
    "WaitTime": ("czas oczekiwania akcji", "?"), "Variation": ("zrodlo wartosci (stala/adres)", "?"),
    # date/time
    "DataFmt": ("format daty", "?"), "DateFmt": ("format daty", "?"), "TimeFmt": ("format czasu", "?"),
    # wyglad
    "ShowBorder": ("pokaz ramke", "?"), "BorderType": ("rodzaj ramki", "?"), "BdrDashType": ("ramka przerywana", "?"),
    "BdrTwinkleSpd": ("miganie ramki", "?"), "EnableBorderMem": ("ramka z adresu", "?"),
    "BDRStartColor": ("kolor ramki gradient", "?"), "BDRMidColor": ("kolor ramki gradient", "?"),
    "BDREndColor": ("kolor ramki gradient", "?"), "LineStyle": ("styl linii", "?"),
    "RoundRadius": ("promien zaokraglenia", "?"), "EnableCustomRadius": ("wlasny promien", "?"),
    "RadOring": ("zaokraglenie", "?"), "FillPatternStyle": ("wzor wypelnienia", "?"),
    "GradFillMode": ("tryb gradientu", "?"), "GradFillStartColor": ("kolor poczatku gradientu", "?"),
    "GradFillEndColor": ("kolor konca gradientu", "?"), "LnrGradAngle": ("kat gradientu", "?"),
    "FillStyle": ("styl wypelnienia", "?"), "SmoothFont": ("wygladzanie czcionki", "ok"),
    "ShowTempDraw": ("podglad w edytorze", "?"), "ShowFrame": ("ramka", "?"),
    "ImageStretch": ("rozciaganie obrazu", "?"), "Penetrate": ("przepuszczanie klikniec", "?"),
    "SizeVary": ("zmiana rozmiaru z adresu", "?"), "PosVary": ("zmiana pozycji z adresu", "?"),
    "ColorVary": ("zmiana koloru z adresu", "?"),
    "LeftVar": ("adres pozycji X", "?"), "LeftLink": ("lacze", "?"), "TopVar": ("adres pozycji Y", "?"),
    "TopLink": ("lacze", "?"),
    # tabele / listy
    "ColNum#": ("numer kolumny", "?"), "ColWidth#": ("szerokosc kolumny #", "?"), "ColumnName#": ("nazwa kolumny #", "?"),
    "ColWidthOfName": ("szerokosc kolumny nazwy", "?"), "ColWidthOfNo": ("szerokosc kolumny numeru", "?"),
    "TotalColumn": ("liczba kolumn", "?"), "GlobalWidth": ("szerokosc kolumn", "?"),
    "EnableCol#": ("kolumna # widoczna", "?"), "DisplayOrder#": ("kolejnosc kolumny #", "?"),
    "TitleTextLen#-#": ("naglowek kolumny (kolumna-jezyk)", "?"), "TitleAlignment": ("wyrownanie naglowka", "?"),
    "TitleBkgColor": ("tlo naglowka", "?"), "TitleFontColor": ("kolor naglowka", "?"), "TitleHeight": ("wysokosc naglowka", "?"),
    "FieldFontSize": ("rozmiar czcionki pol", "?"), "GridColor": ("kolor siatki", "?"),
    "ShowGridLine": ("linie siatki", "?"), "ShowGrid": ("siatka", "?"), "ShowGridRow": ("linie wierszy", "?"),
    "RowColor": ("kolor wiersza", "?"), "RowAlternateColor": ("kolor co drugiego wiersza", "?"),
    "RowColorMode": ("tryb kolorow wierszy", "?"), "RowSelectColor": ("kolor zaznaczenia", "?"),
    "RowHoverColor": ("kolor po najechaniu", "?"), "RowNormalColor": ("kolor wiersza normalnego", "?"),
    "RowActiveColor": ("kolor alarmu aktywnego", "?"), "RowAckColor": ("kolor alarmu potwierdzonego", "?"),
    "SearchMatchTextColor": ("kolor wyniku wyszukiwania", "?"),
    "MaxItemCount": ("maks. liczba pozycji", "?"), "PageLines": ("liczba wierszy na strone", "?"),
    "ShowDate": ("kolumna daty", "?"), "ShowTime": ("kolumna czasu", "?"), "ShowAlarmNumber": ("numer alarmu", "?"),
    "DefaultSortColID": ("domyslne sortowanie", "?"), "SortUsingHeader": ("sortowanie naglowkiem", "?"),
    "Print": ("drukowanie", "?"), "FunctionKeyW": ("szerokosc klawisza funkcyjnego", "?"),
    "FunctionKeyH": ("wysokosc klawisza funkcyjnego", "?"), "FunctionKeyPartID#": ("klawisz funkcyjny #", "?"),
    "Version": ("wersja zapisu elementu", "?"), "KeypadType": ("rodzaj klawisza (Keypad Key): 3 = znak ASCII", "?"), "ASCIIValue#": ("kod znaku klawisza: 13 = Enter (OK), 27 = Esc (Cancel)", "?"), "ShowAll": ("pokaz wszystko", "?"),
    "NoMessage": ("bez komunikatow", "?"), "NotShowAlmUnlock": ("bez odblokowania alarmow", "?"),
    "IgnoreHistOP": ("pomijanie operacji historii", "?"), "MaxDisplayDaysOfData": ("dni danych", "?"),
    "EnableGroupID": ("filtr grupy", "?"), "EnableGroupIDFilter": ("filtr grupy", "?"),
    "GroupIDValue": ("grupa", "?"), "GroupIDVar": ("adres grupy", "?"), "GroupIDVariation": ("grupa ze stalej/adresu", "?"),
    "SelectRowVar": ("adres zaznaczonego wiersza", "?"), "SelectRowTriggerVar": ("bit zaznaczenia wiersza", "?"),
    "SelectColVar": ("adres zaznaczonej kolumny", "?"), "SelectColTriggerVar": ("bit zaznaczenia kolumny", "?"),
    "ScrollCtrlVarType": ("przewijanie z adresu", "?"),
    "ListEnRcpGroupVar": ("grupa receptur", "?"), "ListEnRcpGroupLink": ("lacze", "?"),
    "ListEnRcpNoWriteVar": ("adres numeru receptury (ENRCPNO)", "?"), "ListEnRcpTypeVar": ("typ listy receptur", "?"),
    "DataSourceType": ("zrodlo danych listy", "?"), "OptionsDisplayItem": ("liczba widocznych opcji", "?"),
    "OptionsHeight": ("wysokosc opcji", "?"), "OptionsWidth": ("szerokosc opcji", "?"),
    "OptionsSetWidth": ("wlasna szerokosc opcji", "?"), "OptionsBKColor": ("tlo opcji", "?"),
    "OptionsSelectColor": ("kolor wybranej opcji", "?"), "OptionsFillStyle": ("wypelnienie opcji", "?"),
    "ExpandDirection": ("kierunek rozwijania", "?"), "VariableFieldWidth": ("zmienna szerokosc pola", "?"),
    "AccessType": ("rodzaj dostepu / nosnik", "?"), "AccountOrder": ("kolejnosc kont", "?"),
    "ShowUserLevel": ("poziom uzytkownika", "?"), "LangValue": ("jezyk do ustawienia (Language Change)", "?"),
    "DisplayDataFormat": ("format wyswietlania", "?"), "DisplayTargetID": ("element docelowy", "?"),
    "CancelActBit": ("bit anulowania", "?"), "Active": ("aktywny", "?"), "InstOrder": ("kolejnosc", "?"),
    "ShowInstName": ("pokaz nazwe", "?"),
    # wykresy / skale (Differential itp.)
    "MainScale": ("skala glowna", "?"), "SubScale": ("skala pomocnicza", "?"), "ScaleColor": ("kolor skali", "?"),
    "ScaleDock": ("polozenie skali", "?"), "ScaleFontColor": ("kolor opisu skali", "?"),
    "ScaleFontSize": ("rozmiar opisu skali", "?"), "ScaleStyle": ("styl skali", "?"), "ScaleWidth": ("szerokosc skali", "?"),
    "BarStyle": ("styl paska", "?"), "HLimitValue": ("gorna granica", "?"), "LLimitValue": ("dolna granica", "?"),
    "HRegionColor": ("kolor powyzej granicy", "?"), "LRegionColor": ("kolor ponizej granicy", "?"),
    "ShowTarget": ("pokaz wartosc zadana", "?"), "TargetValue": ("wartosc zadana", "?"),
    "TargetColor": ("kolor wartosci zadanej", "?"), "TargetStyle": ("styl wartosci zadanej", "?"),
    "StateColor": ("kolor stanu", "?"),
    # stan [State]
    "Value": ("wartosc stanu (stan 0 nie ma klucza)", "ok"), "StateIndex": ("numer stanu", "?"),
    "wTextLen#": ("tekst w stanie, # = jezyk (w ekranie: nazwa ekranu)", "ok"),
    "Base#TextLen#": ("kopia dlugiego tekstu w base64 (UTF-16); po zmianie tekstu niezgodna", "?"),
    "FontName#": ("czcionka, # = jezyk", "ok"), "FontSize#": ("rozmiar czcionki, # = jezyk", "ok"),
    "FontRatio#": ("proporcja czcionki [%]", "?"), "FontColor": ("kolor czcionki (COLORREF, 255 = czerwony)", "ok"),
    "FontBold": ("pogrubienie", "ok"), "FontItalic": ("kursywa", "ok"), "FontUnderline": ("podkreslenie", "ok"),
    "FontAlign": ("wyrownanie tekstu, suma: poziomo 1 lewo/2 srodek/4 prawo + pionowo 16 gora/32 srodek/64 dol (34 = srodek, 17 = lewy gorny, 68 = prawy dolny)", "ok"),
    "FgColor": ("kolor wypelnienia elementu (Foreground color)", "ok"), "BgColor": ("w ekranie: kolor tla ekranu; w stanie: kolor tla", "ok"),
    "Twinkles": ("miganie w tym stanie: 1 = Blink ON", "ok"),
    "BgFillType": ("wypelnienie tla: 6 = gradient", "?"), "BgFillStyle": ("styl gradientu: 1 = Mono", "?"),
    "BgFillColor": ("kolor gradientu tla", "ok"), "BgFillEndColor": ("koniec gradientu tla", "?"),
    "BgFillStopPos#": ("punkt gradientu # [%], -1 = nieuzywany", "?"), "BgFillStopColor#": ("kolor punktu #", "?"),
    "BgFillAngleArg": ("kat gradientu", "?"), "BgFillXArg": ("srodek gradientu X", "?"), "BgFillYArg": ("srodek gradientu Y", "?"),
    "FgFillType": ("wypelnienie: 1 = Solid color, 6 = Mono gradient", "ok"), "FgFillStyle": ("styl gradientu", "?"),
    "FgFillColor": ("kolor wypelnienia (jak FgColor)", "ok"), "FgFillEndColor": ("koniec gradientu", "?"),
    "FgFillStopPos#": ("punkt gradientu #", "?"), "FgFillStopColor#": ("kolor punktu #", "?"),
    "FgFillAngleArg": ("kat gradientu", "?"), "FgFillXArg": ("srodek X", "?"), "FgFillYArg": ("srodek Y", "?"),
    "BorderFillType": ("wypelnienie ramki", "?"), "BorderFillStyle": ("styl", "?"), "BorderFillColor": ("kolor", "?"),
    "BorderFillEndColor": ("koniec gradientu", "?"), "BorderFillStopPos#": ("punkt #", "?"),
    "BorderFillStopColor#": ("kolor punktu #", "?"), "BorderFillAngleArg": ("kat", "?"),
    "BorderFillXArg": ("srodek X", "?"), "BorderFillYArg": ("srodek Y", "?"), "BorderStyle": ("styl ramki stanu", "?"),
    "PIB Name": ("biblioteka obrazow, np. $100_Action Button", "ok"), "Picture Name": ("numer obrazu w bibliotece projektu", "?"),
    "PictureAlign": ("wyrownanie obrazu, kodowanie jak FontAlign", "ok"), "PictureCoordX": ("pozycja obrazu X", "?"),
    "PictureCoordY": ("pozycja obrazu Y", "?"), "PictureWidth": ("szerokosc obrazu", "?"),
    "PictureHeight": ("wysokosc obrazu", "?"), "PictureOffset": ("przesuniecie obrazu", "?"),
    "PictureStretch": ("rozciaganie obrazu", "?"), "StretchMode": ("tryb dopasowania obrazu (0/1)", "?"),
    "UsePictureCoord": ("wlasna pozycja obrazu", "?"), "TransColor": ("kolor przezroczysty", "?"),
    "TransEffect": ("przezroczysty kolor obrazu wl (kolor w TransColor)", "?"),
    # ekran [Screen]
    "VER": ("wersja zapisu ekranu (16)", "?"), "ID": ("numer ekranu (w akcji: numer akcji)", "ok"),
    "wTextLen": ("nazwa ekranu", "ok"), "wScreenDESCTextLen#": ("opis ekranu", "ok"),
    "DocSizeX": ("szerokosc ekranu [px]", "ok"), "DocSizeY": ("wysokosc ekranu [px]", "ok"),
    "PanelSizeX": ("rozdzielczosc panelu X", "ok"), "PanelSizeY": ("rozdzielczosc panelu Y", "ok"),
    "ScreenType": ("typ ekranu: 0 = zwykly, 6 = Confirmation screen (z IsConfirmScreen=1)", "?"), "IsSubScreen": ("podekran (okno)", "?"),
    "IsExternalScreen": ("ekran zewnetrzny", "?"), "IsKeypadScreen": ("ekran klawiatury", "?"),
    "IsConfirmScreen": ("ekran potwierdzenia (Confirmation screen), 1 = tak", "ok"), "IsPrintTypeScreen": ("ekran wydruku", "?"),
    "IsTemplateScreen": ("ekran szablonu", "?"), "IsUseFrame": ("ramka okna", "?"),
    "IsUseTitleBar": ("pasek tytulu okna", "?"), "HideSubScreenMinimizedBtn": ("ukryj przycisk minimalizacji", "?"),
    "IsScreenRotate": ("obrot ekranu", "?"), "wTitleTextLen#": ("tytul okna", "?"),
    "TitleTextFontName#": ("czcionka tytulu", "?"), "TitleTextFontSize#": ("rozmiar tytulu", "?"),
    "TitleTextFontColor": ("kolor tytulu", "?"), "RefreshRate": ("czestotliwosc odswiezania", "?"),
    "IsPrintScreen": ("drukowanie ekranu", "?"), "HardCopyLeft": ("obszar wydruku", "?"),
    "HardCopyTop": ("obszar wydruku", "?"), "HardCopyRight": ("obszar wydruku", "?"),
    "HardCopyBottom": ("obszar wydruku", "?"), "BaseScreenID": ("ekran bazowy (tlo), 0 = brak", "?"),
    "ScreenAction": ("akcja ekranu", "?"), "Hidden": ("ekran ukryty", "?"),
    "CycleMacroDelayTime": ("okres makra cyklicznego [ms]", "?"), "EnableCycleMacro": ("makro cykliczne wl", "?"),
    "ScreenLockVar": ("bit blokady ekranu", "?"), "ScreenProtect": ("ochrona ekranu", "?"),
    "ScreenPassword": ("haslo ekranu", "?"), "OpenMacroLen": ("makro otwarcia (binarne)", "?"),
    "CloseMacroLen": ("makro zamkniecia (binarne)", "?"), "CycleMacroLen": ("makro cykliczne (binarne)", "?"),
    "SubScreenX": ("pozycja podekranu X", "?"), "SubScreenY": ("pozycja podekranu Y", "?"),
    "CenterSubScreen": ("podekran na srodku", "?"), "AutoCloseTime": ("automatyczne zamkniecie podekranu", "?"),
}

ZAKRES = {"S": "ekran", "E": "element", "T": "stan", "[PressedAction]": "akcja", "[ReleaseAction]": "akcja"}
DOMYSLNE_TEKSTY = {"No", "Trigger", "Message", "Ack", "Recovery", "Frequency", "Group", "Operator", "Arial",
                   "Numeric Keypad", "CLR", "DEL", "Enter", "ASCII-KEY", "ALT", "ENT", "ENRCPNO", "ENRCPNONAME"}
NUM = re.compile(r"^-?\d+(\.\d+)?$")


def norm(k):
    return re.sub(r"\d+", "#", k)


def bezpieczna(v):
    """Wartosc do slownika: liczby i techniczne stale tak, adresy i teksty - zamaskowane."""
    if NUM.match(v) or v in ("None", "") or v in DOMYSLNE_TEKSTY:
        return v
    if "@" in v or v.startswith("$") or v.startswith("{"):
        return "<adres>"
    return "<tekst>"


def linie_kv(lines):
    """(sekcja, klucz, wartosc) dla linii elementu; pomija dane binarne i base64 po Base64TextLen."""
    sec, skip = "E", False
    for l in lines[1:]:
        if l.startswith("["):
            sec, skip = ("T" if l == "[State]" else l), False
            continue
        if skip and re.fullmatch(r"[A-Za-z0-9+/]+=*", l):
            continue  # dane base64 po Base64TextLen
        kv = d._kv(l)
        if kv is None:
            continue
        skip = kv[0].startswith("Base64TextLen")
        yield sec, kv[0], kv[1]


def main(dirs):
    stat = collections.defaultdict(collections.Counter)   # (zakres, klucz) -> wartosci
    typy = collections.defaultdict(set)
    by_type = collections.defaultdict(list)
    for proj in dirs:
        for s in d.load_screens(proj):
            head = s.lines[:s.lines.index("[AuxKeyElement]")] if "[AuxKeyElement]" in s.lines else []
            for l in head:
                kv = d._kv(l)
                if kv:
                    stat[("S", norm(kv[0]))][bezpieczna(kv[1])] += 1
            for e in s.elements:
                by_type[e.type].append((proj, e))
                for sec, k, v in linie_kv(e.lines):
                    stat[(sec, norm(k))][bezpieczna(v)] += 1
                    typy[(sec, norm(k))].add(e.type)
    os.makedirs(os.path.join(OUT, "wzorce"), exist_ok=True)

    # parametry.csv
    n_types = len(by_type)
    rows = []
    for (sec, k), c in sorted(stat.items(), key=lambda x: (list(ZAKRES).index(x[0][0]), x[0][1].lower())):
        t = typy.get((sec, k), set())
        ts = "*" if sec == "S" or len(t) >= n_types * 0.9 else " ".join("%d/%d" % x for x in sorted(t))
        vals = [v for v, _ in c.most_common(8)]
        opis, pew = OPISY.get(k, ("", "?"))
        rows.append([ZAKRES[sec], k, ts, vals[0], "|".join(vals[:8]), opis, pew])
    with open(os.path.join(OUT, "parametry.csv"), "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(["zakres", "klucz", "typy", "domyslna", "wartosci", "opis", "pewnosc"])
        w.writerows(rows)
    print("parametry.csv:", len(rows), "kluczy, bez opisu:",
          sorted({r[1] for r in rows if not r[5]}))

    # elementy.csv + wzorce
    erows = []
    for t, items in sorted(by_type.items()):
        name = NAZWY.get(t, "Type %d/%d" % t)
        varying = collections.Counter()
        for k in {norm(k) for _, e in items for k in e.props}:
            vals = {e.props.get(kk) for _, e in items for kk in e.props if norm(kk) == k}
            if len(vals) > 1 and k not in POMIN_OPC and not k.endswith("MacroLen") and k not in ("bFreeze", "Level"):
                varying[k] += 1
        req = WYMAGANE.get(t, [])
        opt = [k for k in ZAWSZE if k not in req]
        opt += sorted(k for k in varying if k not in opt and k not in req)
        wz = wybierz_wzorzec(items)
        fname = "%d_%d.txt" % t
        if wz is not None:
            _, e = wz
            with open(os.path.join(OUT, "wzorce", fname), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(oczysc(e, name)) + "\n")
        erows.append(["%d" % t[0], "%d" % t[1], name, len(items), " ".join(req), " ".join(opt),
                      fname if wz else "", max(len(e.states) for _, e in items)])
    with open(os.path.join(OUT, "elementy.csv"), "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(["type", "subtype", "nazwa", "wystapien", "wymagane", "opcjonalne", "wzorzec", "max_stanow"])
        w.writerows(erows)
    print("elementy.csv:", len(erows), "rodzajow")


def wybierz_wzorzec(items):
    """Element bez makr, base64 i grup; najmniej stanow; z pierwszego podanego projektu, jesli sie da."""
    ok = [(p, e) for p, e in items
          if not any(k.endswith("MacroLen") and v not in ("0", "") for k, v in e.props.items())
          and not any(l.startswith("Base64TextLen") and l != "Base64TextLen0=0" for l in e.lines)
          and not any(l.startswith("@@hex") for l in e.lines)]
    if not ok:
        return None
    return min(ok, key=lambda x: (d.template_score(x[1]), DIRS.index(x[0])))


def oczysc(e, name):
    return d.clean_element_lines(e.lines, name, name if e.type == (10, 6) else "")


if __name__ == "__main__":
    DIRS = sys.argv[1:]
    if not DIRS:
        print(__doc__)
        sys.exit(2)
    main(DIRS)
