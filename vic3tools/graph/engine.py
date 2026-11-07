"""Engine reference of the vanilla graph: tables of what script can use, from the game's own dump (console
``script_docs``, ``dump_data_types``, ``dump_tweakables``).

The dump is copied as is into ``<vanilla>/движок/дамп/`` (the snapshot of the reference) and read from there; notes are
one per kind — effects, triggers, modifier types, event targets, on_actions — the big ones split by first letter.
An entry is a list item with a block id (``^m-goods-input-grain-add``), so a card links to the very line
(``[[…/Модификаторы G#^m-goods-input-grain-add|goods_input_grain_add]]``).

The dump is taken with the playset loaded: modifier types, on_actions and custom localization of the mods in it are
listed too, and the note says so.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

GEN = "v3 graph engine"
RAW = ("effects.log", "triggers.log", "modifiers.log", "event_targets.log", "on_actions.log",
       "custom_localization.log", "tweakables.txt")


@dataclass
class Entry:
    name: str
    text: str  # one line of markdown after the name


@dataclass(frozen=True)
class Kind:
    id: str
    title: str  # note name; split notes add " <letter>"
    raw: str
    prefix: str  # block id prefix
    split: bool


KINDS = [
    Kind("effects", "Эффекты", "effects.log", "e", True),
    Kind("triggers", "Триггеры", "triggers.log", "t", True),
    Kind("modifiers", "Модификаторы", "modifiers.log", "m", True),
    Kind("event_targets", "Цели событий", "event_targets.log", "s", False),
    Kind("on_actions", "on_action", "on_actions.log", "o", False),
]


def block_id(prefix: str, name: str) -> str:
    return prefix + "-" + re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()


def _clip(s: str, n: int = 400) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def _code(s: str) -> str:
    return "`" + s.replace("`", "'") + "`"


def parse_docs(text: str) -> list[Entry]:
    """``## name`` / ``### name`` sections: description, usage lines, ``**Supported Scopes**`` and the like."""
    out = []
    for m in re.finditer(r"^#{2,3} (\S+)\s*\n(.*?)(?=^#{2,3} |\Z)", text, re.M | re.S):
        name, body = m.group(1), m.group(2)
        meta, desc, usage = [], [], []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            mm = re.match(r"^\*\*(.+?)\*\*:\s*(.*)$", line) or re.match(r"^(Input Scopes|Output Scopes|Requires Data|"
                                                                     r"Wildcard|Global Link):\s*(.*)$", line)
            if mm:
                meta.append(f"{mm.group(1).lower()}: {mm.group(2)}")
            elif line.startswith(name) or "=" in line or "{" in line:
                usage.append(line)
            else:
                desc.append(line)
        parts = [_clip(" ".join(desc))] if desc else []
        if usage:
            parts.append(_code(_clip(" ".join(usage), 200)))
        parts += [_clip(x, 200) for x in meta]
        out.append(Entry(name, " · ".join(p for p in parts if p)))
    return out


def parse_modifiers(text: str) -> list[Entry]:
    out = []
    for m in re.finditer(r"^(\S+):\n((?:  .*\n?)*)", text, re.M):
        f = dict(re.findall(r"^  (\w+): ?(.*)$", m.group(2), re.M))
        parts = [x for x in (f.get("Name", "").strip(), _clip(f.get("Description", ""))) if x]
        if f.get("Mask"):
            parts.append(f"mask: {f['Mask']}")
        out.append(Entry(m.group(1), " · ".join(parts)))
    return out


def parse_on_actions(text: str) -> list[Entry]:
    out = []
    for chunk in text.split("--------------------"):
        m = re.search(r"^(\S+):\s*$", chunk, re.M)
        if not m or m.group(1).startswith("On Action"):
            continue
        f = dict(re.findall(r"^([\w ]+): (.*)$", chunk, re.M))
        out.append(Entry(m.group(1), f"из кода: {f.get('From Code', '?')} · scope: {f.get('Expected Scope', '?')}"))
    return out


def entries(kind: Kind, raw_dir: Path) -> list[Entry]:
    p = raw_dir / kind.raw
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    if kind.id == "modifiers":
        es = parse_modifiers(text)
    elif kind.id == "on_actions":
        es = parse_on_actions(text)
    else:
        es = parse_docs(text)
    seen, out = set(), []
    for e in sorted(es, key=lambda e: e.name.lower()):
        if e.name not in seen:
            seen.add(e.name)
            out.append(e)
    return out


def letter(name: str) -> str:
    c = name[:1].upper()
    return c if c.isalpha() else "_"


def note_of(kind: Kind, name: str) -> str:
    """Note name of an entry."""
    return f"{kind.title} {letter(name)}" if kind.split else kind.title


def copy_raw(src: Path, raw_dir: Path) -> list[str]:
    """Copy the dump from the game's documents into the snapshot folder; files that differ are listed."""
    changed = []
    raw_dir.mkdir(parents=True, exist_ok=True)
    for f in [*RAW, *(f"data_types/{p.name}" for p in sorted((src / "data_types").glob("*.txt")))]:
        a, b = src / f, raw_dir / f
        if a.is_file() and (not b.is_file() or a.read_bytes() != b.read_bytes()):
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(a, b)
            changed.append(f)
    return changed


def notes(raw_dir: Path, src_name: str, version: str, dated: str) -> tuple[dict[str, str], dict]:
    """Notes of the reference (relative to ``движок/``), and counts."""
    out, counts = {}, {}
    for k in KINDS:
        es = entries(k, raw_dir)
        counts[k.id] = len(es)
        groups: dict[str, list[Entry]] = {}
        for e in es:
            groups.setdefault(note_of(k, e.name), []).append(e)
        for note, items in groups.items():
            fm = ["---", "type: reference",
                  f'description: "Справочник движка Victoria 3 {version}: {note} — {len(items)}, из дампа script_docs"',
                  "project: vic3", f"source: {src_name}", "tags: [ваниль, движок]", f'generated: "{GEN}"', "---"]
            body = [f"# {note}", "",
                    f"Из дампа `{k.raw}` ({dated}; копия — `дамп/`). Генерат `v3 graph engine`: руками не править; "
                    "дамп снят с набором модов — записи модов в нём тоже есть.", ""]
            body += [f"- **{e.name}** — {e.text} ^{block_id(k.prefix, e.name)}" if e.text
                     else f"- **{e.name}** ^{block_id(k.prefix, e.name)}" for e in items]
            out[f"{note}.md"] = "\n".join(fm + body) + "\n"
    idx = ["---", "type: map",
           f'description: "Справочник движка Victoria 3 {version} — карта: что в дампе script_docs"',
           "project: vic3", f"source: {src_name}", "tags: [ваниль, движок]", f'generated: "{GEN}"', "---",
           "# Справочник движка", "",
           f"Что скрипт может звать, по собственному дампу игры ({dated}, консоль `script_docs`, `dump_data_types`, "
           "`dump_tweakables`); сырой дамп — `дамп/`, пересобрать — `v3 graph engine` (папка дампа — `dump` в "
           "`graph.toml`). "
           "Дамп снят с набором модов: модификаторы, on_action и custom localization модов в нём тоже есть.", ""]
    for k in KINDS:
        names = sorted({note_of(k, e.name) for e in entries(k, raw_dir)})
        if not names:
            continue
        links = ", ".join(f"[[{src_name}/движок/{n}|{n.rsplit(' ', 1)[-1] if k.split else n}]]" for n in names)
        idx.append(f"- **{k.title}** ({counts[k.id]}): {links}")
    idx += ["", "Без таблиц, только в `дамп/`: `custom_localization.log`, `tweakables.txt` (все define по имени), "
            "`data_types/` (функции данных интерфейса)."]
    out["_Карта движка.md"] = "\n".join(idx) + "\n"
    return out, counts


def modifier_links(raw_dir: Path, src_name: str) -> dict[str, str]:
    """Modifier type -> link target with the block id, for cards."""
    k = KINDS[2]
    return {e.name: f"{src_name}/движок/{note_of(k, e.name)}#^{block_id(k.prefix, e.name)}"
            for e in entries(k, raw_dir)}
