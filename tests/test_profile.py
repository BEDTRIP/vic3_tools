from pathlib import Path

from vic3tools import ocr, profile


def _row(y, *cells):
    """Words of one OCR'd line: (text, x) pairs."""
    return [ocr.Word(t, x, y, 8 * len(t), 14) for t, x in cells]


def _shot():
    words = []
    words += _row(95, ("root", 56), ("edge", 146), ("capture", 234), ("98.3", 298), ("s,", 342), ("frames", 357),
                  ("5000,", 416), ("ticks", 467), ("1403,", 506), ("samples", 550), ("1000", 618))
    words += _row(124, ("CURRENT:", 58), ("none", 138), ("I", 184), ("No", 194), ("child", 220))
    words += _row(152, ("callee", 214), ("file:line", 1461), ("incl,", 2018), ("s", 2052), ("excl,", 2172),
                  ("s", 2208), ("calls", 2338))
    words += _row(184, ("none", 57), ("No", 213), ("child", 238), ("<unknown>:0", 1462), ("0.000", 2020),
                  ("0.000", 2176), ("0", 2362))
    words += _row(216, ("callers:", 890))
    # OCR slips: underscores lost in the file column, "truer" for trigger, a row without its file column
    words += _row(247, ("truer", 57), ("trigger", 213), ("@", 268), ("ld_cb_rate_values.txt:135", 287),
                  ("ld", 1461), ("cb", 1490), ("rate", 1520), ("valuez.txt:135", 1560), ("0.715", 2020),
                  ("0.715", 2176), ("17067", 2328), ("65", 2513))
    words += _row(275, ("script_value", 58), ("script_value@00_default_strategy.txt:5138", 214), ("0.760", 2020),
                  ("0.760", 2176), ("12057858", 2300))
    words += _row(304, ("trigger", 57), ("garbled", 213), ("0.5", 2020))  # not a row: dropped, counted
    return words


def test_parse_mends_ocr_slips():
    sh = profile.parse(Path("e_edge.png"), _shot(), files=["ld_cb_rate_values.txt", "00_default_strategy.txt"])
    assert (sh.capture, sh.frames, sh.ticks) == (98.3, 5000, 1403)
    assert sh.current.startswith("none | No child")
    assert [(e.section, e.kind, e.file, e.line, e.excl, e.calls) for e in sh.entries] == [
        ("callers", "trigger", "ld_cb_rate_values.txt", 135, 0.715, 17067),
        ("callers", "script_value", "00_default_strategy.txt", 5138, 0.76, 12057858)]
    assert sh.dropped == 1
    assert round(profile.per_tick(sh.entries[0], sh), 3) == 0.51


def test_by_file_and_compare():
    a = profile.parse(Path("a.png"), _shot(), files=["ld_cb_rate_values.txt", "00_default_strategy.txt"])
    b = profile.Shot(Path("b.png"), ticks=1403, entries=[
        profile.Entry("callers", "trigger", "", "ld_cb_rate_values.txt", 135, 0.3, 0.3, 1),
        profile.Entry("callers", "effect", "", "x.txt", 1, 0.2, 0.2, 1)])
    assert profile.by_file(a.entries)[0][0] == "00_default_strategy.txt"
    ch = {c.key: c for c in profile.compare([a], [b])}
    assert ch["trigger ld_cb_rate_values.txt:135"].b is not None
    gone = ch["script_value 00_default_strategy.txt:5138"]
    assert gone.b is None and gone.delta == b.entries[1].excl * 1000 / 1403 - profile.per_tick(a.entries[1], a)


def test_rows_group_by_middle():
    ws = [ocr.Word("b", 50, 100, 10, 14), ocr.Word("a", 10, 102, 10, 14), ocr.Word("c", 10, 130, 10, 14)]
    assert [r.text for r in ocr.rows(ws)] == ["a b", "c"]
