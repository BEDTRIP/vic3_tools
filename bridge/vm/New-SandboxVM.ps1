<#
.SYNOPSIS
Creates the Hyper-V VM that runs Victoria 3 for agent test runs, with a GPU partition (GPU-P).

.DESCRIPTION
The game and the bridge run inside the VM, so a run does not take the host's screen, mouse and keyboard.
The VM gets a share of a host GPU through GPU partitioning; the host keeps using the same GPU.

GPU-P has limits the settings below follow: memory must be static, the VM can not be saved or checkpointed
(AutomaticStopAction TurnOff, checkpoints disabled), and the guest needs the host's driver files copied in
(Copy-GpuDriver.ps1) -- the guest does not install a GPU driver of its own.

Steps:
  1. This script (elevated): creates the VM and boots it from the Windows 11 ISO.
  2. Install Windows in the VM console (vmconnect); then shut the VM down from inside.
  3. Copy-GpuDriver.ps1 (elevated): copies the host GPU driver into the VM disk.
  4. Start the VM; Device Manager shows the GPU.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File bridge\vm\New-SandboxVM.ps1 -IsoPath D:\iso\Win11.iso
#>
#Requires -RunAsAdministrator
param(
    [Parameter(Mandatory)] [string]$IsoPath,
    [string]$Name = "vic3-sandbox",
    [string]$VMPath = "C:\VMs",
    [int]$Cpu = [Environment]::ProcessorCount,
    [long]$MemoryBytes = 24GB,
    [long]$DiskBytes = 150GB,
    # Substring of the GPU instance path (Get-VMHostPartitionableGpu): VEN_10DE = NVIDIA, VEN_1002 = AMD.
    [string]$GpuMatch = "VEN_10DE",
    # Share of the GPU's partition resources (VRAM, encode, decode, compute) the VM asks for.
    [ValidateRange(1, 100)] [int]$GpuPercent = 100,
    [string]$Switch = "Default Switch"
)
$ErrorActionPreference = "Stop"

if (Get-VM -Name $Name -ErrorAction SilentlyContinue) { throw "VM '$Name' already exists" }
if (-not (Test-Path $IsoPath)) { throw "ISO not found: $IsoPath" }
$gpu = Get-VMHostPartitionableGpu | Where-Object Name -like "*$GpuMatch*" | Select-Object -First 1
if (-not $gpu) { throw "no partitionable GPU matching '$GpuMatch'; see Get-VMHostPartitionableGpu" }

$dir = Join-Path $VMPath $Name
New-Item -ItemType Directory -Force $dir | Out-Null
$vhd = Join-Path $dir "$Name.vhdx"

New-VM -Name $Name -Generation 2 -Path $VMPath -MemoryStartupBytes $MemoryBytes `
    -NewVHDPath $vhd -NewVHDSizeBytes $DiskBytes -SwitchName $Switch | Out-Null
Set-VM -Name $Name -ProcessorCount $Cpu -StaticMemory -CheckpointType Disabled -AutomaticCheckpointsEnabled $false `
    -AutomaticStopAction TurnOff -AutomaticStartAction Nothing `
    -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1GB -HighMemoryMappedIoSpace 32GB

# Windows 11 setup refuses to install without Secure Boot and a TPM.
Set-VMKeyProtector -VMName $Name -NewLocalKeyProtector
Enable-VMTPM -VMName $Name
$dvd = Add-VMDvdDrive -VMName $Name -Path $IsoPath -Passthru
Set-VMFirmware -VMName $Name -EnableSecureBoot On -FirstBootDevice $dvd

Add-VMGpuPartitionAdapter -VMName $Name -InstancePath $gpu.Name
$share = [long](1000000000 * $GpuPercent / 100)
Set-VMGpuPartitionAdapter -VMName $Name `
    -MinPartitionVRAM $share -MaxPartitionVRAM $share -OptimalPartitionVRAM $share `
    -MinPartitionEncode $share -MaxPartitionEncode $share -OptimalPartitionEncode $share `
    -MinPartitionDecode $share -MaxPartitionDecode $share -OptimalPartitionDecode $share `
    -MinPartitionCompute $share -MaxPartitionCompute $share -OptimalPartitionCompute $share

Start-VM -Name $Name
Start-Process vmconnect.exe -ArgumentList "localhost", $Name
Write-Host "VM '$Name' started from the ISO: $Cpu CPUs, $($MemoryBytes / 1GB) GB, GPU $($gpu.Name)"
Write-Host "Press a key in the console when it says 'Press any key to boot from CD or DVD'."
Write-Host "After Windows is installed: shut the VM down, then run Copy-GpuDriver.ps1."
