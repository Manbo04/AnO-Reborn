"""War history: a public record of finished wars and the buildings lost in them."""
from datetime import datetime, timezone

from flask import Blueprint, render_template

from database import get_request_cursor
from helpers import error

war_history_bp = Blueprint("war_history", __name__)

HISTORY_LIMIT = 200


def record_building_loss(db, victim_id, building, quantity, source):
    """Log destroyed buildings against the victim's current war.

    Never raises: the log is a record, it must not break the attack that
    destroyed the buildings. Runs in a savepoint so a failure leaves the
    caller's transaction usable.
    """
    try:
        quantity = int(quantity)
        if quantity <= 0:
            return
        db.execute("SAVEPOINT war_building_loss")
        db.execute(
            "SELECT id FROM wars WHERE (attacker = %s OR defender = %s) "
            "AND peace_date IS NULL ORDER BY start_date DESC LIMIT 1",
            (victim_id, victim_id),
        )
        row = db.fetchone()
        if row:
            db.execute(
                "INSERT INTO war_building_losses "
                "(war_id, victim_id, building, quantity, source) "
                "VALUES (%s, %s, %s, %s, %s)",
                (row[0], victim_id, str(building), quantity, source),
            )
        db.execute("RELEASE SAVEPOINT war_building_loss")
    except Exception:
        try:
            db.execute("ROLLBACK TO SAVEPOINT war_building_loss")
        except Exception:
            pass


def _fmt(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%d %b %Y")


def _pretty(name):
    return str(name).replace("_", " ").title()


@war_history_bp.route("/war_history")
def war_history():
    with get_request_cursor() as db:
        db.execute(
            """
            SELECT w.id, w.attacker, a.username, w.defender, d.username,
                   w.war_type, w.start_date, w.peace_date, w.winner_id,
                   COALESCE((SELECT SUM(quantity) FROM war_building_losses l
                             WHERE l.war_id = w.id), 0)
            FROM wars w
            JOIN users a ON a.id = w.attacker
            JOIN users d ON d.id = w.defender
            ORDER BY w.start_date DESC
            LIMIT %s
            """,
            (HISTORY_LIMIT,),
        )
        wars = [
            {
                "id": r[0], "attacker_id": r[1], "attacker": r[2],
                "defender_id": r[3], "defender": r[4], "war_type": r[5],
                "start": _fmt(r[6]), "end": _fmt(r[7]), "winner_id": r[8],
                "buildings_lost": int(r[9] or 0), "ongoing": r[7] is None,
            }
            for r in db.fetchall()
        ]
    return render_template("war_history_v2.html", wars=wars)


@war_history_bp.route("/war_history/<int:war_id>")
def war_history_detail(war_id):
    with get_request_cursor() as db:
        db.execute(
            """
            SELECT w.id, w.attacker, a.username, w.defender, d.username,
                   w.war_type, w.start_date, w.peace_date, w.winner_id
            FROM wars w
            JOIN users a ON a.id = w.attacker
            JOIN users d ON d.id = w.defender
            WHERE w.id = %s
            """,
            (war_id,),
        )
        r = db.fetchone()
        if not r:
            return error(404, "This war doesn't exist")
        war = {
            "id": r[0], "attacker_id": r[1], "attacker": r[2],
            "defender_id": r[3], "defender": r[4], "war_type": r[5],
            "start": _fmt(r[6]), "end": _fmt(r[7]), "winner_id": r[8], "ongoing": r[7] is None,
        }
        db.execute(
            """
            SELECT l.victim_id, u.username, l.building, SUM(l.quantity)
            FROM war_building_losses l JOIN users u ON u.id = l.victim_id
            WHERE l.war_id = %s
            GROUP BY l.victim_id, u.username, l.building
            ORDER BY SUM(l.quantity) DESC
            """,
            (war_id,),
        )
        losses = [
            {"victim_id": x[0], "victim": x[1], "building": _pretty(x[2]), "qty": int(x[3])}
            for x in db.fetchall()
        ]
        db.execute(
            "SELECT target_id, COALESCE(SUM(buildings_destroyed), 0) "
            "FROM nuclear_strikes WHERE war_id = %s GROUP BY target_id",
            (war_id,),
        )
        nukes = {x[0]: int(x[1]) for x in db.fetchall() if x[1]}
    return render_template("war_history_detail_v2.html", war=war, losses=losses, nukes=nukes)
