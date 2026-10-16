# Using `v3`

`v3` is one command for all the tools. Every subcommand has `--help`; output is short by default and `--json`
gives the same data for other programs. `--lang en|ru` picks the language of the output (default: `lang` in the
config, then the system language).

## Where things are read from

Nothing from the game is stored in this repo or copied anywhere: the tools read three roots in place.

| root | what is there | how it is found |
| --- | --- | --- |
| `game` | the game install: `game/` (script, GUI, localization, textures), `launcher/`, `binaries/` | Steam: the library from `libraryfolders.vdf` that has Victoria 3 |
| `workshop` | `steamapps/workshop/content/529340/<id>/` — Workshop mods as they are | the same Steam library |
| `documents` | `Documents/Paradox Interactive/Victoria 3`: logs, saves, local mods, the launcher's playsets | the Windows Documents folder (wherever it was moved, OneDrive included) |

The roots are found by themselves. To correct one, set it in a config file:

```toml
# vic3tools.toml
lang = "ru"

[roots]
game = 'D:\SteamLibrary\steamapps\common\Victoria 3'
```

Two config files are read, the later wins: the user one in the tools' home (`%LOCALAPPDATA%\vic3tools\vic3tools.toml`,
written by `v3 setup`), then the nearest `vic3tools.toml` from the current folder up (a project's own). `V3_HOME`
moves the tools' home elsewhere.

The tools' home also holds the cache (`cache/`) and installed programs (`bin/`, e.g. tiger).

## Commands

| command | what it does |
| --- | --- |
| `v3 where` | the roots in effect and where each came from, the game version, the config files, the cache |
| `v3 setup` | once per machine: find the roots, write the user config, build the cache (the glossary for now), check tiger |
| `v3 doctor` | what is ready and what is not; exit code 1 if something is missing |
| `v3 glossary <text>` | the game's own name for a term in English and Russian (`--all-langs` — all eleven), from the game's localization; also the tools' own terms |
| `v3 docs check-ru` | in this repo: are the Russian translations in `docs/ru/` current |
| `v3 hook pre-tool-use` | the Claude Code hook of the plugin (`claude-plugin/`): a grep for a name, or a read of a whole big file, in game or mod folders gets the index's answer instead, once per session |
| `v3 hook post-tool-use` | the plugin's hook after an edit: an edited `.gui` / `.txt` / `.yml` of a playset mod gets `v3 lint`'s fast rules (braces, BOM, project rules, GUI types that never apply, text width around the edited lines); new reports go to the agent as context |
| `v3 lint [MOD]` | check a mod (default: the last of the set): vic3-tiger with the mods before it loaded as dependencies, plus our rules; known reports left out (baseline, suppressions); by file and line. `--file F` — one file, `--no-tiger` — our rules only (about a second), `--key`, `--severity`, `--all`, `--baseline` — accept every current report as known |
| `v3 bench start / do / shot / diff / stop` | the test bench: the game open in the sandbox VM; `shot NAME --crop x0,y0,x1,y1` sends the mod files changed since (the game in debug mode re-reads them) and takes a screenshot; `diff A B` — what changed; `do "<vic3_ui steps>"` — clicks, hovers, console |
| `v3 save info / list / get / grep / vars / owners / buildings / companies / goods SAVE` | questions to a text save: indexed once (~10 s for 240 MB) into the cache, then read by pieces — a section or an entry, a country's variables and maps as numbers, who owns the production levels by owner class (with two saves: the gross additions and the transfers), buildings of a type, what companies own, a goods' flows |
| `v3 log summary / diff / sites / speed` | the game's logs (or a run's folder with `dbgparts/` / `errparts/`): families of records, two runs compared, error records by the mod file and line (`--mod` maps a script effect's line to the file's), real seconds per game month |
| `v3 def <name>…` | where a name is defined — records (with their line range), GUI types and templates, loc keys — and which definition wins |
| `v3 refs <name>` | where a name is used: `file:line`, the record it sits in, the keys above it (`set_variable>name`), whether it writes; files the game never reads (`_archive/`, replaced by path) listed apart; a glob (`prefix_*`) sums up every matching name |
| `v3 loc <KEY>` | the text of a loc key in English and Russian, every definition and which one shows; `v3 loc --text "…"` — the key behind a text as the player sees it (placeholders filled) |
| `v3 outline <file>` | the tree of records / GUI widgets of a file with line ranges and names (a widget's `name`, else its `text`); `--find X` — nodes whose key or name contains X, with the path to them; `--at LINE` — the nodes around a line. Read this before opening a big file |
| `v3 gui resolve FILE:LINE` | the widget around a line as the game builds it — its type chain, `using` templates, `block` / `blockoverride` substituted — every property with `file:line` and how it got there; `--prop fontsize,elide` — only those, with the widgets above them; `--type NAME` — a type by name |
| `v3 gui types Q`, `v3 gui templates Q` | the reference: types / templates whose name contains Q — definition, base, the blocks a type offers to override, how many uses, one example (vanilla first) |
| `v3 gui textures Q` | `.dds` / `.png` files under `gfx/` whose path contains Q, with width × height and the mod whose copy loads |
| `v3 gui set FILE:LINE KEY=VALUE…` | set properties of the widget around a line: replace at its own level or insert before its `}`; `--find TEXT` picks the widget by key or name, `--dry` shows the change only |
| `v3 gui fit FILE:LINE` | does the text of a textbox fit its width in all 11 languages: fits, wraps into N lines, shrinks to fontsize N, is cut; `--width N` — what if it were N wide |
| `v3 gui render FILE:LINE` | draw the widget to PNG without the game — resolved as by `resolve`, laid out (sizes, anchors, flowcontainer, hbox / vbox, lists), painted with the game's textures (9-slice, frames, tint) and fonts (`--lang`); `--boxes` outlines the boxes, `--compare SHOT --crop …` puts a game shot next to it. An approximation: check with `v3 bench` |
| `v3 gui style` | the look of vanilla's interface counted from its `.gui`: the types and templates used most, text formats with their colours, font sizes, container spacing and margins, textures — each with an example `file:line` (`--out FILE`; the base of a project's GUI style file, skill `vic3-gui`) |
| `v3 playsets` | the launcher's playsets, the active one marked |
| `v3 mods` | the mods of a set, in load order |
| `v3 winner <folder> <key>…` | every definition of a record in load order, what each does (creates, replaces, merges, is ignored, is lost) and which one the game uses; `v3 winner loc <key> --lang russian`, `v3 winner gui <type>` — the same for a localization key and a GUI type |
| `v3 conflicts <A> <B>` | what two mods (or two groups, `--groups`) both define: record keys by folder, file paths, localization keys, GUI types, event ids — with `file:line` on both sides |
| `v3 matrix` | the same counted for every pair of mods of the set (or of groups, `--groups`) |
| `v3 audit replace <mod>` | the mod's `REPLACE:` bodies that omit fields of the record they replace (all of them are lost); `--declared` — deliberate omissions |
| `v3 audit stale <mod>` | the mod's full bodies that lack fields vanilla has — usually copied from an older game version |
| `v3 audit loc-dead <mod>` | the mod's localization keys that never show: defined earlier under another path (move them to `replace/`) |

### The mod set and who wins

The commands about mods work on a set: vanilla first, then the mods in load order. By default it is the launcher's
active playset (read-only from `launcher-v2.sqlite`); `--playset NAME` picks another, `--mods DIR…` gives the
folders, `--set FILE` reads a set file:

```json
{"load_order": ["../mods_out/.vanilla", "../mods_out/CMF", "my_mod"], "labels": {"my_mod": "Mine"}}
```

Paths are relative to the file; a copy of vanilla (it has `checksum_manifest.txt`) may come first, else the installed
game is put in front. `[mod_paths]` in `vic3tools.toml` maps a playset mod's name to another folder (say, your git
checkout instead of the copy in `mod/`). For `matrix` and `conflicts`, `--groups FILE` adds groups of mods:
`{"blocks": {"Group": ["mod1", "mod2"]}, "order": ["Group", …]}`.

The rules `v3 winner` applies, as observed in the game (1.13):

- **mod order rules; file names decide only inside one mod** (by bytes: `_` before letters, capitals before lower
  case, `~` last);
- a file with **the same relative path** replaces the earlier mod's file whole;
- **records**: a later bare definition replaces the record and every `INJECT:` before it; `REPLACE:` replaces it whole;
  `INJECT:` merges into it; `TRY_` variants skip a missing record, `_OR_CREATE` ones create it. In `scripted_effects`,
  `scripted_triggers` and `script_values` a bare repeat does **not** override — the first definition stays;
- **localization**: the first definition of a key wins; one in a `replace/` folder overrides the rest;
- **GUI types**: the first registration wins, files ordered by file name across all mods (mod order does not count),
  the file closer to the root of `gui/` first among equal names. A losing type is reported in `gui.log` as
  "already registered".

Each mod is indexed once into the cache (`cache/index/`); later calls read again only the files that changed (vanilla
from scratch ~7 s, after that ~2 s).

### The index

`v3 def`, `refs`, `loc` and the compatibility commands read one SQLite database per mod in the cache
(`cache/index/`), built by `v3 setup` for the active playset or on first use, and refreshed by changed files on every
call (vanilla: ~40 s once, then ~1 s). It holds:

- **definitions** — top-level records of `.txt` files, GUI `type`s and `template`s, loc keys of every language;
- **references** — every identifier outside comments in script and GUI files (also inside strings, so
  `[GetVariable('x')]` counts) and the `[…]` / `$…$` parts of English loc, each with the record it sits in and the
  keys above it. Plain lowercase words without `_` (`yes`, `limit`, `wood`) are left out; `v3 refs` reads the files
  for those;
- **loc texts** in English and Russian.

Only the folders the game reads count as loaded (`common/`, `events/`, `gui/`, `localization/`, `map_data/`,
`gfx/`…); anything else in a mod folder (documents, `_archive/`) is indexed but marked "never loads".

### GUI

`v3 gui` reads `.gui` files with their own parser (`type x = base {`, `template`, `block` / `blockoverride`, typed
values like `color = hsv { … }`) and finds types and templates through the index. FILE is a path, or a path inside
the set (`gui/my_panel.gui:120` — the copy that loads).

```
> v3 gui resolve gui/ld_cb_rate_panel.gui:31 --prop fontsize,fontsize_min
default_header  [default_header_properties › widget]  E&F: Ledgerdemain: gui/ld_cb_rate_panel.gui:31
default_header › flowcontainer › textbox
  fontsize = 17  # vanilla: gui/shared/defaults.gui:4  via using regular_font (defaults.gui:116) ← type textbox …  (overridden by defaults.gui:15)
  fontsize_min = 14  # vanilla: gui/shared/buttons.gui:894  via using elide_fontsize_min (backgrounds.gui:244) ← …
  fontsize = 20  # vanilla: gui/shared/defaults.gui:15  via using fontsize_large (backgrounds.gui:259) ← block "text_size" (backgrounds.gui:258) ← …
```

How a widget is resolved:

- an instance `K = { … }` of a type `K`: the bodies of the chain `K → base → …` down to a native widget, innermost
  base first, then the instance's own body; a property repeated later wins (the loser is marked "overridden by");
  actions (`onclick`, `state`…) may repeat;
- `blockoverride "x"`: the one closest to the block wins — the type chain from the base outwards, then the
  instance's, then one handed down from an enclosing widget — and it reaches `block "x"` of nested widgets too;
- `using = T` pastes the template's properties (templates use templates);
- a type or template defined more than once: the first, files ordered by file name across mods (as `v3 winner gui`);
- `@name` constants belong to the file that defines them; they are shown with their value.

`v3 gui fit` measures with the game's own fonts: `fonts/*.font` of the game, the engine (`clausewitz/fonts`) and the
mods give a family's files per language (the first has the glyphs, the rest are fallbacks); the width is the sum of
the glyphs' advances (kerning ignored). The text is the loc key of `text` in each language as the player sees it
(`$KEY$` and `[concept_x]` replaced by their text; other `[…]` count as `00000000`; formatting and icons left out),
or `raw_text`. The room is `max_width`, else `maximumsize`, else a fixed `size`, less `margin`; a `%` width is
relative to the parent and is not measured. Pointed at a widget that holds the textbox (a header), it measures the
first text inside.

Checked in the game (1.13.11, 2026-10-15) with a probe window — one row per question, put into `ingame_hud` by a
copy of `gui/ingame_hud.gui` (a free-standing top-level widget of a mod is not drawn on screen):

| question | in the game |
| --- | --- |
| a type's own `blockoverride` against the instance's | the type's wins (the closest to the block) |
| an override of a block inside a nested type instance | reaches it |
| a template defined in two files | the first by file name; `gui.log`: "Template '…' already registered at …" |
| a textbox with no `font` | EBGaramond — vanilla's `type textbox = textbox { using = regular_font }` applies to every textbox |
| `fontsize_min` shrink | to whole pixels: 24 in 150 px → 16, as measured |
| `@constant` from another file | does not resolve (zero width); a type that uses it in its own file works anywhere |
| text width | EBGaramond 15 "Bond Capitalization": 119 px in the game, 120 measured |
| wrap of a multiline label | as measured: English wraps at 100, fits 130; Russian wraps at 130, fits 180 |

Not checked: an override handed down from an enclosing widget against a nested type's own override of the same
block (taken as: the nested type's own wins, the closest one).

### Checks: `v3 lint`

`v3 lint` runs [vic3-tiger](https://github.com/amtep/tiger) (installed into the tools' `bin/`) over the mod with a
generated config: the mod's own `vic3-tiger.conf`, plus a `load_mod` for each mod before it in the set, so what CMF or
another dependency defines is not "missing". tiger's JSON is cached and rerun only when a file of those mods changes
(the fork with CMF and ETF: ~8 s, then ~0.1 s). tiger runs on one thread: in parallel it deduces the scope types
of variables in a different order and reports different lines from run to run. Only reports located in the mod
itself are kept.

Our rules on top (`--rules` picks them):

| rule | what it finds |
| --- | --- |
| `gui-type-ignored` | a GUI type of the mod that never applies: another file registers it first (files ordered by name across mods) |
| `replace-fields` | a `REPLACE:` body that omits fields of the record it replaces — they are lost |
| `loc-dead` | a loc key defined earlier under another path: it never shows (move it to `replace/`) |
| `text-fit` | a one-line textbox with a width of its own whose text is cut or overflows in a language of `--langs` |
| `braces` | `{` and `}` do not balance in a script / GUI file (the line where it breaks) |
| `bom` | a localization file without a BOM (not read), a `.txt` with non-ASCII text and no BOM (misread); for `.gui` a warning |
| `rule:<name>` | the project's own rules: `[[rule]]` in the mod's `v3-lint.toml` — `name`, `files` (globs), `pattern` (a regex), `message`, `severity` |

Known reports are kept in the mod's root, so every session and machine shares them:

- `v3-lint-baseline.json` — written by `v3 lint --baseline`: every current report accepted as known. A report is
  matched by source, key, file, message and the text of its line (not the line number), with a count — edits
  elsewhere do not bring it back, a new one of the same kind shows; scope reports (`scopes`, `strict-scopes`,
  `modifiers`) match by file and line text alone — their message names the scopes tiger guessed, which shifts when
  other files change;
- `[[suppress]]` in `v3-lint.toml` — by hand, with a reason: `key` and `file` (globs), `message` and `text`
  (substrings), `why`.

```toml
# v3-lint.toml
[[suppress]]
key = "missing-item"
file = "common/scripted_effects/ld_listing_switch.txt"
why = "buildings of other mods, checked with has_building_type at run time"

[[rule]]
name = "no-debug-log"
files = ["common/**", "events/**"]
pattern = "debug_log"
message = "debug output left in"
```

The plugin's hook after an edit runs the rules that need only that file (not tiger) and tells the agent about new
reports in the same turn.

### Drawing without the game: `v3 gui render`

```
v3 gui render gui/my_panel.gui:120 --lang russian --boxes
v3 gui render --type my_panel --compare shot.png --crop 0,0.15,0.4,0.8   # side by side with a game shot
```

Checked against the stage-3 probe window in the game: positions within a few pixels, font sizes, shrinking, wraps
and widths as in the game. Known gaps: `modify_texture` overlays, shaders and animations are not drawn (backgrounds
look flatter), text icons and inline formatting are dropped, `[…]` shows as `--stub`, a widget's own anchors are not
applied at the root.

### Test bench: `v3 bench`

The loop "edit a `.gui` → see it" without a run, in the sandbox VM (`bridge/vm`, see the plan's "Runs sandbox"):

```
v3 bench start                          # the playset's mods, a new game as SWI (or --save NAME), left paused
v3 bench shot before --crop 0,0.1,0.5,0.6
# … edit the .gui …
v3 bench shot after --crop 0,0.1,0.5,0.6   # the changed files go to the VM first; the game re-reads them
v3 bench diff before after              # "changed 3.06% of the pixels, in the area …" + a side-by-side image
v3 bench stop
```

Each step takes ~30 s (PowerShell Direct, a task in the guest's session). Shots and steps are in `<cache>/bench/`.
The game's run scripts (`run_vic3_sandbox.ps1`, `vic3_ui.ps1`) are the project's: `[bench] scripts = '<folder>'` in
`vic3tools.toml`; `[bench] vm` names another VM. Cutting and comparing need Pillow: `pip install vic3tools[img]`.
A free-standing top-level widget of a mod is not drawn on screen: to show a probe window, put it into `ingame_hud`
(a copy of `gui/ingame_hud.gui` with the widget as its last child).

### From a cloud session: the bridge

A cloud session has no game files; the PC bridge (`vic3_mods/tools/pc_bridge`, an MCP server over a tunnel) has a
tool `v3(args)` that runs a `v3` command on the PC and returns its output (`vic3tools/bridge.py`). Read-only commands
and the bench only: `gui set` only with `--dry`; `lint --baseline`, `setup`, `hook`, `docs` are refused — the cloud
edits its own clone and pushes. Shots of the bench are read with the bridge's `get_image('bench/<step>/<name>.png')`.

### Saves and logs

`v3 save` reads text saves (the game with `-debug_mode`, or `save_storage = text`; ironman and compressed binary saves
are refused). The first query scans the save's braces (~10 s for 240 MB) and keeps every block down to three levels
with its byte span in `<cache>/saves/`; later queries read only the bytes they need. A save is a path or a name in
the documents' `save games`.

```
v3 save owners autosave_4 autosave --class "bank=company_Bank*" --skip building_financial_centre
v3 save buildings autosave building_textile_mills
v3 save vars autosave GBR 'debt|money'
v3 save goods autosave --ids building_gold_mine      # the save's numeric goods ids
```

Owner classes: `gov` (the country), `company` (an HQ or regional HQ), `manor` (aristocrats), `findist`
(capitalists), `f_pop` / `f_comp` / `f_gov` (an owner from another country), `self`, `other`; `--class NAME=GLOB`
puts company types into a class of their own. Not production (left out): owner buildings, army, ports, urban
centres, government, subsistence buildings, and prefixes given with `--skip`.

`v3 log` reads `debug` / `warning` / `game` / `error` logs as records (a stamped line with its continuation lines);
a family is the message with numbers and quoted names folded. `--skip REGEX` leaves out a mod's own log lines.

### Glossary

Built by `v3 setup` for the installed game version (`cache/glossary-<version>.sqlite`): every localization key whose
English text is a short plain name (no `[...]`, `$...$`, line breaks; at most six words), with its text in each
language. A search matches the key or the text in any language, case-insensitively; game concepts (`concept_*`) come
first. Use it to name things the way the game names them, not with a translator's guess:

```
> v3 glossary институт --limit 2
concept_institution — en: Institution | ru: Институт
LAW_TYPE_TYPE_DESC_INSTITUTION — en: Institution | ru: Институт
```

## Translations of the documents

English is the original; `docs/ru/` mirrors the documents for people. Each translation starts with a mark of the
English version it was made from:

```
<!-- source: docs/usage.md @ 1a2b3c4d5e6f -->
```

The hash is git's blob hash of the English file (`git hash-object docs/usage.md`). `v3 docs check-ru` reports a
translation whose source has changed since, and documents with no translation yet (a note, not a failure). After
updating a translation, put the new hash in its first line.
