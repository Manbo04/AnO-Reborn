from app_core.assembly_effects import influence_multipliers, SANCTION_INFLUENCE


class FakeCur:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self.rows


def test_no_effects_means_no_entries():
    assert influence_multipliers(FakeCur([]), [1]) == {}
    assert influence_multipliers(FakeCur([]), []) == {}


def test_worst_sanction_wins_and_legacy_is_regular():
    rows = [(1, "sanction", "minor"), (1, "sanction", "major"), (2, "sanction", "regular")]
    m = influence_multipliers(FakeCur(rows), [1, 2])
    assert m[1] == SANCTION_INFLUENCE["major"]
    assert m[2] == SANCTION_INFLUENCE["regular"]


def test_commend_does_not_stack_and_offsets_sanction():
    m = influence_multipliers(FakeCur([(3, "commend", "regular"), (3, "commend", "regular")]), [3])
    assert m[3] == 1.05
    m = influence_multipliers(FakeCur([(4, "commend", "regular"), (4, "sanction", "minor")]), [4])
    assert abs(m[4] - 0.9 * 1.05) < 1e-9
