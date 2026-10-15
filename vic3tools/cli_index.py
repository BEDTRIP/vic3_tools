"""``v3`` commands over the index: def, refs, loc, outline."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from vic3tools.cli_compat import indexes, mod_set
from vic3tools.compat import winner
from vic3tools.i18n import t
from vic3tools.index import query


def add_parsers(sub, common: argparse.ArgumentParser) -> None:
    p = sub.add_parser("def", parents=[common], help="where a name is defined (records, GUI types/templates, loc keys) "
                       "and which definition wins")
    p.add_argument("names", nargs="+")
    p.add_argument("--all-langs", action="store_true", help="list loc definitions of every language")
    p.set_defaults(func=cmd_def)

    p = sub.add_parser("refs", parents=[common], help="where a name is used: file:line, the record it sits in, the "
                       "keys above it; a glob (prefix_*) lists every matching name")
    p.add_argument("name")
    p.add_argument("--writes", action="store_true", help="only places that set it (set_variable, add_to_…)")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_refs)

    p = sub.add_parser("loc", parents=[common], help="the text of a loc key (English, Russian) and which one shows; "
                       "--text finds the key behind a text as the player sees it")
    p.add_argument("key", nargs="?")
    p.add_argument("--text", help="text as shown in the game (placeholders filled)")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_loc)

    p = sub.add_parser("outline", help="the tree of records / GUI widgets of a file with line ranges — read this "
                       "before opening a big file")
    p.add_argument("file", type=Path)
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--find", help="only nodes whose key or name contains this, with the path to them")
    p.add_argument("--at", type=int, help="the nodes that contain this line")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_outline)


def _open(args, cfg) -> query.SetIndex:
    return query.SetIndex.open(mod_set(args, cfg), args.rebuild)


def _emit(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _hit_json(h: query.Hit) -> dict:
    return {"mod": h.mod.name, "file": h.rel, "line": h.line, "end_line": h.end_line or None, "kind": h.kind,
            "folder": h.folder, "directive": h.directive, "ctx": h.ctx, "path": h.path,
            "never_loads": h.why_not or False, "full_path": str(h.mod.path / h.rel)}


def cmd_def(args, cfg) -> int:
    si = _open(args, cfg)
    try:
        result = {}
        for name in args.names:
            result[name] = si.defs(name)
        if args.json:
            _emit({n: [_hit_json(h) for h in hs] for n, hs in result.items()})
            return 0 if all(result.values()) else 1
        idx = None
        for name, hits in result.items():
            if not hits:
                print(t("def_none", name=name))
                continue
            kinds = Counter(h.kind for h in hits)
            print(f"{name}: " + ", ".join(f"{k} ×{c}" for k, c in kinds.items()))
            loc_langs = {"english", "russian"}
            for h in hits:
                if h.kind == "loc" and not args.all_langs and h.folder not in loc_langs:
                    continue
                dead = f"  (never loads: {h.why_not})" if h.why_not else ""
                what = h.folder if h.kind in ("db", "loc") else h.kind
                print(f"  {h.mod.name}: {h.where}  [{what}{' ' + h.directive if h.directive else ''}]{dead}")
            # who wins, when there is more than one definition of a kind
            def group(h: query.Hit) -> tuple[str, str]:  # GUI types compete across folders
                return h.kind, h.folder if h.kind != "gui_type" else ""

            need = {group(h) for h in hits if h.kind in ("db", "gui_type", "loc")}
            for kind, folder in sorted(need):
                same = [h for h in hits if group(h) == (kind, folder)]
                if len(same) < 2 or (kind == "loc" and folder not in loc_langs):
                    continue
                idx = idx or indexes(si.ms)
                if kind == "db":
                    v = winner.record(si.ms, idx, folder, name)
                elif kind == "gui_type":
                    v = winner.gui_type(si.ms, idx, name)
                else:
                    v = winner.loc_key(si.ms, idx, name, folder)
                if v.winner:
                    w = v.winner
                    print("  → " + t("def_wins", what=f"{folder} " if kind != "gui_type" else "",
                                     where=f"{w.file.mod.name}: {w.file.rel}:{w.line}"))
                    for d in v.applied:
                        print("    + " + t("winner_inject", where=f"{d.file.mod.name}: {d.file.rel}:{d.line}",
                                           how=d.directive))
        return 0 if all(result.values()) else 1
    finally:
        si.close()


def cmd_refs(args, cfg) -> int:
    si = _open(args, cfg)
    try:
        if any(c in args.name for c in "*?"):
            names = si.names_like(args.name)
            per = {n: [h for h in si.refs(n) if not args.writes or h.writes] for n in names}
            if args.json:
                _emit({n: [_hit_json(h) for h in hs] for n, hs in per.items()})
                return 0 if names else 1
            if not names:
                print(t("refs_none", name=args.name))
                return 1
            print(t("refs_glob", count=len(names), pattern=args.name))
            for n, hs in per.items():
                live = [h for h in hs if h.loads]
                w = sum(h.writes for h in live)
                files = len({(h.mod.name, h.rel) for h in live})
                dead = len(hs) - len(live)
                print(f"  {n}: {len(live)} refs ({w} writes) in {files} file(s)"
                      + (f"; +{dead} in files that never load" if dead else ""))
            print(t("refs_glob_more"))
            return 0
        hits = si.refs(args.name)
        scanned = False
        if not hits and not si.defs(args.name):
            hits, scanned = si.scan_refs(args.name), True
        if args.writes:
            hits = [h for h in hits if h.writes]
        if args.json:
            _emit([_hit_json(h) for h in hits])
            return 0 if hits else 1
        if not hits:
            print(t("refs_none", name=args.name))
            return 1
        live = [h for h in hits if h.loads]
        writes = sum(h.writes for h in live)
        print(t("refs_head", name=args.name, count=len(live), writes=writes,
                files=len({(h.mod.name, h.rel) for h in live})) + (" " + t("refs_scanned") if scanned else ""))
        if len(live) < len(hits):
            print("  " + t("refs_dead", count=len(hits) - len(live)))
        hits = live + [h for h in hits if not h.loads]  # the ones that never load go last
        by_ctx: dict[tuple, list[query.Hit]] = defaultdict(list)
        for h in hits:
            by_ctx[(h.mod.name, h.rel, h.ctx)].append(h)
        shown = 0
        for (mod, rel, ctx), hs in by_ctx.items():
            if shown >= args.limit:
                break
            lines = ", ".join(f"{h.line}{' (write)' if h.writes else ''}" + (f" [{h.path}]" if h.path else "")
                              for h in hs[:6])
            more = f" … +{len(hs) - 6}" if len(hs) > 6 else ""
            dead = f"  (never loads: {hs[0].why_not})" if hs[0].why_not else ""
            print(f"  {mod}: {rel}  in {ctx or '—'}: {lines}{more}{dead}")
            shown += 1
        if len(by_ctx) > args.limit:
            print(f"  … +{len(by_ctx) - args.limit} (--limit)")
        return 0
    finally:
        si.close()


def cmd_loc(args, cfg) -> int:
    if not args.key and not args.text:
        print(t("loc_need_key"))
        return 2
    si = _open(args, cfg)
    try:
        if args.text:
            found = si.loc_search(args.text, args.limit)
            if args.json:
                _emit([{"key": h.name, "lang": h.folder, "covered": c, "text": tx, **_hit_json(h)}
                       for c, h, tx in found])
                return 0 if found else 1
            if not found:
                print(t("loc_text_none"))
                return 1
            for _c, h, tx in found:
                print(f"{h.name}  [{h.folder}]  {h.mod.name}: {h.rel}:{h.line}")
                print(f"    {tx}")
            return 0
        rows = si.loc_texts(args.key)
        if args.json:
            _emit([{"text": tx, **_hit_json(h)} for h, tx in rows])
            return 0 if rows else 1
        if not rows:
            print(t("def_none", name=args.key))
            return 1
        idx = indexes(si.ms)
        for lang in sorted({h.folder for h, _ in rows}):
            v = winner.loc_key(si.ms, idx, args.key, lang)
            w = v.winner
            print(f"{args.key} [{lang}]")
            for h, tx in rows:
                if h.folder != lang:
                    continue
                mark = "→" if w and w.file.mod.name == h.mod.name and w.file.rel == h.rel else " "
                print(f"  {mark} {h.mod.name}: {h.rel}:{h.line}")
                print(f"      {tx}")
        return 0
    finally:
        si.close()


def _lab(nd: query.Node) -> str:
    return f' "{nd.label}"' if nd.label else ""


def cmd_outline(args, cfg) -> int:
    nodes = query.outline(args.file)
    if args.find:
        found = list(query.find_nodes(nodes, args.find))
        if args.json:
            _emit([{"path": [n.key for n in trail], "line": nd.line, "end_line": nd.end_line, "name": nd.label}
                   for trail, nd in found])
            return 0 if found else 1
        for trail, nd in found[:60]:
            path = " > ".join(n.key + (f' "{n.label}"' if n.label else "") for n in trail)
            print(f"{nd.line}-{nd.end_line}  {path}")
        if len(found) > 60:
            print(f"… +{len(found) - 60}")
        return 0 if found else 1
    if args.at:
        trail = []
        level = nodes
        while True:
            hit = next((n for n in level if n.line <= args.at <= n.end_line), None)
            if not hit:
                break
            trail.append(hit)
            level = hit.children
        for depth, nd in enumerate(trail):
            print(f"{'  ' * depth}{nd.key}{_lab(nd)}  {nd.line}-{nd.end_line}")
        return 0 if trail else 1
    rows = list(query.flatten(nodes, args.depth))
    if args.json:
        _emit([{"level": lv, "key": nd.key, "name": nd.label, "line": nd.line, "end_line": nd.end_line,
                "children": len(nd.children)} for lv, nd in rows])
        return 0
    limit = 300
    for lv, nd in rows[:limit]:
        kids = f"  ({len(nd.children)})" if nd.children and lv + 1 >= args.depth else ""
        label = f' "{nd.label}"' if nd.label else ""
        print(f"{'  ' * lv}{nd.key}{label}  {nd.line}-{nd.end_line}{kids}")
    if len(rows) > limit:
        print(t("outline_more", shown=limit, total=len(rows)))
    return 0
