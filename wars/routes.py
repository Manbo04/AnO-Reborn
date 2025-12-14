from flask import Blueprint, session, request, redirect, render_template
from helpers import login_required, get_db_cursor, error, get_flagname, check_required
# Add any other necessary imports here

# Define the wars Blueprint
wars_bp = Blueprint('wars', __name__)

# Peace offers show up here
@wars_bp.route("/peace_offers", methods=["POST", "GET"])
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
				eco = Economy(cId)
				resource_dict = eco.get_particular_resources(resources)
				print(resource_dict)
				count = 0
				for value in resource_dict.values():
					if int(amounts[count]) > value:
						return error(400, f"Can't accept peace offer because you don't have the required resources!. {int(amounts[count])} > {value}")
					print(f"Transfer: {resources[count], int(amounts[count]), author_id, cId}")
					from market import give_resource
					successful = give_resource(cId, author_id, resources[count], int(amounts[count]))
					if successful != True:
						return error(400, successful)
					count += 1
				Nation.set_peace(db, None, None, {"option": "peace_offer_id", "value": offer_id})
			else:
				return error(400, "No decision was made.")
		else:
			return error(403, "You can't accept your own offer.")

		return redirect("/peace_offers")

	return render_template(
	"peace/peace_offers.html", cId=cId,
	incoming_peace_offers=incoming, outgoing_peace_offers=outgoing,
	incoming_counter=incoming_counter, outgoing_counter=outgoing_counter)

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
		except:
			return "Invalid offer!"
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
					resources_string+=res+"," 
					amount_string+=str(amo)+"," 
			db.execute("SELECT peace_offer_id FROM wars WHERE id=(%s)", (war_id,))
			peace_offer_id = db.fetchone()[0]
			if not peace_offer_id:
				db.execute("INSERT INTO peace (author,demanded_resources,demanded_amount) VALUES ((%s),(%s),(%s))", (cId, resources_string[:-1], amount_string[:-1]))
				db.execute("SELECT CURRVAL('peace_id_seq')")
				lastrowid = db.fetchone()[0]
				db.execute("UPDATE wars SET peace_offer_id=(%s) WHERE id=(%s)", (lastrowid, war_id))
			else:
				db.execute("UPDATE peace SET author=(%s),demanded_resources=(%s),demanded_amount=(%s)", (cId, resources_string[:-1], amount_string[:-1]))
		return redirect("/peace_offers")

# War details page
@wars_bp.route("/war/<int:war_id>", methods=["GET"])
@login_required
def war_with_id(war_id):
	with get_db_cursor() as db:
		db.execute("SELECT * FROM wars WHERE id=(%s) AND peace_date IS NULL",(war_id,))
		valid_war = db.fetchone()
		if not valid_war:
			return error(404, "This war doesn't exist")
		db.execute("SELECT peace_date FROM wars WHERE id=(%s)", (war_id,))
		peace_made = db.fetchone()[0]
		if peace_made:
			return "This war already ended"
		cId = session["user_id"]
		db.execute("SELECT defender FROM wars WHERE id=(%s)", (war_id,))
		defender = db.fetchone()[0]
		db.execute("SELECT username FROM users WHERE id=(%s)", (defender,))
		defender_name = db.fetchone()[0]
		db.execute("SELECT defender_supplies,defender_morale FROM wars WHERE id=(%s)",(war_id,))
		info = db.fetchone()
		defender_info={"morale": info[1], "supplies": info[0]}
		db.execute("SELECT attacker FROM wars WHERE id=(%s)", (war_id,))
		attacker = db.fetchone()[0]
		db.execute("SELECT username FROM users WHERE id=(%s)", (attacker,))
		attacker_name = db.fetchone()[0]
		db.execute("SELECT attacker_supplies,attacker_morale FROM wars WHERE id=(%s)",(war_id,))
		info = db.fetchone()
		attacker_info={"morale": info[1], "supplies": info[0]}
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
		spyPrep = 1
		eSpyCount = 0
		eDefcon = 1
		if eSpyCount == 0:
			successChance = 100
		else:
			successChance = spyCount * spyPrep / eSpyCount / eDefcon
		attacker_flag = get_flagname(attacker)
		defender_flag = get_flagname(defender)
		return render_template("war.html",attacker_flag=attacker_flag, defender_flag=defender_flag, defender_info=defender_info, defender=defender, attacker_info=attacker_info, attacker=attacker,
		war_id=war_id, attacker_name=attacker_name, defender_name=defender_name, war_type=war_type,
		agressor_message=agressor_message, cId_type=cId_type, spyCount=spyCount, successChance=successChance, peace_to_send=enemy_id)
# ...existing code...

from units import Units
import math, random, traceback

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
		with get_db_cursor() as db:
			unitamounts = Military.get_particular_units_list(cId, attack_units.selected_units_list)
			return render_template("waramount.html", available_supplies=attack_units.available_supplies, selected_units=attack_units.selected_units_list,
				unit_range=len(unitamounts), unitamounts=unitamounts, unit_interfaces=Units.allUnitInterfaces)
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
				except:
					return error(400, "Unit amount entered was not a number")
			if not sum(selected_units.values()):
				return error(400, "Can't attack because you haven't sent any units")
			err_valid = attack_units.attach_units(selected_units, 3)
			session["attack_units"] = attack_units.__dict__
			if err_valid:
				return error(400, err_valid)
			return redirect("/warResult")
		elif len(units_name) == 1:
			amount = int(request.form.get(units_name[0]))
			if not amount:
				return error(400, "Can't attack because you haven't sent any units")
			selected_units[units_name[0]] = amount
			err_valid = attack_units.attach_units(selected_units, 1)
			session["attack_units"] = attack_units.__dict__
			if err_valid:
				return error(400, err_valid)
			return redirect("/wartarget")
		else:
			return ("everything just broke")

@wars_bp.route("/wartarget", methods=["GET", "POST"])
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
		units = {}
		return render_template("wartarget.html", units=units)
	if request.method == "POST":
		target = request.form.get("targeted_unit")
		target_amount = Military.get_particular_units_list(eId, [target])
		defender = Units(eId, {target: target_amount[0]}, selected_units_list=[target])
		attack_units = Units.rebuild_from_dict(session["attack_units"])
		special_fight_result = Military.special_fight(attack_units, defender, defender.selected_units_list[0])
		if type(special_fight_result) == str:
			return special_fight_result
		session["from_wartarget"] = special_fight_result
		return redirect("warResult")

@wars_bp.route("/warResult", methods=["GET"])
@login_required
def warResult():
	attack_unit_session = session.get("attack_units", None)
	if attack_unit_session is None:
		return redirect("/wars")
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
			defenseunits = {}
			for unit in defenselst:
				db.execute(f"SELECT {unit} FROM military WHERE id=(%s)", (eId,))
				defenseunits[unit] = db.fetchone()[0]
			defender = Units(eId, defenseunits, selected_units_list=defenselst)
			prev_defender = dict(defender.selected_units)
			prev_attacker = dict(attacker.selected_units)
			db.execute("SELECT war_type FROM wars WHERE ((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s)) AND peace_date IS NULL", (attacker.user_id, defender.user_id, defender.user_id, attacker.user_id))
			war_rows = db.fetchall()
			if not war_rows:
				return error(500, "Something went wrong")
			war_type = war_rows[-1][0]
			winner, win_condition, attack_effects = Military.fight(attacker, defender)
			if len(war_type) > 0:
				if war_type == "Raze":
					attack_effects[0] = attack_effects[0]*10
				elif war_type == "Loot":
					attack_effects[0] = attack_effects[0]*0.2
					if winner == attacker.user_id:
						lootable_resource = "gold"
						db.execute("SELECT gold FROM stats WHERE id=(%s)", (defender.user_id,))
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
						db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (loot, attacker.user_id))
				elif war_type == "Sustained":
					pass
				else: return error(400, "Something went wrong")
			else:
				return error(500, "Something went wrong")
			db.execute("SELECT id FROM provinces WHERE userId=(%s) ORDER BY id ASC", (defender.user_id,))
			province_id_fetch = db.fetchall()
			if len(province_id_fetch) > 0:
				random_province = province_id_fetch[random.randint(0, len(province_id_fetch)-1)][0]
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
			del session["from_wartarget"]
	attacker.save()
	del session["attack_units"]
	del session["enemy_id"]
	return render_template(
		"warResult.html",
		winner=winner,
		win_condition=win_condition,
		defender_result=defender_result,
		attacker_result=attacker_result)

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
			attacker = Economy(int(session.get("user_id")))
			defender = Economy(defender_id)
			if attacker.id == defender.id:
				return error(400, "Can't declare war on yourself")
			db.execute(
				"SELECT id FROM wars WHERE ((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s)) AND peace_date IS NULL",
				(attacker.id, defender.id, defender.id, attacker.id),
			)
			if db.fetchone():
				return error(400, "You're already in a war with this country!")
			attacker_provinces = attacker.get_provinces()["provinces_number"]
			defender_provinces = defender.get_provinces()["provinces_number"]
			if (attacker_provinces - defender_provinces > 1):
				return error(400, "That country has too few provinces for you! You can only declare war on countries within 3 provinces more or 1 less province than you.")
			if (defender_provinces - attacker_provinces > 3):
				return error(400, "That country has too many provinces for you! You can only declare war on countries within 3 provinces more or 1 less province than you.")
			db.execute(
				"SELECT MAX(peace_date) FROM wars WHERE ((attacker=%s AND defender=%s) OR (attacker=%s AND defender=%s))",
				(attacker.id, defender.id, defender.id, attacker.id),
			)
			current_peace = db.fetchone()
			if current_peace and current_peace[0]:
				if (current_peace[0] + 259200) > time.time():
					return error(403, "You can't declare war because truce has not expired!")
			start_dates = time.time()
			db.execute("INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited) VALUES (%s, %s, %s, %s, %s, %s)",(attacker.id, defender.id, war_type, war_message, start_dates, start_dates))
			db.execute("SELECT username FROM users WHERE id=(%s)", (attacker.id,))
			attacker_name = db.fetchone()[0]
			Economy.send_news(defender.id, f"{attacker_name} declared war!")
	except Exception as e:
		print("Error in declare_war:")
		print(traceback.format_exc())
		return error(400, "Could not declare war; check server logs for details")
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
			db.execute("UPDATE military SET default_defense=(%s) WHERE id=(%s)", (defense_units, cId))
		else:
			return error(400, "Invalid number of units selected!")
		return redirect("/wars")
from attack_scripts import Nation, Military, Economy
import time
from .service import update_supply

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
				db.execute("SELECT id, defender, attacker FROM wars WHERE (attacker=%s OR defender=%s) AND peace_date IS NULL", (cId, cId))
				war_attacker_defender_ids = db.fetchall()
				war_info = {}
				for war_id,defender,attacker in war_attacker_defender_ids:
					update_supply(war_id)
					attacker_info = {}
					defender_info = {}
					db.execute("SELECT username FROM users WHERE id=%s", (attacker,))
					att_name = db.fetchone()[0]
					attacker_info["name"] = att_name
					attacker_info["id"] = attacker
					db.execute("SELECT attacker_morale, attacker_supplies FROM wars WHERE id=%s", (war_id,))
					att_morale_and_supplies = db.fetchone()
					attacker_info["morale"] = att_morale_and_supplies[0]
					attacker_info["supplies"] = att_morale_and_supplies[1]
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


@wars_bp.route("/find_targets", methods=["GET", "POST"])
@login_required
def find_targets():
	cId = session["user_id"]
	if request.method == "GET":
		return render_template("find_targets.html")
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
