from flask import Blueprint, abort, render_template, session

from app_core.feature_flags import is_on
from database import get_request_cursor
from helpers import login_required

from . import services

bp = Blueprint("ledger_ui", __name__)


@bp.route("/ledger", methods=["GET"])
@login_required
def ledger_home():
    uid = session.get("user_id")
    if not is_on("ledger_ui", uid):
        abort(404)
    with get_request_cursor() as db:
        data = {
            "industry": services.industry(db, uid),
            "needs": services.needs(db, uid),
            "budget": services.budget(db, uid),
            "gazette": services.gazette(db),
        }
    return render_template("ledger.html", **data)
