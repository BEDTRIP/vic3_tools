#!/bin/bash
# Cloud sessions (claude.ai/code): the vic3tools plugin (skills + hooks) and the `v3` command for the session.
#
# A cloud session does not load plugins from a repo's .claude/settings.json (enabledPlugins / extraKnownMarketplaces
# are ignored there) nor from the user's ~/.claude on the PC; the documented way is to install them before Claude
# starts, in the cloud environment's *setup script* (claude.ai/code -> environment -> Setup script). Put there:
#
#   curl -fsSL https://raw.githubusercontent.com/BEDTRIP/vic3_tools/main/claude-plugin/cloud-setup.sh | bash || true
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

# 3. the PC bridge (MCP server vic3-pc), user scope: a project's .mcp.json is read only from the session's working
# folder, and a session with several repos works in their parent (/home/user), so it never sees vic3_mods/.mcp.json.
# The URL: $PC_BRIDGE_URL, else the vic3-pc entry of a project's .mcp.json; the token: $PC_BRIDGE_TOKEN of the
# environment (a new token needs the setup script re-run: change the script's text, e.g. a comment, to drop its cache).
URL="${PC_BRIDGE_URL:-}"
if [ -z "$URL" ]; then
  for f in /home/user/vic3_mods/.mcp.json "$HOME/vic3_mods/.mcp.json" "$PWD/vic3_mods/.mcp.json" "$PWD/.mcp.json"; do
    [ -f "$f" ] || continue
    URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["mcpServers"]["vic3-pc"]["url"])' "$f" 2>/dev/null)"
    [ -n "$URL" ] && break
  done
fi
if [ -n "$URL" ] && [ -n "${PC_BRIDGE_TOKEN:-}" ]; then
  claude mcp remove vic3-pc --scope user >/dev/null 2>&1 || true
  claude mcp add --scope user --transport http vic3-pc "$URL" --header "Authorization: Bearer $PC_BRIDGE_TOKEN" \
    >/dev/null 2>&1 && say "MCP server vic3-pc added ($URL)" || say "MCP server vic3-pc NOT added"
else
  say "no bridge URL or PC_BRIDGE_TOKEN - MCP server vic3-pc not added (projects' .mcp.json still works in a one-repo session)"
fi
exit 0
