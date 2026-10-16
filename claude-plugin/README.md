# Claude Code plugin

For coding agents working on Victoria 3 mods, on top of the `v3` command (install the package first, see the repo's
`README.md`).

- **Skill `vic3-search`** — when a question is "where is X defined, who uses it, which mod wins, what does this loc key
  say, what is in this big file", use `v3 def` / `refs` / `winner` / `loc` / `outline` instead of grep and reading
  whole files.
- **Skills for the work itself** (stage 7): `vic3-modding` — how the engine loads and merges mods and the facts
  checked in the game (a short core + references by topic); `vic3-compat` — compatibility patches, merges, megapacks,
  add-ons, generators; `vic3-gui` — a GUI style file from vanilla (`v3 gui style`) and the passes audit / critique /
  polish with checklists and anti-patterns; `vic3-sandbox` — runs in the sandbox VM, the bench `v3 bench`, reading
  crashes and logs; `vic3-repo-rules` — git and safe writes of game files.
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
