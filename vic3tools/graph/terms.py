"""Terms layer of a source's graph: one note per game concept (Vickypedia tooltips), from ``common/game_concepts``.

Port of the fork's ``regen_ld_vanilla_concepts.py`` (stage ДОК, step 4): the same output byte for byte. A note holds
the concept's name (Russian localization, else English), synonyms (forms of the name, the English one, the key) and
the game's description; concept references in the text (``[Concept('concept_x', 'text')]``, ``[concept_x]``,
``$concept_x$``) become wiki links ``[[Name|text]]`` (a caption longer than 80 characters — a whole description —
goes in as text: a markdown link can't span lines). Forms of one concept (``concept_radicals``) are synonyms of
its note.
A name equal to a note elsewhere in the vault (``avoid``) gets " (ваниль)".

A generated note with a hand section: the hand part (``## Рабочее`` to the end) is kept, by ``key:``, even when
the note's name changes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

GEN = "v3 graph terms; ручной раздел — «## Рабочее»"
HAND_HEAD = "## Рабочее"
SOURCE = re.compile(r"^key: (concept_\w+)$", re.M)
LOC_LINE = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s*"(.*)"\s*(#.*)?$')
BAD_NAME = re.compile(r'[\\/:*?"<>|#^\[\]]')


def load_loc(folder):
    loc = {}
    for dp, dn, fn in os.walk(folder):
        dn.sort()
        for f in sorted(fn):
            if not f.endswith(".yml"):
                continue
            with open(os.path.join(dp, f), encoding="utf-8-sig", errors="replace") as fh:
                for line in fh:
                    m = LOC_LINE.match(line)
                    if m and m.group(1) not in loc:
                        loc[m.group(1)] = m.group(2)
    return loc


def hand_sections(folder):
    """Hand-written part of the existing notes: concept key -> text from HAND_HEAD to the end of the file."""
    out = {}
    if folder.is_dir():
        for f in sorted(os.listdir(folder)):
            if f.endswith(".md"):
                t = (folder / f).read_text(encoding="utf-8")
                m, i = SOURCE.search(t), t.find("\n" + HAND_HEAD)
                if m and i >= 0:
                    out[m.group(1)] = t[i + 1:].rstrip() + "\n"
    return out


def load_concepts(folder):
    keys = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".txt"):
            with open(os.path.join(folder, f), encoding="utf-8-sig") as fh:
                for line in fh:
                    m = re.match(r"^(concept_\w+)\s*=", line)
                    if m and m.group(1) not in keys:
                        keys.append(m.group(1))
    return keys


class Gen:
    def __init__(self, concepts, loc, en, mod_names, fork=None, gen=GEN, version="1.13", src="vanilla",
                 label="ваниль", own=None, base_names=None):
        # a mod's terms: notes only for its ``own`` concepts, links to the rest (vanilla's, named by ``base_names``)
        # and to its own ones carry the path, as every generated link of a mod does
        self.concepts = concepts
        self.src, self.label = src, label
        self.tag = "ваниль" if src == "vanilla" else src
        self.own = own if own is not None else concepts
        self.prefix = {}
        self.fork = fork or {}
        self.gen, self.version = gen, version
        self.cset = set(concepts)
        self.loc, self.en = loc, en
        self.base_cache = {}
        self.nolink = 0
        self.names = {}
        used = {}
        for c in concepts:
            if base_names is not None and c not in self.own:
                self.names[c] = base_names.get(c) or self.clean_name(loc.get(c) or en.get(c) or c)
                self.prefix[c] = "vanilla/Термины/"
                continue
            name = self.clean_name(loc.get(c) or en.get(c) or c)
            if name in mod_names:
                name += f" ({label})"
            if base_names is not None:
                self.prefix[c] = f"{src}/Термины/"
            if name in used:
                name = f"{name} ({c[len('concept_'):]})"
            used[name] = c
            self.names[c] = name

    @staticmethod
    def clean_name(s):
        s = re.sub(r"#\w+(;\w+)*\s?|#!|@\w+!", "", s)
        s = re.sub(r"\[[^\]]*\]|\$[^$]*\$", "", s)
        s = BAD_NAME.sub("", s).strip(" .")
        return s or "?"

    def base(self, key):
        """The concept a localization key is a form of: concept_radicals -> concept_radical."""
        if key in self.base_cache:
            return self.base_cache[key]
        best = None
        if key in self.cset:
            best = key
        else:
            for c in self.concepts:
                if key.startswith(c) and (best is None or len(c) > len(best)):
                    best = c
        self.base_cache[key] = best
        return best

    @staticmethod
    def low(s, fmt):
        """`|l` in a game text call — lowercase first letter."""
        return s[:1].lower() + s[1:] if fmt and "l" in fmt else s

    def link(self, key, text=None, fmt=None):
        c = self.base(key)
        if not c:
            return text or self.loc.get(key, key)
        name = self.names[c]
        raw = text if text is not None else self.loc.get(key) or name
        shown = self.clean_name(self.plain(raw) if self.nolink < 4 else raw) if raw else name
        # only line breaks and plain spaces: a non-breaking space stays, or the caption differs from the name by it
        shown = self.low(re.sub(r"[ \t\r\n]+", " ", shown), fmt)
        if len(shown) > 80:
            # a whole description shown as a concept link (`$concept_x_desc$`, Concept('concept_x', '...')): a markdown
            # link can't span lines, so the text goes in as text, with its own links
            return self.low(self.conv(raw, 3) if self.nolink < 4 else raw, fmt)
        if self.nolink:
            return shown
        target = self.prefix.get(c, "") + name
        self.ph.append(f"[[{target}]]" if shown == name and target == name else f"[[{target}|{shown}]]")
        return f"\x00{len(self.ph) - 1}\x00"

    def plain(self, s, depth=3):
        """Game text without links — for link captions and names."""
        self.nolink += 1
        try:
            return self.conv(s, depth)
        finally:
            self.nolink -= 1

    def game_name(self, key, depth=3):
        v = self.loc.get(key) or self.en.get(key)
        if not v:
            return key
        return self.clean_name(self.plain(v, depth + 1) if depth < 6 else v)

    def conv(self, s, depth=0):
        """Game text -> markdown; links are kept as placeholders until the outermost call returns."""
        outer = depth == 0
        if outer:
            self.ph = []
        s = s.replace("\\n", "\n").replace('\\"', '"')
        s = re.sub(r"\n?\$EFFECT_LIST_BULLET\$", "\n- ", s)
        s = re.sub(r"\n?#indent_newline(:\d+)?\s*", "\n", s)
        s = re.sub(r"#tooltip:\S*\s?", "", s)
        s = s.replace("[Nbsp]", " ")
        # [Concept('concept_x', 'text')|fmt]
        s = re.sub(r"\[Concept\(\s*'(concept_\w+)'\s*,\s*'([^']*)'\s*\)(\|[^\]]*)?\]",
                   lambda m: self.link(m.group(1), m.group(2), m.group(3)), s)
        s = re.sub(r"\[(concept_\w+)(\|\w+)?\]", lambda m: self.link(m.group(1), None, m.group(2)), s)
        s = re.sub(r"\$(concept_\w+)(\|\w+)?\$", lambda m: self.link(m.group(1)), s)
        s = re.sub(r"\[GetDefine\('(\w+)',\s*'(\w+)'\)(\|[^\]]*)?\]", r"`\1.\2`", s)
        # [SelectLocalization(GetPlayer.IsValid, 'KEY_IF_PLAYER', 'key_or_text')|fmt] — the text without a player
        s = re.sub(r"\[SelectLocalization\([^,]+,\s*'\w+',\s*'([^']+)'\)(\|[^\]]*)?\]",
                   lambda m: self.low(self.game_name(m.group(1), depth), m.group(2)), s)
        s = re.sub(r"\[AddLocalizationIf\([^,]+,\s*'(\w+)'\)\]",
                   lambda m: self.conv(self.loc[m.group(1)], depth + 1) if depth < 6 and m.group(1) in self.loc else "",
                   s)
        s = re.sub(r"\[Get\w+\('(\w+)'[^\]|]*(\|[^\]]*)?\]",
                   lambda m: self.low(self.game_name(m.group(1), depth), m.group(2)), s)

        def key(m):
            k = m.group(1)
            if depth < 6 and k in self.loc:
                return self.conv(self.loc[k], depth + 1)
            return k
        s = re.sub(r"\$([A-Za-z0-9_]+)(\|\w+)?\$", key, s)
        s = re.sub(r"\[[^\[\]]*\]", lambda m: f"`{m.group(0)[1:-1]}`", s)
        s = re.sub(r"#(v|b|bold|title) ([^#]*)#!", r"**\2**", s)
        s = re.sub(r"#(i|italic) ([^#]*)#!", r"*\2*", s)
        s = re.sub(r"#\w+([;:]\S*)?\s?", "", s).replace("#!", "")
        s = re.sub(r"@\w+!", "", s)
        s = re.sub(r"^\s*[•·]\s*", "- ", s, flags=re.M)
        s = re.sub(r"(?<=\S) {2,}", " ", s)
        s = re.sub(r"[ \t]+$", "", s, flags=re.M)
        if outer:
            while "\x00" in s:
                s = re.sub(r"\x00(\d+)\x00", lambda m: self.ph[int(m.group(1))], s)
        return s.strip()

    def aliases(self, c):
        al = []
        for k, v in self.loc.items():
            if k.startswith(c) and not k.endswith("_desc") and self.base(k) == c and k != c:
                n = self.clean_name(v)
                if n and n != self.names[c] and n not in al and len(n) < 60:
                    al.append(n)
        en = self.clean_name(self.en.get(c, ""))
        if en and en != "?" and en not in al:
            al.append(en)
        al.append(c)
        return al

    def note(self, c):
        name = self.names[c]
        desc = self.loc.get(c + "_desc") or self.en.get(c + "_desc") or ""
        al = ", ".join('"' + a.replace('"', "'") + '"' for a in self.aliases(c))
        body = self.conv(desc) if desc else "_Описания в игре нет._"
        fork = "\n" + self.fork[c] if c in self.fork else ""
        whose = "Термин игры" if self.src == "vanilla" else f"Термин мода {self.label}"
        dsc = f"{whose} «{name}» — подсказка-понятие Victoria 3 {self.version} (`{c}`)".replace('"', "'")
        return (f'---\ntype: concept\ndescription: "{dsc}"\nproject: vic3\nsource: {self.src}\naliases: [{al}]\n'
                f'tags: [{self.tag}, термин]\ngenerated: "{self.gen}"\nkey: {c}\n---\n'
                f"# {name}\n\n{body}\n{fork}")

    def mod_index(self):
        rows = sorted(self.own, key=lambda c: self.names[c].lower())
        out = ["---", "type: map",
               f'description: "Карта терминов мода {self.label} — его подсказки-понятия по алфавиту"',
               "project: vic3", f"source: {self.src}", f"tags: [{self.tag}, термин]", f'generated: "{self.gen}"',
               "---", f"# Термины {self.label}", "",
               f"Свои подсказки-понятия мода (`common/game_concepts`), {len(rows)}; ссылки на термины игры — в "
               "`vanilla/Термины/`. Генерат: текст руками не править, ручной раздел — «## Рабочее».", ""]
        out += [f"- [[{self.src}/Термины/{self.names[c]}|{self.names[c]}]]" for c in rows]
        return "\n".join(out) + "\n"

    def index(self):
        rows = sorted(self.concepts, key=lambda c: self.names[c].lower())
        out = ["---", "type: map",
               f'description: "Карта терминов игры Victoria 3 {self.version} — все подсказки-понятия по алфавиту"',
               "project: vic3", "source: vanilla", "tags: [ваниль, термин]", f'generated: "{self.gen}"', "---",
               "# Карта ванили", "",
               f"Термины игры — подсказки-понятия Victoria 3 {self.version} (`common/game_concepts`, локализация), "
               "по заметке на понятие.",
               "Генерат: текст игры руками не править, ручной раздел заметки — «## Рабочее», "
               "генератор его сохраняет.", ""]
        letter = None
        for c in rows:
            n = self.names[c]
            first = n[:1].upper()
            if first != letter:
                letter = first
                out += ["", f"## {letter}", ""]
            out.append(f"- [[{n}]]")
        return "\n".join(out) + "\n"


def build_mod(mod: Path, game: Path, dst: Path, avoid: set[str], src: str, label: str, version: str,
              van_names: dict[str, str], lang: str = "russian") -> tuple[dict[str, str], dict]:
    """A mod's own concepts (those vanilla lacks); its text links to vanilla's terms by path."""
    van = load_concepts(game / "common" / "game_concepts")
    folder = mod / "common" / "game_concepts"
    own = [c for c in (load_concepts(folder) if folder.is_dir() else []) if c not in set(van)]
    if not own:
        return {}, {"terms": 0}
    loc = load_loc(mod / "localization" / lang)
    for k, v in load_loc(game / "localization" / lang).items():
        loc.setdefault(k, v)
    en = load_loc(mod / "localization" / "english")
    for k, v in load_loc(game / "localization" / "english").items():
        en.setdefault(k, v)
    g = Gen(own + van, loc, en, avoid, hand_sections(dst), GEN, version, src, label, own, van_names)
    out = {f"{g.names[c]}.md": g.note(c) for c in own}
    out[f"_Карта терминов {label}.md"] = g.mod_index()
    return out, {"terms": len(own)}


def build(game: Path, dst: Path, avoid: set[str], lang: str = "russian", gen: str = GEN,
          version: str = "1.13") -> tuple[dict[str, str], dict]:
    """Notes of the terms layer: file name -> text, and counts for the report."""
    concepts = load_concepts(game / "common" / "game_concepts")
    loc = load_loc(game / "localization" / lang)
    en = load_loc(game / "localization" / "english")
    g = Gen(concepts, loc, en, avoid, hand_sections(dst), gen, version)
    out = {f"{g.names[c]}.md": g.note(c) for c in concepts}
    out["_Карта ванили.md"] = g.index()
    return out, {"concepts": len(concepts), "loc": len(loc)}


def names_of(game: Path, avoid: set[str], lang: str = "russian") -> dict[str, str]:
    """Vanilla's concept -> its note name, as ``build`` names them."""
    concepts = load_concepts(game / "common" / "game_concepts")
    g = Gen(concepts, load_loc(game / "localization" / lang), load_loc(game / "localization" / "english"), avoid)
    return dict(g.names)
