"""
Performance optimization: Add database indexes for commonly queried fields
This script should be run once on the production database to improve query performance.

Run with: python add_indexes.py
"""

from database import get_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INDEXES = [
    # Market offers - queried frequently with filters
    ("idx_offers_resource", "offers", "resource"),
    ("idx_offers_type", "offers", "type"),
    ("idx_offers_price", "offers", "price"),
    ("idx_offers_amount", "offers", "amount"),
    ("idx_offers_user_id", "offers", "user_id"),
    # Users - sorted and filtered often
    ("idx_users_provinces", "users", "provinces"),
    ("idx_users_influence", "users", "influence"),
    ("idx_users_username", "users", "username"),
    ("idx_users_id", "users", "id"),
    # Wars - checked for active conflicts
    ("idx_wars_attacker_id", "wars", "attacker_id"),
    ("idx_wars_defender_id", "wars", "defender_id"),
    ("idx_wars_is_active", "wars", "is_active"),
    # Coalitions
    ("idx_coalitions_leader_id", "coalitions", "leader_id"),
    # Resources - joined with users frequently
    ("idx_resources_id", "resources", "id"),
    # Statistics - joined with users frequently
    ("idx_stats_id", "stats", "id"),
]


def create_index(conn, index_name, table_name, column_name):
    """Create an index if it doesn't already exist."""
    try:
        with conn.cursor() as cursor:
            # Check if index already exists
            cursor.execute(
                """
                SELECT 1 FROM pg_indexes
                WHERE tablename = %s AND indexname = %s
            """,
                (table_name, index_name),
            )

            if cursor.fetchone():
                logger.info(f"Index {index_name} already exists, skipping")
                return False

            # Create index
            sql = f"CREATE INDEX {index_name} ON {table_name} ({column_name})"
            logger.info(f"Creating index: {sql}")
            cursor.execute(sql)
            conn.commit()
            logger.info(f"✓ Created index {index_name} on {table_name}({column_name})")
            return True

    except Exception as e:
        logger.error(f"✗ Failed to create index {index_name}: {e}")
        conn.rollback()
        return False


def analyze_table(conn, table_name):
    """Run ANALYZE to update table statistics after adding indexes."""
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"ANALYZE {table_name}")
            conn.commit()
            logger.info(f"✓ Analyzed table {table_name}")
    except Exception as e:
        logger.error(f"✗ Failed to analyze table {table_name}: {e}")
        conn.rollback()


def main():
    """Add all indexes to the database."""
    logger.info("=" * 60)
    logger.info("Starting database index creation")
    logger.info("=" * 60)

    conn = get_db()

    if not conn:
        logger.error("Failed to connect to database")
        return

    created_count = 0
    skipped_count = 0
    failed_count = 0
    tables_to_analyze = set()

    for index_name, table_name, column_name in INDEXES:
        if create_index(conn, index_name, table_name, column_name):
            created_count += 1
            tables_to_analyze.add(table_name)
        elif index_name in [idx[0] for idx in INDEXES]:
            skipped_count += 1
        else:
            failed_count += 1

    # Analyze tables with new indexes
    logger.info("\nAnalyzing tables to update statistics...")
    for table_name in tables_to_analyze:
        analyze_table(conn, table_name)

    conn.close()

    logger.info("=" * 60)
    logger.info("Index creation complete")
    logger.info(f"Created: {created_count}")
    logger.info(f"Skipped (already exist): {skipped_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info("=" * 60)

    if created_count > 0:
        logger.info("\n✓ Database performance has been improved!")
        logger.info("Query performance should be noticeably faster.")
    else:
        logger.info("\nAll indexes already exist. No changes made.")


if __name__ == "__main__":
    main()
