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

    def cursor(self):
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


def test_buy_missing_amount_returns_400(client):
    # Setup session user
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    resp = client.post("/buy_offer/999", data={})
    assert resp.status_code == 400


def test_buy_invalid_amount_returns_400(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    resp = client.post("/buy_offer/999", data={"amount_999": "abc"})
    assert resp.status_code == 400


def test_buy_offer_not_found_returns_404(client, monkeypatch):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    # Patch DB to return None for the offer select
    class MissingOfferConn(DummyConn):
        def __init__(self):
            super().__init__(fetchone_result=None)

    import psycopg2

    monkeypatch.setattr(psycopg2, "connect", lambda **kwargs: MissingOfferConn())

    resp = client.post("/buy_offer/999", data={"amount_999": "1"})
    assert resp.status_code == 404
