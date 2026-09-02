from flask import request, render_template, session, redirect, jsonify
from helpers import login_required
from helpers import get_influence, error, is_theme_v2_enabled
from database import invalidate_view_cache, reuse_or_new_cursor
import os
import variables
from dotenv import load_dotenv
import logging
from collections import defaultdict
from app_core.policies.services import get_user_policies
from wars.service import target_data
import math
from database import (
    get_request_cursor,
    cache_response,
    rollback_db_cursor,
    get_coalition_members_table,
)

load_dotenv()

# App config will be set when routes are registered


# TODO: rewrite this function for fucks sake
def get_econ_statistics(cId, db=None):
    from database import query_cache
    from psycopg2.extras import RealDictCursor

    # Check cache first
    cache_key = f"econ_stats_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with reuse_or_new_cursor(db, cursor_factory=RealDictCursor) as dbdict:
        total = {name: 0 for name in variables.NEW_INFRA.keys()}
        dbdict.execute(
            """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS total_quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
            GROUP BY bd.name
            """,
            (cId,),
        )
        for row in dbdict.fetchall() or []:
            bname = row.get("name")
            qty = row.get("total_quantity") or 0
            if bname:
                total[bname] = qty

    expenses = {}
    expenses = defaultdict(lambda: defaultdict(lambda: 0), expenses)

    def get_unit_type(unit):
        for type_name, buildings in variables.INFRA_TYPE_BUILDINGS.items():
            if unit in buildings:
                return type_name

    def check_for_resource_upkeep(unit, amount):
        try:
            convert_minus_list = variables.INFRA[f"{unit}_convert_minus"]
        except KeyError:
            return False

        unit_type = get_unit_type(unit)
        for entry in convert_minus_list:
            for resource, cost_per_unit in entry.items():
                expenses[unit_type][resource] += cost_per_unit * amount
        return True

    def check_for_monetary_upkeep(unit, amount):
        try:
            operating_costs = int(variables.INFRA[f"{unit}_money"]) * amount
        except KeyError:
            return
        unit_type = get_unit_type(unit)
        if not unit_type:
            return
        expenses[unit_type]["money"] += operating_costs

    for unit, amount in total.items():
        if amount != 0 and amount is not None:
            check_for_resource_upkeep(unit, amount)
            check_for_monetary_upkeep(unit, amount)

    # Military maintenance upkeep (rations for troops, etc.). The global tick
    # deducts this every hour from user_economy, but it was missing from the
    # revenue display — so a nation feeding a large army saw a net-positive
    # food number while actually running a deficit. Mirror the tick's query.
    with reuse_or_new_cursor(db, cursor_factory=RealDictCursor) as mil_db:
        mil_db.execute(
            """
            SELECT rd.name AS resource, SUM(um.quantity * ud.maintenance_cost_amount) AS required
            FROM user_military um
            JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
            JOIN resource_dictionary rd ON rd.resource_id = ud.maintenance_cost_resource_id
            WHERE um.user_id = %s
              AND um.quantity > 0
              AND ud.maintenance_cost_resource_id IS NOT NULL
              AND ud.maintenance_cost_amount > 0
            GROUP BY rd.name
            """,
            (cId,),
        )
        for row in mil_db.fetchall() or []:
            required = int(row.get("required") or 0)
            if required:
                expenses["military"][row["resource"]] += required

    # Cache the result
    query_cache.set(cache_key, expenses)
    return expenses


def format_econ_statistics(statistics):
    formatted = {}
    formatted = defaultdict(lambda: "", formatted)

    for unit_type, unit_type_data in statistics.items():
        unit_type_data = list(unit_type_data.items())
        idx = 0
        for resource, amount in unit_type_data:
            amount = "{:,}".format(amount)

            if idx != len(unit_type_data) - 1:
                expense_string = f"{amount} {resource}, "
            else:
                expense_string = f"{amount} {resource}"

            if resource == "money":
                expense_string = "$" + expense_string.replace(" money", "")

            formatted[unit_type] += expense_string
            idx += 1

    return formatted


def get_revenue(cId, db=None):
    from database import query_cache
    from app_core.game_ticks.population import find_unit_category

    # Check cache first - expensive calculation
    cache_key = f"revenue_{cId}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    with reuse_or_new_cursor(db, read_only=True) as db:
        # Prefetch province ids, land, productivity, population, and the
        # demographic split (needed below to mirror the actual tax_income
        # tick's age-weighted formula, not just the flat population).
        db.execute(
            "SELECT id, land, productivity, population, "
            "pop_children, pop_working, pop_elderly FROM provinces WHERE userid=%s",
            (cId,),
        )
        province_rows = db.fetchall()
        provinces = [row[0] for row in province_rows]

        # Load unlocked upgrades so the projection reflects project effects
        # (e.g. Stronger Explosives +45% bauxite). The hourly tick applies these
        # but the display used to ignore them, so a player's projection never
        # changed after buying a production project — player-reported.
        upgrades = {}
        try:
            db.execute(
                """
                SELECT td.name FROM user_tech ut
                JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                WHERE ut.user_id = %s AND ut.is_unlocked = TRUE
                """,
                (cId,),
            )
            _tech_to_legacy = {
                "better_engineering": "betterengineering",
                "advanced_machinery": "advancedmachinery",
                "stronger_explosives": "strongerexplosives",
                "integrated_steelmaking": "integratedsteelmaking",
                "cheaper_materials": "cheapermaterials",
                "online_shopping": "onlineshopping",
                "larger_forges": "largerforges",
                "electric_arc_furnace": "electricarcfurnace",
                "automation_integration": "automationintegration",
            }
            for (tech_name,) in db.fetchall() or []:
                legacy = _tech_to_legacy.get(tech_name)
                if legacy:
                    upgrades[legacy] = True
        except Exception:
            upgrades = {}
        land_by_id = {row[0]: row[1] for row in province_rows}
        prod_by_id = {row[0]: row[2] for row in province_rows}

        # Fetched here (not just before the tax calc further down) so the
        # building loop below can also apply POLICY_INDUSTRIAL_SUBSIDIES to
        # operating_costs, mirroring the real tick.
        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (cId,))
            policies_row = db.fetchone()
            policies = policies_row[0] if policies_row else []
        except Exception:
            policies = []

        revenue = {"gross": {}, "gross_theoretical": {}, "net": {}}

        infra = variables.NEW_INFRA
        resources = list(variables.RESOURCES)
        resources.extend(["money", "energy"])
        for resource in resources:
            revenue["gross"][resource] = 0
            revenue["gross_theoretical"][resource] = 0
            revenue["net"][resource] = 0

        # Batch fetch all building data PER PROVINCE
        proinfra_by_id = {}
        if provinces:
            province_ids = list(provinces)
            db.execute(
                """
                SELECT ub.province_id, bd.name, ub.quantity
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s AND ub.province_id = ANY(%s)
                """,
                (cId, province_ids),
            )
            for row in db.fetchall():
                prov_id, building_name, quantity = row
                if prov_id not in proinfra_by_id:
                    proinfra_by_id[prov_id] = {}
                proinfra_by_id[prov_id][building_name] = quantity or 0

        # Fetch gold, rations, and CG in a single combined query
        db.execute(
            """
            SELECT
                COALESCE(s.gold, 0) AS gold,
                COALESCE(r.quantity, 0) AS rations,
                COALESCE(cg.quantity, 0) AS consumer_goods
            FROM stats s
            LEFT JOIN (
                SELECT ue.quantity FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = %s AND rd.name = 'rations'
            ) r ON TRUE
            LEFT JOIN (
                SELECT ue.quantity FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = %s AND rd.name = 'consumer_goods'
            ) cg ON TRUE
            WHERE s.id = %s
            """,
            (cId, cId, cId),
        )
        econ_row = db.fetchone()
        current_money = econ_row[0] if econ_row else 0
        current_rations = econ_row[1] if econ_row else 0
        consumer_goods = int(econ_row[2]) if econ_row else 0

        # Simulated funds used while computing `net`; do not mutate DB
        simulated_funds = current_money

        for province in provinces:
            buildings = proinfra_by_id.get(province)
            if buildings is None:
                buildings = {}

            for building, build_count in buildings.items():
                if building == "id":
                    continue
                if build_count is None or build_count == 0:
                    continue
                if building not in infra:
                    continue

                operating_costs = infra[building]["money"] * build_count

                # Same upkeep discounts app_core/game_ticks/revenue.py applies
                # to the real tick -- missing here meant a subsidies/tech
                # player's Revenue tab showed buildings as unaffordable (or
                # more expensive than they really are) more often than
                # reality, understating projected net production. Same bug
                # shape as the tax/CG fixes above, found by sweeping for
                # other duplicated tick formulas.
                unit_category = find_unit_category(building)
                if unit_category == "industry" and upgrades.get("cheapermaterials"):
                    operating_costs *= 0.8
                if building == "malls" and upgrades.get("onlineshopping"):
                    operating_costs *= 0.7
                if (
                    variables.POLICY_INDUSTRIAL_SUBSIDIES in policies
                    and building in variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS
                ):
                    operating_costs *= variables.POLICY_SUBSIDIES_UPKEEP_REDUCTION

                # Add to gross/net resource production only if this building would
                # actually operate given the player's money. We keep `gross` and
                # `gross_theoretical` as unconditional projections, but `net`
                # reflects a simple money-constrained simulation similar to the
                # actual task runner so UI `net` is consistent with what will
                # actually happen.
                will_operate = simulated_funds >= operating_costs

                if will_operate:
                    simulated_funds -= operating_costs
                    revenue["net"]["money"] -= operating_costs

                plus = infra[building].get("plus", {})
                for resource, amount in plus.items():
                    if building == "farms":
                        land = land_by_id.get(province, 0)
                        amount += land * variables.LAND_FARM_PRODUCTION_ADDITION

                    # BETTER ENGINEERING (mirrors revenue.py's flat +6
                    # energy/reactor -- another gap found sweeping for
                    # duplicated tick formulas).
                    if (
                        building == "nuclear_reactors"
                        and resource == "energy"
                        and upgrades.get("betterengineering")
                    ):
                        amount += 6

                    # Compute theoretical production (no productivity multiplier)
                    theoretical_total = build_count * amount

                    # Apply productivity multiplier to match actual generation behavior
                    productivity = prod_by_id.get(province, 50)
                    if productivity is not None:
                        multiplier = (
                            1
                            + (productivity - 50)
                            * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER
                        )
                    else:
                        multiplier = 1

                    # Production project multipliers (mirror app_core/game_ticks/
                    # revenue.py so the projection matches actual generation).
                    if building == "bauxite_mines" and upgrades.get("strongerexplosives"):
                        multiplier += 0.45
                    if building == "farms" and upgrades.get("advancedmachinery"):
                        multiplier += 0.5
                    if building == "steel_mills" and upgrades.get("integratedsteelmaking"):
                        multiplier += 0.36

                    adjusted_total = build_count * amount * multiplier
                    # Normalize to integer to mirror production rounding
                    adjusted_total = math.ceil(adjusted_total)

                    # Record the theoretical and gross projections
                    revenue["gross_theoretical"][resource] += theoretical_total
                    revenue["gross"][resource] += adjusted_total

                    # Only add to `net` if the building will operate
                    if will_operate:
                        revenue["net"][resource] += adjusted_total

                minus = infra[building].get("minus", {})
                for resource, amount in minus.items():
                    # Input-resource-consumption multipliers, mirroring
                    # revenue.py's per_unit_minus adjustments (same
                    # sequential-if, stackable structure as the real tick --
                    # more gaps found sweeping for duplicated formulas).
                    if building == "steel_mills":
                        if upgrades.get("largerforges"):
                            amount *= 0.7
                        if upgrades.get("integratedsteelmaking"):
                            amount *= 1.36
                        if upgrades.get("electricarcfurnace"):
                            amount *= 0.5
                    if building == "component_factories" and upgrades.get(
                        "automationintegration"
                    ):
                        amount *= 0.75

                    total = build_count * amount
                    # Only subtract upkeep from net if building operates
                    if will_operate:
                        revenue["net"][resource] -= total

        # Reuse already-fetched province data for tax income calculation.
        # province_rows is (id, land, productivity, population, pop_children,
        # pop_working, pop_elderly).
        ti_provinces = [
            (row[3], row[1], row[4], row[5], row[6]) for row in province_rows
        ]  # (pop, land, pc, pw, pe)

        # Mirror app_core/game_ticks/taxes.py's has_demographic_data gate:
        # only use the age-weighted formula once every province actually has
        # a demographic split, else fall back to flat population exactly
        # like the real tick does.
        has_demographic_data = all(
            pc is not None and pw is not None and pe is not None
            for _, _, pc, pw, pe in ti_provinces
        )

        ti_money = 0
        if ti_provinces:
            for population, land, pc, pw, pe in ti_provinces:
                land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
                if land_multiplier > 1:
                    land_multiplier = 1
                base_multiplier = variables.DEFAULT_TAX_INCOME
                if policies and 1 in policies:
                    base_multiplier *= 1.01
                if policies and 6 in policies:
                    base_multiplier *= 0.98
                if policies and 4 in policies:
                    base_multiplier *= 0.98
                multiplier = base_multiplier + (base_multiplier * land_multiplier)
                # Children pay no tax and elderly pay a reduced rate --
                # same DEMO_TAX_MULTIPLIER weighting the tax_income tick
                # actually applies. Previously this projection always used
                # raw population, so it silently never reflected the Aug 30
                # tax rebalance even though the real tick did (player-reported).
                if variables.FEATURE_DEMOGRAPHIC_TAX and has_demographic_data:
                    taxable_population = (
                        (pw or 0) * variables.DEMO_TAX_MULTIPLIER["pop_working"]
                        + (pc or 0) * variables.DEMO_TAX_MULTIPLIER["pop_children"]
                        + (pe or 0) * variables.DEMO_TAX_MULTIPLIER["pop_elderly"]
                    )
                else:
                    taxable_population = population
                ti_money += multiplier * taxable_population

            # CG tax multiplier — mirror the actual tax_income task logic.
            # When FEATURE_DEMOGRAPHIC_CONSUMPTION is enabled, use the
            # demographic-based CG need and distribution-capacity check;
            # otherwise fall back to the legacy population/CONSUMER_GOODS_PER
            # formula.
            if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
                # Demographic CG need (matches tax_income)
                total_cg_need = 0.0
                for row in province_rows:
                    pw = float(row[3]) if row[3] else 0.0  # population as proxy
                    # Use per-province demographic data if available
                    total_cg_need += (
                        pw * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_working"]
                    )
                # province_rows now carries per-province pc/pw/pe too, but
                # this aggregate query is left as-is (not broken, just
                # slightly redundant) to keep this fix scoped to the tax
                # calc above.
                db.execute(
                    "SELECT COALESCE(SUM(pop_working), 0) AS pw,"
                    "       COALESCE(SUM(pop_children), 0) AS pc,"
                    "       COALESCE(SUM(pop_elderly), 0) AS pe "
                    "FROM provinces WHERE userid = %s",
                    (cId,),
                )
                demo_row = db.fetchone()
                if demo_row:
                    pw_sum = float(demo_row[0] or 0)
                    pc_sum = float(demo_row[1] or 0)
                    pe_sum = float(demo_row[2] or 0)
                    # Same healthcare-policy adjustment taxes.py applies to
                    # the real tick (POLICY_UNIVERSAL_HEALTHCARE makes
                    # elderly consume +20% more CG) -- missing here meant
                    # this projection understated CG need, and therefore
                    # overstated the tax-multiplier outcome, for any player
                    # running that policy. Same bug shape as the tax-rate
                    # projection fix above, found by sweeping for other
                    # duplicated tick formulas.
                    elderly_cg_multiplier = (
                        variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
                        if variables.POLICY_UNIVERSAL_HEALTHCARE in policies
                        else 1.0
                    )
                    total_cg_need = (
                        pw_sum
                        * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_working"]
                        + pc_sum
                        * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_children"]
                        + pe_sum
                        * variables.DEMO_CONSUMER_GOODS_CONSUMPTION["pop_elderly"]
                        * elderly_cg_multiplier
                    )
                # Distribution capacity check
                db.execute(
                    "SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS qty "
                    "FROM user_buildings ub "
                    "JOIN building_dictionary bd "
                    "  ON bd.building_id = ub.building_id "
                    "WHERE ub.user_id = %s "
                    "  AND bd.name IN ("
                    "    'distribution_centers','malls',"
                    "    'general_stores','gas_stations'"
                    "  ) "
                    "GROUP BY bd.name",
                    (cId,),
                )
                dist_capacity = 0
                for drow in db.fetchall():
                    bname = drow[0]
                    qty = drow[1] or 0
                    cap = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING.get(
                        bname,
                        variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING_DEFAULT,
                    )
                    dist_capacity += qty * cap
                available_to_consume = min(consumer_goods, dist_capacity)
                if total_cg_need > 0:
                    if available_to_consume >= total_cg_need:
                        ti_money *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                    else:
                        cg_ratio = available_to_consume / total_cg_need
                        ti_money *= 1 + (0.5 * cg_ratio)
            else:
                total_pop_ti = sum(p for p, *_ in ti_provinces)
                max_cg = math.ceil(total_pop_ti / variables.CONSUMER_GOODS_PER)
                if consumer_goods != 0 and max_cg != 0:
                    if max_cg <= consumer_goods:
                        ti_money *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
                    else:
                        cg_multiplier = consumer_goods / max_cg
                        ti_money *= 1 + (0.5 * cg_multiplier)

        ti_money = math.floor(ti_money)

        # Deduct coalition tax so the displayed net matches what the player
        # actually receives (tax_income task deducts this before crediting).
        coalition_tax_deducted = 0
        members_tbl = get_coalition_members_table()
        if members_tbl:
            try:
                db.execute(
                    f"SELECT cl.colid, COALESCE(cn.tax_rate, 0) AS tax_rate "
                    f"FROM {members_tbl} cl "
                    "JOIN colNames cn ON cn.id = cl.colid "
                    "WHERE cl.userid = %s AND COALESCE(cn.tax_rate, 0) > 0",
                    (cId,),
                )
                ctax_row = db.fetchone()
                if ctax_row:
                    tax_rate = ctax_row[1]
                    coalition_tax_deducted = int(ti_money * tax_rate / 100)
            except Exception:
                rollback_db_cursor(db)

        # Updates money
        revenue["gross"]["money"] += ti_money
        revenue["net"]["money"] += ti_money - coalition_tax_deducted
        if coalition_tax_deducted:
            revenue["coalition_tax"] = coalition_tax_deducted

        # Military maintenance upkeep (rations for soldiers, gasoline for
        # vehicles/aircraft/ships, components for spies). The global tick
        # deducts this every hour from user_economy, but it was missing here
        # — a nation feeding a large army/navy/air force saw a net-positive
        # resource number while actually running a deficit. Mirrors the query
        # already used in get_econ_statistics for the expenses breakdown.
        db.execute(
            """
            SELECT rd.name AS resource, SUM(um.quantity * ud.maintenance_cost_amount) AS required
            FROM user_military um
            JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
            JOIN resource_dictionary rd ON rd.resource_id = ud.maintenance_cost_resource_id
            WHERE um.user_id = %s
              AND um.quantity > 0
              AND ud.maintenance_cost_resource_id IS NOT NULL
              AND ud.maintenance_cost_amount > 0
            GROUP BY rd.name
            """,
            (cId,),
        )
        military_upkeep = {row[0]: int(row[1] or 0) for row in db.fetchall()}
        for resource, amount in military_upkeep.items():
            if resource == "rations":
                continue  # folded into the rations recompute below
            if resource in revenue["net"]:
                revenue["net"][resource] -= amount

        # Reuse already-fetched data for CG need calculation
        total_population = sum(row[3] or 0 for row in province_rows)
        if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
            citizen_cg_need = math.ceil(total_cg_need) if ti_provinces else 0
        else:
            citizen_cg_need = math.ceil(total_population / variables.CONSUMER_GOODS_PER)

        # Net consumer goods = gross production - citizen need
        # (gross already includes production from buildings that would operate)
        revenue["net"]["consumer_goods"] = (
            revenue["gross"]["consumer_goods"] - citizen_cg_need
        )

        # Use net rations production (respects gold check — farms can't operate at $0 gold).
        # Using gross here would hide starvation risk: display would show +282 rations
        # even though farms are offline, masking that the stockpile is actually depleting.
        prod_rations = revenue["net"]["rations"]
        # Calculate next turn rations inline using already-fetched data
        current_rations_for_calc = current_rations + prod_rations
        # Calculate consumption from already-fetched province_rows
        total_rations_needed = 0
        for row in province_rows:
            province_pop = row[3] if row[3] else 0  # index 3 is population
            province_consumption = province_pop // variables.RATIONS_PER
            if province_consumption < 1:
                province_consumption = 1
            total_rations_needed += province_consumption
        if total_rations_needed < 1:
            total_rations_needed = 1
        total_rations_needed += military_upkeep.get("rations", 0)
        new_rations = max(0, current_rations_for_calc - total_rations_needed)
        revenue["net"]["rations"] = new_rations - current_rations

        # Filter to only show resources with positive gross production
        # or non-zero net (for special cases like rations)
        # Keep `gross_theoretical` present so templates can always access it
        filtered_revenue = {
            "gross": revenue["gross"],
            "gross_theoretical": revenue["gross_theoretical"],
            "net": revenue["net"],
        }
        if "coalition_tax" in revenue:
            filtered_revenue["coalition_tax"] = revenue["coalition_tax"]

        # Cache the result for 60 seconds (revenue doesn't change often)
        query_cache.set(cache_key, filtered_revenue, ttl_seconds=60)

        return filtered_revenue


def next_turn_rations(cId, prod_rations):
    """Calculate next turn rations after consumption."""
    with get_request_cursor() as db:
        # Get current rations (normalized economy)
        db.execute(
            """
            SELECT ue.quantity
            FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id=%s AND rd.name='rations'
            """,
            (cId,),
        )
        rr = db.fetchone()
        current_rations = (rr[0] if rr and rr[0] is not None else 0) + prod_rations

        # Get population per province to calculate consumption correctly
        # (each province consumes at minimum 1 ration, matching population_growth task)
        db.execute(
            "SELECT population FROM provinces WHERE userid=%s",
            (cId,),
        )
        provinces = db.fetchall()

        # Calculate total consumption matching the population_growth task logic
        total_rations_needed = 0
        for (pop,) in provinces:
            province_pop = pop if pop else 0
            province_consumption = province_pop // variables.RATIONS_PER
            if province_consumption < 1:
                province_consumption = 1
            total_rations_needed += province_consumption

        # If no provinces, still need minimum 1
        if total_rations_needed < 1:
            total_rations_needed = 1

        # Calculate remaining rations after consumption
        remaining_rations = current_rations - total_rations_needed
        if remaining_rations < 0:
            remaining_rations = 0

        return int(remaining_rations)




def delete_news(id):
    with get_request_cursor() as db:
        db.execute("SELECT destination_id FROM news WHERE id=(%s)", (id,))
        news_row = db.fetchone()
        if not news_row:
            return "404"
        destination_id = news_row[0]
        if destination_id == session["user_id"]:
            db.execute("DELETE FROM news WHERE id=(%s)", (id,))
            return "200"
        else:
            return "403"


# The amount of consumer goods a player needs to fill up fully


def cg_need(user_id):
    with get_request_cursor() as db:
        db.execute("SELECT SUM(population) FROM provinces WHERE userid=%s", (user_id,))
        pop_row = db.fetchone()
        population = pop_row[0] if pop_row else None
        if population is None:
            population = 0

        # How many consumer goods are needed to feed a nation
        cg_needed = math.ceil(population / variables.CONSUMER_GOODS_PER)

        return cg_needed


@login_required
def my_country():
    user_id = session.get("user_id")
    return redirect(f"/country/id={user_id}")


def country(cId):
    from services.country_service import CountryService
    data = CountryService.get_country_profile(cId, session.get("user_id"))
    if isinstance(data, dict) and data.get("error"):
        return error(data["code"], data["msg"])

    can_invite_to_coalition = False
    viewer_id = session.get("user_id")
    if viewer_id and str(viewer_id) != str(cId) and not data.get("colId"):
        from database import get_request_cursor, get_coalition_members_table

        members_tbl = get_coalition_members_table()
        if members_tbl:
            with get_request_cursor() as db:
                db.execute(
                    f"SELECT role FROM {members_tbl} WHERE userid=%s", (viewer_id,)
                )
                row = db.fetchone()
                if row and row[0] in ("leader", "deputy_leader"):
                    can_invite_to_coalition = True

    template = "country_v2.html" if is_theme_v2_enabled("country") else "country.html"
    return render_template(
        template, can_invite_to_coalition=can_invite_to_coalition, **data
    )

def countries():
    from services.country_service import CountryService
    cId = session["user_id"]

    # Parse and coerce query params
    search = request.values.get("search", "").strip()
    lowerinf = request.values.get("lowerinf", type=float)
    upperinf = request.values.get("upperinf", type=float)
    province_range = request.values.get("province_range", default=0, type=int)
    sort = request.values.get("sort")
    sortway = request.values.get("sortway")
    page = request.values.get("page", default=1, type=int)
    # Allow users to choose page size: 50, 100, or 150
    per_page = request.values.get("per_page", default=50, type=int)
    if per_page not in [50, 100, 150]:
        per_page = 50

    if sort == "war_range":
        target = target_data(cId)
        lowerinf = float(target.get("lower", 0))
        upperinf = float(target.get("upper", 0))
        province_range = int(target.get("province_range", 0))

    data = CountryService.get_countries_paginated(
        cId=cId,
        search=search,
        lowerinf=lowerinf,
        upperinf=upperinf,
        province_range=province_range,
        sort=sort,
        sortway=sortway,
        page=page,
        per_page=per_page
    )

    template = "countries_v2.html" if is_theme_v2_enabled("countries") else "countries.html"
    return render_template(
        template,
        countries=data["countries"],
        current_user_id=cId,
        current_page=data["current_page"],
        total_pages=data["total_pages"],
        total_count=data["total_count"],
        per_page=per_page,
        sort=sort,
        sortway=sortway,
        search=search,
        lowerinf=lowerinf,
        upperinf=upperinf,
        province_range=province_range,
    )


def delete_news(id):
    from repositories.country_repository import CountryRepository
    CountryRepository.delete_news(id, session["user_id"])
    return redirect("/account")


def update_info():
    with get_request_cursor() as db:
        cId = session["user_id"]

        # Description changing. Only "None" (a legacy sentinel) skips the
        # update -- an empty string is a deliberate clear and must persist.
        description = request.form.get("description", "")

        if description != "None":
            db.execute(
                "UPDATE users SET description=%s WHERE id=%s", (description, cId)
            )

        # Name changing
        new_name = request.form.get("countryName", "").strip()
        if new_name and len(new_name) >= 3 and len(new_name) <= 20:
            db.execute("SELECT id FROM users WHERE username=%s AND id != %s", (new_name, cId))
            if db.fetchone():
                return error(400, "Nation name is already taken")
            db.execute("UPDATE users SET username=%s WHERE id=%s", (new_name, cId))

        # Flag changing
        ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg"]

        def allowed_file(filename):
            return (
                "." in filename
                and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
            )

        flag = request.files.get("flag_input")
        if flag and flag.filename:  # Check both file exists AND has a filename
            if not allowed_file(flag.filename):
                return error(400, "Bad flag file format")

            current_filename = flag.filename

            try:
                db.execute("SELECT flag FROM users WHERE id=(%s)", (cId,))
                flag_row = db.fetchone()
                current_flag = flag_row[0] if flag_row else None
                if not current_flag:
                    raise OSError("No existing flag")
                from flask import current_app

                os.remove(
                    os.path.join(current_app.config["UPLOAD_FOLDER"], current_flag)
                )
            except (OSError, TypeError, AttributeError):
                pass

            # Save the file & store in database for persistent storage
            if allowed_file(current_filename):
                from flask import current_app
                from database import query_cache
                from helpers import compress_flag_image

                # Compress and resize flag for fast storage/retrieval
                flag_data, extension = compress_flag_image(
                    flag, max_size=300, quality=85
                )
                filename = f"flag_{cId}.{extension}"

                db.execute(
                    "UPDATE users SET flag=(%s), flag_data=(%s) WHERE id=(%s)",
                    (filename, flag_data, cId),
                )

                # Also save to filesystem for backward compatibility
                flag.seek(0)  # Reset file pointer after read
                new_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
                flag.save(new_path)

                # Invalidate flag cache so new flag shows immediately
                query_cache.invalidate(f"flag_{cId}")

        """
        bg_flag = request.files["bg_flag_input"]
        if bg_flag and allowed_file(bg_flag.filename):


            # Check if the user already has a flag
            try:
                db.execute("SELECT bg_flag FROM users WHERE id=(%s)", (cId,))
                current_bg_flag = db.fetchone()[0]

                os.remove(os.path.join(
                    current_app.config['UPLOAD_FOLDER'], current_bg_flag))
            except FileNotFoundError:
                pass

            # Save the file & shit
            current_filename = bg_flag.filename
            if allowed_file(current_filename):
                extension = current_filename.rsplit('.', 1)[1].lower()
                filename = f"bg_flag_{cId}" + '.' + extension
                flag.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                db.execute("UPDATE users SET bg_flag=(%s) WHERE id=(%s)",
                           (filename, cId))
        """

        # Location changing
        new_location = request.form.get("countryLocation")

        from app_core.economy.biome_buildings import CANONICAL_BIOMES as continents

        if new_location not in continents and new_location not in ["", "none"]:
            return error(400, "No such continent")

        if new_location not in ["", "none"]:
            # Reset raw-extraction buildings when changing biome/location.
            # Legacy schema used proInfra rows keyed by province id; normalized
            # schema stores these in user_buildings keyed by user_id.
            db.execute(
                """
                UPDATE user_buildings ub
                SET quantity = 0
                FROM building_dictionary bd
                WHERE ub.building_id = bd.building_id
                  AND ub.user_id = %s
                  AND bd.name IN (
                      'pumpjacks',
                      'coal_mines',
                      'bauxite_mines',
                      'copper_mines',
                      'uranium_mines',
                      'lead_mines',
                      'iron_mines',
                      'lumber_mills'
                  )
                """,
                (cId,),
            )
            db.execute("UPDATE stats SET location=%s WHERE id=%s", (new_location, cId))

    return redirect(f"/country/id={cId}")  # Redirects the user to his country


# TODO: check if you can DELETE with one statement
def delete_own_account():
    cId = session["user_id"]
    from repositories.country_repository import CountryRepository
    
    CountryRepository.delete_own_account(cId)
    session.clear()
    return redirect("/")





def reset_account():
    from flask import request, session, redirect, flash
    from helpers import error
    from database import get_request_cursor, invalidate_view_cache
    from signup import _init_economy_tables
    
    reset_type = request.form.get("reset_type", "keep")
    cId = session["user_id"]
    
    try:
        with get_request_cursor() as db:
            db.execute("DELETE FROM user_military WHERE user_id=%s", (cId,))
            db.execute("DELETE FROM offers WHERE user_id=%s", (cId,))
            db.execute("DELETE FROM wars WHERE defender=%s OR attacker=%s", (cId, cId))
            db.execute("SELECT id FROM provinces WHERE userid=%s", (cId,))
            province_ids = db.fetchall()
            if province_ids:
                ids = [p[0] for p in province_ids]
                placeholders = ",".join(["%s"] * len(ids))
                db.execute(f"DELETE FROM provinces WHERE id IN ({placeholders})", tuple(ids))
            db.execute("DELETE FROM user_buildings WHERE user_id=%s", (cId,))
            db.execute("DELETE FROM trades WHERE offeree=%s OR offerer=%s", (cId, cId))
            db.execute("DELETE FROM spyinfo WHERE spyer=%s OR spyee=%s", (cId, cId))
            db.execute("DELETE FROM requests WHERE reqId=%s", (cId,))
            db.execute("DELETE FROM reparation_tax WHERE loser=%s OR winner=%s", (cId, cId))
            db.execute("DELETE FROM peace WHERE author=%s", (cId,))
            db.execute("DELETE FROM user_tech WHERE user_id=%s", (cId,))
            db.execute("DELETE FROM policies WHERE user_id=%s", (cId,))
            db.execute("DELETE FROM news WHERE destination_id=%s", (cId,))
            if reset_type == "scratch":
                # Exploit guard (player-reported): deposit everything into the
                # coalition bank, reset, collect a fresh starter package,
                # repeat. Track resets on the users row (survives the stats
                # wipe below) and only grant the full starter package once.
                db.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_count INTEGER NOT NULL DEFAULT 0"
                )
                db.execute(
                    "UPDATE users SET reset_count = COALESCE(reset_count, 0) + 1 "
                    "WHERE id=%s RETURNING reset_count",
                    (cId,),
                )
                reset_count = db.fetchone()[0]
                first_reset = reset_count <= 1
                from app_core.economy.biome_buildings import CANONICAL_BIOMES

                db.execute("SELECT location FROM stats WHERE id=%s", (cId,))
                prior_location_row = db.fetchone()
                prior_location = (
                    prior_location_row[0] if prior_location_row else None
                )
                if (prior_location or "").strip().title() not in CANONICAL_BIOMES:
                    # No valid prior biome to carry over (e.g. this account's
                    # location was already corrupt) -- fall back to a random
                    # real continent rather than a non-existent placeholder.
                    import random

                    prior_location = random.choice(CANONICAL_BIOMES)
                db.execute("DELETE FROM stats WHERE id=%s", (cId,))
                db.execute("DELETE FROM user_economy WHERE user_id=%s", (cId,))
                starting_gold = 70000000 if first_reset else 1000000
                db.execute(
                    "INSERT INTO stats (id, location, gold) VALUES (%s, %s, %s)",
                    (cId, prior_location, starting_gold),
                )
                if first_reset:
                    _init_economy_tables(db, cId)
                else:
                    # Zeroed economy rows only — no starter care package.
                    db.execute(
                        "INSERT INTO user_economy (user_id, resource_id, quantity) "
                        "SELECT %s, resource_id, 0 FROM resource_dictionary "
                        "ON CONFLICT DO NOTHING",
                        (cId,),
                    )
                    db.execute(
                        "INSERT INTO user_military (user_id, unit_id, quantity) "
                        "SELECT %s, unit_id, 0 FROM unit_dictionary WHERE is_active = TRUE "
                        "ON CONFLICT DO NOTHING",
                        (cId,),
                    )
                    flash(
                        "Repeat resets start with $1,000,000 and no starter "
                        "resources (the full starter package is one-time)."
                    )
            else:
                db.execute("INSERT INTO user_military (user_id, unit_id, quantity) SELECT %s, unit_id, 0 FROM unit_dictionary WHERE is_active = TRUE ON CONFLICT DO NOTHING", (cId,))
                db.execute("INSERT INTO policies (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (cId,))
            invalidate_view_cache(cId)
            flash("Your account has been reset successfully.")
            return redirect("/account")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Account reset failed for user {cId}: {e}")
        return error(500, f"Reset failed: {e}")
def register_countries_routes(app_instance):
    """Register all routes from countries module after app initialization.

    This deferred registration avoids circular imports:
    wsgi.py -> app.py -> countries -> app (causes circular dependency at import time)

    Args:
        app_instance: Flask app instance to register routes with
    """
    # Configure app settings for countries routes
    app_instance.config["UPLOAD_FOLDER"] = "static/flags"
    app_instance.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB limit

    # Register my_country route
    app_instance.add_url_rule(
        "/my_country", "my_country", login_required(my_country), methods=["GET"]
    )

    # Register country route
    # Public route - anyone can view a nation's page
    # Cache is short (30s) since users viewing their own country
    # need fresh data after edits
    app_instance.add_url_rule(
        "/country/id=<cId>",
        "country",
        cache_response(ttl_seconds=30)(country),
        methods=["GET"],
    )

    # Register countries route (cached for 60 seconds - list doesn't change often)
    app_instance.add_url_rule(
        "/countries",
        "countries",
        login_required(cache_response(ttl_seconds=60)(countries)),
        methods=["GET"],
    )

    # Register update_country_info route
    app_instance.add_url_rule(
        "/update_country_info",
        "update_info",
        login_required(update_info),
        methods=["POST"],
    )

    # Register delete_news route
    app_instance.add_url_rule(
        "/delete_news/<int:id>",
        "delete_news",
        login_required(delete_news),
        methods=["POST"],
    )


    # Register reset_account route
    app_instance.add_url_rule(
        "/reset_account",
        "reset_account",
        login_required(reset_account),
        methods=["POST"],
    )

    # Register delete_own_account route
    app_instance.add_url_rule(
        "/delete_own_account",
        "delete_own_account",
        login_required(delete_own_account),
        methods=["POST"],
    )
