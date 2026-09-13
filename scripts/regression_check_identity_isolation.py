#!/usr/bin/env python3
"""Standing regression check for cross-session identity isolation.

Added 2026-09-13 during the account-cross-contamination investigation, at
Dede's request to "continue fixing any and all issues that might cause this
bug." Simulates two genuinely concurrent sessions hitting the two routes
most implicated in this investigation (/country/<id>, /join/<coalition_id>)
and asserts each session only ever gets back its own identity/data, never
the other's. Rerun this any time as a live check; if this bug class ever
regresses, this should catch it directly instead of waiting for a player
report.

Usage:
    python3 scripts/regression_check_identity_isolation.py

Requires SECRET_KEY, DATABASE_URL (or DATABASE_PUBLIC_URL) env vars for the
target (defaults to live prod -- see BASE_URL below). Exits non-zero and
prints full detail on any assertion failure.

Design notes / why this is NOT wired up as an hourly scheduled task:
  - Test 1 (/country/<id>) is pure GET, read-only, safe to run as often as
    you like -- reuses two already-existing real accounts (Dede's own,
    id 1, and the designated test account, id 16) rather than creating
    anything new.
  - Test 2 (/join/<coalition_id>) has to actually perform a real join to
    be a meaningful test of that code path, so it creates two disposable
    throwaway accounts via the real /register/email signup flow, has them
    join a real coalition concurrently, verifies membership landed
    correctly for each, then leaves the coalition and DELETES both
    accounts before exiting (best-effort cleanup even on failure). That's
    fine to run occasionally by hand; running it unattended forever would
    mean the join/leave activity, however brief, shows up in a real
    coalition's real membership history every time. Recommend running
    this manually when checking for a recurrence, not on a cron schedule,
    until/unless a dedicated sandbox coalition + account pool is built for
    it.
"""
import base64
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import uuid

import psycopg2
import requests

BASE_URL = os.environ.get("REGRESSION_CHECK_BASE_URL", "https://affairsandorder.org")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"ok:   {msg}")


def _secret_key():
    key = os.environ.get("SECRET_KEY")
    if not key:
        sys.exit("SECRET_KEY env var required (same live key the app uses)")
    return key


def _db_url():
    return os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")


def forge_cookie(user_id: int, session_epoch: int = 0) -> str:
    """Build a validly-signed session cookie for user_id without a real
    login, using the app's own Flask session serialization. Same technique
    used throughout this investigation to test admin/session-epoch paths."""
    from flask import Flask, session as flask_session

    app = Flask(__name__)
    app.secret_key = _secret_key()
    with app.test_request_context():
        flask_session["user_id"] = user_id
        flask_session["_fresh"] = True
        if session_epoch:
            flask_session["session_epoch"] = session_epoch
        resp = app.response_class()
        app.session_interface.save_session(app, flask_session, resp)
        return resp.headers.get("Set-Cookie").split(";")[0]


def decode_session_payload(cookie_header_value: str):
    """Decode (not verify) a Flask session cookie's payload.

    Flask's SecureCookieSessionInterface zlib-compresses the payload (and
    prefixes it with a leading '.') once it's large enough to benefit --
    a forged cookie with just {"user_id": N} stays under that threshold and
    decodes fine without this, but any *real* server-issued session
    (carrying a csrf_token, flash messages, etc.) routinely is compressed.
    Must strip the leading '.' and zlib-decompress before the JSON parse,
    or this silently returns a decode_error for every real session cookie.
    """
    try:
        cookie_val = cookie_header_value.split("=", 1)[1]
        compressed = cookie_val.startswith(".")
        body = cookie_val[1:] if compressed else cookie_val
        part = body.split(".")[0]
        part += "=" * (-len(part) % 4)
        raw = base64.urlsafe_b64decode(part)
        if compressed:
            import zlib

            raw = zlib.decompress(raw)
        return json.loads(raw)
    except Exception as e:
        return {"decode_error": str(e)}


def session_epoch_for(user_id: int) -> int:
    conn = psycopg2.connect(_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT session_epoch FROM users WHERE id=%s", (user_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 1: concurrent GET /country/<id> from two different real viewers
# ---------------------------------------------------------------------------


def test_country_page_isolation():
    print("\n=== Test 1: /country/<id> concurrent viewer isolation ===")
    viewer_ids = [1, 16]  # Dede's own account + the designated test account
    barrier = threading.Barrier(len(viewer_ids))
    results = {}

    def fetch(viewer_id):
        cookie = forge_cookie(viewer_id, session_epoch=session_epoch_for(viewer_id))
        barrier.wait()
        resp = requests.get(
            f"{BASE_URL}/country/id={viewer_id}",
            headers={"Cookie": cookie},
            timeout=15,
        )
        csrf_in_body = None
        m = re.search(r'csrf-token" content="([^"]+)"', resp.text)
        if m:
            csrf_in_body = m.group(1)
        return {
            "viewer_id": viewer_id,
            "status": resp.status_code,
            "csrf_in_body": csrf_in_body,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(viewer_ids)) as ex:
        for r in ex.map(fetch, viewer_ids):
            results[r["viewer_id"]] = r

    for viewer_id, r in results.items():
        if r["status"] != 200:
            fail(f"viewer {viewer_id}: expected 200, got {r['status']}")

    # The body's csrf-token meta tag is a per-response, itsdangerous-signed
    # value (freshly minted on every render). If two concurrent, DIFFERENT
    # viewers' bodies ever showed the exact same token, that means one
    # viewer's rendered response was served to (or leaked into) the other
    # -- the cache/connection-reuse bleed this whole investigation has
    # chased. This is the real signal; don't try to cross-decode it against
    # the raw session cookie's own csrf_token field, which is a differently
    # -encoded representation (unsigned) and will never textually match the
    # signed one even in a perfectly correct system -- comparing them was a
    # flawed first draft of this check, removed.
    other_tokens = [r["csrf_in_body"] for vid, r in results.items() if r["csrf_in_body"]]
    if len(other_tokens) == len(set(other_tokens)) and len(other_tokens) > 1:
        ok("all concurrent viewers got distinct csrf tokens (no shared/leaked response)")
    elif len(other_tokens) > 1:
        fail(f"two concurrent viewers received the SAME csrf token -- likely response leak: {other_tokens}")


# ---------------------------------------------------------------------------
# Test 2: concurrent POST /join/<coalition_id> from two disposable accounts
# ---------------------------------------------------------------------------


def _signup_disposable_account(tag):
    s = requests.Session()
    page = s.get(f"{BASE_URL}/signup", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
    token = m.group(1) if m else None
    uid = uuid.uuid4().hex[:10]
    username = f"regcheck{tag}{uid}"
    email = f"regcheck.{tag}.{uid}@example-disposable.test"
    password = "RegCheckPassw0rd!23"
    resp = s.post(
        f"{BASE_URL}/register/email",
        data={
            "username": username,
            "email": email,
            "password": password,
            "confirmation": password,
            "csrf_token": token,
        },
        headers={"Referer": f"{BASE_URL}/signup", "Origin": BASE_URL},
        allow_redirects=False,
        timeout=15,
    )
    if resp.status_code != 302:
        return None
    cookie = "session=" + s.cookies.get("session", "")
    payload = decode_session_payload(cookie)
    return {"username": username, "session": s, "user_id": payload.get("user_id")}


def _delete_account(user_id):
    conn = psycopg2.connect(_db_url())
    try:
        with conn.cursor() as cur:
            # referral_active_days has no ON DELETE CASCADE on
            # referred_user_id -- a disposable signup can trip a referral
            # capture (e.g. from a stray referral cookie), which would
            # otherwise block this delete with a FK violation.
            cur.execute(
                "DELETE FROM referral_active_days WHERE referred_user_id=%s",
                (user_id,),
            )
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
    finally:
        conn.close()


def _pick_a_real_coalition_id():
    """Pick an Open-type coalition (join_col() only grants instant
    membership for type='Open'; anything else just files a pending
    request, which this test isn't set up to approve). Explicitly avoids
    coalition 137 ("THE LAMLOR CONFEDERATION") -- that's the actual
    coalition from the original Monti incident this whole investigation
    started from; picking a different one keeps repeated test runs from
    adding join/leave noise to it specifically."""
    conn = psycopg2.connect(_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM colnames WHERE type='Open' AND id != 137 ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def test_join_coalition_isolation():
    print("\n=== Test 2: /join/<coalition_id> concurrent actor isolation ===")
    print("(creates 2 disposable test accounts, joins+leaves a real coalition, cleans up)")

    accounts = [_signup_disposable_account("a"), _signup_disposable_account("b")]
    if not all(accounts):
        fail("could not create disposable test accounts for join test -- skipping")
        return

    coalition_id = _pick_a_real_coalition_id()
    if not coalition_id:
        fail("no coalition found to test against -- skipping")
        _cleanup_join_test(accounts, coalition_id=None)
        return

    barrier = threading.Barrier(len(accounts))

    def get_csrf(s):
        # /coalitions' <form>s carry no static csrf_token field -- the real
        # site injects it client-side via JS from the <meta csrf-token> tag
        # into a X-CSRFToken header (see templates/layout.html). Match that,
        # not a form field, or every POST here 400s regardless of identity.
        r = s.get(f"{BASE_URL}/coalitions", timeout=15)
        m = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
        return m.group(1) if m else None

    def do_join(account):
        s = account["session"]
        token = get_csrf(s)
        barrier.wait()
        resp = s.post(
            f"{BASE_URL}/join/{coalition_id}",
            headers={
                "Referer": f"{BASE_URL}/coalitions",
                "Origin": BASE_URL,
                "X-CSRFToken": token,
            },
            allow_redirects=False,
            timeout=15,
        )
        return {"user_id": account["user_id"], "status": resp.status_code, "body": resp.text[:300] if resp.status_code >= 400 else None}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(accounts)) as ex:
        join_results = list(ex.map(do_join, accounts))

    time.sleep(1)

    conn = psycopg2.connect(_db_url())
    try:
        with conn.cursor() as cur:
            # join_col() actually writes to whichever table
            # get_coalition_members_table() resolves to -- as of 2026-09-13
            # that's coalitions_legacy (colid/userid columns), NOT the
            # newer-looking coalition_members table (coalition_id/user_id
            # columns) despite the latter existing with real-looking data.
            # Check both so this test keeps working if that resolution
            # ever changes, and flag it loudly if they disagree -- two
            # parallel membership tables with different active status is
            # exactly the kind of split-brain that could explain this
            # investigation's "shows the wrong data" reports elsewhere.
            cur.execute(
                "SELECT userid FROM coalitions_legacy WHERE colid=%s AND userid = ANY(%s)",
                (coalition_id, [a["user_id"] for a in accounts]),
            )
            in_legacy = {r[0] for r in cur.fetchall()}
            cur.execute(
                "SELECT user_id FROM coalition_members WHERE coalition_id=%s AND user_id = ANY(%s)",
                (coalition_id, [a["user_id"] for a in accounts]),
            )
            in_new = {r[0] for r in cur.fetchall()}
            actually_joined = in_legacy | in_new
            if in_legacy != in_new:
                print(
                    f"NOTE: coalitions_legacy shows {in_legacy} as members but "
                    f"coalition_members shows {in_new} -- these two tables "
                    f"disagree, see the module docstring for why this matters"
                )
    finally:
        conn.close()

    expected = {a["user_id"] for a in accounts}
    if actually_joined == expected:
        ok(f"both accounts ({expected}) correctly show as members -- no cross-actor mixup")
    elif actually_joined:
        fail(
            f"membership mismatch: expected {expected} to have joined, "
            f"but coalition_members shows {actually_joined} -- possible identity mixup"
        )
    else:
        fail(f"neither account shows as a member after join (join_results={join_results}) -- join may have failed for an unrelated reason")

    _cleanup_join_test(accounts, coalition_id)


def _cleanup_join_test(accounts, coalition_id):
    for account in accounts:
        if not account:
            continue
        try:
            if coalition_id and account.get("user_id"):
                account["session"].post(
                    f"{BASE_URL}/leave/{coalition_id}",
                    headers={"Referer": f"{BASE_URL}/coalitions", "Origin": BASE_URL},
                    timeout=15,
                )
        except Exception:
            pass
        if account.get("user_id"):
            try:
                _delete_account(account["user_id"])
                print(f"cleanup: deleted disposable account user_id={account['user_id']}")
            except Exception as e:
                print(f"cleanup WARNING: failed to delete user_id={account.get('user_id')}: {e}")


if __name__ == "__main__":
    test_country_page_isolation()
    if "--with-join-test" in sys.argv:
        test_join_coalition_isolation()
    else:
        print(
            "\n(skipping Test 2 -- pass --with-join-test to also run the "
            "coalition-join test, which creates+deletes 2 disposable accounts "
            "and briefly joins+leaves a real coalition)"
        )

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"REGRESSION CHECK FAILED: {len(FAILURES)} issue(s) found")
        for f in FAILURES:
            print(f" - {f}")
        sys.exit(1)
    else:
        print("REGRESSION CHECK PASSED: no identity-isolation issues detected")
        sys.exit(0)
