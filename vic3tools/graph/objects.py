"""Objects layer of a source's graph: a card per database record (building, production method, good, law…), with
its fields and the links the files make between records.

A card holds the name (localization of the record's key: Russian, else English, else the key), where the record is
defined, its fields — scalars and lists as written, data blocks (modifiers, ``goods = { … }``) as nested lists, script
blocks (triggers, effects, AI weights) only by name and lines — and links: a value or a block key that is another
record becomes a wiki link with the source's and type's path (``[[vanilla/Здания/Шахта|Шахта]]``), modifiers name
goods, pop types and buildings (``goods_input_grain_add`` → the grain card). "Ссылаются" lists the records that link
to this one, by field (a technology's card shows what it unlocks).

A mod's cards: only the records it adds or changes; a changed one gets "Отличия от ваниль" field by field and
``replaces`` on the vanilla card. Its links go to the mod's own card when the mod defines the target, else to vanilla.

Generated with a hand section: ``## Зачем в механике`` to the end of the file is kept, by ``key:``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.core import loc as locmod
from vic3tools.core import script

GEN = "v3 graph objects; ручной раздел — «## Зачем в механике»"
HAND_HEAD = "## Зачем в механике"


@dataclass(frozen=True)
class Type:
    id: str
    folder: str  # under the source root
    out: str  # folder in the source's graph
    noun: str  # one record, for the description
    tag: str


TYPES = [
    Type("building", "common/buildings", "Здания", "Здание", "здание"),
    Type("building_group", "common/building_groups", "Группы зданий", "Группа зданий", "группа-зданий"),
    Type("pmg", "common/production_method_groups", "Группы методов", "Группа методов производства", "группа-методов"),
    Type("pm", "common/production_methods", "Методы производства", "Метод производства", "метод-производства"),
    Type("goods", "common/goods", "Товары", "Товар", "товар"),
    Type("law", "common/laws", "Законы", "Закон", "закон"),
    Type("law_group", "common/law_groups", "Группы законов", "Группа законов", "группа-законов"),
    Type("tech", "common/technology/technologies", "Технологии", "Технология", "технология"),
    Type("ig", "common/interest_groups", "Группы интересов", "Группа интересов", "группа-интересов"),
    Type("ig_trait", "common/interest_group_traits", "Черты групп интересов", "Черта группы интересов",
         "черта-группы-интересов"),
    Type("ideology", "common/ideologies", "Идеологии", "Идеология", "идеология"),
    Type("company", "common/company_types", "Виды компаний", "Вид компании", "вид-компании"),
    Type("trait", "common/character_traits", "Черты", "Черта персонажа", "черта"),
    Type("pop_type", "common/pop_types", "Население/Типы", "Тип населения", "тип-населения"),
    Type("pop_need", "common/pop_needs", "Население/Потребности", "Потребность населения", "потребность"),
    Type("buy_package", "common/buy_packages", "Население/Пакеты покупок", "Пакет покупок", "пакет-покупок"),
]
BY_ID = {t.id: t for t in TYPES}

# what a field's values are, where a key could mean records of two types
FIELD_TARGETS = {
    "unlocking_technologies": "tech", "unlocking_laws": "law", "disallowing_laws": "law", "unlocking_principles": None,
    "building_group": "building_group", "parent_group": "building_group", "production_method_groups": "pmg",
    "production_methods": "pm", "group": "law_group", "building_types": "building",
    "extension_building_types": "building", "ideologies": "ideology", "traits": "ig_trait", "goods": "goods",
    "default": "goods", "default_building": "building", "unlocking_production_methods": "pm",
    "disabling_production_methods": "pm",
}
NO_LINK = {"texture", "icon", "background", "category", "city_type", "color", "layer", "era", "type", "lens",
           "land_usage", "ownership_type", "strata", "required_construction", "index"}
# modifier names that name a record: (pattern, type, role)
MODIFIER_REFS = [
    (re.compile(r"^goods_input_(\w+?)_(?:add|mult)$"), "goods", "вход"),
    (re.compile(r"^goods_output_(\w+?)_(?:add|mult)$"), "goods", "выход"),
    (re.compile(r"^building_employment_(\w+?)_(?:add|mult)$"), "pop_type", "занятость"),
    (re.compile(r"^(building_\w+?)_throughput_(?:add|mult)$"), "building", "производительность"),
]
# a backlink's field, as the target's card names it
ROLE_LABEL = {"unlocking_technologies": "открывает", "production_method_groups": "группы методов здания",
              "production_methods": "методы группы", "building_group": "входят в группу",
              "parent_group": "подгруппы", "group": "законы группы", "building_types": "здания компании",
              "extension_building_types": "расширения компании", "ideologies": "идеология группы",
              "traits": "черта группы", "default": "товар по умолчанию", "goods": "товар",
              "unlocking_laws": "открывает закон", "disallowing_laws": "запрещает закон"}
CONTROL = {"limit", "if", "else", "else_if", "AND", "OR", "NOT", "NOR", "NAND", "trigger", "modifier_if",
           "switch", "random_list", "custom_tooltip", "desc", "every_scope_state", "any_scope_state"}
# blocks that are script whatever they hold: triggers, effects, AI weights
SCRIPT_FIELD = re.compile(r"^(is_|can_|on_|ai_)|^(possible|potential|visible|valid|trigger|should_auto_expand)$")
TAG_WORD = re.compile(r"[\w-]+")
BAD_NAME = re.compile(r'[\\/:*?"<>|#^\[\]]')


@dataclass
class Record:
    type: Type
    key: str
    directive: str
    rel: str  # file, from the source root
    line: int
    end_line: int
    body: str


@dataclass
class Edge:
    src: tuple[str, str, str]  # source name, type id, key
    dst: tuple[str, str, str]
    role: str


def _game_order(rel: str) -> bytes:
    return rel.encode("utf-8")


def records(root: Path, t: Type) -> dict[str, Record]:
    """Records of one type in a source: the last definition of a key wins (the game's rule for these folders)."""
    folder = root / t.folder
    out: dict[str, Record] = {}
    if not folder.is_dir():
        return out
    files = sorted((p for p in folder.rglob("*.txt")), key=lambda p: _game_order(p.relative_to(root).as_posix()))
    for f in files:
        if t.id == "tech" and "/eras/" in f.as_posix():
            continue
        src = script.read(f)
        rel = f.relative_to(root).as_posix()
        for e in script.parse(src.text)[0]:
            if not e.is_block:
                continue
            out[e.key] = Record(t, e.key, e.directive, rel, src.line(e.start), src.line(e.end),
                                src.text[e.open + 1:e.close])
    return out


def all_records(root: Path) -> dict[str, dict[str, Record]]:
    return {t.id: records(root, t) for t in TYPES}


# --- names -----------------------------------------------------------------------------------------------------------


class Names:
    """Localization of a source (its own first, then the bases') and the card names it gives."""

    def __init__(self, roots: list[Path]):
        self.ru: dict[str, str] = {}
        self.en: dict[str, str] = {}
        for r in roots:
            for lang, d in (("russian", self.ru), ("english", self.en)):
                for k, e in locmod.read_language(r / "localization", lang).items():
                    d.setdefault(k, e.text)

    def text(self, key: str) -> str:
        return self._clean(self.ru.get(key) or self.en.get(key) or "")

    def english(self, key: str) -> str:
        return self._clean(self.en.get(key) or "")

    def _clean(self, s: str, depth: int = 0) -> str:
        if depth < 4:
            s = re.sub(r"\$([A-Za-z0-9_.]+)(\|\w+)?\$",
                       lambda m: self._clean(self.ru.get(m.group(1)) or self.en.get(m.group(1)) or "", depth + 1), s)
        s = re.sub(r"#\w+(;\w+)*\s?|#!|@\w+!", "", s)
        s = re.sub(r"\[[^\]]*\]", "", s)
        s = BAD_NAME.sub("", s).replace("\\n", " ")
        return re.sub(r"\s+", " ", s).strip(" .")


def card_names(recs: dict[str, dict[str, Record]], names: Names, taken: set[str] = frozenset()
               ) -> dict[tuple[str, str], str]:
    """(type id, key) -> file name; the same name twice in a type gets the key in brackets, a name already taken by
    another note of the vault (``taken``, lower case: concepts of the fork, terms) — the type."""
    out = {}
    for tid, rs in recs.items():
        by_name: dict[str, list[str]] = {}
        for k in rs:
            n = (names.text(k) or k)[:100]
            by_name.setdefault(n.lower(), []).append(k)
        for k in rs:
            n = (names.text(k) or k)[:100]
            if len(by_name[n.lower()]) > 1 and n != k:
                n = f"{n} ({k})"
            elif n.lower() in taken:
                n = f"{n} ({BY_ID[tid].noun.lower()})"
            out[(tid, k)] = n
    return out


# --- fields ----------------------------------------------------------------------------------------------------------


def _unquote(v: str) -> str:
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v


def is_data(body: str, depth: int = 0) -> bool:
    """A block of plain data (pairs, words, nested data), not script."""
    if depth > 3:
        return False
    for k, op, _s, _e, blk, o, c in script.block_items(body):
        if k is not None and (k in CONTROL or ":" in k or "." in k or op != "="):
            return False
        if blk and not is_data(body[o + 1:c], depth + 1):
            return False
    return True


class Linker:
    """Wiki links to records: the mod's own card where it has one, else the base source's."""

    def __init__(self, layers: list[tuple[str, dict[str, dict[str, Record]], dict]]):
        # layers: (source name, records it has cards for, card names), the first one wins
        self.layers = layers
        self.by_key: dict[str, set[str]] = {}
        for _s, recs, _n in layers:
            for tid, rs in recs.items():
                for k in rs:
                    self.by_key.setdefault(k, set()).add(tid)

    def target(self, key: str, want: str | None) -> tuple[str, str, str] | None:
        tids = self.by_key.get(key, set())
        if want:
            tid = want if want in tids else None
        else:
            tid = next(iter(tids)) if len(tids) == 1 else None
        if not tid:
            return None
        for src, recs, _names in self.layers:
            if key in recs.get(tid, {}):
                return src, tid, key
        return None

    def link(self, dst: tuple[str, str, str]) -> str:
        src, tid, key = dst
        for s, _recs, names in self.layers:
            if s == src:
                n = names[(tid, key)]
                return f"[[{src}/{BY_ID[tid].out}/{n}|{n}]]"
        return f"`{key}`"


class Fields:
    """Renders a record's fields and collects its edges."""

    def __init__(self, linker: Linker, me: tuple[str, str, str]):
        self.linker, self.me = linker, me
        self.edges: list[Edge] = []

    def _ref(self, word: str, field_: str, role: str | None = None) -> str:
        if field_ in NO_LINK:
            return f"`{word}`"
        want = FIELD_TARGETS.get(field_)
        if field_ in FIELD_TARGETS and want is None:
            return f"`{word}`"
        dst = self.linker.target(word, want) or (self.linker.target(word, None) if role else None)
        if not dst or dst[1:] == self.me[1:]:
            return f"`{word}`"
        self.edges.append(Edge(self.me, dst, role or field_))
        return self.linker.link(dst)

    def _modifier(self, key: str) -> str:
        for pat, tid, role in MODIFIER_REFS:
            m = pat.match(key)
            if m:
                dst = self.linker.target(m.group(1), tid)
                if dst:
                    self.edges.append(Edge(self.me, dst, role))
                    return f" → {self.linker.link(dst)}"
        return ""

    def render(self, body: str, top: str = "", indent: int = 0, start_line=None) -> list[str]:
        out = []
        pad = "  " * indent
        for k, op, s, e, blk, o, c in script.block_items(body):
            fld = k or top
            if not blk:
                v = _unquote(body[s:e].split(op, 1)[1].strip()) if k else _unquote(body[s:e])
                if k is None:
                    out.append(f"{pad}- {self._ref(v, top)}")
                    continue
                if indent == 0:
                    out.append(f"{pad}- **{k}**: {self._ref(v, k)}")
                else:
                    role = top if re.fullmatch(r"-?[\d.]+", v) else f"{top}: {v}"
                    out.append(f"{pad}- {self._ref(k, top, role=role)} = {self._ref(v, k)}" + self._modifier(k))
                continue
            inner = body[o + 1:c]
            name = f"**{k}**" if k else "блок"
            items = script.block_items(inner)
            if items and all(x[0] is None and not x[4] for x in items):  # a list of words
                words = [self._ref(_unquote(inner[x[2]:x[3]]), fld) for x in items]
                out.append(f"{pad}- {name}: {', '.join(words)}")
            elif not items:
                out.append(f"{pad}- {name}: пусто")
            elif is_data(inner) and not (k and SCRIPT_FIELD.search(k)):
                out.append(f"{pad}- {name}:")
                out += self.render(inner, fld, indent + 1)
            else:
                lines = f", строки {start_line(s)}–{start_line(e)}" if start_line else ""
                out.append(f"{pad}- {name}: скрипт{lines}")
        return out


# --- cards -----------------------------------------------------------------------------------------------------------


def hand_sections(folder: Path) -> dict[str, str]:
    out = {}
    if folder.is_dir():
        for f in folder.rglob("*.md"):
            t = f.read_text(encoding="utf-8")
            m, i = re.search(r"^key: (\S+)$", t, re.M), t.find("\n" + HAND_HEAD)
            if m and i >= 0:
                out[m.group(1)] = t[i + 1:].rstrip() + "\n"
    return out


def _q(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


@dataclass
class Card:
    rec: Record
    name: str
    fields: list[str]
    edges: list[Edge]
    diff: list[str] = field(default_factory=list)
    replaces: str = ""


def _line_of(body_line: int, body: str):
    """Line number of an offset into a record's body (the body starts on the record's first line)."""
    def f(pos: int) -> int:
        return body_line + body.count("\n", 0, pos)
    return f


def build_cards(src_name: str, recs: dict[str, dict[str, Record]], names: dict, linker: Linker) -> list[Card]:
    cards = []
    for tid, rs in recs.items():
        for k, r in rs.items():
            fl = Fields(linker, (src_name, tid, k))
            lines = fl.render(r.body, start_line=_line_of(r.line, r.body))
            cards.append(Card(r, names[(tid, k)], lines, fl.edges))
    return cards


def render_card(c: Card, src_name: str, label: str, version: str, snapshot_rel: str, names: Names,
                backlinks: list[Edge], linker: Linker, hand: dict[str, str]) -> str:
    r, t = c.rec, c.rec.type
    al = [c.name]
    en = names.english(r.key)
    if en and en not in al:
        al.append(en)
    if r.key not in al:
        al.append(r.key)
    fm = ["---", "type: concept",
          f"description: {_q(f'{t.noun} «{c.name}» — {label} {version}, `{r.key}`')}",
          "project: vic3", f"source: {src_name}", f"aliases: [{', '.join(_q(a) for a in al)}]",
          f"tags: [{label if TAG_WORD.fullmatch(label) else src_name}, {t.tag}]",
          f"generated: {_q(GEN)}", f"key: {r.key}", f"paths: [{snapshot_rel}/{r.rel}]"]
    if c.replaces:
        fm.append(f"replaces: {_q(c.replaces)}")
    fm.append("---")
    how = {"INJECT": "дополняет запись ваниль (`INJECT:`)", "REPLACE": "заменяет запись ваниль (`REPLACE:`)"}
    head = [f"# {c.name}", "",
            f"{t.noun} · `{r.key}` · `{r.rel}:{r.line}`" + (f" · {how[r.directive]}" if r.directive in how else ""),
            ""]
    if c.diff:
        head += ["## Отличия от ваниль", "", *c.diff, ""]
    body = ["## Поля", "", *(c.fields or ["Полей нет."]), ""]
    if backlinks:
        body += ["## Ссылаются", ""]
        groups: dict[tuple[str, str], list[str]] = {}
        for e in backlinks:
            groups.setdefault((BY_ID[e.src[1]].out, e.role), [])
            ln = linker.link(e.src)
            if ln not in groups[(BY_ID[e.src[1]].out, e.role)]:
                groups[(BY_ID[e.src[1]].out, e.role)].append(ln)
        for (tout, role), links in sorted(groups.items()):
            label = ROLE_LABEL.get(role, role)
            body.append(f"- **{tout}** ({label}): {', '.join(sorted(links, key=str.lower))}")
        body.append("")
    text = "\n".join(fm + head + body)
    if r.key in hand:
        text += "\n" + hand[r.key]
    return text.rstrip("\n") + "\n"


def type_map(src_name: str, label: str, version: str, t: Type, cards: list[Card]) -> str:
    rows = sorted((c for c in cards if c.rec.type is t), key=lambda c: c.name.lower())
    out = ["---", "type: map", f"description: {_q(f'Карта: {t.out} — {label} {version}, все карточки типа')}",
           "project: vic3", f"source: {src_name}", f"tags: [{t.tag}]", f"generated: {_q(GEN)}", "---",
           f"# {t.out} — {label}", "",
           f"Карточки типа «{t.noun}» ({len(rows)}, `{t.folder}`). Генерат `v3 graph objects`: текст не править, "
           f"ручной раздел — «{HAND_HEAD[3:]}».", ""]
    letter = None
    for c in rows:
        first = c.name[:1].upper()
        if first != letter:
            letter = first
            out += ["", f"## {letter}", ""]
        out.append(f"- [[{src_name}/{t.out}/{c.name}|{c.name}]] — `{c.rec.key}`")
    return "\n".join(out) + "\n"


def notes(cards: list[Card], src_name: str, label: str, version: str, snapshot_rel: str, names: Names,
          linker: Linker, extra_edges: list[Edge], dst: Path) -> dict[str, str]:
    """Card files and type maps of a source: relative path -> text."""
    hand = hand_sections(dst)
    back: dict[tuple[str, str, str], list[Edge]] = {}
    for c in cards:
        for e in c.edges:
            back.setdefault(e.dst, []).append(e)
    for e in extra_edges:
        back.setdefault(e.dst, []).append(e)
    out = {}
    for c in cards:
        me = (src_name, c.rec.type.id, c.rec.key)
        out[f"{c.rec.type.out}/{c.name}.md"] = render_card(c, src_name, label, version, snapshot_rel, names,
                                                            back.get(me, []), linker, hand)
    for t in TYPES:
        if any(c.rec.type is t for c in cards):
            out[f"{t.out}/_Карта {t.out.rsplit('/', 1)[-1]}.md"] = type_map(src_name, label, version, t, cards)
    return out


def snapshot_rel(snapshot: Path, paths_root: Path) -> str:
    return Path(os.path.relpath(snapshot, paths_root)).as_posix()
