"""What each mod defines, per file, read from the mod's SQLite index (``vic3tools.index.db``).

For each mod: every file with its time and size, and for script files what they define — top-level records of
``.txt`` files (key, directive, line), GUI types of ``gui/``, localization keys of ``localization/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vic3tools.core.vfs import Mod, loads
from vic3tools.index import db
from vic3tools.index.db import kind_of  # noqa: F401 — re-exported for compat.conflicts


@dataclass
class FileDefs:
    sig: list  # [mtime_ns, size]
    defs: list = field(default_factory=list)  # [key, directive, line] — records of .txt files
    gui: list = field(default_factory=list)  # [type name, line]
    loc: list = field(default_factory=list)  # [key, line]


@dataclass
class ModIndex:
    mod: Mod
    files: dict[str, FileDefs]

    def folder_of(self, rel: str) -> str:
        return rel.rsplit("/", 1)[0] if "/" in rel else ""


def build(mod: Mod, rebuild: bool = False) -> ModIndex:
    """The definitions of one mod by file (the index is refreshed first); files the game never reads are left out."""
    con = db.open_index(mod, rebuild)
    try:
        by_id: dict[int, FileDefs] = {}
        files: dict[str, FileDefs] = {}
        for fid, rel, mt, sz in con.execute("SELECT id, rel, mtime, size FROM files"):
            if loads(rel):
                files[rel] = by_id[fid] = FileDefs([mt, sz])
        sql = ("SELECT d.file_id, n.name, d.directive, d.line, d.kind FROM defs d JOIN names n ON n.id = d.name_id "
               "WHERE d.kind IN ('db', 'gui_type', 'loc') ORDER BY d.file_id, d.line")
        for fid, name, directive, line, kind in con.execute(sql):
            fd = by_id.get(fid)
            if fd is None:
                continue
            if kind == "db":
                fd.defs.append([name, directive, line])
            elif kind == "gui_type":
                fd.gui.append([name, line])
            else:
                fd.loc.append([name, line])
    finally:
        con.close()
    return ModIndex(mod, files)
