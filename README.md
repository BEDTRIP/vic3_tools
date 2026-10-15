# vic3_tools

Tools for Victoria 3 modding, for modders and coding agents: script parsing and indexing, compatibility checks,
GUI help, save and log analysis, and a sandbox for test runs of the game. Work in progress.

Nothing from the game is stored here: the tools read the game, Steam Workshop mods and the game's documents
folder in place on your machine.

## Install

Python 3.11 or newer.

```
pip install -e .
v3 setup
v3 doctor
```

`v3 setup` finds the game, the Workshop and the game's documents folder, writes the user config and builds the
cache; `v3 doctor` tells what is ready. How to use the commands: [`docs/usage.md`](docs/usage.md)
([по-русски](docs/ru/usage.md)).

## Contents

- `vic3tools/` — the Python package behind the `v3` command: finding the roots and the config (`core/paths.py`),
  the script parser (`core/script.py`), the game's virtual file system and load-order rules (`core/vfs.py`), readers
  for Steam's `.vdf` and the game's localization, compatibility of a mod set (`compat/`: index, who wins, conflicts,
  audits), the glossary, the message catalog (`i18n/`, English and Russian).
- `claude-plugin/` — the Claude Code plugin (empty for now); `.claude-plugin/marketplace.json` makes this repo its
  marketplace.
- `docs/` — documents in English, `docs/ru/` — their Russian translations; `docs/benchmarks/` — token and turn counts
  of a fresh agent on reference tasks, before and after the tools.

- `bridge/vm/` — a Hyper-V VM with a GPU partition (GPU-P) that runs the game for test runs, so a run does not
  take the host's screen, mouse and keyboard:
  `New-SandboxVM.ps1` creates the VM, `Copy-GpuDriver.ps1` copies the host GPU driver into it
  (again after every host driver update), `Initialize-SandboxGuest.ps1` sets the guest up for unattended runs
  (autologon, 2560x1440 screen, Steam offline, Defender exclusions), `Invoke-SandboxRun.ps1` runs a game run
  script in the guest: it mirrors the run's mods and the host's game settings into the guest, starts the run on
  the guest's desktop and brings its output and saves back.

## Development

```
pip install -e ".[dev]"
ruff check .
pytest
v3 docs check-ru
```

The same runs in CI on Windows and Linux. Code, names, comments, `--help` and documents are in English; command
output goes through the message catalog (`vic3tools/i18n/`), and documents for people have a Russian mirror in
`docs/ru/`.

## License

MIT, see `LICENSE`.
