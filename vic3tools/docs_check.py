"""Check that the Russian translations in ``docs/ru/`` are current.

Each translation starts with ``<!-- source: docs/<file>.md @ <blob> -->``: the git blob hash of the English file it
was translated from. A different hash now means the English changed and the translation is stale.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_MARK = re.compile(r"<!--\s*source:\s*(\S+)\s*@\s*([0-9a-f]{7,40})\s*-->")


@dataclass
class Problem:
    kind: str  # "stale", "no_mark", "missing_source", "untranslated"
    path: str
    source: str = ""
    old: str = ""
    new: str = ""


def blob_hash(path: Path) -> str:
    """git's blob hash of the file as committed (line ends normalized to LF)."""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def mark_line(repo: Path, source: Path) -> str:
    """The first line for a new or updated translation of ``source``."""
    return f"<!-- source: {source.relative_to(repo).as_posix()} @ {blob_hash(source)[:12]} -->"


def check(repo: Path) -> tuple[list[Problem], int]:
    """Problems found and the number of translations checked. ``untranslated`` is a note, not a failure."""
    docs, ru = repo / "docs", repo / "docs" / "ru"
    problems: list[Problem] = []
    checked = 0
    for tr in sorted(ru.rglob("*.md")) if ru.is_dir() else []:
        rel = tr.relative_to(repo).as_posix()
        checked += 1
        head = tr.read_text(encoding="utf-8").split("\n", 1)[0]
        m = _MARK.search(head)
        if not m:
            problems.append(Problem("no_mark", rel))
            continue
        src = repo / m.group(1)
        if not src.is_file():
            problems.append(Problem("missing_source", rel, m.group(1)))
            continue
        now = blob_hash(src)
        if not now.startswith(m.group(2)):
            problems.append(Problem("stale", rel, m.group(1), m.group(2), now[: len(m.group(2))]))
    for src in sorted(docs.rglob("*.md")) if docs.is_dir() else []:
        if ru in src.parents or "benchmarks" in src.relative_to(docs).parts:
            continue
        if not (ru / src.relative_to(docs)).is_file():
            problems.append(Problem("untranslated", src.relative_to(docs).as_posix()))
    return problems, checked
