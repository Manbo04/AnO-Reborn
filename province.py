from flask import (
    Blueprint,
    request,
    render_template,
    session,
    redirect,
    jsonify,
    flash,
)
from helpers import (
    login_required,
    login_required_or_crawler_preview,
    error,
    require_post_origin,
    compress_province_image,
    province_image_url,
    is_theme_v2_enabled,
)
from dotenv import load_dotenv
import variables
from helpers import get_date
from database import (
    get_request_cursor,
    cache_response,
    invalidate_user_cache,
    provinces_has_demographics,
    provinces_has_image_data,
    rollback_db_cursor,
    row_val,
)
import os
import math
from action_loop import build_structure, ActionLoopError
from app_core.coalitions.repositories import can_manage_province_builds
from app_core.economy.tick_order import tax_due_before_next_upkeep, upkeep_budget
from app_core.economy.project_bonuses import project_output_bonus
from app_core.economy.biome_buildings import mines_for_biome, other_biome_mines
from app_core.economy.building_costs import (
    CITY_UNITS,
    LAND_UNITS,
    enrich_building_row,
    get_build_cost,
)
from app_core.economy.building_purchase import (
    BuildingPurchaseError,
    get_free_slots as economy_get_free_slots,
    purchase_building,
)
from game_ui import (
    FEATURE_PROVINCE_BASE_VIEW,
    SLOT_THEMES,
    build_province_layout_payload,
    building_visual_icon,
    get_slot_config,
)
bp = Blueprint("province", __name__)

load_dotenv()


from services.province_service import ProvinceService

@bp.route("/provinces", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)
def provinces():
    cId = session["user_id"]
    page = request.args.get('page', 1, type=int)
    
    data = ProvinceService.get_user_provinces_paginated(cId, page)

    template = "provinces_v2.html" if is_theme_v2_enabled("provinces") else "provinces.html"
    return render_template(
        template,
        provinces=data["provinces"],
        provinces_with_images=data["provinces_with_images"],
        slots_used=data.get("slots_used", {}),
        growth_rates=data.get("growth_rates", {}),
        current_page=data["current_page"],
        total_pages=data["total_pages"],
        total_count=data["total_count"],
        total_population=data["total_population"],
    )


def _province_crawler_preview(pId):
    from flask import abort, url_for
    from app_core.social_cards.routes import _fetch_province_header, render_preview_page

    data = _fetch_province_header(int(pId))
    if data is None:
        abort(404)
    title = f"{data['name']} · Affairs and Order"
    description = f"{data['name']} — {data['population']:,} population · {data['land']:,} land"
    image_url = url_for("social_cards.province_card", province_id=int(pId), _external=True)
    return render_preview_page(title, description, image_url)


@bp.route("/province/<pId>", methods=["GET"])
@login_required_or_crawler_preview(_province_crawler_preview)
@cache_response(ttl_seconds=30)  # Cache province page
def province(pId):
    from psycopg2.extras import RealDictCursor
    from database import get_request_cursor, query_cache

    cId = session["user_id"]
    
    try:
        pId = int(str(pId).replace('id=', ''))
    except ValueError:
        return "Invalid province ID", 400

    # OPTIMIZED: Single query to fetch province + infra + resources + stats
    # + upgrades - all in ONE database connection
    with get_request_cursor(cursor_factory=RealDictCursor) as db:
        # Combined query for province + stats (legacy resources/proInfra tables removed)
        image_select = (
            "(p.image_data IS NOT NULL AND p.image_data <> '') AS has_image"
            if provinces_has_image_data()
            else "FALSE AS has_image"
        )
        if provinces_has_demographics():
            province_sql = f"""
            SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
                   p.pollution, p.happiness, p.productivity, p.consumer_spending,
                   CAST(p.citycount AS INTEGER) as citycount,
                   p.land, p.energy AS electricity,
                   s.location,
                   COALESCE(p.pop_children, 0) AS pop_children,
                   COALESCE(p.pop_working, 0) AS pop_working,
                   COALESCE(p.pop_elderly, 0) AS pop_elderly,
                   COALESCE(p.edu_none, 0) AS edu_none,
                   COALESCE(p.edu_highschool, 0) AS edu_highschool,
                   COALESCE(p.edu_college, 0) AS edu_college,
                   p.is_capital, (p.flag_data IS NOT NULL) AS has_flag,
                   {image_select}
            FROM provinces p
            LEFT JOIN stats s ON p.userId = s.id
            WHERE p.id = %s
            """
        else:
            province_sql = f"""
            SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
                   p.pollution, p.happiness, p.productivity, p.consumer_spending,
                   CAST(p.citycount AS INTEGER) as citycount,
                   p.land, p.energy AS electricity,
                   s.location,
                   0 AS pop_children, 0 AS pop_working, 0 AS pop_elderly,
                   0 AS edu_none, 0 AS edu_highschool, 0 AS edu_college,
                   p.is_capital, (p.flag_data IS NOT NULL) AS has_flag,
                   {image_select}
            FROM provinces p
            LEFT JOIN stats s ON p.userId = s.id
            WHERE p.id = %s
            """
        try:
            db.execute(province_sql, (pId,))
            result = db.fetchone()
        except Exception:
            rollback_db_cursor(db)
            db.execute(
                """
                SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
                       p.pollution, p.happiness, p.productivity, p.consumer_spending,
                       CAST(p.citycount AS INTEGER) as citycount,
                       p.land, p.energy AS electricity,
                       s.location,
                       0 AS pop_children, 0 AS pop_working, 0 AS pop_elderly,
                       0 AS edu_none, 0 AS edu_highschool, 0 AS edu_college,
                       FALSE AS is_capital, FALSE AS has_flag,
                       FALSE AS has_image
                FROM provinces p
                LEFT JOIN stats s ON p.userId = s.id
                WHERE p.id = %s
                """,
                (pId,),
            )
            result = db.fetchone()

        if not result:
            return error(404, "Province doesn't exist")

        # Convert to dict for template
        result = dict(result)

        # Get upgrades in normalized schema
        user_id = result["user"]
        cache_key = f"upgrades_{user_id}"
        upgrades = query_cache.get(cache_key)
        if upgrades is None:
            legacy_upgrade_to_tech = {
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
            tech_to_legacy = {v: k for k, v in legacy_upgrade_to_tech.items()}
            upgrades = {k: False for k in legacy_upgrade_to_tech.keys()}
            db.execute(
                """
                SELECT td.name
                FROM user_tech ut
                JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                WHERE ut.user_id=%s AND ut.is_unlocked=TRUE
                """,
                (user_id,),
            )
            for row in db.fetchall():
                # db is a RealDictCursor here -- rows are dict-like, so
                # `for (tech_name,) in db.fetchall()` silently unpacked the
                # row's KEY ("name") instead of its VALUE (e.g.
                # "better_engineering"), so tech_to_legacy.get() never
                # matched anything and every upgrade-gated display on this
                # page (bonus text, the reactor "+6 w/ Better Engineering"
                # branch, etc.) silently showed as locked even when unlocked.
                tech_name = row["name"] if hasattr(row, "get") else row[0]
                legacy_key = tech_to_legacy.get(tech_name)
                if legacy_key:
                    upgrades[legacy_key] = True
            query_cache.set(cache_key, upgrades)

        # Projected population change next tick, owner only (same shared
        # formula and nation-wide rations ratio as the real population tick;
        # cached per nation, see get_population_growth).
        growth_rate = None
        if result["user"] == cId:
            try:
                from app_core.game_ticks.population import get_population_growth

                # Plain tuple cursor on the same request connection: the
                # projection indexes rows positionally (db is a dict cursor).
                with db.connection.cursor() as tuple_db:
                    growth_rate = (
                        get_population_growth(cId, db=tuple_db).get("per_province")
                        or {}
                    ).get(str(result["id"]))
            except Exception:
                rollback_db_cursor(db)
                growth_rate = None

        # Build province dict from result
        province = {
            "id": result["id"],
            "user": result["user"],
            "name": result["name"],
            "population": result["population"],
            "pop_children": result["pop_children"],
            "pop_working": result["pop_working"],
            "pop_elderly": result["pop_elderly"],
            # Were missing, so the Education Breakdown always rendered 0
            # (Unknown Identity, staff-chat 09-28).
            "edu_none": result.get("edu_none") or 0,
            "edu_highschool": result.get("edu_highschool") or 0,
            "edu_college": result.get("edu_college") or 0,
            "pollution": result["pollution"],
            "happiness": result["happiness"],
            "productivity": result["productivity"],
            "consumer_spending": result["consumer_spending"],
            "citycount": result["citycount"],
            "land": result["land"],
            "electricity": result["electricity"],
            "location": (result["location"] or "Grassland").strip(),
            "is_capital": bool(result.get("is_capital")),
            "has_flag": bool(result.get("has_flag")),
            # Was missing, so province["has_image"] below was always False and
            # the uploaded province picture never showed on its own page.
            "has_image": bool(result.get("has_image")),
            "growth_rate": growth_rate,
            "flag_url": f"/flag/province/{result['id']}" if result.get("has_flag") else None,
        }

        # Build units dict from user_buildings (Economy 2.0 normalized schema)
        # Maps building name → quantity owned in THIS province
        province_id_val = result["id"]
        db.execute(
            """
            SELECT bd.name, COALESCE(ub.quantity, 0) AS quantity
            FROM building_dictionary bd
            LEFT JOIN user_buildings ub
                ON ub.building_id = bd.building_id
                AND ub.user_id = %s
                AND ub.province_id = %s
            WHERE bd.is_active = TRUE
            """,
            (user_id, province_id_val),
        )
        units = {row["name"]: row["quantity"] for row in db.fetchall()}
        # Ensure all expected building names exist in units (default 0)
        all_building_names = [
            "coal_burners",
            "oil_burners",
            "solar_fields",
            "wind_farms",
            "geothermal_plants",
            "hydro_dams",
            "nuclear_reactors",
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "malls",
            "banks",
            "city_parks",
            "hospitals",
            "libraries",
            "universities",
            "monorails",
            "railways",
            "metros",
            "firewatch_towers",
            "levees",
            "seismic_reinforcements",
            "army_bases",
            "aerodomes",
            "harbours",
            "admin_buildings",
            "silos",
            "farms",
            "pumpjacks",
            "coal_mines",
            "bauxite_mines",
            "copper_mines",
            "uranium_mines",
            "lead_mines",
            "iron_mines",
            "lumber_mills",
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
            "distribution_centers", "food_banks",
            "industrial_district",
            "primary_school",
            "high_school",
            "fisheries",
            "silver_mines",
            "diamond_mines",
            "bullion_mines",
            "workshops",
            "jewelry_stores",
            "automotive_plants",
        ]
        for bname in all_building_names:
            units.setdefault(bname, 0)

        # Calculate free slots in-memory (no extra queries)
        used_city_slots = sum(units.get(b, 0) or 0 for b in CITY_UNITS)
        used_land_slots = sum(units.get(b, 0) or 0 for b in LAND_UNITS)

        province["free_cityCount"] = province["citycount"] - used_city_slots
        province["free_land"] = province["land"] - used_land_slots
        province["own"] = province["user"] == cId
        # Coalition "share-build" access (opt-in, see app_core/coalitions):
        # lets a qualifying coalition role plan/build in this province when
        # its owner has explicitly turned sharing on. Deliberately separate
        # from `own` -- this must only ever unlock the build/demolish
        # actions, never rename/delete/flag/set-capital or anything else
        # gated on `own` elsewhere in this template.
        try:
            province["can_plan_builds"] = province["own"] or can_manage_province_builds(
                db, cId, province["user"]
            )
        except Exception:
            province["can_plan_builds"] = province["own"]
        province["shared_build_access"] = (
            province["can_plan_builds"] and not province["own"]
        )

        # Check consumer goods and rations from normalized economy data
        db.execute(
            """
            SELECT rd.name, ue.quantity
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id=%s AND rd.name IN
                ('consumer_goods', 'rations', 'coal', 'oil', 'uranium')
            """,
            (user_id,),
        )
        economy_values = {row["name"]: row["quantity"] for row in db.fetchall()}
        consumer_goods = economy_values.get("consumer_goods", 0) or 0
        rations = economy_values.get("rations", 0) or 0

        db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
        gold_row = db.fetchone()
        national_gold = (row_val(gold_row, "gold", 0, default=0) or 0) if gold_row else 0

        max_cg = math.ceil(province["population"] / variables.CONSUMER_GOODS_PER)
        cg_dist_cap = 0
        enough_consumer_goods = consumer_goods >= max_cg
        # Per-province CG supply for the status card -- same allocation the
        # tax tick uses (app_core/economy/consumer_goods.py).
        cg_status = None
        try:
            if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
                from app_core.economy.consumer_goods import (
                    allocate_consumer_goods,
                    grace_period_until,
                    load_province_cg_capacities,
                    province_cg_need,
                )

                db.execute(
                    "SELECT id, population, pop_children, pop_working, pop_elderly "
                    "FROM provinces WHERE userId=%s ORDER BY id",
                    (user_id,),
                )
                nation_provs = db.fetchall()
                prov_ids = [row_val(r, "id", 0) for r in nation_provs]
                has_demo = all(
                    row_val(r, "pop_children", 2) is not None
                    and row_val(r, "pop_working", 3) is not None
                    and row_val(r, "pop_elderly", 4) is not None
                    for r in nation_provs
                )
                db.execute("SELECT education FROM policies WHERE user_id=%s", (user_id,))
                pol_row = db.fetchone()
                pol = (row_val(pol_row, "education", 0) if pol_row else None) or []
                healthcare = variables.POLICY_UNIVERSAL_HEALTHCARE in pol
                needs = [
                    province_cg_need(
                        row_val(r, "population", 1, default=0) or 0,
                        row_val(r, "pop_children", 2),
                        row_val(r, "pop_working", 3),
                        row_val(r, "pop_elderly", 4),
                        healthcare,
                        has_demo,
                    )
                    for r in nation_provs
                ]
                caps_by_id = load_province_cg_capacities(db, prov_ids)
                caps = [caps_by_id.get(pid, 0.0) for pid in prov_ids]
                alloc = allocate_consumer_goods(needs, caps, consumer_goods)
                if province["id"] in prov_ids:
                    idx = prov_ids.index(province["id"])
                    cg_dist_cap = int(caps[idx])
                    coverage = alloc["coverage"][idx]
                    if needs[idx] <= 0:
                        source = "none_needed"
                    elif alloc["remote"][idx] > 0 and alloc["local"][idx] <= 0:
                        source = "remote"
                    elif alloc["remote"][idx] > 0:
                        source = "mixed"
                    elif alloc["local"][idx] > 0:
                        source = "local"
                    else:
                        source = "unserved"
                    cg_status = {
                        "coverage_percent": int(round(coverage * 100)),
                        "source": source,
                        "grace_until": grace_period_until(),
                        "remote_efficiency_percent": int(
                            round(variables.REMOTE_CG_EFFICIENCY * 100)
                        ),
                    }
                    enough_consumer_goods = coverage >= 0.999
        except Exception:
            rollback_db_cursor(db)

        # Economies of scale + vertical integration shown on each producing
        # building's card (same helper the production tick uses).
        industry_bonus = {}
        try:
            from app_core.economy.industry_bonuses import (
                PROCESSING_BUILDINGS,
                SCALE_BUILDINGS,
                production_bonuses,
                self_sufficiency,
            )

            db.execute(
                "SELECT bd.name, COALESCE(SUM(ub.quantity), 0) "
                "FROM user_buildings ub "
                "JOIN building_dictionary bd ON bd.building_id = ub.building_id "
                "WHERE ub.user_id = %s GROUP BY bd.name",
                (user_id,),
            )
            nation_counts = {
                row_val(r, "name", 0): int(row_val(r, "coalesce", 1, default=0) or 0)
                for r in db.fetchall()
            }
            for bname in SCALE_BUILDINGS:
                b = production_bonuses(
                    bname,
                    units,
                    province.get("land") or 0,
                    province.get("citycount") or 0,
                    nation_counts,
                )
                entry = {
                    "scale": round(b["scale"] * 100, 1),
                    "integration": None,
                    "multiplier": b["multiplier"],
                }
                if bname in PROCESSING_BUILDINGS:
                    entry["integration"] = round(b["integration"] * 100, 1)
                    entry["self_sufficiency"] = int(
                        round(self_sufficiency(bname, nation_counts) * 100)
                    )
                industry_bonus[bname] = entry
        except Exception:
            rollback_db_cursor(db)
            industry_bonus = {}

        rations_minus = province["population"] // variables.RATIONS_PER
        nation_distribution = None
        dist_cap = None
        enough_rations = rations - rations_minus > 1
        food_score = None
        national_pop = None

        if variables.FEATURE_RATIONS_DISTRIBUTION:
            from tasks import fetch_nation_distribution_status, food_stats

            dist_cap = 0
            try:
                db.execute(
                    "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId = %s",
                    (cId,),
                )
                nat_pop_row = db.fetchone()
                national_pop = int(
                    row_val(nat_pop_row, "coalesce", 0, default=0) or 0
                )
                nat_rations_need = max(1, national_pop // variables.RATIONS_PER)
                nation_distribution = fetch_nation_distribution_status(
                    db, cId, national_pop, nat_rations_need
                )
                dist_cap = (
                    nation_distribution["distribution_cap"]
                    if nation_distribution
                    else 0
                )
                food_score = food_stats(cId, db=db)
                enough_rations = food_score >= -1.0
            except Exception:
                rollback_db_cursor(db)
                nation_distribution = None
                dist_cap = 0
                enough_rations = rations - rations_minus > 1

        # Calculate energy in-memory from proInfra data
        consumers = variables.ENERGY_CONSUMERS
        producers = variables.ENERGY_UNITS
        new_infra = variables.NEW_INFRA

        # Production multiplier — must match generate_province_revenue() exactly:
        # productivity (this province) * workforce efficiency (national, same
        # jobs-available/jobs-needed ratio the real tick uses), or this display
        # can show a surplus while the real tick lands on a deficit (or vice
        # versa) whenever a nation's population outstrips its job-providing
        # buildings, which is common for large/dense provinces.
        prod_val = province.get("productivity")
        productivity_multiplier = (
            1 + ((prod_val - 50) * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER)
            if prod_val is not None
            else 1.0
        )

        efficiency_multiplier = 1.0
        if variables.FEATURE_PHASE3_WORKFORCE:
            db.execute(
                """
                SELECT COALESCE(SUM(pop_working), 0) AS total_pop_working,
                       COALESCE(SUM(edu_none), 0) AS edu_none,
                       COALESCE(SUM(edu_highschool), 0) AS edu_highschool,
                       COALESCE(SUM(edu_college), 0) AS edu_college
                FROM provinces WHERE userId = %s
                """,
                (user_id,),
            )
            demo_row = db.fetchone() or {}
            total_pop_working = int((demo_row.get("total_pop_working") if hasattr(demo_row, "get") else demo_row[0]) or 0)
            jobs_available = int(
                ((demo_row.get("edu_none") if hasattr(demo_row, "get") else demo_row[1]) or 0)
                + ((demo_row.get("edu_highschool") if hasattr(demo_row, "get") else demo_row[2]) or 0)
                + ((demo_row.get("edu_college") if hasattr(demo_row, "get") else demo_row[3]) or 0)
            )

            db.execute(
                """
                SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS count
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s GROUP BY bd.name
                """,
                (user_id,),
            )
            national_building_counts = {
                (r.get("name") if hasattr(r, "get") else r[0]): int(
                    (r.get("count") if hasattr(r, "get") else r[1]) or 0
                )
                for r in db.fetchall()
            }
            jobs_needed = sum(
                matrix_data.get("worker_count", 0) * national_building_counts.get(bname, 0)
                for bname, matrix_data in variables.BUILDING_EMPLOYMENT_MATRICES.items()
            )
            if jobs_needed > 0:
                employment_ratio = jobs_available / jobs_needed
                efficiency_multiplier = min(
                    1.0, max(variables.PRODUCTION_EFFICIENCY_MIN, employment_ratio)
                )
        production_multiplier = productivity_multiplier * efficiency_multiplier

        # Real per-building hourly output in this province, built exactly like
        # generate_province_revenue(): (productivity + national-project bonus)
        # x specialisation x integration x workforce. The static card text
        # only shows base x project, which read far below what the tick pays
        # (Kurai: 65 steel/mill shown vs ~104 actually produced).
        for bname, entry in industry_bonus.items():
            qty = units.get(bname, 0) or 0
            if qty <= 0:
                continue
            mult = (
                productivity_multiplier + project_output_bonus(bname, upgrades)
            ) * entry.get("multiplier", 1.0) * efficiency_multiplier
            flat = (
                int((province.get("land") or 0) * variables.LAND_FARM_PRODUCTION_ADDITION)
                if bname == "farms"
                else 0
            )
            entry["unit_outputs"] = [
                (res, round((amt * qty + flat) * mult / qty, 1))
                for res, amt in (new_infra.get(bname, {}).get("plus") or {}).items()
            ]

        # Per-building consumption breakdown (each consumer building uses 1
        # energy/hour, except Electric Arc Furnace steel mills which use 2 —
        # matches the real per-unit cost applied in generate_province_revenue()).
        consumption_breakdown = []
        energy_consumption = 0
        for c in consumers:
            qty = units.get(c, 0) or 0
            if qty <= 0:
                continue
            unit_cost = 2 if (c == "steel_mills" and upgrades.get("electricarcfurnace")) else 1
            subtotal = qty * unit_cost
            energy_consumption += subtotal
            consumption_breakdown.append(
                {"name": c, "quantity": qty, "unit_cost": unit_cost, "subtotal": subtotal}
            )
        consumption_breakdown.sort(key=lambda r: r["subtotal"], reverse=True)

        # Per-building production breakdown. Two numbers per producer:
        # theoretical (every built unit assumed to run) and affordable (how
        # many can actually afford their money + fuel upkeep this hour, same
        # gate generate_province_revenue() applies). Real player report:
        # /province showed reactors "producing" full output even when
        # uranium/gold couldn't actually sustain them, because this display
        # never checked affordability -- only the theoretical formula.
        production_breakdown = []
        theoretical_production = 0
        affordable_production = 0
        gold_remaining = national_gold
        # Right after the :25 upkeep tick the treasury is at its hourly low,
        # but the :00 tax payout lands before the next upkeep bill. Without
        # counting it, a nation that just spent its gold saw its provinces
        # "unpowered" until taxes arrived (ieb, 2026-09-22). Only pay for the
        # (cached) revenue projection when the treasury alone falls short.
        producer_upkeep = sum(
            (new_infra.get(p, {}).get("money", 0) or 0) * (units.get(p, 0) or 0)
            for p in producers
        )
        if producer_upkeep > national_gold and tax_due_before_next_upkeep():
            try:
                from countries import get_revenue

                next_tax = get_revenue(user_id).get("next_tax_income", 0) or 0
                gold_remaining = upkeep_budget(national_gold, next_tax)
            except Exception:
                gold_remaining = national_gold
        for p in producers:
            qty = units.get(p, 0) or 0
            if qty <= 0:
                continue
            per_unit_energy = new_infra[p]["plus"]["energy"]
            if p == "nuclear_reactors" and upgrades.get("betterengineering"):
                per_unit_energy += 6

            unit_infra = new_infra.get(p, {})
            money_cost_per_unit = unit_infra.get("money", 0) or 0
            fuel_resource = None
            fuel_cost_per_unit = 0
            for res_name, amt in (unit_infra.get("minus", {}) or {}).items():
                if amt > 0:
                    fuel_resource = res_name
                    fuel_cost_per_unit = amt
                    break

            affordable = qty
            limited_by = []
            if abs(production_multiplier - 1.0) > 1e-9:
                # "Each" shows the building's base rate, but production_multiplier
                # (productivity/workforce efficiency) scales the actual total, so
                # Built x Each can look like it doesn't add up to Total without
                # this note. Real player report: geothermal plants "give 5 units"
                # but total showed 4 with no explanation (ticket-0026).
                limited_by.append("productivity")
            if money_cost_per_unit > 0:
                afford_by_money = int(gold_remaining // money_cost_per_unit)
                if afford_by_money < affordable:
                    limited_by.append("money")
                affordable = min(affordable, afford_by_money)
            if fuel_resource:
                have_fuel = economy_values.get(fuel_resource, 0) or 0
                afford_by_fuel = int(have_fuel // fuel_cost_per_unit)
                if afford_by_fuel < affordable:
                    limited_by.append(fuel_resource)
                affordable = min(affordable, afford_by_fuel)
            affordable = max(0, affordable)
            gold_remaining -= money_cost_per_unit * affordable

            theoretical = math.ceil(qty * per_unit_energy * production_multiplier) if qty else 0
            actual = math.ceil(affordable * per_unit_energy * production_multiplier) if affordable else 0
            theoretical_production += theoretical
            affordable_production += actual
            production_breakdown.append(
                {
                    "name": p,
                    "quantity": qty,
                    "affordable_units": affordable,
                    "unit_output": per_unit_energy,
                    "theoretical": theoretical,
                    "actual": actual,
                    "limited_by": limited_by,
                    "fuel_resource": fuel_resource,
                }
            )
        production_breakdown.sort(key=lambda r: r["actual"], reverse=True)

        energy_production = affordable_production
        energy = {
            "consumption": energy_consumption,
            "production": affordable_production,
            "theoretical_production": theoretical_production,
            "consumption_breakdown": consumption_breakdown,
            "production_breakdown": production_breakdown,
            "net": affordable_production - energy_consumption,
            "production_multiplier": production_multiplier,
            "productivity_pct": prod_val,
            "productivity_multiplier": productivity_multiplier,
            "efficiency_multiplier": efficiency_multiplier,
        }
        has_power = affordable_production >= energy_consumption

        # upgrades already fetched in same connection above

        # Normalized buildings (for Action Loop quick-build form)
        # This is static dictionary data — cache it to avoid querying every request
        normalized_buildings = query_cache.get("building_dictionary_active_v2")
        if normalized_buildings is None:
            db.execute(
                """
                SELECT building_id, name, display_name, base_cost
                FROM building_dictionary
                WHERE is_active = TRUE
                ORDER BY display_name ASC
                """
            )
            rows = db.fetchall() or []
            normalized_buildings = [
                enrich_building_row(
                    {
                        "building_id": r["building_id"],
                        "name": r["name"],
                        "display_name": r["display_name"],
                        "base_cost": r["base_cost"],
                    }
                )
                for r in rows
            ]
            query_cache.set(
                "building_dictionary_active_v2", normalized_buildings, ttl_seconds=600
            )

        infra = variables.INFRA
        prices = variables.PROVINCE_UNIT_PRICES

        province_base_layout = None
        if FEATURE_PROVINCE_BASE_VIEW:
            province["own"] = province.get("own", province["user"] == cId)
            # Shallow copy so the base-view canvas's "own" (may act on this
            # province -- owner OR opted-in shared coalition access) doesn't
            # leak into `province["own"]`, which the rest of this template
            # uses to gate owner-only actions (rename/delete/flag/etc).
            layout_province = dict(province)
            layout_province["own"] = province.get(
                "can_plan_builds", province["own"]
            )
            province_base_layout = build_province_layout_payload(
                layout_province, units
            )

        if province.get("location"):
            # Normalize location to avoid strict case-sensitive and whitespace template mismatch errors
            # which cause missing mines and shifted quick-links in province.html
            province["location"] = province["location"].strip().title()

        province["has_image"] = bool(province.get("has_image"))
        province["image_url"] = province_image_url(
            province["id"], province["has_image"]
        )

        db.execute(
            "SELECT COUNT(id) AS province_count FROM provinces WHERE userId = %s",
            (user_id,),
        )
        province_count_row = db.fetchone()
        province_count = (
            province_count_row["province_count"] if province_count_row else 0
        )

        distribution_status = nation_distribution
        if variables.FEATURE_RATIONS_DISTRIBUTION:
            if distribution_status and food_score is not None and food_score < -1:
                distribution_status = dict(distribution_status)
                distribution_status["show_alert"] = True

        # "What makes up this number" for happiness / pollution /
        # productivity (owner only), from the same per-building effect
        # function the hourly tick uses (app_core.economy.province_effects),
        # plus the city/land max-population diminishing-returns numbers.
        stat_breakdown = None
        pop_cap_info = None
        if province.get("own"):
            try:
                from app_core.economy.building_purchase import _load_policies
                from app_core.economy.province_effects import (
                    pop_cap_marginals,
                    province_stat_breakdown,
                )

                with db.connection.cursor() as tuple_db:
                    own_policies = _load_policies(tuple_db, cId)
                stat_breakdown = province_stat_breakdown(
                    {
                        k: province.get(k)
                        for k in ("happiness", "pollution", "productivity")
                    },
                    units,
                    upgrades,
                    own_policies,
                )
                pop_cap_info = pop_cap_marginals(
                    province.get("citycount"), province.get("land")
                )
            except Exception:
                rollback_db_cursor(db)
                stat_breakdown = None
                pop_cap_info = None
        education_stats = None
        if variables.FEATURE_PHASE3_WORKFORCE:
            from app_core.economy.building_purchase import _load_policies
            from app_core.game_ticks.population import calc_education_graduation

            with db.connection.cursor() as tuple_db:
                edu_policies = _load_policies(tuple_db, province.get("owner_id") or cId)
            education_stats = calc_education_graduation(
                province.get("pop_children", 0) or 0,
                edu_policies,
                units.get("primary_school", 0) or 0,
                units.get("high_school", 0) or 0,
                units.get("universities", 0) or 0,
            )

        template = "province_v2.html" if is_theme_v2_enabled("province") else "province.html"
        return render_template(
            template,
            province=province,
            stat_breakdown=stat_breakdown,
            pop_cap_info=pop_cap_info,
            other_mines=other_biome_mines(province.get("location")),
            distribution_status=distribution_status,
            population=national_pop,
            food_score=food_score,
            units=units,
            enough_consumer_goods=enough_consumer_goods,
            enough_rations=enough_rations,
            has_power=has_power,
            energy=energy,
            infra=infra,
            upgrades=upgrades,
            prices=prices,
            new_infra=new_infra,
            normalized_buildings=normalized_buildings,
            distribution_capacity=(
                dist_cap if variables.FEATURE_RATIONS_DISTRIBUTION else None
            ),
            nation_distribution=nation_distribution,
            cg_distribution_capacity=(
                cg_dist_cap if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION else None
            ),
            cg_status=cg_status,
            industry_bonus=industry_bonus,
            province_base_layout=province_base_layout,
            province_count=province_count,
            province_rename_cost=PROVINCE_RENAME_COST,
            education_stats=education_stats,
        )


@bp.route("/province-image/<int:pId>")
def serve_province_image(pId):
    """Serve a province's custom banner image (public, like country flags)."""
    import base64
    import time as time_module

    from flask import Response, send_from_directory, current_app

    if not provinces_has_image_data():
        return send_from_directory(
            current_app.static_folder, "images/province.jpg"
        )

    cache_key = f"province_image_{pId}"
    if not hasattr(serve_province_image, "_cache"):
        serve_province_image._cache = {}
    cached = serve_province_image._cache.get(cache_key)
    if cached is not None:
        body, mimetype, cached_at = cached
        if time_module.time() - cached_at < 300:
            response = Response(body, mimetype=mimetype)
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
        del serve_province_image._cache[cache_key]

    with get_request_cursor(read_only=True) as db:
        db.execute(
            "SELECT image_data FROM provinces WHERE id = %s",
            (pId,),
        )
        row = db.fetchone()

    if not row or not row[0]:
        return send_from_directory(
            current_app.static_folder, "images/province.jpg"
        )

    try:
        image_data = base64.b64decode(row[0])
        if image_data[:8] == b"\x89PNG\r\n\x1a\n":
            mimetype = "image/png"
        elif image_data[:2] == b"\xff\xd8":
            mimetype = "image/jpeg"
        elif image_data[:6] in (b"GIF87a", b"GIF89a"):
            mimetype = "image/gif"
        else:
            mimetype = "image/jpeg"

        if len(serve_province_image._cache) < 500:
            serve_province_image._cache[cache_key] = (
                image_data,
                mimetype,
                time_module.time(),
            )
        response = Response(image_data, mimetype=mimetype)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    except Exception:
        return send_from_directory(
            current_app.static_folder, "images/province.jpg"
        )


@bp.route("/province/<int:pId>/image", methods=["POST"])
@login_required
@require_post_origin
def update_province_image(pId):
    """Upload or remove a province banner image."""
    from database import invalidate_view_cache, query_cache

    cId = session["user_id"]
    remove_image = request.form.get("remove_image") == "1"

    with get_request_cursor() as db:
        if not provinces_has_image_data():
            return error(503, "Province images are not available yet")

        db.execute(
            "SELECT userId FROM provinces WHERE id = %s",
            (pId,),
        )
        row = db.fetchone()
        if not row:
            return error(404, "Province doesn't exist")
        if int(row[0]) != int(cId):
            return error(403, "You do not own this province")

        if remove_image:
            db.execute(
                "UPDATE provinces SET image_data = NULL WHERE id = %s",
                (pId,),
            )
        else:
            allowed_extensions = {"png", "jpg", "jpeg", "webp"}
            upload = request.files.get("province_image")
            if not upload or not upload.filename:
                return error(400, "No image file provided")

            extension = upload.filename.rsplit(".", 1)[-1].lower()
            if extension not in allowed_extensions:
                return error(400, "Use PNG, JPG, or WEBP")

            image_data, _ext = compress_province_image(upload)
            db.execute(
                "UPDATE provinces SET image_data = %s WHERE id = %s",
                (image_data, pId),
            )

    if hasattr(serve_province_image, "_cache"):
        serve_province_image._cache.pop(f"province_image_{pId}", None)

    try:
        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"provinces_{cId}_")
        query_cache.invalidate(pattern=f"province_{cId}_")
        invalidate_view_cache("province", user_id=cId)
        invalidate_view_cache("provinces", user_id=cId)
    except Exception:
        pass

    from time import time as _now

    return redirect(f"/province/{pId}?_={int(_now())}")


@bp.route("/api/province/<int:pId>/layout", methods=["GET"])
@login_required
def province_layout_api(pId):
    """JSON layout for province base canvas (mobile game view)."""
    from psycopg2.extras import RealDictCursor

    cId = session["user_id"]
    with get_request_cursor(cursor_factory=RealDictCursor, read_only=True) as db:
        db.execute(
            """
            SELECT p.id, p.userId, p.provinceName AS name, p.happiness, p.pollution,
                   p.population, p.energy AS electricity, s.location
            FROM provinces p
            LEFT JOIN stats s ON p.userId = s.id
            WHERE p.id = %s
            """,
            (pId,),
        )
        row = db.fetchone()
        if not row:
            return jsonify({"error": "Province not found"}), 404
        owner_id = row.get("userid") or row.get("userId")
        if owner_id is None:
            return jsonify({"error": "Forbidden"}), 403
        owner_id = int(owner_id)
        can_plan = owner_id == int(cId) or can_manage_province_builds(
            db, cId, owner_id
        )
        if not can_plan:
            return jsonify({"error": "Forbidden"}), 403

        province = dict(row)
        province["location"] = (province.get("location") or "Grassland").strip()
        # Gates the interactive build controls in the base-view JS -- true
        # here means "may act on this province" (owner or opted-in shared
        # access), already verified above.
        province["own"] = True

        db.execute(
            """
            SELECT bd.name, COALESCE(ub.quantity, 0) AS quantity
            FROM building_dictionary bd
            LEFT JOIN user_buildings ub
                ON ub.building_id = bd.building_id
                AND ub.user_id = %s
                AND ub.province_id = %s
            WHERE bd.is_active = TRUE
            """,
            (owner_id, pId),
        )
        units = {r["name"]: r["quantity"] for r in db.fetchall()}

    return jsonify(build_province_layout_payload(province, units))


def _province_units_for_user(db, cId, pId):
    db.execute(
        """
        SELECT bd.building_id, bd.name, bd.display_name, bd.base_cost,
               COALESCE(ub.quantity, 0) AS quantity
        FROM building_dictionary bd
        LEFT JOIN user_buildings ub
            ON ub.building_id = bd.building_id
            AND ub.user_id = %s
            AND ub.province_id = %s
        WHERE bd.is_active = TRUE
        ORDER BY bd.display_name ASC
        """,
        (cId, pId),
    )
    return db.fetchall()


@bp.route("/api/province/<int:pId>/slot/<slot_id>", methods=["GET"])
@login_required
def province_slot_api(pId, slot_id):
    """Buildings in a category for interactive base sheet."""
    from psycopg2.extras import RealDictCursor

    slot = get_slot_config(slot_id)
    if not slot:
        return jsonify({"error": "Unknown category"}), 404

    cId = session["user_id"]
    with get_request_cursor(cursor_factory=RealDictCursor, read_only=True) as db:
        db.execute(
            "SELECT id, userId AS owner_id FROM provinces WHERE id = %s",
            (pId,),
        )
        prow = db.fetchone()
        if not prow:
            return jsonify({"error": "Province not found"}), 404
        if prow["owner_id"] != cId:
            return jsonify({"error": "Forbidden"}), 403

        allowed_mines = None
        if slot_id == "mines":
            db.execute("SELECT location FROM stats WHERE id=%s", (cId,))
            loc_row = db.fetchone()
            allowed_mines = set(
                mines_for_biome(loc_row["location"] if loc_row else None)
            )

        rows = _province_units_for_user(db, cId, pId)
        names = set(slot["buildings"])
        buildings = []
        for row in rows:
            if row["name"] not in names:
                continue
            qty = int(row["quantity"] or 0)
            can_build = allowed_mines is None or row["name"] in allowed_mines
            # Locked-biome mines with none built stay in the list (grayed out,
            # reference-only client-side) instead of being hidden entirely --
            # matches classic view's "Other Raw Resources" (see biome_buildings.py),
            # so a player can see a trade partner's mine cost/output here too
            # without switching views. Purchase is still blocked server-side.
            entry = enrich_building_row(
                {
                    "building_id": row["building_id"],
                    "name": row["name"],
                    "display_name": row["display_name"],
                    "base_cost": int(row["base_cost"] or 0),
                }
            )
            entry["icon"] = building_visual_icon(row["name"])
            entry["quantity"] = qty
            entry["can_build"] = can_build
            buildings.append(entry)
        buildings.sort(key=lambda b: (-b["quantity"], b["display_name"]))

    suggest_build = None
    buildable = [b for b in buildings if b["can_build"]]
    if buildable:
        starter = min(buildable, key=lambda b: (b["gold_cost"], b["display_name"]))
        suggest_build = {
            "building_id": starter["building_id"],
            "display_name": starter["display_name"],
            "gold_cost": starter["gold_cost"],
            "resource_cost": starter["resource_cost"],
            "cost_display": starter["cost_display"],
            "icon": starter["icon"],
        }

    theme = SLOT_THEMES.get(slot_id, {})
    return jsonify(
        {
            "slot_id": slot_id,
            "label": slot["label"],
            "icon": slot["icon"],
            "theme": theme,
            "buildings": buildings,
            "suggest_build": suggest_build,
        }
    )


from extensions import limiter

@bp.route("/api/province/<int:pId>/quick_build", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def province_quick_build_api(pId):
    """JSON quick-build (+1) from base sheet without full page reload."""
    from psycopg2.extras import RealDictCursor
    from database import invalidate_view_cache

    cId = session["user_id"]
    payload = request.get_json(silent=True) or {}
    try:
        building_id = int(payload.get("building_id", 0))
        quantity = int(payload.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid request"}), 400

    if quantity == 0 or quantity > 50 or quantity < -50:
        return jsonify(
            {"ok": False, "error": "Quantity must be 1–50 (negative to demolish)"}
        ), 400

    effective_user_id = cId
    with get_request_cursor(cursor_factory=RealDictCursor, read_only=True) as db:
        db.execute(
            "SELECT userId AS owner_id FROM provinces WHERE id = %s",
            (pId,),
        )
        row = db.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Province not found"}), 404
        owner_id = int(row["owner_id"])
        if owner_id != int(cId):
            if not can_manage_province_builds(db, cId, owner_id):
                return jsonify({"ok": False, "error": "Forbidden"}), 403
        effective_user_id = owner_id

    try:
        if quantity < 0:
            from action_loop import demolish_structure

            demolish_structure(
                effective_user_id, building_id, -quantity, province_id=pId
            )
        else:
            build_structure(
                effective_user_id, building_id, quantity, province_id=pId
            )
    except Exception as e:
        # Catch ActionLoopError and psycopg2 DatabaseError (from triggers)
        import psycopg2
        if isinstance(e, psycopg2.DatabaseError):
            err_msg = str(e).split('\n')[0]
        else:
            err_msg = str(e)
        return jsonify({"ok": False, "error": err_msg}), 400

    try:
        invalidate_user_cache(effective_user_id)
        invalidate_view_cache("province", user_id=effective_user_id)
        invalidate_view_cache("provinces", user_id=effective_user_id)
        invalidate_view_cache("military", user_id=effective_user_id)
    except Exception:
        pass

    with get_request_cursor(cursor_factory=RealDictCursor, read_only=True) as db:
        db.execute(
            """
            SELECT p.id, p.provinceName AS name, p.happiness, p.pollution,
                   p.population, p.energy AS electricity, s.location,
                   p.userId AS owner_id
            FROM provinces p
            LEFT JOIN stats s ON p.userId = s.id
            WHERE p.id = %s
            """,
            (pId,),
        )
        province_row = db.fetchone()
        province = dict(province_row) if province_row else {}
        province["location"] = (province.get("location") or "Grassland").strip()
        # Already verified above (owner or opted-in shared access) -- gates
        # the interactive build controls in the base-view JS response.
        province["own"] = True

        db.execute(
            """
            SELECT bd.name, COALESCE(ub.quantity, 0) AS quantity
            FROM building_dictionary bd
            LEFT JOIN user_buildings ub
                ON ub.building_id = bd.building_id
                AND ub.user_id = %s
                AND ub.province_id = %s
            WHERE bd.is_active = TRUE
            """,
            (effective_user_id, pId),
        )
        units = {r["name"]: r["quantity"] for r in db.fetchall()}

    return jsonify(
        {
            "ok": True,
            "message": "Structure built!",
            "layout": build_province_layout_payload(province, units),
            "building_id": building_id,
        }
    )


@bp.route("/build_structure", methods=["POST"])
@login_required
@require_post_origin
def build_structure_action():
    cId = session["user_id"]
    province_id = request.form.get("province_id")

    try:
        building_id = int(request.form.get("building_id", "0"))
        quantity = int(request.form.get("quantity", "1"))
    except (TypeError, ValueError):
        return error(400, "Invalid building selection or quantity.")

    # Defaults to the acting user; only overridden below when this is a
    # coalition "share-build" action on a member's opted-in province, and
    # ONLY after the permission check passes. All gold/resource/building
    # state must land on the province OWNER, never on the acting leader.
    effective_user_id = cId

    if province_id:
        try:
            province_id_int = int(province_id)
        except (TypeError, ValueError):
            return error(400, "Invalid province.")
        with get_request_cursor() as db:
            db.execute(
                "SELECT userId FROM provinces WHERE id = %s",
                (province_id_int,),
            )
            row = db.fetchone()
            if not row:
                return error(404, "Province not found")
            owner_id = row[0]
            if owner_id != cId:
                if not can_manage_province_builds(db, cId, owner_id):
                    return error(403, "You do not own this province")
            effective_user_id = owner_id

    try:
        if quantity < 0:
            from action_loop import demolish_structure

            demolish_structure(
                effective_user_id,
                building_id,
                -quantity,
                province_id=int(province_id) if province_id else None,
            )
        else:
            build_structure(
                effective_user_id,
                building_id,
                quantity,
                province_id=int(province_id) if province_id else None,
            )
    except ActionLoopError as e:
        return error(400, str(e))

    try:
        from database import invalidate_view_cache

        invalidate_user_cache(effective_user_id)
        invalidate_view_cache("province", user_id=effective_user_id)
        invalidate_view_cache("provinces", user_id=effective_user_id)
        invalidate_view_cache("military", user_id=effective_user_id)
    except Exception:
        pass

    if province_id:
        return redirect(f"/province/{province_id}")
    return redirect(f"/country/id={cId}")


def get_province_price(user_id):
    with get_request_cursor() as db:
        db.execute("SELECT COUNT(id) FROM provinces WHERE userId=(%s)", (user_id,))
        count_row = db.fetchone()
        current_province_amount = count_row[0] if count_row else 0

        multiplier = 1 + (0.16 * current_province_amount)
        if current_province_amount == 0:
            price = 2000000
        elif current_province_amount == 1:
            price = 5000000
        else:
            price = int(8000000 * multiplier)

        return price


PROVINCE_RENAME_COST = 10_000_000
PROVINCE_NAME_MAX_LENGTH = 30


@bp.route("/province/<int:pId>/rename", methods=["POST"])
@login_required
@require_post_origin
def rename_province(pId):
    """Rename a province. Costs PROVINCE_RENAME_COST gold per change."""
    cId = session["user_id"]
    new_name = (request.form.get("name") or "").strip()

    if not new_name:
        return error(400, "Province name cannot be empty")
    if len(new_name) > PROVINCE_NAME_MAX_LENGTH:
        return error(
            400, f"Province name must be {PROVINCE_NAME_MAX_LENGTH} characters or fewer"
        )

    with get_request_cursor() as db:
        db.execute(
            "SELECT userId, provinceName FROM provinces WHERE id = %s", (pId,)
        )
        row = db.fetchone()
        if not row:
            return error(404, "Province doesn't exist")
        if int(row[0]) != int(cId):
            return error(403, "You do not own this province")

        current_name = row[1]
        if new_name == current_name:
            return redirect(f"/province/{pId}")

        # Atomic gold deduction, same pattern as coalition renames
        db.execute(
            "UPDATE stats SET gold = gold - %s "
            "WHERE id = %s AND gold >= %s RETURNING gold",
            (PROVINCE_RENAME_COST, cId, PROVINCE_RENAME_COST),
        )
        if not db.fetchone():
            return error(
                400,
                f"Renaming a province costs {PROVINCE_RENAME_COST:,} gold, "
                "which you don't have.",
            )

        db.execute(
            "UPDATE provinces SET provinceName = %s WHERE id = %s",
            (new_name, pId),
        )

    try:
        from database import invalidate_view_cache, query_cache

        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"provinces_{cId}_")
        query_cache.invalidate(pattern=f"province_{cId}_")
        invalidate_view_cache("province", user_id=cId)
        invalidate_view_cache("provinces", user_id=cId)
    except Exception:
        pass

    from time import time as _now

    return redirect(f"/province/{pId}?_={int(_now())}")


@bp.route("/province/<int:pId>/delete", methods=["POST"])
@login_required
@require_post_origin
def delete_province(pId):
    """Permanently delete a province. Buildings/land on it are lost; the
    price of the next province purchased drops accordingly since
    get_province_price() is always computed from the user's live province
    count. Requires typing the exact province name to confirm, and refuses
    to delete a user's only remaining province."""
    cId = session["user_id"]

    with get_request_cursor() as db:
        db.execute(
            "SELECT userId, provinceName FROM provinces WHERE id = %s", (pId,)
        )
        row = db.fetchone()
        if not row:
            return error(404, "Province doesn't exist")
        if int(row[0]) != int(cId):
            return error(403, "You do not own this province")
        province_name = row[1]

        confirm_name = (request.form.get("confirm_name") or "").strip()
        if confirm_name != province_name:
            return error(400, "Confirmation text did not match the province name")

        db.execute("SELECT COUNT(id) FROM provinces WHERE userId = %s", (cId,))
        count_row = db.fetchone()
        if not count_row or int(count_row[0]) <= 1:
            return error(400, "You cannot delete your only remaining province")

        db.execute("DELETE FROM provinces WHERE id = %s", (pId,))

    try:
        from database import invalidate_view_cache, query_cache

        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"provinces_{cId}_")
        query_cache.invalidate(pattern=f"province_{cId}_")
        invalidate_view_cache("province", user_id=cId)
        invalidate_view_cache("provinces", user_id=cId)
        invalidate_view_cache("military", user_id=cId)
    except Exception:
        pass

    return redirect("/provinces")


@bp.route("/province/<int:pId>/set-capital", methods=["POST"])
@login_required
@require_post_origin
def set_capital_province(pId):
    """Designate a province as the nation's capital (shown on the lore
    page). Discord #suggestions "country customisation/larp" (Cheesar,
    2026-09-05). Purely cosmetic -- at most one capital per nation, enforced
    by idx_provinces_one_capital_per_user (migration 0073)."""
    cId = session["user_id"]

    with get_request_cursor() as db:
        db.execute("SELECT userId FROM provinces WHERE id = %s", (pId,))
        row = db.fetchone()
        if not row:
            return error(404, "Province doesn't exist")
        if int(row[0]) != int(cId):
            return error(403, "You do not own this province")

        db.execute(
            "UPDATE provinces SET is_capital = FALSE WHERE userId = %s", (cId,)
        )
        db.execute(
            "UPDATE provinces SET is_capital = TRUE WHERE id = %s", (pId,)
        )

    try:
        from database import invalidate_view_cache, query_cache

        invalidate_user_cache(cId)
        query_cache.invalidate(pattern=f"provinces_{cId}_")
        query_cache.invalidate(pattern=f"province_{cId}_")
        invalidate_view_cache("province", user_id=cId)
        invalidate_view_cache("provinces", user_id=cId)
        invalidate_view_cache("country", user_id=cId)
    except Exception:
        pass

    return redirect(f"/province/{pId}")


@bp.route("/province/<int:pId>/flag", methods=["POST"])
@login_required
@require_post_origin
def upload_province_flag(pId):
    """Upload a per-province flag image. Discord #suggestions "country
    customisation/larp" (Cheesar, 2026-09-05). Same compress-and-store-as-
    base64 pattern as the nation flag (see countries.py::update_info),
    served back by app_core/main/routes.py::serve_flag."""
    cId = session["user_id"]

    flag = request.files.get("flag_input")
    if not flag or not flag.filename:
        return error(400, "No flag file provided")

    allowed_extensions = ("png", "jpg", "jpeg")
    if "." not in flag.filename or flag.filename.rsplit(".", 1)[1].lower() not in allowed_extensions:
        return error(400, "Bad flag file format")

    with get_request_cursor() as db:
        db.execute("SELECT userId FROM provinces WHERE id = %s", (pId,))
        row = db.fetchone()
        if not row:
            return error(404, "Province doesn't exist")
        if int(row[0]) != int(cId):
            return error(403, "You do not own this province")

        from helpers import compress_flag_image

        flag_data, _extension = compress_flag_image(flag, max_size=300, quality=85)
        db.execute(
            "UPDATE provinces SET flag_data = %s WHERE id = %s", (flag_data, pId)
        )

    try:
        from database import invalidate_view_cache, query_cache

        query_cache.invalidate(pattern=f"provinces_{cId}_")
        query_cache.invalidate(pattern=f"province_{cId}_")
        invalidate_view_cache("province", user_id=cId)
        invalidate_view_cache("provinces", user_id=cId)
    except Exception:
        pass

    # Also invalidate the /flag/province/<id> image route's own in-process
    # cache -- separate from query_cache, was only expiring on its 5-minute
    # TTL otherwise.
    from app_core.main.routes import serve_flag
    getattr(serve_flag, "_cache", {}).pop(f"province_{pId}", None)

    return redirect(f"/province/{pId}")





@bp.route("/createprovince", methods=["GET", "POST"])
@login_required
def createprovince():
    cId = session["user_id"]

    if request.method == "POST":
        from database import get_request_cursor

        with get_request_cursor() as db:
            pName = request.form.get("name")

            # Acquire advisory lock to prevent double-submit race condition
            # Lock key is based on user ID to prevent same user creating multiple
            # provinces simultaneously
            lock_key = 100000 + cId  # Offset to avoid collision with other locks
            db.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            lock_result = db.fetchone()
            if not lock_result or not lock_result[0]:
                return error(400, "Province creation already in progress, please wait")

            try:
                # Use atomic gold deduction to prevent race conditions
                province_price = get_province_price(cId)

                db.execute(
                    "UPDATE stats SET gold = gold - %s "
                    "WHERE id = %s AND gold >= %s RETURNING gold",
                    (province_price, cId, province_price),
                )
                result = db.fetchone()
                if not result:
                    return error(400, "You don't have enough money.")

                # Find an available adjacent hex coordinate for the new province
                db.execute("SELECT coordinate_x, coordinate_y FROM provinces WHERE coordinate_x IS NOT NULL AND coordinate_y IS NOT NULL")
                occupied_coords = set(db.fetchall())

                db.execute("SELECT coordinate_x, coordinate_y FROM provinces WHERE userId = %s AND coordinate_x IS NOT NULL AND coordinate_y IS NOT NULL", (cId,))
                user_coords = set(db.fetchall())

                hex_directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
                new_x, new_y = None, None

                if not user_coords:
                    import random
                    if occupied_coords:
                        found = False
                        occupied_list = list(occupied_coords)
                        random.shuffle(occupied_list)
                        for ox, oy in occupied_list:
                            for dx, dy in hex_directions:
                                nx, ny = ox + dx, oy + dy
                                if (nx, ny) not in occupied_coords:
                                    new_x, new_y = nx, ny
                                    found = True
                                    break
                            if found:
                                break
                        if not found:
                            new_x, new_y = 0, 0
                    else:
                        new_x, new_y = 0, 0
                else:
                    # Find an adjacent free hex tile
                    found = False
                    for ux, uy in user_coords:
                        for dx, dy in hex_directions:
                            nx, ny = ux + dx, uy + dy
                            if (nx, ny) not in occupied_coords:
                                new_x, new_y = nx, ny
                                found = True
                                break
                        if found:
                            break
                    if not found:
                        new_x, new_y = 0, 0 # Fallback

                # Split the starting 1,000,000 population across age brackets
                # (60% working / 30% children / 10% elderly) instead of
                # dumping it all into pop_children -- a new nation used to
                # start 100% "children," which zeroed its tax income under
                # the age-weighted tax system and skewed consumer-goods need.
                db.execute(
                    (
                        "INSERT INTO provinces "
                        "(userId, provinceName, pop_children, pop_working, pop_elderly, "
                        "coordinate_x, coordinate_y) "
                        "VALUES (%s, %s, 300000, 600000, 100000, %s, %s) RETURNING id"
                    ),
                    (cId, pName, new_x, new_y),
                )
                db.fetchone()  # Consume result

                # No need to INSERT INTO proInfra - user_buildings is populated
                # dynamically when buildings are purchased

                # Commit handled by teardown_request_connection

                # Invalidate cached provinces page for this user
                # so the new province appears immediately
                try:
                    from database import query_cache, invalidate_user_cache, invalidate_view_cache

                    pattern = f"provinces_{cId}_"
                    query_cache.invalidate(pattern=pattern)
                    # Invalidate the response cache for the provinces list page
                    # so the new province appears immediately on redirect
                    invalidate_view_cache("provinces", user_id=cId)
                    # Also invalidate influence/resources cache so the
                    # new province is reflected in influence score
                    invalidate_user_cache(cId)
                except Exception:
                    # Best-effort: cache invalidation should not raise on failure
                    pass
            finally:
                # Always release the advisory lock
                try:
                    db.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
                except Exception:
                    pass

        return redirect("/provinces")
    else:
        price = get_province_price(cId)
        template = "createprovince_v2.html" if is_theme_v2_enabled("createprovince") else "createprovince.html"
        return render_template(template, price=price)


def get_free_slots(pId, slot_type, db=None):  # pId = province id
    if slot_type not in ("city", "land"):
        return 0

    if db is not None:
        return economy_get_free_slots(db, pId, slot_type)
    with get_request_cursor() as _db:
        return economy_get_free_slots(_db, pId, slot_type)


@bp.route("/<way>/<units>/<province_id>", methods=["POST"])
@login_required
def province_sell_buy(way, units, province_id):
    cId = session["user_id"]

    with get_request_cursor() as db:
        # Serializes this user's buy/sell calls on this route (same pattern
        # as action_loop.py's build_structure, app_core/military/services.py,
        # and the other fixes made 2026-09-13 during the economy-race sweep).
        # This is the PRIMARY, most heavily-used province building purchase
        # path (every Buy/Sell button in templates/province_v2.html posts
        # here; /api/province/<id>/quick_build is a separate, already-locked
        # newer AJAX path) and had no protection at all. `gold` is read once
        # near the top and reused stale throughout; the buy-side deduction
        # is a blind `UPDATE stats SET gold=gold-%s` with no floor; and for
        # land/cityCount specifically, the grant is an ABSOLUTE
        # `SET {units}=%s` computed from a stale `currentUnits` read (not a
        # relative increment) -- two concurrent buys can each charge gold
        # correctly (relative decrement) while the second SET silently
        # overwrites the first's quantity gain, so a race here can charge a
        # player twice while granting the purchase only once.
        db.execute("SELECT pg_advisory_xact_lock(%s)", (cId,))

        import logging

        try:
            db.execute(
                "SELECT id FROM provinces WHERE id=%s AND userId=%s",
                (
                    province_id,
                    cId,
                ),
            )
            row = db.fetchone()
            ownProvince = bool(row)
        except Exception:
            ownProvince = False

        if not ownProvince:
            logger = logging.getLogger(__name__)
            logger.debug(
                "Unauthorized province action: user %s attempted %s on province %s",
                cId,
                way,
                province_id,
            )
            return error(400, "You don't own this province")

        allUnits = [
            "land",
            "cityCount",
            "coal_burners",
            "oil_burners",
            "hydro_dams",
            "nuclear_reactors",
            "solar_fields",
            "wind_farms",
            "geothermal_plants",
            "gas_stations",
            "general_stores",
            "farmers_markets",
            "malls",
            "banks",
            "distribution_centers", "food_banks",
            "city_parks",
            "hospitals",
            "libraries",
            "universities",
            "monorails",
            "railways",
            "metros",
            "firewatch_towers",
            "levees",
            "seismic_reinforcements",
            "primary_school",
            "high_school",
            "industrial_district",
            "army_bases",
            "harbours",
            "aerodomes",
            "admin_buildings",
            "silos",
            "drone_sites",
            "missile_batteries",
            "farms",
            "pumpjacks",
            "coal_mines",
            "bauxite_mines",
            "copper_mines",
            "uranium_mines",
            "lead_mines",
            "iron_mines",
            "lumber_mills",
            "component_factories",
            "steel_mills",
            "ammunition_factories",
            "aluminium_refineries",
            "oil_refineries",
            "fisheries",
            "silver_mines",
            "diamond_mines",
            "bullion_mines",
            "workshops",
            "jewelry_stores",
            "automotive_plants",
        ]

        city_units = CITY_UNITS

        land_units = LAND_UNITS

        db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
        gold_row = db.fetchone()
        if not gold_row:
            return error(500, "Nation data could not be found")
        gold = gold_row[0] or 0

        try:
            wantedUnits = int(request.form.get(units))
        except (ValueError, TypeError):
            return error(400, "You have to enter a unit amount")

        if wantedUnits > 2147483647 or wantedUnits < -2147483647:
            return error(400, "Amount out of range")

        # Player report (ticket-0020): the classic land/city purchase form only
        # has a "Purchase" button (no separate sell button), so entering a
        # negative amount there — the same demolish-via-negative-number pattern
        # already used for buildings — silently failed. Mirror that pattern
        # here: a negative amount on the buy route sells that many instead.
        if way == "buy" and units in ("land", "cityCount") and wantedUnits < 0:
            way = "sell"
            wantedUnits = -wantedUnits

        if wantedUnits < 1:
            return error(400, "Units cannot be less than 1")

        from app_core.economy.building_costs import (
            land_city_purchase_cost,
            sum_cost_capped_linear,
        )

        # Fetch cityCount and land in one query (reused later for currentUnits)
        db.execute(
            "SELECT CAST(citycount AS INTEGER), land FROM provinces WHERE id=%s",
            (province_id,),
        )
        _prov_row = db.fetchone()
        current_cityCount = int(_prov_row[0] or 0) if _prov_row else 0
        current_land = int(_prov_row[1] or 0) if _prov_row else 0

        if units == "cityCount":
            cityCount_price = sum_cost_capped_linear(
                750000, 50000, current_cityCount, wantedUnits, cap_threshold=200
            )
        else:
            cityCount_price = 0

        if units == "land":
            land_price = sum_cost_capped_linear(
                520000, 25000, current_land, wantedUnits, cap_threshold=100
            )
        else:
            land_price = 0

        # All the unit prices in this format:
        """
        unit_price: <price of the unit>
        unit_resource (optional): {resource_name: amount}
        unit_resource2 (optional): second resource dict (if applicable)
        """
        # TODO: change the unit_resource and unit_resource2 into list based system
        unit_prices = variables.PROVINCE_UNIT_PRICES
        unit_prices["land_price"] = land_price
        unit_prices["cityCount_price"] = cityCount_price

        if units not in allUnits:
            return error(400, "No such unit exists.")

        price = unit_prices[f"{units}_price"]

        policies = []
        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (cId,))
            pol_row = db.fetchone()
            if pol_row and pol_row[0] is not None:
                policies = pol_row[0]
        except Exception:
            rollback_db_cursor(db)
            policies = []

        if 2 in policies:
            price *= 0.96
        if 6 in policies and units == "universities":
            price *= 0.93
        if 1 in policies and units == "universities":
            price *= 1.14

        if units not in ["cityCount", "land"]:
            totalPrice = wantedUnits * price
        elif way == "buy":
            # Shared with Mass Purchase (land_city_purchase_cost) so a mass
            # buy always costs exactly the same as these per-province buys.
            totalPrice = land_city_purchase_cost(
                units,
                current_cityCount if units == "cityCount" else current_land,
                wantedUnits,
                policies,
            )
        else:
            totalPrice = price

        try:
            resources_data = unit_prices[f"{units}_resource"].items()
        except KeyError:
            resources_data = {}

        # Parameterized query: buildings use user_buildings,
        # land/city use provinces (reuse already-fetched province data)
        if units in ["land", "cityCount"]:
            currentUnits = current_cityCount if units == "cityCount" else current_land
        else:
            # Economy 2.0: building counts stored in user_buildings per province
            db.execute(
                """
                SELECT COALESCE(ub.quantity, 0)
                FROM building_dictionary bd
                LEFT JOIN user_buildings ub
                    ON ub.building_id = bd.building_id
                    AND ub.user_id = %s
                    AND ub.province_id = %s
                WHERE bd.name = %s
                """,
                (cId, province_id, units),
            )
            row = db.fetchone()
            currentUnits = row[0] if row else 0

        if units in city_units:
            slot_type = "city"
        elif units in land_units:
            slot_type = "land"
        else:  # If unit is cityCount or land
            free_slots = 0
            slot_type = None

        if slot_type is not None:
            free_slots = get_free_slots(province_id, slot_type, db=db)

        # Preload all resource_ids once to avoid N+1 lookups in resource_stuff
        db.execute("SELECT name, resource_id FROM resource_dictionary")
        _res_id_map = {row[0]: row[1] for row in db.fetchall()}

        def resource_stuff(resources_data, way):
            resources_list = list(resources_data)
            if way == "buy":
                # Pre-check: verify ALL resources before deducting any
                for resource, amount in resources_list:
                    qty = amount * wantedUnits
                    resource_id = _res_id_map.get(resource)
                    if not resource_id:
                        return {
                            "fail": True,
                            "resource": resource,
                            "current_amount": 0,
                            "difference": -qty,
                        }
                    db.execute(
                        "SELECT COALESCE(quantity, 0) FROM user_economy "
                        "WHERE user_id = %s AND resource_id = %s",
                        (cId, resource_id),
                    )
                    row = db.fetchone()
                    current_resource = int(row[0]) if row else 0
                    if current_resource < qty:
                        return {
                            "fail": True,
                            "resource": resource,
                            "current_amount": current_resource,
                            "difference": current_resource - qty,
                        }

                # --- All checks passed — now deduct all resources ---
                for resource, amount in resources_list:
                    qty = amount * wantedUnits
                    resource_id = _res_id_map.get(resource)
                    db.execute(
                        (
                            "UPDATE user_economy SET quantity = quantity - %s "
                            "WHERE user_id = %s AND resource_id = %s AND "
                            "quantity >= %s RETURNING quantity"
                        ),
                        (qty, cId, resource_id, qty),
                    )
                    if db.fetchone() is None:
                        # Should not happen after pre-check, but guard anyway
                        return {
                            "fail": True,
                            "resource": resource,
                            "current_amount": 0,
                            "difference": -qty,
                        }

            elif way == "sell":
                for resource, amount in resources_list:
                    qty = amount * wantedUnits
                    resource_id = _res_id_map.get(resource)
                    if not resource_id:
                        continue

                    # Increment resource on sell
                    db.execute(
                        (
                            "UPDATE user_economy SET quantity = quantity + %s "
                            "WHERE user_id = %s AND resource_id = %s "
                            "RETURNING quantity"
                        ),
                        (qty, cId, resource_id),
                    )
                    db.fetchone()

        if way == "sell":
            if wantedUnits > currentUnits:  # Checks if user has enough units to sell
                return error(400, "You don't have enough units.")

            if units in ["land", "cityCount"]:
                unitUpd = f"UPDATE provinces SET {units}=%s WHERE id=%s"
                db.execute(unitUpd, ((currentUnits - wantedUnits), province_id))
            else:
                # Economy 2.0: decrement user_buildings for this province
                db.execute(
                    """
                    UPDATE user_buildings SET quantity = quantity - %s
                    WHERE user_id = %s
                      AND province_id = %s
                      AND building_id = (
                          SELECT building_id FROM building_dictionary WHERE name = %s
                      )
                    """,
                    (wantedUnits, cId, province_id, units),
                )

            # Capture gold before and perform atomic increment
            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_before_row = db.fetchone()
            if not gold_before_row:
                return error(500, "Nation data could not be found")
            gold_before = gold_before_row[0] or 0

            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (totalPrice, cId),
            )

            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_after_row = db.fetchone()
            gold_after = (gold_after_row[0] or 0) if gold_after_row else gold_before

            # Audit the sell event
            db.execute(
                "INSERT INTO purchase_audit (user_id, province_id, unit, units, "
                "gold_before, gold_after, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    cId,
                    province_id,
                    units,
                    wantedUnits,
                    gold_before,
                    gold_after,
                    f"sell_{units}",
                ),
            )

            # If purchase/sell is large, send a Sentry message (env-controlled)
            try:
                THRESH = int(os.getenv("PURCHASE_SENTRY_THRESHOLD", "1000000"))
                diff = abs(gold_after - gold_before)
                if diff >= THRESH:
                    try:
                        import sentry_sdk

                        with sentry_sdk.push_scope() as scope:
                            scope.set_extra("user_id", cId)
                            scope.set_extra("province_id", province_id)
                            scope.set_extra("unit", units)
                            scope.set_extra("units", wantedUnits)
                            scope.set_extra("gold_before", gold_before)
                            scope.set_extra("gold_after", gold_after)
                            msg = (
                                f"Large sell: {units} x{wantedUnits} by user {cId} "
                                f"({diff} gold)"
                            )
                            sentry_sdk.capture_message(msg)
                    except Exception:
                        pass
            except Exception:
                pass

            resource_stuff(resources_data, way)

        elif way == "buy":
            if units in ["land", "cityCount"]:
                if totalPrice > gold:
                    shortfall = totalPrice - gold
                    return error(
                        400,
                        f"Not enough money: {units} cost {totalPrice:,} gold, "
                        f"you have {gold:,} (missing {shortfall:,}).",
                    )

                res_error = resource_stuff(resources_data, way)
                if res_error:
                    missing_count = res_error["difference"] * -1
                    missing_res = res_error["resource"]
                    return error(
                        400,
                        f"Not enough {missing_res}: missing {missing_count:,}. "
                        f"Produce or buy on the market before building.",
                    )

                db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
                gold_before_row = db.fetchone()
                if not gold_before_row:
                    return error(500, "Nation data could not be found")
                gold_before = gold_before_row[0] or 0

                db.execute(
                    "UPDATE stats SET gold=gold-%s WHERE id=(%s)",
                    (totalPrice, cId),
                )

                db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
                gold_after_row = db.fetchone()
                gold_after = (
                    (gold_after_row[0] or 0) if gold_after_row else gold_before
                )

                updStat = f"UPDATE provinces SET {units}=%s WHERE id=%s"
                db.execute(updStat, ((currentUnits + wantedUnits), province_id))

                db.execute(
                    "INSERT INTO purchase_audit (user_id, province_id, unit, units, "
                    "gold_before, gold_after, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        cId,
                        province_id,
                        units,
                        wantedUnits,
                        gold_before,
                        gold_after,
                        f"buy_{units}",
                    ),
                )
            else:
                try:
                    purchase_building(
                        db,
                        cId,
                        int(province_id),
                        units,
                        wantedUnits,
                    )
                except BuildingPurchaseError as exc:
                    return error(400, str(exc))

        if way == "buy":
            rev_type = "expense"
        elif way == "sell":
            rev_type = "revenue"

        name = f"{way.capitalize()}ing {wantedUnits} {units} in a province."
        description = ""

        db.execute(
            (
                "INSERT INTO revenue (user_id, type, name, description, "
                "date, resource, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            ),
            (
                cId,
                rev_type,
                name,
                description,
                get_date(),
                units,
                wantedUnits,
            ),
        )

        # Invalidate caches for this user so UI and influence calculations reflect
        # the recent changes immediately
        try:
            invalidate_user_cache(cId)
        except Exception:
            pass

        # Also invalidate page-level caches (provinces list and province pages)
        # so the UI reflects the new units/land immediately instead of waiting
        # for TTL expiry.
        try:
            from database import query_cache, invalidate_view_cache

            query_cache.invalidate(pattern=f"provinces_{cId}_")
            query_cache.invalidate(pattern=f"province_{cId}_")
            # Invalidate the HTML response caches so the redirect serves fresh data
            invalidate_view_cache("province", user_id=cId)
            invalidate_view_cache("provinces", user_id=cId)
        except Exception:
            pass

    # Cache-bust parameter ensures the redirect doesn't hit a stale cached
    # response (can happen when multiple replicas keep separate in-memory caches).
    from time import time as _now

    action = "Sold" if way == "sell" else "Purchased"
    unit_display = units.replace("_", " ").title()
    flash(f"{action}: {unit_display}")
    return redirect(f"/province/{province_id}?_={int(_now())}")


# ---------------------------------------------------------------------------
# Mass Purchase (Discord #suggestions: mohammad20891 2026-09-08, and the
# 2026-09-27 follow-up asking for cities/land plus "bring each up to X").
# ---------------------------------------------------------------------------

MASS_LAND_CITY_UNITS = ("cityCount", "land")
# Sanity ceiling per province per submit, so a typo can't request billions.
MASS_PURCHASE_MAX_PER_PROVINCE = 100_000


def _normalize_mass_unit(raw):
    """Map the submitted unit name to its canonical key. Buildings are
    lowercase; cityCount keeps its camelCase column name."""
    raw = (raw or "").strip()
    if raw.lower() == "citycount":
        return "cityCount"
    return raw.lower()


def _parse_mass_request(get):
    """Validate the shared (unit, mode, quantity, province ids) inputs.
    `get(name)` / `getlist` come from either the form or a JSON body.
    Returns (params dict, error message or None)."""
    unit = _normalize_mass_unit(get("building"))
    mode = get("purchase_type") or "add"
    if mode not in ("add", "target"):
        mode = "add"
    try:
        quantity = int(get("quantity"))
    except (TypeError, ValueError):
        return None, "Enter a valid amount."
    if quantity < 1:
        return None, "Amount must be at least 1."
    if quantity > MASS_PURCHASE_MAX_PER_PROVINCE:
        return None, f"Amount can be at most {MASS_PURCHASE_MAX_PER_PROVINCE:,}."
    if unit not in MASS_LAND_CITY_UNITS and (
        f"{unit}_price" not in variables.PROVINCE_UNIT_PRICES
    ):
        return None, "Pick something to buy."
    return {"unit": unit, "mode": mode, "quantity": quantity}, None


def _plan_mass_purchase(db, user_id, unit, mode, quantity, province_ids, lock):
    """Work out, per selected province the user owns, how many `unit` to buy
    and what it costs. Pricing goes through the exact same functions the
    single-province buy route uses (land_city_purchase_cost / get_build_cost),
    so a mass buy never costs more or less than doing it one by one.

    With lock=True the province rows are locked (FOR UPDATE, id order) so the
    counts can't change between planning and buying. Must run inside the
    request transaction (get_request_cursor is non-autocommit).
    """
    from app_core.economy.building_costs import land_city_purchase_cost
    from app_core.economy.building_purchase import _load_policies

    lock_sql = " FOR UPDATE" if lock else ""
    db.execute(
        "SELECT id, provinceName, CAST(cityCount AS INTEGER), land "
        "FROM provinces WHERE userId = %s AND id = ANY(%s) ORDER BY id"
        + lock_sql,
        (user_id, province_ids),
    )
    rows = db.fetchall()
    policies = _load_policies(db, user_id)

    existing = {}
    if unit not in MASS_LAND_CITY_UNITS and mode == "target" and rows:
        db.execute(
            """
            SELECT ub.province_id, COALESCE(SUM(ub.quantity), 0)
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s AND bd.name = %s AND ub.province_id = ANY(%s)
            GROUP BY ub.province_id
            """,
            (user_id, unit, [r[0] for r in rows]),
        )
        existing = {pid: int(q or 0) for pid, q in db.fetchall()}

    unit_gold = 0
    unit_resources = {}
    if unit not in MASS_LAND_CITY_UNITS:
        cost = get_build_cost(unit, policies)
        unit_gold = int(cost["gold"])
        unit_resources = dict(cost["resources"] or {})

    plan = []
    for pid, pname, cities, land in rows:
        if unit == "cityCount":
            current = int(cities or 0)
        elif unit == "land":
            current = int(land or 0)
        else:
            current = existing.get(pid, 0)
        num = quantity if mode == "add" else quantity - current
        if num <= 0:
            continue
        if unit in MASS_LAND_CITY_UNITS:
            gold = land_city_purchase_cost(unit, current, num, policies)
        else:
            gold = unit_gold * num
        plan.append(
            {"id": pid, "name": pname, "current": current, "num": num, "gold": gold}
        )

    resources_total = {
        res: int(per) * sum(p["num"] for p in plan)
        for res, per in unit_resources.items()
    }
    return {
        "owned": {r[0]: r[1] for r in rows},
        "plan": plan,
        "total_gold": sum(p["gold"] for p in plan),
        "total_units": sum(p["num"] for p in plan),
        "resources": resources_total,
    }


@bp.route("/mass_purchase/preview", methods=["POST"])
@login_required
def mass_purchase_preview():
    """Read-only total for the Mass Purchase form (no locks, no writes)."""
    cId = session["user_id"]
    data = request.get_json(silent=True) or {}
    params, err = _parse_mass_request(data.get)
    if err:
        return jsonify({"error": err}), 400
    province_ids = [
        int(p) for p in (data.get("province_ids") or []) if str(p).isdigit()
    ]
    if not province_ids:
        return jsonify({"error": "Select at least one province."}), 400

    with get_request_cursor() as db:
        result = _plan_mass_purchase(
            db, cId, params["unit"], params["mode"], params["quantity"],
            province_ids, lock=False,
        )
        db.execute("SELECT gold FROM stats WHERE id = %s", (cId,))
        gold_row = db.fetchone()
    gold = int(gold_row[0] or 0) if gold_row else 0

    return jsonify(
        {
            "total_cost": result["total_gold"],
            "total_units": result["total_units"],
            "provinces": len(result["plan"]),
            "resources": result["resources"],
            "gold": gold,
            "affordable": result["total_gold"] <= gold,
        }
    )


def _mass_buy_land_city(db, cId, unit, mode, quantity, province_ids):
    """All-or-nothing land/city purchase across provinces. Returns
    (bought_in, total_spent, owned, error message or None)."""
    # Lock order: provinces (id order) then stats -- same order
    # purchase_building uses, so concurrent buys can't deadlock each other.
    result = _plan_mass_purchase(
        db, cId, unit, mode, quantity, province_ids, lock=True
    )
    owned, plan, total = result["owned"], result["plan"], result["total_gold"]
    if not owned:
        return 0, 0, owned, "Select at least one province."
    if not plan:
        return 0, 0, owned, "Nothing to buy: every selected province is already at that amount."

    db.execute("SELECT gold FROM stats WHERE id = %s FOR UPDATE", (cId,))
    gold_row = db.fetchone()
    if not gold_row:
        return 0, 0, owned, "Nation data could not be found."
    gold_before = int(gold_row[0] or 0)
    if total > gold_before:
        return 0, 0, owned, (
            f"Not enough money: this costs {total:,} gold, you have "
            f"{gold_before:,} (missing {total - gold_before:,}). Nothing was bought."
        )

    # One atomic, conditional deduction for the whole order.
    db.execute(
        "UPDATE stats SET gold = gold - %s WHERE id = %s AND gold >= %s RETURNING gold",
        (total, cId, total),
    )
    row = db.fetchone()
    if row is None:
        raise BuildingPurchaseError("You don't have enough money.")

    column = "cityCount" if unit == "cityCount" else "land"
    running_before = gold_before
    for p in plan:
        db.execute(
            f"UPDATE provinces SET {column} = {column} + %s WHERE id = %s AND userId = %s",
            (p["num"], p["id"], cId),
        )
        db.execute(
            "INSERT INTO purchase_audit (user_id, province_id, unit, units, "
            "gold_before, gold_after, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cId, p["id"], unit, p["num"], running_before,
             running_before - p["gold"], f"mass_buy_{unit}"),
        )
        running_before -= p["gold"]
        db.execute(
            "INSERT INTO revenue (user_id, type, name, description, date, "
            "resource, amount) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (cId, "expense", f"Buying {p['num']} {unit} in a province.", "",
             get_date(), unit, p["num"]),
        )
    return len(plan), total, owned, None


def _mass_buy_buildings(db, cId, unit, mode, quantity, province_ids):
    """Per-province building purchase (each province succeeds or fails on
    its own, like before). Each province runs in its own SAVEPOINT so a
    failure halfway through purchase_building (e.g. resources deducted,
    then gold short) can't leave a partial deduction behind."""
    result = _plan_mass_purchase(
        db, cId, unit, mode, quantity, province_ids, lock=False
    )
    owned = result["owned"]
    bought_in, total_spent, failures = 0, 0, []
    for p in result["plan"]:
        db.execute("SAVEPOINT mass_buy_building")
        try:
            res = purchase_building(db, cId, p["id"], unit, p["num"])
            db.execute("RELEASE SAVEPOINT mass_buy_building")
            bought_in += 1
            total_spent += res["gold_spent"]
        except BuildingPurchaseError as exc:
            db.execute("ROLLBACK TO SAVEPOINT mass_buy_building")
            failures.append(f"{p['name']}: {exc}")
    if owned and not result["plan"]:
        failures.append("every selected province is already at that amount")
    return bought_in, total_spent, owned, failures


@bp.route("/mass_purchase/buy", methods=["POST"])
@login_required
@require_post_origin
def mass_purchase_buy():
    """Buy the same thing across several provinces in one submit.

    - Buildings: each province is attempted independently (one province out
      of slots doesn't block the rest), same as the first version.
    - Cities / land: one total, one atomic balance check + deduction, and
      either every province gets its purchase or none do.
    Both support "add N to each" and "bring each up to N".
    """
    cId = session["user_id"]
    params, err = _parse_mass_request(request.form.get)
    if err:
        flash(err, "error")
        return redirect("/mass_purchase")
    unit, mode, quantity = params["unit"], params["mode"], params["quantity"]

    province_ids = [
        int(p) for p in request.form.getlist("province_ids") if p.isdigit()
    ]
    if not province_ids:
        flash("Select at least one province.", "error")
        return redirect("/mass_purchase")

    failures = []
    with get_request_cursor() as db:
        if unit in MASS_LAND_CITY_UNITS:
            db.execute("SAVEPOINT mass_buy_land_city")
            try:
                bought_in, total_spent, owned, msg = _mass_buy_land_city(
                    db, cId, unit, mode, quantity, province_ids
                )
                db.execute("RELEASE SAVEPOINT mass_buy_land_city")
            except BuildingPurchaseError as exc:
                db.execute("ROLLBACK TO SAVEPOINT mass_buy_land_city")
                bought_in, total_spent, owned = 0, 0, {}
                failures.append(f"{exc} Nothing was bought.")
            except Exception:
                db.execute("ROLLBACK TO SAVEPOINT mass_buy_land_city")
                raise
            if msg:
                failures.append(msg)
        else:
            bought_in, total_spent, owned, failures = _mass_buy_buildings(
                db, cId, unit, mode, quantity, province_ids
            )

    try:
        invalidate_user_cache(cId)
        from database import query_cache, invalidate_view_cache

        query_cache.invalidate(pattern=f"provinces_{cId}_")
        query_cache.invalidate(pattern=f"province_{cId}_")
        invalidate_view_cache("province", user_id=cId)
        invalidate_view_cache("provinces", user_id=cId)
    except Exception:
        pass

    unit_display = {"cityCount": "Cities", "land": "Land"}.get(
        unit, unit.replace("_", " ").title()
    )
    if bought_in:
        how = f"up to {quantity}" if mode == "target" else f"{quantity}"
        flash(
            f"Bought {unit_display} ({how} each) in {bought_in} of "
            f"{len(owned)} selected provinces (spent {total_spent:,} gold)."
        )
    if failures:
        # Cap how many per-province errors get flashed.
        shown = failures[:8]
        more = len(failures) - len(shown)
        msg = ("Skipped -- " if bought_in else "") + "; ".join(shown)
        if more > 0:
            msg += f"; and {more} more"
        # "error" makes the toast sticky (see layout.html) -- ieb read the
        # per-province skip reasons too slowly before a 5s toast vanished.
        flash(msg, "error")

    return redirect("/mass_purchase")


from flask import jsonify
from database import get_request_cursor

# Add to province.py
# Identical for every visitor (no per-user data), but was re-running 7
# sequential queries -- including an ORDER BY RANDOM() full scan -- on every
# single call, holding a pooled DB connection the whole time. Client polls
# this every 60s per tab (static/script.js), and with many concurrent
# players that was enough concurrent connection-holding to exhaust the
# pool (see "Database connection pool exhausted" in prod logs 2026-09-02).
# A short shared cache collapses all those polls into one DB round-trip
# per window regardless of player count.
@bp.route("/api/global_events", methods=["GET"])
@cache_response(ttl_seconds=45, public=True)
def get_global_events():
    events = [
        "🚨 BREAKING NEWS: New Balance Update! First Province now costs $2M! New player Grace Period active (no starvation)! Lumber is now a core building requirement for Tier 2 buildings. Steel Mills & Aluminium Refineries cost 50% less! 🚨"
    ] * 5  # Duplicate it a few times so it shows up frequently
    try:
        with get_request_cursor() as db:
            # 1. Newest nations
            db.execute("SELECT username FROM users ORDER BY id DESC LIMIT 8")
            for res in db.fetchall():
                events.append(f"A new nation, {res[0]}, has risen to power in Terra.")
            
            # 2. Newest provinces
            db.execute("SELECT provinceName FROM provinces ORDER BY id DESC LIMIT 8")
            for res in db.fetchall():
                events.append(f"New territory established: the province of {res[0]} has been settled.")
                
            # 3. Market shortages (resources with 0 quantity)
            db.execute("""
                SELECT rd.name 
                FROM resource_dictionary rd
                LEFT JOIN global_market gm ON rd.resource_id = gm.resource_id
                WHERE gm.quantity IS NULL OR gm.quantity = 0
                LIMIT 5
            """)
            for row in db.fetchall():
                resource_name = str(row[0]).replace("_", " ").title()
                events.append(f"Global market crisis: {resource_name} supplies have been completely exhausted!")
                
            # 4. Recent treaties/alliances
            db.execute("SELECT name FROM colnames ORDER BY id DESC LIMIT 5")
            for res in db.fetchall():
                events.append(f"Diplomatic breakthrough: The {res[0]} coalition gathers strength.")
                
            # 5. Battles/Wars
            db.execute("""
                SELECT u1.username, u2.username 
                FROM wars 
                JOIN users u1 ON wars.attacker = u1.id 
                JOIN users u2 ON wars.defender = u2.id 
                ORDER BY wars.id DESC LIMIT 5
            """)
            for res in db.fetchall():
                events.append(f"Conflict erupts! {res[0]} has declared war on {res[1]}.")

            # 5b. World Affairs feed - sabotage, aid, treaties, alliances,
            # bounty claims, coalition treaties (see app_core/world_affairs)
            from app_core.world_affairs.repositories import get_recent_messages
            events.extend(get_recent_messages(db, 10))

            # 6. Nation Projects / Tech
            db.execute("""
                SELECT u.username, td.name 
                FROM user_tech ut 
                JOIN tech_dictionary td ON ut.tech_id = td.tech_id 
                JOIN users u ON ut.user_id = u.id 
                ORDER BY u.id DESC, td.tech_id DESC LIMIT 8
            """)
            for res in db.fetchall():
                tech_name = str(res[1]).replace("_", " ").title()
                events.append(f"Scientific breakthrough: {res[0]} has developed {tech_name}.")
                
            # 7. Dynamic Weather Reports
            weather_conditions = [
                "Heavy thunderstorms", "Clear skies and sunshine", "Dense fog",
                "Torrential rain", "Unprecedented heatwaves", "Brisk winds",
                "Light drizzle", "Overcast skies", "A sudden cold snap",
                "Blizzard conditions", "Dust storms", "Perfect harvest weather"
            ]
            import random
            db.execute("SELECT provinceName FROM provinces ORDER BY RANDOM() LIMIT 10")
            for p in db.fetchall():
                condition = random.choice(weather_conditions)
                events.append(f"Weather Update: {condition} reported in the province of {p[0]}.")
                
            # 8. Guaranteed World-Building Filler (to prevent empty gaps)
            from flavor_text import GENERIC_FLAVOR_EVENTS
            try:
                from flavor_text_2 import GENERIC_FLAVOR_EVENTS_2
            except ImportError:
                GENERIC_FLAVOR_EVENTS_2 = []
            try:
                from flavor_text_3 import GENERIC_FLAVOR_EVENTS_3
            except ImportError:
                GENERIC_FLAVOR_EVENTS_3 = []
                
            generic_filler = GENERIC_FLAVOR_EVENTS + GENERIC_FLAVOR_EVENTS_2 + GENERIC_FLAVOR_EVENTS_3
            events.extend(random.sample(generic_filler, 30))

            # Shuffle all events so they mix nicely
            random.shuffle(events)

    except Exception as e:
        print("Error fetching global events:", e)
        pass

    # Escape every event string right before it leaves the server: this list
    # mixes hardcoded/trusted copy with plenty of user-controlled DB values
    # (usernames, province names, coalition names, world-affairs messages)
    # that have no character restriction at signup/rename. The client
    # inserts these strings into the DOM via innerHTML with no sanitization
    # of its own, so an unescaped value here is a stored-XSS payload that
    # would fire in every visitor's browser automatically on page load.
    import html as _html
    events = [_html.escape(str(e)) for e in events]

    return jsonify({"events": events})


