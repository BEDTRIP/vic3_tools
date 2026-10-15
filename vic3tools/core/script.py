"""Paradox script (``.txt``, ``.gui``): tokens and records with exact boundaries in the text.

A record is ``[DIRECTIVE:]key <op> value``; the value is a block ``{ … }``, a word or a string, or a typed block
(``color = hsv { … }``). Boundaries are offsets into the text: ``start`` — the key (with its directive), ``end`` — just
past the value, ``lead`` — the first of the comment lines right above the key (else ``start``); a block also has
``open`` / ``close`` — the offsets of ``{`` and ``}``. Comments and strings never confuse the brace matching.

Reading and writing keep files byte-faithful: the BOM and line ends are reported on read and restored on write, so a
copy of someone else's file stays diffable against their next version.

The helpers at the end (``entry``, ``sub``, ``sub_span``, ``sub_names``, ``replace_sub``) answer "the block called X"
over text for code generators.
"""

from __future__ import annotations

import bisect
import hashlib
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DIRECTIVES = ("REPLACE_OR_CREATE", "TRY_REPLACE", "REPLACE", "TRY_INJECT", "INJECT_OR_CREATE", "INJECT", "CREATE")
OPS = ("=", "?=", "<", ">", "<=", ">=", "!=", "==")
TYPED_BLOCKS = ("hsv", "rgb", "hsv360")
TOKEN = re.compile(r'#[^\n]*|"(?:[^"\\\n]|\\.)*"|[{}]|[<>!=?]=|[<>=]|[^\s{}<>!=?#"]+')
_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


@dataclass
class Tok:
    s: str
    pos: int

    @property
    def end(self) -> int:
        return self.pos + len(self.s)


@dataclass
class Entry:
    key: str
    directive: str  # "" when there is none
    op: str
    start: int
    end: int
    lead: int
    open: int = -1  # -1: a scalar value
    close: int = -1
    value: str = ""  # a scalar's value

    @property
    def is_block(self) -> bool:
        return self.open >= 0

    @property
    def full_key(self) -> str:
        return f"{self.directive}:{self.key}" if self.directive else self.key

    def text(self, src: str, with_lead: bool = False) -> str:
        return src[self.lead if with_lead else self.start:self.end]

    def body(self, src: str) -> str:
        return src[self.open + 1:self.close] if self.is_block else self.value

    def children(self, src: str) -> list[Entry]:
        """Records directly inside this block, offsets into ``src``."""
        return parse(src, self.open + 1, self.close)[0] if self.is_block else []


def tokens(text: str, lo: int = 0, hi: int | None = None) -> list[Tok]:
    """Tokens of ``text[lo:hi]`` without comments; positions are offsets into ``text``."""
    pattern = TOKEN.finditer(text, lo, len(text) if hi is None else hi)
    return [Tok(m.group(0), m.start()) for m in pattern if not m.group(0).startswith("#")]


def split_directive(key: str) -> tuple[str, str]:
    if ":" in key:
        d, rest = key.split(":", 1)
        if d in DIRECTIVES:
            return d, rest
    return "", key


def _lead(text: str, start: int) -> int:
    """Start of the unbroken comment lines right above the line of ``start`` (the key must begin its line)."""
    ls = text.rfind("\n", 0, start) + 1
    if text[ls:start].strip():
        return start
    lead = ls
    while lead > 0:
        pe = lead - 1
        ps = text.rfind("\n", 0, pe) + 1
        if text[ps:pe].strip().startswith("#"):
            lead = ps
        else:
            break
    return lead


def _close(toks: list[Tok], i: int) -> int:
    """Index of the token closing the ``{`` at ``toks[i]``, or ``len(toks)`` if it never closes."""
    depth = 0
    for j in range(i, len(toks)):
        s = toks[j].s
        if s == "{":
            depth += 1
        elif s == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(toks)


def parse(text: str, lo: int = 0, hi: int | None = None) -> tuple[list[Entry], list[str]]:
    """Records at the top level of ``text[lo:hi]``, and parse problems (a stray ``}``, an unclosed block…)."""
    toks = tokens(text, lo, hi)
    entries: list[Entry] = []
    problems: list[str] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.s == "}":
            problems.append(f"stray '}}' at offset {t.pos}")
            i += 1
            continue
        if t.s == "{":
            problems.append(f"block without a key at offset {t.pos}")
            i = _close(toks, i) + 1
            continue
        if i + 1 < n and toks[i + 1].s in OPS:
            d, key = split_directive(t.s)
            op = toks[i + 1].s
            if i + 2 >= n:
                problems.append(f"nothing after '{t.s} {op}' at offset {t.pos}")
                break
            v = toks[i + 2]
            typed = (i + 3 < n and toks[i + 3].s == "{" and v.s in TYPED_BLOCKS and toks[i + 3].pos - v.end <= 1)
            if v.s == "{" or typed:
                oi = i + 2 if v.s == "{" else i + 3
                j = _close(toks, oi)
                if j >= n:
                    problems.append(f"unclosed block '{t.s}' at offset {t.pos}")
                    break
                entries.append(Entry(key, d, op, t.pos, toks[j].end, _lead(text, t.pos), toks[oi].pos, toks[j].pos))
                i = j + 1
            else:
                entries.append(Entry(key, d, op, t.pos, v.end, _lead(text, t.pos), value=v.s))
                i += 3
        else:
            problems.append(f"word without a value '{t.s}' at offset {t.pos}")
            i += 1
    return entries, problems


def block_items(body: str) -> list[tuple]:
    """Items of a block body as ``(key|None, op|None, start, end, is_block, open, close)`` — offsets into ``body``.

    Bare words (list items like ``building_types = { a b }``) and blocks without a key have ``key=None``.
    """
    toks = tokens(body)
    out: list[tuple] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if i + 1 < n and toks[i + 1].s in OPS and t.s not in "{}":
            if i + 2 >= n:
                break
            v = toks[i + 2]
            if v.s == "{" or (i + 3 < n and toks[i + 3].s == "{" and v.s in TYPED_BLOCKS):
                oi = i + 2 if v.s == "{" else i + 3
                j = min(_close(toks, oi), n - 1)
                out.append((t.s, toks[i + 1].s, t.pos, toks[j].end, True, toks[oi].pos, toks[j].pos))
                i = j + 1
            else:
                out.append((t.s, toks[i + 1].s, t.pos, v.end, False, -1, -1))
                i += 3
        elif t.s == "{":
            j = min(_close(toks, i), n - 1)
            out.append((None, None, t.pos, toks[j].end, True, t.pos, toks[j].pos))
            i = j + 1
        else:
            out.append((None, None, t.pos, t.end, False, -1, -1))
            i += 1
    return out


def norm(text: str) -> str:
    """The text without comments and whitespace differences — to compare "the same thing"."""
    return " ".join(t.s for t in tokens(text))


def sha(text: str) -> str:
    """Short hash of the text with whitespace runs collapsed."""
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()[:12]


def brace_balance(text: str) -> int:
    """``{`` minus ``}``, comments and strings ignored."""
    return sum((t.s == "{") - (t.s == "}") for t in tokens(text))


# --- files ---------------------------------------------------------------------------------------------------------


@dataclass
class Source:
    """A script file as read: text with LF line ends and no BOM, and what to restore on write."""

    text: str
    bom: bool
    eol: str
    path: Path | None = None
    _lines: list[int] | None = None

    def __iter__(self):  # (text, bom, eol), so ``text, bom, eol = read(path)`` works
        return iter((self.text, self.bom, self.eol))

    def line(self, pos: int) -> int:
        """1-based line number of an offset."""
        if self._lines is None:
            self._lines = [m.end() for m in re.finditer("\n", self.text)]
        return bisect.bisect_right(self._lines, pos) + 1


def read(path: str | os.PathLike, errors: str = "replace") -> Source:
    raw = Path(path).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = (raw[3:] if bom else raw).decode("utf-8", errors=errors)
    eol = "\r\n" if b"\r\n" in raw else "\n"
    return Source(text.replace("\r\n", "\n"), bom, eol, Path(path))


def read_text(path: str | os.PathLike) -> str:
    """The text only (LF, no BOM); invalid UTF-8 is an error, not a silent replacement."""
    return read(path, errors="strict").text


def needs_bom(text: str) -> bool:
    """The game needs a BOM in a file with a non-ASCII character outside comments."""
    return any(ord(ch) > 127 for line in text.split("\n") for ch in line.split("#")[0])


def write(path: str | os.PathLike, text: str, bom: bool | None = None, eol: str = "\n") -> None:
    """Write a game file through a temporary one (a failed write never leaves it truncated).

    ``bom=None`` decides by ``needs_bom``, so pure-ASCII copies of other people's files stay byte-for-byte.
    """
    if bom is None:
        bom = needs_bom(text)
    data = text.replace("\r\n", "\n")
    if eol != "\n":
        data = data.replace("\n", eol)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data.encode("utf-8"))
    os.replace(tmp, path)


# --- "the block called X", for generators ---------------------------------------------------------------------------


def entry(text: str, key: str, prefix: str | None = None) -> tuple[str, str]:
    """``(whole declaration, body without the outer braces)`` of the first top-level block ``key``.

    ``prefix`` (``"INJECT:"``, ``"REPLACE:"``…) must match exactly when given; ``None`` accepts any or none. The
    declaration starts at the beginning of its line when only indentation precedes the key.
    """
    for e in parse(text)[0]:
        if not e.is_block:
            continue
        raw = e.full_key  # as written, so a malformed `TRY_INJECT::key` is found with prefix "TRY_INJECT::"
        if prefix is not None:
            if raw != prefix + key:
                continue
        elif raw != key and not (raw.endswith(":" + key) and re.fullmatch(r"[A-Z_:]+:", raw[: -len(key)])):
            continue
        ls = text.rfind("\n", 0, e.start) + 1
        begin = ls if not text[ls:e.start].strip() else e.start
        return text[begin:e.end], text[e.open + 1:e.close]
    raise KeyError(f"{key} not found (prefix={prefix!r})")


def depth0_iter(body: str) -> Iterator[tuple[str, int, int, int]]:
    """``(name, start, open, close)`` of each ``name = { … }`` at depth 0 of a block body.

    Only a plain ``=`` and no directive; a typed value like ``color = hsv { … }`` is not a sub-block.
    """
    for e in parse(body)[0]:
        if e.is_block and not e.directive and e.op == "=" and _IDENT.match(e.key) \
                and body[e.start + len(e.key):e.open].strip() == "=":
            yield e.key, e.start, e.open, e.close


def sub(body: str, name: str) -> str | None:
    """Text of the sub-block ``name = { … }`` at depth 0 of ``body``, braces included."""
    for nm, _a, o, c in depth0_iter(body):
        if nm == name:
            return body[o:c + 1]
    return None


def sub_span(body: str, name: str) -> tuple[int, int] | None:
    """``(start, end)`` of the whole ``name = { … }`` statement at depth 0."""
    for nm, a, _o, c in depth0_iter(body):
        if nm == name:
            return a, c + 1
    return None


def sub_names(body: str) -> list[str]:
    return [nm for nm, *_ in depth0_iter(body)]


def replace_sub(body: str, name: str, new_block: str) -> str:
    """``body`` with the block of sub-block ``name`` swapped for ``new_block`` (braces included)."""
    for nm, _a, o, c in depth0_iter(body):
        if nm == name:
            return body[:o] + new_block + body[c + 1:]
    raise KeyError(f"sub-block {name} not found")
