"""More audits of a set: duplicates inside one mod, a mod against vanilla, prestige goods slots, event ids, law groups.

- ``dups`` — inside one mod (a megapack, an add-on): a record defined in two of its files with a replacing directive
  (``INJECT:`` / ``TRY_INJECT:`` add up, they are not duplicates), a loc key twice in one language, an event id twice;
- ``vanilla`` — what a mod does to vanilla, per category: records it creates, overrides whole (bare / ``REPLACE``…),
  injects into; files that override vanilla files by path;
- ``prestige`` — prestige goods per base goods along the load order: only the first three declarations become slots
  (the number is in the exe), the 4th and later are dead, silently;
- ``events`` — event ids defined more than once across the set (the engine does not resolve them by mod order:
  "Duplicated event ID … New Location / Previous Location" in ``debug.log``);
- ``lawgroups`` — the law groups two mods use (``lawgroup_*`` anywhere in ``common/``): a group one uses and the other
  lacks breaks ideologies and laws silently.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from vic3tools.compat.index import ModIndex
from vic3tools.compat.index import build as build_index
from vic3tools.core import script
from vic3tools.core.vfs import Mod, ModSet

REPLACING = {"", "REPLACE", "REPLACE_OR_CREATE", "TRY_REPLACE", "CREATE"}
ADDITIVE = {"common", "common/on_actions", "common/named_colors", "common/modifier_type_definitions"}
ADDITIVE_PREFIXES = ("common/history/",)
_EVENT_ID = re.compile(r"^([A-Za-z0-9_\-]+\.\d+)$")


def _folder(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def duplicates(ix: ModIndex) -> dict[str, list]:
    """Inside one mod: records, loc keys (per language) and event ids defined more than once."""
    recs: dict[tuple[str, str], list] = defaultdict(list)
    locs: dict[tuple[str, str], list] = defaultdict(list)
    for rel, fd in sorted(ix.files.items()):
        cat = _folder(rel)
        for key, directive, line in fd.defs:
            if directive in REPLACING and not (cat in ADDITIVE or cat.startswith(ADDITIVE_PREFIXES)):
                recs[(cat, key)].append(f"{rel}:{line}")
        for key, line in fd.loc:
            lang = rel.split("/")[1] if rel.count("/") >= 2 else ""
            locs[(lang, key)].append(f"{rel}:{line}")
    events = {k: v for k, v in recs.items() if k[0].startswith("events") and _EVENT_ID.match(k[1])}
    return {"records": [(c, k, w) for (c, k), w in recs.items() if len(w) > 1 and (c, k) not in events],
            "loc": [(lang, k, w) for (lang, k), w in locs.items() if len(w) > 1],
            "events": [(k, w) for (_c, k), w in events.items() if len(w) > 1]}


def against_vanilla(van: ModIndex, ix: ModIndex) -> tuple[dict[str, Counter], list[str]]:
    """Per category: created / overridden / injected / other records; and the mod's files overriding vanilla paths."""
    vkeys: dict[str, set[str]] = defaultdict(set)
    for rel, fd in van.files.items():
        for key, _d, _l in fd.defs:
            vkeys[_folder(rel)].add(key)
    out: dict[str, Counter] = defaultdict(Counter)
    for rel, fd in ix.files.items():
        cat = _folder(rel)
        for key, directive, _line in fd.defs:
            in_van = key in vkeys.get(cat, ())
            if directive in ("INJECT", "TRY_INJECT", "INJECT_OR_CREATE"):
                out[cat]["injects" if in_van else "injects into a mod's"] += 1
            elif in_van:
                out[cat]["overrides"] += 1
            else:
                out[cat]["creates"] += 1
    paths = sorted(rel for rel in ix.files if rel in van.files)
    return out, paths


def prestige(ms: ModSet) -> dict[str, list[tuple[str, str, str]]]:
    """Base goods → [(prestige goods, mod, file)] in load order (a later bare repeat of a key replaces it in place)."""
    order: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    seen: dict[str, str] = {}
    for mod in ms.mods:
        folder = mod.path / "common" / "prestige_goods"
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.txt"), key=lambda f: f.name.encode()):
            text = script.read(p).text
            for e in script.parse(text)[0]:
                if not e.is_block:
                    continue
                m = re.search(r"\bbase_good\s*=\s*(\w+)", e.body(text))
                if not m:
                    continue
                base = m.group(1)
                if e.key in seen:  # redefined later: keeps its slot, the definition is the later mod's
                    slots = order[seen[e.key]]
                    for n, x in enumerate(slots):
                        if x[0] == e.key:
                            slots[n] = (e.key, mod.name, p.name)
                    continue
                seen[e.key] = base
                order[base].append((e.key, mod.name, p.name))
    return order


def event_ids(ms: ModSet) -> dict[str, list[str]]:
    """Event ids defined more than once across the set: id → [mod: file:line]."""
    where: dict[str, list[str]] = defaultdict(list)
    for mod in ms.mods:
        ix = build_index(mod)
        for rel, fd in ix.files.items():
            if not rel.startswith("events/"):
                continue
            for key, _d, line in fd.defs:
                if _EVENT_ID.match(key):
                    where[key].append(f"{mod.name}: {rel}:{line}")
    return {k: v for k, v in where.items() if len(v) > 1}


_LAWGROUP = re.compile(r"\blawgroup_[A-Za-z0-9_]+\b")


def lawgroups(mod: Mod) -> dict[str, list[str]]:
    """Law groups a mod mentions in ``common/`` → the files."""
    out: dict[str, list[str]] = defaultdict(list)
    common = mod.path / "common"
    if not common.is_dir():
        return out
    for p in sorted(common.rglob("*.txt")):
        text = script.read(p).text
        text = re.sub(r"#[^\n]*", "", text)
        for g in set(_LAWGROUP.findall(text)):
            out[g].append(p.relative_to(mod.path).as_posix())
    return out
