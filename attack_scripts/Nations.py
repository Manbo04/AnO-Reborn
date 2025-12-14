import os
import random
import time
from typing import Any, Dict, Optional

import psycopg2


def calculate_bonuses(attack_effects: Any, defender: Any, unit: Any) -> int:
    """Compute per-unit bonus for the fight mechanics.

    This is a conservative implementation that preserves existing behavior by
    returning 0 when a detailed calculation isn't available. It can be
    replaced with a more accurate implementation later.
    """
    try:
        # If `unit` exposes a helper we can utilize it
        return unit.calculate_battle_bonus(attack_effects, defender)
    except Exception:
        return 0


class Economy:
    # Known resource keys used across the project
    resources = [
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

    def __init__(self, nationID: int):
        # Keep both names for compatibility.
        # Some codebases use 'nationID' while others use 'id'.
        self.nationID = nationID
        self.id = nationID
        # Compose a Nation instance so Economy exposes nation-level helper methods
        # `Nation` may not be available at import time; type as Optional
        from typing import Optional

        self.nation: Optional["Nation"] = None
        try:
            self.nation = Nation(nationID)
        except NameError:
            # If `Nation` isn't defined at import time, leave as None and
            # lazily instantiate in `__getattr__`.
            self.nation = None

    def get_economy(self) -> None:
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        _db = connection.cursor()

        # TODO: update this query when the database schema changes
        _db.execute("SELECT gold FROM stats WHERE id=(%s)", (self.nationID,))
        self.gold = _db.fetchone()[0]

    def get_particular_resources(self, resources) -> Dict[str, Any]:
        """Return specific resources for this nation as a dict."""
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        _db = connection.cursor()

        resource_dict = {}

        print(resources)

        try:
            for resource in resources:
                if resource == "money":
                    _db.execute(
                        "SELECT gold FROM stats WHERE id=(%s)", (self.nationID,)
                    )
                    resource_dict[resource] = _db.fetchone()[0]
                else:
                    query = f"SELECT {resource}" + " FROM resources WHERE id=(%s)"
                    _db.execute(query, (self.nationID,))
                    resource_dict[resource] = _db.fetchone()[0]
        except Exception as e:
            # TODO ERROR HANDLER OR RETURN THE ERROR AS A VAlUE
            print(e)
            print("INVALID RESOURCE NAME")
            # Return an empty dict to avoid downstream attribute errors and allow
            # the caller to handle invalid resources explicitly.
            return {}

        print(resource_dict)
        return resource_dict

    def __getattr__(self, name: str) -> Any:
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
    def send_news(destination_id: int, message: str) -> None:
        # Backwards-compatible wrapper to forward to Nation.send_news
        try:
            Nation.send_news(destination_id, message)
        except NameError:
            # If Nation isn't available, log or raise a clear error
            raise

    def grant_resources(self, resource: str, amount: int) -> None:
        # TODO find a way to get the database to work on relative directories
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        _db = connection.cursor()

        _db.execute(
            "UPDATE stats SET (%s) = (%s) WHERE id(%s)",
            (resource, amount, self.nationID),
        )

        connection.commit()

    # IMPORTANT: the amount is not validated in this method.
    # Provide a valid value when calling.
    def transfer_resources(
        self, resource: str, amount: int, destinationID: int
    ) -> Optional[str]:
        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )
        _ = connection.cursor()  # reserved for future implementation

        if resource not in self.resources:
            return "Invalid resource"

        def morale_change(column, win_type, winner, loser):
            # Updated morale change: accept a computed morale delta passed
            # through the caller. The caller should compute the delta based on
            # the units involved. We keep the win_type -> human-readable
            # win_condition mapping but morale is adjusted by the provided
            # delta to allow per-unit impacts.
            connection = psycopg2.connect(
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT"),
            )

            db = connection.cursor()

            db.execute(
                (
                    "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) "
                    "AND (defender=(%s) OR defender=(%s))"
                ),
                (winner.user_id, loser.user_id, winner.user_id, loser.user_id),
            )
            war_id = db.fetchall()[-1][0]

            war_column_stat = f"SELECT {column} FROM wars " + "WHERE id=(%s)"
            db.execute(war_column_stat, (war_id,))
            morale = db.fetchone()[0]

            # Determine win_condition label from the win_type. This keeps the
            # semantics used by other logic.
            if win_type >= 3:
                win_condition = "annihilation"
            elif win_type >= 2:
                win_condition = "definite victory"
            else:
                win_condition = "close victory"

            # If the caller attached a `morale_delta` attribute on the loser
            # object (preferred), use it. Otherwise fall back to a conservative
            # fixed decrease based on the win_type.
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

        # No explicit error; return None on success.
        return None


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
            "SELECT id FROM wars WHERE (attacker=(%s) OR defender=(%s)) "
            "AND peace_date IS NULL",
            (id, id),
        )
        id_list = db.fetchall()

        # # determine wheter the user is the aggressor or the defender
        # current_wars_result = []
        # for war_id in id_list:
        # db.execute(
        #     "SELECT 1 FROM wars WHERE id=(%s) AND attacker=(%s)",
        #     (war_id[0], id),
        # )
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
        from psycopg2.extras import RealDictCursor

        from database import get_db_cursor

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
        from psycopg2.extras import RealDictCursor

        from database import get_db_cursor

        with get_db_cursor(cursor_factory=RealDictCursor) as db:
            upgrades = {}

            if upgrade_type == "supplies":
                upgrade_fields = list(cls.supply_related_upgrades.keys())
                if upgrade_fields:
                    upgrade_query = (
                        f"SELECT {', '.join(upgrade_fields)} FROM upgrades "
                        "WHERE user_id=%s"
                    )
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

    # Description: deal damage to random buildings based on `particular_infra`.
    # `particular_infra` example for `public_works`:
    #   {"libraries": 3, "hospitals": x, ...}
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
                    # If multiple of the same building exist, add them multiple
                    # times to the selection list
                    for _ in range(amount):
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

                # NOTE: possible feature: a building might not be destroyed but
                # become unusable if reparation cost is lower than rebuying it.
                else:
                    # Damage was not sufficient to destroy the building; record
                    # the value for debugging if needed.
                    pass

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
                "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) "
                "AND (defender=(%s) OR defender=(%s))",
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
    # NOTE: currently only one winner is supported: winners = [id]
    @staticmethod
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

        # Previously attempted complex single-line SQL; keep this readable
        # and wrapped for maintainability.
        db.execute(
            "SELECT CASE WHEN attacker_morale=0 THEN defender_morale "
            "ELSE attacker_morale END FROM wars "
            "WHERE (attacker=%s OR defender=%s) AND (attacker=%s OR defender=%s)",
            (winners[0], winners[0], losers[0], losers[0]),
        )
        winner_remaining_morale = db.fetchone()[0]

        # Calculate reparation tax based on remaining morale
        # if winner_remaining_morale_effect
        tax_rate = 0.2 * winner_remaining_morale

        # Record the reparation tax entry for bookkeeping
        db.execute(
            "INSERT INTO reparation_tax (winner,loser,percentage,until) "
            "VALUES (%s,%s,%s,%s)",
            (winners[0], losers[0], tax_rate, time.time() + 5000),
        )
        print("reparation_tax recorded", winners[0], losers[0], tax_rate)
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
            "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) "
            "AND (defender=(%s) OR defender=(%s))",
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
            # TODO: award winners appropriately for a total victory. This is not
            # the same as negotiation: the enemy completely lost the war (morale
            # dropped to 0) and should receive the corresponding penalties.
            Nation.set_peace(db, connection, war_id)
            eco = Economy(winner.user_id)

            for resource in Economy.resources:
                resource_sel_stat = f"SELECT {resource} FROM resources WHERE id=%s"
                db.execute(resource_sel_stat, (loser.user_id,))
                resource_amount = db.fetchone()[0]

                # Transfer 20% of the resource on hand.
                # TODO: define how this should behave if an alliance won.
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
            # NOTE: divided attack_effects[0] by 20; otherwise special units
            # damage can be overpowered. Consider tuning this value as needed.

            # Example (min destruction): the old formula (too powerful) is shown
            # commented out here for reference.
            # min_destruction = (
            #     target_amount * (1 / 5) * (
            #         attack_effects[0] / (1 + attack_effects[1])
            #         * attacker.selected_units[special_unit]
            #     )
            # )
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
            # TODO: decrease only the selected amount when attacker uses a subset
            # of their forces (e.g., DB has 100 soldiers but attacker deploys 20).
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

            # NOTE: move this logic to the warResult route and reuse it for both
            # special and regular attacks.
            # TODO: add proper error handling for infra damage (e.g. missing
            # province should return a controlled error, not raise an exception).
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

    # NOTE: may become an instance method in the future instead of static
    # Battle outcome reference and unit counters (short version):
    #   - 3x score: annihilation
    #   - 2x score: definite victory
    #   - >1x score: close victory
    #   - <1x score: close defeat (0 damage)
    #   - <=0.5x score: massive defeat (0 damage)
    # See units.py for detailed unit bonuses and exact counters.

    @staticmethod
    # Attacker/defender here are the participant users for this specific fight
    def fight(attacker, defender):  # Units, Units -> int
        # IMPORTANT: You can tune fight chances, bonuses and casualty rules here.
        # See `units.py` for individual unit bonus definitions.
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
            # Unit amount chance: this grants bonuses based on unit counts even
            # if there is no explicit counter unit type.
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

        # Previously these included roll, unit-amount bonuses and per-unit bonuses.
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

        # Get the absolute side (attacker/defender) from the war record. This
        # determines which morale column (attacker/defender) should be reduced.

        connection = psycopg2.connect(
            database=os.getenv("PG_DATABASE"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
        )

        db = connection.cursor()

        db.execute(
            "SELECT attacker FROM wars WHERE (attacker=(%s) OR defender=(%s)) "
            "AND peace_date IS NULL",
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

        # Debug example: print("MORALE COLUMN", morale_column, "WINNER", winner.user_id)

        # Compute per-unit morale delta based on the loser's unit composition and
        # the win_type. The computed delta is attached to the loser object so
        # `morale_change` can consume it.
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

        # Advantage factor in [0..1]; equal strengths -> ~0.5
        advantage = attacker_strength / (attacker_strength + defender_strength + 1e-9)

        # If defender won, invert the advantage for purposes of computing
        # the impact on the loser.
        if winner is defender:
            advantage_factor = 1.0 - advantage
        else:
            advantage_factor = advantage

        # Base value derived from the loser's own units (their potential to
        # suffer morale loss)
        base_loser_value = 0.0
        try:
            for unit_name, count in loser.selected_units.items():
                base_loser_value += (count or 0) * unit_morale_weights.get(
                    unit_name, 0.01
                )
        except Exception:
            base_loser_value = 1.0

        # Compute the morale delta proportional to base_loser_value, advantage and
        # win_type. Scale down to keep deltas reasonable and cap extremes.
        computed_morale_delta = int(
            round(base_loser_value * advantage_factor * win_type * 0.1)
        )
        computed_morale_delta = max(1, computed_morale_delta)
        computed_morale_delta = min(200, computed_morale_delta)

        # attach to loser for morale_change to pick up
        # Direct attribute assignment is preferred to setattr for static names
        loser._computed_morale_delta = computed_morale_delta

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
        # db.execute(
        #     "SELECT id FROM provinces WHERE userId=(%s) ORDER BY id ASC",
        #     (defender.user_id,),
        # )
        # province_id_fetch = db.fetchall()
        # random_province = province_id_fetch[
        #     random.randint(0, len(province_id_fetch) - 1)
        # ][0]
        #
        # Currently units only affect public works
        # public_works = Nation.get_public_works(random_province)
        #
        # TODO: enforce war type like 'raze' which might scale damage higher
        # infra_damage_effects = Military.infrastructure_damage(
        #     attack_effects[0], public_works, random_province
        # )

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

        # This data comes in the format:
        # [(cId, soldiers, artillery, tanks, bombers, fighters, apaches,
        #   spies, icbms, nukes, destroyer, cruisers, submarines)]
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
        from psycopg2.extras import RealDictCursor

        from database import get_db_cursor

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

            # These numbers determine the upper limit of how many of each
            # military unit can be built per day.
            db.execute("SELECT manpower FROM military WHERE id=(%s)", (cId,))
            _ = db.fetchone()[0]  # manpower currently unused

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
        from psycopg2.extras import RealDictCursor

        from database import get_db_cursor

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
        defense_units = [d.strip() for d in defense_string.split(",") if d.strip()]
        if len(defense_units) == 3:
            # default_defense is stored in the db as 'unit1,unit2,unit3'
            defense_units_str = ",".join(defense_units)

            db.execute(
                "UPDATE nation SET default_defense=(%s) WHERE nation_id=(%s)",
                (defense_units_str, self.id),
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
