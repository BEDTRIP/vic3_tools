# Plan of the tools for Victoria 3 mods

The plan of this repo. Moved here from `vic3_mods` on 2026-10-15.

## Digest of the conversation (cloud session, 2026-10-15)

Where the plan comes from. The user asked which Claude Code extensions are needed for UI design (a Vic3 mod and a
separate PHP website), then what the community has already built, then which tools for modding are still missing.

**Conclusions on UI design.** The agent designs badly not from ignorance but because it does not see the result and has
no sample to lean on. What is needed is a loop "edit → screenshot → edit" and a sample (a design system, vanilla types).

- **The PHP website** (another project, not part of this plan): the plugins `frontend-design` (Anthropic), Impeccable
  (`/plugin marketplace add pbakaus/impeccable`, then `/impeccable init`, passes `critique` / `polish`), Playwright MCP
  (page screenshots); a ready CSS base (Tailwind / Pico) and a design section in the site's `CLAUDE.md` with sample
  screenshots. Taste Skill and UI/UX Pro Max largely repeat Impeccable — do not install them all at once.
- **Vic3 GUI:** the community has no ready skills, preview or checks of `.gui`. There is a general skill
  `victoria3-mod-dev` (trotsky1997) — about events and localization, not GUI. It turned out later that `vic3-tiger`
  (amtep) checks `.gui` as well — see "What the community already has".

**Impeccable for Vic3.** What carries over is the method, not the content: `init` (a style file), separate passes with
checklists, a list of anti-patterns, automatic checks without a model. Its knowledge is about CSS/DOM, the checking
engine is in Rust, for HTML. Conclusion — our own skill `vic3-gui` in the same spirit (stage 7) and GUI checks in
`v3 lint` (stage 4).

**CWTools.** The rules for Vic3 are alive (`cwtools-vic3-config`, updated in June 2026 to 1.13.9), but `config/gui/`
holds only `text_formats.cwt` and `text_icons.cwt` — widgets are not described. The VS Code extension is for a human;
for an agent it is useful if the CWTools language server is connected to Claude Code through a plugin (`.lsp.json`):
errors after each edit, go to definition. What gets in the way is not the cloud but the vanilla files (they are needed
on the spot) and running the server outside VS Code — not checked (stage 5). A GUI preview is not for CWTools: our own
`.gui` → PNG render, as a separate program (stage 9).

**VS Code extensions and Claude Code plugins.** An extension is for a human in an editor (highlighting, underlines). A
plugin is for the agent: skills, commands, hooks, MCP servers, language servers. One server (like CWTools) can have both
"faces".

**The `vic3-pc` bridge** is good for runs, not for a layout loop. An intermediate step is a "test bench": the game in debug
mode, `.gui` re-read on the fly (to be checked), a snapshot of an area (stage 6).

**User's decisions of 15.10:**

1. The tools live in a separate new repo (the user creates it); `vic3_mods` keeps what belongs to the projects.
2. The repo holds what is common to any mods and modders; what belongs to particular mods stays in the projects.
3. The repo's main language is English, Russian is a localization layer; with a Russian-speaking modder the agent
   speaks Russian.
4. The repo is open; no game files are put in it, everything is read on the spot.
5. Three roots: the game folder, Workshop mods (read straight from Steam), the game's documents; `vic3_mods_out` is a
   special case of a project, not the core.
6. The environment is built once per machine by the program `v3 setup`, updates happen by themselves.

7. First take what the community has made (tiger, Modding-Digests dumps, CMF hooks), our own on top.

**User's decisions of 15.10, local session** (answers to the plan's questions):

8. The repo is `BEDTRIP/vic3_tools` (created, open), the package `vic3tools`, the command `v3`; licence MIT (tiger is an
   external program). Commits go straight to `main`, in English, git rules as in `vic3_mods`.
9. Modding-Digests — we keep a link to a commit for each game version, updating is explicit.
10. Moving the scripts is done by `vic3_mods`, links in the fork's documents and the bridge's name templates; the old
    copy is deleted in the same commit.
11. No issues to other people's repos (tiger, CWTools) — gaps are collected into a list for the user.
12. Work is a local session through Remote Control; the bridge for the cloud is updated when everything is ready.
13. **The runs sandbox is a Hyper-V virtual machine with a share of the video card (GPU-P)**: the game and the bridge
    are inside the VM, the user meanwhile works on the PC. Until there is a VM, the game runs on the PC as before. See
    "Runs sandbox".
14. tiger goes to `%LOCALAPPDATA%\vic3tools\bin` (later also everything else `v3 setup` installs); pytest, ruff —
    `vic3_tools\.venv`. CWTools — only at stage 5.

**tiger on the fork (15.10, evening):** `vic3-tiger` 1.19.0 (for game 1.13.5, we have 1.13.11) — 16 s, 5462 reports
(3105 error, 2258 warning); 2948 are `missing-item`, mostly because CMF and ETF are not loaded (the fork depends on
them). The analysis is to be done with the dependencies loaded (`vic3-tiger.conf`, `load_mod`), then the share of false
reports and whether it catches the known GUI errors (616 reports on `.gui`). Raw material — `_tmp_analysis/tiger/`.

**First step in the local session:** answer the questions at the end of the plan, create the repo and start stage 0.
Meanwhile, on the PC — run `vic3-tiger --json` over the fork with vanilla: how much it finds, how much is false,
whether it catches the known GUI errors. This decides how far stage 4 comes down to a wrapper over tiger.

## What the community already has (survey of 15.10)

First take what exists, our own only on top.

| what | whose | what it gives us | how to use |
| --- | --- | --- | --- |
| **tiger** (`vic3-tiger`) | [amtep/tiger](https://github.com/amtep/tiger), Rust, GPL-3.0 | checks the whole mod, **including `.gui`**: ~400 widget properties bound to the game (`src/gui/properties.rs`), value types, `[…]` expressions against Vic3's data-function tables (`src/vic3/tables/datafunctions.rs`); `--json` output, a suppression database `--suppress` | **the core of `v3 lint`** — run as an external program and parse its JSON; our own rules only for what tiger lacks; gaps found go back to the author |
| **Modding-Digests** | [Victoria-3-Modding-Co-op](https://github.com/Victoria-3-Modding-Co-op/Modding-Digests) | dumps of the game's documentation **by version** (1.8.7 … 1.14.5 beta): `script_docs/` (effects, triggers, event_targets, event_scopes, modifiers, on_actions, custom_localization), `data_types/` (common, gui, script…), `types/`; change summaries of every version; diff scripts | the source of dumps for `v3 setup` by game version — **no need to run the game** if the version is already published; the diff between versions is for updating mods after a patch |
| **CMF** | [Community-Mod-Framework](https://github.com/Victoria-3-Modding-Co-op/Community-Mod-Framework) (already in the fork's playset) | GUI hooks that do not overwrite vanilla types (UI Extensions, side-panel buttons, journal widgets, event windows, modifier icons), mod detection, a wiki for every function; `vic3-tiger.conf` in the root | references for the `vic3-gui` skill (how to plug into someone else's interface without conflicts); the rule "a CMF hook first, our own copy of a type after" |
| **ETF** | [Expanded-Topbar-Framework](https://github.com/Victoria-3-Modding-Co-op/Expanded-Topbar-Framework) (also in the playset) | hooks of the top bar | the same |
| Mod-Template, Graphical-Assets, Performance-Measuring, Community-State-Framework, IntelliJ Live Templates | the same organization | a mod repo template; icon templates; measuring "real time / game month" (Go, like our `ld_speed.py`); splitting the map | the template is a sample for `v3 new`; the rest as the occasion arises |
| **Victoria3Tools + JominiTools** | [dementive](https://github.com/dementive/Victoria3Tools), Python, MIT | a Sublime plugin: go to definition of GUI types and templates, preview of `.dds` textures, completion by scope, running tiger | borrow the parsing of GUI types and textures (the licence allows it) |
| **CWTools** | [cwtools](https://github.com/cwtools/cwtools-vic3-config) | `.cwt` rules for Vic3 script (no widgets), a language server | stage 5 — after tiger, if there is still a need for go-to-definition |
| small stuff | jakeOmega/Victoria3ModdingToolkit (no licence), Imperia dev-utilities (viewing and editing values), Vic3-mapdata-editor, Garibaldi (saves) | — | do not rely on |

What this changes in the plan: checks of GUI and bindings (stage 4) are mostly **already done in tiger**; the game's
dumps (step 4 of `v3 setup`) are **already published** by version. Ours is the index and short answers (stage 2),
template expansion and the reference (stage 3), the bridge, the render, skills, project rules.

## Why

The agent (cloud and local) and the human spend time and tokens on the same things: finding a definition, reading a huge
file for one block, learning about an error only from `error.log` after a run, laying out a GUI blind. The tools must:

1. **Answer briefly** — `path:line` and an extract, not the whole file. Output by default is meant for the agent
   (limited in size), `--json` is for other tools.
2. **Catch errors before a run** — checks of script, localization and GUI, automatically after an edit (a hook).
3. **Show the GUI without a run** — first a test bench on the live game through the bridge, then our own `.gui` → PNG render.
4. **Be common** — work with any mod and playset; what belongs to a project (compatibility patches, the fork's money model) stays
   outside, on top of the common core.

The measure: tokens and turns on six reference tasks T1–T6 (find where something is defined and who uses it; fix a
widget in a panel; find the cause of an error from `error.log`; which of several GUI types wins; a widget property's
value after templates; which text the player sees) — measured before and after stages 2–4; the "before" is
[benchmarks/2026-10-15-baseline.md](benchmarks/2026-10-15-baseline.md).

## What exists already

Everything is in `vic3_mods`: 165 scripts in `tools/`, the bridge, four skills, a hook, the profiler mod.

| group | what | where to |
| --- | --- | --- |
| **Script parsing** | `ld_pdx.py` (records with exact boundaries), `vic3lib.py` (byte parsing for generators), `index_mod.py`, `ld_index.py` (definitions and references), `ld_braces.py`, `vfs_order.py` (who wins a key by load order), `vic3merge3.py` (three-way merge of records) | **the core** of the new repo; merge the two parsers into one |
| **Mod compatibility** | `scan_conflicts.py`, `pair_matrix.py`, `content_holes.py`, `check_megapack_conflicts.py`, `replace_audit.py`, `stale_bodies.py`, `loc_dead_overrides.py`, `summarize_mod_vs_vanilla.py`, `compare_gui_names.py`, `scan_event_definitions.py`, `list_lawgroups_diff.py` | **to the new repo**, on top of the core; three of them now have their own key parsing with the same "black list" |
| **Generators of compatibility patches and addons** | `regen_greys_*`, `regen_vc_*`, `regen_llwa_*`, `regen_hc_*`, `regen_tgr_*`, `build_addon_*`, `*_metadata.py`, `tgr_default_strategy.py`, `regen_ef_tr_copies.py` (~40) | **stay** in `vic3_mods`; to the new repo — the common frame (`ld_gen.emit`, the `--check` mode, building an addon from pairs) |
| **The fork's generators** | `regen_ef_*`, `regen_ld_*` (~25), `ld_gen.py`, `ld_curdata.py` | **stay** (the fork's content); the frame is common |
| **Saves** | `save_*`, `scan_save_*`, `ld_save_*`, `scan_building_*`, `scan_goods_io.py`, `scan_pop_need.py`, `scan_company_buildings.py`, `check_fx_reserves.py` (~20) | **the core**: one parser of a text save with a cache, the scripts become queries to it |
| **Logs and runs (common)** | `ld_logcats.py`, `ld_logdiff.py`, `ld_errsites.py`, `ld_runcmp.py`, `ld_speed.py`, `ld_logparts_check.py` | **to the new repo** |
| **Logs of the fork's money model** | parsers of `eflog.txt`: `ld_run_report.py`, `ld_run_*`, `check_*`, `ld_*check.py`, `ld_probe_*`, `ld_r1a_checks.py`, `ld_r23_checks.py` and others (~30) | **stay**; one-off probes of stages go to the archive |
| **The fork's documentation** | `ld_docs_*`, `ld_md_wrap.py`, `ld_comment_clean.py`, `ld_smells.py`, `docs_index.py` | stay; `regen_ld_vanilla_concepts.py` (a dump of the game's concepts) is **common**, to the new repo |
| **Game and PC** | the bridge `pc_bridge/` (an MCP server on the PC: branches, mod sync, a run, logs, screenshots, grep, 6 allowed scripts), `run_vic3_sandbox.ps1`, `vic3_ui*.ps1` (clicks, hovers, screenshots by shares of the window), `ld_sync_live.py`, `ld_install_mod.py`, `playset_content_load.py`, `ld_pc_git_pull.py`, the mod `ld_profiler_view` | **to the new repo**, generalize (paths, playset, mod become parameters) |
| **Skills and hooks** | `vic3-sandbox` (200 lines), `night-run`, `night-until`, `run-report`; the hook `session-start.sh` | split `vic3-sandbox` into a common part (into the plugin) and a project part; the night ones are common for any project; `run-report` is the fork's |

Documents are tools too: they are knowledge the agent reads instead of finding out anew.

| document | what is in it | where to |
| --- | --- | --- |
| **"Правила работы с модами Victoria 3.md"** (314 lines) | how the game loads and overrides mods, facts of 1.13 (script, buildings, GUI, CMF / ETF), diagnostics, analysis procedures, what not to do | **to the new repo — the knowledge base about the engine**: a short skill `vic3-modding` + references by topic, read when needed; the checkable facts go into the `v3 lint` rules (the first file registers a type, a stale copy of a vanilla `.gui` without a widget is a crash, `REPLACE` without fields) |
| **"Правила — сборка.md"** (159) | blocks, pairs, addons, building a megapack, generators | the method becomes the **common skill `vic3-compat`**; what concerns a particular set stays |
| **"Правила — проект.md"** (328) | what lies where, `blocks.json`, the format of a compatibility patch's README, pair statuses, the environment (Python, CRLF, git) | **stays**; section 8 (environment) is common, in the tools repo |
| `CLAUDE.md` of both repos | git and commit rules, the same in two places | the common working rules once, in the plugin; in the projects' `CLAUDE.md` — a link and the project part |
| `tools/steam desc rules.txt` | rules for Workshop descriptions | a common publishing skill |
| `сводки по модам/` (9 summaries) | what other people's mods of the set do | **stay** — knowledge about the set |
| `README.md`, "План проекта.md" | the entry and the plan of `vic3_mods` | stay |
| the fork's `ваниль/` (614 notes) | the game's concepts from tooltips — generated by `regen_ld_vanilla_concepts.py` | the generator goes **to the new repo**; the notes are each project's own (sections "how it is used in the fork") |
| the fork's `docs/`, `понятия/`, `решения.md` | the structure and meaning of the fork | stay with the fork |

What gets in the way now:

- **No common core.** Two parsers (`ld_pdx.py`, `vic3lib.py`) and regular expressions in separate scripts; each save
  script reads a save of hundreds of megabytes anew.
- **Paths are hard-coded** (`FORK = ../..`, `GAME = C:\games\…`), different in every script.
- **One-off mixed with permanent:** stage probes (`ld_probe_*`, `ld_r1a_checks.py`) next to the core; `_to_delete/`.
- **History in docstrings** — stage numbers and dates instead of a description.
- **No tests.**
- **Nothing for GUI**, except `compare_gui_names.py` and `ld_vitrine.py`. **No vanilla reference** — the agent searches
  the game's files through the bridge or from memory.
- **The bridge is built for runs:** a short loop "edit → picture" cannot be made with it; the list of scripts that may
  be run on the PC is six names.

## Layout of the new repo

```
vic3tools/              Python package
  core/                 lexer and parser with positions; load order (VFS); the paths config
  index/                SQLite index: definitions, references, localization, GUI types and templates, textures, defines
  lint/                 check rules and one runner
  gui/                  outline, template expansion, vanilla reference, edit by path, a render later
  compat/               conflicts, pair matrix, who wins a key, merge
  save/                 parser of a text save, cache, queries
  logs/                 error.log by families, comparing runs, error places in code
  gen/                  frame of generators: emit, --check
bridge/                 the PC's MCP server (a generalized bridge) and the game's scripts (PowerShell)
claude-plugin/          the Claude Code plugin: skills, hooks, MCP (the bridge), LSP (CWTools, if it fits)
tests/                  tests on small examples
```

- **One command** `v3 <subcommand>` (`v3 def`, `v3 refs`, `v3 outline`, `v3 lint`, `v3 winner`…), each with `--help`,
  short output and `--json`.
- **Projects plug in the package** (`pip install -e ../vic3-tools`) and keep their own: the generators of compatibility patches in
  `vic3_mods`, the `eflog` parsers and document checks with the fork.

## Where the files come from

The repo is **open** (user's decision of 15.10). It holds code, rules, documents; **nothing from the game**: no copies
of vanilla files, no textures, no localization dumps. Everything needed from the game the tools read on the spot, from
each user's own folders; the index, the reference and the glossary are built there too, into a cache outside the repo.

Three roots are all that is needed for work:

| root | what is there | how to find it |
| --- | --- | --- |
| **game** | vanilla: `game/` (script, GUI, localization, textures), `victoria3.exe` | Steam: `libraryfolders.vdf` → the library with app 529340 |
| **Workshop mods** | `steamapps/workshop/content/529340/<id>/` — mods as they are, read straight from there | the same Steam library |
| **game documents** | `Documents/Paradox Interactive/Victoria 3/`: `logs/`, `save games/`, `mod/` (local mods), `launcher-v2.sqlite` (playsets and mod order), `content_load.json`, crash dumps | the Windows "Documents" folder (allowing for a move to OneDrive) |

- **Found by themselves**, the config `vic3tools.toml` is only to correct what was found. `v3 where` prints what was
  found.
- **The playset comes from the launcher:** the set and order of mods are read from `launcher-v2.sqlite` (as
  `playset_content_load.py` does now); mods are taken from the Workshop or from `mod/` by their paths. No copies of mods
  of our own are needed.
- **Extra sources, if the project wants them:** a working copy of a mod in git (the fork), snapshots of mods by commits
  (`vic3_mods_out`, for diffs between versions) — in the project's config, not in the core.
- **Read only.** The tools write to the cache, to the project's folder and, by an explicit command, to `mod/` (syncing
  the live copy).
- **Cloud:** there are no game folders there and copying them is not needed — the cloud agent calls the same `v3`
  commands on the PC through the bridge and gets a short answer. So the bridge v2 (stage 6) is "`v3` on the PC", not a
  set of separate tools. What does not need the game (parsing the project's files, generators, checking documents) works
  in the cloud by itself.
- **Before publishing** — a check for secrets and personal things: the bridge's token and address, paths with the user's
  name, e-mail.

## Install and update

The environment is built **once per machine** by the command `v3 setup`, afterwards it maintains itself. It is an
ordinary program, not the agent's work: the steps are the same and checkable. The agent (the skill `vic3-setup`) only
runs it, reads the report and helps where a human is needed.

**`v3 setup` on the PC:**

1. Check Python, install the package.
2. Find the three roots, show what was found, write `vic3tools.toml` (ask only if nothing was found or several were).
3. Build the cache: an index of vanilla and of the playset's mods, the GUI reference, a glossary from localization.
4. Dumps of the game's documentation (`script_docs`, data types) — take them from Modding-Digests for the game's
   version; if the version is not there yet — run the game once with console commands and collect the logs (this takes
   the screen — warn the user). Install the right version of tiger.
5. Install the Claude Code plugin: skills, hooks, the bridge's MCP, LSP (if CWTools fits).
6. Optionally, the bridge: token, tunnel, autostart.
7. At the end, `v3 doctor`: what is ready, what is not and why.

**Updating without reinstalling:** the cache remembers the game's version and file dates. A patch came out, a Workshop
mod updated, the playset changed — at the next call only what changed is reindexed, and the dumps from the game (step 4)
the command itself asks to repeat after the game's version changes.

**In the cloud** there is no game install: the session-start hook installs the package and checks the link to the
bridge. Everything that needs the game's files goes to the PC through the bridge.

## Language

The repo is for any modders, so the main language is English, Russian is a localization layer (user's decision of
15.10).

- **In English — everything main:** code, names, comments, docstrings, `--help`, skills (`SKILL.md`), documents, commit
  messages.
- **Russian is a localization, not a second original:**
  - documents for people — a mirror `docs/ru/` with the same sections; each translation has in its header a mark of
    which version of the English it was made from, and the check `v3 docs check-ru` shows the stale ones;
  - command output — a message catalog (`en` by default, `ru`), the language comes from the config or the environment;
  - skills stay English (more reliable for the agent), but tell it to **answer in the user's language**.
- **Terms without invention:** a glossary en ↔ ru built from the game's own localization (English and Russian text by
  one key) — the agent names things as they are named in the Russian Victoria 3, not by its own translation. The tools'
  own terms (index, lint, outline…) go in the same glossary, as a separate section.
- **Moving the documents:** the Russian rules are translated into English when moved, the Russian text becomes the first
  version of `docs/ru/`.
- The projects (`vic3_mods`, the fork) live by their own rules: Russian documents and commits, as now.

## Stages

The order is by gain per effort. "Where" is what is needed to work: the cloud can manage alone, or the PC is needed.

| # | stage | what we get | where |
| --- | --- | --- | --- |
| 0 | **Frame** | the repo, the package, `v3`, `v3 setup` / `v3 where` / `v3 doctor` (finding roots, config), a code linter and pytest in CI, an empty plugin; a message catalog en / ru, `docs/ru/`, a glossary from the game's localization (a dump from the PC). **Done 2026-10-15, commit 82c9149:** the package `vic3tools`, the command `v3` with `where` / `setup` / `doctor` / `glossary` / `docs check-ru`, finding roots and `vic3tools.toml` (user, then project), the glossary from the game's localization (58.7k terms, all 11 languages) in the cache, a message catalog en / ru, `docs/usage.md` + `docs/ru`, ruff + pytest + CI (Windows, Linux), an empty Claude Code plugin with the repo as its marketplace. Not in stage 0 (stays for later stages, as planned): the Modding-Digests dumps and installing tiger from `v3 setup` (step 4), the plugin's content | cloud; the glossary — on the PC |
| 1 | **Core and compatibility** | one parser (from `ld_pdx.py` + `vic3lib.py`), VFS by playset; on it — `scan_conflicts`, `pair_matrix`, `vfs_order`, `replace_audit`, `stale_bodies`, `loc_dead_overrides`; the old copies in `vic3_mods` call the package **Done 2026-10-15:** `vic3tools.core.script` (tokens and records with exact boundaries, byte-faithful read/write; `ld_pdx.py` and `vic3lib.py` in `vic3_mods` are now its wrappers — `--check` of all 60 generators, `ld_verify_port`, `ld_index` byte-identical before and after); `core.vfs` (playset from the launcher, set files, load-order rules); a per-mod index cached and updated by itself; `v3 playsets` / `mods` / `winner` (records, `loc`, `gui`) / `conflicts` / `matrix` / `audit replace|stale|loc-dead` — checked against the old scripts on `vic3_mods`' `blocks.json` (matrix identical; audits identical; differences only where the old scripts were wrong: event ids, a stale index cache). The six old scripts are wrappers calling `v3`. One call now answers T1, T4 and T6 of the benchmark. | cloud |
| 2 | **Index** | SQLite over vanilla and the playset; `v3 def X`, `v3 refs X`, `v3 loc KEY`, `v3 outline <file>` (a tree of records and widgets with line ranges); a rule in the projects' CLAUDE.md "big file — `outline` first" **Done 2026-10-15:** a SQLite index per mod (definitions with line ranges, references with the record and keys around them, loc texts en/ru), refreshed by changed files; `v3 def` / `refs` (globs, writes, files that never load) / `loc` (also by the text the player sees) / `outline` (`--find`, `--at`); `v3 setup` indexes the active playset; `[mod_paths]` maps a playset mod to its git checkout; the stage-1 commands read the same index; the rule "search with `v3` first, outline before a big file" is in the projects' `CLAUDE.md`. Measured on T1–T6: `docs/benchmarks/`. | PC (vanilla on the spot); from the cloud — through the bridge — **the main token saving** |
| 3 | **GUI** | `v3 gui resolve` (a widget with `using` / `blockoverride` substituted), a reference of vanilla types, templates and textures with samples, `v3 gui set <file> <path> prop=…`, a check: does the text fit the width in 11 languages **Done 2026-10-15:** `v3 gui resolve` (type chain, `using`, `block` / `blockoverride` substituted; every property with `file:line` and the path it came by; `--prop`, `--type`), `v3 gui types` / `templates` / `textures` (definition, base, blocks to override, uses, an example; texture sizes from the DDS / PNG header), `v3 gui set` (replace or insert at the widget's own level, byte-faithful, `--dry`, `--find`), `v3 gui fit` (the game's `.font` files per language, a TrueType / OpenType reader, wrap / shrink / elide per language, `--width`). T5 is one `resolve --prop` call; T2's edit is `gui set` on 467 and 463 (lines 475–476, 492–493); `fit` shows the English label wrapping at 100 and not at 130 — and the Russian one wrapping even at 130. Checked in the game the same day with a probe window (`docs/usage.md`, GUI): the override order was wrong — the one closest to the block wins (a type's own beats the instance's), fixed; templates defined twice, the default font, the shrink step, file-local `@constants`, text width (119 px vs 120 measured) and wraps match. | PC; from the cloud — through the bridge |
| 4 | **Checks and hook** | `v3 lint` = tiger (`--json`, suppression database) + our own rules on top: duplicate GUI types by the "first file" rule, text width, `REPLACE` without fields, project ones; short output, by place; a hook after an edit in the plugin **Done 2026-10-15:** `v3 lint` runs vic3-tiger with a generated config (the mod's own `vic3-tiger.conf` + `load_mod` for every mod before it in the set), cached until a file changes (the fork with CMF and ETF: 5.3k reports in ~8 s, then 0.1 s; one thread — in parallel tiger's scope deductions, and with them ~300 reports, vary between runs); our rules `gui-type-ignored` (281 on the fork), `replace-fields`, `loc-dead`, `text-fit` (113), `braces`, `bom`, project `[[rule]]`s; known reports in the mod's root — `v3-lint-baseline.json` (`--baseline`, matched by the text of the line, not its number) and `[[suppress]]` with a reason in `v3-lint.toml`; output by file and line, `--file`, `--key`, `--severity`, `--json`. The plugin's PostToolUse hook (`v3 hook post-tool-use`) runs the per-file rules on an edited mod file (no tiger, ~1 s) and hands new reports to the agent. Loading the dependencies did not cut tiger's `missing-item` (2728): they are the fork's own — 1626 in `ld_listing_switch.txt` (other mods' buildings), the rest loc pointing at script values that do not exist | PC (tiger reads vanilla); from the cloud — through the bridge |
| 5 | **CWTools trial** | after stage 4: if tiger and the index covered checks and search — not needed; otherwise run the CWTools server outside VS Code on the PC, count the false reports, on success — LSP in the plugin **Skipped 2026-10-16 (user's decision):** covered by stages 2 and 4 — `v3 def` / `refs` navigate across the playset with who wins, tiger in `v3 lint` checks scopes and references; CWTools would add completion in an editor, which agents do not use. Back to it if the user wants it in VS Code, or if tiger's share of false reports (not measured) turns out high | PC |
| 6 | **Bridge v2** | the cloud agent calls any `v3` command on the PC (instead of six script names); a "test bench" mode: the game in debug mode on a save, the GUI file re-read on the fly (to be checked), a snapshot of a screen area; comparing two snapshots **Done 2026-10-16:** the bridge (`vic3_mods/tools/pc_bridge/server.py`) has a tool `v3(args)` — any read-only `v3` command on the PC (`vic3tools/bridge.py`: `gui set` only `--dry`, no `lint --baseline` / `setup`), the fork read from the worktree of the pushed branch; checked through a local copy of the server. The test bench `v3 bench start / do / shot / diff / stop`: the game left open in the sandbox VM (`-KeepOpen`), each step sends the mod files changed since and takes `vic3_ui.ps1` steps in the guest's session (`Invoke-SandboxRun.ps1 -WithGame`); **the game in debug mode re-reads a changed `.gui` on the fly** — checked: the probe window's title changed without a restart; one "edit → shot" ~34 s; shots cut by `--crop`, `diff` gives the changed share and area and a side-by-side (Pillow, `vic3tools[img]`). The run scripts stay the project's (`[bench] scripts`) | PC |
| 7 | **Skills and knowledge** | `vic3-gui` in the spirit of Impeccable: `init` writes a style file of the Vic3 interface from vanilla, passes `audit` / `polish` / `critique` with checklists; a common `vic3-sandbox`; `vic3-modding` from "Правила работы с модами Victoria 3.md" (a skill + references by topic; the checkable facts already went to `lint` at stage 4); `vic3-compat` from "Правила — сборка.md"; common git rules into the plugin **Done 2026-10-16:** five skills in the plugin (0.6.0): `vic3-modding` (from "Правила работы с модами Victoria 3.md": the core in `SKILL.md`, seven references by topic — load and override, script, economy content, GUI with the probe's results, frameworks, diagnostics, what not to do), `vic3-compat` (from "Правила — сборка.md" and the analysis procedures: whether a patch is needed, three-way merges field by field, replacement patches, add-ons, megapacks, optional dependencies, generators), `vic3-gui` (`init` writes a style file from `v3 gui style` — vanilla counted: types, templates, formats with colours, sizes, spacing, textures — then audit / critique / polish with checklists and anti-patterns), a common `vic3-sandbox` (the VM, the bench, reading crashes and logs; the project's skill keeps its run script and its mod's logs), `vic3-repo-rules` (git, safe writes of game files, writing results). In English; the Russian originals in `vic3_mods` deleted on 2026-10-16 (user's decision), its README maps their old sections to the references | cloud |
| 8 | **Saves and logs** | parse a save once into the cache, the `save_*` / `scan_*` scripts become queries; common log parsers **Done 2026-10-16:** `v3 save` — a text save indexed once (brace scan, ~10 s for 240 MB, every block to depth 3 with its byte span, SQLite in the cache), then queried by pieces: `info`, `get`, `grep`, `vars`, `owners` (owner classes, gross additions, transfers between saves; matches the old `save_ownership.py` on the same save, which missed records with a blank line — 2 levels), `buildings`, `companies`, `goods`; `v3 log` — `summary`, `diff`, `sites` (with the script-line mapping), `speed` (equal to `ld_speed.py`). The bridge allows both | PC; from the cloud — through the bridge |
| 9 | **GUI render** | `.gui` → PNG without the game: layout (`flowcontainer`, `hbox`/`vbox`, `layoutpolicy`, anchors, `scrollarea`), `.dds`, frames and frame slicing, fonts, stubs in place of `[…]`; comparing with the game's snapshots through the bridge **Done 2026-10-16:** `v3 gui render` (`vic3tools/gui/render.py`): the resolved widget laid out — sizes in px / % / `@constants`, min / max, `autoresize`, anchors and offsets, `flowcontainer`, `hbox` / `vbox` with `expand` and expanding policies, `scrollarea` clipping, lists repeated from `item` — and painted with Pillow: `.dds` / `.png` of the set (all vanilla formats decode), 9-slice by `spriteborder`, frames, tint, alpha, mirror; text with the game's font files per language and glyph fallbacks, the colour of `default_format`, align, wrap, elide; `--compare` + `--crop` against a game shot. Checked on the stage-3 probe window: within a few pixels of the game. Not drawn: `modify_texture`, shaders, animations, text icons | PC (vanilla textures on the spot); from the cloud — through the bridge |
| 10 | **GUI rules for CWTools** (optional) | `.cwt` for widgets, generated from the corpus of vanilla `.gui`; give them to `cwtools-vic3-config` | cloud |
| 11 | **GUI render: scale and languages** | `v3 gui render --scale` (the game's `GUI.scale` of `pdx_settings.json`) and screens as presets (`fhd` 1920×1080, `qhd` 2560×1440); `v3 gui grid` — one widget in a languages × scales grid (russian / english by default), every text box that wraps, is cut or runs out of its parent marked; compared with game shots at two scales in the VM | PC (vanilla textures) |
| 12 | **Profiler and logs as text** | the script profiler window read by Windows OCR (en / ru built in): the bench pages through it, `v3 log profile` turns the shots into CSV (kind, file:line, incl / excl s, calls) and a report — top by own time, by mod file, two runs compared; `log summary` collapses a mod's log lines by their varying fields (country, date, numbers) | PC / VM |
| 13 | **Lint baseline triage** | `v3 lint --triage`: the baseline of a mod grouped by kind, file and missing name (e.g. 2728 `missing-item` of the fork: buildings and script values absent from the set); what is real goes to the project's plan, the noise to suppressions with a reason, the baseline shrinks | PC; from the cloud — through the bridge |

Stages 11–13 were added 2026-10-16 (user's decision) in place of stages 5 and 10 for now: the user's priority is a toolset convenient for the agent, and tiger with the `v3` index already covers what CWTools would add for it.

**Migration of `vic3_mods/tools` — done 2026-10-16** (after stages 8–9, user's decision). (1) `vic3tools.legacy`
(`vic3lib`, `ld_pdx`) and `vic3tools.core.merge3`: the generators of both projects import them from the package, the
old copies deleted; `--check` of all 60 generators gave the same output before and after. (2) The common scripts
became commands: `v3 audit holes / dups / vanilla / prestige / events / lawgroups`, `v3 gui names`, `v3 playsets
--content-load` (with the run script's grammar "<playset> without X + FOLDER"), `v3 save`, `v3 log`; 27 scripts
deleted, outputs compared with the old ones on the project's set. (3) The fork's analyses and generators (88 scripts,
`data/`, `ef48_report/`, the probes) moved to the fork's `tools/`. (4) The game scripts moved to `bridge/game` — what
a project adds is its `vic3_hooks.ps1` (the fork's: its log lines into `eflog.txt`, `event zz_ef_logs.1` after
loading, a gone country's heir, the `-Shots` screens, its points file); the PC bridge moved to `bridge/pc` with a
project's `bridge.toml` (repos, live mods, hooks, allowed scripts, extra roots); `ld_install_mod` / `ld_pc_git_pull`
became the bridge tools `install_mod` / `pull_repos`; the profiler view mod is `mods/profiler_view`. Checked: a
1-minute VM run through the new bridge with the fork's hooks (exit 0, `eflog.txt` gathered, the log event sent). Left
in `vic3_mods/tools`: the compatibility-patch generators, addon builds, `blocks.json`, the bridge client.

After each stage — a measurement on the six reference tasks T1–T6; moving scripts from `vic3_mods` only with a test and
`--help`, the old copy is deleted in the same commit.

## Rules for the tools

- A docstring and `--help` say what it does and how to call it, without history (stage numbers and dates are in git).
- Output by default is short and with a limit; long goes to a file, the screen gets the path and a summary.
- Nothing writes outside the given folders; every generator has `--check`.
- A one-off probe of a stage lives in the project, not in the tools repo; when it is over — to the archive.

## Runs sandbox

The goal (user, 15.10): the agent's game runs do not occupy the screen, mouse and keyboard; the sandbox may use the
whole power of the PC. The decision is a Hyper-V VM on the same PC.

- **Hardware:** Ryzen 7 7800X3D (8 cores / 16 threads), 64 GB, RTX 5070 + integrated Radeon, 788 GB free on `C:`.
- **Processor and memory:** the VM gets all 16 threads and up to ~40 GB (dynamic memory); the host and the VM share
  them — when the user loads the PC, the run is slower, and the other way round. Vic3's speed is bound by the
  processor; Hyper-V's losses are around 5–10 % (measure with `ld_speed.py`: a game month on the PC and in the VM).
- **Video card:** GPU-P (`Add-VMGpuPartitionAdapter`) — a share of the RTX 5070, the driver is copied from the host. On
  client Windows this is unofficial (Easy-GPU-PV does it); on the RTX 50 — to be checked. The fallback is a share of the
  integrated Radeon (weak, but it may be enough for an "AI for all" run on low settings). Passing the whole card
  through (DDA) is only for Windows Server.
- **The VM's screen:** the game needs a display — a virtual monitor inside the VM; for a human to watch — Parsec or the
  Hyper-V console.
- **Steam:** one account does not play in two places at once. Check launching Vic3 in the VM with Steam in offline mode
  — then the user can play on the host during a run.
- **Design:** the bridge (`vic3-pc` → bridge v2) works **inside the VM**: launching the game, logs, saves, screenshots
  of the window; the agent on the host talks to it over Hyper-V's internal network. The mod in the VM is synced from the
  host (a shared folder or the bridge's `sync_mod`). The Workshop is pulled in by itself by the account's
  subscriptions.
- **After each update of the NVIDIA driver on the host** — copy the driver into the VM again (a script).

Steps. The user (administrator rights, once): check `Get-VMHostPartitionableGpu`, enable Hyper-V and reboot, a Windows
11 image, install Windows in the VM, sign in to Steam and install the game in the VM. The agent: scripts for creating
the VM and copying the driver, the bridge in the VM, the skill `vic3-sandbox` — a run in the VM, measuring the speed.

Order: after stage 0 (does not interfere with the other stages), before stage 6.

**Done 2026-10-15** (evening, local session). The design came out simpler than planned: the bridge stays **on the PC**,
in the VM there is only Windows, Steam and the game (no Python, git or tokens). A run in the VM is
`vic3_tools/bridge/vm/Invoke-SandboxRun.ps1`: it copies into the VM the run scripts, the playset's mods (only changed
files) and the PC's game settings, starts the run on the VM's desktop (a scheduler task), returns `runs/<id>` and new
saves (`runs/<id>/saves`). The bridge is `start.ps1 -Vm`. The Workshop is not needed in the VM: Steam there is always
offline, mods come from the PC.

- Setting up the VM is `Initialize-SandboxGuest.ps1`: auto sign-in (with "sign-in without a password" turned off —
  otherwise Windows erases the auto sign-in at boot), the screen 2560×1440 (`Set-VMVideo`; without a viewer window it
  would be 1024×768), no sleep, Steam offline without a question, Defender exclusions (checked: the game loaded to the
  menu in minutes without them, ~20 s with them, as on the PC).
- Reboot the VM only from inside (`Restart-Computer`): `Restart-VM -Force` is a hard reset, registry edits are lost.
- The game's settings from the PC are copied entirely before each run (the interface scale — the script's clicks were
  measured on the PC; the language; autosaves once per half-year; render — Vulkan through GPU-P works, RTX 5070).
- Playing on the PC and running in the VM under one Steam account at the same time is impossible — the user does not
  need it (15.10).
- Checked: a new game with the playset "Ledgerdemain" through the bridge (`checkout` → `start_run` → `run_status`),
  exit 0.
- **Speed:** the first quarters of 1836 — 16.4–17.4 s per game month in the VM against 13.8–14.4 on the PC, **~20 %
  slower** (5–10 % was expected). Vulkan instead of DX11 — no difference (17.0–19.1 s, within the spread); the PC's
  power plan is "maximum performance" (user, 15.10). Open: an honest measurement — identical 5-year runs in the VM and
  on the PC with the PC idle.
- Open: the skill `vic3-sandbox` — a section on the VM; `vic3_ui.ps1` (snapshots after a run, `-KeepOpen`) is not
  carried over to the VM.

## Questions to the user

Closed on 15.10 — decisions 8–14 at the start of the plan.
