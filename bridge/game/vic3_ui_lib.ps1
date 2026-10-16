<#
Shared helpers of the Victoria 3 sandbox scripts (run_vic3_sandbox.ps1, vic3_ui.ps1):
window focus, keys, clicks and hovers at window fractions, console commands, screenshots,
screen recognition by colour. Dot-source it; the caller sets $OutDir (and $Logs, $t0 for
Save-DebugParts).

A project's own parts come from its hooks file: $env:VIC3_HOOKS, else vic3_hooks.ps1 next to these scripts (a run in
the sandbox VM gets the project's hooks copied there). It may set:
    $ModLogPattern   a regex of the mod's own debug.log lines, gathered at the end into $OutDir\$ModLogFile
    $ModLogFile      (default modlog.txt)
    $PointsFile      vic3_ui.ps1's named hover sets and macros ($TipSets, $Macros)
and define:
    Hook-AfterLoad $p $noModLogs   console commands after the game loaded (a mod's debug logs on or off)
    Hook-FindHeir $tag             the played country is gone: its heir's tag from the mod's log, or $null
    Hook-ShotSteps $own            vic3_ui.ps1 steps for -Shots / "country <TAG>" (the screens to take)
#>
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class W {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk, wScan; public uint dwFlags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Explicit, Size = 40)] public struct INPUT { [FieldOffset(0)] public uint type; [FieldOffset(8)] public KEYBDINPUT ki; }
    [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);
    [StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
    [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO li);
    [DllImport("kernel32.dll")] public static extern uint GetTickCount();
    // Milliseconds of the last keyboard/mouse input of anyone (the user's or ours), GetTickCount clock.
    public static uint LastInput() { LASTINPUTINFO li = new LASTINPUTINFO(); li.cbSize = (uint)Marshal.SizeOf(li); GetLastInputInfo(ref li); return li.dwTime; }
    // Types text as Unicode characters (WM_CHAR), whatever the keyboard layout.
    public static void TypeText(string s) {
        foreach (char c in s) {
            INPUT[] a = new INPUT[2];
            a[0].type = 1; a[0].ki.wScan = c; a[0].ki.dwFlags = 4;
            a[1].type = 1; a[1].ki.wScan = c; a[1].ki.dwFlags = 4 | 2;
            SendInput(2, a, Marshal.SizeOf(typeof(INPUT)));
            System.Threading.Thread.Sleep(15);
        }
    }
}
"@

# Underlined links of a tooltip (5.10): the account cards were hovered at fixed rows, but the rows of the
# currency tooltip move from country to country (standard, wrapped lines, long numbers) -- run r1005_102757 got
# no Swiss card at all. A link's underline is a light grey line 1-2 px high, longer than any run of letters.
Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Collections.Generic;
public static class U {
    // rows (bitmap y) of horizontal light-grey runs at least minLen long that start at x <= maxStart
    public static int[] Underlines(Bitmap b, int minLen, int maxStart) {
        var d = b.LockBits(new Rectangle(0, 0, b.Width, b.Height), ImageLockMode.ReadOnly, PixelFormat.Format24bppRgb);
        var buf = new byte[d.Stride * b.Height];
        System.Runtime.InteropServices.Marshal.Copy(d.Scan0, buf, 0, buf.Length);
        b.UnlockBits(d);
        var rows = new List<int>(); int last = -10;
        for (int y = 0; y < b.Height; y++) {
            int cur = 0, start = 0, best = 0, bestStart = 0;
            for (int x = 0; x < b.Width; x++) {
                int i = y * d.Stride + x * 3; int bl = buf[i], g = buf[i + 1], r = buf[i + 2];
                bool on = r + g + bl > 480 && r > 150 && Math.Abs(r - g) < 30 && Math.Abs(r - bl) < 30;
                if (on) { if (cur == 0) start = x; cur++; if (cur > best) { best = cur; bestStart = start; } } else cur = 0;
            }
            if (best >= minLen && bestStart <= maxStart) { if (y - last > 3) rows.Add(y); last = y; }
        }
        return rows.ToArray();
    }
}
"@

function Log($m) { $l = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m; Write-Host $l; Add-Content (Join-Path $OutDir "run.log") $l }

# The engine keeps only debug.1..5.log (~2.5 MB, about 2 game years of the
# weekly lines): a run of 33 min lost 1836-1837 (run 10, 1.10). A rotated part
# keeps its write time when renamed, so it is saved once under that time.
function Save-DebugParts {
    # error.log rotates too (~0.5 MB a part): in a 3-minute run (4.10) the load errors were gone
    # before the game ran -- its parts go to errparts the same way
    foreach ($kind in @("debug", "error")) {
        $dir = Join-Path $OutDir ($(if ($kind -eq "debug") { "dbgparts" } else { "errparts" }))
        New-Item -ItemType Directory -Force $dir | Out-Null
        Get-ChildItem $Logs -Filter "$kind.*.log" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt $t0 } | ForEach-Object {
            $dst = Join-Path $dir ("{0}.log" -f $_.LastWriteTime.Ticks)
            if (-not (Test-Path $dst)) { Copy-Item $_.FullName $dst -ErrorAction SilentlyContinue }
        }
    }
}

function Get-Game { Get-Process -Name "victoria3" -ErrorAction SilentlyContinue | Select-Object -First 1 }

# Keys and clicks go to whatever window has the focus. Windows may refuse to
# bring the game forward (the user is working in another window): then every
# key would land in the user's window (1.10 morning: "enable_ai all" was typed
# into the user's chat). So nothing is sent unless the game is in front; if
# it cannot be brought forward the run stops.
function Raise-Game($p) {
    if ([W]::GetForegroundWindow() -eq $p.MainWindowHandle) { return $true }
    [W]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
    [W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 400
    if ([W]::GetForegroundWindow() -ne $p.MainWindowHandle) {
        # the ALT trick: a key event lets this process take the foreground
        [W]::keybd_event(0x12, 0x38, 0, [UIntPtr]::Zero); [W]::keybd_event(0x12, 0x38, 2, [UIntPtr]::Zero); Mark-Own
        [W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
        Start-Sleep -Milliseconds 400
    }
    return ([W]::GetForegroundWindow() -eq $p.MainWindowHandle)
}

# The user at the PC (5.10, the user: "watch, don't stop: if the mouse was touched or another window is in
# front, put your queue off by 5 s, and so on until I stop touching; then make sure the game is in front, leave
# every menu (the console too) and go on"). The script marks the time of its own input (Mark-Own); any input
# later than that is the user's (GetLastInputInfo counts both). Before every key, click and hover (Assert-Front)
# the script waits while the user touches the keyboard or mouse, or while another window is in front, in steps
# of 5 s; after 5 quiet seconds it raises the game, closes the console and the open panels (Reset-UI) and goes
# on. Before 5.10 it stole the focus back and stopped only if Windows refused.
# global: the ui: steps of a run are a second copy of this script (vic3_ui.ps1) in the same session -- with a
# script-scoped tick the run took their keys for the user's (5.10, r1005_103836)
if (-not $global:Vic3OwnTick) { $global:Vic3OwnTick = [W]::GetTickCount() }
$script:InReset = $false
$script:WantPaused = $false
function Mark-Own { $global:Vic3OwnTick = [W]::GetTickCount() }
# The user's last input: ms ago, or -1 if there has been none since the script's own last input.
function User-InputAgo {
    $li = [W]::LastInput()
    if ([int64]$li - [int64]$global:Vic3OwnTick -le 300) { return -1 }
    return [int64][W]::GetTickCount() - [int64]$li
}
function User-Busy($p) {
    $ago = User-InputAgo
    return (($ago -ge 0 -and $ago -lt 5000) -or ([W]::GetForegroundWindow() -ne $p.MainWindowHandle))
}
function Wait-User($p) {
    if ($script:InReset -or -not (User-Busy $p)) { return $false }
    Log "the user is at the PC (input or another window in front) - waiting"
    $t = Get-Date; $tries = 0
    while ($true) {
        Start-Sleep 5
        $ago = User-InputAgo
        if ($ago -ge 0 -and $ago -lt 5000) { continue }
        if (Raise-Game $p) { break }
        # quiet, but Windows will not give the game the focus: keep trying for 2 min, then stop
        $tries++
        if ($tries -ge 24) { Log "the game cannot be brought to front - stopping, nothing sent"; throw "game window not in front" }
    }
    Log ("the user left after {0:N0} s - leaving menus, going on" -f ((Get-Date) - $t).TotalSeconds)
    # a "redo" step of vic3_ui.ps1 sees this and takes its piece again from the start (its menu reopened)
    $global:Vic3Interrupted = $true
    Reset-UI $p
    return $true
}

function Focus-Game($p) {
    if (Wait-User $p) { return }
    if (-not (Raise-Game $p)) {
        Log "the game is not in front (another window has the focus) - stopping, nothing sent"
        throw "game window not in front"
    }
}

function Assert-Front($p) {
    Wait-User $p | Out-Null
    if ([W]::GetForegroundWindow() -ne $p.MainWindowHandle) { Focus-Game $p }
}

# Pause right now, without waiting for the user (the user, 5.10: "to pause it may take control without the
# check and press pause quickly"). Space toggles: call it only while the game runs.
function Pause-Now($p) {
    Raise-Game $p | Out-Null
    [W]::keybd_event(0x20, 0x39, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
    [W]::keybd_event(0x20, 0x39, 2, [UIntPtr]::Zero); Mark-Own; Start-Sleep -Milliseconds 300
}

# After the user: the console closed, every panel closed, the game paused if the script wants it paused.
# Escape closes the top panel; with nothing open it opens the game menu -- so Escape until the game menu is
# up, then one Escape more closes it and nothing is left open.
function Reset-UI($p) {
    $script:InReset = $true
    try {
        if (Is-Screen $p "console") { Log "reset: the console is open"; Close-Console $p | Out-Null }
        for ($i = 0; $i -lt 8; $i++) {
            Send-Key 0x1B 0x01; Start-Sleep -Milliseconds 700
            if (Is-Screen $p "escmenu") { Send-Key 0x1B 0x01; Start-Sleep -Milliseconds 700; break }
        }
        if (Is-Screen $p "escmenu") { Log "reset: the game menu stays open" }
        if ($script:WantPaused -and (Is-Advancing $p 6)) { Pause-Now $p; Log "reset: paused again" }
    } finally { $script:InReset = $false }
}

# vk + scan code (DirectInput reads scan codes): Space 0x20/0x39, '5' 0x35/0x06
function Send-Key([byte]$vk, [byte]$scan) {
    Assert-Front (Get-Game)
    [W]::keybd_event($vk, $scan, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [W]::keybd_event($vk, $scan, 2, [UIntPtr]::Zero); Mark-Own
    Start-Sleep -Milliseconds 200
}

# The game's interface scale (GUI.scale of pdx_settings.json; 1 = 100 %). Points and boxes here are measured at ×1 on
# 2560x1440; at another scale the interface grows from where each element is anchored -- a point with an anchor
# ("tl", "tr", "bl", "br", "bc": top / bottom, left / right / centre) moves away from that corner by the scale. The
# main menu, the goals screen and the console (a tool, tools_gui_scale) do not follow GUI.scale. Checked 16.10.2026 at
# ×1.3: the lobby's Start button 0.9215 → 0.898 (bottom-right), Random country 0.25 → 0.324 (bottom-left).
$script:UiScale = 1.0
try {
    $set = Get-Content (Join-Path $env:USERPROFILE "Documents\Paradox Interactive\Victoria 3\pdx_settings.json") -Raw -Encoding UTF8
    if ($set -match '"GUI":\s*\{[^}]*?"scale":\s*"([0-9.]+)"') { $script:UiScale = [double]$Matches[1] }
} catch { }

# A 2560x1440 point (px) moved by the interface scale from its anchor; no anchor -- as is.
function Scale-Px($x, $y, $anchor) {
    $s = $script:UiScale
    if (-not $anchor -or $s -eq 1.0) { return @($x, $y) }
    $ax = if ($anchor -match 'r') { 2560 } elseif ($anchor -match 'l') { 0 } else { 1280 }
    $ay = if ($anchor -match 'b') { 1440 } elseif ($anchor -match 't') { 0 } else { 720 }
    return @(($ax + ($x - $ax) * $s), ($ay + ($y - $ay) * $s))
}

# Left click at a point of the window (fraction of its size; with an anchor -- moved by the interface scale).
function Click-Window($p, $fx, $fy, $anchor = $null) {
    if ($anchor) { $q = Scale-Px ($fx * 2560) ($fy * 1440) $anchor; $fx = $q[0] / 2560; $fy = $q[1] / 1440 }
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    Assert-Front $p
    [W]::SetCursorPos([int]($r.L + ($r.R - $r.L) * $fx), [int]($r.T + ($r.B - $r.T) * $fy)) | Out-Null
    Start-Sleep -Milliseconds 150
    [W]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
    [W]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero); Mark-Own; Start-Sleep -Milliseconds 300
}

# A left click with Ctrl held (observer mode: Ctrl + click on a country observes it). Nothing may run between Ctrl down
# and up: a wait for the user there once pressed Escape with Ctrl held -- Ctrl + Esc opened the Windows Start menu over
# the game (16.10.2026). So the window is checked first, then Ctrl, the click and Ctrl up in one go.
function Ctrl-Click-Window($p, $fx, $fy) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    Assert-Front $p
    [W]::SetCursorPos([int]($r.L + ($r.R - $r.L) * $fx), [int]($r.T + ($r.B - $r.T) * $fy)) | Out-Null
    Start-Sleep -Milliseconds 150
    [W]::keybd_event(0x11, 0x1D, 0, [UIntPtr]::Zero)
    try {
        Start-Sleep -Milliseconds 80
        [W]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
        [W]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 80
    } finally { [W]::keybd_event(0x11, 0x1D, 2, [UIntPtr]::Zero); Mark-Own }
    Start-Sleep -Milliseconds 300
}

# Observer mode (the console "observe"): the game runs for every country by the AI, nobody plays. Observing a country
# (its top bar, panels, tooltips as for its player) is a Ctrl + click on its land; the observer picks no country by
# tag, so: "tag <TAG>" (the camera jumps to its capital, in the middle of the window), "observe", Ctrl + click the
# middle. Checked in the game 16.10.2026 (1.13.11): "observe" alone shows "no country selected"; after "tag" the
# capital is at the middle of the window. "observe" toggles, and while observing "tag" neither leaves observer mode nor
# moves the camera (r1016_obs4: the second country's "tag GBR", "observe" printed "Ending observe mode", GBR was played;
# r1016_obs5, "tag GBR" alone: the view stayed on SWI). So from observer mode: "observe" first (back to playing), then
# as from the start; the state is a global (the ui: steps run in the same session).
if ($null -eq $global:Vic3Observing) { $global:Vic3Observing = $false }
function Observe-Country($p, $tag) {
    if ($global:Vic3Observing -and $tag) { Console-Cmd $p "observe"; Start-Sleep 3; $global:Vic3Observing = $false; $p = Get-Game }
    if ($tag) { Console-Cmd $p "tag $tag"; Start-Sleep 3 }
    if (-not $global:Vic3Observing) { Console-Cmd (Get-Game) "observe"; Start-Sleep 3; $global:Vic3Observing = $true }
    $p = Get-Game
    if (Is-Screen $p "console") { Log "the console is open"; Close-Console $p | Out-Null }
    if ($tag) { Ctrl-Click-Window $p 0.5 0.5; Start-Sleep 2; Log "observing $tag" } else { Log "observer mode" }
}

# Console (debug_mode): the key left of 1 (VK_OEM_3, scan 0x29), clear the line
# (if the console was still open the key typed a character into it), type,
# Enter. Closing: while the input line has the focus neither Escape nor the
# console key close it (run 2: a stray character; run 3, 1.10: the console stayed
# open and the speed key "5" went into it, the game never ran). So a click on
# the map takes the focus off the line, then the console key closes it.
function Console-Cmd($p, $cmd) {
    Focus-Game $p
    Send-Key 0xC0 0x29
    Start-Sleep -Milliseconds 500
    # the key toggles: if the console was open already, it just shut -- open it again (r1005_110005: "tag GBR" was
    # typed into the map and lost)
    if (-not (Is-Screen $p "console")) { Send-Key 0xC0 0x29; Start-Sleep -Milliseconds 500 }
    if (-not (Is-Screen $p "console")) { Log "console: did not open - '$cmd' not sent"; return }
    for ($i = 0; $i -lt 3; $i++) { Send-Key 0x08 0x0E }
    Assert-Front $p
    [W]::TypeText($cmd); Mark-Own
    Start-Sleep -Milliseconds 200
    Send-Key 0x0D 0x1C
    Start-Sleep -Milliseconds 800
    Close-Console $p | Out-Null
    Log "console: $cmd"
}

# Click on the map + the console key, then look whether the console is gone; again up to 3 times
# (5.10: the console stayed open twice running, the speed key "5" went into its line).
function Close-Console($p) {
    for ($i = 0; $i -lt 3; $i++) {
        # the console key toggles: pressed with the console shut, it opens it (r1005_110005) -- look first
        if (-not (Is-Screen $p "console")) { return $true }
        Click-Window $p 0.62 0.45
        Send-Key 0xC0 0x29
        Start-Sleep -Milliseconds 600
        if (-not (Is-Screen $p "console")) { return $true }
        Log "the console is still open - closing again"
    }
    Log "the console stays open"
    return $false
}

function Shot($p, $name) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $h = $r.B - $r.T
    if ($w -le 0 -or $h -le 0) { return }
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
    $f = Join-Path $OutDir $name
    $bmp.Save($f); $g.Dispose(); $bmp.Dispose()
    Log "screenshot $f"
}

# Which screen is up, from the mean colour of a box (2560x1440 coordinates, scaled to the
# window). Measured 2026-10-01 on the screenshots of runs 14-15: the main menu's "New game"
# button is dark green, the goals screen's top-left corner near black, the lobby's ocean light,
# and in a loaded game the left column of icons is (76,68,68) for every country (the top-left
# corner is the flag, different per country).
$Screens = @{
    menu  = @{ box = @(340, 545, 730, 590); rgb = @(33, 46, 42); tol = 15 }
    goals = @{ box = @(5, 5, 130, 90); rgb = @(33, 31, 32); tol = 15 }
    # the lobby: the dark right panel AND the grey "Start" button -- run 17 (1.10 night) took a
    # loading screen's light stadium for the lobby's sea and clicked into the void
    lobby = @{ box = @(2200, 300, 2540, 900); rgb = @(47, 52, 49); tol = 15; box2 = @(2180, 1395, 2540, 1430); rgb2 = @(53, 53, 53); tol2 = 15
               anchor = "tr"; anchor2 = "br" }
    # the column's skin depends on the country's interface style: (76, 68, 68) for most, (92, 84, 65) for
    # Croatia -- Austria's style (4.10, the user; a new game waited the full 400 s) -- tolerance 25
    # Two halves of the column, each on its own: 5.10 (run r1005_044523) a loading screen's painting -- beige
    # above, a dark suit below -- averaged (80, 63, 44) over the whole column, inside the tolerance, and the
    # console commands went in while the game was still loading; its halves are (132, 108, 80) and (28, 18, 8)
    # and the date panel at the top right (82, 73, 70): r1005_103836 took a Japanese loading painting for the
    # game -- both halves of the column inside the tolerance; there the panel is (166, 179, 178), the lobby (58, 42, 46)
    game  = @{ box = @(5, 210, 45, 595); rgb = @(76, 68, 68); tol = 25; box2 = @(5, 595, 45, 980); rgb2 = @(76, 68, 68); tol2 = 25
               box3 = @(2200, 10, 2540, 60); rgb3 = @(82, 73, 70); tol3 = 20; anchor = "tl"; anchor2 = "tl"; anchor3 = "tr" }
    # the open console: its log area is a flat dark grey (45, 50, 52); the map there is (59, 75, 92), the
    # budget panel (63, 64, 58) -- 5.10, screenshots of r1005_042928 and r1005_044523
    # and even (spread 3; a state panel or a dark sea 18..61), with the dark input line below it (26, 29, 30): r1005_110005
    # took a state panel for the console, "closed" it with the console key -- which opened it -- and "tag GBR" was lost
    # the log's lines fill the console from the top: the box sits just above the input line (r1016_obs6: after ~12 lines
    # the old 250..650 box held text, std 9.3 > 8, the open console was not seen and stayed over the screens)
    console = @{ box = @(120, 560, 500, 720); rgb = @(39, 44, 45); tol = 8; flat = 8; box2 = @(30, 745, 520, 775); rgb2 = @(26, 29, 30); tol2 = 8; flat2 = 6 }
    # the game menu (Escape with nothing open) -- calibrated on the screenshots of run CAL (5.10)
    # the game menu (Escape with nothing open; "Вернуться к игре" ...): the HUD is gone -- the left icon column turns
    # dark (27, 26, 21), the backdrop under the buttons (39, 34, 29); the game (75, 68, 68) / (57..68), the console
    # (43, 48, 50) / (47, 49, 50) -- measured on r1005_104528 cal_esc1 (5.10)
    # «Конец игры» (the player's country gone): the bottom row of four dark teal buttons, measured at their text-free
    # left ends -- (23, 35, 32) and (22, 33, 29), flat (r1013_180405 stall_182947: the game (33, 36, 35) / (43, 45, 36),
    # uneven; the lobby (41, 55, 51))
    gameover = @{ box = @(40, 1398, 110, 1426); rgb = @(23, 35, 32); tol = 8; flat = 6; box2 = @(1295, 1398, 1340, 1426); rgb2 = @(22, 33, 29); tol2 = 8; flat2 = 6
                  anchor = "bl"; anchor2 = "bc" }
    escmenu = @{ box = @(5, 210, 45, 595); rgb = @(27, 26, 21); tol = 10; box2 = @(40, 420, 360, 880); rgb2 = @(39, 34, 29); tol2 = 10
                 anchor = "tl"; anchor2 = "tl" }
}
function Is-Screen($p, $name) {
    $sc = $Screens[$name]
    if (-not (Is-Box $p (Scale-Box $sc.box $sc.anchor) $sc.rgb $sc.tol $sc.flat)) { return $false }
    if ($sc.box2 -and -not (Is-Box $p (Scale-Box $sc.box2 $sc.anchor2) $sc.rgb2 $sc.tol2 $sc.flat2)) { return $false }
    if ($sc.box3 -and -not (Is-Box $p (Scale-Box $sc.box3 $sc.anchor3) $sc.rgb3 $sc.tol3)) { return $false }
    return $true
}
# A box (x0, y0, x1, y1 of 2560x1440) moved by the interface scale from its anchor.
function Scale-Box($box, $anchor) {
    $a = Scale-Px $box[0] $box[1] $anchor; $b = Scale-Px $box[2] $box[3] $anchor
    return @($a[0], $a[1], $b[0], $b[1])
}
# $flat: if set, the box must also be even -- the spread (std) of its brightness at most $flat
function Is-Box($p, $box, $rgb, $tol, $flat = $null) {
    $sc = @{ box = $box; rgb = $rgb; tol = $tol }
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $x0 = [int]($sc.box[0] * $kx); $y0 = [int]($sc.box[1] * $ky)
    $w = [Math]::Max(1, [int](($sc.box[2] - $sc.box[0]) * $kx)); $h = [Math]::Max(1, [int](($sc.box[3] - $sc.box[1]) * $ky))
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + $x0, $r.T + $y0, 0, 0, $bmp.Size)
    $sum = @(0, 0, 0); $n = 0; $l1 = 0.0; $l2 = 0.0
    for ($x = 0; $x -lt $w; $x += 3) { for ($y = 0; $y -lt $h; $y += 3) {
        $c = $bmp.GetPixel($x, $y); $sum[0] += $c.R; $sum[1] += $c.G; $sum[2] += $c.B; $n++
        $l = ($c.R + $c.G + $c.B) / 3.0; $l1 += $l; $l2 += $l * $l } }
    $g.Dispose(); $bmp.Dispose()
    for ($i = 0; $i -lt 3; $i++) { if ([Math]::Abs($sum[$i] / $n - $sc.rgb[$i]) -gt $sc.tol) { return $false } }
    if ($null -ne $flat) { $m = $l1 / $n; if ([Math]::Sqrt([Math]::Max(0, $l2 / $n - $m * $m)) -gt $flat) { return $false } }
    return $true
}
# Waits until the screen is up (polled every 3 s), at most $max seconds; then $settle seconds.
# The colour is read off the screen, so the game must be in front: at launch Windows may leave
# another window on top (4.10 night: Obsidian, the menu was "seen" in its colours; 4.10 evening:
# the game started behind the user's window). Each poll raises the game first; a box is only
# trusted while the game is in front.
function Wait-Screen($names, $max, $settle) {
    $t = Get-Date
    while (((Get-Date) - $t).TotalSeconds -lt $max) {
        $p = Get-Game
        # while the user touches the keyboard or mouse the game is not pulled forward (5.10)
        $ago = User-InputAgo
        $busy = ($ago -ge 0 -and $ago -lt 5000)
        if ($p -and $p.MainWindowHandle -ne 0 -and -not $busy -and (Raise-Game $p)) {
            # several names: the first one seen is returned (a save may open in the lobby, 5.10)
            foreach ($name in @($names)) {
                if (Is-Screen $p $name) { Log ("screen '$name' after {0:N0} s" -f ((Get-Date) - $t).TotalSeconds); Start-Sleep $settle; return $name }
            }
        }
        if ($t0) { Save-DebugParts }
        Start-Sleep 3
    }
    Log "screen '$(@($names) -join '/')' not seen in $max s - going on"
    return $false
}

# debug.log is buffered while the game runs and autosaves may be half-yearly,
# so progress is read from the screen: the date text at the top right of the
# window (2560x1440: about 330..190 px from the right edge, 2..34 px down).
function Date-Crop($p) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $s = $script:UiScale  # the date panel is anchored top-right
    $bmp = New-Object System.Drawing.Bitmap ([int](160 * $s)), ([int](32 * $s))
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.R - [int](340 * $s), $r.T + [int](2 * $s), 0, 0, $bmp.Size)
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
    [Convert]::ToBase64String($ms.ToArray())
}

# True if the date on screen changes within $sec seconds.
function Is-Advancing($p, $sec) {
    Focus-Game $p
    $a = Date-Crop $p
    for ($i = 0; $i -lt $sec; $i += 4) { Start-Sleep 4; if ((Date-Crop $p) -ne $a) { return $true } }
    return $false
}

# The same without raising the game and without waiting for the user (the run's loop while the user watches): the date
# as the screen shows it -- with another window over it, it reads as standing.
function Is-AdvancingPassive($p, $sec) {
    $a = Date-Crop $p
    for ($i = 0; $i -lt $sec; $i += 4) { Start-Sleep 4; if ((Date-Crop $p) -ne $a) { return $true } }
    return $false
}

# The n-th (1-based, top down) underlined link of the tooltip at the window's top left (x 0..900, y 150..1300 of
# 2560x1440): returns @(fx, fy) of the link's text, or $null when there are fewer links.
function Find-Link($p, $n) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $x0 = 0; $y0 = [int](150 * $ky); $w = [int](900 * $kx); $h = [int](1150 * $ky)
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + $x0, $r.T + $y0, 0, 0, $bmp.Size)
    $rows = [U]::Underlines($bmp, [int](90 * $kx), [int](90 * $kx))
    $g.Dispose(); $bmp.Dispose()
    if ($rows.Count -lt $n) { Log "links: $($rows.Count) found, #$n missing"; return $null }
    $y = $y0 + $rows[$n - 1] - [int](8 * $ky)
    return @((80 * $kx / ($r.R - $r.L)), ($y / ($r.B - $r.T)), $rows.Count)
}

# Moves the mouse to a point of the window (fraction of its size) without clicking: tooltips.
function Hover-Window($p, $fx, $fy) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    Assert-Front $p
    [W]::SetCursorPos([int]($r.L + ($r.R - $r.L) * $fx), [int]($r.T + ($r.B - $r.T) * $fy)) | Out-Null; Mark-Own
    $script:LastHover = @($fx, $fy)
}

# Closes the game and gathers the logs written since $t0 into $OutDir: every log file, the
# rotated debug parts, and the mod's own lines ($ModLogPattern of the hooks) into $ModLogFile.
function Close-And-Collect {
    $p = Get-Game
    if ($p) {
        Log "closing the game"
        $p.CloseMainWindow() | Out-Null
        if (-not $p.WaitForExit(30000)) { Log "force stop"; Stop-Process -Id $p.Id -Force }
    }
    Start-Sleep 2
    Get-ChildItem $Logs -File | Where-Object { $_.LastWriteTime -gt $t0 } | ForEach-Object { Copy-Item $_.FullName (Join-Path $OutDir $_.Name) }
    # debug.log rotates at ~512 KB and keeps only debug.1..5.log: the parts saved
    # during the run (dbgparts) + the last ones, oldest first, each part once (by its content: equal lines of different
    # pops or weeks are kept)
    Save-DebugParts
    $parts = @(Get-ChildItem (Join-Path $OutDir "dbgparts") -Filter "*.log" -ErrorAction SilentlyContinue | Sort-Object Name) +
        @(Get-ChildItem $OutDir -Filter "debug.log")
    if ($parts -and $script:ModLogPattern) {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]'
        $parts = @($parts | Where-Object { $seen.Add((Get-FileHash $_.FullName -Algorithm MD5).Hash) })
        Select-String -Path ($parts | ForEach-Object FullName) -Pattern $script:ModLogPattern |
            ForEach-Object { $_.Line -replace "^\[[^\]]*\]\[[^\]]*\]: ", '' } |
            Set-Content -Encoding utf8 (Join-Path $OutDir $script:ModLogFile)
    }
}

# Mouse wheel at a point of the window: $notches > 0 up, < 0 down (120 per notch).
function Scroll-Window($p, $fx, $fy, $notches) {
    Hover-Window $p $fx $fy
    Start-Sleep -Milliseconds 150
    $n = [Math]::Abs([int]$notches); $d = if ($notches -lt 0) { -120 } else { 120 }
    for ($i = 0; $i -lt $n; $i++) { [W]::mouse_event(0x0800, 0, 0, [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$d), 0), [UIntPtr]::Zero); Mark-Own; Start-Sleep -Milliseconds 80 }
    Start-Sleep -Milliseconds 400
}

# П.15 (4.10, the user: "the script must be able to see everything"): the collapsed section headers of a
# panel ("› Показать список", "› Займы"): a gold chevron at the panel's left edge. Collapsed "›" is taller than
# wide, expanded "⌄" wider than tall. Returns the window-fraction y of each collapsed chevron, top down.
# $x0..$x1, $y0..$y1 -- pixels of a 2560x1440 window (scaled to the real size).
function Find-Collapsed($p, $x0, $x1, $y0, $y1) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $w = [int](($x1 - $x0) * $kx); $h = [int](($y1 - $y0) * $ky)
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + [int]($x0 * $kx), $r.T + [int]($y0 * $ky), 0, 0, $bmp.Size)
    $rows = @{}
    for ($y = 0; $y -lt $h; $y++) {
        for ($x = 0; $x -lt $w; $x++) {
            $c = $bmp.GetPixel($x, $y)
            if ($c.R -gt 150 -and $c.G -gt 100 -and ($c.R - $c.B) -gt 70) {
                if (-not $rows.ContainsKey($y)) { $rows[$y] = @($x, $x, 1) }
                else { $rows[$y] = @([Math]::Min($rows[$y][0], $x), [Math]::Max($rows[$y][1], $x), ($rows[$y][2] + 1)) }
            }
        }
    }
    $g.Dispose(); $bmp.Dispose()
    # clusters of consecutive rows
    $out = @(); $ys = $rows.Keys | Sort-Object
    # "›" (4.10, Britain's budget): 18 px tall, 11 wide, a thin stroke (~1/3 of its box); "⌄" 17 wide, 12 tall;
    # a flag in a table is a filled block
    $start = $null; $prev = $null; $minx = 9999; $maxx = -1; $cnt = 0
    foreach ($y in ($ys + @(99999))) {
        if ($null -ne $prev -and $y -gt $prev + 2) {
            $hh = ($prev - $start + 1) / $ky; $ww = ($maxx - $minx + 1) / $kx; $fill = $cnt / [double](($prev - $start + 1) * ($maxx - $minx + 1))
            # the shape of ">": the middle rows reach further right than the top and the bottom ones (the orange
            # first letters of table cells -- "С", "М", "Д" -- passed the size test, 4.10)
            $n3 = [Math]::Max(1, [int](($prev - $start + 1) / 4))
            $cx = { param($a, $b) $v = @(); for ($q = $a; $q -le $b; $q++) { if ($rows.ContainsKey($q)) { $v += ($rows[$q][0] + $rows[$q][1]) / 2.0 } }; if ($v.Count) { ($v | Measure-Object -Average).Average } else { 0 } }
            $ct = & $cx $start ($start + $n3 - 1); $cb = & $cx ($prev - $n3 + 1) $prev
            $mid = [int](($start + $prev) / 2); $cm = & $cx ($mid - 1) ($mid + 1)
            $arrow = ($cm -gt $ct + 2 * $kx) -and ($cm -gt $cb + 2 * $kx)
            if ($arrow -and $hh -ge 12 -and $hh -le 28 -and $ww -ge 5 -and $ww -le 18 -and $hh -gt 1.3 * $ww -and $fill -lt 0.55) {
                $out += (($y0 + ($start + $prev) / 2.0 / $ky) / 1440.0)
            }
            $start = $null; $minx = 9999; $maxx = -1; $cnt = 0
        }
        if ($y -eq 99999) { break }
        if ($null -eq $start) { $start = $y }
        $minx = [Math]::Min($minx, $rows[$y][0]); $maxx = [Math]::Max($maxx, $rows[$y][1]); $cnt += $rows[$y][2]; $prev = $y
    }
    return $out
}

# П.15: a cheap signature of a screen region (the panel), to tell when scrolling stopped moving it.
function Region-Sig($p, $x0, $x1, $y0, $y1) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $w = [int](($x1 - $x0) * $kx); $h = [int](($y1 - $y0) * $ky)
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + [int]($x0 * $kx), $r.T + [int]($y0 * $ky), 0, 0, $bmp.Size)
    $sb = New-Object System.Text.StringBuilder
    for ($y = 0; $y -lt $h; $y += 23) { for ($x = 0; $x -lt $w; $x += 29) { $c = $bmp.GetPixel($x, $y); [void]$sb.Append([int](($c.R + $c.G + $c.B) / 24)) } }
    $g.Dispose(); $bmp.Dispose()
    return $sb.ToString()
}

# П.15: the panel's scrollbar thumb (teal, x ~608 px of 2560 for the left panels). Returns @(top, bottom) in
# window fractions, or $null.
function Find-Thumb($p, $xpx, $y0, $y1) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $h = [int](($y1 - $y0) * $ky)
    $bmp = New-Object System.Drawing.Bitmap 5, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + [int](($xpx - 2) * $kx), $r.T + [int]($y0 * $ky), 0, 0, $bmp.Size)
    $top = -1; $bot = -1
    for ($y = 0; $y -lt $h; $y++) {
        $c = $bmp.GetPixel(2, $y)
        if ($c.G -gt $c.R + 15 -and $c.B -gt $c.R + 10 -and $c.G -gt 70) { if ($top -lt 0) { $top = $y }; $bot = $y }
    }
    $g.Dispose(); $bmp.Dispose()
    if ($top -lt 0) { return $null }
    return @((($y0 + $top / $ky) / 1440.0), (($y0 + $bot / $ky) / 1440.0))
}
# Drag with the left button from one point to another (window fractions), in small steps.
function Drag-Window($p, $fx, $fy, $tx, $ty) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    Assert-Front $p
    $W = $r.R - $r.L; $H = $r.B - $r.T
    [W]::SetCursorPos([int]($r.L + $W * $fx), [int]($r.T + $H * $fy)) | Out-Null; Start-Sleep -Milliseconds 150
    [W]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 100
    for ($i = 1; $i -le 10; $i++) {
        $x = $fx + ($tx - $fx) * $i / 10; $y = $fy + ($ty - $fy) * $i / 10
        [W]::SetCursorPos([int]($r.L + $W * $x), [int]($r.T + $H * $y)) | Out-Null; Start-Sleep -Milliseconds 30
    }
    Start-Sleep -Milliseconds 100
    [W]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero); Mark-Own; Start-Sleep -Milliseconds 300
}

# П.15 (the user: "you page by ~20% -- the overlap is far too much"): a row profile of a region -- one number a
# pixel row -- and the shift between two profiles, to measure how far the content actually moved.
function Row-Profile($p, $x0, $x1, $y0, $y1) {
    # 6 bands a pixel row: rows of a table look alike as one sum, not as six
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $w = [int](($x1 - $x0) * $kx); $h = [int](($y1 - $y0) * $ky)
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + [int]($x0 * $kx), $r.T + [int]($y0 * $ky), 0, 0, $bmp.Size)
    $bw = [int]($w / 6)
    $prof = New-Object 'int[]' ($h * 6)
    for ($y = 0; $y -lt $h; $y++) { for ($b = 0; $b -lt 6; $b++) { $s = 0; for ($x = $b * $bw; $x -lt ($b + 1) * $bw; $x += 5) { $c = $bmp.GetPixel($x, $y); $s += $c.R + $c.G + $c.B }; $prof[$y * 6 + $b] = $s } }
    $g.Dispose(); $bmp.Dispose()
    return ,$prof
}
# The content moved up by d rows: new[y] ~ old[y + d]. Returns @(d, quality): quality = the second best error
# (more than 6 rows away) / the best one -- under 1.5 the match is not trusted.
function Profile-Shift($old, $new) {
    $n = [int]($old.Length / 6); $errs = @{}
    for ($d = 0; $d -le $n - 60; $d += 2) {
        $err = 0.0; $cnt = 0
        for ($y = 0; $y + $d -lt $n; $y += 3) { for ($b = 0; $b -lt 6; $b++) { $e = $new[$y * 6 + $b] - $old[($y + $d) * 6 + $b]; $err += [Math]::Abs($e) }; $cnt++ }
        $errs[$d] = $err / $cnt
    }
    $best = ($errs.GetEnumerator() | Sort-Object Value | Select-Object -First 1)
    $second = ($errs.GetEnumerator() | Where-Object { [Math]::Abs($_.Key - $best.Key) -gt 6 } | Sort-Object Value | Select-Object -First 1)
    $q = if ($best.Value -gt 0) { $second.Value / $best.Value } else { 99 }
    return @($best.Key, $q)
}

# П.15 (the user 4.10: "optimize the script for tokens"): a shot of a region only (pixels of a 2560x1440 window).
function Shot-Region($p, $name, $x0, $y0, $x1, $y1) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $kx = ($r.R - $r.L) / 2560.0; $ky = ($r.B - $r.T) / 1440.0
    $w = [int](($x1 - $x0) * $kx); $h = [int](($y1 - $y0) * $ky)
    if ($w -le 0 -or $h -le 0) { return }
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L + [int]($x0 * $kx), $r.T + [int]($y0 * $ky), 0, 0, $bmp.Size)
    $f = Join-Path $OutDir $name
    $bmp.Save($f); $g.Dispose(); $bmp.Dispose()
    Log "screenshot $f"
}

# the project's hooks (see the header)
$script:ModLogPattern = ""; $script:ModLogFile = "modlog.txt"; $script:PointsFile = ""
$HooksFile = if ($env:VIC3_HOOKS) { $env:VIC3_HOOKS } else { Join-Path $PSScriptRoot "vic3_hooks.ps1" }
if (Test-Path $HooksFile) { . $HooksFile }
