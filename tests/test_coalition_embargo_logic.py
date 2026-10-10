"""Unit tests for coalition embargo and trade blocking pure logic.

Tests require NO database connection.
Run with:
    python3 -m pytest -q tests/test_coalition_embargo_logic.py -p no:cacheprovider
"""

import pytest
from app_core.market.repositories import trade_blocked, trade_block_reason

pytestmark = pytest.mark.no_server


class TestTradeBlockedNationLevel:
    """Tests for nation-level embargo enforcement."""

    def test_nation_embargo_blocks_both_directions_tuple_set(self):
        # A embargoes B
        nation_embargoes = {(1, 2)}
        assert trade_blocked(1, 2, nation_embargoes, {}, set()) is True
        assert trade_blocked(2, 1, nation_embargoes, {}, set()) is True

        # Unrelated third party is not blocked
        assert trade_blocked(1, 3, nation_embargoes, {}, set()) is False
        assert trade_blocked(2, 3, nation_embargoes, {}, set()) is False

    def test_nation_embargo_blocks_dict_format(self):
        # Dict format: {1: {2}}
        nation_embargoes = {1: [2]}
        assert trade_blocked(1, 2, nation_embargoes, {}, set()) is True
        assert trade_blocked(2, 1, nation_embargoes, {}, set()) is True
        assert trade_blocked(1, 3, nation_embargoes, {}, set()) is False

    def test_mutual_nation_embargo(self):
        nation_embargoes = {(1, 2), (2, 1)}
        assert trade_blocked(1, 2, nation_embargoes, {}, set()) is True
        assert trade_blocked(2, 1, nation_embargoes, {}, set()) is True


class TestTradeBlockedCoalitionLevel:
    """Tests for coalition-level embargo enforcement."""

    def test_coalition_embargo_c1_embargoes_c2(self):
        # Coalition 10 embargoes Coalition 20
        # User 1 is in Col 10, User 2 is in Col 20
        coalition_of = {1: 10, 2: 20}
        col_embargoes = {(10, 20)}

        # Blocked in both directions
        assert trade_blocked(1, 2, set(), coalition_of, col_embargoes) is True
        assert trade_blocked(2, 1, set(), coalition_of, col_embargoes) is True

    def test_coalition_embargo_c2_embargoes_c1(self):
        # Coalition 20 embargoes Coalition 10
        coalition_of = {1: 10, 2: 20}
        col_embargoes = {(20, 10)}

        # Blocked in both directions
        assert trade_blocked(1, 2, set(), coalition_of, col_embargoes) is True
        assert trade_blocked(2, 1, set(), coalition_of, col_embargoes) is True

    def test_coalition_embargo_dict_format(self):
        coalition_of = {1: 10, 2: 20}
        col_embargoes = {10: [20]}

        assert trade_blocked(1, 2, set(), coalition_of, col_embargoes) is True
        assert trade_blocked(2, 1, set(), coalition_of, col_embargoes) is True

    def test_coalition_of_callable(self):
        # Support callable / getter for coalition lookup
        col_map = {1: 10, 2: 20, 3: 30}
        col_embargoes = {(10, 20)}

        assert trade_blocked(1, 2, set(), col_map.get, col_embargoes) is True
        assert trade_blocked(1, 3, set(), col_map.get, col_embargoes) is False

    def test_membership_change_immediately_applies(self):
        # If User 3 joins Coalition 20, they are immediately blocked
        col_embargoes = {(10, 20)}

        # Before joining: User 3 has no coalition
        coalition_of_before = {1: 10, 2: 20, 3: None}
        assert trade_blocked(1, 3, set(), coalition_of_before, col_embargoes) is False

        # After joining Col 20: User 3 is immediately blocked
        coalition_of_after = {1: 10, 2: 20, 3: 20}
        assert trade_blocked(1, 3, set(), coalition_of_after, col_embargoes) is True

        # If User 2 leaves Col 20: immediately unblocked
        coalition_of_left = {1: 10, 2: None, 3: 20}
        assert trade_blocked(1, 2, set(), coalition_of_left, col_embargoes) is False


class TestTradeBlockedNoCoalitionAndEdgeCases:
    """Tests for players without coalitions, same coalition, and edge cases."""

    def test_neither_player_in_coalition(self):
        coalition_of = {1: None, 2: None}
        col_embargoes = {(10, 20)}

        assert trade_blocked(1, 2, set(), coalition_of, col_embargoes) is False

    def test_only_one_player_in_coalition(self):
        # User 1 is in Col 10, User 2 is independent
        coalition_of = {1: 10, 2: None}
        col_embargoes = {(10, 20), (20, 10)}

        assert trade_blocked(1, 2, set(), coalition_of, col_embargoes) is False
        assert trade_blocked(2, 1, set(), coalition_of, col_embargoes) is False

    def test_different_coalitions_without_embargo(self):
        # Col 10 and Col 30 have no embargo
        coalition_of = {1: 10, 3: 30}
        col_embargoes = {(10, 20)}

        assert trade_blocked(1, 3, set(), coalition_of, col_embargoes) is False
        assert trade_blocked(3, 1, set(), coalition_of, col_embargoes) is False

    def test_same_coalition_members_not_blocked(self):
        # Two members of Col 10
        coalition_of = {1: 10, 4: 10}
        col_embargoes = {(10, 20), (10, 10)}  # even if malformed self-embargo exists

        assert trade_blocked(1, 4, set(), coalition_of, col_embargoes) is False

    def test_self_trade_never_blocked(self):
        # Trading with oneself is handled by other rules, not blocked by embargo
        coalition_of = {1: 10}
        col_embargoes = {(10, 10)}
        nation_embargoes = {(1, 1)}

        assert trade_blocked(1, 1, nation_embargoes, coalition_of, col_embargoes) is False


class TestTradeBlockReason:
    """Tests for trade_block_reason explanation strings."""

    def test_reason_none_when_unblocked(self):
        assert trade_block_reason(1, 2, set(), {1: 10, 2: 20}, set()) is None

    def test_reason_nation_embargo(self):
        reason = trade_block_reason(1, 2, {(1, 2)}, {}, set())
        assert reason is not None
        assert "nation 1 has embargoed nation 2" in reason.lower()

    def test_reason_coalition_embargo(self):
        reason = trade_block_reason(1, 2, set(), {1: 10, 2: 20}, {(10, 20)})
        assert reason is not None
        assert "coalition embargo" in reason.lower()
        assert "coalition 10 has embargoed coalition 20" in reason.lower()

        # Reverse check
        reason_rev = trade_block_reason(2, 1, set(), {1: 10, 2: 20}, {(10, 20)})
        assert reason_rev is not None
        assert "coalition 10 has embargoed coalition 20" in reason_rev.lower()
