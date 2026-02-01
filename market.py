# NOTE: 'app' is NOT imported at module level to avoid circular imports
from helpers import login_required, error
from database import get_db_cursor, get_db_connection, invalidate_user_cache
from flask import request, render_template, session, redirect, flash
import variables
import logging

logger = logging.getLogger(__name__)


def _report_trade_error(msg, exc=None, extra=None):
    """Log trade-related errors and attempt to send to Sentry if available.

    `extra` should be a dict of additional context (user_id, trade_id, offer_id,
    resource, amount, price, etc). This will be attached as extras to Sentry
    if available and included in the logger output.
    """
    try:
        if extra:
            logger.error("%s | extra=%s", msg, extra)
        else:
            logger.error(msg)

        # Try to send to Sentry if configured
        try:
            import sentry_sdk

            # If extra context is supplied, push a scope so it is attached to the event
            if extra:
                with sentry_sdk.push_scope() as scope:
                    for k, v in (extra or {}).items():
                        try:
                            scope.set_extra(k, v)
                        except Exception:
                            # Some Sentry SDK versions may differ; ignore failures
                            pass
                    if exc:
                        sentry_sdk.capture_exception(exc)
                    else:
                        sentry_sdk.capture_message(msg)
            else:
                if exc:
                    sentry_sdk.capture_exception(exc)
                else:
                    sentry_sdk.capture_message(msg)
        except Exception:
            # Sentry not configured or failed; don't raise from here
            pass
    except Exception:
        # Logging should never raise and crash handlers
        pass


def give_resource(giver_id, taker_id, resource, amount):
    # If giver_id is bank, don't remove any resources from anyone
    # If taker_id is bank, just remove the resources from the player

    # Use connection pool instead of direct connection
    with get_db_connection() as conn:
        db = conn.cursor()

        if giver_id != "bank":
            giver_id = int(giver_id)
        if taker_id != "bank":
            taker_id = int(taker_id)
        amount = int(amount)

        resources_list = variables.RESOURCES

        # Returns error if resource doesn't exist
        if resource not in resources_list and resource != "money":
            return "No such resource"

        if resource in ["gold", "money"]:
            if giver_id != "bank":
                # Atomically decrement gold only when sufficient balance exists
                db.execute(
                    (
                        "UPDATE stats SET gold=gold-%s "
                        "WHERE id=%s AND gold>=%s "
                        "RETURNING gold"
                    ),
                    (amount, giver_id, amount),
                )
                if db.fetchone() is None:
                    return (
                        "Giver doesn't have enough resources to transfer such amount."
                    )

            if taker_id != "bank":
                # Increment gold for taker and return the new value
                db.execute(
                    ("UPDATE stats SET gold=gold+%s " "WHERE id=%s " "RETURNING gold"),
                    (amount, taker_id),
                )
                db.fetchone()

        else:
            if giver_id != "bank":
                # Atomically decrement resource only when sufficient amount exists
                db.execute(
                    (
                        f"UPDATE resources SET {resource}={resource}-%s "
                        + f"WHERE id=%s AND {resource} >= %s RETURNING {resource}"
                    ),
                    (amount, giver_id, amount),
                )
                if db.fetchone() is None:
                    return (
                        "Giver doesn't have enough resources to transfer such amount."
                    )

            if taker_id != "bank":
                # Increment taker's resource
                db.execute(
                    (
                        f"UPDATE resources SET {resource}={resource}+%s "
                        f"WHERE id=%s RETURNING {resource}"
                    ),
                    (amount, taker_id),
                )
                db.fetchone()

        conn.commit()

        # Invalidate caches affected by this resource transfer so the UI shows
        # fresh data immediately (resources/influence caches are per-user).
        try:
            if giver_id != "bank":
                invalidate_user_cache(giver_id)
            if taker_id != "bank":
                invalidate_user_cache(taker_id)
        except Exception:
            # Cache invalidation failures should not affect the transaction itself
            pass

    return True


@login_required
def market():
    if request.method == "GET":
        # Use connection pool instead of direct connection
        from database import get_db_cursor

        with get_db_cursor() as db:
            cId = session["user_id"]

            # GET Query Parameters
            try:
                filter_resource = request.values.get("filtered_resource")
            except TypeError:
                filter_resource = None

            try:
                price_type = request.values.get("price_type")
            except TypeError:
                price_type = None

            try:
                offer_type = request.values.get("offer_type")
            except TypeError:
                offer_type = None

            # Processing of query parameters into database statements
            if price_type is not None:
                list_of_price_types = ["ASC", "DESC"]

                if price_type not in list_of_price_types:
                    return error(400, "No such price type")

            if filter_resource is not None:
                resources_list = variables.RESOURCES

                if (
                    filter_resource not in resources_list
                ):  # Checks if the resource the user selected actually exists
                    return error(400, "No such resource")

            # Use JOIN query instead of loop to fetch all data at once
            if filter_resource is not None:
                query = (
                    "SELECT o.user_id, o.type, o.resource, o.amount, o.price, "
                    "o.offer_id, u.username "
                    "FROM offers o "
                    "INNER JOIN users u ON o.user_id = u.id "
                    "WHERE o.resource = %s "
                    "ORDER BY o.price ASC"
                )
                db.execute(query, (filter_resource,))
            elif offer_type is not None and price_type is not None:
                order_dir = "ASC" if price_type == "ASC" else "DESC"
                query = (
                    "SELECT o.user_id, o.type, o.resource, o.amount, o.price, "
                    "o.offer_id, u.username "
                    "FROM offers o "
                    "INNER JOIN users u ON o.user_id = u.id "
                    "WHERE o.type = %s "
                    f"ORDER BY o.price {order_dir}"
                )
                db.execute(query, (offer_type,))
            elif offer_type is not None:
                query = (
                    "SELECT o.user_id, o.type, o.resource, o.amount, o.price, "
                    "o.offer_id, u.username "
                    "FROM offers o "
                    "INNER JOIN users u ON o.user_id = u.id "
                    "WHERE o.type = %s "
                    "ORDER BY o.price ASC"
                )
                db.execute(query, (offer_type,))
            elif price_type is not None:
                order_dir = "ASC" if price_type == "ASC" else "DESC"
                query = (
                    "SELECT o.user_id, o.type, o.resource, o.amount, o.price, "
                    "o.offer_id, u.username "
                    "FROM offers o "
                    "INNER JOIN users u ON o.user_id = u.id "
                    f"ORDER BY o.price {order_dir}"
                )
                db.execute(query)
            else:
                query = (
                    "SELECT o.user_id, o.type, o.resource, o.amount, o.price, "
                    "o.offer_id, u.username "
                    "FROM offers o "
                    "INNER JOIN users u ON o.user_id = u.id "
                    "ORDER BY o.price ASC"
                )
                db.execute(query)

            offers_data = db.fetchall()

            # Process results
            ids = []
            types = []
            names = []
            resources = []
            amounts = []
            prices = []
            total_prices = []
            offer_ids = []

            for (
                user_id,
                offer_type_val,
                resource,
                amount,
                price,
                offer_id,
                username,
            ) in offers_data:
                ids.append(user_id)
                types.append(offer_type_val)
                resources.append(resource)
                amounts.append(amount)
                prices.append(price)
                total_prices.append(price * amount)
                offer_ids.append(offer_id)
                names.append(username)

            offers = zip(
                ids, types, names, resources, amounts, prices, offer_ids, total_prices
            )  # Zips everything into 1 list

            return render_template(
                "market.html", offers=offers, price_type=price_type, cId=cId
            )


@login_required
def buy_market_offer(offer_id):
    with get_db_connection() as connection:
        db = connection.cursor()

        cId = session["user_id"]

        amount_str = request.form.get(f"amount_{offer_id}")
        if not amount_str:
            return error(400, "Amount is required")

        try:
            amount_wanted = int(amount_str.replace(",", ""))
        except (ValueError, TypeError, AttributeError):
            return error(400, "Amount must be a valid number")

        db.execute(
            "SELECT resource, amount, price, user_id FROM offers WHERE offer_id=(%s)",
            (offer_id,),
        )
        row = db.fetchone()
        if not row:
            return error(400, "Offer not found")
        resource, total_amount, price_for_one, seller_id = row

        if amount_wanted < 1:
            return error(400, "Amount cannot be less than 1")

        if amount_wanted > total_amount:
            return error(400, "Requested amount exceeds available amount")

        db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
        buyers_gold = int(db.fetchone()[0])

        total_price = amount_wanted * price_for_one

        if (
            total_price > buyers_gold
        ):  # Checks if buyer doesnt have enough gold for buyin
            return error(400, "You don't have enough money.")  # Returns error if true

        res = give_resource("bank", cId, resource, amount_wanted)  # Gives the resource
        if res is not True:
            _report_trade_error(
                f"buy_market_offer: give_resource(bank -> buyer) failed: {res}",
                extra={
                    "user_id": cId,
                    "offer_id": offer_id,
                    "resource": resource,
                    "amount": amount_wanted,
                    "price": price_for_one,
                    "seller_id": seller_id,
                },
            )
            return error(400, str(res))
        res = give_resource(cId, seller_id, "money", total_price)  # Gives the money
        if res is not True:
            _report_trade_error(
                f"buy_market_offer: give_resource(buyer -> seller money) failed: {res}",
                extra={
                    "user_id": cId,
                    "offer_id": offer_id,
                    "resource": resource,
                    "amount": amount_wanted,
                    "price": price_for_one,
                    "seller_id": seller_id,
                },
            )
            return error(400, str(res))

        new_offer_amount = total_amount - amount_wanted

        if new_offer_amount == 0:
            db.execute("DELETE FROM offers WHERE offer_id=(%s)", (offer_id,))
        else:
            db.execute(
                "UPDATE offers SET amount=(%s) WHERE offer_id=(%s)",
                (new_offer_amount, offer_id),
            )

    return redirect("/market")


@login_required
def sell_market_offer(offer_id):
    with get_db_connection() as conn:
        db = conn.cursor()

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

        db.execute(
            "SELECT resource, amount, price, user_id FROM offers WHERE offer_id=(%s)",
            (offer_id,),
        )
        row = db.fetchone()
        if not row:
            return error(400, "Offer not found")
        resource, total_amount, price_for_one, buyer_id = row

        # Sees how much of the resource the seller has
        resource_statement = f"SELECT {resource} FROM resources " + "WHERE id=%s"
        db.execute(resource_statement, (seller_id,))
        sellers_resource = db.fetchone()[0]

        if amount_wanted < 1:
            return error(400, "Amount cannot be less than 1")

        if amount_wanted > total_amount:
            return error(400, "Requested amount exceeds desired amount")

        # Checks if it's less than what the seller wants to sell
        if sellers_resource < amount_wanted:
            return error(400, "You don't have enough of that resource")

        # Removes the resource from the seller and gives it to the buyer
        res = give_resource(seller_id, buyer_id, resource, amount_wanted)
        if res is not True:
            _report_trade_error(
                f"sell_market_offer: give_resource(seller -> buyer) failed: {res}",
                extra={
                    "user_id": seller_id,
                    "offer_id": offer_id,
                    "resource": resource,
                    "amount": amount_wanted,
                    "price": price_for_one,
                    "buyer_id": buyer_id,
                },
            )
            return error(400, str(res))

        # Takes away the money used for buying from the buyer and gives it to the seller
        res = give_resource(
            buyer_id,
            seller_id,
            "money",
            price_for_one * amount_wanted,
        )
        if res is not True:
            msg = (
                "sell_market_offer: give_resource(buyer -> seller money) failed: "
                + str(res)
            )
            _report_trade_error(
                msg,
                extra={
                    "user_id": seller_id,
                    "offer_id": offer_id,
                    "resource": resource,
                    "amount": amount_wanted,
                    "price": price_for_one,
                    "buyer_id": buyer_id,
                },
            )
            return error(400, str(res))
        # Calculate new offer amount after sale
        new_offer_amount = total_amount - amount_wanted

        if new_offer_amount == 0:  # Checks if the new offer amount is equal to 0
            db.execute(
                "DELETE FROM offers WHERE offer_id=(%s)", (offer_id,)
            )  # If yes, it deletes the offer

        else:
            db.execute(
                "UPDATE offers SET amount=(%s) WHERE offer_id=(%s)",
                (new_offer_amount, offer_id),
            )  # Updates the database with the new amount

    return redirect("/market")


@login_required
def marketoffer():
    return render_template("marketoffer.html")


@login_required
def post_offer(offer_type):
    cId = session["user_id"]

    with get_db_connection() as connection:
        db = connection.cursor()

        resource = request.form.get("resource")

        amount_str = request.form.get("amount")
        if not amount_str:
            return error(400, "Amount is required")
        try:
            amount = int(amount_str)
        except (ValueError, TypeError):
            return error(400, "Amount must be a valid number")

        price_str = request.form.get("price")
        if not price_str:
            return error(400, "Price is required")
        try:
            price = int(price_str)
        except (ValueError, TypeError):
            return error(400, "Price must be a valid number")

        # List of all the resources in the game
        resources = variables.RESOURCES

        offer_types = ["buy", "sell"]
        if offer_type not in offer_types:
            return error(400, "Offer type must be 'buy' or 'sell'")

        if (
            resource not in resources
        ):  # Checks if the resource the user selected actually exists
            return error(400, "No such resource")

        if amount < 1:  # Checks if the amount is negative
            return error(400, "Amount must be greater than 0")

        if offer_type == "sell":
            rStatement = f"SELECT {resource} FROM resources " + "WHERE id=%s"
            db.execute(rStatement, (cId,))
            realAmount = int(db.fetchone()[0])

            if amount > realAmount:  # Checks if user wants to sell more than he has
                return error(400, "Selling amount is higher than the amount you have.")

            # Calculates the resource amount the seller should have
            give_resource(cId, "bank", resource, amount)

            # Creates a new offer
            db.execute(
                (
                    "INSERT INTO offers (user_id, type, resource, amount, price) "
                    "VALUES (%s, %s, %s, %s, %s)"
                ),
                (
                    cId,
                    offer_type,
                    resource,
                    int(amount),
                    int(price),
                ),
            )

        elif offer_type == "buy":
            db.execute(
                (
                    "INSERT INTO offers (user_id, type, resource, amount, price) "
                    "VALUES (%s, %s, %s, %s, %s)"
                ),
                (
                    cId,
                    offer_type,
                    resource,
                    int(amount),
                    int(price),
                ),
            )

            money_to_take_away = int(amount) * int(price)
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
            current_money = db.fetchone()[0]

            if current_money < money_to_take_away:
                return error(400, "You don't have enough money.")

            give_resource(cId, "bank", "money", money_to_take_away)

        flash("You just posted a market offer")
    return redirect("/market")


@login_required
def my_offers():
    cId = session["user_id"]
    offers = {}
    with get_db_cursor() as db:
        db.execute(
            (
                "SELECT trades.offer_id, trades.price, trades.resource, "
                "trades.amount, trades.type, trades.offeree, users.username "
                "FROM trades INNER JOIN users ON trades.offeree=users.id "
                "WHERE trades.offerer=(%s) ORDER BY trades.offer_id ASC"
            ),
            (cId,),
        )
        offers["outgoing"] = db.fetchall()

        db.execute(
            (
                "SELECT trades.offer_id, trades.price, trades.resource, "
                "trades.amount, trades.type, trades.offerer, users.username "
                "FROM trades INNER JOIN users ON trades.offerer=users.id "
                "WHERE trades.offeree=(%s) ORDER BY trades.offer_id ASC"
            ),
            (cId,),
        )
        offers["incoming"] = db.fetchall()

        db.execute(
            (
                "SELECT offer_id, price, resource, amount, type "
                "FROM offers WHERE user_id=(%s) ORDER BY offer_id ASC"
            ),
            (cId,),
        )
        offers["market"] = db.fetchall()

    return render_template("my_offers.html", cId=cId, offers=offers)


@login_required
def delete_offer(offer_id):
    cId = session["user_id"]

    with get_db_cursor() as db:
        db.execute("SELECT user_id FROM offers WHERE offer_id=(%s)", (offer_id,))
        result = db.fetchone()
        if not result:
            return error(400, "Offer not found")
        offer_owner = result[0]

        # Checks if user owns the offer
        if cId != offer_owner:
            return error(400, "You didn't post that offer")

        db.execute("SELECT type FROM offers WHERE offer_id=(%s)", (offer_id,))
        row = db.fetchone()
        if not row:
            return error(400, "Offer not found")
        offer_type = row[0]

        if offer_type == "buy":
            db.execute(
                "SELECT amount, price FROM offers WHERE offer_id=(%s)", (offer_id,)
            )
            amount, price = db.fetchone()
            give_resource("bank", cId, "money", price * amount)

        elif offer_type == "sell":
            db.execute(
                "SELECT amount, resource FROM offers WHERE offer_id=(%s)", (offer_id,)
            )
            amount, resource = db.fetchone()
            give_resource("bank", cId, resource, amount)

        db.execute(
            "DELETE FROM offers WHERE offer_id=(%s)", (offer_id,)
        )  # Deletes the offer

    return redirect("/my_offers")


@login_required
def trade_offer(offer_type, offeree_id):
    if request.method == "POST":
        cId = session["user_id"]

        with get_db_connection() as connection:
            db = connection.cursor()

            resource = request.form.get("resource")

            amount_str = request.form.get("amount")
            if not amount_str:
                return error(400, "Amount is required")
            try:
                amount = int(amount_str)
            except (ValueError, TypeError):
                return error(400, "Amount must be a valid number")

            price_str = request.form.get("price")
            if not price_str:
                return error(400, "Price is required")
            try:
                price = int(price_str)
            except (ValueError, TypeError):
                return error(400, "Price must be a valid number")

            if price < 1:
                return error(400, "Price cannot be less than 1")

            if not offeree_id.isnumeric():
                return error(400, "Offeree id must be numeric")

            offer_types = ["buy", "sell"]
            if offer_type not in offer_types:
                return error(400, "Offer type must be 'buy' or 'sell'")

            # List of all the resources in the game
            resources = variables.RESOURCES

            if (
                resource not in resources
            ):  # Checks if the resource the user selected actually exists
                return error(400, "No such resource")

            if amount < 1:  # Checks if the amount is negative
                return error(400, "Amount must be greater than 0")

            if offer_type == "sell":
                rStatement = f"SELECT {resource} FROM resources " + "WHERE id=%s"
                db.execute(rStatement, (cId,))
                realAmount = int(db.fetchone()[0])

                if amount > realAmount:  # Checks if user wants to sell more than he has
                    return error(
                        400, "Selling amount is higher than the amount you have."
                    )
                # Calculates the resource amount the seller should have
                newResourceAmount = realAmount - amount

                upStatement = f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
                db.execute(upStatement, (newResourceAmount, cId))

                # Creates a new offer
                db.execute(
                    (
                        "INSERT INTO trades (offerer, type, resource, amount, price, "
                        "offeree) "
                        "VALUES (%s, %s, %s, %s, %s, %s)"
                    ),
                    (cId, offer_type, resource, amount, price, offeree_id),
                )

            elif offer_type == "buy":
                db.execute(
                    (
                        "INSERT INTO trades (offerer, type, resource, amount, price, "
                        "offeree) "
                        "VALUES (%s, %s, %s, %s, %s, %s)"
                    ),
                    (cId, offer_type, resource, amount, price, offeree_id),
                )

                money_to_take_away = amount * price
                db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
                current_money = db.fetchone()[0]
                if current_money < money_to_take_away:
                    return error(400, "You don't have enough money.")
                new_money = current_money - money_to_take_away

                db.execute("UPDATE stats SET gold=(%s) WHERE id=(%s)", (new_money, cId))

                flash("You just posted a market offer")

        return redirect(f"/country/id={offeree_id}")


@login_required
def decline_trade(trade_id):
    if not trade_id.isnumeric():
        return error(400, "Trade id must be numeric")

    cId = session["user_id"]

    with get_db_connection() as connection:
        db = connection.cursor()

        db.execute(
            (
                "SELECT offeree, offerer, type, resource, amount, price "
                "FROM trades WHERE offer_id=(%s)",
            ),
            (trade_id,),
        )
        row = db.fetchone()
        if not row:
            return error(400, "Trade not found")
        offeree, offerer, type, resource, amount, price = row

        if cId not in [offeree, offerer]:
            return error(400, "You haven't been sent that offer")

        db.execute("DELETE FROM trades WHERE offer_id=(%s)", (trade_id,))

        if type == "sell":  # Give back resources, not money
            query = f"UPDATE resources SET {resource}={resource}" + "+%s WHERE id=%s"
            db.execute(
                query,
                (
                    amount,
                    offerer,
                ),
            )
        elif type == "buy":
            db.execute(
                "UPDATE stats SET gold=gold+%s WHERE id=%s",
                (
                    amount * price,
                    offerer,
                ),
            )

    return redirect("/my_offers")


@login_required
def accept_trade(trade_id):
    cId = session["user_id"]

    with get_db_connection() as connection:
        db = connection.cursor()

        # Prevent concurrent accept attempts on the same trade by acquiring a
        # Postgres advisory lock keyed by the trade id. If we can't acquire the
        # lock, another session is processing the trade.
        lock_acquired = False
        try:
            try:
                db.execute("SELECT pg_try_advisory_lock(%s)", (int(trade_id),))
                lock_ret = db.fetchone()
                if not lock_ret or not lock_ret[0]:
                    return error(400, "Trade is being processed")
                lock_acquired = True
            except Exception:
                # If the DB does not support advisory locks or the call fails,
                # proceed without locking (best-effort). The fake test DB will
                # simulate locks where necessary.
                lock_acquired = False

            # Retrieve the trade row (do not delete yet). By acquiring the
            # advisory lock first we serialize acceptance attempts so it's safe
            # to perform external calls (e.g. give_resource) while holding the lock
            # and only delete the trade once the transfer logic succeeds.
            db.execute(
                (
                    "SELECT offeree, type, offerer, resource, amount, price "
                    "FROM trades WHERE offer_id=(%s)"
                ),
                (trade_id,),
            )
            row = db.fetchone()
            if not row:
                return error(400, "Trade not found")
            offeree, trade_type, offerer, resource, amount, price = row

            if offeree != cId:
                return error(400, "You can't accept that offer")

            # Use give_resource where appropriate (tests monkeypatch this to
            # simulate failures). We call it while holding the advisory lock so
            # concurrent accept attempts won't interleave.
            if trade_type == "sell":
                # Check buyer has sufficient gold first (SELECT only; do not
                # modify DB yet so we can bail out without changing state if the
                # resource transfer fails).
                db.execute("SELECT gold FROM stats WHERE id=%s", (offeree,))
                row = db.fetchone()
                if not row or row[0] < (amount * price):
                    return error(400, "Buyer doesn't have enough money")

                # Perform resource transfer (seller -> buyer). give_resource may
                # return a string error or raise an exception; handle both cases.
                try:
                    gr_ret = give_resource(offerer, offeree, resource, amount)
                except Exception as exc:
                    _report_trade_error(
                        "accept_trade: give_resource raised exception during sell",
                        exc=exc,
                        extra={
                            "user_id": cId,
                            "trade_id": trade_id,
                            "trade_type": trade_type,
                            "offerer": offerer,
                            "offeree": offeree,
                            "resource": resource,
                            "amount": amount,
                            "price": price,
                        },
                    )
                    return error(400, "Trade acceptance failed")
                if gr_ret is not True:
                    return error(400, gr_ret or "Trade acceptance failed")

                # Deduct buyer gold and credit seller gold as the final step
                try:
                    db.execute(
                        (
                            "UPDATE stats SET gold=gold-%s "
                            "WHERE id=%s AND gold>=%s RETURNING gold",
                        ),
                        (amount * price, offeree, amount * price),
                    )
                    row = db.fetchone()
                    if not row:
                        return error(400, "Buyer doesn't have enough money")

                    db.execute(
                        "UPDATE stats SET gold=gold+%s WHERE id=%s RETURNING gold",
                        (amount * price, offerer),
                    )
                    if db.fetchone() is None:
                        raise Exception("Failed to credit seller")
                except Exception as exc:
                    _report_trade_error(
                        "accept_trade: transactional sell failed",
                        exc=exc,
                        extra={
                            "user_id": cId,
                            "trade_id": trade_id,
                            "trade_type": trade_type,
                            "offerer": offerer,
                            "offeree": offeree,
                            "resource": resource,
                            "amount": amount,
                            "price": price,
                        },
                    )
                    return error(400, "Trade acceptance failed")

            elif trade_type == "buy":
                # Seller gives resource to buyer first; if that fails we bail
                try:
                    gr_ret = give_resource(offeree, offerer, resource, amount)
                except Exception as exc:
                    _report_trade_error(
                        "accept_trade: give_resource raised exception during buy",
                        exc=exc,
                        extra={
                            "user_id": cId,
                            "trade_id": trade_id,
                            "trade_type": trade_type,
                            "offerer": offerer,
                            "offeree": offeree,
                            "resource": resource,
                            "amount": amount,
                            "price": price,
                        },
                    )
                    return error(400, "Trade acceptance failed")
                if gr_ret is not True:
                    return error(400, gr_ret or "Trade acceptance failed")

                # Credit seller gold from escrow (buyer funds were removed at posting)
                try:
                    db.execute(
                        "UPDATE stats SET gold=gold+%s WHERE id=%s RETURNING gold",
                        (amount * price, offeree),
                    )
                    if db.fetchone() is None:
                        raise Exception("Failed to credit seller")
                except Exception as exc:
                    _report_trade_error(
                        "accept_trade: transactional buy failed",
                        exc=exc,
                        extra={
                            "user_id": cId,
                            "trade_id": trade_id,
                            "trade_type": trade_type,
                            "offerer": offerer,
                            "offeree": offeree,
                            "resource": resource,
                            "amount": amount,
                            "price": price,
                        },
                    )
                    return error(400, "Trade acceptance failed")
        finally:
            # Release advisory lock if we acquired it
            if lock_acquired:
                try:
                    db.execute("SELECT pg_advisory_unlock(%s)", (int(trade_id),))
                except Exception:
                    # Best-effort: ignore unlock errors
                    pass

        # Remove the trade now that the transfer has succeeded
        try:
            db.execute("DELETE FROM trades WHERE offer_id=(%s)", (trade_id,))
        except Exception:
            pass

        # Invalidate caches so UI shows fresh resource/gold values
        try:
            invalidate_user_cache(offerer)
            invalidate_user_cache(offeree)
        except Exception:
            pass

    return redirect("/my_offers")


@login_required
def transfer(transferee):
    cId = session["user_id"]

    with get_db_connection() as connection:
        db = connection.cursor()

        resource = request.form.get("resource")

        amount_str = request.form.get("amount")
        if not amount_str:
            return error(400, "Amount is required")
        try:
            amount = int(amount_str)
        except (ValueError, TypeError):
            return error(400, "Amount must be a valid number")

        # DEFINITIONS

        # user - the user transferring the resource, whose id is 'cId'
        # transferee - the user upon whom the resource is transferred

        ###################

        # List of all the resources in the game
        resources = variables.RESOURCES

        if resource not in resources and resource not in [
            "gold",
            "money",
        ]:  # Checks if the resource the user selected actually exists
            return error(400, "No such resource")

        if amount < 1:
            return error(400, "Amount cannot be less than 1")

        if resource in ["gold", "money"]:
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
            user_money = db.fetchone()[0]

            if amount > user_money:
                return error(400, "You don't have enough money.")

            # Removes the money from the user
            db.execute("UPDATE stats SET gold=gold-%s WHERE id=(%s)", (amount, cId))

            # Gives the money to the transferee
            db.execute(
                "UPDATE stats SET gold=gold+%s WHERE id=%s", (amount, transferee)
            )

        else:
            user_resource_statement = (
                f"SELECT {resource} FROM resources " + "WHERE id=%s"
            )
            db.execute(user_resource_statement, (cId,))
            user_resource = int(db.fetchone()[0])

            if amount > user_resource:
                return error(400, "You don't have enough resources.")

            # Calculates the amount of resource the user should have
            new_user_resource_amount = user_resource - amount

            # Removes the resource from the user
            user_resource_update_statement = (
                f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
            )
            db.execute(user_resource_update_statement, (new_user_resource_amount, cId))

            # Sees how much of the resource the transferee has
            transferee_resource_statement = (
                f"SELECT {resource} FROM resources " + "WHERE id=%s"
            )
            db.execute(transferee_resource_statement, (transferee,))
            transferee_resource = int(db.fetchone()[0])

            # Calculates the amount of resource the transferee should have
            new_transferee_resource_amount = amount + transferee_resource

            # Gives the resource to the transferee
            transferee_update_statement = (
                f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
            )
            db.execute(
                transferee_update_statement,
                (new_transferee_resource_amount, transferee),
            )

        # Invalidate caches for both the sender and recipient so the UI sees
        # fresh resource totals immediately (non-fatal if this fails).
        try:
            invalidate_user_cache(cId)
            invalidate_user_cache(transferee)
        except Exception:
            pass

    return redirect(f"/country/id={transferee}")


def register_market_routes(app_instance):
    """Register all market routes with the Flask app instance"""
    from database import cache_response

    # Market page with caching for GET requests (30 second TTL)
    app_instance.add_url_rule(
        "/market",
        "market",
        cache_response(ttl_seconds=30)(market),
        methods=["GET", "POST"],
    )
    app_instance.add_url_rule(
        "/buy_offer/<offer_id>", "buy_offer", buy_market_offer, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/sell_offer/<offer_id>", "sell_offer", sell_market_offer, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/marketoffer/", "marketoffer", marketoffer, methods=["GET", "POST"]
    )
    app_instance.add_url_rule(
        "/post_offer/<offer_type>", "post_offer", post_offer, methods=["POST"]
    )
    # My offers page with caching (15 second TTL)
    app_instance.add_url_rule(
        "/my_offers",
        "my_offers",
        cache_response(ttl_seconds=15)(my_offers),
        methods=["GET"],
    )
    app_instance.add_url_rule(
        "/delete_offer/<offer_id>", "delete_offer", delete_offer, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/post_trade_offer/<offer_type>/<offeree_id>",
        "post_trade_offer",
        trade_offer,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/decline_trade/<trade_id>", "decline_trade", decline_trade, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/accept_trade/<trade_id>", "accept_trade", accept_trade, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/transfer/<transferee>", "transfer", transfer, methods=["POST"]
    )
