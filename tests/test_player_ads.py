"""Player advertisement helpers and upload handling."""
from unittest.mock import MagicMock, patch

import pytest

from app_core.ads.helpers import (
    load_rotating_ads,
    normalize_ad_image_url,
    reset_ad_cache,
    save_ad_image_upload,
)

pytestmark = pytest.mark.no_server


def test_normalize_ad_image_url_external():
    assert (
        normalize_ad_image_url("https://cdn.example.com/ad.png")
        == "https://cdn.example.com/ad.png"
    )


def test_normalize_ad_image_url_upload_filename():
    assert normalize_ad_image_url("abc.png") == "/static/uploads/ads/abc.png"


def test_normalize_ad_image_url_static_path():
    assert normalize_ad_image_url("/static/uploads/ads/x.jpg") == (
        "/static/uploads/ads/x.jpg"
    )


def test_load_rotating_ads_caches_results():
    reset_ad_cache()
    calls = {"count": 0}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            calls["count"] += 1

        def fetchone(self):
            return ("/static/uploads/ads/top.png", "https://example.com")

        def fetchall(self):
            return []

    def fake_get_cursor(**kwargs):
        return FakeCursor()

    first = load_rotating_ads(fake_get_cursor)
    second = load_rotating_ads(fake_get_cursor)
    assert first["top_ad"]["image_url"] == "/static/uploads/ads/top.png"
    assert second["top_ad"]["image_url"] == "/static/uploads/ads/top.png"
    assert calls["count"] == 2


def test_save_ad_image_upload_rejects_missing_file(tmp_path):
    ok, msg = save_ad_image_upload(None, str(tmp_path))
    assert not ok
    assert "required" in msg.lower()


def _fake_png_upload():
    from io import BytesIO

    from PIL import Image
    from werkzeug.datastructures import FileStorage

    buf = BytesIO()
    Image.new("RGB", (10, 10), color=(100, 150, 200)).save(buf, format="PNG")
    buf.seek(0)
    return FileStorage(stream=buf, filename="ad.png", content_type="image/png")


def test_save_ad_image_upload_rejects_nsfw_content(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDMERSIVE_API_KEY", "fake-key")
    fake_response = MagicMock()
    fake_response.json.return_value = {"Successful": True, "Score": 0.99}
    fake_response.raise_for_status.return_value = None
    with patch("app_core.ads.helpers.requests.post", return_value=fake_response):
        ok, msg = save_ad_image_upload(_fake_png_upload(), str(tmp_path))
    assert not ok
    assert "moderation" in msg.lower()


def test_save_ad_image_upload_allows_safe_content(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDMERSIVE_API_KEY", "fake-key")
    fake_response = MagicMock()
    fake_response.json.return_value = {"Successful": True, "Score": 0.01}
    fake_response.raise_for_status.return_value = None
    with patch("app_core.ads.helpers.requests.post", return_value=fake_response):
        ok, url = save_ad_image_upload(_fake_png_upload(), str(tmp_path))
    assert ok
    assert url.startswith("/static/uploads/ads/")


def test_save_ad_image_upload_fails_open_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDMERSIVE_API_KEY", raising=False)
    ok, url = save_ad_image_upload(_fake_png_upload(), str(tmp_path))
    assert ok
    assert url.startswith("/static/uploads/ads/")


def test_save_ad_image_upload_fails_open_on_api_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDMERSIVE_API_KEY", "fake-key")
    with patch("app_core.ads.helpers.requests.post", side_effect=Exception("timeout")):
        ok, url = save_ad_image_upload(_fake_png_upload(), str(tmp_path))
    assert ok
    assert url.startswith("/static/uploads/ads/")


def test_get_pending_ads_uses_dict_cursor():
    """Regression test: admin_ads.html reads ad.id/ad.image_url/etc as
    attributes, which only works on RealDictCursor rows, not the plain
    tuples get_request_cursor() returns by default."""
    from psycopg2.extras import RealDictCursor

    from app_core.ads.repositories import AdRepository

    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            pass

        def fetchall(self):
            return [
                {
                    "id": 1,
                    "user_id": 2,
                    "image_url": "/static/uploads/ads/x.png",
                    "target_url": "https://example.com",
                    "ad_type": "top",
                    "status": "pending",
                    "created_at": "2026-09-14",
                }
            ]

    def fake_get_request_cursor(**kwargs):
        captured.update(kwargs)
        return FakeCursor()

    with patch(
        "app_core.ads.repositories.get_request_cursor",
        side_effect=fake_get_request_cursor,
    ):
        rows = AdRepository().get_pending_ads()

    assert captured.get("cursor_factory") is RealDictCursor
    assert rows[0]["id"] == 1


def test_admin_ads_template_renders_pending_ad_with_approve_reject():
    """Regression test: admin_ads.html used to read an `ads` variable that
    routes.py never passed (it passes `pending_ads`), so the panel always
    rendered "No advertisements found" even with real pending ads waiting."""
    import os

    from jinja2 import Environment, FileSystemLoader

    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = Environment(loader=FileSystemLoader(templates_dir))
    env.globals["url_for"] = lambda endpoint, **kwargs: {
        "ads.admin_ads": "/admin/ads",
        "ads.upload_ad": "/ads",
    }.get(endpoint, "/" + endpoint)
    env.globals["get_flashed_messages"] = lambda with_categories=False: []

    src = open(os.path.join(templates_dir, "admin_ads.html")).read()
    src = (
        src.replace('{% extends "layout.html" %}', "")
        .replace("{% block title %}Manage Advertisements{% endblock %}", "")
        .replace("{% block body %}", "")
        .replace("{% endblock %}", "")
    )
    tmpl = env.from_string(src)

    pending_ads = [
        {
            "id": 42,
            "user_id": 69697588,
            "image_url": "/static/uploads/ads/abc123.png",
            "target_url": "https://example.com",
            "ad_type": "top",
            "status": "pending",
            "created_at": "2026-09-14 10:00:00",
        }
    ]
    out = tmpl.render(pending_ads=pending_ads)

    assert "Approve" in out
    assert "Reject" in out
    assert "No pending advertisements" not in out
    assert "https://example.com" in out


def test_set_user_password_preserves_discord_snowflake():
    from database import set_user_password

    db = MagicMock()
    hashed = "$2b$14$abcdefghijklmnopqrstuv"
    with patch(
        "database.get_users_password_column_names",
        return_value={"hash"},
    ):
        with patch("database.users_table_has_column", return_value=True):
            set_user_password(db, 99, hashed)

    calls = [c[0][0].strip() for c in db.execute.call_args_list]
    assert any("SET discord_id = hash" in q for q in calls)
    assert any("UPDATE users SET hash" in q for q in calls)
