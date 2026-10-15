"""Reader for the game's localization files (``*_l_<language>.yml``)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_HEADER = re.compile(r"^﻿?l_(\w+):\s*(#.*)?$")
_ENTRY = re.compile(r"^\s*([\w.\-']+):\d*\s*\"")


@dataclass(frozen=True)
class LocEntry:
    key: str
    text: str
    file: Path
    line: int


def read_file(path: Path) -> Iterator[LocEntry]:
    """Entries of one file, in order. The text is as written (escapes and formatting kept)."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for n, raw in enumerate(fh, 1):
            m = _ENTRY.match(raw)
            if not m:
                continue
            end = _closing_quote(raw, m.end())
            if end is not None:
                yield LocEntry(m.group(1), raw[m.end():end], path, n)


def _closing_quote(raw: str, start: int) -> int | None:
    """The quote that ends the text: the first one followed only by spaces or a ``#`` comment.

    Quotes inside the text are not escaped in the game's files, so the closing one is found by what follows it.
    """
    i = raw.find('"', start)
    while i != -1:
        rest = raw[i + 1:].strip()
        if not rest or rest.startswith("#"):
            return i
        i = raw.find('"', i + 1)
    return None


def language_files(loc_root: Path, lang: str) -> list[Path]:
    """All files of one language under a ``localization`` folder, ``replace/`` included, sorted."""
    folder = loc_root / lang
    if not folder.is_dir():
        return []
    return sorted(folder.rglob(f"*_l_{lang}.yml"))


def read_language(loc_root: Path, lang: str) -> dict[str, LocEntry]:
    """Key → entry for one language: the first file that defines a key wins; ``replace/`` overrides the rest."""
    out: dict[str, LocEntry] = {}
    replaced: set[str] = set()
    for f in language_files(loc_root, lang):
        in_replace = "replace" in f.relative_to(loc_root).parts
        for e in read_file(f):
            if in_replace and e.key not in replaced:
                out[e.key] = e
                replaced.add(e.key)
            elif e.key not in out:
                out[e.key] = e
    return out
