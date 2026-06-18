import os
import sys

# use database.py to get connection
from database import get_db_connection
import countries

def main():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get revenue
                print("Testing get_revenue(1)")
                rev = countries.get_revenue(1)
                print("Revenue:", rev)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
