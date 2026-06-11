import os
from database import get_db_cursor
from app import app
with app.app_context():
    with get_db_cursor() as db:
        db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [r[0] for r in db.fetchall()]
        for t in tables:
            try:
                db.execute(f"SELECT * FROM {t}::text WHERE {t}::text ILIKE '%20891%' OR {t}::text ILIKE '%mohammad%' OR {t}::text ILIKE '%moham%'")
                rows = db.fetchall()
                if rows:
                    print(f"Found in table {t}: {rows}")
            except Exception as e:
                pass
