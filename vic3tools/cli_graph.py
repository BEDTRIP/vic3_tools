"""``v3 graph``: generate the layers of the sources' documentation graph (``graph.toml`` of a documents repo)."""

from __future__ import annotations

import argparse
from pathlib import Path

from vic3tools import graph
from vic3tools.i18n import t

LAYERS = ("terms", "objects", "mods")


def add_parsers(sub) -> None:
    p = sub.add_parser("graph", help="generate the sources' documentation graph: terms, object cards, engine "
                       "reference, what each mod changes in vanilla (graph.toml of the documents repo)",
                       description=graph.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("layer", choices=(*LAYERS, "all"), help="which layer (all — every one, in this order)")
    p.add_argument("--repo", type=Path, default=Path.cwd(), help="a folder in the documents repo (default: current)")
    p.add_argument("--source", action="append", help="mods: only these sources (repeatable; default: all mods)")
    p.add_argument("--check", action="store_true", help="only compare; exit code 1 when notes differ")
    p.set_defaults(func=cmd_graph)


def cmd_graph(args, cfg) -> int:
    from vic3tools.graph import run

    g = graph.load(args.repo)
    dirty = False
    for layer in LAYERS if args.layer == "all" else (args.layer,):
        if layer == "mods":
            results = run.run_mods(g, args.check, args.source)
        else:
            results = [(g.vanilla.name, *getattr(run, f"run_{layer}")(g, args.check))]
        for src, s, counts in results:
            dirty |= bool(s.changed or s.stale)
            info = ", ".join(f"{k} {v}" for k, v in counts.items())
            print(t("graph_layer", layer=layer, source=src, info=info, changed=len(s.changed), stale=len(s.stale)))
    return 1 if args.check and dirty else 0
