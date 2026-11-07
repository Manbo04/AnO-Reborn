"""Guardrail dashboard helpers: failure must not raise into the page; template parses."""
import pytest

pytestmark = pytest.mark.no_server

from balance import live


def test_current_summary_returns_error_string_when_db_unavailable(monkeypatch):
    live._cached = None
    import database

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(database, "get_db_cursor", boom)
    summary, err = live.current_summary(force=True)
    assert summary is None and "db down" in err


def test_thresholds_match_guardrails():
    t = live.thresholds()
    assert t["max_share_net_le_0_rise"] == 0.05 and t["min_new_player_net"] == 0.0


def test_template_parses():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("templates"))
    env.get_template("admin_guardrails.html")
