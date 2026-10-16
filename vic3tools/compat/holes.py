"""What a pairwise comparison of mods never shows (``v3 audit holes``).

``v3 conflicts`` / ``v3 matrix`` compare keys that **both** mods define. Four classes fall out of that, each of which
cost a real loss in a set:

1. **new content** — a building, goods, law… defined by one mod only can never be in an intersection; other mods'
   hand-written lists by name (company ``building_types``, a mod's own registries, AI weights) do not know it.
   Listed per mod with who else mentions the name at all ("nobody" — a hole);
2. **eaten method groups** — the last replacing body of a building drops ``production_method_groups`` that earlier
   mods put in (an ``INJECT:`` after it restores them);
3. **eaten company buildings** — the same for ``building_types`` / ``extension_building_types`` of companies;
4. **builds against what loads after them** — megapacks and add-ons are not blocks of the set: their keys that a
   later mod replaces (not ``INJECT:``) in non-additive categories.

And, with ``--require-pmg``: **private buildings outside a mod's economy** — the final body of every building with
``ownership_type = self`` that lacks a required method group (E&F hooks its finance into buildings by two lists of
names: ``--require-pmg pmg_market_liquidity --require-pmg 'pmg_private_ownership_*'``).

The order is the set's load order (a set file's ``load_order``); inside a mod, file names by bytes.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

from vic3tools.compat.index import ModIndex
from vic3tools.compat.index import build as build_index
from vic3tools.core import script
from vic3tools.core.vfs import ModSet
from vic3tools.index import db

CONTENT_CATEGORIES = ["common/buildings", "common/goods", "common/building_groups", "common/company_types",
                      "common/laws", "common/law_groups", "common/institutions", "common/technology",
                      "common/pop_types", "common/subject_types", "common/diplomatic_actions", "common/decrees",
                      "common/power_bloc_principles", "common/company_charter_types", "common/state_traits"]
ADDITIVE = {"common", "common/on_actions", "common/named_colors", "common/modifier_type_definitions"}
ADDITIVE_PREFIXES = ("common/history/",)
REPLACING = {"", "REPLACE", "REPLACE_OR_CREATE", "TRY_REPLACE"}


@dataclass
class Body:
    mod: int  # index of the mod in the set
    label: str
    directive: str
    file: str
    pmg: list[str] = field(default_factory=list)
    own: str | None = None
    types: list[str] = field(default_factory=list)  # a company's building_types + extension_building_types

    @property
    def order(self) -> tuple[int, bytes]:
        return self.mod, self.file.encode()


@dataclass
class Source:
    label: str
    defs: dict[str, dict[str, list[tuple[str, str]]]]  # category → key → [(directive, file)]
    names: set[str]  # every name the mod mentions
    buildings: dict[str, list[Body]]
    companies: dict[str, list[Body]]


def _inner(body: str, tag: str) -> list[str]:
    m = re.search(tag + r"\s*=\s*\{(.*?)\}", body, re.S)
    return re.findall(r"[A-Za-z0-9_]+", m.group(1)) if m else []


def _bodies(ms: ModSet, i: int, ix: ModIndex, folder: str) -> dict[str, list[Body]]:
    out: dict[str, list[Body]] = {}
    mod = ms.mods[i]
    for rel in sorted(ix.files, key=str.encode):
        if rel.rsplit("/", 1)[0] != folder or not rel.endswith(".txt"):
            continue
        text = script.read_text(mod.path / rel) if (mod.path / rel).is_file() else ""
        for e in script.parse(text)[0]:
            body = e.body(text)
            b = Body(i, mod.name, e.directive, rel)
            if folder == "common/buildings":
                b.pmg = _inner(body, "production_method_groups")
                own = re.search(r"ownership_type\s*=\s*(\w+)", body)
                b.own = own.group(1) if own else None
            else:
                b.types = _inner(body, "building_types") + _inner(body, "extension_building_types")
            out.setdefault(e.key, []).append(b)
    return out


def sources(ms: ModSet) -> list[Source]:
    """Every mod of the set, vanilla first (its bodies are what mods replace), indexed."""
    out = []
    for i, mod in enumerate(ms.mods):
        ix = build_index(mod)
        defs: dict[str, dict[str, list]] = {}
        for rel, fd in ix.files.items():
            cat = rel.rsplit("/", 1)[0]
            for key, directive, _line in fd.defs:
                defs.setdefault(cat, {}).setdefault(key, []).append((directive, rel))
        con = db.open_index(mod)
        try:
            names = {n for (n,) in con.execute("SELECT DISTINCT n.name FROM refs r JOIN names n ON n.id = r.name_id")}
        finally:
            con.close()
        out.append(Source(mod.name, defs, names, _bodies(ms, i, ix, "common/buildings"),
                          _bodies(ms, i, ix, "common/company_types")))
    return out


def new_content(srcs: list[Source], only: str | None = None) -> dict[str, list[tuple[str, str, str, list[str]]]]:
    """Per mod: (category, key, directive, mods that mention it) of keys no other mod of the chain defines."""
    out: dict[str, list] = {}
    for i, s in enumerate(srcs):
        if (only and s.label != only) or i == 0:  # vanilla's own keys are not new content
            continue
        rows = []
        for cat in CONTENT_CATEGORIES:
            for key, occ in sorted(s.defs.get(cat, {}).items()):
                if all(d not in REPLACING for d, _f in occ):
                    continue  # TRY_* / INJECT only: the record may never exist
                if any(key in o.defs.get(cat, {}) for j, o in enumerate(srcs) if j != i):
                    continue
                rows.append((cat, key, occ[0][0], [o.label for j, o in enumerate(srcs) if j != i and key in o.names]))
        if rows:
            out[s.label] = rows
    return out


def _eaten(entries: list[Body], items) -> tuple[Body, dict[str, set[str]]] | None:
    reps = [e for e in entries if e.directive in REPLACING and items(e)]
    if not reps:
        return None
    last = max(reps, key=lambda e: e.order)
    have = set(items(last))
    for e in entries:
        if e.order > last.order:  # an INJECT: after the last body restores what it names
            have |= set(items(e))
    lost: dict[str, set[str]] = {}
    for e in entries:
        if e.order < last.order:
            for x in items(e):
                if x not in have:
                    lost.setdefault(x, set()).add(e.label)
    return (last, lost) if lost else None


def eaten(srcs: list[Source], what: str) -> list[tuple[str, Body, dict[str, set[str]]]]:
    """Buildings (``pmg``) or companies (``companies``) whose final body loses earlier mods' entries."""
    allb: dict[str, list[Body]] = {}
    for s in srcs:
        for key, entries in (s.buildings if what == "pmg" else s.companies).items():
            allb.setdefault(key, []).extend(entries)
    out = []
    for key, entries in sorted(allb.items()):
        r = _eaten(entries, (lambda e: e.pmg) if what == "pmg" else (lambda e: e.types))
        if r:
            out.append((key, r[0], r[1]))
    return out


def builds_vs_later(srcs: list[Source], builds: set[str]) -> dict[str, dict[str, dict[str, list[str]]]]:
    """For each build: later mods' replacing definitions of its keys, by category."""
    out: dict[str, dict[str, dict[str, list[str]]]] = {}
    for i, s in enumerate(srcs):
        if s.label not in builds:
            continue
        per: dict[str, dict[str, list[str]]] = {}
        for o in srcs[i + 1:]:
            hits: dict[str, list[str]] = {}
            for cat, keys in s.defs.items():
                if cat in ADDITIVE or cat.startswith(ADDITIVE_PREFIXES):
                    continue
                for key in keys:
                    occ = o.defs.get(cat, {}).get(key)
                    if occ and any(d in REPLACING for d, _f in occ):
                        hits.setdefault(cat, []).append(key)
            if hits:
                per[o.label] = hits
        out[s.label] = per
    return out


def outside_economy(srcs: list[Source], required: list[str]) -> list[tuple[str, str, list[str], list[str]]]:
    """(the mod of the final body, building, required groups it lacks, companies that may own it) for private
    buildings (``ownership_type = self``) of the final bodies."""
    allb: dict[str, list[Body]] = {}
    owners: dict[str, set[str]] = {}
    for s in srcs:
        for key, entries in s.buildings.items():
            allb.setdefault(key, []).extend(entries)
        for entries in s.companies.values():
            for e in entries:
                for b in e.types:
                    owners.setdefault(b, set()).add(e.label)
    rows = []
    for key, entries in sorted(allb.items()):
        reps = [e for e in entries if e.directive in REPLACING]
        if not reps:
            continue
        last = max(reps, key=lambda e: e.order)
        pmg, own = set(last.pmg), last.own
        for e in entries:
            if e.order > last.order:
                pmg |= set(e.pmg)
                own = e.own or own
        if own != "self":
            continue
        missing = [g for g in required if not any(fnmatch.fnmatch(p, g) for p in pmg)]
        if missing:
            rows.append((last.label, key, missing, sorted(owners.get(key, ()))))
    return rows
