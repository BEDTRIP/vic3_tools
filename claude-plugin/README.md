# Claude Code plugin

For coding agents working on Victoria 3 mods, on top of the `v3` command (install the package first, see the repo's
`README.md`).

- **Skill `vic3-search`** — when a question is "where is X defined, who uses it, which mod wins, what does this loc key
  say, what is in this big file", use `v3 def` / `refs` / `winner` / `loc` / `outline` instead of grep and reading
  whole files.
- **Skills for the work itself:** `vic3-modding` — how the engine loads and merges mods and the facts
  checked in the game (a short core + references by topic); `vic3-compat` — compatibility patches, merges, megapacks,
  add-ons, generators; `vic3-gui` — a GUI style file from vanilla (`v3 gui style`) and the passes audit / critique /
  polish with checklists and anti-patterns; `vic3-sandbox` — runs in the sandbox VM, the bench `v3 bench`, reading
  crashes and logs; `vic3-repo-rules` — git and safe writes of game files.
- **Hook (SessionStart)** — `v3 hook session-start`. At a session's start the agent gets a short menu of what `v3`
  can do (find, GUI, checks, saves and logs, the bench) and whether the session's folder is the game or a mod of the
  set. So a project needs no section about `v3` in its own `CLAUDE.md`; which tool to use stays the agent's choice.
  Silent when the game is not on the machine (a cloud session).
- **Hook (PreToolUse on Grep, Bash, PowerShell, Read)** — `v3 hook pre-tool-use`. A text search for one identifier
  over the game, the Workshop or a mod of the active playset is refused the first time in a session, and the refusal
  carries the index's answer (`v3 def` + `v3 refs`, with the mods' folders). A read of a whole `.gui` / `.txt` over
  300 lines there is refused once with the file's outline. The same call repeated goes through; names the index does
  not know, regexes, other folders and other file types are never touched. Measured on six reference tasks: when the
  agent uses the index, they cost about half the tokens (`docs/benchmarks/2026-10-15-stage2.md`); with a rule in
  `CLAUDE.md` alone agents mostly kept to grep — hence the hook.

Install from this repo:

```
/plugin marketplace add BEDTRIP/vic3_tools
/plugin install vic3tools@vic3tools
```

or, with a local checkout (the plugin is then read from the folder, edits apply at the next session):

```
claude plugin marketplace add <path to vic3_tools>
claude plugin install vic3tools@vic3tools --scope user
```

- **Hook (PostToolUse on Edit, Write, MultiEdit)** — `v3 hook post-tool-use`. An edited `.gui` / `.txt` / `.yml`
  of a playset mod goes through `v3 lint`'s per-file rules (braces, BOM, project rules, GUI types that never apply,
  text width around the edited lines); reports not in the mod's baseline reach the agent in the same turn.

`v3` must be on `PATH` for the hooks; without it the hook fails quietly and nothing is blocked.

## Cloud sessions (claude.ai/code)

A cloud session loads **no** plugin from the repo's `.claude/settings.json`: `enabledPlugins` and
`extraKnownMarketplaces` there are ignored in the cloud (they need the workspace-trust dialog, which a cloud session
never shows), and the user's `~/.claude` on the PC does not reach it either (docs: *cloud-environments → What carries
over from your setup*, *plugins/install → Cloud session*, checked 16.10.2026). So the projects do **not** declare the
plugin in their `.claude/settings.json` — in the cloud it would do nothing, and on the PC a second declaration of the
marketplace `vic3tools` with a GitHub source would make Claude Code re-fetch it over the local `directory` one.

The documented way is the cloud environment's **setup script** (claude.ai/code → the environment → *Setup script*;
it runs as root before Claude Code starts and is cached with the environment for about a week). One line there:

```
curl -fsSL "https://raw.githubusercontent.com/BEDTRIP/vic3_tools/main/claude-plugin/cloud-setup.sh?$(date +%s)" | bash || true
```

[`cloud-setup.sh`](cloud-setup.sh) installs the `v3` package (`pip`, from a checkout of `vic3_tools` attached to the
session if there is one, else from GitHub) and then the plugin at user scope (`claude plugin marketplace add` +
`claude plugin install vic3tools@vic3tools`), and makes the repos' MCP servers (the PC bridge `vic3-pc`) work in a
session with several repos: Claude Code reads `.mcp.json` only from the session's working folder, and such a session
works in the repos' parent (`/home/user`), so the script merges the repos' `mcpServers` into `/home/user/.mcp.json`.
The token stays `${PC_BRIDGE_TOKEN}` in the file and is filled from the environment's variable when the session starts;
the setup script itself sees none of the environment's variables (checked 16.10: `PC_BRIDGE_TOKEN unset` in its log
while the session had it), so it cannot register the server with the token itself. A change of the setup script's
text (a comment will do) drops the cached environment. What the script did is in `~/vic3tools-cloud-setup.log` of the
session (user, which variables it saw, which repos were there, each step). Checked 16.10 in a session with three repos: the `mcp__vic3-pc__*` tools
were there and `v3 def` through the bridge answered. Every step may fail without stopping the session. The environment is
shared by every repo started in it, so `vic3_mods` and the fork both get the plugin. `vic3_mods`' own SessionStart
hook (`.claude/hooks/session-start.sh`, pip packages for its tools) stays as it is.

The hooks in the cloud: there is no game there, so `session-start` prints nothing, `pre-tool-use` lets every call
through and `post-tool-use` says nothing (checked 16.10 on Linux without the game: all three exit 0 with no output,
broken stdin too). Without `v3` on `PATH` (the setup script did not run or pip failed) the hook command fails and
Claude Code shows a non-blocking hook error; nothing is refused.

Not verified without a real cloud session: that the `claude` CLI is on `PATH` in the setup script and that a plugin
installed there loads in the session (the docs say a plugin installed from the shell loads at the next start, which
the session is); that the GitHub proxy lets the setup script clone a public repo that is not attached to the session
(it refuses `archive/` downloads of unattached repos, even public ones — if the clone or `pip install git+…` fails,
attach `vic3_tools` to the session as a second repository, the script then installs from that checkout). Check in
the first cloud session: `claude plugin list` shows `vic3tools`, `/vic3tools:vic3-search` is listed, `v3 -h` runs.
