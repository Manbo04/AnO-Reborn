"""Tests that biome-locked mines can still be demolished / sold.

Buy paths keep the biome restriction; only the demolish / sell paths are
tested here (no live DB required — both modules are importable without one).
"""

import pytest

pytestmark = pytest.mark.no_server


# ---------------------------------------------------------------------------
# biome_buildings helpers
# ---------------------------------------------------------------------------

def test_is_mine_allowed_blocks_buy_for_wrong_biome():
    from app_core.economy.biome_buildings import is_mine_allowed_in_biome

    # iron_mines not allowed in Jungle
    assert not is_mine_allowed_in_biome("iron_mines", "jungle")


def test_is_mine_allowed_permits_non_mine_buildings():
    from app_core.economy.biome_buildings import is_mine_allowed_in_biome

    # non-mine buildings are always allowed regardless of biome
    assert is_mine_allowed_in_biome("hospitals", "jungle")
    assert is_mine_allowed_in_biome("coal_burners", "tundra")


def test_other_biome_mines_returns_locked_mines_for_jungle():
    from app_core.economy.biome_buildings import other_biome_mines, BIOME_MINES

    result = other_biome_mines("jungle")
    names = {m["name"] for m in result}
    allowed = set(BIOME_MINES["jungle"])
    # Every mine in 'result' must NOT be in the allowed set
    assert names.isdisjoint(allowed), (
        f"other_biome_mines returned allowed mines: {names & allowed}"
    )
    # iron_mines is not in jungle's allowed list → must appear in result
    assert "iron_mines" in names


# ---------------------------------------------------------------------------
# demolish_structure has no biome check (unit-level, no DB)
# ---------------------------------------------------------------------------

def test_demolish_structure_does_not_call_is_mine_allowed(monkeypatch):
    """demolish_structure must not import or call is_mine_allowed_in_biome."""
    import action_loop

    calls = []

    # Patch get_db_connection so the function short-circuits without a DB.
    class _FakeCursor:
        def execute(self, *a, **kw):
            # First call is the advisory lock; second fetches building row.
            # Return None to trigger "Building not found" early exit.
            pass
        def fetchone(self):
            return None

    class _FakeConn:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def cursor(self):
            return _FakeCursor()
        def commit(self):
            pass

    monkeypatch.setattr("action_loop.get_db_connection", lambda: _FakeConn())

    # Patch is_mine_allowed_in_biome at the biome_buildings module level
    # to detect if demolish_structure ever calls it.
    import app_core.economy.biome_buildings as bb
    original = bb.is_mine_allowed_in_biome

    def _spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(bb, "is_mine_allowed_in_biome", _spy)

    from action_loop import ActionLoopError
    with pytest.raises(ActionLoopError, match="Building not found"):
        action_loop.demolish_structure(
            user_id=1, building_id=999, quantity=1, province_id=1
        )

    assert calls == [], (
        "demolish_structure must not check biome; "
        f"is_mine_allowed_in_biome was called with: {calls}"
    )


# ---------------------------------------------------------------------------
# province_sell_buy sell path has no biome check (import-level smoke test)
# ---------------------------------------------------------------------------

def test_purchase_building_raises_for_biome_locked_buy():
    """purchase_building (buy) rejects biome-locked mines — buy stays blocked."""
    from app_core.economy.building_purchase import purchase_building, BuildingPurchaseError

    class _FakeCursor:
        def __init__(self):
            self._calls = []
        def execute(self, sql, params=()):
            self._calls.append((sql, params))
        def fetchone(self):
            # Simulate: province owned by user_id=1, location=jungle
            call_count = len(self._calls)
            if call_count == 1:
                return (1,)          # province owner check
            if call_count == 2:
                return ("jungle",)   # location lookup
            return None

    db = _FakeCursor()
    with pytest.raises(BuildingPurchaseError, match="biome"):
        purchase_building(db, user_id=1, province_id=1, building_name="iron_mines", quantity=1)
