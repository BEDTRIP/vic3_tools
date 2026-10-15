"""One runner for every check of a mod: tiger's reports and our rules, minus what is suppressed.

Two ways to silence a report, both kept in the mod's root (so every session and machine shares them):

- ``v3-lint-baseline.json`` — reports accepted as known (``v3 lint --baseline`` writes every current one). A report
  is matched by its fingerprint — source, key, file, message and the text of its line — not by line number, so edits
  elsewhere in the file do not bring it back; each fingerprint keeps a count (scope reports, which tiger deduces
  differently from run to run, match by file and line text only, with no count);
- ``[[suppress]]`` in ``v3-lint.toml`` — rules by hand: every field given must match (``key`` and ``file`` are
  globs, ``message`` and ``text`` substrings), with ``why``::

    [[suppress]]
    key = "missing-item"
    file = "common/scripted_effects/ld_listing_switch.txt"
    why = "buildings of other mods, checked with has_building_type at run time"

The same file holds project rules, ``[[rule]]`` with ``name``, ``files`` (globs), ``pattern`` (a regex),
``message`` and ``severity``.
"""

from __future__ import annotations

import datetime
import fnmatch
import json
from collections import Counter
from dataclasses import dataclass, field

from vic3tools.compat import audits
from vic3tools.compat import index as cindex
from vic3tools.core.vfs import Mod
from vic3tools.index.query import SetIndex
from vic3tools.lint import rules, tiger
from vic3tools.lint.tiger import Report

SEVERITY = {"error": 0, "warning": 1, "untidy": 2, "tips": 3}
BASELINE = "v3-lint-baseline.json"
# tiger deduces the scope type of a variable used in two scopes differently from run to run (one run reports the
# country uses, the next the company ones): these keys are matched by file and line text only, without counts
FLAKY = {"scopes", "strict-scopes", "modifiers"}


@dataclass
class Result:
    shown: list[Report] = field(default_factory=list)
    baselined: list[Report] = field(default_factory=list)
    suppressed: list[tuple[Report, str]] = field(default_factory=list)  # with the rule's why
    notes: list[str] = field(default_factory=list)


def fingerprint(r: Report) -> str:
    msg = "" if r.key in FLAKY else r.message  # the place is enough: the message names the scopes guessed
    return "|".join((r.source, r.key, r.path, msg, r.text))


def collect(si: SetIndex, mod_i: int, use_tiger: bool = True, refresh: bool = False,
            only: tuple[str, ...] = rules.RULES, langs: tuple[str, ...] = ("english", "russian"),
            files: set[str] | None = None, lines: dict[str, set[int]] | None = None) -> tuple[list[Report], list[str]]:
    """Every report on the mod (``files``: only these mod-relative paths)."""
    ms = si.ms
    mod = ms.mods[mod_i]
    out: list[Report] = []
    notes: list[str] = []
    project, _sup = rules.project_rules(mod)
    if use_tiger:
        try:
            out += tiger.run(ms, mod, refresh)
        except (FileNotFoundError, RuntimeError, OSError) as e:
            notes.append(f"tiger skipped: {e}")
    names = files if files is not None else None
    for rel in sorted(names) if names is not None else rules.mod_files(mod, (".txt", ".gui", ".yml")):
        out += [r for r in rules.file_rules(mod, rel, project) if r.key.split(":")[0] in only or r.key.startswith(
            "rule:")]
    if "gui-type-ignored" in only:
        out += rules.gui_types_ignored(si, mod_i, files)
    if "text-fit" in only:
        gui = sorted(f for f in names if f.endswith(".gui")) if names is not None else None
        out += rules.text_fit(si, mod_i, list(langs), gui, lines)
    if {"replace-fields", "loc-dead"} & set(only) and files is None:
        idx = [cindex.build(m) for m in ms.mods]
        if "replace-fields" in only:
            for x in audits.replace(ms, idx, mod_i, {}):
                out.append(Report("warning", "strong", "replace-fields", f"REPLACE:{x.key} omits "
                                  f"{', '.join(x.detail)} of {x.against}: they are lost", x.file.rel, x.line, 0, "",
                                  source="v3"))
        if "loc-dead" in only:
            for x in audits.loc_dead(ms, idx, mod_i, langs):
                out.append(Report("warning", "strong", "loc-dead", f"{x.key} never shows: defined earlier at "
                                  f"{' '.join(x.detail)} (move it to replace/)", x.file.rel, x.line, 0, x.key,
                                  source="v3"))
    if files is not None:
        out = [r for r in out if r.path in files]
    return out, notes


def load_baseline(mod: Mod) -> Counter:
    p = mod.path / BASELINE
    if not p.is_file():
        return Counter()
    return Counter(json.loads(p.read_text(encoding="utf-8")).get("counts", {}))


def write_baseline(mod: Mod, reports: list[Report], *more: list[Report]) -> int:
    """Accept ``reports`` as known; ``more`` — the same check run again (tiger varies): each count is the largest."""
    counts = Counter(fingerprint(r) for r in reports)
    for other in more:
        counts |= Counter(fingerprint(r) for r in other)
    data = {"about": "reports of `v3 lint` accepted as known; `v3 lint --baseline` rewrites it",
            "made": datetime.date.today().isoformat(), "counts": dict(sorted(counts.items()))}
    (mod.path / BASELINE).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(reports)


def _matches(r: Report, s: dict) -> bool:
    if "key" in s and not fnmatch.fnmatch(r.key, s["key"]):
        return False
    if "file" in s and not fnmatch.fnmatch(r.path, s["file"]):
        return False
    if "message" in s and s["message"] not in r.message:
        return False
    return not ("text" in s and s["text"] not in r.text)


def split(mod: Mod, reports: list[Report], use_baseline: bool = True) -> Result:
    res = Result()
    _rules, sup = rules.project_rules(mod)
    left = load_baseline(mod) if use_baseline else Counter()
    for r in sorted(reports, key=lambda r: (r.path, r.line, SEVERITY.get(r.severity, 9), r.key)):
        hit = next((s for s in sup if _matches(r, s)), None)
        if hit is not None:
            res.suppressed.append((r, hit.get("why", "")))
            continue
        fp = fingerprint(r)
        if left[fp] > 0:
            if r.key not in FLAKY:
                left[fp] -= 1
            res.baselined.append(r)
            continue
        res.shown.append(r)
    return res
