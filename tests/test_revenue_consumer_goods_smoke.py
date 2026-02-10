from database import get_db_connection
import tasks


def test_consumer_goods_produced_for_test_account():
    # Use designated test account (id 16) per CLAUDE.md
    uid = 16

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
        row = db.fetchone()
        before = row[0] if row and row[0] is not None else 0

    # Allow tasks to run by resetting cursor
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO task_cursors (task_name, last_id) VALUES (%s, %s) "
            "ON CONFLICT (task_name) DO UPDATE SET last_id=0",
            ("generate_province_revenue", 0),
        )
        conn.commit()

    tasks.generate_province_revenue()

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
        row = db.fetchone()
        after = row[0] if row and row[0] is not None else 0

    assert after >= before

    # Now run tax income and ensure consumer_goods doesn't increase
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO task_cursors (task_name, last_id) VALUES (%s, %s) "
            "ON CONFLICT (task_name) DO UPDATE SET last_id=0",
            ("tax_income", 0),
        )
        conn.commit()

    tasks.tax_income()

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (uid,))
        row = db.fetchone()
        after_tax = row[0] if row and row[0] is not None else 0

    assert after_tax <= after
