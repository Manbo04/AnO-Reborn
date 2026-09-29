from datetime import date

from app_core.analytics.service import (
    classify_device, external_referrer_host, is_bot, should_track_path, visitor_hash,
)


def test_classify_device():
    assert classify_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile") == "mobile"
    assert classify_device("Mozilla/5.0 (iPad; CPU OS 17_0)") == "tablet"
    assert classify_device("Mozilla/5.0 (Linux; Android 14; SM-X700)") == "tablet"
    assert classify_device("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140") == "desktop"


def test_is_bot():
    assert is_bot("Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert is_bot("")
    assert not is_bot("Mozilla/5.0 (Macintosh) AppleWebKit Safari/605")


def test_external_referrer_host():
    assert external_referrer_host("https://www.google.com/search?q=x") == "google.com"
    assert external_referrer_host("https://affairsandorder.org/x") is None
    assert external_referrer_host("https://www.affairsandorder.com/") is None
    assert external_referrer_host(None) is None
    assert external_referrer_host("garbage") is None


def test_visitor_hash():
    a = visitor_hash("s", "1.2.3.4", "ua", date(2026, 9, 29))
    assert a == visitor_hash("s", "1.2.3.4", "ua", date(2026, 9, 29)) and len(a) == 16
    assert a != visitor_hash("s", "1.2.3.4", "ua", date(2026, 9, 30))


def test_should_track_path():
    assert should_track_path("/")
    assert should_track_path("/country/id=5")
    assert not should_track_path("/static/a.css")
    assert not should_track_path("/api/x")
    assert not should_track_path("/robots.txt")
