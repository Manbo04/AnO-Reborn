"""Synthetic render context for templates/province_v2.html (no database)."""
from collections import defaultdict


def province_context(location="Jungle", own=True, upgrades=None, units=None, **over):
    prov = {
        "id": 252, "name": "Test Province", "own": own, "can_plan_builds": own,
        "shared_build_access": False, "location": location, "owner_id": 16,
        "population": 34_994_538, "happiness": 0, "productivity": 100, "pollution": 100,
        "consumer_spending": 50, "land": 20, "citycount": 5, "free_land": 10000, "free_cityCount": 9995,
        "pop_working": 19_896_074, "pop_children": 2_178_943, "pop_elderly": 12_919_521,
        "growth_rate": -91_113, "has_image": False, "has_flag": False,
        "image_url": "/province-image/252", "flag_url": "", "edu_none": 5, "edu_highschool": 0, "edu_college": 0,
        "tax_estimate": 1,
    }
    prov.update(over.pop("province", {}))
    ctx = dict(
        iron_dome={"count": 0, "max": 10, "gold": 250000, "resources": {"components": 6}, "star_wars": False} if own else None,
        gold_policy_mult=1.0, province=prov, stat_breakdown={k: {"current": 50, "projected": 48, "net": -2, "sources": []} for k in ("happiness", "pollution", "productivity", "consumer_spending")},
        pop_cap_info=defaultdict(int), other_mines=[], distribution_status=None, population=36_591_679,
        food_score=1, units=defaultdict(int, units or {}), jobs_here=960000, enough_consumer_goods=True,
        enough_rations=True, has_power=True, energy={"production": 12, "consumption": 3, "net": 9, "theoretical_production": 12, "production_multiplier": 1.0, "productivity_pct": 100, "efficiency_multiplier": 1.0, "production_breakdown": [], "consumption_breakdown": []},
        infra=defaultdict(float), upgrades=defaultdict(bool, upgrades or {}), prices=defaultdict(int),
        new_infra=defaultdict(dict), normalized_buildings=[{"building_id": 1, "display_name": "Farms", "cost_display": "Farms cost $1 each"}],
        distribution_capacity=None, nation_distribution=None, cg_distribution_capacity=None, cg_status=None,
        industry_bonus={}, province_base_layout=None, province_count=2, province_rename_cost=1000,
        education_stats=defaultdict(int), FEATURE_PROVINCE_BASE_VIEW=False,
    )
    ctx.update(over)
    return ctx


def render(template_source=None, name="province_v2.html", **kw):
    import app as application_module

    app = application_module.app
    ctx = province_context(**kw)
    with app.test_request_context("/province/252"):
        from flask import session
        session["user_id"] = 16
        tpl = app.jinja_env.from_string(template_source) if template_source else app.jinja_env.get_template(name)
        # Render only the page body (the layout needs request-scoped DB data).
        return "".join(tpl.blocks["body"](tpl.new_context(ctx)))
