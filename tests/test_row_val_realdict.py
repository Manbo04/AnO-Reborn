"""RealDictCursor compatibility for province economy helpers."""
from psycopg2.extras import RealDictRow

from database import row_val
from tasks import (
    consumer_goods_distribution_capacity,
    fetch_nation_distribution_status,
    food_stats,
)


class RealDictFakeCursor:
    def __init__(self, scripts):
        self.scripts = scripts
        self._rows = []
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        key = sql.strip().lower().split("\n")[0][:80]
        handler = self.scripts.get("default")
        for prefix, fn in self.scripts.items():
            if prefix != "default" and prefix in sql.lower():
                handler = fn
                break
        if handler:
            self._one, self._rows = handler(sql, params)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


def test_row_val_reads_realdict_and_tuple_rows():
    assert row_val(RealDictRow({"name": "farms", "qty": 3}), "name") == "farms"
    assert row_val(RealDictRow({"coalesce": 12}), "coalesce", 0) == 12
    assert row_val((5, 6), 0) == 5
    assert row_val(None, 0, default=0) == 0


def test_food_stats_with_realdict_cursor():
    cursor = RealDictFakeCursor(
        {
            "from policies": lambda sql, params: (
                RealDictRow({"education": []}),
                [],
            ),
            "from provinces": lambda sql, params: (
                None,
                [RealDictRow({"population": 1000, "pop_children": 0, "pop_working": 1000, "pop_elderly": 0})],
            ),
            "rd.name = 'rations'": lambda sql, params: (RealDictRow({"coalesce": 500}), []),
            "distribution_centers": lambda sql, params: (
                None,
                [RealDictRow({"name": "distribution_centers", "qty": 2})],
            ),
            "default": lambda sql, params: (None, []),
        }
    )

    score = food_stats(99, db=cursor)
    assert isinstance(score, float)


def test_consumer_goods_distribution_capacity_with_realdict_cursor():
    cursor = RealDictFakeCursor(
        {
            "default": lambda sql, params: (
                None,
                [
                    RealDictRow({"name": "malls", "qty": 1}),
                    RealDictRow({"name": "gas_stations", "qty": 2}),
                ],
            )
        }
    )
    cap = consumer_goods_distribution_capacity(99, db=cursor)
    assert cap > 0


def test_fetch_nation_distribution_status_with_realdict_cursor():
    cursor = RealDictFakeCursor(
        {
            "rd.name = 'rations'": lambda sql, params: (RealDictRow({"coalesce": 100}), []),
            "default": lambda sql, params: (
                None,
                [RealDictRow({"name": "distribution_centers", "qty": 1})],
            ),
        }
    )
    status = fetch_nation_distribution_status(cursor, 99, 1000, 10)
    assert status is not None
    assert status["distribution_cap"] > 0
