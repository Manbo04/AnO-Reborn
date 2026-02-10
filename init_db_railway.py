#!/usr/bin/env python3
"""
Database initialization script for Railway deployment.
Run this with: railway run python init_db_railway.py
Or set DATABASE_URL and run directly: python init_db_railway.py
"""

import psycopg2
import os


def create_database():
    # Railway provides DATABASE_URL
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Run with: railway run python init_db_railway.py")
        return False

    connection = psycopg2.connect(database_url)
    db = connection.cursor()

    tables = [
        "coalitions",
        "colBanks",
        "colBanksRequests",
        "colNames",
        "col_applications",
        "keys",
        "military",
        "offers",
        "proInfra",
        "provinces",
        "upgrades",
        "requests",
        "resources",
        "spyinfo",
        "stats",
        "trades",
        "treaties",
        "users",
        "peace",
        "wars",
        "reparation_tax",
        "news",
        "revenue",
        "reset_codes",
        "policies",
        "signup_attempts",
        "task_runs",
        "task_cursors",
    ]

    print("Initializing database...")
    print(f"Found {len(tables)} tables to create")

    success_count = 0
    for table_name in tables:
        table_file = f"affo/postgres/{table_name}.txt"
        try:
            with open(table_file, "r") as file:
                sql = file.read()
                db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                db.execute(sql)
                connection.commit()
                print(f"✓ Created table: {table_name}")
                success_count += 1
        except FileNotFoundError:
            print(f"✗ File not found: {table_file}")
        except Exception as e:
            print(f"✗ Failed to create table {table_name}: {e}")
            connection.rollback()

    print("\n✓ Database initialization complete!")
    print(f"Created {success_count} out of {len(tables)} tables")

    # Fix existing provinces with better defaults
    try:
        db.execute("UPDATE provinces SET happiness=50 WHERE happiness=0")
        db.execute("UPDATE provinces SET productivity=50 WHERE productivity=0")
        db.execute(
            "UPDATE provinces SET consumer_spending=50 WHERE consumer_spending=0"
        )
        connection.commit()
        print("✓ Fixed existing provinces with default values")
    except Exception as e:
        print(
            f"Note: Could not fix existing provinces (may be normal on first run): {e}"
        )

    # Insert initial keys for registration
    try:
        db.execute("INSERT INTO keys (key) VALUES ('a'), ('b'), ('c')")
        connection.commit()
        print("\n✓ Inserted registration keys: a, b, c")
    except Exception as e:
        print(f"\n✗ Failed to insert keys: {e}")

    db.close()
    connection.close()

    print(f"\n{'='*50}")
    print("Database initialization complete!")
    print(f"Successfully created {success_count}/{len(tables)} tables")
    print(f"{'='*50}")

    return success_count == len(tables)


if __name__ == "__main__":
    success = create_database()
    exit(0 if success else 1)
