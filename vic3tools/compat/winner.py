"""Who wins: every definition of a record, a localization key or a GUI type across the set, and what the game uses.

The load-order rules are in ``vic3tools.core.vfs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vic3tools.compat.index import ModIndex
from vic3tools.core.vfs import FIRST_WINS_CATEGORIES, ModSet, VFile


@dataclass
class Def:
    file: VFile
    line: int
    directive: str = ""
    note: str = ""  # what this definition does in the chain
    replaced_file: bool = False  # its file is replaced by a later mod's file with the same path: never loads


@dataclass
class Verdict:
    what: str  # "common/buildings building_railway", "loc KEY", "gui TYPE"
    defs: list[Def] = field(default_factory=list)  # in load order
    winner: Def | None = None
    applied: list[Def] = field(default_factory=list)  # injects applied on top of the winner
    notes: list[str] = field(default_factory=list)


def _ordered(ms: ModSet, idx: list[ModIndex], folder: str, kind: str) -> tuple[list[VFile], list[VFile]]:
    """Files of ``folder`` that load (load order) and those replaced by path, from the indexes."""
    by_rel: dict[str, list[VFile]] = {}
    folder = folder.strip("/")
    for i, ix in enumerate(idx):
        for rel in ix.files:
            # records: the folder itself (its subfolders are other categories); loc and gui: the whole tree
            if kind == "db":
                ok = rel.endswith(".txt") and rel.rsplit("/", 1)[0] == folder
            else:
                ok = rel.startswith(folder + "/")
            if ok:
                by_rel.setdefault(rel, []).append(VFile(ix.mod, rel, i))
    live, dead = [], []
    for chain in by_rel.values():
        live.append(chain[-1])
        dead += chain[:-1]
    live.sort(key=lambda f: (f.order, f.rel.encode()))
    return live, dead


def record(ms: ModSet, idx: list[ModIndex], folder: str, key: str) -> Verdict:
    """A database record ``key`` in ``folder`` (e.g. ``common/buildings``)."""
    folder = folder.strip("/")
    v = Verdict(f"{folder} {key}")
    live, dead = _ordered(ms, idx, folder, "db")
    for f in dead:
        for k, d, line in idx[f.order].files[f.rel].defs:
            if k == key:
                v.defs.append(Def(f, line, d, "file replaced by a later mod's file with the same path", True))
    first_wins = folder in FIRST_WINS_CATEGORIES
    for f in live:
        for k, d, line in idx[f.order].files[f.rel].defs:
            if k == key:
                x = Def(f, line, d)
                v.defs.append(x)
                _apply(v, x, first_wins)
    return v


def _where(d: Def) -> str:
    return f"{d.file.mod.name} {d.file.rel}:{d.line}"


def _reset(v: Verdict, x: Def, note: str) -> None:
    """``x`` becomes the record; the previous body and its injects are lost."""
    for old in ([v.winner] if v.winner else []) + v.applied:
        old.note += f"; lost to {_where(x)}"
    x.note = note
    v.winner, v.applied = x, []


def _apply(v: Verdict, x: Def, first_wins: bool) -> None:
    d, exists = x.directive, v.winner is not None
    if d == "" and first_wins and exists:
        x.note = "ignored: here a bare repeat does not override (REPLACE_OR_CREATE: is needed)"
    elif d in ("", "REPLACE_OR_CREATE"):
        _reset(v, x, "replaces the record" if exists else "creates the record")
    elif d in ("REPLACE", "TRY_REPLACE"):
        if exists:
            _reset(v, x, "replaces the record whole")
        else:
            x.note = "nothing to replace: " + ("skipped" if d == "TRY_REPLACE" else "load error")
    elif d in ("INJECT", "TRY_INJECT", "INJECT_OR_CREATE"):
        if exists:
            x.note = "merged into the record"
            v.applied.append(x)
        elif d == "INJECT_OR_CREATE":
            _reset(v, x, "creates the record")
        else:
            x.note = "nothing to inject into: " + ("skipped" if d == "TRY_INJECT" else "load error")
    elif d == "CREATE":
        if exists:
            x.note = "already exists: load error, ignored"
        else:
            _reset(v, x, "creates the record")


def loc_key(ms: ModSet, idx: list[ModIndex], key: str, lang: str = "english") -> Verdict:
    """A localization key in one language: the first definition wins; ``replace/`` overrides the rest."""
    v = Verdict(f"loc {key} ({lang})")
    live, dead = _ordered(ms, idx, f"localization/{lang}", "loc")
    for f in dead:
        for k, line in idx[f.order].files[f.rel].loc:
            if k == key:
                v.defs.append(Def(f, line, note="file replaced by a later mod's file with the same path",
                                  replaced_file=True))
    normal, replace = [], []
    for f in live:
        for k, line in idx[f.order].files[f.rel].loc:
            if k == key:
                d = Def(f, line)
                v.defs.append(d)
                (replace if "/replace/" in f.rel else normal).append(d)
    if replace:
        v.winner = replace[0]
        replace[0].note = "wins: replace/ overrides"
        for d in replace[1:]:
            d.note = "another replace/ definition"
        if len(replace) > 1:
            v.notes.append("several replace/ definitions: which one the game takes was not verified")
        for d in normal:
            d.note = "overridden by replace/"
    elif normal:
        v.winner = normal[0]
        normal[0].note = "wins: first definition"
        for d in normal[1:]:
            d.note = "never shows: defined earlier" + (" (move it to replace/)" if not d.replaced_file else "")
    if len({d.file.order for d in normal}) > 1:
        v.notes.append("localization order between mods is taken as the mod order (not verified in game)")
    return v


def gui_type(ms: ModSet, idx: list[ModIndex], name: str) -> Verdict:
    """A GUI type: the first registration wins, files ordered by file name across all mods, mod order not counted."""
    v = Verdict(f"gui {name}")
    live, dead = _ordered(ms, idx, "gui", "gui")
    for f in dead:
        for k, line in idx[f.order].files[f.rel].gui:
            if k == name:
                v.defs.append(Def(f, line, note="file replaced by a later mod's file with the same path",
                                  replaced_file=True))
    live.sort(key=lambda f: (f.rel.rsplit("/", 1)[-1].encode(), f.rel.count("/"), f.order))
    found = []
    for f in live:
        for k, line in idx[f.order].files[f.rel].gui:
            if k == name:
                found.append(Def(f, line))
    v.defs += found
    if found:
        v.winner = found[0]
        found[0].note = "wins: first registration"
        for d in found[1:]:
            d.note = "ignored: the type is registered earlier (a run's gui.log would say \"already registered\")"
    return v
