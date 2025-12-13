# FULLY MIGRATED
import random
import math
from app import app
from flask import request, render_template, session, redirect
from database import get_db_cursor
from helpers import login_required, error, get_flagname
from attack_scripts import Nation, Military, Economy
import inspect

# Some deployments include a minimal `Nation` class in `attack_scripts.Nations`
# that does not accept an ID argument (causing `Nation(int(...))` to raise
# `TypeError: Nation() takes no arguments`). The fuller implementation
# (with `__init__(self, nationID, ...)`, `get_provinces`, `send_news`, etc.)
# ended up attached to `Economy` in that module due to historical layout.
# If the imported `Nation` is the minimal one (no __init__ params beyond
# `self`), prefer using `Economy` as the runtime `Nation` implementation
# so routes like `/declare_war` keep working while we clean up the module.
try:
    params = inspect.signature(Nation.__init__).parameters
    # parameters include 'self' when present; if there are no other params
    # the constructor takes no required arguments and will fail when called
    # with an ID. In that case swap in `Economy` which contains the
    # expected implementation in this codebase.
    if len(params) <= 1:
        Nation = Economy
except Exception:
    # If anything goes wrong inspecting, prefer the safer, fuller class.
    Nation = Economy
from units import Units
import time
from helpers import get_influence, check_required
from dotenv import load_dotenv
load_dotenv()
import os
import traceback

"""
war page: choose a war

Page 1:
Goes to a page where each 3 units choose what type of unit to attack with (12 options, 9 war and 3 special). There"s up to 8 of these boxes available, since you can attack 5 nations at once or defend from 3 nations at once (make this flexible tho).
War
9 check boxes

Special operations
3 check boxes

Continue button

Page 2:
Goes to a page where you choose how many to send of each of your 3 units, or 1 special

Page 3:
Goes to a page where you target what all your units attack (13 options: 9 war units, 3 specials, 1 morale) (targeting 3)

Page 4:
Whoever lost fewer value in units is the winner. Based on the degree, morale changes. Based on degree on winning, sets a tax on the losing nation.
"""

# NOTICE put these "not routes" inside a different file like utils.py
# Update supplies amount only when user visit page where supplies interaction neccessary
# Call this from every function which displays or works with the supplies
def update_supply(war_id):

    MAX_SUPPLY = 2000

    with get_db_cursor() as db:

        db.execute("SELECT attacker_supplies,defender_supplies,last_visited FROM wars WHERE id=%s", (war_id,))
        attacker_supplies, defender_supplies, supply_date = db.fetchall()[0]

        current_time = time.time()

        if current_time < int(supply_date):
            return "TIME STAMP IS CORRUPTED"

        time_difference = current_time - supply_date
        hours_count = time_difference//3600
        supply_by_hours = hours_count*50 # 50 supply in every hour

        # TODO: give bonus supplies if there is specific infrastructure for it
        # if supply_bonus: xy
        if supply_by_hours > 0:

            db.execute("SELECT attacker,defender FROM wars where id=(%s)", (war_id,))
            attacker_id, defender_id = db.fetchone()

            # TODO: this isn't tested yet until the END TODO, so test it
            attacker_upgrades = Nation.get_upgrades("supplies", attacker_id)
            defender_upgrades = Nation.get_upgrades("supplies", defender_id)

            for i in attacker_upgrades.values():
                attacker_supplies += i

            for i in defender_upgrades.values():
                defender_supplies += i
            # END TODO

            # Limit supplies amount to MAX_SUPPLY
            if (supply_by_hours+attacker_supplies) > MAX_SUPPLY:
                db.execute("UPDATE wars SET attacker_supplies=(%s) WHERE id=(%s)", (MAX_SUPPLY, war_id))
            else:
                db.execute("UPDATE wars SET attacker_supplies=(%s) WHERE id=(%s)", (supply_by_hours+attacker_supplies, war_id))

            if (supply_by_hours+defender_supplies) > MAX_SUPPLY:
                db.execute("UPDATE wars SET defender_supplies=(%s) WHERE id=(%s)", (MAX_SUPPLY, war_id))
            else:
                db.execute("UPDATE wars SET defender_supplies=(%s) WHERE id=(%s)", (supply_by_hours+defender_supplies, war_id))

            db.execute("UPDATE wars SET last_visited=(%s) WHERE id=(%s)", (time.time(), war_id))

# so this is page 0, war menu, choose a war
@app.route("/wars", methods=["GET", "POST"])
@login_required
def wars():

    cId = session["user_id"]

    if request.method == "GET":
        normal_units = Military.get_military(cId)
        special_units = Military.get_special(cId)
        units = normal_units.copy()
        units.update(special_units)

        # obtain the user's country from sql table
        with get_db_cursor() as db:
            db.execute("SELECT username FROM users WHERE id=(%s)", (cId,))
            yourCountry = db.fetchone()[0]

            try:
                db.execute("SELECT id, defender, attacker FROM wars WHERE (attacker=%s OR defender=%s) AND peace_date IS NULL", (cId, cId))
                war_attacker_defender_ids = db.fetchall()
                war_info = {}
                for war_id,defender,attacker in war_attacker_defender_ids:

                    update_supply(war_id)

                    attacker_info = {}
                    defender_info = {}

                    # fetch attacker wars
                    db.execute("SELECT username FROM users WHERE id=%s", (attacker,))
                    att_name = db.fetchone()[0]
                    attacker_info["name"] = att_name
                    attacker_info["id"] = attacker

                    db.execute("SELECT attacker_morale, attacker_supplies FROM wars WHERE id=%s", (war_id,))
                    att_morale_and_supplies = db.fetchone()

                    attacker_info["morale"] = att_morale_and_supplies[0]
                    attacker_info["supplies"] = att_morale_and_supplies[1]

                    # fetch defender wars
                    db.execute("SELECT username FROM users WHERE id=%s", (defender,))
                    def_name = db.fetchone()[0]
                    defender_info["name"] = def_name

                    db.execute("SELECT defender_morale,defender_supplies FROM wars WHERE id=%s", (war_id,))
                    def_morale_and_supplies = db.fetchone()

                    defender_info["morale"] = def_morale_and_supplies[0]
                    defender_info["supplies"] = def_morale_and_supplies[1]

                    defender_info["id"] = defender

                    attacker_info["flag"] = get_flagname(attacker)
                    defender_info["flag"] = get_flagname(defender)

                    war_info[war_id] = {"att": attacker_info, "def": defender_info}
            except:
                war_attacker_defender_ids = []
                war_info = {}

            try:
                db.execute("SELECT COUNT(attacker) FROM wars WHERE (defender=%s OR attacker=%s) AND peace_date IS NULL", (cId, cId))
                warsCount = db.fetchone()[0]
            except:
                warsCount = 0

        return render_template("wars.html", units=units, warsCount=warsCount, war_info=war_info)

# Peace offers show up here
@app.route("/peace_offers", methods=["POST", "GET"])
@login_required
def peace_offers():
    cId = session["user_id"]

    with get_db_cursor() as db:
        db.execute("SELECT peace_offer_id FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND peace_date IS NULL", (cId, cId))
        peace_offers = db.fetchall()
        offers = {}
        incoming_counter=0
        outgoing_counter=0

        incoming={}
        outgoing={}

        resources = []
        resources_fetch = None

        try:
            if peace_offers:

                for offer in peace_offers:
                    offer_id = offer[0]
                    if offer_id is not None:

                        # Every offer has a different subset
                        # offers[offer_id] = {}

                        db.execute("SELECT demanded_resources FROM peace WHERE id=(%s)", (offer_id,))
                        resources_fetch = db.fetchone()
                        db.execute("SELECT author FROM peace WHERE id=(%s)", (offer_id,))
                        author_id = db.fetchone()[0]
                        if author_id == cId:
                            offer = outgoing
                            outgoing_counter+=1
                        else:
                            offer = incoming
                            incoming_counter+=1

                        offer[offer_id] = {}

                    if resources_fetch:
                        resources = resources_fetch[0]
                        if resources:
                            db.execute("SELECT demanded_amount FROM peace WHERE id=(%s)", (offer_id,))
                            amounts = db.fetchone()[0].split(",")
                            resources = resources.split(",")

                            offer[offer_id]["resource_count"] = len(resources)
                            offer[offer_id]["resources"] = resources
                            offer[offer_id]["amounts"] = amounts

                            if cId == author_id:
                                offer[offer_id]["owned"] = 1

                        # white peace
                        else:
                            offer[offer_id]["peace_type"] = "white"

                        db.execute("SELECT author FROM peace WHERE id=(%s)", (offer_id,))
                        # author_id = db.fetchone()[0]
                        db.execute("SELECT username FROM users WHERE id=(%s)", (author_id,))
                        offer[offer_id]["author"] = [author_id, db.fetchone()[0]]

                        db.execute("SELECT attacker,defender FROM wars WHERE peace_offer_id=(%s)", (offer_id,))
                        ids=db.fetchone()
                        if ids[0] == author_id:
                            db.execute("SELECT username FROM users WHERE id=(%s)", (ids[1],))
                            receiver_name = db.fetchone()[0]
                            receiver_id = ids[1]
                        else:
                            db.execute("SELECT username FROM users WHERE id=(%s)", (ids[0],))
                            receiver_id = ids[0]
                            receiver_name = db.fetchone()[0]

                        offer[offer_id]["receiver_id"] = receiver_id
                        offer[offer_id]["receiver"] = receiver_name
        except (TypeError, AttributeError, IndexError, KeyError):
            return "Something went wrong."

    if request.method == "POST":

        offer_id = request.form.get("peace_offer", None)

        # Validate inputs
        try:
            offer_id = int(offer_id)
        except ValueError:
            return error(400, "Invalid offer ID")

        # Make sure that others can't accept,delete,etc. the peace offer other than the participants
        db.execute("SELECT id FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND peace_offer_id=(%s) AND peace_date IS NULL", (cId, cId, offer_id))
        result = db.fetchone()
        if not result:
            raise TypeError("Invalid peace offer")
        check_validity = result[0]

        decision = request.form.get("decision", None)

        # Offer rejected or revoked
        if decision == "0":
            db.execute("UPDATE wars SET peace_offer_id=NULL WHERE peace_offer_id=(%s)", (offer_id,))
            db.execute("DELETE FROM peace WHERE id=(%s)", (offer_id,))

        elif author_id != cId:

            # Offer accepted
            if decision == "1":
                # TODO: send a message about the decision to the participants
                # maybe do the above using a table created for metadata this way we can also send other message not just the peace offer

                eco = Economy(cId)
                resource_dict = eco.get_particular_resources(resources)

                # MAYBE WORKS until this part (???????????)
                print(resource_dict)

                # TODO: move the below check to the transfer_resources
                # check validity if amount is bigger than available resources
                count = 0
                for value in resource_dict.values():
                    if int(amounts[count]) > value:
                        return error(400, f"Can't accept peace offer because you don't have the required resources!. {int(amounts[count])} > {value}")

                    print(f"Transfer: {resources[count], int(amounts[count]), author_id, cId}")

                    from market import give_resource  # delayed import to avoid circular dependency
                    successful = give_resource(cId, author_id, resources[count], int(amounts[count]))
                    if successful != True:
                        return error(400, successful)
                    count += 1

                # TODO: test this 
                Nation.set_peace(db, connection, None, {"option": "peace_offer_id", "value": offer_id})

            else:
                return error(400, "No decision was made.")
        else:
            return error(403, "You can't accept your own offer.")

        return redirect("/peace_offers")

    return render_template(
    "peace/peace_offers.html", cId=cId,
    incoming_peace_offers=incoming, outgoing_peace_offers=outgoing,
    incoming_counter=incoming_counter, outgoing_counter=outgoing_counter)

@app.route("/send_peace_offer/<int:war_id>/<int:enemy_id>", methods=["POST"])
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
        except:
            return "Invalid offer!"

        with get_db_cursor() as db:
            # try:
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

                    resources_string+=res+","
                    amount_string+=str(amo)+","

            # TODO: Made peace offer where can offer to give resources and not just demand
            # if enemy_id is None:
            #     return "Selected target is invalid!"

            db.execute("SELECT peace_offer_id FROM wars WHERE id=(%s)", (war_id,))
            peace_offer_id = db.fetchone()[0]

            # Only one peace offer could be attached to one war
            if not peace_offer_id:
                db.execute("INSERT INTO peace (author,demanded_resources,demanded_amount) VALUES ((%s),(%s),(%s))", (cId, resources_string[:-1], amount_string[:-1]))
                db.execute("SELECT CURRVAL('peace_id_seq')")
                lastrowid = db.fetchone()[0]
                db.execute("UPDATE wars SET peace_offer_id=(%s) WHERE id=(%s)", (lastrowid, war_id))

            # If peace offer is already associated with war then just update it
            else:
                db.execute("UPDATE peace SET author=(%s),demanded_resources=(%s),demanded_amount=(%s)", (cId, resources_string[:-1], amount_string[:-1]))

            # Send white peace (won't lose or gain anything)
        return redirect("/peace_offers")

# page 0, kind of a pseudo page where you can click attack vs special
@app.route("/war/<int:war_id>", methods=["GET"])
@login_required
def war_with_id(war_id):
    with get_db_cursor() as db:
        # Check if war_exist
        db.execute("SELECT * FROM wars WHERE id=(%s) AND peace_date IS NULL",(war_id,))
        valid_war = db.fetchone()
        if not valid_war:
            return error(404, "This war doesn't exist")

        # Check if peace already made
        db.execute("SELECT peace_date FROM wars WHERE id=(%s)", (war_id,))
        peace_made = db.fetchone()[0]
        if peace_made:
            return "This war already ended"

        update_supply(war_id)

        cId = session["user_id"]

        # defender meaning the one who got declared on
        db.execute("SELECT defender FROM wars WHERE id=(%s)", (war_id,))
        defender = db.fetchone()[0]
        db.execute("SELECT username FROM users WHERE id=(%s)", (defender,))
        defender_name = db.fetchone()[0]
        db.execute("SELECT defender_supplies,defender_morale FROM wars WHERE id=(%s)",(war_id,))
        info = db.fetchone()
        defender_info={"morale": info[1], "supplies": info[0]}

        # # attacker meaning the one who intially declared war, nothing to do with the current user (who is obviously currently attacking)
        db.execute("SELECT attacker FROM wars WHERE id=(%s)", (war_id,))
        attacker = db.fetchone()[0]
        db.execute("SELECT username FROM users WHERE id=(%s)", (attacker,))
        attacker_name = db.fetchone()[0]
        db.execute("SELECT attacker_supplies,attacker_morale FROM wars WHERE id=(%s)",(war_id,))
        info = db.fetchone()
        attacker_info={"morale": info[1], "supplies": info[0]}

        # The current enemy from our perspective (not neccessarily the one who declared war)
        if attacker==cId:
            enemy_id=defender
        else:
            enemy_id=attacker

        db.execute("SELECT war_type FROM wars WHERE id=(%s)", (war_id,))
        war_type = db.fetchone()[0]
        db.execute("SELECT agressor_message FROM wars WHERE id=(%s)", (war_id,))
        agressor_message = db.fetchone()[0]

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
        spyCount = db.fetchone()[0]
        spyPrep = 1 # this is an integer from 1 to 5
        eSpyCount = 0 # this is an integer from 0 to 100
        eDefcon = 1 # this is an integer from 1 to 5

        if eSpyCount == 0:
            successChance = 100
        else:
            successChance = spyCount * spyPrep / eSpyCount / eDefcon

        attacker_flag = get_flagname(attacker)
        defender_flag = get_flagname(defender)

        return render_template("war.html",attacker_flag=attacker_flag, defender_flag=defender_flag, defender_info=defender_info, defender=defender, attacker_info=attacker_info, attacker=attacker,
        war_id=war_id, attacker_name=attacker_name, defender_name=defender_name, war_type=war_type,
        agressor_message=agressor_message, cId_type=cId_type, spyCount=spyCount, successChance=successChance, peace_to_send=enemy_id)

# the flask route that activates when you click attack on a nation in your wars page.
# check if you have enough supplies.
# page 1: where you can select what units to attack with
@app.route("/warchoose/<int:war_id>", methods=["GET", "POST"])
@login_required
@check_required
def warChoose(war_id):
    cId = session["user_id"]
    # print("HEY", session.get("attack_units", None))

    if request.method == "GET":

        # this is upon first landing on this page after the user clicks attack in wars.html
        normal_units = Military.get_military(cId)
        special_units = Military.get_special(cId)
        units = normal_units.copy()
        units.update(special_units)

        return render_template("warchoose.html", units=units, war_id=war_id)

    elif request.method == "POST":
        # this post request happens when they click submit, upon which we would redirect to /waramount
        # typical post redirect get pattern means we should do with the request.form.get values here (the 3 units)
        # store the 3 values in session and retrieve it in waramount later

        selected_units = {}

        # If special unit sent
        special_unit = request.form.get("special_unit")
        if special_unit:
            selected_units[special_unit] = 0
            unit_amount = 1

         # If regular units sent
        else:
            selected_units[request.form.get("u1")] = 0
            selected_units[request.form.get("u2")] = 0
            selected_units[request.form.get("u3")] = 0
            unit_amount = 3

        attack_units = Units(cId, war_id=war_id)

        # Output error if any
        return_error = attack_units.attach_units(selected_units, unit_amount)
        if return_error:
            return error(400, return_error)

        # BEFORE DEBUG:
        # cache Unit object reference in session
        # session["attack_units"] = attack_units
        # return redirect("/waramount")

        # DURING DEBUG:
        session["attack_units"] = attack_units.__dict__

        # return redirect("/warchoose")
        return redirect("/waramount")

# page 2 choose how many of each of your units to send
@app.route("/waramount", methods=["GET", "POST"])
@login_required
@check_required
def warAmount():
    cId = session["user_id"]
    attack_units = Units.rebuild_from_dict(session["attack_units"])

    if request.method == "GET":

        with get_db_cursor() as db:
            # grab supplies amount
            # if the user is the attacker in the war
            # if cId == db.execute("SELECT attacker FROM wars WHERE ")
            # db.execute("SELECT attacker_supplies FROM wars WHERE id=(%s)", (cId,))
            # supplies = db.fetchone()[0]

            # find the max amount of units of each of those 3 the user can attack with to send to the waramount page on first load
            unitamounts = Military.get_particular_units_list(cId, attack_units.selected_units_list)

            # turn this dictionary into a list of its values
            # if the user comes to this page by bookmark, it might crash because session["attack_units"] wouldn"t exist
            # TODO: rename *.jpg file related to units because not load in (or create a list of image name with the corresponding unit)
            return render_template("waramount.html", available_supplies=attack_units.available_supplies, selected_units=attack_units.selected_units_list,
            unit_range=len(unitamounts), unitamounts=unitamounts, unit_interfaces=Units.allUnitInterfaces)

    elif request.method == "POST":

        # Separate object's units list from new units list
        selected_units = attack_units.selected_units_list

        # this is in the form of a dictionary
        selected_units = attack_units.selected_units.copy()

        # 3 units list
        units_name = list(selected_units.keys())
        incoming_unit = list(request.form)

        # check if its 3 regular units or 1 special unit (missile or nuke)
        if len(units_name) == 3 and len(incoming_unit) == 3:  # this should happen if 3 regular units
            for unit in incoming_unit:
                if unit not in Military.allUnits:
                    return "Invalid unit!"

                unit_amount = request.form[unit]

                try:
                    selected_units[unit] = int(unit_amount)
                except:
                    return error(400, "Unit amount entered was not a number") # maybe add javascript checks for this also in the front end

            # Check if user send at least 1 amount from a specific unit type
            if not sum(selected_units.values()):
                return error(400, "Can't attack because you haven't sent any units")

            # Check every time when user input comes in, lest the user bypass input validation
            # Error code if any else return None
            err_valid = attack_units.attach_units(selected_units, 3)
            session["attack_units"] = attack_units.__dict__
            if err_valid:
                return error(400, err_valid)

            # same note as before as to how to use this request.form.get to get the unit amounts.

            return redirect("/warResult")  # warTarget route is skipped

        elif len(units_name) == 1:  # this should happen if special
            amount = int(request.form.get(units_name[0]))
            if not amount:
                return error(400, "Can't attack because you haven't sent any units")

            selected_units[units_name[0]] = amount
            err_valid = attack_units.attach_units(selected_units, 1)
            session["attack_units"] = attack_units.__dict__
            if err_valid:
                return error(400, err_valid)

            return redirect("/wartarget")

        else:  # lets just leave this here if something dumb happens, then we can fix it!
            return ("everything just broke")

# This route is only for ICMB or nuke attacks
@app.route("/wartarget", methods=["GET", "POST"])
@login_required
def warTarget():
    cId = session["user_id"]
    eId = session["enemy_id"]

    if request.method == "GET":

        with get_db_cursor() as db:

            db.execute("SELECT * FROM spyinfo WHERE spyer=(%s) AND spyee=(%s)", (cId, eId,))
        revealed_info = db.fetchall()
        needed_types = ["soldiers", "tanks", "artillery", "fighters",
                        "bombers", "apaches", "destroyers", "cruisers", "submarines"]

        # cycle through revealed_info. if a value is true, and it"s a unit, add it to the units dictionary
        units = {}
        return render_template("wartarget.html", units=units)

    if request.method == "POST":

        # TODO: check if targeted_unit is send a valid unit type like soldiers and not like sdfsgsdw
        target = request.form.get("targeted_unit")
        target_amount = Military.get_particular_units_list(eId, [target])

        # The attack happens before warResult page rendered
        # Skip attach_units because no need for validation for target_amount since the data coming directly from the db without user affection
        # only validate is targeted_unit is valid
        defender = Units(eId, {target: target_amount[0]}, selected_units_list=[target])
        attack_units = Units.rebuild_from_dict(session["attack_units"])
        # session["from_wartarget"] = Military.special_fight(session["attack_units"], defender, defender.selected_units_list[0])

        special_fight_result = Military.special_fight(attack_units, defender, defender.selected_units_list[0])

        # NOTE: MIGHT PUT THE VALIDATION WHICH GIVES ERROR TO THIS FUNCTION AND DELETE FROM SPECIAL_FIGHT (optimization purpose)
        # Error messages
        if type(special_fight_result) == str:
            return special_fight_result

        session["from_wartarget"] = special_fight_result

        return redirect("warResult")

# page 4 results
# infra damage, building damage
# giant loot, coalition loot, reparation tax set if morale reaches 0
@app.route("/warResult", methods=["GET"])
@login_required
def warResult():
    attack_unit_session = session.get("attack_units", None)
    if attack_unit_session is None:
        return redirect("/wars")

    attacker = Units.rebuild_from_dict(attack_unit_session)
    eId = session["enemy_id"]

    # dev: making sure these values are correct
    # print(attacker.selected_units, "| attack units") # {'soldiers': 0, 'tanks': 0, 'artillery': 0} | attack units
    # print(eId, "| eId") # 10 | eId
    # print(defensestring, "| defense units")  # soldiers,tanks,artillery | defense units

    with get_db_cursor() as db:

        db.execute("SELECT username FROM users WHERE id=(%s)", (session["user_id"],))
        attacker_name = db.fetchone()[0]
        db.execute("SELECT username FROM users WHERE id=(%s)", (session["enemy_id"],))
        defender_name = db.fetchone()[0]

        attacker_result = {"nation_name": attacker_name}
        defender_result = {"nation_name": defender_name}

        win_condition = None
        winner = None

        # If user came from /wartarget only then they have from_wartarget
        result = session.get("from_wartarget", None)
        if result is None:
            db.execute("SELECT default_defense FROM military WHERE id=(%s)", (eId,))
            defensestring = db.fetchone()[0]  # this is in the form of a string soldiers,tanks,artillery

            defenselst = defensestring.split(",")  # will give something like: [soldiers, tanks, artillery]
            
            # Validate units are legitimate (prevents SQL injection via stored data)
            from units import Units as UnitsClass
            for unit in defenselst:
                if unit not in UnitsClass.allUnits:
                    return error(400, "Invalid unit in default defense configuration.")
            
            defenseunits = {}

            for unit in defenselst:
                db.execute(f"SELECT {unit} FROM military WHERE id=(%s)", (eId,))
                defenseunits[unit] = db.fetchone()[0]

            defender = Units(eId, defenseunits, selected_units_list=defenselst)

            # Save the stats before the fight which used to calculate the lost amount from unit
            prev_defender = dict(defender.selected_units)
            prev_attacker = dict(attacker.selected_units)

            # TODO: error because there isn't even one province make error handler
            # TODO: enforce war type like raze,etc.
            # example for the above line: if war_type is raze then attack_effects[0]*10

            # WAR TYPES
            # The war_type which the attacker choose hit back if lose the war
            # "raze" --> no loot, no reparation tax, destroy 10x more buildings, destroys money/res
            # "sustained" --> 1x loot, 1x infra destruction, 1x building destroy
            # "loot" --> 2x loot, 0.1x infra destruction, buildings cannot be destroyed
            db.execute("SELECT war_type FROM wars WHERE ((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s)) AND peace_date IS NULL", (attacker.user_id, defender.user_id, defender.user_id, attacker.user_id))
            war_rows = db.fetchall()
            if not war_rows:
                # no matching war row found — treat as server error (shouldn't happen)
                return error(500, "Something went wrong")

            war_type = war_rows[-1][0]

            # attack_effects = sum of 3 attack effect in fight() method
            winner, win_condition, attack_effects = Military.fight(attacker, defender)

            if len(war_type) > 0:
                if war_type == "Raze":

                    # infrastructure damage
                    attack_effects[0] = attack_effects[0]*10

                elif war_type == "Loot":

                    # infrastructure damage
                    attack_effects[0] = attack_effects[0]*0.2

                    # resource loot amount
                    if winner == attacker.user_id:

                      # TODO: maybe include all resources here
                      lootable_resource = "gold"
                      db.execute("SELECT gold FROM stats WHERE id=(%s)", (defender.user_id,))
                      fetched = db.fetchone()
                      available_resource = 0
                      if fetched and fetched[0] is not None:
                          try:
                              # ensure numeric
                              available_resource = float(fetched[0])
                          except Exception:
                              available_resource = 0

                      # max lootable is 10% of available resources (integer)
                      max_loot = int(math.floor(max(0, available_resource * 0.1)))
                      # randint requires integer bounds; ensure at least 0
                      if max_loot < 0:
                          max_loot = 0

                      loot = random.randint(0, max_loot)
                      attacker_result["loot"] = {"money": loot}
                      db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (loot, attacker.user_id))

                elif war_type == "Sustained":
                    pass

                # Invalid war type
                else: return error(400, "Something went wrong")

            else:
                # it could mean invalid user id
                return error(500, "Something went wrong")

            db.execute("SELECT id FROM provinces WHERE userId=(%s) ORDER BY id ASC", (defender.user_id,))
            province_id_fetch = db.fetchall()
            if len(province_id_fetch) > 0:
                random_province = province_id_fetch[random.randint(0, len(province_id_fetch)-1)][0]

                # Currently units only affect public works
                public_works = Nation.get_public_works(random_province)
                infra_damage_effects = Military.infrastructure_damage(attack_effects[0], public_works, random_province)
            else:
                infra_damage_effects = {}

            defender_result["infra_damage"] = infra_damage_effects

            if winner == defender.user_id:
                winner = defender_name
            else: winner = attacker_name

            defender_loss = {}
            attacker_loss = {}

            for unit in defender.selected_units_list:
                defender_loss[unit] = prev_defender[unit]-defender.selected_units[unit]

            for unit in attacker.selected_units_list:
                attacker_loss[unit] = prev_attacker[unit]-attacker.selected_units[unit]

            defender_result["unit_loss"] = defender_loss
            attacker_result["unit_loss"] = attacker_loss
        else:
            defender_result["unit_loss"] = result[0]
            defender_result["infra_damage"] = result[1]

            # unlink the session values so user can't just reattack when reload or revisit this page
            del session["from_wartarget"]

    # possible war policies:
    # "empire builder"--> winning gives no loot 2x reparation tax
    # "pirate" --> winning gives 2x more loot no reparation tax
    # "tactical" --> winning gives 1x loot 1x reparation tax
    # "pacifist" --> winning gives no loot no reparation tax, lowers project timer by 5 days, boosts your economy by 10%
    # "guerilla": --> winning gives 1x loot no reparation tax, losing makes you lose 40% less loot, and you resist 60% reparation tax.

    # save method only function for the attacker now, and maybe we won't change that
    # saves the decreased supply amount
    attacker.save()

    # unlink the session values so user can't just reattack when reload or revisit this page
    del session["attack_units"]
    del session["enemy_id"]

    return render_template(
        "warResult.html",
        winner=winner,
        win_condition=win_condition,
        defender_result=defender_result,
        attacker_result=attacker_result)

# Endpoint for war declaration
@app.route("/declare_war", methods=["POST"])
@login_required
def declare_war():

    # CONSTANT VALUE
    WAR_TYPES = ["Raze", "Sustained", "Loot"]
    # Validate inputs early to return clear errors instead of a 500
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
            # Use `Economy` here because some deployments include a
            # minimal `Nation` class in `attack_scripts.Nations` which
            # doesn't accept an ID parameter. `Economy` provides the
            # fuller implementation we rely on (get_provinces, send_news, etc.).
            attacker = Economy(int(session.get("user_id")))
            defender = Economy(defender_id)

            if attacker.id == defender.id:
                return error(400, "Can't declare war on yourself")

            db.execute("SELECT attacker, defender FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND peace_date IS NULL", (attacker.id, attacker.id,))
            already_war_with = db.fetchall()

            if ((attacker.id, defender.id) in already_war_with) or ((defender.id, attacker.id) in already_war_with):
                return error(400, "You're already in a war with this country!")

            # Check province difference
            attacker_provinces = attacker.get_provinces()["provinces_number"]
            defender_provinces = defender.get_provinces()["provinces_number"]

            # TODO: might put this into abs() because if defender_provinces > attacker_provinces then the > 1 won't be true
            if (attacker_provinces - defender_provinces > 1):
                return error(400, "That country has too few provinces for you! You can only declare war on countries within 3 provinces more or 1 less province than you.")
            if (defender_provinces - attacker_provinces > 3):
                return error(400, "That country has too many provinces for you! You can only declare war on countries within 3 provinces more or 1 less province than you.")

            # Check if nation currently at peace with another nation
            db.execute("SELECT MAX(peace_date) FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND (attacker=(%s) OR defender=(%s))", (attacker.id, attacker.id, defender.id, defender.id))
            current_peace = db.fetchone()

            # 259200 = 3 days
            if current_peace[0]:
                if (current_peace[0]+259200) > time.time():
                    return error(403, "You can't declare war because truce has not expired!")

            start_dates = time.time()
            db.execute("INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited) VALUES (%s, %s, %s, %s, %s, %s)",(attacker.id, defender.id, war_type, war_message, start_dates, start_dates))
            # current_peace = db.fetchone()

            # War declaration notification
            db.execute("SELECT username FROM users WHERE id=(%s)", (attacker.id,))
            attacker_name = db.fetchone()[0]
            Economy.send_news(defender.id, f"{attacker_name} declared war!")

    except Exception as e:
        print("Error in declare_war:")
        print(traceback.format_exc())
        return error(400, "Could not declare war; check server logs for details")

    return redirect("/wars")

def target_data(cId):

    with get_db_cursor() as db:

        influence = get_influence(cId)
        db.execute("SELECT COUNT(id) FROM provinces WHERE userid=(%s)", (cId,))
        province_range = db.fetchone()[0]

    data = {
        "upper": influence * 2,
        "lower": influence * 0.9,
        "province_range": province_range
    }
    return data

# this should go to countries with a specific URL influence arguments set up by taking the user's influence and putting in the lower and upper bounds.
@app.route("/find_targets", methods=["GET"])
@login_required
def find_targets():
    cId = session["user_id"]
    target = target_data(cId)
    # Coerce values to safe integers/strings so query params are valid
    try:
        lower = int(round(float(target.get('lower') or 0)))
    except Exception:
        lower = 0
    try:
        upper = int(round(float(target.get('upper') or 0)))
    except Exception:
        upper = 0
    try:
        province_range = int(target.get('province_range') or 0)
    except Exception:
        province_range = 0

    url = f"/countries?lowerinf={lower}&upperinf={upper}&province_range={province_range}"
    return redirect(url)

@app.route("/defense", methods=["GET", "POST"])
@login_required
def defense():
    cId = session["user_id"]
    units = Military.get_military(cId) # returns dictionary {'soldiers': 1000}

    if request.method == "GET":

        return render_template("defense.html", units=units)

    elif request.method == "POST":

        with get_db_cursor() as db:

            defense_units = list(request.form.values())

        # defense_units = ["soldier", "tank", "apache"]

        for item in defense_units:
            if item not in Military.allUnits:
                return error(400, "Invalid unit types!")

        if len(defense_units) == 3:
            # default_defense is stored in the db: "unit1,unit2,unit3"
            defense_units = ",".join(defense_units)
            db.execute("UPDATE military SET default_defense=(%s) WHERE id=(%s)", (defense_units, cId))

        else:
            return error(400, "Invalid number of units selected!")

        # should be a back button on this page to go back to wars so dw about some infinite loop

        return redirect("/wars")
