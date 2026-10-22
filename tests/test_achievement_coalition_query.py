import pytest

pytestmark = pytest.mark.no_server


def test_dip_coalition_reads_live_membership_table():
    """Better Together must read the table the app writes, not the dead coalition_members."""
    from app_core.game_ticks import achievements

    q = dict(achievements.ACHIEVEMENT_QUERIES)["dip_coalition"]
    assert "coalition_members" not in q
    assert "{members_tbl}" in q
    assert "userid" in q


def test_no_achievement_query_reads_dead_coalition_members():
    from app_core.game_ticks import achievements

    for key, q in achievements.ACHIEVEMENT_QUERIES:
        assert "coalition_members" not in q, key
