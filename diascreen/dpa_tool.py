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

Uzycie:
  python dpa_tool.py decode PROJEKT.dpa [KATALOG]
  python dpa_tool.py encode KATALOG [WYJSCIE.dpa]
  python dpa_tool.py verify PROJEKT.dpa      (test round-trip bajt-w-bajt)
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
    return b"\r\n".join(out)


def items_to_text(items, out_dir):
    """Zwraca linie project.txt; pliki poboczne (SQLite, Lua) zapisuje w out_dir."""
    lines = []
    for it in items:
        kind = it[0]
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
        if tag == "@@hex":
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


def main(argv):
    if len(argv) < 3 or argv[1] not in ("decode", "encode", "verify"):
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "decode":
        print("Zdekodowano do:", decode(argv[2], argv[3] if len(argv) > 3 else None))
    elif cmd == "encode":
        print("Zapisano:", encode(argv[2], argv[3] if len(argv) > 3 else None))
    else:
        return 0 if all([verify(p) for p in argv[2:]]) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
