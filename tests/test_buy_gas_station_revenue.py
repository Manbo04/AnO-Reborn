from tests.test_revenue_consumer_goods import FakeConn, FakeCursor

import countries


def make_conn(province_population=240000, gas_count=0, gold=500000):
    # provinces: list of tuples (id, land, productivity)
    infra_ids = [(100, 1, 50)]

    # Prepare proInfra row: id followed by columns in order (we only need gas_stations)
    # proinfra_by_id query expects columns in a particular order
    # Craft a row where gas_stations index matches that expected order
    proinfra_row = [100] + [0] * 6 + [gas_count] + [0] * 30

    # non-dict cursor used by get_revenue; return minimal initial values
    db = FakeCursor(fetchone_returns=[(0,), (0,)], fetchall_return=[])
    db._queue = [infra_ids, [tuple(proinfra_row)]]

    # Ensure SELECT gold FROM stats will return the desired gold value
    # (append it to the fake fetchone queue)
    db._fetchone_returns.append((gold,))

    # resources select for rations as used later by next_turn_rations
    db._fetchone_returns.append((0,))

    conn = FakeConn(db, db)
    return conn


def test_buy_gas_stations_does_not_change_raw_taxes(monkeypatch):
    # Before buying: no gas stations
    conn_before = make_conn(gas_count=0, gold=500000)
    monkeypatch.setattr("database.get_db_connection", lambda: conn_before)
    # Ensure cg_need doesn't interfere
    monkeypatch.setattr(countries, "cg_need", lambda cid: 0)
    # calc_ti is now inlined in get_revenue, no need to monkeypatch

    # Avoid cache
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val, ttl_seconds=None: None)

    rev_before = countries.get_revenue(1)

    # After buying: gas stations = 3
    # Simulate a smaller gold reduction
    conn_after = make_conn(gas_count=3, gold=440000)
    monkeypatch.setattr("database.get_db_connection", lambda: conn_after)

    rev_after = countries.get_revenue(1)

    same = rev_after["gross"]["money"] == rev_before["gross"]["money"]
    if not same:
        before_val = rev_before["gross"]["money"]
        after_val = rev_after["gross"]["money"]
        raise AssertionError(
            f"Gross tax changed after buying gas stations: {before_val} -> {after_val}"
        )
