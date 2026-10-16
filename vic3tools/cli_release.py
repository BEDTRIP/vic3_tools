"""``v3 release``: get a mod ready for the Steam Workshop — check, build, record; ``zip`` packs a set."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from vic3tools import release
from vic3tools.core import paths, vfs
from vic3tools.i18n import t


def add_parsers(sub) -> None:
    p = sub.add_parser("release", help="get a mod ready for the Steam Workshop: checks, a clean build, change note, "
                       "description, the SteamCMD VDF; a set as a zip",
                       description=release.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    rsub = p.add_subparsers(dest="release_command", required=True, metavar="<command>")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("mod", help="the mod: its folder, or its name in the active playset")
    common.add_argument("--version", help="the version of this release (default: the one in metadata.json)")
    common.add_argument("--playset", help="the playset for dependencies and lint (default: the active one)")

    s = rsub.add_parser("check", parents=[common], help="what would go wrong: metadata, preview, game version, "
                        "dependencies, what is left out, description, version, lint")
    s.add_argument("--no-lint", action="store_true", help="skip v3 lint (it runs tiger: a minute or two)")
    s.set_defaults(func=cmd_check)

    s = rsub.add_parser("build", parents=[common], help="check, then a clean copy + change note + descriptions + "
                        "VDF for SteamCMD in the tool's home")
    s.add_argument("--no-lint", action="store_true")
    s.add_argument("--force", action="store_true", help="build despite errors of the check")
    s.add_argument("--out", type=Path, help="where to build (default: <tool home>/release)")
    s.set_defaults(func=cmd_build)

    s = rsub.add_parser("done", parents=[common], help="after the upload: record the Workshop ID and the published "
                        "description in the mod")
    s.add_argument("--workshop-id", help="the item's ID (first upload: SteamCMD prints it)")
    s.add_argument("--with-description", action="store_true", help="the description went up too")
    s.add_argument("--out", type=Path)
    s.set_defaults(func=cmd_done)

    s = rsub.add_parser("zip", help="a ready set for one game version: the playset's mods (clean) + load order")
    s.add_argument("--playset", help="the playset (default: the active one)")
    s.add_argument("--out", type=Path, help="the zip (default: <tool home>/release/zip/<playset> <game> <date>.zip)")
    s.set_defaults(func=cmd_zip)


def _mod(args, cfg) -> tuple[Path, vfs.ModSet | None]:
    try:
        ms = vfs.ModSet.from_playset(args.playset, cfg)
    except Exception:  # noqa: BLE001 — no playset: a folder still works
        ms = None
    p = Path(args.mod)
    if p.is_dir():
        return p.resolve(), ms
    if ms is None:
        raise FileNotFoundError(args.mod)
    return ms.find(args.mod).path, ms


def _ids(ms: vfs.ModSet | None) -> set[str] | None:
    if ms is None:
        return None
    ids = set()
    for m in ms.mods:
        try:
            ids.add(str(release.read_metadata(m.path).get("id")))
        except (OSError, ValueError):
            pass
    return ids


def _game_version(cfg) -> str | None:
    r = paths.resolve_roots(cfg)["game"]
    return paths.game_version(r.path) if r.ok else None


def _lint(mod: Path, playset: str | None) -> tuple[int, int] | None:
    cmd = [sys.executable, "-m", "vic3tools.cli", "lint", str(mod), "--json"]
    if playset:
        cmd += ["--playset", playset]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=900)
        data = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    reps = data.get("reports") or []
    return len(reps), sum(1 for r in reps if r.get("severity") == "error")


def _report(mod: Path, args, cfg, ms) -> int:
    gv = _game_version(cfg)
    probs = release.check(mod, gv, _ids(ms), args.version)
    meta = release.read_metadata(mod) if release.metadata_path(mod).is_file() else {}
    print(t("release_head", name=meta.get("name", mod.name), version=args.version or meta.get("version", "?"),
            game=gv or "?", tag=release.last_tag(mod) or "—"))
    sel = release.select(release.source_files(mod), meta.get("picture"))
    print(t("release_files", keep=len(sel.keep), left=sum(sel.left_out.values())))
    if sel.left_out:
        print("  " + ", ".join(f"{k} {n}" for k, n in sorted(sel.left_out.items(), key=lambda x: -x[1])[:12]))
    if not getattr(args, "no_lint", False):
        lr = _lint(mod, args.playset)
        if lr is None:
            probs.append(release.Problem("warn", "release_lint_failed", {}))
        elif lr[0]:
            probs.append(release.Problem("error" if lr[1] else "warn", "release_lint", {"n": lr[0], "errors": lr[1]}))
    for pr in probs:
        print(f"  {pr.severity}: " + t(pr.key, **pr.args))
    errors = sum(1 for pr in probs if pr.severity == "error")
    print(t("release_summary", errors=errors, warns=len(probs) - errors))
    return errors


def cmd_check(args, cfg) -> int:
    mod, ms = _mod(args, cfg)
    return 1 if _report(mod, args, cfg, ms) else 0


def _steamcmd(cfg) -> str:
    """SteamCMD: ``[release] steamcmd`` of the config, else on PATH, else C:/steamcmd; else just the name."""
    for c in (cfg.get("release", "steamcmd"), shutil.which("steamcmd"), r"C:\steamcmd\steamcmd.exe"):
        if c and Path(c).is_file():
            return f'"{c}"' if " " in str(c) else str(c)
    return "steamcmd"


def _out(args) -> Path:
    return args.out or paths.tool_home() / "release"


def cmd_build(args, cfg) -> int:
    mod, ms = _mod(args, cfg)
    if _report(mod, args, cfg, ms) and not args.force:
        print(t("release_stop"))
        return 1
    b = release.build(mod, _out(args), args.version, _game_version(cfg))
    print(t("release_built", out=b.out, files=b.files))
    for lang, path in b.descriptions.items():
        old = release.published_path(mod, lang)
        new = path.read_text(encoding="utf-8")
        if not old.is_file():
            print(t("release_desc_new", lang=lang, n=len(new)))
            continue
        diff = list(difflib.unified_diff(old.read_text(encoding="utf-8").splitlines(), new.splitlines(),
                                         "published", "this release", lineterm="", n=1))
        print(t("release_desc_diff", lang=lang, n=len(diff)) if diff else t("release_desc_same", lang=lang))
        for line in diff[:60]:
            print("    " + line)
    print(t("release_next_new") if b.new_item else t("release_next_update", id=b.workshop_id))
    sc = _steamcmd(cfg)
    print(f"  {sc} +login <steam user> +workshop_build_item \"{b.out / 'upload.vdf'}\" +quit")
    if "en" in b.descriptions:
        print(t("release_with_desc"))
        print(f"  {sc} +login <steam user> +workshop_build_item \"{b.out / 'upload_with_description.vdf'}\" +quit")
    if "ru" in b.descriptions:
        print(t("release_ru_by_hand", path=b.descriptions["ru"]))
    print(t("release_then_done", mod=args.mod, version=b.version))
    return 0


def cmd_done(args, cfg) -> int:
    mod, _ms = _mod(args, cfg)
    meta = release.read_metadata(mod)
    version = args.version or meta["version"]
    out = _out(args) / release.slug(meta, mod) / version
    if not out.is_dir():
        print(t("release_no_build", out=out))
        return 1
    changed = release.done(mod, out, args.workshop_id, args.with_description)
    print(t("release_done", changed=", ".join(changed) or "—", tag=release.TAG_PREFIX + version))
    return 0


def cmd_zip(args, cfg) -> int:
    ms = vfs.ModSet.from_playset(args.playset, cfg)
    gv = _game_version(cfg)
    mods = [(m.name, m.path) for m in ms.mods if m.kind not in ("engine", "vanilla")]
    name = args.playset or ms.source or "playset"
    out = args.out or paths.tool_home() / "release" / "zip" / f"{name} {gv or ''} {date.today()}.zip".replace("  ", " ")
    path, n = release.zip_set(mods, out, gv, f"{name} — Victoria 3 {gv or ''}")
    print(t("release_zip", path=path, mods=len(mods), files=n))
    return 0
