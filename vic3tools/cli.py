"""The ``v3`` command: one entry point for all tools.

Output is short by default (meant for a coding agent as much as for a person); ``--json`` gives the same data for
other programs.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from vic3tools import __version__, cli_compat, cli_log, cli_save, docs_check, glossary
from vic3tools.core import paths
from vic3tools.i18n import set_lang, t


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="v3", description="Tools for Victoria 3 modding.")
    parser.add_argument("--version", action="version", version=f"vic3tools {__version__}")
    parser.add_argument("--lang", choices=["en", "ru"], help="language of the output (default: config, then system)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("where", help="show the roots found (game, workshop, documents), the config and the cache")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_where)

    p = sub.add_parser("setup", help="set this machine up: find the roots, write the config, build the cache")
    p.add_argument("--no-glossary", action="store_true", help="skip building the glossary")
    p.add_argument("--no-index", action="store_true", help="skip indexing the active playset")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor", help="check what is ready and what is not, and why")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("glossary", help="the game's own name for a term, in English and Russian (and the rest)")
    p.add_argument("query", help="a word or phrase in any language, or a localization key")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--all-langs", action="store_true", help="show every language, not only en and ru")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_glossary)

    cli_compat.add_parsers(sub)
    cli_save.add_parsers(sub)
    cli_log.add_parsers(sub)

    p = sub.add_parser("hook", help="Claude Code hooks (reads the hook's JSON on stdin)")
    hsub = p.add_subparsers(dest="hook_event", required=True, metavar="<event>")
    h = hsub.add_parser("pre-tool-use", help="a grep for a name / a read of a whole big file in game or mod "
                        "folders: answer from the index instead, once per session")
    h.set_defaults(func=cmd_hook)
    h = hsub.add_parser("post-tool-use", help="after an edit of a playset mod's file: its fast lint rules, known "
                        "reports left out, as context for the agent")
    h.set_defaults(func=cmd_hook_post)

    p = sub.add_parser("docs", help="checks of this repo's documents")
    dsub = p.add_subparsers(dest="docs_command", required=True, metavar="<check>")
    d = dsub.add_parser("check-ru", help="are the Russian translations in docs/ru/ current")
    d.add_argument("--repo", type=Path, default=Path.cwd(), help="repo root (default: current folder)")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_docs_check_ru)

    args = parser.parse_args(argv)
    cfg = paths.load_config()
    set_lang(args.lang or cfg.values.get("lang"))
    try:
        return args.func(args, cfg) or 0
    except (KeyError, FileNotFoundError) as e:  # a name or a folder that is not there: say so, no traceback
        print(f"v3 {args.command}: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2


def _emit_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cmd_where(args, cfg: paths.Config) -> int:
    roots = paths.resolve_roots(cfg)
    version = paths.game_version(roots["game"].path) if roots["game"].ok else None
    if args.json:
        _emit_json({
            "roots": {n: {"path": r.path, "exists": r.ok, "source": r.source} for n, r in roots.items()},
            "game_version": version,
            "config": [str(f) for f in cfg.files],
            "cache": str(paths.cache_dir()),
        })
        return 0
    for name, r in roots.items():
        where = str(r.path) if r.ok else f"{t('not_found')} ({r.source})"
        source = f"  [{r.source}]" if r.ok else ""
        print(f"{t('root_' + name)}: {where}{source}")
    if version:
        print(t("game_version", version=version))
    print(t("config_files", files=", ".join(map(str, cfg.files))) if cfg.files else t("config_none"))
    print(t("cache_at", path=paths.cache_dir()))
    return 0


def tiger_path() -> Path:
    return paths.bin_dir() / ("vic3-tiger.exe" if sys.platform == "win32" else "vic3-tiger")


def cmd_setup(args, cfg: paths.Config) -> int:
    roots = paths.resolve_roots(cfg)
    print(t("setup_found"))
    for name, r in roots.items():
        print(f"  {t('root_' + name)}: {r.path if r.ok else t('not_found')}")
    found = {n: r.path for n, r in roots.items() if r.ok}
    # Keep any value the user set by hand, even if it does not exist right now.
    for name in paths.ROOT_NAMES:
        if cfg.get("roots", name):
            found[name] = Path(cfg.get("roots", name))
    user_cfg = {}
    if paths.user_config_path().is_file():
        import tomllib

        user_cfg = tomllib.loads(paths.user_config_path().read_text(encoding="utf-8"))
    written = paths.write_user_config(found, cfg.values.get("lang"), keep=user_cfg)
    print(t("setup_wrote_config", path=written))
    for name, r in roots.items():
        if not r.ok:
            print(t("setup_missing_root", name=t("root_" + name), path=written))
    if not args.no_glossary:
        if roots["game"].ok:
            version = paths.game_version(roots["game"].path) or "unknown"
            db, count = glossary.build(roots["game"].path, version)
            print(t("setup_glossary", count=count, path=db))
        else:
            print(t("setup_glossary_skip"))
    if not args.no_index and roots["game"].ok and roots["documents"].ok:
        from vic3tools.core.vfs import ModSet
        from vic3tools.index import db

        try:
            ms = ModSet.from_playset(None, paths.load_config())
        except KeyError as e:
            print(t("setup_index_skip", why=e.args[0]))
        else:
            for m in ms.mods:
                db.open_index(m).close()
            print(t("setup_index", source=ms.source, count=len(ms.mods)))
    tiger = tiger_path()
    print(t("setup_tiger_ok", path=tiger) if tiger.is_file() else t("setup_tiger_missing", path=tiger.parent))
    print(t("setup_done"))
    return 0


def cmd_doctor(args, cfg: paths.Config) -> int:
    checks: list[tuple[str, bool, str]] = []  # name, ok, line
    py_ok = sys.version_info >= (3, 11)
    checks.append(("python", py_ok, t("doctor_python", version=platform.python_version())))
    roots = paths.resolve_roots(cfg)
    for name, r in roots.items():
        line = t("doctor_root", name=t("root_" + name), path=r.path) if r.ok else \
            t("doctor_root_missing", name=t("root_" + name), source=r.source)
        checks.append((name, r.ok, line))
    if roots["game"].ok:
        version = paths.game_version(roots["game"].path) or "unknown"
        db = glossary.db_path(version)
        checks.append(("glossary", db.is_file(), t("doctor_glossary", version=version, path=db) if db.is_file()
                       else t("doctor_glossary_missing", version=version)))
    tiger = tiger_path()
    checks.append(("tiger", tiger.is_file(), t("doctor_tiger", path=tiger) if tiger.is_file()
                   else t("doctor_tiger_missing", path=tiger)))
    failed = sum(1 for _, ok, _ in checks if not ok)
    if args.json:
        _emit_json({name: {"ok": ok, "detail": line} for name, ok, line in checks})
    else:
        for _, ok, line in checks:
            print(f"[{t('doctor_ok') if ok else t('doctor_fail')}] {line}")
        print(t("doctor_summary_ok") if not failed else t("doctor_summary_fail", count=failed))
    return 1 if failed else 0


def cmd_glossary(args, cfg: paths.Config) -> int:
    roots = paths.resolve_roots(cfg)
    version = paths.game_version(roots["game"].path) if roots["game"].ok else None
    db = glossary.db_path(version) if version else None
    if db is None or not db.is_file():
        db = None
        if not args.json:
            print(t("glossary_no_db"))
    hits = glossary.search(args.query, db, limit=args.limit + 1)
    more = len(hits) > args.limit
    hits = hits[: args.limit]
    if args.json:
        _emit_json([{"key": h.key, "section": h.section, "texts": h.texts} for h in hits])
        return 0 if hits else 1
    if not hits:
        print(t("glossary_none", query=args.query))
        return 1
    for h in hits:
        langs = h.texts if args.all_langs else {k: v for k, v in h.texts.items() if k in ("en", "ru")}
        texts = " | ".join(f"{k}: {v}" for k, v in langs.items())
        print(f"{h.key}{' (tools)' if h.section == 'tools' else ''} — {texts}")
    if more:
        print(t("glossary_more", shown=args.limit))
    return 0


def cmd_hook(args, cfg: paths.Config) -> int:
    from vic3tools import hook

    return hook.main()


def cmd_hook_post(args, cfg: paths.Config) -> int:
    from vic3tools import hook_lint

    return hook_lint.main()


def cmd_docs_check_ru(args, cfg: paths.Config) -> int:
    problems, checked = docs_check.check(args.repo)
    failures = [p for p in problems if p.kind != "untranslated"]
    if args.json:
        _emit_json({"checked": checked, "problems": [p.__dict__ for p in problems]})
        return 1 if failures else 0
    for p in problems:
        print(t(f"docs_ru_{p.kind}", path=p.path, source=p.source, old=p.old, new=p.new))
    if not failures:
        print(t("docs_ru_ok", count=checked))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
