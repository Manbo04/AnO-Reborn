from flask import Blueprint, render_template, session, redirect, request

from helpers import login_required, error, is_theme_v2_enabled
from database import get_request_cursor
from action_loop import start_research, ActionLoopError, RESEARCH_COST_RESOURCE

from .repositories import LEGACY_UPGRADE_TO_TECH, get_active_tech_id_by_name
from .services import get_upgrades, build_upgrades_page_data, invalidate_upgrade_caches

try:
    bp = Blueprint("upgrades", __name__)
except Exception:
    # In Celery worker context, Blueprint may fail
    bp = None


@bp.route("/upgrades", methods=["GET"])
@login_required
def upgrades():
    cId = session["user_id"]
    upgrades = get_upgrades(cId)  # already a dict keyed by column name

    with get_request_cursor() as db:
        tech_rows, unlocked_ids, tech_costs, tech_prereq_names = build_upgrades_page_data(db, cId)

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

    invalidate_upgrade_caches(cId)

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
        tech_id = get_active_tech_id_by_name(db, tech_name)
        if not tech_id:
            return error(400, "Technology definition not found.")

    try:
        start_research(cId, tech_id)
    except ActionLoopError as e:
        return error(400, str(e))

    invalidate_upgrade_caches(cId)

    return redirect("/upgrades")
