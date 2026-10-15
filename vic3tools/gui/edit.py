"""Set properties of one widget in a ``.gui`` file, touching nothing else.

A property is looked for at the widget's own level (not in nested blocks): an existing ``KEY = …`` is replaced
(the last one, the one that applies), a missing one is inserted before the widget's closing ``}`` with the
indentation of its other lines. The file keeps its BOM and line ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vic3tools.core import script
from vic3tools.gui import tree
from vic3tools.gui.tree import GNode


@dataclass
class Change:
    key: str
    line: int
    was: str | None  # None: inserted
    becomes: str
    others: int = 0  # more lines with the same key at this level, left as they are


def plan(text: str, w: GNode, values: list[tuple[str, str]]) -> tuple[str, list[Change]]:
    """The new text and what changes; ``w`` is a node parsed from ``text``."""
    edits: list[tuple[int, int, str]] = []  # (start, end, new text)
    changes: list[Change] = []
    lines = text.split("\n")
    close_line = lines[w.end_line - 1] if w.end_line else ""
    child_lines = [c.line for c in w.children or [] if c.line != w.line]
    if child_lines:
        ref = lines[child_lines[0] - 1]
        indent = ref[:len(ref) - len(ref.lstrip())]
    else:
        base = lines[w.line - 1]
        indent = base[:len(base) - len(base.lstrip())] + "\t"
    insert_at = w.end - 1  # the closing brace
    for key, value in values:
        new = f"{key} = {value}"
        own = [c for c in w.children or [] if c.key == key and c.op]
        if own:
            c = own[-1]
            edits.append((c.start, c.end, new))
            changes.append(Change(key, c.line, text[c.start:c.end], new, len(own) - 1))
            continue
        if close_line.strip() == "}" and w.end_line != w.line:  # `}` on a line of its own
            pos = text.rfind("\n", 0, insert_at) + 1
            edits.append((pos, pos, f"{indent}{new}\n"))
            changes.append(Change(key, w.end_line, None, new))
        else:
            edits.append((insert_at, insert_at, f"{new} "))
            changes.append(Change(key, w.end_line, None, new))
    out = text
    for start, end, new in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:start] + new + out[end:]
    return out, changes


def find(nodes: list[GNode], needle: str) -> list[GNode]:
    """Widgets whose key or label contains ``needle``."""
    low = needle.casefold()
    return [nd for _t, nd in tree.walk(nodes)
            if nd.is_block and nd.op and not nd.is_list and (low in nd.key.casefold() or low in nd.label().casefold())]


def apply(path: Path, w: GNode, values: list[tuple[str, str]], dry: bool = False) -> list[Change]:
    src = script.read(path)
    new, changes = plan(src.text, w, values)
    if not dry and new != src.text:
        script.write(path, new, bom=src.bom, eol=src.eol)
    return changes
