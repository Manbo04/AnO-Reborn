"""Peace offers must be limited to war participants."""

import pytest

from helpers import error


@pytest.fixture
def app_ctx():
    from app import app

    app.config["TESTING"] = True
    with app.app_context():
        yield app


def test_send_peace_offer_rejects_non_participant(client, monkeypatch):
    """Non-participants receive 403, not 500."""
    war_id = 999001
    attacker = 16
    defender = 17
    intruder = 999002

    class _FakeCursor:
        calls = 0

        def execute(self, sql, params=None):
            self.calls += 1
            sql_s = str(sql)
            if "attacker_id, defender_id" in sql_s:
                self._war = (attacker, defender)

        def fetchone(self):
            if self.calls == 1:
                return getattr(self, "_war", None)
            return None

    class _FakeCM:
        def __enter__(self):
            return _FakeCursor()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("wars.routes.get_request_cursor", lambda: _FakeCM())

    with client.session_transaction() as sess:
        sess["user_id"] = intruder

    resp = client.post(
        f"/send_peace_offer/{war_id}/{defender}",
        data={},
    )
    assert resp.status_code == 403


def test_error_helper_status_order(app_ctx):
    _body, status = error(403, "forbidden")
    assert status == 403
