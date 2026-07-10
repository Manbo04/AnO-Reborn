#!/bin/bash
# Hourly autonomous maintenance agent for Affairs and Order, driven by agy
# (Gemini CLI). Scheduled by ~/Library/LaunchAgents/com.ano.hourly-monitor.plist.
# It detects new issues, fixes real bugs, verifies the deploy, and replies to
# the reporting players. See scripts/AGENT_PLAYBOOK.md for the full procedure.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$HOME/AnO-Reborn" || exit 1

PROMPT="You are the autonomous hourly maintenance agent for the Affairs and Order game. \
FIRST read scripts/AGENT_PLAYBOOK.md, GEMINI.md and CLAUDE.md in this repo and follow them exactly. \
Then run: python3 scripts/hourly_monitor.py --alert \
For each real bug it reports (new Discord messages are tagged channel_id=/author_id=): \
investigate against production read-only, fix the code, commit and push to master, \
VERIFY both the CI and 'Redeploy game stack' workflows passed and the fix is actually live \
(re-trigger the deploy if the redeploy workflow failed), then reply to the reporting player \
via: python3 scripts/discord_reply.py <channel_id> <author_id> \"<fix confirmation + plain explanation>\". \
Answer questions/misunderstandings with an explanation only (no code change). Log feature requests \
and anything risky/uncertain to monitor.log and post to staff-chat instead of guessing a fix. \
Never run 'railway up'. Never delete player data. One bug per commit. Append a short summary of \
what you did to monitor.log when finished."

exec "$HOME/.local/bin/agy" -p "$PROMPT" --dangerously-skip-permissions \
  --log-file "$HOME/AnO-Reborn/.agy-monitor.log" >> "$HOME/AnO-Reborn/monitor.log" 2>&1
