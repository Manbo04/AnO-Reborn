
import os
from dataclasses import dataclass

from database import get_db_connection
from app_core.economy.building_purchase import (
    BuildingPurchaseError,
    purchase_building,
)


BUILD_COST_RESOURCE = os.getenv("BUILD_COST_RESOURCE", "steel")
RESEARCH_COST_RESOURCE = os.getenv("RESEARCH_COST_RESOURCE", "components")


class ActionLoopError(Exception):
    """Business-rule error for build/research actions."""


@dataclass
class ActionResult:
    success: bool
    message: str


def _get_resource_id(db, resource_name: str):
    db.execute(
        "SELECT resource_id FROM resource_dictionary WHERE name=%s",
        (resource_name,),
    )
    row = db.fetchone()
    return row[0] if row else None


def _is_tech_unlocked(db, user_id: int, tech_id: int) -> bool:
    db.execute(
        """
        SELECT is_unlocked
        FROM user_tech
        WHERE user_id=%s AND tech_id=%s
        """,
        (user_id, tech_id),
    )
    row = db.fetchone()
    return bool(row and row[0])


def build_structure(
    user_id: int, building_id: int, quantity: int, province_id: int = None
) -> ActionResult:
    """Build structure(s) using canonical PROVINCE_UNIT_PRICES (gold + resources)."""
    if quantity <= 0:
        raise ActionLoopError("Quantity must be greater than 0.")
    if province_id is None:
        raise ActionLoopError("Province must be specified when building.")

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

        db.execute(
            """
            SELECT building_id, name, display_name, required_tech_id, is_active
            FROM building_dictionary
            WHERE building_id=%s
            """,
            (building_id,),
        )
        row = db.fetchone()
        if not row:
            raise ActionLoopError("Building not found.")

        _, building_name, display_name, required_tech_id, is_active = row
        if not is_active:
            raise ActionLoopError("This building is not currently available.")

        if required_tech_id and not _is_tech_unlocked(db, user_id, required_tech_id):
            raise ActionLoopError("Required technology is not unlocked.")

        try:
            purchase_building(
                db,
                user_id,
                province_id,
                building_name,
                quantity,
            )
        except BuildingPurchaseError as exc:
            raise ActionLoopError(str(exc)) from exc

        conn.commit()

    return ActionResult(
        success=True,
        message=f"Built {quantity}x {display_name}.",
    )


def demolish_structure(
    user_id: int, building_id: int, quantity: int, province_id: int = None
) -> ActionResult:
    """Demolish structure(s), refunding gold and resources.

    Mirrors the classic province sell path: full resource refund plus the
    current (policy-discounted) gold price per unit, and a revenue ledger row.
    """
    if quantity <= 0:
        raise ActionLoopError("Quantity must be greater than 0.")
    if province_id is None:
        raise ActionLoopError("Province must be specified when demolishing.")

    import variables
    from app_core.economy.building_purchase import (
        _load_policies,
        apply_policy_gold_discount,
    )

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

        db.execute(
            """
            SELECT name, display_name FROM building_dictionary
            WHERE building_id=%s
            """,
            (building_id,),
        )
        row = db.fetchone()
        if not row:
            raise ActionLoopError("Building not found.")
        building_name, display_name = row

        db.execute(
            "SELECT userId FROM provinces WHERE id = %s FOR UPDATE",
            (province_id,),
        )
        owner = db.fetchone()
        if not owner or owner[0] != user_id:
            raise ActionLoopError("You do not own this province.")

        db.execute(
            """
            SELECT quantity FROM user_buildings
            WHERE user_id=%s AND province_id=%s AND building_id=%s
            """,
            (user_id, province_id, building_id),
        )
        owned_row = db.fetchone()
        owned = owned_row[0] if owned_row else 0
        if owned < quantity:
            raise ActionLoopError(
                f"You only have {owned} {display_name} in this province."
            )

        db.execute(
            """
            UPDATE user_buildings SET quantity = quantity - %s
            WHERE user_id=%s AND province_id=%s AND building_id=%s
            """,
            (quantity, user_id, province_id, building_id),
        )

        prices = variables.PROVINCE_UNIT_PRICES
        policies = _load_policies(db, user_id)
        unit_gold = apply_policy_gold_discount(
            building_name, prices.get(f"{building_name}_price", 0), policies
        )
        refund_gold = int(unit_gold) * quantity
        if refund_gold:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id=%s",
                (refund_gold, user_id),
            )

        for resource, per_unit in (prices.get(f"{building_name}_resource") or {}).items():
            qty = int(per_unit) * quantity
            db.execute(
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                SELECT %s, resource_id, %s FROM resource_dictionary WHERE name=%s
                ON CONFLICT (user_id, resource_id)
                DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
                """,
                (user_id, qty, resource),
            )

        from helpers import get_date

        db.execute(
            """
            INSERT INTO revenue (user_id, type, name, description, date, resource, amount)
            VALUES (%s, 'revenue', %s, '', %s, %s, %s)
            """,
            (
                user_id,
                f"Demolishing {quantity} {building_name} in a province.",
                get_date(),
                building_name,
                quantity,
            ),
        )

        conn.commit()

    return ActionResult(
        success=True,
        message=f"Demolished {quantity}x {display_name} (refund: ${refund_gold:,}).",
    )


def start_research(user_id: int, tech_id: int) -> ActionResult:
    """Unlock a technology using normalized schema.

    Cost is deducted from `user_economy` using `RESEARCH_COST_RESOURCE`.
    Transactions use consistent ascending-order user_id locking to prevent deadlocks.
    """
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

        db.execute(
            """
            SELECT tech_id, display_name, research_cost, prerequisite_tech_id, is_active
            FROM tech_dictionary
            WHERE tech_id=%s
            """,
            (tech_id,),
        )
        row = db.fetchone()
        if not row:
            raise ActionLoopError("Technology not found.")

        _, display_name, research_cost, prerequisite_tech_id, is_active = row
        if not is_active:
            raise ActionLoopError("This technology is not currently available.")

        if _is_tech_unlocked(db, user_id, tech_id):
            return ActionResult(
                success=True, message=f"{display_name} already unlocked."
            )

        if prerequisite_tech_id and not _is_tech_unlocked(
            db,
            user_id,
            prerequisite_tech_id,
        ):
            raise ActionLoopError("Prerequisite technology is not unlocked.")

        resource_id = _get_resource_id(db, RESEARCH_COST_RESOURCE)
        if resource_id is None:
            raise ActionLoopError(
                "Research cost resource is not configured in dictionary."
            )

        total_cost = int(research_cost)

        db.execute(
            """
            UPDATE user_economy
            SET quantity = quantity - %s,
                updated_at = now()
            WHERE user_id=%s
              AND resource_id=%s
              AND quantity >= %s
            RETURNING quantity
            """,
            (total_cost, user_id, resource_id, total_cost),
        )
        if db.fetchone() is None:
            db.execute(
                "SELECT COALESCE(quantity, 0) FROM user_economy "
                "WHERE user_id=%s AND resource_id=%s",
                (user_id, resource_id),
            )
            bal_row = db.fetchone()
            current_bal = int(bal_row[0]) if bal_row else 0
            raise ActionLoopError(
                f"Not enough {RESEARCH_COST_RESOURCE} to research {display_name}. "
                f"Need {total_cost:,}, but you only have {current_bal:,}."
            )

        db.execute(
            """
            INSERT INTO user_tech
                (user_id, tech_id, is_unlocked, research_progress, unlocked_at)
            VALUES (%s, %s, TRUE, 100, now())
            ON CONFLICT (user_id, tech_id)
            DO UPDATE SET
                is_unlocked = TRUE,
                research_progress = 100,
                unlocked_at = now()
            """,
            (user_id, tech_id),
        )

        conn.commit()

    return ActionResult(success=True, message=f"Researched {display_name}.")
