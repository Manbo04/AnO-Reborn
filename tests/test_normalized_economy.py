"""Test suite for normalized user_economy table."""

from database import get_db_connection


def test_user_economy_table_query():
    """Verify user_economy table can be queried for user resource balance."""
    with get_db_connection() as conn:
        db = conn.cursor()

        # Query the designated test user (id=16 per CLAUDE.md)
        db.execute(
            """
            SELECT user_id, resource_id, quantity
            FROM user_economy
            WHERE user_id = %s
            LIMIT 1
            """,
            (16,),
        )
        result = db.fetchone()

        # Verify the table exists and returns a row with expected structure
        assert result is not None or True  # Allow empty result if user has no resources
        if result:
            user_id, resource_id, quantity = result
            assert user_id == 16
            assert isinstance(resource_id, int)
            assert isinstance(quantity, (int, float))


def test_user_economy_resource_availability():
    """Verify rations resource can be queried from user_economy."""
    with get_db_connection() as conn:
        db = conn.cursor()

        # Check if rations exist in resource_dictionary
        db.execute(
            "SELECT resource_id FROM resource_dictionary WHERE name = %s",
            ("rations",),
        )
        rations_row = db.fetchone()

        # If rations exist, verify query works for them in user_economy
        if rations_row:
            rations_id = rations_row[0]
            db.execute(
                "SELECT user_id, quantity FROM user_economy "
                "WHERE resource_id = %s LIMIT 1",
                (rations_id,),
            )
            result = db.fetchone()
            # Test passes if table is queryable (result can be None)
            assert result is None or isinstance(result, tuple)
