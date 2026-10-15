"""Per-mod index of definitions, cached and updated by itself.

For each mod: every file (with its size and time, to notice changes), and for script files what they define:
top-level records of ``.txt`` files — ``common/``, ``events/``, ``map_data/``… (key, directive, line), GUI types of
``gui/``, localization keys of ``localization/``. The cache lives in the tools' cache folder, one JSON per mod
folder; on the next use only the files that changed are read again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.core import loc, script
from vic3tools.core.paths import cache_dir
from vic3tools.core.vfs import Mod

VERSION = 2
SCRIPT_EXT = (".txt", ".gui", ".yml")
_GUI_TYPE = re.compile(r"^\s*type\s+([A-Za-z0-9_.:\-]+)\s*=", re.M)


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


def kind_of(rel: str) -> str | None:
    """What a file defines: "db" (records), "gui", "loc" or None."""
    low = rel.lower()
    if low.startswith("gui/"):
        return "gui" if low.endswith(".gui") else None
    if low.startswith("localization/"):
        return "loc" if low.endswith(".yml") else None
    if low.endswith(".txt") and "/" in low:  # common/, events/, map_data/state_regions/…; not the root's own files
        return "db"
    return None


def scan_file(full: Path, rel: str) -> tuple[list, list, list]:
    kind = kind_of(rel)
    if kind == "db":
        src = script.read(full)
        return [[e.key, e.directive, src.line(e.start)] for e in script.parse(src.text)[0]], [], []
    if kind == "gui":
        text = script.read(full).text
        bare = re.sub(r"#[^\n]*", "", text)
        return [], [[m.group(1), bare.count("\n", 0, m.start(1)) + 1] for m in _GUI_TYPE.finditer(bare)], []
    if kind == "loc":
        return [], [], [[e.key, e.line] for e in loc.read_file(full)]
    return [], [], []


def _cache_file(mod: Mod) -> Path:
    tag = hashlib.md5(str(mod.path.resolve()).lower().encode()).hexdigest()[:12]
    safe = re.sub(r"[^\w.-]+", "_", mod.path.name)[:40]
    return cache_dir() / "index" / f"{safe}.{tag}.json"


def build(mod: Mod, rebuild: bool = False) -> ModIndex:
    """The index of one mod, reading only files that changed since the cached one."""
    cf = _cache_file(mod)
    old: dict = {}
    if cf.is_file() and not rebuild:
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
            if data.get("version") == VERSION:
                old = data["files"]
        except (OSError, ValueError, KeyError):
            old = {}
    files: dict[str, FileDefs] = {}
    changed = False
    for dirpath, dirnames, filenames in os.walk(mod.path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = full.relative_to(mod.path).as_posix()
            try:
                st = full.stat()
            except OSError:
                continue
            sig = [st.st_mtime_ns, st.st_size]
            prev = old.get(rel)
            if prev and prev["sig"] == sig:
                files[rel] = FileDefs(**prev)
                continue
            changed = True
            d, g, lk = scan_file(full, rel) if fn.lower().endswith(SCRIPT_EXT) else ([], [], [])
            files[rel] = FileDefs(sig, d, g, lk)
    if changed or set(files) != set(old):
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_suffix(".tmp")
        payload = {"version": VERSION, "root": str(mod.path), "files": {r: f.__dict__ for r, f in files.items()}}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, cf)
    return ModIndex(mod, files)
