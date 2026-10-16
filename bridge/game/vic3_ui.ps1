<#
Drives a Victoria 3 window left open by run_vic3_sandbox.ps1 -KeepOpen:
screenshots of tooltips and panels, other countries, then closing the game with the logs gathered.

Usage (PowerShell):
    powershell -ExecutionPolicy Bypass -File bridge\game\vic3_ui.ps1 -OutDir <run dir> -Do "<step>;<step>;..."
Steps (';'-separated, run in order):
    shot <name>             screenshot of the window into <OutDir>\<name>.png
    click <fx> <fy>         left click at a fraction of the window (2560x1440 measured)
    hover <fx> <fy>         move the mouse there (a tooltip opens after ~1 s)
    scroll <fx> <fy> <n>    mouse wheel there, n notches (negative = down)
    wait <sec>              sleep
    key <name>              esc | space | enter | f1..f9 | tilde (the console key) (scan codes for DirectInput)
    console <command>       a console command (debug_mode), e.g. "console tag GBR"
    prof <path>=<name> ...  script profiler window: root, then the rows of the path (1.1.2), a screenshot each
    macro <name> <prefix>   a named step sequence from vic3_ui_points.ps1 ({P} = prefix)
    tips <set> <prefix>     every hover of the named set below, one screenshot each (<prefix>_<n>.png)
    country <TAG>           "tag <TAG>", then the project's screens of it (Hook-ShotSteps of its hooks)
    close                   close the game and gather the logs into <OutDir> (the mod's log lines as after a run)
#>
param(
    [Parameter(Mandatory = $true)][string]$OutDir,
    [Parameter(Mandatory = $true)][string]$Do
)

$ErrorActionPreference = "Stop"
$Docs = Join-Path $env:USERPROFILE "Documents\Paradox Interactive\Victoria 3"
$Logs = Join-Path $Docs "logs"
New-Item -ItemType Directory -Force $OutDir | Out-Null
$t0f = Join-Path $OutDir "t0.txt"
$t0 = if (Test-Path $t0f) { [datetime]::Parse((Get-Content $t0f -Raw).Trim(), $null, [Globalization.DateTimeStyles]::RoundtripKind) } else { (Get-Date).AddHours(-3) }

. (Join-Path $PSScriptRoot "vic3_ui_lib.ps1")
# the steps are taken on a paused game (after a run, or -KeepOpen): after the user it is paused again (5.10)
$script:WantPaused = $true

$Keys = @{ esc = @(0x1B, 0x01); space = @(0x20, 0x39); enter = @(0x0D, 0x1C)
    f1 = @(0x70, 0x3B); f2 = @(0x71, 0x3C); f3 = @(0x72, 0x3D); f4 = @(0x73, 0x3E); f5 = @(0x74, 0x3F)
    f6 = @(0x75, 0x40); f7 = @(0x76, 0x41); f8 = @(0x77, 0x42); f9 = @(0x78, 0x43)
    # the console key (5.10: after -Commands "tag ...; money ..." the console stayed open, the speed key went into it)
    tilde = @(0xC0, 0x29) }

# Named hover sets: the points measured on the screenshots of the night of 4.10 (fractions of a
# 2560x1440 window). Filled in as they are found.
$TipSets = @{}
$Macros = @{}
# the project's points and macros: its hooks name the file ($PointsFile), else vic3_ui_points.ps1 next to this script
$setsFile = if ($script:PointsFile) { $script:PointsFile } else { Join-Path $PSScriptRoot "vic3_ui_points.ps1" }
if (Test-Path $setsFile) { . $setsFile }

foreach ($step in ($Do -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    $a = $step -split '\s+', 2
    $cmd = $a[0]; $rest = if ($a.Count -gt 1) { $a[1] } else { "" }
    $p = Get-Game
    if (-not $p -and $cmd -ne "close") { Log "no game running - '$step' skipped"; break }
    switch ($cmd) {
        "shot"    { Focus-Game $p; Start-Sleep -Milliseconds 300; Shot $p ($rest + ".png") }
        "click"   { $xy = $rest -split '\s+'; Click-Window $p ([double]$xy[0]) ([double]$xy[1]) }
        "hover"   { $xy = $rest -split '\s+'; Hover-Window $p ([double]$xy[0]) ([double]$xy[1]) }
        # hoverlink <n> <fy>: the n-th underlined link of the pinned tooltip, found by its look (5.10); not found --
        # the fixed row fy (the old way)
        "hoverlink" {
            $xy = $rest -split '\s+'; $at = Find-Link $p ([int]$xy[0])
            if ($at) { Hover-Window $p $at[0] $at[1]; if ($at[2] -ne 7) { Log "links: $($at[2]) found (7 expected)" } }
            else { Hover-Window $p 0.03 ([double]$xy[1]) }
        }
        "scroll"  { $xy = $rest -split '\s+'; Scroll-Window $p ([double]$xy[0]) ([double]$xy[1]) ([int]$xy[2]) }
        "wait"    { Start-Sleep -Milliseconds ([int]([double]$rest * 1000)) }
        "key"     { $k = $Keys[$rest]; Send-Key ([byte]$k[0]) ([byte]$k[1]) }
        "console" { Console-Cmd $p $rest }
        "tips"    {
            $xy = $rest -split '\s+'; $set = $TipSets[$xy[0]]; $pre = $xy[1]
            if (-not $set) { Log "no tip set '$($xy[0])'"; break }
            $i = 0
            foreach ($pt in $set) {
                $i++
                if ($pt.click) { Click-Window $p $pt.click[0] $pt.click[1]; Start-Sleep -Milliseconds 1200 }
                if ($pt.hover) { Hover-Window $p $pt.hover[0] $pt.hover[1]; Start-Sleep -Milliseconds 1800 }
                Shot $p ("{0}_{1:D2}_{2}.png" -f $pre, $i, $pt.name)
            }
        }
        # redo <step|step|...>: a piece that needs its own menu (a budget tab, a card); if the user came in while it
        # ran (the menus were closed after them), it is taken again from its start -- up to 3 times (5.10: the user
        # interrupted a budget tab, the script closed the budget and paged on over the map)
        "redo"    {
            $sub = $rest -replace '\|', ';'
            for ($k = 1; $k -le 3; $k++) {
                $global:Vic3Interrupted = $false
                & $PSCommandPath -OutDir $OutDir -Do $sub
                if (-not $global:Vic3Interrupted) { break }
                Log "redo: the user came in - again ($k)"
            }
        }
        # prof <path>=<name> ...: the script profiler window (vic3_tools mods/profiler_view): for each item -- "root", then the
        # rows of the path (1.1.2 = row 1, row 1, row 2; the rows are sorted by inclusive time), a screenshot <name>.png
        # (8.10: one step instead of ~15 per shot -- the command line of the run has a length limit)
        "prof"    {
            Focus-Game $p
            foreach ($it in ($rest -split '\s+')) {
                $pn = $it -split '='
                Click-Window $p 0.028 0.067; Start-Sleep -Milliseconds 500
                foreach ($r in ($pn[0] -split '\.')) {
                    Click-Window $p 0.5 (0.1275 + 0.0198 * ([int]$r - 1)); Start-Sleep -Milliseconds 400
                }
                Start-Sleep -Milliseconds 300; Shot $p ($pn[1] + ".png")
            }
        }
        "macro"   {
            $xy = $rest -split '\s+'; $m = $Macros[$xy[0]]
            if (-not $m) { Log "no macro '$($xy[0])'"; break }
            & $PSCommandPath -OutDir $OutDir -Do ($m -replace '\{P\}', $xy[1])
        }
        "country" {
            # sit down as another country (paused, nothing played) and take the project's screens of it (Hook-ShotSteps)
            $more = if (Get-Command Hook-ShotSteps -ErrorAction SilentlyContinue) { "; " + (Hook-ShotSteps $rest) } else { "" }
            & $PSCommandPath -OutDir $OutDir -Do "console tag $rest; wait 3; hover 0.6 0.97; wait 1$more"
        }
        "browse"  {
            # П.15 (4.10): the open panel's tab top to bottom -- every collapsed section expanded (only "›",
            # what is open stays open), a shot a page, until the page stops moving. "browse <name> [pages]".
            # The mouse rests on the map (0.75 0.55): on a panel's title it pinned the title's tooltip over the
            # scrollbar (a market's owner, 4.10). Paged by dragging the scrollbar's thumb (x 0.2375): the wheel over the content scrolled the nested
            # tables (currencies, countries) instead of the panel, over the scrollbar it did nothing. A "›" that stays after its click (a button,
            # not a section) is not clicked again.
            $xy = $rest -split '\s+'; $name = $xy[0]; $max = if ($xy.Count -gt 1) { [int]$xy[1] } else { 150 }
            # the panel's title bar is remembered; before every click and drag it must be the same -- the user
            # closed the panel once and the drags went on over the map (4.10)
            Hover-Window $p 0.75 0.55; Start-Sleep -Milliseconds 700
            $title = Region-Sig $p 130 540 95 175
            $same = { (Region-Sig $p 130 540 95 175) -eq $title }
            # to the top: the thumb dragged above the track
            $th = Find-Thumb $p 608 280 1435
            if ($th) { Drag-Window $p 0.2375 (($th[0] + $th[1]) / 2) 0.2375 0.15 }
            Hover-Window $p 0.75 0.55; Start-Sleep -Milliseconds 700
            $last = ""; $fac = 0.85
            for ($pg = 1; $pg -le $max; $pg++) {
                $skip = @()
                for ($k = 0; $k -lt 10; $k++) {
                    $f = @(Find-Collapsed $p 50 92 300 1430 | Where-Object { $y = $_; -not ($skip | Where-Object { [Math]::Abs($_ - $y) -lt 0.004 }) })
                    if ($f.Count -eq 0) { break }
                    if (-not (& $same)) { Log "browse: the panel changed - stopping"; $pg = $max + 1; break }
                    Log ("browse: expanding the section at y {0:N4}" -f $f[0])
                    Click-Window $p 0.06 $f[0]; Start-Sleep -Milliseconds 900; Hover-Window $p 0.75 0.55; Start-Sleep -Milliseconds 500
                    $after = @(Find-Collapsed $p 50 92 300 1430)
                    if ($after | Where-Object { [Math]::Abs($_ - $f[0]) -lt 0.004 }) { $skip += $f[0]; Log "browse: it stays collapsed - skipped" }
                }
                if ($pg -gt $max) { break }
                if (-not (& $same)) { Log "browse: the panel changed - stopping"; break }
                $sig = Region-Sig $p 60 600 300 1430
                if ($sig -eq $last) { Log "browse: the end at page $pg"; break }
                $last = $sig
                Shot-Region $p ("{0}_{1:D2}.png" -f $name, $pg) 0 0 640 1440
                # a page down: the thumb dragged by 85% of its height (its height is the visible share)
                $th = Find-Thumb $p 608 280 1435
                if (-not $th) { Log "browse: no scrollbar - one page"; break }
                # the step adapts: the content's real shift (row profiles before / after) against 85% of the view
                $before = Row-Profile $p 70 580 310 1420
                $mid = ($th[0] + $th[1]) / 2; Drag-Window $p 0.2375 $mid 0.2375 ([Math]::Min(0.995, $mid + $fac * ($th[1] - $th[0])))
                Hover-Window $p 0.75 0.55; Start-Sleep -Milliseconds 700
                $after = Row-Profile $p 70 580 310 1420
                $sh = Profile-Shift $before $after; $d = $sh[0]; $q = $sh[1]; $n = [int]($before.Length / 6)
                if ($q -ge 1.5 -and $d -gt 20) { $fac = $fac * [Math]::Max(0.5, [Math]::Min(2.0, 0.85 * $n / $d)) }
                elseif ($q -ge 1.5) { $fac = $fac * 2 }
                $fac = [Math]::Max(0.2, [Math]::Min(8, $fac))
                Log ("browse: page {0} moved {1} rows (match {2:N1}), next factor {3:N2}" -f $pg, $d, $q, $fac)
                if ($q -ge 1.5 -and $d -ge 0 -and $d -lt 15) { Log "browse: the end at page $pg (no more movement)"; break }
            }
        }
        "market"  {
            # П.15 (4.10): another market's "Global" tab (forex, rating, bonds): own market (the left column's
            # icon) -> "World market" -> "Participants" -> the row's arrow -> "Global", browsed. Rows are the
            # world market's own order (the biggest first; Britain 1836: 1 Britain, 2 Russia, 3 France).
            # "market <row> <name>"
            $xy = $rest -split '\s+'; $row = [int]$xy[0]; $name = $xy[1]
            & $PSCommandPath -OutDir $OutDir -Do (("click 0.0085 0.2635; wait 2; hover 0.75 0.55; wait 0.5; click 0.13 0.976; wait 2; " +
                "hover 0.75 0.55; wait 0.5; click 0.1835 0.145; wait 2; click 0.0785 {0}; wait 2; hover 0.75 0.55; wait 0.5; " +
                "click 0.215 0.145; wait 2; hover 0.75 0.55; wait 1; browse {1}_market_global; click 0.2265 0.095; wait 1") -f (0.385 + 0.0209 * ($row - 1)).ToString([Globalization.CultureInfo]::InvariantCulture), $name)
        }
        "crop"    {
            # "crop <name> <x0> <y0> <x1> <y1>" -- a region shot, pixels of 2560x1440
            $xy = $rest -split '\s+'; Focus-Game $p; Start-Sleep -Milliseconds 300
            Shot-Region $p ($xy[0] + ".png") ([int]$xy[1]) ([int]$xy[2]) ([int]$xy[3]) ([int]$xy[4])
        }
        "census"  {
            # П.15 (4.10, the user: no paging the census -- sort, filter, open a row): "census <name> [sort <column>]
            # [row <n>]". Opens the census from the population panel, sorts by a header column (a second click
            # reverses), shoots the table's top (cropped), and the row's arrow opens that pop group's details.
            # Columns (1836 Britain): pop size, profession, culture, religion, state, workplace, radicals, loyalists,
            # standard of living, political strength, interest groups.
            $cols = @{ size = 0.33; profession = 0.385; culture = 0.448; religion = 0.482; state = 0.52; workplace = 0.565
                radicals = 0.628; loyalists = 0.664; sol = 0.72; political = 0.775; ig = 0.817 }
            $xy = $rest -split '\s+'; $name = $xy[0]; $sort = $null; $row = 0
            for ($i = 1; $i -lt $xy.Count - 1; $i++) { if ($xy[$i] -eq "sort") { $sort = $xy[$i + 1] }; if ($xy[$i] -eq "row") { $row = [int]$xy[$i + 1] } }
            Hover-Window $p 0.75 0.55; Start-Sleep -Milliseconds 400
            Click-Window $p 0.0085 0.461; Start-Sleep -Milliseconds 1800
            Click-Window $p 0.13 0.976; Start-Sleep -Milliseconds 2500
            if ($sort -and $cols[$sort]) { Click-Window $p $cols[$sort] 0.3876; Start-Sleep -Milliseconds 1200 }
            Hover-Window $p 0.95 0.5; Start-Sleep -Milliseconds 500
            # the table's header and first ~16 rows
            Shot-Region $p ($name + "_census.png") 800 540 2200 1000
            if ($row -gt 0) {
                Click-Window $p 0.846 (0.438 + 0.0222 * ($row - 1)); Start-Sleep -Milliseconds 2000
                Hover-Window $p 0.75 0.55; Start-Sleep -Milliseconds 500
                Shot-Region $p ($name + "_popgroup_$row.png") 0 0 640 1440
            }
        }
        "close"   { Close-And-Collect }
        default   { Log "unknown step '$step'" }
    }
}
Log "vic3_ui done: $Do"
