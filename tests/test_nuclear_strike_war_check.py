"""Nuclear strikes / airstrikes must require an active war with the target."""


class _FakeCursor:
    """Simulates the DB calls made by nuclear_strike()/strategic_airstrike().

    call #1 is always the active-war check added by the fix. When
    `war_exists` is False, it returns no row (so the route must 403 before
    touching weapons/provinces). When True, it returns a row so the route
    proceeds to the next check (weapon quantity), which we deliberately
    make return "no weapons" so the request fails there instead of
    mutating anything.
    """

    def __init__(self, war_exists):
        self.war_exists = war_exists
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1

    def fetchone(self):
        if self.calls == 1:
            return (1,) if self.war_exists else None
        if self.calls == 2:
            # weapon/bomber quantity check: pretend attacker owns none
            return None
        return None


class _FakeCM:
    def __init__(self, war_exists):
        self.war_exists = war_exists

    def __enter__(self):
        return _FakeCursor(self.war_exists)

    def __exit__(self, *args):
        return False


# Real existing production account (also used as the fixture account by
# tests/test_bot_api.py) — needed so app.py's before_request admin-control
# lookup (a real, unmocked, read-only query) finds a real user and lets the
# request reach the route instead of redirecting to /login.
REAL_SESSION_USER_ID = 16


def test_nuclear_strike_rejects_no_active_war(client, monkeypatch):
    monkeypatch.setattr(
        "wars.routes.get_request_cursor", lambda: _FakeCM(war_exists=False)
    )
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID

    resp = client.post(
        "/nuclear_strike",
        data={"target_id": "1", "weapon_type": "nuke"},
    )
    assert resp.status_code == 403
    assert b"not at war" in resp.data


def test_nuclear_strike_proceeds_past_war_check_when_at_war(client, monkeypatch):
    monkeypatch.setattr(
        "wars.routes.get_request_cursor", lambda: _FakeCM(war_exists=True)
    )
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID

    resp = client.post(
        "/nuclear_strike",
        data={"target_id": "1", "weapon_type": "nuke"},
    )
    # Must NOT be rejected for lack of an active war (403) — it should
    # instead reach the weapon-ownership check, which our fake cursor
    # makes fail with a 400. (Apostrophe in the rendered message is
    # HTML-entity-escaped by Jinja autoescaping, so match without it.)
    assert resp.status_code == 400
    assert b"have any" in resp.data


def test_strategic_airstrike_rejects_no_active_war(client, monkeypatch):
    monkeypatch.setattr(
        "wars.routes.get_request_cursor", lambda: _FakeCM(war_exists=False)
    )
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID

    resp = client.post(
        "/strategic_airstrike",
        data={"target_id": "1", "strike_target": "silo", "bombers_count": "5"},
    )
    assert resp.status_code == 403
    assert b"not at war" in resp.data
