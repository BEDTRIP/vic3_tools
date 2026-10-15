import struct

import pytest
from conftest import write

from vic3tools import cli
from vic3tools.core import vfs
from vic3tools.gui import edit, fit, fonts, resolve, tree
from vic3tools.index import query

TYPES = """\
types T {
\ttype base_header = widget {
\t\tsize = { 100 40 }
\t\tblock "box" {
\t\t\ttextbox = {
\t\t\t\tusing = elide_min
\t\t\t\tblock "text" {
\t\t\t\t\traw_text = "DEFAULT"
\t\t\t\t}
\t\t\t\tblock "text_size" {
\t\t\t\t\tusing = big
\t\t\t\t}
\t\t\t}
\t\t}
\t}
\ttype my_header = base_header {
\t\tblockoverride "text_size" {
\t\t\tfontsize = 12
\t\t}
\t}
\ttype textbox = textbox {
\t\tusing = regular
\t}
}
template big {
\tusing = bigger
}
template bigger {
\tfontsize = 20
}
template elide_min {
\telide = right
\tfontsize_min = 14
}
template regular {
\tfont = "Serif"
\tfontsize = 17
}
"""

PANEL = """\
@w = 300
window = {
\tsize = { @w 200 }
\tmy_header = {
\t\tblockoverride "text" {
\t\t\ttext = "MY_TITLE"
\t\t}
\t\tblockoverride "text_size" {
\t\t\tfontsize = 30
\t\t}
\t}
\ttextbox = {
\t\ttext = "MY_LABEL"
\t\tmultiline = yes
\t\tmaximumsize = { 100 -1 }
\t}
}
"""


@pytest.fixture
def gset(tmp_path, home):
    van, m1 = tmp_path / "van" / "game", tmp_path / "m1"
    write(van.parent / "launcher" / "launcher-settings.json", '{"rawVersion": "1.13.11"}')
    write(van / "gui/shared/types.gui", TYPES)
    write(van / "gui/panel.gui", PANEL)
    write(van / "localization/english/a_l_english.yml", 'l_english:\n MY_LABEL: "Bond $X$ index"\n X: "market"\n')
    write(m1 / "gui/extra.gui", "template unused { a = 1 }\n")
    (van / "gfx/interface/icons").mkdir(parents=True)
    with open(van / "gfx/interface/icons/coin.dds", "wb") as fh:
        fh.write(b"DDS " + struct.pack("<II", 124, 0) + struct.pack("<II", 32, 64) + b"\0" * 100)
    (home / "vic3tools.toml").write_text(f"[roots]\ngame = '{van.parent.as_posix()}'\n", encoding="utf-8")
    si = query.SetIndex.open(vfs.ModSet.from_dirs([m1]))
    yield si
    si.close()


def _props(r, key):
    return [(p.value, bool(p.lost_to)) for _t, p in resolve.walk(r) if not p.is_widget and p.key == key]


def test_resolve_types_blocks_templates(gset):
    res = resolve.Resolver(gset)
    nodes = tree.parse_file(gset.ms.mods[0].path / "gui/panel.gui")
    w, _up = resolve.widget_at(nodes, 5)  # inside my_header's blockoverride
    assert w.key == "my_header"
    r = res.expand(w)
    assert r.types == ["my_header", "base_header", "widget"]
    # the type's own override (12) beats the instance's (30), as in the game; the inner type textbox's 17 loses
    assert _props(r, "fontsize") == [("17", True), ("12", False)]
    assert _props(r, "text") == [('"MY_TITLE"', False)]
    assert _props(r, "raw_text") == []
    assert _props(r, "elide") == [("right", False)]
    box = next(p for _t, p in resolve.walk(r) if p.key == "fontsize" and not p.lost_to)
    assert box.via[-1].startswith('blockoverride "text_size" (types.gui:17)')
    # a template through a template
    t = res.expand(res.find("type", "base_header"))
    assert _props(t, "fontsize") == [("17", True), ("20", False)]
    assert [s.split(" (")[0] for s in next(p for _t, p in resolve.walk(t) if p.key == "fontsize"
                                          and not p.lost_to).via][-2:] == ["using big", "using bigger"]
    assert resolve.blocks_offered(res, res.find("type", "my_header")) == ["box", "text", "text_size"]
    assert res.const(w.file, "@w").scalar() == "300"


def test_cli_resolve_and_reference(gset, capsys):
    van, m1 = gset.ms.mods[0].path, str(gset.ms.mods[1].path)
    assert cli.main(["--lang", "en", "gui", "resolve", "gui/panel.gui:4", "--prop", "fontsize", "--mods", m1]) == 0
    out = capsys.readouterr().out
    assert "my_header › textbox" in out and "fontsize = 12" in out and "overridden by" in out
    assert cli.main(["--lang", "en", "gui", "types", "header", "--mods", m1]) == 0
    out = capsys.readouterr().out
    assert "my_header = base_header" in out and "blocks: box, text, text_size" in out
    assert cli.main(["--lang", "en", "gui", "textures", "coin", "--mods", m1]) == 0
    assert "gfx/interface/icons/coin.dds  64×32  vanilla" in capsys.readouterr().out
    assert (van / "gui/panel.gui").is_file()


def test_set_replace_and_insert(tmp_path):
    p = tmp_path / "a.gui"
    p.write_bytes(b"\xef\xbb\xbfwindow = {\r\n\ttextbox = {\r\n\t\tsize = { 100 40 }\r\n\t\tchild = { a = 1 }\r\n"
                  b"\t}\r\n\tbox = { x = 1 }\r\n}\r\n")
    nodes = tree.parse_file(p)
    w, _ = resolve.widget_at(nodes, 3)
    ch = edit.apply(p, w, [("size", "{ 130 40 }"), ("a", "2"), ("multiline", "yes")], dry=True)
    assert [(c.line, c.was, c.becomes) for c in ch] == [(3, "size = { 100 40 }", "size = { 130 40 }"),
                                                         (5, None, "a = 2"), (5, None, "multiline = yes")]
    edit.apply(p, w, [("size", "{ 130 40 }"), ("multiline", "yes")])
    assert p.read_bytes() == (b"\xef\xbb\xbfwindow = {\r\n\ttextbox = {\r\n\t\tsize = { 130 40 }\r\n"
                              b"\t\tchild = { a = 1 }\r\n\t\tmultiline = yes\r\n\t}\r\n\tbox = { x = 1 }\r\n}\r\n")
    one = tree.parse_file(p)
    box = edit.find(one, "box")
    assert [b.key for b in box] == ["textbox", "box"]
    edit.apply(p, box[1], [("y", "2")])
    assert b"\tbox = { x = 1 y = 2 }\r\n" in p.read_bytes()


def _face(widths: dict[str, int]) -> fonts.Face:
    return fonts.Face(None, 1000, {ord(c): w for c, w in widths.items()})


def test_fit_verdicts():
    face = _face({c: 500 for c in "abcdefghijklmnopqrstuvwxyz 0"})  # every glyph half an em
    w = resolve.RNode("textbox", tree.parse_text("textbox = { }")[0], children=[])

    def b(**kw):
        return fit.Box(kw.get("font", "F"), kw.get("size", 10), kw.get("size_min"), kw.get("elide", False),
                       kw.get("multiline", False), kw.get("avail"), "")

    assert fit.measure(b(avail=60), "english", "abcdefghij", [face]).verdict == "fits"  # 10 × 5 = 50
    assert fit.measure(b(avail=40, multiline=True), "english", "abcd efgh", [face]).lines == 2
    r = fit.measure(b(avail=40, size_min=7), "english", "abcdefghij", [face])
    assert (r.verdict, r.size) == ("shrinks", 8)
    assert fit.measure(b(avail=20, size_min=7, elide=True), "english", "abcdefghij", [face]).verdict == "elided"
    assert fit.measure(b(), "english", "x", [face]).verdict == "grows"
    assert fit.plain("A [Get.X] $Y$ #bold b#! @icon!c\\nd") == "A 00000000 00000000 b c\nd"
    assert fit.box(w).font == fit.DEFAULT_FONT


def _ttf(adv: dict[str, int]) -> bytes:
    """A minimal sfnt: head, hhea, hmtx, cmap (format 4) — enough for the reader."""
    chars = sorted(adv)
    n = len(chars) + 1  # glyph 0 is .notdef
    head = bytearray(54)
    struct.pack_into(">H", head, 18, 1000)
    hhea = bytearray(36)
    struct.pack_into(">H", hhea, 34, n)
    hmtx = struct.pack(">HH", 0, 0) + b"".join(struct.pack(">HH", adv[c], 0) for c in chars)
    segs = [(ord(c), ord(c), i + 1 - ord(c)) for i, c in enumerate(chars)] + [(0xFFFF, 0xFFFF, 1)]
    sc = len(segs)
    sub = struct.pack(">HHHHHHH", 4, 0, 0, sc * 2, 0, 0, 0)
    sub += b"".join(struct.pack(">H", e) for e, _s, _d in segs) + b"\0\0"
    sub += b"".join(struct.pack(">H", s) for _e, s, _d in segs)
    sub += b"".join(struct.pack(">h", ((d + 0x8000) & 0xFFFF) - 0x8000) for _e, _s, d in segs)
    sub += b"\0\0" * sc
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + sub
    tables = {"cmap": cmap, "head": bytes(head), "hhea": bytes(hhea), "hmtx": hmtx}
    out = bytearray(struct.pack(">IHHHH", 0x10000, len(tables), 0, 0, 0))
    off = 12 + 16 * len(tables)
    body = b""
    for tag, data in tables.items():
        out += struct.pack(">4sIII", tag.encode(), 0, off + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return bytes(out + body)


def test_font_files_and_fallback(tmp_path):
    game = tmp_path / "game"
    (game / "fonts").mkdir(parents=True)
    (game / "fonts" / "a.ttf").write_bytes(_ttf({"a": 600, "b": 400}))
    (game / "fonts" / "z.ttf").write_bytes(_ttf({"я": 700}))
    write(game / "fonts/fonts.font",
          'fontfiles = {\n\tname = "Serif-Regular"\n\tgroup = {\n\t\tlanguages = { "l_english" "l_russian" }\n'
          '\t\tfiles = { "fonts/a.ttf" "fonts/z.ttf" }\n\t}\n}\n'
          'font = {\n\tname = "Serif"\n\tfontstyle = {\n\t\tstyle = regular\n\t\tfontfiles = "Serif-Regular"\n\t}\n}\n')
    fs = fonts.Fonts.load(game)
    faces = fs.faces("Serif", "russian")
    assert [f.path.name for f in faces] == ["a.ttf", "z.ttf"]
    assert faces[0].advances == {ord("a"): 600, ord("b"): 400}
    assert fonts.width("abя", faces, 10) == pytest.approx(6 + 4 + 7)
    assert fonts.width("?", faces, 10) == 5  # missing everywhere: half an em
