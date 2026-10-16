"""Checks of our own, on top of tiger: what needs the set or the game's own rules, which tiger does not know.

- ``gui-type-ignored`` — a GUI type of the mod that never applies: another file registers it first (files ordered
  by file name across all mods);
- ``replace-fields`` — a ``REPLACE:`` body that omits fields of the record it replaces (they are lost);
- ``loc-dead`` — a loc key defined earlier under another path: it never shows (move it to ``replace/``);
- ``text-fit`` — a one-line textbox with a fixed width whose text does not fit in some language (cut or overflows);
- ``braces`` — a script / GUI file whose ``{`` and ``}`` do not balance;
- ``bom`` — a localization file without a BOM, or a script file with non-ASCII text and no BOM (the game misreads it);
- ``rule:<name>`` — project rules: a regex over files, from ``[[rule]]`` in the mod's ``v3-lint.toml``.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from vic3tools.core import script
from vic3tools.core.vfs import Mod, loads
from vic3tools.gui import fit, fonts, loctext, resolve, tree
from vic3tools.index.query import SetIndex
from vic3tools.lint.tiger import Report

RULES = ("gui-type-ignored", "replace-fields", "loc-dead", "text-fit", "braces", "bom")


def _r(severity: str, key: str, message: str, rel: str, line: int = 0, text: str = "") -> Report:
    return Report(severity, "strong", key, message, rel, line, 0, text.strip(), source="v3")


def mod_files(mod: Mod, exts: tuple[str, ...]) -> list[str]:
    out = []
    for p in mod.path.rglob("*"):
        if p.suffix.lower() in exts and p.is_file():
            rel = p.relative_to(mod.path).as_posix()
            if loads(rel):
                out.append(rel)
    return sorted(out)


# --- per file ---------------------------------------------------------------------------------------------------------


def file_rules(mod: Mod, rel: str, project: list[dict]) -> list[Report]:
    """The checks that need only the file: braces, BOM, project rules."""
    p = mod.path / rel
    try:
        raw = p.read_bytes()
    except OSError:
        return []
    out: list[Report] = []
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = (raw[3:] if bom else raw).decode("utf-8", "replace").replace("\r\n", "\n")
    low = rel.lower()
    if low.endswith((".txt", ".gui")):
        bal = script.brace_balance(text)
        if bal:
            out.append(_r("error", "braces", f"{abs(bal)} more `{'{' if bal > 0 else '}'}` than "
                          f"`{'}' if bal > 0 else '{'}` — everything after the break is read wrong", rel,
                          _unbalanced_line(text, bal)))
        if not bom and script.needs_bom(text):
            if low.endswith(".txt"):
                out.append(_r("error", "bom", "non-ASCII text without a BOM: the game misreads it", rel, 1))
            else:  # vanilla's .gui files with non-ASCII text have a BOM (all but a developers' library)
                out.append(_r("warning", "bom", "non-ASCII text without a BOM (vanilla .gui files have one)", rel, 1))
    elif low.startswith("localization/") and low.endswith(".yml") and not bom:
        out.append(_r("error", "bom", "a localization file without a BOM is not read", rel, 1))
    lines = None
    for rule in project:
        if not any(fnmatch.fnmatch(rel, g) for g in _list(rule.get("files", "*"))):
            continue
        rx = rule.get("_rx") or re.compile(rule.get("pattern", "(?!)"), re.M)
        rule["_rx"] = rx
        lines = lines if lines is not None else text.split("\n")
        for m in rx.finditer(text):
            ln = text.count("\n", 0, m.start()) + 1
            out.append(_r(rule.get("severity", "warning"), "rule:" + rule.get("name", "?"),
                          rule.get("message", rule.get("pattern", "")), rel, ln, lines[ln - 1]))
    return out


def _list(v) -> list[str]:
    return [v] if isinstance(v, str) else list(v)


def _unbalanced_line(text: str, bal: int) -> int:
    """Where the balance first goes negative (an extra `}`), else the start of the last top-level block left open."""
    depth, opened = 0, 1
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"|#[^\n]*|[{}]', text):
        s = m.group(0)
        if s == "{":
            if depth == 0:
                opened = text.count("\n", 0, m.start()) + 1
            depth += 1
        elif s == "}":
            depth -= 1
            if depth < 0:
                return text.count("\n", 0, m.start()) + 1
    return opened


# --- needs the set ----------------------------------------------------------------------------------------------------


def gui_types_ignored(si: SetIndex, mod_i: int, files: set[str] | None = None) -> list[Report]:
    order = {m: i for i, m in enumerate(si.mods)}
    mod = si.ms.mods[mod_i]
    con = si.cons[si.mods.index(mod)]
    rows = con.execute("SELECT n.name, f.rel, d.line FROM defs d JOIN names n ON n.id = d.name_id "
                       "JOIN files f ON f.id = d.file_id WHERE d.kind = 'gui_type'").fetchall()
    out = []
    for name, rel, line in rows:
        if files is not None and rel not in files:
            continue
        hits = [h for h in si.defs(name) if h.kind == "gui_type" and h.loads]
        if len(hits) < 2:
            continue
        hits.sort(key=lambda h: (h.rel.rsplit("/", 1)[-1].encode(), h.rel.count("/"), order[h.mod], h.line))
        w = hits[0]
        if w.mod == mod and w.rel == rel and w.line == line:
            continue
        if not any(h.mod == mod and h.rel == rel for h in hits):
            continue  # the mod's file never loads
        out.append(_r("warning", "gui-type-ignored", f"type {name} never applies: {w.mod.name} {w.rel}:{w.line} "
                      "registers it first (files ordered by name across mods)", rel, line))
    return out


def text_fit(si: SetIndex, mod_i: int, langs: list[str], files: list[str] | None = None,
             lines: dict[str, set[int]] | None = None, limit: int = 2000) -> list[Report]:
    """One-line textboxes with a width of their own whose loc text is cut or overflows in some language."""
    mod = si.ms.mods[mod_i]
    res = resolve.Resolver(si)
    game = si.ms.mods[0].path
    fs = fonts.Fonts.load(game, [m.path for m in si.ms.mods[1:]])
    out: list[Report] = []
    checked = 0
    for rel in files if files is not None else mod_files(mod, (".gui",)):
        try:
            nodes = tree.parse_file(mod.path / rel)
        except (OSError, ValueError):
            continue
        want = lines.get(rel) if lines else None
        for _trail, nd in tree.walk(nodes):
            if not (nd.is_block and nd.op and nd.key == "textbox"):
                continue
            if want is not None and not any(nd.line <= x <= nd.end_line for x in want):
                continue
            own = {c.key: c for c in nd.children or [] if c.op}
            if "text" not in own or not any(k in own for k in ("size", "maximumsize", "max_width")):
                continue
            key = own["text"].scalar().strip('"')
            if not key or "[" in key or " " in key:
                continue
            checked += 1
            if checked > limit:
                return out
            r = res.expand(nd)
            b = fit.box(r)
            if b.multiline or b.avail is None:
                continue
            texts = loctext.texts(si, key, langs)
            bad = []
            for lang in langs:
                if lang not in texts:
                    continue
                faces = fs.faces(b.font, lang)
                if not faces:
                    continue
                row = fit.measure(b, lang, loctext.expand(si, texts[lang][0], lang), faces)
                if row.verdict in ("elided", "overflows"):
                    bad.append(f"{lang} {row.width:.0f} px ({'cut' if row.verdict == 'elided' else 'overflows'})")
            if bad:
                out.append(_r("warning", "text-fit", f"{key} does not fit {b.avail:g} px: " + ", ".join(bad), rel,
                              nd.line, f"textbox text = {key}"))
    return out


def project_rules(mod: Mod) -> tuple[list[dict], list[dict]]:
    """``[[rule]]`` and ``[[suppress]]`` from the mod's ``v3-lint.toml``."""
    import tomllib

    p = mod.path / "v3-lint.toml"
    if not p.is_file():
        return [], []
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return list(data.get("rule", [])), list(data.get("suppress", []))


def as_rel(mod: Mod, path: str | Path) -> str | None:
    """A path (absolute, or relative to the mod) as the mod-relative form, or None if outside the mod."""
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix().lstrip("./") if (mod.path / p).exists() else None
    try:
        return p.resolve().relative_to(mod.path.resolve()).as_posix()
    except ValueError:
        return None
