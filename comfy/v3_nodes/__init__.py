"""ComfyUI nodes for Victoria 3 interface graphics (category "vic3").

The game builds a wide picture from pieces and layers: an end and a repeated middle (spriteborder, Corneredtiled), a
half and its mirror (mirror = horizontal), a colour under a cloth texture under an ornament (modify_texture blend modes).
These nodes let a workflow generate one such piece and look at it the way the game will show it:

- V3 Load Game Image  -- a .dds / .png from the game, a DLC skin, the mod or the Workshop, by its path in the game's
                         tree (samples go in as layers, not as screenshots)
- V3 Roll / V3 Seam Mask / V3 Tile -- a seamless piece: shift by half with wrap, repaint the cross, check 3x3
- V3 Mirror / V3 Sprite Border -- the piece put together as the game does (mirror; ends + stretched or tiled middle)
- V3 Blend / V3 Fill / V3 Gray -- layers with the game's blend modes (overlay, multiply, alphamultiply, add ...)
- V3 Text  -- a caption in the game's own font (fonts/ of the game) for the preview
- V3 Sheet -- a labelled contact sheet of variants or models

Masks follow ComfyUI: 1 = transparent / to repaint (LoadImage gives 1 - alpha, SetLatentNoiseMask repaints 1).
Roots for paths: v3_nodes.json next to this file ({"game": ".../Victoria 3/game", "fork": ..., "workshop": ...});
without it, the usual Steam folders are tried.
"""
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
STEAM = [Path(p) for p in ("C:/games/steam/steamapps", "C:/Program Files (x86)/Steam/steamapps")]


def _roots() -> dict:
    cfg = {}
    try:
        cfg = json.loads((HERE / "v3_nodes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for s in STEAM:
        cfg.setdefault("game", str(s / "common/Victoria 3/game")) if (s / "common/Victoria 3/game").is_dir() else None
        cfg.setdefault("workshop", str(s / "workshop/content/529340")) if (s / "workshop/content/529340").is_dir() else None
    return cfg


ROOTS = ["game", "fork", "workshop", "absolute"]


def _resolve(root: str, path: str) -> Path:
    path = path.strip().strip('"').replace("\\", "/")
    if root == "absolute":
        return Path(path)
    base = _roots().get(root)
    if not base:
        raise ValueError(f"root '{root}' is not set: put it in {HERE / 'v3_nodes.json'}")
    return Path(base) / path


def _to_tensor(im: Image.Image):
    """PIL -> (IMAGE [1,H,W,3], MASK [1,H,W] with 1 = transparent)."""
    rgba = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
    t = torch.from_numpy(rgba)[None]
    return t[..., :3].contiguous(), (1.0 - t[..., 3]).contiguous()


def _to_pil(img: torch.Tensor, mask: torch.Tensor | None = None) -> Image.Image:
    a = (img[0, ..., :3].clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
    im = Image.fromarray(a, "RGB")
    if mask is not None:
        al = ((1.0 - _fit_mask(mask, img)[0]).clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
        im.putalpha(Image.fromarray(al, "L"))
    return im


def _split(img: torch.Tensor, mask: torch.Tensor | None = None):
    """RGB and mask of an IMAGE that may carry alpha (Qwen Image 2.1 decodes RGBA): the alpha is the mask unless one
    is given."""
    if img.shape[-1] == 4:
        rgb = img[..., :3].contiguous()
        return rgb, (mask if mask is not None else 1.0 - img[..., 3])
    return img, mask


def _fit_mask(mask: torch.Tensor, img: torch.Tensor) -> torch.Tensor:
    if mask.dim() == 2:
        mask = mask[None]
    h, w = img.shape[1:3]
    if mask.shape[1:] != (h, w):
        mask = torch.nn.functional.interpolate(mask[:, None], size=(h, w), mode="bilinear")[:, 0]
    return mask


def _fonts() -> list[str]:
    game = _roots().get("game")
    if not game or not (Path(game) / "fonts").is_dir():
        return ["(game fonts not found)"]
    fonts = Path(game) / "fonts"
    return sorted(str(p.relative_to(fonts)).replace("\\", "/") for p in fonts.rglob("*") if p.suffix.lower() in (".otf", ".ttf"))


class V3LoadGameImage:
    """A picture from the game's tree: .dds (any the game uses) or .png; the alpha comes out as a mask."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT")
    RETURN_NAMES = ("image", "mask", "width", "height")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "root": (ROOTS, {"default": "game", "tooltip": "game = .../Victoria 3/game (DLC skins: dlc/<dlc>/gfx/skins/...); fork = the mod; workshop = content/529340/<id>/..."}),
            "path": ("STRING", {"default": "gfx/interface/backgrounds/fullscreen_header_dec.dds", "multiline": False}),
        }}

    @classmethod
    def IS_CHANGED(cls, root, path):
        p = _resolve(root, path)
        return p.stat().st_mtime if p.exists() else float("nan")

    def load(self, root, path):
        p = _resolve(root, path)
        if not p.exists():
            raise FileNotFoundError(p)
        im = Image.open(p)
        img, mask = _to_tensor(im)
        return img, mask, im.width, im.height


class V3Roll:
    """Shift with wrap-around. By 0.5 the piece's edges meet in the middle: what is wrong there is the seam the game
    would show when it repeats the piece; repaint it with V3 Seam Mask and roll back."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "roll"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "x": ("FLOAT", {"default": 0.5, "min": -1.0, "max": 1.0, "step": 0.01, "tooltip": "share of the width"}),
            "y": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01, "tooltip": "share of the height"}),
        }, "optional": {"mask": ("MASK",)}}

    def roll(self, image, x, y, mask=None):
        image, mask = _split(image, mask)
        h, w = image.shape[1:3]
        dx, dy = round(x * w), round(y * h)
        out = torch.roll(image, shifts=(dy, dx), dims=(1, 2))
        m = torch.roll(_fit_mask(mask, image), shifts=(dy, dx), dims=(1, 2)) if mask is not None \
            else torch.zeros(image.shape[:3])
        return out, m


class V3SeamMask:
    """A band (or a cross) in the middle of the canvas, soft edges: the area to repaint after V3 Roll by 0.5."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("MASK",)
    FUNCTION = "make"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 1024, "min": 8, "max": 16384}),
            "height": ("INT", {"default": 1024, "min": 8, "max": 16384}),
            "shape": (["vertical", "horizontal", "cross"], {"default": "vertical", "tooltip": "vertical: a piece repeated left-right"}),
            "band": ("INT", {"default": 96, "min": 2, "max": 4096, "tooltip": "full width of the band, px"}),
            "feather": ("INT", {"default": 32, "min": 0, "max": 2048}),
        }, "optional": {"image": ("IMAGE", {"tooltip": "takes width and height from it"})}}

    def make(self, width, height, shape, band, feather, image=None):
        if image is not None:
            height, width = image.shape[1:3]

        def ramp(n):
            d = (torch.arange(n, dtype=torch.float32) + 0.5 - n / 2).abs()
            inner = band / 2
            return ((inner + max(feather, 1e-6) - d) / max(feather, 1e-6)).clamp(0, 1) if feather else (d <= inner).float()

        vx, vy = ramp(width)[None, :].expand(height, width), ramp(height)[:, None].expand(height, width)
        m = vx if shape == "vertical" else vy if shape == "horizontal" else torch.maximum(vx, vy)
        return (m[None].contiguous(),)


class V3Tile:
    """The piece repeated cols x rows: seams and repeats show at a glance."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "tile"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "cols": ("INT", {"default": 3, "min": 1, "max": 16}),
                             "rows": ("INT", {"default": 3, "min": 1, "max": 16})}}

    def tile(self, image, cols, rows):
        return (image.repeat(1, rows, cols, 1),)


class V3Mirror:
    """The piece and its mirror side by side, as the game's mirror = horizontal half + half."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "mirror"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "side": (["right", "left", "down", "up"], {"default": "right"})},
                "optional": {"mask": ("MASK",)}}

    def mirror(self, image, side, mask=None):
        image, mask = _split(image, mask)
        m = _fit_mask(mask, image) if mask is not None else torch.zeros(image.shape[:3])
        if side in ("right", "left"):
            fi, fm = torch.flip(image, dims=(2,)), torch.flip(m, dims=(2,))
            pair = ((image, fi), (m, fm)) if side == "right" else ((fi, image), (fm, m))
            return torch.cat(pair[0], dim=2), torch.cat(pair[1], dim=2)
        fi, fm = torch.flip(image, dims=(1,)), torch.flip(m, dims=(1,))
        pair = ((image, fi), (m, fm)) if side == "down" else ((fi, image), (fm, m))
        return torch.cat(pair[0], dim=1), torch.cat(pair[1], dim=1)


class V3SpriteBorder:
    """The picture at another size the way the game draws a spriteborder: corners kept, edges and middle stretched
    (or tiled, as spriteborder_type / Corneredtiled)."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        b = {"default": 0, "min": 0, "max": 8192}
        return {"required": {
            "image": ("IMAGE",),
            "left": ("INT", b), "right": ("INT", b), "top": ("INT", b), "bottom": ("INT", b),
            "width": ("INT", {"default": 2556, "min": 1, "max": 16384}),
            "height": ("INT", {"default": 0, "min": 0, "max": 16384, "tooltip": "0 = as the image"}),
            "middle": (["stretch", "tile"], {"default": "stretch"}),
        }, "optional": {"mask": ("MASK",)}}

    def build(self, image, left, right, top, bottom, width, height, middle, mask=None):
        image, mask = _split(image, mask)
        rgba = torch.cat([image, (1.0 - (_fit_mask(mask, image) if mask is not None else torch.zeros(image.shape[:3])))[..., None]], dim=-1)
        H, W = rgba.shape[1:3]
        height = height or H

        def fit(part, h, w):
            if h <= 0 or w <= 0:
                return None
            ph, pw = part.shape[1:3]
            if middle == "tile" and ph > 0 and pw > 0:
                reps = (-(-h // ph), -(-w // pw))
                return part.repeat(1, reps[0], reps[1], 1)[:, :h, :w]
            return torch.nn.functional.interpolate(part.permute(0, 3, 1, 2), size=(h, w), mode="bilinear",
                                                   align_corners=False).permute(0, 2, 3, 1)

        xs, ys = (0, left, W - right, W), (0, top, H - bottom, H)
        tx, ty = (0, left, width - right, width), (0, top, height - bottom, height)
        out = torch.zeros((rgba.shape[0], height, width, 4))
        for i in range(3):
            for j in range(3):
                src = rgba[:, ys[i]:ys[i + 1], xs[j]:xs[j + 1]]
                h, w = ty[i + 1] - ty[i], tx[j + 1] - tx[j]
                if src.shape[1] == 0 or src.shape[2] == 0 or h <= 0 or w <= 0:
                    continue
                corner = i != 1 and j != 1
                piece = src if corner and src.shape[1:3] == (h, w) else fit(src, h, w)
                out[:, ty[i]:ty[i + 1], tx[j]:tx[j + 1]] = piece
        return out[..., :3].contiguous(), (1.0 - out[..., 3]).contiguous()


def _blend(a, b, mode):
    if mode == "normal":
        return b
    if mode == "multiply":
        return a * b
    if mode == "screen":
        return 1 - (1 - a) * (1 - b)
    if mode == "add":
        return (a + b).clamp(0, 1)
    if mode == "overlay":
        return torch.where(a < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    if mode == "colordodge":
        return (a / (1 - b).clamp(min=1e-4)).clamp(0, 1)
    if mode == "darken":
        return torch.minimum(a, b)
    if mode == "lighten":
        return torch.maximum(a, b)
    raise ValueError(mode)


class V3Blend:
    """One layer over another with the game's blend modes (modify_texture blend_mode). alphamultiply: the layer's
    brightness multiplies the base's alpha -- a frame mask cutting the shape; the colour stays."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "blend"
    MODES = ["overlay", "multiply", "normal", "alphamultiply", "add", "screen", "colordodge", "darken", "lighten"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "base": ("IMAGE",), "layer": ("IMAGE",),
            "mode": (cls.MODES, {"default": "overlay"}),
            "opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            "fit": (["stretch", "tile", "none"], {"default": "stretch", "tooltip": "the layer to the base's size"}),
        }, "optional": {"base_mask": ("MASK",), "layer_mask": ("MASK",)}}

    def blend(self, base, layer, mode, opacity, fit, base_mask=None, layer_mask=None):
        base, base_mask = _split(base, base_mask)
        layer, layer_mask = _split(layer, layer_mask)
        H, W = base.shape[1:3]
        lm = _fit_mask(layer_mask, layer) if layer_mask is not None else torch.zeros(layer.shape[:3])
        la = torch.cat([layer, (1 - lm)[..., None]], dim=-1)
        if la.shape[1:3] != (H, W):
            if fit == "tile":
                la = la.repeat(1, -(-H // la.shape[1]), -(-W // la.shape[2]), 1)[:, :H, :W]
            elif fit == "stretch":
                la = torch.nn.functional.interpolate(la.permute(0, 3, 1, 2), size=(H, W), mode="bilinear").permute(0, 2, 3, 1)
            else:
                pad = torch.zeros((la.shape[0], H, W, 4))
                h, w = min(H, la.shape[1]), min(W, la.shape[2])
                pad[:, :h, :w] = la[:, :h, :w]
                la = pad
        l_rgb, l_a = la[..., :3], la[..., 3:4] * opacity
        b_alpha = 1 - (_fit_mask(base_mask, base) if base_mask is not None else torch.zeros(base.shape[:3]))
        if mode == "alphamultiply":
            lum = (l_rgb * torch.tensor([0.299, 0.587, 0.114])).sum(-1)
            new_alpha = b_alpha * (1 - l_a[..., 0] + l_a[..., 0] * lum)
            return base, (1 - new_alpha).clamp(0, 1)
        out = base * (1 - l_a) + _blend(base, l_rgb, mode) * l_a
        return out.clamp(0, 1), (1 - b_alpha).clamp(0, 1)


class V3Fill:
    """A flat colour canvas (header_color and the like); hex like #4a2b1f or 0.29 0.17 0.12."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "fill"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"width": ("INT", {"default": 1226, "min": 1, "max": 16384}),
                             "height": ("INT", {"default": 120, "min": 1, "max": 16384}),
                             "color": ("STRING", {"default": "#3b2a20"})}}

    def fill(self, width, height, color):
        c = color.strip()
        if c.startswith("#"):
            rgb = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        else:
            rgb = [float(v) for v in c.replace(",", " ").split()[:3]]
            rgb = [v / 255 for v in rgb] if max(rgb) > 1 else rgb
        return (torch.tensor(rgb, dtype=torch.float32).expand(1, height, width, 3).contiguous(),)


class V3Gray:
    """Grey by brightness, levels stretched to a range: an ornament layer the game tints itself (overlay)."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "gray"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",),
                             "low": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                             "high": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                             "normalize": ("BOOLEAN", {"default": False, "tooltip": "stretch the darkest..lightest to low..high"})}}

    def gray(self, image, low, high, normalize):
        image = _split(image)[0]
        g = (image * torch.tensor([0.299, 0.587, 0.114])).sum(-1, keepdim=True)
        if normalize:
            mn, mx = g.amin(dim=(1, 2, 3), keepdim=True), g.amax(dim=(1, 2, 3), keepdim=True)
            g = (g - mn) / (mx - mn).clamp(min=1e-6)
        return ((low + g * (high - low)).expand(*g.shape[:3], 3).contiguous(),)


class V3Text:
    """A caption in a font of the game (game/fonts) -- the window title or a number on the preview."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "text"

    @classmethod
    def INPUT_TYPES(cls):
        fonts = _fonts()
        default = next((f for f in fonts if "ParadoxVictorian-Condensed" in f), fonts[0])
        return {"required": {
            "image": ("IMAGE",), "text": ("STRING", {"default": "Бюджет", "multiline": True}),
            "font": (fonts, {"default": default}),
            "size": ("INT", {"default": 32, "min": 4, "max": 512}),
            "x": ("INT", {"default": 0, "min": -16384, "max": 16384, "tooltip": "from the anchor"}),
            "y": ("INT", {"default": 0, "min": -16384, "max": 16384}),
            "anchor": (["center", "left", "right"], {"default": "center"}),
            "color": ("STRING", {"default": "#f2e6c9"}),
            "shadow": ("BOOLEAN", {"default": True}),
        }}

    def text(self, image, text, font, size, x, y, anchor, color, shadow):
        im = _to_pil(image)
        f = ImageFont.truetype(str(Path(_roots()["game"]) / "fonts" / font), size)
        d = ImageDraw.Draw(im)
        W, H = im.size
        ax = {"center": W / 2, "left": 0, "right": W}[anchor] + x
        pa = {"center": "mm", "left": "lm", "right": "rm"}[anchor]
        if shadow:
            d.multiline_text((ax + max(1, size // 16), H / 2 + y + max(1, size // 16)), text, font=f, fill="#000000a0", anchor=pa, align=anchor)
        d.multiline_text((ax, H / 2 + y), text, font=f, fill=color, anchor=pa, align=anchor)
        return (_to_tensor(im)[0],)


class V3Sheet:
    """Variants side by side with captions (one line of `labels` per image): a sheet to choose from."""
    CATEGORY = "vic3"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "sheet"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "labels": ("STRING", {"default": "", "multiline": True}),
            "columns": ("INT", {"default": 4, "min": 1, "max": 32}),
            "cell_width": ("INT", {"default": 512, "min": 32, "max": 4096}),
            "background": ("STRING", {"default": "#202020"}),
        }}

    def sheet(self, images, labels, columns, cell_width, background):
        names = [s for s in labels.splitlines()]
        cells = []
        for i in range(images.shape[0]):
            im = _to_pil(images[i:i + 1])
            im = im.resize((cell_width, max(1, round(im.height * cell_width / im.width))), Image.LANCZOS)
            cells.append(im)
        cap = 28
        ch = max(c.height for c in cells) + cap
        rows = -(-len(cells) // columns)
        pad = 8
        out = Image.new("RGB", (columns * (cell_width + pad) + pad, rows * (ch + pad) + pad), background)
        d = ImageDraw.Draw(out)
        try:
            f = ImageFont.truetype(str(Path(_roots()["game"]) / "fonts" / "NotoSans" / "NotoSans-Regular.ttf"), 18)
        except (OSError, KeyError):
            f = ImageFont.load_default()
        for i, c in enumerate(cells):
            x, y = pad + (i % columns) * (cell_width + pad), pad + (i // columns) * (ch + pad)
            d.text((x + 4, y + 4), names[i] if i < len(names) else str(i + 1), font=f, fill="#e0e0e0")
            out.paste(c, (x, y + cap))
        return (_to_tensor(out)[0],)


NODE_CLASS_MAPPINGS = {c.__name__: c for c in (V3LoadGameImage, V3Roll, V3SeamMask, V3Tile, V3Mirror, V3SpriteBorder,
                                               V3Blend, V3Fill, V3Gray, V3Text, V3Sheet)}
NODE_DISPLAY_NAME_MAPPINGS = {
    "V3LoadGameImage": "V3 Load Game Image", "V3Roll": "V3 Roll", "V3SeamMask": "V3 Seam Mask", "V3Tile": "V3 Tile",
    "V3Mirror": "V3 Mirror", "V3SpriteBorder": "V3 Sprite Border", "V3Blend": "V3 Blend", "V3Fill": "V3 Fill",
    "V3Gray": "V3 Gray", "V3Text": "V3 Text", "V3Sheet": "V3 Sheet",
}
