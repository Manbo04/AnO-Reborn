"""Referral API routes."""
from flask import Blueprint, jsonify, session

from app_core.referrals.service import get_referral_dashboard
from database import get_request_cursor
from helpers import login_required

bp = Blueprint("referrals_api", __name__)


@bp.route("/api/referrals/stats", methods=["GET"])
@login_required
def referral_stats():
    user_id = session["user_id"]
    with get_request_cursor() as db:
        data = get_referral_dashboard(db, user_id)
    return jsonify({"ok": True, **data})
