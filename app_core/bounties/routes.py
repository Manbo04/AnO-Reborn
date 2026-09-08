from flask import Blueprint, request, render_template, session, redirect, flash, url_for

from helpers import login_required
from database import get_request_cursor

from .services import place_bounty, cancel_bounty, fetch_bounty_board

bp = Blueprint("bounties", __name__)


@bp.route("/bounties", methods=["GET"])
@login_required
def view_bounties():
    page = request.args.get("page", default=1, type=int) or 1
    with get_request_cursor(read_only=True) as db:
        bounties, page, total_pages = fetch_bounty_board(db, page)

    return render_template(
        "bounties.html", bounties=bounties, page=page, total_pages=total_pages
    )


@bp.route("/bounties/place", methods=["POST"])
@login_required
def place_bounty_route():
    poster_id = session["user_id"]
    target_id = request.form.get("target_id", type=int)
    amount = request.form.get("amount", type=int)

    if target_id is None or amount is None:
        flash("A target nation and amount are required.", "danger")
        return redirect("/bounties")

    with get_request_cursor() as db:
        ok, error, category = place_bounty(db, poster_id, target_id, amount)

    if not ok:
        flash(error, category)
    else:
        flash("Bounty placed!", "success")
    return redirect(f"/country/id={target_id}")


@bp.route("/bounties/cancel/<int:bounty_id>", methods=["POST"])
@login_required
def cancel_bounty_route(bounty_id):
    poster_id = session["user_id"]
    with get_request_cursor() as db:
        ok, error, category = cancel_bounty(db, bounty_id, poster_id)

    flash("Bounty cancelled, gold refunded." if ok else error, "success" if ok else category)
    return redirect(url_for("bounties.view_bounties"))
