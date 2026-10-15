"""A GUI widget as the game builds it: types, ``using`` templates and ``block`` / ``blockoverride`` substituted.

Every property of the result keeps where its text is (``file:line``) and how it got there — the chain of ``using``,
``block`` and ``blockoverride`` steps. Rules:

- an instance ``K = { … }`` of a type ``K``: the bodies of the chain ``K → base → …`` (down to a native widget) and the
  instance's own body, innermost base first; a repeated property keeps the later value;
- ``blockoverride "x"``: the one closest to the block wins — the type chain from the base outwards, then the
  instance, then one handed down from an enclosing widget; overrides reach blocks of nested widgets too;
- the winner of a type or template defined more than once: the first one, files ordered by file name across all mods
  (``compat.winner.gui_type``);
- ``@name`` constants belong to the file that defines them: they work in text written in that file only.

Checked in the game (1.13.11, a probe window): a type's own ``blockoverride`` beats the instance's; an override
reaches a block of a nested type; a template defined twice — the first (``gui.log``: "already registered"); a constant
from another file does not resolve. Not checked: a handed-down override against a nested type's own one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.gui import tree
from vic3tools.gui.tree import GNode
from vic3tools.index.query import SetIndex

MAX_DEPTH = 40  # nesting of types / templates / widgets, against loops

# Properties a widget may carry several times (actions, not settings): no "later wins" for them.
REPEATABLE = {"onclick", "onrightclick", "on_start", "on_finish", "onhover", "onmousewheel", "state", "tooltipwidget",
              "input_action", "shortcut", "clicksound", "oversound", "on_keyframe_move", "modify_texture"}


@dataclass
class RNode:
    """A node of the resolved tree: a widget (``children`` is a list) or a property."""

    key: str
    node: GNode  # where its text is
    via: tuple[str, ...] = ()  # how it got here, outermost step first
    children: list[RNode] | None = None
    types: list[str] = field(default_factory=list)  # a widget's type chain, down to the native widget
    lost_to: RNode | None = None  # a property repeated later in the same widget

    @property
    def value(self) -> str:
        nd = self.node
        if nd.value and nd.is_block:  # color = hsv { … }
            return f"{nd.value} {{ " + " ".join(c.key for c in nd.children or []) + " }"
        return nd.scalar() if nd.op else nd.key

    @property
    def is_widget(self) -> bool:
        return self.children is not None

    def label(self) -> str:
        return self.node.label()

    def props(self, key: str) -> list[RNode]:
        return [c for c in self.children or [] if c.key == key and not c.is_widget]


class Resolver:
    """Expands widgets against the GUI types and templates of a mod set."""

    def __init__(self, si: SetIndex):
        self.si = si
        self._defs: dict[tuple[str, str], GNode | None] = {}
        self._consts: dict[Path, dict[str, GNode]] = {}
        self._where: dict[Path, tuple[str, str]] = {}

    # --- lookups ------------------------------------------------------------------------------------------------

    def find(self, kind: str, name: str | None) -> GNode | None:
        """The winning ``type`` / ``template`` definition of ``name`` (None for a native widget or an unknown name)."""
        if not name:
            return None
        k = (kind, name)
        if k not in self._defs:
            self._defs[k] = self._find(kind, name)
        return self._defs[k]

    def _find(self, kind: str, name: str) -> GNode | None:
        order = {m: i for i, m in enumerate(self.si.ms.mods)}
        hits = [h for h in self.si.defs(name) if h.kind == "gui_" + kind and h.loads]
        hits.sort(key=lambda h: (h.rel.rsplit("/", 1)[-1].encode(), h.rel.count("/"), order[h.mod], h.line))
        for h in hits:
            nodes = tree.parse_file(h.mod.path / h.rel)
            found = [nd for _t, nd in tree.walk(nodes) if nd.is_block and nd.head[:1] == [kind] and nd.name == name]
            best = next((nd for nd in found if nd.line == h.line), found[0] if found else None)
            if best:
                return best
        return None

    def const(self, file: Path | None, name: str) -> GNode | None:
        """``@name = value`` at the top of ``file``."""
        if file is None:
            return None
        if file not in self._consts:
            self._consts[file] = {nd.key: nd for nd in tree.parse_file(file) if nd.key.startswith("@") and nd.op}
        return self._consts[file].get(name)

    def where(self, nd: GNode) -> tuple[str, str]:
        """(mod name, path relative to the mod) of a node's file."""
        f = nd.file
        if f is None:
            return "", ""
        if f not in self._where:
            self._where[f] = ("", f.as_posix())
            for m in reversed(self.si.ms.mods):
                try:
                    self._where[f] = (m.name, f.relative_to(m.path).as_posix())
                    break
                except ValueError:
                    continue
        return self._where[f]

    def loc(self, nd: GNode, short: bool = False) -> str:
        mod, rel = self.where(nd)
        if short:
            return f"{rel.rsplit('/', 1)[-1]}:{nd.line}"
        return f"{mod}: {rel}:{nd.line}" if mod else f"{rel}:{nd.line}"

    # --- expansion ----------------------------------------------------------------------------------------------

    def expand(self, nd: GNode, overrides: dict[str, tuple[GNode, tuple]] | None = None, via: tuple = (),
               depth: int = 0) -> RNode:
        """The widget ``nd`` with its type chain, templates and blocks substituted."""
        is_def = nd.head[:1] == ["type"]  # a type definition itself: its chain, no instance body
        chain: list[GNode] = []
        t = nd if is_def else self.find("type", nd.key) if nd.op else None
        while t is not None and len(chain) < MAX_DEPTH and all(t is not c for c in chain):
            chain.append(t)
            t = self.find("type", t.value)
        key = nd.name if is_def else nd.key
        out = RNode(key, nd, via, [], [c.name for c in chain] + ([chain[-1].value or "?"] if chain else []))
        if depth > MAX_DEPTH:
            return out
        bodies = ([] if is_def else [(nd, via)]) + [(c, via + (f"type {c.name} ({self.loc(c, True)})",))
                                                     for c in chain]
        ov: dict[str, tuple[GNode, tuple]] = {}
        for body, bvia in reversed(bodies):  # the closest to the block first: the type chain, then the instance
            for c in body.children or []:
                if c.head[:1] == ["blockoverride"] and c.name not in ov:
                    ov[c.name] = (c, bvia)
        for name, o in (overrides or {}).items():  # handed down from enclosing widgets: only where none is closer
            ov.setdefault(name, o)
        for body, bvia in reversed(bodies):  # innermost base first: later text overrides earlier
            out.children += self._items(body.children or [], ov, bvia, depth)
        _mark_repeats(out)
        return out

    def _items(self, children: list[GNode], ov: dict, via: tuple, depth: int) -> list[RNode]:
        out: list[RNode] = []
        for c in children:
            head = c.head[:1]
            if head == ["blockoverride"]:
                continue
            if head == ["block"]:
                if c.name in ov:
                    o, _ovia = ov[c.name]
                    rest = {k: v for k, v in ov.items() if k != c.name}
                    step = f'blockoverride "{c.name}" ({self.loc(o, True)}) for block ({self.loc(c, True)})'
                    out += self._items(o.children or [], rest, via + (step,), depth + 1)
                else:
                    out += self._items(c.children or [], ov, via + (f'block "{c.name}" ({self.loc(c, True)})',),
                                       depth + 1)
            elif c.key == "using" and c.op and not c.is_block:
                tpl = self.find("template", c.value)
                if tpl is not None and depth < MAX_DEPTH:
                    step = f"using {c.value} ({self.loc(c, True)})"
                    out += self._items(tpl.children or [], ov, via + (step,), depth + 1)
                else:
                    out.append(RNode(c.key, c, via + ("template not found",)))
            elif c.head[:1] in (["type"], ["types"], ["template"], ["local_template"]):
                continue
            elif c.is_block and c.op and c.value is None and not c.is_list:
                out.append(self.expand(c, ov, via, depth + 1))
            else:
                out.append(RNode(c.key, c, via))
        return out


def _mark_repeats(w: RNode) -> None:
    last: dict[str, RNode] = {}
    for c in reversed(w.children or []):
        if c.is_widget or not c.node.op or c.key in REPEATABLE or c.key.startswith("@"):
            continue
        if c.key in last:
            c.lost_to = last[c.key]
        else:
            last[c.key] = c


# --- picking the widget at a line ------------------------------------------------------------------------------------


def widget_at(nodes: list[GNode], line: int) -> tuple[GNode | None, list[GNode]]:
    """The innermost widget around ``line`` (not a block, an override, a list or a typed value) and the chain above."""
    chain = tree.node_at(nodes, line)
    for i in range(len(chain) - 1, -1, -1):
        nd = chain[i]
        if nd.op and nd.value is None and not nd.is_list and nd.head[:1] not in (["block"], ["blockoverride"]):
            return nd, chain[:i]
        if nd.head[:1] == ["type"]:
            return nd, chain[:i]
    return None, chain


def walk(r: RNode, trail: tuple = ()):
    """Every node of a resolved tree with the widgets above it."""
    yield trail, r
    for c in r.children or []:
        if c.is_widget:
            yield from walk(c, trail + (r,))
        else:
            yield trail + (r,), c


def blocks_offered(res: Resolver, t: GNode) -> list[str]:
    """Names of the ``block``s a type (with its base chain) offers to override."""
    seen: list[str] = []
    cur, n = t, 0
    while cur is not None and n < MAX_DEPTH:
        for _trail, nd in tree.walk(cur.children or []):
            if nd.head[:1] == ["block"] and nd.name not in seen:
                seen.append(nd.name)
        cur, n = res.find("type", cur.value), n + 1
    return seen
