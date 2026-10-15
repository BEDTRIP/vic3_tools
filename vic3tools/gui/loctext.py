"""Loc text as the player sees it, for measuring: the winning definition per language, references filled in."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from vic3tools.core import loc as locfile
from vic3tools.index.query import Hit, SetIndex


def texts(si: SetIndex, key: str, langs: list[str]) -> dict[str, tuple[str, Hit]]:
    """The text of ``key`` the game shows in each language (``replace/`` first, else the first in load order)."""
    order = {m: i for i, m in enumerate(si.ms.mods)}
    out = {}
    hits = [h for h in si.defs(key) if h.kind == "loc" and h.loads]
    for lang in langs:
        hs = sorted((h for h in hits if h.folder == lang),
                    key=lambda h: ("/replace/" not in h.rel, order[h.mod], h.rel.encode()))
        for h in hs:
            p = h.mod.path / h.rel
            text = _lines(str(p), p.stat().st_mtime_ns).get(h.line)
            if text is not None:
                out[lang] = (text, h)
                break
    return out


@lru_cache(maxsize=64)
def _lines(path: str, mtime: int) -> dict[int, str]:
    return {e.line: e.text for e in locfile.read_file(Path(path))}


_REF = re.compile(r"\$([A-Za-z_][\w.]*)\$|\[(concept_\w+)\]")


def expand(si: SetIndex, text: str, lang: str, depth: int = 0) -> str:
    """``$KEY$`` and ``[concept_x]`` replaced by their text in the same language (as the game shows them)."""
    if depth > 4:
        return text

    def sub(m: re.Match) -> str:
        key = m.group(1) or m.group(2)
        found = texts(si, key, [lang])
        if lang not in found:
            return m.group(0)
        return expand(si, found[lang][0], lang, depth + 1)

    return _REF.sub(sub, text)
