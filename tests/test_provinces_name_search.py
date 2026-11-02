import pytest
from contextlib import contextmanager

from repositories.province_repository import ProvinceRepository
from services.province_service import ProvinceService

pytestmark = pytest.mark.no_server


class _FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))

    def fetchall(self):
        return [(7, "Alpha")]


def _patch_cursor(monkeypatch):
    cur = _FakeCursor()

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    monkeypatch.setattr("repositories.province_repository.get_request_cursor", fake_cursor)
    return cur


def test_search_is_scoped_to_user_and_escapes_wildcards(monkeypatch):
    cur = _patch_cursor(monkeypatch)
    rows = ProvinceRepository.search_provinces_by_name(16, r"50%_\x")
    assert rows == [(7, "Alpha")]
    sql, params = cur.calls[0]
    assert "userId=(%s)" in sql and "ESCAPE" in sql
    assert params[0] == 16
    assert params[1] == r"%50\%\_\\x%"
    assert params[2] == 20


def test_service_blank_query_does_not_hit_db(monkeypatch):
    cur = _patch_cursor(monkeypatch)
    assert ProvinceService.search_user_provinces(16, "   ") == []
    assert ProvinceService.search_user_provinces(16, None) == []
    assert cur.calls == []


def test_service_truncates_long_query(monkeypatch):
    cur = _patch_cursor(monkeypatch)
    ProvinceService.search_user_provinces(16, "a" * 500)
    assert cur.calls[0][1][1] == "%" + "a" * 50 + "%"
