# Stage 3 — GUI: hand-off

The plan's row ([`plan.md`](plan.md), stage 3): `v3 gui resolve` (a widget with `using` / `blockoverride`
substituted), a reference of vanilla types, templates and textures with samples, `v3 gui set <file> <path> prop=…`,
and a check whether a text fits its width in all 11 languages. PC only (the game files are read in place).

Written 2026-10-15 at the start of the stage, for the session that does it. Delete this file (or fold what is still
true into `usage.md`) when the stage is done.

## What already exists

- **`vic3tools/gui/tree.py`** (tested, `tests/test_gui_tree.py`) — the parser of `.gui` files: `GNode(head, op, value,
  children, line, end_line, start, end, open, file)`. It knows `type x = base { }`, `template x { }`,
  `block "x" { }`, `blockoverride "x" { }`, `types X { }`, typed values (`color = hsv { }`), list values
  (`size = { 100% 40 }` → `is_list`, `scalar()` gives `{ 100% 40 }`), bare words. Helpers: `parse_file` (cached by
  mtime), `walk`, `node_at(nodes, line)` (the chain of blocks around a line), `find_def(nodes, "type"|"template",
  name)`, `GNode.props(key)`, `GNode.label()` (`name`, else `text` / `raw_text` / `datacontext`).
  `core/script.parse` is **not** for `.gui`: it does not understand `type a = b {` or `template a {`.
- **The index** (`vic3tools/index/db.py`) already has `gui_type` and `gui_template` definitions with line ranges for
  every mod of the set: `SetIndex.defs(name)` in `index/query.py`. References of a type or template name (where it
  is instantiated, `using = …`) — `SetIndex.refs(name)`.
- **Who wins** — `compat/winner.gui_type`: the first registration, files ordered by file name across all mods, mod
  order not counted, the file closer to `gui/` root first among equal names. Use the same order for templates (see the
  open questions).
- `v3 outline` (`index/query.outline`) is a generic tree for any script file; for GUI work prefer `gui/tree.py`.
- The plugin (`claude-plugin/`): skill `vic3-search` and the hook. Add the new GUI commands to the skill's table
  when they exist.

## Engine facts gathered (1.13.11)

- `type NAME = BASE { body }` inside `types GROUP { }`; BASE is a native widget (`window`, `widget`, `flowcontainer`,
  `textbox`, `icon`, `button`, `hbox`/`vbox`…) or another type. An instance is `NAME = { … }` anywhere.
- `template NAME { props }`; `using = NAME` pastes the template's props in place (templates use templates).
- `block "x" { default }` inside a type's body is a hole; an instance (or a derived type) fills it with
  `blockoverride "x" { … }`. Holes sit at any depth of the body — e.g. `default_header` (`gui/shared/backgrounds.gui`
  233–270) has `block "text"`, `"text_mod"`, `"margin"`, `"text_size"`, `"align"` inside
  `block "textbox"` › `flowcontainer` › `textbox`.
- Text formats (`default_format = "#title"`) are in `gui/textformatting.gui` (55 `format = { name … format … }`);
  `title` is `"grey;shadow"` — colour and shadow, **no size or font**.
- Fonts: `game/fonts/fonts.font` — `fontfiles = { name group = { languages = {…} files = {…} } }` (per-language
  groups; the first file has the glyphs, the rest are fallbacks) and `font = { name fontstyle = { style fontfiles } }`
  aliases: `standard_font` → `Game-OpenSans-Regular`; `OpenSans` (regular/bold/italic); `EBGaramond`;
  `PlayfairDisplay`; `Fancy` → `ParadoxVictorian`. Font files are in `game/fonts/` and `clausewitz/fonts/`
  (`Open_Sans`, `NotoSans`, `Roboto_Mono`, also `cw_fonts.font` there). In vanilla `.gui`: `font = "standard_font"`
  47 times, `StandardGameFont` 7, `tools_font` 4. Templates in `gui/shared/defaults.gui`: `regular_font`
  (EBGaramond 17), `tooltip_font` (OpenSans 15), `fontsize_large` 20, `fontsize_xl` 22, `fontsize_medium` 14 + tooltip
  font….
- `elide_fontsize_min` (`gui/shared/buttons.gui` 892) = `elide = right` + `fontsize_min = 14`: a long text shrinks
  to 14, then is cut with "…".
- `@name = value` constants are defined at the top of `.gui` files (file-local; `@panel_width_plus_14` comes from
  several files).

## Design

### `v3 gui resolve FILE:LINE` (also `--type NAME`, `--prop KEY[,KEY]`, `--depth N`)

Take the widget instance around LINE (`node_at`, the innermost block that is not a property), expand it, print the
result with where every property came from.

Expansion of an instance `K = { body }`:

1. If K is a GUI type (winner by the rule above), build the chain K → its base → … until a native widget:
   bodies `[innermost base body, …, K's body, the instance's body]`.
2. Overrides: walk the bodies outermost first; a `blockoverride "x"` is taken if "x" is not yet taken; the overrides
   handed down from above are taken first (assumption: the outermost wins, see open questions).
3. Children, bodies innermost first: `blockoverride` — dropped (consumed); `block "x"` — the override's children if
   there is one, else its own; `using = T` — T's props inlined (recursively); a property — kept; a child widget —
   expanded the same way, the overrides passed down.
4. Each output line keeps its origin: `file:line` of the property and the path of how it got there
   (`via using fontsize_large ← block "text_size" of type default_header`). A key repeated later overrides the
   earlier one — mark the loser.

Expected for T5 of the benchmark (`gui/ld_cb_rate_panel.gui:31`, `--prop fontsize,fontsize_min,elide`):

```
default_header › block "textbox" › flowcontainer › textbox
  fontsize = 20      # vanilla gui/shared/defaults.gui:15  via using fontsize_large ← block "text_size" (backgrounds.gui:258)
  fontsize_min = 14  # vanilla gui/shared/buttons.gui:894  via using elide_fontsize_min (backgrounds.gui:244)
  elide = right      # vanilla gui/shared/buttons.gui:893  via using elide_fontsize_min (backgrounds.gui:244)
```

### Reference: `v3 gui types QUERY`, `v3 gui templates QUERY`, `v3 gui textures QUERY`

- types / templates whose name contains QUERY: definition `mod: file:line-end`, base (types), the blocks a type
  offers (`block "…"` names — what an instance can override), how many places use it (refs) and one example
  instance `file:line`;
- textures: `.dds` (and `.png`) files under `gfx/` of the set whose path contains QUERY, with width × height from the
  DDS header (bytes 12–19: height, width, little-endian) and the mod that wins the path.

### `v3 gui set FILE:LINE KEY=VALUE [KEY=VALUE…] [--find TEXT] [--dry]`

The widget around LINE (or the single node whose key or label contains TEXT): replace `KEY = …` at its own level
(not in nested blocks), or insert it before the closing `}` with the block's indentation. Byte-faithful write
(`core/script.read` / `write` keep BOM and line ends). Print `file:line  was → becomes`. For T2: the textbox at
`ld_cb_rate_panel.gui:467` and the flowcontainer at 463 — `minimumsize="{ 130 40 }"` etc.

### `v3 gui fit FILE:LINE`

For a textbox: resolve it (`font`, `fontsize`, `fontsize_min`, `elide`, `multiline`, `size` / `minimumsize` /
`maximumsize`, `margin`), take its `text` key, read the text in all 11 languages (loc definitions of every language
are in the index; `loc_text` keeps only en/ru — read the line from the file for the rest), measure, and say per
language: fits / shrinks to N px / elided / wraps into N lines.

- Measure without new dependencies: a small sfnt reader (`cmap` formats 4 and 12, `hmtx`, `head.unitsPerEm`) — width
  = Σ advance × fontsize / unitsPerEm; a glyph missing in the first file is taken from the next file of the
  language's group in `fonts.font`. Kerning ignored (say so in the output).
- Placeholders `[…]` and `$…$` — a fixed sample length (say 8 characters of "0"), formatting `#x … #!` and icons
  `@x!` removed (`index/query._plain` does that).
- A width in `%` depends on the parent — report "relative to the parent" unless the parent chain gives a number.

## Open questions — verify, do not guess

- Do outer `blockoverride`s beat inner ones, and do they reach blocks inside nested type instances? (Assumed yes;
  check on a case in vanilla where both exist, or in the game.)
- Templates defined twice: first or last wins? (Assumed as for types; `gui.log` may name duplicates.)
- The font of a textbox with no `font` — `standard_font`? (Check a plain vanilla textbox in the game.)
- `@constants` — which file's value applies when a type defined in file A is used in file B?
- How the game checks a run is the sandbox's job (`vic3_mods` skill `vic3-sandbox`, Hyper-V VM); a screenshot of the
  financial centre window answers the font and elide questions at once.

## Done when

- T5 is answered by one `v3 gui resolve … --prop …` call; T2's edit is made by `v3 gui set` with the exact lines
  (and `--dry` shows it); `v3 gui fit` on the T2 label shows the wrap at 100 and none at 130.
- Tests on small fixtures (`tests/`), `ruff`, `pytest`, `v3 docs check-ru` green; `docs/usage.md` and
  `docs/ru/usage.md` describe the commands (restamp the hash in the Russian file's first line); the plan's stage-3 row
  says done with the commit; the skill `vic3-search` lists the new commands.

## Practical notes for this repo

- Code, names, comments, `--help`, docs and commits in English; command output through `vic3tools/i18n` (en + ru);
  line length 120; Python 3.11 compatible (CI runs 3.11 — no backslashes or reused quotes inside f-strings).
- Write Python with the Write / Edit tools, not with `python - <<'EOF'` heredocs that contain `"\n"` or regex
  escapes: the shell eats them (several broken files this way so far).
- Commit straight to `main` with explicit paths, push after each commit (`vic3_mods/CLAUDE.md`, git rules).
- `vic3_mods` and the fork use the package (`ld_pdx.py`, `vic3lib.py` wrap `core/script.py`): changing
  `core/script.py` needs `--check` of all their generators before and after (see stage 1 in the plan).
