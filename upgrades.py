from flask import Blueprint, render_template, session, redirect
from helpers import login_required, error
from database import get_db_cursor
import os
# Game.ping() # temporarily removed this line because it might make celery not work
from dotenv import load_dotenv
load_dotenv()

bp = Blueprint("upgrades", __name__)

def get_upgrades(cId): 
    with get_db_cursor() as db:
        db.execute("SELECT * FROM upgrades WHERE user_id=%s", (cId,))
        row = db.fetchone()
        if not row:
            return {}
        colnames = [desc[0] for desc in db.description]
        return dict(zip(colnames, row))

@bp.route("/upgrades", methods=["GET"])
@login_required
def upgrades():
    cId = session["user_id"]
    upgrades = get_upgrades(cId) # already a dict keyed by column name
    return render_template("upgrades.html", upgrades=upgrades)

@bp.route("/upgrades_sb/<ttype>/<thing>", methods=["POST"])
@login_required
def upgrade_sell_buy(ttype, thing):

    with get_db_cursor() as db:
        cId = session["user_id"]

        prices = {
            'betterEngineering': {"money": 254000000, "resources": {"steel": 500, "aluminium": 420}},
            'cheaperMaterials': {"money": 22000000, "resources": {"lumber": 220}},
            'onlineShopping': {"money": 184000000, "resources": {"steel": 600, "aluminium": 450, "lumber": 800}},
            'governmentRegulation': {"money": 112000000, "resources": {"steel": 980, "aluminium": 750}},
            'nationalHealthInstitution': {"money": 95000000, "resources": {"steel": 320, "aluminium": 80, "lumber": 675}},
            'highSpeedRail': {"money": 220000000, "resources": {"steel": 1350, "aluminium": 450}},
            'advancedMachinery': {"money": 180000000, "resources": {"steel": 1400, "aluminium": 320, "lumber": 850}},
            'strongerExplosives': {"money": 65000000, "resources": {}},
            'widespreadPropaganda': {"money": 150000000, "resources": {}},
            'increasedFunding': {"money": 225000000, "resources": {"steel": 950, "aluminium": 450}},
            'automationIntegration': {"money": 420000000, "resources": {"steel": 2200, "aluminium": 1150}},
            'largerForges': {"money": 320000000, "resources": {"steel": 1850, "aluminium": 650}},
            'lootingTeams': {"money": 140000000, "resources": {"steel": 800, "aluminium": 350}},
            'organizedSupplyLines': {"money": 200000000, "resources": {"steel": 1100, "aluminium": 550}},
            'largeStoreHouses': {"money": 315000000, "resources": {"steel": 1600, "aluminium": 900}},
            'ballisticMissileSilo': {"money": 280000000, "resources": {"steel": 1200, "aluminium": 450}},
            'ICBMsilo': {"money": 355000000, "resources": {"steel": 1550, "aluminium": 700}},
            'nuclearTestingFacility': {"money": 575000000, "resources": {"steel": 2250, "aluminium": 1050}}
        }

    if thing not in prices:
        return error(400, f"Upgrade type '{thing}' does not exist.")
    money = prices[thing]["money"]
    resources = prices[thing]["resources"]

    if ttype == "buy":
        # Removal of money for purchase and error handling
        try:
            db.execute("UPDATE stats SET gold=gold-%s WHERE id=%s", (money, cId,))
        except Exception as e:
            return error(400, f"You don't have enough money to buy this upgrade.")

        # Removal of resources for purchase and error handling
        for resource, amount in resources.items():
            try:
                resource_statement = f"UPDATE resources SET {resource}={resource}-%%s WHERE id=%%s"
                db.execute(resource_statement, (amount, cId,))
            except Exception as e:
                return error(400, f"You don't have enough {resource.upper()} to buy this upgrade.")

        upgrade_statement = f"UPDATE upgrades SET {thing}=1 WHERE user_id=%s"
        db.execute(upgrade_statement, (cId,))

    elif ttype == "sell":
        db.execute("UPDATE stats SET gold=gold+%s WHERE id=%s", (money, cId))
        for resource, amount in resources.items():
            resource_statement = f"UPDATE resources SET {resource}={resource}+%%s WHERE id=%%s"
            db.execute(resource_statement, (amount, cId,))

        upgrade_statement = f"UPDATE upgrades SET {thing}=0 WHERE user_id=%s"
        db.execute(upgrade_statement, (cId,))

    # Always reload upgrades after transaction
    return redirect("/upgrades")
