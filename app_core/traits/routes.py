"""Routes for unique-nation traits (Golden Throne pilgrimage + public Wall of the Spent)."""
from datetime import date

from flask import Blueprint, flash, jsonify, redirect, request, session

from database import get_request_cursor
from helpers import login_required

from . import golden_throne

bp = Blueprint("traits_bp", __name__)


@bp.route("/traits/golden-throne/pilgrimage", methods=["POST"])
@login_required
def golden_throne_pilgrimage():
    """Send pilgrims: once per dawn window, server-side cost, atomic (see send_pilgrims)."""
    kind = (request.form.get("kind") or "").strip()
    with get_request_cursor() as db:
        owner = golden_throne.owner_id(db)
        ok, msg = golden_throne.send_pilgrims(db, session["user_id"], kind)
    flash(msg, "success" if ok else "danger")
    return redirect(f"/country/id={owner}" if owner else "/countries")


@bp.route("/traits/golden-throne/wall", methods=["GET"])
def golden_throne_wall():
    """Public, read-only, paginated Wall of the Spent (newest dawn first)."""
    before = None
    raw = request.args.get("before")
    if raw:
        try:
            before = date.fromisoformat(raw)
        except ValueError:
            return jsonify({"error": "bad date"}), 400
    with get_request_cursor(read_only=True) as db:
        rows, nxt = golden_throne.wall_page(db, before)
    return jsonify({"days": rows, "next_before": nxt})
