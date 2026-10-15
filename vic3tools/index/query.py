"""Questions to the index of a mod set: where a name is defined and used, what a loc key says, a file's outline.

Answers are short and located (``mod: file:line``), meant to replace reading whole files.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.core import script
from vic3tools.core.vfs import Mod, ModSet, loads
from vic3tools.index import db

WRITE_KEYS = {"set_variable", "change_variable", "add_to_variable_list", "set_global_variable",
              "change_global_variable", "add_to_global_variable_list", "set_local_variable", "change_local_variable",
              "add_to_local_variable_list", "remove_variable", "remove_global_variable", "remove_list_variable",
              "remove_list_global_variable", "clear_variable_list", "clear_global_variable_list", "set_global_flag",
              "set_country_flag", "set_state_flag", "set_flag", "remove_global_flag", "save_scope_as",
              "save_temporary_scope_as", "add_modifier", "remove_modifier"}


@dataclass
class Hit:
    mod: Mod
    rel: str
    line: int
    end_line: int = 0
    kind: str = ""
    folder: str = ""
    directive: str = ""
    ctx: str = ""
    path: str = ""
    name: str = ""
    replaced: bool = False  # the file is replaced by a later mod's file with the same path: never loads

    @property
    def loads(self) -> bool:
        return not self.replaced and loads(self.rel)

    @property
    def why_not(self) -> str:
        """Why the game never reads this place ("" when it does)."""
        if self.replaced:
            return "file replaced by a later mod's file with the same path"
        return "" if loads(self.rel) else "outside the folders the game reads"

    @property
    def where(self) -> str:
        span = f"-{self.end_line}" if self.end_line and self.end_line != self.line else ""
        return f"{self.rel}:{self.line}{span}"

    @property
    def writes(self) -> bool:
        parent = self.path.split(">", 1)[0]
        return parent in WRITE_KEYS


@dataclass
class SetIndex:
    """Open indexes of every mod of a set, vanilla first."""

    ms: ModSet
    cons: list[sqlite3.Connection] = field(default_factory=list)
    live: dict[str, int] = field(default_factory=dict)  # rel → index of the mod whose copy loads

    @classmethod
    def open(cls, ms: ModSet, rebuild: bool = False) -> SetIndex:
        si = cls(ms, [db.open_index(m, rebuild) for m in ms.mods])
        for i, con in enumerate(si.cons):
            for (rel,) in con.execute("SELECT rel FROM files"):
                si.live[rel] = i
        return si

    def close(self) -> None:
        for c in self.cons:
            c.close()

    def _replaced(self, i: int, rel: str) -> bool:
        return self.live.get(rel, i) != i

    # --- definitions --------------------------------------------------------------------------------------------

    def defs(self, name: str) -> list[Hit]:
        out = []
        for i, con in enumerate(self.cons):
            sql = ("SELECT f.rel, d.line, d.end_line, d.kind, d.folder, d.directive FROM defs d "
                   "JOIN names n ON n.id = d.name_id JOIN files f ON f.id = d.file_id WHERE n.name = ? "
                   "ORDER BY f.rel, d.line")
            for rel, line, end, kind, folder, directive in con.execute(sql, (name,)):
                out.append(Hit(self.ms.mods[i], rel, line, end, kind, folder, directive, name=name,
                               replaced=self._replaced(i, rel)))
        return out

    # --- references ---------------------------------------------------------------------------------------------

    def names_like(self, pattern: str) -> list[str]:
        """Names in the index matching a glob (``*`` and ``?``), across the set."""
        rx = re.compile(fnmatch_to_re(pattern))
        prefix = re.split(r"[*?\[]", pattern, maxsplit=1)[0]
        found: set[str] = set()
        for con in self.cons:
            if prefix:
                rows = con.execute("SELECT name FROM names WHERE name >= ? AND name < ?", (prefix, prefix + "￿"))
            else:
                rows = con.execute("SELECT name FROM names")
            found.update(n for (n,) in rows if rx.fullmatch(n))
        return sorted(found)

    def refs(self, name: str) -> list[Hit]:
        out = []
        for i, con in enumerate(self.cons):
            sql = ("SELECT f.rel, r.line, c.name, r.path FROM refs r JOIN names n ON n.id = r.name_id "
                   "JOIN files f ON f.id = r.file_id LEFT JOIN names c ON c.id = r.ctx_id WHERE n.name = ? "
                   "ORDER BY f.rel, r.line")
            seen = set()
            for rel, line, ctx, path in con.execute(sql, (name,)):
                if (rel, line, path) in seen:
                    continue
                seen.add((rel, line, path))
                out.append(Hit(self.ms.mods[i], rel, line, ctx=ctx or "", path=path or "", name=name,
                               replaced=self._replaced(i, rel)))
        return out

    def scan_refs(self, word: str) -> list[Hit]:
        """References of a plain word the index leaves out, by reading the script files (whole words only)."""
        rx = re.compile(rf"(?<![\w.:]){re.escape(word)}(?![\w])")
        out = []
        for i, (m, con) in enumerate(zip(self.ms.mods, self.cons, strict=True)):
            for (rel,) in con.execute("SELECT rel FROM files"):
                if db.kind_of(rel) not in ("db", "gui"):
                    continue
                src = script.read(m.path / rel)
                text = re.sub(r"#[^\n]*", lambda x: " " * len(x.group(0)), src.text)
                for mt in rx.finditer(text):
                    out.append(Hit(m, rel, src.line(mt.start()), name=word, replaced=self._replaced(i, rel)))
        return out

    # --- localization -------------------------------------------------------------------------------------------

    def loc_texts(self, key: str) -> list[tuple[Hit, str]]:
        out = []
        for i, con in enumerate(self.cons):
            sql = ("SELECT f.rel, t.line, t.lang, t.text FROM loc_text t JOIN files f ON f.id = t.file_id "
                   "WHERE t.key = ? ORDER BY t.lang, f.rel")
            for rel, line, lang, text in con.execute(sql, (key,)):
                out.append((Hit(self.ms.mods[i], rel, line, folder=lang, name=key,
                                replaced=self._replaced(i, rel)), text))
        return out

    def loc_search(self, shown: str, limit: int = 10) -> list[tuple[int, Hit, str]]:
        """Loc entries whose fixed parts all appear, in order, in a text as the player sees it.

        ``[…]`` and ``$…$`` in an entry stand for anything; formatting (``#bold … #!``) is ignored. Ranked by how much
        of the shown text the entry's fixed parts cover.
        """
        target = _plain(shown).casefold()
        # Any word may be a filled-in placeholder, so a candidate needs only one of them; the fixed parts decide.
        words = sorted(set(re.findall(r"\w{4,}", target)), key=len, reverse=True)[:8]
        out = []
        for i, con in enumerate(self.cons):
            if words:
                where = " OR ".join("instr(cf(t.text), ?) > 0" for _ in words)
                con.create_function("cf", 1, lambda s: s.casefold() if s else "", deterministic=True)
                rows = con.execute("SELECT f.rel, t.line, t.lang, t.key, t.text FROM loc_text t JOIN files f "
                                   f"ON f.id = t.file_id WHERE {where}", words)
            else:
                rows = []
            for rel, line, lang, key, text in rows:
                parts = [p for p in re.split(r"\[[^\]]*\]|\$[^$]*\$|\\n", _plain(text).casefold()) if p.strip()]
                pos, covered = 0, 0
                for p in parts:
                    p = p.strip()
                    j = target.find(p, pos)
                    if j < 0:
                        break
                    pos, covered = j + len(p), covered + len(p)
                else:
                    if covered:
                        out.append((covered, Hit(self.ms.mods[i], rel, line, folder=lang, name=key,
                                                 replaced=self._replaced(i, rel)), text))
        out.sort(key=lambda x: (-x[0], x[1].name))
        return out[:limit]


def _plain(text: str) -> str:
    """Loc text without formatting codes (``#v``, ``#bold``, ``#!``) and icons (``@x!``)."""
    text = re.sub(r"#[A-Za-z_;]+ ?|#!", "", text)
    return re.sub(r"@\w+!", "", text)


def fnmatch_to_re(pattern: str) -> str:
    return "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)


# --- outline ---------------------------------------------------------------------------------------------------------


@dataclass
class Node:
    key: str
    line: int
    end_line: int
    label: str = ""  # name = "…" or the type a gui widget is
    children: list[Node] = field(default_factory=list)


def outline(path: Path) -> list[Node]:
    """The tree of records (and GUI widgets) of a script file with line ranges."""
    src = script.read(path)
    text = src.text

    def walk(lo: int, hi: int | None) -> list[Node]:
        nodes = []
        toks = script.tokens(text, lo, hi)
        i, n = 0, len(toks)
        while i < n:
            t = toks[i]
            # `key = {`, `key = value`, `type name = base {`, `template name {`, `types X {`, `blockoverride "x" {`
            j = i
            while j < n and toks[j].s not in ("{", "}") and not (j > i and toks[j].s in script.OPS) and j - i < 3:
                j += 1
            if j < n and toks[j].s in script.OPS:
                k = j + 1
                while k < n and toks[k].s not in ("{", "}") and k - j < 3 and not _is_key(toks, k):
                    k += 1
                if k < n and toks[k].s == "{":
                    close = script._close(toks, k)
                    head = " ".join(x.s for x in toks[i:k] if x.s not in script.OPS)
                    node = Node(head, src.line(t.pos), src.line(toks[min(close, n - 1)].pos))
                    node.children = walk(toks[k].pos + 1, toks[min(close, n - 1)].pos)
                    node.label = _label(text, toks[k].pos, toks[min(close, n - 1)].pos)
                    nodes.append(node)
                    i = close + 1
                    continue
                i = k if k > i else i + 1
                continue
            if j < n and toks[j].s == "{":
                close = script._close(toks, j)
                head = " ".join(x.s for x in toks[i:j])
                if head:
                    node = Node(head, src.line(t.pos), src.line(toks[min(close, n - 1)].pos))
                    node.children = walk(toks[j].pos + 1, toks[min(close, n - 1)].pos)
                    node.label = _label(text, toks[j].pos, toks[min(close, n - 1)].pos)
                    nodes.append(node)
                i = close + 1
                continue
            i += 1
        return nodes

    return walk(0, None)


def _is_key(toks, k: int) -> bool:
    return k + 1 < len(toks) and toks[k + 1].s in script.OPS


_LABEL = re.compile(r'^\s*(name|text|raw_text|datacontext)\s*=\s*("[^"\n]*"|[^\s}#]+)', re.M)
_LABEL_ORDER = ("name", "text", "raw_text", "datacontext")


def _label(text: str, open_pos: int, close_pos: int) -> str:
    """What names a block, from its own lines (not nested blocks): ``name``, else ``text``, ``raw_text``,
    ``datacontext`` — so a GUI widget can be found by its name or the text it shows."""
    body = text[open_pos + 1:close_pos]
    depth = 0
    found: dict[str, str] = {}
    for line in body.split("\n"):
        if depth == 0:
            m = _LABEL.match(line.split("#", 1)[0] if '"' not in line else line)
            if m and m.group(1) not in found:
                found[m.group(1)] = m.group(2).strip('"')
        depth += line.count("{") - line.count("}")
    for k in _LABEL_ORDER:
        if k in found:
            v = found[k]
            return (v if k == "name" else f"{k}: {v}")[:70]
    return ""


def is_property(nd: Node) -> bool:
    """A one-line block without children (``size = { 10 20 }``) — a property, not a widget or a record."""
    return not nd.children and nd.line == nd.end_line


def flatten(nodes: list[Node], depth: int, level: int = 0, props: bool = False) -> Iterator[tuple[int, Node]]:
    for nd in nodes:
        if not props and level and is_property(nd):
            continue
        yield level, nd
        if level + 1 < depth:
            yield from flatten(nd.children, depth, level + 1, props)


def find_nodes(nodes: list[Node], needle: str, trail: tuple = ()) -> Iterator[tuple[tuple, Node]]:
    """Nodes whose key or name contains ``needle``, with the keys above them."""
    for nd in nodes:
        here = trail + (nd,)
        if needle.casefold() in nd.key.casefold() or needle.casefold() in nd.label.casefold():
            yield here, nd
        yield from find_nodes(nd.children, needle, here)
