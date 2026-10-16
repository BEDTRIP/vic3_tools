"""The GUI identifiers of a mod: widget names, types, text icons — to compare two mods or two versions of a file.

The engine finds widgets by name: a copy of a vanilla ``.gui`` that lost a named widget crashes the game when the
code asks for it. A merged file's names must therefore be a superset of each merged version's names.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from vic3tools.gui import tree


def identifiers(root: Path, only: str | None = None) -> dict[str, dict[str, list[str]]]:
    """kind (``name``, ``type``, ``icon``) → identifier → files (relative to ``root``), from ``root/gui/**/*.gui``
    (``only``: one relative path)."""
    out: dict[str, dict[str, list[str]]] = {"name": defaultdict(list), "type": defaultdict(list),
                                             "icon": defaultdict(list)}
    files = [root / only] if only else sorted((root / "gui").rglob("*.gui"))
    for f in files:
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        for _trail, nd in tree.walk(tree.parse_file(f)):
            if nd.head[:1] == ["type"] and nd.is_block:
                out["type"][nd.name].append(rel)
            elif nd.key == "name" and nd.op and not nd.is_block:
                out["name"][nd.scalar().strip('"')].append(rel)
            elif nd.key == "texticon" and nd.is_block:
                for c in nd.props("icon"):
                    out["icon"][c.scalar().strip('"')].append(rel)
    return {k: dict(v) for k, v in out.items()}


def compare(a: dict, b: dict) -> dict[str, dict[str, list[str]]]:
    """Per kind: ``shared``, ``only_a``, ``only_b`` identifiers."""
    out = {}
    for kind in ("name", "type", "icon"):
        ka, kb = set(a.get(kind, {})), set(b.get(kind, {}))
        out[kind] = {"shared": sorted(ka & kb), "only_a": sorted(ka - kb), "only_b": sorted(kb - ka)}
    return out
