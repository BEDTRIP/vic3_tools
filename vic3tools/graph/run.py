"""The layers of ``v3 graph`` for one source, from the config to notes on disk."""

from __future__ import annotations

from pathlib import Path

from vic3tools.graph import Config, Sync, engine, mods, objects, sync, terms


def run_terms(cfg: Config, check: bool) -> tuple[Sync, dict]:
    van = cfg.vanilla
    dst = cfg.root / van.name / "Термины"
    out, counts = terms.build(van.snapshot, dst, cfg.avoid_names(), version=cfg.version)
    return sync(dst, out, check, audience=cfg.audience), counts


def engine_dir(cfg: Config) -> Path:
    return cfg.root / cfg.vanilla.name / "движок"


def run_engine(cfg: Config, check: bool) -> tuple[Sync, dict]:
    """Copy the dump (``dump`` of graph.toml, when it is there) and write the reference tables."""
    raw = engine_dir(cfg) / "дамп"
    copied = []
    if cfg.dump and cfg.dump.is_dir() and not check:
        copied = engine.copy_raw(cfg.dump, raw)
    out, counts = engine.notes(raw, cfg.vanilla.name, cfg.version, cfg.dump_date)
    s = sync(engine_dir(cfg), out, check, tuple(f"{k.title}" for k in engine.KINDS) + ("_Карта движка",),
             cfg.audience)
    return s, counts | {"copied": len(copied)}


def modifier_links(cfg: Config) -> dict[str, str]:
    return engine.modifier_links(engine_dir(cfg) / "дамп", cfg.vanilla.name)


def taken_names(cfg: Config) -> set[str]:
    """Names generated cards must not repeat (lower case): the ``avoid`` notes and vanilla's terms."""
    term_names = {f.stem.lower() for f in (cfg.root / cfg.vanilla.name / "Термины").glob("*.md")}
    return {n.lower() for n in cfg.avoid_names()} | term_names


def vanilla_layer(cfg: Config):
    van = cfg.vanilla
    recs = objects.all_records(van.snapshot)
    names = objects.Names([van.snapshot])
    return recs, names, objects.card_names(recs, names, taken_names(cfg))


def run_objects(cfg: Config, check: bool) -> tuple[Sync, dict]:
    van = cfg.vanilla
    recs, names, cnames = vanilla_layer(cfg)
    linker = objects.Linker([(van.name, recs, cnames)], modifier_links(cfg))
    cards = objects.build_cards(van.name, recs, cnames, linker)
    dst = cfg.root / van.name
    out = objects.notes(cards, van.name, van.label, cfg.version, objects.snapshot_rel(van.snapshot, cfg.paths_root),
                        names, linker, [], dst)
    scope = tuple(t.out.split("/")[0] + "/" for t in objects.TYPES)
    return sync(dst, out, check, scope, cfg.audience), {"cards": len(cards)}


def run_mods(cfg: Config, check: bool, only: list[str] | None = None) -> list[tuple[str, Sync, dict]]:
    """Every source but vanilla (or ``only`` those): what it changes in vanilla, cards of its records."""
    van = cfg.vanilla
    layer = vanilla_layer(cfg)
    taken = taken_names(cfg)
    mlinks = modifier_links(cfg)
    scope = (*(t.out.split("/")[0] + "/" for t in objects.TYPES), "Что меняет в ванили", "Термины/")
    avoid = cfg.avoid_names()
    van_terms = terms.names_of(van.snapshot, avoid)
    avoid_terms = avoid | set(van_terms.values())
    out = []
    for name, src in cfg.sources.items():
        if name == van.name or (only and name not in only):
            continue
        dst = cfg.root / name
        ml = mods.build(name, src.label, cfg.version, src.snapshot, van.snapshot, layer,
                        objects.snapshot_rel(src.snapshot, cfg.paths_root), taken, dst, mlinks)
        tn, tc = terms.build_mod(src.snapshot, van.snapshot, dst / "Термины", avoid_terms, name, src.label,
                                 cfg.version, van_terms)
        ml.notes.update({f"Термины/{k}": v for k, v in tn.items()})
        out.append((name, sync(dst, ml.notes, check, scope, cfg.audience), ml.counts | tc))
    return out
