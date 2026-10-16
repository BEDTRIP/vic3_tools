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
  `bridge.toml`): `v3(["bench", …])`, `start_run`, `run_status`, `get_image`, `read_text`, `grep`.

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

The project's hooks: `[bench] hooks = '<folder with vic3_hooks.ps1>'` in `vic3tools.toml`. Crop the shots:
a whole 2560×1440 frame costs ~2k tokens to read; a subagent can read many shots and report only what matters.

## Rules

- **Never `Restart-VM -Force`** — a hard reset; registry edits were lost and the VM sat at the password screen. Reboot
  from inside (`Restart-Computer -Force` through `Invoke-Command`).
- A guest session left **"Disc"** (a VMConnect window opened and closed) has no screen — screenshots fail with "The
  handle is invalid". `Invoke-SandboxRun.ps1` restarts the guest from inside by itself; `query user` shows the state.
- **A game on the PC in `-debug_mode` re-reads changed files on the fly** — do not sync the live mod copy during a PC
  run (half-reloaded effects fill `error.log` with false errors). The VM has its own copy: syncing on the PC is fine
  while a VM run goes.
- To see your own window on screen, make it a child of a vanilla window or of `ingame_hud` (a copy of
  `gui/ingame_hud.gui`); a free-standing top-level widget is not drawn.
- The played country must be a country, not observer mode — GUI commands do not run in observer mode.
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
