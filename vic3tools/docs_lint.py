"""Check a project's documents by the documentation methodology (``v3 docs check``).

One core for every repo of a project; each repo describes its layout in ``docs-check.toml`` at its root (what is a
document, where history, concepts, decisions, stages and findings live, which code its documents describe). A node
repo — the folder above the clones of the others, the Obsidian vault — lists them in ``members``: checked from the
node, links between repos resolve as Obsidian resolves them in the whole vault. A repo checked alone (its CI) checks
its own links; a link that leads out of it is a note for the node's check.

What is checked (the methodology's «Проверка»): headers (keys, values from the lists, keys of the kind), Obsidian and
Markdown links, anchors, ambiguous names, concepts on the map with their core section, ``status`` of a concept against
its «Открыто», findings, ``paths`` and ``verified``, active decisions nobody embodies, mentions as text (decision and
stage numbers, paths to documents, concept names — ``--fix`` makes them links), code paths in backticks, decision
numbers and document paths in code comments, code no document's ``paths`` covers. History — only links and anchors.

``docs-check-known.txt`` beside the config: findings accepted for now (``<file>: <code> <arg>``, ``#`` — why); they
are listed as notes, not failures.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from urllib.parse import unquote

CONFIG = "docs-check.toml"
KNOWN = "docs-check-known.txt"
SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
             ".ruff_cache", ".mypy_cache"}
TYPES = {"entry", "concept", "map", "code", "procedure", "reference", "goals", "plan", "phase", "queue", "decision",
         "finding", "lesson", "history"}
STATUS = {"concept": {"open", "done"}, "phase": {"planned", "active", "paused", "done"},
          "queue": {"planned", "active", "done"}, "decision": {"open", "active", "replaced"},
          "finding": {"suspected", "confirmed", "blocked", "fixed", "resolved", "rejected", "accepted"}}
NEED = {"phase": ["status", "date"], "queue": ["phase", "date", "status"], "decision": ["status", "date"],
        "finding": ["status", "date"], "lesson": ["date", "applies"], "history": ["date", "kind"],
        "concept": ["status"]}
KINDS = {"phase", "snapshot", "journal", "audit", "research"}
SEVERITY = {"critical", "high", "medium", "low"}
EMBODY_TYPES = {"procedure", "plan", "map", "phase", "code", "entry"}

LINK = re.compile(r"!?\[\[([^\]|#\n]*)(?:#([^\]|\n]*?))?(?:\\?\|[^\]\n]*)?\]\]")
CODE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`", re.S)
MDLINK = re.compile(r"!?\[[^\]\n]*(?:\n[^\]\n]*)?\]\((<[^>\n]+>|[^)\s]+)\)")  # the text may wrap a line
# not to be turned into links: code, links, addresses, headings, HTML comments, «quotes» (a quoted name of a section)
PROTECT = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`|!?\[\[[^\]\n]*\]\]|!?\[[^\]\n]*\]\([^)\n]*\)|<[^>\n]*>|"
                     r"https?://\S+|^#{1,6} [^\n]*$|<!--.*?-->|«[^»\n]*»", re.S | re.M)
DOC_PATH = re.compile(r"((?:\.\./)*(?:[\w.\-]+/)*docs/[^\s`'\"()<>,;|]*?\.md)\b")


@dataclass
class Finding:
    repo: str
    file: str  # path in the repo
    code: str  # message key (``dc_<code>``)
    arg: str = ""  # what makes the finding unique in its file: a link, a key, a path
    detail: dict = field(default_factory=dict)
    note: bool = False  # a note, not a failure

    @property
    def key(self) -> str:
        return f"{self.file}: {self.code}" + (f" {self.arg}" if self.arg else "")


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)  # repo → documents checked
    fixed: int = 0
    known: int = 0

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if not f.note]


# --- globs ------------------------------------------------------------------------------------------------------
@cache
def _glob_re(pat: str) -> re.Pattern:
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pat.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("".join(out) + "(?:/.*)?$" if not pat.endswith("*") else "".join(out) + "$")


def matches(rel: str, pats) -> bool:
    """Is the repo-relative path ``rel`` under one of the globs (``**`` crosses folders; a folder, or a mask of
    folders, covers what is in them)?"""
    heads = [rel[:i] for i, ch in enumerate(rel) if ch == "/"]
    for p in pats:
        r = _glob_re(p.rstrip("/"))
        if r.match(rel) or any(r.match(h) for h in heads):
            return True
    return False


def _is_glob(p: str) -> bool:
    return any(ch in p for ch in "*?[")


# --- headers ----------------------------------------------------------------------------------------------------
def frontmatter(text: str) -> dict | None:
    m = re.match(r"---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not m:
        return None
    out: dict = {}
    last = None
    for line in m.group(1).split("\n"):
        k = re.match(r"^([A-Za-z_][\w-]*):[ \t]*(.*?)[ \t]*$", line)
        if k:
            last = k.group(1)
            out[last] = k.group(2)
        elif last and re.match(r"^\s+-\s+", line):  # a block list: key:\n  - a\n  - b
            out[last] = (out[last] + "\n" if out[last] else "") + line.strip()[1:].strip()
    return out


def listval(v) -> list[str]:
    v = (v or "").strip()
    if "\n" in v:
        return [x.strip().strip("'\"") for x in v.split("\n") if x.strip()]
    if v.startswith("["):
        inner = v[1:-1]
        if '"' in inner:
            return re.findall(r'"([^"]*)"', inner)
        return [x.strip().strip("'") for x in inner.split(",") if x.strip()]
    return [v.strip("'\"")] if v else []


def strip_fm(text: str) -> tuple[str, int]:
    m = re.match(r"---\n.*?\n---(?:\n|$)", text, re.S)
    return (text[m.end():], m.end()) if m else (text, 0)


# --- the vault --------------------------------------------------------------------------------------------------
@dataclass
class Repo:
    root: Path
    prefix: str  # its path in the vault with a slash, "" for the vault's root
    cfg: dict
    known: set[str] = field(default_factory=set)

    @property
    def name(self) -> str:
        return self.cfg.get("name") or self.root.name

    def get(self, key: str, default=None):
        return self.cfg.get(key, default)

    def globs(self, key: str, default: list[str]) -> list[str]:
        v = self.cfg.get(key, default)
        return [v] if isinstance(v, str) else list(v)


def load_repo(root: Path, prefix: str) -> Repo:
    cfg = tomllib.loads((root / CONFIG).read_text(encoding="utf-8"))
    known = set()
    kf = root / KNOWN
    if kf.exists():
        known = {ln.split("#", 1)[0].strip() for ln in kf.read_text(encoding="utf-8").splitlines()}
        known.discard("")
    return Repo(root, prefix, cfg, known)


def find_repo(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / CONFIG).is_file():
            return d
    raise FileNotFoundError(f"{CONFIG}: not found in {start} or above")


def find_vault(start: Path) -> tuple[Path, list[Repo], list[Repo], bool]:
    """(vault root, all repos of the vault, repos to check, standalone)."""
    repo_root = find_repo(start.resolve())
    for d in repo_root.parents:
        if (d / CONFIG).is_file():
            node = load_repo(d, "")
            members = [m.rstrip("/") for m in node.get("members", [])]
            rel = repo_root.relative_to(d).as_posix()
            if rel in members:
                repos = [node] + [load_repo(d / m, m + "/") for m in members if (d / m / CONFIG).is_file()]
                target = [r for r in repos if r.prefix == rel + "/"]
                return d, repos, target, False
    repo = load_repo(repo_root, "")
    members = [m.rstrip("/") for m in repo.get("members", [])]
    if members:  # a node: the whole vault
        repos = [repo] + [load_repo(repo_root / m, m + "/") for m in members if (repo_root / m / CONFIG).is_file()]
        return repo_root, repos, repos, False
    return repo_root, [repo], [repo], True


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


class Vault:
    def __init__(self, root: Path, repos: list[Repo]):
        self.root = root
        self.repos = repos
        self.files: dict[str, Path] = {}  # vault-relative path, lower case → file
        self.by_name: dict[str, list[str]] = {}
        self.repo_of: dict[str, Repo] = {}
        self.docs: dict[str, tuple[Repo, str]] = {}  # key → (repo, repo-relative path)
        members = {r.prefix.rstrip("/") for r in repos if r.prefix}
        for repo in repos:
            skip = set(repo.globs("vault_skip", []))
            for dp, dn, fn in os.walk(repo.root):
                rd = Path(dp).relative_to(repo.root).as_posix()
                rd = "" if rd == "." else rd + "/"
                keep = []
                for d in dn:
                    sub = rd + d
                    if d in SKIP_DIRS or (repo.prefix == "" and sub in members) or matches(sub, skip):
                        continue
                    keep.append(d)
                dn[:] = keep
                for f in fn:
                    rel = rd + f
                    key = (repo.prefix + rel).lower()
                    self.files[key] = Path(dp) / f
                    self.by_name.setdefault(f.lower(), []).append(key)
                    self.repo_of[key] = repo
                    if f.endswith(".md") and matches(rel, repo.globs("docs", ["**/*.md"])) \
                            and not matches(rel, repo.globs("exclude", [])):
                        self.docs[key] = (repo, rel)
        self._text: dict[str, str] = {}
        self._resolved: dict[str, tuple[str, ...]] = {}
        self._anchors: dict[str, tuple[set, set]] = {}

    def text(self, key: str) -> str:
        if key not in self._text:
            self._text[key] = self.files[key].read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
        return self._text[key]

    def resolve(self, t: str) -> tuple[str, ...]:
        """Candidates for ``[[t]]`` as Obsidian finds them: the one file of that name; the exact path from the vault's
        root; else every file whose path ends with ``t`` (no extension in the link — only ``.md``)."""
        if t not in self._resolved:  # called for every name in every piece of text
            self._resolved[t] = self._resolve(t)
        return self._resolved[t]

    def _resolve(self, t: str) -> tuple[str, ...]:
        o = unquote(t).replace("\\", "").strip().lower().lstrip("/")
        name = o.rsplit("/", 1)[-1]
        cands = list(self.by_name.get(name + ".md", []))
        if "." in name:
            cands += self.by_name.get(name, [])
        if "/" not in o and len(cands) == 1:
            return tuple(cands)
        for x in (o, o + ".md"):
            if x in self.files:
                return (x,)
        return tuple(k for k in cands if k.endswith("/" + o) or k.endswith("/" + o + ".md"))

    @staticmethod
    def pick(cands, src: str) -> list[str]:
        """Obsidian's order: those in the linking document's folder first, then the shorter path."""
        folder = src.rsplit("/", 1)[0] + "/" if "/" in src else ""
        return sorted(cands, key=lambda k: (not (folder and k.startswith(folder)), len(k)))

    def anchors(self, key: str) -> tuple[set, set]:
        if key not in self._anchors:
            t = re.sub(r"```.*?```", "", self.text(key), flags=re.S)
            self._anchors[key] = ({h.strip() for h in re.findall(r"^#{1,6} (.+?)\s*$", t, re.M)},
                                  set(re.findall(r"\s\^([A-Za-z0-9-]+)\s*$", t, re.M)))
        return self._anchors[key]

    def link_to(self, key: str, src: str) -> str:
        """The shortest link text from ``src`` that leads to ``key``: the name if it leads there, else the path."""
        stem = self.files[key].stem
        if self.resolve(stem) == (key,):
            return stem
        full = _orig_case(self, key)
        full = full[:-3] if full.endswith(".md") else full
        if self.repo_of[key] is not self.repo_of.get(src):  # into another repo: the path from the vault's root
            return full
        parts = full.split("/")
        for i in range(len(parts) - 2, 0, -1):  # the shortest tail of the path that leads only there
            tail = "/".join(parts[i:])
            if self.resolve(tail) == (key,):
                return tail
        return full


def _orig_case(vault: Vault, key: str) -> str:
    return vault.files[key].relative_to(vault.root).as_posix()


# --- the check --------------------------------------------------------------------------------------------------
class Checker:
    def __init__(self, vault: Vault, targets: list[Repo], standalone: bool, fix: bool):
        self.v = vault
        self.targets = targets
        self.standalone = standalone
        self.fix = fix
        self.res = Result()
        self.incoming: dict[str, set[str]] = {}
        self._files: dict[Path, tuple[str, ...]] = {}
        self._index()

    def add(self, repo: Repo, file: str, code: str, arg: str = "", note: bool = False, **detail) -> None:
        f = Finding(repo.name, file, code, arg, detail, note)
        if not note and f.key in repo.known:
            f.note = True
            f.detail["known"] = True
            self.res.known += 1
        self.res.findings.append(f)

    # what there is: decisions, stages, findings, concepts — over the whole vault (numbers are unique per project)
    def _index(self) -> None:
        self.decision: dict[str, str] = {}
        self.stage: dict[str, str] = {}
        self.finding: dict[str, str] = {}
        self.concepts: dict[str, dict[str, str]] = {}  # repo name → concept name → key
        self.fm: dict[str, dict] = {}
        for key, (repo, rel) in self.v.docs.items():
            name = self.v.files[key].stem
            fm = frontmatter(self.v.text(key)) or {}
            self.fm[key] = fm
            folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
            if folder in repo.globs("decisions", ["docs/решения", "docs/история/решения"]) and " — " in name:
                self.decision[name.split(" — ", 1)[0]] = key
            if folder in repo.globs("findings", ["docs/находки", "docs/история/находки"]) and " — " in name:
                self.finding[name.split(" — ", 1)[0]] = key
            st = repo.get("stages", {"dir": "docs/этапы", "name": r"^Этап (\S+?)\. "})
            if folder == st["dir"]:
                m = re.match(st["name"], name)
                if m:
                    self.stage[m.group(1)] = key
            if folder == repo.get("concepts", "docs/понятия") and not name.startswith("_") and not fm.get("source"):
                self.concepts.setdefault(repo.name, {})[name] = key
        ids = sorted(self.decision, key=len, reverse=True)
        self.decision_re = re.compile(r"(?<![\w.\-–/])(" + "|".join(map(re.escape, ids)) + r")(?![\w\-–]|\.[\w])") \
            if ids else None
        sids = sorted(self.stage, key=len, reverse=True)
        self.stage_re = re.compile(r"(?<![\w\[|])([Ээ]тап(?:а|у|ом|е|ы|ов)?) (" + "|".join(map(re.escape, sids)) +
                                   r")(?![\w])(?!\.\d)") if sids else None
        node = [r for r in self.v.repos if r.prefix == ""]
        self.node_name = node[0].name if node else None

    def run(self) -> Result:
        # links of every document in the vault count for orphans and embodiment
        for key in self.v.docs:
            self._collect_links(key)
        for repo in self.targets:
            n = 0
            for key, (r, rel) in self.v.docs.items():
                if r is repo:
                    self._doc(repo, rel, key)
                    n += 1
            self.res.checked[repo.name] = n
            self._repo_level(repo)
            self._code(repo)
            self._extra(repo)
        return self.res

    def _collect_links(self, key: str) -> None:
        text = self.v.text(key)
        fm_text = text[:strip_fm(text)[1]]
        body = CODE.sub("", strip_fm(text)[0])
        for target, _ in LINK.findall(body + "\n" + fm_text):
            target = target.replace("\\", "").strip()
            if not target:
                continue
            hit = self.v.pick(self.v.resolve(target), key)
            if hit:
                self.incoming.setdefault(hit[0], set()).add(key)

    def _doc(self, repo: Repo, rel: str, key: str) -> None:
        raw = self.v.files[key].read_bytes().decode("utf-8", errors="replace")
        text = raw.replace("\r\n", "\n")
        hist = matches(rel, repo.globs("history", ["docs/история/**"]))
        fm = frontmatter(text)
        body_all, off = strip_fm(text)
        body = CODE.sub("", body_all)
        if not hist:
            self._header(repo, rel, key, fm, body_all)
            fm = fm or {}
        # links — in history too
        fm_text = text[:off]
        if re.search(r"\[\[[^\]\n]*\n", body):
            self.add(repo, rel, "link_split")
        for m in MDLINK.finditer(body):
            h = m.group(1).strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", h, re.I) or h.startswith("#"):
                continue
            path = unquote(h.split("#")[0])
            if path.endswith(".md") and not hist and not repo.get("md_links"):
                self.add(repo, rel, "md_link", m.group(0))
            elif path and not (self.v.files[key].parent / path).exists() \
                    and (path.startswith(("./", "../")) or not self.v.resolve(path)):  # a relative path — from here
                self.add(repo, rel, "md_link_nowhere", m.group(0))
        for target, anchor in LINK.findall(body + "\n" + fm_text):
            self._link(repo, rel, key, target.replace("\\", "").strip(), anchor)
        if hist or not fm:
            return
        self._mentions(repo, rel, key, text, body_all, off, raw)
        self._code_refs(repo, rel, body_all)

    def _link(self, repo: Repo, rel: str, key: str, target: str, anchor: str) -> None:
        hit = self.v.pick(self.v.resolve(target), key) if target else [key]
        if not hit:
            if self.standalone and repo.get("node"):
                self.add(repo, rel, "link_outside", target, note=True)
            else:
                self.add(repo, rel, "link_nowhere", target)
            return
        top = self.v.pick(hit, "")
        if len(hit) > 1 and (hit[0] != top[0] or len(top[0]) == len(top[1])):
            self.add(repo, rel, "link_ambiguous", target, cands=", ".join(_orig_case(self.v, h) for h in hit[:4]))
        if anchor and hit[0].endswith(".md"):
            heads, blocks = self.v.anchors(hit[0])
            a = anchor.split("#")[-1].strip()
            if not (a[1:] in blocks if a.startswith("^") else a in heads):
                self.add(repo, rel, "anchor", f"{target}#{anchor}")

    def _header(self, repo: Repo, rel: str, key: str, fm: dict | None, body_all: str) -> None:
        if fm is None:
            self.add(repo, rel, "no_header")
            return
        for k in ("type", "description", "project", "tags"):
            if not fm.get(k):
                self.add(repo, rel, "no_key", k)
        project = repo.get("project")
        if project and fm.get("project") and fm["project"].strip("'\"") != project \
                and not matches(rel, repo.globs("method", [])):
            self.add(repo, rel, "project", fm["project"], want=project)
        t = fm.get("type")
        if not t:
            return
        if t not in TYPES:
            self.add(repo, rel, "type", t)
            return
        external = bool(fm.get("source"))
        need = repo.get("need", {}).get(t, NEED.get(t, []))
        for k in need:
            if k == "status" and external:
                continue
            if not fm.get(k):
                self.add(repo, rel, "need", k, type=t)
        if t in STATUS and fm.get("status") and fm["status"] not in STATUS[t]:
            self.add(repo, rel, "status", fm["status"], type=t)
        if t == "history" and fm.get("kind") and fm["kind"] not in KINDS:
            self.add(repo, rel, "kind", fm["kind"])
        if t == "concept" and key in self.concepts.get(repo.name, {}).values():
            core = repo.globs("concept_core", ["Суть"])
            if fm.get("tags") and any(x in listval(fm["tags"]) for x in repo.globs("concept_no_core_tags", [])):
                core = []
            if core and not any(re.search(rf"^## {re.escape(c)}\s*$", body_all, re.M) for c in core):
                self.add(repo, rel, "no_core", "", sections=" / ".join(f"«{c}»" for c in core))
            m = re.search(r"^#{2,3} Открыто\s*\n(.*?)(?=^#{1,3} |\Z)", body_all, re.M | re.S)
            empty = (not m) or m.group(1).strip().rstrip(".") in ("", "Пусто", "Нет")
            if fm.get("status") in ("open", "done") and (fm["status"] == "done") != empty:
                self.add(repo, rel, "status_open_" + ("empty" if empty else "full"), fm["status"])
        if t == "decision" and fm.get("status") == "replaced" and not fm.get("replaced_by"):
            self.add(repo, rel, "need", "replaced_by", type="decision replaced")
        if t == "finding":
            self._finding(repo, rel, fm)
        self._paths(repo, rel, fm)

    def _finding(self, repo: Repo, rel: str, fm: dict) -> None:
        st = fm.get("status")
        areas = repo.get("finding_areas")
        if areas:
            area = fm.get("area")
            if area not in areas:
                self.add(repo, rel, "area", area or "")
            elif not Path(rel).stem.startswith(area + "-"):
                self.add(repo, rel, "area_name", area)
            if fm.get("severity") not in SEVERITY:
                self.add(repo, rel, "severity", fm.get("severity") or "")
        need = {"fixed": "fixed_in", "resolved": "verified_by", "accepted": "decisions"}
        if st in need and not fm.get(need[st]):
            self.add(repo, rel, "need", need[st], type=f"finding {st}")
        if st in ("resolved", "rejected", "accepted") and not matches(rel, repo.globs("history", ["docs/история/**"])):
            self.add(repo, rel, "finding_closed_place", st)

    # paths and verified: masks of the files the document describes, against git
    def _paths_base(self, repo: Repo) -> Path:
        return (repo.root / repo.get("paths_root", ".")).resolve()

    def _tracked(self, base: Path) -> tuple[str, ...]:
        """Files of ``base`` (git's, else all on disk), paths from ``base``."""
        if base not in self._files:
            if _git(base, "rev-parse", "--show-toplevel").strip():
                self._files[base] = tuple(_git(base, "ls-files", "--", ".").splitlines())
            else:
                self._files[base] = tuple(Path(dp, f).relative_to(base).as_posix()
                                          for dp, _, fn in os.walk(base) for f in fn)
        return self._files[base]

    def _paths(self, repo: Repo, rel: str, fm: dict) -> None:
        ps = listval(fm.get("paths"))
        if not ps:
            return
        base = self._paths_base(repo)
        tracked = self._tracked(base)
        for p in ps:
            if _is_glob(p):
                if not any(matches(x, [p]) for x in tracked):
                    self.add(repo, rel, "paths_missing", p)
            elif not (base / p).exists():
                self.add(repo, rel, "paths_missing", p)
        ver = fm.get("verified", "")
        if not ver:
            return
        h = re.search(r"\b([0-9a-f]{7,40})\b", ver)
        d = re.search(r"\d{4}-\d{2}-\d{2}", ver)
        if h:
            out = _git(base, "rev-list", "--count", f"{h.group(1)}..HEAD", "--", *ps).strip()
            if out and out != "0":
                self.add(repo, rel, "stale_commit", "", note=True, commit=h.group(1), count=out)
        elif d:
            last = _git(base, "log", "-1", "--format=%cs", "--", *ps).strip()
            if last and last > d.group(0):
                self.add(repo, rel, "stale", "", note=True, last=last, verified=d.group(0))

    # mentions as text → links
    def _mentions(self, repo: Repo, rel: str, key: str, text: str, body_all: str, off: int, raw: str) -> None:
        fm = self.fm.get(key, {})
        if fm.get("generated") or matches(rel, repo.globs("method", [])) or repo.get("mentions", True) is False:
            return
        spans = [m.span() for m in PROTECT.finditer(body_all)]
        table = {0} if body_all.lstrip(" ").startswith("|") else set()
        pos = 0
        for line in body_all.split("\n"):
            if line.lstrip().startswith("|"):
                table.add(pos)
            pos += len(line) + 1

        def free(a, b):
            return not any(s < b and a < e for s, e in spans)

        def sep(a):
            return "\\|" if body_all.rfind("\n", 0, a) + 1 in table else "|"

        out = []
        if self.decision_re:
            for m in self.decision_re.finditer(body_all):
                k = self.decision[m.group(1)]
                if k != key and free(*m.span()):
                    out.append((*m.span(), f"[[{self.v.link_to(k, key)}{sep(m.start())}{m.group(0)}]]"))
        if self.stage_re:
            for m in self.stage_re.finditer(body_all):
                k = self.stage[m.group(2)]
                if k != key and free(*m.span()):
                    out.append((*m.span(), f"[[{self.v.link_to(k, key)}{sep(m.start())}{m.group(0)}]]"))
        for m in re.finditer(r"`([^`\n]+?\.md)`", body_all):
            p = m.group(1).lstrip("./")
            cands = [(repo.prefix + p).lower(), p.lower()]
            k = next((c for c in cands if c in self.v.docs), None)
            if "/" in p and k and k != key:
                a, b = m.span()
                if any(s <= a and b <= e and (e - s) > (b - a) for s, e in spans):
                    continue
                out.append((a, b, f"[[{self.v.link_to(k, key)}]]"))
        # concept names: the first mention, of this repo's concepts and the node's
        own = dict(self.concepts.get(self.node_name, {})) if self.node_name else {}
        own.update(self.concepts.get(repo.name, {}))
        linked = {t.replace("\\", "").strip().rsplit("/", 1)[-1].lower() for t, _ in LINK.findall(body_all)}
        taken = [(a, b) for a, b, _ in out]
        if fm.get("type") in repo.globs("concept_mention_types", ["concept", "code", "procedure", "map", "entry"]):
            for n in sorted((n for n in own if len(n) >= 4), key=len, reverse=True):
                if n.lower() in linked or own[n] == key:
                    continue
                for m in re.finditer(rf"(?<![\w«\-/]){re.escape(n)}(?![\w»\-])", body_all):
                    a, b = m.span()
                    if free(a, b) and not any(s < b and a < e for s, e in taken):
                        out.append((a, b, f"[[{self.v.link_to(own[n], key)}]]" if self.v.link_to(own[n], key) == n
                                    else f"[[{self.v.link_to(own[n], key)}{sep(a)}{n}]]"))
                        taken.append((a, b))
                        break
        out.sort()
        res, last = [], -1
        for o in out:
            if o[0] >= last:
                res.append(o)
                last = o[1]
        if not res:
            return
        if self.fix:
            new = body_all
            for a, b, rep in reversed(res):
                new = new[:a] + rep + new[b:]
            full = text[:off] + new
            if "\r\n" in raw:
                full = full.replace("\n", "\r\n")
            self.v.files[key].write_bytes(full.encode("utf-8"))
            self.res.fixed += 1
            return
        for a, b, rep in res:
            line = text.count("\n", 0, off + a) + 1
            self.add(repo, rel, "mention", f"{body_all[a:b]}@{line}", line=line, text=body_all[a:b], link=rep)

    # code paths in backticks: `common/x.txt`, `gui/x.gui:120`, masks
    def _code_refs(self, repo: Repo, rel: str, body_all: str) -> None:
        roots = repo.globs("code_roots", [])
        if not roots or not matches(rel, repo.globs("code_roots_in", ["docs/**"])):
            return
        ref = re.compile(r"`((?:" + "|".join(map(re.escape, roots)) + r")[^`\n:]+?)(?::(\d+)[^`]*)?`")
        tracked = self._tracked(repo.root)
        for m in ref.finditer(body_all):
            if "…" in m.group(1) or "{" in m.group(1):
                continue
            p = re.sub(r"<[^>]+>", "*", m.group(1).strip())
            if p.endswith("/"):
                p += "**"
            if _is_glob(p):
                if not any(matches(x, [p]) for x in tracked):
                    self.add(repo, rel, "code_ref", m.group(1))
            elif not (repo.root / p).exists():
                self.add(repo, rel, "code_ref", m.group(1))
            elif m.group(2) and (repo.root / p).is_file():
                n = (repo.root / p).read_bytes().count(b"\n") + 1
                if int(m.group(2)) > n:
                    self.add(repo, rel, "code_ref_line", f"{m.group(1)}:{m.group(2)}", lines=n)

    def _repo_level(self, repo: Repo) -> None:
        mine = {k: rel for k, (r, rel) in self.v.docs.items() if r is repo}
        hist = repo.globs("history", ["docs/история/**"])
        # the map: every concept on it
        mp = repo.get("map")
        if mp:
            mk = (repo.prefix + mp).lower()
            if mk not in self.v.files:
                self.add(repo, mp, "no_map")
            else:
                on = {self.v.pick(self.v.resolve(t.replace("\\", "").strip()), mk)[:1][0]
                      for t, _ in LINK.findall(CODE.sub("", self.v.text(mk)))
                      if self.v.resolve(t.replace("\\", "").strip())}
                for k in self.concepts.get(repo.name, {}).values():
                    if k not in on:
                        self.add(repo, mine[k], "not_on_map")
        # an active decision is embodied: decisions of a concept, a link from a plan, phase, procedure, code document
        embody: set[str] = set()
        for k, (r, rel) in self.v.docs.items():
            if matches(rel, r.globs("history", ["docs/история/**"])):
                continue
            fm = self.fm.get(k, {})
            for d in listval(fm.get("decisions")):
                hit = self.v.resolve(d.strip("[]").split("|")[0])
                embody.update(hit)
            if fm.get("type") in EMBODY_TYPES or matches(rel, r.globs("method", [])):
                for t, _ in LINK.findall(CODE.sub("", self.v.text(k))):
                    hit = self.v.pick(self.v.resolve(t.replace("\\", "").strip()), k)
                    if hit:
                        embody.add(hit[0])
        for k, rel in mine.items():
            fm = self.fm.get(k, {})
            if fm.get("type") == "decision" and fm.get("status") == "active" and k not in embody \
                    and not matches(rel, hist):
                # alone, the node's plan and phases are out of sight: the node's check decides
                self.add(repo, rel, "decision_idle", note=self.standalone and bool(repo.get("node")))
        # notes: orphans, one name for two documents
        for k, rel in mine.items():
            if matches(rel, hist) or k in self.incoming or Path(rel).name.lower() == "readme.md" \
                    or (mp and rel == mp) or self.fm.get(k, {}).get("generated"):
                continue
            self.add(repo, rel, "orphan", note=True)
        seen: dict[str, list[str]] = {}
        for rel in mine.values():
            seen.setdefault(Path(rel).stem.lower(), []).append(rel)
        for name, rels in seen.items():
            if len(rels) > 1 and name != "readme":
                self.add(repo, rels[0], "same_name", note=True, files=", ".join(rels))
        # code no document's paths covers
        cover = repo.globs("cover", [])
        if cover:
            pats = [p for k in mine for p in listval(self.fm.get(k, {}).get("paths"))]
            pats = [re.sub(r"<[^>]+>", "*", p) for p in pats]
            for f in self._tracked(repo.root):
                if matches(f, cover) and not matches(f, pats):
                    self.add(repo, f, "uncovered", note=not repo.get("cover_strict", False))

    # code: decision numbers and document paths in comments
    def _code(self, repo: Repo) -> None:
        ext = set(repo.globs("code_ext", []))
        if not ext:
            return
        skip = repo.globs("code_exclude", [])
        pat = repo.get("code_decision")
        dre = re.compile(pat) if pat else None
        for f in self._tracked(repo.root):
            p = repo.root / f
            if p.suffix not in ext or matches(f, skip) or f in (CONFIG, KNOWN) or not p.is_file():
                continue
            try:
                lines = p.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").split("\n")
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(lines, 1):
                if dre:
                    for m in dre.finditer(line):
                        i = m.group(1) if m.groups() else m.group(0)
                        if i not in self.decision:
                            self.add(repo, f, "code_decision", i, line=n, id=i)
                for path in DOC_PATH.findall(line):
                    if "<" in path or "*" in path:
                        continue
                    if (repo.root / path).exists() or (p.parent / path).exists() or (self.v.root / path).exists():
                        continue
                    self.add(repo, f, "code_doc_path", path, line=n, path=path)

    def _extra(self, repo: Repo) -> None:
        for cmd in repo.globs("extra", []):
            r = subprocess.run(cmd, cwd=repo.root, shell=True, capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            if r.returncode != 0:
                out = (r.stdout + r.stderr).strip().splitlines()
                self.add(repo, CONFIG, "extra", cmd, output="\n    ".join(out[-15:]))


def check(start: Path, fix: bool = False) -> Result:
    root, repos, targets, standalone = find_vault(start)
    vault = Vault(root, repos)
    return Checker(vault, targets, standalone, fix).run()
