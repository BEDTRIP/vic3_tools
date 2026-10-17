<#
Starts the PC bridge for a Claude Code cloud session: the tunnel and the MCP server (bridge/pc/server.py) in this
window, for a project described by its bridge.toml. Ctrl+C here stops the server. The tunnel is [bridge] tunnel:
"tailscale" (Tailscale Funnel in the background, address https://<this PC>.<tailnet>.ts.net; `tailscale funnel reset`
cuts it) or "ngrok" (the default; its own window, close it to cut the tunnel; the free plan has a monthly traffic cap).

Run from the user's desktop session (not a service, not over RDP): runs on this screen need it.
    powershell -ExecutionPolicy Bypass -File bridge\pc\start.ps1 -Config ..\my_mods\bridge.toml
    powershell -ExecutionPolicy Bypass -File bridge\pc\start.ps1 -Config ..\my_mods\bridge.toml -Vm
        (runs go to the sandbox VM, the screen stays free)
First time: creates the venv <home>\venv (mcp<2, pillow, uvicorn) and the token <home>\token.txt; home, tunnel,
domain, port and the VM's name come from [bridge] of the config. Tailscale: HTTPS certificates and Funnel must be
allowed for the tailnet (the first `tailscale funnel` prints the link to allow them).
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
$domain = $cfg.domain
if ($cfg.tunnel -eq "tailscale") {
    # serves https://<this PC>.<tailnet>.ts.net/ -> 127.0.0.1:$port until `tailscale funnel reset`; rerunning is harmless
    & tailscale funnel --bg "$port"
    if ($LASTEXITCODE) { throw "tailscale funnel failed (allow HTTPS and Funnel for the tailnet, see its message)" }
    $domain = (& tailscale status --json | ConvertFrom-Json).Self.DNSName.TrimEnd(".")
    if ($cfg.domain -and $cfg.domain -ne $domain) { Write-Warning "bridge.toml domain $($cfg.domain) != Funnel address $domain" }
} elseif ($domain -and -not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
    Start-Process ngrok -ArgumentList "http", "--url=$domain", "$port"
}
$env:PC_BRIDGE_CONFIG = $Config
$env:PC_BRIDGE_TARGET = if ($Vm) { "vm" } else { "pc" }
Write-Host "bridge: https://$domain/mcp -> 127.0.0.1:$port; token in $home_\token.txt; runs: $(if ($Vm) { "VM" } else { "this screen" })"
& $py (Join-Path $PSScriptRoot "server.py")
