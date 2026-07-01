import os
import math
from flask import Blueprint, render_template, session, jsonify, request, redirect, abort

from database import get_request_cursor
from helpers import login_required

bp = Blueprint("game_map", __name__)

# Token-based private access. Set GAME_MAP_TOKEN env var on Railway to change this.
_DEFAULT_TOKEN = "3f8a92e1b4d6c7"

GAME_MAP_TOKEN = os.getenv("GAME_MAP_TOKEN", _DEFAULT_TOKEN)

HEX_DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def _is_authorized() -> bool:
    return bool(session.get("game_map_authorized"))


def _hex_neighbors(q: int, r: int) -> list[tuple[int, int]]:
    return [(q + dq, r + dr) for dq, dr in HEX_DIRECTIONS]


@bp.route("/game_map/<path:token>")
def game_map_auth(token: str):
    """Visit this URL once to unlock access to /game_map in the current session."""
    if token == GAME_MAP_TOKEN:
        session["game_map_authorized"] = True
        return redirect("/game_map")
    abort(404)


@bp.route("/game_map")
def game_map_view():
    if not _is_authorized():
        abort(404)
    user_id = session.get("user_id")
    with get_request_cursor(read_only=True) as db:
        db.execute("SELECT gold, soldiers FROM stats s JOIN military m ON m.id = s.id WHERE s.id = %s", (user_id,))
        row = db.fetchone()
    gold = int(row[0]) if row else 0
    soldiers = int(row[1]) if row else 0
    return render_template(
        "game_map.html",
        user_id=user_id,
        gold=gold,
        soldiers=soldiers,
    )


@bp.route("/api/game_map/data")
@login_required
def game_map_data():
    if not _is_authorized():
        abort(404)

    user_id = session.get("user_id")
    with get_request_cursor(read_only=True) as db:
        # All provinces with coordinates, owner info, and deployment counts
        db.execute("""
            SELECT
                p.id,
                p.provinceName AS name,
                p.userId AS owner_id,
                u.username AS owner_name,
                COALESCE(p.coordinate_x, 0) AS q,
                COALESCE(p.coordinate_y, 0) AS r,
                COALESCE(p.pop_working, 0) + COALESCE(p.pop_children, 0) + COALESCE(p.pop_elderly, 0) AS population,
                COALESCE(d.soldiers, 0) AS deployed_soldiers,
                d.user_id AS deployer_id
            FROM provinces p
            JOIN users u ON p.userId = u.id
            LEFT JOIN map_unit_deployments d ON d.province_id = p.id
            WHERE p.coordinate_x IS NOT NULL AND p.coordinate_y IS NOT NULL
            ORDER BY p.id
        """)
        rows = db.fetchall()

        # Current user's military stockpile
        db.execute("SELECT gold, soldiers FROM stats s JOIN military m ON m.id = s.id WHERE s.id = %s", (user_id,))
        stats = db.fetchone()

        # Recent combat log
        db.execute("""
            SELECT
                cl.result,
                au.username AS attacker,
                du.username AS defender,
                p.provinceName AS province,
                cl.attacker_soldiers,
                cl.defender_soldiers,
                cl.occurred_at
            FROM map_combat_log cl
            JOIN users au ON cl.attacker_id = au.id
            LEFT JOIN users du ON cl.defender_id = du.id
            JOIN provinces p ON cl.province_id = p.id
            ORDER BY cl.occurred_at DESC
            LIMIT 20
        """)
        combat_rows = db.fetchall()

    provinces = []
    coord_to_province = {}
    for row in rows:
        prov = {
            "id": row[0],
            "name": str(row[1]),
            "owner_id": row[2],
            "owner_name": str(row[3]),
            "q": row[4],
            "r": row[5],
            "population": row[6],
            "deployed_soldiers": row[7],
            "deployer_id": row[8],
            "is_mine": row[2] == user_id,
        }
        provinces.append(prov)
        coord_to_province[(row[4], row[5])] = prov["id"]

    # Build adjacency: mark which provinces border each other
    adjacency = {}
    for prov in provinces:
        neighbors = []
        for nq, nr in _hex_neighbors(prov["q"], prov["r"]):
            neighbor_id = coord_to_province.get((nq, nr))
            if neighbor_id is not None:
                neighbors.append(neighbor_id)
        adjacency[prov["id"]] = neighbors

    combat_log = []
    for row in combat_rows:
        combat_log.append({
            "result": row[0],
            "attacker": row[1],
            "defender": row[2] or "Neutral",
            "province": row[3],
            "attacker_soldiers": row[4],
            "defender_soldiers": row[5],
            "occurred_at": row[6].isoformat() if row[6] else None,
        })

    return jsonify({
        "status": "success",
        "user_id": user_id,
        "gold": int(stats[0]) if stats else 0,
        "soldiers_stockpile": int(stats[1]) if stats else 0,
        "provinces": provinces,
        "adjacency": adjacency,
        "combat_log": combat_log,
    })


@bp.route("/api/game_map/deploy", methods=["POST"])
@login_required
def game_map_deploy():
    if not _is_authorized():
        abort(404)

    user_id = session.get("user_id")
    data = request.get_json(force=True) or {}
    province_id = data.get("province_id")
    amount = data.get("soldiers", 0)

    if not province_id or not isinstance(amount, int) or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid request."})

    with get_request_cursor() as db:
        # Verify user owns this province
        db.execute("SELECT userId FROM provinces WHERE id = %s", (province_id,))
        prov = db.fetchone()
        if not prov or prov[0] != user_id:
            return jsonify({"status": "error", "message": "You don't own this province."})

        # Check stockpile
        db.execute("SELECT soldiers FROM military WHERE id = %s FOR UPDATE", (user_id,))
        mil = db.fetchone()
        if not mil or mil[0] < amount:
            return jsonify({"status": "error", "message": f"Not enough soldiers in stockpile (have {mil[0] if mil else 0:,})."})

        # Deduct from stockpile
        db.execute("UPDATE military SET soldiers = soldiers - %s WHERE id = %s", (amount, user_id))

        # Add to deployment
        db.execute("""
            INSERT INTO map_unit_deployments (province_id, user_id, soldiers, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (province_id, user_id) DO UPDATE
              SET soldiers = map_unit_deployments.soldiers + EXCLUDED.soldiers,
                  updated_at = NOW()
        """, (province_id, user_id, amount))

    return jsonify({"status": "success", "message": f"Deployed {amount:,} soldiers."})


@bp.route("/api/game_map/retreat", methods=["POST"])
@login_required
def game_map_retreat():
    if not _is_authorized():
        abort(404)

    user_id = session.get("user_id")
    data = request.get_json(force=True) or {}
    province_id = data.get("province_id")
    amount = data.get("soldiers", 0)

    if not province_id or not isinstance(amount, int) or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid request."})

    with get_request_cursor() as db:
        db.execute(
            "SELECT soldiers FROM map_unit_deployments WHERE province_id = %s AND user_id = %s FOR UPDATE",
            (province_id, user_id),
        )
        dep = db.fetchone()
        if not dep or dep[0] < amount:
            return jsonify({"status": "error", "message": f"Only {dep[0] if dep else 0:,} soldiers deployed there."})

        new_amount = dep[0] - amount
        if new_amount == 0:
            db.execute(
                "DELETE FROM map_unit_deployments WHERE province_id = %s AND user_id = %s",
                (province_id, user_id),
            )
        else:
            db.execute(
                "UPDATE map_unit_deployments SET soldiers = %s, updated_at = NOW() WHERE province_id = %s AND user_id = %s",
                (new_amount, province_id, user_id),
            )

        db.execute("UPDATE military SET soldiers = soldiers + %s WHERE id = %s", (amount, user_id))

    return jsonify({"status": "success", "message": f"Retreated {amount:,} soldiers back to stockpile."})


@bp.route("/api/game_map/attack", methods=["POST"])
@login_required
def game_map_attack():
    if not _is_authorized():
        abort(404)

    user_id = session.get("user_id")
    data = request.get_json(force=True) or {}
    from_province_id = data.get("from_province_id")
    target_province_id = data.get("target_province_id")

    if not from_province_id or not target_province_id:
        return jsonify({"status": "error", "message": "Specify from_province_id and target_province_id."})

    if from_province_id == target_province_id:
        return jsonify({"status": "error", "message": "Cannot attack your own province."})

    with get_request_cursor() as db:
        # Validate attacker owns the source province
        db.execute("SELECT userId, coordinate_x, coordinate_y FROM provinces WHERE id = %s", (from_province_id,))
        src = db.fetchone()
        if not src or src[0] != user_id:
            return jsonify({"status": "error", "message": "You don't own that province."})

        # Validate target province exists and is adjacent
        db.execute("SELECT userId, coordinate_x, coordinate_y, provinceName FROM provinces WHERE id = %s", (target_province_id,))
        tgt = db.fetchone()
        if not tgt:
            return jsonify({"status": "error", "message": "Target province not found."})

        defender_id = tgt[0]
        if defender_id == user_id:
            return jsonify({"status": "error", "message": "That's your own province."})

        # Adjacency check
        sq, sr = src[1], src[2]
        tq, tr = tgt[1], tgt[2]
        neighbors = _hex_neighbors(sq, sr)
        if (tq, tr) not in neighbors:
            return jsonify({"status": "error", "message": "Provinces must be adjacent to attack."})

        target_name = tgt[3]

        # Attacker's deployed soldiers on source province (FOR UPDATE)
        db.execute(
            "SELECT soldiers FROM map_unit_deployments WHERE province_id = %s AND user_id = %s FOR UPDATE",
            (from_province_id, user_id),
        )
        atk_dep = db.fetchone()
        attacker_soldiers = atk_dep[0] if atk_dep else 0

        if attacker_soldiers < 100:
            return jsonify({"status": "error", "message": "You need at least 100 soldiers deployed on your source province to attack."})

        # Defender's deployed soldiers
        db.execute(
            "SELECT soldiers, user_id FROM map_unit_deployments WHERE province_id = %s FOR UPDATE",
            (target_province_id,),
        )
        def_dep = db.fetchone()
        defender_soldiers = def_dep[0] if def_dep else 0
        actual_defender_id = def_dep[1] if def_dep else defender_id

        # Combat: attacker wins if they have at least 50% more troops than defender
        # Losses are proportional
        attacker_wins = attacker_soldiers > (defender_soldiers * 1.5)

        if attacker_wins:
            # Attacker loses 50% of troops; defender loses all
            attacker_losses = max(attacker_soldiers // 2, 1)
            remaining_attackers = attacker_soldiers - attacker_losses

            # Update attacker's deployment on source province
            db.execute(
                "UPDATE map_unit_deployments SET soldiers = %s, updated_at = NOW() WHERE province_id = %s AND user_id = %s",
                (remaining_attackers, from_province_id, user_id),
            )

            # Clear defender's deployment on target province
            if def_dep:
                db.execute(
                    "DELETE FROM map_unit_deployments WHERE province_id = %s",
                    (target_province_id,),
                )
                # Return defender's lost troops to a "losses" table (just delete for now)

            # Transfer province ownership
            db.execute(
                "UPDATE provinces SET userId = %s WHERE id = %s",
                (user_id, target_province_id),
            )

            # Log the battle
            db.execute("""
                INSERT INTO map_combat_log
                  (attacker_id, defender_id, province_id, attacker_soldiers, defender_soldiers, result)
                VALUES (%s, %s, %s, %s, %s, 'attacker_won')
            """, (user_id, actual_defender_id, target_province_id, attacker_soldiers, defender_soldiers))

            result_msg = (
                f"Victory! Captured {target_name} with {remaining_attackers:,} survivors. "
                f"Defender had {defender_soldiers:,} troops."
            )
            return jsonify({"status": "success", "result": "attacker_won", "message": result_msg})

        else:
            # Defender wins. Attacker loses 75% of troops; defender loses 30%
            attacker_losses = max(int(attacker_soldiers * 0.75), attacker_soldiers)
            remaining_attackers = attacker_soldiers - attacker_losses

            defender_losses = max(int(defender_soldiers * 0.3), 0)
            remaining_defenders = defender_soldiers - defender_losses

            if remaining_attackers > 0:
                db.execute(
                    "UPDATE map_unit_deployments SET soldiers = %s, updated_at = NOW() WHERE province_id = %s AND user_id = %s",
                    (remaining_attackers, from_province_id, user_id),
                )
            else:
                db.execute(
                    "DELETE FROM map_unit_deployments WHERE province_id = %s AND user_id = %s",
                    (from_province_id, user_id),
                )

            if def_dep and remaining_defenders > 0:
                db.execute(
                    "UPDATE map_unit_deployments SET soldiers = %s, updated_at = NOW() WHERE province_id = %s",
                    (remaining_defenders, target_province_id),
                )

            # Log
            db.execute("""
                INSERT INTO map_combat_log
                  (attacker_id, defender_id, province_id, attacker_soldiers, defender_soldiers, result)
                VALUES (%s, %s, %s, %s, %s, 'defender_won')
            """, (user_id, actual_defender_id, target_province_id, attacker_soldiers, defender_soldiers))

            result_msg = (
                f"Repelled! {target_name} held. You lost {attacker_losses:,} soldiers. "
                f"Defender had {defender_soldiers:,} troops."
            )
            return jsonify({"status": "success", "result": "defender_won", "message": result_msg})


@bp.route("/api/game_map/move", methods=["POST"])
@login_required
def game_map_move():
    """Move soldiers between two adjacent provinces you own."""
    if not _is_authorized():
        abort(404)

    user_id = session.get("user_id")
    data = request.get_json(force=True) or {}
    from_province_id = data.get("from_province_id")
    to_province_id = data.get("to_province_id")
    amount = data.get("soldiers", 0)

    if not from_province_id or not to_province_id or not isinstance(amount, int) or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid request."})

    with get_request_cursor() as db:
        # Both must be owned by the user
        db.execute(
            "SELECT id, coordinate_x, coordinate_y FROM provinces WHERE id = ANY(%s) AND userId = %s",
            ([from_province_id, to_province_id], user_id),
        )
        owned = db.fetchall()
        if len(owned) < 2:
            return jsonify({"status": "error", "message": "You must own both provinces."})

        coords = {row[0]: (row[1], row[2]) for row in owned}
        fq, fr = coords[from_province_id]
        tq, tr = coords[to_province_id]

        if (tq, tr) not in _hex_neighbors(fq, fr):
            return jsonify({"status": "error", "message": "Provinces must be adjacent to move troops."})

        db.execute(
            "SELECT soldiers FROM map_unit_deployments WHERE province_id = %s AND user_id = %s FOR UPDATE",
            (from_province_id, user_id),
        )
        dep = db.fetchone()
        if not dep or dep[0] < amount:
            return jsonify({"status": "error", "message": f"Only {dep[0] if dep else 0:,} soldiers deployed there."})

        new_from = dep[0] - amount
        if new_from == 0:
            db.execute("DELETE FROM map_unit_deployments WHERE province_id = %s AND user_id = %s", (from_province_id, user_id))
        else:
            db.execute(
                "UPDATE map_unit_deployments SET soldiers = %s, updated_at = NOW() WHERE province_id = %s AND user_id = %s",
                (new_from, from_province_id, user_id),
            )

        db.execute("""
            INSERT INTO map_unit_deployments (province_id, user_id, soldiers, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (province_id, user_id) DO UPDATE
              SET soldiers = map_unit_deployments.soldiers + EXCLUDED.soldiers,
                  updated_at = NOW()
        """, (to_province_id, user_id, amount))

    return jsonify({"status": "success", "message": f"Moved {amount:,} soldiers."})
