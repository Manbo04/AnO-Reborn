from flask import Blueprint, render_template, session, redirect, request
from helpers import login_required, error
from database import get_db_cursor, query_cache, invalidate_user_cache
from action_loop import start_research, ActionLoopError, RESEARCH_COST_RESOURCE

# Game.ping() # temporarily removed this line because it might make celery not work
from dotenv import load_dotenv

load_dotenv()

try:
    bp = Blueprint("upgrades", __name__)
except Exception:
    # In Celery worker context, Blueprint may fail
    bp = None

LEGACY_UPGRADE_TO_TECH = {
    "betterengineering": "better_engineering",
    "cheapermaterials": "cheaper_materials",
    "onlineshopping": "online_shopping",
    "governmentregulation": "government_regulation",
    "nationalhealthinstitution": "national_health_institution",
    "highspeedrail": "high_speed_rail",
    "advancedmachinery": "advanced_machinery",
    "strongerexplosives": "stronger_explosives",
    "widespreadpropaganda": "widespread_propaganda",
    "increasedfunding": "increased_funding",
    "automationintegration": "automation_integration",
    "largerforges": "larger_forges",
    "lootingteams": "looting_teams",
    "organizedsupplylines": "organized_supply_lines",
    "largestorehouses": "large_storehouses",
    "ballisticmissilesilo": "ballistic_missile_silo",
    "icbmsilo": "icbm_silo",
    "nucleartestingfacility": "nuclear_testing_facility",
}

TECH_TO_LEGACY_UPGRADE = {v: k for k, v in LEGACY_UPGRADE_TO_TECH.items()}


def get_upgrades(cId):
    # Check cache first
    cache_key = f"upgrades_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as db:
        result = {key: False for key in LEGACY_UPGRADE_TO_TECH.keys()}

        db.execute(
            """
            SELECT td.name
            FROM user_tech ut
            JOIN tech_dictionary td ON td.tech_id = ut.tech_id
            WHERE ut.user_id=%s AND ut.is_unlocked=TRUE
            """,
            (cId,),
        )
        for (tech_name,) in db.fetchall():
            legacy_key = TECH_TO_LEGACY_UPGRADE.get(tech_name)
            if legacy_key:
                result[legacy_key] = True

        # Cache for 5 minutes
        query_cache.set(cache_key, result)
        return result


@bp.route("/upgrades", methods=["GET"])
@login_required
def upgrades():
    cId = session["user_id"]
    upgrades = get_upgrades(cId)  # already a dict keyed by column name

    with get_db_cursor() as db:
        db.execute(
            """
            SELECT tech_id, display_name, research_cost, prerequisite_tech_id
            FROM tech_dictionary
            WHERE is_active = TRUE
            ORDER BY display_name ASC
            """
        )
        tech_rows = db.fetchall() or []

        db.execute(
            """
            SELECT tech_id
            FROM user_tech
            WHERE user_id=%s AND is_unlocked=TRUE
            """,
            (cId,),
        )
        unlocked_ids = {row[0] for row in db.fetchall()}

    return render_template(
        "upgrades.html",
        upgrades=upgrades,
        tech_rows=tech_rows,
        unlocked_ids=unlocked_ids,
        research_cost_resource=RESEARCH_COST_RESOURCE,
    )


@bp.route("/start_research", methods=["POST"])
@login_required
def start_research_action():
    cId = session["user_id"]
    try:
        tech_id = int(request.form.get("tech_id", "0"))
    except (TypeError, ValueError):
        return error(400, "Invalid technology selection.")

    try:
        start_research(cId, tech_id)
    except ActionLoopError as e:
        return error(400, str(e))

    try:
        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"upgrades_{cId}")
    except Exception:
        pass

    return redirect("/upgrades")


@bp.route("/upgrades_sb/<ttype>/<thing>", methods=["POST"])
@login_required
def upgrade_sell_buy(ttype, thing):
    thing_key = thing.lower()
    tech_name = LEGACY_UPGRADE_TO_TECH.get(thing_key)
    if not tech_name:
        return error(400, f"Upgrade type '{thing}' does not exist.")

    if ttype != "buy":
        return error(400, "Selling upgrades is no longer supported.")

    with get_db_cursor() as db:
        cId = session["user_id"]
        db.execute(
            "SELECT tech_id FROM tech_dictionary WHERE name=%s",
            (tech_name,),
        )
        row = db.fetchone()
        if not row:
            return error(400, "Technology definition not found.")
        tech_id = row[0]

    try:
        start_research(cId, tech_id)
    except ActionLoopError as e:
        return error(400, str(e))

    try:
        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"upgrades_{cId}")
    except Exception:
        pass

    return redirect("/upgrades")
