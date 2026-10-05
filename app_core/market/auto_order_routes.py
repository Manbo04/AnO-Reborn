"""/market/auto_orders -- manage automatic buy/sell rules (app_core/market/auto_orders.py)."""
from flask import Blueprint, flash, redirect, render_template, request, session
from helpers import redirect_back

import variables
from database import get_request_cursor, invalidate_view_cache
from helpers import error, login_required

from app_core.currency.repositories import get_currency_labels

from .auto_orders import delete_rule, describe_rule, list_rules, save_rule, set_rule_active
from .currency_pricing import currency_balances, parse_currency_choice
from .repositories import get_active_resources

auto_orders_bp = Blueprint("auto_orders_bp", __name__)

MAX_RULES_PER_NATION = 30
MAX_LIMIT = 2_000_000_000  # BIGINT columns, but offers.amount is INTEGER


def _optional_int(name, minimum):
    """(value or None, error message or None) for an optional whole number."""
    raw = (request.form.get(name) or "").replace(",", "").strip()
    if not raw:
        return None, None
    try:
        value = int(raw)
    except ValueError:
        return None, f"{name.replace('_', ' ').capitalize()} must be a whole number."
    if value < minimum or value > MAX_LIMIT:
        return None, f"{name.replace('_', ' ').capitalize()} must be between {minimum:,} and {MAX_LIMIT:,}."
    return value, None


def _back():
    return redirect_back("/market/auto_orders")


@auto_orders_bp.route("/market/auto_orders", methods=["GET"])
@login_required
def auto_orders():
    cId = session["user_id"]
    with get_request_cursor(read_only=True) as db:
        rules = list_rules(db, cId)
        resources = get_active_resources(db)
        balances = currency_balances(db, cId)
        ids = {r["currency_id"] for r in rules if r["currency_id"]} | set(balances) | {cId}
        labels = get_currency_labels(db, ids)

    for rule in rules:
        label = labels.get(rule["currency_id"], "currency") if rule["currency_id"] else "gold"
        rule["currency_label"] = label
        rule["summary"] = describe_rule(
            rule["type"], rule["resource"], rule["price"], label,
            rule["reserve_limit"], rule["max_offer"], rule["max_per_day"],
        )

    currencies = [(cId, labels.get(cId, "Your currency") + " (yours)")]
    currencies += sorted(
        ((iid, labels.get(iid, "currency")) for iid, amt in balances.items()
         if iid != cId and amt > 0),
        key=lambda pair: pair[1].lower(),
    )
    return render_template(
        "market_auto_orders.html",
        rules=rules,
        market_resources=resources,  # "resources" is taken by layout.html's HUD
        currencies=currencies,
        max_rules=MAX_RULES_PER_NATION,
        trade_fee_percent=variables.TRADE_FEE_PERCENT,
    )


@auto_orders_bp.route("/market/auto_orders", methods=["POST"])
@login_required
def save_auto_order():
    cId = session["user_id"]
    kind = request.form.get("type")
    if kind not in ("buy", "sell"):
        return error(400, "Choose Buy or Sell.")

    price, err = _optional_int("price", 1)
    if err or price is None:
        return error(400, err or "Set a price per unit.")
    reserve_limit, err = _optional_int("reserve_limit", 0)
    if err:
        return error(400, err)
    max_offer, err = _optional_int("max_offer", 1)
    if err:
        return error(400, err)
    max_per_day, err = _optional_int("max_per_day", 1)
    if err:
        return error(400, err)
    alert_pct, err = _optional_int("alert_pct", 1)
    if err:
        return error(400, err)
    if alert_pct is not None and alert_pct > 1000:
        return error(400, "Price alert must be between 1% and 1000%.")
    if max_offer is None and max_per_day is None:
        return error(400, "Set a maximum offer, a daily limit, or both, so the rule can't sell or buy without limit.")

    with get_request_cursor() as db:
        resource = request.form.get("resource")
        if resource not in get_active_resources(db):
            return error(400, "No such resource")

        currency_id, cur_err = parse_currency_choice(db, request.form.get("currency_id"))
        if cur_err:
            return error(400, cur_err)
        if kind == "buy" and currency_id and currency_id != cId:
            if currency_balances(db, cId).get(currency_id, 0) <= 0:
                return error(400, "You don't hold that currency, so you can't back a buy offer with it.")

        db.execute(
            "SELECT COUNT(*) FROM market_auto_orders WHERE user_id=%s "
            "AND NOT (type=%s AND resource=%s)",
            (cId, kind, resource),
        )
        if db.fetchone()[0] >= MAX_RULES_PER_NATION:
            return error(400, f"You can have at most {MAX_RULES_PER_NATION} auto orders.")

        _, reset = save_rule(db, cId, {
            "type": kind, "resource": resource, "price": price,
            "currency_id": currency_id, "reserve_limit": reserve_limit,
            "max_offer": max_offer, "max_per_day": max_per_day,
            "alert_pct": alert_pct,
        })

    _invalidate(cId)
    msg = "Auto order saved. It tops up at the next hourly check."
    if reset:
        msg += " The price changed, so its old offer was taken down and refunded."
    flash(msg)
    return _back()


@auto_orders_bp.route("/market/auto_orders/<int:rule_id>/toggle", methods=["POST"])
@login_required
def toggle_auto_order(rule_id):
    cId = session["user_id"]
    active = request.form.get("active") == "1"
    with get_request_cursor() as db:
        if not set_rule_active(db, rule_id, cId, active):
            return error(404, "Auto order not found")
    flash("Auto order resumed." if active else
          "Auto order paused. Its current offer stays on the market until it sells or you delete it.")
    return _back()


@auto_orders_bp.route("/market/auto_orders/<int:rule_id>/delete", methods=["POST"])
@login_required
def delete_auto_order(rule_id):
    cId = session["user_id"]
    with get_request_cursor() as db:
        if not delete_rule(db, rule_id, cId):
            return error(404, "Auto order not found")
    _invalidate(cId)
    flash("Auto order deleted and whatever was still on offer was returned to you.")
    return _back()


def _invalidate(user_id):
    try:
        invalidate_view_cache("market", user_id=user_id)
    except Exception:
        pass
