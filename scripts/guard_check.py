#!/usr/bin/env python3
"""Guard: changes that loosen the safety checks need Dede's approval.

Runs from master's copy (pull_request_target), so a PR cannot edit this
file to let itself through. It never runs the PR's code; it only reads
the PR's file list and diff through the GitHub API.

A PR is held when it
  * touches CI, the check scripts, the schema snapshot or test config,
  * deletes a test file or adds a skip/xfail to tests,
  * raises a count in scripts/economy_write_baseline.json.

To approve, Dede puts `guard-approve: 123456` in the PR description,
using the current 6-digit code from the authenticator app that holds
GUARD_TOTP_SECRET (a repo secret no AI has seen). The code is only valid
for a couple of minutes, so it cannot be reused later; every new commit
needs a fresh approval.
"""

import base64
import fnmatch
import hashlib
import hmac
import json
import os
import re
import struct
import subprocess
import sys
import time

PROTECTED = [
    ".github/*",
    ".github/**",
    "scripts/check_*",
    "scripts/ci_full_check.sh",
    "scripts/guard_check.py",
    "scripts/apply_all_pending_migrations.py",
    "scripts/load_schema_snapshot.py",
    "scripts/snapshot_prod_schema.sh",
    "scripts/generate_system_map.py",
    "db/*",
    "setup.cfg",
    "pytest.ini",
    "pyproject.toml",
    "conftest.py",
    "tests/conftest.py",
    "tests/_db_cleanup.py",
    "tests/_session.py",
]
BASELINE = "scripts/economy_write_baseline.json"
SKIP_MARKERS = re.compile(r"pytest\.mark\.(skip|skipif|xfail)|pytest\.skip\(|pytest\.xfail\(|--deselect|unittest\.skip")

REPO = os.environ["REPO"]
PR = os.environ["PR"]


def gh_api(path):
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def pr_files():
    out = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{REPO}/pulls/{PR}/files?per_page=100"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [f for page in json.loads(out) for f in page]


def file_at(path, ref):
    try:
        data = gh_api(f"repos/{REPO}/contents/{path}?ref={ref}")
        return base64.b64decode(data["content"]).decode()
    except subprocess.CalledProcessError:
        return None


def is_protected(name):
    return any(fnmatch.fnmatch(name, pat) for pat in PROTECTED)


def violations():
    found = []
    for f in pr_files():
        name, status = f["filename"], f["status"]
        names = [name] + ([f["previous_filename"]] if f.get("previous_filename") else [])
        if name == BASELINE:
            base = json.loads(file_at(BASELINE, os.environ["BASE_SHA"]) or "{}")
            head = json.loads(file_at(BASELINE, os.environ["HEAD_SHA"]) or "{}")
            raised = [k for k, v in head.items() if v > base.get(k, 0)]
            if raised:
                found.append(f"{BASELINE}: raw-write allowance raised for {', '.join(raised)}")
            continue
        if any(is_protected(n) for n in names):
            found.append(f"{name}: protected file ({status})")
            continue
        in_tests = name.startswith("tests/") or any(n.startswith("tests/") for n in names)
        if in_tests and status == "removed":
            found.append(f"{name}: test file deleted")
            continue
        if status == "renamed" and any(n.startswith("tests/") for n in names) and not name.startswith("tests/"):
            found.append(f"{name}: test file moved out of tests/")
            continue
        if in_tests and name.endswith(".py"):
            added = [l[1:] for l in (f.get("patch") or "").splitlines() if l.startswith("+") and not l.startswith("+++")]
            if any(SKIP_MARKERS.search(l) for l in added):
                found.append(f"{name}: adds a skip/xfail")
    return found


def totp(secret, step):
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = digest[-1] & 0x0F
    return "%06d" % ((struct.unpack(">I", digest[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def approved():
    secret = os.environ.get("GUARD_TOTP_SECRET", "")
    m = re.search(r"guard-approve:\s*(\d{6})", os.environ.get("PR_BODY") or "")
    if not secret or not m:
        return False
    now = int(time.time()) // 30
    # Allow for queue delay: codes from the last ~3 minutes.
    return any(hmac.compare_digest(totp(secret, now - d), m.group(1)) for d in range(-1, 7))


def main():
    found = violations()
    if not found:
        print("guard: no safety-check changes in this PR")
        return 0
    print("guard: this PR changes safety checks:")
    for v in found:
        print("  - " + v)
    if approved():
        print("guard: approved by Dede (valid authenticator code)")
        return 0
    print(
        "\nNeeds Dede's approval: add `guard-approve: <6-digit code>` from the "
        "AnO guard authenticator entry to the PR description."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
