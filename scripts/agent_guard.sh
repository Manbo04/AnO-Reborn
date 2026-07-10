#!/bin/bash
# Safety guard for the autonomous agent: refuse (exit 1) if the staged/branch
# changes touch forbidden paths or the current branch is master. Run before any
# agent commit. Human commits are unaffected (they don't call this).
set -e
cd "$(git rev-parse --show-toplevel)"

branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" = "master" ] || [ "$branch" = "main" ]; then
  echo "GUARD FAIL: agent must not commit on $branch — use a agent/fix-* branch."
  exit 1
fi

# Files changed vs master (staged + working tree on this branch)
changed=$(git diff --name-only master...HEAD; git diff --name-only; git diff --cached --name-only)
changed=$(echo "$changed" | sort -u | grep -v '^$' || true)

forbidden_re='^(migrations/|\.github/|config\.py$|app\.py$|scripts/hourly_monitor\.py$|scripts/run_hourly_monitor\.sh$|scripts/discord_reply\.py$|scripts/agent_guard\.sh$|scripts/AGENT_PLAYBOOK\.md$|GEMINI\.md$|CLAUDE\.md$|railway.*\.json$|Dockerfile|nixpacks\.toml$)'

bad=$(echo "$changed" | grep -E "$forbidden_re" || true)
if [ -n "$bad" ]; then
  echo "GUARD FAIL: agent may not modify these protected paths:"
  echo "$bad" | sed 's/^/  - /'
  exit 1
fi

count=$(echo "$changed" | grep -c . || true)
if [ "$count" -gt 8 ]; then
  echo "GUARD FAIL: $count files changed — too large for an autonomous fix (max 8)."
  exit 1
fi

echo "GUARD OK: $count file(s), no protected paths."
