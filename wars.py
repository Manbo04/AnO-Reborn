# FULLY MIGRATED
import random
import math
from app import app
from flask import request, render_template, session, redirect
from database import get_db_cursor
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
