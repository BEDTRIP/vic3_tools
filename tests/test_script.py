import pytest

from vic3tools.core import script as s

SRC = """\
# about a
# more
a = { x = 1 y = { z = 2 } }
INJECT:b = { color = hsv { 0.1 0.2 0.3 } t = "a { b" } # } in comment
c ?= yes
TRY_INJECT::d = { k = 1 }
"""


def test_parse_boundaries_and_lead():
    entries, problems = s.parse(SRC)
    assert problems == []
    a, b, c, d = entries
    assert (a.key, a.directive, a.is_block) == ("a", "", True)
    assert a.text(SRC, with_lead=True).startswith("# about a")
    assert a.body(SRC).strip() == "x = 1 y = { z = 2 }"
    assert (b.key, b.directive, b.full_key) == ("b", "INJECT", "INJECT:b")
    assert b.body(SRC).count('"a { b"') == 1
    assert (c.op, c.value, c.is_block) == ("?=", "yes", False)
    assert d.full_key == "TRY_INJECT::d"


def test_children_and_lines(tmp_path):
    a = s.parse(SRC)[0][0]
    assert [e.key for e in a.children(SRC)] == ["x", "y"]
    f = tmp_path / "t.txt"
    f.write_bytes(b"\xef\xbb\xbf" + SRC.replace("\n", "\r\n").encode())
    src = s.read(f)
    assert src.bom and src.eol == "\r\n"
    text, bom, eol = src
    assert src.line(s.parse(text)[0][2].start) == 5


def test_problems():
    assert "stray" in s.parse("a = 1 }")[1][0]
    assert "unclosed" in s.parse("a = { b = 1")[1][0]


def test_generator_helpers():
    decl, body = s.entry(SRC, "b")
    assert decl.startswith("INJECT:b") and "color" in body
    assert s.entry(SRC, "d", "TRY_INJECT::")[0].startswith("TRY_INJECT::d")
    with pytest.raises(KeyError):
        s.entry(SRC, "b", "REPLACE:")
    body = s.entry(SRC, "a")[1]
    assert s.sub_names(body) == ["y"]
    assert s.sub(body, "y") == "{ z = 2 }"
    assert s.replace_sub(body, "y", "{ }").strip() == "x = 1 y = { }"
    assert s.sub_names(s.entry(SRC, "b")[1]) == []  # `color = hsv { }` is a typed value, not a sub-block


def test_norm_balance_sha():
    assert s.norm("a = { # c\n b = 1 }") == "a = { b = 1 }"
    assert s.brace_balance('a = { t = "}" # }\n') == 1
    assert s.sha("a  =\n1") == s.sha("a = 1")


def test_write_bom_rule_and_eol(tmp_path):
    f = tmp_path / "o" / "x.txt"
    s.write(f, "a = 1 # ü in a comment\n")
    assert not f.read_bytes().startswith(b"\xef\xbb\xbf")
    s.write(f, 'a = "ü"\n', eol="\r\n")
    assert f.read_bytes() == b'\xef\xbb\xbfa = "\xc3\xbc"\r\n'
