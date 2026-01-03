from app import app
from helpers import login_required, error
from database import get_db_cursor, fetchone_first
import psycopg2
from flask import request, render_template, session, redirect, flash
import os
import variables


# TODO: implement connection passing here.
def give_resource(giver_id, taker_id, resource, amount):
    # If giver_id is bank, don't remove any resources from anyone
    # If taker_id is bank, just remove the resources from the player

    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

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
            db.execute("SELECT gold FROM stats WHERE id=%s", (giver_id,))
            current_giver_money = fetchone_first(db, 0)

            if current_giver_money < amount:
                return "Giver doesn't have enough resources to transfer such amount."

            db.execute("UPDATE stats SET gold=gold-%s WHERE id=%s", (amount, giver_id))

        if taker_id != "bank":
            db.execute("UPDATE stats SET gold=gold+%s WHERE id=%s", (amount, taker_id))

    else:
        if giver_id != "bank":
            current_resource_statement = (
                f"SELECT {resource} FROM resources WHERE " + "id=%s"
            )
            db.execute(current_resource_statement, (giver_id,))
            current_giver_resource = fetchone_first(db, 0)

            if current_giver_resource < amount:
                return "Giver doesn't have enough resources to transfer such amount."

            giver_update_statement = (
                f"UPDATE resources SET {resource}={resource}-{amount}" + " WHERE id=%s"
            )
            db.execute(giver_update_statement, (giver_id,))

        if taker_id != "bank":
            taker_update_statement = (
                f"UPDATE resources SET {resource}={resource}+{amount}" + " WHERE id=%s"
            )
            db.execute(taker_update_statement, (taker_id,))

    conn.commit()
    conn.close()

    return True


@app.route("/market", methods=["GET", "POST"])
@login_required
def market():
    if request.method == "GET":
        # Connection
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()
        cId = session["user_id"]

        # GET Query Parameters
        try:
            filter_resource = request.values.get("filtered_resource")
        except TypeError:
            filter_resource = None

        # Pagination
        try:
            page = int(request.values.get("page", 1))
            if page < 1:
                page = 1
        except (TypeError, ValueError):
            page = 1

        per_page = 50  # Show 50 offers per page
        offset = (page - 1) * per_page

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

        if offer_type is not None and price_type is None:
            db.execute("SELECT offer_id FROM offers WHERE type=(%s)", (offer_type,))
            _ = db.fetchall()

        elif offer_type is None and price_type is not None:
            offer_ids_statement = (
                f"SELECT offer_id FROM offers ORDER BY price {price_type}"
            )
            db.execute(offer_ids_statement)
            _ = db.fetchall()

        elif offer_type is not None and price_type is not None:
            offer_ids_statement = (
                "SELECT offer_id FROM offers WHERE type=%s"
                + f"ORDER by price {price_type}"
            )
            db.execute(offer_ids_statement, (offer_type,))
            _ = db.fetchall()

        elif offer_type is None and price_type is None:
            db.execute("SELECT offer_id FROM offers ORDER BY price ASC")
            _ = db.fetchall()

        if filter_resource is not None:
            resources_list = variables.RESOURCES

            if (
                filter_resource not in resources_list
            ):  # Checks if the resource the user selected actually exists
                return error(400, "No such resource")

        # Use JOIN query instead of loop to fetch all data at once
        # Add pagination with LIMIT and OFFSET
        if filter_resource is not None:
            # Get total count for pagination
            db.execute("SELECT COUNT(*) FROM offers WHERE resource = %s", (filter_resource,))
            total_offers = fetchone_first(db, 0)

            query = """
                SELECT o.user_id, o.type, o.resource, o.amount, o.price, o.offer_id, u.username
                FROM offers o
                INNER JOIN users u ON o.user_id = u.id
                WHERE o.resource = %s
                ORDER BY o.price ASC
                LIMIT %s OFFSET %s
            """
            params = (filter_resource, per_page, offset)
        elif offer_type is not None and price_type is not None:
            # Get total count for pagination
            db.execute("SELECT COUNT(*) FROM offers WHERE type = %s", (offer_type,))
            total_offers = fetchone_first(db, 0)

            query = """
                SELECT o.user_id, o.type, o.resource, o.amount, o.price, o.offer_id, u.username
                FROM offers o
                INNER JOIN users u ON o.user_id = u.id
                WHERE o.type = %s
                ORDER BY o.price """ + ("ASC" if price_type == "ascending" else "DESC") + """
                LIMIT %s OFFSET %s
            """
            params = (offer_type, per_page, offset)
        elif offer_type is not None:
            # Get total count for pagination
            db.execute("SELECT COUNT(*) FROM offers WHERE type = %s", (offer_type,))
            total_offers = fetchone_first(db, 0)

            query = """
                SELECT o.user_id, o.type, o.resource, o.amount, o.price, o.offer_id, u.username
                FROM offers o
                INNER JOIN users u ON o.user_id = u.id
                WHERE o.type = %s
                ORDER BY o.price ASC
                LIMIT %s OFFSET %s
            """
            params = (offer_type, per_page, offset)
        else:
            # Get total count for pagination
            db.execute("SELECT COUNT(*) FROM offers")
            total_offers = fetchone_first(db, 0)

            query = """
                SELECT o.user_id, o.type, o.resource, o.amount, o.price, o.offer_id, u.username
                FROM offers o
                INNER JOIN users u ON o.user_id = u.id
                ORDER BY o.price ASC
                LIMIT %s OFFSET %s
            """
            params = (per_page, offset)

        if params:
            db.execute(query, params)
        else:
            db.execute(query)

        offers_data = db.fetchall()

        # Calculate pagination data
        total_pages = (total_offers + per_page - 1) // per_page  # Ceiling division
        has_prev = page > 1
        has_next = page < total_pages

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
            offer_type,
            resource,
            amount,
            price,
            offer_id,
            username,
        ) in offers_data:
            ids.append(user_id)
            types.append(offer_type)
            resources.append(resource)
            amounts.append(amount)
            prices.append(price)
            total_prices.append(price * amount)
            offer_ids.append(offer_id)
            names.append(username)

        connection.close()  # Closes the connection

        offers = zip(
            ids, types, names, resources, amounts, prices, offer_ids, total_prices
        )  # Zips everything into 1 list

        return render_template(
            "market.html",
            offers=offers,
            price_type=price_type,
            cId=cId,
            page=page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            total_offers=total_offers
        )


@app.route("/buy_offer/<offer_id>", methods=["POST"])
@login_required
def buy_market_offer(offer_id):
    connection = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = connection.cursor()

    cId = session["user_id"]
    # Guard against missing or invalid form input
    amt_raw = request.form.get(f"amount_{offer_id}")
    if not amt_raw:
        return error(400, "Missing amount")
    try:
        amount_wanted = int(amt_raw.replace(",", ""))
    except ValueError:
        return error(400, "Invalid amount")

    db.execute(
        "SELECT resource, amount, price, user_id FROM offers WHERE offer_id=(%s)",
        (offer_id,),
    )
    _row = db.fetchone()
    if not _row:
        return error(404, "Offer not found")
    resource, total_amount, price_for_one, seller_id = _row

    if amount_wanted < 1:
        return error(400, "Amount cannot be less than 1")

    if amount_wanted > total_amount:
        return error(400, "Amount wanted cant be higher than total amount")

    db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
    from database import fetchone_first

    buyers_gold = int(fetchone_first(db, 0))

    total_price = amount_wanted * price_for_one

    if total_price > buyers_gold:  # Checks if buyer doesnt have enough gold for buyin
        return error(400, "You don't have enough money.")  # Returns error if true

    give_resource("bank", cId, resource, amount_wanted)  # Gives the resource
    give_resource(cId, seller_id, "money", total_price)  # Gives the money

    new_offer_amount = total_amount - amount_wanted

    if new_offer_amount == 0:
        db.execute("DELETE FROM offers WHERE offer_id=(%s)", (offer_id,))
    else:
        db.execute(
            "UPDATE offers SET amount=(%s) WHERE offer_id=(%s)",
            (new_offer_amount, offer_id),
        )

    connection.commit()  # Commits the connection
    connection.close()  # Closes the connection

    return redirect("/market")


@app.route("/sell_offer/<offer_id>", methods=["POST"])
@login_required
def sell_market_offer(offer_id):
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = conn.cursor()

    seller_id = session["user_id"]
    amount_wanted = int(request.form.get(f"amount_{offer_id}"))

    if not offer_id.isnumeric():
        return error(400, "Values must be numeric")

    db.execute(
        "SELECT resource, amount, price, user_id FROM offers WHERE offer_id=(%s)",
        (offer_id,),
    )
    row = db.fetchone()
    if not row:
        return error(404, "Offer not found")
    resource, total_amount, price_for_one, buyer_id = row

    # Sees how much of the resource the seller has
    resource_statement = f"SELECT {resource} FROM resources " + "WHERE id=%s"
    db.execute(resource_statement, (seller_id,))
    sellers_resource = fetchone_first(db, 0)

    if amount_wanted < 1:
        return error(400, "Amount cannot be less than 1")

    if amount_wanted > total_amount:
        return error(
            400,
            "The amount of resources you're selling is higher than what the buyer wants",
        )

    # Checks if it's less than what the seller wants to sell
    if sellers_resource < amount_wanted:
        return error(400, "You don't have enough of that resource")

    # Removes the resource from the seller and gives it to the buyer
    give_resource(seller_id, buyer_id, resource, amount_wanted)

    # Takes away the money used for buying from the buyer and gives it to the seller
    give_resource(buyer_id, seller_id, "money", price_for_one * amount_wanted)

    # Generates the new amount, after the buyer has got his resources from the seller
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

    conn.commit()
    conn.close()

    return redirect("/market")


@app.route("/marketoffer/", methods=["GET"])
@login_required
def marketoffer():
    return render_template("marketoffer.html")


@app.route("/post_offer/<offer_type>", methods=["POST"])
@login_required
def post_offer(offer_type):
    import uuid

    cId = session["user_id"]

    # Guard the entire handler so unexpected exceptions are logged with a
    # short reference id for postmortem, and connections are closed.
    uid = uuid.uuid4().hex[:12]
    try:
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()

        resource = request.form.get("resource")
        # Validate numeric inputs early and return helpful errors instead of
        # letting a ValueError bubble up and produce a 500/502 in production.
        try:
            amount_raw = request.form.get("amount")
            amount = int(amount_raw)
        except Exception:
            return ("Invalid amount", 400)

        price_raw = request.form.get("price")
        try:
            price = int(price_raw)
        except Exception:
            return ("Invalid price", 400)

        # List of all the resources in the game
        resources = variables.RESOURCES

        offer_types = ["buy", "sell"]
        if offer_type not in offer_types:
            return ("Offer type must be 'buy' or 'sell'", 400)

        if (
            resource not in resources
        ):  # Checks if the resource the user selected actually exists
            return ("No such resource", 400)

        if amount < 1:  # Checks if the amount is negative
            return ("Amount must be greater than 0", 400)

        if offer_type == "sell":
            rStatement = f"SELECT {resource} FROM resources " + "WHERE id=%s"
            db.execute(rStatement, (cId,))
            from database import fetchone_first

            # `fetchone_first` returns a safe default when the SELECT yields no
            # rows — avoid indexing into None.
            realAmount = int(fetchone_first(db, 0) or 0)

            if amount > realAmount:  # Checks if user wants to sell more than he has
                return ("Selling amount is higher than the amount you have.", 400)

            # Calculates the resource amount the seller should have
            give_resource(cId, "bank", resource, amount)

            # Creates a new offer
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) VALUES (%s, %s, %s, %s, %s)",
                (cId, offer_type, resource, int(amount), int(price)),
            )

        elif offer_type == "buy":
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) VALUES (%s, %s, %s, %s, %s)",
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
        current_money = int(fetchone_first(db, 0) or 0)

        if current_money < money_to_take_away:
            return error(400, "You don't have enough money.")

        give_resource(cId, "bank", "money", money_to_take_away)

        connection.commit()
        connection.close()
        return redirect("/market")
    except Exception as e:
        # Log the exception with an id the user can provide for debugging.
        app.logger.exception(f"post_offer error ({uid}): {e}")
        try:
            connection.close()
        except Exception:
            pass
        # Return a minimal text response to avoid executing the regular error
        # template (which may touch the DB during template rendering).
        return (f"Internal Server Error. Reference id: {uid}", 500)

    connection.commit()
    flash("You just posted a market offer")
    connection.close()  # Closes the connection
    return redirect("/market")


@app.route("/my_offers", methods=["GET"])
@login_required
def my_offers():
    cId = session["user_id"]
    offers = {}
    with get_db_cursor() as db:
        db.execute(
            """
SELECT trades.offer_id, trades.price, trades.resource, trades.amount, trades.type, trades.offeree, users.username
FROM trades INNER JOIN users ON trades.offeree=users.id
WHERE trades.offerer=(%s) ORDER BY trades.offer_id ASC
""",
            (cId,),
        )
        offers["outgoing"] = db.fetchall()

        db.execute(
            """
SELECT trades.offer_id, trades.price, trades.resource, trades.amount, trades.type, trades.offerer, users.username
FROM trades INNER JOIN users ON trades.offerer=users.id
WHERE trades.offeree=(%s) ORDER BY trades.offer_id ASC
""",
            (cId,),
        )
        offers["incoming"] = db.fetchall()

        db.execute(
            "SELECT offer_id, price, resource, amount, type FROM offers WHERE user_id=(%s) ORDER BY offer_id ASC",
            (cId,),
        )
        offers["market"] = db.fetchall()

    return render_template("my_offers.html", cId=cId, offers=offers)


@app.route("/delete_offer/<offer_id>", methods=["POST"])
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


@app.route("/post_trade_offer/<offer_type>/<offeree_id>", methods=["POST"])
@login_required
def trade_offer(offer_type, offeree_id):
    if request.method == "POST":
        cId = session["user_id"]

        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()

        resource = request.form.get("resource")
        amount = int(request.form.get("amount"))
        price = int(request.form.get("price"))

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
            from database import fetchone_first

            realAmount = int(fetchone_first(db, 0))

            if amount > realAmount:  # Checks if user wants to sell more than he has
                return error("400", "Selling amount is higher the amount you have.")

            # Calculates the resource amount the seller should have
            newResourceAmount = realAmount - amount

            upStatement = f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
            db.execute(upStatement, (newResourceAmount, cId))

            # Creates a new offer
            db.execute(
                "INSERT INTO trades (offerer, type, resource, amount, price, offeree) VALUES (%s, %s, %s, %s, %s, %s)",
                (cId, offer_type, resource, amount, price, offeree_id),
            )

            connection.commit()  # Commits the data to the database

        elif offer_type == "buy":
            db.execute(
                "INSERT INTO trades (offerer, type, resource, amount, price, offeree) VALUES (%s, %s, %s, %s, %s, %s)",
                (cId, offer_type, resource, amount, price, offeree_id),
            )

            money_to_take_away = amount * price
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
            current_money = fetchone_first(db, 0)
            if current_money < money_to_take_away:
                return error(400, "You don't have enough money.")
            new_money = current_money - money_to_take_away

            db.execute("UPDATE stats SET gold=(%s) WHERE id=(%s)", (new_money, cId))

            flash("You just posted a market offer")

            connection.commit()

        connection.close()  # Closes the connection
        return redirect(f"/country/id={offeree_id}")


@app.route("/decline_trade/<trade_id>", methods=["POST"])
@login_required
def decline_trade(trade_id):
    if not trade_id.isnumeric():
        return error(400, "Trade id must be numeric")

    cId = session["user_id"]

    connection = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = connection.cursor()

    db.execute(
        "SELECT offeree, offerer, type, resource, amount, price FROM trades WHERE offer_id=(%s)",
        (trade_id,),
    )
    offeree, offerer, type, resource, amount, price = db.fetchone()

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

    connection.commit()
    connection.close()

    return redirect("/my_offers")


@app.route("/accept_trade/<trade_id>", methods=["POST"])
@login_required
def accept_trade(trade_id):
    cId = session["user_id"]

    connection = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = connection.cursor()

    db.execute(
        "SELECT offeree, type, offerer, resource, amount, price FROM trades WHERE offer_id=(%s)",
        (trade_id,),
    )
    offeree, trade_type, offerer, resource, amount, price = db.fetchone()

    if offeree != cId:
        return error(400, "You can't accept that offer")

    if trade_type == "sell":
        give_resource(offeree, offerer, "money", amount * price)
        give_resource(offerer, offeree, resource, amount)
    elif trade_type == "buy":
        give_resource(offerer, offeree, "money", amount * price)
        give_resource(offeree, offerer, resource, amount)

    db.execute("DELETE FROM trades WHERE offer_id=(%s)", (trade_id,))

    connection.commit()
    connection.close()
    return redirect("/my_offers")


@app.route("/transfer/<transferee>", methods=["POST"])
@login_required
def transfer(transferee):
    cId = session["user_id"]

    connection = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = connection.cursor()

    resource = request.form.get("resource")
    amount = int(request.form.get("amount"))

    ### DEFINITIONS ###

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
        from database import fetchone_first

        user_money = fetchone_first(db, 0)

        if amount > user_money:
            return error(400, "You don't have enough money.")

        # Removes the money from the user
        db.execute("UPDATE stats SET gold=gold-%s WHERE id=(%s)", (amount, cId))

        # Gives the money to the transferee
        db.execute("UPDATE stats SET gold=gold+%s WHERE id=%s", (amount, transferee))

    else:
        user_resource_statement = f"SELECT {resource} FROM resources " + "WHERE id=%s"
        db.execute(user_resource_statement, (cId,))
        user_resource = int(fetchone_first(db, 0))

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
        transferee_resource = int(fetchone_first(db, 0))

        # Calculates the amount of resource the transferee should have
        new_transferee_resource_amount = amount + transferee_resource

        # Gives the resource to the transferee
        transferee_update_statement = (
            f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
        )
        db.execute(
            transferee_update_statement, (new_transferee_resource_amount, transferee)
        )

    connection.commit()
    connection.close()

    return redirect(f"/country/id={transferee}")
