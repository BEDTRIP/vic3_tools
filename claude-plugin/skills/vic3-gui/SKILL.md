---
name: vic3-gui
description: Design, build and review Victoria 3 interface (.gui) so it looks like the game's own and works in all 11 languages — a style file from vanilla (init), then separate passes audit (does it work), critique (does it look like Vic3), polish (make it consistent), each with a checklist, plus the anti-patterns that crash or silently break windows. Use whenever a mod adds or changes a window, panel, tooltip, journal widget, header, list or button, when text is cut or wraps, when a widget does not show, or the user asks to review or polish a mod's interface.
---

# Victoria 3 interface

The method of Impeccable, the content of Vic3: one **style file** describing how the game's own interface looks, then
**separate passes** with checklists, each run on its own. Answer in the user's language.

Tools: `v3 gui resolve FILE:LINE` (what a widget really gets after types / templates / blocks), `v3 gui types|templates
|textures Q` (what to reuse), `v3 gui fit FILE:LINE` (text width in 11 languages), `v3 gui set` (edit a property),
`v3 lint --file F` (tiger + rules), `v3 gui render FILE:LINE` (a PNG without the game, ~2 s — an approximation),
`v3 bench` (see it in the game, ~30 s per look). Engine facts: `vic3-modding`,
`references/gui.md`.

## init — the style file (once per project)

1. `v3 gui style --out <project>/docs/vic3-gui-style.md` — vanilla counted: the types instantiated most (headers,
   buttons, list entries, dividers), templates (`fontsize_large`, `default_button`, `entry_bg_simple`…), text formats
   and their colours, font sizes, container spacing and margins, textures — each with an example `file:line`.
2. Read it and add on top, in the same file, **the project's decisions**: which header type for a window, for a section
   (`default_header`, `section_header_button`…); the list entry background; numbers' format (`|v`, `|+`, `#P` / `#N`);
   the standard widths of the project's panels; what is never done (see anti-patterns). Short — a page.
3. Every pass below reads this file first. If it is missing — run `init` before anything else.

## audit — does it work (technical)

Run on each changed `.gui` file; report by place (`file:line`), fix only what is asked.

- [ ] `v3 lint --file <file>` clean of new reports (tiger + `gui-type-ignored`, `text-fit`, `braces`, `bom`).
- [ ] A copied vanilla file still has **every widget name** of the current vanilla (and of each mod whose version was
      merged): a missing named widget is a crash.
- [ ] Every `type` the mod (re)defines **applies**: its file sorts before the owner's (`v3 winner gui TYPE`); no
      "already registered" for the mod's files in `gui.log` after a start.
- [ ] `blockoverride` names exist in the type chain (`v3 gui types TYPE` — blocks offered); remember the type's own
      override beats the instance's.
- [ ] `@constants` used in a file are defined **in that file**.
- [ ] Every text fits in all 11 languages: `v3 gui fit FILE:LINE` for each label with a fixed width; a label that may
      grow — `multiline` with a `maximumsize` and a height that allows two lines, or `elide` + a tooltip with the full
      text.
- [ ] Data bindings (`[…]`) resolve: no new `error.log` lines after opening the window (`v3 bench` + logs).
- [ ] A window that should show actually shows: it is a child of a vanilla window, `ingame_hud`, a CMF hook or a journal
      widget — a free-standing top-level widget is not drawn.

## critique — does it look like Vic3 (design)

Compare with the style file and with a vanilla window of the same role (open both in `v3 bench`, `diff` the shots).
Answer each with "matches / differs: how / why it matters".

- Hierarchy: one window header, section headers of the vanilla kind, values right-aligned and formatted like vanilla.
- Reuse: vanilla types and templates for headers, buttons, entries, dividers, tooltips — not hand-built look-alikes.
- Typography: sizes from vanilla's template ladder — `fontsize_xsmall` 10, `fontsize_small` 12 and `fontsize_medium`
  14 (these two switch to the tooltip font, OpenSans), the textbox default 17 (EBGaramond), `fontsize_large` 20,
  `fontsize_xl` 22, `fontsize_xxl` 26, `fontsize_mega` 30 (`gui/shared/defaults.gui`); formats from `textformatting.gui` (`#title`, `#v`, `#low`, `#P` / `#N`) — no literal colours where a format
  exists.
- Spacing: container `spacing` / `margin` from the common values in the style file; edges aligned with the window's.
- Density: no wall of numbers — group, use headers, move detail into tooltips (vanilla puts breakdowns in tooltips).
- Language: labels are loc keys, short enough for German and Russian; no English in `raw_text` the player sees.
- The player's question first: what is this window for, and is the answer readable in two seconds?

## polish — make it consistent

Small, safe edits after `audit` and `critique`, each checked in the bench:

- Replace literal fonts, sizes and colours with the vanilla templates and formats they imitate.
- Align spacing and margins to the style file's values; equalize the widths of sibling blocks (`v3 gui set` with exact
  lines; keep the neighbours that must stay).
- Give every cut label a tooltip with the full text, or room for two lines.
- Remove dead widgets (`visible = no` forever, empty containers) and comment why a non-obvious widget exists.

## Anti-patterns (each broke something)

- A stale copy of a vanilla `.gui` — a crash when vanilla's code asks for a widget it lacks.
- Overriding a type from a file that sorts after the owner — silently ignored ("already registered").
- Fixed widths sized to English text — Russian / German labels cut or wrapped (the bond market label: 120 px in
  English, 166 px in Russian).
- A copy of `journal_entry.gui` to change one detail — it overrides CMF's panel for everyone; use CMF's hooks or a
  journal widget.
- `@constant` used in a file that does not define it — zero size, no error.
- A progress bar inside your own widget with a `ScriptedProgressBar` tooltip — an error each frame.
- A free-standing top-level widget expected on screen — not drawn.
- A section "open by default" by a variable named `x_open` — the variable system is empty at start, everything starts
  folded; name it `x_closed`.
- Literal colours and sizes copied from a screenshot instead of the formats and templates vanilla uses.
