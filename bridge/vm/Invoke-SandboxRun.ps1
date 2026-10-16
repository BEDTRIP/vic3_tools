<#
.SYNOPSIS
Runs a game run script inside the sandbox VM and brings its output back to the host.

.DESCRIPTION
The host keeps the repos, the mods and the tools; the guest only has Windows, Steam and the game
(Initialize-SandboxGuest.ps1). For one run this script:

  1. checks the guest answers and the game is not running there;
  2. copies the *.ps1 files of -ScriptDir (default: bridge\game of this repo, the game scripts) and of -HooksDir (a
     project's vic3_hooks.ps1 and its points: its mod's log lines, commands after loading, screens) to
     C:\vic3tools\run in the guest;
  3. mirrors every mod of -ContentLoad (the game's content_load.json format, host paths) into
     C:\vic3tools\mods\<folder> in the guest -- only changed files travel, as one zip -- and writes the guest's
     content_load.json with the guest paths;
  4. copies the host's game settings (pdx_settings.json) and key bindings, and
     -StartSave from the host's "save games" into the guest's, if given;
  5. starts -Script with the parameters -ParamsJson in the guest's console session (a scheduled task: the game
     needs the desktop, PowerShell Direct itself lives in session 0) with -OutDir C:\vic3tools\runs\<id>;
  6. while it runs, prints the new lines of its output; at the end copies the guest's run folder to -OutDir and
     the saves the run wrote to -OutDir\saves (with -FetchSaves).

The exit code is the run script's.

A test bench: a run with "KeepOpen": true leaves the game paused; then -WithGame -Script vic3_ui.ps1
-ParamsJson '{"Do": "wait 3; shot after"}' sends the mod files changed since (the game in debug mode re-reads
them), takes the steps in the guest's session and brings the screenshots back; "Do": "close" ends it.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File bridge\vm\Invoke-SandboxRun.ps1 -HooksDir ..\my_mod\tools `
    -Script run_vic3_sandbox.ps1 -OutDir C:\runs\r1 -ParamsJson C:\runs\r1.json   # {"RunMinutes": 5, "NewGame": true}
#>
param(
    [string]$ScriptDir = (Join-Path (Split-Path $PSScriptRoot) "game"),
    # a project's hooks for the game scripts (vic3_hooks.ps1 and the files it uses), copied next to them
    [string]$HooksDir = "",
    [string]$Script = "run_vic3_sandbox.ps1",
    [Parameter(Mandatory)] [string]$OutDir,
    # the run script's parameters as a JSON object, or a .json file with it (Windows' command line eats the quotes
    # of an inline JSON passed from PowerShell)
    [string]$ParamsJson = "{}",
    # content_load.json to run with; default: the host's (the mods the launcher started last)
    [string]$ContentLoad = "",
    [string]$StartSave = "",
    [switch]$FetchSaves,
    # a step on a game left open (run_vic3_sandbox.ps1 -KeepOpen): -Script vic3_ui.ps1; changed mod files still travel
    [switch]$WithGame,
    # the guest's interface scale (GUI.scale) and language (l_english, l_russian…) instead of the host's
    [string]$GuiScale = "",
    [string]$Language = "",
    [string]$Name = "vic3-sandbox",
    [string]$CredentialPath = (Join-Path $env:LOCALAPPDATA "vic3tools\vm-cred.xml"),
    [int]$TimeoutMinutes = 180
)
$ErrorActionPreference = "Stop"
$HostDocs = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Paradox Interactive\Victoria 3"
if (-not $ContentLoad) { $ContentLoad = Join-Path $HostDocs "content_load.json" }
$Guest = "C:\vic3tools"
$RunId = Split-Path $OutDir -Leaf
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Say($msg) { Write-Host "[$(Get-Date -Format HH:mm:ss)] vm: $msg" }

$cred = Import-Clixml $CredentialPath
if ((Get-VM -Name $Name).State -ne "Running") { Say "starting the VM"; Start-VM -Name $Name }
$session = $null
$end = (Get-Date).AddMinutes(5)
while (-not $session) {
    try { $session = New-PSSession -VMName $Name -Credential $cred -ErrorAction Stop }
    catch { if ((Get-Date) -gt $end) { throw "the guest does not answer over PowerShell Direct" }; Start-Sleep 5 }
}
try {
    $probe = {
        $end = (Get-Date).AddMinutes(3)
        while (-not (Get-Process explorer -ErrorAction SilentlyContinue) -and (Get-Date) -lt $end) { Start-Sleep 3 }
        @{ desktop = [bool](Get-Process explorer -ErrorAction SilentlyContinue)
           game = [bool](Get-Process victoria3 -ErrorAction SilentlyContinue)
           # "Disc": the session lost its console (a VMConnect window was opened and closed); screenshots fail there
           active = ((query user 2>&1) -join " ") -match "\bActive\b"
           docs = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Paradox Interactive\Victoria 3" }
    }
    $ready = Invoke-Command -Session $session -ScriptBlock $probe
    if ($ready.desktop -and -not $ready.active -and -not $ready.game) {
        # autologon puts the session back on the console after a restart from inside (never Restart-VM -Force)
        Say "the guest's session is disconnected - restarting the guest from inside"
        Invoke-Command -Session $session -ScriptBlock { Restart-Computer -Force }
        Remove-PSSession $session; $session = $null
        Start-Sleep 30
        $end = (Get-Date).AddMinutes(6)
        while (-not $session) {
            try { $session = New-PSSession -VMName $Name -Credential $cred -ErrorAction Stop }
            catch { if ((Get-Date) -gt $end) { throw "the guest did not come back after the restart" }; Start-Sleep 5 }
        }
        $ready = Invoke-Command -Session $session -ScriptBlock $probe
    }
    if (-not $ready.active) { throw "the guest's session is not on the console (query user: not Active)" }
    if (-not $ready.desktop) { throw "no desktop session in the guest (autologon: Initialize-SandboxGuest.ps1)" }
    if ($ready.game -and -not $WithGame) { throw "Victoria 3 is already running in the guest" }
    if ($WithGame -and -not $ready.game) { throw "no game open in the guest (start one with -KeepOpen)" }
    $GuestDocs = $ready.docs

    # 2. scripts
    Invoke-Command -Session $session -ScriptBlock { param($g, $id)
        Remove-Item "$g\run", "$g\runs\$id" -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force "$g\run", "$g\mods", "$g\runs\$id" | Out-Null
    } -ArgumentList $Guest, $RunId
    foreach ($f in Get-ChildItem $ScriptDir -Filter *.ps1) { Copy-Item $f.FullName "$Guest\run\" -ToSession $session }
    Say "scripts: $((Get-ChildItem $ScriptDir -Filter *.ps1).Count) files from $ScriptDir"
    if ($HooksDir) {
        foreach ($f in Get-ChildItem $HooksDir -Filter *.ps1) { Copy-Item $f.FullName "$Guest\run\" -ToSession $session }
        Say "hooks: $((Get-ChildItem $HooksDir -Filter *.ps1).Count) files from $HooksDir"
    }

    # 3. mods: mirror each into the guest, changed files only (by size and write time), extra files removed.
    #    The changed files travel as one zip (.NET writes non-Latin names as UTF-8; Windows tar loses them), and
    #    the write times are set after unpacking (zip keeps them to 2 s).
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $cl = Get-Content $ContentLoad -Raw -Encoding UTF8 | ConvertFrom-Json
    $guestMods = @()
    foreach ($m in @($cl.enabledMods)) {
        $src = $m.path
        if (-not (Test-Path -LiteralPath $src)) { throw "mod folder not found on the host: $src" }
        $leaf = Split-Path $src -Leaf
        $dst = "$Guest\mods\$leaf"
        $guestMods += $dst
        $theirs = Invoke-Command -Session $session -ScriptBlock { param($d)
            $h = @{}
            if (Test-Path -LiteralPath $d) {
                $n = $d.Length + 1
                Get-ChildItem -LiteralPath $d -Recurse -File -Force | ForEach-Object {
                    $h[$_.FullName.Substring($n)] = "$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }
            }
            $h
        } -ArgumentList $dst
        $n = (Resolve-Path -LiteralPath $src).Path.Length + 1
        $mine = @{}
        $times = @{}
        Get-ChildItem -LiteralPath $src -Recurse -File -Force | Where-Object { $_.FullName.Substring($n) -notmatch '^(\.git|_to_delete)(\\|$)' } |
            ForEach-Object {
                $rel = $_.FullName.Substring($n)
                $mine[$rel] = "$($_.Length)|$($_.LastWriteTimeUtc.Ticks)"
                $times[$rel] = $_.LastWriteTimeUtc.Ticks
            }
        $changed = @($mine.Keys | Where-Object { $theirs[$_] -ne $mine[$_] })
        $gone = @($theirs.Keys | Where-Object { -not $mine.ContainsKey($_) })
        if ($changed.Count) {
            $zipPath = Join-Path $env:TEMP "vic3vm_$RunId.zip"
            Remove-Item -LiteralPath $zipPath -ErrorAction SilentlyContinue    # left by a failed attempt
            $zip = [System.IO.Compression.ZipFile]::Open($zipPath, "Create")
            try {
                foreach ($rel in $changed) {
                    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $src $rel), ($rel -replace '\\', '/'),
                        [System.IO.Compression.CompressionLevel]::NoCompression) | Out-Null
                }
            } finally { $zip.Dispose() }
            Copy-Item -LiteralPath $zipPath "$Guest\mods\_in.zip" -ToSession $session
            $sent = @{}; foreach ($rel in $changed) { $sent[$rel] = $times[$rel] }
            Invoke-Command -Session $session -ScriptBlock { param($d, $z, $sent)
                Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
                $zip = [System.IO.Compression.ZipFile]::OpenRead($z)
                try {
                    foreach ($e in $zip.Entries) {
                        $rel = $e.FullName -replace '/', '\'
                        $to = Join-Path $d $rel
                        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to)) | Out-Null
                        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $to, $true)
                        [IO.File]::SetLastWriteTimeUtc($to, [DateTime]::new([long]$sent[$rel], [DateTimeKind]::Utc))
                    }
                } finally { $zip.Dispose() }
                Remove-Item -LiteralPath $z
            } -ArgumentList $dst, "$Guest\mods\_in.zip", $sent
            Remove-Item -LiteralPath $zipPath
        }
        if ($gone.Count) {
            Invoke-Command -Session $session -ScriptBlock { param($d, $files) foreach ($f in $files) { Remove-Item -LiteralPath (Join-Path $d $f) -Force } } -ArgumentList $dst, $gone
        }
        Say "mod ${leaf}: $($changed.Count) files copied, $($gone.Count) removed, $($mine.Count) in all"
    }
    $guestCl = [ordered]@{ enabledMods = @($guestMods | ForEach-Object { @{ path = $_ } }); disabledDLC = @($cl.disabledDLC); enabledUGC = @() }
    $json = $guestCl | ConvertTo-Json -Depth 4 -Compress
    Invoke-Command -Session $session -ScriptBlock { param($p, $j) [IO.File]::WriteAllText($p, $j, (New-Object Text.UTF8Encoding $false)) } `
        -ArgumentList (Join-Path $GuestDocs "content_load.json"), $json

    # the host's game settings (interface scale, language, autosaves: the run scripts click at places measured on
    # the host and read half-yearly autosaves; the renderer -- Vulkan works through GPU-P too) and key bindings
    $settings = Get-Content (Join-Path $HostDocs "pdx_settings.json") -Raw -Encoding UTF8
    if ($GuiScale) { $settings = $settings -replace '("GUI":\s*\{[^}]*?"scale":\s*")[^"]*"', "`${1}$GuiScale`"" }
    if ($Language) { $settings = $settings -replace '("language":\s*")[^"]*"', "`${1}$Language`"" }
    if ($GuiScale -or $Language) { Say "settings: scale $(if ($GuiScale) { $GuiScale } else { 'as host' }), language $(if ($Language) { $Language } else { 'as host' })" }
    Invoke-Command -Session $session -ScriptBlock { param($p, $j) [IO.File]::WriteAllText($p, $j, (New-Object Text.UTF8Encoding $false)) } `
        -ArgumentList (Join-Path $GuestDocs "pdx_settings.json"), $settings
    if (Test-Path (Join-Path $HostDocs "user_bindings")) {
        Copy-Item (Join-Path $HostDocs "user_bindings") $GuestDocs -Recurse -Force -ToSession $session
    }

    # 4. start save
    if ($StartSave) {
        $s = Join-Path $HostDocs "save games\$StartSave"
        if (-not (Test-Path $s)) { throw "no save on the host: $s" }
        Invoke-Command -Session $session -ScriptBlock { param($d) New-Item -ItemType Directory -Force $d | Out-Null } -ArgumentList (Join-Path $GuestDocs "save games")
        Copy-Item $s (Join-Path $GuestDocs "save games\$StartSave") -ToSession $session
        Say "save: $StartSave"
    }

    # 5. start in the console session
    if ($ParamsJson -like "*.json" -and (Test-Path -LiteralPath $ParamsJson)) { $ParamsJson = Get-Content -LiteralPath $ParamsJson -Raw -Encoding UTF8 }
    $params = $ParamsJson | ConvertFrom-Json
    if ($StartSave) { $params | Add-Member -NotePropertyName StartSave -NotePropertyValue $StartSave -Force }
    $params | Add-Member -NotePropertyName OutDir -NotePropertyValue "$Guest\runs\$RunId" -Force
    $job = @{ script = "$Guest\run\$Script"; params = $params } | ConvertTo-Json -Depth 4
    $started = Invoke-Command -Session $session -ScriptBlock { param($g, $id, $job)
        $dir = "$g\runs\$id"
        [IO.File]::WriteAllText("$dir\job.json", $job, (New-Object Text.UTF8Encoding $false))
        $wrapper = @'
param($dir)
$job = Get-Content "$dir\job.json" -Raw | ConvertFrom-Json
$p = @{}
foreach ($k in $job.params.PSObject.Properties) { $p[$k.Name] = if ($k.Value -is [bool]) { [switch]$k.Value } else { $k.Value } }
$code = 0
try { & $job.script @p *>&1 | ForEach-Object { "$_" } | Out-File "$dir\stdout.txt" -Encoding utf8 -Append; if ($LASTEXITCODE) { $code = $LASTEXITCODE } }
catch { "$_" | Out-File "$dir\stdout.txt" -Encoding utf8 -Append; $code = 1 }
Set-Content "$dir\exit.txt" $code
'@
        Set-Content "$g\run\_job.ps1" $wrapper -Encoding UTF8
        $user = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon").DefaultUserName
        $a = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory "$g\run" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$g\run\_job.ps1`" -dir `"$dir`""
        $pr = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
        $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName "vic3_run" -Action $a -Principal $pr -Settings $st -Force | Out-Null
        Start-ScheduledTask "vic3_run"
        Get-Date
    } -ArgumentList $Guest, $RunId, $job
    Say "run $RunId started in the guest"

    # 6. follow, then fetch
    $seen = 0
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    $code = $null
    while ($null -eq $code) {
        Start-Sleep 10
        $r = Invoke-Command -Session $session -ScriptBlock { param($dir, $from)
            $lines = @(if (Test-Path "$dir\stdout.txt") { Get-Content "$dir\stdout.txt" -Encoding UTF8 })
            $exit = ""
            if (Test-Path "$dir\exit.txt") { $exit = "$(Get-Content "$dir\exit.txt" -Raw)".Trim() }
            @{ lines = [string[]]@($lines | Select-Object -Skip $from); n = $lines.Count; exit = $exit }
        } -ArgumentList "$Guest\runs\$RunId", $seen
        $r.lines | ForEach-Object { Write-Host $_ }
        $seen = $r.n
        if ("$($r.exit)" -match '^-?\d+$') { $code = [int]"$($r.exit)" }
        elseif ((Get-Date) -gt $deadline) {
            Invoke-Command -Session $session -ScriptBlock { Stop-ScheduledTask "vic3_run"; Get-Process victoria3 -ErrorAction SilentlyContinue | Stop-Process -Force }
            throw "the run took more than $TimeoutMinutes min - stopped"
        }
    }
    # the guest's own stdout.txt / exit.txt / job.json stay there: the output was printed above, and a caller (the
    # PC bridge) may keep its own stdout.txt and exit.txt in -OutDir
    $items = Invoke-Command -Session $session -ScriptBlock { param($d)
        Get-ChildItem $d | Where-Object Name -notin "stdout.txt", "exit.txt", "job.json" | ForEach-Object FullName
    } -ArgumentList "$Guest\runs\$RunId"
    foreach ($i in $items) { Copy-Item $i $OutDir -Recurse -Force -FromSession $session }
    if ($FetchSaves) {
        $saves = Invoke-Command -Session $session -ScriptBlock { param($d, $t)
            Get-ChildItem (Join-Path $d "save games") -File -ErrorAction SilentlyContinue | Where-Object LastWriteTime -gt $t | ForEach-Object FullName
        } -ArgumentList $GuestDocs, $started
        if ($saves) {
            New-Item -ItemType Directory -Force (Join-Path $OutDir "saves") | Out-Null
            foreach ($s in $saves) { Copy-Item $s (Join-Path $OutDir "saves") -FromSession $session }
        }
        Say "saves fetched: $(@($saves).Count)"
    }
    Say "run $RunId finished, exit $code; output in $OutDir"
    exit $code
}
finally { if ($session) { Remove-PSSession $session } }
