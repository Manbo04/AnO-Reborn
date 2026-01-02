"""Clean tasks module with working revenue generation.

Contains defensive implementations of calc_ti and generate_province_revenue
that properly iterate through provinces and generate resources.
"""

from __future__ import annotations

import math
from typing import Tuple

import variables

# Capture any pre-existing calc_ti (e.g., monkeypatched) so reloads keep using it.
_CALC_TI_OVERRIDE = globals().get("calc_ti", None)


# Maximum safe 32-bit signed integer
MAX_INT_32 = 2**31 - 1


def find_unit_category(unit):
    """Helper to determine unit category."""
    industry = [
        "component_factories",
        "steel_mills",
        "aluminium_factories",
        "gasoline_refineries",
        "ammunition_factories",
    ]
    retail = ["malls", "grocery_stores"]

    if unit in industry:
        return "industry"
    elif unit in retail:
        return "retail"
    return None


def handle_exception(e):
    """Handle exceptions with detailed logging."""
    filename = __file__
    line = e.__traceback__.tb_lineno
    print("\n-----------------START OF EXCEPTION-------------------")
    print(f"Filename: {filename}")
    print(f"Error: {e}")
    print(f"Line: {line}")
    print("-----------------END OF EXCEPTION---------------------\n")


def rations_needed(user_id: int) -> int:
    """Return how many rations a player needs."""
    from database import get_db_cursor

    with get_db_cursor() as db:
        db.execute(
            "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId=%s",
            (user_id,),
        )
        total_population = db.fetchone()[0]
        return total_population // variables.RATIONS_PER


def energy_info(province_id: int) -> tuple[int, int]:
    """Return energy production and consumption from a province."""
    from database import get_db_cursor

    with get_db_cursor() as db:
        production = 0
        consumption = 0

        consumers = variables.ENERGY_CONSUMERS
        producers = variables.ENERGY_UNITS
        infra = variables.NEW_INFRA

        # Fetch all data in a single query
        all_fields = consumers + producers
        query = f"SELECT {', '.join(all_fields)} FROM proInfra WHERE id=%s"
        db.execute(query, (province_id,))
        result = db.fetchone()

        if not result:
            return 0, 0

        # Calculate consumption from first N fields
        consumption = sum(result[: len(consumers)])

        # Calculate production from remaining fields
        for idx, producer in enumerate(producers):
            producer_count = result[len(consumers) + idx]
            production += producer_count * infra[producer]["plus"]["energy"]

        return consumption, production


def calc_ti(user_id: int) -> Tuple[int, int] | Tuple[bool, bool]:
    """Authoritative, defensive tax income calculation.

    Returns (income, removed_consumer_goods) or (False, False) when the
    user has no provinces.
    """
    from database import get_db_cursor, fetchone_first

    with get_db_cursor() as db:
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (user_id,))
        consumer_goods = int(fetchone_first(db, 0) or 0)

        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (user_id,))
            policies = fetchone_first(db, [])
            if isinstance(policies, int):
                policies = [policies]
        except Exception:
            policies = []

        try:
            db.execute(
                "SELECT population, land FROM provinces WHERE userId=%s", (user_id,)
            )
            provinces = db.fetchall() or []
        except Exception:
            provinces = []

    if not provinces:
        return False, False

    income = 0
    for population, land in provinces:
        land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
        land_multiplier = min(land_multiplier, 1)

        base_multiplier = variables.DEFAULT_TAX_INCOME
        if 1 in policies:
            base_multiplier *= 1.01
        if 6 in policies:
            base_multiplier *= 0.98
        if 4 in policies:
            base_multiplier *= 0.98

        multiplier = base_multiplier + (base_multiplier * land_multiplier)
        income += multiplier * population

    total_pop = sum(p for p, _ in provinces)
    max_cg = math.ceil(total_pop / variables.CONSUMER_GOODS_PER) if total_pop > 0 else 0

    removed_cg = 0
    if max_cg and consumer_goods > 0:
        if consumer_goods >= max_cg:
            removed_cg = max_cg
            income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
        else:
            cg_multiplier = consumer_goods / max_cg
            income *= 1 + (0.5 * cg_multiplier)
            removed_cg = consumer_goods

    return math.floor(income), int(removed_cg)


def calc_pg(pId, rations):
    """Safe stub for population growth helper used by views/tests."""
    return rations, rations


def generate_province_revenue() -> None:
    """Generate resources for all provinces based on their infrastructure.

    This function iterates through all provinces with infrastructure and:
    1. Deducts operating costs (money, energy, raw materials)
    2. Adds produced resources (rations, oil, components, etc.)
    3. Updates province stats (happiness, productivity, pollution)
    """
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor

    with get_db_connection() as conn:
        db = conn.cursor()
        dbdict = conn.cursor(cursor_factory=RealDictCursor)

        columns = variables.BUILDINGS
        province_resources = [
            "energy",
            "population",
            "happiness",
            "pollution",
            "productivity",
            "consumer_spending",
        ]
        percentage_based = [
            "happiness",
            "productivity",
            "consumer_spending",
            "pollution",
        ]
        energy_consumers = variables.ENERGY_CONSUMERS
        user_resources = variables.RESOURCES
        infra = variables.NEW_INFRA

        try:
            db.execute(
                "SELECT proInfra.id, provinces.userId, provinces.land "
                "FROM proInfra INNER JOIN provinces ON proInfra.id=provinces.id "
                "ORDER BY id ASC"
            )
            infra_ids = db.fetchall()
        except Exception:
            infra_ids = []

        for province_id, user_id, land in infra_ids:
            db.execute("UPDATE provinces SET energy=0 WHERE id=%s", (province_id,))

            dbdict.execute("SELECT * FROM upgrades WHERE user_id=%s", (user_id,))
            upgrades = dict(dbdict.fetchone())

            try:
                db.execute(
                    "SELECT education FROM policies WHERE user_id=%s", (user_id,)
                )
                policies = db.fetchone()[0]
            except Exception:
                policies = []

            dbdict.execute("SELECT * FROM proInfra WHERE id=%s", (province_id,))
            units = dict(dbdict.fetchone())

            for unit in columns:
                unit_amount = units[unit]

                if unit_amount == 0:
                    continue

                unit_category = find_unit_category(unit)
                try:
                    effminus = infra[unit].get("effminus", {})
                    minus = infra[unit].get("minus", {})

                    operating_costs = infra[unit]["money"] * unit_amount
                    plus_amount = 0
                    plus_amount_multiplier = 1

                    if 1 in policies and unit == "universities":
                        operating_costs *= 1.14
                    if 3 in policies and unit == "universities":
                        operating_costs *= 1.18
                    if 6 in policies and unit == "universities":
                        operating_costs *= 0.93

                    # CHEAPER MATERIALS
                    if unit_category == "industry" and upgrades.get(
                        "cheapermaterials", False
                    ):
                        operating_costs *= 0.8
                    # ONLINE SHOPPING
                    if unit == "malls" and upgrades.get("onlineshopping", False):
                        operating_costs *= 0.7

                    # Check if user has enough money
                    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
                    current_money = db.fetchone()[0]
                    operating_costs = int(operating_costs)

                    has_enough_stuff = {"status": True, "issues": []}

                    if current_money < operating_costs:
                        print(
                            f"Couldn't update {unit} for {province_id} as they don't "
                            "have enough money"
                        )
                        has_enough_stuff["status"] = False
                        has_enough_stuff["issues"].append("money")
                    else:
                        try:
                            db.execute(
                                "UPDATE stats SET gold=gold-%s WHERE id=%s",
                                (operating_costs, user_id),
                            )
                        except Exception:
                            conn.rollback()
                            continue

                    # Check energy requirements
                    if unit in energy_consumers:
                        db.execute(
                            "SELECT energy FROM provinces WHERE id=%s", (province_id,)
                        )
                        current_energy = db.fetchone()[0]
                        new_energy = current_energy - unit_amount

                        if new_energy < 0:
                            has_enough_stuff["status"] = False
                            has_enough_stuff["issues"].append("energy")
                            new_energy = 0

                        db.execute(
                            "UPDATE provinces SET energy=%s WHERE id=%s",
                            (new_energy, province_id),
                        )

                    # Check raw material requirements
                    dbdict.execute("SELECT * FROM resources WHERE id=%s", (user_id,))
                    resources = dict(dbdict.fetchone())

                    for resource, amount in minus.items():
                        amount *= unit_amount
                        current_resource = resources[resource]

                        # AUTOMATION INTEGRATION
                        if unit == "component_factories" and upgrades.get(
                            "automationintegration", False
                        ):
                            amount *= 0.75
                        # LARGER FORGES
                        if unit == "steel_mills" and upgrades.get(
                            "largerforges", False
                        ):
                            amount *= 0.7

                        new_resource = current_resource - amount

                        if new_resource < 0:
                            has_enough_stuff["status"] = False
                            has_enough_stuff["issues"].append(resource)
                            minus_fail_msg = " ".join(
                                [
                                    f"F | USER: {user_id}",
                                    f"PROVINCE: {province_id}",
                                    f"{unit} ({unit_amount})",
                                    "Failed to minus",
                                    f"{amount} of {resource}",
                                    f"({current_resource})",
                                ]
                            )
                            print(minus_fail_msg)
                        else:
                            resource_u_statement = (
                                f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
                            )
                            minus_success_msg = " ".join(
                                [
                                    "S | MINUS |",
                                    f"USER: {user_id}",
                                    f"PROVINCE: {province_id}",
                                    f"{unit} ({unit_amount})",
                                    f"{resource} {current_resource}={new_resource}",
                                    f"(-{current_resource-new_resource})",
                                ]
                            )
                            print(minus_success_msg)
                            db.execute(
                                resource_u_statement,
                                (
                                    new_resource,
                                    user_id,
                                ),
                            )

                    if not has_enough_stuff["status"]:
                        not_enough_msg = " ".join(
                            [
                                f"F | USER: {user_id}",
                                f"PROVINCE: {province_id}",
                                f"{unit} ({unit_amount})",
                                f"Not enough {', '.join(has_enough_stuff['issues'])}",
                            ]
                        )
                        print(not_enough_msg)
                        continue

                    # Apply production bonuses
                    plus = infra[unit].get("plus", {})

                    # BETTER ENGINEERING
                    if unit == "nuclear_reactors" and upgrades.get(
                        "betterengineering", False
                    ):
                        plus["energy"] += 6

                    eff = infra[unit].get("eff", {})

                    if unit == "universities" and 3 in policies:
                        eff["productivity"] *= 1.10
                        eff["happiness"] *= 1.10

                    if unit == "hospitals":
                        if upgrades.get("nationalhealthinstitution", False):
                            eff["happiness"] *= 1.3
                            eff["happiness"] = int(eff["happiness"])

                    if unit == "monorails":
                        if upgrades.get("highspeedrail", False):
                            eff["productivity"] *= 1.2
                            eff["productivity"] = int(eff["productivity"])

                    if unit == "bauxite_mines" and upgrades.get(
                        "strongerexplosives", False
                    ):
                        plus_amount_multiplier += 0.45

                    if unit == "farms":
                        if upgrades.get("advancedmachinery", False):
                            plus_amount_multiplier += 0.5
                        plus_amount += int(
                            land * variables.LAND_FARM_PRODUCTION_ADDITION
                        )

                    # Add produced resources
                    for resource, amount in plus.items():
                        amount += plus_amount
                        amount *= unit_amount
                        amount *= plus_amount_multiplier
                        # Normalize production to integer units
                        amount = math.ceil(amount)

                        if resource in province_resources:
                            cpr_statement = (
                                f"SELECT {resource} FROM provinces" + " WHERE id=%s"
                            )
                            db.execute(cpr_statement, (province_id,))
                            current_plus_resource = db.fetchone()[0]
                            new_resource_number = current_plus_resource + amount

                            if (
                                resource in percentage_based
                                and new_resource_number > 100
                            ):
                                new_resource_number = 100
                            if new_resource_number < 0:
                                new_resource_number = 0

                            upd_prov_statement = (
                                f"UPDATE provinces SET {resource}" + "=%s WHERE id=%s"
                            )
                            plus_msg = " ".join(
                                [
                                    "S | PLUS |USER:",
                                    str(user_id),
                                    f"PROVINCE: {province_id}",
                                    f"{unit} ({unit_amount})",
                                    "ADDING",
                                    resource,
                                    str(amount),
                                ]
                            )
                            print(plus_msg)
                            db.execute(
                                upd_prov_statement, (new_resource_number, province_id)
                            )

                        elif resource in user_resources:
                            upd_res_statement = (
                                f"UPDATE resources SET {resource}={resource}"
                                + "+%s WHERE id=%s"
                            )
                            plus_user_msg = " ".join(
                                [
                                    "S | PLUS | USER:",
                                    str(user_id),
                                    f"PROVINCE: {province_id}",
                                    f"{unit} ({unit_amount})",
                                    "ADDING",
                                    resource,
                                    str(amount),
                                ]
                            )
                            print(plus_user_msg)
                            db.execute(
                                upd_res_statement,
                                (
                                    amount,
                                    user_id,
                                ),
                            )

                    # Apply effects (pollution, happiness, productivity, etc.)
                    def do_effect(
                        eff_name,
                        eff_amount,
                        sign,
                        province_id=province_id,
                        unit_category=unit_category,
                        upgrades=upgrades,
                        unit=unit,
                        policies=policies,
                        percentage_based=percentage_based,
                    ):
                        effect_select = (
                            f"SELECT {eff_name} FROM provinces " + "WHERE id=%s"
                        )
                        db.execute(effect_select, (province_id,))
                        current_effect = db.fetchone()[0]

                        # GOVERNMENT REGULATION
                        if (
                            unit_category == "retail"
                            and upgrades.get("governmentregulation", False)
                            and eff_name == "pollution"
                            and sign == "+"
                        ):
                            eff_amount *= 0.75

                        if unit == "universities" and 3 in policies:
                            eff_amount *= 1.1

                        eff_amount = math.ceil(eff_amount)

                        if sign == "+":
                            new_effect = current_effect + eff_amount
                        elif sign == "-":
                            new_effect = current_effect - eff_amount

                        if eff_name in percentage_based:
                            if new_effect > 100:
                                new_effect = 100
                            if new_effect < 0:
                                new_effect = 0
                        else:
                            if new_effect < 0:
                                new_effect = 0

                        eff_update = (
                            f"UPDATE provinces SET {eff_name}" + "=%s WHERE id=%s"
                        )
                        db.execute(eff_update, (new_effect, province_id))

                    for effect, amount in eff.items():
                        amount *= unit_amount
                        do_effect(effect, amount, "+")

                    for effect, amount in effminus.items():
                        amount *= unit_amount
                        do_effect(effect, amount, "-")

                    # Apply policy effects
                    if 5 in policies:
                        db.execute(
                            "UPDATE provinces SET productivity=productivity*0.91 "
                            "WHERE id=%s",
                            (province_id,),
                        )
                    if 4 in policies:
                        db.execute(
                            "UPDATE provinces SET productivity=productivity*1.05 "
                            "WHERE id=%s",
                            (province_id,),
                        )
                    if 2 in policies:
                        db.execute(
                            "UPDATE provinces SET happiness=happiness*0.89 WHERE id=%s",
                            (province_id,),
                        )

                except Exception as e:
                    conn.rollback()
                    handle_exception(e)
                    continue


def tax_income() -> None:
    """Give tax income to all users."""
    from database import get_db_connection
    import psycopg2.extras as extras

    calc_fn = _CALC_TI_OVERRIDE or calc_ti

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id FROM users")
        users = db.fetchall() or []

        money_updates = []
        cg_updates = []

        for (uid,) in users:
            res = calc_fn(uid)
            if res and isinstance(res, tuple):
                income, removed = res
                if income:
                    money_updates.append((income, uid))
                if removed and removed > 0:
                    cg_updates.append((removed, uid))

        if money_updates:
            extras.execute_batch(
                db,
                "UPDATE stats SET gold=gold+%s WHERE id=%s",
                money_updates,
            )
        if cg_updates:
            extras.execute_batch(
                db,
                "UPDATE resources SET consumer_goods=consumer_goods-%s WHERE id=%s",
                cg_updates,
            )


def _safe_update_productivity(db_cursor, province_id, multiplier) -> None:
    """Safely update productivity with bounds checking."""
    db_cursor.execute("SELECT productivity FROM provinces WHERE id=%s", (province_id,))
    row = db_cursor.fetchone()
    if not row:
        return
    current = int(row[0])
    new_val = int(current * multiplier)
    if new_val > MAX_INT_32:
        new_val = MAX_INT_32
    db_cursor.execute(
        "UPDATE provinces SET productivity=(%s) WHERE id=%s", (new_val, province_id)
    )


class _TaskWrapper:
    """Wrapper for Celery tasks."""

    def __init__(self, func):
        self.func = func

    def run(self):
        try:
            self.func()
        except Exception:
            return None


task_tax_income = _TaskWrapper(tax_income)
task_generate_province_revenue = _TaskWrapper(generate_province_revenue)
