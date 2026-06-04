"""Trade agreement create: resource aliases and partner resolution."""

import pytest

from trade_agreements import (
    VALID_TRADE_RESOURCES,
    normalize_trade_resource,
    resolve_trade_partner_id,
)


class FakeCursor:
    def __init__(self, users_by_id=None, users_by_name=None):
        self.users_by_id = users_by_id or {}
        self.users_by_name = users_by_name or {}
        self.last_sql = None
        self.last_args = None

    def execute(self, sql, args=None):
        self.last_sql = sql
        self.last_args = args

    def fetchone(self):
        if self.last_args is None:
            return None
        if "WHERE id = %s" in (self.last_sql or ""):
            uid = self.last_args[0]
            if uid in self.users_by_id:
                return (uid,)
            return None
        if "LOWER(username) = LOWER" in (self.last_sql or ""):
            name = self.last_args[0].lower()
            uid = self.users_by_name.get(name)
            return (uid,) if uid else None
        return None


def test_normalize_trade_resource_accepts_gold_and_money():
    assert normalize_trade_resource("gold") == "money"
    assert normalize_trade_resource("Gold") == "money"
    assert normalize_trade_resource("money") == "money"
    assert normalize_trade_resource("coal") == "coal"
    assert normalize_trade_resource("bogus") is None


def test_normalize_consumer_goods_aliases():
    assert normalize_trade_resource("consumer goods") == "consumer_goods"
    assert normalize_trade_resource("consumer_goods") == "consumer_goods"


@pytest.mark.parametrize("resource", VALID_TRADE_RESOURCES)
def test_all_valid_resources_normalize(resource):
    assert normalize_trade_resource(resource) == resource


def test_resolve_partner_by_id():
    db = FakeCursor(users_by_id={42: True})
    assert resolve_trade_partner_id(db, 1, "42", "") == 42


def test_resolve_partner_by_username():
    db = FakeCursor(users_by_name={"ailati": 99})
    assert resolve_trade_partner_id(db, 1, "", "AILATI") == 99


def test_resolve_partner_rejects_self():
    db = FakeCursor(users_by_id={1: True})
    assert resolve_trade_partner_id(db, 1, "1", "") is None


def test_resolve_partner_missing():
    db = FakeCursor()
    assert resolve_trade_partner_id(db, 1, "", "NobodyHere") is None
