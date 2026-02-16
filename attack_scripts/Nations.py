# flake8: noqa -- legacy module with many historical style issues; enable
# linting after full refactor is done.
import random
import time
from dotenv import load_dotenv
from database import fetchone_first, get_db_connection

load_dotenv()


def _cached_get_particular_resources(self, resources):
    from database import get_db_connection, fetchone_first, query_cache

    rd = {}
    non_money = [r for r in resources if r != "money"]

    # Money (stats) - cached
    if "money" in resources:
        s_key = f"stats_{self.nationID}"
        stats_cached = query_cache.get(s_key)
        if stats_cached is not None and "gold" in stats_cached:
            rd["money"] = stats_cached["gold"]
        else:
            with get_db_connection() as connection:
                db = connection.cursor()
                db.execute("SELECT gold FROM stats WHERE id=%s", (self.nationID,))
                _m = fetchone_first(db, None)
                rd["money"] = _m if _m is not None else 0
                query_cache.set(s_key, {"gold": rd["money"]})

    # Non-money resources: fetch full row and cache
    if non_money:
        r_key = f"resources_{self.nationID}"
        resources_cached = query_cache.get(r_key)
        if resources_cached is None:
            with get_db_connection() as connection:
                db = connection.cursor()
                cols = ", ".join(self.resources)
                db.execute(
                    f"SELECT {cols} FROM resources WHERE id=%s", (self.nationID,)
                )
                row = db.fetchone()

                full_row = {}
                if row is None:
                    for r in self.resources:
                        full_row[r] = 0
                elif isinstance(row, (list, tuple)):
                    for i, r in enumerate(self.resources):
                        full_row[r] = (
                            row[i] if i < len(row) and row[i] is not None else 0
                        )
                elif isinstance(row, dict):
                    for r in self.resources:
                        full_row[r] = row.get(r, 0) or 0
                else:
                    full_row[self.resources[0]] = row if row is not None else 0

                query_cache.set(r_key, full_row)
                resources_cached = full_row

        for r in non_money:
            rd[r] = resources_cached.get(r, 0) or 0

    for r in resources:
        rd.setdefault(r, 0)

    return rd


# Canonical implementation for get_particular_resources is defined above.
# No debug prints or noisy markers at import-time.


# `calculate_bonuses` moved to `attack_scripts.nations_helpers` to
# begin progressive refactoring and enable focused unit tests.
from attack_scripts.nations_helpers import calculate_bonuses  # noqa: F401


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
        # Keep both attribute names for compatibility.
        # Some codebases use 'nationID' while others use 'id'.
        self.nationID = nationID
        self.id = nationID
        # Compose a Nation instance so Economy exposes nation-level helper methods
        try:
            self.nation = Nation(nationID)
        except NameError:
            # If Nation is not yet defined at import time, delay composition until needed
            self.nation = None

    def get_economy(self):
        with get_db_connection() as connection:
            db = connection.cursor()

            # TODO fix this when the databases changes and update to include all resources
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (self.nationID,))
            self.gold = fetchone_first(db, 0)

    def get_particular_resources(self, resources):
        """Delegate to the module-level canonical implementation.

        The real implementation is `_cached_get_particular_resources` defined
        at module scope and bound on import. This keeps class definitions
        lightweight and deterministic across reloads.
        """
        return _cached_get_particular_resources(self, resources)

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

    # No custom __getattribute__ -- use default attribute lookup to avoid
    # surprising behavior under reloads and to keep semantics simple.

    @staticmethod
    def send_news(destination_id: int, message: str):
        # Backwards-compatible wrapper to forward to Nation.send_news
        try:
            Nation.send_news(destination_id, message)
        except NameError:
            # If Nation isn't available, log or raise a clear error
            raise

    def grant_resources(self, resource, amount):
        # Update a stat/resource and invalidate cache so subsequent reads are
        # served from fresh data.
        from database import invalidate_user_cache

        with get_db_connection() as connection:
            db = connection.cursor()

            db.execute(
                "UPDATE stats SET (%s) = (%s) WHERE id(%s)",
                (resource, amount, self.nationID),
            )

            connection.commit()

        # Invalidate caches related to this nation so reads are refreshed
        try:
            invalidate_user_cache(self.nationID)
        except Exception:
            pass

    # IMPORTANT: the amount is not validated in this method.
    # Callers must provide a validated value.
    def transfer_resources(self, resource, amount, destinationID):
        with get_db_connection() as connection:
            db = connection.cursor()  # noqa: F841

            if resource not in self.resources:
                return "Invalid resource"

            @staticmethod
            def morale_change(column, win_type, winner, loser):
                # Updated morale change: accept a computed morale delta passed through the caller
                # The caller should compute a morale delta based on units involved. We still keep
                # the win_type -> human-readable win_condition mapping, but morale is adjusted
                # by the provided delta to allow per-unit impacts.
                with get_db_connection() as connection:
                    db = connection.cursor()

                    db.execute(
                        "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
                        (winner.user_id, loser.user_id, winner.user_id, loser.user_id),
                    )
                    war_id = db.fetchall()[-1][0]

    # IMPORTANT: the amount is not validated in this method.
    # Callers must provide a validated value.
    def transfer_resources(self, resource, amount, destinationID):
        from database import invalidate_user_cache

        with get_db_connection() as connection:
            db = connection.cursor()  # noqa: F841

            if resource not in self.resources:
                return "Invalid resource"

            @staticmethod
            def morale_change(column, win_type, winner, loser):
                # Updated morale change: accept a computed morale delta passed through the caller
                # The caller should compute a morale delta based on units involved. We still keep
                # the win_type -> human-readable win_condition mapping, but morale is adjusted
                # by the provided delta to allow per-unit impacts.
                with get_db_connection() as connection:
                    db = connection.cursor()

                    db.execute(
                        "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
                        (winner.user_id, loser.user_id, winner.user_id, loser.user_id),
                    )
                    war_id = db.fetchall()[-1][0]

            war_column_stat = f"SELECT {column} FROM wars " + "WHERE id=(%s)"
            db.execute(war_column_stat, (war_id,))
            morale = fetchone_first(db, 0)

            # Determine win_condition label from win_type (keeps semantics for other logic)
            if win_type >= 3:
                win_condition = "annihilation"
            elif win_type >= 2:
                win_condition = "definite victory"
            else:
                win_condition = "close victory"

        # Invalidate caches for the source and destination nations after transfer
        try:
            invalidate_user_cache(self.nationID)
            invalidate_user_cache(destinationID)
        except Exception:
            pass
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
                    resource_amount = fetchone_first(db, 0)
                    # transfer 20% of resource on hand
                    eco.transfer_resources(
                        resource, resource_amount * (1 / 5), winner.user_id
                    )

                db.execute(
                    f"UPDATE wars SET {column}=(%s) WHERE id=(%s)", (morale, war_id)
                )

                connection.commit()

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
        with get_db_connection() as connection:
            db = connection.cursor()
            db.execute(
                "INSERT INTO news(destination_id, message) VALUES (%s, %s)",
                (destination_id, message),
            )
            connection.commit()

    def get_provinces(self):
        with get_db_connection() as connection:
            logger = __import__("logging").getLogger(__name__)
            logger.debug(
                "get_provinces: connection type=%s closed=%s",
                type(connection),
                getattr(connection, "closed", None),
            )
            db = connection.cursor()
            logger.debug(
                "get_provinces: after cursor created cursor.closed=%s",
                getattr(db, "closed", None),
            )
            if self.provinces is None:
                self.provinces = {"provinces_number": 0, "province_stats": {}}
                try:
                    db.execute(
                        "SELECT COUNT(provinceName) FROM provinces WHERE userId=%s",
                        (self.id,),
                    )
                except Exception as e:
                    # Defensive recovery: if the underlying cursor was closed for any reason,
                    # retry the query on a fresh connection once before failing.
                    logger.warning("get_provinces: initial db.execute failed: %s", e)
                    if "cursor already closed" in str(e).lower():
                        logger.info("get_provinces: retrying with fresh connection")
                        with get_db_connection() as c2:
                            db2 = c2.cursor()
                            db2.execute(
                                "SELECT COUNT(provinceName) FROM provinces WHERE userId=%s",
                                (self.id,),
                            )
                            provinces_number = fetchone_first(db2, 0)
                            self.provinces["provinces_number"] = provinces_number
                    else:
                        raise
                else:
                    provinces_number = fetchone_first(db, 0)
                    self.provinces["provinces_number"] = provinces_number

            if provinces_number > 0:
                try:
                    db.execute("SELECT * FROM provinces WHERE userId=(%s)", (self.id,))
                except Exception as e:
                    if "cursor already closed" in str(e).lower():
                        logger.info(
                            "get_provinces: retrying SELECT * with fresh connection"
                        )
                        with get_db_connection() as c3:
                            db3 = c3.cursor()
                            db3.execute(
                                "SELECT * FROM provinces WHERE userId=(%s)", (self.id,)
                            )
                            provinces = db3.fetchall()
                    else:
                        raise
                else:
                    provinces = db.fetchall()
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
        with get_db_connection() as connection:
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
                    fields = ", ".join(upgrade_fields)
                    upgrade_query = (
                        "SELECT " + fields + " FROM upgrades WHERE user_id=%s"
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
                    _max_damage = abs(damage - health)

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
                "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
                (
                    attacker.user_id,
                    defender.user_id,
                    attacker.user_id,
                    defender.user_id,
                ),
            )
            war_id = db.fetchall()[-1][0]
            db.execute(f"SELECT {column} FROM wars WHERE id=(%s)", (war_id,))
            morale = fetchone_first(db, 0)
            return (war_id, morale)

    @staticmethod
    def reparation_tax(winners, losers):
        """Reparation tax

        Parameters:
            winners: list of winner ids (currently only one winner supported)
            losers: list of loser ids
        """
        # def reparation_tax(winner_side, loser_side):

        # get remaining morale for winner (only one supported current_wars)
        with get_db_connection() as connection:
            db = connection.cursor()

            # db.execute(
            # "SELECT IF attacker_morale==0 THEN defender_morale ELSE attacker_morale FROM (SELECT defender_morale,attacker_morale FROM wars WHERE (attacker=%s OR defender=%s) AND (attacker=%s OR defender=%s)) L",
            # (winners[0], winners[0], losers[0], losers[0]))

            db.execute(
                "SELECT CASE WHEN attacker_morale=0 THEN defender_morale\n ELSE attacker_morale\n END\n FROM wars WHERE (attacker=%s OR defender=%s) AND (attacker=%s OR defender=%s)",
                (winners[0], winners[0], losers[0], losers[0]),
            )
            winner_remaining_morale = fetchone_first(db, 0)

            # Calculate reparation tax based on remaining morale
            # if winner_remaining_morale_effect
            tax_rate = 0.2 * winner_remaining_morale

            db.execute(
                "INSERT INTO reparation_tax (winner,loser,percentage,until) VALUES (%s,%s,%s,%s)",
                (winners[0], losers[0], tax_rate, time.time() + 5000),
            )

            connection.commit()

    # Update the morale and give back the win type name
    @staticmethod
    # def morale_change(war_id, morale, column, win_type, winner, loser):
    def morale_change(column, win_type, winner, loser):
        with get_db_connection() as connection:
            db = connection.cursor()

            db.execute(
                "SELECT id FROM wars WHERE (attacker=(%s) OR attacker=(%s)) AND (defender=(%s) OR defender=(%s))",
                (winner.user_id, loser.user_id, winner.user_id, loser.user_id),
            )
            war_id = db.fetchall()[-1][0]

            war_column_stat = f"SELECT {column} FROM wars " + "WHERE id=(%s)"
            db.execute(war_column_stat, (war_id,))
            morale = fetchone_first(db, 0)

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
                    resource_amount = fetchone_first(db, 0)

                    # transfer 20% of resource on hand (TODO: implement if and alliance won how to give it)
                    eco.transfer_resources(
                        resource, resource_amount * (1 / 5), winner.user_id
                    )

                # print("THE WAR IS OVER")

            db.execute(f"UPDATE wars SET {column}=(%s) WHERE id=(%s)", (morale, war_id))

            connection.commit()

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
            with get_db_connection() as connection:
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
                special_unit_fetch = fetchone_first(db, 0)

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

        # Delegate inner engagement calculations to a helper so this file
        # can be progressively refactored into smaller, testable units.
        from attack_scripts.combat_helpers import compute_engagement_metrics

        (
            attacker_unit_amount_bonuses,
            defender_unit_amount_bonuses,
            attacker_bonus,
            defender_bonus,
            dealt_infra_damage,
        ) = compute_engagement_metrics(attacker, defender)

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

        with get_db_connection() as connection:
            db = connection.cursor()

            db.execute(
                "SELECT attacker FROM wars WHERE (attacker=(%s) OR defender=(%s)) AND peace_date IS NULL",
                (winner.user_id, winner.user_id),
            )
            abs_attacker = fetchone_first(db, 0)

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

        # Delegate morale/strength calculation to the combat helper so the
        # core `fight` logic remains focused on flow control and DB effects.
        from attack_scripts.combat_helpers import compute_morale_delta, compute_strength

        # Compute the morale delta and attach to the loser (unchanged behaviour)
        winner_is_defender = winner is defender
        computed_morale_delta = compute_morale_delta(
            loser.selected_units,
            attacker.selected_units,
            defender.selected_units,
            winner_is_defender,
            win_type,
        )

        setattr(loser, "_computed_morale_delta", computed_morale_delta)

        # Expose advantage for potential telemetry/debugging (keeps parity)
        attacker_strength = compute_strength(attacker.selected_units)
        defender_strength = compute_strength(defender.selected_units)
        advantage = attacker_strength / (attacker_strength + defender_strength + 1e-9)
        if winner is defender:
            advantage_factor = 1.0 - advantage
        else:
            advantage_factor = advantage

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

        # infrastructure damage (code commented out - connection removed)
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
        with get_db_connection() as connection:
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

            return unit_lst  # this is a list of the format [100, 50, 50]

    @staticmethod
    def get_military(cId: int) -> dict:  # int -> dict
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
    def get_limits(cId: int) -> dict:  # int -> dict
        from database import get_db_cursor

        # Aggregate proInfra using the infra helper so `Nations.py` can be
        # progressively simplified and the SQL is easier to test in isolation.
        from attack_scripts.infra_helpers import aggregate_proinfra_for_user

        (
            army_bases,
            harbours,
            aerodomes,
            admin_buildings,
            silos,
        ) = aggregate_proinfra_for_user(cId)

        # these numbers determine the upper limit of how many of each military unit can be built per day
        with get_db_cursor() as db:
            db.execute("SELECT manpower FROM military WHERE id=(%s)", (cId,))
            _manpower = fetchone_first(db, 0)

            # fetch upgrade flag while cursor is open
            db.execute("SELECT increasedfunding FROM upgrades WHERE user_id=%s", (cId,))
            increased_funding = fetchone_first(db, 0)

        military = Military.get_military(cId)

        # TODO: maybe clear this mess a bit up
        # Land units
        soldiers = max(0, army_bases * 100 - military["soldiers"])
        tanks = max(0, army_bases * 8 - military["tanks"])
        artillery = max(0, army_bases * 8 - military["artillery"])

        # Air units
        # Fighters and bombers share aerodome capacity
        air_units = military["fighters"] + military["bombers"]
        air_limit = max(0, aerodomes * 5 - air_units)
        bombers = air_limit
        fighters = air_limit

        # Apaches use army_bases (separate capacity from aerodomes)
        apaches = max(0, army_bases * 5 - military.get("apaches", 0))

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
        """Set the nation's default defense composition.

        Expected format: 'unit1,unit2,unit3' (three unit names)
        """
        with get_db_connection() as connection:
            db = connection.cursor()
            parts = [p.strip() for p in defense_string.split(",") if p.strip()]
            if len(parts) != 3:
                # user should never reach here; return a friendly message for beta testers
                return "Invalid number of units given to set_defense, report to admin"

            defense_units = ",".join(parts)
            # Use standard %s placeholders for parameterized queries
            db.execute(
                "UPDATE nation SET default_defense=%s WHERE nation_id=%s",
                (defense_units, self.id),
            )
            connection.commit()


# Legacy helpers removed — use `_cached_get_particular_resources` above.

# Canonical implementation moved to module top. The binding and
# import-time patching below still ensure older imports are corrected.

# One authoritative bind on import
Economy.get_particular_resources = _cached_get_particular_resources

# Patch any already-imported modules that may hold a stale Economy class
import sys as _sys

for _m in list(_sys.modules.values()):
    try:
        if getattr(_m, "Economy", None) is not None:
            _m.Economy.get_particular_resources = _cached_get_particular_resources
    except Exception:
        pass


# Robust fallback implementation usable from any binding. If any other
# code path binds a stale or broken `get_particular_resources`, we wrap it to
# delegate to this canonical helper on error or suspicious results.


def _impl_get_particular_resources(nationID, resources):
    from database import get_db_connection, fetchone_first, query_cache

    rd = {}
    non_money = [r for r in resources if r != "money"]

    # Money (stats) - cached
    if "money" in resources:
        s_key = f"stats_{nationID}"
        stats_cached = query_cache.get(s_key)
        if stats_cached is not None and "gold" in stats_cached:
            rd["money"] = stats_cached["gold"]
        else:
            with get_db_connection() as connection:
                db = connection.cursor()
                db.execute("SELECT gold FROM stats WHERE id=%s", (nationID,))
                _m = fetchone_first(db, None)
                rd["money"] = _m if _m is not None else 0
                try:
                    query_cache.set(s_key, {"gold": rd["money"]})
                except Exception:
                    pass

    if non_money:
        r_key = f"resources_{nationID}"
        resources_cached = query_cache.get(r_key)
        if resources_cached is None:
            with get_db_connection() as connection:
                db = connection.cursor()
                cols = ", ".join(Economy.resources)
                db.execute(f"SELECT {cols} FROM resources WHERE id=%s", (nationID,))
                row = db.fetchone()

                full_row = {}
                if row is None:
                    for r in Economy.resources:
                        full_row[r] = 0
                elif isinstance(row, (list, tuple)):
                    for i, r in enumerate(Economy.resources):
                        full_row[r] = (
                            row[i] if i < len(row) and row[i] is not None else 0
                        )
                elif isinstance(row, dict):
                    for r in Economy.resources:
                        full_row[r] = row.get(r, 0) or 0
                else:
                    full_row[Economy.resources[0]] = row if row is not None else 0

                try:
                    query_cache.set(r_key, full_row)
                except Exception:
                    pass
                resources_cached = full_row

        for r in non_money:
            rd[r] = resources_cached.get(r, 0) or 0

    for r in resources:
        rd.setdefault(r, 0)

    return rd


# Final, authoritative binding: ensure `Economy.get_particular_resources`
# references the canonical implementation and patch any already-imported
# modules that may have a stale Economy class object.
Economy.get_particular_resources = _cached_get_particular_resources
import sys as _sys

for _m in list(_sys.modules.values()):
    try:
        if getattr(_m, "Economy", None) is not None:
            _m.Economy.get_particular_resources = _cached_get_particular_resources
    except Exception:
        pass
