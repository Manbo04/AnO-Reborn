from flask import Blueprint, render_template, request, redirect, session, flash
from helpers import login_required
from database import get_request_cursor

bp = Blueprint('game_engine_bp', __name__)

@bp.route("/recruitments", methods=["GET"])
@login_required
def recruitments():
    with get_request_cursor() as db:
        db.execute("SELECT id, name, type, description, flag FROM colNames WHERE recruiting=TRUE ORDER BY id ASC")
        cols = db.fetchall()
    return render_template("recruitments.html", coalitions=cols)

@bp.route("/businesses", methods=["GET"])
@login_required
def businesses():
    return render_template("businesses.html")

@bp.route("/country", methods=["GET"])
@login_required
def country_redirect():
    return redirect("/my_country")

@bp.route("/assembly", methods=["GET", "POST"])
@login_required
def assembly():
    user_id = session.get("user_id")
    poll_name = "world_name"
    with get_request_cursor() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS poll_votes (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            poll_name TEXT NOT NULL,
            vote_option TEXT NOT NULL,
            PRIMARY KEY (user_id, poll_name)
        )''')
        
        if request.method == "POST":
            vote_option = request.form.get("vote_option")
            if vote_option in ["Terra", "Aethelgard", "Nova Pangaea", "Gaia", "Eos"]:
                try:
                    db.execute('''INSERT INTO poll_votes (user_id, poll_name, vote_option) VALUES (%s, %s, %s)
                                  ON CONFLICT (user_id, poll_name) DO UPDATE SET vote_option = EXCLUDED.vote_option''', 
                               (user_id, poll_name, vote_option))
                    flash("Your vote has been cast!", "success")
                except Exception:
                    db.execute("ROLLBACK")
                    flash("Failed to cast vote.", "danger")
            else: flash("Invalid option.", "danger")
            return redirect("/assembly")

        db.execute("SELECT vote_option, COUNT(*) as vote_count FROM poll_votes WHERE poll_name = %s GROUP BY vote_option", (poll_name,))
        rows = db.fetchall()
        results = {}
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'): results[r['vote_option']] = r['vote_count']
            else: results[r[0]] = r[1]

        db.execute("SELECT vote_option FROM poll_votes WHERE user_id = %s AND poll_name = %s", (user_id, poll_name))
        row = db.fetchone()
        user_vote = (row['vote_option'] if (isinstance(row, dict) or hasattr(row, 'keys')) else row[0]) if row else None

    return render_template("assembly.html", results=results, user_vote=user_vote)


@bp.route("/war", methods=["GET"])
def war(): return redirect("/wars")

@bp.route("/warresult", methods=["GET"])
def warresult_deprecated(): return redirect("/warResult")

@bp.route("/mass_purchase", methods=["GET"])
@login_required
def mass_purchase():
    cId = session["user_id"]
    with get_request_cursor() as db:
        db.execute("SELECT id, provinceName as name, CAST(citycount AS INTEGER) as citycount, land FROM provinces WHERE userId=%s ORDER BY provinceName", (cId,))
        provinces = db.fetchall()
        province_list = []
        if provinces:
            colnames = [desc[0] for desc in db.description]
            for row in provinces: province_list.append(dict(zip(colnames, row)))
    return render_template("mass_purchase.html", provinces=province_list)
