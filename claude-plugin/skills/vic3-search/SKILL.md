---
name: vic3-search
description: Find things in Victoria 3 game and mod files with the `v3` index instead of grep and reading whole files, and resolve or edit GUI widgets. Use whenever a Vic3 modding question asks where something is defined, who uses or calls it, who writes a variable, which mod's definition wins, what text a localization key shows (or which key is behind a text seen in game), or what is inside a big .gui / .txt file — scripted effects and triggers, script values, variables, modifiers, buildings, laws, events, GUI types and templates, loc keys. Also when an error.log line names a variable or key, and for GUI work: what font size / size a widget ends up with, which type or template to reuse, changing a widget property, whether a text fits its width.
---

# Search Victoria 3 files with `v3`

`v3` answers from an index of vanilla and the mods of the active launcher playset, with `file:line`, the record a use
sits in and which definition the game actually takes. One call usually replaces several greps and reads. Answer the
user in their language.

| question | command |
| --- | --- |
| where is X defined, and which definition wins | `v3 def X` |
| who uses X — calls, reads, writes (variables: `set_variable`, `add_to_variable_list`…) | `v3 refs X` |
| many numbered names (`list_1` … `list_25`) | `v3 refs 'list_*'` |
| the whole chain of a record across mods: creates, replaces, merges, ignored | `v3 winner common/<folder> X` |
| which GUI type / loc key wins | `v3 winner gui X`, `v3 winner loc X --lang russian` |
| the text of a loc key, which version the player sees | `v3 loc KEY` |
| the key behind a text seen in the game | `v3 loc --text "text as shown"` |
| what is in a big file | `v3 outline FILE` then `--find NAME_OR_TEXT` or `--at LINE`; read only that line range |
| what a GUI widget really gets after types / `using` / `blockoverride` (font size, size, texture…) and from where | `v3 gui resolve FILE:LINE --prop fontsize,size` |
| GUI types, templates, textures to reuse: base, blocks to override, an example, texture size | `v3 gui types Q`, `v3 gui templates Q`, `v3 gui textures Q` |
| change a widget's property, or give the exact edit with its lines (no hand editing or line counting in a big `.gui`) | `v3 gui set FILE:LINE KEY=VALUE … --dry`, then without `--dry` |
| does a label fit its width in all 11 languages | `v3 gui fit FILE:LINE` (`--width N` to try a width) |
| check a mod or one file after changes: tiger + our rules, known reports left out | `v3 lint` (`--file F`, `--no-tiger` for a quick pass, `--key missing-item`) |

How to work:

- **Start with `v3`, not grep.** Use grep only for what `v3` does not cover: comments, documents, files outside the
  game's folders, free text.
- **Follow a chain with `refs`:** each reference shows the record it sits in (`in <record>`); run `v3 refs <record>`
  on that to go one level up, until an on_action, an event or a GUI is reached.
- **"Nobody writes it"** — `v3 refs` counts writes only in files the game loads; writes in `_archive/` or in a file
  replaced by a later mod are listed last, marked "never loads". That is often the answer.
- **Big file:** never read a `.gui` or long `.txt` whole. `v3 outline` gives the tree with line ranges; GUI widgets are
  named by their `name`, else their `text`.
- The set is the active playset; another one: `--playset NAME`, `--mods DIR…`, `--set FILE`. `--json` for exact data.
- `v3` needs the game files on this machine; in a cloud session without them it reports the game as not found — then
  fall back to grep.
