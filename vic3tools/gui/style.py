"""The look of vanilla's interface, counted from its ``.gui`` files: what a mod's window should reuse to fit in.

Counts over every ``gui/**/*.gui`` of one folder (vanilla by default): the templates pulled in with ``using``, the
GUI types instantiated (headers, buttons, backgrounds…), literal fonts, font sizes and text formats, the spacing and
margins of containers, the textures in use; and the text formats of ``textformatting.gui`` (``#title`` etc.) with
their colours. Each line keeps one example ``file:line``, so a reader can open a real use.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.gui import tree

CONTAINERS = {"flowcontainer", "hbox", "vbox", "dynamicgridbox", "fixedgridbox", "overlappingitembox"}


@dataclass
class Style:
    root: Path
    files: int = 0
    using: Counter = field(default_factory=Counter)
    types: Counter = field(default_factory=Counter)
    fonts: Counter = field(default_factory=Counter)
    sizes: Counter = field(default_factory=Counter)
    formats: Counter = field(default_factory=Counter)
    spacing: Counter = field(default_factory=Counter)
    margins: Counter = field(default_factory=Counter)
    textures: Counter = field(default_factory=Counter)
    text_formats: dict[str, str] = field(default_factory=dict)  # #name → its format (colour; shadow…)
    defined_types: dict[str, str] = field(default_factory=dict)  # type name → base
    example: dict[tuple[str, str], str] = field(default_factory=dict)  # (kind, value) → file:line

    def note(self, kind: str, counter: Counter, value: str, where: str) -> None:
        counter[value] += 1
        self.example.setdefault((kind, value), where)


def collect(root: Path) -> Style:
    """Count the use of everything in ``root/gui`` (a mod or vanilla folder)."""
    st = Style(root)
    files = sorted((root / "gui").rglob("*.gui"))
    trees = []
    for f in files:
        try:
            trees.append((f, tree.parse_file(f)))
        except (OSError, ValueError):
            continue
    st.files = len(trees)
    for _f, nodes in trees:
        for _trail, nd in tree.walk(nodes):
            if nd.head[:1] == ["type"] and nd.is_block:
                st.defined_types.setdefault(nd.name, nd.value or "")
    for f, nodes in trees:
        rel = f.relative_to(root).as_posix()
        for _trail, nd in tree.walk(nodes):
            where = f"{rel}:{nd.line}"
            if nd.key == "using" and nd.op and not nd.is_block:
                st.note("using", st.using, nd.value or "", where)
            elif (nd.is_block and nd.op and nd.value is None and nd.key in st.defined_types
                  and st.defined_types[nd.key] != nd.key):  # not `type textbox = textbox`: a native widget
                st.note("type", st.types, nd.key, where)
            elif nd.key == "font" and nd.op:
                st.note("font", st.fonts, nd.scalar().strip('"'), where)
            elif nd.key == "fontsize" and nd.op:
                st.note("size", st.sizes, nd.scalar(), where)
            elif nd.key == "default_format" and nd.op:
                st.note("format", st.formats, nd.scalar().strip('"'), where)
            elif nd.key == "texture" and nd.op:
                st.note("texture", st.textures, nd.scalar().strip('"'), where)
            if nd.is_block and nd.key in CONTAINERS:
                for c in nd.children or []:
                    if c.key == "spacing" and c.op:
                        st.note("spacing", st.spacing, c.scalar(), f"{rel}:{c.line}")
                    elif c.key == "margin" and c.op:
                        st.note("margin", st.margins, c.scalar(), f"{rel}:{c.line}")
        if f.name == "textformatting.gui":
            for _trail, nd in tree.walk(nodes):
                if nd.key == "format" and nd.is_block:
                    name = next((c.scalar().strip('"') for c in nd.props("name")), "")
                    fmt = next((c.scalar().strip('"') for c in nd.props("format")), "")
                    if name:
                        st.text_formats[name] = fmt
    return st


def _table(st: Style, kind: str, counter: Counter, n: int, extra=None) -> list[str]:
    out = []
    for value, count in counter.most_common(n):
        more = f" — {extra(value)}" if extra else ""
        out.append(f"| `{value}` | {count} | {st.example.get((kind, value), '')}{more} |")
    return out


def markdown(st: Style, top: int = 25) -> str:
    """The counts as a Markdown file: the raw material of a project's GUI style file."""
    base = lambda name: f"type = {st.defined_types.get(name) or '?'}"  # noqa: E731
    lines = [f"# Vanilla GUI style — counted from {st.files} files of {st.root}", "",
             "Made by `v3 gui style`. Counts of use; one example `file:line` each. Prefer the most used for a "
             "role — players read them as \"the game's own\".", ""]

    def section(title: str, kind: str, counter: Counter, note: str = "", extra=None, n: int = top) -> None:
        lines.extend([f"## {title}", ""] + ([note, ""] if note else []))
        lines.extend(["| value | uses | example |", "| --- | --- | --- |"])
        lines.extend(_table(st, kind, counter, n, extra))
        lines.append("")

    section("Types instantiated", "type", st.types, "Headers, buttons, backgrounds, list entries: reuse the type "
            "instead of rebuilding it (`v3 gui types NAME` — its blocks to override).", base)
    section("Templates (`using`)", "using", st.using, "Fonts, sizes, backgrounds, sounds and tooltips come as "
            "templates more often than as literal properties.")
    section("Text formats (`default_format`)", "format", st.formats)
    lines.extend(["### What the formats are (`gui/textformatting.gui`)", "", "| format | is |", "| --- | --- |"])
    for name, fmt in sorted(st.text_formats.items()):
        lines.append(f"| `#{name}` | `{fmt}` |")
    lines.append("")
    section("Font sizes (literal `fontsize`)", "size", st.sizes, "Sizes set by templates (`fontsize_large` = 20…) "
            "are counted under Templates.", n=15)
    section("Fonts (literal `font`)", "font", st.fonts, "A textbox without `font` gets EBGaramond 17 from vanilla's "
            "`type textbox = textbox { using = regular_font }`.", n=10)
    section("Container spacing", "spacing", st.spacing, n=12)
    section("Container margins", "margin", st.margins, n=12)
    section("Textures", "texture", st.textures, n=top)
    return "\n".join(lines) + "\n"

