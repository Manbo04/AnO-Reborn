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


class _OutgoingCookieMismatchMiddleware:
    """True WSGI middleware -- wraps the whole Flask dispatch, including the
    session interface's own Set-Cookie, unlike an app.after_request hook.

    Added 2026-09-23, ported from the throwaway local staging harness
    (scratch/wsgi_staging_diag.py + the first version of this file's sibling
    module in scratch/) built during the account cross-contamination
    investigation, once BOTH of its own bugs were found and fixed:

    1. The first version used app.after_request to read the outgoing
       Set-Cookie -- but Flask's own session_interface.save_session() (what
       actually sets the session cookie) runs AFTER all after_request
       functions, so that approach could never see a real session cookie at
       all. This version wraps app.wsgi_app directly, which sees the fully
       finalized response.
    2. A version of this class that read the per-thread "what identity did
       THIS request start as" state at the top of __call__ (before
       self.wsgi_app() -- which runs before_request, the thing that
       actually sets it -- had even run) produced a 52944/82234-row false-
       positive storm: it read the PREVIOUS request's leftover value on a
       reused gthread thread. Fixed by resetting to a sentinel at the top
       and reading the real value only inside custom_start_response, which
       fires after the full dispatch completes for THIS exact request.

    check_session_cookie_consistency() above catches a DIFFERENT, narrower
    bug shape: a single request's own incoming cookie disagreeing with its
    own resolved session, which is structurally impossible under correct
    Flask/Werkzeug behavior and has never fired once in this table's
    history. This middleware catches the actual shape the "many different
    real players ended up authenticated as one account" reports describe:
    the OUTGOING response for request A ends up carrying a Set-Cookie whose
    signed payload encodes a DIFFERENT, also-logged-in user than what
    session A started as -- cookies crossing between concurrent
    requests/threads, not a single request's internal consistency.

    Off by default (ANO_OUTGOING_COOKIE_DIAG=1 to enable) -- this has not
    been load-tested against real production traffic patterns the way the
    narrower check above has, so it ships disabled until a maintainer
    explicitly turns it on (e.g. when the real game comes back up after a
    security incident and extra visibility is wanted for a while).
    """

    def __init__(self, wsgi_app, flask_app):
        self.wsgi_app = wsgi_app
        self.flask_app = flask_app
        self._local = threading.local()

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "?")
        self._local.start_user_id = "<unset>"

        def custom_start_response(status, headers, exc_info=None):
            start_user_id = getattr(self._local, "start_user_id", "<unset>")
            try:
                cookie_name = self.flask_app.config.get("SESSION_COOKIE_NAME", "session")
                our_cookie_raw = None
                for k, v in headers:
                    if k.lower() == "set-cookie" and v.startswith(cookie_name + "="):
                        our_cookie_raw = v.split(";", 1)[0][len(cookie_name) + 1:]
                        break

                if our_cookie_raw and start_user_id not in (None, "<unset>"):
                    try:
                        serializer = self.flask_app.session_interface.get_signing_serializer(
                            self.flask_app
                        )
                        decoded = serializer.loads(our_cookie_raw)
                        outgoing_user_id = decoded.get("user_id") if decoded else None
                    except Exception:
                        outgoing_user_id = None

                    if (
                        outgoing_user_id is not None
                        and not isinstance(outgoing_user_id, str)
                        and outgoing_user_id != start_user_id
                    ):
                        detail = {
                            "check": "outgoing_cookie_mismatch",
                            "request_start_user_id": start_user_id,
                            "outgoing_cookie_user_id": outgoing_user_id,
                            "path": path,
                            "worker_pid": os.getpid(),
                            "thread_id": threading.get_ident(),
                            "timestamp": time(),
                        }
                        _safe_insert(path, start_user_id, None, "critical", detail)
                        _alert_staff_of_critical(path, {
                            "ambient_session_user_id": start_user_id,
                            "freshly_decoded_cookie_user_id": outgoing_user_id,
                            "worker_pid": detail["worker_pid"],
                            "thread_id": detail["thread_id"],
                        })
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "outgoing cookie mismatch check failed for path=%s", path
                )
            return start_response(status, headers, exc_info)

        return self.wsgi_app(environ, custom_start_response)


def install_outgoing_cookie_diagnostic(app):
    """Call once at app startup (see app.py). No-op unless
    ANO_OUTGOING_COOKIE_DIAG=1 is set -- see _OutgoingCookieMismatchMiddleware's
    docstring for why this ships disabled by default."""
    if os.environ.get("ANO_OUTGOING_COOKIE_DIAG") != "1":
        return app

    from flask import session as flask_session

    middleware = _OutgoingCookieMismatchMiddleware(app.wsgi_app, app)

    @app.before_request
    def _capture_outgoing_diag_start_identity():
        middleware._local.start_user_id = flask_session.get("user_id")

    app.wsgi_app = middleware
    return app


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
