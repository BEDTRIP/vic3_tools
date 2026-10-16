"""Release a mod to the Steam Workshop: checks, a clean build, the change note, the description, the SteamCMD VDF.

The flow (``v3 release``, stage 14 of the plan):

- ``check`` — what would go wrong: the metadata, the preview, the game version, dependencies missing from the playset,
  what the build leaves out, the description's length and images, the version against the last release tag.
- ``build`` — a clean copy in the tool's home (``release/<mod>/<version>/content``): only the folders the game reads,
  ``.metadata`` and the preview, and from a git checkout only files committed at HEAD; ``docs/``, ``_archive/``,
  ``_to_delete/``, ``*.md``, scripts, sources of pictures stay out. Beside it: ``changenote.txt`` (a draft from git
  since the last ``release/*`` tag — edit it), ``description.<lang>.bbcode`` (rendered from the mod's template),
  ``upload.vdf`` (content, preview, title, change note) and ``upload_with_description.vdf`` (the same + the English
  description). The user runs SteamCMD with one of them; the description goes up only after the user has seen its diff.
- ``done`` — after the upload: the Workshop ID and the published description are recorded in the mod's repo, so the
  next release updates the same item and diffs against what is on Steam.

The mod's own release data is a key ``vic3tools`` in ``.metadata/metadata.json``: ``workshop_id``, ``links`` (name →
``workshop:<id>`` / ``collection:<id>`` / a URL) for ``{link:name}`` in the description. Templates:
``docs/workshop/description.<lang>.bbcode``; ``{img:name}`` is ``docs/workshop/img/<name>.png`` linked as a raw GitHub
URL pinned to the release tag (push the tag before the upload), ``{version}``, ``{game_version}``, ``{link:name}``.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

APP_ID = 529340
DESC_LIMIT = 8000  # characters in a Workshop description
PREVIEW_LIMIT = 1024 * 1024  # bytes of the preview image
GAME_DIRS = ("common", "content_source", "dlc", "dlc_metadata", "events", "fonts", "gfx", "gui", "localization",
             "map_data", "music", "sound")
JUNK_SUFFIXES = {".md", ".py", ".pyc", ".bat", ".cmd", ".ps1", ".sh", ".psd", ".xcf", ".kra", ".zip", ".7z", ".rar",
                 ".bak", ".orig", ".log", ".tmp"}
JUNK_DIRS = {"_archive", "_to_delete", "docs", "__pycache__", ".git", ".github", ".obsidian", ".vscode", ".claude"}
CUSTOM_KEY = "vic3tools"
TEMPLATE_DIR = "docs/workshop"
TAG_PREFIX = "release/"
LANGS = ("en", "ru")
_PLACEHOLDER = re.compile(r"\{(img|link|version|game_version)(?::([A-Za-z0-9_.\-]+))?\}")


@dataclass
class Problem:
    severity: str  # "error" stops a build, "warn" is shown
    key: str  # message key of the catalog
    args: dict = field(default_factory=dict)


@dataclass
class Selection:
    keep: list[str]  # mod-relative posix paths going into the build
    left_out: dict[str, int]  # top-level entry (or "*.md" style group) → files left out


# --- metadata --------------------------------------------------------------------------------------------------------


def metadata_path(mod: Path) -> Path:
    return mod / ".metadata" / "metadata.json"


def read_metadata(mod: Path) -> dict:
    return json.loads(metadata_path(mod).read_text(encoding="utf-8-sig"))


def write_metadata(path: Path, meta: dict) -> None:
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def custom(meta: dict) -> dict:
    v = meta.get(CUSTOM_KEY)
    return v if isinstance(v, dict) else {}


def slug(meta: dict, mod: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", meta.get("name") or mod.name).strip("_") or "mod"


# --- what goes in ----------------------------------------------------------------------------------------------------


def _git(mod: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(mod), *args], capture_output=True, text=True, encoding="utf-8",
                           timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def is_git(mod: Path) -> bool:
    out = _git(mod, "rev-parse", "--show-toplevel")
    return out is not None and Path(out.strip()).resolve() == mod.resolve()


def source_files(mod: Path) -> list[str]:
    """Files of the mod: committed at HEAD in a git checkout (so the build is the commit), else everything on disk."""
    if is_git(mod):
        out = _git(mod, "ls-tree", "-r", "--name-only", "-z", "HEAD")
        if out is not None:
            return sorted(f for f in out.split("\0") if f)
    return sorted(p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_file())


def select(files: list[str], picture: str | None) -> Selection:
    keep: list[str] = []
    left_out: dict[str, int] = {}
    for f in files:
        parts = f.split("/")
        top = parts[0]
        why = None
        if f == ".metadata/metadata.json" or (picture and f == picture):
            keep.append(f)
            continue
        if top not in GAME_DIRS:
            why = top if len(parts) > 1 else f
        elif any(p in JUNK_DIRS for p in parts[:-1]):
            why = next(p for p in parts[:-1] if p in JUNK_DIRS) + "/"
        elif Path(f).suffix.lower() in JUNK_SUFFIXES:
            why = "*" + Path(f).suffix.lower()
        if why:
            left_out[why] = left_out.get(why, 0) + 1
        else:
            keep.append(f)
    return Selection(keep, left_out)


# --- checks ----------------------------------------------------------------------------------------------------------


def last_tag(mod: Path) -> str | None:
    out = _git(mod, "describe", "--tags", "--abbrev=0", "--match", TAG_PREFIX + "*")
    return out.strip() if out else None


def check(mod: Path, game_version: str | None, playset_ids: set[str] | None = None,
          version: str | None = None) -> list[Problem]:
    probs: list[Problem] = []
    try:
        meta = read_metadata(mod)
    except FileNotFoundError:
        return [Problem("error", "release_no_metadata", {"path": metadata_path(mod)})]
    except ValueError as e:
        return [Problem("error", "release_bad_metadata", {"error": e})]
    for k in ("name", "id", "version", "supported_game_version", "short_description", "picture"):
        if not meta.get(k):
            probs.append(Problem("error", "release_meta_missing", {"key": k}))
    pic = meta.get("picture")
    if pic:
        p = mod / pic
        if not p.is_file():
            probs.append(Problem("error", "release_no_picture", {"path": pic}))
        else:
            if p.stat().st_size > PREVIEW_LIMIT:
                probs.append(Problem("error", "release_picture_big", {"path": pic, "kb": p.stat().st_size // 1024}))
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif"):
                probs.append(Problem("warn", "release_picture_type", {"path": pic}))
    sgv = meta.get("supported_game_version")
    if sgv and game_version and not fnmatch.fnmatch(game_version, sgv):
        probs.append(Problem("warn", "release_game_version", {"supported": sgv, "game": game_version}))
    if playset_ids is not None:
        for r in meta.get("relationships") or []:
            if r.get("rel_type") == "dependency" and r.get("id") not in playset_ids:
                probs.append(Problem("warn", "release_dependency", {"name": r.get("display_name") or r.get("id")}))
    v = version or meta.get("version")
    tag = last_tag(mod)
    if tag and v and tag == TAG_PREFIX + v:
        probs.append(Problem("error", "release_same_version", {"version": v}))
    if is_git(mod):
        if _git(mod, "status", "--porcelain", "--untracked-files=no"):
            probs.append(Problem("warn", "release_dirty", {}))
    for lang in LANGS:
        tpl = mod / TEMPLATE_DIR / f"description.{lang}.bbcode"
        if tpl.is_file():
            text, missing = render(mod, tpl.read_text(encoding="utf-8-sig"), meta, TAG_PREFIX + (v or "0"))
            for m in missing:
                probs.append(Problem("error", "release_desc_missing", {"lang": lang, "what": m}))
            if len(text) > DESC_LIMIT:
                probs.append(Problem("error", "release_desc_long", {"lang": lang, "n": len(text), "limit": DESC_LIMIT}))
        elif lang == "en":
            probs.append(Problem("warn", "release_no_template", {"path": tpl.relative_to(mod).as_posix()}))
    return probs


# --- the description -------------------------------------------------------------------------------------------------


def github_raw_base(mod: Path) -> str | None:
    """``https://raw.githubusercontent.com/<owner>/<repo>`` of the checkout's ``origin``, if it is on GitHub."""
    url = (_git(mod, "remote", "get-url", "origin") or "").strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}" if m else None


def link_url(target: str) -> str:
    kind, _, rest = target.partition(":")
    if kind in ("workshop", "collection") and rest.isdigit():
        return f"https://steamcommunity.com/sharedfiles/filedetails/?id={rest}"
    return target


def render(mod: Path, template: str, meta: dict, tag: str, game_version: str | None = None) -> tuple[str, list[str]]:
    """The description with its placeholders filled; and what could not be filled."""
    missing: list[str] = []
    base = github_raw_base(mod)
    links = custom(meta).get("links") or {}

    def sub(m: re.Match) -> str:
        kind, name = m.group(1), m.group(2)
        if kind == "version":
            return str(meta.get("version", ""))
        if kind == "game_version":
            return game_version or str(meta.get("supported_game_version", ""))
        if kind == "img":
            rel = f"{TEMPLATE_DIR}/img/{name}.png"
            if not (mod / rel).is_file():
                missing.append(rel)
            if not base:
                missing.append("origin on GitHub (for image links)")
                return m.group(0)
            return f"{base}/{tag}/{rel}"
        if name not in links:
            missing.append(f"link {name} ({CUSTOM_KEY}.links in metadata.json)")
            return m.group(0)
        return link_url(links[name])

    return _PLACEHOLDER.sub(sub, template), sorted(set(missing))


# --- change note, VDF ------------------------------------------------------------------------------------------------


def changes(mod: Path, since: str | None) -> list[str]:
    """Subjects of the commits since the tag that touch what goes into the build (not documents, tools, notes).
    No tag yet — nothing: a first release's note is written by hand."""
    if not since:
        return []
    dirs = [d for d in GAME_DIRS if (mod / d).is_dir()] + [".metadata"]
    out = _git(mod, "log", f"{since}..HEAD", "--no-merges", "--format=%s", "--", *dirs) or ""
    seen, lines = set(), []
    for s in out.splitlines():
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            lines.append(s)
    return lines


def _vdf_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def vdf(fields: dict[str, str]) -> str:
    body = "".join(f"\t{_vdf_str(k)}\t{_vdf_str(str(v))}\n" for k, v in fields.items())
    return '"workshopitem"\n{\n' + body + "}\n"


# --- build -----------------------------------------------------------------------------------------------------------


@dataclass
class Build:
    out: Path
    version: str
    files: int
    left_out: dict[str, int]
    workshop_id: str
    new_item: bool
    descriptions: dict[str, Path]


def build(mod: Path, out_root: Path, version: str | None = None, game_version: str | None = None) -> Build:
    meta = read_metadata(mod)
    version = version or meta["version"]
    meta["version"] = version
    out = out_root / slug(meta, mod) / version
    if out.exists():
        shutil.rmtree(out)
    content = out / "content"
    sel = select(source_files(mod), meta.get("picture"))
    git = is_git(mod)
    for rel in sel.keep:
        dst = content / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if git and rel != ".metadata/metadata.json":
            data = subprocess.run(["git", "-C", str(mod), "show", f"HEAD:{rel}"], capture_output=True,
                                  check=True).stdout
            dst.write_bytes(data)
        elif rel != ".metadata/metadata.json":
            shutil.copy2(mod / rel, dst)
    # the uploaded copy carries no key of ours: the game and the launcher see the metadata as they know it
    write_metadata(content / ".metadata" / "metadata.json", {k: v for k, v in meta.items() if k != CUSTOM_KEY})
    tag = TAG_PREFIX + version
    since = last_tag(mod) if git else None
    note = "\n".join(f"- {s}" for s in changes(mod, since)) if since else "First release."
    (out / "changenote.txt").write_text(f"{version}\n{note}\n", encoding="utf-8")
    descs: dict[str, Path] = {}
    for lang in LANGS:
        tpl = mod / TEMPLATE_DIR / f"description.{lang}.bbcode"
        if tpl.is_file():
            text, _ = render(mod, tpl.read_text(encoding="utf-8-sig"), meta, tag, game_version)
            descs[lang] = out / f"description.{lang}.bbcode"
            descs[lang].write_text(text, encoding="utf-8")
    wid = str(custom(meta).get("workshop_id") or "")
    fields = {"appid": str(APP_ID), "publishedfileid": wid or "0", "contentfolder": str(content.resolve()),
              "previewfile": str((content / meta["picture"]).resolve()), "title": meta.get("name", "")}
    if not wid:
        fields["visibility"] = "2"  # a new item starts private: the user looks at it, then makes it public
    fields["changenote"] = "@CHANGENOTE@"
    note_text = (out / "changenote.txt").read_text(encoding="utf-8")
    plain = vdf(fields).replace('"@CHANGENOTE@"', _vdf_str(note_text))
    (out / "upload.vdf").write_text(plain, encoding="utf-8")
    if "en" in descs:
        with_desc = dict(fields)
        with_desc["description"] = descs["en"].read_text(encoding="utf-8")
        (out / "upload_with_description.vdf").write_text(
            vdf(with_desc).replace('"@CHANGENOTE@"', _vdf_str(note_text)), encoding="utf-8")
    return Build(out, version, len(sel.keep), sel.left_out, wid, not wid, descs)


def published_path(mod: Path, lang: str) -> Path:
    return mod / TEMPLATE_DIR / "published" / f"description.{lang}.bbcode"


def done(mod: Path, out: Path, workshop_id: str | None, with_description: bool) -> list[str]:
    """Record a finished upload in the mod: the Workshop ID (first upload), the published descriptions."""
    changed = []
    meta = read_metadata(mod)
    c = custom(meta)
    if workshop_id and str(c.get("workshop_id") or "") != workshop_id:
        c["workshop_id"] = workshop_id
        meta[CUSTOM_KEY] = c
        write_metadata(metadata_path(mod), meta)
        changed.append(metadata_path(mod).relative_to(mod).as_posix())
    if with_description:
        for lang in LANGS:
            src = out / f"description.{lang}.bbcode"
            if src.is_file():
                dst = published_path(mod, lang)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                changed.append(dst.relative_to(mod).as_posix())
    return changed


# --- a set as a zip --------------------------------------------------------------------------------------------------


def zip_set(mods: list[tuple[str, Path]], out: Path, game_version: str | None, title: str) -> tuple[Path, int]:
    """A ready set for one game version: each mod's clean folder under ``mod/<folder>``, and ``README.txt`` with the
    load order. The files are taken as they are on disk (the installed copies of the set)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        order = []
        for name, path in mods:
            try:
                pic = read_metadata(path).get("picture")
            except (OSError, ValueError):
                pic = None
            sel = select(sorted(p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()), pic)
            folder = re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or path.name
            for rel in sel.keep:
                z.write(path / rel, f"mod/{folder}/{rel}")
                n += 1
            order.append(f"{len(order) + 1:>3}. {name}")
        readme = (f"{title}\nGame version: {game_version or '?'}\n\nPut the folders of mod/ into\n"
                  "Documents/Paradox Interactive/Victoria 3/mod/ and enable them in this order:\n\n"
                  + "\n".join(order) + "\n")
        z.writestr("README.txt", readme)
    return out, n
