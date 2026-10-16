"""Text from screenshots with Windows' own OCR (``Windows.Media.Ocr``; ``data/win_ocr.ps1``): words with boxes,
grouped into rows. Nothing to install on Windows 10+ — the OCR languages are Windows' own (en-US and ru are usual);
other systems have no OCR here. A shot is upscaled ×2 first (Pillow): the game's small table text reads better.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT = Path(__file__).with_name("data") / "win_ocr.ps1"


@dataclass
class Word:
    t: str
    x: float
    y: float
    w: float
    h: float

    @property
    def mid(self) -> float:
        return self.y + self.h / 2


@dataclass
class Row:
    y: float
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.t for w in self.words)


def available() -> bool:
    return sys.platform == "win32" and SCRIPT.is_file()


def read(paths: list[Path], lang: str = "en-US", upscale: int = 2, crop: tuple[int, int, int, int] | None = None
         ) -> dict[Path, list[Word]]:
    """The words of each picture, in the picture's own pixels (``crop``: the part read, x0, y0, x1, y1)."""
    if not available():
        raise RuntimeError("OCR needs Windows (Windows.Media.Ocr)")
    with tempfile.TemporaryDirectory() as tmp:
        work, scale = [], {}
        for i, p in enumerate(paths):
            src = Path(p)
            if upscale > 1 or crop:
                from PIL import Image

                im = Image.open(src)
                if crop:
                    im = im.crop(crop)
                if upscale > 1:
                    im = im.resize((im.width * upscale, im.height * upscale), Image.LANCZOS)
                q = Path(tmp) / f"{i}.png"
                im.save(q)
            else:
                q = src
            work.append(q)
            scale[str(q.resolve())] = src
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Lang", lang,
               *[str(q) for q in work]]
        p = subprocess.run(cmd, capture_output=True, timeout=300, env={**os.environ})
        if p.returncode:
            raise RuntimeError(p.stderr.decode("utf-8", "replace").strip()[-500:])
    out: dict[Path, list[Word]] = {}
    ox, oy = (crop[0], crop[1]) if crop else (0, 0)
    for line in p.stdout.decode("utf-8-sig", "replace").splitlines():
        if not line.strip():
            continue
        d = json.loads(line.lstrip("﻿"))
        src = scale.get(str(Path(d["path"]).resolve()), Path(d["path"]))
        k = max(1, upscale)
        out[src] = [Word(w["t"], w["x"] / k + ox, w["y"] / k + oy, w["w"] / k, w["h"] / k) for w in d["words"]]
    return out


def rows(words: list[Word], tolerance: float | None = None) -> list[Row]:
    """Words grouped into lines by their middle (within half a word's height), each line left to right."""
    out: list[Row] = []
    for w in sorted(words, key=lambda w: w.mid):
        tol = tolerance if tolerance is not None else max(3.0, w.h / 2)
        if out and abs(out[-1].y - w.mid) <= tol:
            out[-1].words.append(w)
        else:
            out.append(Row(w.mid, [w]))
    for r in out:
        r.words.sort(key=lambda w: w.x)
    return out
