"""Find the three roots the tools read from, and the tools' own config and cache.

The three roots:

- ``game`` — the game install (``Victoria 3/``, with ``game/``, ``launcher/``, ``binaries/``), found through Steam;
- ``workshop`` — ``steamapps/workshop/content/529340`` in the same Steam library, mods as they are;
- ``documents`` — ``Documents/Paradox Interactive/Victoria 3`` (logs, saves, local mods, the launcher's database).

Each root is found by itself; ``vic3tools.toml`` only corrects what was found. Two config files are read, the later
wins: the user one in the tools' home (``%LOCALAPPDATA%\\vic3tools``), then the nearest ``vic3tools.toml`` from the
current folder up (a project's own).
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from vic3tools.core import vdf

APP_ID = "529340"
GAME_FOLDER = "Victoria 3"
CONFIG_NAME = "vic3tools.toml"
ROOT_NAMES = ("game", "workshop", "documents")


@dataclass
class Root:
    path: Path | None
    source: str  # where it came from: "config <file>", "steam", "documents folder", "not found"

    @property
    def ok(self) -> bool:
        return self.path is not None and self.path.is_dir()


@dataclass
class Config:
    values: dict = field(default_factory=dict)
    files: list[Path] = field(default_factory=list)  # read, in order; later ones win

    def get(self, section: str, key: str, default=None):
        return self.values.get(section, {}).get(key, default)

    def source_of(self, section: str, key: str) -> Path | None:
        for f, vals in reversed(self._per_file):
            if key in vals.get(section, {}):
                return f
        return None

    _per_file: list[tuple[Path, dict]] = field(default_factory=list, repr=False)


def tool_home() -> Path:
    """Folder for the user config, the cache and installed programs (tiger)."""
    if env := os.environ.get("V3_HOME"):
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "vic3tools"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "vic3tools"


def cache_dir() -> Path:
    return tool_home() / "cache"


def bin_dir() -> Path:
    return tool_home() / "bin"


def user_config_path() -> Path:
    return tool_home() / CONFIG_NAME


def find_project_config(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        f = d / CONFIG_NAME
        if f.is_file() and f != user_config_path():
            return f
    return None


def load_config(start: Path | None = None) -> Config:
    cfg = Config()
    for f in (user_config_path(), find_project_config(start)):
        if f is None or not f.is_file():
            continue
        with open(f, "rb") as fh:
            vals = tomllib.load(fh)
        cfg.files.append(f)
        cfg._per_file.append((f, vals))
        for section, body in vals.items():
            if isinstance(body, dict):
                cfg.values.setdefault(section, {}).update(body)
            else:
                cfg.values[section] = body
    return cfg


def write_user_config(roots: dict[str, Path], lang: str | None = None) -> Path:
    """Write the user config with the given roots (and language). Overwrites the file."""
    f = user_config_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# vic3tools user config, written by `v3 setup`; edit to correct what was found", ""]
    if lang:
        lines += [f'lang = "{lang}"', ""]
    lines.append("[roots]")
    for name in ROOT_NAMES:
        if name in roots:
            lines.append(f"{name} = {_toml_str(str(roots[name]))}")
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def _toml_str(s: str) -> str:
    return "'" + s + "'" if "'" not in s else json.dumps(s)


# --- Steam ---------------------------------------------------------------------------------------------------------


def steam_dirs() -> list[Path]:
    """Candidate Steam install folders, most likely first."""
    found: list[Path] = []
    if sys.platform == "win32":
        import winreg

        for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    found.append(Path(winreg.QueryValueEx(k, value)[0]))
            except OSError:
                pass
        found.append(Path(r"C:\Program Files (x86)\Steam"))
    else:
        home = Path.home()
        found += [home / ".steam" / "steam", home / ".local" / "share" / "Steam",
                  home / "Library" / "Application Support" / "Steam"]
    out: list[Path] = []
    for d in found:
        if d.is_dir() and all(not _same(d, o) for o in out):
            out.append(d)
    return out


def steam_libraries(steam_dir: Path) -> list[Path]:
    """Library folders of one Steam install (the install itself first)."""
    libs = [steam_dir]
    f = steam_dir / "steamapps" / "libraryfolders.vdf"
    if f.is_file():
        data = vdf.loads(f.read_text(encoding="utf-8", errors="replace")).get("libraryfolders", {})
        for entry in data.values():
            if isinstance(entry, dict) and entry.get("path"):
                p = Path(entry["path"])
                if p.is_dir() and all(not _same(p, o) for o in libs):
                    libs.append(p)
    return libs


def find_game_library(steam: list[Path] | None = None) -> Path | None:
    for s in steam if steam is not None else steam_dirs():
        for lib in steam_libraries(s):
            if (lib / "steamapps" / "common" / GAME_FOLDER / "game").is_dir():
                return lib
    return None


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a).lower() == str(b).lower()


# --- documents -----------------------------------------------------------------------------------------------------


def documents_folder() -> Path:
    """The user's Documents folder (on Windows, the real one — it may have been moved to OneDrive)."""
    if sys.platform == "win32":
        try:
            return Path(_known_folder_documents())
        except OSError:
            pass
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
    return Path.home() / ".local" / "share"


def _known_folder_documents() -> str:
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    folder_id = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
    out = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out))
    if hr != 0:
        raise OSError(f"SHGetKnownFolderPath failed: {hr}")
    try:
        return out.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


# --- the three roots -----------------------------------------------------------------------------------------------


def detect_roots() -> dict[str, Root]:
    """Find the roots on this machine, ignoring any config."""
    roots: dict[str, Root] = {}
    lib = find_game_library()
    if lib:
        roots["game"] = Root(lib / "steamapps" / "common" / GAME_FOLDER, f"steam library {lib}")
        roots["workshop"] = Root(lib / "steamapps" / "workshop" / "content" / APP_ID, f"steam library {lib}")
    else:
        roots["game"] = Root(None, "not found: no Steam library has Victoria 3")
        roots["workshop"] = Root(None, "not found: no Steam library has Victoria 3")
    docs = documents_folder() / "Paradox Interactive" / GAME_FOLDER
    roots["documents"] = Root(docs, "documents folder") if docs.is_dir() else Root(None, f"not found: {docs}")
    return roots


def resolve_roots(cfg: Config | None = None) -> dict[str, Root]:
    """The roots in effect: config values over detected ones."""
    cfg = cfg if cfg is not None else load_config()
    roots = detect_roots()
    for name in ROOT_NAMES:
        value = cfg.get("roots", name)
        if value:
            roots[name] = Root(Path(value), f"config {cfg.source_of('roots', name)}")
    return roots


def game_version(game_root: Path) -> str | None:
    f = game_root / "launcher" / "launcher-settings.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("rawVersion")
    except (OSError, ValueError):
        return None
