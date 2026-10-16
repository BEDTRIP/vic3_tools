"""``v3 log``: the game's logs as families, places in a mod, a comparison of two runs, run speed."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from vic3tools import logs, profile
from vic3tools.core import paths
from vic3tools.i18n import t

KINDS = "debug,warning,game,error"


def add_parsers(sub) -> None:
    p = sub.add_parser("log", help="the game's logs: families of records, places in a mod, two runs compared, run "
                       "speed", description=logs.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    lsub = p.add_subparsers(dest="log_command", required=True, metavar="<command>")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--kinds", default=KINDS, help=f"which logs (default {KINDS})")
    common.add_argument("--skip", help="a regex of records to leave out (a mod's own log lines, e.g. '(^|: )EF..?\\|')")
    common.add_argument("--top", type=int, default=30)
    common.add_argument("--json", action="store_true")

    g = lsub.add_parser("summary", parents=[common], help="records and families per log, by source, one example "
                        "each; 'set but never used' names apart")
    g.add_argument("folder", nargs="?", type=Path, help="a logs folder or a run's folder (default: the game's logs)")
    g.set_defaults(func=cmd_summary)

    g = lsub.add_parser("diff", parents=[common], help="two runs' logs: families only in the second, grown (> 2× "
                        "and +10), gone")
    g.add_argument("base", type=Path)
    g.add_argument("run", type=Path)
    g.set_defaults(func=cmd_diff)

    g = lsub.add_parser("sites", help="error records by the mod's file and line they point at")
    g.add_argument("folder", nargs="?", type=Path)
    g.add_argument("--kind", default="error")
    g.add_argument("--all", action="store_true", help="also records that name no place")
    g.add_argument("--mod", type=Path, help="the mod's folder: map script lines to the file's lines")
    g.add_argument("--top", type=int, default=60)
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_sites)

    g = lsub.add_parser("speed", help="real seconds per game month of runs (debug lines with a game date)")
    g.add_argument("folders", nargs="+", type=Path)
    g.add_argument("--from", dest="start", default="1836.2", help="leave out the start (YEAR.MONTH)")
    g.set_defaults(func=cmd_speed)

    g = lsub.add_parser("profile", help="screenshots of the script profiler window (mods/profiler_view) read by "
                        "Windows OCR: a table of entries with file:line, own / total seconds, calls, ms per tick",
                        description=profile.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g.add_argument("shots", nargs="+", type=Path, help="PNG shots of the profiler window (root, edge, a path)")
    g.add_argument("--compare", nargs="+", type=Path, help="shots of another run: own ms per tick side by side")
    g.add_argument("--by-file", action="store_true", help="own time summed by file")
    g.add_argument("--csv", type=Path, help="write every entry to a CSV file")
    g.add_argument("--top", type=int, default=25)
    g.add_argument("--json", action="store_true")
    g.add_argument("--playset", help="the set whose file names OCR slips are snapped to (default: the active one)")
    g.add_argument("--mods", nargs="+", type=Path, help="mod folders instead of a playset")
    g.set_defaults(func=cmd_profile)


def _folder(f: Path | None) -> Path:
    if f is not None:
        return f
    docs = paths.resolve_roots()["documents"]
    if not docs.ok:
        raise FileNotFoundError("no logs folder given and the documents folder was not found")
    return docs.path / "logs"


def cmd_summary(args, cfg) -> int:
    folder = _folder(args.folder)
    res = [logs.summarize(folder, k, args.skip) for k in args.kinds.split(",")]
    if args.json:
        print(json.dumps([{"kind": s.kind, "files": s.files, "records": s.records, "skipped": s.skipped,
                           "families": dict(s.families.most_common(args.top)), "sources": dict(s.sources),
                           "unused": [list(k) + [n] for k, n in s.unused.items()]} for s in res],
                         ensure_ascii=False, indent=2))
        return 0
    for s in res:
        print(t("log_summary", kind=s.kind, files=s.files, records=s.records, families=len(s.families))
              + (f"; {t('log_skipped', count=s.skipped)}" if s.skipped else ""))
        if not s.records:
            continue
        print("  " + ", ".join(f"{src} {n}" for src, n in s.sources.most_common(6)))
        for k, n in s.families.most_common(args.top):
            print(f"  {n:7d}  {k}")
        if s.unused:
            print("  " + t("log_unused", count=len(s.unused)) + " " + ", ".join(
                f"{name} ({how})" for (_w, name, how) in sorted(s.unused)[:20]))
    return 0


def cmd_diff(args, cfg) -> int:
    res = [logs.compare(args.base, args.run, k, args.skip) for k in args.kinds.split(",")]
    if args.json:
        print(json.dumps([{"kind": d.kind, "base": d.a.records, "run": d.b.records, "new": d.new[:args.top],
                           "grown": d.grown[:args.top], "gone": d.gone[:args.top]} for d in res],
                         ensure_ascii=False, indent=2))
        return 0
    for d in res:
        print(t("log_diff_head", kind=d.kind, a=d.a.records, fa=len(d.a.families), b=d.b.records,
                fb=len(d.b.families)))
        for title, rows in ((t("log_new"), [(n, k, "") for k, n in d.new]),
                            (t("log_grown"), [(n, k, f" (was {a})") for k, a, n in d.grown]),
                            (t("log_gone"), [(n, k, "") for k, n in d.gone])):
            if rows:
                print(f"  {title}: {len(rows)}")
                for n, k, extra in rows[:args.top]:
                    print(f"    {n:7d}  {k}{extra}")
    return 0


def cmd_sites(args, cfg) -> int:
    total, places, per_file = logs.sites(_folder(args.folder), args.kind, args.all)
    if args.json:
        print(json.dumps({"records": total, "places": [[p, m, n] for (p, m), n in places.most_common(args.top)],
                          "files": dict(per_file)}, ensure_ascii=False, indent=2))
        return 0
    print(t("log_sites", records=total, located=sum(per_file.values()), places=len(places), files=len(per_file)))
    for f, n in per_file.most_common(15):
        print(f"  {n:7d}  {f}")
    print()
    for (place, msg), n in places.most_common(args.top):
        extra = ""
        if args.mod and place != "-" and place.rsplit(":", 1)[-1].isdigit() and "/script" in place:
            f, ln = place.rsplit(":", 1)
            real = logs.real_lines(args.mod / f, int(ln))
            if real and real != [int(ln)]:
                extra = "  (" + t("log_real_lines", lines=",".join(map(str, real[:3]))) + ")"
        print(f"  {n:7d}  {place}  {msg}{extra}")
    return 0


def cmd_speed(args, cfg) -> int:
    y, m = (int(x) for x in args.start.split(".")[:2])
    g0 = date(y, m, 1).toordinal()
    for folder in args.folders:
        pts = sorted(p for p in logs.speed_points(folder) if p[0] >= g0)
        s = logs.slope(pts)
        if s is None:
            print(t("log_speed_few", run=folder.name, count=len(pts)))
            continue
        d1, d2 = date.fromordinal(pts[0][0]), date.fromordinal(pts[-1][0])
        print(t("log_speed", run=folder.name, count=len(pts), a=d1, b=d2, sec=f"{s:.2f}"))
        q0 = pts[0][0]
        while q0 < pts[-1][0]:
            q = [p for p in pts if q0 <= p[0] < q0 + 91]
            qs = logs.slope(q)
            if qs is not None and len(q) >= 5:
                print(f"    {date.fromordinal(q0)}: {qs:.2f} s/month ({len(q)})")
            q0 += 91
    return 0


def _set_files(args, cfg) -> list[str]:
    """Base names of the set's script and GUI files (with the engine's), to snap OCR'd file names to."""
    from vic3tools.cli_compat import mod_set
    from vic3tools.index import query

    try:
        si = query.SetIndex.open(mod_set(args, cfg))
    except (OSError, KeyError, ValueError):
        return []
    try:
        names = {rel.rsplit("/", 1)[-1] for con in si.cons for (rel,) in con.execute("SELECT rel FROM files")}
    finally:
        si.close()
    return sorted(n for n in names if n.endswith((".txt", ".gui")))


def cmd_profile(args, cfg) -> int:
    files = _set_files(args, cfg)
    shots = profile.read(args.shots, files)
    other = profile.read(args.compare, files) if args.compare else []
    if args.csv:
        profile.write_csv(shots + other, args.csv)
    if args.json:
        print(json.dumps([{"shot": str(s.path), "capture": s.capture, "ticks": s.ticks, "current": s.current,
                           "dropped": s.dropped, "entries": [dict(e.__dict__, ms_per_tick=profile.per_tick(e, s))
                                                             for e in s.entries]} for s in shots + other],
                         ensure_ascii=False, indent=2))
        return 0
    show_profile(shots + other, args.top, args.by_file, table=not args.compare)
    if args.compare:
        print(t("prof_compare"))
        def side(v, floor):
            return f"{v:8.3f}" if v is not None else f"{'<' + format(floor, '.3f'):>8}"

        for c in profile.compare(shots, other)[:args.top]:
            print(f"  {side(c.a, c.floor_a)} {side(c.b, c.floor_b)} {c.delta:+8.3f}  {c.key}")
    if args.csv:
        print(args.csv)
    return 0


def show_profile(shots: list, top: int = 25, by_file: bool = False, table: bool = True) -> int:
    """Print profiler shots: a head line each, then (``table``) callees by total and callers by own time."""
    for s in shots:
        print(t("prof_shot", shot=s.path.name, capture=s.capture, ticks=s.ticks, current=s.current or "-",
                rows=len(s.entries), dropped=s.dropped))
        if not table:
            continue
        for section, key in (("callees", lambda e: -e.incl), ("callers", lambda e: -e.excl)):
            rows = sorted((e for e in s.entries if e.section == section), key=key)
            if not rows:
                continue
            print(f"  {section}:  {'incl s':>8} {'excl s':>8} {'calls':>10} {'ms/tick':>8}  kind  file:line")
            for e in rows[:top]:
                where = f"{e.file}:{e.line}" if e.file else e.name
                print(f"  {'':9} {e.incl:8.3f} {e.excl:8.3f} {e.calls:10d} {profile.per_tick(e, s):8.3f}  "
                      f"{e.kind}  {where}")
        if by_file:
            print("  " + t("prof_by_file"))
            for f, sec, n in profile.by_file(s.entries)[:top]:
                print(f"    {sec:8.3f} s  {n:3d}  {f}")
    return 0
