#!/bin/bash
# Cloud sessions (claude.ai/code): the vic3tools plugin (skills + hooks) and the `v3` command for the session.
#
# A cloud session does not load plugins from a repo's .claude/settings.json (enabledPlugins / extraKnownMarketplaces
# are ignored there) nor from the user's ~/.claude on the PC; the documented way is to install them before Claude
# starts, in the cloud environment's *setup script* (claude.ai/code -> environment -> Setup script). Put there:
#
#   curl -fsSL "https://raw.githubusercontent.com/BEDTRIP/vic3_tools/main/claude-plugin/cloud-setup.sh?$(date +%s)" | bash || true
#
# The script runs as root on Ubuntu before Claude Code launches; its result is cached with the environment (about
# a week, or until the setup script changes). Every step is optional: a failure is reported and the session starts.
# Without the game in the cloud the plugin's hooks print nothing and block nothing; the skills work as text.

# every line also goes to a log the session can read afterwards (the setup script's own output is not shown there)
LOG="${HOME:-/root}/vic3tools-cloud-setup.log"
say() { echo "vic3tools cloud-setup: $*"; echo "$(date -u +%FT%TZ) $*" >> "$LOG" 2>/dev/null || true; }
say "start: user $(id -un 2>/dev/null), PWD $PWD, PC_BRIDGE_URL $([ -n "${PC_BRIDGE_URL:-}" ] && echo set || echo unset), PC_BRIDGE_TOKEN $([ -n "${PC_BRIDGE_TOKEN:-}" ] && echo set || echo unset), repos: $(ls -d /home/user/*/ 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"

# a checkout of vic3_tools attached to the session as a second repository, else GitHub
SRC=""
for d in "${VIC3TOOLS_SRC:-}" /home/user/vic3_tools "$HOME/vic3_tools" "$PWD/../vic3_tools"; do
  if [ -n "$d" ] && [ -f "$d/.claude-plugin/marketplace.json" ]; then SRC="$(cd "$d" && pwd)"; break; fi
done

# 1. the `v3` command: the plugin's hooks call it; vic3_mods' tools import the package
# a local checkout goes in editable: a plain install would leave a build/ folder in the clone
if [ -n "$SRC" ]; then PKG="$SRC"; EDIT="-e"; else PKG="git+https://github.com/BEDTRIP/vic3_tools@main"; EDIT=""; fi
python3 -m pip install --quiet --disable-pip-version-check --break-system-packages $EDIT "$PKG" 2>&1 \
  | grep -v "Running pip as the 'root' user" || true
command -v v3 >/dev/null && say "v3 installed ($PKG)" || say "v3 NOT installed - the plugin's hooks will fail quietly"

# 1b. the repos' MCP servers (the PC bridge vic3-pc) for a session with several repos: Claude Code reads .mcp.json
# only from the session's working folder, and such a session works in the repos' parent (/home/user). So their
# mcpServers are merged into $PWD/.mcp.json. The files keep "${PC_BRIDGE_TOKEN}" as text: Claude Code fills it from the
# environment at the session's start (the setup script itself sees none of the environment's variables, 16.10).
if [ ! -d "$PWD/.git" ]; then
  MERGED="$(python3 - "$PWD" <<'PY' 2>/dev/null
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
servers = {}
for f in sorted(root.glob("*/.mcp.json")):
    try:
        servers.update(json.loads(f.read_text(encoding="utf-8")).get("mcpServers") or {})
    except (OSError, ValueError):
        pass
own = root / ".mcp.json"
if servers:
    if own.exists():
        try:
            servers = {**servers, **(json.loads(own.read_text(encoding="utf-8")).get("mcpServers") or {})}
        except (OSError, ValueError):
            pass
    own.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n", encoding="utf-8")
print(" ".join(servers))
PY
)"
  [ -n "$MERGED" ] && say "MCP servers of the repos into $PWD/.mcp.json: $MERGED" || say "no repo has a .mcp.json - nothing to merge"
fi

# 2. the plugin, user scope (the session's ~/.claude)
if ! command -v claude >/dev/null; then
  say "no claude CLI in the setup script - plugin not installed"
  exit 0
fi
if [ -n "$SRC" ]; then MKT="$SRC"; else MKT="BEDTRIP/vic3_tools"; fi
export CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1
claude plugin marketplace add "$MKT" || say "marketplace add failed ($MKT)"
claude plugin install vic3tools@vic3tools --scope user || say "plugin install failed"
claude plugin list 2>/dev/null | grep -A3 vic3tools || true

exit 0
