"""Buduje paczke skilla i instaluje ja lokalnie - jednym poleceniem.

Uzycie:
  python aktualizuj_skill.py [--bez-instalacji] [--ignoruj-slowa]

1. Buduje _ns_dist/diascreen.zip (zbuduj_skill.py, z kontrola zakazanych slow).
2. Instaluje paczke w %USERPROFILE%/.claude/skills (pomijane z --bez-instalacji).
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zbuduj_skill  # noqa: E402

DIST = os.path.join(HERE, '_ns_dist')
SKILL = zbuduj_skill.SKILL


def install():
    skills = os.path.join(os.path.expanduser('~'), '.claude', 'skills')
    target = os.path.join(skills, SKILL)
    if os.path.isdir(target):
        shutil.rmtree(target)  # folder skilla nie zawiera danych uzytkownika
    with zipfile.ZipFile(os.path.join(DIST, SKILL + '.zip')) as z:
        z.extractall(skills)
    print('  zainstalowano w %s (wersja %s)' % (target, open(os.path.join(target, 'WERSJA.txt'), encoding='utf-8').read().strip()))


def main(argv):
    print('1. Budowanie paczki')
    if zbuduj_skill.main(['--ignoruj-slowa'] if '--ignoruj-slowa' in argv else []) != 0:
        print('Przerwano - paczka nie zostala zbudowana.')
        return 1
    if '--bez-instalacji' not in argv:
        print('2. Instalacja skilla')
        install()
    print('Gotowe. Paczka dla innych: %s' % os.path.join(DIST, SKILL + '.zip'))
    print('Pamietaj o commicie zmian w %s/ (git add -A && git commit).' % SKILL)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
