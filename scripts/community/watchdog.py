"""Hourly production health watchdog (2026-10-05).

Run by .github/workflows/health-watchdog.yml. Checks the live game from the
outside and heals what it safely can, so nobody has to notice outages by hand:

  site       /health answers 200 (3 tries)              heal: redeploy web
  ticks      /deploy-info economy tasks not stale       heal: redeploy celery-worker
  deploy     live commit == master within 45 minutes    heal: redeploy web,celery-worker
  pipeline   last "Redeploy game stack" run succeeded   (alert only)

Alerts go to #staff-chat only when a check changes state (and a reminder every
6h while it stays broken). If a heal didn't fix it by the next run, Dede is
pinged. State lives in health.json on the community-queue branch.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from sync import STAFF_CHAT, Queue, iso, now, parse, send  # noqa: E402

SITE = "https://affairsandorder.org"
REPO = "Manbo04/AnO-Reborn"
DEDE = "710359818329915443"
REMIND_HOURS = 6
DEPLOY_GRACE_MIN = 45
HEAL_COOLDOWN_MIN = 90


def http(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "ano-watchdog/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def gh_json(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[:200])
    return json.loads(out.stdout)


def check_site():
    last = None
    for _ in range(3):
        try:
            code, body = http(SITE + "/health")
            if code == 200:
                return True, "ok"
            last = f"HTTP {code}"
        except Exception as e:  # timeouts, 5xx, DNS
            last = str(e)[:120]
        time.sleep(20)
    return False, f"/health failing ({last})"


def deploy_info():
    code, body = http(SITE + "/deploy-info")
    return json.loads(body)


def check_ticks(info):
    tasks = info.get("economy_tasks") or {}
    stale = [f"{k} ({v.get('age_minutes')} min old)" for k, v in tasks.items() if v.get("stale")]
    if info.get("economy_stale") or stale:
        return False, "game ticks stopped: " + (", ".join(stale) or "economy marked stale")
    return True, "ok"


def check_deploy(info):
    """Deploys only run for code changes (railway-redeploy-stack.yml), so the
    live commit should match the last successful deploy job's commit once that
    job has had DEPLOY_GRACE_MIN to roll out."""
    live = (info.get("git_commit") or info.get("boot_marker") or "")[:12]
    runs = gh_json(f"repos/{REPO}/actions/workflows/railway-redeploy-stack.yml/runs?branch=master&per_page=30")
    ok_runs = [r for r in runs.get("workflow_runs", []) if r.get("conclusion") == "success"]
    # Don't trust the API's ordering (it has returned a weeks-old run first).
    run = max(ok_runs, key=lambda r: r["created_at"]) if ok_runs else None
    if not run or not live or live == "unknown":
        return True, "ok"
    expected = run["head_sha"]
    if expected.startswith(live) or live.startswith(expected[:12]):
        return True, "ok"
    age = (now() - parse(run["updated_at"])).total_seconds() / 60
    if age < DEPLOY_GRACE_MIN:
        return True, "ok"
    return False, f"live game still runs {live[:8]}, but {expected[:8]} was deployed {int(age)} min ago and never went live"


def check_pipeline():
    runs = gh_json(f"repos/{REPO}/actions/workflows/railway-redeploy-stack.yml/runs?branch=master&per_page=30")
    run = max(runs.get("workflow_runs", []), key=lambda r: r["created_at"], default=None)
    if run and run.get("status") == "completed" and run.get("conclusion") not in ("success", "skipped"):
        return False, f"last deploy job {run['conclusion']}: {run['html_url']}"
    return True, "ok"


def heal(services):
    if not os.environ.get("RAILWAY_TOKEN"):
        return "no RAILWAY_TOKEN, can't redeploy"
    out = subprocess.run(
        ["python3", "scripts/railway_production_fix.py", "--redeploy-only", "--services", services],
        capture_output=True, text=True, timeout=600,
    )
    return "redeployed " + services if out.returncode == 0 else f"redeploy {services} failed: {out.stderr[-200:]}"


HEALS = {"site": "web", "ticks": "celery-worker", "deploy": "web,celery-worker"}
LABELS = {"site": "Website", "ticks": "Game ticks", "deploy": "Deploy", "pipeline": "Deploy pipeline"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default="community-queue")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    import sync
    sync.DRY = args.dry_run

    q = Queue(args.queue)
    state = q.load("health.json", default={}) or {}
    results = {}
    ok, msg = check_site()
    results["site"] = (ok, msg)
    if ok:
        try:
            info = deploy_info()
            results["ticks"] = check_ticks(info)
            results["deploy"] = check_deploy(info)
        except Exception as e:
            results["site"] = (False, f"/deploy-info failing ({str(e)[:120]})")
    try:
        results["pipeline"] = check_pipeline()
    except Exception as e:
        print("pipeline check skipped:", e)

    lines, ping = [], False
    for key, (ok, msg) in results.items():
        prev = state.get(key) or {"ok": True}
        entry = {"ok": ok, "msg": msg, "checked_at": iso(now())}
        if ok:
            if not prev.get("ok", True):
                lines.append(f"✅ **{LABELS[key]}** is healthy again.")
            state[key] = entry
            continue
        if key != "site" and prev.get("ok", True) and not prev.get("pending"):
            # First failure: wait for a second consecutive one before acting
            # (GitHub's API and tick timing can be briefly inconsistent).
            state[key] = {"ok": True, "pending": True, "msg": msg, "checked_at": iso(now())}
            continue
        entry["since"] = prev.get("since") if not prev.get("ok") else iso(now())
        entry["alerted_at"] = prev.get("alerted_at")
        entry["healed_at"] = prev.get("healed_at")
        action = ""
        if key in HEALS:
            last_heal = parse(entry["healed_at"]) if entry.get("healed_at") else None
            if last_heal and (now() - last_heal).total_seconds() / 60 < HEAL_COOLDOWN_MIN:
                ping = True  # healed recently and still broken: a human is needed
            else:
                action = heal(HEALS[key]) if not args.dry_run else f"[dry-run] would redeploy {HEALS[key]}"
                entry["healed_at"] = iso(now())
        first = prev.get("ok", True)
        due = not entry.get("alerted_at") or (now() - parse(entry["alerted_at"])).total_seconds() > REMIND_HOURS * 3600
        if first or due or action or ping:
            lines.append(f"⚠️ **{LABELS[key]}**: {msg}" + (f" — {action}" if action else ""))
            entry["alerted_at"] = iso(now())
        state[key] = entry

    print(json.dumps({k: v for k, v in results.items()}, default=str))
    if lines:
        text = "**Health watchdog**\n" + "\n".join(lines)
        if ping:
            text += f"\n<@{DEDE}> automatic restart didn't fix this, needs a look."
        send(STAFF_CHAT, text, ping_users=[DEDE] if ping else [])
    q.save(state, "health.json")


if __name__ == "__main__":
    main()
