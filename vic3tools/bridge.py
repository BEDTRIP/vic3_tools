"""``v3`` for a remote agent: the PC bridge's tool that runs a ``v3`` command on the PC and returns its output.

A cloud session has no game files; through the bridge (an MCP server on the PC, ``vic3_mods/tools/pc_bridge``) it calls
the same commands. Only commands that read are allowed, plus the test bench: nothing the remote agent runs here
writes into the PC's repositories or mods — it edits its own clone and pushes. ``gui set`` only with ``--dry``;
``lint --baseline``, ``setup``, ``hook``, ``docs`` are refused.
"""

from __future__ import annotations

import os
import subprocess
import sys

READ_COMMANDS = {"where", "doctor", "glossary", "def", "refs", "loc", "outline", "playsets", "mods", "winner",
                 "conflicts", "matrix", "audit", "gui", "lint", "bench", "save", "log"}
REFUSED_FLAGS = {"lint": {"--baseline", "--refresh-baseline"}}
MAX_OUTPUT = 40_000


def check(args: list[str]) -> str | None:
    """Why ``args`` may not run from a remote agent (None: it may)."""
    if not args:
        return "no command"
    cmd = args[0]
    if cmd not in READ_COMMANDS:
        return f"`v3 {cmd}` is not allowed from the bridge (allowed: {', '.join(sorted(READ_COMMANDS))})"
    if cmd == "gui" and len(args) > 1 and args[1] == "set" and "--dry" not in args:
        return "`v3 gui set` writes a file on the PC: only with --dry here (edit your clone, push, then lint)"
    bad = REFUSED_FLAGS.get(cmd, set()) & set(args)
    if bad:
        return f"`v3 {cmd} {' '.join(sorted(bad))}` writes into a mod on the PC: run it in your clone"
    return None


def run(args: list[str], lang: str = "en", timeout: int = 1800, cwd: str | None = None) -> str:
    """The output of ``v3 <args>`` (exit code first), or the reason it is refused. ``cwd``: where the nearest
    ``vic3tools.toml`` is looked for — the bridge keeps one mapping a mod to the checkout of the pushed branch."""
    why = check(args)
    if why:
        return f"refused: {why}"
    # the bridge's own venv may not have the package installed: point the child at this checkout
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "PYTHONPATH": os.pathsep.join(x for x in (root, os.environ.get("PYTHONPATH", "")) if x)}
    p = subprocess.run([sys.executable, "-m", "vic3tools.cli", "--lang", lang, *args], capture_output=True, cwd=cwd,
                       timeout=timeout, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n… cut at {MAX_OUTPUT} characters: narrow it (--limit, --file, --prop, --json)"
    return f"exit {p.returncode}\n{out}"
