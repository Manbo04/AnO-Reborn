"""Robot side of the live chat: wait for a player's answer after asking a question.

Run from the `community-queue` worktree right after pushing a needs_info result:
  python3 <repo>/scripts/community/wait_reply.py bugs/<id>.json --since <result updated_at>

Every minute it fetches origin/community-queue and checks whether the thread's
last_player_message_at is newer than --since (community-live.yml posts the question
and pushes the answer within a minute of it arriving). Exit 0 = answered (the worktree
is fast-forwarded so the new messages are on disk), exit 1 = no answer in time,
move on to the next item.
"""

import argparse
import datetime as dt
import json
import subprocess
import time


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record", help="queue path, e.g. bugs/123.json or tickets/456.json")
    ap.add_argument("--since", required=True, help="UTC time the question was written")
    # 5 minutes of player time + about a minute for the Action to start and post.
    ap.add_argument("--minutes", type=int, default=6)
    args = ap.parse_args()
    since = parse(args.since)
    for i in range(args.minutes):
        time.sleep(60)
        subprocess.run(["git", "fetch", "-q", "origin", "community-queue"], check=False)
        raw = subprocess.run(["git", "show", f"origin/community-queue:{args.record}"],
                             capture_output=True, text=True).stdout
        last = json.loads(raw).get("last_player_message_at") if raw else None
        if last and parse(last) > since:
            subprocess.run(["git", "pull", "-q", "--rebase", "origin", "community-queue"], check=False)
            print(f"player answered at {last} (after {i + 1} min); read {args.record} again")
            return 0
        print(f"no answer yet ({i + 1}/{args.minutes} min)", flush=True)
    print("no answer, move on to the next item")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
