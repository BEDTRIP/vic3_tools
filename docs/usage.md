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
