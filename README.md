# vic3_tools

Tools for Victoria 3 modding, for modders and coding agents: script parsing and indexing, compatibility checks,
GUI help, save and log analysis, and a sandbox for test runs of the game. Work in progress.

Nothing from the game is stored here: the tools read the game, Steam Workshop mods and the game's documents
folder in place on your machine.

## Contents

- `bridge/vm/` — a Hyper-V VM with a GPU partition (GPU-P) that runs the game for test runs, so a run does not
  take the host's screen, mouse and keyboard:
  `New-SandboxVM.ps1` creates the VM, `Copy-GpuDriver.ps1` copies the host GPU driver into it
  (again after every host driver update), `Initialize-SandboxGuest.ps1` sets the guest up for unattended runs
  (autologon, 2560x1440 screen, Steam offline, Defender exclusions), `Invoke-SandboxRun.ps1` runs a game run
  script in the guest: it mirrors the run's mods and the host's game settings into the guest, starts the run on
  the guest's desktop and brings its output and saves back.

## License

MIT, see `LICENSE`.
