"""Claude Code hook: at the start of a session, tell the agent that `v3` is there and what it can do.

Run as ``v3 hook session-start`` (SessionStart); it reads the hook's JSON on stdin and prints ``additionalContext`` —
a short menu of the commands, and whether the session's folder is the game or a mod of the active playset. So a
project needs no section about `v3` in its own CLAUDE.md: the plugin brings it wherever it is enabled. It only says
what is there; which tool to use for an answer stays the agent's choice.

Nothing is printed when the game is not found on this machine (a cloud session: `v3` has nothing to read there).
Whatever goes wrong inside, the hook prints nothing: it must never be the reason a session fails to start.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from vic3tools.core import paths

MENU = """\
`v3` (vic3tools) is installed: it knows the game and the mods of the active launcher playset, and answers with
file:line and what the game actually takes. Use it where it helps; `v3 <command> -h` for details.
- Find: `def X` (where defined, which definition wins), `refs X` (who uses, reads, writes; `prefix_*`; `_archive/`
  listed apart), `loc KEY` / `loc --text "…"` (the text shown, the key behind a text), `outline FILE` (a big file's
  tree with line ranges), `winner <folder> X` (the chain across mods), `glossary` (the game's own term).
- GUI: `gui resolve FILE:LINE` (after types / using / blockoverride), `gui types|templates|textures`, `gui set … --dry`
  (an exact edit with its lines), `gui fit` (does a text fit, 11 languages), `gui render` / `gui grid`.
- Check: `lint` (tiger + own rules, known reports left out), `audit replace|stale|loc-dead|dups|…`, `conflicts`,
  `mods`, `playsets`.
- Saves and logs: `save` (a save, read by pieces), `log` (record families, two runs compared, speed, `log profile`).
- The game: `bench` (the game open in the sandbox VM: edit → shot). Another set: `--playset NAME`, `--mods DIR…`."""


def where(cwd: Path, roots: list[Path]) -> str | None:
    """A line on what the session's folder is: the game, a playset mod, or nothing to say."""
    from vic3tools.hook import inside

    up = [r for r in roots if inside(cwd, [r])]
    if up:
        return f"This folder is inside {up[-1]} — part of the set `v3` reads."
    down = [r for r in roots if inside(r, [cwd])]
    if down:
        more = f" (+{len(down) - 3} more)" if len(down) > 3 else ""
        return "Under this folder, in the set `v3` reads: " + ", ".join(str(r) for r in down[:3]) + more + "."
    return None


def run(stdin: str) -> str:
    try:
        data = json.loads(stdin or "{}")
        cfg = paths.load_config()
        if not paths.resolve_roots(cfg)["game"].ok:
            return ""
        from vic3tools.hook import watched_roots

        text = MENU
        cwd = data.get("cwd")
        if cwd:
            line = where(Path(cwd), watched_roots())
            if line:
                text += "\n" + line
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
    except Exception:  # noqa: BLE001 — never block a session start
        return ""


def main() -> int:
    out = run(sys.stdin.read())
    if out:
        sys.stdout.write(out)
    return 0
