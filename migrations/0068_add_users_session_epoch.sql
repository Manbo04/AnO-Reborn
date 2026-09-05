-- Migration: 0068 - users.session_epoch (real session invalidation)
-- Date: 2026-09-05
--
-- Following the admin-kick-doesn't-actually-kick incident (admin_actions row
-- admin_kick_user for user_id=1 at 2026-09-04 05:27:59 UTC, apparently
-- silently swallowed -- a hard-delete via /reset_account happened ~19h
-- later at 2026-09-05 00:49:28 UTC with no fresh login in between per
-- login_events): admin_user_controls.kick_pending is a one-shot flag,
-- cached per-session in app.py's before_request for up to
-- ADMIN_CTRL_REFRESH_SECONDS (default 300s). If a user has two concurrent
-- sessions (e.g. a stolen/leaked cookie alongside their real browser),
-- whichever session polls the DB first flips kick_pending back to FALSE,
-- so only that one session gets logged out -- the other rides on
-- indefinitely.
--
-- session_epoch is real monotonic per-user state instead: every login
-- embeds the epoch value current at login time into the Flask session, and
-- every request compares it against the live DB value (via the same
-- cached-lookup pattern, so no extra DB round-trip per request). Bumping
-- the epoch (admin kick/ban, password change) invalidates *every* session
-- carrying an older embedded value, not just the first one to poll.

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS session_epoch INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN users.session_epoch IS
    'Monotonic counter embedded into a session at login time (session["session_epoch"]) and compared against this live value on every request (app.py before_request). Bumped by admin kick/ban (app_core/admin/services.py) and password changes (database.set_user_password) to unconditionally invalidate every outstanding session for the user, not just one racing to poll first like kick_pending did.';

COMMIT;
