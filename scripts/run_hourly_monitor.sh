#!/bin/bash
# Hourly maintenance agent for Affairs and Order, driven by agy (Gemini CLI).
# SAFE MODE: the agent detects, investigates, and PREPARES fixes as pull
# requests + drafts player replies — but never deploys to production or messages
# players on its own. A human reviews/merges the PR (which deploys) and sends the
# reply. See scripts/AGENT_PLAYBOOK.md. Scheduled by the launchd plist.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$HOME/AnO-Reborn" || exit 1

# Kill switch: create ~/AnO-Reborn/.agent-disabled to pause the agent entirely.
if [ -f "$HOME/AnO-Reborn/.agent-disabled" ]; then
  echo "$(date -u +%FT%TZ) agent disabled (.agent-disabled present)" >> "$HOME/AnO-Reborn/monitor.log"
  exit 0
fi

# Always make sure we're on a clean, up-to-date master before the agent starts,
# so it never builds on a half-finished working tree.
git stash --include-untracked >/dev/null 2>&1 || true
git checkout master >/dev/null 2>&1 || true
git pull --ff-only origin master >/dev/null 2>&1 || true

PROMPT="You are the SAFE-MODE hourly maintenance agent for the Affairs and Order game. \
FIRST read scripts/AGENT_PLAYBOOK.md, GEMINI.md and CLAUDE.md and follow them exactly. \
Then run: python3 scripts/hourly_monitor.py \
You may investigate production READ-ONLY (railway ssh, SELECT-only). You MUST NOT: push to \
master, merge anything, deploy, run 'railway up', run any write/DELETE/UPDATE SQL on player \
data, message any player directly, or edit migrations/.github/config.py/app.py auth or the \
scripts/ agent files. \
For each REAL bug: create a branch 'agent/fix-<short-slug>', make the smallest possible fix, \
compile-check it, commit to that branch, push the BRANCH (never master), and open a PR with \
'gh pr create' describing the bug, the fix, and a DRAFT player reply. \
Then post ONE summary to the staff-chat Discord channel (get its id from the monitor's helper) \
listing: each proposed PR link, and for each, the exact draft reply a human should send to the \
player (include the channel_id and author_id). If a bug is uncertain, risky, or a game-balance/ \
design decision, do NOT write a fix — just describe it in the staff-chat summary for a human. \
Append what you did to monitor.log. Keep everything small and reviewable."

exec "$HOME/.local/bin/agy" -p "$PROMPT" --dangerously-skip-permissions \
  --log-file "$HOME/AnO-Reborn/.agy-monitor.log" >> "$HOME/AnO-Reborn/monitor.log" 2>&1
