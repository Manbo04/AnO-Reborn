# Trade Agreements - Private recurring automatic trades between players
from flask import request, render_template, session, redirect, flash, jsonify

from helpers import login_required, is_theme_v2_enabled
from database import get_request_cursor, cache_response

from .repositories import (
    VALID_TRADE_RESOURCES,
    TRADE_RESOURCE_LABELS,
    VALID_INTERVALS,
    normalize_trade_resource,
    get_agreements_for_user,
    search_partner_by_id,
    search_partners_by_prefix,
)
from .services import (
    execute_trade_agreement,
    create_agreement,
    accept_agreement,
    reject_agreement,
    cancel_agreement,
    resume_agreement,
)


@login_required
@cache_response(ttl_seconds=30)
def trade_agreements():
    """View all trade agreements for current user."""
    user_id = session["user_id"]

    with get_request_cursor() as db:
        agreements = get_agreements_for_user(db, user_id)

    template = "trade_agreements_v2.html" if is_theme_v2_enabled("trade_agreements") else "trade_agreements.html"
    return render_template(
        template,
        agreements=agreements,
        resources=VALID_TRADE_RESOURCES,
        resource_labels=TRADE_RESOURCE_LABELS,
        intervals=VALID_INTERVALS,
        user_id=user_id,
    )


@login_required
def search_trade_partners():
    """JSON autocomplete for trade partner search (prefix match on name or exact ID)."""
    user_id = session["user_id"]
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])

    with get_request_cursor(read_only=True) as db:
        if q.isdigit():
            rows = search_partner_by_id(db, user_id, int(q))
        else:
            rows = search_partners_by_prefix(db, user_id, q)

    return jsonify([{"id": r[0], "username": r[1]} for r in rows])


@login_required
def create_trade_agreement():
    """Create a new trade agreement proposal."""
    user_id = session["user_id"]

    receiver_id_raw = request.form.get("receiver_id")
    receiver_query = request.form.get("receiver", "")
    proposer_resource = normalize_trade_resource(request.form.get("proposer_resource"))
    proposer_amount = request.form.get("proposer_amount")
    receiver_resource = normalize_trade_resource(request.form.get("receiver_resource"))
    receiver_amount = request.form.get("receiver_amount")
    interval_hours = request.form.get("interval_hours")
    max_executions = request.form.get("max_executions")
    message = (request.form.get("message") or "").strip()

    with get_request_cursor() as db:
        ok, error = create_agreement(
            db,
            user_id,
            receiver_id_raw,
            receiver_query,
            proposer_resource,
            proposer_amount,
            receiver_resource,
            receiver_amount,
            interval_hours,
            max_executions,
            message,
        )

    if not ok:
        flash(error, "error")
        return redirect("/trade-agreements")

    flash("Trade agreement proposal sent!", "success")
    return redirect("/trade-agreements")


@login_required
def accept_trade_agreement(agreement_id):
    """Accept a pending trade agreement."""
    user_id = session["user_id"]

    with get_request_cursor() as db:
        ok, error = accept_agreement(db, agreement_id, user_id)

    if not ok:
        flash(error, "error")
        return redirect("/trade-agreements")

    # Execute the first trade immediately
    success, msg = execute_trade_agreement(agreement_id)

    if success:
        flash("Agreement accepted and first trade executed!", "success")
    else:
        flash(f"Agreement accepted but first trade failed: {msg}", "warning")

    return redirect("/trade-agreements")


@login_required
def reject_trade_agreement(agreement_id):
    """Reject a pending trade agreement."""
    user_id = session["user_id"]

    with get_request_cursor() as db:
        ok, error = reject_agreement(db, agreement_id, user_id)

    if not ok:
        flash(error, "error")
        return redirect("/trade-agreements")

    flash("Agreement rejected", "success")
    return redirect("/trade-agreements")


@login_required
def cancel_trade_agreement(agreement_id):
    """Cancel an active trade agreement (either party can cancel)."""
    user_id = session["user_id"]

    with get_request_cursor() as db:
        ok, error = cancel_agreement(db, agreement_id, user_id)

    if not ok:
        flash(error, "error")
        return redirect("/trade-agreements")

    flash("Agreement cancelled", "success")
    return redirect("/trade-agreements")


@login_required
def resume_trade_agreement(agreement_id):
    """Resume a paused trade agreement."""
    user_id = session["user_id"]

    with get_request_cursor() as db:
        ok, error = resume_agreement(db, agreement_id, user_id)

    if not ok:
        flash(error, "error")
        return redirect("/trade-agreements")

    flash("Agreement resumed", "success")
    return redirect("/trade-agreements")


def register_trade_agreement_routes(app):
    """Register trade agreement routes with the Flask app."""
    app.add_url_rule("/trade-agreements", "trade_agreements", trade_agreements)
    app.add_url_rule(
        "/trade-agreements/partners",
        "search_trade_partners",
        search_trade_partners,
        methods=["GET"],
    )
    app.add_url_rule(
        "/trade-agreements/create",
        "create_trade_agreement",
        create_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/accept",
        "accept_trade_agreement",
        accept_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/reject",
        "reject_trade_agreement",
        reject_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/cancel",
        "cancel_trade_agreement",
        cancel_trade_agreement,
        methods=["POST"],
    )
    app.add_url_rule(
        "/trade-agreements/<int:agreement_id>/resume",
        "resume_trade_agreement",
        resume_trade_agreement,
        methods=["POST"],
    )
