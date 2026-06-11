"""Onboarding API and checklist data."""
from flask import Blueprint, jsonify, session

from app_core.onboarding.service import get_onboarding_status
from database import get_request_cursor
from helpers import login_required

bp = Blueprint("onboarding_api", __name__)


@bp.route("/api/onboarding/status", methods=["GET"])
@login_required
def onboarding_status():
    user_id = session["user_id"]
    with get_request_cursor() as db:
        data = get_onboarding_status(db, user_id)
    return jsonify({"ok": True, **data})
