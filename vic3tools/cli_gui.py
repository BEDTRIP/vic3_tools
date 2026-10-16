"""``v3 gui`` commands: resolve a widget, the reference of types / templates / textures, set a property, text fit."""

from __future__ import annotations

import argparse
import json
import os
import struct
from pathlib import Path

from vic3tools.cli_compat import mod_set
from vic3tools.core import paths
from vic3tools.gui import edit, fit, fonts, loctext, resolve, tree
from vic3tools.i18n import t
from vic3tools.index import query


def add_parsers(sub, common: argparse.ArgumentParser) -> None:
    p = sub.add_parser("gui", help="GUI: a widget with types / templates / blocks resolved, the reference of types, "
                       "templates and textures, setting a property, does a text fit")
    gsub = p.add_subparsers(dest="gui_command", required=True, metavar="<command>")

    g = gsub.add_parser("resolve", parents=[common], help="the widget at FILE:LINE as the game builds it, every "
                        "property with where it comes from")
    g.add_argument("target", nargs="?", help="FILE:LINE (FILE: a path or gui/… of the set)")
    g.add_argument("--type", dest="type_name", help="resolve a type by name instead")
    g.add_argument("--prop", help="only these properties (comma-separated), with the widgets above them")
    g.add_argument("--depth", type=int, default=3, help="levels of nested widgets shown (default 3)")
    g.add_argument("--limit", type=int, default=200, help="lines shown")
    g.set_defaults(func=cmd_resolve)

    for kind, what in (("types", "GUI types"), ("templates", "GUI templates")):
        g = gsub.add_parser(kind, parents=[common], help=f"{what} whose name contains QUERY: definition, base, "
                            "blocks to override, uses and one example")
        g.add_argument("query")
        g.add_argument("--limit", type=int, default=15)
        g.set_defaults(func=cmd_reference, kind=kind[:-1])

    g = gsub.add_parser("textures", parents=[common], help="texture files (.dds, .png under gfx/) whose path "
                        "contains QUERY, with width × height and the mod whose copy loads")
    g.add_argument("query")
    g.add_argument("--limit", type=int, default=30)
    g.set_defaults(func=cmd_textures)

    g = gsub.add_parser("render", parents=[common], help="draw the widget at FILE:LINE to PNG without the game "
                        "(textures, fonts, layout — an approximation; --compare puts a game shot next to it)")
    g.add_argument("target", nargs="?", help="FILE:LINE")
    g.add_argument("--type", dest="type_name", help="draw a type by name instead")
    g.add_argument("--out", type=Path, help="the PNG (default: <cache>/render/<name>.png)")
    g.add_argument("--lang", dest="text_lang", default="english", help="the language of loc texts (russian…)")
    g.add_argument("--boxes", action="store_true", help="outline every widget's box")
    g.add_argument("--items", type=int, default=3, help="items drawn for a list with a datamodel")
    g.add_argument("--stub", default="000", help="what [ … ] and $ … $ show as (default 000)")
    g.add_argument("--hide-bound", action="store_true", help="leave out widgets with a bound visible = \"[…]\"")
    g.add_argument("--canvas", default="1920x1080", help="the parent's size for % sizes (WxH)")
    g.add_argument("--compare", type=Path, help="a game screenshot to put next to the render")
    g.add_argument("--crop", help="the area of --compare: x0,y0,x1,y1 in fractions or pixels")
    g.set_defaults(func=cmd_render)

    g = gsub.add_parser("names", help="widget names, types and text icons of two mods (or one file in both): shared "
                        "and only in one — a merged .gui must keep every name of the versions it merges")
    g.add_argument("a", type=Path, help="a mod folder")
    g.add_argument("b", type=Path, help="another mod folder")
    g.add_argument("--file", help="only this relative path in both (gui/…)")
    g.add_argument("--limit", type=int, default=40)
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_names)

    g = gsub.add_parser("style", parents=[common], help="the look of vanilla's interface counted from its .gui: "
                        "types, templates, formats, fonts, spacing, textures in use (the base of a GUI style file)")
    g.add_argument("--mod", help="count this mod of the set instead of vanilla")
    g.add_argument("--out", type=Path, help="write the Markdown here (default: print it)")
    g.add_argument("--top", type=int, default=25)
    g.set_defaults(func=cmd_style)

    g = gsub.add_parser("set", parents=[common], help="set KEY=VALUE on the widget at FILE:LINE (replace at its own "
                        "level or insert before its `}`)")
    g.add_argument("target", help="FILE:LINE, or FILE with --find")
    g.add_argument("values", nargs="+", metavar="KEY=VALUE")
    g.add_argument("--find", help="the single widget whose key or name contains this")
    g.add_argument("--dry", action="store_true", help="show the change, do not write")
    g.set_defaults(func=cmd_set)

    g = gsub.add_parser("fit", parents=[common], help="does the text of the textbox at FILE:LINE fit its width, "
                        "in every language")
    g.add_argument("target")
    g.add_argument("--width", type=float, help="measure against this width instead of the widget's")
    g.add_argument("--langs", default=",".join(fonts.LANGS), help="languages, comma-separated")
    g.set_defaults(func=cmd_fit)


# --- helpers ---------------------------------------------------------------------------------------------------------


def _open(args, cfg) -> query.SetIndex:
    return query.SetIndex.open(mod_set(args, cfg), args.rebuild)


def _emit(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _target(spec: str, si: query.SetIndex | None) -> tuple[Path, int | None]:
    """FILE:LINE → (path, line); FILE may be a path or a path inside the set (the copy that loads)."""
    file, line = spec, None
    head, sep, tail = spec.rpartition(":")
    if sep and tail.isdigit():
        file, line = head, int(tail)
    p = Path(file)
    if not p.is_file() and si is not None:
        rel = file.replace("\\", "/").lstrip("/")
        for m in reversed(si.ms.mods):
            if (m.path / rel).is_file():
                p = m.path / rel
                break
    if not p.is_file():
        raise FileNotFoundError(t("gui_no_file", file=file))
    return p, line


def _widget(path: Path, line: int | None, find: str | None = None) -> tree.GNode:
    nodes = tree.parse_file(path)
    if find:
        found = edit.find(nodes, find)
        if line is not None:
            found = [nd for nd in found if nd.line <= line <= nd.end_line] or found
        if len(found) != 1:
            names = "; ".join(f"{nd.line} {nd.key} {nd.label()}".strip() for nd in found[:10])
            raise KeyError(t("gui_find_many", count=len(found), needle=find, found=names or "—"))
        return found[0]
    if line is None:
        raise KeyError(t("gui_need_line"))
    w, _up = resolve.widget_at(nodes, line)
    if w is None:
        raise KeyError(t("gui_no_widget", where=f"{path.name}:{line}"))
    return w


def _types(r: resolve.RNode) -> str:
    chain: list[str] = []
    for x in r.types:  # `type textbox = textbox`: the native widget of the same name once
        if x != r.key and (not chain or chain[-1] != x):
            chain.append(x)
    return f"  [{' › '.join(chain)}]" if chain else ""


def _value(res: resolve.Resolver, n: resolve.RNode) -> str:
    v = n.value
    if v.startswith("@"):
        c = res.const(n.node.file, v)
        if c is not None:
            v += f" (= {c.scalar()}, {res.loc(c, True)})"
    return v


def _via(n: resolve.RNode) -> str:
    return "  via " + " ← ".join(reversed(n.via)) if n.via else ""


def _rjson(res: resolve.Resolver, n: resolve.RNode) -> dict:
    d = {"key": n.key, "where": res.loc(n.node), "via": list(n.via)}
    if n.is_widget:
        d.update(name=n.label(), types=n.types, children=[_rjson(res, c) for c in n.children])
    else:
        d.update(value=n.value, overridden=bool(n.lost_to))
    return d


# --- resolve ---------------------------------------------------------------------------------------------------------


def cmd_resolve(args, cfg) -> int:
    si = _open(args, cfg)
    try:
        res = resolve.Resolver(si)
        if args.type_name:
            nd = res.find("type", args.type_name)
            if nd is None:
                print(t("def_none", name=args.type_name))
                return 1
        elif args.target:
            path, line = _target(args.target, si)
            nd = _widget(path, line)
        else:
            print(t("gui_need_target"))
            return 2
        r = res.expand(nd)
        if args.json:
            _emit(_rjson(res, r))
            return 0
        print(f"{r.key}{' ' + repr(r.label()) if r.label() else ''}{_types(r)}  {res.loc(nd)}")
        out: list[str] = []
        if args.prop:
            keys = {k.strip() for k in args.prop.split(",")}
            groups: dict[tuple, list[resolve.RNode]] = {}
            for trail, n in resolve.walk(r):
                if not n.is_widget and n.key in keys:
                    groups.setdefault(tuple(id(x) for x in trail), []).append(n)
            paths_ = {tuple(id(x) for x in trail): trail for trail, _n in resolve.walk(r)}
            for k, ns in groups.items():
                out.append(" › ".join(x.key for x in paths_[k]))
                for n in ns:
                    lost = f"  ({t('gui_overridden', line=res.loc(n.lost_to.node, True))})" if n.lost_to else ""
                    out.append(f"  {n.key} = {_value(res, n)}  # {res.loc(n.node)}{_via(n)}{lost}")
            if not groups:
                out.append(t("gui_no_prop", keys=args.prop))
        else:
            _tree(res, r, 1, args.depth, out)
        for s in out[:args.limit]:
            print(s)
        if len(out) > args.limit:
            print(t("gui_more", shown=args.limit, total=len(out)))
        return 0
    finally:
        si.close()


def _tree(res: resolve.Resolver, r: resolve.RNode, level: int, depth: int, out: list[str]) -> None:
    pad = "  " * level
    for c in r.children or []:
        if c.is_widget:
            lab = f' "{c.label()}"' if c.label() else ""
            if level >= depth:
                out.append(f"{pad}{c.key}{lab}{_types(c)}  {res.loc(c.node, True)}  (+{len(c.children)})")
                continue
            out.append(f"{pad}{c.key}{lab}{_types(c)}  {res.loc(c.node, True)}")
            _tree(res, c, level + 1, depth, out)
        else:
            lost = "  (" + t("gui_overridden", line=res.loc(c.lost_to.node, True)) + ")" if c.lost_to else ""
            step = f"  via {c.via[-1]}" if c.via and not c.via[-1].startswith("type ") else ""
            out.append(f"{pad}{c.key} = {_value(res, c)}  # {res.loc(c.node, True)}{step}{lost}")


# --- reference -------------------------------------------------------------------------------------------------------


def cmd_reference(args, cfg) -> int:
    si = _open(args, cfg)
    try:
        res = resolve.Resolver(si)
        kind = args.kind
        names = [n for n in si.names_like(f"*{args.query}*")
                 if any(h.kind == "gui_" + kind for h in si.defs(n))]
        rows = []
        for name in names:
            d = res.find(kind, name)
            if d is None:
                continue
            defs = [h for h in si.defs(name) if h.kind == "gui_" + kind]
            refs = [h for h in si.refs(name) if h.loads]
            mark = ">using" if kind == "template" else f">{name}"
            ex = next((h for h in refs if h.path.endswith(mark) and h.mod.kind == "vanilla"),
                      next((h for h in refs if h.path.endswith(mark)), None))
            row = {"name": name, "where": res.loc(d), "end_line": d.end_line, "definitions": len(defs),
                   "uses": len(refs), "example": f"{ex.mod.name}: {ex.rel}:{ex.line}" if ex else None}
            if kind == "type":
                row["base"] = d.value
                row["blocks"] = resolve.blocks_offered(res, d)
            else:
                row["props"] = [f"{c.key} = {c.scalar()}" if c.op else c.key for c in d.children or []][:6]
            rows.append(row)
        rows.sort(key=lambda x: -x["uses"])
        if args.json:
            _emit(rows)
            return 0 if rows else 1
        if not rows:
            print(t("refs_none", name=args.query))
            return 1
        for row in rows[:args.limit]:
            extra = f" = {row['base']}" if kind == "type" else ""
            more = f", {t('gui_defined_times', count=row['definitions'])}" if row["definitions"] > 1 else ""
            print(f"{row['name']}{extra}  {row['where']}-{row['end_line']}  ({t('gui_uses', count=row['uses'])}"
                  f"{more})")
            if kind == "type" and row["blocks"]:
                print("    blocks: " + ", ".join(row["blocks"]))
            if kind == "template" and row["props"]:
                print("    " + "; ".join(row["props"]))
            if row["example"]:
                print(f"    e.g. {row['example']}")
        if len(rows) > args.limit:
            print(f"… +{len(rows) - args.limit} (--limit)")
        return 0
    finally:
        si.close()


def texture_size(path: Path) -> tuple[int, int] | None:
    """(width, height) from a DDS or PNG header."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if head[:4] == b"DDS " and len(head) >= 20:
        h, w = struct.unpack_from("<II", head, 12)
        return w, h
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        w, h = struct.unpack_from(">II", head, 16)
        return w, h
    return None


def cmd_textures(args, cfg) -> int:
    ms = mod_set(args, cfg)
    needle = args.query.casefold().replace("\\", "/")
    found: dict[str, list] = {}  # rel → mods that have it, load order
    for m in ms.mods:
        root = m.path / "gfx"
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if not f.lower().endswith((".dds", ".png")):
                    continue
                rel = (Path(dirpath) / f).relative_to(m.path).as_posix()
                if needle in rel.casefold():
                    found.setdefault(rel, []).append(m)
    rows = []
    for rel, mods in sorted(found.items()):
        m = mods[-1]
        size = texture_size(m.path / rel)
        rows.append({"path": rel, "mod": m.name, "size": f"{size[0]}×{size[1]}" if size else "?",
                     "also_in": [x.name for x in mods[:-1]]})
    if args.json:
        _emit(rows)
        return 0 if rows else 1
    if not rows:
        print(t("refs_none", name=args.query))
        return 1
    for row in rows[:args.limit]:
        also = f"  (replaces {', '.join(row['also_in'])})" if row["also_in"] else ""
        print(f"{row['path']}  {row['size']}  {row['mod']}{also}")
    if len(rows) > args.limit:
        print(f"… +{len(rows) - args.limit} (--limit)")
    return 0


# --- render --------------------------------------------------------------------------------------------------------


def cmd_render(args, cfg) -> int:
    from vic3tools.core import paths as cpaths
    from vic3tools.gui import render

    si = _open(args, cfg)
    try:
        rd = render.Renderer(si, args.text_lang, args.stub, args.items, args.hide_bound)
        if args.type_name:
            nd = rd.res.find("type", args.type_name)
            if nd is None:
                print(t("def_none", name=args.type_name))
                return 1
            name = args.type_name
        elif args.target:
            path, line = _target(args.target, si)
            nd = _widget(path, line)
            name = f"{path.stem}_{line}"
        else:
            print(t("gui_need_target"))
            return 2
        cw, _, ch = args.canvas.partition("x")
        img, box = rd.render(nd, (int(cw), int(ch or 1080)), args.boxes)
    finally:
        si.close()
    if args.compare:
        from vic3tools import bench

        shot = bench.cut(args.compare, args.crop, (cpaths.cache_dir() / "render_cmp.png"))
        from PIL import Image

        other = Image.open(shot).convert("RGBA")
        side = Image.new("RGBA", (img.width + other.width + 8, max(img.height, other.height)), (255, 0, 255, 255))
        side.alpha_composite(img, (0, 0))
        side.alpha_composite(other, (img.width + 8, 0))
        img = side
    out = args.out or (cpaths.cache_dir() / "render" / f"{name}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    if args.json:
        _emit({"png": str(out), "size": [box.w, box.h], "notes": sorted(rd.notes)})
        return 0
    print(t("gui_render", out=out, w=round(box.w), h=round(box.h)))
    for n in sorted(rd.notes)[:10]:
        print("  " + n)
    return 0


# --- names ---------------------------------------------------------------------------------------------------------


def cmd_names(args, cfg) -> int:
    from vic3tools.gui import names

    for p in (args.a, args.b):
        if not p.is_dir():
            raise FileNotFoundError(t("gui_no_file", file=p))
    res = names.compare(names.identifiers(args.a, args.file), names.identifiers(args.b, args.file))
    if args.json:
        _emit(res)
        return 0
    for kind, r in res.items():
        print(t("gui_names", kind=kind, shared=len(r["shared"]), a=args.a.name, na=len(r["only_a"]), b=args.b.name,
                nb=len(r["only_b"])))
        for side, name in (("only_a", args.a.name), ("only_b", args.b.name)):
            if r[side]:
                shown = ", ".join(r[side][:args.limit]) + (" …" if len(r[side]) > args.limit else "")
                print(f"  only {name}: {shown}")
    return 0


# --- style ---------------------------------------------------------------------------------------------------------


def cmd_style(args, cfg) -> int:
    from vic3tools.gui import style

    ms = mod_set(args, cfg)
    mod = ms.find(args.mod) if args.mod else ms.mods[0]
    st = style.collect(mod.path)
    text = style.markdown(st, args.top)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(t("gui_style_written", path=args.out, files=st.files))
    else:
        print(text)
    return 0


# --- set -------------------------------------------------------------------------------------------------------------


def cmd_set(args, cfg) -> int:
    try:
        path, line = _target(args.target, None)
    except FileNotFoundError:  # a path inside the set: open the index only then
        si = _open(args, cfg)
        try:
            path, line = _target(args.target, si)
        finally:
            si.close()
    values = []
    for v in args.values:
        k, sep, val = v.partition("=")
        if not sep or not k.strip():
            print(t("gui_bad_value", value=v))
            return 2
        values.append((k.strip(), val.strip()))
    w = _widget(path, line, args.find)
    changes = edit.apply(path, w, values, args.dry)
    if args.json:
        _emit([c.__dict__ for c in changes])
        return 0
    print(f"{path.name}: {w.key}{' ' + repr(w.label()) if w.label() else ''} {w.line}-{w.end_line}"
          + ("  (--dry)" if args.dry else ""))
    for c in changes:
        was = c.was if c.was is not None else t("gui_inserted")
        more = "  " + t("gui_set_others", count=c.others) if c.others else ""
        print(f"  {c.line}: {was} → {c.becomes}{more}")
    return 0


# --- fit -------------------------------------------------------------------------------------------------------------


def cmd_fit(args, cfg) -> int:
    si = _open(args, cfg)
    try:
        res = resolve.Resolver(si)
        path, line = _target(args.target, si)
        nd = _widget(path, line)
        r = res.expand(nd)
        trail_ = ()
        if not (fit.prop(r, "text") or fit.prop(r, "raw_text")):  # a widget around it: its first text inside
            trail_, r = next(((tr, w) for tr, w in resolve.walk(r)
                              if w.is_widget and (fit.prop(w, "text") or fit.prop(w, "raw_text"))), ((), r))
        b = fit.box(r, args.width)
        tp = fit.prop(r, "text") or fit.prop(r, "raw_text")
        langs = [x.strip() for x in args.langs.split(",") if x.strip()]
        texts: dict[str, str] = {}
        source = ""
        if tp is None:
            print(t("gui_fit_no_text", where=res.loc(nd)))
            return 1
        val = tp.value.strip('"')
        if tp.key == "text" and val and "[" not in val and " " not in val:
            found = loctext.texts(si, val, langs)
            texts = {lang: loctext.expand(si, tx, lang) for lang, (tx, _h) in found.items()}
            source = f"loc {val}"
            missing = [lang for lang in langs if lang not in found]
        else:
            texts = {lang: val for lang in langs}
            source = "raw_text" if tp.key == "raw_text" else "text"
            missing = []
        game = si.ms.mods[0].path
        if not (game.parent / "clausewitz").is_dir():
            root = paths.resolve_roots(cfg)["game"]
            game = root.path / "game" if root.ok else game
        fs = fonts.Fonts.load(game, [m.path for m in si.ms.mods[1:]])
        rows = []
        for lang in langs:
            if lang in texts:
                faces = fs.faces(b.font, lang)
                if not faces:
                    print(t("gui_fit_no_font", font=b.font, lang=lang))
                    return 1
                rows.append(fit.measure(b, lang, texts[lang], faces))
        if args.json:
            _emit({"widget": res.loc(nd), "font": b.font, "size": b.size, "size_min": b.size_min, "elide": b.elide,
                   "multiline": b.multiline, "width": b.avail, "width_from": b.why, "text": source,
                   "missing": missing, "rows": [r_.__dict__ for r_ in rows]})
            return 0
        flags = ", ".join(x for x in (f"fontsize_min {b.size_min:g}" if b.size_min else "",
                                       "elide" if b.elide else "", "multiline" if b.multiline else "") if x)
        width = f"{b.avail:g} px ({b.why})" if b.avail is not None else b.why
        print(f"{nd.key}{' ' + repr(nd.label()) if nd.label() else ''}  {res.loc(nd)}")
        if trail_:
            print("  › " + " › ".join(x.key for x in trail_[1:] + (r,)) + f"  {res.loc(r.node)}")
        print(f"  {source}; {b.font} {b.size:g}" + (f" ({flags})" if flags else "") + f"; width {width}")
        for row in rows:
            print(f"  {row.lang:<13} {row.width:6.0f} px  {_verdict(row)}   {row.text[:50]!r}")
        if missing:
            print("  " + t("gui_fit_missing", langs=", ".join(missing)))
        for n in b.notes:
            print("  " + n)
        print("  " + t("gui_fit_note", sample=fit.SAMPLE))
        return 0
    finally:
        si.close()


def _verdict(row: fit.Row) -> str:
    if row.verdict == "wraps":
        return t("gui_fit_wraps", lines=row.lines)
    if row.verdict == "shrinks":
        return t("gui_fit_shrinks", size=f"{row.size:g}")
    return t("gui_fit_" + row.verdict)
