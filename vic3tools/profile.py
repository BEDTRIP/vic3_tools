"""The game's script profiler read from screenshots of its window (the ``mods/profiler_view`` layout: type, callee,
file:line, inclusive and exclusive seconds, calls), through Windows OCR — a table instead of pictures.

A shot shows the current entry, its callees (the root's: the top entries by inclusive time) and its callers (the
"edge" view's: the leaves by their own time). OCR slips are mended: a file name is snapped to a file of the mod set
(OCR drops underscores: ``ld cb rate values.txt``), the type to the profiler's kinds (``truer`` → ``trigger``), a row
whose file column was not read takes the ``@file:line`` of its callee; a row without three numbers is dropped and
counted.
"""

from __future__ import annotations

import csv
import difflib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vic3tools import ocr

KINDS = ("trigger", "effect", "script_value", "on_actions", "on_action", "event", "scripted_gui", "gui", "ai",
         "modifier", "none")
NUMBER = re.compile(r"^-?\d+([.,]\d+)?$")
FILE_LINE = re.compile(r"([\w .\-]+?\.(?:txt|gui|yml)):(\d+)")
CAPTURE = re.compile(r"capture\s+([\d.,]+)\s*s.*?frames\s+(\d+).*?ticks\s+(\d+)", re.I)


@dataclass
class Entry:
    section: str  # "callees" or "callers"
    kind: str
    name: str
    file: str
    line: int
    incl: float
    excl: float
    calls: int

    @property
    def key(self) -> str:
        return f"{self.kind} {self.file}:{self.line}" if self.file else f"{self.kind} {self.name}"


@dataclass
class Shot:
    path: Path
    capture: float = 0  # seconds of the capture
    ticks: int = 0
    frames: int = 0
    current: str = ""
    entries: list[Entry] = field(default_factory=list)
    dropped: int = 0  # rows of the table that did not read as a row


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _snap(word: str, choices: list[str], cutoff: float) -> str:
    if not choices or word in choices:
        return word
    hit = difflib.get_close_matches(word, choices, n=1, cutoff=cutoff)
    return hit[0] if hit else word


def parse(path: Path, words: list[ocr.Word], files: list[str] | None = None) -> Shot:
    """One shot of the profiler window; ``files``: base names of the set's files, to snap file names to."""
    sh = Shot(Path(path))
    rows = ocr.rows(words)
    head = next((r for r in rows if {"callee", "calls"} <= {w.t.lower().strip(",") for w in r.words}), None)
    for r in rows:
        m = CAPTURE.search(r.text)
        if m:
            sh.capture, sh.frames, sh.ticks = _num(m[1]), int(m[2]), int(m[3])
        if r.text.startswith("CURRENT"):
            sh.current = re.sub(r"\s[I|l]\s", " | ", r.text.split(":", 1)[1].strip())  # OCR reads | as I
    if head is None:
        return sh
    hw = {w.t.lower().strip(","): w for w in head.words}
    x_name = hw["callee"].x - 8
    x_file = hw["file:line"].x - 8 if "file:line" in hw else None
    x_right = hw["calls"].x + hw["calls"].w + 40
    section = "callees"
    for r in rows:
        if r.y <= head.y:
            continue
        if r.text.lower().startswith("callers"):
            section = "callers"
            continue
        ws = [w for w in r.words if w.x < x_right]
        nums = [i for i, w in enumerate(ws) if NUMBER.match(w.t)]
        if len(nums) < 3 or nums[-3] == 0:
            # a table row that did not read (covered, cut): it has text in the callee column; screen noise has not
            if any(x_name <= w.x < (x_file or x_right) for w in ws):
                sh.dropped += 1
            continue
        i_incl, i_excl, i_calls = nums[-3:]
        if ws[i_incl].x < (x_file or x_name):
            sh.dropped += 1
            continue
        lead = ws[:i_incl]
        kind = " ".join(w.t for w in lead if w.x < x_name)
        name = " ".join(w.t for w in lead if x_name <= w.x and (x_file is None or w.x < x_file))
        name = re.sub(r"\s*@\s*", "@", name)
        fcol = "_".join(w.t for w in lead if x_file is not None and w.x >= x_file)
        m = FILE_LINE.search(fcol) or FILE_LINE.search(name.replace(" ", "_"))
        fname, line = (m[1].strip(" _"), int(m[2])) if m else ("", 0)
        fname = re.sub(r"\s*_\s*", "_", fname).replace(" ", "_")  # OCR splits a name at its underscores
        if fname and files:
            fname = _snap(fname.replace(" ", "_"), files, 0.75)
        kind = _snap(kind.strip(), list(KINDS), 0.6) if kind.strip() else ""
        if kind == "none":
            continue
        try:
            calls = int(ws[i_calls].t.replace(",", "").replace(".", ""))
            sh.entries.append(Entry(section, kind, name, fname, line, _num(ws[i_incl].t), _num(ws[i_excl].t),
                                    calls))
        except ValueError:
            sh.dropped += 1
    return sh


def read(paths: list[Path], files: list[str] | None = None) -> list[Shot]:
    got = ocr.read(paths)
    return [parse(p, got.get(Path(p), []), files) for p in paths]


def by_file(entries: list[Entry]) -> list[tuple[str, float, int]]:
    """Own time summed by file, most first: (file, seconds, rows)."""
    acc: dict[str, list] = {}
    for e in entries:
        a = acc.setdefault(e.file or "?", [0.0, 0])
        a[0] += e.excl
        a[1] += 1
    return sorted(((f, s, n) for f, (s, n) in acc.items()), key=lambda x: -x[1])


def per_tick(e: Entry, sh: Shot) -> float:
    """Own milliseconds per game tick: comparable between captures of different length."""
    return e.excl * 1000 / sh.ticks if sh.ticks else e.excl * 1000


@dataclass
class Change:
    key: str
    a: float | None  # own ms per tick in the first run; None: not among the rows its shots show
    b: float | None
    floor_a: float = 0  # the smallest value the first run's shots show: a missing entry is below it
    floor_b: float = 0

    @property
    def delta(self) -> float:
        """The change, a missing side counted at its floor (so at most this big)."""
        return (self.b if self.b is not None else self.floor_b) - (self.a if self.a is not None else self.floor_a)


def compare(a: list[Shot], b: list[Shot]) -> list[Change]:
    """Every entry of either run with its own ms per tick in each, the biggest change first; an entry a run's shots
    do not show (below their last row) is None there, not zero."""
    def table(shots):
        out: dict[str, float] = {}
        for sh in shots:
            for e in sh.entries:
                out[e.key] = max(out.get(e.key, 0.0), per_tick(e, sh))
        return out, (min(out.values()) if out else 0.0)

    (ta, fa), (tb, fb) = table(a), table(b)
    rows = [Change(k, ta.get(k), tb.get(k), fa, fb) for k in set(ta) | set(tb)]
    return sorted(rows, key=lambda c: -abs(c.delta))


def write_csv(shots: list[Shot], out: Path) -> None:
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["shot", "capture_s", "ticks", "section", "kind", "name", "file", "line", "incl_s", "excl_s",
                    "calls", "excl_ms_per_tick"])
        for sh in shots:
            for e in sh.entries:
                d = asdict(e)
                w.writerow([sh.path.name, sh.capture, sh.ticks, d["section"], d["kind"], d["name"], d["file"],
                            d["line"], d["incl"], d["excl"], d["calls"], round(per_tick(e, sh), 4)])
