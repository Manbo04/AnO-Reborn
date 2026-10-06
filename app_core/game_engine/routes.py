import logging
from flask import Blueprint, render_template, request, redirect, session, flash
from helpers import login_required, empty_state, is_theme_v2_enabled, get_influence
from database import get_request_cursor
from psycopg2.extras import RealDictCursor
from app_core.coalitions.repositories import _coalition_id_for_user

bp = Blueprint('game_engine_bp', __name__)

@bp.route("/recruitments", methods=["GET"])
@login_required
def recruitments():
    with get_request_cursor() as db:
        db.execute("SELECT id, name, type, description, flag FROM colNames WHERE recruiting=TRUE ORDER BY id ASC")
        cols = db.fetchall()
        own_coalition_id = _coalition_id_for_user(db, session["user_id"])
    template = "recruitments_v2.html" if is_theme_v2_enabled("recruitments") else "recruitments.html"
    return render_template(template, coalitions=cols, own_coalition_id=own_coalition_id)

@bp.route("/businesses", methods=["GET"])
@login_required
def businesses():
    return empty_state(
        "Businesses",
        "Businesses aren't available yet — check back later.",
        icon="business",
    )

@bp.route("/country", methods=["GET"])
@login_required
def country_redirect():
    return redirect("/my_country")

@bp.route("/assembly", methods=["GET", "POST"])
@login_required
def assembly():
    user_id = session.get("user_id")
    poll_name = "world_name"

    with get_request_cursor(cursor_factory=RealDictCursor) as db:
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
            else:
                flash("Invalid option.", "danger")
            return redirect("/assembly")

        db.execute("SELECT vote_option, COUNT(*) as vote_count FROM poll_votes WHERE poll_name = %s GROUP BY vote_option", (poll_name,))
        rows = db.fetchall()
        results = {r['vote_option']: r['vote_count'] for r in rows}

        db.execute("SELECT vote_option FROM poll_votes WHERE user_id = %s AND poll_name = %s", (user_id, poll_name))
        row = db.fetchone()
        user_vote = row['vote_option'] if row else None

        # --- Assembly Data ---
        # Each block runs inside a savepoint: if one query fails (e.g. a missing
        # assembly_* table/column) the page still loads with that section empty
        # instead of returning a 500 for the whole Assembly screen.
        def _safe_fetch(label, sql, params=None):
            db.execute("SAVEPOINT assembly_section")
            try:
                db.execute(sql, params)
                rows = db.fetchall()
                db.execute("RELEASE SAVEPOINT assembly_section")
                return rows
            except Exception:
                logging.exception("assembly page: %s query failed", label)
                db.execute("ROLLBACK TO SAVEPOINT assembly_section")
                return []

        # Fetch active sanctions/effects
        active_sanctions = _safe_fetch("sanctions", '''
            SELECT ae.*, u.username as target_name
            FROM assembly_effects ae
            LEFT JOIN users u ON ae.target_nation_id = u.id
            WHERE ae.active = TRUE AND (ae.expires_at IS NULL OR ae.expires_at > NOW())
        ''')

        # Fetch open proposals
        open_proposals = _safe_fetch("open proposals", '''
            SELECT ap.*,
                   COALESCE(SUM(CASE WHEN av.vote = 'for' THEN av.weight ELSE 0 END), 0) as votes_for,
                   COALESCE(SUM(CASE WHEN av.vote = 'against' THEN av.weight ELSE 0 END), 0) as votes_against,
                   COALESCE(SUM(CASE WHEN av.vote = 'abstain' THEN av.weight ELSE 0 END), 0) as votes_abstain,
                   (SELECT vote FROM assembly_votes WHERE proposal_id = ap.id AND voter_id = %s LIMIT 1) as my_vote,
                   pu.username as proposer_name, tu.username as target_name
            FROM assembly_proposals ap
            LEFT JOIN assembly_votes av ON ap.id = av.proposal_id
            LEFT JOIN users pu ON pu.id = ap.proposer_id
            LEFT JOIN users tu ON tu.id = ap.target_nation_id
            WHERE ap.status = 'open'
            GROUP BY ap.id, pu.username, tu.username
            ORDER BY ap.created_at DESC
        ''', (user_id,))

        # Fetch closed proposals
        closed_proposals = _safe_fetch("closed proposals", '''
            SELECT ap.*,
                   COALESCE(SUM(CASE WHEN av.vote = 'for' THEN av.weight ELSE 0 END), 0) as votes_for,
                   COALESCE(SUM(CASE WHEN av.vote = 'against' THEN av.weight ELSE 0 END), 0) as votes_against,
                   COALESCE(SUM(CASE WHEN av.vote = 'abstain' THEN av.weight ELSE 0 END), 0) as votes_abstain,
                   tu.username as target_name
            FROM assembly_proposals ap
            LEFT JOIN assembly_votes av ON ap.id = av.proposal_id
            LEFT JOIN users tu ON tu.id = ap.target_nation_id
            WHERE ap.status != 'open'
            GROUP BY ap.id, tu.username
            ORDER BY ap.closes_at DESC LIMIT 20
        ''')

    return render_template("assembly.html", results=results, user_vote=user_vote,
                           active_sanctions=active_sanctions, open_proposals=open_proposals, closed_proposals=closed_proposals)

@bp.route("/assembly/propose", methods=["GET", "POST"])
@login_required
def assembly_propose():
    user_id = session.get("user_id")
    if request.method == "GET":
        return render_template("assembly_propose.html")

    _VALID_TYPES = {'sanction', 'condemn', 'lift_sanction', 'currency_cap', 'free_text'}

    p_type = request.form.get("type", "")
    if p_type not in _VALID_TYPES:
        flash("Invalid proposal type.", "danger")
        return redirect("/assembly/propose")

    target_nation_id = request.form.get("target_nation_id")
    target_currency_id = request.form.get("target_currency_id")
    currency_cap_amount = request.form.get("currency_cap_amount")
    text = request.form.get("text", "").strip()[:2000]

    if not text:
        flash("Proposal text is required.", "danger")
        return redirect("/assembly/propose")

    target_nation_id = int(target_nation_id) if target_nation_id and target_nation_id.isdigit() else None
    target_currency_id = int(target_currency_id) if target_currency_id and target_currency_id.isdigit() else None
    currency_cap_amount = int(currency_cap_amount) if currency_cap_amount and currency_cap_amount.isdigit() else None

    if p_type in ('sanction', 'condemn', 'lift_sanction') and not target_nation_id:
        flash("Target nation ID is required for this proposal type.", "danger")
        return redirect("/assembly/propose")

    if p_type == 'currency_cap':
        if not target_currency_id or not currency_cap_amount or currency_cap_amount <= 0:
            flash("Target currency ID and a positive cap amount are required.", "danger")
            return redirect("/assembly/propose")
        target_nation_id = target_currency_id

    # Proposer cannot target themselves
    if target_nation_id and target_nation_id == user_id:
        flash("You cannot target your own nation.", "danger")
        return redirect("/assembly/propose")

    with get_request_cursor() as db:
        # Verify target nation exists
        if target_nation_id:
            db.execute("SELECT 1 FROM users WHERE id = %s", (target_nation_id,))
            if not db.fetchone():
                flash("Target nation does not exist.", "danger")
                return redirect("/assembly/propose")

        # Check eligibility: 5 provinces minimum
        db.execute("SELECT COUNT(*) FROM provinces WHERE userId = %s", (user_id,))
        prov_count = db.fetchone()[0]
        if prov_count < 5:
            flash("Your nation must have at least 5 provinces to submit a proposal.", "danger")
            return redirect("/assembly")

        # Check max 1 open proposal per nation
        db.execute("SELECT COUNT(*) FROM assembly_proposals WHERE proposer_id = %s AND status = 'open'", (user_id,))
        if db.fetchone()[0] > 0:
            flash("You already have an active proposal. Wait for it to conclude.", "danger")
            return redirect("/assembly")

        # Insert proposal
        db.execute('''
            INSERT INTO assembly_proposals (proposer_id, type, target_nation_id, target_currency_id, currency_cap_amount, text, closes_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW() + INTERVAL '48 hours')
        ''', (user_id, p_type, target_nation_id, target_currency_id, currency_cap_amount, text))

        flash("Proposal submitted successfully.", "success")
        return redirect("/assembly")

@bp.route("/assembly/vote/<int:proposal_id>", methods=["POST"])
@login_required
def assembly_vote(proposal_id):
    import math
    user_id = session.get("user_id")
    vote = request.form.get("vote")

    if vote not in ('for', 'against', 'abstain'):
        flash("Invalid vote option.", "danger")
        return redirect("/assembly")

    with get_request_cursor(cursor_factory=RealDictCursor) as db:
        # Get proposal — use RealDictCursor so prop['status'] and prop['target_nation_id'] work
        db.execute("SELECT proposer_id, target_nation_id, status FROM assembly_proposals WHERE id = %s", (proposal_id,))
        prop = db.fetchone()

        if not prop or prop['status'] != 'open':
            flash("Proposal not found or closed.", "danger")
            return redirect("/assembly")

        if prop['target_nation_id'] == user_id:
            flash("You cannot vote on proposals directly targeting your nation.", "danger")
            return redirect("/assembly")

        # Calculate vote weight using computed influence (users.influence does not exist)
        influence = get_influence(user_id, db=db) or 0
        weight = max(1.0, math.sqrt(influence))

        try:
            db.execute('''
                INSERT INTO assembly_votes (proposal_id, voter_id, vote, weight)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (proposal_id, voter_id) DO UPDATE SET vote = EXCLUDED.vote, weight = EXCLUDED.weight
            ''', (proposal_id, user_id, vote, weight))
            flash("Vote recorded.", "success")
        except Exception:
            db.execute("ROLLBACK")
            flash("Failed to record vote.", "danger")

    return redirect("/assembly")


@bp.route("/war", methods=["GET"])
def war(): return redirect("/wars")

@bp.route("/warresult", methods=["GET"])
def warresult_deprecated(): return redirect("/warResult")

@bp.route("/mass_purchase", methods=["GET"])
@login_required
def mass_purchase():
    from app_core.economy.building_costs import BUILDING_DISPLAY_NAMES, CITY_UNITS, LAND_UNITS
    import variables
    from app_core.economy import province_energy as pe
    from app_core.economy.tick_order import tax_due_before_next_upkeep, upkeep_budget
    from app_core.game_ticks.food import food_stats

    def _display(name):
        return BUILDING_DISPLAY_NAMES.get(name, name.replace("_", " ").title())

    cId = session["user_id"]
    with get_request_cursor() as db:
        db.execute("SELECT id, provinceName as name, CAST(citycount AS INTEGER) as citycount, land, productivity FROM provinces WHERE userId=%s ORDER BY id", (cId,))
        provinces = db.fetchall()
        province_list = []
        if provinces:
            colnames = [desc[0] for desc in db.description]
            for row in provinces: province_list.append(dict(zip(colnames, row)))

    # Player-requested status indicators (Mohammad, mass-purchase thread) --
    # so a bad province is visible in this list before opening it, instead of
    # having to click into each one individually. Electricity is a genuine
    # per-province figure (built consumers vs. producers in THAT province).
    # Rations are a *national* pool under FEATURE_RATIONS_DISTRIBUTION (see
    # province.py's enough_rations logic) -- showing a fake per-province
    # rations number would misrepresent the mechanic, so that's surfaced once
    # for the whole nation instead of duplicated per row.
    # Same calculation as the province page (pe.province_energy), so a
    # province /province shows as powered isn't flagged "Blackout" here.
    if province_list:
        with get_request_cursor() as db:
            energy_names = tuple(variables.ENERGY_CONSUMERS + variables.ENERGY_UNITS)
            db.execute(
                """
                SELECT ub.province_id, bd.name, ub.quantity
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s AND bd.name IN %s
                """,
                (cId, energy_names),
            )
            units_by_province = {}
            for r in db.fetchall():
                pid, name, qty = (r["province_id"], r["name"], r["quantity"]) if hasattr(r, "get") else r
                units_by_province.setdefault(pid, {})[name] = qty or 0

            db.execute(
                """
                SELECT td.name FROM user_tech ut
                JOIN tech_dictionary td ON td.tech_id = ut.tech_id
                WHERE ut.user_id = %s AND ut.is_unlocked = TRUE
                  AND td.name IN ('better_engineering', 'electric_arc_furnace')
                """,
                (cId,),
            )
            techs = {(r["name"] if hasattr(r, "get") else r[0]) for r in db.fetchall()}
            upgrades = {
                "betterengineering": "better_engineering" in techs,
                "electricarcfurnace": "electric_arc_furnace" in techs,
            }

            db.execute(
                """
                SELECT rd.name, ue.quantity FROM user_economy ue
                JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                WHERE ue.user_id = %s AND rd.name IN ('coal', 'oil', 'uranium')
                """,
                (cId,),
            )
            economy_values = {
                (r["name"] if hasattr(r, "get") else r[0]): (r["quantity"] if hasattr(r, "get") else r[1])
                for r in db.fetchall()
            }
            db.execute("SELECT gold FROM stats WHERE id=%s", (cId,))
            gold_row = db.fetchone()
            national_gold = ((gold_row["gold"] if hasattr(gold_row, "get") else gold_row[0]) or 0) if gold_row else 0
            efficiency = pe.national_efficiency_multiplier(db, cId)

        next_tax = None
        for province in province_list:
            units = units_by_province.get(province["id"], {})
            gold_budget = national_gold
            if pe.producer_upkeep(units) > national_gold and tax_due_before_next_upkeep():
                try:
                    if next_tax is None:
                        from countries import get_revenue

                        next_tax = get_revenue(cId).get("next_tax_income", 0) or 0
                    gold_budget = upkeep_budget(national_gold, next_tax)
                except Exception:
                    gold_budget = national_gold
            province["powered"] = pe.province_energy(
                units, upgrades, province.get("productivity"), efficiency,
                gold_budget, economy_values,
            )["has_power"]

    rations_ok = True
    if province_list:
        food_score = food_stats(cId)
        rations_ok = food_score >= -1.0

    template = "mass_purchase_v2.html" if is_theme_v2_enabled("mass_purchase") else "mass_purchase.html"
    city_buildings = sorted(({"name": n, "label": _display(n)} for n in CITY_UNITS), key=lambda b: b["label"])
    land_buildings = sorted(({"name": n, "label": _display(n)} for n in LAND_UNITS), key=lambda b: b["label"])
    return render_template(
        template,
        provinces=province_list,
        city_buildings=city_buildings,
        land_buildings=land_buildings,
        rations_ok=rations_ok,
    )
