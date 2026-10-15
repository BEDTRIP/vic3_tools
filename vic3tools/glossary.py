"""Glossary: the game's own names for things in every language, from its localization.

Built once per game version into the cache (``glossary-<version>.sqlite``): for each key, the English text and the
text in every other language the game ships. A "term" is a short plain entry (a name, not a sentence or a template),
so a search for "institution" finds what the Russian game calls it, not a translator's guess. The tools' own terms
(index, lint, outline…) are a separate section from ``data/tool_terms.toml``.
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from vic3tools.core import loc
from vic3tools.core.paths import cache_dir

LANGS = ("english", "russian", "french", "german", "spanish", "polish", "braz_por", "japanese", "korean",
         "simp_chinese", "turkish")
SHORT = {"english": "en", "russian": "ru", "french": "fr", "german": "de", "spanish": "es", "polish": "pl",
         "braz_por": "pt", "japanese": "ja", "korean": "ko", "simp_chinese": "zh", "turkish": "tr"}
MAX_TERM_WORDS = 6
_NOT_TERM = re.compile(r"[\[\]$£@]|\\n|#\w|\|")


@dataclass
class Hit:
    key: str
    texts: dict[str, str]  # short language code → text
    section: str  # "game" or "tools"


def db_path(version: str) -> Path:
    return cache_dir() / f"glossary-{version}.sqlite"


def is_term(text: str) -> bool:
    return bool(text.strip()) and not _NOT_TERM.search(text) and len(text.split()) <= MAX_TERM_WORDS


def build(game_root: Path, version: str, out: Path | None = None) -> tuple[Path, int]:
    """Build the glossary from the game's localization. Returns the database path and the number of terms."""
    loc_root = game_root / "game" / "localization"
    per_lang = {lang: loc.read_language(loc_root, lang) for lang in LANGS}
    english = per_lang["english"]
    out = out or db_path(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    cols = ", ".join(SHORT[lang] for lang in LANGS)
    con.execute(f"CREATE TABLE terms (key TEXT PRIMARY KEY, {cols})")
    rows = []
    for key, e in english.items():
        if not is_term(e.text):
            continue
        rows.append((key, *(per_lang[lang][key].text if key in per_lang[lang] else None for lang in LANGS)))
    marks = ", ".join("?" * (len(LANGS) + 1))
    con.executemany(f"INSERT INTO terms VALUES ({marks})", rows)
    con.execute("CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('game_version', ?)", (version,))
    con.commit()
    con.close()
    tmp.replace(out)
    return out, len(rows)


def tool_terms() -> list[Hit]:
    data = tomllib.loads(resources.files("vic3tools").joinpath("data/tool_terms.toml").read_text(encoding="utf-8"))
    return [Hit(key, dict(texts), "tools") for key, texts in data.items()]


def search(query: str, db: Path | None, limit: int = 10) -> list[Hit]:
    """Terms whose text in any language matches ``query``: exact first, then starting with it, then containing it."""
    q = query.strip().casefold()
    if not q:
        return []
    # Sort: how well it matches, then game concepts (`concept_*`) before other keys, then shorter English text.
    scored: list[tuple[int, int, int, Hit]] = []
    for hit in tool_terms():
        rank = _rank(q, [hit.key, *hit.texts.values()])
        if rank is not None:
            scored.append((rank, 0, 0, hit))
    if db is not None and db.is_file():
        con = sqlite3.connect(db)
        # SQLite's own lower() is ASCII-only; Cyrillic and the rest need Python's casefold.
        con.create_function("cf", 1, lambda s: s.casefold() if s else s, deterministic=True)
        names = [SHORT[lang] for lang in LANGS]
        where = " OR ".join(f"instr(cf({c}), ?) > 0" for c in ["key", *names])
        sql = f"SELECT key, {', '.join(names)} FROM terms WHERE {where}"
        for row in con.execute(sql, [q] * (len(names) + 1)):
            texts = {n: v for n, v in zip(names, row[1:], strict=True) if v}
            rank = _rank(q, [row[0], *texts.values()])
            if rank is not None:
                concept = 0 if row[0].startswith("concept_") else 1
                scored.append((rank, concept, len(texts.get("en", "")), Hit(row[0], texts, "game")))
        con.close()
    scored.sort(key=lambda s: (s[0], s[1], s[2], s[3].key))
    return [s[3] for s in scored[:limit]]


def _rank(q: str, values: list[str]) -> int | None:
    best = None
    for v in values:
        v = v.casefold()
        r = 0 if v == q else 1 if v.startswith(q) else 2 if q in v else None
        if r is not None and (best is None or r < best):
            best = r
    return best
