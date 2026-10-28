"""Coalition bank: a deposit of EVERY resource type lands where the player chose.

Discord "Bank bug" (celess mob, 2026-10-27): personal deposits of some
resources ended up only in the alliance vault. Every resource is exercised
for both destinations so a per-resource difference cannot hide again.

Needs Postgres (DATABASE_URL), like the CI prod-shaped job provides; rows are
removed by the shared coalition fixture. Deliberately not skipped without a DB.
"""


import pytest

import variables
from database import get_db_connection
from tests.test_coalition_qol_wishlist import (  # noqa: F401  (fixtures + helpers)
    _login,
    _q,
    _render_v2_coalition_page,
    coalition,
)

ALL_RESOURCES = ["money"] + list(variables.RESOURCES)



def _seed(uid, res, qty):
    """Give the user `qty` of `res` through the same tables the ledger uses."""
    with get_db_connection() as conn:
        db = conn.cursor()
        if res == "money":
            db.execute("UPDATE stats SET gold=%s WHERE id=%s", (qty, uid))
        else:
            db.execute(
                "INSERT INTO resource_dictionary (name, display_name) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (res, res.replace("_", " ").title()),
            )
            db.execute(
                "INSERT INTO user_economy (user_id, resource_id, quantity) "
                "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name=%s "
                "ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity=EXCLUDED.quantity",
                (uid, qty, res),
            )
        conn.commit()


def _held(uid, res):
    if res == "money":
        return _q("SELECT gold FROM stats WHERE id=%s", (uid,))[0][0]
    rows = _q(
        "SELECT ue.quantity FROM user_economy ue "
        "JOIN resource_dictionary rd USING (resource_id) "
        "WHERE ue.user_id=%s AND rd.name=%s",
        (uid, res),
    )
    return rows[0][0] if rows else 0


def _vault(col_id, res):
    return _q(f"SELECT {res} FROM colBanks WHERE colId=%s", (col_id,))[0][0]


@pytest.mark.parametrize("res", ALL_RESOURCES)
def test_personal_deposit_credits_personal_balance(client, coalition, res):
    c = coalition
    _seed(c["member"], res, 1_000)
    before_vault = _vault(c["col_id"], res)

    _login(client, c["member"])
    r = client.post(
        f"/deposit_into_bank/{c['col_id']}",
        data={res: "400", "deposit_destination": "personal"},
    )
    assert r.status_code in (302, 303)

    assert _held(c["member"], res) == 600
    assert _vault(c["col_id"], res) == before_vault + 400
    rows = _q(
        "SELECT total_deposited, COALESCE(total_withdrawn, 0) FROM col_bank_contributions "
        "WHERE coalition_id=%s AND user_id=%s AND resource=%s",
        (c["col_id"], c["member"], res),
    )
    assert rows == [(400, 0)], f"{res}: personal balance not credited"
    kinds = _q(
        "SELECT kind, amount FROM col_bank_transactions "
        "WHERE coalition_id=%s AND user_id=%s AND resource=%s AND direction='deposit'",
        (c["col_id"], c["member"], res),
    )
    assert kinds == [("personal", 400)]

    # ...and the player can take it back out of the personal balance.
    r = client.post(
        f"/withdraw_personal_from_bank/{c['col_id']}", data={res: "400"}
    )
    assert r.status_code in (302, 303)
    assert _held(c["member"], res) == 1_000
    assert _vault(c["col_id"], res) == before_vault


@pytest.mark.parametrize("res", ALL_RESOURCES)
def test_alliance_donation_does_not_credit_personal_balance(client, coalition, res):
    c = coalition
    _seed(c["member"], res, 1_000)
    before_vault = _vault(c["col_id"], res)

    _login(client, c["member"])
    r = client.post(
        f"/deposit_into_bank/{c['col_id']}",
        data={res: "250", "deposit_destination": "alliance"},
    )
    assert r.status_code in (302, 303)

    assert _held(c["member"], res) == 750
    assert _vault(c["col_id"], res) == before_vault + 250
    assert not _q(
        "SELECT 1 FROM col_bank_contributions "
        "WHERE coalition_id=%s AND user_id=%s AND resource=%s AND total_deposited > 0",
        (c["col_id"], c["member"], res),
    )
    kinds = _q(
        "SELECT kind FROM col_bank_transactions "
        "WHERE coalition_id=%s AND user_id=%s AND resource=%s AND direction='deposit'",
        (c["col_id"], c["member"], res),
    )
    assert kinds == [("donation",)]


def test_multi_resource_personal_deposit_in_one_submit(client, coalition):
    """The real form posts every row at once (blank rows included)."""
    c = coalition
    for res in ALL_RESOURCES:
        _seed(c["member"], res, 1_000)
    _login(client, c["member"])
    form = {res: "" for res in ALL_RESOURCES}
    form.update({"money": "1,000", "rations": "7", "consumer_goods": "9"})
    form["deposit_destination"] = "personal"
    r = client.post(f"/deposit_into_bank/{c['col_id']}", data=form)
    assert r.status_code in (302, 303)
    got = dict(
        _q(
            "SELECT resource, total_deposited FROM col_bank_contributions "
            "WHERE coalition_id=%s AND user_id=%s",
            (c["col_id"], c["member"]),
        )
    )
    assert got == {"money": 1000, "rations": 7, "consumer_goods": 9}


def test_personal_balance_column_shows_every_deposited_resource(client, coalition):
    """The Personal Balance column must show what was just deposited, per row."""
    import re

    c = coalition
    for res in ALL_RESOURCES:
        _seed(c["member"], res, 1_000)
    _login(client, c["member"])
    form = {res: "321" for res in ALL_RESOURCES}
    form["deposit_destination"] = "personal"
    assert client.post(f"/deposit_into_bank/{c['col_id']}", data=form).status_code in (302, 303)

    html = client.get(f"/coalition/{c['col_id']}").get_data(as_text=True)
    start = html.index("Personal Balance")
    rows = re.findall(r"<tr>\s*<td>(?:<img[^>]*>)?\s*([^<]+):</td>\s*<td>[^<]*</td>\s*<td[^>]*>([^<]*)</td>", html[start:])
    shown = {label.strip(): val.strip() for label, val in rows}
    assert shown, "bank table not rendered"
    for label, val in shown.items():
        assert val == "321", f"{label} personal balance shows {val!r}"


@pytest.mark.parametrize("res", ALL_RESOURCES)
def test_alliance_payout_never_eats_later_personal_deposits(client, coalition, res):
    """A leader paid more of a resource from alliance reserves than they ever
    personally deposited must not end up with a hidden negative personal
    balance that swallows their next personal deposits (celess mob's bug:
    money/rations/consumer goods are exactly what gets paid out)."""
    c = coalition
    leader = c["leader"]
    _seed(leader, res, 1_000)
    with get_db_connection() as conn:
        conn.cursor().execute(f"UPDATE colBanks SET {res}=10000 WHERE colId=%s", (c["col_id"],))
        conn.commit()

    _login(client, leader)
    form = lambda dest, n: {res: str(n), "deposit_destination": dest}  # noqa: E731
    assert client.post(f"/deposit_into_bank/{c['col_id']}", data=form("personal", 100)).status_code in (302, 303)
    # Paid 500 from alliance reserves while holding only 100 personally.
    assert client.post(f"/withdraw_from_bank/{c['col_id']}", data={res: "500"}).status_code in (302, 303)
    assert client.post(f"/deposit_into_bank/{c['col_id']}", data=form("personal", 300)).status_code in (302, 303)

    deposited, withdrawn = _q(
        "SELECT total_deposited, COALESCE(total_withdrawn, 0) FROM col_bank_contributions "
        "WHERE coalition_id=%s AND user_id=%s AND resource=%s",
        (c["col_id"], leader, res),
    )[0]
    assert withdrawn <= deposited, "payout drove the personal balance negative"
    assert deposited - withdrawn == 300, f"{res}: personal balance is {deposited - withdrawn}, not 300"


def test_legacy_negative_personal_balance_is_healed_by_next_deposit(client, coalition):
    """Rows already in the hole (withdrawn > deposited, created before the cap
    existed) must credit the next personal deposit in full."""
    c = coalition
    _seed(c["member"], "rations", 1_000)
    with get_db_connection() as conn:
        conn.cursor().execute(
            "INSERT INTO col_bank_contributions "
            "(coalition_id, user_id, resource, total_deposited, total_withdrawn) "
            "VALUES (%s, %s, 'rations', 100, 500)",
            (c["col_id"], c["member"]),
        )
        conn.commit()
    _login(client, c["member"])
    client.post(
        f"/deposit_into_bank/{c['col_id']}",
        data={"rations": "300", "deposit_destination": "personal"},
    )
    deposited, withdrawn = _q(
        "SELECT total_deposited, total_withdrawn FROM col_bank_contributions "
        "WHERE coalition_id=%s AND user_id=%s AND resource='rations'",
        (c["col_id"], c["member"]),
    )[0]
    assert deposited - withdrawn == 300


@pytest.mark.parametrize("res", ["money", "rations", "consumer_goods"])
def test_failed_contribution_tracking_rolls_back_whole_deposit(client, coalition, res, monkeypatch):
    """If the personal-balance insert fails the deposit must not half-happen."""
    import psycopg2

    import app_core.coalitions.routes as col_routes

    real = col_routes.get_request_cursor

    class _Boom:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, sql, *a, **kw):
            if "INTO col_bank_contributions" in sql:
                raise psycopg2.Error("simulated contribution failure")
            return self._cur.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._cur, name)

    from contextlib import contextmanager

    @contextmanager
    def patched(*a, **kw):
        with real(*a, **kw) as cur:
            yield _Boom(cur)

    c = coalition
    _seed(c["member"], res, 1_000)
    before_vault = _vault(c["col_id"], res)
    monkeypatch.setattr(col_routes, "get_request_cursor", patched)
    monkeypatch.setitem(client.application.config, "PROPAGATE_EXCEPTIONS", False)
    _login(client, c["member"])
    r = client.post(
        f"/deposit_into_bank/{c['col_id']}",
        data={res: "400", "deposit_destination": "personal"},
    )
    assert r.status_code >= 500
    assert _held(c["member"], res) == 1_000
    assert _vault(c["col_id"], res) == before_vault
    assert not _q(
        "SELECT 1 FROM col_bank_transactions WHERE coalition_id=%s AND user_id=%s",
        (c["col_id"], c["member"]),
    )
