"""The tree of a `.gui` file: widgets, properties, types, templates, blocks — with positions.

A node is ``head op value { children }`` with any part missing:

- ``textbox = { … }`` — head ``["textbox"]``, a block;
- ``fontsize = 20`` — a property (``value`` = "20");
- ``type default_header = default_header_properties { … }`` — head ``["type", "default_header"]``, ``value`` = the base;
- ``template fontsize_large { … }``, ``block "text" { … }``, ``blockoverride "text" { … }``, ``types X { … }``;
- ``color = hsv { … }`` — ``value`` = "hsv" and a block;
- bare items of a list (``{ 100 40 }``) — head ``[word]``, no op, no block.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from vic3tools.core import script

HEAD_WORDS = {"type", "template", "block", "blockoverride", "types", "local_template"}


@dataclass
class GNode:
    head: list[str]
    op: str | None = None
    value: str | None = None
    children: list[GNode] | None = None  # None: not a block
    line: int = 0
    end_line: int = 0
    start: int = 0  # offset of the first head token
    end: int = 0  # offset just past the node
    open: int = -1  # offset of `{`
    file: Path | None = None

    @property
    def key(self) -> str:
        return self.head[0] if self.head else ""

    @property
    def name(self) -> str:
        """The name of a `type` / `template` / `block` / `blockoverride` / `types` (quotes removed)."""
        return self.head[1].strip('"') if len(self.head) > 1 else ""

    @property
    def is_block(self) -> bool:
        return self.children is not None

    @property
    def is_list(self) -> bool:
        """A block of bare items only, like ``{ 100 40 }`` — a value, not a widget."""
        return self.is_block and bool(self.children) and all(c.op is None and not c.is_block for c in self.children)

    def scalar(self) -> str:
        if self.is_list:
            return "{ " + " ".join(c.key for c in self.children) + " }"
        return self.value or ""

    def props(self, key: str) -> list[GNode]:
        return [c for c in self.children or [] if c.key == key and c.op]

    def label(self) -> str:
        for k in ("name", "text", "raw_text", "datacontext"):
            p = self.props(k)
            if p:
                v = p[0].scalar().strip('"')
                return v if k == "name" else f"{k}: {v}"
        return ""


def parse_text(text: str, path: Path | None = None) -> list[GNode]:
    src = script.Source(text, False, "\n", path)
    toks = script.tokens(text)
    nodes, _ = _parse(toks, 0, len(toks), src)
    return nodes


@lru_cache(maxsize=256)
def _parse_file_cached(path: str, mtime: int, size: int) -> tuple[GNode, ...]:
    src = script.read(path)
    toks = script.tokens(src.text)
    nodes, _ = _parse(toks, 0, len(toks), src)
    return tuple(nodes)


def parse_file(path: Path) -> list[GNode]:
    st = path.stat()  # the size too: a quick rewrite may keep the mtime
    return list(_parse_file_cached(str(path), st.st_mtime_ns, st.st_size))


def _parse(toks, i: int, n: int, src: script.Source) -> tuple[list[GNode], int]:
    out: list[GNode] = []
    while i < n:
        t = toks[i]
        if t.s == "}":
            return out, i
        # gather the head: up to 3 words before an operator or `{`
        j = i
        while j < n and toks[j].s not in ("{", "}") and toks[j].s not in script.OPS and j - i < 3:
            j += 1
        if j < n and toks[j].s in script.OPS:
            head = [x.s for x in toks[i:j]]
            # words before the key that are not a head form (`a b c = …`) are bare items
            if len(head) > 1 and head[0] not in HEAD_WORDS:
                for x in toks[i:j - 1]:
                    out.append(_bare(x, src))
                head = head[-1:]
                i = j - 1
            op = toks[j].s
            if j + 1 >= n:
                break
            v = toks[j + 1]
            if v.s == "{":
                node, i = _block(toks, i, j + 1, n, head, op, None, src)
            elif j + 2 < n and toks[j + 2].s == "{" and v.s not in script.OPS:
                node, i = _block(toks, i, j + 2, n, head, op, v.s, src)
            else:
                node = GNode(head, op, v.s, None, src.line(toks[i].pos), src.line(v.pos), toks[i].pos, v.end,
                             file=src.path)
                i = j + 2
            out.append(node)
        elif j < n and toks[j].s == "{" and j > i and toks[i].s in HEAD_WORDS:
            node, i = _block(toks, i, j, n, [x.s for x in toks[i:j]], None, None, src)
            out.append(node)
        elif j < n and toks[j].s == "{" and j == i:
            node, i = _block(toks, i, j, n, [], None, None, src)  # an unnamed block
            out.append(node)
        else:
            # bare words (list items) up to the next structure
            stop = j if j > i else i + 1
            for x in toks[i:stop]:
                out.append(_bare(x, src))
            i = stop
    return out, i


def _bare(t, src) -> GNode:
    line = src.line(t.pos)
    return GNode([t.s], line=line, end_line=line, start=t.pos, end=t.end, file=src.path)


def _block(toks, i, oi, n, head, op, value, src) -> tuple[GNode, int]:
    children, k = _parse(toks, oi + 1, n, src)
    close = toks[k] if k < n else toks[-1]
    node = GNode(head, op, value, children, src.line(toks[i].pos), src.line(close.pos), toks[i].pos, close.end,
                 toks[oi].pos, src.path)
    return node, k + 1


def walk(nodes: list[GNode], trail: tuple = ()):
    """Every node with the nodes above it."""
    for nd in nodes:
        yield trail, nd
        if nd.children:
            yield from walk(nd.children, trail + (nd,))


def node_at(nodes: list[GNode], line: int) -> list[GNode]:
    """The chain of blocks containing ``line``, outermost first."""
    chain: list[GNode] = []
    level = nodes
    while True:
        hit = next((nd for nd in level if nd.is_block and nd.line <= line <= nd.end_line), None)
        if not hit:
            return chain
        chain.append(hit)
        level = hit.children or []


def find_def(nodes: list[GNode], kind: str, name: str) -> GNode | None:
    """The `type name` / `template name` node in a file's tree."""
    for _trail, nd in walk(nodes):
        if nd.is_block and nd.head[:1] == [kind] and nd.name == name:
            return nd
    return None
