"""Referral signup linking, invitee bonus, and milestone idempotency."""
from datetime import date

import pytest
from flask import Flask

from app_core.referrals.rewards import INVITEE_SIGNUP_BONUS, MILESTONE_REWARDS
from app_core.referrals.service import (
    apply_signup_referral_bonus,
    link_referrer_on_signup,
    record_active_day,
    resolve_referrer_id,
    try_grant_milestones,
)


class ReferralFakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        sql_lower = " ".join(sql.lower().split())
        params = params or ()

        if "alter table" in sql_lower or "create table" in sql_lower or "create index" in sql_lower:
            return

        if "information_schema.columns" in sql_lower:
            self._last = ("is_verified",) if self.state.get("has_is_verified", True) else None
            return

        if "select referral_code from users where id" in sql_lower:
            uid = params[0]
            self._last = (self.state["users"].get(uid, {}).get("referral_code"),)
            return

        if "select id from users where referral_code" in sql_lower:
            code = params[0]
            for uid, user in self.state["users"].items():
                if user.get("referral_code") == code:
                    self._last = (uid,)
                    return
            self._last = None
            return

        if "update users set referral_code" in sql_lower:
            code, uid = params
            self.state["users"].setdefault(uid, {})["referral_code"] = code
            return

        if "update users set referred_by_user_id" in sql_lower:
            referrer_id, new_user_id = params
            user = self.state["users"].setdefault(new_user_id, {})
            if user.get("referred_by_user_id") is None:
                user["referred_by_user_id"] = referrer_id
                self.rowcount = 1
            else:
                self.rowcount = 0
            return

        if "select referred_by_user_id from users where id" in sql_lower:
            uid = params[0]
            self._last = (self.state["users"].get(uid, {}).get("referred_by_user_id"),)
            return

        if "select coalesce(is_verified" in sql_lower:
            uid = params[0]
            self._last = (self.state["users"].get(uid, {}).get("is_verified", True),)
            return

        if "update stats set gold = gold + %s where id" in sql_lower:
            amount, uid = params
            self.state["stats"].setdefault(uid, {"gold": 0})["gold"] += amount
            return

        if "insert into referral_active_days" in sql_lower:
            referred_id, activity_date = params
            key = (referred_id, activity_date)
            days = self.state.setdefault("active_days", set())
            if key not in days:
                days.add(key)
            return

        if "select count(*) from referral_active_days where referred_user_id" in sql_lower:
            referred_id = params[0]
            count = sum(1 for uid, _ in self.state.get("active_days", set()) if uid == referred_id)
            self._last = (count,)
            return

        if "select milestone_days from referral_milestone_payouts" in sql_lower:
            referrer_id, referred_id = params
            paid = [
                m
                for (r, ref, m) in self.state.get("payouts", set())
                if r == referrer_id and ref == referred_id
            ]
            self._last = [(m,) for m in paid] if paid else []
            return

        if "insert into referral_milestone_payouts" in sql_lower:
            referrer_id, referred_id, milestone_days = params
            payouts = self.state.setdefault("payouts", set())
            key = (referrer_id, referred_id, milestone_days)
            if key not in payouts:
                payouts.add(key)
                self.rowcount = 1
            else:
                self.rowcount = 0
            return

        if "select u.id, u.username" in sql_lower and "referred_by_user_id" in sql_lower:
            referrer_id = params[0]
            rows = []
            for uid, user in sorted(self.state["users"].items(), reverse=True):
                if user.get("referred_by_user_id") == referrer_id:
                    days = sum(
                        1 for u, _ in self.state.get("active_days", set()) if u == uid
                    )
                    rows.append((uid, user.get("username", f"user{uid}"), days))
            self._last = rows
            return

        raise AssertionError(f"Unhandled SQL in ReferralFakeCursor: {sql_lower[:120]}")

    def fetchone(self):
        if isinstance(self._last, list):
            if not self._last:
                return None
            return self._last.pop(0)
        return self._last

    def fetchall(self):
        if isinstance(self._last, list):
            rows = self._last
            self._last = None
            return rows
        return [self._last] if self._last is not None else []


@pytest.fixture
def referral_state():
    return {
        "users": {
            1: {"referral_code": "ANO7X3K", "username": "inviter"},
            2: {"username": "invitee", "is_verified": True},
        },
        "stats": {1: {"gold": 0}, 2: {"gold": 0}},
        "active_days": set(),
        "payouts": set(),
        "has_is_verified": True,
    }


@pytest.fixture
def db(referral_state):
    return ReferralFakeCursor(referral_state)


def test_resolve_referrer_id_valid_and_invalid(db, referral_state):
    assert resolve_referrer_id(db, "ANO7X3K") == 1
    assert resolve_referrer_id(db, "BADCODE") is None
    assert resolve_referrer_id(db, "") is None


def test_link_referrer_on_signup(db, referral_state):
    assert link_referrer_on_signup(db, 2, "ANO7X3K") == 1
    assert referral_state["users"][2]["referred_by_user_id"] == 1


def test_self_referral_rejected(db, referral_state):
    referral_state["users"][1]["referral_code"] = "ANOSELF"
    assert link_referrer_on_signup(db, 1, "ANOSELF") is None
    assert referral_state["users"][1].get("referred_by_user_id") is None


def test_invalid_code_no_link(db, referral_state):
    assert link_referrer_on_signup(db, 2, "NOTREAL") is None
    assert referral_state["users"][2].get("referred_by_user_id") is None


def test_invitee_signup_bonus(monkeypatch, db, referral_state):
    granted = []

    def fake_give_resource(_bank, uid, resource, amount, cursor=None):
        granted.append((uid, resource, amount))
        return True

    monkeypatch.setattr("app_core.referrals.service.give_resource", fake_give_resource)
    referral_state["users"][2]["referred_by_user_id"] = 1

    result = apply_signup_referral_bonus(db, 2)

    assert result == INVITEE_SIGNUP_BONUS
    assert referral_state["stats"][2]["gold"] == INVITEE_SIGNUP_BONUS["money"]
    assert (2, "lumber", INVITEE_SIGNUP_BONUS["lumber"]) in granted


def test_no_bonus_without_referrer(monkeypatch, db, referral_state):
    monkeypatch.setattr(
        "app_core.referrals.service.give_resource",
        lambda *_a, **_k: True,
    )
    assert apply_signup_referral_bonus(db, 2) is None


def test_milestone_day1_grants_once(monkeypatch, db, referral_state):
    granted = []

    def fake_give_resource(_bank, uid, resource, amount, cursor=None):
        granted.append((uid, resource, amount))
        return True

    monkeypatch.setattr("app_core.referrals.service.give_resource", fake_give_resource)
    referral_state["users"][2]["referred_by_user_id"] = 1
    referral_state["active_days"].add((2, date.today()))

    payouts = try_grant_milestones(db, 2)
    assert len(payouts) == 1
    assert payouts[0]["milestone_days"] == 1
    assert payouts[0]["granted"]["money"] == MILESTONE_REWARDS[1]["money"]
    assert referral_state["stats"][1]["gold"] == MILESTONE_REWARDS[1]["money"]

    payouts_again = try_grant_milestones(db, 2)
    assert payouts_again == []
    assert len([p for p in referral_state["payouts"] if p[2] == 1]) == 1


def test_milestone_requires_verified_invitee(monkeypatch, db, referral_state):
    monkeypatch.setattr(
        "app_core.referrals.service.give_resource",
        lambda *_a, **_k: True,
    )
    referral_state["users"][2]["referred_by_user_id"] = 1
    referral_state["users"][2]["is_verified"] = False
    referral_state["active_days"].add((2, date.today()))

    assert try_grant_milestones(db, 2) == []


def test_record_active_day_counts_distinct_days(db, referral_state):
    today = date.today()
    referral_state["active_days"].add((2, today))
    assert record_active_day(db, 2) == 1


def test_signup_session_captures_ref_code(monkeypatch):
    from app_core.referrals.service import capture_referral_from_request, referral_code_from_signup_request

    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context("/signup?ref=ANO7X3K"):
        code = capture_referral_from_request()
        assert code == "ANO7X3K"
        assert referral_code_from_signup_request() == "ANO7X3K"
