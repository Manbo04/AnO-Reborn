from flask import Blueprint, session, request, redirect, render_template
from helpers import (
    login_required,
    get_db_cursor,
    error,
    get_flagname,
    check_required,
    get_influence,
)
from database import get_db_connection
from attack_scripts.Nations import (
    Economy as AttackEconomy,
    Economy,
    Nation as AttackNation,
    Military,
)
from attack_scripts import Nation
import time

from units import Units
import math
import random
import traceback

# Add any other necessary imports here

# Define the wars Blueprint
wars_bp = Blueprint("wars", __name__)


# Peace offers show up here
@wars_bp.route("/peace_offers", methods=["POST", "GET"])
@login_required
def peace_offers():
    cId = session["user_id"]

    with get_db_cursor() as db:
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
            return "Something went wrong."

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
                    from market import give_resource

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


# Send peace offer
@wars_bp.route("/send_peace_offer/<int:war_id>/<int:enemy_id>", methods=["POST"])
@login_required
def send_peace_offer(war_id, enemy_id):
    cId = session["user_id"]
    if request.method == "POST":
        resources = []
        resources_amount = []
        try:
            for resource in request.form:
                amount = request.form.get(resource, None)
                if amount:
                    amo = int(amount)
                    if amo:
                        resources.append(resource)
                        resources_amount.append(amo)
        except (ValueError, TypeError):
            return error(400, "Invalid offer!")
        with get_db_cursor() as db:
            if not war_id:
                raise Exception("War id is invalid")
            resources_string = ""
            amount_string = ""
            validResources = list(Economy.resources)
            validResources.append("money")
            if len(resources) and len(resources_amount):
                for res, amo in zip(resources, resources_amount):
                    if res not in validResources:
                        raise Exception("Invalid resource")
                    resources_string += res + ","
                    amount_string += str(amo) + ","
            db.execute("SELECT peace_offer_id FROM wars WHERE id=(%s)", (war_id,))
            peace_offer_id = db.fetchone()[0]
            if not peace_offer_id:
                db.execute(
                    (
                        "INSERT INTO peace (author,demanded_resources,demanded_amount) "
                        "VALUES ((%s),(%s),(%s))"
                    ),
                    (cId, resources_string[:-1], amount_string[:-1]),
                )
                db.execute("SELECT CURRVAL('peace_id_seq')")
                lastrowid = db.fetchone()[0]
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
        return redirect("/peace_offers")


# War details page
@wars_bp.route("/war/<int:war_id>", methods=["GET"])
@login_required
def war_with_id(war_id):
    with get_db_cursor() as db:
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

        if attacker == cId:
            enemy_id = defender
        else:
            enemy_id = attacker
        if cId == attacker:
            session["enemy_id"] = defender
        else:
            session["enemy_id"] = attacker
        if cId == defender:
            cId_type = "defender"
        elif cId == attacker:
            cId_type = "attacker"
        else:
            cId_type = "spectator"
        if cId_type == "spectator":
            return error(400, "You can't view this war")
        db.execute("SELECT spies FROM military WHERE id=(%s)", (cId,))
        spy_result = db.fetchone()
        spyCount = spy_result[0] if spy_result else 0
        spyPrep = 1
        eSpyCount = 0
        eDefcon = 1
        if eSpyCount == 0:
            successChance = 100
        else:
            successChance = spyCount * spyPrep / eSpyCount / eDefcon
        attacker_flag = get_flagname(attacker)
        defender_flag = get_flagname(defender)
        return render_template(
            "war.html",
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
        )


# ...existing code...


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
        return render_template("warchoose.html", units=units, war_id=war_id)
    elif request.method == "POST":
        selected_units = {}
        special_unit = request.form.get("special_unit")
        if special_unit:
            selected_units[special_unit] = 0
            unit_amount = 1
        else:
            selected_units[request.form.get("u1")] = 0
            selected_units[request.form.get("u2")] = 0
            selected_units[request.form.get("u3")] = 0
            unit_amount = 3
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
    attack_units = Units.rebuild_from_dict(session["attack_units"])
    if request.method == "GET":
        unitamounts = Military.get_particular_units_list(
            cId, attack_units.selected_units_list
        )
        return render_template(
            "waramount.html",
            available_supplies=attack_units.available_supplies,
            selected_units=attack_units.selected_units_list,
            unit_range=len(unitamounts),
            unitamounts=unitamounts,
            unit_interfaces=Units.allUnitInterfaces,
        )
    elif request.method == "POST":
        selected_units = attack_units.selected_units_list
        selected_units = attack_units.selected_units.copy()
        units_name = list(selected_units.keys())
        incoming_unit = list(request.form)
        if len(units_name) == 3 and len(incoming_unit) == 3:
            for unit in incoming_unit:
                if unit not in Military.allUnits:
                    return "Invalid unit!"
                unit_amount = request.form[unit]
                try:
                    selected_units[unit] = int(unit_amount)
                except (ValueError, TypeError):
                    return error(400, "Unit amount entered was not a number")
            if not sum(selected_units.values()):
                return error(400, "Can't attack because you haven't sent any units")
            err_valid = attack_units.attach_units(selected_units, 3)
            session["attack_units"] = attack_units.__dict__
            if err_valid:
                return error(400, err_valid)
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
            session["attack_units"] = attack_units.__dict__
            if err_valid:
                return error(400, err_valid)
            return redirect("/wartarget")
        else:
            return "everything just broke"


@wars_bp.route("/wartarget", methods=["GET", "POST"])
@login_required
def warTarget():
    cId = session["user_id"]
    eId = session["enemy_id"]
    if request.method == "GET":
        with get_db_cursor() as db:
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
        units = {}
        return render_template(
            "wartarget.html",
            units=units,
            revealed_info=revealed_info,
            needed_types=needed_types,
        )
    if request.method == "POST":
        target = request.form.get("targeted_unit")
        target_amount = Military.get_particular_units_list(eId, [target])
        defender = Units(eId, {target: target_amount[0]}, selected_units_list=[target])
        attack_units = Units.rebuild_from_dict(session["attack_units"])
        special_fight_result = Military.special_fight(
            attack_units, defender, defender.selected_units_list[0]
        )
        if isinstance(special_fight_result, str):
            return special_fight_result
        session["from_wartarget"] = special_fight_result
        return redirect("warResult")


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
    attacker = Units.rebuild_from_dict(attack_unit_session)
    eId = session["enemy_id"]
    with get_db_cursor() as db:
        db.execute("SELECT username FROM users WHERE id=(%s)", (session["user_id"],))
        attacker_name = db.fetchone()[0]
        db.execute("SELECT username FROM users WHERE id=(%s)", (session["enemy_id"],))
        defender_name = db.fetchone()[0]
        attacker_result = {"nation_name": attacker_name}
        defender_result = {"nation_name": defender_name}
        win_condition = None
        winner = None
        result = session.get("from_wartarget", None)
        if result is None:
            db.execute("SELECT default_defense FROM military WHERE id=(%s)", (eId,))
            defensestring = db.fetchone()[0]
            defenselst = defensestring.split(",")
            from units import Units as UnitsClass

            for unit in defenselst:
                if unit not in UnitsClass.allUnits:
                    return error(400, "Invalid unit in default defense configuration.")

            # OPTIMIZATION: Fetch all defense units in ONE query instead of N queries
            defense_cols = ", ".join(defenselst)
            db.execute(f"SELECT {defense_cols} FROM military WHERE id=(%s)", (eId,))
            defense_row = db.fetchone()
            defenseunits = (
                dict(zip(defenselst, defense_row))
                if defense_row
                else {u: 0 for u in defenselst}
            )

            defender = Units(eId, defenseunits, selected_units_list=defenselst)
            prev_defender = dict(defender.selected_units)
            prev_attacker = dict(attacker.selected_units)
            db.execute(
                (
                    "SELECT war_type FROM wars WHERE ((attacker=%s AND defender=%s) "
                    "OR (attacker=%s AND defender=%s)) AND peace_date IS NULL"
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
            war_type = war_rows[-1][0]
            winner, win_condition, attack_effects = Military.fight(attacker, defender)
            if len(war_type) > 0:
                if war_type == "Raze":
                    attack_effects[0] = attack_effects[0] * 10
                elif war_type == "Loot":
                    attack_effects[0] = attack_effects[0] * 0.2
                    if winner == attacker.user_id:
                        db.execute(
                            "SELECT gold FROM stats WHERE id=(%s)", (defender.user_id,)
                        )
                        fetched = db.fetchone()
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
                        attacker_result["loot"] = {"money": loot}
                        db.execute(
                            "UPDATE stats SET gold = gold + %s WHERE id = %s",
                            (loot, attacker.user_id),
                        )
                elif war_type == "Sustained":
                    pass
                else:
                    return error(400, "Something went wrong")
            else:
                return error(500, "Something went wrong")
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
            else:
                infra_damage_effects = {}
            defender_result["infra_damage"] = infra_damage_effects
            if winner == defender.user_id:
                winner = defender_name
            else:
                winner = attacker_name
            defender_loss = {}
            attacker_loss = {}
            for unit in defender.selected_units_list:
                defender_loss[unit] = (
                    prev_defender[unit] - defender.selected_units[unit]
                )
            for unit in attacker.selected_units_list:
                attacker_loss[unit] = (
                    prev_attacker[unit] - attacker.selected_units[unit]
                )
            defender_result["unit_loss"] = defender_loss
            attacker_result["unit_loss"] = attacker_loss
        else:
            defender_result["unit_loss"] = result[0]
            defender_result["infra_damage"] = result[1]
            del session["from_wartarget"]
    attacker.save()
    del session["attack_units"]
    del session["enemy_id"]
    return render_template(
        "warResult.html",
        winner=winner,
        win_condition=win_condition,
        defender_result=defender_result,
        attacker_result=attacker_result,
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
        with get_db_cursor() as db:
            import logging

            logger = logging.getLogger(__name__)
            attacker = Economy(int(session.get("user_id")))
            defender = Economy(defender_id)
            logger.debug(
                "declare_war: attacker=%s defender=%s", attacker.id, defender.id
            )
            if attacker.id == defender.id:
                return error(400, "Can't declare war on yourself")
            logger.debug("declare_war: checking existing wars")
            db.execute(
                (
                    "SELECT id FROM wars WHERE ((attacker=%s AND defender=%s) OR "
                    "(attacker=%s AND defender=%s)) AND peace_date IS NULL"
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
            attacker_provinces = db.fetchone()[0] or 0
            db.execute(
                "SELECT COUNT(id) FROM provinces WHERE userId=%s", (defender.id,)
            )
            defender_provinces = db.fetchone()[0] or 0
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
                    "INSERT INTO wars (attacker, defender, war_type, agressor_message, "
                    "start_date, last_visited) VALUES (%s, %s, %s, %s, %s, %s)"
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
            db.execute("SELECT username FROM users WHERE id=(%s)", (attacker.id,))
            attacker_name = db.fetchone()[0]
            # Insert news directly using the current cursor to avoid nested DB context issues
            db.execute(
                "INSERT INTO news(destination_id, message) VALUES (%s, %s)",
                (defender.id, f"{attacker_name} declared war!"),
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


@wars_bp.route("/defense", methods=["GET", "POST"])
@login_required
def defense():
    cId = session["user_id"]
    units = Military.get_military(cId)
    if request.method == "GET":
        return render_template("defense.html", units=units)
    elif request.method == "POST":
        with get_db_cursor() as db:
            defense_units = list(request.form.values())
        for item in defense_units:
            if item not in Military.allUnits:
                return error(400, "Invalid unit types!")
        if len(defense_units) == 3:
            defense_units = ",".join(defense_units)
            db.execute(
                "UPDATE military SET default_defense=(%s) WHERE id=(%s)",
                (defense_units, cId),
            )
        else:
            return error(400, "Invalid number of units selected!")
        return redirect("/wars")


@wars_bp.route("/wars", methods=["GET", "POST"])
@login_required
def wars():
    cId = session["user_id"]
    if request.method == "GET":
        normal_units = Military.get_military(cId)
        special_units = Military.get_special(cId)
        units = normal_units.copy()
        units.update(special_units)
        with get_db_cursor() as db:
            db.execute("SELECT username FROM users WHERE id=(%s)", (cId,))
            yourCountry = db.fetchone()[0]
            try:
                db.execute(
                    (
                        "SELECT id, defender, attacker FROM wars WHERE (attacker=%s "
                        "OR defender=%s) AND peace_date IS NULL"
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
                        # NOTE: update_supply is now performed in background; skip here
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
                warsCount = db.fetchone()[0]
            except Exception:
                warsCount = 0
        return render_template(
            "wars.html",
            units=units,
            warsCount=warsCount,
            war_info=war_info,
            yourCountry=yourCountry,
        )


@wars_bp.route("/find_targets", methods=["GET", "POST"])
@login_required
def find_targets():
    cId = session["user_id"]
    if request.method == "GET":
        with get_db_cursor() as db:
            db.execute("SELECT COUNT(id) FROM provinces WHERE userid=%s", (cId,))
            user_provinces = db.fetchone()[0]
            min_provinces = max(0, user_provinces - 3)
            max_provinces = user_provinces + 1
            user_influence = get_influence(cId)
            # Choose a sensible search range around the player's influence.
            # For very new/low-influence players, expand the max_influence so
            # they still see potential targets (otherwise max would be 0 and
            # filter out viable targets).
            min_influence = max(0.0, user_influence * 0.9)
            max_influence = max(user_influence * 2.0, 100.0)
            query = (
                "SELECT users.id, users.username, users.flag, "
                "COUNT(provinces.id) as provinces_count, "
                "COALESCE(SUM(military.soldiers * 0.02 + military.artillery * 1.6 + "
                "military.tanks * 0.8 + "
                "military.fighters * 3.5 + "
                "military.bombers * 2.5 + "
                "military.apaches * 3.2 + "
                "military.submarines * 4.5 + "
                "military.destroyers * 3 + "
                "military.cruisers * 5.5 + "
                "military.icbms * 250 + military.nukes * 500 + "
                "military.spies * 25), 0) as influence "
                "FROM users "
                "LEFT JOIN provinces ON users.id = provinces.userId "
                "LEFT JOIN military ON users.id = military.id "
                "WHERE users.id != %s "
                "GROUP BY users.id, users.username, users.flag "
                "HAVING COUNT(provinces.id) BETWEEN %s AND %s "
                "ORDER BY users.username "
                "LIMIT 50"
            )
            db.execute(query, (cId, min_provinces, max_provinces))
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
            if len(targets_list) >= 20:
                break

        # Handle filtering
        search = request.args.get("search", "").strip()
        sort = request.args.get("sort", "influence")
        sortway = request.args.get("sortway", "desc")

        if search:
            targets_list = [
                t for t in targets_list if search.lower() in t["username"].lower()
            ]

        if sort == "influence":
            targets_list.sort(key=lambda x: x["influence"], reverse=(sortway == "desc"))
        elif sort == "provinces":
            targets_list.sort(key=lambda x: x["provinces"], reverse=(sortway == "desc"))
        elif sort == "username":
            targets_list.sort(
                key=lambda x: x["username"].lower(), reverse=(sortway == "desc")
            )

        return render_template("find_targets.html", targets=targets_list)
    # POST - find a target by id or username and redirect
    defender_raw = request.form.get("defender")
    if not defender_raw:
        return error(400, "Missing defender")
    defender_id = None
    try:
        defender_id = int(defender_raw)
    except (TypeError, ValueError):
        with get_db_cursor() as db:
            db.execute("SELECT id FROM users WHERE username=%s", (defender_raw,))
            row = db.fetchone()
            if row:
                defender_id = row[0]
    if not defender_id:
        return error(404, "Country not found")
    return redirect(f"/country/id={defender_id}")


# ...existing code for peace_offers and send_peace_offer will be moved here next...
# War-related Flask routes will be moved here during refactor
