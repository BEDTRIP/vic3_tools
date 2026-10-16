"""Fonts of the game and text width: ``*.font`` definitions, a small TrueType / OpenType reader, measuring.

``font = { name fontstyle = { style fontfiles } }`` names a family; ``fontfiles = { name group = { languages files } }``
gives per-language files — the first file has the glyphs, the rest are fallbacks. Paths in ``files`` are relative to
``game/`` or ``clausewitz/`` (the engine's own fonts). Width = Σ advance × size / unitsPerEm; kerning is ignored.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from vic3tools.gui import tree

LANGS = ("english", "braz_por", "french", "german", "polish", "russian", "spanish", "turkish", "japanese", "korean",
         "simp_chinese")


# --- sfnt -----------------------------------------------------------------------------------------------------------


@dataclass
class Face:
    path: Path
    upem: int
    advances: dict[int, int]  # code point → advance width in font units
    ascent: int = 0  # hhea, font units (descent is negative)
    descent: int = 0

    def has(self, ch: str) -> bool:
        return ord(ch) in self.advances

    def line(self, px: int) -> float:
        """A line's height in pixels at ``px``: ascent and descent each rounded, as FreeType does; without the font's
        metrics, 1.25 × px. Checked against the game (EBGaramond at ×1.3: rows of a long column at the game's
        places, where 1.25 × px drifted 2 px a row)."""
        if not self.ascent:
            return px * 1.25
        return round(self.ascent * px / self.upem) + round(-self.descent * px / self.upem)


@lru_cache(maxsize=32)
def load_face(path: str) -> Face:
    data = Path(path).read_bytes()
    tables = {}
    (num,) = struct.unpack_from(">H", data, 4)
    for i in range(num):
        tag, _sum, off, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        tables[tag.decode("latin-1")] = (off, length)
    upem = struct.unpack_from(">H", data, tables["head"][0] + 18)[0]
    (n_metrics,) = struct.unpack_from(">H", data, tables["hhea"][0] + 34)
    ascent, descent = struct.unpack_from(">hh", data, tables["hhea"][0] + 4)
    hm = tables["hmtx"][0]
    widths = [struct.unpack_from(">H", data, hm + 4 * i)[0] for i in range(n_metrics)]
    cmap = _cmap(data, tables["cmap"][0])
    last = widths[-1] if widths else 0
    adv = {cp: (widths[g] if g < n_metrics else last) for cp, g in cmap.items() if g}
    return Face(Path(path), upem, adv, ascent, descent)


def _cmap(data: bytes, base: int) -> dict[int, int]:
    """Code point → glyph id, from the best Unicode subtable (format 12, else 4)."""
    _ver, num = struct.unpack_from(">HH", data, base)
    subs = {}
    for i in range(num):
        pid, eid, off = struct.unpack_from(">HHI", data, base + 4 + 8 * i)
        fmt = struct.unpack_from(">H", data, base + off)[0]
        if pid in (0, 3):
            subs.setdefault(fmt, base + off)
    if 12 in subs:
        o = subs[12]
        (groups,) = struct.unpack_from(">I", data, o + 12)
        out = {}
        for g in range(groups):
            a, b, gid = struct.unpack_from(">III", data, o + 16 + 12 * g)
            for cp in range(a, b + 1):
                out[cp] = gid + cp - a
        return out
    if 4 in subs:
        o = subs[4]
        seg2 = struct.unpack_from(">H", data, o + 6)[0]
        segs = seg2 // 2
        ends = struct.unpack_from(f">{segs}H", data, o + 14)
        starts = struct.unpack_from(f">{segs}H", data, o + 16 + seg2)
        deltas = struct.unpack_from(f">{segs}h", data, o + 16 + 2 * seg2)
        ro_base = o + 16 + 3 * seg2
        ros = struct.unpack_from(f">{segs}H", data, ro_base)
        out = {}
        for s in range(segs):
            for cp in range(starts[s], ends[s] + 1):
                if cp == 0xFFFF:
                    continue
                if ros[s] == 0:
                    gid = (cp + deltas[s]) & 0xFFFF
                else:
                    at = ro_base + 2 * s + ros[s] + 2 * (cp - starts[s])
                    gid = struct.unpack_from(">H", data, at)[0]
                    gid = (gid + deltas[s]) & 0xFFFF if gid else 0
                out[cp] = gid
        return out
    return {}


# --- font definitions -----------------------------------------------------------------------------------------------


@dataclass
class Fonts:
    roots: list[Path]  # where `files` paths resolve: mods (last first), game/, clausewitz/
    families: dict[str, dict[str, str]] = field(default_factory=dict)  # font name → style → fontfiles name
    files: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # fontfiles name → lang → files

    @classmethod
    def load(cls, game_dir: Path, mod_dirs: list[Path] = ()) -> Fonts:
        """Font definitions of the game (``game/fonts``, ``clausewitz/fonts``) and of the mods (later wins)."""
        cw = game_dir.parent / "clausewitz"
        f = cls([*reversed(list(mod_dirs)), game_dir, cw])
        for root in [cw, game_dir, *mod_dirs]:
            for p in sorted((root / "fonts").glob("*.font")) if (root / "fonts").is_dir() else []:
                f._read(p)
        return f

    def _read(self, path: Path) -> None:
        for nd in tree.parse_file(path):
            if not nd.is_block:
                continue
            name = next((c.scalar().strip('"') for c in nd.props("name")), "")
            if nd.key == "fontfiles":
                groups: dict[str, list[str]] = {}
                for g in nd.children or []:
                    if g.key == "group" and g.is_block:
                        langs = [c.key.strip('"') for x in g.props("languages") for c in x.children or []]
                        files = [c.key.strip('"') for x in g.props("files") for c in x.children or []]
                        for lang in langs or ["*"]:
                            groups[lang.removeprefix("l_")] = files
                    elif g.key == "file" and g.op:  # a single file, all languages
                        groups.setdefault("*", []).append(g.scalar().strip('"'))
                self.files[name] = groups
            elif nd.key == "font":
                styles = {}
                for s in nd.children or []:
                    if s.key == "fontstyle" and s.is_block:
                        style = next((c.scalar() for c in s.props("style")), "regular")
                        ff = next((c.scalar().strip('"') for c in s.props("fontfiles")), "")
                        styles[style] = ff
                self.families[name] = styles

    def faces(self, font: str, lang: str, style: str = "regular") -> list[Face]:
        """The files of ``font`` for ``lang``, first the one with the glyphs, then the fallbacks."""
        ff = self.families.get(font, {}).get(style) or self.families.get(font, {}).get("regular") or font
        groups = self.files.get(ff, {})
        out = []
        for rel in groups.get(lang) or groups.get("english") or groups.get("*") or []:
            for root in self.roots:
                p = root / rel
                if p.is_file():
                    out.append(load_face(str(p)))
                    break
        return out


def width(text: str, faces: list[Face], size: float) -> float:
    """Width in pixels of one line of text; a glyph missing everywhere counts as half an em."""
    total = 0.0
    for ch in text:
        for f in faces:
            a = f.advances.get(ord(ch))
            if a is not None:
                total += a * size / f.upem
                break
        else:
            total += size / 2
    return total


def wrap(text: str, faces: list[Face], size: float, avail: float) -> list[str]:
    """Greedy word wrap (by character where there are no spaces, as in CJK)."""
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ") if " " in para.strip() else list(para)
        sep = " " if " " in para.strip() else ""
        cur = ""
        for w in words:
            cand = f"{cur}{sep}{w}" if cur else w
            if cur and width(cand, faces, size) > avail:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
    return lines
