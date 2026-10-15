<#
.SYNOPSIS
Copies the host GPU driver into the sandbox VM's disk, as GPU partitioning (GPU-P) requires.

.DESCRIPTION
A GPU-P guest runs the host's driver: the driver package folder from the host DriverStore goes to the guest's
C:\Windows\System32\HostDriverStore\FileRepository\, and the driver's other files (System32 DLLs) go to the same
paths in the guest. The file list comes from the driver's WMI record (Win32_PNPSignedDriverCIMDataFile).

Run with the VM shut down: the script mounts its disk. Run again after every host GPU driver update -- a
guest with an old copy shows the GPU with an error in Device Manager, or games fail to start.

Uses Get-WmiObject, so run it in Windows PowerShell 5.1 (powershell.exe), not pwsh.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File bridge\vm\Copy-GpuDriver.ps1
#>
#Requires -RunAsAdministrator
param(
    [string]$Name = "vic3-sandbox",
    # Host GPU, matched against Win32_PnPSignedDriver.DeviceName.
    [string]$GpuName = "NVIDIA GeForce*"
)
$ErrorActionPreference = "Stop"

$vm = Get-VM -Name $Name
if ($vm.State -ne "Off") { throw "VM '$Name' is $($vm.State); shut it down first" }
$vhd = (Get-VMHardDiskDrive -VMName $Name | Select-Object -First 1).Path

$drivers = @(Get-WmiObject Win32_PnPSignedDriver | Where-Object { $_.DeviceName -like $GpuName })
if (-not $drivers) { throw "no host driver with DeviceName like '$GpuName'" }

$disk = Mount-VHD -Path $vhd -PassThru | Get-Disk
try {
    # The Windows partition is the largest one; give it a drive letter if it has none.
    $part = $disk | Get-Partition | Sort-Object Size -Descending | Select-Object -First 1
    if (-not $part.DriveLetter -or $part.DriveLetter -eq [char]0) {
        $part | Add-PartitionAccessPath -AssignDriveLetter
        $part = Get-Partition -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber
    }
    $root = "$($part.DriveLetter):"
    if (-not (Test-Path "$root\Windows\System32")) { throw "no Windows on $root; is Windows installed in the VM?" }

    $store = "$root\Windows\System32\HostDriverStore\FileRepository"
    New-Item -ItemType Directory -Force $store | Out-Null
    $packages = 0; $files = 0
    foreach ($d in $drivers) {
        Write-Host "driver: $($d.DeviceName) $($d.DriverVersion)"
        $id = $d.DeviceID -replace '\\', '\\'
        $antecedent = "\\$env:COMPUTERNAME\ROOT\cimv2:Win32_PnPSignedDriver.DeviceID=""$id"""
        $links = Get-WmiObject Win32_PNPSignedDriverCIMDataFile | Where-Object { $_.Antecedent -eq $antecedent }
        foreach ($l in $links) {
            # Dependent: \\HOST\root\cimv2:CIM_DataFile.Name="c:\\windows\\system32\\x.dll"
            $path = ($l.Dependent.Split("=", 2)[1].Trim('"')) -replace '\\\\', '\'
            $parts = $path.Split('\')
            if ($path -like "c:\windows\system32\driverstore\*") {
                # the whole package folder, once: c:\windows\system32\driverstore\filerepository\<package>
                $src = $parts[0..5] -join '\'
                $dst = Join-Path $store $parts[5]
                if (-not (Test-Path $dst)) { Copy-Item $src $dst -Recurse; $packages++ }
            } elseif (Test-Path $path) {
                $dst = $root + $path.Substring(2)
                New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
                Copy-Item $path $dst -Force; $files++
            }
        }
    }
    Write-Host "copied $packages driver package(s) and $files file(s) to $root"
} finally {
    Dismount-VHD -Path $vhd
}
Write-Host "Start the VM: Start-VM $Name; vmconnect localhost $Name"
