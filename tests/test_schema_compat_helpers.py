"""Unit tests for schema compatibility helpers (no DB required for validation)."""

from database import get_coalition_members_table, users_is_compat_view


def test_coalition_members_table_whitelist(monkeypatch):
    """Resolved table name must be one of the known legacy tables."""

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            pass

        def fetchone(self):
            return ("coalitions",)

    class FakeConn:
        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    class FakeCtx:
        def __enter__(self):
            return FakeCursor()

        def __exit__(self, *args):
            pass

    import database as db_mod

    monkeypatch.setattr(db_mod, "_schema_compat_applied", True)
    monkeypatch.setattr(db_mod, "_coalition_members_table_cache", None)
    monkeypatch.setattr(db_mod, "get_db_cursor", lambda: FakeCtx())

    assert get_coalition_members_table() == "coalitions"


def test_users_is_compat_view_cached(monkeypatch):
    import database as db_mod

    db_mod._users_is_compat_view_cache = None
    monkeypatch.setattr(db_mod, "_public_relation_kind", lambda _n: "v")
    assert users_is_compat_view() is True
    assert users_is_compat_view() is True  # cached


def test_users_is_compat_view_table(monkeypatch):
    import database as db_mod

    db_mod._users_is_compat_view_cache = None
    monkeypatch.setattr(db_mod, "_public_relation_kind", lambda _n: "r")
    assert users_is_compat_view() is False
