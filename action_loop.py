from __future__ import annotations

import os
from dataclasses import dataclass

from database import get_db_connection


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


def build_structure(user_id: int, building_id: int, quantity: int) -> ActionResult:
    """Build structure(s) using normalized schema.

    Cost is deducted from `user_economy` using `BUILD_COST_RESOURCE`.
    Transactions use consistent ascending-order user_id locking to prevent deadlocks.
    """
    if quantity <= 0:
        raise ActionLoopError("Quantity must be greater than 0.")

    with get_db_connection() as conn:
        db = conn.cursor()
        # Acquire advisory lock for deadlock safety (always by ascending user_id)
        db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))

        db.execute(
            """
            SELECT building_id, display_name, base_cost, required_tech_id, is_active
            FROM building_dictionary
            WHERE building_id=%s
            """,
            (building_id,),
        )
        row = db.fetchone()
        if not row:
            raise ActionLoopError("Building not found.")

        _, display_name, base_cost, required_tech_id, is_active = row
        if not is_active:
            raise ActionLoopError("This building is not currently available.")

        if required_tech_id and not _is_tech_unlocked(db, user_id, required_tech_id):
            raise ActionLoopError("Required technology is not unlocked.")

        resource_id = _get_resource_id(db, BUILD_COST_RESOURCE)
        if resource_id is None:
            raise ActionLoopError(
                "Build cost resource is not configured in dictionary."
            )

        total_cost = int(base_cost) * int(quantity)

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
            raise ActionLoopError(
                f"Not enough {BUILD_COST_RESOURCE} to build {display_name}."
            )

        db.execute(
            """
            INSERT INTO user_buildings (user_id, building_id, quantity, last_upgraded)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id, building_id)
            DO UPDATE SET
                quantity = user_buildings.quantity + EXCLUDED.quantity,
                last_upgraded = now()
            """,
            (user_id, building_id, quantity),
        )

        conn.commit()

    return ActionResult(
        success=True,
        message=f"Built {quantity}x {display_name}.",
    )


def start_research(user_id: int, tech_id: int) -> ActionResult:
    """Unlock a technology using normalized schema.

    Cost is deducted from `user_economy` using `RESEARCH_COST_RESOURCE`.
    Transactions use consistent ascending-order user_id locking to prevent deadlocks.
    """
    with get_db_connection() as conn:
        db = conn.cursor()
        # Acquire advisory lock for deadlock safety (always by ascending user_id)
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
            raise ActionLoopError(
                f"Not enough {RESEARCH_COST_RESOURCE} to research {display_name}."
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
