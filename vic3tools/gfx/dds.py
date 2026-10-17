"""DDS the way vanilla interface textures are stored: uncompressed 32-bit BGRA with the full mip chain.

Vanilla 1.13 (gfx/interface, 2026-10-17): goods 49 of 54, laws 127 of 132, buildings 99 of 101, production methods
271 of 290, company logos 159 of 195, backgrounds 67 of 79 are raw 32-bit with mips; DXT5 / BC7 are a handful.
Pillow reads every DDS the game uses; it writes no mips, so the writer is here.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PITCH, DDSD_PIXELFORMAT, DDSD_MIPMAPCOUNT = 0x1, 0x2, 0x4, 0x8, 0x1000, 0x20000
DDPF_ALPHAPIXELS, DDPF_RGB = 0x1, 0x40
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000


@dataclass
class DdsInfo:
    width: int
    height: int
    format: str  # "BGRA8" (raw 32-bit), "DXT1", "DXT5", "DX10:<dxgi>", "raw<bits>"
    mips: int

    @property
    def vanilla_like(self) -> bool:
        return self.format == "BGRA8" and self.mips > 1


def info(path: Path) -> DdsInfo:
    d = Path(path).read_bytes()[:148]
    if d[:4] != b"DDS ":
        raise ValueError(f"{path}: not a DDS")
    _, _, h, w, _, _, mips = struct.unpack_from("<7I", d, 4)
    pf_flags, fourcc, bits, rm, gm, bm, am = struct.unpack_from("<I4s5I", d, 80)
    if fourcc == b"DX10":
        fmt = f"DX10:{struct.unpack_from('<I', d, 128)[0]}"
    elif fourcc.strip(b"\0"):
        fmt = fourcc.decode("latin1")
    elif bits == 32 and (rm, gm, bm) == (0xFF0000, 0xFF00, 0xFF):
        fmt = "BGRA8"
    else:
        fmt = f"raw{bits}"
    return DdsInfo(w, h, fmt, max(mips, 1))


def mip_chain(img):
    """The image and its halvings down to 1x1 (box filter on premultiplied alpha: no dark fringes)."""
    from PIL import Image

    img = img.convert("RGBA")
    levels = [img]
    while img.width > 1 or img.height > 1:
        w, h = max(1, img.width // 2), max(1, img.height // 2)
        pre = img.convert("RGBa").resize((w, h), Image.BOX)
        img = pre.convert("RGBA")
        levels.append(img)
    return levels


def write(img, path: Path, mips: bool = True) -> Path:
    """`img` (PIL) -> uncompressed BGRA8 DDS with the full mip chain, as vanilla interface textures."""
    levels = mip_chain(img) if mips else [img.convert("RGBA")]
    w, h = levels[0].size
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT
    caps = DDSCAPS_TEXTURE
    if len(levels) > 1:
        flags |= DDSD_MIPMAPCOUNT
        caps |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    header = struct.pack("<4s7I44x", b"DDS ", 124, flags, h, w, w * 4, 0, len(levels))
    header += struct.pack("<2I4s5I", 32, DDPF_RGB | DDPF_ALPHAPIXELS, b"\0\0\0\0", 32,
                          0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    header += struct.pack("<5I", caps, 0, 0, 0, 0)
    body = b"".join(lv.tobytes("raw", "BGRA") for lv in levels)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(header + body)
    tmp.replace(path)
    return path
