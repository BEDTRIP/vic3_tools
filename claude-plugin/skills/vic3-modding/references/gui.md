# GUI (1.13)

Checked in the game with a probe window on 2026-10-15 unless dated otherwise. Work with
`v3 gui resolve / types / templates / fit / set` and the bench `v3 bench` (skill `vic3-gui`).

- **The engine finds widgets by name. A stale copy of a vanilla `.gui` missing a widget = a crash**, not a log line.
  Sign in a diff: "minus hundreds of lines, plus two or three". A merged file's widget names must be a **superset** of
  both mods' versions; a difference from vanilla alone is not evidence — what matters is whether either author removed
  the line.
- **A `type` defined in two files: not a crash, the FIRST wins** — files ordered by file name (bytes) across all mods,
  mod order ignored (`gui.log`, 2026-09-30: "Type 'budget_panel_financial_panel_content' already registered at
  'gui/00_ef_deported_gui_1.gui:141729'"). To override another mod's type your file name must sort **before** the
  owner's (`00_00_…`); check `gui.log` after a start for your file in "already registered". **Templates the same**
  ("Template '…' already registered at …").
- **`blockoverride`: the one closest to the block wins** — a type's own override beats the instance's; an instance's
  beats one handed down from an enclosing widget. An override reaches a `block` inside a nested type instance.
- **`@constants` belong to their file.** A constant defined in file A does not resolve in text written in file B (zero
  width, no error); a type defined in A that uses it works anywhere. Copy the constants with the blocks you copy.
- **Every `textbox` gets EBGaramond 17** from vanilla's `type textbox = textbox { using = regular_font }`; set `font`
  / `fontsize` (or `using = fontsize_large` = 20…) explicitly to differ. `fontsize_min` shrinks by whole pixels, then
  `elide` cuts.
- **A free-standing top-level widget of a mod's file is not drawn on screen** (hidden "hook" widgets with a `state`,
  CMF's `com_hidden_trigger` pattern, are reported to fire — not re-checked). To show your own window: a child of a
  vanilla window or of `ingame_hud`, a CMF hook, or a journal entry widget.
- **`.gui` can hide whole entities by name, invisible from `common/`.** E&F's `building_details_panel.gui` builds one
  `visible` from twelve `EqualTo_string(ProductionMethodGroup.GetKey,'pmg_X')` — the group is simply not drawn. If a
  widget is missing while the data is fine — look the entity's name up in `gui/` (`v3 refs NAME`).
- **A journal widget can be replaced without touching another mod's `.gui`:** in the journal entry `widget = { gui =
  "my file" name = "my widget" container = … }`, your file in `gui/scripted_widgets/`.
- **The pinned journal shows only the entry's progress bars** (`scripted_progress_bar`), not widgets. Order in the
  entry panel (`gui/journal_entry.gui`): status description → `custom_widget_container_2` → journal buttons →
  `custom_widget_container_3` → bars → `custom_widget_container_4` → `reason`. A bar inside your own widget has no
  `ScriptedProgressBar` context (its tooltip is an `error.log` line each frame). To hide the entry's bars in the panel
  but keep them pinned — CMF's hook (`com_custom_widget_container_scripted_progress_bars`), not a copy of
  `journal_entry.gui` (that copy overrides CMF's panel and silently drops its icons and styled bars for everyone).
- **A section open by default:** `GetVariableSystem` is empty at each start, so name the variable "closed":
  `visible = "[Not(GetVariableSystem.Exists('x_closed'))]"` and the button toggles `x_closed` (E&F does the reverse:
  everything starts folded).
- **Colours in text:** `#N` red (bad), `#P` green; number format `|+` sign and colour (plus green), `|-` the reverse.
  Different text by sign — different textboxes with `visible`.
- The game in `-debug_mode` re-reads a changed `.gui` on the fly — no restart needed to see an edit (`v3 bench`).
