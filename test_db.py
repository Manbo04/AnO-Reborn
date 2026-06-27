from database import get_request_cursor

try:
    with get_request_cursor() as db:
        # Get schema of provinces
        db.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'provinces';
        """)
        columns = [row[0] for row in db.fetchall()]
        print("Provinces columns:", columns)

        # Run the problematic query
        db.execute("""
            SELECT p.id, p.provinceName as name, p.userId as user_id, u.username, p.coordinate_x, p.coordinate_y,
                   p.pop_working + p.pop_children + p.pop_elderly as population, p.tax_rate, p.unrest, p.corruption
            FROM provinces p
            JOIN users u ON p.userId = u.id
            WHERE p.coordinate_x IS NOT NULL AND p.coordinate_y IS NOT NULL
        """)
        rows = db.fetchall()
        print("Query succeeded! Rows:", len(rows))
except Exception as e:
    import traceback
    traceback.print_exc()
