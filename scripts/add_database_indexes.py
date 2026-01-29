#!/usr/bin/env python3
"""
Add missing database indexes to improve query performance.
Run this once to optimize the database for the AnO application.
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def add_indexes():
    """Add critical indexes for performance optimization."""

    connection = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )

    db = connection.cursor()

    indexes = [
        # Users and provinces queries
        (
            "CREATE INDEX IF NOT EXISTS idx_provinces_userId ON provinces(userId);",
            "Index on provinces.userId for user lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_coalitions_userId ON coalitions(userId);",
            "Index on coalitions.userId for coalition membership lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_coalitions_colId ON coalitions(colId);",
            "Index on coalitions.colId for coalition lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_proinfra_id ON proInfra(id);",
            "Index on proInfra.id for province infrastructure lookups",
        ),
        # Military queries
        (
            "CREATE INDEX IF NOT EXISTS idx_military_id ON military(id);",
            "Index on military.id for unit lookups",
        ),
        # War queries
        (
            "CREATE INDEX IF NOT EXISTS idx_wars_attacker ON wars(attacker);",
            "Index on wars.attacker for attacker lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_wars_defender ON wars(defender);",
            "Index on wars.defender for defender lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_wars_peace_date ON wars(peace_date);",
            "Index on wars.peace_date for active war filtering",
        ),
        (
            (
                "CREATE INDEX IF NOT EXISTS idx_wars_peace_offer_id "
                "ON wars(peace_offer_id);"
            ),
            "Index on wars.peace_offer_id for peace offer lookups",
        ),
        # Stats and resources
        (
            "CREATE INDEX IF NOT EXISTS idx_stats_id ON stats(id);",
            "Index on stats.id for resource lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_resources_id ON resources(id);",
            "Index on resources.id for resource lookups",
        ),
        # Market offers
        (
            "CREATE INDEX IF NOT EXISTS idx_offers_user_id ON offers(user_id);",
            "Index on offers.user_id for user offer lookups",
        ),
        (
            (
                "CREATE INDEX IF NOT EXISTS idx_offers_resource_type "
                "ON offers(resource, type);"
            ),
            "Composite index on offers for market queries",
        ),
        # Users
        (
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
            "Index on users.username for login and display lookups",
        ),
        # News
        (
            (
                "CREATE INDEX IF NOT EXISTS idx_news_destination_id "
                "ON news(destination_id);"
            ),
            "Index on news.destination_id for user news lookups",
        ),
        # Coalition related
        (
            "CREATE INDEX IF NOT EXISTS idx_colbanks_colId ON colBanks(colId);",
            "Index on colBanks.colId for coalition bank lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_requests_colId ON requests(colId);",
            "Index on requests.colId for join request lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_treaties_col1_id ON treaties(col1_id);",
            "Index on treaties.col1_id for treaty lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_treaties_col2_id ON treaties(col2_id);",
            "Index on treaties.col2_id for treaty lookups",
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_treaties_status ON treaties(status);",
            "Index on treaties.status for active treaty filtering",
        ),
        # Policies
        (
            "CREATE INDEX IF NOT EXISTS idx_policies_user_id ON policies(user_id);",
            "Index on policies.user_id for policy lookups",
        ),
    ]

    for sql, description in indexes:
        try:
            print(f"Creating: {description}...", end=" ")
            db.execute(sql)
            connection.commit()
            print("✓")
        except Exception as e:
            print(f"✗ Error: {e}")
            connection.rollback()

    connection.close()
    print("\nIndex creation complete!")


if __name__ == "__main__":
    add_indexes()
