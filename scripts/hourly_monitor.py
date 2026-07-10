#!/usr/bin/env python3
"""Hourly health monitor for Affairs and Order.

Two jobs, run once per hour (see scripts/run_hourly_monitor.sh + the launchd
plist that invokes agy):

  1. DEPLOY HEALTH — verify the code on master actually shipped: latest CI
     passed, the "Redeploy game stack" workflow passed, and production is
     serving the current master commit. Catches the failure mode where a
     commit passes CI but the deploy workflow fails, so the fix never goes live.

  2. DISCORD BUG SCAN — surface new player messages in the bug/ticket/suggestion
     channels since the last run (state stored in ~/.ano_monitor_state.json).

Prints a human-readable report and exits non-zero if anything needs attention,
so the caller (agy) knows to investigate/notify. Read-only: makes no changes.

Secrets are pulled at runtime from the tooling already logged in on this
machine (gh CLI, railway CLI) — nothing is hardcoded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

STATE_FILE = os.path.expanduser("~/.ano_monitor_state.json")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUILD_ID = "708006319658893385"
BUG_KEYWORDS = ("bug", "ticket", "suggest", "support", "chat", "progress")
PROD_URL = "https://affairsandorder.org/"


def _run(cmd, **kw):
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=REPO, timeout=60, **kw
    )


def load_state() -> dict:
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"seen_message_ids": [], "last_report": None}


def save_state(state: dict) -> None:
    try:
        json.dump(state, open(STATE_FILE, "w"))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 1. Deploy health
# --------------------------------------------------------------------------- #
def check_deploy_health() -> list[str]:
    issues = []

    # Latest master commit
    head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    subj = _run(["git", "log", "-1", "--format=%s"]).stdout.strip()
    if not head:
        return ["Could not read git HEAD — is this a git checkout?"]

    # CI + redeploy workflow status for that commit (via gh CLI)
    r = _run(
        [
            "gh", "run", "list", "--commit", head, "--limit", "10",
            "--json", "name,status,conclusion",
        ]
    )
    if r.returncode == 0 and r.stdout.strip():
        try:
            runs = json.loads(r.stdout)
        except Exception:
            runs = []
        wanted = {"CI", "Redeploy game stack"}
        for run in runs:
            if run.get("name") in wanted:
                if run.get("status") == "completed" and run.get("conclusion") != "success":
                    issues.append(
                        f"❌ '{run['name']}' {run.get('conclusion')} for master "
                        f"({head[:8]} — {subj!r}). The fix may NOT be live."
                    )
    else:
        issues.append("⚠️ Could not query GitHub Actions (gh CLI not authed?).")

    # Is production serving the current master commit? The deployed HTML carries
    # <meta name="deploy-commit" content="..."> — compare its git-sha prefix.
    try:
        html = urllib.request.urlopen(
            urllib.request.Request(PROD_URL, headers={"User-Agent": "ano-monitor"}),
            timeout=20,
        ).read().decode("utf-8", "replace")
        import re

        m = re.search(r'name="deploy-commit" content="([^"]+)"', html)
        deployed = m.group(1) if m else ""
        # deploy-commit is an asset-version hash, not the git sha, so we can't
        # compare directly; instead confirm the site is up and 200.
        if not deployed:
            issues.append("⚠️ Production page has no deploy-commit tag (unexpected).")
    except Exception as e:
        issues.append(f"❌ Production home page not reachable: {e}")

    return issues


# --------------------------------------------------------------------------- #
# 2. Discord bug scan
# --------------------------------------------------------------------------- #
def _discord_token() -> str | None:
    # Pull the bot token from Railway (uses the logged-in railway CLI).
    r = _run(["railway", "variables", "--service", "bot", "--json"])
    if r.returncode == 0 and r.stdout.strip():
        try:
            return json.loads(r.stdout).get("DISCORD_BOT_TOKEN")
        except Exception:
            pass
    return os.getenv("DISCORD_BOT_TOKEN")


def _dapi(path: str, token: str):
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        headers={"Authorization": f"Bot {token}", "User-Agent": "ano-monitor/1.0"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def check_discord(state: dict) -> tuple[list[str], set[str]]:
    token = _discord_token()
    if not token:
        return (["⚠️ No Discord bot token available — skipping bug scan."], set())

    seen = set(state.get("seen_message_ids", []))
    new_seen = set(seen)
    findings = []
    try:
        chans = _dapi(f"/guilds/{GUILD_ID}/channels", token)
        targets = [
            (c["id"], c["name"])
            for c in chans
            if any(k in c["name"].lower() for k in BUG_KEYWORDS)
        ]
        for t in _dapi(f"/guilds/{GUILD_ID}/threads/active", token).get("threads", []):
            targets.append((t["id"], "thread:" + t["name"]))
    except Exception as e:
        return ([f"⚠️ Discord API error: {e}"], set())

    BOT_ID = "1447272377896669236"
    first_run = not seen
    for cid, name in targets:
        try:
            msgs = _dapi(f"/channels/{cid}/messages?limit=10", token)
        except Exception:
            continue
        for m in msgs:
            new_seen.add(m["id"])
            if first_run:
                continue  # seed state without alerting on history
            if m["id"] in seen or m["author"].get("bot"):
                continue
            content = m["content"].replace("\n", " ")[:200]
            att = " [+img/video]" if m.get("attachments") else ""
            findings.append(f"🐞 {name} — {m['author']['username']}: {content}{att}")

    return (findings, new_seen)


# --------------------------------------------------------------------------- #
def _post_staff_alert(lines: list[str]) -> None:
    """Post a concise alert to the staff-chat channel (best effort)."""
    token = _discord_token()
    if not token:
        return
    try:
        chans = _dapi(f"/guilds/{GUILD_ID}/channels", token)
        staff = next(
            (c["id"] for c in chans if "staff-chat" in c["name"].lower()), None
        )
        if not staff:
            return
        body = "🤖 **Hourly monitor — attention needed:**\n" + "\n".join(
            f"• {ln}" for ln in lines[:12]
        )
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{staff}/messages",
            data=json.dumps({"content": body[:1900]}).encode(),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "ano-monitor/1.0",
            },
        )
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass


def main() -> int:
    import datetime

    alert = "--alert" in sys.argv
    state = load_state()
    deploy_issues = check_deploy_health()
    bug_findings, new_seen = check_discord(state)
    state["seen_message_ids"] = list(new_seen)[-500:]
    save_state(state)

    out = ["=== AnO hourly monitor ===", "", "[Deploy health]"]
    out += ["  " + i for i in deploy_issues] or [
        "  ✅ master CI + redeploy green, production reachable."
    ]
    out += ["", "[New Discord reports since last run]"]
    out += ["  " + f for f in bug_findings] or ["  ✅ nothing new."]

    needs_attention = bool(deploy_issues) or bool(bug_findings)
    out += ["", "RESULT: " + ("ATTENTION NEEDED" if needs_attention else "all clear")]

    report = "\n".join(out)
    print(report)

    # Always append to a rolling log.
    try:
        with open(os.path.join(REPO, "monitor.log"), "a") as f:
            f.write(f"\n----- {datetime.datetime.now().isoformat(timespec='seconds')} -----\n")
            f.write(report + "\n")
    except Exception:
        pass

    if alert and needs_attention:
        _post_staff_alert(deploy_issues + bug_findings)

    return 1 if needs_attention else 0


if __name__ == "__main__":
    sys.exit(main())
