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

say() { echo "vic3tools cloud-setup: $*"; }

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
exit 0
