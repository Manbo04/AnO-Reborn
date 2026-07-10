#!/bin/bash
# Hourly health check for Affairs and Order, driven by the Gemini CLI (agy).
# Scheduled by ~/Library/LaunchAgents/com.ano.hourly-monitor.plist.
# agy runs the monitor (deploy health + Discord bug scan) and reports/alerts.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$HOME/AnO-Reborn" || exit 1

PROMPT="You are the automated hourly health monitor for the Affairs and Order game. \
Run: python3 scripts/hourly_monitor.py --alert \
It checks (1) that the latest master commit passed GitHub CI AND the 'Redeploy game stack' \
workflow AND is live on Railway (catches fixes that pass CI but fail to deploy), and \
(2) new player bug reports in the Discord bug/ticket/suggestion channels. \
The script already logs to monitor.log and posts a staff-chat alert when attention is needed. \
After it runs: if it printed 'ATTENTION NEEDED', write a 2-3 sentence plain-English summary \
of the specific problems to the end of monitor.log. Do NOT edit code, commit, or deploy \
anything — detection and reporting only. Keep your output short."

exec "$HOME/.local/bin/agy" -p "$PROMPT" --dangerously-skip-permissions \
  --log-file "$HOME/AnO-Reborn/.agy-monitor.log" >> "$HOME/AnO-Reborn/monitor.log" 2>&1
