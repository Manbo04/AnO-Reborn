"""Player advertisement helpers and upload handling."""
from unittest.mock import MagicMock, patch

import pytest

from app_core.ads.helpers import (
    load_rotating_ads,
    normalize_ad_image_url,
    reset_ad_cache,
    save_ad_image_upload,
)


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
