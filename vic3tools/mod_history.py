"""The history of the playset's mods in git: each new version of a mod is a commit, so any two versions diff.

Steam keeps only a mod's latest version and the Steam client overwrites it on update; this keeps what was there. The
history is a git repo in the tool's home (``mod_history/``): one folder per mod (its Workshop ID or folder name), a
commit per mod whose files changed since the last snapshot, the message ``<name> <version> — game <version>``. With
``--vanilla`` the game's text folders are kept the same way (``_vanilla/``), so a patch's changes diff too.

Mods that are git checkouts themselves (the user's own repos) are skipped: they have their history.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vic3tools.core import paths

VANILLA_DIRS = ("common", "events", "gui", "localization")
SKIP = {".git", "__pycache__"}


@dataclass
class Snap:
    name: str
    folder: str
    version: str
    changed: int  # files added, changed or removed; 0 — nothing new


def repo_dir() -> Path:
    return paths.tool_home() / "mod_history"


def _git(repo: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def ensure_repo(repo: Path) -> None:
    if not (repo / ".git").is_dir():
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.name", "vic3tools")
        _git(repo, "config", "user.email", "vic3tools@localhost")
        _git(repo, "config", "core.autocrlf", "false")


def _meta(mod: Path) -> dict:
    try:
        return json.loads((mod / ".metadata" / "metadata.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def folder_name(mod: Path, meta: dict) -> str:
    wid = str(meta.get("id") or "")
    return wid if wid.isdigit() else mod.name


def is_own_repo(mod: Path) -> bool:
    return (mod / ".git").exists()


def _mirror(src: Path, dst: Path, roots: tuple[str, ...] | None = None) -> None:
    """Make ``dst`` the same as ``src`` (only ``roots`` of it, if given)."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    tops = [src / r for r in roots] if roots else [src]
    for top in tops:
        if not top.exists():
            continue
        for p in top.rglob("*"):
            rel = p.relative_to(src)
            if any(part in SKIP for part in rel.parts) or not p.is_file():
                continue
            q = dst / rel
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)


def _commit(repo: Path, folder: str, message: str) -> int:
    _git(repo, "add", "-A", "--", folder)
    n = len([x for x in _git(repo, "diff", "--cached", "--name-only", "--", folder).splitlines() if x])
    if n:
        _git(repo, "commit", "-q", "-m", message, "--", folder)
    return n


def snapshot(mods: list[tuple[str, Path]], game: Path | None, game_version: str | None,
             vanilla: bool = False, repo: Path | None = None) -> list[Snap]:
    repo = repo or repo_dir()
    ensure_repo(repo)
    out = []
    gv = game_version or "?"
    if vanilla and game is not None:
        _mirror(game / "game", repo / "_vanilla", VANILLA_DIRS)
        out.append(Snap("vanilla", "_vanilla", gv, _commit(repo, "_vanilla", f"vanilla — game {gv}")))
    for name, path in mods:
        if not path.is_dir() or is_own_repo(path):
            continue
        meta = _meta(path)
        folder = folder_name(path, meta)
        version = str(meta.get("version") or "?")
        _mirror(path, repo / folder)
        out.append(Snap(name, folder, version,
                        _commit(repo, folder, f"{name} {version} — game {gv}")))
    return out


def history(repo: Path, folder: str, limit: int = 30) -> list[str]:
    return _git(repo, "log", f"-{limit}", "--format=%h %cs %s", "--", folder).splitlines()


def find_folder(repo: Path, name_or_folder: str) -> str | None:
    """A mod's folder in the history: the folder itself, or the one whose last snapshot names the mod."""
    if (repo / name_or_folder).is_dir():
        return name_or_folder
    for d in repo.iterdir():
        if d.is_dir() and d.name != ".git":
            log = _git(repo, "log", "-1", "--format=%s", "--", d.name, check=False)
            if name_or_folder.casefold() in log.casefold():
                return d.name
    return None


def diff(repo: Path, folder: str, a: str | None = None, b: str | None = None, stat: bool = True) -> str:
    """The changes of one mod between two snapshots (default: its last two)."""
    if not a:
        commits = _git(repo, "log", "-2", "--format=%h", "--", folder).split()
        if len(commits) < 2:
            return ""
        b, a = commits[0], commits[1]
    args = ["diff", "--stat=160" if stat else "-U3", a, b or "HEAD", "--", folder]
    return _git(repo, *args)
