# vic3_tools

Tools for Victoria 3 modding — for modders and for AI coding agents (Claude Code). One command, `v3`, answers the
questions modding keeps asking: where a thing is defined and which mod's definition the game actually takes, who uses
it, what a GUI widget really gets, whether two mods conflict, what a save or a log says, how a mod goes to the Steam
Workshop. A Claude Code plugin teaches an agent to use it, and a sandbox VM lets an agent run the game without taking
your screen.

Nothing from the game is stored here: the tools read the game, the Workshop mods and the game's documents folder in
place on your machine, and keep their index in a cache outside the repo.

## What is inside

| | commands |
| --- | --- |
| **Find** | `v3 def` (where defined, who wins), `v3 refs` (who uses, reads, writes), `v3 loc` (a key's text, the key behind a text seen in game), `v3 outline` (a big file's tree), `v3 winner` (the chain across mods), `v3 glossary` |
| **GUI** | `v3 gui resolve` (a widget after types / templates / blocks), `gui types / templates / textures`, `gui set --dry` (an exact edit), `gui fit` (does a text fit in 11 languages), `gui render` / `gui grid` (a picture without the game) |
| **Check** | `v3 lint` (vic3-tiger with the mods loaded before, plus own rules; known reports left out), `v3 audit`, `v3 conflicts`, `v3 matrix` |
| **Saves and logs** | `v3 save` (a text save, read by pieces), `v3 log` (record families, two runs compared, run speed, the script profiler read by OCR) |
| **Release** | `v3 release check / build / done` (a clean build for the Workshop, change note, BBCode description, a SteamCMD VDF), `v3 release zip` (a playset as a ready set), `v3 mods snapshot` (the playset's mods' versions kept in git) |
| **Game** | `v3 bench` (the game open in the sandbox VM: edit → screenshot → diff), sandbox runs (`bridge/game`, `bridge/vm`) |

Every command has `--help`; short output by default, `--json` for exact data. How to use them:
[`docs/usage.md`](docs/usage.md) ([по-русски](docs/ru/usage.md)).

- **Claude Code plugin** (`claude-plugin/`): skills — `vic3-search`, `vic3-modding` (how the engine loads and merges
  mods, facts checked in the game), `vic3-compat` (compatibility patches, megapacks), `vic3-gui`, `vic3-sandbox`,
  `vic3-repo-rules`; hooks — at a session's start the agent learns what `v3` can do; a grep for a name in game or mod
  folders gets the index's answer; an edited mod file gets lint's fast rules.
- **PC bridge** (`bridge/pc/`): an MCP server through an ngrok tunnel, so a cloud session (claude.ai/code) runs `v3`
  and game runs on your PC.

## Install

Windows with Victoria 3 from Steam; Python 3.11 or newer. The package is not on PyPI — install it from GitHub:

```
pip install "vic3tools[img] @ git+https://github.com/BEDTRIP/vic3_tools"
v3 setup
v3 doctor
```

or from a checkout: `git clone https://github.com/BEDTRIP/vic3_tools` and `pip install -e "vic3_tools[img]"`. The
`[img]` extra is Pillow, needed only for screenshots of the bench and the sandbox (cropping, comparing); without it
everything else works.

- `v3 setup` finds the game, the Workshop and the documents folder (Steam's `libraryfolders.vdf`, the Windows
  Documents folder), writes the user config `%LOCALAPPDATA%\vic3tools\vic3tools.toml` (only to correct what was found)
  and builds the glossary and the index of the active launcher playset. `v3 doctor` says what is ready and what is not;
  it exits with 1 while something is missing (in a cloud session, with no game, that is expected).
- **First commands** to see it work: `v3 mods` (the active playset in load order), `v3 def <a scripted effect or
  building of your mod>` (where it is defined and which definition wins), `v3 refs <the same name>` (who uses it).
- **Language of the output:** English by default; Russian with `v3 --lang ru <command>`, the environment variable `V3_LANG=ru`,
  or `lang = "ru"` in the user config (a Russian Windows gets it from the system locale).
- **vic3-tiger** (for `v3 lint`): put `vic3-tiger.exe` from [its releases](https://github.com/amtep/tiger/releases) into
  `%LOCALAPPDATA%\vic3tools\bin`.
- **Claude Code plugin:** in Claude Code
  ```
  /plugin marketplace add BEDTRIP/vic3_tools
  /plugin install vic3tools@vic3tools
  ```
  `v3` must be on `PATH` for the hooks. Cloud sessions: put `claude-plugin/cloud-setup.sh` into the cloud environment's
  setup script ([`claude-plugin/README.md`](claude-plugin/README.md)).

Optional:

- **Sandbox VM** for test runs off your screen (Hyper-V with a GPU partition): [`bridge/vm/README.md`](bridge/vm/README.md).
- **PC bridge** for cloud sessions: `bridge/pc/start.ps1 -Config <project>\bridge.toml [-Vm]`. It needs
  [ngrok](https://ngrok.com) with an account and its free static domain (`domain` in `[bridge]` of `bridge.toml`);
  the token is made on the first start (`<home>\token.txt`) and goes into the cloud environment's variable
  `PC_BRIDGE_TOKEN` — [`docs/usage.md`](docs/usage.md), «From a cloud session: the bridge».
- **SteamCMD** for Workshop uploads: unpack [steamcmd.zip](https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip)
  into `C:\steamcmd` and sign in once (`steamcmd +login <user>`); `v3 release build` prints the upload command.

**Without the game** (a cloud session, Linux) the commands that read only a mod's own files work: `outline`,
`release check / build`, `docs`, the tests; everything that needs the game's files runs on the PC through the bridge.

Updating: `pip install -U …` (or `git pull` in a checkout); the cache follows the game's version and the playset by
itself, and `/plugin update` refreshes the plugin.

## Layout

```
vic3tools/        the package behind `v3`: core (paths, parser, load order), index, lint, gui, compat, save, logs,
                  release, the message catalog (i18n/, English and Russian)
claude-plugin/    the Claude Code plugin: skills, hooks, the cloud setup script
bridge/game/      the game run scripts (PowerShell): new game / save, AI for all, screenshots, logs
bridge/vm/        the sandbox VM: create, set up, run in it
bridge/pc/        the PC bridge (MCP server) for cloud sessions
mods/             small helper mods (profiler_view: the script profiler full screen)
docs/             usage (and docs/ru/), benchmarks of an agent on reference tasks
tests/            tests on small examples
```

## Development

```
pip install -e ".[dev]"
ruff check .
pytest
v3 docs check-ru
```

The same runs in CI on Windows and Linux. Rules:

- Code, names, comments, `--help`, skills and documents are in English; command output goes through the message
  catalog (`vic3tools/i18n/`, `en` / `ru`); documents for people have a Russian mirror in `docs/ru/`, each with a mark
  of the English version it was translated from (`v3 docs check-ru` shows stale ones).
- A docstring and `--help` say what a command does and how to call it, without history (that is in git).
- Output is short and limited by default; long output goes to a file, the screen gets the path and a summary.
- Nothing writes outside the given folders; a generator has `--check`. A one-off probe belongs to the project that
  needed it, not here.
- Before publishing: no secrets or personal data (tokens, bridge addresses, paths with a user name, e-mail).

## License

MIT, see `LICENSE`.
