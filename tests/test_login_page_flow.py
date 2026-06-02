from contextlib import contextmanager


def test_login_button_submits_without_js(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'form action="/login/"' in body
    assert 'button type="submit"' in body
    assert 'button type="button"' not in body


def test_login_missing_credentials_shows_message(client):
    resp = client.post("/login/", data={"username": "", "password": ""})
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert "Please provide both username and password." in body


@contextmanager
def _dummy_cursor_for_unlinked():
    class DummyDB:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return None

    yield DummyDB()


def test_discord_login_missing_token_redirects_with_message(client):
    resp = client.get("/discord_login/", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Discord login session expired" in body


def test_discord_login_unlinked_account_message(client, monkeypatch):
    import login as login_module

    class DummyDiscordResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "discord-user-1"}

    class DummyDiscordClient:
        @staticmethod
        def get(_url):
            return DummyDiscordResponse()

    monkeypatch.setattr(login_module, "make_session", lambda token=None: DummyDiscordClient())
    monkeypatch.setattr(login_module, "get_request_cursor", _dummy_cursor_for_unlinked)

    with client.session_transaction() as sess:
        sess["oauth2_token"] = {"access_token": "fake"}

    resp = client.get("/discord_login/", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "No account linked to this Discord" in body
