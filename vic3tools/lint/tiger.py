"""Run ``vic3-tiger`` over one mod of a set and read its reports.

The mods before it in the set are loaded as dependencies (``load_mod`` in a generated config, after the mod's own
``vic3-tiger.conf`` if it has one), so items they define are not "missing". The JSON output is cached per mod and
reused while no file of the set's mods changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from vic3tools.core import paths
from vic3tools.core.vfs import Mod, ModSet


@dataclass
class Report:
    severity: str  # error, warning, untidy, tips
    confidence: str
    key: str
    message: str
    path: str  # relative to the mod, forward slashes
    line: int
    column: int
    text: str  # the source line
    info: str = ""
    source: str = "tiger"
    also: tuple[str, ...] = ()  # more locations, "path:line"

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


def exe() -> Path:
    return paths.bin_dir() / ("vic3-tiger.exe" if sys.platform == "win32" else "vic3-tiger")


def _stamp(mods: list[Mod]) -> str:
    """Changes when any file of these mods changes (mtime and size of every file)."""
    h = hashlib.sha1()
    for m in mods:
        for dirpath, dirs, files in os.walk(m.path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for f in sorted(files):
                try:
                    st = os.stat(os.path.join(dirpath, f))
                except OSError:
                    continue
                h.update(f"{dirpath}/{f}:{st.st_mtime_ns}:{st.st_size};".encode("utf-8", "replace"))
    return h.hexdigest()


def config_text(mod: Mod, deps: list[Mod]) -> str:
    """The mod's own ``vic3-tiger.conf`` (if any) plus a ``load_mod`` for each dependency it does not name."""
    own = mod.path / "vic3-tiger.conf"
    text = own.read_text(encoding="utf-8-sig") if own.is_file() else ""
    out = [text.rstrip(), "", "# added by v3 lint: the mods before this one in the set"] if text else []
    for d in deps:
        if d.path.as_posix() in text:
            continue
        label = "".join(c for c in d.name if c.isalnum() or c in " _-.&")[:40] or "dep"
        out.append(f'load_mod = {{\n\tlabel = "{label}"\n\tmod = "{d.path.as_posix()}"\n}}')
    return "\n".join(out) + "\n"


def run(ms: ModSet, mod: Mod, refresh: bool = False, timeout: int = 900) -> list[Report]:
    """tiger's reports on ``mod`` (cached); raises FileNotFoundError if tiger or the game is not there."""
    tiger = exe()
    if not tiger.is_file():
        raise FileNotFoundError(f"vic3-tiger is not installed ({tiger}); see `v3 setup`")
    roots = paths.resolve_roots()
    if not roots["game"].ok:
        raise FileNotFoundError("the game was not found; see `v3 where`")
    i = ms.mods.index(mod)
    deps = [m for m in ms.mods[1:i]]
    cache = paths.cache_dir() / "lint"
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(mod.path.as_posix().encode()).hexdigest()[:12]
    out_file = cache / f"tiger-{tag}.json"
    stamp_file = cache / f"tiger-{tag}.stamp"
    stamp = _stamp([*deps, mod]) + ":" + str(tiger.stat().st_mtime_ns)
    if not refresh and out_file.is_file() and stamp_file.is_file() and stamp_file.read_text() == stamp:
        return parse(out_file.read_text(encoding="utf-8"), mod)
    conf = cache / f"tiger-{tag}.conf"
    conf.write_text(config_text(mod, deps), encoding="utf-8")
    cmd = [str(tiger), "--json", "--no-color", "--config", str(conf), "--game", str(roots["game"].path)]
    if roots["workshop"].ok:
        cmd += ["--workshop", str(roots["workshop"].path)]
    cmd.append(str(mod.path))
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    raw = res.stdout.decode("utf-8", "replace")
    if not raw.strip().startswith("["):
        err = (res.stderr.decode("utf-8", "replace") or raw).strip().splitlines()
        raise RuntimeError("vic3-tiger failed: " + (err[-1] if err else f"exit code {res.returncode}"))
    out_file.write_text(raw, encoding="utf-8")
    stamp_file.write_text(stamp)
    return parse(raw, mod)


def parse(raw: str, mod: Mod | None = None) -> list[Report]:
    """Reports of tiger's ``--json`` output located in the checked mod (``from`` = MOD)."""
    out = []
    for r in json.loads(raw):
        locs = r.get("locations") or []
        if not locs or locs[0].get("from") != "MOD":
            continue
        first = locs[0]
        also = tuple(f"{(x.get('path') or '').replace(chr(92), '/')}:{x.get('linenr') or 0}" for x in locs[1:])
        out.append(Report(r.get("severity") or "", r.get("confidence") or "", r.get("key") or "",
                          r.get("message") or "", (first.get("path") or "").replace("\\", "/"),
                          first.get("linenr") or 0, first.get("column") or 0, (first.get("line") or "").strip(),
                          r.get("info") or "", "tiger", also))
    return out
