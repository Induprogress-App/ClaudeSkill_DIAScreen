"""Dekoder/koder plikow projektow Delta DIAScreen (.dpa) do postaci tekstowej.

Struktura pliku .dpa:
  [miniatura BMP 164x123 + 28 B trailera konczacego sie "ABPD"]  -> thumbnail.bin (bez zmian)
  [strumien gzip] -> po rozpakowaniu:
      "Delta-HMI Screen Editor DOP V1010\\t   " (naglowek)
      uint32 LE  dlugosc tresci
      tresc XOR 0x64 -> tekst INI (CRLF) z wstawkami binarnymi

Reprezentacja tekstowa (project.txt, UTF-8, jedna linia = jedna linia INI):
  zwykla linia                -> bez zmian
  @@u16 KEY=<json string>     -> "KEY=<n>" + n bajtow UTF-16LE zakonczonych \\0\\0 (dlugosc liczona automatycznie)
  @@lenhex KEY=<hex>          -> "KEY=<n>" + n surowych bajtow
  @@blob32 KEY=<hex>          -> "KEY=" + uint32 LE dlugosc + bajty (np. MeMeCode)
  @@sqlite <plik>             -> uint32 LE dlugosc + zawartosc pliku bazy SQLite
  @@hex <hex>                 -> surowe bajty linii (nierozpoznane dane binarne)
  KEYMacroLen=<n> + linie @@m -> makro: "\\x02REV" + polecenia zakonczone CRLF; n liczone przy encode
  @@m <naglowek> <flagi> [tekst, op1, op2, op3, op4]  -> jedno polecenie makra (napisy latin-1)
  @@m 00000067                -> rekord konczacy (bez pol)
  @@screen screens/<plik>     -> wstawia w tym miejscu zawartosc pliku ekranu (ten sam format)
  @@luaxml KEY=lua/_lua_files.xml -> "KEY=<n>" + XML z programami Lua; w XML-u
                                 <content>@@lua:Main.lua</content> = base64 pliku lua/Main.lua

Katalog po dekodowaniu:
  project.txt      ustawienia globalne + odnosniki do ekranow
  screens/NNN_Nazwa.txt   po jednym pliku na ekran ([Screen] wraz z [Element]/[State])
  lua/*.lua        programy Lua (czysty tekst), lua/_lua_files.xml - atrybuty plikow Lua
  sram_data.db     baza SQLite (hasla, siec, kontakty...)
  thumbnail.bin, meta.json  - nie edytowac
Kolejnosc ekranow w pliku = kolejnosc linii @@screen w project.txt.

Uzycie: patrz USAGE (python dpa_tool.py bez argumentow)

Sekcje pliku (znaczniki "# ----"; szukac grep "^# ----", czytac tylko potrzebny zakres):
  kontener, tresc <-> tekst, komendy (decode/encode/verify), przegladanie (screens/list/show/find),
  edycja elementow (set/add), ekrany, projekty, slownik (add-screen/new/params), dane z instalacji
  DIAScreen (info/lua-api), porownanie projektow (diff), USAGE + main
"""
import base64
import json
import os
import re
import shutil
import struct
import sys
import zlib

XOR_KEY = 0x64
MAGIC = b"Delta-HMI Screen Editor DOP"
BLOB32_KEYS = {b"MeMeCode"}
SQLITE_SECTIONS = {b"[100_SRAM_DATA]"}
RAW_LEN_KEYS = {b"SysKeyPwd"}  # "KEY=n" + n bajtow, mimo braku "Len" w nazwie
LEN_LINE = re.compile(rb"^([A-Za-z0-9_\-]+)=(\d+)$")
MACRO_LINE = re.compile(rb"^([A-Za-z0-9_]*MacroLen)=(\d+)$")
MACRO_HEAD = b"\x02REV"
MACRO_END = b"\x00\x00\x00\x67"
LUA_LINE = re.compile(rb"^(<EXTENT>LuaXmlFileLen)=(\d+)$")
LUA_CONTENT = re.compile(r'(<file\b[^>]*\bname="([^"]*)"[^>]*>\s*<content>)([^<]*)(</content>)')
LUA_REF = re.compile(r"<content>@@lua:([^<]+)</content>")
SCREEN_FILE_REF = "@@screen "
SCREEN_DIR = "screens"
LUA_DIR = "lua"
LUA_XML = "_lua_files.xml"
SQLITE_NAME = "sram_data.db"
# sekcje globalne, ktore koncza blok ostatniego ekranu
TOP_SECTIONS = {"[SubMacro]", "[Global_Auxkey]", "[Alarm]", "[History]", "[NewTextBank]", "[Tag]",
                "[100_SRAM_DATA]", "[SysMessage]", "[Picture]", "[Background]", "[DIATag]",
                "[DeviceTable]", "[MQTTFile]", "[END]"}
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x0b"


def _printable(b):
    return all(32 <= c < 127 or c == 9 for c in b)


# ---------------------------------------------------------------- kontener

def read_container(data):
    gz = data.find(b"ABPD\x1f\x8b\x08")
    if gz < 0:
        raise ValueError("nie znaleziono strumienia gzip (znacznik ABPD)")
    gz += 4
    raw = zlib.decompress(data[gz:], 31)
    if not raw.startswith(MAGIC):
        raise ValueError("nieznany naglowek: %r" % raw[:40])
    hdr_end = raw.index(b"\t   ") + 4
    (n,) = struct.unpack_from("<I", raw, hdr_end)
    body = bytes(c ^ XOR_KEY for c in raw[hdr_end + 4:hdr_end + 4 + n])
    if hdr_end + 4 + n != len(raw):
        raise ValueError("dlugosc tresci nie zgadza sie z naglowkiem")
    return data[:gz], raw[:hdr_end], body, data[gz:gz + 10]


def write_container(prefix, header, body, gzip_header=GZIP_HEADER):
    raw = header + struct.pack("<I", len(body)) + bytes(c ^ XOR_KEY for c in body)
    c = zlib.compressobj(6, zlib.DEFLATED, -15, 8)
    deflated = c.compress(raw) + c.flush()
    trailer = struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)
    return prefix + gzip_header + deflated + trailer


# ---------------------------------------------------------------- tresc <-> tekst

def body_to_items(body):
    """Dzieli tresc na elementy (laczone CRLF). Zwraca liste (rodzaj, ...)."""
    items = []
    pos = 0
    n = len(body)
    while True:
        # blob z 4-bajtowa dlugoscia po "KEY="
        eq = body.find(b"=", pos, pos + 64)
        key = body[pos:eq] if eq >= 0 else None
        if key in BLOB32_KEYS:
            (ln,) = struct.unpack_from("<I", body, eq + 1)
            end = eq + 5 + ln
            items.append(("blob32", key, body[eq + 5:end]))
            pos = _expect_crlf(body, end)
            if pos is None:
                break
            continue

        end = body.find(b"\r\n", pos)
        line = body[pos:] if end < 0 else body[pos:end]

        if line in SQLITE_SECTIONS and end >= 0:
            items.append(("line", line))
            p = end + 2
            (ln,) = struct.unpack_from("<I", body, p)
            items.append(("sqlite", body[p + 4:p + 4 + ln]))
            pos = _expect_crlf(body, p + 4 + ln)
            if pos is None:
                break
            continue

        m = LUA_LINE.match(line) if end >= 0 else None
        if m:
            p = end + 2
            ln = int(m.group(2))
            items.append(("luaxml", m.group(1), body[p:p + ln]))
            pos = _expect_crlf(body, p + ln)
            if pos is None:
                break
            continue

        m = LEN_LINE.match(line) if end >= 0 else None
        if m and int(m.group(2)) > 0 and (b"Len" in m.group(1) or m.group(1) in RAW_LEN_KEYS):
            ln = int(m.group(2))
            p = end + 2
            chunk = body[p:p + ln]
            if (len(chunk) == ln and body[p + ln:p + ln + 2] == b"\r\n"
                    and not all(_printable(x) for x in chunk.split(b"\r\n"))):
                kind = "u16" if _is_u16(chunk) else "lenhex"
                items.append((kind, m.group(1), chunk))
                pos = p + ln + 2
                continue

        items.append(("line", line))
        if end < 0:
            break
        pos = end + 2
    return items


def _expect_crlf(body, p):
    if p >= len(body):
        return None
    if body[p:p + 2] != b"\r\n":
        raise ValueError("oczekiwano CRLF po bloku binarnym na pozycji %d" % p)
    return p + 2


def _is_u16(chunk):
    if len(chunk) % 2 or not chunk.endswith(b"\x00\x00"):
        return False
    try:
        s = chunk[:-2].decode("utf-16-le")
    except UnicodeDecodeError:
        return False
    return "\x00" not in s and _u16_bytes(s) == chunk


def _u16_bytes(s):
    return s.encode("utf-16-le") + b"\x00\x00"


def items_to_body(items):
    out = []
    for it in items:
        kind = it[0]
        if kind == "line":
            out.append(it[1])
        elif kind in ("u16", "lenhex", "luaxml"):
            out.append(it[1] + b"=" + str(len(it[2])).encode() + b"\r\n" + it[2])
        elif kind == "blob32":
            out.append(it[1] + b"=" + struct.pack("<I", len(it[2])) + it[2])
        elif kind == "sqlite":
            out.append(struct.pack("<I", len(it[1])) + it[1])
        elif kind == "macro":
            raw = macro_bytes(it[2])
            out.append(it[1] + b"=" + str(len(raw)).encode() + b"\r\n" + raw[:-2])
    return b"\r\n".join(out)


def parse_macro(raw):
    """Bajty makra -> lista polecen: MACRO_END albo (naglowek 4 B, flagi 12 B, [5 napisow]).
    Polecenie = naglowek + 5x (uint32 LE dlugosc + bajty) + 12 B flag, zakonczone CRLF.
    Zwraca None, gdy bajty nie pasuja do tego ukladu."""
    if not raw.startswith(MACRO_HEAD):
        return None
    p, out = len(MACRO_HEAD), []
    try:
        while p < len(raw):
            head = raw[p:p + 4]
            p += 4
            if head == MACRO_END:
                out.append(MACRO_END)
            else:
                fields = []
                for _ in range(5):
                    (n,) = struct.unpack_from("<I", raw, p)
                    if p + 4 + n > len(raw):
                        return None
                    fields.append(raw[p + 4:p + 4 + n].decode("latin-1"))
                    p += 4 + n
                out.append((head, raw[p:p + 12], fields))
                p += 12
            if raw[p:p + 2] != b"\r\n":
                return None
            p += 2
    except struct.error:
        return None
    return out if macro_bytes(out) == raw else None


def macro_bytes(cmds):
    out = [MACRO_HEAD]
    for c in cmds:
        if c == MACRO_END:
            out.append(MACRO_END)
        else:
            out.append(c[0])
            for f in c[2]:
                b = f.encode("latin-1")
                out.append(struct.pack("<I", len(b)) + b)
            out.append(c[1])
        out.append(b"\r\n")
    return b"".join(out)


def macro_line(c):
    if c == MACRO_END:
        return "@@m " + MACRO_END.hex()
    return "@@m %s %s %s" % (c[0].hex(), c[1].hex(), json.dumps(c[2]))


def parse_macro_line(line):
    parts = line[4:].split(" ", 2)
    if len(parts) == 1:
        return bytes.fromhex(parts[0])
    return bytes.fromhex(parts[0]), bytes.fromhex(parts[1]), json.loads(parts[2])


def _macro_at(items, i):
    """Linia 'KEYMacroLen=n' w items[i] -> (polecenia, indeks za makrem) albo None.
    Bajty makra to kolejne linie (przedzielone CRLF), lacznie z koncowym CRLF = n bajtow."""
    m = MACRO_LINE.match(items[i][1])
    n = int(m.group(2)) if m else 0
    if not n:
        return None
    j, size, parts = i + 1, -2, []
    while j < len(items) and items[j][0] == "line" and size + 2 < n:
        parts.append(items[j][1])
        size += len(items[j][1]) + 2
        j += 1
    if size + 2 != n:
        return None
    cmds = parse_macro(b"\r\n".join(parts) + b"\r\n")
    return (cmds, j) if cmds else None


def items_to_text(items, out_dir):
    """Zwraca linie project.txt; pliki poboczne (SQLite, Lua) zapisuje w out_dir."""
    lines = []
    i = 0
    while i < len(items):
        it = items[i]
        i += 1
        kind = it[0]
        mac = _macro_at(items, i - 1) if kind == "line" else None
        if mac:
            lines.append(it[1].decode("ascii"))
            lines.extend(macro_line(c) for c in mac[0])
            i = mac[1]
            continue
        if kind == "line":
            line = it[1]
            if _printable(line) and not line.startswith(b"@@"):
                lines.append(line.decode("ascii"))
            else:
                lines.append("@@hex " + line.hex())
        elif kind == "u16":
            s = it[2][:-2].decode("utf-16-le")
            lines.append("@@u16 %s=%s" % (it[1].decode(), json.dumps(s, ensure_ascii=False)))
        elif kind == "lenhex":
            lines.append("@@lenhex %s=%s" % (it[1].decode(), it[2].hex()))
        elif kind == "blob32":
            lines.append("@@blob32 %s=%s" % (it[1].decode(), it[2].hex()))
        elif kind == "sqlite":
            _write(os.path.join(out_dir, SQLITE_NAME), it[1])
            lines.append("@@sqlite " + SQLITE_NAME)
        elif kind == "luaxml":
            ref = _extract_lua(it[2], out_dir)
            if ref:
                lines.append("@@luaxml %s=%s" % (it[1].decode(), ref))
            else:
                lines.append("@@lenhex %s=%s" % (it[1].decode(), it[2].hex()))
    return lines


def _extract_lua(xml_bytes, out_dir):
    """Rozpisuje programy Lua (base64 w <content>) do lua/*.lua. Zwraca sciezke XML-a albo None."""
    try:
        xml = xml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None
    lua_dir = os.path.join(out_dir, LUA_DIR)
    used = set()

    def repl(m):
        b64 = m.group(3)
        try:
            code = base64.b64decode(b64, validate=True)
        except ValueError:
            return m.group(0)
        if base64.b64encode(code).decode("ascii") != b64:
            return m.group(0)  # niestandardowy base64 - zostaw w XML
        fname = _unique(_safe_name(m.group(2)) or "lua", used, ".lua")
        _write(os.path.join(lua_dir, fname), code)
        return m.group(1) + "@@lua:" + fname + m.group(4)

    skeleton = LUA_CONTENT.sub(repl, xml)
    if _build_lua_xml(skeleton, lua_dir) != xml_bytes:
        return None
    _write(os.path.join(lua_dir, LUA_XML), skeleton.encode("utf-8"))
    return LUA_DIR + "/" + LUA_XML


def _build_lua_xml(skeleton, lua_dir):
    def repl(m):
        with open(os.path.join(lua_dir, m.group(1)), "rb") as f:
            return "<content>" + base64.b64encode(f.read()).decode("ascii") + "</content>"
    return LUA_REF.sub(repl, skeleton).encode("utf-8")


def split_screens(lines, out_dir):
    """Przenosi sekcje [Screen] do screens/*.txt, w project.txt zostawia odnosniki @@screen."""
    out, used = [], set()
    i = 0
    while i < len(lines):
        if lines[i] != "[Screen]":
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j] != "[Screen]" and lines[j] not in TOP_SECTIONS:
            j += 1
        block = lines[i:j]
        sid = next((l[3:] for l in block if l.startswith("ID=")), "x")
        name = next((json.loads(l.split("=", 1)[1]) for l in block
                     if l.startswith("@@u16 wTextLen=")), "")
        fname = _unique("%s_%s" % (sid.zfill(3), _safe_name(name) or "screen"), used, ".txt")
        _write(os.path.join(out_dir, SCREEN_DIR, fname), "\n".join(block).encode("utf-8"))
        out.append(SCREEN_FILE_REF + SCREEN_DIR + "/" + fname)
        i = j
    return out


def _safe_name(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")


def _unique(base, used, ext):
    n, cand = 2, base + ext
    while cand.lower() in used:
        cand = "%s_%d%s" % (base, n, ext)
        n += 1
    used.add(cand.lower())
    return cand


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _read_text(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return f.read()


def text_to_items(text, base_dir):
    items = []
    for raw in text.split("\n"):
        line = raw[:-1] if raw.endswith("\r") else raw
        if line.startswith(SCREEN_FILE_REF):
            path = os.path.join(base_dir, line[len(SCREEN_FILE_REF):].strip())
            items.extend(text_to_items(_read_text(path), base_dir))
            continue
        if not line.startswith("@@"):
            items.append(("line", line.encode("ascii")))
            continue
        tag, _, rest = line.partition(" ")
        if tag == "@@m":
            if items[-1][0] != "macro":
                m = MACRO_LINE.match(items[-1][1]) if items[-1][0] == "line" else None
                if not m:
                    raise ValueError("linia @@m bez poprzedzajacej linii ...MacroLen=: " + line[:60])
                items[-1] = ("macro", m.group(1), [])
            items[-1][2].append(parse_macro_line(line))
        elif tag == "@@hex":
            items.append(("line", bytes.fromhex(rest)))
        elif tag == "@@sqlite":
            with open(os.path.join(base_dir, rest.strip()), "rb") as f:
                items.append(("sqlite", f.read()))
        else:
            key, _, val = rest.partition("=")
            key = key.strip().encode("ascii")
            if tag == "@@u16":
                items.append(("u16", key, _u16_bytes(json.loads(val))))
            elif tag == "@@lenhex":
                items.append(("lenhex", key, bytes.fromhex(val)))
            elif tag == "@@blob32":
                items.append(("blob32", key, bytes.fromhex(val)))
            elif tag == "@@luaxml":
                xml_path = os.path.join(base_dir, val.strip())
                items.append(("luaxml", key, _build_lua_xml(_read_text(xml_path),
                                                            os.path.dirname(xml_path))))
            else:
                raise ValueError("nieznany znacznik: " + tag)
    return items


# ---------------------------------------------------------------- komendy

def decode(dpa_path, out_dir=None):
    out_dir = out_dir or os.path.splitext(dpa_path)[0]
    os.makedirs(out_dir, exist_ok=True)
    for sub in (SCREEN_DIR, LUA_DIR):  # usun pozostalosci po poprzednim dekodowaniu
        d = os.path.join(out_dir, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
    with open(dpa_path, "rb") as f:
        data = f.read()
    prefix, header, body, gzh = read_container(data)
    items = body_to_items(body)
    if items_to_body(items) != body:
        raise RuntimeError("wewnetrzny blad: podzial tresci nie jest bezstratny")

    _write(os.path.join(out_dir, "thumbnail.bin"), prefix)
    lines = split_screens(items_to_text(items, out_dir), out_dir)
    _write(os.path.join(out_dir, "project.txt"), "\n".join(lines).encode("utf-8"))
    meta = {"header": header.decode("latin-1"), "gzip_header": gzh.hex(),
            "source": os.path.basename(dpa_path)}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out_dir


def encode(src_dir, out_path=None):
    with open(os.path.join(src_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    out_path = out_path or os.path.join(os.path.dirname(os.path.abspath(src_dir)),
                                        os.path.basename(os.path.normpath(src_dir)) + "_edited.dpa")
    with open(os.path.join(src_dir, "thumbnail.bin"), "rb") as f:
        prefix = f.read()
    body = items_to_body(text_to_items(_read_text(os.path.join(src_dir, "project.txt")), src_dir))
    data = write_container(prefix, meta["header"].encode("latin-1"), body,
                           bytes.fromhex(meta["gzip_header"]))
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def verify(dpa_path):
    import tempfile
    with open(dpa_path, "rb") as f:
        orig = f.read()
    with tempfile.TemporaryDirectory() as tmp:
        d = decode(dpa_path, os.path.join(tmp, "src"))
        out = encode(d, os.path.join(tmp, "out.dpa"))
        with open(out, "rb") as f:
            again = f.read()
    ok = again == orig
    print("%s: %s" % (dpa_path, "OK (identyczny bajt-w-bajt)" if ok else "ROZNICA"))
    return ok


# ---------------------------------------------------------------- przegladanie (oszczedne w tokenach)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dane")
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "szablony")


def _load_csv(name):
    import csv
    path = os.path.join(DATA_DIR, name)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


# (Type, SubType) -> wiersz elementy.csv (nazwa, wymagane, opcjonalne, wzorzec); "?" w nazwie = niepotwierdzona
ELEMENT_INFO = {(int(r["type"]), int(r["subtype"])): r for r in _load_csv("elementy.csv")}
ELEMENT_TYPES = {k: r["nazwa"] for k, r in ELEMENT_INFO.items()}
# klucze z adresami / powiazaniami pokazywane w "list" (skrot: klucz)
LIST_KEYS = [("R", "ReadVar"), ("W", "WriteVar"), ("Trg", "TriggerVar"), ("Vis", "VisibleVar"),
             ("Lock", "InterLockVar"), ("Scr", "GoToScreenID")]
EMPTY_VALUES = {"0", "-1", "None", "", '""', "0.0", "0.000000"}
SECTION_END = ("[Element]", "[Group]")


def element_type_name(t, s):
    return ELEMENT_TYPES.get((t, s), "Type %d/%d" % (t, s))


def _kv(line):
    """Linia 'KEY=val' albo '@@u16 KEY="..."' -> (klucz, wartosc tekstowa) albo None."""
    if line.startswith("@@u16 "):
        k, _, v = line[6:].partition("=")
        return k, json.loads(v)
    if line.startswith("@@") or line.startswith("[") or "=" not in line:
        return None
    k, _, v = line.partition("=")
    return k, v


class Element:
    def __init__(self, lines, start):
        self.lines, self.start = lines, start  # start = numer linii w pliku (od 1)
        self.states = [i for i, l in enumerate(lines) if l == "[State]"]
        head = lines[:self.states[0]] if self.states else lines
        self.props = dict(kv for kv in map(_kv, head) if kv)
        self.id = int(self.props.get("nPartsID", -1))
        self.type = (int(self.props.get("Type", 0)), int(self.props.get("SubType", 0)))

    @property
    def type_name(self):
        return element_type_name(*self.type)

    def sections(self):
        """Podsekcje elementu ([State], [PressedAction]...) jako listy linii (pierwsza = naglowek)."""
        idx = [i for i, l in enumerate(self.lines) if i and l.startswith("[")] + [len(self.lines)]
        return [self.lines[idx[i]:idx[i + 1]] for i in range(len(idx) - 1)]

    def state_blocks(self):
        return [s for s in self.sections() if s[0] == "[State]"]

    def texts(self):
        out = []
        for st in self.state_blocks():
            for l in st:
                kv = _kv(l)
                if kv and kv[0].startswith("wTextLen") and kv[1] and kv[1] not in out:
                    out.append(kv[1])
        return out


class Screen:
    def __init__(self, path):
        self.path = path
        self.file = os.path.basename(path)
        self.lines = _read_text(path).split("\n")
        starts = [i for i, l in enumerate(self.lines) if l == "[Element]"]
        self.elements = []
        for n, i in enumerate(starts):
            j = i + 1
            while j < len(self.lines) and self.lines[j] not in SECTION_END:
                j += 1
            self.elements.append(Element(self.lines[i:j], i + 1))
        head = self.lines[:starts[0]] if starts else self.lines
        self.props = dict(kv for kv in map(_kv, head) if kv)
        self.id = int(self.props.get("ID", -1))
        self.name = self.props.get("wTextLen", "")

    def element(self, ident):
        for e in self.elements:
            if str(e.id) == str(ident) or e.props.get("wDescTextLen0") == ident:
                return e
        raise SystemExit("Brak elementu %s na ekranie %s" % (ident, self.file))


def _project_dir(path, allow_dpa=True):
    """KATALOG po decode albo plik .dpa (wtedy dekodowany do katalogu tymczasowego)."""
    if allow_dpa and os.path.isfile(path) and path.lower().endswith(".dpa"):
        import atexit
        import tempfile
        tmp = tempfile.mkdtemp(prefix="dpa_")
        atexit.register(shutil.rmtree, tmp, True)
        return decode(path, os.path.join(tmp, "src"))
    if not os.path.isfile(os.path.join(path, "project.txt")):
        raise SystemExit("To nie jest katalog po decode ani plik .dpa: " + path)
    return path


def load_screens(proj):
    out = []
    for line in _read_text(os.path.join(proj, "project.txt")).split("\n"):
        if line.startswith(SCREEN_FILE_REF):
            out.append(Screen(os.path.join(proj, line[len(SCREEN_FILE_REF):].strip())))
    return out


def find_screen(screens, ident):
    for test in (lambda s: str(s.id) == ident, lambda s: s.file == ident,
                 lambda s: os.path.splitext(s.file)[0] == ident, lambda s: s.name == ident,
                 lambda s: s.name.lower() == ident.lower()):
        hit = [s for s in screens if test(s)]
        if hit:
            return hit[0]
    raise SystemExit("Brak ekranu: %s (podaj ID, nazwe albo plik)" % ident)


def _short(s, n=60):
    s = s.replace("\r\n", "\n").replace("\n", "\\n")
    return s if len(s) <= n else s[:n - 3] + "..."


def cmd_screens(proj):
    for s in load_screens(proj):
        extra = " base=%s" % s.props["BaseScreenID"] if s.props.get("BaseScreenID", "0") != "0" else ""
        print("%5d  %-24s %-28s %3d el.%s" % (s.id, _short(s.name, 24), s.file, len(s.elements), extra))


def element_summary(e, xy=False):
    p = e.props
    parts = ["%3d %s" % (e.id, e.type_name)]
    desc = p.get("wDescTextLen0", "")
    if desc and not desc.startswith(e.type_name.rstrip("?")):
        parts.append("desc=" + json.dumps(desc, ensure_ascii=False))
    for short, key in LIST_KEYS:
        v = p.get(key)
        if v is not None and v not in EMPTY_VALUES:
            parts.append("%s=%s" % (short, v))
    if xy:
        parts.append("@%s,%s %sx%s" % (p.get("X"), p.get("Y"), p.get("Width"), p.get("Height")))
    if any(k.endswith("MacroLen") and v not in EMPTY_VALUES for k, v in p.items()):
        parts.append("macro")
    if len(e.states) > 2:
        parts.append("states=%d" % len(e.states))
    texts = e.texts()
    if texts:
        parts.append(" | ".join(json.dumps(_short(t, 40), ensure_ascii=False) for t in texts[:4])
                     + (" (+%d)" % (len(texts) - 4) if len(texts) > 4 else ""))
    return "  ".join(parts)


def cmd_list(proj, screen, xy=False):
    s = find_screen(load_screens(proj), screen)
    print("# %d %s (%s), %d el." % (s.id, s.name, s.file, len(s.elements)))
    for e in s.elements:
        print(element_summary(e, xy))


def _macro_text(mlines, sep=" ; "):
    """Linie makra (@@m albo nierozpoznane @@hex) -> teksty polecen."""
    if mlines and mlines[0].startswith("@@m "):
        cmds = (parse_macro_line(l) for l in mlines)
        return sep.join(c[2][0].strip() for c in cmds if c != MACRO_END)
    raw = b"".join(bytes.fromhex(l[6:]) for l in mlines)
    return " ".join(m.decode("ascii") for m in re.findall(rb"[\x20-\x7e]{4,}", raw))


def _show_lines(lines, skip_empty, prev=None):
    """Linie bloku w postaci skroconej; prev = slownik poprzedniego stanu (pokaz tylko roznice)."""
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        kv = _kv(l)
        if kv and kv[0].endswith("MacroLen") and kv[1] not in EMPTY_VALUES:
            j = i + 1
            while j < len(lines) and lines[j].startswith(("@@hex ", "@@m ")):
                j += 1
            out.append("%s: %s" % (kv[0][:-3], _macro_text(lines[i + 1:j])))
            i = j
            continue
        i += 1
        if kv is None:
            continue
        if prev is not None:
            if prev.get(kv[0]) != kv[1]:
                out.append("%s=%s" % kv)
        elif not (skip_empty and kv[1] in EMPTY_VALUES):
            out.append(l[6:] if l.startswith("@@u16 ") else l)
    return out


def cmd_show(proj, screen, ident, full=False):
    s = find_screen(load_screens(proj), screen)
    e = s.element(ident)
    if full:
        for n, l in enumerate(e.lines):
            print("%d: %s" % (e.start + n, l))
        return
    print("# %s / element %d %s (linie %d-%d w %s)" % (s.name, e.id, e.type_name, e.start,
                                                       e.start + len(e.lines) - 1, s.file))
    secs = e.sections()
    head = e.lines[:len(e.lines) - sum(len(x) for x in secs)]
    print("\n".join(_show_lines(head[1:], True)))
    prev = None
    for st in secs:
        if st[0] != "[State]":
            print(st[0])
            print("\n".join(_show_lines(st[1:], True)))
            continue
        cur = dict(kv for kv in map(_kv, st) if kv)
        print("[State %s]" % cur.get("Value", "0") + (" (roznice)" if prev else ""))
        body = _show_lines(st[1:], True, prev)
        if body:
            print("\n".join(body))
        prev = cur


def cmd_find(proj, text):
    low = text.lower()
    for s in load_screens(proj):
        for e in s.elements:
            for n, l in enumerate(e.lines):
                kv = _kv(l)
                if l.startswith("@@m "):
                    c = parse_macro_line(l)
                    if c != MACRO_END and any(low in f.lower() for f in c[2]):
                        print("%s:%d  [%d %s] el.%d %s  makro: %s" % (s.file, e.start + n, s.id, s.name, e.id,
                                                                     e.type_name, _short(c[2][0].strip())))
                elif kv and low in kv[1].lower():
                    print("%s:%d  [%d %s] el.%d %s  %s=%s" % (s.file, e.start + n, s.id, s.name, e.id,
                                                              e.type_name, kv[0], _short(kv[1])))


# ---------------------------------------------------------------- edycja elementow

KEY_ALIASES = {"text": "wTextLen{L}", "desc": "wDescTextLen{L}", "read": "ReadVar", "write": "WriteVar",
               "visible": "VisibleVar", "x": "X", "y": "Y", "w": "Width", "h": "Height",
               "name": "wTextLen", "base": "BaseScreenID", "screen": "GoToScreenID"}
LONG_TEXT = 256  # wTextLenN przechowuje najwyzej tyle znakow; calosc w Base64TextLenN
B64_LINE = re.compile(r"[A-Za-z0-9+/]+=*")
LANG_KEY = [re.compile(r"^(@@u16 )?(wTextLen|FontName|FontSize|FontRatio|wDescTextLen|UnitTextLen|UnitFontName"
                       r"|UnitFontSize)(\d)=(.*)$"),
            re.compile(r"^(@@u16 )?(KPFontName|KPFontSize|TitleTextLen|wKPFStringLen)(\d+-)(\d{3})=(.*)$")]


def _parse_assign(items, lang=0):
    out = []
    for a in items:
        k, eq, v = a.partition("=")
        if not eq:
            raise SystemExit("Oczekiwano KLUCZ=WARTOSC: " + a)
        out.append((KEY_ALIASES.get(k.lower(), k).replace("{L}", str(lang)), v))
    return out


def _b64_block(lines, i):
    """Koniec danych base64 zaczynajacych sie w linii i."""
    j = i
    while j < len(lines) and B64_LINE.fullmatch(lines[j]):
        j += 1
    return j


def _set_in(lines, key, value):
    """Zmienia KEY w liniach bloku. Zwraca True, jesli znaleziono. Dlugi tekst -> takze Base64TextLenN."""
    for i, l in enumerate(lines):
        kv = _kv(l)
        if not kv or kv[0] != key:
            continue
        if l.startswith("@@u16 "):
            # nowa linia w tekscie (podana jako \n) -> CRLF, jak zapisuje DIAScreen
            value = value.replace("\r\n", "\n").replace("\\n", "\n").replace("\n", "\r\n")
            m = re.match(r"wTextLen(\d+)$", key)
            b64 = next((n for n, x in enumerate(lines) if m and x.startswith("Base64TextLen%s=" % m.group(1))), None)
            if b64 is not None:
                end = _b64_block(lines, b64 + 1)
                if len(value) > LONG_TEXT:
                    enc = base64.b64encode(_u16_bytes(value)).decode("ascii")
                    chunks = [enc[p:p + 76] for p in range(0, len(enc), 76)]
                    lines[b64:end] = ["Base64TextLen%s=%d" % (m.group(1), len("\r\n".join(chunks)))] + chunks
                else:
                    lines[b64:end] = ["Base64TextLen%s=0" % m.group(1)]
                value = value[:LONG_TEXT]
            elif m and len(value) > LONG_TEXT:
                print("UWAGA: tekst dluzszy niz %d znakow, a element nie ma Base64TextLen%s" % (LONG_TEXT, m.group(1)))
            lines[i] = "@@u16 %s=%s" % (key, json.dumps(value, ensure_ascii=False))
        else:
            lines[i] = "%s=%s" % (key, value)
        return True
    return False


def _section_ranges(lines):
    idx = [i for i, l in enumerate(lines) if i and l.startswith("[")] + [len(lines)]
    return idx[0], [(idx[n], idx[n + 1]) for n in range(len(idx) - 1) if lines[idx[n]] == "[State]"]


# Klucze pomijane przez DIAScreen, gdy adres nie jest ustawiony: wstawiane przed VisibleCondition
OPTIONAL_LINK = {"VisibleLink": "VisibleCondition", "VisibleVar": "VisibleCondition"}


def _add_link(head, key):
    """Dopisuje brakujace VisibleLink=1 i VisibleVar=None przed VisibleCondition (jak DIAScreen)."""
    pos = next((i for i, l in enumerate(head) if l.startswith(OPTIONAL_LINK[key] + "=")), None)
    if pos is None:
        return
    new = [l for l in ("VisibleLink=1", "VisibleVar=None")
           if not any(x.startswith(l.split("=")[0] + "=") for x in head)]
    head[pos:pos] = new


def set_element(lines, assigns, state=None):
    """Zmienia parametry w liniach elementu (lista modyfikowana w miejscu). state: None, numer albo 'all'."""
    msgs = []
    for key, value in assigns:
        head_end, states = _section_ranges(lines)
        head = lines[:head_end]
        if state in (None, "all") and key in OPTIONAL_LINK and not any(l.startswith(key + "=") for l in head):
            _add_link(head, key)
        if state in (None, "all") and _set_in(head, key, value):
            lines[:head_end] = head
            msgs.append("%s=%s" % (key, value))
            continue
        if state is None and len(states) > 1:
            raise SystemExit("%s: element ma %d stanow - podaj --state=N albo --state=all" % (key, len(states)))
        sel = range(len(states)) if state in (None, "all") else [int(state)]
        hit = False
        for n in reversed(list(sel)):  # od konca - zmiana dlugosci bloku nie przesuwa wczesniejszych
            if n >= len(states):
                raise SystemExit("Brak stanu %s" % n)
            a, b = states[n]
            blk = lines[a:b]
            if _set_in(blk, key, value):
                lines[a:b] = blk
                hit = True
        if not hit:
            raise SystemExit("Nie znaleziono klucza %s w elemencie (nowych kluczy nie dodaje; "
                             "lista kluczy: params --type=T/S)" % key)
        msgs.append("%s=%s (stan %s)" % (key, _short(value, 40), "wszystkie" if state in (None, "all") else state))
    head_end = _section_ranges(lines)[0]
    props = dict(kv for kv in map(_kv, lines[:head_end]) if kv)
    for key, value in assigns:
        link = key[:-3] + "Link" if key.endswith("Var") else None
        if link and value != "None" and props.get(link) in ("0", "None"):
            msgs.append("UWAGA: %s=%s - adres zwykle wymaga %s=1" % (link, props.get(link), link))
    return msgs


def _save_screen(s, idx, new_lines, old_len):
    s.lines[idx:idx + old_len] = new_lines
    _write(s.path, "\n".join(s.lines).encode("utf-8"))


def project_languages(proj):
    n = sum(1 for l in _read_text(os.path.join(proj, "project.txt")).split("\n")
            if re.match(r"LanguageEnable\d+=1$", l))
    return max(n, 1)


def _lang_of(line):
    for r in LANG_KEY:
        m = r.match(line)
        if m:
            return int(m.group(3).rstrip("-")) if r is LANG_KEY[0] else int(m.group(4)), m, r
    return None, None, None


def _with_lang(m, r, lang):
    g = m.groups()
    if r is LANG_KEY[0]:
        return "%s%s%d=%s" % (g[0] or "", g[1], lang, g[3])
    return "%s%s%s%03d=%s" % (g[0] or "", g[1], g[2], lang, g[4])


def adapt_languages(lines, n):
    """Usuwa wersje jezykowe >= n, dopisuje brakujace (kopie jezyka 0)."""
    out = [l for l in lines if (_lang_of(l)[0] or 0) < n]
    present = {_lang_of(l)[0] for l in out}
    for lang in range(1, n):
        if lang in present:
            continue
        res, run = [], []
        for l in out + [None]:
            lg, m, r = _lang_of(l) if l is not None else (None, None, None)
            if lg == 0:
                run.append((m, r))
            elif run:
                res += [_with_lang(m2, r2, lang) for m2, r2 in run]
                run = []
            if l is not None:
                res.append(l)
        out = res
    return out


def clean_element_lines(lines, name, text=""):
    """Kopia elementu bez danych projektu: adresy -> None, teksty -> puste/domyslne, opis, numer, grupa, obrazy."""
    keep = {"No", "Trigger", "Message", "Ack", "Recovery", "Frequency", "Group", "Operator", "Arial",
            "Numeric Keypad", "CLR", "DEL", "Enter", "ASCII-KEY", "ALT", "ENT"}
    out, skip = [], False
    for l in lines:
        if skip and B64_LINE.fullmatch(l):
            continue
        skip = False
        kv = _kv(l)
        if kv is None:
            out.append(l)
            continue
        k, v = kv
        if k.startswith("Base64TextLen"):
            out.append(k + "=0")
            skip = True
            continue
        if l.startswith("@@u16 "):
            if k.startswith("wDescTextLen"):
                v = name.rstrip("?") + "_001"
            elif k.startswith("wTextLen"):
                v = text
            elif v not in keep:
                v = ""
            out.append("@@u16 %s=%s" % (k, json.dumps(v, ensure_ascii=False)))
            continue
        if k == "nPartsID":
            v = "1"
        elif k == "GroupID":
            v = "0"
        elif k.endswith("Var") and not re.match(r"^-?\d+(\.\d+)?$", v):
            v = "None"
        elif _is_address(v):
            v = "0"
        elif k in ("PIB Name", "Picture Name", "GoToScreenName", "ConfirmScreenName"):
            v = ""
        elif k in ("GoToScreenID", "ConfirmScreenID"):
            v = "0"
        out.append("%s=%s" % (k, v))
    return out


def _is_address(v):
    return "@" in v or v.startswith("$") or v.startswith("{")


def template_score(e):
    """Mniej = lepszy wzorzec: bez adresow poza kluczami *Var, bez obrazow, malo stanow."""
    addr = any(_is_address(v) for k, v in (kv for kv in map(_kv, e.lines) if kv) if not k.endswith("Var"))
    pic = any(l.startswith("Picture Name=") and l != "Picture Name=" for l in e.lines)
    return addr, pic, len(e.states) if len(e.states) > 1 else 0


def resolve_type(spec):
    """'5/1', '5_1' albo nazwa rodzaju (bez wielkosci liter) -> (Type, SubType)."""
    m = re.match(r"^(\d+)[/_](\d+)$", spec)
    if m:
        return int(m.group(1)), int(m.group(2))
    low = spec.lower().replace("_", " ")
    for k, n in ELEMENT_TYPES.items():
        if n.rstrip("?").lower() == low:
            return k
    raise SystemExit("Nieznany rodzaj elementu: %s (lista: types)" % spec)


BIT_WORD_TYPES = {(2, 1), (1, 5)}  # typ danych (MemLen) bit/slowo wynika z adresu


def _memlen_for(ttype, given, lines):
    """MemLen pasujacy do adresu wewnetrznego: $N.b -> 0 (bit), $N -> 1 (Word, jesli wzorzec mial bit)."""
    if ttype not in BIT_WORD_TYPES:
        return None
    addr = given.get("ReadVar") or given.get("WriteVar") or ""
    cur = next((l[7:] for l in lines if l.startswith("MemLen=")), None)
    if re.match(r"^\$\d+\.\d+$", addr):
        return "0"
    if re.match(r"^\$\d+$", addr) and cur == "0":
        return "1"
    if addr and not addr.startswith("$") and addr != "None":
        print("UWAGA: sprawdz MemLen (0 = bit, 1 = Word) dla adresu", addr)
    return None


def _text_size(text, lines):
    """Przyblizony rozmiar pola Text dla tekstu (DIAScreen nie przelicza go sam po otwarciu)."""
    size = next((int(l[10:]) for l in lines if l.startswith("FontSize0=") and l[10:].isdigit()), 16)
    rows = text.replace("\\n", "\n").split("\n")
    w = int(max(len(r) for r in rows) * size * 0.62) + 8
    h = int(len(rows) * size * 1.3) + 6
    return [("Width", str(w)), ("Height", str(h))]


def set_state_count(lines, count):
    """Ustawia liczbe stanow: dopisuje kopie ostatniego stanu (kolejne Value/StateIndex) albo usuwa nadmiarowe."""
    head_end, states = _section_ranges(lines)
    if not states or count < 1:
        raise SystemExit("Element nie ma stanow albo zla liczba stanow")
    if count < len(states):
        del lines[states[count][0]:states[-1][1]]
        return
    last_a, last_b = states[-1]
    block = lines[last_a:last_b]
    insert = []
    for n in range(len(states), count):
        nb = list(block)
        for k in ("Value", "StateIndex"):
            if not _set_in(nb, k, str(n)):
                nb.insert(1, "%s=%d" % (k, n))
        insert += nb
    lines[last_b:last_b] = insert


def cmd_set(proj, screen, ident, assigns, state=None, lang=0, states=None):
    s = find_screen(load_screens(proj), screen)
    given = _parse_assign(assigns, lang)
    if ident in ("-", "screen"):
        head_end = next((i for i, l in enumerate(s.lines) if l in ("[AuxKeyElement]", "[Element]")), len(s.lines))
        head = s.lines[:head_end]
        for k, v in given:
            if not _set_in(head, k, v):
                raise SystemExit("Brak klucza %s w naglowku ekranu" % k)
        _save_screen(s, 0, head, head_end)
        print("%s ekran: %s" % (s.file, "; ".join("%s=%s" % kv for kv in given)))
        return
    e = s.element(ident)
    lines = list(e.lines)
    if states:
        set_state_count(lines, int(states))
    msgs = (set_element(lines, given, state) if given else []) + (["stanow: %s" % states] if states else [])
    _save_screen(s, e.start - 1, lines, len(e.lines))
    print("%s el.%d %s: %s" % (s.file, e.id, e.type_name, "; ".join(msgs)))


def _max_desc_number(screens):
    n = 0
    for s in screens:
        for e in s.elements:
            m = re.search(r"_(\d+)$", e.props.get("wDescTextLen0", ""))
            if m:
                n = max(n, int(m.group(1)))
    return n


def cmd_add(proj, screen, source, assigns, src_proj=None, state=None, lang=0, force=False, states=None):
    """Dodaje element: z rodzaju (wzorzec z projektu albo ze skilla) albo kopie EKRAN:ELEMENT."""
    screens = load_screens(proj)
    s = find_screen(screens, screen)
    given = _parse_assign(assigns, lang)
    keys = {k for k, _ in given}
    auto = []
    if ":" in source:
        src_screen, _, src_el = source.rpartition(":")
        src_screens = load_screens(src_proj) if src_proj else screens
        e = find_screen(src_screens, src_screen).element(src_el)
        lines, ttype, origin = list(e.lines), e.type, "kopia %s" % source
        base = re.sub(r"_\d+$", "", e.props.get("wDescTextLen0", "")) or e.type_name.rstrip("?")
        if "GroupID" in e.props:
            auto.append(("GroupID", "0"))
        if not ({"X", "Y"} & keys) and not src_proj and e in s.elements:
            auto += [("X", str(int(e.props["X"]) + 20)), ("Y", str(int(e.props["Y"]) + 20))]
    else:
        ttype = resolve_type(source)
        name = element_type_name(*ttype).rstrip("?")
        base = name
        same = [e for sc in screens for e in sc.elements if e.type == ttype
                and not any(k.endswith("MacroLen") and v not in ("0", "") for k, v in e.props.items())]
        if same:
            src = min(same, key=template_score)
            lines, origin = clean_element_lines(src.lines, name), "wzorzec z projektu (%s:%d)" % (
                next(sc.id for sc in screens if src in sc.elements), src.id)
        else:
            info = ELEMENT_INFO.get(ttype, {})
            path = os.path.join(DATA_DIR, "wzorce", info.get("wzorzec") or "-")
            if not os.path.isfile(path):
                raise SystemExit("Brak wzorca dla %s - skopiuj element z innego projektu (EKRAN:ELEMENT --from=)"
                                 % name)
            lines, origin = _read_text(path).rstrip("\n").split("\n"), "wzorzec skilla " + os.path.basename(path)
        req = (ELEMENT_INFO.get(ttype, {}).get("wymagane") or "").split()
        req = [r.replace("0", str(lang)) if r.startswith("wTextLen") else r for r in req]
        missing = [r for r in req if r not in keys]
        if missing and not force:
            raise SystemExit("Brak wymaganych parametrow dla %s: %s (skroty: text, read, write, screen; "
                             "--force pomija kontrole)" % (name, ", ".join(missing)))
    lines = adapt_languages(lines, project_languages(proj))
    new_id = max([x.id for x in s.elements] + [0]) + 1
    auto = [("nPartsID", str(new_id)), ("wDescTextLen0", "%s_%03d" % (base, _max_desc_number(screens) + 1))] + auto
    if project_languages(proj) > 1:
        auto.append(("wDescTextLen1", auto[1][1]))
    mem = _memlen_for(ttype, dict(given), lines)
    if mem is not None and "MemLen" not in keys:
        auto.append(("MemLen", mem))
    gid = dict(given).get("GoToScreenID")
    if gid and "GoToScreenName" not in keys and any(l.startswith("GoToScreenName=") for l in lines):
        gname = next((x.name for x in screens if str(x.id) == gid), "")
        auto.append(("GoToScreenName", gname if gname.isascii() else ""))  # zwykla linia - tylko ASCII
    for k, v in given:  # adres podany -> lacze 1
        link = k[:-3] + "Link" if k.endswith("Var") else None
        if link and v != "None" and link not in keys and any(l.startswith(link + "=") for l in lines):
            auto.append((link, "1"))
    text = next((v for k, v in given if k.startswith("wTextLen")), None)
    if ttype == (10, 6) and text and not ({"Width", "Height"} & keys):
        auto += _text_size(text, lines)
    if not states and dict(auto).get("MemLen") == "0" and len(_section_ranges(lines)[1]) > 2:
        states = 2  # bit ma dwa stany
    if states:
        set_state_count(lines, int(states))
    set_element(lines, [a for a in auto if a[0] not in keys])
    msgs = set_element(lines, given, state or "all")
    idx = len(s.lines)
    if s.elements:
        last = s.elements[-1]
        idx = last.start - 1 + len(last.lines)
    elif "[AuxKeyElement]" in s.lines:
        idx = s.lines.index("[AuxKeyElement]") + 1
    _save_screen(s, idx, lines, 0)
    s = find_screen(load_screens(proj), screen)
    print("Dodano do %s (%s): %s" % (s.file, origin, element_summary(s.element(new_id))))
    for m in msgs:
        if m.startswith("UWAGA"):
            print(m)


# ---------------------------------------------------------------- ekrany, projekty, slownik

WINDOW_KEYS = ("Width", "Height", "CenterSubScreen", "SubScreenX", "SubScreenY", "AutoCloseTime")


def cmd_add_screen(proj, sid, name, base=None, sub=False, src=None, confirm=False, size=None, pos=None,
                   title=None):
    """Nowy ekran. Okno (podekran / ekran potwierdzenia) ma po IsConfirmScreen linie Width, Height,
    CenterSubScreen, SubScreenX, SubScreenY (podekran takze AutoCloseTime) - jak zapisuje DIAScreen."""
    screens = load_screens(proj)
    if any(str(s.id) == str(sid) for s in screens):
        raise SystemExit("Ekran %s juz istnieje" % sid)
    window = sub or confirm
    tpl = find_screen(screens, src) if src else next(
        (s for s in screens if s.props.get("ScreenType") == ("6" if confirm else "1" if sub else "0")),
        screens[0])
    end = next((i for i, l in enumerate(tpl.lines) if l in ("[Element]", "[Group]", "[AuxKeyElement]")),
               len(tpl.lines))
    lines = tpl.lines[:end] + ["[AuxKeyElement]"]
    old = dict(kv for kv in map(_kv, lines) if kv)
    sets = [("ID", str(sid)), ("wTextLen", name), ("wScreenDESCTextLen000", name)]
    if base is not None:
        sets.append(("BaseScreenID", str(base)))
    elif src is None:
        sets.append(("BaseScreenID", "0"))
    if title is not None:
        sets += [("wTitleTextLen000", title), ("IsUseTitleBar", "1" if title else "0")]
    sets += [("ScreenType", "6" if confirm else "1" if sub else "0"),
             ("IsSubScreen", "1" if sub else "0"), ("IsConfirmScreen", "1" if confirm else "0")]
    if window:
        w, _, h = (size or ("%sx%s" % (old["Width"], old["Height"]) if "Width" in old else "430x260")).partition("x")
        x, _, y = (pos or "0,0").partition(",")
        lines = [l for l in lines if (_kv(l) or ("",))[0] not in WINDOW_KEYS]
        at = next(i for i, l in enumerate(lines) if l.startswith("IsConfirmScreen=")) + 1
        win = ["Width=" + w, "Height=" + h, "CenterSubScreen=%d" % (pos is None), "SubScreenX=" + x,
               "SubScreenY=" + y] + (["AutoCloseTime=0"] if sub else [])
        lines[at:at] = win
        sets += [("DocSizeX", w), ("DocSizeY", h)]
    else:
        lines = [l for l in lines if (_kv(l) or ("",))[0] not in WINDOW_KEYS]
        sets += [("DocSizeX", old.get("PanelSizeX")), ("DocSizeY", old.get("PanelSizeY"))]
    for k, v in sets:
        if v is not None:
            _set_in(lines, k, v)
    fname = _unique("%s_%s" % (str(sid).zfill(3), _safe_name(name) or "screen"),
                    {s.file.lower() for s in screens}, ".txt")
    _write(os.path.join(proj, SCREEN_DIR, fname), "\n".join(lines).encode("utf-8"))
    ptxt = os.path.join(proj, "project.txt")
    plines = _read_text(ptxt).split("\n")
    last = max(i for i, l in enumerate(plines) if l.startswith(SCREEN_FILE_REF))
    plines.insert(last + 1, SCREEN_FILE_REF + SCREEN_DIR + "/" + fname)
    _write(ptxt, "\n".join(plines).encode("utf-8"))
    print("Dodano ekran %s %s (%s, naglowek z ekranu %d %s)" % (sid, name, fname, tpl.id, tpl.name))


def cmd_files(folder):
    import time
    found = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [x for x in dirs if not os.path.isfile(os.path.join(root, x, "meta.json"))]
        found += [os.path.join(root, n) for n in names if n.lower().endswith(".dpa")]
    for p in sorted(found):
        st = os.stat(p)
        dec = os.path.splitext(p)[0]
        info = ""
        if os.path.isfile(os.path.join(dec, "project.txt")):
            newer = max(os.path.getmtime(os.path.join(r, n)) for r, _, ns in os.walk(dec) for n in ns)
            info = "  [folder: %s]" % ("zmiany po decode" if newer > st.st_mtime + 2 else "jest")
        print("%s  %7d kB  %s%s" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                                    st.st_size // 1024, os.path.relpath(p, folder), info))
    if not found:
        print("Brak plikow .dpa w", folder)


def cmd_new(out_path, name=None, template=None):
    tpls = sorted(f for f in os.listdir(TEMPLATE_DIR) if f.lower().endswith(".dpa")) \
        if os.path.isdir(TEMPLATE_DIR) else []
    if not template:
        if not tpls:
            raise SystemExit("Brak szablonow w " + TEMPLATE_DIR)
        template = tpls[0]
    src = template if os.path.isfile(template) else os.path.join(TEMPLATE_DIR, template)
    if not os.path.isfile(src):
        raise SystemExit("Brak szablonu %s (dostepne: %s)" % (template, ", ".join(tpls)))
    if os.path.exists(out_path):
        raise SystemExit("Plik juz istnieje: " + out_path)
    out_dir = os.path.splitext(out_path)[0]
    decode(src, out_dir)
    if name:
        ptxt = os.path.join(out_dir, "project.txt")
        lines = _read_text(ptxt).split("\n")
        lines = ["Name=" + name if l.startswith("Name=") else l for l in lines]
        _write(ptxt, "\n".join(lines).encode("utf-8"))
    with open(os.path.join(out_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    meta["source"] = os.path.basename(out_path)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    encode(out_dir, out_path)
    print("Nowy projekt %s (szablon %s), rozlozony w %s" % (out_path, os.path.basename(src), out_dir))


def cmd_types():
    for (t, s), r in sorted(ELEMENT_INFO.items()):
        opt = r["opcjonalne"].split()
        print("%d/%d %s | wymagane: %s | opcje: %s%s" % (t, s, r["nazwa"], r["wymagane"] or "-",
                                                       " ".join(opt[:12]), " ..." if len(opt) > 12 else ""))


def cmd_params(pattern=None, ttype=None, scope=None):
    rows = _load_csv("parametry.csv")
    want = "%d/%d" % resolve_type(ttype) if ttype else None
    low = (pattern or "").lower()
    n = 0
    for r in rows:
        if scope and not r["zakres"].startswith(scope):
            continue
        if want and r["typy"] != "*" and want not in r["typy"].split():
            continue
        if low and low not in r["klucz"].lower() and low not in r["opis"].lower():
            continue
        vals = r["wartosci"].split("|")
        print("%s %s = %s | %s | %s%s" % (r["zakres"][:2], r["klucz"], r["domyslna"] or '""',
                                          "/".join(vals[:6]) if len(vals) > 1 else "-", r["opis"],
                                          "" if r["pewnosc"] == "ok" else " (?)"))
        n += 1
    if not n:
        print("Brak pasujacych parametrow")


# ---------------------------------------------------------------- dane z instalacji DIAScreen

def dia_dir():
    """Katalog instalacji DIAScreen: zmienna DIASCREEN_DIR albo najnowszy w Program Files."""
    env = os.environ.get("DIASCREEN_DIR")
    if env and os.path.isdir(env):
        return env
    import glob
    for root in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("ProgramFiles", r"C:\Program Files")):
        hits = sorted(glob.glob(os.path.join(root, "Delta Industrial Automation", "DIAStudio", "DIAScreen*")))
        if hits:
            return hits[-1]
    return None


def _dia_file(*parts):
    d = dia_dir()
    p = os.path.join(d, *parts) if d else None
    if not p or not os.path.isfile(p):
        raise SystemExit("Nie znaleziono %s w instalacji DIAScreen (ustaw zmienna DIASCREEN_DIR)" % "/".join(parts))
    return p


def panel_name(model):
    """ModelName z project.txt -> nazwa panelu wg ScrEditApp/PanelList.ini ([Inquire])."""
    key = "%08X" % (int(model) & 0xFFFFFFFF)
    try:
        path = _dia_file("ScrEditApp", "PanelList.ini")
    except SystemExit:  # brak instalacji - kopia listy w skillu
        return next((r["panel"] for r in _load_csv("panele.csv") if r["kod"] == key), None)
    with open(path, encoding="latin-1") as f:
        sec = None
        for line in f:
            line = line.strip()
            if line.startswith("["):
                sec = line
            elif sec == "[Inquire]" and line.upper().startswith(key + "="):
                return line.split("=", 1)[1]
    return None


def _ip(v, signed=True):
    n = int(v) & 0xFFFFFFFF
    return ".".join(str((n >> s) & 255) for s in (24, 16, 8, 0))


def cmd_info(proj):
    lines = _read_text(os.path.join(proj, "project.txt")).split("\n")
    p = {}
    for l in lines:
        kv = _kv(l)
        if kv and kv[0] not in p:
            p[kv[0]] = kv[1]
    model = p.get("ModelName", "?")
    print("Projekt: %s | DIAScreen %s | panel %s (ModelName=%s) | %sx%s" % (
        p.get("Name"), p.get("Version"), panel_name(model) or "?", model, p.get("PanelResWidth"),
        p.get("PanelResHeight")))
    if p.get("EthIP", "0") not in ("0", "1"):
        print("IP panelu: %s" % _ip(p["EthIP"]))
    n = 0
    while "ControllerName%d" % n in p:
        k = lambda s: p.get("%s%d" % (s, n))
        conn = "Ethernet %s:%s" % (_ip(k("PLCIP")), k("PLCPort")) if k("PLCIP") else \
            "COM%s %s,%s,%s,%s" % (k("PortNr"), k("baud"), k("databits"), k("parity"), k("stopbits"))
        print("Lacze %d: %s | %s | %s | stacja PLC %s" % (n, k("CommName"), k("ControllerName"), conn,
                                                          k("DefPLCStationNr")))
        n += 1
    print("Jezyki: %d | ekrany: %d | domyslny ekran: %s" % (
        project_languages(proj), sum(1 for l in lines if l.startswith(SCREEN_FILE_REF)), p.get("DefaultScreen")))
    lua = os.path.join(proj, LUA_DIR)
    if os.path.isdir(lua):
        print("Lua:", ", ".join(f for f in sorted(os.listdir(lua)) if f.endswith(".lua")))


def cmd_lua_api(pattern=None, full=False):
    """Funkcje Lua DIAScreen z ScrEditApp/Language/ProgList_English.xml instalacji."""
    try:
        path = _dia_file("ScrEditApp", "Language", "ProgList_English.xml")
    except SystemExit:  # brak instalacji - kopia w skillu
        path = os.path.join(DATA_DIR, "lua_api.xml")
    xml = _read_text(path)
    funcs = []
    for m in re.finditer(r'<function name="([^"]*)"\s*>(.*?)</function>', xml, re.S):
        body = [re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", c)).rstrip()
                for c in re.findall(r"<content>(.*?)</content>", m.group(2), re.S)]
        funcs.append((m.group(1), body))
    if not pattern:
        groups = {}
        for name, _ in funcs:
            g = name.rsplit(".", 1)[0] if "." in name else name
            groups[g] = groups.get(g, 0) + 1
        print("Grupy funkcji (lua-api GRUPA albo NAZWA):")
        print(", ".join("%s(%d)" % kv for kv in sorted(groups.items())))
        return
    low = pattern.lower()
    hits = [f for f in funcs if low in f[0].lower()] or [f for f in funcs if any(low in c.lower() for c in f[1])]
    if not hits:
        print("Brak funkcji pasujacych do", pattern)
    for name, body in hits:
        if full or len(hits) <= 3 or name.lower() == low:
            print("## " + name)
            print("\n".join(body))
        else:
            print(body[0] if body else name)


# ---------------------------------------------------------------- porownanie projektow

def _flat(lines):
    """Linie bloku (bez naglowka) -> {klucz: wartosc}; klucze podsekcji z przedrostkiem, np. State1.Width.
    Bajty makr (@@hex) trafiaja pod klucz '<klucz makra> bajty'."""
    out, sec, count, last = {}, "", {}, None
    for l in lines[1:]:
        if l.startswith("["):
            name = l[1:-1]
            count[name] = count.get(name, -1) + 1
            sec, last = "%s%d." % (name, count[name]), None
            continue
        if last and l.startswith("@@m "):
            c = parse_macro_line(l)
            if c != MACRO_END:
                out[last + " makro"] = (out.get(last + " makro", "") + " ; " + c[2][0].strip()).lstrip(" ;")
            continue
        if last and (l.startswith("@@hex ") or "Base64" in last and B64_LINE.fullmatch(l)):
            out[last + " bajty"] = out.get(last + " bajty", "") + l
            continue
        kv = _kv(l)
        if kv is None and l.startswith("@@"):  # @@lenhex, @@blob32...: tresc binarna
            k, _, v = l.partition(" ")[2].partition("=")
            last = sec + k
            out[last + " bajty"] = v
            continue
        last = sec + (kv[0] if kv else l)
        out[last] = kv[1] if kv else ""
    return out


def _flat_diff(a, b):
    """Roznice dwoch slownikow z _flat jako lista opisow 'klucz: stara -> nowa'."""
    out = []
    for k in list(a) + [k for k in b if k not in a]:
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        if k.endswith(" bajty"):
            out.append("%s zmienione" % k)
        else:
            show = lambda v: "brak" if v is None else json.dumps(_short(v, 30), ensure_ascii=False)
            out.append("%s: %s -> %s" % (k, show(va), show(vb)))
    return out


def _screen_parts(s):
    """Ekran -> (naglowek, elementy, reszta po ostatnim elemencie, np. [Group])."""
    if not s.elements:
        return s.lines, [], []
    last = s.elements[-1]
    end = last.start - 1 + len(last.lines)
    return s.lines[:s.elements[0].start - 1], s.elements, s.lines[end:]


def _diff_key(e):
    """Tozsamosc elementu przy porownaniu: DIAScreen uzywa ponownie nPartsID usunietego elementu,
    a rodzaju i opisu elementu nie da sie zmienic."""
    return e.id, e.type, e.props.get("wDescTextLen0", "")


def _diff_summary(e):
    s = element_summary(e)
    desc = json.dumps(e.props.get("wDescTextLen0", ""), ensure_ascii=False)
    return s if "desc=" + desc in s else s + "  " + desc


def _print_changes(changes, full, indent="    "):
    for c in changes if full else changes[:8]:
        print(indent + c)
    if not full and len(changes) > 8:
        print(indent + "... (+%d, --all pokazuje wszystkie)" % (len(changes) - 8))


def _dir_files(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def _same_file(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def cmd_diff(proj_a, proj_b, out=None, full=False):
    """Zmiany B wzgledem A: ekrany i elementy (wg ID i nPartsID), ustawienia projektu, Lua.
    out = plik .dpa: kopia B, na ktorej zostaja tylko elementy zmienione i dodane."""
    pa = _flat(["[Project]"] + [l for l in _read_text(os.path.join(proj_a, "project.txt")).split("\n")
                                if not l.startswith(SCREEN_FILE_REF)])
    pb = _flat(["[Project]"] + [l for l in _read_text(os.path.join(proj_b, "project.txt")).split("\n")
                                if not l.startswith(SCREEN_FILE_REF)])
    changes = _flat_diff(pa, pb)
    if os.path.isfile(os.path.join(proj_a, SQLITE_NAME)) and os.path.isfile(os.path.join(proj_b, SQLITE_NAME)) \
            and not _same_file(os.path.join(proj_a, SQLITE_NAME), os.path.join(proj_b, SQLITE_NAME)):
        changes.append("%s (hasla, siec...) zmieniona" % SQLITE_NAME)
    la, lb = os.path.join(proj_a, LUA_DIR), os.path.join(proj_b, LUA_DIR)
    for f in sorted(set(_dir_files(la)) | set(_dir_files(lb))):
        if f not in _dir_files(la):
            changes.append("Lua %s: dodany" % f)
        elif f not in _dir_files(lb):
            changes.append("Lua %s: usuniety" % f)
        elif not _same_file(os.path.join(la, f), os.path.join(lb, f)):
            changes.append("Lua %s: zmieniony" % f)
    if changes:
        print("# Ustawienia projektu: %d zmian" % len(changes))
        _print_changes(changes, full, "  ")

    screens_a = {s.id: s for s in load_screens(proj_a)}
    screens_b = load_screens(proj_b)
    ids_b = {s.id for s in screens_b}
    kept = {}  # plik ekranu B -> nPartsID elementow do zostawienia w projekcie roznic
    total = 0
    for s in screens_b:
        a = screens_a.get(s.id)
        if a is None:
            print("+ ekran %d %s (%s): nowy, %d el." % (s.id, s.name, s.file, len(s.elements)))
            kept[s.path] = {e.id for e in s.elements}
            total += len(s.elements)
            continue
        head_a, els_a, tail_a = _screen_parts(a)
        head_b, els_b, tail_b = _screen_parts(s)
        head = _flat_diff(_flat(head_a), _flat(head_b))
        by_key = {_diff_key(e): e for e in els_a}
        rows, keep = [], set()
        for e in els_b:
            old = by_key.get(_diff_key(e))
            if old is None:
                rows.append(("+ " + _diff_summary(e), []))
            elif old.lines != e.lines:
                rows.append(("~ " + _diff_summary(e), _flat_diff(_flat(old.lines), _flat(e.lines))
                             or ["kolejnosc linii"]))
            else:
                continue
            keep.add(e.id)
        keys = {_diff_key(e) for e in els_b}
        rows += [("- " + _diff_summary(e), []) for e in els_a if _diff_key(e) not in keys]
        if tail_a != tail_b:
            head.append("grupy ([Group]) zmienione")
        if not rows and not head:
            continue
        kept[s.path] = keep
        total += len(rows)
        print("# ekran %d %s (%s): %d zm." % (s.id, s.name, s.file, len(rows))
              + (" (nazwa w A: %s)" % a.name if a.name != s.name else ""))
        _print_changes(head, full, "  ekran: ")
        for title, ch in rows:
            print("  " + title)
            _print_changes(ch, full)
    for i, a in screens_a.items():
        if i not in ids_b:
            print("- ekran %d %s (%s): usuniety, %d el." % (i, a.name, a.file, len(a.elements)))
    if not changes and not kept and set(screens_a) <= ids_b:
        print("Brak roznic.")
    if out:
        _write_diff_project(proj_b, screens_b, kept, out)
        print("Projekt roznic (%d el.): %s" % (sum(len(k) for k in kept.values()), out))


def _write_diff_project(proj_b, screens_b, kept, out):
    """Kopia B z samymi ekranami ze zmianami (i ich ekranami bazowymi) i samymi elementami z 'kept'."""
    import tempfile
    by_id = {s.id: s for s in screens_b}
    files = set()
    for s in [s for s in screens_b if s.path in kept]:
        while s is not None and s.file not in files:
            files.add(s.file)
            s = by_id.get(int(s.props.get("BaseScreenID", "0") or 0))  # ekran bazowy musi zostac
    if not files and screens_b:
        files.add(screens_b[0].file)  # projekt musi miec choc jeden ekran
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "diff")
        shutil.copytree(proj_b, d)
        proj_lines = _read_text(os.path.join(d, "project.txt")).split("\n")
        proj_lines = [l for l in proj_lines if not l.startswith(SCREEN_FILE_REF)
                      or os.path.basename(l[len(SCREEN_FILE_REF):].strip()) in files]
        _write(os.path.join(d, "project.txt"), "\n".join(proj_lines).encode("utf-8"))
        for s in screens_b:
            keep = kept.get(s.path, set())
            head, els, tail = _screen_parts(s)
            els = [e for e in els if e.id in keep]
            groups = {e.props.get("GroupID") for e in els} - {None, "0"}
            if tail and tail[0] == "[Group]":  # zostaw tylko grupy uzywane przez pozostale elementy
                grp = re.compile(r"^Group(ID|XVar|YVar)(\d+)=(.*)$")
                rest = [l for l in tail[1:] if not grp.match(l)]
                vals = {}  # numer grupy -> {ID/XVar/YVar: wartosc}
                for l in tail[1:]:
                    m = grp.match(l)
                    if m:
                        vals.setdefault(int(m.group(2)), {})[m.group(1)] = m.group(3)
                g = [v for _, v in sorted(vals.items()) if v.get("ID") in groups]
                tail = (["[Group]"] + ["Group%s%d=%s" % (k, n, v[k]) for n, v in enumerate(g)
                                       for k in ("ID", "XVar", "YVar")] if g else []) + rest
            lines = head + [l for e in els for l in e.lines] + tail
            _write(os.path.join(d, SCREEN_DIR, s.file), "\n".join(lines).encode("utf-8"))
        encode(d, out)


USAGE = """Uzycie (KAT = katalog po decode; przegladanie dziala tez na PROJEKT.dpa):
  files   [FOLDER]                      pliki .dpa w folderze
  new     NOWY.dpa [--name=NAZWA] [--template=PLIK]   nowy projekt z szablonu (+ folder po decode)
  decode  PROJEKT.dpa [KAT]   |  encode KAT [WYJSCIE.dpa]  |  verify PROJEKT.dpa ...
  screens KAT                           lista ekranow
  list    KAT EKRAN [--xy]              elementy ekranu
  show    KAT EKRAN ELEMENT [--all]     parametry elementu
  find    KAT TEKST                     szukanie adresu/tekstu
  set     KAT EKRAN ELEMENT|- KLUCZ=WART ... [--state=N|all] [--lang=N] [--states=N]   (- = naglowek ekranu)
  add     KAT EKRAN RODZAJ|EKRAN:ELEMENT [KLUCZ=WART ...] [--from=KAT2] [--state=N|all] [--lang=N] [--states=N] [--force]
  add-screen KAT ID NAZWA [--base=ID] [--sub|--confirm] [--size=SZERxWYS] [--pos=X,Y] [--title=TYTUL] [--from=EKRAN]
  types                                 rodzaje elementow z parametrami wymaganymi
  params  [TEKST] [--type=T/S|NAZWA] [--scope=ekran|element|stan|akcja]   slownik parametrow
  info    KAT                           panel, lacza, jezyki, ekrany, programy Lua
  lua-api [TEKST] [--full]              funkcje Lua DIAScreen (z instalacji programu)
  diff    STARY NOWY [--out=ROZNICE.dpa] [--all]   zmienione ekrany i elementy (+ projekt z samymi zmianami)
KLUCZ: nazwa z pliku albo skrot text, desc, read, write, visible, screen, x, y, w, h, name, base.
EKRAN = ID, nazwa albo plik ekranu; ELEMENT = nPartsID albo opis; RODZAJ = np. "Numeric Display" albo 5/1."""


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = dict((a[2:].partition("=")[0], a.partition("=")[2]) for a in argv[1:] if a.startswith("--"))
    need = {"decode": 2, "encode": 2, "verify": 2, "screens": 2, "list": 3, "show": 4, "find": 3,
            "set": 4, "add": 4, "add-screen": 4, "files": 1, "new": 2, "types": 1, "params": 1, "info": 2, "lua-api": 1, "diff": 3}
    if not args or args[0] not in need or len(args) < need[args[0]]:
        print(USAGE)
        return 2
    cmd = args[0]
    lang = int(flags.get("lang") or 0)
    if cmd == "decode":
        print("Zdekodowano do:", decode(args[1], args[2] if len(args) > 2 else None))
    elif cmd == "encode":
        print("Zapisano:", encode(args[1], args[2] if len(args) > 2 else None))
    elif cmd == "verify":
        return 0 if all([verify(p) for p in args[1:]]) else 1
    elif cmd == "files":
        cmd_files(args[1] if len(args) > 1 else ".")
    elif cmd == "new":
        cmd_new(args[1], flags.get("name"), flags.get("template"))
    elif cmd == "lua-api":
        cmd_lua_api(args[1] if len(args) > 1 else None, "full" in flags)
    elif cmd == "types":
        cmd_types()
    elif cmd == "diff":
        cmd_diff(_project_dir(args[1]), _project_dir(args[2]), flags.get("out"), "all" in flags)
    elif cmd == "params":
        cmd_params(args[1] if len(args) > 1 else None, flags.get("type"), flags.get("scope"))
    elif cmd == "set":
        cmd_set(_project_dir(args[1], False), args[2], args[3], args[4:], flags.get("state"), lang,
                flags.get("states"))
    elif cmd == "add":
        src = _project_dir(flags["from"], False) if flags.get("from") else None
        cmd_add(_project_dir(args[1], False), args[2], args[3], args[4:], src, flags.get("state"), lang,
                "force" in flags, flags.get("states"))
    elif cmd == "add-screen":
        cmd_add_screen(_project_dir(args[1], False), args[2], args[3], flags.get("base"), "sub" in flags,
                       flags.get("from"), "confirm" in flags, flags.get("size"), flags.get("pos"),
                       flags.get("title"))
    else:
        proj = _project_dir(args[1])
        if cmd == "screens":
            cmd_screens(proj)
        elif cmd == "info":
            cmd_info(proj)
        elif cmd == "list":
            cmd_list(proj, args[2], "xy" in flags)
        elif cmd == "show":
            cmd_show(proj, args[2], args[3], "all" in flags)
        else:
            cmd_find(proj, args[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
