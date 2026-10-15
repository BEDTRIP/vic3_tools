"""``v3 lint``: tiger and our own rules over one mod of the set, minus the baseline and suppressions, by place."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from vic3tools.cli_compat import mod_set
from vic3tools.i18n import t
from vic3tools.index import query
from vic3tools.lint import rules, run


def add_parsers(sub, common: argparse.ArgumentParser) -> None:
    p = sub.add_parser("lint", parents=[common], help="check a mod: vic3-tiger with the mods before it loaded, plus "
                       "rules of our own; known reports (baseline, suppressions) left out; short, by place",
                       description=run.__doc__ + "\nOur rules:\n" + rules.__doc__.split("\n", 2)[2],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mod", nargs="?", help="the mod: its name in the set or its folder (default: the last of the set)")
    p.add_argument("--file", action="append", help="only reports in this file (a path or mod-relative); repeatable")
    p.add_argument("--key", help="only these report keys (comma-separated, globs: missing-*)")
    p.add_argument("--severity", choices=list(run.SEVERITY), default="untidy",
                   help="the least severity shown (default: untidy — tips left out)")
    p.add_argument("--rules", default=",".join(rules.RULES), help="our rules to run (comma-separated)")
    p.add_argument("--langs", default="english,russian", help="languages for text-fit and loc-dead")
    p.add_argument("--no-tiger", action="store_true", help="our rules only (fast)")
    p.add_argument("--refresh", action="store_true", help="run tiger even if nothing changed since the last run")
    p.add_argument("--all", action="store_true", help="also the reports in the baseline and the suppressed ones")
    p.add_argument("--baseline", action="store_true", help="accept every current report as known: write "
                   f"{run.BASELINE} in the mod's root")
    p.add_argument("--limit", type=int, default=40, help="reports shown")
    p.set_defaults(func=cmd_lint)


def cmd_lint(args, cfg) -> int:
    import fnmatch

    ms = mod_set(args, cfg)
    target = ms.find(args.mod) if args.mod else ms.mods[-1]
    if target not in ms.mods:
        ms.mods.append(target)
    mod_i = ms.mods.index(target)
    files = None
    if args.file:
        files = set()
        for f in args.file:
            rel = rules.as_rel(target, f)
            if rel is None:
                raise FileNotFoundError(t("lint_not_in_mod", file=f, mod=target.name))
            files.add(rel)
    si = query.SetIndex.open(ms, args.rebuild)
    try:
        only = tuple(x.strip() for x in args.rules.split(",") if x.strip())
        langs = tuple(x.strip() for x in args.langs.split(",") if x.strip())
        reports, notes = run.collect(si, mod_i, not args.no_tiger, args.refresh, only, langs, files)
    finally:
        si.close()
    if args.baseline:
        if files is not None or args.no_tiger:
            print(t("lint_baseline_whole"))
            return 2
        kept = run.split(target, reports, use_baseline=False)
        n = run.write_baseline(target, kept.shown)
        print(t("lint_baseline_written", count=n, path=target.path / run.BASELINE))
        return 0
    least = run.SEVERITY[args.severity]
    keys = [k.strip() for k in (args.key or "").split(",") if k.strip()]
    reports = [r for r in reports if run.SEVERITY.get(r.severity, 9) <= least
               and (not keys or any(fnmatch.fnmatch(r.key, k) for k in keys))]
    res = run.split(target, reports, use_baseline=not args.all)
    shown = res.shown + ([r for r, _w in res.suppressed] if args.all else [])
    shown.sort(key=lambda r: (r.path, r.line, run.SEVERITY.get(r.severity, 9)))
    if args.json:
        print(json.dumps({"mod": target.name, "notes": notes, "baselined": len(res.baselined),
                          "suppressed": len(res.suppressed), "reports": [r.__dict__ for r in shown]},
                         ensure_ascii=False, indent=2, default=str))
        return 1 if any(r.severity == "error" for r in res.shown) else 0
    by_src = Counter(r.source for r in reports)
    print(t("lint_head", mod=target.name, tiger=by_src.get("tiger", 0), own=by_src.get("v3", 0),
            baselined=len(res.baselined), suppressed=len(res.suppressed), shown=len(shown)))
    for n in notes:
        print("  " + n)
    if shown:
        kinds = Counter((r.severity, r.key) for r in shown)
        print("  " + ", ".join(f"{s} {k} {c}" for (s, k), c in kinds.most_common(10))
              + (" …" if len(kinds) > 10 else ""))
    last = None
    for r in shown[:args.limit]:
        if r.path != last:
            print(r.path)
            last = r.path
        msg = r.message if len(r.message) <= 140 else r.message[:137] + "…"
        print(f"  {r.line:>5}  {r.severity:<7} {r.key:<18} {msg}")
    if len(shown) > args.limit:
        print(t("lint_more", shown=args.limit, total=len(shown)))
    if not shown and not res.baselined and not res.suppressed:
        print("  " + t("lint_clean"))
    return 1 if any(r.severity == "error" for r in res.shown) else 0
