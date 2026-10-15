<#
.SYNOPSIS
Sets up Windows inside the sandbox VM for unattended game runs: autologon, a 2560x1440 screen, Steam always
offline, no sleep, the game's folders out of Defender's real-time scan.

.DESCRIPTION
Run on the host after Windows, Steam and the game are installed in the VM and the game was started once by hand.
It talks to the guest over PowerShell Direct with the credential saved by:

    New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\vic3tools" | Out-Null
    Get-Credential -Message "vic3-sandbox: guest account" | Export-Clixml "$env:LOCALAPPDATA\vic3tools\vm-cred.xml"

The guest account needs a password: PowerShell Direct does not log in without one. The host user needs to be in
the local group Hyper-V Administrators (SID S-1-5-32-578) or be an administrator.

What it changes and why:
  - Screen: the VM's video is set to a single 2560x1440 mode (the VM is shut down for that). Without the viewer
    window open the guest console otherwise falls back to 1024x768, and the run scripts click at fractions of a
    16:9 screen.
  - Autologon of the guest account to the console session: the game needs a desktop to draw on after a reboot.
    Windows 11 wipes the autologon values at boot while "passwordless sign-in" is on, so that is turned off too.
  - Power: the display and the guest never sleep.
  - Defender: the Steam folder, the game's documents folder and victoria3.exe are excluded from the real-time scan.
    With the scan the game took minutes to reach the main menu in the guest instead of ~20 s.
  - Steam: offline mode without the "go online?" prompt, so a run never waits on a dialog and the guest does not
    take the account's online session away from the host.

The guest is rebooted from inside at the end (never a hard reset of the VM: registry changes not yet flushed to
disk are lost).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File bridge\vm\Initialize-SandboxGuest.ps1
#>
param(
    [string]$Name = "vic3-sandbox",
    [string]$CredentialPath = (Join-Path $env:LOCALAPPDATA "vic3tools\vm-cred.xml"),
    [int]$Width = 2560,
    [int]$Height = 1440
)
$ErrorActionPreference = "Stop"

$cred = Import-Clixml $CredentialPath
$vm = Get-VM -Name $Name

function Wait-Guest([int]$TimeoutSec = 300) {
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        try { Invoke-Command -VMName $Name -Credential $cred -ScriptBlock { 1 } -ErrorAction Stop | Out-Null; return }
        catch { Start-Sleep 5 }
    }
    throw "the guest did not answer over PowerShell Direct in $TimeoutSec s"
}

$video = Get-VMVideo -VMName $Name
if ($video.ResolutionType -ne "Single" -or $video.HorizontalResolution -ne $Width -or $video.VerticalResolution -ne $Height) {
    if ($vm.State -ne "Off") {
        Write-Host "shutting the VM down to set its screen to ${Width}x$Height"
        Wait-Guest
        Invoke-Command -VMName $Name -Credential $cred -ScriptBlock { Stop-Computer -Force }
        $end = (Get-Date).AddSeconds(180)
        while ((Get-VM -Name $Name).State -ne "Off") {
            if ((Get-Date) -gt $end) { throw "the VM did not shut down in 180 s" }
            Start-Sleep 3
        }
    }
    Set-VMVideo -VMName $Name -ResolutionType Single -HorizontalResolution $Width -VerticalResolution $Height
}
if ((Get-VM -Name $Name).State -ne "Running") { Start-VM -Name $Name }
Wait-Guest

Invoke-Command -VMName $Name -Credential $cred -ArgumentList $cred.UserName, $cred.GetNetworkCredential().Password -ScriptBlock {
    param($user, $password)
    $ErrorActionPreference = "Stop"
    $user = $user.Split("\")[-1]

    $pl = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device"
    New-Item $pl -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty $pl DevicePasswordLessBuildVersion 0 -Type DWord
    $wl = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    Set-ItemProperty $wl AutoAdminLogon "1"
    Set-ItemProperty $wl DefaultUserName $user
    Set-ItemProperty $wl DefaultDomainName $env:COMPUTERNAME
    Set-ItemProperty $wl DefaultPassword $password
    Remove-ItemProperty $wl AutoLogonCount -ErrorAction SilentlyContinue
    "autologon: $user"

    powercfg /change monitor-timeout-ac 0
    powercfg /change standby-timeout-ac 0
    "power: no display off, no sleep"

    $steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam").SteamPath -replace "/", "\"
    $docs = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Paradox Interactive"
    Add-MpPreference -ExclusionPath $steam, $docs -ExclusionProcess "victoria3.exe"
    "defender: excluded $steam, $docs, victoria3.exe"

    if (Get-Process steam -ErrorAction SilentlyContinue) {
        Start-Process (Join-Path $steam "steam.exe") -ArgumentList "-shutdown"
        $end = (Get-Date).AddSeconds(60)
        while ((Get-Process steam -ErrorAction SilentlyContinue) -and (Get-Date) -lt $end) { Start-Sleep 2 }
        Get-Process steam -ErrorAction SilentlyContinue | Stop-Process -Force
    }
    $users = Join-Path $steam "config\loginusers.vdf"
    $text = [IO.File]::ReadAllText($users)
    foreach ($key in "WantsOfflineMode", "SkipOfflineModeWarning") {
        if ($text -match "`"$key`"") { $text = $text -replace "(`"$key`"\s+)`"\d`"", '$1"1"' }
        else { $text = $text -replace '("AccountName"[^\r\n]*\r?\n)', "`$1`t`t`"$key`"`t`t`"1`"`r`n" }
    }
    [IO.File]::WriteAllText($users, $text)
    "steam: offline, no prompt"

    Restart-Computer -Force
}

Start-Sleep 20
Wait-Guest
$explorer = Invoke-Command -VMName $Name -Credential $cred -ScriptBlock {
    $end = (Get-Date).AddSeconds(120)
    while (-not (Get-Process explorer -ErrorAction SilentlyContinue) -and (Get-Date) -lt $end) { Start-Sleep 3 }
    [bool](Get-Process explorer -ErrorAction SilentlyContinue)
}
if (-not $explorer) { throw "the guest did not log in by itself after the reboot" }
Write-Host "done: the guest logged in by itself; screen ${Width}x$Height"
