"""The game's logs read as records: families, the places in a mod they point at, two runs compared, run speed.

A record is a line ``[HH:MM:SS][file.cpp:N]: message`` plus the lines after it without a stamp. A folder is the
game's ``logs/`` or a run's folder (the run scripts also keep ``dbgparts/`` and ``errparts/`` — copies of rotated
``debug.log`` / ``error.log`` taken during the run; the same file is read once). The **family** of a message is its
text with numbers → ``N`` and quoted names → ``'…'`` (names kept for "Unknown …", where the name is the point).

Engine facts used:

- ``debug.log`` / ``error.log`` rotate by 512 KB (``error.1.log`` … ``error.5.log``): read the parts too;
- **line numbers of scripted effects and values in ``error.log`` count the definition's lines without blank and
  comment lines, from its top-level key** — ``real_lines`` maps them back to the file's lines.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

HEAD = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\]\[([^\]]*)\]:\s?(.*)")
NUM = re.compile(r"\d+(\.\d+)?")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
UNUSED = re.compile(r"(\w+(?: target)?) '([^']+)' is (set|used) but is never (?:used|set)")
LOC = re.compile(r"((?:common|gui|events|localization)/[^'\"\n:]+?\.(?:txt|gui|yml))"
                 r"(?:['\"]?\s*(?:near line:|:)\s*(\d+))?")
MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8,
          "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
          "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6, "July": 7, "August": 8,
          "September": 9, "October": 10, "November": 11, "December": 12}
GAME_DATE = re.compile(r"(?:^|[|:]\s?)(" + "|".join(MONTHS) + r") (\d{1,2}), (\d{4})")
PARTS = {"debug": "dbgparts", "error": "errparts"}


def files(folder: Path, kind: str) -> list[Path]:
    """``<kind>*.log`` of a folder and the run's parts, each distinct file once, oldest first."""
    folder = Path(folder)
    parts = folder / PARTS.get(kind, "-")
    cand = sorted(parts.glob("*")) if parts.is_dir() else []
    # error.5.log … error.1.log, then error.log: the highest number is the oldest
    numbered = [p for p in folder.glob(f"{kind}.*.log") if p.name.split(".")[-2].isdigit()]
    cand += sorted(numbered, key=lambda p: -int(p.name.split(".")[-2]))
    if (folder / f"{kind}.log").is_file():
        cand.append(folder / f"{kind}.log")
    out, seen = [], set()
    for p in cand:
        h = hashlib.sha1(p.read_bytes()).hexdigest()
        if h not in seen:
            seen.add(h)
            out.append(p)
    return out


@dataclass
class Record:
    time: int  # seconds since midnight
    source: str  # file.cpp:N
    text: str  # the message, continuation lines joined with \n


def records(folder: Path, kind: str) -> Iterator[Record]:
    for p in files(folder, kind):
        cur = None
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                m = HEAD.match(line)
                if m:
                    if cur is not None:
                        yield cur
                    cur = Record(int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), m[4], m[5])
                elif cur is not None:
                    cur.text += "\n" + line
        if cur is not None:
            yield cur


def family(msg: str) -> str:
    first = msg.split("\n", 1)[0]
    s = first if "nknown" in first else QUOTED.sub("'…'", first)
    return NUM.sub("N", s)[:220]


@dataclass
class Summary:
    kind: str
    files: int = 0
    records: int = 0
    skipped: int = 0  # records matching --skip (a mod's own log lines)
    families: Counter = field(default_factory=Counter)
    sources: Counter = field(default_factory=Counter)
    example: dict[str, str] = field(default_factory=dict)
    unused: Counter = field(default_factory=Counter)  # (what, name, set|used) → count


def summarize(folder: Path, kind: str, skip: str | None = None) -> Summary:
    sk = re.compile(skip) if skip else None
    s = Summary(kind, len(files(folder, kind)))
    for r in records(folder, kind):
        if sk and sk.search(r.text):
            s.skipped += 1
            continue
        s.records += 1
        k = family(r.text)
        s.families[k] += 1
        s.sources[r.source.split(":")[0]] += 1
        s.example.setdefault(k, r.text.split("\n", 1)[0][:300])
        u = UNUSED.match(r.text)
        if u:
            s.unused[(u[1], u[2], u[3])] += 1
    return s


@dataclass
class Diff:
    kind: str
    a: Summary
    b: Summary
    new: list[tuple[str, int]]
    grown: list[tuple[str, int, int]]
    gone: list[tuple[str, int]]


def compare(base: Path, run: Path, kind: str, skip: str | None = None) -> Diff:
    a, b = summarize(base, kind, skip), summarize(run, kind, skip)
    new = [(k, n) for k, n in b.families.most_common() if k not in a.families]
    grown = [(k, a.families[k], n) for k, n in b.families.most_common()
             if k in a.families and n > 2 * a.families[k] and n - a.families[k] >= 10]
    gone = [(k, n) for k, n in a.families.most_common() if k not in b.families]
    return Diff(kind, a, b, new, grown, gone)


# --- places in a mod --------------------------------------------------------------------------------------------------


def sites(folder: Path, kind: str = "error", with_unlocated: bool = False) -> tuple[int, Counter, Counter]:
    """(records, (place, message) → count, file → count): records pointing at a mod's file and line."""
    total = 0
    places: Counter = Counter()
    per_file: Counter = Counter()
    for r in records(folder, kind):
        total += 1
        locs = [(m[1], m[2] or "?") for m in LOC.finditer(r.text)]
        msg = NUM.sub("N", LOC.sub("<loc>", r.text.split("\n", 1)[0]))[:240]
        if locs:
            f, n = locs[0]
            places[(f"{f}:{n}", msg)] += 1
            per_file[f] += 1
        elif with_unlocated:
            places[("-", msg)] += 1
    return total, places, per_file


_TOP = re.compile(r"[A-Za-z_][\w:.\-]*\s*=")
_BLANK = re.compile(r"^[ \t]*(#.*)?$")


def real_lines(path: Path, n: int) -> list[int]:
    """The file's lines behind line ``n`` of an ``error.log`` place in a scripted effect / value: the engine counts
    from the definition's top-level key and skips blank and comment lines."""
    if not path.is_file():
        return []
    rep: dict[int, list[int]] = {}
    skipped = 0
    for i, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").split("\n"), 1):
        if _TOP.match(line):
            skipped = 0
        if _BLANK.match(line):
            skipped += 1
        else:
            rep.setdefault(i - skipped, []).append(i)
    return rep.get(n, [])


# --- speed ------------------------------------------------------------------------------------------------------------


def speed_points(folder: Path) -> list[tuple[int, int]]:
    """(game day ordinal, real seconds) from ``debug`` lines that carry a game date ("May 5, 1837" / "мая 5, 1837")."""
    out, prev, day = [], None, 0
    for r in records(folder, "debug"):
        d = GAME_DATE.search(r.text.split("\n", 1)[0])
        if not d:
            continue
        sec = r.time
        if prev is not None and sec + day < prev - 3600:  # past midnight
            day += 86400
        sec += day
        prev = sec
        out.append((date(int(d[3]), MONTHS[d[1]], int(d[2])).toordinal(), sec))
    return out


def slope(pts: list[tuple[int, int]]) -> float | None:
    """Least squares: real seconds per 30 game days."""
    n = len(pts)
    if n < 3:
        return None
    mx = sum(g for g, _ in pts) / n
    my = sum(s for _, s in pts) / n
    sxx = sum((g - mx) ** 2 for g, _ in pts)
    if sxx == 0:
        return None
    return sum((g - mx) * (s - my) for g, s in pts) / sxx * 30
