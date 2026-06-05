from flask import Blueprint, request, render_template, session, redirect, flash, url_for
from helpers import login_required
from database import get_db_connection, get_request_cursor

treaties_bp = Blueprint("treaties", __name__)

@treaties_bp.route("/treaties", methods=["GET"])
@login_required
def view_treaties():
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        # Fetch active treaties
        db.execute("""
            SELECT t.id, t.treaty_type, t.created_at, u.username as other_nation, u.id as other_id, t.sender_id
            FROM treaties t
            JOIN users u ON (u.id = t.recipient_id AND t.sender_id = %s) OR (u.id = t.sender_id AND t.recipient_id = %s)
            WHERE t.status = 'active' AND (t.sender_id = %s OR t.recipient_id = %s)
        """, (user_id, user_id, user_id, user_id))
        active_treaties = db.fetchall()

        # Fetch pending incoming treaties
        db.execute("""
            SELECT t.id, t.treaty_type, t.created_at, u.username as sender_name, u.id as sender_id
            FROM treaties t
            JOIN users u ON u.id = t.sender_id
            WHERE t.status = 'pending' AND t.recipient_id = %s
        """, (user_id,))
        incoming_treaties = db.fetchall()

        # Fetch pending outgoing treaties
        db.execute("""
            SELECT t.id, t.treaty_type, t.created_at, u.username as recipient_name, u.id as recipient_id
            FROM treaties t
            JOIN users u ON u.id = t.recipient_id
            WHERE t.status = 'pending' AND t.sender_id = %s
        """, (user_id,))
        outgoing_treaties = db.fetchall()

    return render_template(
        "treaty.html",
        active_treaties=active_treaties,
        incoming_treaties=incoming_treaties,
        outgoing_treaties=outgoing_treaties,
        user_id=user_id
    )

@treaties_bp.route("/treaties/offer", methods=["POST"])
@login_required
def offer_treaty():
    sender_id = session.get("user_id")
    recipient_name = request.form.get("recipient_name")
    treaty_type = request.form.get("treaty_type")

    if treaty_type not in ["non_aggression", "mutual_defense"]:
        flash("Invalid treaty type.", "danger")
        return redirect(url_for("treaties.view_treaties"))

    with get_request_cursor() as db:
        db.execute("SELECT id FROM users WHERE username = %s", (recipient_name,))
        row = db.fetchone()
        if not row:
            flash("Nation not found.", "danger")
            return redirect(url_for("treaties.view_treaties"))
        
        recipient_id = row[0]
        if sender_id == recipient_id:
            flash("You cannot offer a treaty to yourself.", "danger")
            return redirect(url_for("treaties.view_treaties"))
        
        # Check if already active or pending
        db.execute("""
            SELECT id FROM treaties 
            WHERE status IN ('pending', 'active') AND treaty_type = %s AND 
            ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
        """, (treaty_type, sender_id, recipient_id, recipient_id, sender_id))
        if db.fetchone():
            flash("A treaty of this type is already pending or active with this nation.", "warning")
            return redirect(url_for("treaties.view_treaties"))

        db.execute("""
            INSERT INTO treaties (sender_id, recipient_id, treaty_type, status)
            VALUES (%s, %s, %s, 'pending')
        """, (sender_id, recipient_id, treaty_type))

    flash("Treaty offer sent!", "success")
    return redirect(url_for("treaties.view_treaties"))

@treaties_bp.route("/treaties/accept/<int:treaty_id>", methods=["POST"])
@login_required
def accept_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        db.execute("UPDATE treaties SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = %s AND recipient_id = %s AND status = 'pending'", (treaty_id, user_id))
    flash("Treaty accepted!", "success")
    return redirect(url_for("treaties.view_treaties"))

@treaties_bp.route("/treaties/reject/<int:treaty_id>", methods=["POST"])
@login_required
def reject_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        db.execute("UPDATE treaties SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = %s AND recipient_id = %s AND status = 'pending'", (treaty_id, user_id))
    flash("Treaty rejected.", "info")
    return redirect(url_for("treaties.view_treaties"))

@treaties_bp.route("/treaties/cancel/<int:treaty_id>", methods=["POST"])
@login_required
def cancel_treaty(treaty_id):
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        db.execute("UPDATE treaties SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = %s AND (sender_id = %s OR recipient_id = %s) AND status IN ('pending', 'active')", (treaty_id, user_id, user_id))
    flash("Treaty cancelled.", "info")
    return redirect(url_for("treaties.view_treaties"))
