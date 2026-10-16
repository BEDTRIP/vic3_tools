"""A test bench: the game left open in the sandbox VM, steps on it, screenshots, their difference.

The loop "edit a .gui → see it" without a run: ``start`` opens the game in debug mode (a new game or a save) and
leaves it paused; ``step`` sends the mod files changed since (the game in debug mode re-reads them) and takes
``vic3_ui.ps1`` steps in the guest's session (shots, clicks, hovers, console); ``shot`` is a step that takes a
screenshot, cut to a region; ``diff`` tells what changed between two shots; ``stop`` closes the game.

The VM side is ``bridge/vm/Invoke-SandboxRun.ps1`` and the game scripts are ``bridge/game`` of this repo; a project's
hooks (its mod's log lines, commands after loading, screens) come from
``[bench] hooks = '<folder with vic3_hooks.ps1>'`` in ``vic3tools.toml``. Shots live in ``<cache>/bench/<step>/``.
Cutting and comparing images needs Pillow (``pip install vic3tools[img]``).
"""

from __future__ import annotations

import datetime
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vic3tools.core import paths

VM_RUN = Path(__file__).resolve().parents[1] / "bridge" / "vm" / "Invoke-SandboxRun.ps1"


@dataclass
class Step:
    id: str
    out: Path
    code: int
    log: str  # the tail of the output

    @property
    def shots(self) -> list[Path]:
        return sorted(self.out.glob("*.png"))


def bench_dir() -> Path:
    d = paths.cache_dir() / "bench"
    d.mkdir(parents=True, exist_ok=True)
    return d


GAME_SCRIPTS = Path(__file__).resolve().parents[1] / "bridge" / "game"


def scripts_dir(cfg: paths.Config) -> Path:
    """The game scripts: ``[bench] scripts`` if a project has its own, else this repo's ``bridge/game``."""
    p = Path(cfg.get("bench", "scripts") or GAME_SCRIPTS)
    if not (p / "vic3_ui.ps1").is_file():
        raise FileNotFoundError(f"no vic3_ui.ps1 in {p} ([bench] scripts)")
    return p


def _run(cfg: paths.Config, script: str, params: dict, content_load: Path | None = None, with_game: bool = False,
         start_save: str = "", name: str = "", timeout: int = 1800) -> Step:
    sid = datetime.datetime.now().strftime("b%m%d_%H%M%S") + (f"_{name}" if name else "")
    out = bench_dir() / sid
    out.mkdir(parents=True, exist_ok=True)
    pj = out / "params.json"
    pj.write_text(json.dumps(params, ensure_ascii=False), encoding="utf-8")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(VM_RUN),
           "-ScriptDir", str(scripts_dir(cfg)), "-Script", script, "-OutDir", str(out), "-ParamsJson", str(pj)]
    vm = cfg.get("bench", "vm")
    if vm:
        cmd += ["-Name", vm]
    hooks = cfg.get("bench", "hooks")
    if hooks:
        cmd += ["-HooksDir", str(hooks)]
    content_load = content_load or (bench_dir() / "content_load.json")  # a step sends the mods of the last start
    if content_load.is_file():
        cmd += ["-ContentLoad", str(content_load)]
    if with_game:
        cmd.append("-WithGame")
    if start_save:
        cmd += ["-StartSave", start_save]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    text = (p.stdout + p.stderr).decode("utf-8", "replace")
    (out / "bench.log").write_text(text, encoding="utf-8")
    return Step(sid, out, p.returncode, "\n".join(text.strip().splitlines()[-15:]))


def content_load_for(mods: list[Path]) -> Path:
    """A content_load.json with these mod folders (the game's format, host paths)."""
    p = bench_dir() / "content_load.json"
    data = {"enabledMods": [{"path": str(Path(m).resolve())} for m in mods], "disabledDLC": [], "enabledUGC": []}
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def start(cfg: paths.Config, mods: list[Path] | None = None, save: str = "", tag: str = "SWI",
          load_wait: int = 400) -> Step:
    """Open the game in the VM and leave it paused: a new game as ``tag``, or the host's save ``save``."""
    params = {"RunMinutes": 0, "AiTag": "", "KeepOpen": True, "Tag": tag, "LoadWaitSec": load_wait}
    if not save:
        params["NewGame"] = True
    cl = content_load_for(mods) if mods else None
    return _run(cfg, "run_vic3_sandbox.ps1", params, cl, start_save=save, name="start")


def step(cfg: paths.Config, do: str, name: str = "") -> Step:
    """``vic3_ui.ps1`` steps on the open game (changed mod files are sent first)."""
    return _run(cfg, "vic3_ui.ps1", {"Do": do}, with_game=True, name=name)


def stop(cfg: paths.Config) -> Step:
    return _run(cfg, "vic3_ui.ps1", {"Do": "close"}, with_game=True, name="stop")


# --- images ----------------------------------------------------------------------------------------------------------


def _pil():
    try:
        from PIL import Image, ImageChops
    except ImportError as e:
        raise FileNotFoundError("cutting and comparing shots needs Pillow: pip install vic3tools[img]") from e
    return Image, ImageChops


def box(size: tuple[int, int], crop: str | None) -> tuple[int, int, int, int]:
    """``x0,y0,x1,y1`` in fractions (0..1) or pixels → a pixel box inside ``size``."""
    w, h = size
    if not crop:
        return 0, 0, w, h
    v = [float(x) for x in crop.split(",")]
    if len(v) != 4:
        raise ValueError(f"crop is x0,y0,x1,y1: {crop}")
    if all(x <= 1 for x in v):
        v = [v[0] * w, v[1] * h, v[2] * w, v[3] * h]
    x0, y0, x1, y1 = (round(x) for x in v)
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def cut(src: Path, crop: str | None, dst: Path) -> Path:
    Image, _ = _pil()
    im = Image.open(src)
    im.crop(box(im.size, crop)).save(dst)
    return dst


@dataclass
class Diff:
    changed: float  # share of pixels that differ (0..1)
    bbox: tuple[int, int, int, int] | None  # the changed area, pixels
    image: Path | None  # the two shots side by side with the change marked


def diff(a: Path, b: Path, crop: str | None = None, out: Path | None = None, tolerance: int = 12) -> Diff:
    """What differs between two shots (of the same size): the share of changed pixels and where."""
    Image, ImageChops = _pil()
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        raise ValueError(f"different sizes: {ia.size} and {ib.size}")
    bx = box(ia.size, crop)
    ia, ib = ia.crop(bx), ib.crop(bx)
    d = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > tolerance else 0)
    hist = d.histogram()
    changed = hist[255] / max(1, ia.width * ia.height)
    bb = d.getbbox()
    img = None
    if out is not None:
        side = Image.new("RGB", (ia.width * 2 + 8, ia.height), (255, 0, 255))
        side.paste(ia, (0, 0))
        side.paste(ib, (ia.width + 8, 0))
        if bb:
            from PIL import ImageDraw

            dr = ImageDraw.Draw(side)
            for dx in (0, ia.width + 8):
                dr.rectangle((bb[0] + dx, bb[1], bb[2] + dx - 1, bb[3] - 1), outline=(255, 0, 0), width=2)
        side.save(out)
        img = out
    if bb:
        bb = (bb[0] + bx[0], bb[1] + bx[1], bb[2] + bx[0], bb[3] + bx[1])
    return Diff(changed, bb, img)
