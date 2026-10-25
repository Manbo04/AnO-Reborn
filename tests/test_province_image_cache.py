"""The stock province banner must be publicly cacheable (209KB; crawlers and
page loads re-downloaded it with a session cookie on every hit, 2026-10)."""

import os

from flask import Flask

import province


def test_default_province_image_is_public_and_short_lived():
    static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    app = Flask(__name__, static_folder=static)
    with app.test_request_context("/province-image/1"):
        response = province._default_province_image()
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "public, max-age=300"
        assert response.mimetype == "image/jpeg"
        response.close()
