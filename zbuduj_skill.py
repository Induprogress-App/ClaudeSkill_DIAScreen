"""Buduje paczke skilla "diascreen" do przekazania innym osobom: _ns_dist/diascreen.zip.

Uzycie:
  python zbuduj_skill.py [--out _ns_dist] [--ignoruj-slowa]

Paczka = zawartosc katalogu diascreen/ 1:1 (SKILL.md, INSTALACJA.md, dpa_tool.py, README.md, FORMAT_DPA.md,
PARAMETRY.md) plus WERSJA.txt. Pomijane sa: __pycache__, *.pyc, *.dpa i wszystko, co zaczyna sie od _ns_.

Jesli istnieje plik _ns_zakazane_slowa.txt (jedno slowo/fraza w linii, np. nazwy klientow lub projektow),
wszystkie pliki paczki sa sprawdzane pod katem tych slow.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = 'diascreen'
SRC = os.path.join(HERE, SKILL)
WORDS_FILE = os.path.join(HERE, '_ns_zakazane_slowa.txt')
SKIP_DIRS = {'__pycache__'}


def git_version():
    try:
        return subprocess.check_output(['git', '-C', HERE, 'describe', '--always', '--dirty'],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        return 'brak gita'


def package_files():
    """(sciezka na dysku, sciezka w paczce) dla wszystkich plikow katalogu diascreen/."""
    result = []
    for root, dirs, names in os.walk(SRC):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('_ns_'))
        for n in sorted(names):
            if n.startswith('_ns_') or n.endswith(('.pyc', '.dpa')):
                continue
            path = os.path.join(root, n)
            result.append((path, SKILL + '/' + os.path.relpath(path, SRC).replace(os.sep, '/')))
    return result


def check_words(files, words):
    hits, ips = [], []
    for path, arc in files:
        data = open(path, 'rb').read()
        text = data.decode('utf-8', 'replace')
        for w in words:
            line = next((l for l in text.splitlines() if w.lower() in l.lower()), None)
            if line is not None:
                hits.append('%s: "%s" w: %s' % (arc, w, line.strip()[:100]))
        ips += [(arc, ip) for ip in sorted(set(re.findall(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', text)))]
    return hits, ips


def main(argv):
    p = argparse.ArgumentParser(description='Buduje paczke skilla diascreen.')
    p.add_argument('--out', default=os.path.join(HERE, '_ns_dist'))
    p.add_argument('--ignoruj-slowa', action='store_true', help='buduj mimo znalezionych zakazanych slow')
    args = p.parse_args(argv)

    files = package_files()
    if not any(arc == SKILL + '/SKILL.md' for _, arc in files):
        print('Brak %s/SKILL.md - to nie jest katalog skilla.' % SKILL)
        return 1
    words = []
    if os.path.isfile(WORDS_FILE):
        words = [w.strip() for w in open(WORDS_FILE, encoding='utf-8') if w.strip() and not w.startswith('#')]
    hits, ips = check_words(files, words)
    for arc, ip in ips:
        print('UWAGA: adres IP %s w %s' % (ip, arc))
    if hits:
        print('Znaleziono zakazane slowa:\n  ' + '\n  '.join(hits))
        if not args.ignoruj_slowa:
            print('Paczki NIE zbudowano (--ignoruj-slowa, zeby zbudowac mimo to).')
            return 1

    version = '%s, %s' % (git_version(), datetime.date.today().isoformat())
    os.makedirs(args.out, exist_ok=True)
    zip_path = os.path.join(args.out, SKILL + '.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, arc in files:
            z.write(path, arc)
        z.writestr(SKILL + '/WERSJA.txt', version + '\n')
    print('Zbudowano %s (wersja %s, %d plikow)%s' % (zip_path, version, len(files) + 1,
                                                   '' if words else ' - bez pliku slow zakazanych, slow nie sprawdzano'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
