"""CSRF protection on state-changing routes."""
from flask import Flask
from flask_wtf.csrf import CSRFProtect


def test_post_without_csrf_returns_400():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    CSRFProtect(app)

    @app.route("/signup", methods=["POST"])
    def fake_signup():
        return "ok", 200

    client = app.test_client()
    resp = client.post("/signup", data={"username": "x"})
    assert resp.status_code == 400
