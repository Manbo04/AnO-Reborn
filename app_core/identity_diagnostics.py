"""Persistent per-request diagnostic logging for identity-sensitive routes.

Added 2026-09-13 during the account-cross-contamination investigation
(Monti 2026-09-12, veyro/xs 2026-09-13, an official-bot-confirmed recurrence
of the same symptom for player Ibby on 2026-09-09). The investigation kept
losing evidence to Railway's own ephemeral log retention (roughly a day or
less) before a report could be traced -- both the Sept 9 and the already-once
-pulled Sept 12 windows became permanently unavailable within the same
investigation. This writes a small, persistent (DB table, 30+ day retention)
row per request on the routes most implicated so far (/country/<id>,
/join/<coalition_id>, and as of 2026-09-21 also /my_country, /account,
/military, /statistics, /rankings -- widened after a report on one of
these produced zero evidence under the narrower coverage), so the *next*
occurrence can be traced with real per-request forensic data instead of
starting from Discord screenshots again.

Deliberately cheap and fire-and-forget: a logging failure must never break
the request it's instrumenting.
"""
import os
import threading
from time import time

from flask import request, session


def _safe_insert(route, session_user_id, cache_hit, severity, detail):
    try:
        from database import get_request_cursor
        from helpers import session_cookie_fingerprint, client_ip_from_request
        import json

        cookie_fp = session_cookie_fingerprint()
        ip = client_ip_from_request()

        with get_request_cursor() as db:
            db.execute(
                """
                INSERT INTO identity_diagnostic_log
                    (route, session_user_id, cookie_fp, ip, worker_pid,
                     thread_id, cache_hit, severity, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    route,
                    session_user_id,
                    cookie_fp,
                    ip,
                    os.getpid(),
                    threading.get_ident(),
                    cache_hit,
                    severity,
                    json.dumps(detail) if detail is not None else None,
                ),
            )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "identity_diagnostic_log insert failed for route=%s", route
        )


def log_identity_diagnostic(route, cache_hit=None):
    """Fire-and-forget diagnostic row for an identity-sensitive request.

    Call once near the top of an instrumented view, after session["user_id"]
    is known to be resolvable (post @login_required, or after the anonymous
    case is handled) but before any state-changing work happens.
    """
    session_user_id = session.get("user_id")
    _safe_insert(route, session_user_id, cache_hit, "info", None)


def _alert_staff_of_critical(route, detail):
    """Real-time page, not a passive DB row: DM the account owner the
    moment a CRITICAL identity_diagnostic_log row is written. A tripwire
    nobody queries until days later isn't actually a tripwire -- this
    turns it into an instant alert.
    """
    try:
        from database import get_request_cursor
        from app_core.discord_notify import send_staff_bot_dm

        with get_request_cursor() as db:
            db.execute("SELECT discord_id FROM users WHERE id=1")
            row = db.fetchone()
        discord_id = row[0] if row and row[0] else None
        if not discord_id:
            return

        message = (
            "🚨 **CRITICAL identity_diagnostic_log tripwire fired**\n\n"
            f"Route: `{route}`\n"
            f"Ambient session user_id: `{detail.get('ambient_session_user_id')}`\n"
            f"Freshly-decoded cookie user_id: `{detail.get('freshly_decoded_cookie_user_id')}`\n"
            f"Worker PID: `{detail.get('worker_pid')}`  Thread: `{detail.get('thread_id')}`\n\n"
            "A request's own session and its own cookie disagreed on identity "
            "-- this should be structurally impossible under correct Flask "
            "behavior. Check /admin/command-center/identity-diagnostics?"
            "severity=critical for full context."
        )
        send_staff_bot_dm(discord_id, message)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "_alert_staff_of_critical failed for route=%s", route
        )


def check_session_cookie_consistency(route):
    """Independently re-decode the raw incoming session cookie and compare
    its user_id against flask.session's already-resolved user_id for this
    same request.

    Structurally these can never disagree under correct Flask/Werkzeug
    behavior -- session IS populated by decoding this exact cookie at the
    start of the request via the same session_interface used here. That's
    the point: this is a tripwire, not a routine check. If it ever fires,
    something is seriously wrong at a level below the application (shared
    request/session state across two different real requests), which is
    exactly the class of bug this whole investigation has been chasing
    without being able to catch it live. A mismatch logs a CRITICAL row
    immediately with full context for forensic follow-up.
    """
    try:
        from flask import current_app

        raw_cookie_present = "session" in request.cookies
        if not raw_cookie_present:
            return

        fresh_session = current_app.session_interface.open_session(
            current_app, request
        )
        fresh_user_id = fresh_session.get("user_id") if fresh_session else None
        ambient_user_id = session.get("user_id")

        if fresh_user_id != ambient_user_id:
            detail = {
                "check": "session_cookie_consistency_mismatch",
                "ambient_session_user_id": ambient_user_id,
                "freshly_decoded_cookie_user_id": fresh_user_id,
                "path": request.path,
                "worker_pid": os.getpid(),
                "thread_id": threading.get_ident(),
                "timestamp": time(),
            }
            _safe_insert(route, ambient_user_id, None, "critical", detail)
            _alert_staff_of_critical(route, detail)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "check_session_cookie_consistency failed for route=%s", route
        )
