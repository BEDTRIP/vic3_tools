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
- **A side panel's width is the instance's `size`** (2026-10-17, bench at 2560×1440). Vanilla side panels are
  `default_block_window` with the template `sidepanel_plus_sidebar_size` (`size = { 613 0 }`, ~25 % of the screen);
  `size = { 1226 0 }` in `type budget_panel = default_block_window { … }` opens the panel at ~48 %. Width is per window,
  not per tab. Vanilla content stretches only where it is laid out by the file's `@panel_width*` constants (double
  them too); content with fixed sizes stays a narrow centred column. The header (`block "window_header"` of
  `default_block_window`, `gui/block_windows.gui`) and `top_illu` take their width from constants of *their* files —
  override `window_header` at your width and give `top_illu` a `size`. The header does not widen well: its ornament
  `top_header_dec.dds` (1140×212, density 2) is pinned 280 px from each edge, so only a 10 px strip stretches and the
  pattern breaks; stretched whole it looks drawn out. For a wide window use the fullscreen header instead.
- **`fullscreen_top_header`** (`gui/shared/backgrounds.gui:54`, used by `fullscreen_block_window`) is vanilla's header for
  any width: frame `fullscreen_header_frame.dds` (2556 px, Corneredtiled, `spriteborder` 600 — a plain middle line that
  tiles), ornament `fullscreen_header_dec.dds` as a half (an end piece + a tiling oak pattern, `spriteborder_left` 600)
  drawn twice, the right half with `mirror = horizontal`, over `fullscreen_header_behind.dds`.
- **UI themes (2026-10-17).** `common/themes/00_themes.txt`, category `ui_skin_theme`, `ui_skin = "<name>"`; a skin is
  `gfx/skins/<name>.skin` (`name`, `folder = gfx/skins/<name>`) — a folder mirroring `gfx/interface/`: a file at the same
  relative path replaces the vanilla one while the theme is on. DLC skins: `votp` (dlc004), `ap1` (dlc007), `ip2`
  (dlc011), `ip3` (dlc014), `ip4` (dlc016), `ep2` (dlc018); each replaces every header layer (`top_header_*`,
  `fullscreen_header_*`, `header_color`, `header_borders`, `header_bg_dec`, `big_header_pattern`). A mod's own texture
  is not themed: a themed variant goes to `gfx/skins/<name>/…` of the mod (picked up from a mod — not checked yet).
- **Event pictures are videos (2026-10-17).** `event_image = { video = "<name>" }` plays `gfx/event_pictures/<name>.bk2`
  (Bink 2, 1700×1200, ~300 frames; DLC ones in `dlc/<dlc>/gfx/event_pictures/`); the 13 `.dds` there are character
  frames and masks. ffmpeg does not decode Bink 2; a still for a sample — through the game's `binaries/bink2w64.dll`
  (`BinkOpen` → `BinkGoto` → `BinkDoFrame` → `BinkCopyToBuffer`, BGRA = 5): `vic3_tools/comfy/bk2frames.py`. The first
  frames are often black (fade-in).
  Vanilla UI textures are uncompressed RGBA with mipmaps (1140×212 → 1 288 512 bytes).
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
