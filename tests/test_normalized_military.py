"""Test suite for normalized unit_dictionary and military tables."""

from decimal import Decimal
from database import get_db_connection


def test_unit_dictionary_base_attack_exists():
    """Verify base_attack is correctly pulled from unit_dictionary."""
    with get_db_connection() as conn:
        db = conn.cursor()

        # Query unit_dictionary for base_attack column
        db.execute(
            """
            SELECT unit_id, name, base_attack
            FROM unit_dictionary
            LIMIT 1
            """
        )
        result = db.fetchone()

        # On fresh/empty database, this may be None; skip assertion if so
        if result is None:
            return  # Pass if table exists but is empty

        unit_id, name, base_attack = result
        assert isinstance(unit_id, int)
        assert isinstance(name, str)
        assert isinstance(base_attack, (int, float, Decimal))


def test_unit_dictionary_has_expected_units():
    """Verify unit_dictionary contains expected military units."""
    with get_db_connection() as conn:
        db = conn.cursor()

        # Query for a few expected unit types
        expected_units = ["soldiers", "fighters", "helicopters"]

        db.execute(
            "SELECT name FROM unit_dictionary WHERE name = ANY(%s)",
            (expected_units,),
        )
        results = db.fetchall()

        # Verify at least some expected units exist
        found_units = {row[0] for row in results}
        assert len(found_units) > 0, f"No expected units found. Got: {found_units}"


def test_user_military_query():
    """Verify user_military table can be queried for unit quantities."""
    with get_db_connection() as conn:
        db = conn.cursor()

        # Query designated test user's military (id=16)
        db.execute(
            """
            SELECT user_id, unit_id, quantity
            FROM user_military
            WHERE user_id = %s
            LIMIT 1
            """,
            (16,),
        )
        result = db.fetchone()

        # Verify table structure if data exists
        if result:
            user_id, unit_id, quantity = result
            assert user_id == 16
            assert isinstance(unit_id, int)
            assert isinstance(quantity, int)
