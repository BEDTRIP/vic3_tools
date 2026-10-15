"""Claude Code hook: turn a grep for a name, or a read of a whole big file, in game or mod folders into a `v3` answer.

Run as ``v3 hook pre-tool-use`` (PreToolUse, matcher ``Grep|Bash|PowerShell|Read``); it reads the hook's JSON on stdin.

- A text search (the Grep tool, or ``grep`` / ``rg`` / ``findstr`` / ``Select-String`` in a shell) for one identifier
  over the game, the Workshop or a playset mod: the first time in a session the call is refused, and the refusal
  carries the answer from the index — ``v3 def`` and ``v3 refs`` for that name. Repeating the same search lets it
  through (comments, documents, free text are grep's job).
- A read of a whole ``.gui`` / ``.txt`` over 300 lines in those folders: refused once with ``v3 outline`` of the file,
  so the agent reads only the line range it needs. Repeating the read lets it through.

Anything else, and any name the index does not know, passes untouched. Whatever goes wrong inside, the hook lets the
call through: it must never be the reason a tool fails.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

from vic3tools.core import paths

BIG_FILE_LINES = 300
ROOTS_TTL = 600  # seconds the list of folders is cached
MAX_ANSWER_LINES = 45
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[0-9]+)?\Z")
# command names as typed (PowerShell's cmdlets in any case); found only outside heredoc bodies and quoted strings
_SHELL_SEARCH = re.compile(r"(?:^|[\s|;&(])(grep|egrep|rg|findstr|(?i:Select-String|sls))(?=\s)")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)(?:\n\2\s*(?:\n|$)|\Z)", re.S)
_QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")


def _blank(text: str, rx: re.Pattern, group: int = 0) -> str:
    """``text`` with the matches of ``rx`` (its ``group``) replaced by spaces: offsets stay."""
    return rx.sub(lambda m: m.group(0)[:m.start(group) - m.start()] + re.sub(r"[^\n]", " ", m.group(group))
                  + m.group(0)[m.end(group) - m.start():], text)


def _search_at(cmd: str) -> re.Match | None:
    """The search command in a shell line, not a word inside a heredoc or a string."""
    return _SHELL_SEARCH.search(_blank(_blank(cmd, _HEREDOC, 3), _QUOTED))
_TOKEN = re.compile(r"'([^']*)'|\"([^\"]*)\"|(\S+)")
_GAME_DIRS = re.compile(r"(?:^|[\s/\\\"'])(common|gui|localization|events|map_data)[/\\]", re.I)
_SCRIPT_GLOB = re.compile(r"\.(txt|gui|yml)\b|\*\*?$|^\*$", re.I)


def run(stdin: str) -> str:
    """The hook's stdout for one call ("" lets the call through)."""
    try:
        data = json.loads(stdin or "{}")
        decision = decide(data)
    except Exception:  # noqa: BLE001 — a broken hook must not break the tool
        return ""
    if not decision:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": decision}}, ensure_ascii=False)


def decide(data: dict) -> str | None:
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    cwd = Path(data.get("cwd") or os.getcwd())
    session = str(data.get("session_id") or "nosession")
    roots = watched_roots()
    if not roots:
        return None
    if tool == "Grep":
        name = identifier(inp.get("pattern", ""))
        glob = inp.get("glob") or ""
        if not name or (glob and not _SCRIPT_GLOB.search(glob)) or inp.get("type") not in (None, "", "txt"):
            return None
        target = Path(inp["path"]) if inp.get("path") else cwd
        if not touches(target, roots):
            return None
        return once(session, f"grep:{name}", lambda: name_answer(name))
    if tool in ("Bash", "PowerShell"):
        cmd = inp.get("command", "")
        if not _search_at(cmd):
            return None
        name = shell_identifier(cmd)
        if not name or not (_GAME_DIRS.search(cmd) or any(_mentions(cmd, r) for r in roots) or touches(cwd, roots)):
            return None
        return once(session, f"grep:{name}", lambda: name_answer(name))
    if tool == "Read":
        f = Path(inp.get("file_path", ""))
        if inp.get("offset") or inp.get("limit") or f.suffix.lower() not in (".gui", ".txt"):
            return None
        if not inside(f, roots) or count_lines(f) <= BIG_FILE_LINES:
            return None
        return once(session, f"read:{f.resolve()}", lambda: outline_answer(f))
    return None


# --- what to look at -------------------------------------------------------------------------------------------------


def watched_roots() -> list[Path]:
    """The game, the Workshop, the local mods and every mod folder of the active playset (cached a few minutes)."""
    cache = paths.tool_home() / "hook_roots.json"
    try:
        if time.time() - cache.stat().st_mtime < ROOTS_TTL:
            return [Path(p) for p in json.loads(cache.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        pass
    found: list[Path] = []
    cfg = paths.load_config()
    roots = paths.resolve_roots(cfg)
    if roots["game"].ok:
        found.append(roots["game"].path)
    if roots["workshop"].ok:
        found.append(roots["workshop"].path)
    if roots["documents"].ok:
        found.append(roots["documents"].path / "mod")
    try:
        from vic3tools.core.vfs import ModSet

        found += [m.path for m in ModSet.from_playset(None, cfg).mods]
    except Exception:  # noqa: BLE001 — no playset is fine: the roots above still count
        pass
    unique = []
    for p in found:
        if p.is_dir() and all(not _same(p, q) for q in unique):
            unique.append(p)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([str(p) for p in unique]), encoding="utf-8")
    except OSError:
        pass
    return unique


def inside(p: Path, roots: list[Path]) -> bool:
    try:
        rp = p.resolve()
    except OSError:
        return False
    return any(rp == r.resolve() or r.resolve() in rp.parents for r in roots)


def touches(p: Path, roots: list[Path]) -> bool:
    """``p`` is inside a watched folder, or contains one (a search from a parent folder reaches it too)."""
    if inside(p, roots):
        return True
    try:
        rp = p.resolve()
    except OSError:
        return False
    return any(rp in r.resolve().parents for r in roots)


def _mentions(cmd: str, root: Path) -> bool:
    norm = cmd.replace("\\", "/").lower()
    r = str(root).replace("\\", "/").lower()
    return r in norm or r.replace("c:/", "/c/") in norm


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def identifier(pattern: str) -> str | None:
    """The name a search pattern looks for, if it is one plain identifier (word anchors allowed)."""
    p = pattern.strip()
    p = re.sub(r"^(\\b|\\<|\^|\\s\*)+|(\\b|\\>|\$|\\s\*=?)+$", "", p)
    p = p.replace("\\.", ".")
    # a numbered family: `name_\d+`, `name_[0-9]+`, `name_.*`, `name_N` → the glob `name_*`
    fam = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*?_?)(?:\\d[+*]?|\[0-9\][+*]?|\.\*|\.\+|N|\*)", p)
    if fam and len(fam.group(1)) >= 6 and fam.group(1).endswith("_"):
        return fam.group(1) + "*"
    return p if _IDENT.match(p) and len(p) >= 4 and ("_" in p or "." in p or p.isupper()) else None


def shell_identifier(cmd: str) -> str | None:
    """The first identifier-like argument after the search command in a shell line."""
    m = _search_at(cmd)
    rest = cmd[m.end():] if m else ""
    for t in _TOKEN.finditer(rest):
        tok = next(g for g in t.groups() if g is not None)
        if tok.startswith("-") or tok in ("|", "&&", ";"):
            continue
        name = identifier(tok)
        if name:
            return name
        if tok in ("|", "&&", ";") or tok.endswith((";", "|")):
            break
    return None


def count_lines(f: Path) -> int:
    try:
        with open(f, "rb") as fh:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 16), b""))
    except OSError:
        return 0


# --- answers ---------------------------------------------------------------------------------------------------------


def once(session: str, key: str, answer) -> str | None:
    """Refuse the first time a key is seen in a session (with the answer); let it through after."""
    state_dir = paths.tool_home() / "hook_state"
    f = state_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', session)[:80]}.json"
    try:
        seen = set(json.loads(f.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        seen = set()
    if key in seen:
        return None
    text = answer()
    if not text:
        return None
    seen.add(key)
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass
    return text


def _v3(*args: str) -> tuple[int, str]:
    from vic3tools import cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = cli.main(["--lang", "en", *args])
        except SystemExit as e:
            code = int(e.code or 0)
    return code, buf.getvalue()


def _clip(text: str) -> str:
    lines = text.rstrip().split("\n")
    if len(lines) > MAX_ANSWER_LINES:
        lines = lines[:MAX_ANSWER_LINES] + [f"… {len(lines) - MAX_ANSWER_LINES} more lines (run the command itself)"]
    return "\n".join(lines)


def name_answer(name: str) -> str | None:
    if not name.endswith("*"):
        dcode, dout = _v3("def", name)
        rcode, rout = _v3("refs", name, "--limit", "20")
        if dcode == 0 or rcode == 0:
            return _name_text(name, dout, rout)
        name += "*"  # not a name of its own: maybe the common part of numbered names (`list_` → `list_1`…)
    gcode, gout = _v3("refs", name)
    if gcode != 0:
        return None  # the index does not know it: grep is the right tool
    return ("The v3 index answers this search (vic3-search skill) — use it instead of grep:\n\n"
            f"$ v3 refs '{name}'\n{_clip(gout)}\n\nOne of them in detail: `v3 refs <name>` (file:line, the record "
            "it sits in, writes). If you still need a text search (comments, documents, free text), repeat the same "
            "call and it will run.")


def _name_text(name: str, dout: str, rout: str) -> str:
    return ("The v3 index answers this search (vic3-search skill) — use it instead of grep:\n\n"
            f"$ v3 def {name}\n{_clip(dout)}\n\n$ v3 refs {name}\n{_clip(rout)}\n\n{_folders(dout + rout)}"
            "Follow a chain with `v3 refs <the record a use sits in>`. If you still need a text search (comments, "
            "documents, free text), repeat the same call and it will run.")


def _folders(text: str) -> str:
    """Where the mods named in an answer live (answers give paths relative to a mod's folder)."""
    try:
        from vic3tools.core.vfs import ModSet

        mods = ModSet.from_playset(None, paths.load_config()).mods
    except Exception:  # noqa: BLE001
        return ""
    used = [m for m in mods if f"{m.name}:" in text]
    return ("Paths are relative to: " + "; ".join(f"{m.name} = {m.path}" for m in used) + "\n\n") if used else ""


def outline_answer(f: Path) -> str | None:
    """The deepest outline of the file that still fits the answer."""
    from vic3tools.index import query

    nodes = query.outline(f)
    if not nodes:
        return None
    best, depth = None, 1
    for d in range(1, 12):
        rows = list(query.flatten(nodes, d))
        if len(rows) > MAX_ANSWER_LINES and best is not None:
            break
        best, depth = rows, d
        if len(rows) > MAX_ANSWER_LINES:
            break
    lines = []
    for lv, nd in best[:MAX_ANSWER_LINES]:
        label = f' "{nd.label}"' if nd.label else ""
        kids = f"  ({len(nd.children)} inside)" if nd.children and lv + 1 >= depth else ""
        lines.append(f"{'  ' * lv}{nd.key}{label}  {nd.line}-{nd.end_line}{kids}")
    return (f"{f.name} has {count_lines(f)} lines. Its outline to depth {depth} (v3 outline, vic3-search skill) — "
            f"read only the line range you need with offset/limit; `v3 outline <file> --find <name or text>` finds "
            f"a widget by its name or text, `--at <line>` shows what is around a line:\n\n" + "\n".join(lines)
            + "\n\nTo read the whole file anyway, repeat the same Read.")


def main() -> int:
    out = run(sys.stdin.read())
    if out:
        sys.stdout.write(out)
    return 0
