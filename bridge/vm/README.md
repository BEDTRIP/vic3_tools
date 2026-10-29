---
type: code
description: "The sandbox VM: game runs in a Hyper-V VM on the same PC — what is in it, how mods and settings get there, how the bridge drives it"
project: vic3
tags: [sandbox, bridge]
paths: ["bridge/vm"]
---
# The sandbox VM

Test runs of the game in a Hyper-V virtual machine on the same PC, so a run does not take the screen, mouse and
keyboard. In the VM there is only Windows, Steam (always offline) and the game; Python, git, tokens and the bridge stay
on the PC. Mods and game settings are copied in before each run.

## Set up once

Windows 11 Pro / Enterprise / Education (Hyper-V), an NVIDIA or AMD card that supports GPU partitioning
(`Get-VMHostPartitionableGpu` lists it), a Windows 11 ISO. As administrator:

1. Enable Hyper-V and reboot.
2. `New-SandboxVM.ps1 -IsoPath <Windows 11 ISO>` — creates the VM `vic3-sandbox` (all CPU threads, 24 GB static
   memory, 150 GB disk, a GPU partition; GPU-P needs static memory and no checkpoints) and boots it from the ISO.
   Dynamic memory is not an option for the same reason; to share the PC, lower it with the VM off
   (`Set-VMMemory vic3-sandbox -StartupBytes 20GB`) or keep it off when not testing — runs start it themselves,
   the bridge's `comfy` shuts it down (both use the GPU).
3. Install Windows in the VM console, create a local user, shut the VM down from inside.
4. `Copy-GpuDriver.ps1` — copies the PC's GPU driver into the VM disk. **Again after every driver update on the PC.**
   Start the VM; install Steam, sign in, install Victoria 3 (the same version as on the PC).
5. `Initialize-SandboxGuest.ps1` — sets the guest up for unattended runs: auto sign-in (with "sign-in without a
   password" turned off, else Windows drops it at boot), the 2560×1440 screen, no sleep, Steam offline without asking,
   Defender exclusions (the game loads to the menu in ~20 s with them, minutes without). Before it, save the guest
   account (it needs a password) for PowerShell Direct once:
   `Get-Credential | Export-Clixml "$env:LOCALAPPDATA\vic3tools\vm-cred.xml"`. The PC user must be an administrator
   or in the local group Hyper-V Administrators.

## A run

`Invoke-SandboxRun.ps1 -OutDir <folder> -ParamsJson <file.json> [-HooksDir <project hooks>] [-ContentLoad
<content_load.json>] [-StartSave <save>] [-FetchSaves] [-GuiScale 1.3] [-Language l_russian]` copies the game scripts
(`bridge/game`) and the project's hooks into the guest, mirrors the playset's mods (changed files only) and the PC's
`pdx_settings.json`, starts `run_vic3_sandbox.ps1` on the guest's desktop (a scheduled task in its console session),
follows its output and brings back `runs/<id>` (logs, screenshots) and, with `-FetchSaves`, the new saves. The run
script's parameters are a JSON object (`RunMinutes`, `NewGame`, `Tag`, `Observe`, `Countries`, `Shots`, `Commands`…;
`Get-Help ..\game\run_vic3_sandbox.ps1`). Runs with screen steps get interface scale 1 unless `-GuiScale` is given:
those steps click at points measured at 1. The PC bridge runs this with `start.ps1 -Vm`; the bench (`v3 bench`) keeps
the game open in the VM between steps.

## Good to know

- Restart the VM only from inside (`Restart-Computer -Force`). `Restart-VM -Force` is a hard reset and loses registry
  edits.
- Opening and closing a VMConnect window leaves the guest session "Disc" — no screen, screenshots fail with "The
  handle is invalid". `Invoke-SandboxRun.ps1` restarts the guest from inside by itself.
- If the game cannot be brought to the front (a stuck Start menu or another window after a failed run), restart the
  guest from inside and run again.
- The game in the VM is about 20 % slower per game month than on the PC (Ryzen 7 7800X3D, RTX 5070; Vulkan and DX11
  alike).
- One Steam account cannot play on the PC and run in the VM at the same time.
- Observer mode (`-Observe`): nobody plays, the AI runs every country; a mod's GUI-driven script (scripted GUIs fired
  from widgets) does not run there.
