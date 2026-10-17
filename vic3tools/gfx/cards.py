"""Cards: one picture of a mod = one TOML card next to its chosen source PNG.

    <mod>/gfx_src/<kind>/<name>.toml    what the picture is, where it goes, how it was made
    <mod>/gfx_src/<kind>/<name>.png     the chosen variant at full size (after the cut-out) -- the source of the DDS
    <mod>/gfx_src/<kind>/<name>.variants/   the variants to choose from (not in git)

`v3 gfx new` writes a card from its kind's defaults, `gen` draws variants, `pick` keeps one, `build` makes the DDS.
Kinds follow the vanilla interface (the fork's этапы/R10.md, «Виды графики»): what size vanilla uses, what the
samples are, what the source needs before the DDS (cut-out, tint), which models draw it.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

# size: the vanilla size of that kind; canvas: what the generator draws (2-4x, near-square); bg: the samples' backing
# (their transparent parts reach the model as that colour); post: steps from the chosen variant to the DDS source.
KINDS: dict[str, dict] = {
    "goods": dict(size=[256, 256], canvas=[1024, 1024], bg="#ffffff", post=["cutout"], models=["qwen21", "klein4b"],
                  folder="gfx/interface/icons/goods_icons", mips=True),
    "invention": dict(size=[256, 256], canvas=[1024, 1024], bg="#ffffff", post=["cutout"],
                      models=["qwen21", "klein4b"], folder="gfx/interface/icons/invention_icons", mips=True),
    "event_icon": dict(size=[150, 150], canvas=[1024, 1024], bg="#ffffff", post=["cutout"],
                       models=["qwen21", "klein4b"], folder="gfx/interface/icons/event_icons", mips=True),
    "building": dict(size=[256, 256], canvas=[1024, 1024], bg="#ffffff", post=[], models=["klein4b", "qwen21"],
                     folder="gfx/interface/icons/building_icons", mips=True),
    "law": dict(size=[256, 256], canvas=[1024, 1024], bg="#ffffff", post=["cutout", "tint"], tint="bronze",
                models=["qwen21", "klein4b"], folder="gfx/interface/icons/law_icons", mips=True),
    "production_method": dict(size=[104, 104], canvas=[1024, 1024], bg="#ffffff", post=["cutout", "tint"],
                              tint="#b04a3c", models=["qwen21", "klein4b"],
                              folder="gfx/interface/icons/production_method_icons", mips=True),
    "timed_modifier": dict(size=[120, 120], canvas=[1024, 1024], bg="#ffffff", post=["cutout", "tint"],
                           tint="#c0453a", models=["qwen21", "klein4b"],
                           folder="gfx/interface/icons/timed_modifier_icons", mips=False),
    "logo": dict(size=[256, 256], canvas=[1024, 1024], bg="#ffffff", post=["cutout"], models=["qwen21", "klein4b"],
                 folder="gfx/interface/icons/company_icons/historical_company_icons", mips=True),
    "event": dict(size=[1536, 1024], canvas=[1536, 1024], bg="#808080", post=[], models=["qwen21"],
                  folder="(vanilla_events/ in ComfyUI's input: stills of gfx/event_pictures/*.bk2)", mips=True),
    "illustration": dict(size=[1108, 300], canvas=[1664, 448], bg="#808080", post=[], models=["qwen21"],
                         folder="gfx/interface/illustrations/top_illus", mips=True),
    "layer": dict(size=[1140, 212], canvas=[1824, 336], bg="#808080", post=["gray"], models=["qwen21", "klein4b"],
                  folder="gfx/interface/backgrounds", mips=True),
}

TINTS = {"bronze": ("#2b1a0e", "#a8794a", "#f3dcb4"), "gold": ("#2e2208", "#c9a03a", "#fff1b8"),
         "silver": ("#1c1e22", "#9aa0a8", "#f4f6f8")}


@dataclass
class Card:
    target: str                      # the DDS path in the mod, e.g. gfx/interface/icons/goods_icons/ef_banknotes.dds
    kind: str
    prompt: str = ""
    samples: list[str] = field(default_factory=list)  # game paths; "fork:<path>", "workshop:<path>", or absolute
    size: list[int] = field(default_factory=list)
    canvas: list[int] = field(default_factory=list)
    bg: str = ""
    post: list[str] = field(default_factory=list)
    tint: str = ""
    models: list[str] = field(default_factory=list)
    mips: bool = True
    chosen: str = ""                 # the variant kept: "Q3", "K1" ...
    model: str = ""                  # who drew it
    seed: int = 0
    notes: str = ""
    path: Path | None = None         # the card file (not saved)

    @classmethod
    def new(cls, target: str, kind: str, **kw) -> Card:
        if kind not in KINDS:
            raise ValueError(f"kind: one of {', '.join(KINDS)}")
        d = {k: v for k, v in KINDS[kind].items() if k in cls.__dataclass_fields__}
        d.update({k: v for k, v in kw.items() if v not in (None, "", [])})
        return cls(target=target, kind=kind, **d)

    @classmethod
    def load(cls, path: Path) -> Card:
        d = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        c = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        c.path = Path(path)
        return c

    def save(self, path: Path | None = None) -> Path:
        path = Path(path or self.path)
        d = {k: v for k, v in asdict(self).items() if k != "path"}
        lines = []
        for k, v in d.items():
            lines.append(f"{k} = {_toml(v)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.path = path
        return path

    @property
    def source(self) -> Path:
        return self.path.with_suffix(".png")

    @property
    def variants(self) -> Path:
        return self.path.with_suffix(".variants")

    def mod_root(self) -> Path:
        """The mod: the folder above gfx_src/."""
        for p in self.path.resolve().parents:
            if p.name == "gfx_src":
                return p.parent
        raise ValueError(f"{self.path}: not under a gfx_src/ folder")


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    s = str(v)
    if "\n" in s:
        return '"""\n' + s.replace("\\", "\\\\").replace('"""', '\\"""') + '"""'
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_cards(mod: Path) -> list[Path]:
    return sorted((Path(mod) / "gfx_src").glob("*/*.toml"))


# -- from the source PNG to what goes into the DDS ------------------------------------------------------------------

def fit(img, size, opaque: bool = False):
    """Into `size` keeping the aspect (lanczos): an icon trimmed, padded a little and centred on transparency (vanilla
    icons fill their square); an opaque picture (event, illustration, building icon) covers
    the frame, the middle kept."""
    from PIL import Image

    img = img.convert("RGBA")
    w, h = size
    if not opaque:
        box = img.getbbox()  # trim the empty border the cut-out leaves
        if box:
            img = img.crop(box)
        pad = round(max(img.size) * 0.04)
        canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
        canvas.paste(img, (pad, pad))
        img = canvas
    if opaque:  # a picture fills its frame: cover and crop the middle
        scale = max(w / img.width, h / img.height)
        img = img.resize((max(w, round(img.width * scale)), max(h, round(img.height * scale))), Image.LANCZOS)
        x, y = (img.width - w) // 2, (img.height - h) // 2
        return img.crop((x, y, x + w, y + h))
    scale = min(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    return out


def tint(img, colour: str):
    """A grey relief -> one material: dark-mid-light ramp by brightness (bronze, gold, silver, or one colour)."""
    from PIL import Image

    ramp = TINTS.get(colour)
    if ramp is None:
        c = _rgb(colour)
        ramp = (tuple(int(x * 0.22) for x in c), c, tuple(int(x + (255 - x) * 0.7) for x in c))
    else:
        ramp = tuple(_rgb(x) for x in ramp)
    lut = []
    for ch in range(3):
        for v in range(256):
            t = v / 255
            a, b = (ramp[0][ch], ramp[1][ch]) if t < 0.5 else (ramp[1][ch], ramp[2][ch])
            k = t * 2 if t < 0.5 else t * 2 - 1
            lut.append(round(a + (b - a) * k))
    img = img.convert("RGBA")
    gray = img.convert("L")
    rgb = Image.merge("RGB", (gray, gray, gray)).point(lut)
    rgb.putalpha(img.getchannel("A"))
    return rgb


def gray(img):
    from PIL import Image

    img = img.convert("RGBA")
    g = img.convert("L")
    out = Image.merge("RGB", (g, g, g))
    out.putalpha(img.getchannel("A"))
    return out


def _rgb(hexs: str) -> tuple[int, int, int]:
    hexs = hexs.lstrip("#")
    return tuple(int(hexs[i:i + 2], 16) for i in (0, 2, 4))


def render(card: Card):
    """The source PNG -> the picture that goes into the DDS (the size, tint, grey of the card)."""
    from PIL import Image

    img = Image.open(card.source).convert("RGBA")
    if "gray" in card.post:
        img = gray(img)
    if "tint" in card.post and card.tint:
        img = tint(img, card.tint)
    opaque = "cutout" not in card.post and img.getextrema()[3][0] == 255
    return fit(img, card.size, opaque=opaque)
