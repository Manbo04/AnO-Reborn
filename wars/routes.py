from flask import Blueprint, session, request, redirect, render_template
from influence_formula import influence_subquery_sql
from helpers import (
    login_required,
    error,
    get_flagname,
    check_required,
    get_influence,
    is_theme_v2_enabled,
)
from database import get_db_connection, get_request_cursor, rollback_db_cursor
from attack_scripts.Nations import (
    Economy as AttackEconomy,
    Economy,
    Nation as AttackNation,
    Military,
)
from attack_scripts import Nation
import time
from datetime import datetime

from units import Units
import math
import random
import traceback

import variables
from wars.service import apply_building_damage, apply_population_strike
from app_core.world_affairs.services import log_event

# Add any other necessary imports here

# Define the wars Blueprint
wars_bp = Blueprint("wars", __name__)


# Peace offers show up here
@wars_bp.route("/peace_offers", methods=["POST", "GET"])
@login_required
def peace_offers():
    cId = session["user_id"]

    with get_request_cursor() as db:
        db.execute(
            "SELECT peace_offer_id FROM wars WHERE "
            "(attacker=(%s) OR defender=(%s)) AND peace_date IS NULL",
            (cId, cId),
        )
        peace_offers = db.fetchall()
        incoming_counter = 0
        outgoing_counter = 0

        incoming = {}
        outgoing = {}

        resources = []

        try:
            if peace_offers:
                # OPTIMIZATION: Batch fetch all peace offer data in fewer queries
                offer_ids = [o[0] for o in peace_offers if o[0] is not None]

                if offer_ids:
                    # Fetch all peace data at once
                    placeholders = ",".join(["%s"] * len(offer_ids))
                    db.execute(
                        (
                            "SELECT p.id, p.demanded_resources, p.demanded_amount, "
                            "p.author, u.username as author_name, w.attacker, "
                            "w.defender FROM peace p "
                            "JOIN users u ON p.author = u.id "
                            "JOIN wars w ON w.peace_offer_id = p.id "
                            "AND w.peace_date IS NULL "
                            "WHERE p.id IN (" + placeholders + ")"
                        ),
                        tuple(offer_ids),
                    )
                    peace_data = {row[0]: row for row in db.fetchall()}

                    # Fetch all user names we might need
                    all_user_ids = set()
                    for row in peace_data.values():
                        all_user_ids.add(row[5])  # attacker
                        all_user_ids.add(row[6])  # defender

                    if all_user_ids:
                        user_placeholders = ",".join(["%s"] * len(all_user_ids))
                        db.execute(
                            (
                                "SELECT id, username FROM users "
                                "WHERE id IN (" + user_placeholders + ")"
                            ),
                            tuple(all_user_ids),
                        )
                        usernames = {row[0]: row[1] for row in db.fetchall()}
                    else:
                        usernames = {}

                    for offer in peace_offers:
                        offer_id = offer[0]
                        if offer_id is None or offer_id not in peace_data:
                            continue

                        row = peace_data[offer_id]
                        (
                            _,
                            demanded_resources,
                            demanded_amount,
                            author_id,
                            author_name,
                            attacker,
                            defender,
                        ) = row

                        if author_id == cId:
                            target_dict = outgoing
                            outgoing_counter += 1
                        else:
                            target_dict = incoming
                            incoming_counter += 1

                        target_dict[offer_id] = {}

                        if demanded_resources:
                            resources = demanded_resources.split(",")
                            amounts = (
                                demanded_amount.split(",") if demanded_amount else []
                            )
                            target_dict[offer_id]["resource_count"] = len(resources)
                            target_dict[offer_id]["resources"] = resources
                            target_dict[offer_id]["amounts"] = amounts
                            if cId == author_id:
                                target_dict[offer_id]["owned"] = 1
                        else:
                            target_dict[offer_id]["peace_type"] = "white"

                        target_dict[offer_id]["author"] = [author_id, author_name]

                        if attacker == author_id:
                            receiver_id = defender
                        else:
                            receiver_id = attacker

                        target_dict[offer_id]["receiver_id"] = receiver_id
                        target_dict[offer_id]["receiver"] = usernames.get(
                            receiver_id, "Unknown"
                        )
        except (TypeError, AttributeError, IndexError, KeyError):
            return error(500, "Something went wrong.")

    if request.method == "POST":
        offer_id = request.form.get("peace_offer", None)

        # Validate inputs
        try:
            offer_id = int(offer_id)
        except (ValueError, TypeError):
            return error(400, "Invalid offer ID")

        decision = request.form.get("decision", None)

        # operate using a db connection (we need both cursor and
        # connection for set_peace)
        with get_db_connection() as connection:
            db = connection.cursor()

            # Make sure others can't accept/delete/etc. the peace
            # offer other than the participants
            db.execute(
                "SELECT id, attacker, defender FROM wars WHERE "
                "(attacker=(%s) OR defender=(%s)) AND peace_offer_id=(%s) "
                "AND peace_date IS NULL",
                (cId, cId, offer_id),
            )
            result = db.fetchone()
            if not result:
                return error(400, "Invalid peace offer")

            # load the offer author and desired resources
            db.execute(
                (
                    "SELECT author, demanded_resources, demanded_amount "
                    "FROM peace WHERE id=(%s)"
                ),
                (offer_id,),
            )
            row = db.fetchone()
            if not row:
                return error(400, "Invalid peace offer data")
            author_id = row[0]
            demanded_resources = row[1] or ""
            demanded_amount = row[2] or ""

            # Offer rejected or revoked
            if decision == "0":
                db.execute(
                    "UPDATE wars SET peace_offer_id=NULL WHERE peace_offer_id=(%s)",
                    (offer_id,),
                )
                db.execute("DELETE FROM peace WHERE id=(%s)", (offer_id,))
                return redirect("/peace_offers")

            # Make sure user is not author
            if author_id == cId:
                return error(403, "You can't accept your own offer.")

            # Offer accepted
            if decision == "1":
                # Parse resources/amounts into lists
                resources = (
                    [r for r in demanded_resources.split(",") if r]
                    if demanded_resources
                    else []
                )
                amounts = (
                    [a for a in demanded_amount.split(",") if a]
                    if demanded_amount
                    else []
                )

                eco = AttackEconomy(cId)
                try:
                    resource_dict = eco.get_particular_resources(resources)
                except Exception:
                    rollback_db_cursor(db)
                    return error(400, "Invalid resource requested in peace offer")

                # If function returned a non-dict (e.g. empty or invalid result),
                # normalize it to a dict
                if not isinstance(resource_dict, dict):
                    resource_dict = {}

                # Validate amounts and process transfers
                for idx, res in enumerate(resources):
                    try:
                        required = int(amounts[idx]) if idx < len(amounts) else 0
                    except (ValueError, IndexError):
                        return error(400, "Invalid requested resource amount")
                    available = resource_dict.get(res, 0)
                    if required > available:
                        return error(
                            400,
                            (
                                "Can't accept peace offer because you don't have the "
                                "required resources: "
                                f"{required} > {available}"
                            ),
                        )
                    from app_core.market import give_resource

                    successful = give_resource(cId, author_id, res, required)
                    if successful is not True:
                        return error(400, successful)

                # commit peace (we pass the DB cursor and real connection)
                AttackNation.set_peace(
                    db,
                    connection,
                    None,
                    {"option": "peace_offer_id", "value": offer_id},
                )
                try:
                    _record_peace_news(
                        db, cId, author_id, dict(zip(resources, amounts))
                    )
                except Exception:
                    rollback_db_cursor(db)
                return redirect("/peace_offers")

            return error(400, "No decision was made.")

    return render_template(
        "peace/peace_offers.html",
        cId=cId,
        incoming_peace_offers=incoming,
        outgoing_peace_offers=outgoing,
        incoming_counter=incoming_counter,
        outgoing_counter=outgoing_counter,
    )


def _record_peace_news(db, accepter_id, author_id, paid):
    """News for both sides when a peace offer ends a war (Silent, 2026-10-04)."""
    db.execute(
        "SELECT id, username FROM users WHERE id IN (%s, %s)", (accepter_id, author_id)
    )
    names = {row[0]: row[1] for row in db.fetchall()}
    accepter = names.get(accepter_id, "Unknown")
    author = names.get(author_id, "Unknown")
    terms = ", ".join(
        f"{int(a):,} {r.replace('_', ' ')}" for r, a in paid.items() if int(a or 0)
    )
    author_msg = f"🕊️ PEACE: {accepter} accepted your peace offer. The war is over." + (
        f" You received: {terms}." if terms else ""
    )
    accepter_msg = f"🕊️ PEACE: You accepted {author}'s peace offer. The war is over." + (
        f" You paid: {terms}." if terms else ""
    )
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s), (%s, %s)",
        (author_id, author_msg, accepter_id, accepter_msg),
    )


# Send peace offer
@wars_bp.route("/send_peace_offer/<int:war_id>/<int:enemy_id>", methods=["POST"])
@login_required
def send_peace_offer(war_id, enemy_id):
    cId = session["user_id"]
    if request.method == "POST":
        resources = []
        resources_amount = []
        validResources = list(Economy.resources)
        validResources.append("money")
        try:
            for resource in validResources:
                amount = request.form.get(resource, None)
                if amount:
                    amo = int(amount)
                    if amo:
                        resources.append(resource)
                        resources_amount.append(amo)
        except (ValueError, TypeError):
            return error(400, "Invalid offer!")
        with get_request_cursor() as db:
            if not war_id:
                return error(400, "War id is invalid")
            db.execute(
                "SELECT attacker, defender FROM wars WHERE id=%s",
                (war_id,),
            )
            war_row = db.fetchone()
            if not war_row:
                return error(404, "War not found")
            if cId not in (war_row[0], war_row[1]):
                return error(403, "You are not a participant in this war")
            resources_string = ""
            amount_string = ""
            if len(resources) and len(resources_amount):
                for res, amo in zip(resources, resources_amount):
                    if res not in validResources:
                        return error(400, "Invalid resource")
                    resources_string += res + ","
                    amount_string += str(amo) + ","
            db.execute("SELECT peace_offer_id FROM wars WHERE id=(%s)", (war_id,))
            peace_row = db.fetchone()
            peace_offer_id = peace_row[0] if peace_row else None
            if not peace_offer_id:
                db.execute(
                    (
                        "INSERT INTO peace (author,demanded_resources,demanded_amount) "
                        "VALUES ((%s),(%s),(%s))"
                    ),
                    (cId, resources_string[:-1], amount_string[:-1]),
                )
                db.execute("SELECT CURRVAL('peace_id_seq')")
                peace_id_row = db.fetchone()
                if not peace_id_row:
                    return error(500, "Failed to create peace offer")
                lastrowid = peace_id_row[0]
                db.execute(
                    "UPDATE wars SET peace_offer_id=(%s) " "WHERE id=(%s)",
                    (lastrowid, war_id),
                )
            else:
                db.execute(
                    (
                        "UPDATE peace SET author=(%s),demanded_resources=(%s),"
                        "demanded_amount=(%s)"
                    ),
                    (cId, resources_string[:-1], amount_string[:-1]),
                )
            try:
                from app_core.discord_notify import notify_peace_offer

                db.execute(
                    "SELECT id, username FROM users WHERE id IN (%s, %s)",
                    (cId, enemy_id),
                )
                by_id = {int(row[0]): row[1] for row in db.fetchall()}
                notify_peace_offer(
                    by_id.get(cId, str(cId)),
                    by_id.get(enemy_id, str(enemy_id)),
                )
            except Exception:
                pass
        return redirect("/peace_offers")


# War details page
@wars_bp.route("/war/<int:war_id>", methods=["GET"])
@login_required
def war_with_id(war_id):
    with get_request_cursor() as db:
        # Single query to get all war data
        db.execute(
            (
                "SELECT id, attacker, defender, war_type, agressor_message, "
                "peace_date, attacker_supplies, attacker_morale, "
                "defender_supplies, defender_morale FROM wars WHERE id=(%s)"
            ),
            (war_id,),
        )
        war = db.fetchone()
        if not war:
            return error(404, "This war doesn't exist")

        # Unpack war data (tuple access by position)
        (
            war_id_db,
            attacker,
            defender,
            war_type,
            agressor_message,
            peace_date,
            attacker_supplies,
            attacker_morale,
            defender_supplies,
            defender_morale,
        ) = war

        if peace_date:
            return "This war already ended"

        cId = session["user_id"]

        # Single query to get both usernames
        db.execute(
            "SELECT id, username FROM users WHERE id IN (%s, %s)", (attacker, defender)
        )
        user_rows = db.fetchall()
        usernames = {row[0]: row[1] for row in user_rows}
        attacker_name = usernames.get(attacker, "Unknown")
        defender_name = usernames.get(defender, "Unknown")

        defender_info = {"morale": defender_morale, "supplies": defender_supplies}
        attacker_info = {"morale": attacker_morale, "supplies": attacker_supplies}

        if cId == defender:
            cId_type = "defender"
        elif cId == attacker:
            cId_type = "attacker"
        else:
            cId_type = "spectator"

        attacker_flag = get_flagname(attacker)
        defender_flag = get_flagname(defender)
        template = "war_v2.html" if is_theme_v2_enabled("wars") else "war.html"

        # Anyone can watch a war; only the two sides get the attack, spy and
        # peace controls. Spectators must not touch session["enemy_id"], which
        # the attack flow trusts.
        if cId_type == "spectator":
            return render_template(
                template,
                attacker_flag=attacker_flag,
                defender_flag=defender_flag,
                defender_info=defender_info,
                defender=defender,
                attacker_info=attacker_info,
                attacker=attacker,
                war_id=war_id,
                attacker_name=attacker_name,
                defender_name=defender_name,
                war_type=war_type,
                agressor_message=agressor_message,
                cId_type=cId_type,
            )

        enemy_id = defender if cId == attacker else attacker
        session["enemy_id"] = enemy_id
        db.execute(
            "SELECT COALESCE(um.quantity, 0) FROM unit_dictionary ud "
            "LEFT JOIN user_military um ON um.unit_id = ud.unit_id AND um.user_id = %s "
            "WHERE LOWER(ud.name) = 'spies' AND ud.is_active = TRUE",
            (cId,),
        )
        spy_result = db.fetchone()
        spyCount = spy_result[0] if spy_result else 0
        spyPrep = 1
        eSpyCount = 0
        eDefcon = 1
        if eSpyCount == 0:
            successChance = 100
        else:
            successChance = spyCount * spyPrep / eSpyCount / eDefcon
        return render_template(
            template,
            attacker_flag=attacker_flag,
            defender_flag=defender_flag,
            defender_info=defender_info,
            defender=defender,
            attacker_info=attacker_info,
            attacker=attacker,
            war_id=war_id,
            attacker_name=attacker_name,
            defender_name=defender_name,
            war_type=war_type,
            agressor_message=agressor_message,
            cId_type=cId_type,
            spyCount=spyCount,
            successChance=successChance,
            peace_to_send=enemy_id,
            repeat_attack=_repeat_attack_ctx(war_id),
        )


# ...existing code...


# "Repeat last attack" (Silent, 2026-10-04): raiding meant walking
# war -> warchoose -> waramount (-> wartarget) -> warResult for every single
# strike. The last attack sent in each war is remembered in the session so
# it can be fired again in one click from the war page or the result page.
_LAST_ATTACK_MAX_WARS = 10


def _remember_last_attack(war_id, entry):
    if not war_id:
        return
    store = dict(session.get("last_attack") or {})
    key = str(war_id)
    store.pop(key, None)
    store[key] = entry
    while len(store) > _LAST_ATTACK_MAX_WARS:
        store.pop(next(iter(store)))
    session["last_attack"] = store


def _last_attack_for(war_id):
    if not war_id:
        return None
    entry = (session.get("last_attack") or {}).get(str(war_id))
    if not isinstance(entry, dict) or not entry.get("units"):
        return None
    return entry


def _last_attack_label(entry):
    parts = [
        f"{int(q):,} {u.replace('_', ' ')}"
        for u, q in (entry.get("units") or {}).items()
        if int(q or 0) > 0
    ]
    label = ", ".join(parts) or "nothing"
    if entry.get("target"):
        label += f" at their {entry['target'].replace('_', ' ')}"
    return label


def _repeat_attack_ctx(war_id):
    entry = _last_attack_for(war_id)
    if not entry:
        return None
    return {"war_id": war_id, "label": _last_attack_label(entry)}


@wars_bp.route("/war/<int:war_id>/repeat_attack", methods=["POST"])
@login_required
@check_required
def repeat_attack(war_id):
    """Re-send the last attack made in this war with one click. Amounts are
    capped at what's still owned, so losses from the previous strike don't
    turn the button into an error."""
    cId = session["user_id"]
    entry = _last_attack_for(war_id)
    if not entry:
        return error(400, "No previous attack to repeat in this war.")
    with get_request_cursor() as db:
        db.execute(
            "SELECT attacker, defender FROM wars WHERE id=%s AND peace_date IS NULL",
            (war_id,),
        )
        row = db.fetchone()
    if not row or cId not in (row[0], row[1]):
        return error(400, "This war is over or you're not in it.")
    eId = row[1] if cId == row[0] else row[0]

    wanted = {u: int(q or 0) for u, q in (entry.get("units") or {}).items()}
    if any(u not in Military.allUnits for u in wanted):
        return error(400, "Invalid unit type!")
    owned = Military.get_military(cId)
    owned.update(Military.get_special(cId))
    units = {u: min(q, int(owned.get(u, 0) or 0)) for u, q in wanted.items()}
    if not sum(units.values()):
        return error(400, "You have none of those units left to send.")

    attack_units = Units(cId, war_id=war_id)
    if entry.get("special"):
        target = entry.get("target")
        if len(units) != 1 or not target or target not in Military.allUnits:
            return error(400, "Invalid attack request. Please start again.")
        err = attack_units.attach_units(units, 1)
        if err:
            return error(400, err)
        session["enemy_id"] = eId
        session["war_domain"] = None
        session["attack_units"] = attack_units.__dict__
        return _resolve_special_attack(attack_units, eId, target)

    domain = entry.get("domain")
    if domain not in Military.UNIT_DOMAINS or len(units) != 3:
        return error(400, "Invalid attack request. Please start again.")
    err = attack_units.attach_units(units, 3)
    if err:
        return error(400, err)
    session["enemy_id"] = eId
    session["war_domain"] = domain
    session["attack_units"] = attack_units.__dict__
    return redirect("/warResult")


@wars_bp.route("/warchoose/<int:war_id>", methods=["GET", "POST"])
@login_required
@check_required
def warChoose(war_id):
    cId = session["user_id"]
    if request.method == "GET":
        normal_units = Military.get_military(cId)
        special_units = Military.get_special(cId)
        units = normal_units.copy()
        units.update(special_units)
        template = "warchoose_v2.html" if is_theme_v2_enabled("wars") else "warchoose.html"
        return render_template(template, units=units, war_id=war_id)
    elif request.method == "POST":
        selected_units = {}
        special_unit = request.form.get("special_unit")
        if special_unit == "nukes":
            # Nukes hit one chosen province via the nuclear strike planner
            # (two-step confirm + influence cost), never the unit-fight path.
            return redirect(f"/nuclear_strike/{war_id}")
        if special_unit:
            selected_units[special_unit] = 0
            unit_amount = 1
            session["war_domain"] = None
        else:
            # The attacker declares one attack domain (ground/naval/air) for
            # this strike. That domain's 3 unit types are used automatically
            # — a destroyer can't be sent to a ground invasion it can't
            # reach, so there's nothing left to hand-pick once the domain is
            # chosen.
            domain = request.form.get("domain")
            if domain not in Military.UNIT_DOMAINS:
                return error(
                    400, "Please select an attack type (Ground, Naval, or Air)"
                )
            for unit in Military.UNIT_DOMAINS[domain]:
                selected_units[unit] = 0
            unit_amount = 3
            session["war_domain"] = domain
        attack_units = Units(cId, war_id=war_id)
        return_error = attack_units.attach_units(selected_units, unit_amount)
        if return_error:
            return error(400, return_error)
        session["attack_units"] = attack_units.__dict__
        return redirect("/waramount")


@wars_bp.route("/waramount", methods=["GET", "POST"])
@login_required
@check_required
def warAmount():
    cId = session["user_id"]
    attack_unit_session = session.get("attack_units")
    if not attack_unit_session:
        return error(
            400,
            "No attack units selected. Please start again.",
        )
    try:
        attack_units = Units.rebuild_from_dict(attack_unit_session)
    except Exception:
        return error(
            400,
            "Attack session expired. Please start again.",
        )
    if not attack_units.selected_units:
        return error(
            400,
            "No attack units selected. Please start again.",
        )
    if request.method == "GET":
        unitamounts = Military.get_particular_units_list(
            cId, attack_units.selected_units_list
        )
        template = "waramount_v2.html" if is_theme_v2_enabled("wars") else "waramount.html"
        return render_template(
            template,
            available_supplies=attack_units.available_supplies,
            selected_units=attack_units.selected_units_list,
            unit_range=len(unitamounts),
            unitamounts=unitamounts,
            unit_interfaces=Units.allUnitInterfaces,
        )
    elif request.method == "POST":
        selected_units = attack_units.selected_units.copy()
        units_name = list(selected_units.keys())
        if len(units_name) == 3:
            for unit in units_name:
                if unit not in Military.allUnits:
                    return error(400, "Invalid unit type!")
                unit_amount = request.form.get(unit)
                try:
                    selected_units[unit] = int(unit_amount)
                except (ValueError, TypeError):
                    return error(400, "Unit amount entered was not a number")
            if not sum(selected_units.values()):
                return error(400, "Can't attack because you haven't sent any units")
            err_valid = attack_units.attach_units(selected_units, 3)
            if err_valid:
                return error(400, err_valid)
            session["attack_units"] = attack_units.__dict__
            return redirect("/warResult")
        elif len(units_name) == 1:
            amount_str = request.form.get(units_name[0])
            if not amount_str:
                return error(400, "Can't attack because you haven't sent any units")
            try:
                amount = int(amount_str)
            except (ValueError, TypeError):
                return error(400, "Unit amount must be a valid number")
            if not amount:
                return error(400, "Can't attack because you haven't sent any units")
            selected_units[units_name[0]] = amount
            err_valid = attack_units.attach_units(selected_units, 1)
            if err_valid:
                return error(400, err_valid)
            session["attack_units"] = attack_units.__dict__
            return redirect("/wartarget")
        else:
            return error(400, "Invalid attack request. Please start again.")


def _resolve_special_attack(attack_units, eId, target):
    """Fire a special-unit strike at one enemy unit type (wartarget POST and
    the repeat-attack button both land here)."""
    target_amount = Military.get_particular_units_list(eId, [target])
    defender = Units(eId, {target: target_amount[0]}, selected_units_list=[target])
    # FIXED 2026-09-23: same replay race as warResult() (see its
    # docstring for the full mechanism) -- attack_units is sourced
    # from the client-side signed session cookie with no server-side
    # session store, and this POST route has no idempotency check
    # before Military.special_fight() applies casualties/infra damage
    # and decrements the attacker's special unit via its own
    # independent, immediately-committing connection. A double-click
    # or resubmitted POST carrying the same still-valid stale cookie
    # could apply a second round of damage from a single special
    # attack (e.g. a nuke/ICBM sent via this legacy special-unit path,
    # separate from the dedicated /nuclear_strike route also fixed
    # this session). Reuses the same wars.last_attack_resolved_at gate
    # (migrations/0081) added for warResult -- one shared "has this
    # war's most recent attack already been resolved" gate covers
    # both paths a war's combat can be resolved through.
    if attack_units.war_id is not None:
        now_ts = time.time()
        with get_request_cursor() as db:
            db.execute(
                """
                UPDATE wars SET last_attack_resolved_at = %s
                WHERE id = %s
                  AND (last_attack_resolved_at IS NULL OR %s - last_attack_resolved_at >= 1)
                RETURNING id
                """,
                (now_ts, attack_units.war_id, now_ts),
            )
            if not db.fetchone():
                session.pop("attack_units", None)
                session.pop("enemy_id", None)
                session.pop("war_domain", None)
                return error(
                    400,
                    "This attack was already resolved. Please start a new attack.",
                )
            # Commit the guard now: special_fight() updates this same wars
            # row on its own connection, and an uncommitted row lock here
            # makes it wait on us until the 30s statement timeout.
            db.connection.commit()

    requested = {u: int(q or 0) for u, q in (attack_units.selected_units or {}).items()}
    special_fight_result = Military.special_fight(
        attack_units, defender, defender.selected_units_list[0]
    )
    if isinstance(special_fight_result, str):
        return special_fight_result
    _remember_last_attack(
        attack_units.war_id, {"special": True, "units": requested, "target": target}
    )
    session["from_wartarget"] = special_fight_result
    return redirect("/warResult")


@wars_bp.route("/wartarget", methods=["GET", "POST"])
@login_required
def warTarget():
    cId = session["user_id"]
    eId = session.get("enemy_id")
    if eId is None:
        return error(400, "No enemy selected. Please start again.")
    if request.method == "GET":
        with get_request_cursor() as db:
            db.execute(
                "SELECT * FROM spyinfo WHERE spyer=(%s) AND spyee=(%s)",
                (
                    cId,
                    eId,
                ),
            )
            revealed_info = db.fetchall()
        needed_types = [
            "soldiers",
            "tanks",
            "artillery",
            "fighters",
            "bombers",
            "apaches",
            "destroyers",
            "cruisers",
            "submarines",
        ]
        units = {t: "?" for t in needed_types}
        return render_template(
            "wartarget.html",
            units=units,
            revealed_info=revealed_info,
            needed_types=needed_types,
        )
    if request.method == "POST":
        target = request.form.get("targeted_unit")
        if not target or target not in Military.allUnits:
            return error(400, "Invalid target unit type")
        attack_unit_session = session.get("attack_units")
        if not attack_unit_session:
            return error(
                400,
                "Attack session expired. Please start again.",
            )
        try:
            attack_units = Units.rebuild_from_dict(attack_unit_session)
        except Exception:
            return error(
                400,
                "Attack session expired. Please start again.",
            )

        return _resolve_special_attack(attack_units, eId, target)


@wars_bp.route("/warResult", methods=["GET"])
@login_required
def warResult():
    import logging

    logger = logging.getLogger(__name__)
    logger.debug("Entering warResult")
    attack_unit_session = session.get("attack_units", None)
    logger.debug("attack_units present in session: %s", bool(attack_unit_session))
    if attack_unit_session is None:
        # If no attack units are set in session, render a neutral war result
        # page indicating there is no winner.
        logger.debug("Rendering neutral warResult page (no attack_units)")
        return render_template(
            "warResult.html",
            winner=None,
            win_condition=None,
            defender_result={"nation_name": ""},
            attacker_result={"nation_name": ""},
        )
    try:
        attacker = Units.rebuild_from_dict(attack_unit_session)
    except Exception:
        logger.exception("Failed to rebuild Units from session")
        session.pop("attack_units", None)
        session.pop("war_domain", None)
        return error(
            400,
            "Attack session expired. Please start again.",
        )
    eId = session.get("enemy_id")
    if eId is None:
        session.pop("attack_units", None)
        session.pop("war_domain", None)
        return error(400, "No enemy selected. Please start again.")
    with get_request_cursor() as db:
        db.execute("SELECT username FROM users WHERE id=(%s)", (session["user_id"],))
        row = db.fetchone()
        attacker_name = row[0] if row else "Unknown"
        db.execute("SELECT username FROM users WHERE id=(%s)", (eId,))
        row = db.fetchone()
        defender_name = row[0] if row else "Unknown"
        attacker_result = {"nation_name": attacker_name}
        defender_result = {"nation_name": defender_name}
        win_condition = None
        winner = None
        result = session.get("from_wartarget", None)
        if result is None:
            # Determine what the defender is actually defending with: their
            # saved `/defense` composition if they've set one, otherwise the
            # top-3-owned-by-quantity auto-pick (legacy behaviour).
            from attack_scripts.war_orchestrator import resolve_defender_composition

            war_domain = session.get("war_domain")
            defenselst, defenseunits = resolve_defender_composition(eId, war_domain)

            defender = Units(eId, dict(defenseunits), selected_units_list=defenselst)
            prev_attacker = dict(attacker.selected_units)
            db.execute(
                (
                    "SELECT id, war_type FROM wars "
                    "WHERE ((attacker=%s AND defender=%s) "
                    "OR (attacker=%s AND defender=%s)) "
                    "AND peace_date IS NULL"
                ),
                (
                    attacker.user_id,
                    defender.user_id,
                    defender.user_id,
                    attacker.user_id,
                ),
            )
            war_rows = db.fetchall()
            if not war_rows:
                return error(500, "Something went wrong")
            war_id_for_guard, war_type = war_rows[-1]

            # War supply asymmetry fix (wars/supply.py): the defender now
            # pays supply for the units it fields, from its own pool on this
            # war, with a flat 200 floor. If the full army costs more than
            # that, every unit type defends at the same reduced share. With
            # nothing combat-capable left in this domain, a Citizen Army
            # (no supply) fights instead and bleeds the attacker.
            from wars import supply as war_supply

            defense_pool = war_supply.read_supply_pool(db, war_id_for_guard, eId)
            defense_budget = war_supply.defense_supply_budget(defense_pool)
            fielded_units, defense_spend = war_supply.ration_defenders(
                defenseunits, defense_budget, unusable=defender.unusable_units
            )
            defender.selected_units = fielded_units
            prev_defender = dict(fielded_units)
            citizen_pct = None
            # Citizen army only defends on ground combat against land invasions.
            # Air and naval attacks do not fight ground citizen militias (fikusmikus suggestion).
            if (war_domain == "ground" or war_domain is None) and sum(fielded_units.values()) == 0:
                pop_total, prov_count = war_supply.get_population_and_provinces(
                    db, eId
                )
                citizen_pct = war_supply.citizen_army_pct(pop_total, prov_count)
            defender_result["supply"] = {
                "pool_before": defense_pool,
                "budget": defense_budget,
                "spent": defense_spend,
                "pool_after": war_supply.pool_after_defense(
                    defense_pool, defense_spend
                ),
                "owned": sum(int(v or 0) for v in defenseunits.values()),
                "fielded": sum(fielded_units.values()),
                "floor": war_supply.DEFENDER_SUPPLY_FLOOR,
            }

            # FIXED 2026-09-23: found live while auditing wars/ during the
            # account cross-contamination investigation -- unrelated bug,
            # real replay/double-resolution race. attack_units/enemy_id/
            # war_domain live in the client-side signed session cookie
            # (this app has no server-side session store -- confirmed no
            # SESSION_TYPE/Flask-Session config), so session.pop()'ing them
            # at the end of this GET route does NOT stop a second,
            # concurrent request carrying the SAME still-valid stale cookie
            # (double-click, browser back+resubmit, two tabs) from also
            # reading the identical attack_units and re-entering this
            # branch. Military.fight() -> persist_fight_results() applies
            # casualties AND, if morale drops to 0, a full war-ending
            # resource transfer from loser to winner -- via its OWN
            # independent connection that commits immediately, with no
            # lock and no per-attack idempotency token. A replayed request
            # could apply a second, spurious round of casualties/looting
            # for a single attack the player only meant to submit once.
            #
            # There's no existing per-attack nonce to key an idempotency
            # check on. wars.last_visited looked like a reusable timestamp
            # for a one-shot debounce gate, but it's a `real` (single-
            # precision float) column -- accurate to ~7 significant digits,
            # too coarse to represent a current Unix timestamp (~10 digits)
            # precisely enough for a sub-second comparison, confirmed
            # empirically (an intended 1-second-window check behaved
            # unpredictably due to rounding, not an actual locking
            # problem). Added migrations/0081 for a dedicated
            # last_attack_resolved_at DOUBLE PRECISION column instead of
            # reusing/altering last_visited's existing informational use.
            # A WHERE-guarded UPDATE against that column only succeeds once
            # inside a 1-second window for this war; Postgres serializes
            # concurrent UPDATEs to the same row (the second blocks, then
            # re-evaluates its WHERE against the just-committed fresh
            # value), so a genuine race is rejected here, before any
            # combat resolution or casualties are ever applied. Legitimate
            # sequential attacks (which need multiple full page
            # round-trips through warChoose/warAmount first) are far
            # enough apart not to collide with this window.
            now_ts = time.time()
            db.execute(
                """
                UPDATE wars SET last_attack_resolved_at = %s
                WHERE id = %s
                  AND (last_attack_resolved_at IS NULL OR %s - last_attack_resolved_at >= 1)
                RETURNING id
                """,
                (now_ts, war_id_for_guard, now_ts),
            )
            if not db.fetchone():
                session.pop("attack_units", None)
                session.pop("enemy_id", None)
                session.pop("war_domain", None)
                return error(
                    400,
                    "This attack was already resolved. Please start a new attack.",
                )
            # FIXED 2026-09-26: commit the guard before fighting. Military.fight()
            # -> persist_fight_results() updates this same wars row (morale) on
            # its own connection; leaving the guard's row lock uncommitted here
            # made that UPDATE wait on this request until the 30s statement
            # timeout, so every battle 500'd ("An error occurred during the
            # battle"). Committing still rejects replays: a concurrent request's
            # guard UPDATE re-reads the committed timestamp and matches nothing.
            db.connection.commit()
            try:
                if citizen_pct is not None:
                    winner, win_condition, attack_effects = Military.fight(
                        attacker, defender, citizen_army_pct=citizen_pct
                    )
                else:
                    winner, win_condition, attack_effects = Military.fight(
                        attacker, defender
                    )
            except Exception:
                rollback_db_cursor(db)
                logger.exception(
                    "Military.fight() crashed for attacker=%s defender=%s",
                    attacker.user_id,
                    eId,
                )
                session.pop("attack_units", None)
                session.pop("enemy_id", None)
                session.pop("war_domain", None)
                return error(
                    500, "An error occurred during the battle. Please try again."
                )
            _remember_last_attack(
                war_id_for_guard, {"domain": war_domain, "units": prev_attacker}
            )
            # Charge the defense AFTER the fight: persist_fight_results()
            # updates this same wars row on its own connection, so locking it
            # here first would stall that update (see the 2026-09-26 note).
            try:
                new_pool = war_supply.spend_defense_supplies(
                    db, war_id_for_guard, eId, defense_spend
                )
                if new_pool is not None:
                    defender_result["supply"]["pool_after"] = new_pool
            except Exception:
                logger.exception(
                    "defense supply spend failed war=%s defender=%s",
                    war_id_for_guard,
                    eId,
                )
            citizen_losses = getattr(attacker, "_citizen_army_losses", None)
            if citizen_pct is not None:
                defender_result["citizen_army"] = {
                    "pct": round(citizen_pct * 100, 1),
                    "losses": {
                        u: q for u, q in (citizen_losses or {}).items() if q > 0
                    },
                }
            if war_type:
                attack_effects = list(attack_effects)
                if war_type == "Raze":
                    attack_effects[0] = attack_effects[0] * 10
                elif war_type == "Loot":
                    attack_effects[0] = attack_effects[0] * 0.2
                    if winner == attacker.user_id:
                        # Independent connection so loot survives request rollback
                        # if a later step (infra damage, template render) raises.
                        from database import get_db_connection as _loot_gdc
                        loot = 0
                        with _loot_gdc() as _loot_conn:
                            _loot_cur = _loot_conn.cursor()
                            _loot_cur.execute(
                                "SELECT gold FROM stats WHERE id=(%s)",
                                (defender.user_id,),
                            )
                            fetched = _loot_cur.fetchone()
                            available_resource = 0
                            if fetched and fetched[0] is not None:
                                try:
                                    available_resource = float(fetched[0])
                                except Exception:
                                    available_resource = 0
                            max_loot = int(math.floor(max(0, available_resource * 0.1)))
                            if max_loot < 0:
                                max_loot = 0
                            loot = random.randint(0, max_loot)
                            if loot > 0:
                                _loot_cur.execute(
                                    "UPDATE stats SET gold = gold + %s WHERE id = %s",
                                    (loot, attacker.user_id),
                                )
                                _loot_cur.execute(
                                    "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                                    (loot, defender.user_id),
                                )
                        attacker_result["loot"] = {"money": loot}
                elif war_type == "Sustained":
                    pass
                else:
                    return error(400, "Something went wrong")
            else:
                return error(500, "Something went wrong")

            # Best-effort infra damage — failures here must NOT undo the fight
            # results (morale/loot/casualties) which now commit independently.
            infra_damage_effects = {}
            try:
                db.execute(
                    "SELECT id FROM provinces WHERE userId=(%s) ORDER BY id ASC",
                    (defender.user_id,),
                )
                province_id_fetch = db.fetchall()
                if len(province_id_fetch) > 0:
                    random_province = province_id_fetch[
                        random.randint(0, len(province_id_fetch) - 1)
                    ][0]
                    public_works = Nation.get_public_works(random_province)
                    infra_damage_effects = Military.infrastructure_damage(
                        attack_effects[0], public_works, random_province
                    )
            except Exception:
                rollback_db_cursor(db)
                logger.exception(
                    "infra_damage step failed for defender=%s (fight result already committed)",
                    defender.user_id,
                )
            defender_result["infra_damage"] = infra_damage_effects
            if winner == defender.user_id:
                winner = defender_name
            else:
                winner = attacker_name
            defender_loss = {}
            attacker_loss = {}
            defender_initial = {}
            defender_remaining = {}
            attacker_initial = {}
            attacker_remaining = {}
            # Real losses come from the casualty pairs Military.fight()
            # applied (selected_units is never mutated by the fight, so the
            # old "initial - remaining" diff always showed 0 losses).
            d_losses = getattr(defender, "_fight_losses", None) or {}
            a_losses = getattr(attacker, "_fight_losses", None) or {}
            for unit in defender.selected_units_list:
                d_init = prev_defender.get(unit, 0)
                d_lost = min(d_init, int(d_losses.get(unit, 0)))
                defender_initial[unit] = d_init
                defender_remaining[unit] = d_init - d_lost
                defender_loss[unit] = d_lost
            for unit in attacker.selected_units_list:
                a_init = prev_attacker.get(unit, 0)
                a_lost = min(a_init, int(a_losses.get(unit, 0)))
                attacker_initial[unit] = a_init
                attacker_remaining[unit] = a_init - a_lost
                attacker_loss[unit] = a_lost
            defender_result["unit_loss"] = defender_loss
            defender_result["initial_units"] = defender_initial
            defender_result["remaining_units"] = defender_remaining
            attacker_result["unit_loss"] = attacker_loss
            attacker_result["initial_units"] = attacker_initial
            attacker_result["remaining_units"] = attacker_remaining
        else:
            defender_result["unit_loss"] = result[0]
            defender_result["infra_damage"] = result[1]
            attacker_result["unit_loss"] = dict(attacker.selected_units)
            session.pop("from_wartarget", None)
        
        if result is None:
            attacker.save(db_cursor=db)
            defender.save(db_cursor=db)
        else:
            attacker.save(db_cursor=db)

        # In-game notification via news table for both defender and attacker so defenders
        # can see battle history and know what happened when attacked (joshmd suggestion).
        try:
            domain_name = (session.get("war_domain") or "ground").title()
            d_loss_summary = ", ".join(
                f"{q} {u.replace('_', ' ')}"
                for u, q in (defender_result.get("unit_loss") or {}).items()
                if q and q > 0
            ) or "none"
            a_loss_summary = ", ".join(
                f"{q} {u.replace('_', ' ')}"
                for u, q in (attacker_result.get("unit_loss") or {}).items()
                if q and q > 0
            ) or "none"

            if winner == defender_name:
                outcome_def = f"Victory! You successfully repelled the attack ({win_condition})."
                outcome_att = f"Defeat. The defender repelled your assault ({win_condition})."
            else:
                outcome_def = f"Defeat! The attacker broke your lines ({win_condition})."
                outcome_att = f"Victory! You won the battle ({win_condition})."

            def_news = (
                f"⚔️ BATTLE REPORT: {attacker_name} launched a {domain_name} assault on your nation! "
                f"{outcome_def} Your casualties: {d_loss_summary}. Enemy casualties: {a_loss_summary}."
            )
            att_news = (
                f"⚔️ BATTLE REPORT: Your {domain_name} assault on {defender_name} resolved. "
                f"{outcome_att} Your casualties: {a_loss_summary}. Enemy casualties: {d_loss_summary}."
            )
            looted = int((attacker_result.get("loot") or {}).get("money") or 0)
            if looted > 0:
                att_news += f" You looted {looted:,} gold."
                def_news += f" They looted {looted:,} gold."
            db.execute("INSERT INTO news (destination_id, message) VALUES (%s, %s)", (eId, def_news))
            db.execute("INSERT INTO news (destination_id, message) VALUES (%s, %s)", (attacker.user_id, att_news))
        except Exception as e:
            logger.warning("Failed to record battle news: %s", e)

    session.pop("attack_units", None)
    session.pop("enemy_id", None)
    session.pop("war_domain", None)
    try:
        from app_core.discord_notify import notify_war_result

        notify_war_result(
            attacker_name=attacker_name,
            defender_name=defender_name,
            winner=str(winner),
            win_condition=win_condition,
        )
    except Exception:
        pass
    return render_template(
        "warResult.html",
        winner=winner,
        win_condition=win_condition,
        defender_result=defender_result,
        attacker_result=attacker_result,
        repeat_attack=_repeat_attack_ctx(attacker.war_id),
    )


@wars_bp.route("/declare_war", methods=["POST"])
@login_required
def declare_war():
    WAR_TYPES = ["Raze", "Sustained", "Loot"]
    defender_raw = request.form.get("defender")
    war_message = request.form.get("description")
    war_type = request.form.get("warType")
    if not defender_raw:
        return error(400, "Missing defender")
    try:
        defender_id = int(defender_raw)
    except (TypeError, ValueError):
        return error(400, "Invalid defender id")
    if war_type not in WAR_TYPES:
        return error(400, "Invalid war type")
    try:
        with get_request_cursor() as db:
            import logging

            logger = logging.getLogger(__name__)
            attacker = Economy(int(session.get("user_id")))
            defender = Economy(defender_id)
            logger.debug(
                "declare_war: attacker=%s defender=%s", attacker.id, defender.id
            )
            if attacker.id == defender.id:
                return error(400, "Can't declare war on yourself")

            # FIXED 2026-09-23: found live while auditing wars/ during the
            # account cross-contamination investigation -- unrelated bug,
            # real duplicate-war race. Unlike establish_coalition's similar
            # SELECT-then-INSERT check (protected by a real DB UNIQUE
            # constraint), `wars` has no constraint on (attacker, defender)
            # at all -- two concurrent declare_war calls for the same pair
            # (in either attacker/defender order) could both pass the
            # "not already at war" check below before either commits,
            # creating two simultaneous active war rows between the same
            # two nations. That doubles the attacker's total
            # attacker_supplies/attacker_morale pool for the ground-war
            # flow (warChoose/warAmount), and a peace offer accepted on one
            # war row would leave the other one silently still active.
            # Locked on both nation ids (LEAST/GREATEST so it serializes
            # regardless of which side calls first) to close the race.
            lo_id, hi_id = min(attacker.id, defender.id), max(attacker.id, defender.id)
            db.execute("SELECT pg_advisory_xact_lock(%s, %s)", (lo_id, hi_id))

            # Treaties check: Prevent war if an active Non-Aggression pact exists
            db.execute(
                """
                SELECT id FROM nation_treaties 
                WHERE status = 'active' AND treaty_type = 'non_aggression' 
                AND ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
                """, 
                (attacker.id, defender.id, defender.id, attacker.id)
            )
            if db.fetchone():
                return error(403, "You cannot declare war on a nation you have an active Non-Aggression Pact with!")
            logger.debug("declare_war: checking existing wars")
            db.execute(
                (
                    "SELECT id FROM wars "
                    "WHERE ((attacker=%s AND defender=%s) "
                    "OR (attacker=%s AND defender=%s)) "
                    "AND peace_date IS NULL"
                ),
                (attacker.id, defender.id, defender.id, attacker.id),
            )
            logger.debug(
                "declare_war: after select, db.closed=%s",
                getattr(db, "closed", "unknown"),
            )
            if db.fetchone():
                return error(400, "You're already in a war with this country!")
            # Query provinces count directly using the current cursor to avoid
            # nested DB contexts which have previously caused cursor closure errors.
            db.execute(
                "SELECT COUNT(id) FROM provinces WHERE userId=%s", (attacker.id,)
            )
            attacker_row = db.fetchone()
            attacker_provinces = (attacker_row[0] or 0) if attacker_row else 0
            db.execute(
                "SELECT COUNT(id) FROM provinces WHERE userId=%s", (defender.id,)
            )
            defender_row = db.fetchone()
            defender_provinces = (defender_row[0] or 0) if defender_row else 0
            logger.debug(
                "declare_war: attacker_provinces=%s defender_provinces=%s",
                attacker_provinces,
                defender_provinces,
            )
            if attacker_provinces - defender_provinces > 1:
                return error(
                    400,
                    (
                        "That country has too few provinces for you! You can only "
                        "declare war on countries within 3 provinces more or 1 "
                        "less province than you."
                    ),
                )
            if defender_provinces - attacker_provinces > 3:
                return error(
                    400,
                    (
                        "That country has too many provinces for you! You can only "
                        "declare war on countries within 3 provinces more or 1 "
                        "less province than you."
                    ),
                )
            # Check most recent peace date between the two nations
            db.execute(
                (
                    "SELECT MAX(peace_date) FROM wars WHERE ((attacker=%s "
                    "AND defender=%s) OR (attacker=%s AND defender=%s))"
                ),
                (attacker.id, defender.id, defender.id, attacker.id),
            )
            current_peace = db.fetchone()
            if current_peace and current_peace[0]:
                if (current_peace[0] + 259200) > time.time():
                    return error(
                        403, "You can't declare war because truce has not expired!"
                    )
            start_dates = time.time()
            db.execute(
                (
                    "INSERT INTO wars (attacker, defender, "
                    "war_type, agressor_message, start_date, "
                    "last_visited) VALUES (%s, %s, %s, %s, %s, %s) "
                    "RETURNING id"
                ),
                (
                    attacker.id,
                    defender.id,
                    war_type,
                    war_message,
                    start_dates,
                    start_dates,
                ),
            )
            new_war_row = db.fetchone()
            new_war_id = new_war_row[0] if new_war_row else None
            db.execute("SELECT username FROM users WHERE id=(%s)", (attacker.id,))
            attacker_row = db.fetchone()
            attacker_name = (
                attacker_row[0] if attacker_row else f"Nation {attacker.id}"
            )
            db.execute("SELECT username FROM users WHERE id=(%s)", (defender.id,))
            defender_row = db.fetchone()
            defender_name = (
                defender_row[0] if defender_row else f"Nation {defender.id}"
            )
            # Insert news directly using current cursor (avoid nested DB contexts)
            attacker_news = f"{attacker_name} declared war!"
            db.execute(
                "INSERT INTO news(destination_id, message) VALUES (%s, %s)",
                (defender.id, attacker_news),
            )
            log_event(
                db, "war",
                f"Conflict erupts! {attacker_name} has declared war on {defender_name}.",
                actor_id=attacker.id, target_id=defender.id,
            )

            # Notify active Mutual Defense partners of the defender - they can
            # join this war as a second, independent attacker against the
            # aggressor via /wars/<war_id>/join_ally (see join_war_as_ally()).
            if new_war_id is not None:
                db.execute(
                    """
                    SELECT CASE WHEN sender_id = %s THEN recipient_id ELSE sender_id END
                    FROM nation_treaties
                    WHERE status = 'active' AND treaty_type = 'mutual_defense'
                    AND (sender_id = %s OR recipient_id = %s)
                    """,
                    (defender.id, defender.id, defender.id),
                )
                for (ally_id,) in db.fetchall():
                    db.execute(
                        "INSERT INTO news(destination_id, message) VALUES (%s, %s)",
                        (
                            ally_id,
                            f"Your Mutual Defense partner {defender_name} is under attack "
                            f"from {attacker_name}! Visit /wars to join the fight.",
                        ),
                    )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error("Error in declare_war: %s", e)
        tb = traceback.format_exc()
        logger.error(tb)
        # Return a safe error message (traceback logged only)
        return error(500, f"Could not declare war; exception: {str(e)}")
    return redirect("/wars")


@wars_bp.route("/wars/<int:war_id>/join_ally", methods=["POST"])
@login_required
def join_war_as_ally(war_id):
    """A Mutual Defense partner of a war's defender joins as a second,
    independent 1v1 war against the original attacker - not a true multi-
    nation war (the `wars` table is strictly attacker/defender), just a
    second war row reusing declare_war's guards minus the province-count
    gate (this is solidarity, not an unprovoked declaration)."""
    ally_id = int(session.get("user_id"))
    try:
        with get_request_cursor() as db:
            db.execute(
                "SELECT attacker, defender FROM wars WHERE id=%s AND peace_date IS NULL",
                (war_id,),
            )
            row = db.fetchone()
            if not row:
                return error(404, "That war doesn't exist or has already ended.")
            original_attacker_id, original_defender_id = row

            if ally_id in (original_attacker_id, original_defender_id):
                return error(400, "You're already a combatant in this war.")

            db.execute(
                """
                SELECT id FROM nation_treaties
                WHERE status = 'active' AND treaty_type = 'mutual_defense'
                AND ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
                """,
                (ally_id, original_defender_id, original_defender_id, ally_id),
            )
            if not db.fetchone():
                return error(403, "You don't have an active Mutual Defense pact with that nation.")

            # Same guards as declare_war, minus the province-count gate.
            db.execute(
                """
                SELECT id FROM nation_treaties
                WHERE status = 'active' AND treaty_type = 'non_aggression'
                AND ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
                """,
                (ally_id, original_attacker_id, original_attacker_id, ally_id),
            )
            if db.fetchone():
                return error(403, "You cannot join this war - you have an active Non-Aggression Pact with the aggressor!")

            db.execute(
                "SELECT id FROM wars WHERE ((attacker=%s AND defender=%s) "
                "OR (attacker=%s AND defender=%s)) AND peace_date IS NULL",
                (ally_id, original_attacker_id, original_attacker_id, ally_id),
            )
            if db.fetchone():
                return error(400, "You're already at war with this nation!")

            db.execute(
                "SELECT MAX(peace_date) FROM wars WHERE ((attacker=%s AND defender=%s) "
                "OR (attacker=%s AND defender=%s))",
                (ally_id, original_attacker_id, original_attacker_id, ally_id),
            )
            current_peace = db.fetchone()
            if current_peace and current_peace[0]:
                if (current_peace[0] + 259200) > time.time():
                    return error(403, "You can't join this war because a truce with the aggressor has not expired!")

            db.execute("SELECT username FROM users WHERE id=(%s)", (ally_id,))
            ally_row = db.fetchone()
            ally_name = ally_row[0] if ally_row else f"Nation {ally_id}"
            db.execute("SELECT username FROM users WHERE id=(%s)", (original_attacker_id,))
            aggressor_row = db.fetchone()
            aggressor_name = aggressor_row[0] if aggressor_row else f"Nation {original_attacker_id}"

            start_dates = time.time()
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, "
                "start_date, last_visited) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    ally_id, original_attacker_id, "Sustained",
                    f"{ally_name} joins the fight in defense of their ally!",
                    start_dates, start_dates,
                ),
            )
            db.execute(
                "INSERT INTO news(destination_id, message) VALUES (%s, %s)",
                (original_attacker_id, f"{ally_name} has joined the war against you in defense of their ally!"),
            )
            log_event(
                db, "ally_join",
                f"{ally_name} joined the war against {aggressor_name} in defense of their Mutual Defense partner.",
                actor_id=ally_id, target_id=original_attacker_id,
            )
    except Exception as e:
        import logging

        logging.getLogger(__name__).error("Error in join_war_as_ally: %s\n%s", e, traceback.format_exc())
        return error(500, f"Could not join this war; exception: {str(e)}")
    return redirect("/wars")


@wars_bp.route("/defense", methods=["GET", "POST"])
@login_required
def defense():
    cId = session["user_id"]
    units = Military.get_military(cId)
    current_defense = Military.get_defense(cId)

    if request.method == "POST":
        # Save the user's defense selection
        selected_units = request.form.getlist("defense_units")
        if len(selected_units) == 3:
            defense_string = ",".join(selected_units)
            nation = Military(cId)
            result = nation.set_defense(defense_string)
            if result:
                return error(500, result)
            # Update current defense after saving
            current_defense = selected_units
        else:
            return error(400, "You must select exactly 3 unit types for defense.")

    return render_template(
        "defense.html",
        units=units,
        current_defense=current_defense,
    )


@wars_bp.route("/wars", methods=["GET", "POST"])
@login_required
def wars():
    cId = session["user_id"]
    if request.method == "GET":
        normal_units = Military.get_military(cId)
        special_units = Military.get_special(cId)
        units = normal_units.copy()
        units.update(special_units)
        current_defense = Military.get_defense(cId)
        with get_request_cursor() as db:
            db.execute("SELECT username FROM users WHERE id=(%s)", (cId,))
            country_row = db.fetchone()
            yourCountry = country_row[0] if country_row else "Unknown"
            try:
                db.execute(
                    (
                        "SELECT id, defender, attacker "
                        "FROM wars WHERE (attacker=%s "
                        "OR defender=%s) "
                        "AND peace_date IS NULL"
                    ),
                    (cId, cId),
                )
                war_attacker_defender_ids = db.fetchall()
                war_info = {}

                if war_attacker_defender_ids:
                    # OPTIMIZATION: batch fetch war and user data to reduce queries
                    war_ids = [w[0] for w in war_attacker_defender_ids]
                    all_user_ids = set()
                    for _, defender, attacker in war_attacker_defender_ids:
                        all_user_ids.add(defender)
                        all_user_ids.add(attacker)

                    # Fetch all war details at once
                    war_placeholders = ",".join(["%s"] * len(war_ids))
                    db.execute(
                        (
                            "SELECT id, attacker_morale, attacker_supplies, "
                            "defender_morale, defender_supplies "
                            "FROM wars WHERE id IN (" + war_placeholders + ")"
                        ),
                        tuple(war_ids),
                    )
                    war_details = {row[0]: row[1:] for row in db.fetchall()}

                    # Fetch all usernames AND flags at once
                    user_placeholders = ",".join(["%s"] * len(all_user_ids))
                    db.execute(
                        (
                            "SELECT id, username, flag FROM users "
                            "WHERE id IN (" + user_placeholders + ")"
                        ),
                        tuple(all_user_ids),
                    )
                    user_data = {
                        row[0]: {"name": row[1], "flag": row[2] or "default_flag.jpg"}
                        for row in db.fetchall()
                    }

                    for war_id, defender, attacker in war_attacker_defender_ids:
                        # NOTE: supply regen now happens in global_tick's war_supply_regen
                        # phase (app_core/game_ticks/maintenance.py); skip here
                        attacker_info = {}
                        defender_info = {}

                        att_data = user_data.get(
                            attacker, {"name": "Unknown", "flag": "default_flag.jpg"}
                        )
                        def_data = user_data.get(
                            defender, {"name": "Unknown", "flag": "default_flag.jpg"}
                        )

                        attacker_info["name"] = att_data["name"]
                        attacker_info["id"] = attacker
                        attacker_info["flag"] = att_data["flag"]

                        details = war_details.get(war_id, (100, 0, 100, 0))
                        attacker_info["morale"] = details[0]
                        attacker_info["supplies"] = details[1]

                        defender_info["name"] = def_data["name"]
                        defender_info["id"] = defender
                        defender_info["flag"] = def_data["flag"]
                        defender_info["morale"] = details[2]
                        defender_info["supplies"] = details[3]

                        war_info[war_id] = {"att": attacker_info, "def": defender_info}
            except Exception:
                rollback_db_cursor(db)
                war_attacker_defender_ids = []
                war_info = {}
            try:
                db.execute(
                    (
                        "SELECT COUNT(attacker) FROM wars WHERE (defender=%s "
                        "OR attacker=%s) AND peace_date IS NULL"
                    ),
                    (cId, cId),
                )
                wars_row = db.fetchone()
                warsCount = wars_row[0] if wars_row else 0
            except Exception:
                rollback_db_cursor(db)
                warsCount = 0

            joinable_wars = []
            try:
                db.execute(
                    """
                    SELECT w.id, ua.username, ud.username
                    FROM wars w
                    JOIN nation_treaties nt ON nt.status='active' AND nt.treaty_type='mutual_defense'
                        AND ((nt.sender_id = w.defender AND nt.recipient_id = %s)
                          OR (nt.recipient_id = w.defender AND nt.sender_id = %s))
                    JOIN users ua ON ua.id = w.attacker
                    JOIN users ud ON ud.id = w.defender
                    WHERE w.peace_date IS NULL
                      AND w.attacker != %s AND w.defender != %s
                      AND NOT EXISTS (
                          SELECT 1 FROM wars w2 WHERE w2.peace_date IS NULL
                          AND ((w2.attacker=%s AND w2.defender=w.attacker) OR (w2.attacker=w.attacker AND w2.defender=%s))
                      )
                    """,
                    (cId, cId, cId, cId, cId, cId),
                )
                joinable_wars = db.fetchall()
            except Exception:
                rollback_db_cursor(db)
                joinable_wars = []

            # Every other ongoing war, so players can spectate (Silent, 2026-10-04).
            world_wars = []
            try:
                db.execute(
                    """
                    SELECT w.id, w.attacker, ua.username, w.attacker_morale,
                           w.defender, ud.username, w.defender_morale
                    FROM wars w
                    JOIN users ua ON ua.id = w.attacker
                    JOIN users ud ON ud.id = w.defender
                    WHERE w.peace_date IS NULL
                      AND w.attacker != %s AND w.defender != %s
                    ORDER BY w.id DESC
                    LIMIT 100
                    """,
                    (cId, cId),
                )
                world_wars = [
                    {
                        "id": r[0],
                        "att": {"id": r[1], "name": r[2], "morale": r[3]},
                        "def": {"id": r[4], "name": r[5], "morale": r[6]},
                    }
                    for r in db.fetchall()
                ]
            except Exception:
                rollback_db_cursor(db)
                world_wars = []
        template = "wars_v2.html" if is_theme_v2_enabled("wars") else "wars.html"
        return render_template(
            template,
            units=units,
            warsCount=warsCount,
            war_info=war_info,
            yourCountry=yourCountry,
            current_defense=current_defense,
            joinable_wars=joinable_wars,
            world_wars=world_wars,
        )


@wars_bp.route("/find_targets", methods=["GET", "POST"])
@login_required
def find_targets():
    cId = session["user_id"]
    if request.method == "GET":
        with get_request_cursor() as db:
            db.execute("SELECT COUNT(id) FROM provinces WHERE userid=%s", (cId,))
            provinces_row = db.fetchone()
            user_provinces = provinces_row[0] if provinces_row else 0
            min_provinces = max(0, user_provinces - 3)
            max_provinces = user_provinces + 1
            user_influence = get_influence(cId)
            # Choose a sensible search range around the player's influence.
            # For very new/low-influence players, expand the max_influence so
            # they still see potential targets (otherwise max would be 0 and
            # filter out viable targets).
            min_influence = max(0.0, user_influence * 0.9)
            max_influence = max(user_influence * 2.0, 100.0)
            # Influence comes from the shared formula (influence_formula);
            # this used to be a separate military-only copy that drifted.
            query = (
                "SELECT users.id, users.username, users.flag, "
                "COUNT(provinces.id) AS provinces_count, "
                "COALESCE(MAX(inf.influence), 0) AS influence "
                "FROM users "
                "LEFT JOIN provinces ON users.id = provinces.userId "
                "LEFT JOIN "
                + influence_subquery_sql("SELECT id FROM users WHERE id != %s")
                + " inf ON inf.user_id = users.id "
                "WHERE users.id != %s "
                "GROUP BY users.id, users.username, users.flag "
                "HAVING COUNT(provinces.id) BETWEEN %s AND %s "
                "ORDER BY users.username "
                "LIMIT 50"
            )
            db.execute(query, (cId, cId, min_provinces, max_provinces))
            targets = db.fetchall()
        targets_list = []
        for target in targets:
            tid, tname, tflag, tprovinces, tinfluence = target
            tflag = tflag or "default_flag.jpg"
            if min_influence <= tinfluence <= max_influence:
                targets_list.append(
                    {
                        "id": tid,
                        "username": tname,
                        "flag": tflag,
                        "provinces": tprovinces,
                        "influence": tinfluence,
                    }
                )

        # Handle filtering
        search = request.args.get("search", "").strip()
        sort = request.args.get("sort", "influence")
        sortway = request.args.get("sortway", "desc")

        # Limit to 20 results after filtering and sorting
        # (apply the slice after sort and search are applied so we don't drop
        # candidates prematurely)
        # the slice will be performed after sorting below

        if search:
            targets_list = [
                t for t in targets_list if search.lower() in (t["username"] or "").lower()
            ]

        if sort == "influence":
            rev = sortway == "desc"
            targets_list.sort(key=lambda x: x["influence"], reverse=rev)
        elif sort == "provinces":
            rev = sortway == "desc"
            targets_list.sort(key=lambda x: x["provinces"], reverse=rev)
        elif sort == "username":
            rev = sortway == "desc"
            targets_list.sort(key=lambda x: x["username"].lower(), reverse=rev)

        # take the top 20 after filtering/sorting
        targets_list = targets_list[:20]

        template = "find_targets_v2.html" if is_theme_v2_enabled("find_targets") else "find_targets.html"
        return render_template(template, targets=targets_list)
    # POST - find a target by id or username and redirect
    defender_raw = request.form.get("defender")
    if not defender_raw:
        return error(400, "Missing defender")
    defender_id = None
    try:
        defender_id = int(defender_raw)
    except (TypeError, ValueError):
        with get_request_cursor() as db:
            db.execute("SELECT id FROM users WHERE username=%s", (defender_raw,))
            row = db.fetchone()
            if row:
                defender_id = row[0]
    if not defender_id:
        return error(404, "Country not found")
    return redirect(f"/country/id={defender_id}")


@wars_bp.route("/nuclear_strike", methods=["POST"])
@login_required
def nuclear_strike():
    """Entry point from a country page: find the active war with that nation
    and open the nuclear strike planner (the strike itself is a two-step
    confirm there; see wars/nuclear.py for the rules)."""
    attacker_id = session["user_id"]
    try:
        target_id = int(request.form.get("target_id"))
    except (TypeError, ValueError):
        return error(400, "Invalid payload")
    if attacker_id == target_id:
        return error(400, "You cannot nuke yourself!")
    if request.form.get("weapon_type", "nuke") != "nuke":
        return error(
            400,
            "ICBMs are launched from a war's Attack page (Special Attack). "
            "Only nukes use the nuclear strike planner.",
        )
    with get_request_cursor() as db:
        db.execute(
            "SELECT id FROM wars WHERE peace_date IS NULL AND "
            "((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s)) "
            "ORDER BY id DESC LIMIT 1",
            (attacker_id, target_id, target_id, attacker_id),
        )
        row = db.fetchone()
    if not row:
        return error(403, "You are not at war with this nation.")
    return redirect(f"/nuclear_strike/{row[0]}")


def _nuke_template():
    return "nuclear_strike.html"


@wars_bp.route("/nuclear_strike/<int:war_id>", methods=["GET"])
@login_required
def nuclear_strike_plan(war_id):
    """Step 0: pick a province (shows the blast preview for each)."""
    from wars.nuclear import plan_strike, StrikeError

    attacker_id = session["user_id"]
    with get_request_cursor() as db:
        try:
            plan = plan_strike(db, attacker_id, war_id)
        except StrikeError as exc:
            return error(exc.status, str(exc))
    return render_template(_nuke_template(), step="plan", plan=plan)


@wars_bp.route("/nuclear_strike/<int:war_id>/review", methods=["POST"])
@login_required
def nuclear_strike_review(war_id):
    """Step 1: show exactly what this launch will do and what it costs."""
    import secrets
    from wars.nuclear import plan_strike, StrikeError

    attacker_id = session["user_id"]
    try:
        province_id = int(request.form.get("province_id"))
    except (TypeError, ValueError):
        return error(400, "Pick a province to target.")
    with get_request_cursor() as db:
        try:
            plan = plan_strike(db, attacker_id, war_id, province_id)
        except StrikeError as exc:
            return error(exc.status, str(exc))
    if plan["blocked"]:
        return error(400, plan["blocked"])
    token = secrets.token_urlsafe(16)
    session["nuke_confirm"] = {
        "token": token,
        "war_id": war_id,
        "province_id": province_id,
        "ts": time.time(),
    }
    return render_template(_nuke_template(), step="confirm", plan=plan, token=token)


@wars_bp.route("/nuclear_strike/<int:war_id>/launch", methods=["POST"])
@login_required
def nuclear_strike_launch(war_id):
    """Step 2: the actual launch. Needs the one-time token from the review
    page (so a stray POST or a replayed form can't fire a nuke)."""
    from wars.nuclear import execute_strike, StrikeError

    attacker_id = session["user_id"]
    pending = session.pop("nuke_confirm", None)
    try:
        province_id = int(request.form.get("province_id"))
    except (TypeError, ValueError):
        return error(400, "Invalid payload")
    if (
        not pending
        or request.form.get("token") != pending.get("token")
        or pending.get("war_id") != war_id
        or pending.get("province_id") != province_id
        or time.time() - float(pending.get("ts") or 0) > 600
    ):
        return error(
            400,
            "This launch confirmation expired or was already used. "
            "Please review the strike again.",
        )
    if request.form.get("confirm_launch") != "yes":
        return error(400, "Tick the confirmation box to launch.")
    with get_request_cursor() as db:
        try:
            result = execute_strike(db, attacker_id, war_id, province_id)
        except StrikeError as exc:
            rollback_db_cursor(db)
            return error(exc.status, str(exc))
        # Commit before dropping caches so no request re-caches the
        # pre-strike influence in between.
        db.connection.commit()
    try:
        from database import invalidate_user_cache

        invalidate_user_cache(attacker_id)
        invalidate_user_cache(result["enemy_id"])
    except Exception:
        pass
    return render_template(_nuke_template(), step="result", result=result)

@wars_bp.route("/strategic_airstrike", methods=["POST"])
@login_required
def strategic_airstrike():
    attacker_id = session["user_id"]
    try:
        target_id = int(request.form.get("target_id"))
        strike_target = request.form.get("strike_target")
        bombers_count = int(request.form.get("bombers_count"))
    except (TypeError, ValueError):
        return error(400, "Invalid payload")

    if attacker_id == target_id:
        return error(400, "You cannot bomb yourself!")

    if strike_target not in ["silo", "nuclear_testing_facility"]:
        return error(400, "Invalid target")

    if bombers_count <= 0:
        return error(400, "Must send at least 1 bomber.")

    with get_request_cursor() as db:
        # FIXED 2026-09-23: same race class already fixed in drone_strike/
        # cruise_missile_strike on 2026-09-13, and the same underlying bug
        # as nuclear_strike above -- the bombers-quantity read below and
        # the UPDATE decrementing lost_bombers have no lock between them.
        # Most of the time lost_bombers is well under the attacker's
        # stock, so this doesn't reach user_military's CHECK
        # (quantity >= 0) constraint at all -- but when the defender's
        # fighters shoot down the full batch sent (lost_bombers ==
        # quantity), two concurrent strikes hit exactly the same crash
        # confirmed for nuclear_strike: the second racer's UPDATE blocks,
        # re-evaluates against the now-lower committed value, goes
        # negative, and raises an unhandled CheckViolation instead of a
        # clean rejection. Locked per-attacker, matching the established
        # pattern for every other strike route in this file.
        db.execute("SELECT pg_advisory_xact_lock(%s)", (attacker_id,))

        # Require an active war with the target before allowing a strike
        db.execute(
            (
                "SELECT id FROM wars "
                "WHERE ((attacker=%s AND defender=%s) "
                "OR (attacker=%s AND defender=%s)) "
                "AND peace_date IS NULL"
            ),
            (attacker_id, target_id, target_id, attacker_id),
        )
        if not db.fetchone():
            return error(403, "You are not at war with this nation.")

        # Check attacker bombers
        db.execute(
            """
            SELECT um.quantity, ud.unit_id
            FROM user_military um
            JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
            WHERE um.user_id = %s AND ud.name = 'bombers'
            """,
            (attacker_id,)
        )
        row = db.fetchone()
        if not row or row[0] < bombers_count:
            return error(400, "You don't have enough bombers!")
        bombers_unit_id = row[1]

        # Get defender fighters
        db.execute(
            """
            SELECT um.quantity, ud.unit_id 
            FROM user_military um
            JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
            WHERE um.user_id = %s AND ud.name = 'fighters'
            """,
            (target_id,)
        )
        def_row = db.fetchone()
        defender_fighters = def_row[0] if def_row else 0
        fighters_unit_id = def_row[1] if def_row else None

        import random
        # Interception Logic with RNG
        # Fighters have a random effectiveness multiplier (0.5x to 1.5x)
        fighter_effectiveness = random.uniform(0.5, 1.5)
        intercept_capacity = int(defender_fighters * fighter_effectiveness)
        
        lost_bombers = min(bombers_count, intercept_capacity)
        surviving_bombers = bombers_count - lost_bombers
        
        # Defenders lose some fighters in the dogfight (10% to 40% of engaged fighters)
        engaged_fighters = min(defender_fighters, bombers_count)
        casualty_rate = random.uniform(0.1, 0.4)
        lost_fighters = int(engaged_fighters * casualty_rate)

        # Update attacker bombers
        # The attacker sends `bombers_count`. The surviving ones return. We only deduct `lost_bombers`.
        db.execute(
            "UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s",
            (lost_bombers, attacker_id, bombers_unit_id)
        )

        # Update defender fighters
        if lost_fighters > 0 and fighters_unit_id:
            db.execute(
                "UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s",
                (lost_fighters, target_id, fighters_unit_id)
            )

        damage_report = ""

        if surviving_bombers > 0:
            # Bombing payload damage is randomized (0.7x to 1.3x)
            bombing_power = surviving_bombers * random.uniform(0.7, 1.3)
            
            if strike_target == "silo":
                # 15 damage points needed to destroy 1 silo
                db.execute(
                    "SELECT ub.quantity, ub.building_id FROM user_buildings ub JOIN building_dictionary bd ON ub.building_id = bd.building_id WHERE ub.user_id = %s AND bd.name = 'silos'",
                    (target_id,)
                )
                s_row = db.fetchone()
                if s_row and s_row[0] > 0:
                    silos_count = s_row[0]
                    silo_building_id = s_row[1]
                    destroyed_silos = min(silos_count, int(bombing_power // 15))
                    if destroyed_silos > 0:
                        db.execute(
                            "UPDATE user_buildings SET quantity = quantity - %s WHERE user_id = %s AND building_id = %s",
                            (destroyed_silos, target_id, silo_building_id)
                        )
                        damage_report = f"destroyed {destroyed_silos} Missile Silo(s)"
                    else:
                        damage_report = "dropped their payload but failed to penetrate the silo's reinforced armor due to poor accuracy or glancing hits"
                else:
                    damage_report = "found no silos to destroy"
            
            elif strike_target == "nuclear_testing_facility":
                # 50 damage points needed to destroy the tech
                db.execute(
                    "SELECT ut.tech_id FROM user_tech ut JOIN tech_dictionary td ON ut.tech_id = td.tech_id WHERE ut.user_id = %s AND td.name = 'nuclear_testing_facility' AND ut.is_unlocked = TRUE",
                    (target_id,)
                )
                t_row = db.fetchone()
                if t_row:
                    if bombing_power >= 50:
                        tech_id = t_row[0]
                        db.execute(
                            "UPDATE user_tech SET is_unlocked = FALSE WHERE user_id = %s AND tech_id = %s",
                            (target_id, tech_id)
                        )
                        damage_report = "landed direct hits and completely destroyed their Nuclear Testing Facility!"
                    else:
                        damage_report = "dropped their payloads but failed to deal enough concentrated damage to destroy the massive Nuclear Testing Facility"
                else:
                    damage_report = "found no operational facility"
        else:
            damage_report = "were completely wiped out by defending fighters before reaching the target"

        # News
        db.execute("SELECT username FROM users WHERE id=%s", (attacker_id,))
        attacker_row = db.fetchone()
        attacker_name = attacker_row[0] if attacker_row else "Unknown"
        
        db.execute("SELECT username FROM users WHERE id=%s", (target_id,))
        target_row = db.fetchone()
        target_name = target_row[0] if target_row else "Unknown"

        attacker_news = f"Your strategic airstrike on {target_name} ({strike_target.replace('_', ' ').title()}) had {surviving_bombers} bombers penetrate the airspace. You lost {lost_bombers} bombers. Result: {damage_report}."
        defender_news = f"{attacker_name} launched an airstrike against your {strike_target.replace('_', ' ').title()}! Your fighters shot down {lost_bombers} bombers (losing {lost_fighters} fighters). Result: The enemy {damage_report}."

        db.execute(
            "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
            (attacker_id, f"AIRSTRIKE RESULT: {attacker_news}")
        )
        db.execute(
            "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
            (target_id, f"🚨 UNDER ATTACK: {defender_news}")
        )

    return redirect(f"/country/id={target_id}")


# kamikaze_drones/cruise_missiles strike targets: military (silo) plus the
# economic buildings Kaiser's suggestion asked for ("damaging the enemy
# economy" with swarms), not just military infrastructure like
# strategic_airstrike above. "silo" maps to the building_dictionary row
# 'silos', same as strategic_airstrike's own convention; everything else
# maps 1:1.
STRIKE_TARGET_BUILDINGS = {
    "silo": "silos",
    "steel_mills": "steel_mills",
    "component_factories": "component_factories",
    "aluminium_refineries": "aluminium_refineries",
    "oil_refineries": "oil_refineries",
}
STRIKE_TARGET_LABELS = {
    "silo": "Missile Silos",
    "steel_mills": "Steel Mills",
    "component_factories": "Component Factories",
    "aluminium_refineries": "Aluminium Refineries",
    "oil_refineries": "Oil Refineries",
}


# "population" is the one strike target that isn't a building: it hits the
# enemy's most populous province instead (wars/service.apply_population_strike).
# Share of that province killed per drone hit / per cruise missile, capped
# per strike so one big launch can't empty a province.
POPULATION_TARGET = "population"
POPULATION_TARGET_LABEL = "Population Centres"
POP_KILL_PER_DRONE_HIT = 0.0002
POP_KILL_PER_MISSILE = 0.003
POP_KILL_CAP_PER_STRIKE = 0.02


def _valid_strike_target(strike_target):
    return strike_target == POPULATION_TARGET or strike_target in STRIKE_TARGET_BUILDINGS


def _population_report(result):
    if not result:
        return "found no population to hit"
    name, deaths, happiness_lost = result
    if deaths <= 0:
        return f"hit {name} but caused no casualties"
    return f"killed {deaths:,} people in {name} (-{happiness_lost} happiness)"


def _target_has_building(db, target_id, strike_target):
    if strike_target == POPULATION_TARGET:
        db.execute(
            "SELECT 1 FROM provinces WHERE userid = %s AND COALESCE(population, 0) > 0 LIMIT 1",
            (target_id,),
        )
        return db.fetchone() is not None
    db.execute(
        "SELECT COALESCE(SUM(ub.quantity), 0) FROM user_buildings ub "
        "JOIN building_dictionary bd ON bd.building_id = ub.building_id "
        "WHERE ub.user_id = %s AND bd.name = %s",
        (target_id, STRIKE_TARGET_BUILDINGS[strike_target]),
    )
    return int(db.fetchone()[0] or 0) > 0


# Damage points needed to destroy 1 of the target building. Silos are
# reinforced military infrastructure (matches strategic_airstrike's existing
# 15); ordinary economic buildings are softer.
STRIKE_TARGET_THRESHOLDS = {
    "silo": 15,
    "steel_mills": 10,
    "component_factories": 10,
    "aluminium_refineries": 10,
    "oil_refineries": 10,
}


def _require_active_war(db, attacker_id, target_id):
    db.execute(
        (
            "SELECT id FROM wars "
            "WHERE ((attacker=%s AND defender=%s) "
            "OR (attacker=%s AND defender=%s)) "
            "AND peace_date IS NULL"
        ),
        (attacker_id, target_id, target_id, attacker_id),
    )
    return db.fetchone() is not None


def _spend_gasoline(db, user_id, amount):
    """Returns True if the user had enough gasoline and it was deducted.

    Both current callers already hold a pg_advisory_xact_lock(attacker_id)
    for the whole request (see drone_strike/cruise_missile_strike), but the
    deduction below is also made atomic/self-guarding on its own -- defense
    in depth for any future caller that forgets the lock, matching the
    give_resource()-style `WHERE quantity >= amount` pattern used safely
    elsewhere in the app. Previously this UPDATE had no such guard at all
    (not even a GREATEST(0, ...) floor), so it could drive gasoline negative
    if ever called unlocked.
    """
    db.execute(
        """
        UPDATE user_economy SET quantity = quantity - %s
        WHERE user_id = %s
          AND resource_id = (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline')
          AND quantity >= %s
        RETURNING quantity
        """,
        (amount, user_id, amount),
    )
    return db.fetchone() is not None


def _strike_news(db, attacker_id, target_id, attacker_msg, defender_msg):
    db.execute("SELECT username FROM users WHERE id=%s", (attacker_id,))
    row = db.fetchone()
    attacker_name = row[0] if row else "Unknown"
    db.execute("SELECT username FROM users WHERE id=%s", (target_id,))
    row = db.fetchone()
    target_name = row[0] if row else "Unknown"
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
        (attacker_id, attacker_msg.format(target_name=target_name)),
    )
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
        (target_id, defender_msg.format(attacker_name=attacker_name)),
    )


@wars_bp.route("/drone_strike", methods=["POST"])
@login_required
def drone_strike():
    """Launch kamikaze_drones (stockpile-backed, see
    app_core/game_ticks/unit_production.py + app_core/military/services.py)
    at a target building. Weak alone -- meant to be launched in swarms;
    Kaiser's Discord suggestion (#suggestions "add kamikaze drones",
    2026-08-25)."""
    attacker_id = session["user_id"]
    try:
        target_id = int(request.form.get("target_id"))
        strike_target = request.form.get("strike_target")
        drones_count = int(request.form.get("drones_count"))
    except (TypeError, ValueError):
        return error(400, "Invalid payload")

    if attacker_id == target_id:
        return error(400, "You cannot strike yourself!")
    if not _valid_strike_target(strike_target):
        return error(400, "Invalid target")
    if drones_count <= 0:
        return error(400, "Must launch at least 1 drone.")

    with get_request_cursor() as db:
        # Serializes this attacker's strike launches (same pattern as
        # action_loop.py's build_structure / app_core/military/services.py).
        # Found 2026-09-13: neither the drone-count check below nor
        # _spend_gasoline's deduction has any WHERE-guarded/atomic floor --
        # _spend_gasoline's UPDATE has no `AND quantity >= amount` at all,
        # and the drone-quantity UPDATE right after it is the same shape.
        # Without this lock, two concurrent launches both pass their reads
        # before either commits and both proceed to the (unconditional)
        # combat resolution below -- doubling real, irreversible damage to
        # the target (building destruction, soldiers killed) from a single
        # drone/gasoline payment, not just an economy exploit against the
        # attacker's own account.
        db.execute("SELECT pg_advisory_xact_lock(%s)", (attacker_id,))

        if not _require_active_war(db, attacker_id, target_id):
            return error(403, "You are not at war with this nation.")
        if not _target_has_building(db, target_id, strike_target):
            return error(
                400,
                f"They have no {STRIKE_TARGET_LABELS.get(strike_target, POPULATION_TARGET_LABEL)} to hit. Pick another target.",
            )

        db.execute(
            """
            SELECT um.quantity, ud.unit_id
            FROM user_military um
            JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
            WHERE um.user_id = %s AND ud.name = 'kamikaze_drones'
            """,
            (attacker_id,),
        )
        row = db.fetchone()
        if not row or row[0] < drones_count:
            return error(400, "You don't have enough kamikaze drones!")
        unit_id = row[1]

        fuel_cost = variables.UNIT_LAUNCH_FUEL_COST["kamikaze_drones"] * drones_count
        if not _spend_gasoline(db, attacker_id, fuel_cost):
            return error(400, f"Not enough gasoline (need {fuel_cost})")

        # Kamikaze drones are one-way -- the full launched count is consumed
        # regardless of whether they're intercepted, unlike bombers which
        # return home if they survive.
        db.execute(
            "UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s",
            (drones_count, attacker_id, unit_id),
        )

        # Interception: SAM batteries + defending fighters + apaches
        db.execute(
            """
            SELECT COALESCE(SUM(um.quantity), 0)
            FROM user_military um
            JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
            WHERE um.user_id = %s AND ud.name IN ('fighters', 'apaches')
            """,
            (target_id,),
        )
        defender_interceptors = int(db.fetchone()[0] or 0)

        db.execute(
            """
            SELECT COALESCE(SUM(um.quantity), 0)
            FROM user_military um
            JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
            WHERE um.user_id = %s AND ud.name = 'sam_batteries'
            """,
            (target_id,),
        )
        sam_count = int(db.fetchone()[0] or 0)
        from wars.air_defense import calculate_sam_interception
        sam_intercept_pct = calculate_sam_interception(sam_count, 'kamikaze_drones')

        sam_intercepted = min(drones_count, int(drones_count * sam_intercept_pct))
        remaining_after_sam = drones_count - sam_intercepted
        # Iron Dome (migration 0104) engages whatever got past the SAMs.
        from app_core.military.iron_dome import roll_intercepts

        dome_intercepted = roll_intercepts(db, target_id, remaining_after_sam, "kamikaze_drones")
        sam_intercepted += dome_intercepted
        remaining_after_sam -= dome_intercepted

        intercept_effectiveness = random.uniform(0.5, 1.5)
        fighter_intercepted = min(remaining_after_sam, int(defender_interceptors * intercept_effectiveness))
        
        intercepted = sam_intercepted + fighter_intercepted
        surviving_drones = drones_count - intercepted

        hits = int(surviving_drones * random.uniform(0.5, 0.9))
        damage_points = hits * 2

        pop_result = None
        if strike_target == POPULATION_TARGET:
            destroyed, had_target = 0, True
            if hits > 0:
                pop_result = apply_population_strike(
                    db, target_id,
                    min(POP_KILL_CAP_PER_STRIKE, hits * POP_KILL_PER_DRONE_HIT),
                )
        else:
            destroyed, had_target = apply_building_damage(
                db, target_id, STRIKE_TARGET_BUILDINGS[strike_target],
                damage_points, STRIKE_TARGET_THRESHOLDS[strike_target],
            )

        soldiers_lost = 0
        if hits > 0 and random.random() < 0.10:
            db.execute(
                """
                SELECT um.quantity, ud.unit_id
                FROM user_military um
                JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
                WHERE um.user_id = %s AND ud.name = 'soldiers'
                """,
                (target_id,),
            )
            s_row = db.fetchone()
            if s_row and s_row[0] > 0:
                soldiers_lost = min(int(s_row[0]), hits)
                db.execute(
                    "UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s",
                    (soldiers_lost, target_id, s_row[1]),
                )

        if strike_target == POPULATION_TARGET:
            damage_report = (
                _population_report(pop_result) if hits > 0
                else "failed to inflict meaningful damage"
            )
        elif not had_target:
            damage_report = f"found no {strike_target.replace('_', ' ')} to destroy"
        elif destroyed > 0:
            damage_report = f"destroyed {destroyed} {strike_target.replace('_', ' ')}"
        else:
            damage_report = "failed to inflict meaningful damage"
        if soldiers_lost:
            damage_report += f" and killed {soldiers_lost} soldiers caught in the open"

        _strike_news(
            db, attacker_id, target_id,
            attacker_msg=(
                f"Your drone swarm on {{target_name}} had {surviving_drones}/{drones_count} "
                f"drones evade interception ({intercepted} shot down). Result: {damage_report}."
            ),
            defender_msg=(
                f"🚨 UNDER ATTACK: {{attacker_name}} launched {drones_count} kamikaze drones at you! "
                f"Your defenses shot down {intercepted}. Result: {damage_report}."
            ),
        )

    return redirect(f"/country/id={target_id}")


@wars_bp.route("/cruise_missile_strike", methods=["POST"])
@login_required
def cruise_missile_strike():
    """Launch cruise_missiles (stockpile-backed) at a target building.
    Pricier and slower to manufacture than drones, but a guaranteed hit --
    no interception roll, unlike drone_strike above."""
    attacker_id = session["user_id"]
    try:
        target_id = int(request.form.get("target_id"))
        strike_target = request.form.get("strike_target")
        missiles_count = int(request.form.get("missiles_count"))
    except (TypeError, ValueError):
        return error(400, "Invalid payload")

    if attacker_id == target_id:
        return error(400, "You cannot strike yourself!")
    if not _valid_strike_target(strike_target):
        return error(400, "Invalid target")
    if missiles_count <= 0:
        return error(400, "Must launch at least 1 missile.")

    with get_request_cursor() as db:
        # Same race as drone_strike above -- see the comment there.
        db.execute("SELECT pg_advisory_xact_lock(%s)", (attacker_id,))

        if not _require_active_war(db, attacker_id, target_id):
            return error(403, "You are not at war with this nation.")
        if not _target_has_building(db, target_id, strike_target):
            return error(
                400,
                f"They have no {STRIKE_TARGET_LABELS.get(strike_target, POPULATION_TARGET_LABEL)} to hit. Pick another target.",
            )

        db.execute(
            """
            SELECT um.quantity, ud.unit_id
            FROM user_military um
            JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
            WHERE um.user_id = %s AND ud.name = 'cruise_missiles'
            """,
            (attacker_id,),
        )
        row = db.fetchone()
        if not row or row[0] < missiles_count:
            return error(400, "You don't have enough cruise missiles!")
        unit_id = row[1]

        fuel_cost = variables.UNIT_LAUNCH_FUEL_COST["cruise_missiles"] * missiles_count
        if not _spend_gasoline(db, attacker_id, fuel_cost):
            return error(400, f"Not enough gasoline (need {fuel_cost})")

        db.execute(
            "UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s",
            (missiles_count, attacker_id, unit_id),
        )

        # Iron Dome (migration 0104): average province coverage vs a nationwide strike.
        from app_core.military.iron_dome import roll_intercepts

        dome_intercepted = roll_intercepts(db, target_id, missiles_count, "cruise_missiles")
        missiles_count -= dome_intercepted

        damage_points = missiles_count * 8
        pop_result = None
        if strike_target == POPULATION_TARGET:
            destroyed, had_target = 0, True
            pop_result = apply_population_strike(
                db, target_id,
                min(POP_KILL_CAP_PER_STRIKE, missiles_count * POP_KILL_PER_MISSILE),
            )
        else:
            destroyed, had_target = apply_building_damage(
                db, target_id, STRIKE_TARGET_BUILDINGS[strike_target],
                damage_points, STRIKE_TARGET_THRESHOLDS[strike_target],
            )

        if strike_target == POPULATION_TARGET:
            damage_report = _population_report(pop_result)
        elif not had_target:
            damage_report = f"found no {strike_target.replace('_', ' ')} to destroy"
        elif destroyed > 0:
            damage_report = f"destroyed {destroyed} {strike_target.replace('_', ' ')}"
        else:
            damage_report = "landed hits but didn't accumulate enough damage to destroy one"

        _strike_news(
            db, attacker_id, target_id,
            attacker_msg=(
                f"Your {missiles_count} cruise missile(s) struck {{target_name}}"
                + (f" ({dome_intercepted} shot down by Iron Dome)" if dome_intercepted else " unopposed")
                + ". "
                f"Result: {damage_report}."
            ),
            defender_msg=(
                f"🚨 UNDER ATTACK: {{attacker_name}} struck you with {missiles_count} cruise "
                f"missile(s)"
                + (f" (your Iron Domes shot down {dome_intercepted} more)" if dome_intercepted else "")
                + f". Result: {damage_report}."
            ),
        )

    return redirect(f"/country/id={target_id}")
