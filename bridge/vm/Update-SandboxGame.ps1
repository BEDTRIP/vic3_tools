<#
.SYNOPSIS
Brings the game in the sandbox VM to the PC's version: copies the files that differ, without Steam going online.
.DESCRIPTION
Steam in the guest is always offline (Initialize-SandboxGuest.ps1) and one account cannot play on the PC and update
in the VM at once, so after a game patch the guest keeps the old version. This script compares the game folder of
the PC and of the guest by size and MD5 (modification times differ: the guest installed on another day), copies the
files that differ over PowerShell Direct and the PC's Steam manifest of the game (its build id). The game must not run
in the guest. Prints the guest's version (rawVersion of launcher-settings.json) at the end.
.EXAMPLE
powershell -ExecutionPolicy Bypass -File bridge\vm\Update-SandboxGame.ps1 -WhatIf   # only list what differs
#>
param(
    [string]$HostGame = "",  # default: roots.game of %LOCALAPPDATA%\vic3tools\vic3tools.toml, else C:\Games\Steam\…
    [string]$GuestGame = "C:\Program Files (x86)\Steam\steamapps\common\Victoria 3",
    [string]$Name = "vic3-sandbox",
    [string]$CredentialPath = (Join-Path $env:LOCALAPPDATA "vic3tools\vm-cred.xml"),
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"
if (-not $HostGame) {
    $cfg = Join-Path $env:LOCALAPPDATA "vic3tools\vic3tools.toml"
    if (Test-Path $cfg) {
        $m = Select-String -Path $cfg -Pattern "^\s*game\s*=\s*['""](.+?)['""]" | Select-Object -First 1
        if ($m) { $HostGame = $m.Matches[0].Groups[1].Value }
    }
    if (-not $HostGame) { $HostGame = "C:\Games\Steam\steamapps\common\Victoria 3" }
}
$HostGame = (Resolve-Path $HostGame).Path
$manifest = Join-Path (Split-Path (Split-Path $HostGame)) "appmanifest_529340.acf"

$hashes = {
    param($root)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $h = @{}
    Get-ChildItem $root -Recurse -File | ForEach-Object {
        $fs = [IO.File]::OpenRead($_.FullName)
        try { $h[$_.FullName.Substring($root.Length + 1)] = "$($_.Length)|" + [BitConverter]::ToString($md5.ComputeHash($fs)) }
        finally { $fs.Dispose() }
    }
    $h
}

if ((Get-VM $Name).State -ne "Running") { Start-VM $Name }
$deadline = (Get-Date).AddMinutes(3)
while ((Get-VM $Name).Heartbeat -notlike "Ok*") {
    if ((Get-Date) -gt $deadline) { throw "the guest does not answer" }
    Start-Sleep 5
}
$session = New-PSSession -VMName $Name -Credential (Import-Clixml $CredentialPath)
try {
    if (Invoke-Command -Session $session { Get-Process victoria3 -ErrorAction SilentlyContinue }) {
        throw "the game is running in the guest"
    }
    $job = Invoke-Command -Session $session -ScriptBlock $hashes -ArgumentList $GuestGame -AsJob
    $pc = & $hashes $HostGame
    $guest = Receive-Job $job -Wait
    $diff = @($pc.Keys | Where-Object { $guest[$_] -ne $pc[$_] } | Sort-Object)
    $mb = [math]::Round((($diff | ForEach-Object { [long]$pc[$_].Split("|")[0] } | Measure-Object -Sum).Sum) / 1MB)
    "differ: $($diff.Count) files, $mb MB"
    if ($WhatIf) { $diff; return }
    foreach ($f in $diff) {
        $dst = Join-Path $GuestGame $f
        Invoke-Command -Session $session { param($d) New-Item -ItemType Directory -Force (Split-Path $d) | Out-Null } -ArgumentList $dst
        Copy-Item -LiteralPath (Join-Path $HostGame $f) -Destination $dst -ToSession $session -Force
    }
    if (Test-Path $manifest) {
        $gm = Join-Path (Split-Path (Split-Path $GuestGame)) "appmanifest_529340.acf"
        Copy-Item $manifest -Destination $gm -ToSession $session -Force
    }
    $v = Invoke-Command -Session $session -ArgumentList $GuestGame {
        param($g) (Get-Content (Join-Path $g "launcher\launcher-settings.json") -Raw | ConvertFrom-Json).rawVersion
    }
    "copied $($diff.Count); guest game version $v"
}
finally { Remove-PSSession $session }
