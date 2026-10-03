from flask import Blueprint, request, render_template, session, redirect, flash
from helpers import login_required, error, get_valid_int, record_trade_event, is_theme_v2_enabled
import variables
import logging
from database import get_request_cursor, invalidate_user_cache, invalidate_view_cache, rollback_db_cursor, cache_response

from .repositories import (
    is_active_resource, get_user_resource_quantity,
    get_offer_by_id, delete_offer, update_offer_amount, lock_users, get_user_gold_for_update,
    insert_offer, insert_trade, get_my_trades, get_my_offers, delete_trade, try_lock_trade,
    unlock_trade, get_trade_by_id, get_username, insert_news, delete_trade_by_id, user_exists,
    decrement_gold, increment_gold, is_embargoed, add_embargo, remove_embargo, list_embargoes,
    get_user_gold, get_user_resource_quantities, get_my_currency_ids,
    get_active_resources, get_resource_book, get_exchange_issuers, get_embargo_partners,
    get_market_preferences, upsert_market_preferences, record_market_fill,
    get_last_fill_prices,
)
from .fees import trade_fee, trade_fee_percent, union_partner_ids, max_affordable_amount
from .services import give_resource, report_trade_error
from .currency_pricing import (
    parse_currency_choice, currency_balances, get_currency_labels, get_currency_balance,
    classify_offer_currency, gold_normalised, TAG_LABELS, TAG_SHORT,
)
from app_core.currency.repositories import take_currency, give_currency
from .auto_orders import cancel_offer_with_refund
from app_core.world_affairs.services import log_event

# trades.amount/price/offeree/offer_id are Postgres INTEGER columns.
MAX_TRADE_INT = 2_147_483_647

market_bp = Blueprint("market_bp", __name__)
logger = logging.getLogger(__name__)

def _record_fill(db, offer_id, resource, amount, price, currency_id, seller_id, buyer_id):
    """Log a market fill for "last traded price" (order book + auto-order
    alerts). Runs in a savepoint: a logging failure must never undo a trade
    that has already moved resources and money in this transaction."""
    try:
        db.execute("SAVEPOINT market_fill")
        record_market_fill(
            db, offer_id, resource, amount, price, currency_id,
            gold_normalised(price, currency_id), seller_id, buyer_id,
        )
        db.execute("RELEASE SAVEPOINT market_fill")
    except Exception:
        logger.exception("market fill log failed for offer %s", offer_id)
        try:
            db.execute("ROLLBACK TO SAVEPOINT market_fill")
        except Exception:
            logger.exception("savepoint rollback failed for offer %s", offer_id)


MARKET_PER_SIDE_CHOICES = (10, 25, 50, 100)
MARKET_DEFAULT_RESOURCE = "rations"


def _book_row(row, cId, ctx):
    """One order-book entry as a dict the template can read by name."""
    user_id, offer_type, resource, amount, price, offer_id, username, currency_id = row
    pct = (
        variables.UNION_TRADE_FEE_PERCENT
        if user_id in ctx["union_partners"]
        else variables.TRADE_FEE_PERCENT
    )
    if offer_type == "sell":
        # The viewer buys from this offer: capped by what they can pay
        # (price + transport fee) in the offer's currency.
        funds = ctx["my_currency"].get(currency_id, 0) if currency_id else ctx["my_gold"]
        take = min(amount, max_affordable_amount(funds, price, pct))
    else:
        # The viewer sells into this offer: capped by their stock.
        take = min(amount, ctx["my_resources"].get(resource, 0))
    tag = classify_offer_currency(currency_id, cId, ctx["my_currency"], ctx["exchange_issuers"])
    return {
        "offer_id": offer_id,
        "user_id": user_id,
        "username": username,
        "type": offer_type,
        "resource": resource,
        "amount": amount,
        "price": price,
        "total": price * amount,
        "currency_id": currency_id,
        "currency_label": ctx["labels"].get(currency_id, "currency") if currency_id else "Gold",
        "gold_price": gold_normalised(price, currency_id),
        "tag": tag,
        "tag_label": TAG_LABELS[tag],
        "tag_short": TAG_SHORT[tag],
        "max_take": max(0, take),
        "fee_percent": pct,
    }


def _hidden_by_preferences(offer, prefs, embargo_partners):
    if prefs["hide_embargoed"] and offer["user_id"] in embargo_partners:
        return True
    if prefs["hide_unavailable"] and offer["tag"] == "unavailable":
        return True
    if prefs["hide_exchange"] and offer["tag"] == "exchange":
        return True
    if prefs["currency_mode"] == "gold" and offer["currency_id"]:
        return True
    if prefs["currency_mode"] == "currency" and offer["currency_id"] != prefs["currency_id"]:
        return True
    return False


@market_bp.route("/market", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)
def market():
    """Order book for one resource (Market UI Rework, Helios 2026-10-03):
    offers you can BUY from (cheapest first) beside offers you can SELL to
    (best price first), sorted on the gold-normalised price and colour-tagged
    by whether you can use the offer's currency at all."""
    with get_request_cursor(read_only=True) as db:
        cId = session["user_id"]
        prefs = get_market_preferences(db, cId)
        resources = get_active_resources(db)

        resource = (
            request.values.get("resource")
            or request.values.get("filtered_resource")  # old links / bookmarks
            or prefs["default_resource"]
            or MARKET_DEFAULT_RESOURCE
        )
        if resource != "all" and resource not in resources:
            if request.values.get("resource") or request.values.get("filtered_resource"):
                return error(400, "No such resource")
            resource = MARKET_DEFAULT_RESOURCE  # a saved default that was retired

        per_side = request.values.get("per_side", default=25, type=int)
        if per_side not in MARKET_PER_SIDE_CHOICES:
            per_side = 25

        rows = get_resource_book(db, resource, cId)
        currency_ids = {row[7] for row in rows if row[7]}
        my_currency = currency_balances(db, cId)
        ctx = {
            "my_gold": get_user_gold(db, cId) or 0,
            "my_resources": get_user_resource_quantities(db, cId),
            "my_currency": my_currency,
            "union_partners": union_partner_ids(db, cId),
            "exchange_issuers": get_exchange_issuers(db, cId) if currency_ids else set(),
            "labels": get_currency_labels(db, currency_ids | {cId} | set(my_currency)),
        }
        embargo_partners = get_embargo_partners(db, cId) if prefs["hide_embargoed"] else set()

        asks, bids, hidden_count = [], [], 0
        for row in rows:
            offer = _book_row(row, cId, ctx)
            if _hidden_by_preferences(offer, prefs, embargo_partners):
                hidden_count += 1
            elif offer["type"] == "sell":
                asks.append(offer)
            else:
                bids.append(offer)
        asks.sort(key=lambda o: (o["gold_price"], o["offer_id"]))
        bids.sort(key=lambda o: (-o["gold_price"], o["offer_id"]))

        best_ask = asks[0]["gold_price"] if asks else None
        best_bid = bids[0]["gold_price"] if bids else None
        last_fill = None
        if resource != "all":
            last_fill = get_last_fill_prices(db, [resource]).get(resource)

        my_currencies = [(cId, ctx["labels"].get(cId, "Your currency") + " (yours)")]
        my_currencies += sorted(
            ((iid, ctx["labels"].get(iid, "currency")) for iid, amt in my_currency.items()
             if iid != cId and amt > 0),
            key=lambda pair: pair[1].lower(),
        )

        return render_template(
            "market_v2.html",
            resource=resource,
            market_resources=resources,  # "resources" is taken by layout.html's HUD
            asks=asks[:per_side],
            bids=bids[:per_side],
            asks_total=len(asks),
            bids_total=len(bids),
            best_ask=best_ask,
            best_bid=best_bid,
            spread=(best_ask - best_bid) if best_ask is not None and best_bid is not None else None,
            last_fill=last_fill,
            prefs=prefs,
            my_currencies=my_currencies,
            hidden_count=hidden_count,
            per_side=per_side,
            per_side_choices=MARKET_PER_SIDE_CHOICES,
            gold_per_unit=variables.CURRENCY_GOLD_PER_UNIT,
            tag_labels=TAG_LABELS,
            cId=cId,
        )


@market_bp.route("/market/preferences", methods=["POST"])
@login_required
def market_preferences():
    cId = session["user_id"]
    with get_request_cursor() as db:
        resources = get_active_resources(db)
        default_resource = (request.form.get("default_resource") or "").strip() or None
        if default_resource is not None and default_resource != "all" and default_resource not in resources:
            return error(400, "No such resource")

        currency_mode = request.form.get("currency_mode", "all")
        if currency_mode not in ("all", "gold", "currency"):
            return error(400, "Unknown currency filter")
        currency_id = None
        if currency_mode == "currency":
            currency_id, cur_err = parse_currency_choice(db, request.form.get("currency_id"))
            if cur_err:
                return error(400, cur_err)
            if currency_id is None:
                return error(400, "Pick which currency to trade in, or choose another option.")

        upsert_market_preferences(db, cId, {
            "default_resource": default_resource,
            "hide_unavailable": request.form.get("hide_unavailable") == "on",
            "hide_exchange": request.form.get("hide_exchange") == "on",
            "hide_embargoed": request.form.get("hide_embargoed") == "on",
            "currency_mode": currency_mode,
            "currency_id": currency_id,
        })

    try:
        invalidate_view_cache("market", user_id=cId)
    except Exception:
        pass
    flash("Market settings saved")
    return redirect("/market")


@market_bp.route("/buy_offer/<offer_id>", methods=["POST"])
@login_required
def buy_market_offer(offer_id):
    with get_request_cursor() as db:
        cId = session["user_id"]

        amount_str = request.form.get(f"amount_{offer_id}")
        if not amount_str:
            return error(400, "Amount is required")

        try:
            amount_wanted = int(amount_str.replace(",", ""))
        except (ValueError, TypeError, AttributeError):
            return error(400, "Amount must be a valid number")

        row = get_offer_by_id(db, offer_id)
        if not row:
            return error(400, "Offer not found")
        resource, total_amount, price_for_one, seller_id, offer_type, currency_id = row
        # Only a sell offer's resource is escrowed at the bank. Buying
        # "from" a buy offer used to hand out bank resources nobody had put up.
        if offer_type != "sell":
            return error(400, "That is a buy offer; use Sell to fill it.")

        if is_embargoed(db, seller_id, cId):
            return error(403, "This nation has embargoed you and will not sell to you.")

        db.execute(
            "SELECT 1 FROM assembly_effects WHERE target_nation_id IN (%s, %s)"
            " AND effect_type = 'sanction' AND active = TRUE"
            " AND (expires_at IS NULL OR expires_at > NOW())",
            (seller_id, cId),
        )
        if db.fetchone():
            return error(403, "Trade blocked by active World Assembly sanctions on one of the nations.")

        if not is_active_resource(db, resource):
            return error(400, "This resource is not currently tradable.")

        if amount_wanted < 1:
            return error(400, "Amount cannot be less than 1")

        lock_users(db, [cId, seller_id])

        if amount_wanted > total_amount:
            return error(400, "Requested amount exceeds available amount")

        buyers_gold = get_user_gold_for_update(db, cId)
        if buyers_gold is None:
            return error(500, "Your nation data could not be found")

        total_price = amount_wanted * price_for_one
        # Transport fee (app_core/market/fees.py): buyer pays it on top.
        market_fee = trade_fee(total_price, trade_fee_percent(db, cId, seller_id))
        total_cost_to_buyer = total_price + market_fee

        if currency_id:
            # Priced in a nation currency: price + fee come out of the
            # buyer's holding of it; the fee is burned in that currency.
            if total_cost_to_buyer > get_currency_balance(db, cId, currency_id):
                return error(400, "You don't have enough of the currency this offer is priced in.")
        elif total_cost_to_buyer > buyers_gold:
            return error(400, "You don't have enough money.")

        res = give_resource("bank", cId, resource, amount_wanted, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"buy_market_offer: give_resource(bank -> buyer) failed: {res}")
            return error(400, str(res))

        if currency_id:
            if not take_currency(db, cId, currency_id, total_cost_to_buyer):
                rollback_db_cursor(db)
                return error(400, "You don't have enough of the currency this offer is priced in.")
            give_currency(db, seller_id, currency_id, total_price)
            res = True
        else:
            res = give_resource(cId, seller_id, "money", total_price, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"buy_market_offer: give_resource(buyer -> seller money) failed: {res}")
            return error(400, str(res))

        if market_fee > 0 and not currency_id:
            res = give_resource(cId, "bank", "money", market_fee, cursor=db)
            if res is not True:
                rollback_db_cursor(db)
                report_trade_error(f"buy_market_offer: give_resource(buyer -> bank fee) failed: {res}")
                return error(400, str(res))

        new_offer_amount = total_amount - amount_wanted
        if new_offer_amount == 0:
            delete_offer(db, offer_id)
        else:
            update_offer_amount(db, offer_id, new_offer_amount)
        _record_fill(db, offer_id, resource, amount_wanted, price_for_one,
                     currency_id, seller_id=seller_id, buyer_id=cId)

        try:
            buyer_name = get_username(db, cId) or "A nation"
            insert_news(
                db, seller_id,
                f"{buyer_name} purchased {amount_wanted:,} {resource} from your "
                f"market offer for ${total_price:,}.",
            )
        except Exception:
            pass

    try:
        invalidate_user_cache(cId)
        invalidate_user_cache(seller_id)
        invalidate_view_cache("market", user_id=cId)
        invalidate_view_cache("market", user_id=seller_id)
    except Exception:
        pass

    return redirect("/market")

@market_bp.route("/sell_offer/<offer_id>", methods=["POST"])
@login_required
def sell_market_offer(offer_id):
    with get_request_cursor() as db:
        seller_id = session["user_id"]

        if not offer_id.isnumeric():
            return error(400, "Values must be numeric")

        amount_str = request.form.get(f"amount_{offer_id}")
        if not amount_str:
            return error(400, "Amount is required")

        try:
            amount_wanted = int(amount_str)
        except (ValueError, TypeError):
            return error(400, "Amount must be a valid number")

        row = get_offer_by_id(db, offer_id)
        if not row:
            return error(400, "Offer not found")
        resource, total_amount, price_for_one, buyer_id, offer_type, currency_id = row
        # Only a buy offer's payment is escrowed at the bank. Selling "into"
        # a sell offer used to pay the seller bank gold nobody had put up.
        if offer_type != "buy":
            return error(400, "That is a sell offer; use Buy to fill it.")

        if is_embargoed(db, buyer_id, seller_id):
            return error(403, "This nation has embargoed you and will not buy from you.")

        db.execute(
            "SELECT 1 FROM assembly_effects WHERE target_nation_id IN (%s, %s)"
            " AND effect_type = 'sanction' AND active = TRUE"
            " AND (expires_at IS NULL OR expires_at > NOW())",
            (buyer_id, seller_id),
        )
        if db.fetchone():
            return error(403, "Trade blocked by active World Assembly sanctions on one of the nations.")

        lock_users(db, [seller_id, buyer_id])

        if not is_active_resource(db, resource):
            return error(400, "This resource is not currently tradable.")

        sellers_resource = get_user_resource_quantity(db, seller_id, resource)
        if sellers_resource is None:
            return error(400, "No such resource")

        if amount_wanted < 1:
            return error(400, "Amount cannot be less than 1")

        if amount_wanted > total_amount:
            return error(400, "Requested amount exceeds desired amount")

        if sellers_resource < amount_wanted:
            return error(400, "You don't have enough of that resource")

        total_price = price_for_one * amount_wanted
        # Transport fee (app_core/market/fees.py): the buyer's escrow already
        # holds total_price, so the seller is paid the price minus the fee and
        # the fee stays out of circulation.
        market_fee = trade_fee(total_price, trade_fee_percent(db, seller_id, buyer_id))
        seller_proceeds = total_price - market_fee

        res = give_resource(seller_id, buyer_id, resource, amount_wanted, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"sell_market_offer: give_resource(seller -> buyer) failed: {res}")
            return error(400, str(res))

        if currency_id:
            # The buy offer escrowed amount*price of this currency; the
            # seller gets it minus the fee, the fee stays burned.
            give_currency(db, seller_id, currency_id, seller_proceeds)
            res = True
        else:
            res = give_resource("bank", seller_id, "money", seller_proceeds, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"sell_market_offer: give_resource(bank -> seller money) failed: {res}")
            return error(400, str(res))

        new_offer_amount = total_amount - amount_wanted
        if new_offer_amount == 0:
            delete_offer(db, offer_id)
        else:
            update_offer_amount(db, offer_id, new_offer_amount)
        _record_fill(db, offer_id, resource, amount_wanted, price_for_one,
                     currency_id, seller_id=seller_id, buyer_id=buyer_id)

        try:
            seller_name = get_username(db, seller_id) or "A nation"
            insert_news(
                db, buyer_id,
                f"{seller_name} sold you {amount_wanted:,} {resource} for "
                f"${total_price:,} via your market offer.",
            )
        except Exception:
            pass

    try:
        invalidate_user_cache(seller_id)
        invalidate_user_cache(buyer_id)
        invalidate_view_cache("market", user_id=seller_id)
        invalidate_view_cache("market", user_id=buyer_id)
    except Exception:
        pass

    return redirect("/market")

@market_bp.route("/marketoffer/", methods=["GET", "POST"])
@login_required
def marketoffer():
    from app_core.currency_market.repositories import list_known_currencies
    from app_core.currency.repositories import currency_label

    with get_request_cursor(read_only=True) as db:
        currencies = [
            (issuer_id, currency_label(cname, uname), uname)
            for issuer_id, uname, cname in list_known_currencies(db, session["user_id"])
        ]
    template = "marketoffer_v2.html" if is_theme_v2_enabled("marketoffer") else "marketoffer.html"
    return render_template(template, currencies=currencies)


def notify_market_ping(user_id: int, offer_type: str, resource: str, amount: int, price: int):
    """Notify Discord #early-market (1449182898728079380) with @Market Alerts (1554905946835394572)."""
    import threading

    def _send():
        import json
        import os
        import urllib.request
        from database import QueryHelper

        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            try:
                orch_env = "/Users/dede/vivobook-archive/AnO-Orchestrator/.env"
                if os.path.exists(orch_env):
                    with open(orch_env) as f:
                        for line in f:
                            if line.startswith("DISCORD_BOT_TOKEN="):
                                token = line.strip().split("=", 1)[1]
                                break
            except Exception:
                pass
        if not token:
            return

        username = None
        try:
            row = QueryHelper.fetch_one("SELECT username FROM users WHERE id=%s", (user_id,))
            if row:
                username = row[0]
        except Exception:
            pass

        nation_str = f"**{username}**" if username else "A nation"
        type_str = offer_type.upper()
        res_display = resource.replace("_", " ").title()
        content = (
            f"📢 <@&1554905946835394572> **New Market Offer!**\n"
            f"{nation_str} posted a **{type_str}** offer: **{amount:,}** {res_display} at **{price:,}** gold each!\n"
            f"View offers: <https://affairsandorder.org/market>"
        )
        url = "https://discord.com/api/v10/channels/1449182898728079380/messages"
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "AffairsAndOrder/1.0",
        }
        payload = json.dumps({
            "content": content,
            "allowed_mentions": {"roles": ["1554905946835394572"]},
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.warning("Failed to send market ping to Discord: %s", e)

    threading.Thread(target=_send, daemon=True).start()


@market_bp.route("/post_offer/<offer_type>", methods=["POST"])
@login_required
def post_offer(offer_type):
    cId = session["user_id"]

    with get_request_cursor() as db:
        resource = request.form.get("resource")
        amount, err = get_valid_int("amount", error_invalid="Amount must be a valid number")
        if err: return err
        price, err = get_valid_int("price", error_invalid="Price must be a valid number")
        if err: return err

        if offer_type not in ["buy", "sell"]:
            return error(400, "Offer type must be 'buy' or 'sell'")

        if not is_active_resource(db, resource):
            return error(400, "No such resource")

        if amount < 1:
            return error(400, "Amount must be greater than 0")

        if price < 1:
            return error(400, "Price must be greater than 0")

        currency_id, cur_err = parse_currency_choice(db, request.form.get("currency_id"))
        if cur_err:
            return error(400, cur_err)
        db.execute(
            "SELECT 1 FROM assembly_effects WHERE target_nation_id = %s"
            " AND effect_type = 'sanction' AND active = TRUE"
            " AND (expires_at IS NULL OR expires_at > NOW())",
            (cId,),
        )
        if db.fetchone():
            return error(403, "You cannot post market offers while under World Assembly sanctions.")

        if offer_type == "sell":
            realAmount = get_user_resource_quantity(db, cId, resource)
            if realAmount is None:
                return error(400, "No such resource")

            if amount > realAmount:
                return error(400, "Selling amount is higher than the amount you have.")

            res = give_resource(cId, "bank", resource, amount, cursor=db)
            if res is not True:
                rollback_db_cursor(db)
                return error(400, str(res))

            insert_offer(db, cId, offer_type, resource, amount, price, currency_id)

        elif offer_type == "buy" and currency_id:
            # Escrow the offer's value in the chosen currency.
            lock_users(db, [cId])
            if not take_currency(db, cId, currency_id, int(amount) * int(price)):
                return error(400, "You don't hold enough of that currency to back this offer.")
            insert_offer(db, cId, offer_type, resource, amount, price, currency_id)

        elif offer_type == "buy":
            money_to_take_away = int(amount) * int(price)
            current_money = get_user_gold_for_update(db, cId)
            if current_money is None:
                return error(500, "Your nation data could not be found")

            if current_money < money_to_take_away:
                return error(400, "You don't have enough money.")

            res = give_resource(cId, "bank", "money", money_to_take_away, cursor=db)
            if res is not True:
                rollback_db_cursor(db)
                return error(400, str(res))

            insert_offer(db, cId, offer_type, resource, amount, price)

        flash("You just posted a market offer")
        notify_market_ping(cId, offer_type, resource, amount, price)
    return redirect("/market")

@market_bp.route("/my_offers", methods=["GET"])
@login_required
@cache_response(ttl_seconds=15)
def my_offers():
    cId = session["user_id"]
    offers = {}
    with get_request_cursor(read_only=True) as db:
        outgoing, incoming = get_my_trades(db, cId)
        offers["outgoing"] = outgoing
        offers["incoming"] = incoming
        offers["market"] = get_my_offers(db, cId)
        embargoes = list_embargoes(db, cId)
        offer_cur, trade_cur = get_my_currency_ids(db, cId)
        labels = get_currency_labels(db, list(offer_cur.values()) + list(trade_cur.values()))

    template = "my_offers_v2.html" if is_theme_v2_enabled("my_offers") else "my_offers.html"
    return render_template(
        template, cId=cId, offers=offers, embargoes=embargoes,
        offer_currency={k: labels.get(v, "currency") for k, v in offer_cur.items()},
        trade_currency={k: labels.get(v, "currency") for k, v in trade_cur.items()},
    )

@market_bp.route("/delete_offer/<offer_id>", methods=["POST"])
@login_required
def delete_offer_endpoint(offer_id):
    cId = session["user_id"]
    with get_request_cursor() as db:
        # Same refund path the auto-order rules use when they cancel an offer.
        if not cancel_offer_with_refund(db, offer_id, cId):
            return error(400, "Offer not found or already processed")

    return redirect("/my_offers")

@market_bp.route("/post_trade_offer/<offer_type>/<offeree_id>", methods=["POST"])
@login_required
def post_trade_offer(offer_type, offeree_id):
    cId = session["user_id"]
    with get_request_cursor() as db:
        resource = request.form.get("resource")
        amount, err = get_valid_int("amount", error_invalid="Amount must be a valid number")
        if err: return err
        price, err = get_valid_int("price", error_invalid="Price must be a valid number")
        if err: return err

        if price < 1:
            return error(400, "Price cannot be less than 1")

        if not offeree_id.isnumeric():
            return error(400, "Offeree id must be numeric")
        
        if offer_type not in ["buy", "sell"]:
            return error(400, "Offer type must be 'buy' or 'sell'")

        if not is_active_resource(db, resource):
            return error(400, "No such resource")

        if amount < 1:
            return error(400, "Amount must be greater than 0")

        # trades.amount / trades.price / trades.offeree are INTEGER columns:
        # anything past 2,147,483,647 raised NumericValueOutOfRange on the
        # INSERT (a 500, after the escrow had already been taken).
        if amount > MAX_TRADE_INT or price > MAX_TRADE_INT:
            return error(
                400, f"Amount and price can be at most {MAX_TRADE_INT:,} per offer"
            )
        offeree_int = int(offeree_id)
        if offeree_int == cId:
            return error(400, "You cannot send a direct trade to yourself!")

        # A deleted/nonexistent nation failed the trades.offeree foreign key
        # on INSERT -- another 500 after escrow.
        if offeree_int > MAX_TRADE_INT or not user_exists(db, offeree_int):
            return error(404, "That nation does not exist")
        offeree_id = str(offeree_int)

        currency_id, cur_err = parse_currency_choice(db, request.form.get("currency_id"))
        if cur_err:
            return error(400, cur_err)

        if offer_type == "sell":
            realAmount = get_user_resource_quantity(db, cId, resource)
            if realAmount is None:
                return error(400, "No such resource")

            if amount > realAmount:
                return error(400, "Selling amount is higher than the amount you have.")

            res = give_resource(cId, "bank", resource, amount, cursor=db)
            if res is not True:
                report_trade_error(f"trade_offer: escrow reserve failed: {res}")
                return error(400, str(res))

            insert_trade(db, cId, offer_type, resource, amount, price, offeree_id, currency_id)

        elif offer_type == "buy" and currency_id:
            lock_users(db, [cId])
            if not take_currency(db, cId, currency_id, amount * price):
                return error(400, "You don't hold enough of that currency to back this offer.")
            insert_trade(db, cId, offer_type, resource, amount, price, offeree_id, currency_id)

        elif offer_type == "buy":
            # Escrow first, insert last: every error() below still ends in a
            # teardown COMMIT, so inserting up front left an unfunded buy offer
            # behind whenever the buyer couldn't pay -- and accepting it
            # credited the seller amount*price gold that was never escrowed.
            money_to_take_away = amount * price
            current_money = get_user_gold_for_update(db, cId)
            if current_money is None:
                return error(500, "Your nation data could not be found")
            
            if current_money < money_to_take_away:
                return error(400, "You don't have enough money.")

            res = give_resource(cId, "bank", "money", money_to_take_away, cursor=db)
            if res is not True:
                report_trade_error(f"trade_offer: escrow take money failed: {res}")
                return error(400, str(res))

            insert_trade(db, cId, offer_type, resource, amount, price, offeree_id)

            flash("You just posted a market offer")

    return redirect(f"/country/id={offeree_id}")

# Direct sell trades posted before the bank-escrow change (e59c853c, Feb 2026)
# never had their resource set aside. Two were still pending on 2026-09-28
# (ids 4 and 5): accepting takes the resource from the seller as it did back
# then, and declining has nothing to refund.
LEGACY_UNESCROWED_SELL_TRADE_IDS = frozenset({4, 5})


def _sell_trade_escrowed(trade_id):
    return int(trade_id) not in LEGACY_UNESCROWED_SELL_TRADE_IDS


@market_bp.route("/decline_trade/<trade_id>", methods=["POST"])
@login_required
def decline_trade_endpoint(trade_id):
    if not trade_id.isnumeric():
        return error(400, "Trade id must be numeric")

    cId = session["user_id"]
    with get_request_cursor() as db:
        deleted_row = delete_trade(db, trade_id, cId)
        if not deleted_row:
            return error(400, "Trade not found or already processed")
            
        trade_type, resource, amount, price, offerer, currency_id = deleted_row

        if trade_type == "sell" and not _sell_trade_escrowed(trade_id):
            pass  # legacy pre-escrow trade: nothing was set aside
        elif trade_type == "sell":
            try:
                give_resource("bank", offerer, resource, amount, cursor=db)
            except Exception:
                rollback_db_cursor(db)
        elif trade_type == "buy" and currency_id:
            give_currency(db, offerer, currency_id, amount * price)
        elif trade_type == "buy":
            try:
                give_resource("bank", offerer, "money", amount * price, cursor=db)
            except Exception:
                rollback_db_cursor(db)

    return redirect("/my_offers")

@market_bp.route("/accept_trade/<trade_id>", methods=["POST"])
@login_required
def accept_trade(trade_id):
    # int(trade_id) in try_lock_trade raised on a non-numeric id and the
    # lookup below then 500'd on the bad SQL parameter.
    if not str(trade_id).isnumeric() or int(trade_id) > MAX_TRADE_INT:
        return error(400, "Trade id must be numeric")
    cId = session["user_id"]
    with get_request_cursor() as db:
        lock_blocked = False
        lock_acquired = False
        try:
            acquired = try_lock_trade(db, trade_id)
            if not acquired:
                lock_blocked = True
            else:
                lock_acquired = True
        except Exception:
            rollback_db_cursor(db)
            lock_acquired = False

        if lock_blocked:
            return error(400, "Trade is being processed")

        try:
            row = get_trade_by_id(db, trade_id)
            if not row:
                return error(400, "Trade not found")
            offeree, trade_type, offerer, resource, amount, price, currency_id = row

            if offeree != cId:
                return error(400, "You can't accept that offer")

            if not is_active_resource(db, resource):
                return error(400, "This resource is not currently tradable")

            lock_users(db, [cId, offerer])

            # Transport fee (app_core/market/fees.py), paid by the accepting
            # nation: on top of the price when it's buying, out of the
            # proceeds when it's selling.
            trade_total = amount * price
            accept_fee = trade_fee(trade_total, trade_fee_percent(db, offeree, offerer))

            if trade_type == "sell" and currency_id:
                # Priced in a nation currency: the accepting buyer pays price
                # + fee in it; the fee is burned. Checked before anything moves.
                if get_currency_balance(db, offeree, currency_id) < trade_total + accept_fee:
                    return error(400, "You don't have enough of the currency this trade is priced in")
                gr_ret = give_resource("bank", offeree, resource, amount, cursor=db)
                if gr_ret is not True:
                    rollback_db_cursor(db)
                    return error(400, gr_ret or "Trade acceptance failed")
                if not take_currency(db, offeree, currency_id, trade_total + accept_fee):
                    rollback_db_cursor(db)
                    return error(400, "You don't have enough of the currency this trade is priced in")
                give_currency(db, offerer, currency_id, trade_total)

            elif trade_type == "buy" and currency_id:
                # The offerer escrowed trade_total of the currency; the
                # accepting seller gets it minus the fee.
                gr_ret = give_resource(offeree, offerer, resource, amount, cursor=db)
                if gr_ret is not True:
                    return error(400, gr_ret or "Trade acceptance failed")
                give_currency(db, offeree, currency_id, trade_total - accept_fee)

            elif trade_type == "sell":
                buyer_gold = get_user_gold_for_update(db, offeree)
                if buyer_gold is None or buyer_gold < (trade_total + accept_fee):
                    return error(400, "Buyer doesn't have enough money")

                # post_trade_offer escrows a sell trade's resource at the bank
                # (since e59c853c, Feb 2026), so it's delivered from there.
                # This used to try offerer -> offeree first, which took the
                # resource from the seller a second time whenever they still
                # had that much left, leaving the escrow stranded.
                source = "bank" if _sell_trade_escrowed(trade_id) else offerer
                try:
                    gr_ret = give_resource(source, offeree, resource, amount, cursor=db)
                except Exception as exc:
                    report_trade_error("accept_trade: escrow delivery raised exception", exc=exc)
                    return error(400, "Trade acceptance failed")
                if gr_ret is not True:
                    return error(400, gr_ret or "Trade acceptance failed")

                try:
                    if not decrement_gold(db, offeree, trade_total + accept_fee):
                        return error(400, "Buyer doesn't have enough money")
                    if not increment_gold(db, offerer, amount * price):
                        raise Exception("Failed to credit seller")
                except Exception as exc:
                    report_trade_error("accept_trade: transactional sell failed", exc=exc)
                    return error(400, "Trade acceptance failed")

            elif trade_type == "buy":
                try:
                    gr_ret = give_resource(offeree, offerer, resource, amount, cursor=db)
                except Exception as exc:
                    report_trade_error("accept_trade: give_resource raised exception during buy", exc=exc)
                    return error(400, "Trade acceptance failed")
                if gr_ret is not True:
                    return error(400, gr_ret or "Trade acceptance failed")

                try:
                    if not increment_gold(db, offeree, trade_total - accept_fee):
                        raise Exception("Failed to credit seller")
                except Exception as exc:
                    report_trade_error("accept_trade: transactional buy failed", exc=exc)
                    return error(400, "Trade acceptance failed")

            # FIXED 2026-09-23: found live while auditing app_core/market/
            # during the account cross-contamination investigation --
            # unrelated bug, real double-accept race. try_lock_trade() uses
            # a SESSION-level pg_try_advisory_lock (not the transaction-
            # scoped pg_advisory_xact_lock used everywhere else in this
            # codebase), explicitly released below in `finally`. This
            # delete_trade_by_id() call used to happen AFTER that finally
            # block -- meaning the lock was released while the trade row
            # (the actual idempotency marker) still existed, opening a real
            # window: a second accept_trade call (double-click, two tabs)
            # could acquire the now-free lock, find the trade still
            # present via get_trade_by_id(), and run the entire resource/
            # gold transfer a second time for one trade offer, all before
            # either request got around to deleting the row. Moved inside
            # this same try block so the row is gone before the lock is
            # ever released -- a second racer's get_trade_by_id() then
            # correctly finds nothing.
            delete_trade_by_id(db, trade_id)
        finally:
            if lock_acquired:
                try:
                    unlock_trade(db, trade_id)
                except Exception:
                    pass

        _offerer_username = get_username(db, offerer)
        _offeree_username = get_username(db, offeree)

        if _offerer_username and _offeree_username:
            try:
                total_price = int(amount) * int(price)
                news_msg = f"Your market offer of {amount} {resource} was purchased by {_offeree_username} for ${total_price}"
                insert_news(db, offerer, news_msg)
            except Exception:
                pass

        _offerer = offerer
        _offeree = offeree

    try:
        invalidate_user_cache(_offerer)
        invalidate_user_cache(_offeree)
    except Exception:
        pass

    try:
        logger.info(
            "trade_executed",
            extra={
                "offer_id": trade_id,
                "resource": resource,
                "amount": int(amount),
                "price": int(price),
                "total": int(amount) * int(price),
                "offerer": int(offerer),
                "offeree": int(offeree),
                "trade_type": trade_type,
            },
        )
    except Exception:
        pass

    try:
        record_trade_event(trade_id, offerer, offeree, resource, amount, price, trade_type)
    except Exception:
        pass

    return redirect("/my_offers")

@market_bp.route("/transfer/<transferee>", methods=["POST"])
@login_required
def transfer(transferee):
    cId = session["user_id"]

    try:
        transferee_id = int(transferee)
    except (ValueError, TypeError):
        return error(400, "Invalid nation ID")

    if transferee_id == cId:
        return error(400, "You cannot transfer resources to yourself")

    with get_request_cursor() as db:
        if not user_exists(db, transferee_id):
            return error(404, "That nation does not exist")

        # Bulk aid support (player-requested: send multiple resource kinds in
        # one package instead of one gift per resource). The form repeats
        # "resource"/"amount" field names for each row the player added
        # client-side; Flask's getlist pairs them up positionally. Single-item
        # gifts (the original UI shape) still work the same way -- getlist on
        # a form with exactly one "resource"/"amount" pair just returns
        # 1-item lists.
        resource_list = request.form.getlist("resource")
        amount_list = request.form.getlist("amount")
        gift_message = (request.form.get("message") or "").strip()[:240]
        keep_private = request.form.get("keep_private") == "on"

        if not resource_list or not amount_list:
            return error(400, "Pick at least one resource and amount")
        if len(resource_list) != len(amount_list):
            return error(400, "Mismatched resource/amount rows")

        # Merge duplicate resource rows (e.g. two "gold" rows) into one so a
        # single balance check/decrement covers the combined amount.
        merged = {}
        order = []
        for resource, amount_str in zip(resource_list, amount_list):
            resource = (resource or "").strip()
            if not resource:
                continue
            if not amount_str:
                return error(400, "Amount is required for every resource row")
            try:
                amount = int(amount_str)
            except (ValueError, TypeError):
                return error(400, "Amount must be a valid number")
            if amount < 1:
                return error(400, "Amount cannot be less than 1")
            norm = "gold" if resource == "money" else resource
            if norm not in merged:
                merged[norm] = 0
                order.append(norm)
            merged[norm] += amount

        if not merged:
            return error(400, "Pick at least one resource and amount")
        if len(merged) > 20:
            return error(400, "Too many resource kinds in one package")

        # Validate every resource kind exists BEFORE touching any balance, so
        # a bad row in a bulk package can't partially apply.
        for resource in order:
            if resource != "gold" and not is_active_resource(db, resource):
                return error(400, f"No such resource: {resource}")

        # Pre-check every balance up front too (still re-checked atomically
        # at debit time below) so a package that's affordable on gold but not
        # on, say, steel fails cleanly with nothing charged yet.
        for resource, amount in merged.items():
            if resource == "gold":
                have = get_user_gold_for_update(db, cId)
                if have is None:
                    return error(500, "Your nation data could not be found")
            else:
                have = get_user_resource_quantity(db, cId, resource)
                if have is None:
                    return error(400, f"No such resource: {resource}")
            if amount > have:
                return error(400, f"You don't have enough {resource if resource != 'gold' else 'money'}.")

        for resource, amount in merged.items():
            if resource == "gold":
                if not decrement_gold(db, cId, amount):
                    return error(400, "You don't have enough money.")
                increment_gold(db, transferee_id, amount)
            else:
                res = give_resource(cId, transferee_id, resource, amount, cursor=db)
                if res is not True:
                    return error(400, str(res))

        sender_name = get_username(db, cId) or "A nation"
        item_descs = [
            f"${amount:,}" if resource == "gold" else f"{amount:,} {resource}"
            for resource, amount in ((r, merged[r]) for r in order if r in merged)
        ]
        amount_desc = ", ".join(item_descs)
        recipient_msg = f"{sender_name} sent you {amount_desc}."
        sender_msg = f"You sent {amount_desc} to your ally."
        if gift_message:
            recipient_msg += f' Message: "{gift_message}"'
            sender_msg += f' Message: "{gift_message}"'
        insert_news(db, transferee_id, recipient_msg)
        insert_news(db, cId, sender_msg)

        if not keep_private:
            recipient_name = get_username(db, transferee_id) or "a nation"
            log_event(
                db, "aid",
                f"{sender_name} sent {amount_desc} in aid to {recipient_name}.",
                actor_id=cId, target_id=transferee_id,
            )

        try:
            invalidate_user_cache(cId)
            invalidate_user_cache(transferee_id)
        except Exception:
            pass

    return redirect(f"/country/id={transferee_id}")

@market_bp.route("/embargo/<target_id>", methods=["POST"])
@login_required
def embargo_nation(target_id):
    cId = session["user_id"]

    try:
        target_id = int(target_id)
    except (ValueError, TypeError):
        return error(400, "Invalid nation ID")

    if target_id == cId:
        return error(400, "You cannot embargo yourself")

    with get_request_cursor() as db:
        if not user_exists(db, target_id):
            return error(404, "That nation does not exist")
        add_embargo(db, cId, target_id)

    return redirect(f"/country/id={target_id}")

@market_bp.route("/embargo/<target_id>/remove", methods=["POST"])
@login_required
def remove_embargo_endpoint(target_id):
    cId = session["user_id"]

    try:
        target_id = int(target_id)
    except (ValueError, TypeError):
        return error(400, "Invalid nation ID")

    with get_request_cursor() as db:
        remove_embargo(db, cId, target_id)

    redirect_to = request.form.get("redirect_to")
    if redirect_to == "my_offers":
        return redirect("/my_offers")
    return redirect(f"/country/id={target_id}")
