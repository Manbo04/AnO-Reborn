from flask import Blueprint, render_template, session, redirect, request
from helpers import login_required, error, is_theme_v2_enabled
from database import (
    get_request_cursor,
    query_cache,
    invalidate_user_cache,
    invalidate_view_cache,
    reuse_or_new_cursor,
)
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
    "integratedsteelmaking": "integrated_steelmaking",
    "electricarcfurnace": "electric_arc_furnace",
}

TECH_TO_LEGACY_UPGRADE = {v: k for k, v in LEGACY_UPGRADE_TO_TECH.items()}


def get_upgrades(cId, db=None):
    # Check cache first
    cache_key = f"upgrades_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with reuse_or_new_cursor(db) as db:
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

    with get_request_cursor() as db:
        db.execute(
            """
            SELECT tech_id, display_name, research_cost, prerequisite_tech_id, name, description
            FROM tech_dictionary
            WHERE is_active = TRUE
            ORDER BY display_name ASC
            """
        )
        tech_rows = db.fetchall() or []

        # Build legacy_key → research_cost / prerequisite display-name
        # mappings for template cards. Players had no way to see a tech's
        # prerequisite before attempting to research it and hitting a
        # generic error -- surface it up front instead.
        tech_id_to_display_name = {row[0]: row[1] for row in tech_rows}
        tech_costs = {}
        tech_prereq_names = {}
        for row in tech_rows:
            tech_id, display_name, research_cost, prerequisite_tech_id, tech_name, description = row
            legacy_key = TECH_TO_LEGACY_UPGRADE.get(tech_name)
            if not legacy_key:
                continue
            tech_costs[legacy_key] = int(research_cost)
            if prerequisite_tech_id:
                tech_prereq_names[legacy_key] = tech_id_to_display_name.get(
                    prerequisite_tech_id, "an earlier technology"
                )

        db.execute(
            """
            SELECT tech_id
            FROM user_tech
            WHERE user_id=%s AND is_unlocked=TRUE
            """,
            (cId,),
        )
        unlocked_ids = {row[0] for row in db.fetchall()}

    template = "upgrades_v2.html" if is_theme_v2_enabled("upgrades") else "upgrades.html"
    return render_template(
        template,
        upgrades=upgrades,
        tech_rows=tech_rows,
        unlocked_ids=unlocked_ids,
        research_cost_resource=RESEARCH_COST_RESOURCE,
        tech_costs=tech_costs,
        tech_prereq_names=tech_prereq_names,
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
        invalidate_view_cache("military", user_id=cId)
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

    with get_request_cursor() as db:
        cId = session["user_id"]
        # tech_dictionary has had duplicate rows under the same `name` in
        # production (one active, one not) -- an unqualified lookup could
        # nondeterministically grab the inactive one and fail with "not
        # currently available" even though /upgrades shows the tech as
        # researchable (that page's query already filters is_active=TRUE).
        # Prefer the active row explicitly, and pick deterministically if
        # duplicates still exist.
        db.execute(
            "SELECT tech_id FROM tech_dictionary WHERE name=%s "
            "ORDER BY is_active DESC, tech_id DESC LIMIT 1",
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
        invalidate_view_cache("military", user_id=cId)
    except Exception:
        pass

    return redirect("/upgrades")
