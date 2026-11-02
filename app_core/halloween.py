"""Yearly Halloween gift: a one-click money gift on Oct 31 (Europe/Vilnius).

Claim-once-per-year is enforced by the PRIMARY KEY (user_id, year) on
halloween_gift_claims: the claim row and the credit happen in one transaction,
so double clicks, refreshes and several devices cannot pay out twice.

Testing off-season: set HALLOWEEN_GIFT_DATE=YYYY-MM-DD (e.g. 2025-10-31) in the
environment. It replaces "today" and its year is the claim year, so a test
claim never consumes the real year's gift. Leave it unset in production.
"""
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, session

from app_core.economy import ledger
from database import get_db_cursor
from helpers import login_required

HALLOWEEN_GIFT_AMOUNT = 13_000_000_000  # money, the single knob
HALLOWEEN_MONTH, HALLOWEEN_DAY = 10, 31
SERVER_TZ = ZoneInfo("Europe/Vilnius")

bp = Blueprint("halloween_bp", __name__)


def gift_date():
    """Today's server date, or the HALLOWEEN_GIFT_DATE test override."""
    raw = (os.environ.get("HALLOWEEN_GIFT_DATE") or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(SERVER_TZ).date()


def is_halloween(today=None):
    today = today or gift_date()
    return (today.month, today.day) == (HALLOWEEN_MONTH, HALLOWEEN_DAY)


def has_claimed(db, user_id, year):
    db.execute(
        "SELECT 1 FROM halloween_gift_claims WHERE user_id=%s AND year=%s",
        (user_id, year),
    )
    return db.fetchone() is not None


def claim_gift(db, user_id, today=None):
    """Atomically claim. Returns (ok, message, amount). Caller commits."""
    today = today or gift_date()
    if not is_halloween(today):
        return False, "The gift is only available on October 31.", 0
    db.execute(
        "INSERT INTO halloween_gift_claims (user_id, year, amount) "
        "VALUES (%s, %s, %s) ON CONFLICT (user_id, year) DO NOTHING RETURNING 1",
        (user_id, today.year, HALLOWEEN_GIFT_AMOUNT),
    )
    if db.fetchone() is None:
        return False, "You already opened this year's gift.", 0
    ledger.credit_gold(db, user_id, HALLOWEEN_GIFT_AMOUNT)
    if db.rowcount == 0:  # no stats row: roll the claim back instead of eating it
        raise RuntimeError("no stats row for user %s" % user_id)
    return True, "Happy Halloween!", HALLOWEEN_GIFT_AMOUNT


@bp.app_context_processor
def _inject_halloween():
    # Date-only check (no DB): the modal JS asks the API whether to show itself.
    return {"halloween_gift_day": is_halloween(), "halloween_gift_amount": HALLOWEEN_GIFT_AMOUNT}


@bp.route("/api/halloween/status")
@login_required
def status():
    today = gift_date()
    if not is_halloween(today):
        return jsonify(available=False)
    with get_db_cursor() as db:
        claimed = has_claimed(db, session["user_id"], today.year)
    return jsonify(available=not claimed, amount=HALLOWEEN_GIFT_AMOUNT)


@bp.route("/api/halloween/claim", methods=["POST"])
@login_required
def claim():
    try:
        with get_db_cursor() as db:
            ok, msg, amount = claim_gift(db, session["user_id"])
    except Exception:
        return jsonify(success=False, error="Could not open the gift, try again."), 500
    return jsonify(success=ok, message=msg, amount=amount), (200 if ok else 409)
