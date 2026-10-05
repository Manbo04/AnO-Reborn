# Community automation (2026-10-05)

Players decide balance and features; bugs get fixed without Dede in the loop.

- `#bug-reports` / `#suggestions` threads -> mirrored hourly to the `community-queue`
  branch by `.github/workflows/community-sync.yml` (`sync.py`, the only code with the
  Discord token, stored as the `DISCORD_BOT_TOKEN` Actions secret).
- A Claude cloud routine (prompt: `ROBOT_PROMPT.md`, see claude.ai/code/routines) reads
  the queue every few hours: fixes bugs, triages new suggestions, builds voted ones,
  pushes `claude/robot-*` branches and writes replies to `results/` on the queue branch.
- `.github/workflows/robot-automerge.yml` merges a robot branch into master once CI
  passes on it (deploys via Railway like any push).
- Every Friday 16:00 UTC `sync.py` tallies the open ballot (Yes > No, at least 3 votes),
  posts results, opens a new ballot (one Discord poll per new suggestion in
  #weekly-vote), and posts a weekly summary to staff chat.

- Support tickets (`ticket-NNNN` channels) are mirrored too; the robot answers what it
  can and marks the rest `needs_staff`, which pings Moderators/Admins in the ticket.
- `.github/workflows/health-watchdog.yml` (`watchdog.py`, hourly :37) checks the live site,
  game ticks and that the latest deploy is actually live; restarts Railway services
  itself, posts changes to staff chat, pings Dede only if a restart didn't fix it.

To change the robot's instructions, edit the routine at claude.ai/code/routines (keep
`ROBOT_PROMPT.md` in sync). To stop everything: disable the routine and the two workflows.
