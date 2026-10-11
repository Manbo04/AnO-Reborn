from app_core.game_ticks.achievements import ACHIEVEMENT_QUERIES


def test_war_won_query_infers_winner_from_morale():
    # wars.winner_id is never written by game code, so the achievement query
    # must also derive winners from the morale columns.
    query = dict(ACHIEVEMENT_QUERIES)["mil_war_won"]
    assert "defender_morale <= 0" in query
    assert "attacker_morale <= 0" in query
    assert "winner_id" in query
