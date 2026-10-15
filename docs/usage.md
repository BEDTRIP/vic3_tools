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
| `v3 def <name>…` | where a name is defined — records (with their line range), GUI types and templates, loc keys — and which definition wins |
| `v3 refs <name>` | where a name is used: `file:line`, the record it sits in, the keys above it (`set_variable>name`), whether it writes; files the game never reads (`_archive/`, replaced by path) listed apart; a glob (`prefix_*`) sums up every matching name |
| `v3 loc <KEY>` | the text of a loc key in English and Russian, every definition and which one shows; `v3 loc --text "…"` — the key behind a text as the player sees it (placeholders filled) |
| `v3 outline <file>` | the tree of records / GUI widgets of a file with line ranges and names (a widget's `name`, else its `text`); `--find X` — nodes whose key or name contains X, with the path to them; `--at LINE` — the nodes around a line. Read this before opening a big file |
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
