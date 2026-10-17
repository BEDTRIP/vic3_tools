"""``v3 gfx``: a mod's pictures from cards — variants in ComfyUI, the chosen one kept, the DDS built as vanilla's.

    v3 gfx new  <mod>/gfx_src/<kind>/<name>.toml --kind goods --target gfx/interface/icons/goods_icons/x.dds
    v3 gfx gen  CARD [--repeat 4]     # variants of every model of the card -> <name>.variants/, a sheet Q1..K4
    v3 gfx pick CARD Q3               # keep one (cut out if the kind needs it) -> <name>.png, recorded in the card
    v3 gfx build CARD... | --mod DIR  # <name>.png -> size, tint -> the DDS at the card's target (BGRA8 + mips)
    v3 gfx check FILE.dds...          # format and size against vanilla of the same folder
    v3 gfx dds IN.png OUT.dds         # one picture -> a vanilla-like DDS
    v3 gfx workflows save|run|list    # the ComfyUI workflows ld_00..ld_50 (vic3tools.gfx.workflows)

Needs Pillow (`pip install vic3tools[img]`); gen / pick need a running ComfyUI (COMFY_URL, default 127.0.0.1:8188)
with the vic3 nodes (comfy/v3_nodes) and the models of the card.
"""

from __future__ import annotations

import argparse
import collections
import json
import shutil
import sys
from pathlib import Path

from vic3tools.core import paths


def add_parsers(sub) -> None:
    p = sub.add_parser("gfx", help="a mod's pictures from cards: variants in ComfyUI, the chosen one, a vanilla-like "
                       "DDS; checks of DDS files", description=__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    gsub = p.add_subparsers(dest="gfx_command", required=True, metavar="<command>")

    s = gsub.add_parser("new", help="a card from its kind's defaults (size, canvas, samples, models, steps)")
    s.add_argument("card", type=Path, help="<mod>/gfx_src/<kind>/<name>.toml")
    s.add_argument("--kind", required=True)
    s.add_argument("--target", required=True, help="the DDS path in the mod")
    s.add_argument("--prompt", default="")
    s.add_argument("--samples", nargs="*", default=[], help="game paths (fork:..., workshop:..., or absolute); "
                   "default: 6 from the kind's vanilla folder")
    s.set_defaults(func=cmd_new)

    s = gsub.add_parser("gen", help="variants of every model of the card -> <name>.variants/ and a sheet")
    s.add_argument("card", type=Path)
    s.add_argument("--repeat", type=int, default=4, help="variants per model (one run each, a fresh seed)")
    s.set_defaults(func=cmd_gen)

    s = gsub.add_parser("pick", help="keep a variant (Q3, K1 ...): cut out if the kind needs it -> <name>.png")
    s.add_argument("card", type=Path)
    s.add_argument("variant")
    s.set_defaults(func=cmd_pick)

    s = gsub.add_parser("build", help="<name>.png -> the DDS at the card's target")
    s.add_argument("cards", type=Path, nargs="*")
    s.add_argument("--mod", type=Path, help="every card of this mod (its gfx_src/)")
    s.set_defaults(func=cmd_build)

    s = gsub.add_parser("check", help="DDS files against vanilla of the same folder: format, mips, size")
    s.add_argument("files", type=Path, nargs="+")
    s.set_defaults(func=cmd_check)

    s = gsub.add_parser("dds", help="a picture -> a vanilla-like DDS (BGRA8 + mips)")
    s.add_argument("src", type=Path)
    s.add_argument("dst", type=Path)
    s.add_argument("--size", help="WxH (fit, keeping the aspect)")
    s.add_argument("--no-mips", action="store_true")
    s.set_defaults(func=cmd_dds)

    s = gsub.add_parser("workflows", help="the ComfyUI workflows ld_00..ld_50: save | run | list",
                        add_help=False)
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(func=cmd_workflows)


def _game(cfg=None) -> Path:
    """The game's files (the install root's game/: gfx/, gui/ ...)."""
    root = Path(paths.resolve_roots(cfg or paths.load_config())["game"].path)
    return root / "game" if (root / "game" / "gfx").is_dir() else root


def cmd_new(args, cfg=None) -> int:
    from vic3tools.gfx.cards import KINDS, Card

    samples = args.samples
    if not samples:
        folder = _game(cfg) / KINDS[args.kind]["folder"]
        files = sorted(folder.glob("*.dds")) if folder.is_dir() else []
        step = max(1, len(files) // 6)
        samples = [str(f.relative_to(_game(cfg))).replace("\\", "/") for f in files[::step][:6]]
    card = Card.new(args.target, args.kind, prompt=args.prompt, samples=samples)
    print(card.save(args.card))
    return 0


def cmd_gen(args, cfg=None) -> int:
    from vic3tools.gfx import workflows as W
    from vic3tools.gfx.cards import Card

    card = Card.load(args.card)
    if not card.prompt or not card.samples:
        print("the card needs a prompt and samples", file=sys.stderr)
        return 2
    out = card.variants
    out.mkdir(parents=True, exist_ok=True)
    api = W.wf_variants(None, samples=card.samples, models=card.models, prompt=card.prompt, bg=card.bg,
                        canvas=card.canvas).to_api()
    tags = {"qwen21": "Q", "klein4b": "K", "krea2": "R", "zimage": "Z"}
    found = collections.defaultdict(list)
    index = {}
    for rep in range(args.repeat):
        saved, seed = W.queue(json.loads(json.dumps(api)), out, tag=f"r{rep + 1}_")
        for f in (f for fs in saved.values() for f in fs):
            name = Path(f).name.split("_ld_02_")[-1]
            m = next((m for m in card.models if name.startswith(m + "_")), None)
            if m:
                found[m].append(f)
                index[f"{tags[m]}{len(found[m])}"] = {"model": m, "seed": seed, "file": Path(f).name}
    (out / "variants.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    W.variants_sheet({"": [f for fs in found.values() for f in fs]}, str(out / "variants.png"), models=card.models)
    return 0


def cmd_pick(args, cfg=None) -> int:
    from vic3tools.gfx import workflows as W
    from vic3tools.gfx.cards import Card

    card = Card.load(args.card)
    index = json.loads((card.variants / "variants.json").read_text(encoding="utf-8"))
    v = index.get(args.variant.upper())
    if not v:
        print(f"no variant {args.variant}: {', '.join(index)}", file=sys.stderr)
        return 2
    src = card.variants / v["file"]
    if "cutout" in card.post:
        src = W.cutout(src, card.variants / "cut")
    shutil.copyfile(src, card.source)
    card.chosen, card.model, card.seed = args.variant.upper(), v["model"], v["seed"]
    card.save()
    print(card.source)
    return 0


def cmd_build(args, cfg=None) -> int:
    from vic3tools.gfx import dds
    from vic3tools.gfx.cards import Card, find_cards, render

    files = list(args.cards) + (find_cards(args.mod) if args.mod else [])
    if not files:
        print("no cards", file=sys.stderr)
        return 2
    bad = 0
    for f in files:
        card = Card.load(f)
        if not card.source.exists():
            print(f"skip {f}: no {card.source.name} (v3 gfx pick first)")
            bad += 1
            continue
        dst = card.mod_root() / card.target
        dds.write(render(card), dst, mips=card.mips)
        i = dds.info(dst)
        print(f"{dst}  {i.width}x{i.height} {i.format} mips={i.mips}")
    return 1 if bad else 0


def cmd_check(args, cfg=None) -> int:
    from vic3tools.gfx import dds

    game, bad = _game(cfg), 0
    for f in args.files:
        i = dds.info(f)
        parts = Path(f).resolve().as_posix().split("/gfx/", 1)
        folder = game / "gfx" / Path(parts[1]).parent if len(parts) == 2 else None
        sizes = collections.Counter()
        if folder and folder.is_dir():
            for v in folder.glob("*.dds"):
                try:
                    vi = dds.info(v)
                    sizes[(vi.width, vi.height)] += 1
                except (OSError, ValueError):
                    pass
        common = sizes.most_common(1)[0][0] if sizes else None
        notes = []
        if not i.vanilla_like:
            notes.append(f"vanilla is BGRA8 with mips, this is {i.format} mips={i.mips}")
        if common and (i.width, i.height) not in sizes:
            notes.append(f"size {i.width}x{i.height}: vanilla here is {common[0]}x{common[1]} ({sizes[common]} of "
                         f"{sum(sizes.values())})")
        bad += bool(notes)
        print(f"{f}: {i.width}x{i.height} {i.format} mips={i.mips}" + ("" if not notes else "  — " + "; ".join(notes)))
    return 1 if bad else 0


def cmd_dds(args, cfg=None) -> int:
    from PIL import Image

    from vic3tools.gfx import dds
    from vic3tools.gfx.cards import fit

    img = Image.open(args.src)
    if args.size:
        w, h = (int(x) for x in args.size.lower().split("x"))
        img = fit(img, (w, h), opaque=img.mode != "RGBA")
    dds.write(img, args.dst, mips=not args.no_mips)
    i = dds.info(args.dst)
    print(f"{args.dst}  {i.width}x{i.height} {i.format} mips={i.mips}")
    return 0


def cmd_workflows(args, cfg=None) -> int:
    from vic3tools.gfx import workflows as W

    W.main(args.rest)
    return 0
