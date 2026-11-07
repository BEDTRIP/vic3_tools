"""``v3 graph``: the generated layers of a source's documentation graph (terms, object cards, engine reference, what a
mod changes in vanilla), written into a documents repo next to a snapshot of the sources.

The layout is ``graph.toml`` at the root of the documents repo::

    version = "1.13"                       # game version of the snapshot, written into notes
    avoid = ["../../docs"]                 # folders whose note names generated names must not repeat
    paths_root = ".."                      # ``paths`` of the notes are relative to it (as docs-check.toml has it)
    dump = "C:/…/Victoria 3/docs"          # engine: the script_docs dump to copy (optional), and its date
    dump_date = "2026-10-13"
    audience = "agent"                     # into every note's header: who the notes are for (methodology,
                                           # «Шапка документа»); none — for a person
    [sources.vanilla]
    snapshot = "../.vanillaVIC3"           # the source's files, relative to graph.toml
    label = "ваниль"
    [sources.ef]
    snapshot = "../E&F"
    label = "E&F"

Each source writes into ``<repo>/<source>/``. Notes are generated: the text is never edited by hand, a hand section
(named per layer) is kept by the note's ``key:``.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Source:
    name: str  # folder in the documents repo
    snapshot: Path
    label: str


@dataclass
class Config:
    root: Path
    version: str
    sources: dict[str, Source]
    avoid: list[Path] = field(default_factory=list)
    paths_root: Path = Path()  # what ``paths`` of the notes are relative to (the snapshot's repo)
    dump: Path | None = None  # the game's docs folder with the script_docs dump, copied by ``engine``
    dump_date: str = ""
    audience: str = ""

    @property
    def vanilla(self) -> Source:
        return self.sources["vanilla"]

    def avoid_names(self) -> set[str]:
        """Note names (file stems) in the ``avoid`` folders."""
        out: set[str] = set()
        for d in self.avoid:
            if d.is_dir():
                out |= {f.stem for f in d.rglob("*.md")}
        return out


def find_config(start: Path) -> Path:
    for d in [start.resolve(), *start.resolve().parents]:
        if (d / "graph.toml").is_file():
            return d / "graph.toml"
    raise FileNotFoundError("graph.toml not found here or above")


def load(start: Path) -> Config:
    path = find_config(start)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    srcs = {name: Source(name, (root / s["snapshot"]).resolve(), s.get("label", name))
            for name, s in data.get("sources", {}).items()}
    return Config(root, str(data.get("version", "")), srcs, [(root / a).resolve() for a in data.get("avoid", [])],
                  (root / data.get("paths_root", ".")).resolve(), Path(data["dump"]) if data.get("dump") else None,
                  str(data.get("dump_date", "")), str(data.get("audience", "")))


@dataclass
class Sync:
    changed: list[str]
    stale: list[str]


def with_audience(text: str, audience: str) -> str:
    """``audience: <who>`` into the note's header, right after ``project:`` (or the header's first line)."""
    if not audience or not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 3)
    head = text[4:end].split("\n")
    at = next((i + 1 for i, line in enumerate(head) if line.startswith("project:")), 1)
    head.insert(at, f"audience: {audience}")
    return "---\n" + "\n".join(head) + text[end:]


def sync(dst: Path, notes: dict[str, str], check: bool, scope: tuple[str, ...] = (), audience: str = "") -> Sync:
    """Make ``dst`` hold exactly ``notes`` (relative path -> text): ``.md`` files not in ``notes`` are stale and
    removed — only under ``scope`` (relative folder prefixes the layer owns) when it is given. ``audience`` goes into
    every header."""
    notes = {k: with_audience(v, audience) for k, v in notes.items()}
    have = set()
    if dst.is_dir():
        for dp, _dn, fn in os.walk(dst):
            for f in fn:
                if f.endswith(".md"):
                    have.add(Path(dp, f).relative_to(dst).as_posix())
    have = {h for h in have if h.startswith(scope)} if scope else have
    changed = [f for f, t in notes.items()
               if not (dst / f).is_file() or (dst / f).read_bytes().decode("utf-8") != t]
    stale = sorted(have - set(notes))
    if not check:
        for f in changed:
            p = dst / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(notes[f], encoding="utf-8", newline="\n")
        for f in stale:
            (dst / f).unlink()
    return Sync(sorted(changed), stale)
