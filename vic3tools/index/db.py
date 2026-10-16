"""Per-mod SQLite index, built once and refreshed file by file.

One database per mod folder in the tools' cache (``cache/index/<name>.<hash>.sqlite``):

- ``files`` — every file of the mod with its time and size (a changed file is read again, a gone one dropped);
- ``defs`` — what the mod defines: top-level records of ``.txt`` files (``kind`` "db", with folder, directive and line
  range), GUI types and templates (``gui_type``, ``gui_template``), localization keys (``loc``, folder = language);
- ``refs`` — where names are used: every identifier of a script or GUI file outside comments (inside strings too, so
  ``[GetVariable('x')]`` counts), and the ``[…]`` / ``$…$`` parts of English localization; each with the top-level
  record it sits in (``ctx``) and the keys it sits under (``path``: ``set_variable>name``). Plain lowercase words
  without ``_`` (``yes``, ``limit``, ``wood``) are left out to keep the index small — ``v3 refs`` scans the files for
  those;
- ``loc_text`` — the text of localization keys in the languages that are kept (English and Russian by default).
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path

from vic3tools.core import loc, script
from vic3tools.core.paths import cache_dir
from vic3tools.core.vfs import Mod

VERSION = 4
TEXT_LANGS = ("english", "russian")
_LANG = re.compile(r"_l_([a-z_]+)\.yml$", re.I)
REF_LANGS = ("english",)
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[0-9]+)?")
_LOC_REF = re.compile(r"\$([A-Za-z0-9_.]+)\$|\[([^\]]*)\]")
_GUI_DEF = re.compile(r"^\s*(type|template)\s+([A-Za-z0-9_.:\-]+)\s*(=|\{)", re.M)

SCHEMA = """
CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT);
CREATE TABLE files (id INTEGER PRIMARY KEY, rel TEXT UNIQUE, mtime INTEGER, size INTEGER);
CREATE TABLE names (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE defs (name_id INTEGER, file_id INTEGER, line INTEGER, end_line INTEGER, kind TEXT, folder TEXT,
                   directive TEXT);
CREATE TABLE refs (name_id INTEGER, file_id INTEGER, line INTEGER, ctx_id INTEGER, path TEXT);
CREATE TABLE loc_text (file_id INTEGER, line INTEGER, key TEXT, lang TEXT, text TEXT);
CREATE INDEX defs_name ON defs (name_id);
CREATE INDEX defs_file ON defs (file_id);
CREATE INDEX refs_name ON refs (name_id);
CREATE INDEX refs_file ON refs (file_id);
CREATE INDEX loc_text_key ON loc_text (key);
CREATE INDEX loc_text_file ON loc_text (file_id);
"""


def kind_of(rel: str) -> str | None:
    """What a file holds: "db" (records), "gui", "loc" or None."""
    low = rel.lower()
    if low.startswith("gui/"):
        return "gui" if low.endswith(".gui") else None
    if low.startswith("localization/"):
        return "loc" if low.endswith(".yml") else None
    if low.endswith(".txt") and "/" in low:  # common/, events/, map_data/…; not the root's own files
        return "db"
    return None


def keep_ref(name: str) -> bool:
    return len(name) >= 3 and not (name.islower() and "_" not in name and "." not in name)


def db_path(mod: Mod) -> Path:
    tag = hashlib.md5(str(mod.path.resolve()).lower().encode()).hexdigest()[:12]
    safe = re.sub(r"[^\w.-]+", "_", mod.path.name)[:40]
    return cache_dir() / "index" / f"{safe}.{tag}.sqlite"


class Writer:
    """Fills one mod's database; name ids are cached in memory."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.ids = dict(con.execute("SELECT name, id FROM names"))

    def nid(self, name: str) -> int:
        i = self.ids.get(name)
        if i is None:
            i = self.con.execute("INSERT INTO names (name) VALUES (?)", (name,)).lastrowid
            self.ids[name] = i
        return i

    def drop(self, file_id: int) -> None:
        for table in ("defs", "refs", "loc_text"):
            self.con.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))

    def add_file(self, file_id: int, full: Path, rel: str) -> None:
        kind = kind_of(rel)
        if kind in ("db", "gui"):
            self._script(file_id, full, rel, kind)
        elif kind == "loc":
            self._loc(file_id, full, rel)

    def _script(self, file_id: int, full: Path, rel: str, kind: str) -> None:
        src = script.read(full)
        text = src.text
        folder = rel.rsplit("/", 1)[0]
        defs, refs = [], []
        if kind == "db":
            for e in script.parse(text)[0]:
                defs.append((self.nid(e.key), file_id, src.line(e.start), src.line(e.end), "db", folder, e.directive))
        else:
            # comments blanked with spaces, so offsets (and lines) stay those of the file
            bare = re.sub(r"#[^\n]*", lambda c: " " * len(c.group(0)), text)
            for m in _GUI_DEF.finditer(bare):
                start = m.start(2)
                defs.append((self.nid(m.group(2)), file_id, src.line(start), src.line(_block_end(bare, m.end())),
                             "gui_" + m.group(1), folder, ""))
        toks = script.tokens(text)
        stack: list[str] = []  # keys of the open blocks
        top_ctx = 0
        key = ""  # the key the current value belongs to
        n = len(toks)
        for i, t in enumerate(toks):
            s = t.s
            if s == "{":
                stack.append(key)
                key = ""
                continue
            if s == "}":
                if stack:
                    stack.pop()
                key = ""
                continue
            if s in script.OPS:
                continue
            is_key = i + 1 < n and toks[i + 1].s in script.OPS
            if is_key:
                key = script.split_directive(s)[1]
                if not stack:  # a top-level record: its key is a definition, not a reference
                    top_ctx = self.nid(key) if kind == "db" else 0
                    continue
            parent = stack[-1] if stack else ""
            path = f"{parent}>{key}" if parent else key
            line = src.line(t.pos)
            for m in _ID.finditer(s):
                name = m.group(0)
                if keep_ref(name):
                    refs.append((self.nid(name), file_id, line, top_ctx if stack else 0, path))
            if not is_key:
                key = "" if not stack else key
        self.con.executemany("INSERT INTO defs VALUES (?, ?, ?, ?, ?, ?, ?)", defs)
        self.con.executemany("INSERT INTO refs VALUES (?, ?, ?, ?, ?)", refs)

    def _loc(self, file_id: int, full: Path, rel: str) -> None:
        parts = rel.split("/")
        m = _LANG.search(parts[-1])  # the file name says the language (the engine's files are not in a language folder)
        lang = m[1] if m else parts[1] if len(parts) > 2 else ""
        defs, texts, refs = [], [], []
        for e in loc.read_file(full):
            nid = self.nid(e.key)
            defs.append((nid, file_id, e.line, e.line, "loc", lang, ""))
            if lang in TEXT_LANGS:
                texts.append((file_id, e.line, e.key, lang, e.text))
            if lang in REF_LANGS:
                for m in _LOC_REF.finditer(e.text):
                    for name in ([m.group(1)] if m.group(1) else [x.group(0) for x in _ID.finditer(m.group(2))]):
                        if keep_ref(name) or m.group(1):
                            refs.append((self.nid(name), file_id, e.line, nid, "loc"))
        self.con.executemany("INSERT INTO defs VALUES (?, ?, ?, ?, ?, ?, ?)", defs)
        self.con.executemany("INSERT INTO loc_text VALUES (?, ?, ?, ?, ?)", texts)
        self.con.executemany("INSERT INTO refs VALUES (?, ?, ?, ?, ?)", refs)


def _block_end(text: str, pos: int) -> int:
    """Offset of the ``}`` closing the first ``{`` at or after ``pos`` (comments already removed)."""
    i = text.find("{", pos - 1)
    if i < 0:
        return pos
    toks = script.tokens(text, i)
    j = script._close(toks, 0)
    return toks[j].pos if j < len(toks) else len(text)


def open_index(mod: Mod, rebuild: bool = False) -> sqlite3.Connection:
    """The mod's index, refreshed: files that changed since the last call are read again."""
    path = db_path(mod)
    path.parent.mkdir(parents=True, exist_ok=True)
    if rebuild:
        path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        ok = con.execute("SELECT value FROM meta WHERE name = 'version'").fetchone() == (str(VERSION),)
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        con.close()
        path.unlink(missing_ok=True)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
        con.execute("INSERT INTO meta VALUES ('version', ?)", (str(VERSION),))
        con.execute("INSERT INTO meta VALUES ('root', ?)", (str(mod.path),))
    _refresh(con, mod)
    return con


def _refresh(con: sqlite3.Connection, mod: Mod) -> None:
    known = {rel: (fid, mt, sz) for fid, rel, mt, sz in con.execute("SELECT id, rel, mtime, size FROM files")}
    seen: set[str] = set()
    w: Writer | None = None
    for dirpath, dirnames, filenames in os.walk(mod.path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = full.relative_to(mod.path).as_posix()
            seen.add(rel)
            try:
                st = full.stat()
            except OSError:
                continue
            old = known.get(rel)
            if old and old[1] == st.st_mtime_ns and old[2] == st.st_size:
                continue
            w = w or Writer(con)
            if old:
                fid = old[0]
                w.drop(fid)
                con.execute("UPDATE files SET mtime = ?, size = ? WHERE id = ?", (st.st_mtime_ns, st.st_size, fid))
            else:
                fid = con.execute("INSERT INTO files (rel, mtime, size) VALUES (?, ?, ?)",
                                  (rel, st.st_mtime_ns, st.st_size)).lastrowid
            w.add_file(fid, full, rel)
    for rel in known.keys() - seen:
        w = w or Writer(con)
        w.drop(known[rel][0])
        con.execute("DELETE FROM files WHERE id = ?", (known[rel][0],))
    con.commit()
