#!/usr/bin/env python3
"""Migration 011: Sanitize duplicate building entries.

Removes legacy/duplicate university (ID 20) from building_dictionary.
Cleans up any user_buildings rows for the deleted building.

Run: python migrations/011_sanitize_duplicates.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_cursor  # noqa: E402


def run():
    with get_db_cursor() as db:
        try:
            # Check for duplicate university
            db.execute(
                "SELECT building_id, name, display_name, base_cost "
                "FROM building_dictionary WHERE name IN ('universities', 'university')"
            )
            universities = db.fetchall()
            print(f"Universities found: {universities}")

            if len(universities) > 1:
                # Find legacy entry (ID 20 is the legacy one)
                legacy_id = None
                canonical_id = None
                for row in universities:
                    if row[0] == 20:
                        legacy_id = row[0]
                    elif row[0] == 9:
                        canonical_id = row[0]

                if legacy_id and canonical_id:
                    print(f"\nDeleting legacy 'university' (ID {legacy_id})")
                    print(f"Canonical 'universities' (ID {canonical_id}) remains")

                    # Delete user_buildings rows for legacy building
                    db.execute(
                        "DELETE FROM user_buildings WHERE building_id = %s",
                        (legacy_id,),
                    )
                    deleted_user_buildings = db.rowcount
                    print(f"Deleted {deleted_user_buildings} user_buildings rows")

                    # Delete from building_dictionary
                    db.execute(
                        "DELETE FROM building_dictionary WHERE building_id = %s",
                        (legacy_id,),
                    )
                    print(f"Deleted building_dictionary row for ID {legacy_id}")
                    print("\n✓ Sanitization complete")

            else:
                print("No duplicates found, skipping sanitization")

        except Exception as e:
            print(f"Error during sanitization: {e}")
            raise


if __name__ == "__main__":
    run()
