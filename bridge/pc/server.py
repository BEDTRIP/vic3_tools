"""The PC bridge: an MCP server on the user's PC for a Claude Code cloud session.

The cloud session edits a repo in its own clone and pushes a branch; this server, reached over a tunnel, does on the
PC what needs the PC: checks the branch out into a worktree of its own, copies a mod into the live folder
Documents/…/Victoria 3/mod, runs the game (bridge/game of vic3_tools, on this screen or in the sandbox VM), and gives
back `v3` answers, logs, screenshots and the output of the project's Python tools. Files are readable only under the
roots; nothing here writes outside the worktrees, the live mod folder, the runs folder and the cache of `v3`.

The project is described by a TOML file (``--config``, ``PC_BRIDGE_CONFIG``)::

    [bridge]
    tunnel = "tailscale"                  # start.ps1: "tailscale" (Funnel) or "ngrok" (default)
    domain = "<the tunnel's domain>"      # ngrok: its static domain; tailscale: <PC>.<tailnet>.ts.net (checked)
    port = 8080
    home = "../_bridge"                   # token, worktrees, runs, the log, the venv (not in git)
    vm = "vic3-sandbox"
    hooks = "fork:tools"                  # the project's vic3_hooks.ps1 for the game scripts (<repo>:<folder>)
    links = { vic3_mods_out = "../vic3_mods_out" }   # junctions in home: tools run in a worktree find them there

    [repos.main]                          # the first repo: checkout(); its worktree is the root "wt"
    path = "."
    branch = "main"
    [repos.fork]                          # checkout_fork() / sync_fork() / fork_diff(); root "fork"
    path = "../Economic-and-Financial-Ledgerdemain-Mod"
    branch = "master"
    mod_name = "E&F: Ledgerdemain"        # v3 reads this mod from the worktree once checked out
    live = "E&F Ledgerdemain"             # sync_fork's default live mod

    [tools]                               # py_tool: tools/<name>.py of these repos (their worktree, else checkout)
    repos = ["main", "fork"]
    names = ["parse_eflog", "save_money_check"]
    globs = ["regen_*.py", "ld_*.py"]

    [roots]                               # more readable roots (paths relative to the config)
    orig = "../vic3_mods_out"

    [comfy]                               # comfy_* tools: a local ComfyUI (optional)
    url = "http://127.0.0.1:8000"         # ComfyUI Desktop's default port; the portable build uses 8188
    base = ""                             # its folder with models/; "" -- from the running ComfyUI (--base-directory)

Every request must carry "Authorization: Bearer <token>" (``<home>/token.txt``, made on the first start). Run it in
the user's desktop session, not as a service: the game scripts need the screen. ``PC_BRIDGE_TARGET=vm`` (start.ps1
-Vm): runs go to the Hyper-V sandbox VM (bridge/vm/Invoke-SandboxRun.ps1) and the screen stays free; ``start_run(target=
"vm" | "pc")`` picks it per run (the VM's screen is the 2560x1440 the game scripts' points are measured on).
"""
import collections
import datetime
import fnmatch
import hmac
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

TOOLS_REPO = Path(__file__).resolve().parents[2]          # vic3_tools: the game scripts, the VM runner, `v3`
CONFIG = Path(os.environ.get("PC_BRIDGE_CONFIG") or (sys.argv[sys.argv.index("--config") + 1]
                                                       if "--config" in sys.argv else "bridge.toml")).resolve()
CFG = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
BASE = CONFIG.parent


def _p(v: str) -> Path:
    return (BASE / v).resolve()


B = CFG.get("bridge", {})
HOME = _p(B.get("home", "../_bridge"))
REPOS = {name: {**r, "path": _p(r["path"])} for name, r in CFG.get("repos", {}).items()}
MAIN = next(iter(REPOS))
for name, r in REPOS.items():  # the main repo's worktree is "wt"; the others are named after their folder
    r["wt"] = HOME / ("wt" if name == MAIN else r["path"].name)
RUNS = HOME / "runs"
DOCS = Path.home() / "Documents" / "Paradox Interactive" / "Victoria 3"
GAME_SCRIPTS = TOOLS_REPO / "bridge" / "game"
VM_RUN = TOOLS_REPO / "bridge" / "vm" / "Invoke-SandboxRun.ps1"
BENCH = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "vic3tools" / "cache" / "bench"
PORT = int(os.environ.get("PC_BRIDGE_PORT") or B.get("port", 8080))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
VM = os.environ.get("PC_BRIDGE_TARGET", "pc") == "vm"
VM_NAME = os.environ.get("PC_BRIDGE_VM") or B.get("vm", "vic3-sandbox")
T = CFG.get("tools", {})
C = CFG.get("comfy", {})
COMFY = C.get("url", "http://127.0.0.1:8000").rstrip("/")
GEN = HOME / "gen"
PY_TOOLS = set(T.get("names", []))
PY_TOOL_GLOBS = tuple(T.get("globs", []))


def _roots() -> dict[str, Path]:
    sys.path.insert(0, str(TOOLS_REPO))
    from vic3tools.core import paths

    found = paths.resolve_roots()
    roots = {"docs": DOCS, "runs": RUNS, "bench": BENCH, "gen": GEN}
    for k in ("game", "workshop"):
        if found[k].ok:
            roots[k] = found[k].path
    for name, r in REPOS.items():
        roots["wt" if name == MAIN else name] = r["wt"]
    roots.update({k: _p(v) for k, v in CFG.get("roots", {}).items()})
    return roots


HOME.mkdir(parents=True, exist_ok=True)
RUNS.mkdir(exist_ok=True)
GEN.mkdir(exist_ok=True)
for _name, _target in B.get("links", {}).items():
    _link, _target = HOME / _name, _p(_target)
    if _target.is_dir() and not _link.exists():
        subprocess.run(["cmd", "/c", "mklink", "/J", str(_link), str(_target)], capture_output=True)
ROOTS = _roots()
TOKEN_FILE = HOME / "token.txt"
if not TOKEN_FILE.exists():
    TOKEN_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()

_runs = {}            # run id -> Popen of this server's lifetime
_targets = {}         # run id -> True if it runs in the sandbox VM
_lock = threading.Lock()


def log(msg):
    with open(HOME / "bridge.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def sh(args, cwd=None, timeout=300, env=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=NO_WINDOW, env=env)
    if p.returncode:
        raise RuntimeError(f"{' '.join(map(str, args))} -> {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def resolve(path):
    """'docs/logs/error.log', 'runs/r1/03_end.png' or an absolute path inside a root."""
    head, _, rest = path.replace("\\", "/").partition("/")
    p = (ROOTS[head] / rest) if head in ROOTS else Path(path)
    p = p.resolve()
    for root in ROOTS.values():
        if p == root.resolve() or root.resolve() in p.parents:
            return p
    raise ValueError(f"outside the allowed roots {', '.join(f'{k}={v}' for k, v in ROOTS.items())}: {path}")


def ps(script, timeout=120):
    return sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=timeout)


def in_vm(script, timeout=120):
    """A PowerShell command inside the sandbox VM (PowerShell Direct, the credential saved by the VM setup)."""
    cred = '(Import-Clixml (Join-Path $env:LOCALAPPDATA "vic3tools/vm-cred.xml"))'
    return ps(f"Invoke-Command -VMName '{VM_NAME}' -Credential {cred} -ScriptBlock {{ {script} }}", timeout)


def game_running(vm: bool | None = None):
    """The game is up -- in the sandbox VM (vm=True), on the PC (False); None: where runs go by default."""
    if VM if vm is None else vm:
        return in_vm("[bool](Get-Process victoria3 -ErrorAction SilentlyContinue)").strip() == "True"
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq victoria3.exe", "/NH"], capture_output=True,
                         text=True, errors="replace", creationflags=NO_WINDOW).stdout
    return "victoria3.exe" in out.lower()


def active_run():
    with _lock:
        return next((rid for rid, p in _runs.items() if p.poll() is None), None)


def _repo_dir(name: str) -> Path:
    """A repo's bridge worktree if made (the pushed branch), else its checkout on the PC."""
    r = REPOS[name]
    return r["wt"] if (r["wt"] / ".git").exists() else r["path"]


def _place(spec: str) -> Path:
    """'<repo>:<folder>' (a repo of the config, or 'tools' for vic3_tools) → a folder."""
    repo, _, folder = spec.partition(":")
    base = TOOLS_REPO if repo == "tools" else _repo_dir(repo)
    return (base / folder).resolve()


def _hooks_dir() -> Path | None:
    return _place(B["hooks"]) if B.get("hooks") else None


def _v3_config() -> str:
    """The project config `v3` finds from the bridge's home: each repo that has a worktree -> that worktree."""
    conf = HOME / "vic3tools.toml"
    lines = []
    for r in REPOS.values():
        if (r["wt"] / ".git").exists() and r.get("mod_name"):
            lines.append(f"'{r['mod_name']}' = '{r['wt']}'")
    if lines:
        conf.write_text("[mod_paths]\n" + "\n".join(lines) + "\n", encoding="utf-8")
    elif conf.exists():
        conf.unlink()
    return str(HOME)


mcp = FastMCP(
    "vic3-pc",
    instructions="The user's Windows PC with Victoria 3. Questions about game and mod files: v3(args) -- the "
                 "same `v3` commands as on the PC (def, refs, loc, outline, winner, gui resolve/fit/render, lint, "
                 "save, log...), read-only. Images on the PC's GPU: comfy_status / comfy_models / comfy_get / comfy_fetch / comfy "
                 "(ComfyUI; shuts the sandbox VM down -- they share the GPU). GUI test bench: v3(['bench','start']) then v3(['bench','shot',name,"
                 "'--crop',...]) after each push+sync -> get_image('bench/<step>/<name>_crop.png'). Runs: "
                 "checkout(branch) -> sync_mod() -> start_run(...) -> run_status(id) until finished -> read_text / "
                 "grep / get_image on runs/<id>/... and docs/... . See the project's skill vic3-sandbox.",
    stateless_http=True, json_response=True, host="127.0.0.1", port=PORT,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _checkout(name: str, branch: str) -> str:
    if not re.fullmatch(r"[\w./-]+", branch) or ".." in branch or branch.startswith("-"):
        raise ValueError(f"bad branch name: {branch}")
    r = REPOS[name]
    sh(["git", "-C", r["path"], "fetch", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"], timeout=1800)
    if not (r["wt"] / ".git").exists():
        sh(["git", "-C", r["path"], "worktree", "add", "--detach", r["wt"], f"origin/{branch}"], timeout=1800)
    else:
        sh(["git", "-C", r["wt"], "checkout", "--detach", "--force", f"origin/{branch}"], timeout=1800)
        sh(["git", "-C", r["wt"], "clean", "-fdq"])
    log(f"checkout {name} {branch}")
    return sh(["git", "-C", r["wt"], "log", "-1", "--format=%h %ad %s", "--date=iso"])


@mcp.tool()
def checkout(branch: str = "", repo: str = "") -> str:
    """Fetch a branch of a project repo from GitHub and check it out (detached) in its bridge worktree (the main
    repo: root 'wt'; sync_mod, py_tool use it). repo: a name of the bridge config (default: the main one). Returns
    the commit."""
    name = repo or MAIN
    if name not in REPOS:
        raise ValueError(f"repos: {', '.join(REPOS)}")
    return _checkout(name, branch or REPOS[name].get("branch", "main"))


@mcp.tool()
def checkout_fork(branch: str = "") -> str:
    """checkout(branch, repo="fork"): the fork's bridge worktree (root 'fork'); sync_fork and its tools use it."""
    if "fork" not in REPOS:
        raise ValueError("no repo 'fork' in the bridge config")
    return _checkout("fork", branch or REPOS["fork"].get("branch", "master"))


def _sync(src, dst):
    """dst = src: changed and new files copied, files gone from src moved to dst/_to_delete/<date>/."""
    skip = lambda rel: rel.parts[0] in ("_to_delete", ".git", "docs", "CLAUDE.md", "tools", ".claude")  # noqa: E731
    copied, moved = [], []
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        if f.is_file() and not skip(rel):
            t = dst / rel
            if not t.exists() or t.read_bytes().replace(b"\r\n", b"\n") != f.read_bytes().replace(b"\r\n", b"\n"):
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                copied.append(str(rel))
    bin_ = dst / "_to_delete" / f"{datetime.date.today():%Y-%m-%d}"
    for t in list(dst.rglob("*")):
        rel = t.relative_to(dst)
        if t.is_file() and not skip(rel) and not (src / rel).exists():
            (bin_ / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(t, bin_ / rel)
            moved.append(str(rel))
    return copied, moved


def _sync_to_live(src: Path, live_name: str) -> dict:
    if game_running(vm=False):
        raise RuntimeError("the game is running on the PC: the live copy is not synced during its run")
    dst = (DOCS / "mod" / live_name).resolve()
    if dst.parent != (DOCS / "mod").resolve() or not dst.is_dir():
        raise ValueError(f"no such live mod: {live_name}")
    copied, moved = _sync(src, dst)
    log(f"sync {src} -> {live_name}: {len(copied)} copied, {len(moved)} moved")
    return {"copied": copied, "moved_to_delete": moved}


@mcp.tool()
def sync_mod(repo_folder: str, live_name: str, repo: str = "") -> dict:
    """Make the live mod Documents/.../Victoria 3/mod/<live_name> equal to <repo_folder> of a repo's worktree (default
    the main repo): changed and new files are copied, files gone from the repo are moved to _to_delete/<date>/ inside
    the live mod. Refused while the game runs on this screen."""
    name = repo or MAIN
    wt = REPOS[name]["wt"]
    src = (wt / repo_folder).resolve()
    if not (wt == src or wt.resolve() in src.parents) or not src.is_dir():
        raise ValueError(f"no such folder in the worktree: {repo_folder}")
    return _sync_to_live(src, live_name)


@mcp.tool()
def sync_fork(live_name: str = "") -> dict:
    """The live mod (default: the fork's 'live' of the config) = the fork's bridge worktree (checkout_fork first):
    changed and new files copied, files gone moved to _to_delete/<date>/; docs/, tools/, CLAUDE.md stay out."""
    if "fork" not in REPOS or not (REPOS["fork"]["wt"] / ".git").exists():
        raise ValueError("no fork worktree: checkout_fork() first")
    return _sync_to_live(REPOS["fork"]["wt"], live_name or REPOS["fork"].get("live", ""))


@mcp.tool()
def install_mod(source: str, live_name: str) -> str:
    """Copy a folder to Documents/…/Victoria 3/mod/<live_name> whole (a helper mod for a run, e.g. the profiler view:
    source 'tools:mods/profiler_view'). source: '<repo>:<folder>', 'tools' = vic3_tools. A folder holding another mod
    (another id in .metadata/metadata.json) is not replaced."""
    src = _place(source)
    dst = (DOCS / "mod" / live_name).resolve()
    if dst.parent != (DOCS / "mod").resolve() or not (src / ".metadata" / "metadata.json").is_file():
        raise ValueError(f"not a mod folder: {source}")

    def mod_id(d):
        p = d / ".metadata" / "metadata.json"
        return json.loads(p.read_text(encoding="utf-8-sig")).get("id") if p.is_file() else None

    if dst.exists() and mod_id(dst) != mod_id(src):
        raise ValueError(f"{dst} holds another mod")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    log(f"install_mod {source} -> {live_name}")
    return f"{dst}: {sum(len(f) for _, _, f in os.walk(dst))} files"


@mcp.tool()
def pull_repos() -> str:
    """`git pull --ff-only` in the PC's own checkouts of the project repos and vic3_tools (on the user's request: so
    the PC sees what was pushed). Only fast-forward on the expected branch; local edits are reported, never touched."""
    out = []
    for name, path, want in [(n, r["path"], r.get("branch", "main")) for n, r in REPOS.items()] + \
            [("vic3_tools", TOOLS_REPO, "main")]:
        branch = subprocess.run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                                text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True,
                               text=True).stdout.strip()
        if branch != want:
            out.append(f"{name}: on {branch}, expected {want} - not touched")
            continue
        p = subprocess.run(["git", "-C", str(path), "pull", "--ff-only", "origin", want], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        head = subprocess.run(["git", "-C", str(path), "log", "-1", "--format=%h %s"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace").stdout.strip()
        out.append(f"{name}: {'ok' if p.returncode == 0 else 'FAILED'} -> {head}"
                   + (f" (local changes: {len(dirty.splitlines())})" if dirty else "")
                   + ("" if p.returncode == 0 else "\n  " + (p.stdout + p.stderr).strip()[-1500:]))
    log("pull_repos")
    return "\n".join(out)


@mcp.tool()
def start_run(run_minutes: int = 10, new_game: bool = False, tag: str = "", start_save: str = "",
              autosaves: int = 0, ai_tag: str = "all", commands: str = "", shots: bool = False,
              countries: str = "", load_wait_sec: int = 400, playset: str = "", target: str = "") -> dict:
    """Start a game run in the background: vic3_tools' bridge/game/run_vic3_sandbox.ps1 with the project's hooks
    (parameters as in the skill vic3-sandbox; playset -- the launcher playset's mods for this run). target: "vm" --
    the sandbox VM (its own fixed 2560x1440 screen the scripts' points are measured on; the PC stays free -- the
    default choice), "pc" -- the user's screen (whatever its size), "" -- the bridge's default (PC_BRIDGE_TARGET).
    Returns the run id at once; poll run_status(id). Output: runs/<id>/."""
    if target not in ("", "vm", "pc"):
        raise ValueError("target: vm | pc")
    use_vm = VM if not target else target == "vm"
    if active_run() or game_running(use_vm):
        raise RuntimeError("a run or the game is already going")
    rid = datetime.datetime.now().strftime("r%m%d_%H%M%S")
    out = RUNS / rid
    out.mkdir()
    hooks = _hooks_dir()
    env = dict(os.environ)
    if use_vm:
        params = {"RunMinutes": int(run_minutes), "LoadWaitSec": int(load_wait_sec), "Autosaves": int(autosaves),
                  "AiTag": ai_tag, "NewGame": bool(new_game), "Shots": bool(shots)}
        params.update({k: v for k, v in (("Tag", tag), ("Commands", commands), ("Countries", countries)) if v})
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(VM_RUN), "-Name", VM_NAME,
                "-ScriptDir", str(GAME_SCRIPTS), "-OutDir", str(out), "-ParamsJson", json.dumps(params), "-FetchSaves"]
        if hooks:
            args += ["-HooksDir", str(hooks)]
        if playset:      # the playset's mod list from the PC's launcher; the VM gets those mods
            cl = out / "content_load.json"
            sh(["v3", "playsets", "--content-load", playset, "--out", str(cl)], cwd=_v3_config())
            args += ["-ContentLoad", str(cl)]
        if start_save:   # from the PC's "save games"
            args += ["-StartSave", start_save]
    else:
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(GAME_SCRIPTS / "run_vic3_sandbox.ps1"),
                "-RunMinutes", str(int(run_minutes)), "-LoadWaitSec", str(int(load_wait_sec)),
                "-Autosaves", str(int(autosaves)), "-AiTag", ai_tag, "-OutDir", str(out)]
        if new_game:
            args.append("-NewGame")
        if shots:
            args.append("-Shots")
        for flag, val in (("-Tag", tag), ("-StartSave", start_save), ("-Commands", commands), ("-Countries", countries),
                          ("-Playset", playset)):
            if val:
                args += [flag, val]
        if hooks:
            env["VIC3_HOOKS"] = str(hooks / "vic3_hooks.ps1")
    stdout = open(out / "stdout.txt", "w", encoding="utf-8")
    p = subprocess.Popen(args, cwd=GAME_SCRIPTS, stdout=stdout, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                         env=env)
    (out / "args.json").write_text(json.dumps(args[5:], ensure_ascii=False), encoding="utf-8")

    def wait():
        code = p.wait()
        stdout.close()
        (out / "exit.txt").write_text(str(code), encoding="utf-8")
        log(f"run {rid} exited {code}")

    with _lock:
        _runs[rid] = p
        _targets[rid] = use_vm
    threading.Thread(target=wait, daemon=True).start()
    log(f"run {rid} started{' in the VM' if use_vm else ' on the PC'}: {args[5:]}")
    return {"id": rid, "out": f"runs/{rid}", "target": "vm" if use_vm else "pc"}


def tail(path, n):
    with open(path, encoding="utf-8", errors="replace") as f:
        return "".join(collections.deque(f, n))


@mcp.tool()
def run_status(run_id: str, tail_lines: int = 30) -> dict:
    """State of a run: running / finished (exit code), the tail of its stdout and, once finished,
    of run.log (run.log is not read while the script writes it), and the files in runs/<id>."""
    out = resolve(f"runs/{run_id}")
    with _lock:
        p = _runs.get(run_id)
    exit_file = out / "exit.txt"
    state = ("running" if p and p.poll() is None else
             f"finished, exit {exit_file.read_text().strip()}" if exit_file.exists() else
             "unknown (the bridge was restarted during the run)")
    res = {"state": state, "game_running": game_running(_targets.get(run_id)),
           "stdout": tail(out / "stdout.txt", tail_lines) if (out / "stdout.txt").exists() else ""}
    if state != "running" and (out / "run.log").exists():
        res["run_log"] = tail(out / "run.log", tail_lines)
    res["files"] = sorted(f"{f.relative_to(out).as_posix()} {f.stat().st_size}" for f in out.rglob("*") if f.is_file())
    return res


@mcp.tool()
def stop_run(run_id: str = "") -> str:
    """Kill a run's script and the game (e.g. it stands on «Конец игры» after an annexation).
    The logs are then in docs/logs (the script did not copy them)."""
    with _lock:
        p = _runs.get(run_id) if run_id else None
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NO_WINDOW)
    vm = _targets.get(run_id, VM)
    if vm:
        in_vm('Stop-ScheduledTask "vic3_run" -ErrorAction SilentlyContinue; '
              'Get-Process victoria3 -ErrorAction SilentlyContinue | Stop-Process -Force')
    else:
        subprocess.run(["taskkill", "/F", "/IM", "victoria3.exe"], capture_output=True, creationflags=NO_WINDOW)
    log(f"stop {run_id}")
    return f"game running: {game_running(vm)}"


@mcp.tool()
def list_dir(path: str = "runs", pattern: str = "*", limit: int = 200) -> list[str]:
    """Entries of a folder, newest first: '<name>[/] <size> <mtime>'. Roots: docs (Documents/Paradox Interactive/
    Victoria 3: mod, logs, save games, crashes), game, workshop, runs (bridge runs), bench (v3 bench shots), wt (the
    main repo's worktree), the other repos' worktrees by name, and the config's roots."""
    d = resolve(path)
    items = sorted((e for e in d.iterdir() if fnmatch.fnmatch(e.name, pattern)), key=lambda e: -e.stat().st_mtime)
    return [f"{e.name}{'/' if e.is_dir() else ''} {e.stat().st_size if e.is_file() else ''} "
            f"{datetime.datetime.fromtimestamp(e.stat().st_mtime):%Y-%m-%d %H:%M}" for e in items[:limit]]


@mcp.tool()
def read_text(path: str, offset: int = 0, limit: int = 400, from_end: bool = False) -> str:
    """Lines of a text file, numbered from 1; offset skips lines, from_end gives the last `limit`
    lines. Streams, so a 450 MB save is fine for its first lines but use grep (or v3 save) to find things."""
    f = resolve(path)
    with open(f, encoding="utf-8-sig", errors="replace") as fh:
        if from_end:
            buf = collections.deque(maxlen=limit)
            for n, line in enumerate(fh, 1):
                buf.append((n, line))
            return "".join(f"{i}\t{line}" for i, line in buf)
        out = []
        for i, line in enumerate(fh, 1):
            if i > offset + limit:
                out.append(f"... (more after line {i - 1})\n")
                break
            if i > offset:
                out.append(f"{i}\t{line}")
        return "".join(out)


@mcp.tool()
def grep(path: str, pattern: str, glob: str = "*", max_matches: int = 200, context: int = 0) -> str:
    """Regex search in a file or, recursively, in the files of a folder matching `glob`.
    Lines as 'file:line:text' (context lines with '-')."""
    rx = re.compile(pattern)
    p = resolve(path)
    files = [p] if p.is_file() else sorted(f for f in p.rglob(glob) if f.is_file())
    out, hits = [], 0
    for f in files:
        before = collections.deque(maxlen=context)
        after = 0
        with open(f, encoding="utf-8-sig", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                name = f.name if p.is_file() else f.relative_to(p).as_posix()
                if rx.search(line):
                    out += [f"{name}-{j}-{x.rstrip()}" for j, x in before]
                    before.clear()
                    out.append(f"{name}:{i}:{line.rstrip()}")
                    hits += 1
                    after = context
                    if hits >= max_matches:
                        return "\n".join(out + [f"... stopped at {max_matches} matches"])
                elif after:
                    out.append(f"{name}-{i}-{line.rstrip()}")
                    after -= 1
                else:
                    before.append((i, line))
    return "\n".join(out) or "no matches"


@mcp.tool()
def get_image(path: str, crop: list[float] | None = None, max_width: int = 1600) -> Image:
    """A screenshot (PNG/JPG). crop = [x0, y0, x1, y1] in fractions of the image (0..1), to read a
    tooltip at full resolution instead of the whole 2560x1440 screen; then scaled to max_width."""
    from PIL import Image as PImage
    im = PImage.open(resolve(path)).convert("RGB")
    if crop:
        w, h = im.size
        im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return Image(data=buf.getvalue(), format="jpeg")


@mcp.tool()
def get_file(path: str) -> dict:
    """A file as it is (base64, up to 30 MB) -- a generated PNG to convert to DDS in the cloud, a texture to edit."""
    import base64
    f = resolve(path)
    if f.stat().st_size > 30 << 20:
        raise ValueError(f"{f.stat().st_size} bytes: over 30 MB")
    return {"name": f.name, "size": f.stat().st_size, "base64": base64.b64encode(f.read_bytes()).decode()}


@mcp.tool()
def py_tool(name: str, args: list[str]) -> str:
    """Run a project tool on the PC's files (saves are 450 MB, too big to fetch): tools/<name>.py of the config's
    tool repos in order (each repo's bridge worktree if made, else its checkout), run from that repo's folder. Allowed:
    the config's names and globs. Paths in args may be 'runs/...', 'docs/...' (any root). Returns the output (tail)."""
    allowed = name in PY_TOOLS or (re.fullmatch(r"\w+", name) and any(fnmatch.fnmatch(f"{name}.py", g)
                                                                       for g in PY_TOOL_GLOBS))
    home = next((d for d in (_repo_dir(r) for r in T.get("repos", [MAIN])) if (d / "tools" / f"{name}.py").is_file()),
                None)
    if not allowed or home is None:
        raise ValueError(f"tools: {', '.join(sorted(PY_TOOLS))} and {', '.join(PY_TOOL_GLOBS)} "
                         f"in tools/ of {', '.join(T.get('repos', [MAIN]))}")
    real = [str(resolve(a)) if a.split("/")[0] in ROOTS else a for a in args]
    p = subprocess.run(["py", f"tools/{name}.py", *real], cwd=home, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1200, creationflags=NO_WINDOW,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    log(f"py_tool {name} {real} -> {p.returncode}")
    return f"exit {p.returncode}\n{(p.stdout + p.stderr)[-20000:]}"


@mcp.tool()
def v3(args: list[str], timeout: int = 1800) -> str:
    """Run a `v3` command (vic3_tools) on the PC and return its output, exit code first. The set is the PC's active
    launcher playset; a repo with a bridge worktree is read from it (your pushed branch: checkout first). Read-only:
    def, refs, loc, outline, winner, conflicts, matrix, audit, mods, gui (set only with --dry), lint (not
    --baseline), save, log, bench (start / do / shot / diff / stop -- shots under bench/). Example:
    v3(["refs", "my_var", "--limit", "20"]), v3(["gui", "resolve", "gui/x.gui:120", "--prop", "fontsize"])."""
    sys.path.insert(0, str(TOOLS_REPO))
    from vic3tools import bridge as v3bridge
    out = v3bridge.run([str(a) for a in args], timeout=timeout, cwd=_v3_config())
    log(f"v3 {args} -> {out.splitlines()[0] if out else ''}")
    return out


@mcp.tool()
def wt_diff(repo: str = "") -> str:
    """A repo worktree's changes made by generators (default the main repo), new files included, as a git patch for
    `git apply` in the cloud clone."""
    wt = REPOS[repo or MAIN]["wt"]
    sh(["git", "-C", wt, "add", "-A", "-N"])
    return sh(["git", "-C", wt, "diff", "--binary"])


@mcp.tool()
def fork_diff() -> str:
    """wt_diff(repo="fork")."""
    return wt_diff("fork")


# --- ComfyUI: image generation on the PC's GPU ---------------------------------------------------------------------
# The sandbox VM holds a partition of the same GPU and static memory, so generation and the VM take turns.

_fetches = {}         # model file -> "downloading 1.2/9.8 GB" | "done" | "error: ..."
FETCH_HOSTS = ("huggingface.co", "civitai.com")


def _comfy(path, data=None, timeout=60):
    req = urllib.request.Request(COMFY + path, data=data,
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body[:1] in (b"{", b"[") else body


def _comfy_base() -> Path:
    if C.get("base"):
        return _p(C["base"])
    argv = _comfy("/system_stats")["system"].get("argv", [])
    if "--base-directory" in argv:
        return Path(argv[argv.index("--base-directory") + 1])
    raise RuntimeError("ComfyUI's folder is unknown: set [comfy] base in the config")


def _vm_state() -> str:
    try:
        return ps(f"(Get-VM -Name '{VM_NAME}').State").strip()
    except Exception as e:
        return f"unknown ({str(e).splitlines()[-1] if str(e) else e})"


def _free_gpu() -> str:
    """Shut the sandbox VM down for a generation; refuse while a run uses it."""
    rid = active_run()
    if rid and _targets.get(rid):
        raise RuntimeError(f"run {rid} is going in the VM: stop_run first or wait")
    if _vm_state() == "Running":
        ps(f"Stop-VM -Name '{VM_NAME}' -Force", timeout=300)
        log("comfy: the VM shut down to free the GPU")
        return "the VM was shut down (a bench in it is gone)"
    return ""


@mcp.tool()
def comfy_status() -> dict:
    """ComfyUI: up or not, the GPU and its free memory, the queue, its folder, model downloads in progress, and the
    sandbox VM's state (it shares the GPU)."""
    res = {"url": COMFY, "vm": _vm_state(), "downloads": dict(_fetches)}
    try:
        st = _comfy("/system_stats")
        res["devices"] = [{k: d.get(k) for k in ("name", "vram_total", "vram_free")} for d in st.get("devices", [])]
        res["version"] = st["system"].get("comfyui_version")
        res["queue"] = {k: len(v) for k, v in _comfy("/queue").items()}
        res["base"] = str(_comfy_base())
    except Exception as e:
        res["error"] = f"ComfyUI is not reachable: {e}"
    return res


@mcp.tool()
def comfy_models(folder: str = "") -> dict:
    """Model files ComfyUI sees: folder "" -- the folder names (checkpoints, diffusion_models, text_encoders, vae,
    loras...); a name -- its files."""
    if not folder:
        return {"folders": _comfy("/models")}
    return {folder: _comfy(f"/models/{urllib.parse.quote(folder)}")}


@mcp.tool()
def comfy_get(path: str) -> str:
    """A read-only GET to ComfyUI's API, for building workflows: "/object_info/<NodeClass>" (a node's inputs and
    outputs), "/api/userdata?dir=workflows" (saved workflows), "/api/userdata/workflows%2F<name>.json",
    "/api/workflow_templates" (the installed templates)."""
    if not path.startswith("/") or any(w in path for w in ("/prompt", "/upload", "/interrupt", "/free")):
        raise ValueError("a GET path of ComfyUI's API")
    body = _comfy(path, timeout=120)
    return (json.dumps(body, ensure_ascii=False) if not isinstance(body, bytes)
            else body.decode("utf-8", "replace"))[:60000]


@mcp.tool()
def comfy_fetch(url: str, folder: str, name: str = "") -> str:
    """Download a model file into ComfyUI's models/<folder>/ in the background (huggingface.co, civitai.com only);
    progress in comfy_status()['downloads']. A file already there is not fetched again."""
    host = urllib.parse.urlparse(url).hostname or ""
    if not any(host == h or host.endswith("." + h) for h in FETCH_HOSTS):
        raise ValueError(f"hosts: {', '.join(FETCH_HOSTS)}")
    if not re.fullmatch(r"[\w.-]+", folder):
        raise ValueError("folder: a models/ subfolder name")
    name = name or Path(urllib.parse.urlparse(url).path).name
    if not re.fullmatch(r"[\w.-]+", name):
        raise ValueError("name: a plain file name")
    dst = _comfy_base() / "models" / folder / name
    if dst.exists():
        return f"already there: {dst}"
    dst.parent.mkdir(parents=True, exist_ok=True)

    def get():
        part = dst.with_suffix(dst.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
                size, done = int(r.headers.get("Content-Length") or 0), 0
                while chunk := r.read(1 << 22):
                    f.write(chunk)
                    done += len(chunk)
                    _fetches[name] = f"downloading {done / 1e9:.1f}/{size / 1e9:.1f} GB"
            part.replace(dst)
            _fetches[name] = "done"
        except Exception as e:
            _fetches[name] = f"error: {e}"
        log(f"comfy_fetch {url} -> {dst}: {_fetches[name]}")

    _fetches[name] = "starting"
    threading.Thread(target=get, daemon=True).start()
    return f"downloading to {dst}"


@mcp.tool()
def comfy(workflow: dict, inputs: list[str] | None = None, wait: int = 45) -> dict:
    """Run a ComfyUI workflow (API format: {"<node id>": {"class_type": ..., "inputs": {...}}}).
    inputs: images to upload first ('wt/...', 'game/...', 'gen/...', any root, or "data:<name>;base64,<data>" made
    in the cloud; DDS goes as PNG); the strings "$in0",
    "$in1"... in the workflow become their uploaded names (for LoadImage). Shuts the sandbox VM down first (they share
    the GPU). Waits up to `wait` s (the client gives a call 60 s): unfinished -> comfy_result(id) later.
    Output images: gen/<prompt id>/ -- read them with get_image."""
    from PIL import Image as PImage
    note = _free_gpu()
    text = json.dumps(workflow)
    for i, src in enumerate(inputs or []):
        if src.startswith("data:"):          # an image made in the cloud: data:<name>;base64,<data>
            import base64
            head, _, b64 = src.partition(",")
            name, data = Path(head[5:].split(";")[0]).name or f"in{i}.png", base64.b64decode(b64)
            f = Path(name)
        else:
            f = resolve(src)
            name, data = f.name, f.read_bytes()
        if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            buf = io.BytesIO()
            PImage.open(io.BytesIO(data)).save(buf, "PNG")
            name, data = f.stem + ".png", buf.getvalue()
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + \
               f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n" \
               f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(COMFY + "/upload/image", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            text = text.replace(f'"$in{i}"', json.dumps(json.loads(r.read())["name"]))
    pid = _comfy("/prompt", json.dumps({"prompt": json.loads(text), "client_id": "vic3-pc"}).encode())["prompt_id"]
    log(f"comfy {pid} queued")
    return {**comfy_result(pid, wait), **({"note": note} if note else {})}


@mcp.tool()
def comfy_result(prompt_id: str, wait: int = 45) -> dict:
    """A queued comfy() run: waits up to `wait` s; done -> its images saved to gen/<prompt id>/ (with errors, if any);
    else "running" with the queue's length."""
    end = time.time() + wait
    while True:
        h = _comfy(f"/history/{prompt_id}")
        if prompt_id in h:
            break
        if time.time() > end:
            return {"id": prompt_id, "state": "running",
                    "queue": {k: len(v) for k, v in _comfy("/queue").items()}}
        time.sleep(2)
    entry = h[prompt_id]
    out = GEN / prompt_id
    out.mkdir(exist_ok=True)
    files = []
    for node in entry.get("outputs", {}).values():
        for im in node.get("images", []):
            q = urllib.parse.urlencode({k: im[k] for k in ("filename", "subfolder", "type")})
            (out / im["filename"]).write_bytes(_comfy(f"/view?{q}", timeout=120))
            files.append(f"gen/{prompt_id}/{im['filename']}")
    status = entry.get("status", {})
    log(f"comfy {prompt_id} {status.get('status_str')}: {files}")
    return {"id": prompt_id, "state": status.get("status_str"), "files": files,
            "errors": [m[1] for m in status.get("messages", []) if m[0] == "execution_error"]}


class BearerAuth:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            got = dict(scope["headers"]).get(b"authorization", b"").decode()
            if not hmac.compare_digest(got, f"Bearer {TOKEN}"):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    log(f"bridge up on 127.0.0.1:{PORT} with {CONFIG}" + (f", runs in the VM {VM_NAME}" if VM else ""))
    uvicorn.run(BearerAuth(mcp.streamable_http_app()), host="127.0.0.1", port=PORT, log_level="warning")
