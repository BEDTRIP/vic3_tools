"""A GUI widget drawn to PNG without the game: the resolved widget laid out and painted with the game's textures and
fonts. An approximation — check it against the game with ``v3 bench`` (``--compare`` puts a shot next to it).

Layout (Jomini GUI, as far as it is known):

- ``size = { w h }`` — pixels, ``N%`` of the parent, ``@constant`` of the widget's file; ``minimumsize`` /
  ``maximumsize`` clamp (``-1`` = no limit); no size → the size of the content (children's bounding box, a text, a
  texture);
- ``position`` is an offset from the anchor: ``parentanchor`` (a point of the parent: ``top|left`` by default,
  ``hcenter``, ``vcenter``, ``center``, ``right``, ``bottom``) to ``widgetanchor`` (the same point of the widget unless
  set);
- ``flowcontainer`` lays its children in a row (``direction = vertical`` — a column) with ``spacing`` and ``margin``;
  its size is its content's; a child's ``parentanchor`` aligns it across the row;
- ``hbox`` / ``vbox`` fill their own size (``size``, else the parent's); children keep their size, ``expand = {}``
  and children with ``layoutpolicy_horizontal`` / ``_vertical = expanding`` / ``growing`` share what is left;
- ``scrollarea`` clips its content; a box with a ``datamodel`` repeats its ``item`` (``--items``);
- ``visible = no`` is not drawn; a bound ``visible = "[…]"`` is drawn (``--hide-bound`` leaves it out).

Paint: ``background`` and ``icon`` textures (``.dds`` / ``.png`` of the set), 9-slice with ``spriteborder`` for
``Corneredstretched`` / ``Corneredtiled`` (tiled drawn stretched), ``framesize`` + ``frame``, ``color`` / ``tintcolor``,
``alpha``, ``mirror``; text with the game's fonts per language (glyph fallbacks), the colour of ``default_format``
from ``textformatting.gui``, ``align``, ``multiline`` wrap, ``elide``. Not drawn: ``modify_texture`` overlays, shaders,
animations, text icons; ``[…]`` and ``$…$`` show as ``--stub``.

Scale (the game's ``GUI.scale`` in ``pdx_settings.json``) multiplies the whole interface: the layout is in logical
pixels with the screen ÷ scale as the parent of ``%`` sizes, a text is measured at the whole font pixels the scale gives
(cut down: 15 at ×1.3 is 19 px, so widths do not scale exactly), and the picture is painted at the scale.

Problems found while laying out (``issues``): a text that wraps, is cut by its box's height, elided, shrunk to
``fontsize_min``, or runs out of a fixed-width box; a widget outside its fixed-size parent; a widget larger than the
screen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from vic3tools.gui import fit, fonts, loctext, resolve, tree
from vic3tools.gui.resolve import RNode

TEXT_KINDS = {"textbox", "text_single", "text_multi"}
FLOW = {"flowcontainer"}
BOXES = {"hbox", "vbox"}
SKIP_KEYS = {"tooltipwidget", "state", "item", "blockoverride", "modify_texture", "background", "icon_effect",
             "dragdropbutton_settings", "animation", "frame_offset"}
DEFAULT_TEXT = (0.76, 0.74, 0.72)  # #default_text / darker_white


@dataclass
class Box:
    node: RNode
    kind: str  # the native widget: textbox, icon, flowcontainer, hbox…
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    children: list[Box] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)  # a textbox's lines as drawn
    size: float = 0  # its font size
    clip: bool = False
    issues: list[str] = field(default_factory=list)


def _pair(v: str | None) -> list[str]:
    return v.strip("{} ").split() if v else []


def _anchor(v: str | None) -> tuple[float, float]:
    """``top|left`` … → (fx, fy) in 0..1."""
    v = (v or "").replace(" ", "").lower()
    fx = 0.5 if ("hcenter" in v or v == "center" or "|center" in v or "center|" in v) else 1.0 if "right" in v else 0
    fy = 0.5 if ("vcenter" in v or v == "center" or "|center" in v or "center|" in v) else 1.0 if "bottom" in v else 0
    return fx, fy


class Renderer:
    def __init__(self, si, lang: str = "english", stub: str = fit.SAMPLE, items: int = 3, hide_bound: bool = False,
                 scale: float = 1.0, marks: bool = False):
        self.si = si
        self.scale = scale
        self.marks = marks  # outline the widgets with issues
        self.res = resolve.Resolver(si)
        self.lang = lang
        self.stub = stub
        self.items = items
        self.hide_bound = hide_bound
        game = si.ms.mods[0].path
        self.fonts = fonts.Fonts.load(game, [m.path for m in si.ms.mods[1:]])
        self.formats = self._formats()
        self.notes: set[str] = set()

    # --- lookups -----------------------------------------------------------------------------------------------------

    def _formats(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for m in self.si.ms.mods:
            p = m.path / "gui" / "textformatting.gui"
            if p.is_file():
                for _t, nd in tree.walk(tree.parse_file(p)):
                    if nd.key == "format" and nd.is_block:
                        name = next((c.scalar().strip('"') for c in nd.props("name")), "")
                        if name:
                            out[name] = next((c.scalar().strip('"') for c in nd.props("format")), "")
        return out

    def color_of(self, fmt: str | None, depth: int = 0) -> tuple[float, float, float]:
        """The colour a text format ends with (``#title`` → ``grey;shadow`` → ``grey`` → ``color:{…}``)."""
        if not fmt or depth > 8:
            return DEFAULT_TEXT
        name = fmt.strip('"').lstrip("#")
        spec = self.formats.get(name, "")
        for part in reversed([p.strip() for p in spec.split(";") if p.strip()]):
            m = re.match(r"color:\{([^}]*)\}", part.replace(" ", ""))
            if m:
                v = [float(x) for x in m.group(1).split(",")[:3]]
                return v[0], v[1], v[2]
            if part in self.formats:
                return self.color_of(part, depth + 1)
        return DEFAULT_TEXT

    def texture(self, rel: str) -> Path | None:
        rel = rel.strip('"').replace("\\", "/")
        for m in reversed(self.si.ms.mods):
            p = m.path / rel
            if p.is_file():
                return p
        return None

    def props(self, r: RNode) -> dict[str, RNode]:
        out: dict[str, RNode] = {}
        for c in r.children or []:
            if not c.is_widget and c.node.op and c.lost_to is None:
                out[c.key] = c
        return out

    def value(self, r: RNode | None) -> str:
        if r is None:
            return ""
        v = r.value
        if v.startswith("@"):
            c = self.res.const(r.node.file, v)
            return c.scalar() if c is not None else "0"
        return v

    def num(self, s: str, whole: float, default: float = 0) -> float:
        s = s.strip()
        if s.startswith("@"):
            return default
        try:
            return float(s[:-1]) / 100 * whole if s.endswith("%") else float(s)
        except ValueError:
            return default

    def pair(self, r: RNode | None, pw: float = 0, ph: float = 0) -> tuple[float | None, float | None]:
        if r is None:
            return None, None
        parts = _pair(self.value(r))
        out: list[float | None] = []
        for i, s in enumerate(parts[:2]):
            if s.startswith("@"):
                c = self.res.const(r.node.file, s)
                s = c.scalar() if c is not None else "0"
            out.append(self.num(s, pw if i == 0 else ph))
        while len(out) < 2:
            out.append(None)
        return out[0], out[1]

    def native(self, r: RNode) -> str:
        return (r.types[-1] if r.types else r.key) or r.key

    # --- text --------------------------------------------------------------------------------------------------------

    def text_of(self, p: dict[str, RNode]) -> str:
        if "raw_text" in p:
            return fit.plain(self.value(p["raw_text"]).strip('"').replace("[", "\0[")).replace("\0", "")\
                .replace(fit.SAMPLE, self.stub)
        if "text" in p:
            key = self.value(p["text"]).strip('"')
            if key and "[" not in key and " " not in key:
                found = loctext.texts(self.si, key, [self.lang])
                if self.lang in found:
                    return fit.plain(loctext.expand(self.si, found[self.lang][0], self.lang)).replace(fit.SAMPLE,
                                                                                                      self.stub)
                return key
            return fit.plain(key).replace(fit.SAMPLE, self.stub)
        return ""

    def faces(self, p: dict[str, RNode]) -> list[fonts.Face]:
        font = self.value(p.get("font")).strip('"') or fit.DEFAULT_FONT
        return self.fonts.faces(font, self.lang)

    def font_size(self, p: dict[str, RNode]) -> float:
        return self.num(self.value(p.get("fontsize")), 0, fit.DEFAULT_SIZE) or fit.DEFAULT_SIZE

    def measure(self, size: float) -> float:
        """The size a text is measured at, in logical pixels: the game draws the font at the scaled size cut down to
        whole pixels (15 at ×1.3 is 19 px, not 20 -- checked in the game)."""
        return max(1, int(size * self.scale + 1e-6)) / self.scale

    # --- layout ------------------------------------------------------------------------------------------------------

    def visible(self, r: RNode) -> bool:
        v = self.props(r).get("visible")
        if v is None:
            return True
        s = self.value(v).strip('"')
        if s == "no":
            return False
        return not (self.hide_bound and s.startswith("["))

    def children(self, r: RNode) -> list[RNode]:
        out = []
        for c in r.children or []:
            if not c.is_widget or c.key in SKIP_KEYS or not self.visible(c):
                continue
            out.append(c)
        return out

    def layout(self, r: RNode, pw: float, ph: float) -> Box:
        """The widget's box (size and children placed), its position not yet set."""
        kind = self.native(r)
        p = self.props(r)
        b = Box(r, kind, clip=kind in ("scrollarea", "scrollbox"))
        w, h = self.pair(p.get("size"), pw, ph)
        mx, my = self.margins(p)
        auto = self.value(p.get("autoresize")) == "yes"

        has_text = "text" in p or "raw_text" in p
        if kind in TEXT_KINDS or (has_text and kind not in FLOW | BOXES):
            self.layout_text(b, p, w, h, auto, mx, my)
            w, h = b.w, b.h
        else:
            kids = self.children(r)
            kids = self.repeat(r, kids)
            inner_w = (w if w is not None else pw) - mx[0] - mx[1]
            inner_h = (h if h is not None else ph) - my[0] - my[1]
            if kind in FLOW:
                cw, ch = self.layout_flow(b, p, kids, inner_w, inner_h)
                w, h = cw + mx[0] + mx[1], ch + my[0] + my[1]  # a flowcontainer is as big as its content
            elif kind in BOXES:
                w = w if w is not None else pw
                h = h if h is not None else ph
                self.layout_box(b, p, kids, w - mx[0] - mx[1], h - my[0] - my[1], mx[0], my[0])
            else:
                placed = [self.layout(c, inner_w, inner_h) for c in kids]
                if w is None or h is None:
                    tex = self.texture_size(p)
                    bw = max((c.w + max(0.0, self.offset(c)[0]) for c in placed), default=tex[0] if tex else 0)
                    bh = max((c.h + max(0.0, self.offset(c)[1]) for c in placed), default=tex[1] if tex else 0)
                    w = w if w is not None else bw
                    h = h if h is not None else bh
                for c in placed:
                    self.place(c, w, h)
                b.children = placed
        b.w, b.h = self.clamp(p, w or 0, h or 0, pw, ph)
        return b

    def margins(self, p: dict[str, RNode]) -> tuple[tuple[float, float], tuple[float, float]]:
        mx = my = 0.0
        m = p.get("margin")
        if m is not None:
            a, c = self.pair(m)
            mx, my = a or 0, c or 0
        left = right = mx
        top = bottom = my
        for k in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            if k in p:
                v = self.num(self.value(p[k]), 0)
                if k == "margin_left":
                    left = v
                elif k == "margin_right":
                    right = v
                elif k == "margin_top":
                    top = v
                else:
                    bottom = v
        return (left, right), (top, bottom)

    def clamp(self, p, w, h, pw, ph) -> tuple[float, float]:
        lo = self.pair(p.get("minimumsize"), pw, ph)
        hi = self.pair(p.get("maximumsize"), pw, ph)
        if lo[0] is not None and lo[0] > 0:
            w = max(w, lo[0])
        if lo[1] is not None and lo[1] > 0:
            h = max(h, lo[1])
        if hi[0] is not None and hi[0] > 0:
            w = min(w, hi[0])
        if hi[1] is not None and hi[1] > 0:
            h = min(h, hi[1])
        return w, h

    def offset(self, b: Box) -> tuple[float, float]:
        x, y = self.pair(self.props(b.node).get("position"))
        return x or 0, y or 0

    def place(self, b: Box, pw: float, ph: float) -> None:
        """Set a child's position inside a plain parent: anchors and offset."""
        p = self.props(b.node)
        pa = _anchor(self.value(p.get("parentanchor")))
        wa = _anchor(self.value(p.get("widgetanchor"))) if "widgetanchor" in p else pa
        ox, oy = self.offset(b)
        b.x = pa[0] * pw - wa[0] * b.w + ox
        b.y = pa[1] * ph - wa[1] * b.h + oy

    def layout_text(self, b: Box, p, w, h, auto, mx, my) -> None:
        text = self.text_of(p)
        faces = self.faces(p)
        size = self.font_size(p)
        multiline = self.value(p.get("multiline")) == "yes"
        lo = self.pair(p.get("minimumsize"))
        hi = self.pair(p.get("maximumsize"))
        avail = w if (w is not None and not auto) else (hi[0] if hi[0] and hi[0] > 0 else None)
        if avail is not None:
            avail -= mx[0] + mx[1]
        if not faces:
            self.notes.add(f"no font files for {self.value(p.get('font')) or fit.DEFAULT_FONT} in {self.lang}")
        lines = text.split("\n") if text else [""]
        own = len(lines)
        natural = max((fonts.width(ln, faces, self.measure(size)) for ln in lines), default=0) if faces else 0
        elide = self.value(p.get("elide")) in ("right", "left", "middle")
        if multiline and avail and faces:
            lines = fonts.wrap(text, faces, self.measure(size), avail)
        elif avail and faces and elide:
            fmin = self.num(self.value(p.get("fontsize_min")), 0, 0)
            if natural > avail and fmin:
                was = size
                size = max(fmin, int(size * avail / natural))
                b.issues.append(f"font shrunk {was:g} → {size:g}")
            lines = [self.elide(ln, faces, self.measure(size), avail) for ln in lines]
        m = self.measure(size)
        tw = max((fonts.width(ln, faces, m) for ln in lines), default=0) if faces else len(text) * size / 2
        th = len(lines) * m * 1.25
        b.lines, b.size = lines, size
        if text and faces:
            if len(lines) > own:
                b.issues.append(f"wraps to {len(lines)} lines")
            if any(ln.endswith("…") for ln in lines) and "…" not in text:
                b.issues.append(f"elided: needs {natural:.0f} px, has {avail:.0f}")
            elif not multiline and not elide and avail is not None and natural > avail + 0.5:
                b.issues.append(f"runs out of its box: needs {natural:.0f} px, has {avail:.0f}")
            if h is not None and not auto and th + my[0] + my[1] > h + 0.5:
                b.issues.append(f"cut by height: needs {th + my[0] + my[1]:.0f} px, has {h:.0f}")
        if w is None or auto:
            w = tw + mx[0] + mx[1]
            if lo[0] and lo[0] > 0:
                w = max(w, lo[0])
        if h is None or auto:
            h = th + my[0] + my[1]
        b.w, b.h = w, h

    def check(self, b: Box) -> None:
        """Children outside a parent of a fixed size (a flowcontainer grows with them, a scrollarea clips them)."""
        for c in b.children:
            if b.kind not in FLOW and not b.clip:
                out = max(-c.x, -c.y, c.x + c.w - b.w, c.y + c.h - b.h)
                if out > 0.5:
                    c.issues.append(f"outside its parent by {out:.0f} px")
            self.check(c)

    def issues(self, b: Box, path: str = "") -> list[tuple[str, str, str]]:
        """(where, widget, problem) for every problem in the tree."""
        nd = b.node.node
        who = f"{b.kind} '{nd.label()}'" if nd.label() else b.kind
        where = f"{nd.file.name if nd.file else '?'}:{nd.line}"
        here = f"{path}/{who}" if path else who
        out = [(where, here, i) for i in b.issues]
        for c in b.children:
            out += self.issues(c, here)
        return out

    def elide(self, line: str, faces, size: float, avail: float) -> str:
        if fonts.width(line, faces, size) <= avail:
            return line
        while line and fonts.width(line + "…", faces, size) > avail:
            line = line[:-1]
        return line + "…"

    def layout_flow(self, b: Box, p, kids: list[RNode], iw: float, ih: float) -> tuple[float, float]:
        vertical = self.value(p.get("direction")) == "vertical"
        spacing = self.num(self.value(p.get("spacing")), 0, 0)
        placed = [self.layout(c, iw, ih) for c in kids]
        main = 0.0
        cross = max(((c.w if vertical else c.h) for c in placed), default=0)
        (ml, _mr), (mt, _mb) = self.margins(p)
        for c in placed:
            ox, oy = self.offset(c)
            pa = _anchor(self.value(self.props(c.node).get("parentanchor")))
            if vertical:
                c.x, c.y = ml + pa[0] * (cross - c.w) + ox, mt + main + oy
                main += c.h + spacing
            else:
                c.x, c.y = ml + main + ox, mt + pa[1] * (cross - c.h) + oy
                main += c.w + spacing
        if placed:
            main -= spacing
        b.children = placed
        return (cross, main) if vertical else (main, cross)

    def layout_box(self, b: Box, p, kids: list[RNode], iw: float, ih: float, ox0: float, oy0: float) -> None:
        vertical = b.kind == "vbox"
        spacing = self.num(self.value(p.get("spacing")), 0, 0)
        placed = []
        grow = []
        for c in kids:
            cp = self.props(c)
            pol = self.value(cp.get("layoutpolicy_vertical" if vertical else "layoutpolicy_horizontal"))
            bx = self.layout(c, iw, ih)
            if c.key == "expand" or pol in ("expanding", "growing"):
                grow.append(bx)
            placed.append(bx)
        used = sum((c.h if vertical else c.w) for c in placed if c not in grow) + spacing * max(0, len(placed) - 1)
        free = max(0.0, (ih if vertical else iw) - used)
        for c in grow:
            if vertical:
                c.h = free / len(grow)
            else:
                c.w = free / len(grow)
        pos = 0.0
        for c in placed:
            ca = _anchor(self.value(self.props(c.node).get("parentanchor")) or "center")
            if vertical:
                c.x, c.y = ox0 + ca[0] * (iw - c.w), oy0 + pos
                pos += c.h + spacing
            else:
                c.x, c.y = ox0 + pos, oy0 + ca[1] * (ih - c.h)
                pos += c.w + spacing
        b.children = placed

    def repeat(self, r: RNode, kids: list[RNode]) -> list[RNode]:
        """A box with a datamodel draws its ``item`` a few times."""
        if "datamodel" not in self.props(r):
            return kids
        item = next((c for c in r.children or [] if c.key == "item" and c.is_widget), None)
        if item is None:
            return kids
        inner = [c for c in item.children or [] if c.is_widget]
        return kids + inner * self.items

    def texture_size(self, p) -> tuple[float, float] | None:
        t = p.get("texture")
        if t is None:
            return None
        path = self.texture(self.value(t))
        if path is None:
            return None
        fw, fh = self.pair(p.get("framesize"))
        if fw and fh:
            return fw, fh
        img = _image(str(path))
        return (img.width, img.height) if img else None

    # --- paint -------------------------------------------------------------------------------------------------------

    def paint(self, b: Box, img, ox: float = 0, oy: float = 0, boxes: bool = False, clip=None) -> None:
        from PIL import ImageDraw

        x, y = ox + b.x, oy + b.y
        s = self.scale
        p = self.props(b.node)
        for c in b.node.children or []:
            if c.is_widget and c.key == "background" and self.visible(c):
                self.draw_texture(img, self.props(c), x, y, b.w, b.h, background=True)
        if b.kind in ("icon",) or ("texture" in p and b.kind not in TEXT_KINDS):
            self.draw_texture(img, p, x, y, b.w, b.h)
        if b.lines:
            self.draw_text(img, b, p, x, y)
        if b.clip:
            clip = (x, y, x + b.w, y + b.h)
        for c in b.children:
            self.paint(c, img, x, y, boxes, clip)
        if boxes or (self.marks and b.issues):
            d = ImageDraw.Draw(img)
            bad = self.marks and b.issues
            d.rectangle((x * s, y * s, (x + b.w) * s - 1, (y + b.h) * s - 1),
                        outline=(255, 40, 40, 255) if bad else (255, 0, 255, 160), width=2 if bad else 1)

    def draw_texture(self, img, p, x, y, w, h, background: bool = False) -> None:
        from PIL import Image

        t = p.get("texture")
        if t is None or w <= 0 or h <= 0:
            return
        path = self.texture(self.value(t))
        if path is None:
            self.notes.add(f"texture not found: {self.value(t)}")
            return
        src = _image(str(path))
        if src is None:
            return
        fw, fh = self.pair(p.get("framesize"))
        if fw and fh:
            frame = int(self.num(self.value(p.get("frame")), 0, 1) or 1)
            cols = max(1, src.width // int(fw))
            i = frame - 1
            src = src.crop((int((i % cols) * fw), int((i // cols) * fh), int((i % cols + 1) * fw),
                            int((i // cols + 1) * fh)))
        if background and "margin" in p:
            mx, my = self.pair(p.get("margin"))
            x, y, w, h = x - (mx or 0), y - (my or 0), w + 2 * (mx or 0), h + 2 * (my or 0)
        sprite = self.value(p.get("spriteType")).lower()
        bx, by = self.pair(p.get("spriteborder"))
        s = self.scale
        size = (max(1, round(w * s)), max(1, round(h * s)))
        if sprite.startswith("cornered") and (bx or by):
            tile = _nine(src, int(bx or 0), int(by or 0), int(w), int(h))
            if tile.size != size:
                tile = tile.resize(size, Image.BILINEAR)
        else:
            tile = src.resize(size, Image.BILINEAR)
        mirror = self.value(p.get("mirror"))
        if "horizontal" in mirror:
            tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
        if "vertical" in mirror:
            tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
        tint = self.pair_color(p.get("color") or p.get("tintcolor"))
        alpha = self.num(self.value(p.get("alpha")), 0, 1) if "alpha" in p else 1.0
        if tint or alpha < 1:
            r_, g_, b_, a_ = tile.split()
            if tint:
                r_ = r_.point(lambda v, k=tint[0]: int(v * k))
                g_ = g_.point(lambda v, k=tint[1]: int(v * k))
                b_ = b_.point(lambda v, k=tint[2]: int(v * k))
                if len(tint) > 3:
                    alpha *= tint[3]
            a_ = a_.point(lambda v, k=alpha: int(v * k))
            tile = Image.merge("RGBA", (r_, g_, b_, a_))
        img.alpha_composite(tile, (int(round(x * s)), int(round(y * s))))

    def pair_color(self, r: RNode | None) -> list[float] | None:
        if r is None:
            return None
        v = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", self.value(r))]
        if len(v) < 3:
            return None
        if any(x > 1 for x in v[:3]):  # rgb { 255 … }
            v = [x / 255 for x in v[:3]] + v[3:]
        return v[:4]

    def draw_text(self, img, b: Box, p, x, y) -> None:
        from PIL import ImageDraw

        faces = self.faces(p)
        if not faces:
            return
        color = tuple(int(c * 255) for c in self.color_of(self.value(p.get("default_format")) or None)) + (255,)
        tint = self.pair_color(p.get("fonttintcolor"))
        if tint:
            color = tuple(int(c * 255) for c in tint[:3]) + (255,)
        s = self.scale
        (ml, mr), (mt, _mb) = self.margins(p)
        x, y, w, h, ml, mr, mt = x * s, y * s, b.w * s, b.h * s, ml * s, mr * s, mt * s  # screen pixels from here
        px = max(1, int(b.size * s + 1e-6))
        align = self.value(p.get("align"))
        d = ImageDraw.Draw(img)
        lh = px * 1.25
        top = y + (h - len(b.lines) * lh) / 2  # no vertical align: centred (the engine's default, seen in the game)
        if "top" in align:
            top = y + mt
        elif "bottom" in align:
            top = y + h - _mb * s - len(b.lines) * lh
        for i, line in enumerate(b.lines):
            lw = fonts.width(line, faces, px)
            if "hcenter" in align or align == "center":
                cx = x + ml + (w - ml - mr - lw) / 2
            elif "right" in align:
                cx = x + w - mr - lw
            else:
                cx = x + ml
            cy = top + i * lh
            for ch in line:
                face = next((f for f in faces if f.has(ch)), faces[0])
                font = _font(str(face.path), px)
                d.text((cx, cy), ch, font=font, fill=color)
                cx += face.advances.get(ord(ch), face.upem // 2) * px / face.upem

    # --- top ---------------------------------------------------------------------------------------------------------

    def render(self, nd, canvas: tuple[float, float] = (1920, 1080), boxes: bool = False, pad: int = 8):
        """The widget as a picture at the scale; ``canvas`` is the parent in logical pixels (the screen ÷ scale)."""
        from PIL import Image

        r = self.res.expand(nd)
        b = self.layout(r, canvas[0], canvas[1])
        self.check(b)
        if b.w > canvas[0] + 0.5 or b.h > canvas[1] + 0.5:
            b.issues.append(f"larger than the screen: {b.w:.0f}×{b.h:.0f} on {canvas[0]:.0f}×{canvas[1]:.0f}")
        b.x, b.y = pad, pad  # the widget alone: its own anchors and position are not applied
        s = self.scale
        img = Image.new("RGBA", (round((b.w + 2 * pad) * s), round((b.h + 2 * pad) * s)), (0, 0, 0, 0))
        self.paint(b, img, 0, 0, boxes)
        return img, b


@lru_cache(maxsize=256)
def _image(path: str):
    from PIL import Image

    try:
        return Image.open(path).convert("RGBA")
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=64)
def _font(path: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(path, max(1, size))


def _nine(src, bx: int, by: int, w: int, h: int):
    """A 9-slice: corners kept, edges and centre stretched to w × h."""
    from PIL import Image

    sw, sh = src.size
    bx, by = min(bx, sw // 2), min(by, sh // 2)
    w, h = max(w, 2 * bx + 1), max(h, 2 * by + 1)
    out = Image.new("RGBA", (w, h))
    xs = [(0, bx, 0, bx), (bx, sw - bx, bx, w - bx), (sw - bx, sw, w - bx, w)]
    ys = [(0, by, 0, by), (by, sh - by, by, h - by), (sh - by, sh, h - by, h)]
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
                continue
            part = src.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.BILINEAR)
            out.paste(part, (dx0, dy0))
    return out
