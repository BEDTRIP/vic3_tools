"""Claude Code hook after an edit: check the edited file of a playset mod with ``v3 lint``'s fast rules.

Run as ``v3 hook post-tool-use`` (PostToolUse, matcher ``Edit|Write|MultiEdit``); it reads the hook's JSON on stdin.
For a ``.gui`` / ``.txt`` / ``.yml`` file inside a mod of the active playset (not vanilla) it runs the rules that need
only that file and the index — braces, BOM, project rules, GUI types that never apply, text width of the textboxes
around the edited lines — leaves out known reports (baseline, suppressions) and hands the rest to the agent as
context. tiger is not run (it takes seconds per mod; ``v3 lint`` runs it). Whatever goes wrong, the hook says nothing.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

MAX_LINES = 15
EXTS = (".gui", ".txt", ".yml")


def run(stdin: str) -> str:
    try:
        data = json.loads(stdin or "{}")
        text = check(data)
    except Exception:  # noqa: BLE001 — a broken hook must not break the edit
        return ""
    if not text:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}},
                      ensure_ascii=False)


def _edited_lines(path: Path, inp: dict) -> set[int] | None:
    """Lines the edit wrote (None: the whole file, as for Write)."""
    news = [inp.get("new_string")] if inp.get("new_string") else [e.get("new_string") for e in inp.get("edits") or []]
    news = [n for n in news if n]
    if not news:
        return None
    text = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    out: set[int] = set()
    for n in news:
        at = text.find(n.replace("\r\n", "\n"))
        if at >= 0:
            first = text.count("\n", 0, at) + 1
            out.update(range(first, first + n.count("\n") + 1))
    return out or None


def check(data: dict, ms=None) -> str:
    inp = data.get("tool_input") or {}
    f = inp.get("file_path")
    if not f or not f.lower().endswith(EXTS):
        return ""
    path = Path(f)
    if not path.is_file():
        return ""
    from vic3tools.core import paths
    from vic3tools.core.vfs import ModSet
    from vic3tools.i18n import set_lang, t
    from vic3tools.index.query import SetIndex
    from vic3tools.lint import rules
    from vic3tools.lint import run as lint_run

    cfg = paths.load_config()
    set_lang(cfg.values.get("lang"))
    ms = ms or ModSet.from_playset(None, cfg)
    mod_i, rel = None, None
    for i, m in enumerate(ms.mods[1:], 1):
        rel = rules.as_rel(m, path)
        if rel is not None:
            mod_i = i
            break
    if mod_i is None or rel is None:
        return ""
    mod = ms.mods[mod_i]
    lines = _edited_lines(path, inp)
    with contextlib.redirect_stdout(io.StringIO()):
        si = SetIndex.open(ms)
        try:
            only = ("braces", "bom", "gui-type-ignored", "text-fit")
            reports, _notes = lint_run.collect(si, mod_i, use_tiger=False, only=only, files={rel},
                                               lines={rel: lines} if lines else None)
        finally:
            si.close()
    res = lint_run.split(mod, reports)
    if not res.shown:
        return ""
    out = [t("hook_lint_head", file=rel)]
    for r in res.shown[:MAX_LINES]:
        out.append(f"  {r.path}:{r.line}  {r.severity} {r.key}: {r.message}")
    if len(res.shown) > MAX_LINES:
        out.append(f"  … +{len(res.shown) - MAX_LINES} (v3 lint --no-tiger --file {rel})")
    return "\n".join(out)


def main() -> int:
    out = run(sys.stdin.read())
    if out:
        sys.stdout.write(out)
    return 0
