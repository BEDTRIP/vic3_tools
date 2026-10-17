---
name: vic3-sandbox
description: Run Victoria 3 yourself to check a mod — in the Hyper-V sandbox VM (the PC's screen stays free) or on the PC — and read what the game says: crashes, debug.log / error.log / gui.log, screenshots; the test bench `v3 bench` to see a GUI edit in a running game in ~30 s. Use when a change must be checked in the game, a run's numbers or screens are needed, a crash or log line must be explained, or the user says "проверь в игре", "прогон", "песочница", "запусти игру". A project may have its own run-script skill on top (its parameters, its mod's logs).
---

# Running the game for a check

The game's facts beat reasoning: one load of the game closes a question that otherwise takes half a session. Answer in
the user's language.

## Where it runs

- **The sandbox VM** (`vic3-sandbox`, Hyper-V with a share of the video card) — the default: the user keeps the PC.
  `vic3_tools/bridge/vm/Invoke-SandboxRun.ps1 -Script <script> -OutDir <dir> -ParamsJson <file.json>
  [-HooksDir <the project's hooks>] [-ContentLoad <content_load.json>] [-StartSave <save>] [-FetchSaves]` copies the
  game scripts (`bridge/game`), the project's hooks and the mods (changed files only) into the guest, runs the script
  in the guest's desktop session and brings the output back. Login: `Invoke-Command -VMName vic3-sandbox -Credential (Import-Clixml
  "$env:LOCALAPPDATA\vic3tools\vm-cred.xml")`.
- **On the PC** — the game takes the screen, mouse and keyboard: warn the user first; a script that sends keys must
  check the game window is in front before every key (keys typed into the user's chat happened).
- **From a cloud session** — through the PC bridge (`vic3-pc` MCP, `bridge/pc/server.py` with the project's
  `bridge.toml`): `v3(["bench", …])`, `start_run`, `run_status`, `get_image`, `read_text`, `grep`. **Every run goes to
  the VM: `start_run(..., target="vm")`** — the bridge's own default is wherever it was started (`start.ps1 -Vm` or
  not), so pass it each time; `target="pc"` only when the user asks for their screen. The plugin
  itself (these skills) reaches a cloud session only through the environment's setup script, not through the repo's
  `.claude/settings.json` — see `claude-plugin/README.md`, «Cloud sessions».

The game scripts are `vic3_tools/bridge/game`: `run_vic3_sandbox.ps1` (load a new game or a save, run N minutes with
the AI for everyone, console commands, autosaves, screens, gather the logs; `-KeepOpen` leaves the game paused) and
`vic3_ui.ps1` (steps on the open game: click, hover, key, shot, console, macros). What a project adds — its mod's log
lines gathered into their own file, console commands after loading, a gone country's heir, the screens of `-Shots` —
lives in its `vic3_hooks.ps1` (the hooks are listed at the top of `vic3_ui_lib.ps1`): on the PC `$env:VIC3_HOOKS`, in
the VM `-HooksDir`, for the bench `[bench] hooks = '<folder>'` in `vic3tools.toml`.

## The test bench: a GUI edit in a running game

```
v3 bench start                         # the playset's mods; a new game (or --save NAME), left paused in the VM
v3 bench shot before --crop 0,0.1,0.5,0.6
# … edit the .gui …
v3 bench shot after --crop 0,0.1,0.5,0.6   # changed files are sent first; the game in debug mode re-reads them
v3 bench diff before after             # the changed share, the area, a side-by-side image
v3 bench do "hover 0.42 0.31; wait 2; shot tip"   # vic3_ui steps: click, hover, key, console …
v3 bench stop                          # close and gather the logs
```

`--theme ip4` (base, votp, ap1, ip2, ip3, ip4, ep2) starts the guest in that interface theme: graphics are checked in
every theme. **An event from the console waits for a day:** `console event X` on the paused game logs
`console_success` and shows nothing; the event comes on the next daily tick, minimized (a line in the right column and
an envelope on the map, 17.10): `key space; wait 4; key space`, then a click on its line opens the window.
`Close-Console` clicks the map at (0.62, 0.45) to take the focus off the console line; in the 1836 GBR start that
opens the sea region «Южная бухта» — not the mod.

The project's hooks: `[bench] hooks = '<folder with vic3_hooks.ps1>'` in `vic3tools.toml`. Crop the shots:
a whole 2560×1440 frame costs ~2k tokens to read; a subagent can read many shots and report only what matters.

## Rules

- **The screen is part of the run.** The game scripts click and read the screen at points measured on a 2560×1440
  window (moved by the interface scale). The VM's screen is fixed at 2560×1440 (`Initialize-SandboxGuest.ps1`); the
  user's PC screen is whatever the user has now (1920×1080 on 17.10.2026). On another size the run breaks in ways that
  look like the game: the lobby's "Random country" misses ("screen 'game' not seen in 300 s", the lobby with no country
  chosen on `01_loaded.png`), "console: did not open — 'tag …' not sent", «Конец игры» not seen ("date stands" on the
  game-over screen), the profiler's view shots empty. Then move the run to the VM — do not patch points in a project's
  hooks for the PC's screen (17.10 a night lost three runs and an hour to it). The size of a shot: `get_image(path,
  crop=[0, 0.96, 0.05, 1], max_width=4000)` comes back 96 px wide at 1920, 128 at 2560.
- **Never `Restart-VM -Force`** — a hard reset; registry edits were lost and the VM sat at the password screen. Reboot
  from inside (`Restart-Computer -Force` through `Invoke-Command`).
- A guest session left **"Disc"** (a VMConnect window opened and closed) has no screen — screenshots fail with "The
  handle is invalid". `Invoke-SandboxRun.ps1` restarts the guest from inside by itself; `query user` shows the state.
- **A game on the PC in `-debug_mode` re-reads changed files on the fly** — do not sync the live mod copy during a PC
  run (half-reloaded effects fill `error.log` with false errors). The VM has its own copy: syncing on the PC is fine
  while a VM run goes.
- To see your own window on screen, make it a child of a vanilla window or of `ingame_hud` (a copy of
  `gui/ingame_hud.gui`); a free-standing top-level widget is not drawn.
- **Interface scale:** only the run's own flow (menu, goals, lobby clicks, game and date detection) is checked at another
  scale (×1.3, r1016_sc13). The screen steps (`-Shots`, `-Countries`, `ui:`: cards, budget tabs, `hoverlink`, `browse`)
  click at points measured at 1 and miss — `Invoke-SandboxRun.ps1` gives such runs scale 1 unless `-GuiScale` is set.
- The played country must be a country, not observer mode — GUI commands do not run in observer mode (checked
  16.10.2026, r1016_obs4: E&F's GUI money bridge delivered 0 in all 201 lines, against ~97 % nonzero when a country is
  played). So `-Observe` runs suit "how the game goes", not a mod's GUI-fed numbers. Console: `observe` toggles
  (a second one ends observer mode); while observing, `tag X` neither ends it nor moves the camera.
- Keep runs short and targeted; record every finding where the project tracks work (its plan), not only in the answer.

## Reading what the game said

- **A crash:** `Documents/Paradox Interactive/Victoria 3/crashes/<date>/exception.txt` first, then its `logs/`
  snapshot. `grep -c victoria3.exe exception.txt` stuck at the same number across edits = infinite recursion.
- **Load errors:** `debug.log` (Unknown modifier type, Badly read, Unexpected token, compile and PostValidate errors,
  "Duplicated event ID", "more than one 'effect'"); it rotates by 512 KB — the oldest `debug.N.log` has the start.
- **Run-time errors:** `error.log` — summarize instead of reading:
  `sed -E 's/^\[[0-9:]+\]//' error.log | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -40`.
- **GUI:** `gui.log` — "Type / Template '…' already registered at …" (which definition was ignored).
- **What was loaded:** `content_load.json` (the mods and paths of the last start), `v3 mods` (the playset).
- **Tools:** `v3 log summary <run>` (families), `v3 log diff <base run> <run>` (what is new), `v3 log sites <run>
  --mod <mod>` (errors by the mod's file and line), `v3 log speed <runs>` (seconds per game month); a run's text
  saves — `v3 save info / owners / buildings / companies / vars / goods / grep` (indexed once, then by pieces).
- **What is slow:** the script profiler as a table, not pictures — `v3 bench profile --seconds 60 --by-file` on a
  bench started with `mods/profiler_view` in the set (root view: top entries by total time; edge view: leaves by own
  time, with file:line and ms per tick); old shots — `v3 log profile <shots> [--compare <shots of another run>]`.
  The shots are read by Windows OCR; read the picture itself only when the table says rows were not read.
- Silence in the logs is not confirmation: many breakages log nothing (skill `vic3-modding`, `diagnostics.md`).
