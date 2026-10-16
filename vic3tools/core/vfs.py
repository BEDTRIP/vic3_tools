"""The game's virtual file system: which mods load, in what order, and which file or definition wins.

The mod set is the launcher's playset (``launcher-v2.sqlite``, read-only) with vanilla first, or an explicit list of
mod folders. The rules, as observed in the game (1.13):

- **Mod order rules, file names decide only inside one mod.** Files of a folder load mod by mod; inside a mod, by the
  bytes of the relative path (``_`` before letters, capitals before lower case, ``~`` last).
- **A file with the same relative path replaces the earlier mod's file whole** (the earlier one never loads).
- **Database records** (``common/…``): a later bare definition replaces the record (and every ``INJECT:`` before it);
  ``REPLACE:`` replaces it whole; ``INJECT:`` merges sub-blocks into it; ``TRY_``/``_OR_CREATE`` variants as named.
  Exception — ``scripted_effects``, ``scripted_triggers``, ``script_values``: a bare repeat does not override, the
  first definition stays (``REPLACE_OR_CREATE:`` is needed).
- **Localization:** the first file that defines a key wins, whatever the mod order; a key in a ``replace/`` folder
  overrides keys defined outside it.
- **GUI types:** the first registration wins, files ordered by file name (ASCII) across all mods at once, mod order
  not counted; with equal names, the file closer to the root of ``gui/`` first.
- **The engine's own folders** next to ``game/`` — ``clausewitz/`` and then ``jomini/`` — load before vanilla, as
  layers under it (their GUI types, localization, fonts, textures; ``clausewitz/gui/profiler.gui`` is the script
  profiler's window). The index reads them (``engine_mods``); a mod set stays "vanilla first".
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.core import paths

FIRST_WINS_CATEGORIES = ("common/scripted_effects", "common/scripted_triggers", "common/script_values")
# Top-level folders the game reads from a mod (as in vanilla's game/); anything else (docs, _archive/…) never loads.
LOADED_FOLDERS = {"common", "content_source", "data_binding", "dlc", "dlc_metadata", "events", "fonts", "gfx", "gui",
                  "input_profile", "interface", "localization", "map_data", "music", "notifications", "sound",
                  "soundtrack", "tools"}


def loads(rel: str) -> bool:
    """Whether the game reads a mod file at all (by its top-level folder)."""
    return rel.split("/", 1)[0] in LOADED_FOLDERS


@dataclass(frozen=True)
class Mod:
    name: str
    path: Path
    kind: str = "mod"  # "engine", "vanilla", "workshop", "local", "mod"

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class VFile:
    mod: Mod
    rel: str  # relative to the mod root, forward slashes
    order: int  # index of the mod in the set

    @property
    def full(self) -> Path:
        return self.mod.path / self.rel


@dataclass
class ModSet:
    mods: list[Mod]  # load order, vanilla first
    source: str = ""  # where the set came from, for output
    overridden: dict[str, list[VFile]] = field(default_factory=dict, repr=False)

    # --- building the set ------------------------------------------------------------------------------------------

    @classmethod
    def from_playset(cls, name: str | None = None, cfg: paths.Config | None = None) -> ModSet:
        """Vanilla plus the enabled mods of a launcher playset (the active one by default), in launcher order."""
        cfg = cfg if cfg is not None else paths.load_config()
        roots = paths.resolve_roots(cfg)
        name = name or cfg.values.get("playset")
        mods = [vanilla_mod(roots)]
        title, rows = playset_mods(launcher_db(roots), name)
        overrides = cfg.values.get("mod_paths", {})
        for display, dir_path, steam_id in rows:
            p = Path(overrides.get(display, dir_path))
            kind = "workshop" if steam_id and display not in overrides else "local"
            mods.append(Mod(display, p, kind))
        return cls(mods, f"playset {title}")

    @classmethod
    def from_dirs(cls, dirs: list[Path], cfg: paths.Config | None = None, vanilla: bool = True) -> ModSet:
        """Vanilla (unless told otherwise) plus the given mod folders, in the given order."""
        mods = []
        if vanilla:
            mods.append(vanilla_mod(paths.resolve_roots(cfg if cfg is not None else paths.load_config())))
        for d in dirs:
            mods.append(Mod(mod_display_name(Path(d)), Path(d), "mod"))
        return cls(mods, "folders")

    @classmethod
    def from_set_file(cls, path: Path, cfg: paths.Config | None = None) -> ModSet:
        """A set file (JSON): ``load_order`` — mod folders in load order, ``labels`` — folder → name; paths
        relative to the file. Vanilla (or a copy of it, recognised by ``checksum_manifest.txt``) may come first;
        otherwise the installed game is put in front."""
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        base = Path(path).resolve().parent
        labels = data.get("labels", {})
        mods = []
        for p in data["load_order"]:
            full = Path(p) if Path(p).is_absolute() else (base / p).resolve()
            kind = "vanilla" if not mods and (full / "checksum_manifest.txt").is_file() else "mod"
            mods.append(Mod(labels.get(p) or ("vanilla" if kind == "vanilla" else full.name), full, kind))
        if not mods or mods[0].kind != "vanilla":
            mods.insert(0, vanilla_mod(paths.resolve_roots(cfg if cfg is not None else paths.load_config())))
        return cls(mods, f"set file {path}")

    def find(self, name_or_path: str) -> Mod:
        """A mod of the set by name (exact, then unique substring, case-insensitive) or by folder."""
        for m in self.mods:
            if m.name == name_or_path:
                return m
        p = Path(name_or_path)
        if p.exists():
            for m in self.mods:
                if _same(m.path, p):
                    return m
            return Mod(mod_display_name(p), p, "mod")
        hits = [m for m in self.mods if name_or_path.casefold() in m.name.casefold()]
        if len(hits) == 1:
            return hits[0]
        raise KeyError(f"no single mod matches {name_or_path!r} in {self.source}: "
                       + (", ".join(m.name for m in hits) if hits else "none"))

    # --- files -----------------------------------------------------------------------------------------------------

    def files(self, folder: str, exts: tuple[str, ...] = (".txt",)) -> list[VFile]:
        """Files that load from ``folder`` (e.g. ``common/buildings``), in load order; files replaced by a later
        mod's file with the same path are left out (see ``replaced``)."""
        folder = folder.strip("/")
        by_rel: dict[str, list[VFile]] = {}
        for i, m in enumerate(self.mods):
            base = m.path / folder
            if not base.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in filenames:
                    if fn.lower().endswith(exts):
                        rel = (Path(dirpath) / fn).relative_to(m.path).as_posix()
                        by_rel.setdefault(rel, []).append(VFile(m, rel, i))
        out = []
        for rel, chain in by_rel.items():
            out.append(chain[-1])
            if len(chain) > 1:
                self.overridden[rel] = chain[:-1]
        out.sort(key=lambda f: (f.order, f.rel.encode()))
        return out

    def replaced(self, rel: str) -> list[VFile]:
        """Earlier copies of ``rel`` that a later mod's file replaced (filled by ``files``)."""
        return self.overridden.get(rel, [])

    def file_chain(self, rel: str) -> list[VFile]:
        """Every mod's copy of one relative path, in load order; the last one is what loads."""
        return [VFile(m, rel, i) for i, m in enumerate(self.mods) if (m.path / rel).is_file()]


ENGINE_FOLDERS = ("clausewitz", "jomini")  # in load order, both before game/


def engine_mods(vanilla: Mod) -> list[Mod]:
    """The engine's folders under vanilla (``clausewitz/``, ``jomini/`` next to ``game/``) that exist."""
    if vanilla.kind != "vanilla":
        return []
    root = vanilla.path.parent
    return [Mod(name, root / name, "engine") for name in ENGINE_FOLDERS if (root / name).is_dir()]


def vanilla_mod(roots: dict[str, paths.Root]) -> Mod:
    game = roots["game"]
    if not game.ok:
        raise FileNotFoundError(f"the game was not found ({game.source}); see `v3 where`")
    return Mod("vanilla", game.path / "game", "vanilla")


def launcher_db(roots: dict[str, paths.Root]) -> Path:
    docs = roots["documents"]
    if not docs.ok:
        raise FileNotFoundError(f"the game's documents folder was not found ({docs.source}); see `v3 where`")
    return docs.path / "launcher-v2.sqlite"


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)


def list_playsets(db: Path) -> list[tuple[str, bool]]:
    with _connect(db) as con:
        return [(n, bool(a)) for n, a in con.execute(
            "SELECT name, isActive FROM playsets WHERE coalesce(isRemoved, 0) = 0 ORDER BY name")]


def playset_mods(db: Path, name: str | None) -> tuple[str, list[tuple[str, str, str | None]]]:
    """``(playset name, [(display name, folder, steam id)])`` of the enabled mods, in launcher order."""
    with _connect(db) as con:
        if name:
            row = con.execute("SELECT id, name FROM playsets WHERE name = ? AND coalesce(isRemoved, 0) = 0",
                              (name,)).fetchone()
        else:
            row = con.execute("SELECT id, name FROM playsets WHERE isActive = 1").fetchone()
        if not row:
            known = ", ".join(n for n, _ in list_playsets(db))
            raise KeyError(f"no playset {name!r}; the launcher has: {known}" if name else "no active playset")
        rows = con.execute(
            "SELECT m.displayName, m.dirPath, m.steamId FROM playsets_mods pm JOIN mods m ON m.id = pm.modId "
            "WHERE pm.playsetId = ? AND pm.enabled = 1 ORDER BY pm.position", (row[0],)).fetchall()
    return row[1], rows


def mod_display_name(path: Path) -> str:
    """The name from ``.metadata/metadata.json``, else the folder name."""
    f = path / ".metadata" / "metadata.json"
    try:
        return json.loads(f.read_text(encoding="utf-8-sig")).get("name") or path.name
    except (OSError, ValueError):
        return path.name


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False
