import pytest


# Minimal dummy DB objects used to patch psycopg2.connect
class DummyCursor:
    def __init__(self, fetchone_result=None):
        self.fetchone_result = fetchone_result

    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return []


class DummyConn:
    def __init__(self, fetchone_result=None):
        self._cursor = DummyCursor(fetchone_result)

    def cursor(self, cursor_factory=None):
        # Accept cursor_factory kw for compatibility with get_db_cursor
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture(autouse=True)
def disable_real_db(monkeypatch):
    import psycopg2

    monkeypatch.setattr(psycopg2, "connect", lambda **kwargs: DummyConn())
    yield


def test_post_offer_invalid_price_returns_400(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    resp = client.post(
        "/post_offer/sell", data={"resource": "rations", "amount": "1", "price": "abc"}
    )
    assert resp.status_code == 400


def test_post_offer_db_error_returns_500_with_id(client, monkeypatch):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    import psycopg2

    def boom(**kwargs):
        raise Exception("boom")

    monkeypatch.setattr(psycopg2, "connect", boom)

    resp = client.post(
        "/post_offer/sell", data={"resource": "rations", "amount": "1", "price": "1"}
    )
    assert resp.status_code == 500
    assert b"Reference id" in resp.data
