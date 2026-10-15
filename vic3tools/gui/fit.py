"""Does a textbox's text fit its width: per language, after the widget is resolved.

Placeholders ``[…]`` and ``$…$`` count as a fixed sample (``SAMPLE``), formatting ``#x … #!`` and icons ``@x!`` are
removed, kerning is ignored. Rules taken for the engine: a width is ``max_width``, else ``maximumsize``, else a fixed
``size`` (not with ``autoresize``); ``margin`` is inside it; a too long line shrinks by whole pixels down to
``fontsize_min``, then is cut (``elide``) or overflows; ``multiline`` wraps by words.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from vic3tools.gui import fonts
from vic3tools.gui.resolve import RNode

SAMPLE = "00000000"
DEFAULT_FONT = "standard_font"  # assumed for a textbox with no font at all (vanilla's `type textbox` gives one)
DEFAULT_SIZE = 15


@dataclass
class Box:
    font: str
    size: float
    size_min: float | None
    elide: bool
    multiline: bool
    avail: float | None  # pixels for the text; None: grows with it, no limit
    why: str  # where the width comes from
    relative: bool = False  # the width is in % of the parent
    notes: tuple[str, ...] = ()


@dataclass
class Row:
    lang: str
    text: str
    width: float
    verdict: str  # fits / wraps / shrinks / elided / overflows / grows
    lines: int = 1
    size: float = 0


def prop(w: RNode, key: str) -> RNode | None:
    """The value a widget ends with for ``key`` (the last one that is not overridden)."""
    ps = [p for p in w.props(key) if p.lost_to is None]
    return ps[-1] if ps else None


def _num(v: str | None) -> float | None:
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _pair(v: str | None) -> tuple[str, str] | None:
    if not v:
        return None
    parts = v.strip("{} ").split()
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def box(w: RNode, width: float | None = None) -> Box:
    """The font and the room for text of a resolved textbox; ``width`` overrides the widget's own."""
    notes = []
    font_p = prop(w, "font")
    font = font_p.value.strip('"') if font_p else DEFAULT_FONT
    if not font_p:
        notes.append(f"no font set: {DEFAULT_FONT} assumed")
    size_p = prop(w, "fontsize")
    size = _num(size_p.value) if size_p else None
    if size is None:
        size = DEFAULT_SIZE
        notes.append(f"no fontsize set: {DEFAULT_SIZE} assumed")
    size_min = _num(prop(w, "fontsize_min").value) if prop(w, "fontsize_min") else None
    elide = bool(prop(w, "elide")) and prop(w, "elide").value not in ("no", "none")
    multiline = bool(prop(w, "multiline")) and prop(w, "multiline").value == "yes"
    autoresize = bool(prop(w, "autoresize")) and prop(w, "autoresize").value == "yes"
    margin = 0.0
    m = _pair(prop(w, "margin").value) if prop(w, "margin") else None
    if m and _num(m[0]) is not None:
        margin += 2 * _num(m[0])
    for k in ("margin_left", "margin_right"):
        if prop(w, k) and _num(prop(w, k).value) is not None:
            margin += _num(prop(w, k).value)
    avail, why, relative = None, "autoresize, no maximum: grows with the text", False
    if width is not None:
        avail, why = width, "--width"
    else:
        for key in ("max_width", "maximumsize", "size"):
            p = prop(w, key)
            if not p:
                continue
            v = p.value if key == "max_width" else (_pair(p.value) or ("",))[0]
            if key == "size" and autoresize and not v.endswith("%"):  # the text sets the size; a % still bounds it
                continue
            if v.endswith("%"):
                relative, why = True, f"{key} {v} of the parent"
                break
            n = _num(v)
            if n is not None and n > 0:
                avail, why = n, f"{key} ({p.node.file.name if p.node.file else ''}:{p.node.line})"
                break
        if avail is None and not relative and not autoresize:
            why = "no width set"
    if avail is not None:
        avail = max(avail - margin, 0)
    return Box(font, size, size_min, elide, multiline, avail, why, relative, tuple(notes))


def plain(text: str) -> str:
    """Loc text as measured: placeholders → ``SAMPLE``, formatting and icons removed, ``\\n`` → a line break."""
    text = re.sub(r"\[[^\]]*\]|\$[^$]*\$", SAMPLE, text)
    text = re.sub(r"#[A-Za-z_;]+ ?|#!", "", text)
    text = re.sub(r"@\w+!", "", text)
    return text.replace("\\n", "\n")


def measure(b: Box, lang: str, text: str, faces: list[fonts.Face]) -> Row:
    shown = plain(text)
    lines = shown.split("\n")
    w = max(fonts.width(ln, faces, b.size) for ln in lines)
    if b.avail is None:
        return Row(lang, shown, w, "grows" if not b.relative else "relative", len(lines), b.size)
    if b.multiline:
        wrapped = fonts.wrap(shown, faces, b.size, b.avail)
        return Row(lang, shown, w, "wraps" if len(wrapped) > len(lines) else "fits", len(wrapped), b.size)
    if w <= b.avail:
        return Row(lang, shown, w, "fits", len(lines), b.size)
    if b.size_min:
        s = math.floor(b.size * b.avail / w)
        if s >= b.size_min:
            return Row(lang, shown, w, "shrinks", len(lines), s)
        return Row(lang, shown, w, "elided" if b.elide else "overflows", len(lines), b.size_min)
    return Row(lang, shown, w, "elided" if b.elide else "overflows", len(lines), b.size)
