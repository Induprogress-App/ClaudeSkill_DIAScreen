# Instalacja skilla „diascreen” dla Claude Code

Skill pozwala Claude odczytywać i edytować projekty HMI Delta DIAScreen (`.dpa`): ekrany i ich elementy,
programy Lua, ustawienia projektu. Szczegóły narzędzia: `README.md` w paczce.

## Wymagania
- Claude Code (aplikacja desktop, terminal albo rozszerzenie IDE).
- Python 3.8 lub nowszy. Sprawdzenie w wierszu poleceń: `python --version` (albo `py -3 --version`).
  Instalator: https://www.python.org/downloads/ – zaznacz „Add python.exe to PATH”.
- DIAScreen (do otwierania i kompilowania projektów; narzędzie sprawdzone z panelem serii AX-8).

## Instalacja
1. Rozpakuj `diascreen.zip` do folderu skilli użytkownika, tak aby powstał plik
   `%USERPROFILE%\.claude\skills\diascreen\SKILL.md`. W PowerShellu:
   ```
   Expand-Archive .\diascreen.zip -DestinationPath "$env:USERPROFILE\.claude\skills" -Force
   ```
2. Zamknij i ponownie uruchom Claude Code (albo otwórz nową sesję).
3. Sprawdź: w nowej sesji wpisz `/diascreen` albo zapytaj „Jakie masz skille?” – na liście powinien być `diascreen`.

## Używanie
- Otwórz Claude Code w folderze z projektem HMI (albo podaj pełną ścieżkę do pliku `.dpa`) i opisz zadanie,
  np. „Na ekranie 2 projektu X.dpa przesuń wyświetlacz numeryczny i ustaw 5 cyfr”.
- **Przed zapisem zmian przez Claude zamknij projekt w DIAScreen.** Po zmianach otwórz go i skompiluj.
- Claude zapyta o zgodę przed uruchomieniem poleceń (`python ... dpa_tool.py ...`). Możesz wybrać „zawsze zezwalaj”
  dla tego polecenia, żeby nie potwierdzać go za każdym razem.
- Narzędzie tworzy obok projektu folder o tej samej nazwie z plikami tekstowymi. Nie trzymaj w nim własnych plików
  w `screens/` ani `lua/` – są tworzone od nowa przy każdym rozkładzie projektu.

## Aktualizacja
Rozpakuj nową paczkę poleceniem z punktu 1 (zastępuje folder skilla).

## Odinstalowanie
Usuń folder `%USERPROFILE%\.claude\skills\diascreen`.
