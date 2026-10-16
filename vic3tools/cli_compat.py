"""``v3`` commands about a mod set: playsets, mods, winner, conflicts, matrix, audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vic3tools.compat import audits, conflicts, holes, index, set_audits, winner
from vic3tools.core import paths, vfs
from vic3tools.i18n import t


def add_parsers(sub) -> None:
    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("mod set (default: the launcher's active playset)")
    g.add_argument("--playset", help="a launcher playset by name")
    g.add_argument("--set", type=Path, dest="set_file", help="a set file (JSON with load_order, labels)")
    g.add_argument("--mods", type=Path, nargs="+", help="mod folders in load order (vanilla is put in front)")
    common.add_argument("--rebuild", action="store_true", help="re-read every file, ignoring the index cache")
    common.add_argument("--json", action="store_true")

    from vic3tools import cli_bench, cli_gui, cli_index, cli_lint

    cli_index.add_parsers(sub, common)
    cli_gui.add_parsers(sub, common)
    cli_lint.add_parsers(sub, common)
    cli_bench.add_parsers(sub, common)

    p = sub.add_parser("playsets", help="the launcher's playsets (* — active); --content-load writes the game's "
                       "content_load.json for one")
    p.add_argument("--json", action="store_true")
    p.add_argument("--content-load", metavar="PLAYSET", help="write content_load.json with this playset's mods "
                   "(the game reads its mods from that file, not from the active playset)")
    p.add_argument("--without", action="append", default=[], help="leave out mods whose name contains this")
    p.add_argument("--add", action="append", default=[], type=Path, help="a mod folder appended at the end")
    p.add_argument("--out", type=Path, help="where to write (default: the documents' content_load.json)")
    p.set_defaults(func=cmd_playsets)

    p = sub.add_parser("mods", parents=[common], help="the mods of the set, in load order; snapshot / history / "
                       "diff — the set's mods' versions kept in git")
    p.add_argument("action", nargs="?", choices=["list", "snapshot", "history", "diff"], default="list",
                   help="list (default); snapshot — commit each changed mod to the history; history MOD; "
                   "diff MOD [A B] — what changed between two snapshots (default: the last two)")
    p.add_argument("args", nargs="*", help="for history / diff: the mod (name or history folder), commits")
    p.add_argument("--vanilla", action="store_true", help="snapshot: the game's text folders too")
    p.add_argument("--full", action="store_true", help="diff: the lines, not just the files")
    p.set_defaults(func=cmd_mods)

    p = sub.add_parser("winner", parents=[common],
                       help="every definition of a record / loc key / GUI type in load order, and which one wins",
                       description="WHAT is a folder (common/buildings, events…), `loc` or `gui`.")
    p.add_argument("what", help="common/<folder>, events, loc or gui")
    p.add_argument("keys", nargs="+")
    p.add_argument("--lang", default="english", help="for loc: the language folder (english, russian…)")
    p.set_defaults(func=cmd_winner)

    p = sub.add_parser("conflicts", parents=[common], help="what two mods (or groups) both define")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--groups", type=Path, help="a groups file (blocks/order); A and B are group names")
    p.add_argument("--limit", type=int, default=25, help="items shown per kind and folder")
    p.set_defaults(func=cmd_conflicts)

    p = sub.add_parser("matrix", parents=[common], help="shared keys / file paths for every pair of mods or groups")
    p.add_argument("--groups", type=Path, help="a groups file (blocks/order); default: each mod of the set")
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("audit", parents=[common], help="audits of a mod or the set: replace, stale, loc-dead, dups, "
                       "vanilla, holes, prestige, events, lawgroups",
                       description=audits.__doc__ + "\n" + set_audits.__doc__ + "\n" + holes.__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kind", choices=["replace", "stale", "loc-dead", "dups", "vanilla", "holes", "prestige", "events",
                                    "lawgroups"])
    p.add_argument("mod", nargs="?", help="the mod: its name in the set or its folder (replace, stale, loc-dead, "
                   "dups, vanilla, lawgroups)")
    p.add_argument("--declared", type=Path, help="TOML file of deliberate omissions (replace, stale)")
    p.add_argument("--langs", default="english,russian", help="for loc-dead: languages, comma-separated")
    p.add_argument("--other", help="lawgroups: the mod to compare with")
    p.add_argument("--only", choices=["new", "pmg", "companies", "builds", "economy"], help="holes: one section")
    p.add_argument("--source", help="holes, new: only this mod's content")
    p.add_argument("--builds", action="append", default=[], help="holes: a mod of the set that is a build "
                   "(megapack, add-on); repeatable")
    p.add_argument("--require-pmg", action="append", default=[], help="holes: a method group (glob) every private "
                   "building must have; repeatable")
    p.add_argument("--limit", type=int, default=60, help="findings shown")
    p.set_defaults(func=cmd_audit)


# --- helpers -------------------------------------------------------------------------------------------------------


def mod_set(args, cfg: paths.Config) -> vfs.ModSet:
    if getattr(args, "mods", None):
        return vfs.ModSet.from_dirs(args.mods, cfg)
    if getattr(args, "set_file", None):
        return vfs.ModSet.from_set_file(args.set_file, cfg)
    return vfs.ModSet.from_playset(getattr(args, "playset", None), cfg)


def indexes(ms: vfs.ModSet, rebuild: bool = False) -> list[index.ModIndex]:
    return [index.build(m, rebuild) for m in ms.mods]


def _emit(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _loc(name: str, rel: str, line: int = 0) -> str:
    return f"{name}: {rel}" + (f":{line}" if line else "")


# --- commands ------------------------------------------------------------------------------------------------------


def cmd_playsets(args, cfg) -> int:
    roots = paths.resolve_roots(cfg)
    if args.content_load:
        # the run scripts' short forms: "vanilla"; "NAME без X" / "NAME without X"; "NAME + FOLDER" (Documents/…/mod)
        spec, _, extra = args.content_load.partition(" + ")
        spec, _, drop = spec.partition(" без ") if " без " in spec else spec.partition(" without ")
        without = args.without + ([drop] if drop else [])
        if spec == "vanilla":
            name, mods = "vanilla", []
        else:
            name, mods = vfs.playset_mods(vfs.launcher_db(roots), spec)
        dirs = [Path(d) for n, d, _s in mods if not any(w.casefold() in n.casefold() for w in without)]
        if extra:
            dirs.append(roots["documents"].path / "mod" / extra)
        dirs += [Path(a).resolve() for a in args.add]
        out = args.out or (roots["documents"].path / "content_load.json")
        data = {"enabledMods": [{"path": str(d)} for d in dirs], "disabledDLC": [], "enabledUGC": []}
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(t("playsets_content_load", path=out, name=name, count=len(dirs)))
        return 0
    rows = vfs.list_playsets(vfs.launcher_db(roots))
    if args.json:
        _emit([{"name": n, "active": a} for n, a in rows])
    else:
        for n, a in rows:
            print(("* " if a else "  ") + n)
    return 0


def cmd_mods(args, cfg) -> int:
    if args.action != "list":
        return _mod_history(args, cfg)
    ms = mod_set(args, cfg)
    if args.json:
        _emit({"source": ms.source, "mods": [{"name": m.name, "kind": m.kind, "path": m.path} for m in ms.mods]})
        return 0
    print(ms.source)
    for i, m in enumerate(ms.mods):
        missing = "" if m.path.is_dir() else "  (folder missing!)"
        print(f"{i:3} {m.name}  [{m.kind}]  {m.path}{missing}")
    return 0


def cmd_winner(args, cfg) -> int:
    ms = mod_set(args, cfg)
    idx = indexes(ms, args.rebuild)
    out = []
    for key in args.keys:
        if args.what == "loc":
            v = winner.loc_key(ms, idx, key, args.lang)
        elif args.what == "gui":
            v = winner.gui_type(ms, idx, key)
        else:
            v = winner.record(ms, idx, args.what, key)
        out.append(v)
    if args.json:
        _emit([{"what": v.what, "winner": _def_json(v.winner) if v.winner else None,
                "applied": [_def_json(d) for d in v.applied], "definitions": [_def_json(d) for d in v.defs],
                "notes": v.notes} for v in out])
        return 0 if all(v.defs for v in out) else 1
    is_db = args.what not in ("loc", "gui")
    for v in out:
        print(f"{v.what}  [{ms.source}]")
        if not v.defs:
            print("  " + t("winner_none"))
            continue
        if v.winner:
            w = v.winner
            where = _loc(w.file.mod.name, w.file.rel, w.line)
            print("  " + (t("winner_is", where=where, how=w.directive or "bare") if is_db
                          else t("winner_is_plain", where=where)))
            for d in v.applied:
                print("    + " + t("winner_inject", where=_loc(d.file.mod.name, d.file.rel, d.line), how=d.directive))
        for i, d in enumerate(v.defs, 1):
            how = f"  {d.directive or 'bare'}" if is_db else ""
            print(f"  {i}. {d.file.mod.name}{how}  {d.file.rel}:{d.line} — {d.note}")
        for n in v.notes:
            print("  ! " + n)
    return 0 if all(v.defs for v in out) else 1


def _def_json(d: winner.Def) -> dict:
    return {"mod": d.file.mod.name, "file": d.file.rel, "line": d.line, "path": str(d.file.full),
            "directive": d.directive, "note": d.note}


def _groups(args, ms: vfs.ModSet) -> tuple[list[str], dict[str, list[index.ModIndex]]]:
    if args.groups:
        order, groups = conflicts.load_groups(args.groups)
        built = {g: [index.build(m, args.rebuild) for m in conflicts.group_mods(groups[g])] for g in order}
        return order, built
    order = [m.name for m in ms.mods if m.kind != "vanilla"]
    return order, {m.name: [index.build(m, args.rebuild)] for m in ms.mods if m.kind != "vanilla"}


def cmd_conflicts(args, cfg) -> int:
    if args.groups:
        _order, built = _groups(args, None)
        a_ix, b_ix = built[args.a], built[args.b]
        a_name, b_name = args.a, args.b
    else:
        ms = mod_set(args, cfg)
        a_mod, b_mod = ms.find(args.a), ms.find(args.b)
        a_ix, b_ix = [index.build(a_mod, args.rebuild)], [index.build(b_mod, args.rebuild)]
        a_name, b_name = a_mod.name, b_mod.name
    a, b = conflicts.side(a_ix), conflicts.side(b_ix)
    o = conflicts.overlap(a, b)
    if args.json:
        _emit({"a": a_name, "b": b_name, "keys": {k: {"a": a.keys[k], "b": b.keys[k]} for k in o.keys},
               "files": o.files, "loc": {k: {"a": a.loc[k], "b": b.loc[k]} for k in o.loc},
               "gui": {k: {"a": a.gui[k], "b": b.gui[k]} for k in o.gui}})
        return 0
    print(t("conflicts_head", a=a_name, b=b_name, keys=len(o.keys), files=len(o.files), loc=len(o.loc),
            gui=len(o.gui)))
    if not o.total:
        print("  " + t("conflicts_none"))
        return 0
    for f in o.files[: args.limit]:
        print(f"  FILE {f}")
    if len(o.files) > args.limit:
        print(f"  … +{len(o.files) - args.limit}")
    by_folder: dict[str, list[str]] = {}
    for k in o.keys:
        folder, key = k.split("|", 1)
        by_folder.setdefault(folder, []).append(key)
    for folder in sorted(by_folder):
        keys = by_folder[folder]
        print(f"  {folder}: {len(keys)}")
        for key in keys[: args.limit]:
            ka, kb = a.keys[f"{folder}|{key}"][0], b.keys[f"{folder}|{key}"][0]
            print(f"      {key:48} {ka[1]}:{ka[2]}  vs  {kb[1]}:{kb[2]}")
        if len(keys) > args.limit:
            print(f"      … +{len(keys) - args.limit}")
    for kind, items, side_a, side_b in (("gui types", o.gui, a.gui, b.gui), ("loc keys", o.loc, a.loc, b.loc)):
        if items:
            print(f"  {kind}: {len(items)}")
            for k in items[: args.limit]:
                print(f"      {k:48} {side_a[k][0][1]}:{side_a[k][0][2]}  vs  {side_b[k][0][1]}:{side_b[k][0][2]}")
            if len(items) > args.limit:
                print(f"      … +{len(items) - args.limit}")
    return 0


def cmd_matrix(args, cfg) -> int:
    ms = None if args.groups else mod_set(args, cfg)
    order, built = _groups(args, ms)
    sides = {g: conflicts.side(built[g]) for g in order}
    cells = {}
    for a in order:
        for b in order:
            if a != b:
                o = conflicts.overlap(sides[a], sides[b])
                cells[(a, b)] = (len(o.keys), len(o.files))
    if args.json:
        _emit({"order": order, "cells": {f"{a}|{b}": {"keys": k, "files": f} for (a, b), (k, f) in cells.items()}})
        return 0
    print(t("matrix_head"))
    width = max(len(g) for g in order) + 1
    print(" " * width + "| " + " ".join(f"{g[:11]:>12}" for g in order))
    for a in order:
        row = [f"{'-':>12}" if a == b else f"{cells[(a, b)][0]}/{cells[(a, b)][1]:<}".rjust(12) for b in order]
        print(f"{a:<{width}}| " + " ".join(row))
    print(t("matrix_more"))
    return 0


def cmd_audit(args, cfg) -> int:
    ms = mod_set(args, cfg)
    if args.kind in ("holes", "prestige", "events"):
        return _set_audit(args, ms)
    if not args.mod:
        print(t("audit_need_mod", kind=args.kind))
        return 2
    target = ms.find(args.mod)
    if args.kind in ("dups", "vanilla", "lawgroups"):
        return _mod_audit(args, ms, target)
    if target not in ms.mods:
        ms.mods.append(target)
    mod_i = ms.mods.index(target)
    idx = indexes(ms, args.rebuild)
    declared = audits.load_declared(args.declared)
    if args.kind == "replace":
        found = audits.replace(ms, idx, mod_i, declared)
    elif args.kind == "stale":
        found = audits.stale(ms, idx, mod_i, declared)
    else:
        found = audits.loc_dead(ms, idx, mod_i, tuple(args.langs.split(",")))
    live = [x for x in found if not x.declared]
    if args.json:
        _emit([{"file": x.file.rel, "line": x.line, "key": x.key, "missing": x.detail, "against": x.against,
                "declared": x.declared} for x in found])
        return 1 if live else 0
    print(t(f"audit_{args.kind.replace('-', '_')}", mod=target.name, count=len(live),
            declared=len(found) - len(live)))
    for x in live[: args.limit]:
        miss = f" missing {', '.join(x.detail)}" if x.detail else ""
        print(f"  {x.file.rel}:{x.line}  {x.key}{miss}  ← {x.against}")
    if len(live) > args.limit:
        print(f"  … +{len(live) - args.limit} (--limit)")
    return 1 if live else 0



def _mod_audit(args, ms: vfs.ModSet, target: vfs.Mod) -> int:
    if args.kind == "lawgroups":
        if not args.other:
            print(t("audit_need_other"))
            return 2
        other = ms.find(args.other)
        a, b = set_audits.lawgroups(target), set_audits.lawgroups(other)
        only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
        if args.json:
            _emit({"only_" + target.name: {g: a[g] for g in only_a}, "only_" + other.name: {g: b[g] for g in only_b}})
            return 0
        print(t("audit_lawgroups", a=target.name, na=len(a), b=other.name, nb=len(b)))
        for name, only, src in ((target.name, only_a, a), (other.name, only_b, b)):
            print(f"  only in {name}: {len(only)}")
            for g in only[:args.limit]:
                print(f"    {g}  ({', '.join(src[g][:2])})")
        return 0
    ix = index.build(target, args.rebuild)
    if args.kind == "dups":
        d = set_audits.duplicates(ix)
        if args.json:
            _emit(d)
            return 1 if any(d.values()) else 0
        print(t("audit_dups", mod=target.name, records=len(d["records"]), loc=len(d["loc"]), events=len(d["events"])))
        for cat, key, where in d["records"][:args.limit]:
            print(f"  {cat} {key}: {', '.join(where)}")
        for lang, key, where in d["loc"][:args.limit]:
            print(f"  loc [{lang}] {key}: {', '.join(where)}")
        for key, where in d["events"][:args.limit]:
            print(f"  event {key}: {', '.join(where)}")
        return 1 if any(d.values()) else 0
    van = index.build(ms.mods[0], args.rebuild)
    cats, paths_ = set_audits.against_vanilla(van, ix)
    if args.json:
        _emit({"categories": {c: dict(v) for c, v in cats.items()}, "path_overrides": paths_})
        return 0
    print(t("audit_vanilla", mod=target.name, paths=len(paths_)))
    for cat, v in sorted(cats.items(), key=lambda x: -sum(x[1].values()))[:args.limit]:
        print(f"  {cat:45} " + ", ".join(f"{k} {n}" for k, n in v.most_common()))
    for rel in paths_[:args.limit]:
        print(f"  ⇄ {rel}")
    return 0


def _set_audit(args, ms: vfs.ModSet) -> int:
    if args.kind == "prestige":
        order = set_audits.prestige(ms)
        over = {b: v for b, v in order.items() if len(v) > 3}
        if args.json:
            _emit({b: [list(x) for x in v] for b, v in order.items()})
            return 1 if over else 0
        print(t("audit_prestige", bases=len(order), over=len(over), dead=sum(len(v) - 3 for v in over.values())))
        for base, v in sorted(over.items()):
            print(f"  {base}: " + ", ".join(f"{k} ({m})" for k, m, _f in v[:3]) + "  | dead: "
                  + ", ".join(f"{k} ({m})" for k, m, _f in v[3:]))
        return 1 if over else 0
    if args.kind == "events":
        dup = set_audits.event_ids(ms)
        if args.json:
            _emit(dup)
            return 1 if dup else 0
        print(t("audit_events", count=len(dup)))
        for k, where in sorted(dup.items())[:args.limit]:
            print(f"  {k}: " + "; ".join(where))
        return 1 if dup else 0
    srcs = holes.sources(ms)
    out: dict = {}
    if args.only in (None, "new"):
        out["new"] = holes.new_content(srcs, args.source)
    if args.only in (None, "pmg"):
        out["pmg"] = holes.eaten(srcs, "pmg")
    if args.only in (None, "companies"):
        out["companies"] = holes.eaten(srcs, "companies")
    if args.only in (None, "builds") and args.builds:
        out["builds"] = holes.builds_vs_later(srcs, set(args.builds))
    if args.only in (None, "economy") and args.require_pmg:
        out["economy"] = holes.outside_economy(srcs, args.require_pmg)
    if args.json:
        _emit({k: ([[key, b.label, b.directive, b.file, {x: sorted(w) for x, w in lost.items()}]
                    for key, b, lost in v] if k in ("pmg", "companies") else v) for k, v in out.items()})
        return 0
    print(t("audit_holes_chain", count=len(srcs), chain=" → ".join(s.label for s in srcs[1:])))
    if "new" in out:
        print("\n" + t("audit_holes_new"))
        for label, rows in out["new"].items():
            print(f"  {label}: {len(rows)}")
            for cat, key, d, who in rows[:args.limit]:
                print(f"    {cat.removeprefix('common/'):22} {key:44} [{d or 'bare'}]  "
                      + (", ".join(who) if who else t("audit_holes_nobody")))
    for kind in ("pmg", "companies"):
        if kind in out:
            print("\n" + t(f"audit_holes_{kind}", count=len(out[kind])))
            for key, last, lost in out[kind][:args.limit]:
                print(f"  {key}  ← {last.label} {last.directive or 'bare'} ({last.file})")
                for x, who in sorted(lost.items()):
                    print(f"      - {x:46} [{', '.join(sorted(who))}]")
    if "builds" in out:
        print("\n" + t("audit_holes_builds"))
        for build, per in out["builds"].items():
            print(f"  {build}")
            for other, hits in per.items():
                print(f"    × {other}: {sum(len(v) for v in hits.values())}")
                for cat, keys in sorted(hits.items()):
                    print(f"        {cat.removeprefix('common/')}: {', '.join(sorted(keys)[:12])}"
                          + (" …" if len(keys) > 12 else ""))
    if "economy" in out:
        print("\n" + t("audit_holes_economy", count=len(out["economy"]), groups=", ".join(args.require_pmg)))
        for label, key, missing, owners in out["economy"][:args.limit]:
            print(f"  {key:46} lacks {', '.join(missing):40} [{label}]  companies: "
                  + (", ".join(owners) if owners else t("audit_holes_nobody")))
    return 0


def _mod_history(args, cfg) -> int:
    from vic3tools import mod_history as mh

    repo = mh.repo_dir()
    if args.action == "snapshot":
        ms = mod_set(args, cfg)
        roots = paths.resolve_roots(cfg)
        game = roots["game"].path if roots["game"].ok else None
        gv = paths.game_version(game) if game else None
        mods = [(m.name, m.path) for m in ms.mods if m.kind not in ("engine", "vanilla")]
        snaps = mh.snapshot(mods, game, gv, args.vanilla, repo)
        new = [s for s in snaps if s.changed]
        print(t("history_snapshot", repo=repo, mods=len(snaps), new=len(new), game=gv or "?"))
        for s in new:
            print(t("history_new", name=s.name, version=s.version, files=s.changed, folder=s.folder))
        return 0
    if not args.args:
        print(t("history_need_mod"))
        return 2
    if not (repo / ".git").is_dir():
        print(t("history_none", repo=repo))
        return 1
    folder = mh.find_folder(repo, args.args[0])
    if folder is None:
        print(t("history_no_mod", mod=args.args[0]))
        return 1
    if args.action == "history":
        for line in mh.history(repo, folder):
            print(line)
        return 0
    a = args.args[1] if len(args.args) > 1 else None
    b = args.args[2] if len(args.args) > 2 else None
    out = mh.diff(repo, folder, a, b, stat=not args.full)
    print(out.rstrip() if out else t("history_one_snapshot", mod=args.args[0]))
    return 0

