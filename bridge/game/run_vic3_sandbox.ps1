<#
A sandbox run of Victoria 3 for an agent: start, run at speed 5, pause, screenshots, logs.

Launches the game with the last save (-continuelastsave -debug_mode), waits for
it to load, sets speed 5 and unpauses, lets it run, pauses, takes a screenshot
of the game window, closes the game and collects the logs. A project's own parts
-- its mod's log lines, what to type after loading, how to find the heir of a
gone country, which screens -Shots takes -- come from its hooks (vic3_ui_lib.ps1).

Progress is checked by the date on screen (debug.log is buffered until the
game closes, autosaves may be half-yearly): the window must stay visible and
the date at its top right uncovered; a standing date is unpaused.

-Observe runs the game in observer mode: nobody plays, the AI runs every country -- the base run "how the game goes
without us". A project whose mod takes numbers from the GUI (a GUI -> script bridge) must check that the bridge still
works there before trusting such a run.

While it runs the game takes the keyboard focus: do not type or click.

Usage (PowerShell):
    powershell -ExecutionPolicy Bypass -File bridge\game\run_vic3_sandbox.ps1 -RunMinutes 5
Parameters:
    -RunMinutes   minutes the game runs at speed 5 (default 5): the minutes it advanced, the user's pauses not
                  counted (the wall clock's limit -- RunMinutes + 60)
    -LoadWaitSec  at most this many seconds for the save to load (default 400); the script goes on as
                  soon as the game's screen is up (Wait-Screen, by the colour of the left icon column)
    -Autosaves    stop as soon as this many new autosaves are written (0 = run -RunMinutes);
                  -RunMinutes stays the limit. Autosaves are half-yearly in this setup, so
                  the state to read from the save needs the run to pass 1 Jan / 1 Jul.
    -NoModLogs    passed to the project's Hook-AfterLoad: the mod's own debug logs stay off, as in a normal game;
                  through the bridge: the word "nomodlogs" in -Commands
    -Minimized    run with the game window minimized (R1а, Р8 7.10: does the GUI bridge live without drawing?);
                  the date is not checked while minimized, the window comes back before the pause;
                  through the bridge: the word "minimized" in -Commands
    -Commands     extra console commands after loading, ';'-separated (e.g. "dump_data_types"); their
                  output files in logs/ are copied with the other logs. "end:<cmd>" -- entered at the end of
                  the run, after the pause; "end:ui:<step>" -- a vic3_ui.ps1 step there (script profiler:
                  "Script.Profiling.Start;end:Script.Profiling.Stop;end:Script.Profiling.Gui;end:ui:wait 3;
                  end:ui:shot prof_1"; ScriptProfiling.Dump crashes 1.13.11, vanilla too -- 7.10)
    -AiTag        console "enable_ai <tag>" after loading, so the AI plays the player's country
                  too (default "all"; "" to skip)
    -StartSave    start from this save instead of the last one: a file name in "save games" (e.g.
                  sandbox_1836.v3). It is copied to sandbox_start.v3 and continue_game.json is pointed at
                  the copy, so the original is never written to; later runs without -StartSave go on
                  from the run's own autosaves -- if it made none, "continue" is put back to the previous save.
                  A manual save may open in the lobby (no country chosen): a random country, then "tag <Tag>".
    -NewGame      start a new game from 1836 instead of a save (start conditions, history files):
                  main menu -> New game -> Sandbox -> Random country -> Start, then the console
                  "tag <Tag>". Clicks are at fractions of the window, measured on 2560x1440 (16:9).
    -Playset      run on this launcher playset's mods instead of the last ones the launcher started (the game
                  reads content_load.json, not the active playset -- 6.10): the file is written from
                  launcher-v2.sqlite (`v3 playsets --content-load`) and put back after the run, failures too
    -Tag          the country to play in a new game (default BUG); gone in the run («Конец игры») -- the run sits
                  down as its heir if the project's Hook-FindHeir names one, else stops
    -NoDumps      kept for old command lines; does nothing (1.10 night: debugcountrybudgets and
                  debugmarkets are strings in victoria3.exe, but the release console answers
                  "Unknown command" -- developer-build commands)
    -KeepOpen     leave the game paused at the end instead of closing it (tooltips and other countries
                  with vic3_ui.ps1, which closes it and gathers the logs: -Do close)
    -Shots        at the end (paused) take the project's screens of the played country (Hook-ShotSteps:
                  vic3_ui.ps1 steps, macros in its points file)
    -Countries    then sit down as these countries in turn ("GBR,USA,RUS"; console "tag") and take the
                  same screens of each; nothing is played as them, the game stays paused; with -Observe -- observe
                  each instead (nobody plays them either way)
    -Observe      observer mode after loading (console "observe"): nobody plays, the AI runs every country; the view
                  is -Tag's country (its top bar, panels, tooltips); a gone country is no game over there. To step in:
                  "tag X" plays X, "observe" goes back (vic3_ui.ps1 "observe X")
    -OutDir       where to put logs and screenshots (default: %TEMP%\vic3_sandbox\<timestamp>)
#>
param(
    [int]$RunMinutes = 5,
    [int]$LoadWaitSec = 400,
    [int]$Autosaves = 0,
    [string]$AiTag = "all",
    [string]$Commands = "",
    [switch]$NoModLogs,
    [switch]$Minimized,
    [string]$StartSave = "",
    [switch]$NewGame,
    [string]$Tag = "BUG",
    [string]$Playset = "",
    [switch]$NoDumps,
    [switch]$KeepOpen,
    [switch]$Shots,
    [string]$Countries = "",
    [switch]$Observe,
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
# The game in the Steam library that has it (the PC: C:\games\steam; the sandbox VM: Program Files)
$Exe = "C:\games\steam\steamapps\common\Victoria 3\binaries\victoria3.exe"
if (-not (Test-Path $Exe)) {
    $steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam").SteamPath -replace "/", "\"
    $libs = @($steam) + @(Select-String -Path (Join-Path $steam "steamapps\libraryfolders.vdf") -Pattern '"path"\s+"(.+)"' |
        ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' })
    $Exe = $libs | ForEach-Object { Join-Path $_ "steamapps\common\Victoria 3\binaries\victoria3.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Exe) { throw "victoria3.exe not found in the Steam libraries" }
}
$Docs = Join-Path $env:USERPROFILE "Documents\Paradox Interactive\Victoria 3"
$Logs = Join-Path $Docs "logs"
if (-not $OutDir) { $OutDir = Join-Path $env:TEMP ("vic3_sandbox\" + (Get-Date -Format "yyyyMMdd_HHmmss")) }
New-Item -ItemType Directory -Force $OutDir | Out-Null

. (Join-Path $PSScriptRoot "vic3_ui_lib.ps1")

if (Get-Game) { throw "Victoria 3 is already running - close it first." }

# -continuelastsave loads the save named by "title" in continue_game.json.
if ($StartSave) {
    $Saves = Join-Path $Docs "save games"
    $src = Join-Path $Saves $StartSave
    if (-not (Test-Path $src)) { throw "no save $src" }
    Copy-Item $src (Join-Path $Saves "sandbox_start.v3") -Force
    $cg = Join-Path $Docs "continue_game.json"
    $j = Get-Content $cg -Raw -Encoding UTF8 | ConvertFrom-Json
    $prevTitle = $j.title
    $j.title = "sandbox_start"
    [IO.File]::WriteAllText($cg, ($j | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Log "start save: $StartSave (copied to sandbox_start.v3)"
}

# -Playset: the game's mod list for this run; the previous one comes back at the end (and on a failure, by the trap)
$ContentLoad = Join-Path $Docs "content_load.json"
$ContentBackup = Join-Path $OutDir "content_load.before.json"
if ($Playset) {
    Copy-Item $ContentLoad $ContentBackup -Force
    & v3 playsets --content-load $Playset --out $ContentLoad | ForEach-Object { Log "playset $_" }
    if ($LASTEXITCODE -ne 0) { Copy-Item $ContentBackup $ContentLoad -Force; throw "no playset '$Playset'" }
    trap { if (Test-Path $ContentBackup) { Copy-Item $ContentBackup $ContentLoad -Force; Log "content_load.json restored (failure)" }; break }
}

# «Конец игры»: the played country is gone (a revolution won, annexed). «Продолжить в режиме наблюдателя», then the
# project's Hook-FindHeir looks for the heir (a mod's log may name it); console "tag <heir>" and the run goes on as the
# heir. No hook, or no heir in 3 minutes -- $false (the run stops).
function Sit-Heir($p) {
    Shot $p ("gameover_" + (Get-Date -Format "HHmmss") + ".png")
    Log "game over: $Tag is gone - observer mode, looking for its heir"
    Click-Window $p 0.13 0.981 "bl"; Start-Sleep 5
    $p = Get-Game
    if (-not $p) { return $false }
    if (-not (Is-Advancing $p 16)) { Send-Key 0x20 0x39 }
    if (-not (Get-Command Hook-FindHeir -ErrorAction SilentlyContinue)) { Log "game over: no Hook-FindHeir - stopping"; return $false }
    $until = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $until) {
        Start-Sleep 5; Save-DebugParts
        $found = Hook-FindHeir $Tag  # @(heir tag, its name) or $null
        if (-not $found) { continue }
        $heir = $found[0]; $name = $found[1]
        Console-Cmd (Get-Game) "tag $heir"; Start-Sleep 5
        Log "the heir of $($Tag): $heir ($name) - playing it, the run goes on"
        $script:Tag = $heir
        $p = Get-Game; Focus-Game $p
        if (-not (Is-Advancing $p 16)) { Send-Key 0x20 0x39 }
        return $true
    }
    Log "game over: no heir of $Tag in the log in 3 min - stopping"
    return $false
}

if ($NewGame) {
    Log "launching $Exe -debug_mode (new game)"
    Start-Process -FilePath $Exe -ArgumentList "-debug_mode" -WorkingDirectory (Split-Path $Exe)
} else {
    Log "launching $Exe -continuelastsave -debug_mode"
    Start-Process -FilePath $Exe -ArgumentList "-continuelastsave", "-debug_mode" -WorkingDirectory (Split-Path $Exe)
}

$t0 = Get-Date
$p = $null
while (((Get-Date) - $t0).TotalSeconds -lt 240) {
    $p = Get-Game
    if ($p -and $p.MainWindowHandle -ne 0) { break }
    Start-Sleep 3
}
if (-not $p -or $p.MainWindowHandle -eq 0) { throw "no game window after 4 minutes" }
if ($NewGame) {
    # The main menu, the goals screen, the lobby (map), the game (2026-10-01, 1.13.11 with this playset).
    Wait-Screen "menu" 300 3 | Out-Null
    $p = Get-Game
    Shot $p "00a_menu.png"
    Click-Window $p 0.2086 0.394                                               # New game
    Wait-Screen "goals" 90 4 | Out-Null; Shot $p "00b_goals.png"
    Click-Window $p 0.8665 0.625                                               # Sandbox: start the game
    Wait-Screen "lobby" 180 3 | Out-Null; Shot $p "00c_lobby.png"
    Click-Window $p 0.25 0.981 "bl"; Start-Sleep 2                             # Random country
    Click-Window $p 0.9215 0.975 "br"; Log "new game: starting"                # Start
    Wait-Screen "game" 300 8 | Out-Null
    $p = Get-Game
    Console-Cmd $p "tag $Tag"
    Start-Sleep 5
} else {
    Log "window up, waiting for the save to load (at most $LoadWaitSec s)"
    # a save may open in the lobby (r1005_103836, -StartSave of a manual save: the country picker, no country
    # chosen -- "Начать" does nothing until one is, r1005_104216 waited 5 min): as for a new game -- "Случайное
    # государство", "Начать", then "tag" to -Tag (without -Tag the run plays the random country -- logged)
    if ((Wait-Screen @("game", "lobby") $LoadWaitSec 8) -eq "lobby") {
        $p = Get-Game; Shot $p "00c_lobby.png"
        Click-Window $p 0.25 0.981 "bl"; Start-Sleep 2
        Click-Window $p 0.9215 0.975 "br"; Log "the save opened in the lobby: a random country, starting"
        Wait-Screen "game" 300 8 | Out-Null
        if ($PSBoundParameters.ContainsKey("Tag")) { Console-Cmd (Get-Game) "tag $Tag"; Start-Sleep 5 }
        else { Log "no -Tag: playing the random country of the lobby" }
    }
}
$p = Get-Game
Shot $p "01_loaded.png"
if ($AiTag) { Console-Cmd $p "enable_ai $AiTag"; Shot $p "01b_ai.png" }
# the project's commands after loading (its mod's debug logs on, or off with -NoModLogs)
# the bridge passes only -Commands: the word "nomodlogs" there does the same as -NoModLogs
if ($Commands -match '(^|;)\s*nomodlogs\s*(;|$)') { $NoModLogs = $true; $Commands = ($Commands -replace '(^|;)\s*nomodlogs\s*(?=;|$)', '') }
if (Get-Command Hook-AfterLoad -ErrorAction SilentlyContinue) { Hook-AfterLoad $p ([bool]$NoModLogs) }
if ($Commands -match '(^|;)\s*minimized\s*(;|$)') { $Minimized = $true; $Commands = ($Commands -replace '(^|;)\s*minimized\s*(?=;|$)', '') }
# a command "ui:<step>" is a step of vic3_ui.ps1 (key, click, hover, shot, wait ...), the rest -- console commands
# a command "end:<cmd>" is entered at the end of the run, after the pause (e.g. "end:Script.Profiling.Stop", 7.10)
$EndCommands = @()
foreach ($c in ($Commands -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    if ($c.StartsWith("end:")) { $EndCommands += $c.Substring(4); continue }
    if ($c.StartsWith("ui:")) { & (Join-Path $PSScriptRoot "vic3_ui.ps1") -OutDir $OutDir -Do $c.Substring(3) }
    else { Console-Cmd $p $c; Start-Sleep 5; Log "console: $c" }
}

# -Observe: nobody plays from here (after the project's commands: a console event may need a played country); the view is -Tag's country
if ($Observe) { Observe-Country $p $Tag; $p = Get-Game; Shot $p "01c_observe.png" }
# speed 5, unpause; verify by the date on screen, toggle pause once more if it stands
Focus-Game $p
Send-Key 0x35 0x06
Send-Key 0x20 0x39
$ok = Is-Advancing $p 24
if (-not $ok) { Send-Key 0x20 0x39; $ok = Is-Advancing $p 24 }
Log ("advancing: " + $ok)
if (-not $ok) { Shot $p "02_not_running.png"; Log "the game does not advance - stopping"; }
else {
    Log "running for $RunMinutes min (autosaves wanted: $Autosaves)"
    # SW_MINIMIZE; Is-Advancing raises the window, so the date is not checked until the end
    if ($Minimized) { [W]::ShowWindow($p.MainWindowHandle, 6) | Out-Null; Log "the game window is minimized" }
    $since = Get-Date
    $autoSeen = New-Object 'System.Collections.Generic.HashSet[long]'
    # -RunMinutes counts the minutes the game ran (the user, 10.10: watching, the user pauses, switches countries and comes
    # back -- that time is not the run's); the wall clock's limit -- RunMinutes + 60
    $ranSec = 0
    $wallEnd = (Get-Date).AddMinutes($RunMinutes + 60)
    $userMode = $false
    while ($ranSec -lt $RunMinutes * 60 -and (Get-Date) -lt $wallEnd) {
        # every 2 s: the game keeps 5 parts of ~512 KB and fills one in 2-4 s with the fork's logs -- at 15 s whole
        # parts were lost (r1012_200620: 6-19 October 1850, about 40 months with lines missing)
        for ($k = 0; $k -lt 30; $k++) { Start-Sleep 2; Save-DebugParts }
        if ($Autosaves -gt 0) {
            # Count distinct write times, not files: the game keeps five rotating
            # autosave files, so a file count never got past 5 (3.10, night G).
            Get-ChildItem (Join-Path $Docs "save games") -Filter "autosave*.v3" | Where-Object { $_.LastWriteTime -gt $since -and $_.Name -ne "autosave_exit.v3" } | ForEach-Object { [void]$autoSeen.Add($_.LastWriteTime.Ticks) }
            $n = $autoSeen.Count
            Log "new autosaves: $n"
            if ($n -ge $Autosaves) { Start-Sleep 20; break }
        }
        if (-not (Get-Game)) { Log "the game exited"; break }
        $p = Get-Game
        if ($Minimized) { Log "minimized"; continue }
        # the user touched the PC in the last 3 min: hands off -- nothing pressed, no panel closed, the date read without
        # raising the game; a standing date is the user's pause, not counted and not undone
        $ago = User-InputAgo
        if ($ago -ge 0 -and $ago -lt 180000) {
            if (-not $userMode) { $userMode = $true; Log "the user is watching - hands off" }
            if (Is-AdvancingPassive $p 16) { $ranSec += 60; Log ("advancing (the user is watching), ran {0:N0} of {1} min" -f ($ranSec / 60), $RunMinutes) }
            else { Log "paused by the user - not counted" }
            continue
        }
        if ($userMode) { $userMode = $false; Log "the user has been away 3 min - the run goes on" }
        if (-not (Is-Advancing $p 16) -and (Is-Screen $p "gameover")) {
            # the player's country is gone (Д.R4б.34): observer mode, the project's hook finds the heir, sit down as it
            if (-not (Sit-Heir $p)) { break }
            continue
        }
        if (-not (Is-Advancing $p 16)) {
            Log "date stands - unpausing"
            Shot $p ("stall_" + (Get-Date -Format "HHmmss") + ".png")
            if (Is-Screen $p "console") { Log "the console is open"; Close-Console $p | Out-Null }
            Send-Key 0x20 0x39
            if (-not (Is-Advancing $p 16)) { Send-Key 0x20 0x39; Log "still standing after a toggle" }
            else { $ranSec += 60 }
        } else { $ranSec += 60; Log ("advancing, ran {0:N0} of {1} min" -f ($ranSec / 60), $RunMinutes) }
    }
    $p = Get-Game
    if ($p -and $Minimized) { [W]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; Start-Sleep 3; Raise-Game $p | Out-Null; Log "the game window is restored" }
    if ($p) {
        # pause at once, even if the user is at the PC (the user, 5.10); the screens after it wait for the user
        Pause-Now $p; $script:WantPaused = $true; Start-Sleep 3; Shot $p "03_end.png"
        foreach ($c in $EndCommands) {
            if ($c.StartsWith("ui:")) { & (Join-Path $PSScriptRoot "vic3_ui.ps1") -OutDir $OutDir -Do $c.Substring(3) }
            else { Console-Cmd $p $c; Start-Sleep 10; Log "console (end): $c" }
        }
    }
}

if (($Shots -or $Countries) -and (Get-Game)) {
    # the project's screens (Hook-ShotSteps) of the played country and of others
    Set-Content (Join-Path $OutDir "t0.txt") $t0.ToString("o")
    # events and panels the AI or the console click left open covered the shots (r1005_102757, r1005_104528: an
    # event window over the cards) -- closed first, as after the user (Escape until the game menu, once more)
    Reset-UI (Get-Game); Shot (Get-Game) "03b_clean.png"
    $steps = @()
    if ($Shots -and (Get-Command Hook-ShotSteps -ErrorAction SilentlyContinue)) { $own = if ($NewGame) { $Tag } else { "own" }; $steps += (Hook-ShotSteps $own) }
    foreach ($c in ($Countries -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
        if (-not $Observe) { $steps += "country $c"; continue }
        $steps += "observe $c"
        if (Get-Command Hook-ShotSteps -ErrorAction SilentlyContinue) { $steps += (Hook-ShotSteps $c) }
    }
    Log "screens: $($steps -join '; ')"
    try { & (Join-Path $PSScriptRoot "vic3_ui.ps1") -OutDir $OutDir -Do ($steps -join '; ') }
    catch { Log "screens failed: $_" }
}
if ($KeepOpen -and (Get-Game)) {
    # the game stays paused for vic3_ui.ps1 (tooltips, other countries); logs are
    # gathered when that script closes it ("close")
    Set-Content (Join-Path $OutDir "t0.txt") $t0.ToString("o")
    Log "kept open (paused)"
} else {
    Close-And-Collect
}
# -StartSave pointed "continue" at the copy; if the run made no autosave (a short run -- the game moves the pointer
# itself on an autosave) the pointer still names the copy and the user's "Continue" (and the next run without
# -StartSave) would open it: r1005_105248 continued the copy into the lobby. Put the previous save back.
if ($StartSave -and -not $KeepOpen) {
    $j = Get-Content $cg -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($j.title -eq "sandbox_start") {
        $j.title = $prevTitle
        [IO.File]::WriteAllText($cg, ($j | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
        Log "continue_game.json: back to '$prevTitle' (the run made no autosave)"
    }
}
if ($Playset -and (Test-Path $ContentBackup)) {
    Copy-Item $ContentBackup $ContentLoad -Force
    Log "content_load.json: back to the launcher's mods"
}
Log "done: $OutDir"
