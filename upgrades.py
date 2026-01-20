from flask import Blueprint, render_template, session, redirect
from helpers import login_required, error
from database import get_db_cursor, query_cache

# Game.ping() # temporarily removed this line because it might make celery not work
from dotenv import load_dotenv

load_dotenv()

bp = Blueprint("upgrades", __name__)


def get_upgrades(cId):
    # Check cache first
    cache_key = f"upgrades_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as db:
        db.execute("SELECT * FROM upgrades WHERE user_id=%s", (cId,))
        row = db.fetchone()
        if not row:
            result = {}
        else:
            colnames = [desc[0] for desc in db.description]
            result = dict(zip(colnames, row))

        # Cache for 5 minutes
        query_cache.set(cache_key, result)
        return result


@bp.route("/upgrades", methods=["GET"])
@login_required
def upgrades():
    cId = session["user_id"]
    upgrades = get_upgrades(cId)  # already a dict keyed by column name
    return render_template("upgrades.html", upgrades=upgrades)


@bp.route("/upgrades_sb/<ttype>/<thing>", methods=["POST"])
@login_required
def upgrade_sell_buy(ttype, thing):
    prices = {
        "betterengineering": {
            "money": 254000000,
            "resources": {"steel": 500, "aluminium": 420},
        },
        "cheapermaterials": {"money": 22000000, "resources": {"lumber": 220}},
        "onlineshopping": {
            "money": 184000000,
            "resources": {"steel": 600, "aluminium": 450, "lumber": 800},
        },
        "governmentregulation": {
            "money": 112000000,
            "resources": {"steel": 980, "aluminium": 750},
        },
        "nationalhealthinstitution": {
            "money": 95000000,
            "resources": {"steel": 320, "aluminium": 80, "lumber": 675},
        },
        "highspeedrail": {
            "money": 220000000,
            "resources": {"steel": 1350, "aluminium": 450},
        },
        "advancedmachinery": {
            "money": 180000000,
            "resources": {"steel": 1400, "aluminium": 320, "lumber": 850},
        },
        "strongerexplosives": {"money": 65000000, "resources": {}},
        "widespreadpropaganda": {"money": 150000000, "resources": {}},
        "increasedfunding": {
            "money": 225000000,
            "resources": {"steel": 950, "aluminium": 450},
        },
        "automationintegration": {
            "money": 420000000,
            "resources": {"steel": 2200, "aluminium": 1150},
        },
        "largerforges": {
            "money": 320000000,
            "resources": {"steel": 1850, "aluminium": 650},
        },
        "lootingteams": {
            "money": 140000000,
            "resources": {"steel": 800, "aluminium": 350},
        },
        "organizedsupplylines": {
            "money": 200000000,
            "resources": {"steel": 1100, "aluminium": 550},
        },
        "largestorehouses": {
            "money": 315000000,
            "resources": {"steel": 1600, "aluminium": 900},
        },
        "ballisticmissilesilo": {
            "money": 280000000,
            "resources": {"steel": 1200, "aluminium": 450},
        },
        "icbmsilo": {
            "money": 355000000,
            "resources": {"steel": 1550, "aluminium": 700},
        },
        "nucleartestingfacility": {
            "money": 575000000,
            "resources": {"steel": 2250, "aluminium": 1050},
        },
    }

    thing_key = thing.lower()
    if thing_key not in prices:
        return error(400, f"Upgrade type '{thing}' does not exist.")

    money = prices[thing_key]["money"]
    resources = prices[thing_key]["resources"]

    with get_db_cursor() as db:
        cId = session["user_id"]

        if ttype == "buy":
            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            current_gold = db.fetchone()[0]

            if current_gold < money:
                return error(400, f"You don't have enough money to buy this upgrade.")

            for resource, amount in resources.items():
                db.execute(f"SELECT {resource} FROM resources WHERE id=%s", (cId,))
                current_amount = db.fetchone()[0]
                if current_amount < amount:
                    return error(
                        400,
                        f"You don't have enough {resource.upper()} to buy this upgrade.",
                    )

            db.execute(
                "UPDATE stats SET gold=gold-%s WHERE id=%s",
                (
                    money,
                    cId,
                ),
            )
            for resource, amount in resources.items():
                db.execute(
                    f"UPDATE resources SET {resource}={resource}-%s WHERE id=%s",
                    (
                        amount,
                        cId,
                    ),
                )
            db.execute(f"UPDATE upgrades SET {thing_key}=1 WHERE user_id=%s", (cId,))

        elif ttype == "sell":
            db.execute("UPDATE stats SET gold=gold+%s WHERE id=%s", (money, cId))
            for resource, amount in resources.items():
                db.execute(
                    f"UPDATE resources SET {resource}={resource}+%s WHERE id=%s",
                    (
                        amount,
                        cId,
                    ),
                )
            db.execute(f"UPDATE upgrades SET {thing_key}=0 WHERE user_id=%s", (cId,))

    return redirect("/upgrades")
