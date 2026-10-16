# Profiler View — the script profiler window for measurements

A helper mod for measuring runs only (not for play). It replaces the window of the built-in script profiler,
`gui/script_profiler/script_profiler.gui` (the game loads it by this path): full screen, the table "callees of the
current entry" with the full name, file:line, total and own time and the call count -- readable from a screenshot.
Row 1 of the table is at y = 0.155 of the screen, step 0.0215 (1080p); a click on a row selects the entry, the "root"
button (0.02, 0.06) goes back to the root.

A run: install it once (the bridge: `install_mod("tools:mods/profiler_view", "LD Profiler View")`; by hand: copy the
folder to `Documents/Paradox Interactive/Victoria 3/mod/LD Profiler View`), add it to a playset
(`v3 playsets --content-load "<playset> + LD Profiler View"`), then the run's commands
`Script.Profiling.Start;end:Script.Profiling.Stop;end:Script.Profiling.Gui;end:ui:wait 3;end:ui:prof 1=root 1.1=…`
(the `prof` step of `bridge/game/vic3_ui.ps1`). The file dump `ScriptProfiling.Dump` crashes 1.13.11 (vanilla too),
hence the window.
