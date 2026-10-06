"""Session helpers for tests that use FAKE (mocked, not in the DB) users."""
import time


def mark_validated(sess, epoch=0):
    """Pretend app.before_request already validated this session.

    Every request re-checks the logged-in user against the users table
    (deleted user, ban, kick, session_epoch) and clears the session if the
    row is missing. Tests that mock the database use user ids that do not
    exist, so they set the cached "already checked" marker instead -- the
    same marker a real session carries between DB refreshes.
    """
    sess["_admin_ctrl"] = [False, "", False, epoch]
    sess["_admin_ctrl_ts"] = time.time()
    sess["session_epoch"] = epoch
