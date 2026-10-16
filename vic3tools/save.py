"""A text save (not ironman), read once into an index in the cache, then queried by pieces.

A save is 200–500 MB of script. The first look at it scans its braces (a few seconds) and stores every block down to
``DEPTH`` levels — its key, byte span and parent — in ``<cache>/saves/<name>-<hash>.sqlite``; the index is rebuilt
when the file changes. Then a query reads only the bytes it needs (``mmap``): a section, one entry of a database
(``building_manager={ database={ 123={ … } } }``), the fields of every entry of a section.

    s = Save.open(path)
    s.date, s.version, s.mods
    for bid, b in s.entries("building_manager"): b.get("building"), b.get("state") …
    s.countries()  → id → tag;  s.states() → id → (country id, region)

``Block`` is a parsed entry: ``get(key)`` the first scalar, ``all(key)`` every value, ``block(key)`` a sub-block,
``scalars()`` the flat fields. Parsing is lazy (per entry).
"""

from __future__ import annotations

import hashlib
import mmap
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from vic3tools.core import paths

DEPTH = 3  # blocks indexed: top sections (0), their children (1), grandchildren (2) — database entries are at 1 or 2
SCHEMA = """
CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT);
CREATE TABLE blocks (id INTEGER PRIMARY KEY, parent INTEGER, depth INTEGER, key TEXT, start INTEGER, end INTEGER);
CREATE INDEX blocks_parent ON blocks (parent, key);
CREATE INDEX blocks_top ON blocks (depth, key);
"""
_TOKEN = re.compile(rb'[{}]|"[^"]*"')
_KEY_BEFORE = re.compile(rb'([^\s={}"]+|"[^"]*")\s*=\s*$')


def save_dir() -> Path:
    return paths.resolve_roots()["documents"].path / "save games"


def find(name: str) -> Path:
    """A save by path, or by name in the documents' "save games" (with or without ``.v3``)."""
    p = Path(name)
    if p.is_file():
        return p
    for cand in (save_dir() / name, save_dir() / f"{name}.v3"):
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"no save {name} (a path, or a name in {save_dir()})")


def _index_path(path: Path) -> Path:
    st = path.stat()
    h = hashlib.sha1(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:12]
    d = paths.cache_dir() / "saves"
    d.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", path.stem)[:40]  # no backslash inside an f-string: Python 3.11
    return d / f"{stem}-{h}.sqlite"


def build_index(data: bytes, con: sqlite3.Connection) -> None:
    """Every block down to ``DEPTH``: (parent, depth, key, start of the key, end past ``}``)."""
    rows: list[tuple] = []
    stack: list[int] = []  # ids of the open indexed blocks; deeper blocks are counted, not stored
    depth = 0
    next_id = 1
    for m in _TOKEN.finditer(data):
        c = data[m.start()]
        if c == 0x7B:  # {
            if depth < DEPTH:
                lo = max(0, m.start() - 200)
                km = _KEY_BEFORE.search(data, lo, m.start())
                key = km.group(1).decode("utf-8", "replace").strip('"') if km else ""
                start = km.start(1) if km else m.start()
                rows.append([next_id, stack[-1] if stack else 0, depth, key, start, -1])
                stack.append(next_id)
                next_id += 1
            depth += 1
        elif c == 0x7D:  # }
            depth -= 1
            if depth < DEPTH and stack:
                bid = stack.pop()
                rows[bid - 1][5] = m.end()
    con.executemany("INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?)", rows)


@dataclass
class Block:
    """One parsed block of a save."""

    text: str

    @cached_property
    def _items(self) -> list[tuple[str, str | Block]]:
        return _items(self.text)

    @cached_property
    def _flat(self) -> dict[str, str]:
        """The block's own ``key=value`` lines, read by indentation (fast on the huge country entries)."""
        nl = self.text.find("\n")
        if nl < 0:
            return {}
        m = re.match(r"\n(\t*)\S", self.text[nl:nl + 200])
        if not m:
            return {}
        rx = re.compile(r"^" + m.group(1) + r'([^\s={}]+)=([^{\s][^\n]*)$', re.M)
        out: dict[str, str] = {}
        for k, v in rx.findall(self.text):
            out.setdefault(k, v.strip().strip('"'))
        return out

    def get(self, key: str, default: str | None = None) -> str | None:
        if "\n" in self.text:
            return self._flat.get(key, default)
        for k, v in self._items:
            if k == key and isinstance(v, str):
                return v
        return default

    def all(self, key: str) -> list[str | Block]:
        return [v for k, v in self._items if k == key]

    def block(self, key: str) -> Block | None:
        for k, v in self._items:
            if k == key and isinstance(v, Block):
                return v
        return None

    def items(self) -> list[tuple[str, str | Block]]:
        return self._items

    def scalars(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in self._items:
            if isinstance(v, str) and k not in out:
                out[k] = v
        return out

    def values(self) -> list[str]:
        """Bare items of a list block (``{ 1 2 3 }``)."""
        return [v for k, v in self._items if k == "" and isinstance(v, str)]


_ITEM = re.compile(r'"[^"]*"|[{}=]|[^\s{}="]+')


def _items(text: str) -> list[tuple[str, str | Block]]:
    """The direct items of a block's body (``key=value``, ``key={…}``, bare values)."""
    body_start = text.find("{")
    body = text[body_start + 1:text.rfind("}")] if body_start >= 0 else text
    toks = [(m.group(0), m.start(), m.end()) for m in _ITEM.finditer(body)]
    out: list[tuple[str, str | Block]] = []
    i, n = 0, len(toks)
    while i < n:
        s = toks[i][0]
        if s == "}":
            i += 1
            continue
        if i + 1 < n and toks[i + 1][0] == "=" and i + 2 < n:
            key = s.strip('"')
            v = toks[i + 2]
            if v[0] == "{":
                end = _close(toks, i + 2)
                out.append((key, Block("{" + body[v[2]:toks[end][1]] + "}")))
                i = end + 1
            elif i + 3 < n and toks[i + 3][0] == "{" and v[0] not in "{}=":  # key=rgb { … }
                end = _close(toks, i + 3)
                out.append((key, Block("{" + body[toks[i + 3][2]:toks[end][1]] + "}")))
                i = end + 1
            else:
                out.append((key, v[0].strip('"')))
                i += 3
        elif s == "{":
            end = _close(toks, i)
            out.append(("", Block("{" + body[toks[i][2]:toks[end][1]] + "}")))
            i = end + 1
        else:
            out.append(("", s.strip('"')))
            i += 1
    return out


def _close(toks, i: int) -> int:
    depth = 0
    for j in range(i, len(toks)):
        if toks[j][0] == "{":
            depth += 1
        elif toks[j][0] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(toks) - 1


class Save:
    def __init__(self, path: Path, con: sqlite3.Connection, fh, mm):
        self.path, self.con, self._fh, self.mm = path, con, fh, mm

    @classmethod
    def open(cls, path: Path | str, rebuild: bool = False) -> Save:
        path = find(str(path))
        ip = _index_path(path)
        fh = open(path, "rb")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        if mm[:3] == b"SAV" and b"meta_data" not in mm[:200]:
            raise ValueError(f"{path.name}: a binary (ironman or compressed) save; only text saves are read")
        if rebuild and ip.exists():
            ip.unlink()
        fresh = not ip.exists()
        con = sqlite3.connect(ip)
        if fresh:
            try:
                con.executescript(SCHEMA)
                build_index(mm, con)
                con.execute("INSERT INTO meta VALUES ('source', ?)", (str(path),))
                con.commit()
            except BaseException:
                con.close()
                ip.unlink(missing_ok=True)
                raise
        return cls(path, con, fh, mm)

    def close(self) -> None:
        self.con.close()
        self.mm.close()
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- raw access ---------------------------------------------------------------------------------------------

    def text(self, start: int, end: int) -> str:
        return self.mm[start:end].decode("utf-8", "replace")

    def sections(self) -> list[tuple[str, int, int]]:
        return [(k, s, e) for k, s, e in self.con.execute("SELECT key, start, end FROM blocks WHERE depth = 0 "
                                                           "ORDER BY start")]

    def section(self, key: str) -> Block | None:
        row = self.con.execute("SELECT start, end FROM blocks WHERE depth = 0 AND key = ? ORDER BY start LIMIT 1",
                               (key,)).fetchone()
        return Block(self.text(*row)) if row else None

    def _section_id(self, key: str) -> int | None:
        row = self.con.execute("SELECT id FROM blocks WHERE depth = 0 AND key = ? ORDER BY start LIMIT 1",
                               (key,)).fetchone()
        return row[0] if row else None

    def entries(self, section: str) -> Iterator[tuple[str, Block]]:
        """The entries of a database section: ``section={ database={ id={…} } }`` or ``section={ id={…} }``."""
        sid = self._section_id(section)
        if sid is None:
            return
        db = self.con.execute("SELECT id FROM blocks WHERE parent = ? AND key = 'database'", (sid,)).fetchone()
        parent = db[0] if db else sid
        for key, s, e in self.con.execute("SELECT key, start, end FROM blocks WHERE parent = ? ORDER BY start",
                                          (parent,)):
            yield key, Block(self.text(s, e))

    def entry(self, section: str, eid: str) -> Block | None:
        for k, b in self.entries(section):
            if k == eid:
                return b
        return None

    def grep(self, pattern: str, context: int = 200, limit: int = 20) -> Iterator[tuple[int, str, str]]:
        """Pieces of the save around a regex: (offset, top section, text)."""
        rx = re.compile(pattern.encode())
        secs = self.sections()
        for n, m in enumerate(rx.finditer(self.mm)):
            if n >= limit:
                return
            sec = next((k for k, s, e in secs if s <= m.start() < e), "")
            yield m.start(), sec, self.text(max(0, m.start() - context), m.end() + context)

    # --- what most queries need -----------------------------------------------------------------------------------

    @cached_property
    def meta(self) -> Block:
        return self.section("meta_data") or Block("{}")

    @property
    def date(self) -> str:
        m = re.search(rb"\ndate=([\d.]+)", self.mm[:20000])
        return m.group(1).decode() if m else ""

    @property
    def version(self) -> str:
        return self.meta.get("version", "") or ""

    @property
    def mods(self) -> list[str]:
        b = self.meta.block("mods")
        return b.values() if b else []

    @cached_property
    def _countries(self) -> dict[str, str]:
        return {cid: b.get("definition", "") or "" for cid, b in self.entries("country_manager")
                if b.get("definition")}

    def countries(self) -> dict[str, str]:
        """Country id → tag."""
        return self._countries

    def tag_id(self, tag: str) -> str | None:
        return next((cid for cid, t in self._countries.items() if t == tag), None)

    @cached_property
    def _states(self) -> dict[str, tuple[str, str]]:
        return {sid: (b.get("country", "") or "", b.get("region", "") or "") for sid, b in self.entries("states")}

    def states(self) -> dict[str, tuple[str, str]]:
        """State id → (country id, state region id)."""
        return self._states


def number(v: str | None, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except ValueError:
        return default
