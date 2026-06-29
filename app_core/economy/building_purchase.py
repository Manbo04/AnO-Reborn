"""Shared building purchase — gold + resources from PROVINCE_UNIT_PRICES."""
from __future__ import annotations

import os

from app_core.economy.building_costs import (
    CITY_UNITS,
    LAND_UNITS,
    apply_policy_gold_discount,
    get_slot_type,
)
import variables


class BuildingPurchaseError(Exception):
    """Business-rule failure when buying a building."""


def get_free_slots(db, province_id: int, slot_type: str) -> int:
    if slot_type == "city":
        db.execute(
            """
            SELECT COALESCE(SUM(ub.quantity), 0), CAST(p.citycount AS INTEGER)
            FROM provinces p
            LEFT JOIN (
                user_buildings ub
                JOIN building_dictionary bd
                    ON bd.building_id = ub.building_id
                    AND bd.name = ANY(%s)
            ) ON ub.province_id = p.id
            WHERE p.id = %s
            GROUP BY p.id, p.citycount
            """,
            (list(CITY_UNITS), province_id),
        )
    elif slot_type == "land":
        db.execute(
            """
            SELECT COALESCE(SUM(ub.quantity), 0), p.land
            FROM provinces p
            LEFT JOIN (
                user_buildings ub
                JOIN building_dictionary bd
                    ON bd.building_id = ub.building_id
                    AND bd.name = ANY(%s)
            ) ON ub.province_id = p.id
            WHERE p.id = %s
            GROUP BY p.id, p.land
            """,
            (list(LAND_UNITS), province_id),
        )
    else:
        return 0

    row = db.fetchone()
    if not row:
        return 0
    return int(row[1] or 0) - int(row[0] or 0)


def _load_policies(db, user_id: int) -> list:
    try:
        db.execute("SELECT education FROM policies WHERE user_id=%s", (user_id,))
        row = db.fetchone()
        if row and row[0] is not None:
            return list(row[0])
    except Exception:
        pass
    return []


def _resource_id_map(db) -> dict[str, int]:
    db.execute("SELECT name, resource_id FROM resource_dictionary")
    return {row[0]: row[1] for row in db.fetchall()}


def purchase_building(
    db,
    user_id: int,
    province_id: int,
    building_name: str,
    quantity: int,
    *,
    policies: list | None = None,
    skip_slot_check: bool = False,
) -> dict:
    """Buy `quantity` buildings in a province. Uses caller's db cursor (no commit)."""
    if quantity < 1:
        raise BuildingPurchaseError("Quantity must be at least 1.")

    name = building_name.strip().lower()
    prices = variables.PROVINCE_UNIT_PRICES
    if f"{name}_price" not in prices:
        raise BuildingPurchaseError("No such building exists.")

    db.execute("SELECT userId FROM provinces WHERE id = %s FOR UPDATE", (province_id,))
    owner = db.fetchone()
    if not owner or owner[0] != user_id:
        raise BuildingPurchaseError("You do not own this province.")

    if policies is None:
        policies = _load_policies(db, user_id)

    unit_gold = apply_policy_gold_discount(name, prices[f"{name}_price"], policies)
    total_gold = int(unit_gold) * quantity
    resources_data = dict(prices.get(f"{name}_resource") or {})

    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
    gold_row = db.fetchone()
    if not gold_row:
        raise BuildingPurchaseError("Nation data could not be found.")
    gold_before = int(gold_row[0] or 0)

    if total_gold > gold_before:
        raise BuildingPurchaseError("You don't have enough money.")

    slot_type = get_slot_type(name)
    if slot_type and not skip_slot_check:
        free_slots = get_free_slots(db, province_id, slot_type)
        if free_slots < quantity:
            raise BuildingPurchaseError(
                f"Not enough {slot_type} slots for {quantity}"
            )

    res_map = _resource_id_map(db)
    for resource, per_unit in resources_data.items():
        qty = int(per_unit) * quantity
        resource_id = res_map.get(resource)
        if not resource_id:
            raise BuildingPurchaseError(f"Unknown resource: {resource}")
        db.execute(
            "SELECT COALESCE(quantity, 0) FROM user_economy "
            "WHERE user_id = %s AND resource_id = %s",
            (user_id, resource_id),
        )
        row = db.fetchone()
        current = int(row[0]) if row else 0
        if current < qty:
            missing = qty - current
            raise BuildingPurchaseError(f"Missing {missing} {resource}")

    for resource, per_unit in resources_data.items():
        qty = int(per_unit) * quantity
        resource_id = res_map[resource]
        db.execute(
            """
            UPDATE user_economy SET quantity = quantity - %s
            WHERE user_id = %s AND resource_id = %s AND quantity >= %s
            RETURNING quantity
            """,
            (qty, user_id, resource_id, qty),
        )
        if db.fetchone() is None:
            raise BuildingPurchaseError(f"Missing {qty} {resource}")

    db.execute(
        "UPDATE stats SET gold = gold - %s WHERE id = %s AND gold >= %s "
        "RETURNING gold",
        (total_gold, user_id, total_gold),
    )
    if db.fetchone() is None:
        raise BuildingPurchaseError("You don't have enough money.")

    db.execute(
        """
        INSERT INTO user_buildings
            (user_id, building_id, province_id, quantity, last_upgraded)
        VALUES (
            %s,
            (SELECT building_id FROM building_dictionary WHERE name = %s),
            %s,
            %s,
            now()
        )
        ON CONFLICT (user_id, building_id, province_id)
        DO UPDATE SET
            quantity = user_buildings.quantity + EXCLUDED.quantity,
            last_upgraded = now()
        """,
        (user_id, name, province_id, quantity),
    )

    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
    gold_after_row = db.fetchone()
    gold_after = int(gold_after_row[0] or 0) if gold_after_row else gold_before - total_gold

    db.execute(
        """
        INSERT INTO purchase_audit (user_id, province_id, unit, units,
            gold_before, gold_after, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            province_id,
            name,
            quantity,
            gold_before,
            gold_after,
            f"buy_{name}",
        ),
    )

    try:
        thresh = int(os.getenv("PURCHASE_SENTRY_THRESHOLD", "1000000"))
        diff = abs(gold_before - gold_after)
        if diff >= thresh:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_extra("user_id", user_id)
                scope.set_extra("province_id", province_id)
                scope.set_extra("unit", name)
                scope.set_extra("units", quantity)
                scope.set_extra("gold_before", gold_before)
                scope.set_extra("gold_after", gold_after)
                sentry_sdk.capture_message(
                    f"Large buy: {name} x{quantity} by user {user_id} ({diff} gold)"
                )
    except Exception:
        pass

    # === TUTORIAL ACTION INTERCEPTION ===
    try:
        from app_core.tutorial.routes import advance_tutorial_step_by_action
        if name == "farms":
            advance_tutorial_step_by_action(db, user_id, "build_farm")
        elif name == "distribution_centers":
            advance_tutorial_step_by_action(db, user_id, "build_distribution_center")
        elif name == "mines":
            advance_tutorial_step_by_action(db, user_id, "build_mine")
    except Exception as exc:
        pass # Fail silently so we don't break the purchase transaction

    return {
        "building_name": name,
        "quantity": quantity,
        "gold_spent": total_gold,
        "resources_spent": {k: int(v) * quantity for k, v in resources_data.items()},
        "gold_before": gold_before,
        "gold_after": gold_after,
    }
