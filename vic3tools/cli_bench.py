"""``v3 bench``: the test bench — the game open in the sandbox VM, steps on it, shots and their difference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vic3tools import bench
from vic3tools.cli_compat import mod_set
from vic3tools.i18n import t


def add_parsers(sub, common: argparse.ArgumentParser) -> None:
    p = sub.add_parser("bench", help="the test bench: the game open in the sandbox VM, steps, shots, their difference",
                       description=bench.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    bsub = p.add_subparsers(dest="bench_command", required=True, metavar="<command>")

    b = bsub.add_parser("start", parents=[common], help="open the game in the VM with the set's mods, paused")
    b.add_argument("--save", default="", help="a save of the host's 'save games' (default: a new game)")
    b.add_argument("--tag", default="SWI", help="the country (a new game; a save that opens in the lobby)")
    b.add_argument("--scale", default="", help="the guest's interface scale (GUI.scale), e.g. 1.25")
    b.add_argument("--language", default="", help="the guest's language (english, russian…); default: the host's")
    b.set_defaults(func=cmd_start)

    b = bsub.add_parser("do", help="vic3_ui.ps1 steps on the open game, after sending the changed mod files "
                        "(shot NAME; click FX FY; hover FX FY; wait S; key esc; console CMD …)")
    b.add_argument("steps")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_do)

    b = bsub.add_parser("shot", help="a screenshot of the open game (changed mod files sent first), cut to --crop")
    b.add_argument("name")
    b.add_argument("--crop", help="x0,y0,x1,y1 in fractions of the window (0..1) or pixels")
    b.add_argument("--wait", type=float, default=2, help="seconds to wait before the shot (a re-read .gui)")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_shot)

    b = bsub.add_parser("diff", help="what differs between two shots: the share of pixels, the area, a side-by-side")
    b.add_argument("a", help="a shot: a path or a name of `v3 bench shot` (the latest one)")
    b.add_argument("b")
    b.add_argument("--crop")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_diff)

    b = bsub.add_parser("profile", parents=[common], help="the script profiler on the open game: a capture, then "
                        "its root and edge views read as a table (the set needs mods/profiler_view)")
    b.add_argument("--seconds", type=int, default=60, help="the capture's length, the game running")
    b.add_argument("--speed", type=int, default=5, choices=range(1, 6), help="game speed during the capture")
    b.add_argument("--top", type=int, default=25)
    b.add_argument("--by-file", action="store_true", help="own time summed by file")
    b.set_defaults(func=cmd_profile)

    b = bsub.add_parser("stop", help="close the game in the VM and gather its logs")
    b.set_defaults(func=cmd_stop)


def _report(st: bench.Step, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"id": st.id, "code": st.code, "out": str(st.out), "shots": [str(s) for s in st.shots],
                          "log": st.log}, ensure_ascii=False, indent=2))
        return st.code
    print(t("bench_step", id=st.id, code=st.code, out=st.out))
    for s in st.shots:
        print(f"  {s}")
    if st.code:
        print(st.log)
    return st.code


def cmd_start(args, cfg) -> int:
    ms = mod_set(args, cfg)
    st = bench.start(cfg, [m.path for m in ms.mods[1:]], args.save, args.tag, scale=args.scale, language=args.language)
    return _report(st, args.json)


def cmd_do(args, cfg) -> int:
    return _report(bench.step(cfg, args.steps), args.json)


def cmd_shot(args, cfg) -> int:
    name = "".join(c for c in args.name if c.isalnum() or c in "_-") or "shot"
    st = bench.step(cfg, f"wait {args.wait:g}; shot {name}", name)
    shot = st.out / f"{name}.png"
    if args.crop and shot.is_file():
        bench.cut(shot, args.crop, st.out / f"{name}_crop.png")
    return _report(st, args.json)


def find_shot(ref: str) -> Path:
    """A path, or the latest ``<name>.png`` of the bench's steps."""
    p = Path(ref)
    if p.is_file():
        return p
    name = ref.removesuffix(".png")
    hits = sorted(bench.bench_dir().glob(f"*/{name}.png"), key=lambda f: f.stat().st_mtime)
    if not hits:
        raise FileNotFoundError(t("bench_no_shot", name=ref))
    return hits[-1]


def cmd_diff(args, cfg) -> int:
    a, b = find_shot(args.a), find_shot(args.b)
    out = b.parent / f"diff_{a.stem}_{b.stem}.png"
    d = bench.diff(a, b, args.crop, out)
    if args.json:
        print(json.dumps({"a": str(a), "b": str(b), "changed": d.changed, "bbox": d.bbox, "image": str(d.image)},
                         indent=2))
        return 0
    if d.bbox is None:
        print(t("bench_same", a=a.name, b=b.name))
    else:
        print(t("bench_diff", share=f"{d.changed:.2%}", box=",".join(map(str, d.bbox))))
    print(f"  {d.image}")
    return 0


def cmd_profile(args, cfg) -> int:
    from vic3tools import cli_log, profile

    shots, problem = bench.profile(cfg, args.seconds, args.speed)
    if problem:
        print(problem)
        for s in shots:
            print(f"  {s}")
        return 1
    return cli_log.show_profile(profile.read(shots, cli_log._set_files(args, cfg)), args.top, args.by_file)


def cmd_stop(args, cfg) -> int:
    return _report(bench.stop(cfg), False)
