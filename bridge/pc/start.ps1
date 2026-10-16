<#
Starts the PC bridge for a Claude Code cloud session: the ngrok tunnel in its own window and the MCP server
(bridge/pc/server.py) in this one, for a project described by its bridge.toml. Ctrl+C here stops the server; close
the ngrok window to cut the tunnel.

Run from the user's desktop session (not a service, not over RDP): runs on this screen need it.
    powershell -ExecutionPolicy Bypass -File bridge\pc\start.ps1 -Config ..\my_mods\bridge.toml
    powershell -ExecutionPolicy Bypass -File bridge\pc\start.ps1 -Config ..\my_mods\bridge.toml -Vm
        (runs go to the sandbox VM, the screen stays free)
First time: creates the venv <home>\venv (mcp<2, pillow, uvicorn) and the token <home>\token.txt; home, domain, port
and the VM's name come from [bridge] of the config.
#>
param(
    [Parameter(Mandatory)] [string]$Config,
    # runs in the Hyper-V sandbox VM (bridge/vm) instead of on this screen
    [switch]$Vm
)
$ErrorActionPreference = "Stop"
$Config = (Resolve-Path $Config).Path
$py0 = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$cfg = & $py0 -c "import json, sys, tomllib; print(json.dumps(tomllib.load(open(sys.argv[1], 'rb')).get('bridge', {})))" $Config | ConvertFrom-Json
$home_ = [IO.Path]::GetFullPath((Join-Path (Split-Path $Config) $(if ($cfg.home) { $cfg.home } else { "../_bridge" })))
$port = if ($cfg.port) { $cfg.port } else { 8080 }
$py = Join-Path $home_ "venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    New-Item -ItemType Directory -Force $home_ | Out-Null
    & $py0 -m venv (Join-Path $home_ "venv")
    & $py -m pip install --quiet "mcp<2" pillow uvicorn
}
if ($cfg.domain -and -not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
    Start-Process ngrok -ArgumentList "http", "--url=$($cfg.domain)", "$port"
}
$env:PC_BRIDGE_CONFIG = $Config
$env:PC_BRIDGE_TARGET = if ($Vm) { "vm" } else { "pc" }
Write-Host "bridge: https://$($cfg.domain)/mcp -> 127.0.0.1:$port; token in $home_\token.txt; runs: $(if ($Vm) { "VM" } else { "this screen" })"
& $py (Join-Path $PSScriptRoot "server.py")
