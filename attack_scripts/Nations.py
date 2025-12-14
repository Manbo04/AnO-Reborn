import random
import psycopg2
import os, time
import math
from dotenv import load_dotenv

load_dotenv()


def calculate_bonuses(attack_effects, enemy_object, target):  # int, Units, str -> int
    # Calculate the percentage of total units will be affected
    defending_unit_amount = enemy_object.selected_units[target]

    # sum of units amount
    enemy_units_total_amount = sum(enemy_object.selected_units.values())

    # the affected percentage from sum of units
    unit_of_army = (defending_unit_amount * 100) / (enemy_units_total_amount + 1)

    # the bonus calculated based on affected percentage
    affected_bonus = attack_effects[1] * (unit_of_army / 100)

    # divide affected_bonus to make bonus effect less relevant
    attack_effects = affected_bonus / 100

    # DEBUGGING:
    # print("UOA", unit_of_army, attacker_unit, target, self.user_id, affected_bonus)
    return attack_effects


class Economy:
    resources = [
        "rations",
        "oil",
        "coal",
        "uranium",
        "bauxite",
        "iron",
        "lead",
        "copper",
        "lumber",
        "components",
        "steel",
        "consumer_goods",
        "aluminium",
        "gasoline",
        "ammunition",
    ]

    def __init__(self, nationID):
        # Keep both names for compatibility: some codebases use 'nationID' while others use 'id'
        self.nationID = nationID
        self.id = nationID
        # Compose a Nation instance so Economy exposes nation-level helper methods
        try:
            self.nation = Nation(nationID)
        except NameError:
            # If Nation is not yet defined at import time, delay composition until needed
            self.nation = None

    def get_economy(self):
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        db = connection.cursor()

        # TODO fix this when the databases changes and update to include all resources
        db.execute("SELECT gold FROM stats WHERE id=(%s)", (self.nationID,))
        self.gold = db.fetchone()[0]

    def get_particular_resources(
        self, resources
    ):  # works, i think (?) returns players resources
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        db = connection.cursor()

        resource_dict = {}

        print(resources)

        try:
            for resource in resources:
                if resource == "money":
                    db.execute("SELECT gold FROM stats WHERE id=(%s)", (self.nationID,))
                    resource_dict[resource] = db.fetchone()[0]
                else:
                    query = f"SELECT {resource}" + " FROM resources WHERE id=(%s)"
                    db.execute(query, (self.nationID,))
                    resource_dict[resource] = db.fetchone()[0]
        except Exception as e:
            # TODO ERROR HANDLER OR RETURN THE ERROR AS A VAlUE
            print(e)
            print("INVALID RESOURCE NAME")
            # Return an empty dict to avoid downstream attribute errors and allow
            # the caller to handle invalid resources explicitly.
            return {}

        print(resource_dict)
        return resource_dict

    def __getattr__(self, name):
        # Delegate missing attributes to the composed Nation object if available
        if name in ("nation", "id", "nationID"):
            raise AttributeError(name)
        if self.nation is None:
            # Lazy initialize Nation if it wasn't available at init time
            try:
                self.nation = Nation(self.id)
            except Exception:
                raise AttributeError(name)
        return getattr(self.nation, name)

    @staticmethod
    def send_news(destination_id: int, message: str):
        # Backwards-compatible wrapper to forward to Nation.send_news
        try:
            Nation.send_news(destination_id, message)
        except NameError:
            # If Nation isn't available, log or raise a clear error
            raise

    def grant_resources(self, resource, amount):
        # TODO find a way to get the database to work on relative directories
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        db = connection.cursor()

        db.execute(
            "UPDATE stats SET (%s) = (%s) WHERE id(%s)",
            (resource, amount, self.nationID),
        )

        connection.commit()

    # IMPORTANT: the amount is not validated in this method, so you should provide a valid value
    def transfer_resources(self, resource, amount, destinationID):
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        db = connection.cursor()

        if resource not in self.resources:
            return "Invalid resource"

        @staticmethod
        def morale_change(column, win_type, winner, loser):
            # Updated morale change: accept a computed morale delta passed through the caller
            # The caller should compute a morale delta based on units involved. We still keep
            # the win_type -> human-readable win_condition mapping, but morale is adjusted
            # by the provided delta to allow per-unit impacts.
            connection = psycopg2.connect(
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT"),
            )

            db = connection.cursor()

            db.execute(
                "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
                (winner.user_id, loser.user_id, winner.user_id, loser.user_id),
            )
            war_id = db.fetchall()[-1][0]

            war_column_stat = f"SELECT {column} FROM wars " + "WHERE id=(%s)"
            db.execute(war_column_stat, (war_id,))
            morale = db.fetchone()[0]

            # Determine win_condition label from win_type (keeps semantics for other logic)
            if win_type >= 3:
                win_condition = "annihilation"
            elif win_type >= 2:
                win_condition = "definite victory"
            else:
                win_condition = "close victory"

            # If the caller attached a morale_delta attribute on the loser object (preferred),
            # use it. Otherwise fall back to a conservative fixed decrease based on win_type.
            morale_delta = getattr(loser, "_computed_morale_delta", None)
            if morale_delta is None:
                # conservative fallback (small penalties)
                if win_type >= 3:
                    morale_delta = 15
                elif win_type >= 2:
                    morale_delta = 10
                else:
                    morale_delta = 5

            # Apply morale delta and persist
            morale = morale - int(morale_delta)

            # Win the war if morale drops to zero or below
            if morale <= 0:
                Nation.set_peace(db, connection, war_id)
                eco = Economy(winner.user_id)

                for resource in Economy.resources:
                    resource_sel_stat = f"SELECT {resource} FROM resources WHERE id=%s"
                    db.execute(resource_sel_stat, (loser.user_id,))
                    resource_amount = db.fetchone()[0]
                    # transfer 20% of resource on hand
                    eco.transfer_resources(
                        resource, resource_amount * (1 / 5), winner.user_id
                    )

            db.execute(f"UPDATE wars SET {column}=(%s) WHERE id=(%s)", (morale, war_id))

            connection.commit()
            connection.close()

            return win_condition


class Nation:
    def __init__(
        self, nationID, military=None, economy=None, provinces=None, current_wars=None
    ):
        self.id = nationID  # integer ID

        self.military = military
        self.economy = economy
        self.provinces = provinces

        self.current_wars = current_wars
        self.wins = 0
        self.losses = 0

    def declare_war(self, target_nation):
        pass

    # Function for sending posts to nation's news page
    @staticmethod
    def send_news(destination_id: int, message: str):
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        db = connection.cursor()
        db.execute(
            "INSERT INTO news(destination_id, message) VALUES (%s, %s)",
            (destination_id, message),
        )
        connection.commit()
        connection.close()

    def get_provinces(self):
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()
        if self.provinces is None:
            self.provinces = {"provinces_number": 0, "province_stats": {}}
            db.execute(
                "SELECT COUNT(provinceName) FROM provinces WHERE userId=%s", (self.id,)
            )
            provinces_number = db.fetchone()[0]
            self.provinces["provinces_number"] = provinces_number

            if provinces_number > 0:
                db.execute("SELECT * FROM provinces WHERE userId=(%s)", (self.id,))
                provinces = db.fetchall()
                for province in provinces:
                    self.provinces["province_stats"][province[1]] = {
                        "userId": province[0],
                        "provinceName": province[2],
                        "cityCount": province[3],
                        "land": province[4],
                        "population": province[5],
                        "energy": province[6],
                        "pollution": province[7],
                    }

        return self.provinces

    @staticmethod
    def get_current_wars(id):
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()
        db.execute(
            "SELECT id FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND peace_date IS NULL",
            (
                id,
                id,
            ),
        )
        id_list = db.fetchall()

        # # determine wheter the user is the aggressor or the defender
        # current_wars_result = []
        # for war_id in id_list:
        # db.execute("SELECT 1 FROM wars WHERE id=(%s) AND attacker=(%s)", (war_id[0], id))
        #     is_attacker = db.fetchone()
        #
        #     if is_attacker:
        #         war_id.append("attacker")
        #     else:
        #         war_id.append("defender")

        return id_list

    # Get everything from proInfra table which is in the "public works" category
    @classmethod
    def get_public_works(self, province_id):
        from database import get_db_cursor
        from psycopg2.extras import RealDictCursor

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            public_works_string = ",".join(self.public_works)

            infra_sel_stat = (
                f"SELECT {public_works_string} FROM proInfra " + "WHERE id=%s"
            )
            db.execute(infra_sel_stat, (province_id,))
            result = db.fetchone()

            if not result:
                return {pw: 0 for pw in self.public_works}

            return dict(result)

    # set the peace_date in wars table for a particular war
    @staticmethod
    def set_peace(db, connection, war_id=None, options=None):
        print("Setting war peace")
        print(war_id, options)
        if war_id is not None:
            db.execute(
                "UPDATE wars SET peace_date=(%s) WHERE id=(%s)", (time.time(), war_id)
            )
        else:
            option = options["option"]
            query = "UPDATE wars SET peace_date=(%s)" + f"WHERE {option}" + "=(%s)"
            db.execute(query, (time.time(), options["value"]))

        connection.commit()

    # Get the list of owned upgrades like supply amount increaser from 200 to 210, etc.
    @classmethod
    def get_upgrades(cls, upgrade_type, user_id):
        from database import get_db_cursor
        from psycopg2.extras import RealDictCursor

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            upgrades = {}

            if upgrade_type == "supplies":
                upgrade_fields = list(cls.supply_related_upgrades.keys())
                if upgrade_fields:
                    upgrade_query = f"SELECT {', '.join(upgrade_fields)} FROM upgrades WHERE user_id=%s"
                    db.execute(upgrade_query, (user_id,))
                    result = db.fetchone()
                    if result:
                        upgrades = dict(result)

            # returns the bonus given by the upgrade
            return upgrades

        # The minimal set_peace static method is already implemented as a method
        # of the Nation class above; no additional placeholder class is required.


class Military(Nation):
    allUnits = [
        "soldiers",
        "tanks",
        "artillery",
        "bombers",
        "fighters",
        "apaches",
        "destroyers",
        "cruisers",
        "submarines",
        "spies",
        "icbms",
        "nukes",
    ]

    # description of the function: deal damage to random buildings based on particular_infra
    # particular_infra parameter example: for public_works -> {"libraries": 3, "hospitals": x, etc.}
    # note: also could use this for population damage when attack happens
    @staticmethod
    def infrastructure_damage(damage, particular_infra, province_id):
        from database import get_db_connection

        available_buildings = []

        with get_db_connection() as connection:
            db = connection.cursor()

            for building in particular_infra.keys():
                amount = particular_infra[building]
                if amount > 0:
                    # If there are multiple of the same building add those multiple times
                    for i in range(0, amount):
                        available_buildings.append(building)

            # Damage logic (might include population damage)
            # health is the damage required to destroy a building
            health = 1500

            damage_effects = {}

            while damage > 0:
                if not len(available_buildings):
                    break

                max_range = len(available_buildings) - 1
                random_building = random.randint(0, max_range)

                target = available_buildings[random_building]

                # destroy target
                if (damage - health) >= 0:
                    particular_infra[target] -= 1

                    infra_update_stat = (
                        f"UPDATE proInfra SET {target}" + "=%s WHERE id=(%s)"
                    )
                    db.execute(
                        infra_update_stat, (particular_infra[target], province_id)
                    )

                    available_buildings.pop(random_building)

                    if damage_effects.get(target, 0):
                        damage_effects[target][1] += 1
                    else:
                        damage_effects[target] = ["destroyed", 1]

                # NOTE: possible feature, when a building not destroyed but could be unusable (the reparation cost lower than rebuying it)
                else:
                    max_damage = abs(damage - health)

                damage -= health

            # will return: how many buildings are damaged or destroyed
            # format: {building_name: ["effect name", affected_amount]}
            return damage_effects

    # Returns the morale either for the attacker or the defender, and with the war_id
    @staticmethod
    def get_morale(column, attacker, defender):
        from database import get_db_cursor

        with get_db_cursor() as db:
            db.execute(
                f"SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
                (
                    attacker.user_id,
                    defender.user_id,
                    attacker.user_id,
                    defender.user_id,
                ),
            )
            war_id = db.fetchall()[-1][0]
            db.execute(f"SELECT {column} FROM wars WHERE id=(%s)", (war_id,))
            morale = db.fetchone()[0]
            return (war_id, morale)

    # Reparation tax
    # parameter description:
    # winners: [id1,id2...idn]
    # losers: [id1,id2...idn]
    @staticmethod

    # NOTE: currently only one winner is supported winners = [id]
    def reparation_tax(winners, losers):
        # def reparation_tax(winner_side, loser_side):

        # get remaining morale for winner (only one supported current_wars)
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        db = connection.cursor()

        # db.execute(
        # "SELECT IF attacker_morale==0 THEN defender_morale ELSE attacker_morale FROM (SELECT defender_morale,attacker_morale FROM wars WHERE (attacker=%s OR defender=%s) AND (attacker=%s OR defender=%s)) L",
        # (winners[0], winners[0], losers[0], losers[0]))

        db.execute(
            "SELECT CASE WHEN attacker_morale=0 THEN defender_morale\n ELSE attacker_morale\n END\n FROM wars WHERE (attacker=%s OR defender=%s) AND (attacker=%s OR defender=%s)",
            (winners[0], winners[0], losers[0], losers[0]),
        )
        winner_remaining_morale = db.fetchone()[0]

        # Calculate reparation tax based on remaining morale
        # if winner_remaining_morale_effect
        tax_rate = 0.2 * winner_remaining_morale

        print(
            db.execute(
                "INSERT INTO reparation_tax (winner,loser,percentage,until) VALUES (%s,%s,%s,%s)",
                (winners[0], losers[0], tax_rate, time.time() + 5000),
            )
        )
        print(winner_remaining_morale, tax_rate)

        connection.commit()
        connection.close()

    # Update the morale and give back the win type name
    @staticmethod
    # def morale_change(war_id, morale, column, win_type, winner, loser):
    def morale_change(column, win_type, winner, loser):
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()

        db.execute(
            "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
            (winner.user_id, loser.user_id, winner.user_id, loser.user_id),
        )
        war_id = db.fetchall()[-1][0]

        war_column_stat = f"SELECT {column} FROM wars " + "WHERE id=(%s)"
        db.execute(war_column_stat, (war_id,))
        morale = db.fetchone()[0]

        # annihilation
        # 50 morale change
        # Morale change tiers (reduced severity so wars require sustained action)
        # annihilation: large defeat
        if win_type >= 3:
            morale = morale - 15
            win_condition = "annihilation"

        # definite victory: moderate defeat
        elif win_type >= 2:
            morale = morale - 10
            win_condition = "definite victory"

        # close victory: minor defeat
        else:
            morale = morale - 5
            win_condition = "close victory"

        # Win the war
        if morale <= 0:
            # TODO: need a method for give the winner the prize for winning the war (this is not negotiation because the enemy completly lost the war since morale is 0)
            Nation.set_peace(db, connection, war_id)
            eco = Economy(winner.user_id)

            for resource in Economy.resources:
                resource_sel_stat = f"SELECT {resource} FROM resources WHERE id=%s"
                db.execute(resource_sel_stat, (loser.user_id,))
                resource_amount = db.fetchone()[0]

                # transfer 20% of resource on hand (TODO: implement if and alliance won how to give it)
                eco.transfer_resources(
                    resource, resource_amount * (1 / 5), winner.user_id
                )

            # print("THE WAR IS OVER")

        db.execute(f"UPDATE wars SET {column}=(%s) WHERE id=(%s)", (morale, war_id))

        connection.commit()
        connection.close()

        return win_condition

    @staticmethod
    def special_fight(attacker, defender, target):  # Units, Units, int -> str, None
        target_amount = defender.get_military(defender.user_id).get(target, None)

        if target_amount is not None:
            special_unit = attacker.selected_units_list[0]
            attack_effects = attacker.attack(special_unit, target)

            # Surely destroy this percentage of the targeted units
            # NOTE: devided attack_effects[0] by 20 otherwise special units damage are too overpowered maybe give it other value

            # THIS COMMENTED LINE IS TOO OP BECAUSE THE target_amount
            # min_destruction = target_amount*(1/5)*(attack_effects[0]/(1+attack_effects[1])*attacker.selected_units[special_unit])
            min_destruction = (
                attack_effects[0]
                / (1 + attack_effects[1])
                * attacker.selected_units[special_unit]
            )

            # Random bonus on unit destruction
            destruction_rate = random.uniform(0.3, 0.5)
            final_destruction = destruction_rate * min_destruction

            # print(final_destruction, "final_destruction")

            before_casulaties = list(dict(defender.selected_units).values())[0]
            defender.casualties(target, final_destruction)

            # infrastructure damage
            connection = psycopg2.connect(
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT"),
            )

            db = connection.cursor()

            db.execute(
                "SELECT id FROM provinces WHERE userId=(%s) ORDER BY id ASC",
                (defender.user_id,),
            )
            province_id_fetch = db.fetchall()

            # decrease special unit amount after attack
            # TODO: check if too much special_unit amount is selected
            # TODO: decreate only the selected amount when attacker (ex. db 100 soldiers, attack with 20, don't decreate from 100)
            db.execute(
                f"SELECT {special_unit} FROM military WHERE id=(%s)",
                (attacker.user_id,),
            )
            special_unit_fetch = db.fetchone()[0]

            db.execute(
                f"UPDATE military SET {special_unit}=(%s) WHERE id=(%s)",
                (
                    special_unit_fetch - attacker.selected_units[special_unit],
                    attacker.user_id,
                ),
            )

            connection.commit()

            # NOTE: put this on the warResult route and use it for both the special and regular attack
            # TODO: NEED PROPER ERROR HANDLING FOR THIS INFRA DAMAGE ex. when user doesn't have province the can't damage it (it throws error)
            if len(province_id_fetch) > 0:
                random_province = province_id_fetch[
                    random.randint(0, len(province_id_fetch) - 1)
                ][0]

                # If nuke damage public_works
                public_works = Nation.get_public_works(random_province)
                infra_damage_effects = Military.infrastructure_damage(
                    attack_effects[0], public_works, random_province
                )
            else:
                infra_damage_effects = 0

            # {target: losed_amount} <- the target and the destroyed amount
            return (
                {
                    target: before_casulaties
                    - list(dict(defender.selected_units).values())[0]
                },
                infra_damage_effects,
            )

        else:
            return "Invalid target is selected!"

    # NOTICE: in the future we could use this as an instance method unstead of static method
    """
    if your score is higher by 3x, annihilation,
    if your score is higher by 2x, definite victory
    if your score is higher, close victory,
    if your score is lower, close defeat, 0 damage,
    if your score is lower by 2x, massive defeat, 0 damage

    from annihilation (resource, field, city, depth, blockade, air):
    soldiers: resource control
    tanks: field control and city control
    artillery: field control
    destroyers: naval blockade
    cruisers: naval blockade
    submarines: depth control
    bombers: field control
    apaches: city control
    fighter jets: air control

    counters | countered by
    soldiers beat artillery, apaches | tanks, bombers
    tanks beat soldiers | artilllery, bombers
    artillery beat tanks | soldiers
    destroyers beat submarines | cruisers, bombers
    cruisers beat destroyers, fighters, apaches | submarines
    submarines beat cruisers | destroyers, bombers
    bombers beat soldiers, tanks, destroyers, submarines | fighters, apaches
    apaches beat soldiers, tanks, bombers, fighters | soldiers
    fighters beat bombers | apaches, cruisers

    resource control: soldiers can now loot enemy munitions (minimum between 1 per 100 soldiers and 50% of their total munitions)
    field control: soldiers gain 2x power
    city control: 2x morale damage
    depth control: missile defenses go from 50% to 20% and nuke defenses go from  35% to 10%
    blockade: enemy can no longer trade
    air control: enemy bomber power reduced by 60%"""

    @staticmethod
    # attacker, defender means the attacker and the defender user JUST in this particular fight not in the whole war
    def fight(attacker, defender):  # Units, Units -> int
        # IMPORTANT: Here you can change the values for the fight chances, bonuses and even can controll casualties (in this whole funciton)
        # If you want to change the bonuses given by a particular unit then go to `units.py` and you can find those in the classes
        attacker_roll = random.uniform(1, 5)
        attacker_chance = 0
        attacker_unit_amount_bonuses = 0
        attacker_bonus = 0

        defender_roll = random.uniform(1, 5)
        defender_chance = 0
        defender_unit_amount_bonuses = 0
        defender_bonus = 0

        dealt_infra_damage = 0

        for attacker_unit, defender_unit in zip(
            attacker.selected_units_list, defender.selected_units_list
        ):
            # Unit amount chance - this way still get bonuses even if no counter unit_type
            defender_unit_amount_bonuses += (
                defender.selected_units[defender_unit] / 150
            )  # is dict
            attacker_unit_amount_bonuses += attacker.selected_units[attacker_unit] / 150

            # Compare attacker agains defender
            for unit in defender.selected_units_list:
                attack_effects = attacker.attack(attacker_unit, unit)
                attacker_bonus += calculate_bonuses(attack_effects, defender, unit)
                # used to be += attacker.attack(attacker_unit, unit, defender)[1]

                dealt_infra_damage += attack_effects[0]

            # Compare defender against attacker
            for unit in attacker.selected_units_list:
                defender_bonus += calculate_bonuses(
                    defender.attack(defender_unit, unit), attacker, unit
                )

        # used to be: attacker_chance += attacker_roll+attacker_unit_amount_bonuses+attacker_bonus
        #             defender_chance += defender_roll+defender_unit_amount_bonuses+defender_bonus
        attacker_chance += attacker_roll + attacker_unit_amount_bonuses + attacker_bonus
        defender_chance += defender_roll + defender_unit_amount_bonuses + defender_bonus

        # # If there are not attackers or defenders
        if defender_unit_amount_bonuses == 0:
            defender_chance = 0
        elif attacker_unit_amount_bonuses == 0:
            attacker_chance = 0

        # print(attacker_chance, defender_chance)

        # Determine the winner
        if defender_chance >= attacker_chance:
            winner = defender
            loser = attacker
            if attacker_unit_amount_bonuses == 0:
                winner_casulties = 0
                win_type = 5
            else:
                win_type = defender_chance / attacker_chance
                winner_casulties = (1 + attacker_chance) / defender_chance
        else:
            winner = attacker
            loser = defender
            if defender_unit_amount_bonuses == 0:
                winner_casulties = 0
                win_type = 5
            else:
                win_type = attacker_chance / defender_chance
                winner_casulties = (1 + defender_chance) / attacker_chance

        # Get the absolute side (absolute attacker and defender) in the war for determining the loser's morale column name to decrease

        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()

        db.execute(
            "SELECT attacker FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND peace_date IS NULL",
            (winner.user_id, winner.user_id),
        )
        abs_attacker = db.fetchone()[0]

        if winner.user_id == abs_attacker:
            # morale column of the loser
            morale_column = "defender_morale"
        else:
            # morale column of the loser
            morale_column = "attacker_morale"

        # Effects based on win_type (idk: destroy buildings or something)
        # loser_casulties = win_type so win_type also is the loser's casulties

        war_id, morale = Military.get_morale(morale_column, attacker, defender)

        # print("MORALE COLUMN", morale_column, "WINNER FROM FIGHT MEHTOD", winner.user_id)
        # print("ATTC", attacker.user_id, defender.user_id)

        # Compute a per-unit morale delta based on the loser's unit composition and the win_type.
        # We attach the computed delta to the loser object so `morale_change` can consume it.
        unit_morale_weights = {
            "soldiers": 0.0002,
            "artillery": 0.01,
            "tanks": 0.02,
            "bombers": 0.03,
            "fighters": 0.03,
            "apaches": 0.025,
            "destroyers": 0.03,
            "cruisers": 0.04,
            "submarines": 0.04,
            "spies": 0.0,
            "icbms": 5,
            "nukes": 12,
        }

        # Compute attacker and defender strengths using the unit morale weights
        attacker_strength = 0.0
        defender_strength = 0.0
        try:
            for unit_name, count in attacker.selected_units.items():
                attacker_strength += (count or 0) * unit_morale_weights.get(
                    unit_name, 0.01
                )
            for unit_name, count in defender.selected_units.items():
                defender_strength += (count or 0) * unit_morale_weights.get(
                    unit_name, 0.01
                )
        except Exception:
            # fallback small strengths to avoid zero division
            attacker_strength = max(attacker_strength, 1.0)
            defender_strength = max(defender_strength, 1.0)

        # Advantage factor ranges (0..1). If attacker and defender are equal, advantage ~ 0.5
        advantage = attacker_strength / (attacker_strength + defender_strength + 1e-9)

        # If defender actually won, invert advantage for purposes of computing loser impact
        if winner is defender:
            advantage_factor = 1.0 - advantage
        else:
            advantage_factor = advantage

        # Base value derived from the loser's own units (their potential to suffer morale loss)
        base_loser_value = 0.0
        try:
            for unit_name, count in loser.selected_units.items():
                base_loser_value += (count or 0) * unit_morale_weights.get(
                    unit_name, 0.01
                )
        except Exception:
            base_loser_value = 1.0

        # Compute the morale delta proportional to base_loser_value, advantage_factor and win_type.
        # Scale down to keep deltas reasonable; cap to prevent instant annihilation.
        computed_morale_delta = int(
            round(base_loser_value * advantage_factor * win_type * 0.1)
        )
        computed_morale_delta = max(1, computed_morale_delta)
        computed_morale_delta = min(200, computed_morale_delta)

        # attach to loser for morale_change to pick up
        setattr(loser, "_computed_morale_delta", computed_morale_delta)

        win_condition = Military.morale_change(morale_column, win_type, winner, loser)

        # Maybe use the damage property also in unit loss
        # TODO: make unit loss more precise
        for winner_unit, loser_unit in zip(
            winner.selected_units_list, loser.selected_units_list
        ):
            w_casualties = winner_casulties * random.uniform(2, 10) * 2
            l_casualties = win_type * random.uniform(2, 10.5) * 2

            # print("w_casualties", w_casualties)
            # print("l_casualties", l_casualties)
            winner.casualties(winner_unit, w_casualties)
            loser.casualties(loser_unit, l_casualties)

        # infrastructure damage
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        # db = connection.cursor()
        # db.execute("SELECT id FROM provinces WHERE userId=(%s) ORDER BY id ASC", (defender.user_id,))
        # province_id_fetch = db.fetchall()
        # random_province = province_id_fetch[random.randint(0, len(province_id_fetch)-1)][0]
        #
        # # Currently units only affect public works
        # public_works = Nation.get_public_works(random_province)
        #
        # # TODO: enforce war type like raze,etc.
        # # example for the above line: if war_type is raze then attack_effects[0]*10
        # infra_damage_effects = Military.infrastructure_damage(attack_effects[0], public_works, random_province)

        # return (winner.user_id, return_winner_cas, return_loser_cas)
        return (winner.user_id, win_condition, [dealt_infra_damage, 0])

    # select only needed units instead of all
    # particular_units must be a list of string unit names
    @staticmethod
    def get_particular_units_list(cId, particular_units):  # int, list -> list
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()

        # this data come in the format [(cId, soldiers, artillery, tanks, bombers, fighters, apaches, spies, icbms, nukes, destroyer, cruisers, submarines)]
        db.execute("SELECT * FROM military WHERE id=%s", (cId,))
        allAmounts = db.fetchall()

        # get the unit amounts based on the selected_units
        unit_to_amount_dict = {}

        # TODO: maybe use the self.allUnits because it looks like repetative code
        cidunits = [
            "cId",
            "soldiers",
            "artillery",
            "tanks",
            "bombers",
            "fighters",
            "apaches",
            "spies",
            "icbms",
            "nukes",
            "destroyers",
            "cruisers",
            "submarines",
        ]
        for count, item in enumerate(cidunits):
            unit_to_amount_dict[item] = allAmounts[0][count]

        # make a dictionary with 3 keys, listed in the particular_units list
        unit_lst = []
        for unit in particular_units:
            unit_lst.append(unit_to_amount_dict[unit])

        connection.close()
        return unit_lst  # this is a list of the format [100, 50, 50]

    @staticmethod
    def get_military(cId):  # int -> dict
        from database import get_db_cursor
        from psycopg2.extras import RealDictCursor

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            db.execute(
                """SELECT tanks, soldiers, artillery, bombers, fighters, apaches,
                   destroyers, cruisers, submarines
                   FROM military WHERE id=%s""",
                (cId,),
            )
            result = db.fetchone()
            return dict(result) if result else {}

    @staticmethod
    def get_limits(cId):  # int -> dict
        from database import get_db_cursor

        with get_db_cursor() as db:
            # Use aggregated query instead of loop
            db.execute(
                """SELECT
                    COALESCE(SUM(pi.army_bases), 0) as army_bases,
                    COALESCE(SUM(pi.harbours), 0) as harbours,
                    COALESCE(SUM(pi.aerodomes), 0) as aerodomes,
                    COALESCE(SUM(pi.admin_buildings), 0) as admin_buildings,
                    COALESCE(SUM(pi.silos), 0) as silos
                FROM proinfra pi
                INNER JOIN provinces p ON pi.id = p.id
                WHERE p.userID=%s""",
                (cId,),
            )
            result = db.fetchone()
            army_bases, harbours, aerodomes, admin_buildings, silos = result

            # these numbers determine the upper limit of how many of each military unit can be built per day
            db.execute("SELECT manpower FROM military WHERE id=(%s)", (cId,))
            manpower = db.fetchone()[0]

            # fetch upgrade flag while cursor is open
            db.execute("SELECT increasedfunding FROM upgrades WHERE user_id=%s", (cId,))
            increased_funding = db.fetchone()[0]

        military = Military.get_military(cId)

        # TODO: maybe clear this mess a bit up
        # Land units
        soldiers = max(0, army_bases * 100 - military["soldiers"])
        tanks = max(0, army_bases * 8 - military["tanks"])
        artillery = max(0, army_bases * 8 - military["artillery"])

        # Air units
        air_units = military["fighters"] + military["bombers"] + military["apaches"]
        air_limit = max(0, aerodomes * 5 - air_units)
        bombers = air_limit
        fighters = air_limit
        apaches = air_limit

        # Naval units
        naval_units = military["submarines"] + military["destroyers"]
        naval_limit = max(0, harbours * 3 - naval_units)
        submarines = naval_limit
        destroyers = naval_limit

        cruisers = max(0, harbours * 2 - military["cruisers"])

        # Special
        special_units = Military.get_special(cId)
        spies = max(0, admin_buildings * 1 - special_units["spies"])
        icbms = max(0, silos + 1 - special_units["icbms"])
        nukes = max(0, silos - special_units["nukes"])

        if increased_funding:
            spies *= 1.4

        return {
            "soldiers": soldiers,
            "tanks": tanks,
            "artillery": artillery,
            "bombers": bombers,
            "fighters": fighters,
            "apaches": apaches,
            "destroyers": destroyers,
            "cruisers": cruisers,
            "submarines": submarines,
            "spies": spies,
            "icbms": icbms,
            "nukes": nukes,
        }

    @staticmethod
    def get_special(cId):  # int -> dict
        from database import get_db_cursor
        from psycopg2.extras import RealDictCursor

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            db.execute("SELECT spies, ICBMs, nukes FROM military WHERE id=%s", (cId,))
            result = db.fetchone()
            return dict(result) if result else {"spies": 0, "icbms": 0, "nukes": 0}

    # Check and set default_defense in nation table
    def set_defense(self, defense_string):  # str -> None
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()
        defense_list = defense_string.split(",")
        if len(defense_units) == 3:
            # default_defense is stored in the db: 'unit1,unit2,unit3'
            defense_units = ",".join(defense_units)

            db.execute(
                "UPDATE nation SET default_defense=(%s) WHERE nation_id=(%s)",
                (defense_units, nation[1]),
            )

            connection.commit()
        else:
            # user should never reach here, msg for beta testers
            return "Invalid number of units given to set_defense, report to admin"


# DEBUGGING:
if __name__ == "__main__":
    # p = Nation.get_public_works(14)
    # Military.infrastructure_damage(20, p)
    # print(p)

    # m = Military(2)
    # m.reparation_tax([2], [1])

    Nation.send_news(2, "You won the 100 years war!")
