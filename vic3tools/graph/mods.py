"""What a mod changes in vanilla: the reference note ``Что меняет в ванили — <mod>`` and the cards of the records it
adds or changes (``objects`` layer, only the mod's own).

Records of ``common/`` are sorted by what the game does with them (rules of the ``vic3-modding`` skill,
``load-and-override``): a key vanilla lacks — the mod **adds** it; a bare body or ``REPLACE:`` of a vanilla key —
**replaces** the record whole (and every ``INJECT:`` before it); ``INJECT:`` — **adds to** it; a file with vanilla's
relative path — vanilla's file is not read at all, so its records the mod does not define again are **removed**. In
``scripted_effects`` / ``scripted_triggers`` / ``script_values`` a bare repeat of a vanilla key does not take effect.
``on_actions``, ``history``, ``named_colors`` add up; ``defines`` merge per define — listed define by define.
Outside ``common/``: files of each folder, those that override vanilla's by path; event ids vanilla also has
(the game keeps one, not by load order); localization keys vanilla has outside ``replace/`` (the first file wins).

The comparison is with vanilla only: a mod built on another mod (an add-on, a patch) shows its records on that mod as
"a record vanilla lacks" — the note says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.core import loc as locmod
from vic3tools.core import script
from vic3tools.graph import objects

FIRST_WINS = {"scripted_effects", "scripted_triggers", "script_values"}
ADDITIVE = {"on_actions", "history", "named_colors"}
INJECTS = {"INJECT", "TRY_INJECT", "INJECT_OR_CREATE"}
CARD_FOLDERS = {t.folder: t for t in objects.TYPES}


@dataclass
class FolderChange:
    folder: str  # under common/
    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    injected: list[str] = field(default_factory=list)
    injected_foreign: list[str] = field(default_factory=list)  # INJECT into a key vanilla lacks: another mod's
    merged: list[str] = field(default_factory=list)  # additive folders: a vanilla key, adds up
    removed: list[str] = field(default_factory=list)  # by a file over vanilla's path
    dead: list[str] = field(default_factory=list)  # first-wins folders: a bare repeat
    files_over: list[str] = field(default_factory=list)


def _common_folders(root: Path) -> list[str]:
    base = root / "common"
    if not base.is_dir():
        return []
    out = set()
    for f in base.rglob("*.txt"):
        rel = f.relative_to(base).as_posix()
        top = rel.split("/")[0]
        if top == "technology":
            top = "/".join(rel.split("/")[:2])
        if "/" not in rel:  # a file right in common/
            continue
        out.add(top)
    return sorted(out)


def _folder_files(root: Path, folder: str) -> list[Path]:
    d = root / "common" / folder
    if not d.is_dir():
        return []
    return sorted(d.rglob("*.txt"), key=lambda p: p.relative_to(root).as_posix().encode())


_CACHE: dict[tuple, object] = {}


def _cached(*key):
    """Memoize by arguments: vanilla's side is the same for every mod."""
    def deco(fn):
        def wrap(*args):
            k = (fn.__name__, *args)
            if k not in _CACHE:
                _CACHE[k] = fn(*args)
            return _CACHE[k]
        return wrap
    return deco


@_cached()
def _keys(root: Path, folder: str) -> dict[str, tuple[str, str]]:
    """key -> (directive of the last definition, file) of a common/ folder."""
    out: dict[str, tuple[str, str]] = {}
    for f in _folder_files(root, folder):
        rel = f.relative_to(root).as_posix()
        for e in script.parse(script.read(f).text)[0]:
            out[e.key] = (e.directive, rel)
    return out


@_cached()
def _defines(root: Path) -> dict[str, str]:
    out = {}
    for f in _folder_files(root, "defines"):
        text = script.read(f).text
        for e in script.parse(text)[0]:
            if not e.is_block:
                continue
            for k, op, s, end, blk, _o, _c in script.block_items(e.body(text)):
                if k and not blk:
                    out[f"{e.key}.{k}"] = e.body(text)[s:end].split(op, 1)[1].strip()
    return out


def common_changes(mod: Path, van: Path) -> list[FolderChange]:
    out = []
    for folder in _common_folders(mod):
        if folder in ("defines", "history"):
            continue
        fc = FolderChange(folder)
        vk = _keys(van, folder)
        mk = _keys(mod, folder)
        van_files = {f.relative_to(van).as_posix() for f in _folder_files(van, folder)}
        over = sorted(f.relative_to(mod).as_posix() for f in _folder_files(mod, folder)
                      if f.relative_to(mod).as_posix() in van_files)
        fc.files_over = over
        for k, (d, _rel) in mk.items():
            if k not in vk:
                (fc.injected_foreign if d in INJECTS - {"INJECT_OR_CREATE"} else fc.added).append(k)
            elif d in INJECTS:
                fc.injected.append(k)
            elif folder.split("/")[0] in ADDITIVE:
                fc.merged.append(k)
            elif folder.split("/")[0] in FIRST_WINS and d not in ("REPLACE_OR_CREATE", "REPLACE", "TRY_REPLACE"):
                fc.dead.append(k)
            else:
                fc.replaced.append(k)
        over_set = set(over)
        fc.removed = sorted(k for k, (_d, rel) in vk.items() if rel in over_set and k not in mk)
        out.append(fc)
    return out


def defines_changes(mod: Path, van: Path) -> list[tuple[str, str | None, str]]:
    md = _defines(mod)
    if not md:
        return []
    vd = _defines(van)
    return [(k, vd.get(k), v) for k, v in sorted(md.items()) if vd.get(k) != v]


def files_over(mod: Path, van: Path, top: str) -> tuple[int, list[str]]:
    d = mod / top
    if not d.is_dir():
        return 0, []
    files = [f.relative_to(mod).as_posix() for f in d.rglob("*") if f.is_file()]
    return len(files), sorted(f for f in files if (van / f).is_file())


@_cached()
def event_ids(root: Path) -> set[str]:
    out = set()
    d = root / "events"
    for f in d.rglob("*.txt") if d.is_dir() else []:
        for e in script.parse(script.read(f).text)[0]:
            if "." in e.key and e.is_block:
                out.add(e.key)
    return out


def loc_overlap(mod: Path, van: Path) -> tuple[int, int, int]:
    """Russian and English keys of the mod: total, those vanilla has outside replace/ (dead), in replace/."""
    total = dead = repl = 0
    for lang in ("english", "russian"):
        vk = objects.read_language(van, lang)
        for f in locmod.language_files(mod / "localization", lang):
            in_replace = "replace" in f.relative_to(mod / "localization").parts
            same_path = (van / f.relative_to(mod)).is_file()
            for e in locmod.read_file(f):
                total += 1
                if in_replace:
                    repl += 1
                elif e.key in vk and not same_path:
                    dead += 1
    return total, dead, repl


# --- field diff for a changed card ----------------------------------------------------------------------------------


def _items(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, _op, s, e, _blk, _o, _c in script.block_items(body):
        out.setdefault(k or "", []).append(script.norm(body[s:e]))
    return out


def _short(s: str, n: int = 80) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def field_diff(van_body: str, mod_body: str, inject: bool) -> list[str]:
    a, b = _items(van_body), _items(mod_body)
    out = []
    for k in b:
        if k not in a:
            out.append(f"- **{k}**: {'добавлено' if not inject else 'добавлено вставкой'}")
        elif a[k] != b[k]:
            if all(" = { " not in x and not x.endswith("}") for x in a[k] + b[k]) and len(a[k]) == len(b[k]) == 1:
                old, new = a[k][0].split("=", 1)[-1].strip(), b[k][0].split("=", 1)[-1].strip()
                out.append(f"- **{k}**: `{_short(old)}` → `{_short(new)}`")
            else:
                out.append(f"- **{k}**: {'изменено' if not inject else 'вставка в блок'}")
    if not inject:
        out += [f"- **{k}**: убрано" for k in a if k not in b]
    return out


# --- the reference note ---------------------------------------------------------------------------------------------


def _q(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def _list(keys: list[str], link=None, limit: int = 400) -> str:
    shown = [link(k) if link else f"`{k}`" for k in sorted(keys)[:limit]]
    more = f" … и ещё {len(keys) - limit}" if len(keys) > limit else ""
    return ", ".join(shown) + more


def reference(src_name: str, label: str, version: str, snap_rel: str, changes: list[FolderChange],
              defines: list, tops: dict[str, tuple[int, list[str]]], events: tuple[int, list[str]],
              locs: tuple[int, int, int], link_card, text_files: int = 1, van_version: str = "") -> str:
    """``version`` — the mod's snapshot, ``van_version`` — vanilla's (the same when not given)."""
    van_version = van_version or version
    own = f" (снимок мода — {version})" if van_version != version else ""
    what = "записи common/ по папкам, defines, файлы поверх ваниль, события, локализация"
    tag = label if objects.TAG_WORD.fullmatch(label) else src_name
    fm = ["---", "type: reference", f"description: {_q(f'Что мод {label} меняет в ванили {van_version}{own}: {what}')}",
          "project: vic3", f"source: {src_name}", f"tags: [{tag}, что-меняет]",
          f"generated: {_q('v3 graph mods')}", *([f"paths: [{snap_rel}/**]"] if text_files else []), "---"]
    out = [f"# Что меняет в ванили — {label}", "",
           f"Снимок `{snap_rel}`{own}, сравнение с ваниль {van_version}. Генерат `v3 graph mods`: руками не править. Правила "
           "слияния — навык `vic3-modding`, «load-and-override»: запись, которой нет у ваниль, мод **добавляет**; "
           "голое тело или `REPLACE:` ключа ваниль **заменяет** запись целиком; `INJECT:` **дополняет**; файл с путём "
           "файла ваниль — файл ваниль не читается, его записи, которых мод не повторил, **удалены**. Сравнение только "
           "с ваниль: запись другого мода (мод — аддон или патч) здесь — «нет у ваниль».", ""]
    if not text_files:
        out += ["**В снимке у мода только картинки** (`.dds`): ни скрипта, ни локализации — менять в ванили ему "
                "нечего, кроме графики; снимок, похоже, неполный.", ""]
    rows = [c for c in changes
            if any((c.added, c.replaced, c.injected, c.injected_foreign, c.merged, c.removed, c.dead))]
    out += ["## Записи common/", "", "| папка | добавляет | заменяет | дополняет | складывает | вставка в чужое "
            "| удаляет файлом | не действует |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in rows:
        out.append(f"| `{c.folder}` | {len(c.added)} | {len(c.replaced)} | {len(c.injected)} | {len(c.merged)} | "
                   f"{len(c.injected_foreign)} | {len(c.removed)} | {len(c.dead)} |")
    if not rows:
        out.append("| — | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")
    out.append("")
    names = {"added": "добавляет", "replaced": "заменяет", "injected": "дополняет",
             "merged": "ключ ваниль в папке, которая складывается (`on_actions` складываются, `effect` — последний "
                       "загруженный)",
             "injected_foreign": "вставка в запись, которой нет у ваниль", "removed": "удаляет заменой файла",
             "dead": "повтор без `REPLACE_OR_CREATE:` — не действует (первое определение остаётся)"}
    for c in rows:
        t = CARD_FOLDERS.get("common/" + c.folder)
        out += [f"### {c.folder}", ""]
        if c.files_over:
            out.append(f"Файлы поверх ваниль: {', '.join(f'`{f}`' for f in c.files_over)}.")
            out.append("")
        for attr, title in names.items():
            keys = getattr(c, attr)
            if not keys:
                continue
            lk = (lambda k, t=t, attr=attr: link_card(t, k, attr)) if t else None
            out.append(f"- **{title}** ({len(keys)}): {_list(keys, lk)}")
        out.append("")
    if defines:
        out += ["## defines", "", "Сливаются по одному define, не блоком.", "", "| define | ваниль | мод |",
                "| --- | --- | --- |"]
        out += [f"| `{k}` | {f'`{_short(v)}`' if v is not None else 'нет'} | `{_short(m)}` |" for k, v, m in defines]
        out.append("")
    out += ["## Вне common/", "", "| папка | файлов | поверх файла ваниль |", "| --- | --- | --- |"]
    for top, (n, over) in tops.items():
        if n:
            out.append(f"| `{top}/` | {n} | {len(over)} |")
    out.append("")
    for top, (_n, over) in tops.items():
        if over:
            out.append(f"- **{top}/ поверх ваниль**: {', '.join(f'`{f}`' for f in over[:200])}"
                       + (f" … и ещё {len(over) - 200}" if len(over) > 200 else ""))
    n_ev, dup = events
    out += ["", f"**События**: {n_ev} id; с id ваниль — {len(dup)}"
            + (f" ({_list(dup, limit=100)}) — игра оставляет одно, не по порядку модов" if dup else "") + ".",
            "", f"**Локализация** (английская и русская): ключей {locs[0]}; в `replace/` — {locs[2]}; есть у ваниль "
            f"вне `replace/` — {locs[1]} (не действуют: побеждает первый файл).", ""]
    return "\n".join(fm + out)


# --- cards ----------------------------------------------------------------------------------------------------------


@dataclass
class ModLayer:
    notes: dict[str, str]
    counts: dict


def build(src_name: str, label: str, version: str, mod_root: Path, van_root: Path, van_layer, snap_rel: str,
          taken: set[str], dst: Path, modifier_links: dict[str, str] | None = None, van_version: str = "") -> ModLayer:
    van_recs, _van_names, van_cnames = van_layer
    mod_recs = objects.all_records(mod_root)
    names = objects.Names([mod_root, van_root])
    cnames = objects.card_names(mod_recs, names, taken)
    linker = objects.Linker([(src_name, mod_recs, cnames), ("vanilla", van_recs, van_cnames)], modifier_links)
    cards = objects.build_cards(src_name, mod_recs, cnames, linker)
    for c in cards:
        r = c.rec
        v = van_recs[r.type.id].get(r.key)
        if v is not None:
            c.diff = field_diff(v.body, r.body, r.directive in INJECTS) or ["- полей не меняет (тело как у ваниль)"]
            c.replaces = f"[[vanilla/{r.type.out}/{van_cnames[(r.type.id, r.key)]}]]"
    notes = objects.notes(cards, src_name, label, version, snap_rel, names, linker, [], dst)
    changes = common_changes(mod_root, van_root)

    def link_card(t, key, attr):
        if attr in ("removed",):
            return linker.link(("vanilla", t.id, key)) if key in van_recs[t.id] else f"`{key}`"
        return linker.link((src_name, t.id, key)) if key in mod_recs[t.id] else f"`{key}`"

    tops = {top: files_over(mod_root, van_root, top)
            for top in ("events", "gui", "gfx", "localization", "map_data", "data_binding", "fonts", "music",
                        "sound", "dlc_metadata")}
    ev = event_ids(mod_root)
    dup = sorted(ev & event_ids(van_root)) if ev else []
    ref = reference(src_name, label, version, snap_rel, changes, defines_changes(mod_root, van_root), tops,
                    (len(ev), dup), loc_overlap(mod_root, van_root), link_card,
                    sum(1 for f in mod_root.rglob("*") if f.is_file() and f.suffix.lower() not in (".dds", ".png")),
                    van_version)
    notes[f"Что меняет в ванили — {file_label(label)}.md"] = ref
    return ModLayer(notes, {"cards": len(cards), "folders": len(changes)})


def file_label(label: str) -> str:
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", label)
