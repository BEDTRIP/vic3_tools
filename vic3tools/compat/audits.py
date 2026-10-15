"""Audits of a mod against the set it loads in.

- ``replace``: its ``REPLACE:`` / ``TRY_REPLACE:`` bodies that omit top-level fields of the record they replace —
  ``REPLACE:`` replaces the record whole, so every omitted field is lost.
- ``stale``: its full bodies (bare, ``REPLACE:``, ``TRY_REPLACE:``, ``REPLACE_OR_CREATE:``) that lack fields vanilla
  has for the same record — usually a body copied from an older game version.
- ``loc-dead``: its localization keys outside ``replace/`` that an earlier file already defines under another path —
  they never show (the first definition wins); the fix is to move them to ``localization/<lang>/replace/``.

Deliberate omissions are declared in a TOML file (``--declared``) and not reported again while they stay the same::

    [[declared]]
    folder = "common/buildings"
    key = "building_construction_sector"
    fields = ["has_max_level"]      # leave out to accept any omission
    why = "PSC's own body"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from vic3tools.compat.index import ModIndex
from vic3tools.compat.winner import _ordered
from vic3tools.core import script
from vic3tools.core.vfs import ModSet, VFile

SKIP_STALE = ("common/defines", "common/on_actions", "common/history")
FULL = ("", "REPLACE", "TRY_REPLACE", "REPLACE_OR_CREATE")


@dataclass
class Finding:
    file: VFile
    line: int
    key: str
    detail: list[str]  # missing fields, or [earlier mod, earlier file:line]
    against: str = ""  # where the compared record is
    declared: str = ""  # why, when declared on purpose


def load_declared(path: Path | None) -> dict[tuple[str, str], tuple[list[str] | None, str]]:
    if path is None:
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {(d["folder"], d["key"]): (sorted(d["fields"]) if "fields" in d else None, d.get("why", ""))
            for d in data.get("declared", [])}


def _fields(f: VFile, line: int, key: str, cache: dict) -> set[str] | None:
    """Top-level field names of the record ``key`` defined at ``line`` of a file."""
    if f.full not in cache:
        src = script.read(f.full)
        cache[f.full] = (src, script.parse(src.text)[0])
    src, entries = cache[f.full]
    for e in entries:
        if e.key == key and src.line(e.start) == line and e.is_block:
            return {c.key for c in e.children(src.text)}
    return None


def _db_folders(idx: list[ModIndex], mod_i: int) -> list[str]:
    return sorted({idx[mod_i].folder_of(r) for r, fd in idx[mod_i].files.items() if fd.defs})


def replace(ms: ModSet, idx: list[ModIndex], mod_i: int, declared: dict) -> list[Finding]:
    out: list[Finding] = []
    cache: dict = {}
    for folder in _db_folders(idx, mod_i):
        live, _dead = _ordered(ms, idx, folder, "db")
        record: dict[str, set[str]] = {}  # key → fields the record has so far
        origin: dict[str, str] = {}
        for f in live:
            for key, d, line in idx[f.order].files[f.rel].defs:
                fields = None
                if f.order == mod_i and d in ("REPLACE", "TRY_REPLACE") and key in record:
                    fields = _fields(f, line, key, cache) or set()
                    missing = sorted(record[key] - fields)
                    if missing:
                        out.append(_declare(Finding(f, line, key, missing, origin[key]), folder, declared))
                if d in ("INJECT", "TRY_INJECT", "INJECT_OR_CREATE") and key in record:
                    record[key] |= _fields(f, line, key, cache) or set()
                elif d in FULL or d in ("CREATE", "INJECT_OR_CREATE"):
                    record[key] = fields if fields is not None else (_fields(f, line, key, cache) or set())
                    origin[key] = f"{f.mod.name} {f.rel}:{line}"
    return out


def stale(ms: ModSet, idx: list[ModIndex], mod_i: int, declared: dict) -> list[Finding]:
    out: list[Finding] = []
    cache: dict = {}
    van = idx[0]
    van_defs: dict[tuple[str, str], tuple[VFile, int]] = {}
    for rel, fd in van.files.items():
        for key, d, line in fd.defs:
            if d in FULL:
                van_defs[(van.folder_of(rel), key)] = (VFile(van.mod, rel, 0), line)
    for rel, fd in sorted(idx[mod_i].files.items()):
        folder = idx[mod_i].folder_of(rel)
        if not fd.defs or folder.startswith(SKIP_STALE):
            continue
        f = VFile(idx[mod_i].mod, rel, mod_i)
        for key, d, line in fd.defs:
            if d not in FULL or (folder, key) not in van_defs:
                continue
            vf, vline = van_defs[(folder, key)]
            missing = sorted((_fields(vf, vline, key, cache) or set()) - (_fields(f, line, key, cache) or set()))
            if missing:
                out.append(_declare(Finding(f, line, key, missing, f"vanilla {vf.rel}:{vline}"), folder, declared))
    return out


def loc_dead(ms: ModSet, idx: list[ModIndex], mod_i: int, langs: tuple[str, ...]) -> list[Finding]:
    out: list[Finding] = []
    for lang in langs:
        live, _dead = _ordered(ms, idx, f"localization/{lang}", "loc")
        first: dict[str, tuple[VFile, int]] = {}
        for f in live:
            if "/replace/" in f.rel:
                continue
            for key, line in idx[f.order].files[f.rel].loc:
                if key not in first:
                    first[key] = (f, line)
                elif f.order == mod_i and first[key][0].rel != f.rel:
                    ef, eline = first[key]
                    out.append(Finding(f, line, key, [], f"{ef.mod.name} {ef.rel}:{eline}"))
    return out


def _declare(x: Finding, folder: str, declared: dict) -> Finding:
    dec = declared.get((folder, x.key))
    if dec and (dec[0] is None or dec[0] == x.detail):
        x.declared = dec[1] or "declared"
    return x
