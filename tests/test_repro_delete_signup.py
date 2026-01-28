from test_auth import register, delete_user, register_session
import credentials


def test_create_delete_signup_repro():
    """Reproduce: create → delete → signup (should be allowed).

    Uses existing helpers in `test_auth.py` so behavior matches test suite.
    """
    # Create the account
    assert register(register_session) is True

    # Delete the account (session should still be authenticated)
    assert (
        delete_user(credentials.username, credentials.email, register_session) is True
    )

    # Attempt to sign up again — this should succeed (no persistent blocker)
    assert register(register_session) is True
