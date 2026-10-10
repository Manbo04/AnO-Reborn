"""Weekly vote 2026-10-09: losing a battle no longer freezes growth."""
from unittest.mock import MagicMock

from wars import aftermath


def test_lost_battle_writes_no_growth_freeze():
    db = MagicMock()
    db.fetchone.return_value = (0,)
    summary = aftermath.apply_battle_aftermath(
        db, 1, 2, False, "ground", {"soldiers": 10}, 1.0
    )
    sql = " ".join(str(c.args[0]) for c in db.execute.call_args_list)
    assert "population_growth_freezes" not in sql
    assert summary["frozen"] is None
