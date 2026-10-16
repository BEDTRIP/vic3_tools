"""``v3 save``: questions to a text save, read once into an index in the cache."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from vic3tools import save_queries as q
from vic3tools.i18n import t
from vic3tools.save import Save, save_dir


def add_parsers(sub) -> None:
    p = sub.add_parser("save", help="questions to a text save (indexed once, then read by pieces): info, owners of "
                       "levels, buildings, companies, variables, goods, grep",
                       description=q.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ssub = p.add_subparsers(dest="save_command", required=True, metavar="<command>")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    common.add_argument("--rebuild", action="store_true", help="index the save again")

    s = ssub.add_parser("info", parents=[common], help="date, version, mods, the biggest sections")
    s.add_argument("save", help="a path, or a name in the documents' \"save games\" (with or without .v3)")
    s.set_defaults(func=cmd_info)

    s = ssub.add_parser("list", help="the saves in the documents' 'save games', newest first")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_list)

    s = ssub.add_parser("get", parents=[common], help="a section, or one entry of it (by id; country_manager by tag)")
    s.add_argument("save")
    s.add_argument("section")
    s.add_argument("id", nargs="?")
    s.add_argument("--lines", type=int, default=60)
    s.set_defaults(func=cmd_get)

    s = ssub.add_parser("grep", parents=[common], help="pieces of the save around a regex, with their section")
    s.add_argument("save")
    s.add_argument("pattern")
    s.add_argument("--context", type=int, default=200)
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_grep)

    s = ssub.add_parser("vars", parents=[common], help="a country's script variables and maps as numbers "
                        "(--global: the global ones)")
    s.add_argument("save")
    s.add_argument("tag", nargs="?")
    s.add_argument("pattern", nargs="?", default=".")
    s.add_argument("--global", dest="glob", action="store_true")
    s.set_defaults(func=cmd_vars)

    s = ssub.add_parser("owners", parents=[common], help="who owns the production levels, by owner class and country; "
                        "with two saves or more also the gross additions and the transfers between them")
    s.add_argument("saves", nargs="+")
    s.add_argument("--class", dest="classes", action="append", default=[], metavar="NAME=GLOB[,GLOB]",
                   help="put companies of these types into a class of their own (bank=company_Bank*)")
    s.add_argument("--skip", action="append", default=[], help="a building-type prefix that is not production")
    s.add_argument("--top", type=int, default=15)
    s.set_defaults(func=cmd_owners)

    s = ssub.add_parser("buildings", parents=[common], help="buildings of one type by country: levels, weekly sales, "
                        "costs, profit, owners")
    s.add_argument("save")
    s.add_argument("type")
    s.add_argument("--top", type=int, default=20)
    s.set_defaults(func=cmd_buildings)

    s = ssub.add_parser("companies", parents=[common], help="what companies own: levels by building type")
    s.add_argument("save")
    s.add_argument("pattern", nargs="?", default="")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_companies)

    s = ssub.add_parser("goods", parents=[common], help="one goods' weekly flows through buildings by country (the "
                        "save's numeric goods id; --ids BUILDING_TYPE finds the ids)")
    s.add_argument("save")
    s.add_argument("goods", nargs="?")
    s.add_argument("--ids", help="print the output goods ids of a building type")
    s.add_argument("--top", type=int, default=20)
    s.set_defaults(func=cmd_goods)


def _emit(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _open(args, name: str) -> Save:
    return Save.open(name, rebuild=getattr(args, "rebuild", False))


def cmd_list(args, cfg) -> int:
    files = sorted(save_dir().glob("*.v3"), key=lambda f: -f.stat().st_mtime)
    for f in files[:args.limit]:
        print(f"{f.stat().st_size / 1e6:7.1f} MB  {f.name}")
    return 0


def cmd_info(args, cfg) -> int:
    with _open(args, args.save) as s:
        secs = sorted(s.sections(), key=lambda x: x[1] - x[2])
        if args.json:
            _emit({"path": str(s.path), "date": s.date, "version": s.version, "mods": s.mods,
                   "sections": {k: e - st for k, st, e in secs}})
            return 0
        print(f"{s.path.name}: {s.date}, game {s.version}, {s.path.stat().st_size / 1e6:.0f} MB")
        print("  mods: " + (", ".join(s.mods) or "—"))
        print("  " + ", ".join(f"{k} {(e - st) / 1e6:.1f} MB" for k, st, e in secs[:12]))
    return 0


def cmd_get(args, cfg) -> int:
    with _open(args, args.save) as s:
        if args.id is None:
            b = s.section(args.section)
        else:
            eid = s.tag_id(args.id) if args.section == "country_manager" and not args.id.isdigit() else args.id
            b = s.entry(args.section, eid) if eid else None
        if b is None:
            print(t("save_none", what=f"{args.section} {args.id or ''}".strip()))
            return 1
        lines = b.text.split("\n")
        print("\n".join(lines[:args.lines]))
        if len(lines) > args.lines:
            print(t("save_more_lines", shown=args.lines, total=len(lines)))
    return 0


def cmd_grep(args, cfg) -> int:
    with _open(args, args.save) as s:
        hits = list(s.grep(args.pattern, args.context, args.limit))
        if args.json:
            _emit([{"offset": o, "section": sec, "text": tx} for o, sec, tx in hits])
            return 0 if hits else 1
        for o, sec, tx in hits:
            print(f"--- {sec or '?'} @ {o}")
            print(tx)
        return 0 if hits else 1


def cmd_vars(args, cfg) -> int:
    with _open(args, args.save) as s:
        tags = s.countries()
        if args.glob:
            b = s.section("variables")
            if b is not None:
                b = type(b)("{ variables=" + b.text[b.text.find("{"):] + " }")
        else:
            if not args.tag:
                print(t("save_need_tag"))
                return 2
            cid = s.tag_id(args.tag)
            b = s.entry("country_manager", cid) if cid else None
            if b is None:
                print(t("save_none", what=args.tag))
                return 1
        vals, maps = q.variables(b, tags, args.pattern)
        if args.json:
            _emit({"date": s.date, "vars": dict(vals), "maps": {n: rows for n, rows in maps}})
            return 0
        print(f"{s.date} {args.tag or 'global'}: {len(vals)} variable(s), {len(maps)} map(s)")
        for n, v in vals:
            print(f"  {n} = {v}")
        for n, rows in maps:
            print(f"  map {n} ({len(rows)}):")
            for k, v in rows:
                print(f"    {k} = {v}")
    return 0


def _classes(specs: list[str]) -> dict[str, list[str]]:
    out = {}
    for spec in specs:
        name, _, globs = spec.partition("=")
        out[name.strip()] = [g.strip() for g in globs.split(",") if g.strip()]
    return out


def _table(title: str, data: dict[str, Counter], classes: list[str], top: int, order_by: dict | None = None,
           pop: bool = True) -> None:
    print(title)
    print("country " + " ".join(f"{c:>8}" for c in classes) + ("    pop%" if pop else ""))
    ref = order_by or data
    for c in sorted(data, key=lambda c: -sum(ref.get(c, Counter()).values()))[:top + 1]:
        v = data[c]
        priv = sum(v[x] for x in classes if x not in ("gov", "f_gov"))
        share = f"  {100 * sum(v[x] for x in q.POP) / priv if priv else 0:6.1f}" if pop else ""
        print(f"{c:7} " + " ".join(f"{v[x]:8d}" for x in classes) + share)


def cmd_owners(args, cfg) -> int:
    extra = _classes(args.classes)
    hs = []
    for name in args.saves:
        with _open(args, name) as s:
            hs.append(q.holdings(s, extra, tuple(args.skip)))
    classes = q.CLASSES[:2] + list(extra) + q.CLASSES[2:]
    last = q.levels_by_class(hs[-1])
    adds = [(a.date, b.date, q.additions(a, b), q.transfers(a, b)) for a, b in zip(hs, hs[1:], strict=False)]
    if args.json:
        _emit({"levels": {h.date: {c: dict(v) for c, v in q.levels_by_class(h).items()} for h in hs},
               "additions": [{"from": a, "to": b, "adds": {c: dict(v) for c, v in ad.items()},
                              "transfers": {c: dict(v) for c, v in tr.items()}} for a, b, ad, tr in adds]})
        return 0
    for a, b, ad, tr in adds:
        _table(t("save_adds", a=a, b=b), ad, classes, args.top, last)
        _table(t("save_transfers", a=a, b=b), tr, classes, args.top, last, pop=False)
        print()
    _table(t("save_levels", date=hs[-1].date), last, classes, args.top)
    return 0


def cmd_buildings(args, cfg) -> int:
    with _open(args, args.save) as s:
        rows = q.buildings_of(s, args.type)
    if args.json:
        _emit({k: {**v, "owners": dict(v["owners"])} for k, v in rows.items()})
        return 0 if rows else 1
    if not rows:
        print(t("save_none", what=args.type))
        return 1
    print("country  bldgs  levels       sales        cost      profit  owners")
    for tag, v in sorted(rows.items(), key=lambda x: -x[1]["levels"])[:args.top]:
        own = ", ".join(f"{k} {n}" for k, n in v["owners"].most_common())
        print(f"{tag:7} {v['buildings']:6d} {v['levels']:7d} {v['sales']:11.0f} {v['cost']:11.0f} "
              f"{v['profit']:11.0f}  {own}")
    return 0


def cmd_companies(args, cfg) -> int:
    with _open(args, args.save) as s:
        rows = q.company_holdings(s, args.pattern)
    if args.json:
        _emit(rows)
        return 0 if rows else 1
    for r in rows[:args.limit]:
        lv = ", ".join(f"{k.removeprefix('building_')} {n}" for k, n in list(r["levels"].items())[:8])
        print(f"{r['type']}  {r['country']}  hq {r['hq']}: {lv or '—'}")
    if len(rows) > args.limit:
        print(f"… +{len(rows) - args.limit} (--limit)")
    return 0 if rows else 1


def cmd_goods(args, cfg) -> int:
    with _open(args, args.save) as s:
        if args.ids:
            print(" ".join(q.goods_ids(s, args.ids)) or "—")
            return 0
        if not args.goods:
            print(t("save_need_goods"))
            return 2
        rows = q.goods_flows(s, args.goods)
    if args.json:
        _emit({k: {**v, "buyers": dict(v["buyers"])} for k, v in rows.items()})
        return 0 if rows else 1
    print("country       input      output  top buyers")
    for tag, v in sorted(rows.items(), key=lambda x: -(x[1]["input"] + x[1]["output"]))[:args.top]:
        buy = ", ".join(f"{k.removeprefix('building_')} {n:.1f}" for k, n in v["buyers"].most_common(3))
        print(f"{tag:7} {v['input']:11.2f} {v['output']:11.2f}  {buy}")
    return 0 if rows else 1
