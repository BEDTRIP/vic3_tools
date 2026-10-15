"""Where mods of a set collide: shared record keys, file paths, localization keys, GUI types, event ids.

A shared key is only a place to look, not a verdict: ``v3 winner`` tells what the game does with it. Folders whose
records the game adds up (on_actions, history, named colors…) and container keys are left out — they are never
conflicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.compat.index import ModIndex, kind_of
from vic3tools.core.vfs import Mod

ADDITIVE_FOLDERS = {
    "common",
    "common/on_actions",
    "common/named_colors",
    "common/modifier_type_definitions",
    "music/main_themes",
    "tools/scripted_tests",
    "gfx/map/map_object_data",
}
ADDITIVE_PREFIXES = ("common/history/",)
NOISE_KEYS = {
    "namespace", "group", "object", "game_object_locator", "colors", "tests", "last_date", "BUILDINGS", "GLOBAL",
    "POPS", "STATES", "COUNTRIES", "CHARACTERS", "DIPLOMACY", "DIPLOMATIC_PLAYS", "MILITARY_DEPLOYMENTS",
    "MILITARY_FORMATIONS", "GOVERNMENTS", "TRADE_ROUTES", "LOBBIES", "TREATIES", "POLITICAL_MOVEMENTS", "POWER_BLOCS",
    "SPLINE_NETWORK", "POPULATION",
}


def is_additive(folder: str) -> bool:
    return folder in ADDITIVE_FOLDERS or folder.startswith(ADDITIVE_PREFIXES)


@dataclass
class Side:
    """What a mod or a group of mods defines: item → [(mod name, rel path, line)]."""

    keys: dict[str, list] = field(default_factory=dict)  # "folder|key"
    files: dict[str, list] = field(default_factory=dict)  # rel path of a script file
    loc: dict[str, list] = field(default_factory=dict)  # loc key
    gui: dict[str, list] = field(default_factory=dict)  # gui type


def side(indexes: list[ModIndex]) -> Side:
    s = Side()
    for ix in indexes:
        name = ix.mod.name
        for rel, fd in ix.files.items():
            if kind_of(rel):
                s.files.setdefault(rel, []).append((name, rel, 0))
            folder = ix.folder_of(rel)
            if fd.defs and not is_additive(folder):
                for key, _d, line in fd.defs:
                    if key not in NOISE_KEYS and not key.startswith("@"):  # @x = file-local constants
                        s.keys.setdefault(f"{folder}|{key}", []).append((name, rel, line))
            for key, line in fd.loc:
                s.loc.setdefault(key, []).append((name, rel, line))
            for t, line in fd.gui:
                s.gui.setdefault(t, []).append((name, rel, line))
    return s


@dataclass
class Overlap:
    keys: list[str]
    files: list[str]
    loc: list[str]
    gui: list[str]

    @property
    def total(self) -> int:
        return len(self.keys) + len(self.files) + len(self.loc) + len(self.gui)


def overlap(a: Side, b: Side) -> Overlap:
    return Overlap(sorted(a.keys.keys() & b.keys.keys()), sorted(a.files.keys() & b.files.keys()),
                   sorted(a.loc.keys() & b.loc.keys()), sorted(a.gui.keys() & b.gui.keys()))


def load_groups(path: Path) -> tuple[list[str], dict[str, list[Path]]]:
    """A groups file: ``{"blocks": {name: [mod folder, …]}, "order": [name, …]}``; paths relative to the file.

    Groups whose name starts with ``_`` (vanilla, frameworks) are not columns of the matrix.
    """
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    base = path.parent
    groups = {name: [p if Path(p).is_absolute() else (base / p).resolve() for p in map(Path, paths)]
              for name, paths in cfg["blocks"].items()}
    order = cfg.get("order") or [g for g in groups if not g.startswith("_")]
    return order, groups


def group_mods(paths: list[Path]) -> list[Mod]:
    return [Mod(p.name, p, "mod") for p in paths]
