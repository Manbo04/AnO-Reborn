from flask import Blueprint, request, render_template, session, redirect, flash
from helpers import login_required, error, get_valid_int, record_trade_event
import variables
import logging
from database import get_request_cursor, invalidate_user_cache, rollback_db_cursor, cache_response

from .repositories import (
    is_active_resource, get_user_resource_quantity, count_offers, get_offers,
    get_offer_by_id, delete_offer, update_offer_amount, lock_users, get_user_gold_for_update,
    insert_offer, insert_trade, get_my_trades, get_my_offers, delete_trade, try_lock_trade,
    unlock_trade, get_trade_by_id, get_username, insert_news, delete_trade_by_id, user_exists,
    decrement_gold, increment_gold
)
from .services import give_resource, report_trade_error

market_bp = Blueprint("market_bp", __name__)
logger = logging.getLogger(__name__)

@market_bp.route("/market", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)
def market():
    with get_request_cursor(read_only=True) as db:
        cId = session["user_id"]

        filter_resource = request.values.get("filtered_resource")
        price_type = request.values.get("price_type")
        offer_type = request.values.get("offer_type")

        page = request.values.get("page", default=1, type=int)
        per_page = request.values.get("per_page", default=50, type=int)
        if per_page not in [50, 100, 150]:
            per_page = 50

        if price_type is not None and price_type not in ["ASC", "DESC"]:
            return error(400, "No such price type")

        if filter_resource is not None and filter_resource not in variables.RESOURCES:
            return error(400, "No such resource")

        total_count = count_offers(db, filter_resource, offer_type)
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page

        offers_data = get_offers(db, filter_resource, offer_type, price_type, per_page, offset)
        
        offers = []
        for row in offers_data:
            user_id, offer_type_val, resource, amount, price, offer_id, username = row
            offers.append((user_id, offer_type_val, username, resource, amount, price, offer_id, price * amount))

        return render_template(
            "market.html",
            offers=offers,
            price_type=price_type,
            cId=cId,
            current_page=page,
            total_pages=total_pages,
            total_count=total_count,
            per_page=per_page,
            filtered_resource=filter_resource,
            offer_type=offer_type,
        )

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
        resource, total_amount, price_for_one, seller_id = row

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
        market_fee = int(total_price * 0.05)
        total_cost_to_buyer = total_price + market_fee

        if total_cost_to_buyer > buyers_gold:
            return error(400, "You don't have enough money.")

        res = give_resource("bank", cId, resource, amount_wanted, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"buy_market_offer: give_resource(bank -> buyer) failed: {res}")
            return error(400, str(res))

        res = give_resource(cId, seller_id, "money", total_price, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"buy_market_offer: give_resource(buyer -> seller money) failed: {res}")
            return error(400, str(res))

        if market_fee > 0:
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

    try:
        invalidate_user_cache(cId)
        invalidate_user_cache(seller_id)
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
        resource, total_amount, price_for_one, buyer_id = row

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

        res = give_resource(seller_id, buyer_id, resource, amount_wanted, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"sell_market_offer: give_resource(seller -> buyer) failed: {res}")
            return error(400, str(res))

        res = give_resource("bank", seller_id, "money", total_price, cursor=db)
        if res is not True:
            rollback_db_cursor(db)
            report_trade_error(f"sell_market_offer: give_resource(bank -> seller money) failed: {res}")
            return error(400, str(res))

        new_offer_amount = total_amount - amount_wanted
        if new_offer_amount == 0:
            delete_offer(db, offer_id)
        else:
            update_offer_amount(db, offer_id, new_offer_amount)

    try:
        invalidate_user_cache(seller_id)
        invalidate_user_cache(buyer_id)
    except Exception:
        pass

    return redirect("/market")

@market_bp.route("/marketoffer/", methods=["GET", "POST"])
@login_required
def marketoffer():
    return render_template("marketoffer.html")

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

            insert_offer(db, cId, offer_type, resource, amount, price)

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

    return render_template("my_offers.html", cId=cId, offers=offers)

@market_bp.route("/delete_offer/<offer_id>", methods=["POST"])
@login_required
def delete_offer_endpoint(offer_id):
    cId = session["user_id"]
    with get_request_cursor() as db:
        deleted_row = delete_offer(db, offer_id, cId)
        if not deleted_row:
            return error(400, "Offer not found or already processed")

        offer_type, amount, price, resource = deleted_row

        if offer_type == "buy":
            give_resource("bank", cId, "money", price * amount, cursor=db)
        elif offer_type == "sell":
            give_resource("bank", cId, resource, amount, cursor=db)

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

        if offeree_id == str(cId):
            return error(400, "You cannot send a direct trade to yourself!")

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

            insert_trade(db, cId, offer_type, resource, amount, price, offeree_id)

        elif offer_type == "buy":
            insert_trade(db, cId, offer_type, resource, amount, price, offeree_id)

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

            flash("You just posted a market offer")

    return redirect(f"/country/id={offeree_id}")

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
            
        trade_type, resource, amount, price, offerer = deleted_row

        if trade_type == "sell":
            try:
                give_resource("bank", offerer, resource, amount, cursor=db)
            except Exception:
                rollback_db_cursor(db)
        elif trade_type == "buy":
            try:
                give_resource("bank", offerer, "money", amount * price, cursor=db)
            except Exception:
                rollback_db_cursor(db)

    return redirect("/my_offers")

@market_bp.route("/accept_trade/<trade_id>", methods=["POST"])
@login_required
def accept_trade_endpoint(trade_id):
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
            offeree, trade_type, offerer, resource, amount, price = row

            if offeree != cId:
                return error(400, "You can't accept that offer")

            if not is_active_resource(db, resource):
                return error(400, "This resource is not currently tradable")

            lock_users(db, [cId, offerer])

            if trade_type == "sell":
                buyer_gold = get_user_gold_for_update(db, offeree)
                if buyer_gold is None or buyer_gold < (amount * price):
                    return error(400, "Buyer doesn't have enough money")

                try:
                    gr_ret = give_resource(offerer, offeree, resource, amount, cursor=db)
                except Exception as exc:
                    report_trade_error("accept_trade: give_resource raised exception during sell", exc=exc)
                    return error(400, "Trade acceptance failed")

                if gr_ret is not True:
                    try:
                        gr_ret2 = give_resource("bank", offeree, resource, amount, cursor=db)
                    except Exception as exc:
                        report_trade_error("accept_trade: fallback give_resource raised exception", exc=exc)
                        return error(400, "Trade acceptance failed")
                    if gr_ret2 is not True:
                        return error(400, gr_ret or (gr_ret2 or "Trade acceptance failed"))

                try:
                    if not decrement_gold(db, offeree, amount * price):
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
                    if not increment_gold(db, offeree, amount * price):
                        raise Exception("Failed to credit seller")
                except Exception as exc:
                    report_trade_error("accept_trade: transactional buy failed", exc=exc)
                    return error(400, "Trade acceptance failed")
        finally:
            if lock_acquired:
                try:
                    unlock_trade(db, trade_id)
                except Exception:
                    pass

        try:
            delete_trade_by_id(db, trade_id)
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

        resource = request.form.get("resource")
        amount_str = request.form.get("amount")
        if not amount_str:
            return error(400, "Amount is required")
        try:
            amount = int(amount_str)
        except (ValueError, TypeError):
            return error(400, "Amount must be a valid number")

        if resource not in ["gold", "money"] and not is_active_resource(db, resource):
            return error(400, "No such resource")

        if amount < 1:
            return error(400, "Amount cannot be less than 1")

        if resource in ["gold", "money"]:
            user_money = get_user_gold_for_update(db, cId)
            if user_money is None:
                return error(500, "Your nation data could not be found")

            if amount > user_money:
                return error(400, "You don't have enough money.")

            if not decrement_gold(db, cId, amount):
                return error(400, "You don't have enough money.")

            increment_gold(db, transferee_id, amount)

        else:
            user_resource = get_user_resource_quantity(db, cId, resource)
            if user_resource is None:
                return error(400, "No such resource")

            if amount > user_resource:
                return error(400, "You don't have enough resources.")
            res = give_resource(cId, transferee_id, resource, amount, cursor=db)
            if res is not True:
                return error(400, str(res))

        try:
            invalidate_user_cache(cId)
            invalidate_user_cache(transferee_id)
        except Exception:
            pass

    return redirect(f"/country/id={transferee_id}")
