# FULLY MIGRATED

from abc import ABC, abstractmethod
from attack_scripts import Military
from random import randint
from typing import Union
from dotenv import load_dotenv
from database import get_db_connection

load_dotenv()


def get_unusable_units(user_id: int) -> set:
    """Return the set of unit names that are currently unusable for a player.

    A unit is unusable when its maintenance resource stock in user_economy is
    exactly 0 (or absent).  Units are NEVER deleted — they simply contribute
    zero attack and zero defense power until the player resupplies.

    The mapping of unit → maintenance resource is read live from
    unit_dictionary so it stays in sync with any future balance changes.
    """
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            SELECT ud.name, COALESCE(ue.quantity, 0) AS stock
            FROM unit_dictionary ud
            JOIN resource_dictionary rd
                ON rd.resource_id = ud.maintenance_cost_resource_id
            LEFT JOIN user_economy ue
                ON ue.user_id = %s
                AND ue.resource_id = ud.maintenance_cost_resource_id
            WHERE ud.maintenance_cost_resource_id IS NOT NULL
            """,
            (user_id,),
        )
        return {name for name, stock in db.fetchall() if stock == 0}


# Blueprint for units
class BlueprintUnit(ABC):
    """Base blueprint for all Unit types.

    Required attributes:
      - unit_type: name used to identify the unit (e.g., "TankUnit").
      - bonus: battle advantage value (int).
      - damage: base damage dealt to targets.
      - resource_cost: dict of resources required per unit, e.g.:
          {"ammunition": 1}  # 1 ammunition needed per unit to attack

    Subclasses implement `attack()` and `buy()` methods.
    """

    damage = 0
    bonus = 0

    """
    attack method:

        Calculates the advantage or disagvantage based on the enemy unit type.

        return: a tuple which contains (damage, bonus)

    buy method:
        return
    """

    @abstractmethod
    def attack(defending_units):
        pass

    @abstractmethod
    def buy(amount):
        pass


class SoldierUnit(BlueprintUnit):
    unit_type = "soldiers"
    damage = 1
    supply_cost = 1
    resource_cost = {"ammunition": 1}

    def __init__(self, amount: int) -> None:
        self.amount = amount

    def attack(self, defending_units: str) -> list:
        if defending_units == "artillery":
            # self.damage += 55
            self.bonus += 3 * self.amount
        if defending_units == "apaches":
            self.bonus += 2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass


class TankUnit(BlueprintUnit):
    unit_type = "tanks"
    damage = 40
    supply_cost = 5
    resource_cost = {"ammunition": 1, "gasoline": 1}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        # One tank beats 4 soldiers. If one tank beat only 4 soldiers then
        # soldiers would counter tanks (1 tank costs ~50 soldiers). One tank is
        # therefore modeled as 4x more effective vs soldiers.
        if defending_units == "soldiers":
            self.damage += 2
            self.bonus += 6 * self.amount

        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass


class ArtilleryUnit(BlueprintUnit):
    unit_type = "artillery"
    damage = 80
    supply_cost = 5
    resource_cost = {"ammunition": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        # One artillery beats 3 tanks
        if defending_units == "tanks":
            self.bonus += 2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


class BomberUnit(BlueprintUnit):
    unit_type = "bombers"
    damage = 100
    supply_cost = 5
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "soldiers":
            self.bonus += 2 * self.amount

        # Micro randomization
        # One bomber beats random number of tanks (where they drop the bombs)
        # between 2 and 6
        if defending_units == "tanks":
            self.bonus += randint(2, 6) * self.amount
            # self.bonus += 2 * self.amount

        if defending_units == "destroyers":
            self.bonus += 2 * self.amount
        if defending_units == "submarines":
            self.bonus += 2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass


class FighterUnit(BlueprintUnit):
    unit_type = "fighters"
    damage = 100
    supply_cost = 5
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "bombers":
            # self.damage += 55
            self.bonus += 4 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass


class ApacheUnit(BlueprintUnit):
    unit_type = "apaches"
    damage = 100
    supply_cost = 5
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "soldiers":
            self.bonus += 1 * self.amount
        elif defending_units == "tanks":
            self.bonus += 1 * self.amount
        elif defending_units == "bombers":
            self.bonus += 2 * self.amount
        elif defending_units == "fighter":
            self.bonus += 2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


class DestroyerUnit(BlueprintUnit):
    unit_type = "destroyers"
    damage = 100
    supply_cost = 5
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus += 1.6 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass


class CruiserUnit(BlueprintUnit):
    unit_type = "cruisers"
    damage = 200
    supply_cost = 5
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "destroyers":
            self.bonus += 0.3 * self.amount
        elif defending_units == "fighters":
            self.bonus += 0.1 * self.amount
        elif defending_units == "apaches":
            self.bonus += 0.4 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy(amount):
        pass


class SubmarineUnit(BlueprintUnit):
    unit_type = "submarines"
    damage = 100
    supply_cost = 5
    resource_cost = {"ammunition": 2, "gasoline": 2}

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "cruisers":
            self.bonus += 0.2 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


# Special units attack method handeled differently (not using the fight method)
class IcbmUnit(BlueprintUnit):
    unit_type = "icbms"
    damage = 1000
    supply_cost = 500

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus -= 5 * self.amount
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


class NukeUnit(BlueprintUnit):
    unit_type = "nukes"
    damage = 3000
    supply_cost = 1000

    def __init__(self, amount):
        self.amount = amount

    def attack(self, defending_units):
        if defending_units == "submarines":
            self.bonus -= 5 * self.amount
        else:
            pass
        return [self.damage * self.amount, self.bonus]

    def buy():
        pass


# does not have an attack method; functionality is implemented
# separately in intelligence.py
class SpyUnit(BlueprintUnit):
    unit_type = "spies"
    damage = 0  # does not attack anyway

    def __init__(self, amount):
        self.amount = amount

    def buy():
        pass


# make an instance of this object with Units(cId)
class Units(Military):
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
    # spyunit is not included here because it has no interactions with
    # other units and thus does not run inside Units.attack.
    allUnitInterfaces = [
        SoldierUnit,
        TankUnit,
        ArtilleryUnit,
        BomberUnit,
        FighterUnit,
        ApacheUnit,
        DestroyerUnit,
        CruiserUnit,
        SubmarineUnit,
        IcbmUnit,
        NukeUnit,
    ]

    """Units container and validator.

    Call `attach_units(selected_units, units_count)` to validate and attach units.

    Properties:
      - user_id: integer owner id
      - selected_units: dict mapping unit names to amounts, e.g. {"soldiers": 100}
      - bonuses: optional integer bonuses from generals, etc.
    """

    def __init__(
        self,
        user_id,
        selected_units: dict = None,
        bonuses: int = None,
        selected_units_list: list = None,
        war_id=None,
    ):
        self.user_id = user_id
        self.selected_units = selected_units
        self.bonuses = bonuses
        self.supply_costs = 0
        self.available_supplies = None
        self.war_id = war_id
        # Cache for unusable-unit lookup (populated lazily on first combat use)
        self._unusable_units_cache = None

        # selected_units_list is needed at: Nations.py/Military->fight();
        # a list of selected_units keys
        self.selected_units_list = selected_units_list

    @property
    def unusable_units(self) -> set:
        """Set of unit names with a depleted maintenance resource.

        Lazy-loaded once per Units instance so a single fight never issues
        more than one DB round-trip for this check.
        Units in this set deal 0 attack damage and 0 defense bonus until the
        player's resource stock is replenished — they are NEVER deleted.
        """
        if self._unusable_units_cache is None:
            self._unusable_units_cache = get_unusable_units(self.user_id)
        return self._unusable_units_cache

    # this is needed because we can't store object in server side cache :(
    @classmethod
    def rebuild_from_dict(cls, sess_dict):
        # if you modify the sess_dict it'll affect the actual session. For safety,
        # create a copy before mutating.
        dic = dict(sess_dict)
        sort_out = ["supply_costs", "available_supplies"]
        store_sort_values = []

        for it in sort_out:
            temp = dic.get(it, None)
            if temp is None:
                continue

            store_sort_values.append(dic[it])
            dic.pop(it)

        # Filter out private/cache attributes (e.g. _unusable_units_cache)
        # that are stored in __dict__ but are NOT __init__ parameters.
        # Without this, cls(**dic) raises TypeError on unknown kwargs.
        dic = {k: v for k, v in dic.items() if not k.startswith("_")}

        try:
            reb = cls(**dic)
        except (TypeError, ValueError):
            raise TypeError("Cannot create Units instance from database row")

        for sort, value in zip(sort_out, store_sort_values):
            setattr(reb, sort, value)

        return reb

    # Validate then attach units
    # Function parameter description:
    #    - selected_units read the Units class document above
    #    - units_count how many selected_units should be given (will be validated)
    #        example: units_count = 3 when 3 different unit_type should be selected
    #                 (like from warchoose)
    #        example: units_count = 1 when a single special unit type is selected
    #                 (e.g., nukes or icbms)
    def attach_units(self, selected_units: dict, units_count: int) -> Union[str, None]:
        self.supply_costs = 0
        unit_types = list(selected_units.keys())
        normal_units = self.get_military(self.user_id)
        special_units = self.get_special(self.user_id)

        available_units = normal_units.copy()
        available_units.update(special_units)

        # Validate selected unit types and amounts explicitly. We avoid the
        # prior index-based loop which caused confusing IndexErrors when the
        # submitted form omitted selections. Instead, validate the number of
        # distinct unit types provided and ensure each type is valid.
        unit_types = [u for u in unit_types if u]

        if len(unit_types) != units_count:
            return "Not enough unit type selected"

        # Validate each declared unit type
        for current_unit in unit_types:
            if current_unit not in self.allUnits:
                return "Invalid unit type!"

            # Ensure a non-negative integer amount was provided (0 allowed at
            # selection time; final checks are performed when concrete
            # amounts are submitted in /waramount or /wartarget)
            try:
                amt = int(selected_units.get(current_unit, 0))
            except Exception:
                return "Invalid amount selected!"

            if amt < 0:
                return "Invalid amount selected!"

            # If an actual amount (>0) was supplied, ensure user owns that many
            # units and that supplies are sufficient. When amount==0 (selection
            # stage) we skip supply-related checks to avoid spurious failures
            # when wars have low available supplies (e.g., <200).
            if amt > 0:
                if amt > available_units.get(current_unit, 0):
                    return "Invalid amount selected!"

                # Check supply cost only when we will actually send units.
                for interface in self.allUnitInterfaces:
                    if interface.unit_type == current_unit:
                        supply_check = self.attack_cost(interface.supply_cost * amt)
                        if supply_check:
                            return supply_check
                        break

        # If the validation is ended successfully
        self.selected_units = selected_units
        self.selected_units_list = list(selected_units.keys())

    # Attack with all units contained in selected_units
    def attack(self, attacker_unit: str, target: str) -> Union[str, tuple, None]:
        if self.selected_units:
            # Call interface to unit type
            for interface in self.allUnitInterfaces:
                if interface.unit_type == attacker_unit:
                    # Check unit amount validity
                    unit_amount = self.selected_units.get(attacker_unit, None)

                    if unit_amount is None:
                        return "Unit is not valid!"

                    # Unusable penalty: if this unit's maintenance resource is
                    # depleted the unit contributes zero attack AND zero defense
                    # power. The unit remains in the player's inventory and
                    # becomes effective again once resupplied.
                    if attacker_unit in self.unusable_units:
                        return (0, 0)

                    # interface.supply_cost * self.selected_units[attacker_unit]
                    # calculates the supply cost based on unit amount
                    # supply = self.attack_cost(
                    #     interface.supply_cost * self.selected_units[attacker_unit]
                    # )
                    # if supply:
                    #     return supply

                    if unit_amount != 0:
                        interface_object = interface(unit_amount)
                        attack_effects = interface_object.attack(target)

                    # doesen't have any effect if unit amount is zero
                    else:
                        return (0, 0)

                    return tuple(attack_effects)
        else:
            return "Units are not attached!"

    def save(self):
        """Persist post-fight state.

        Casualties are now handled by war_orchestrator.persist_fight_results(),
        so this method only deducts supply costs from the war record.
        """
        if not self.supply_costs or not self.war_id:
            return

        with get_db_connection() as connection:
            db = connection.cursor()

            # Determine whether this user is attacker or defender in the war
            db.execute("SELECT attacker_id FROM wars WHERE war_id = %s", (self.war_id,))
            row = db.fetchone()
            if not row:
                return

            if row[0] == self.user_id:
                supply_col = "attacker_supplies"
            else:
                supply_col = "defender_supplies"

            db.execute(
                f"UPDATE wars SET {supply_col} = "
                f"GREATEST(0, {supply_col} - %s) "
                f"WHERE war_id = %s",
                (self.supply_costs, self.war_id),
            )
            connection.commit()

    # Save casualties to the db and check for casualty validity
    # NOTE: to save the data to the db later on put it to the save method
    # unit_type -> name of the unit type, amount -> used to decreate by it
    def casualties(self, unit_type: str, amount: int) -> None:
        from math import floor

        # Make sure this is an integer
        amount = int(floor(amount))
        unit_amount = self.selected_units[unit_type]

        if amount > unit_amount:
            amount = unit_amount

        self.selected_units[unit_type] = unit_amount - amount

        # Save records to the database using normalized tables
        with get_db_connection() as connection:
            db = connection.cursor()

            db.execute(
                """UPDATE user_military um
                   SET quantity = GREATEST(0, um.quantity - %s)
                   FROM unit_dictionary ud
                   WHERE um.unit_id = ud.unit_id
                     AND um.user_id = %s
                     AND LOWER(ud.name) = LOWER(%s)""",
                (amount, self.user_id, unit_type),
            )
            connection.commit()

    # Fetch the available supplies and resources which are required
    # and compare them to the unit attack cost. Also persist morale.

    def attack_cost(self, cost: int) -> str:
        if self.available_supplies is None:
            with get_db_connection() as connection:
                db = connection.cursor()

                db.execute(
                    "SELECT attacker_id FROM wars WHERE war_id=(%s)", (self.war_id,)
                )
                row = db.fetchone()

                # Resolve attacker id safely and compare to this object's user id.
                attacker_id = row[0] if row else None

                # If the current Units object belongs to the attacker side,
                # read attacker_supplies,
                # otherwise read defender_supplies.
                if attacker_id is not None and attacker_id == self.user_id:
                    db.execute(
                        "SELECT attacker_supplies FROM wars WHERE war_id=(%s)",
                        (self.war_id,),
                    )
                    fetched = db.fetchone()
                    self.available_supplies = (
                        fetched[0] if fetched and fetched[0] is not None else 0
                    )
                else:
                    db.execute(
                        "SELECT defender_supplies FROM wars WHERE war_id=(%s)",
                        (self.war_id,),
                    )
                    fetched = db.fetchone()
                    self.available_supplies = (
                        fetched[0] if fetched and fetched[0] is not None else 0
                    )

        if self.available_supplies < 200:
            return "The minimum supply amount is 200"

        self.supply_costs += cost
        if self.supply_costs > self.available_supplies:
            return "Not enough supplies available"


# DEBUGGING
if __name__ == "__main__":
    import time

    attacker = 2
    defender = 5
    war_id = 666

    with get_db_connection() as connection:
        db = connection.cursor()

        db.execute(
            (
                "INSERT INTO wars VALUES ("
                f"{war_id},"
                f"{attacker},{defender},'Raze','falas message',NULL,"
                f"{time.time()},"
                "2000,2000,"
                f"{time.time()},100,100)"
            )
        )
        connection.commit()

        attack_units = Units(
            attacker,
            war_id=war_id,
            selected_units_list=["soldiers", "cruisers", "tanks"],
            selected_units={"soldiers": 1000, "cruisers": 100, "tanks": 50},
        )

        defender_units = Units(
            defender,
            {"tanks": 544, "soldiers": 64, "artillery": 55},
            selected_units_list=["tanks", "soldiers", "artillery"],
        )

        db.execute(f"DELETE FROM wars WHERE id={war_id}")
        connection.commit()
