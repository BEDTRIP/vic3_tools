"""The layers of ``v3 graph`` for one source, from the config to notes on disk."""

from __future__ import annotations

from vic3tools.graph import Config, Sync, objects, sync, terms


def run_terms(cfg: Config, check: bool) -> tuple[Sync, dict]:
    van = cfg.vanilla
    dst = cfg.root / van.name / "Термины"
    out, counts = terms.build(van.snapshot, dst, cfg.avoid_names(), version=cfg.version)
    return sync(dst, out, check), counts


def vanilla_layer(cfg: Config):
    van = cfg.vanilla
    recs = objects.all_records(van.snapshot)
    names = objects.Names([van.snapshot])
    term_names = {f.stem.lower() for f in (cfg.root / van.name / "Термины").glob("*.md")}
    taken = {n.lower() for n in cfg.avoid_names()} | term_names
    return recs, names, objects.card_names(recs, names, taken)


def run_objects(cfg: Config, check: bool) -> tuple[Sync, dict]:
    van = cfg.vanilla
    recs, names, cnames = vanilla_layer(cfg)
    linker = objects.Linker([(van.name, recs, cnames)])
    cards = objects.build_cards(van.name, recs, cnames, linker)
    dst = cfg.root / van.name
    out = objects.notes(cards, van.name, van.label, cfg.version, objects.snapshot_rel(van.snapshot, cfg.paths_root),
                        names, linker, [], dst)
    scope = tuple(t.out.split("/")[0] + "/" for t in objects.TYPES)
    return sync(dst, out, check, scope), {"cards": len(cards)}
