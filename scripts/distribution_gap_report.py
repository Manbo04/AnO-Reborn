#!/usr/bin/env python3
"""Report ration distribution gap for a nation (default: test user 16)."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection  # noqa: E402
from tasks import fetch_nation_distribution_status, food_stats  # noqa: E402
import variables  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, default=16)
    args = parser.parse_args()
    uid = args.user_id

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId = %s",
            (uid,),
        )
        pop = int(db.fetchone()[0] or 0)
        rations_need = max(1, pop // variables.RATIONS_PER)
        status = fetch_nation_distribution_status(db, uid, pop, rations_need)

    if not status:
        print("Rations distribution feature disabled.")
        return 0

    score = food_stats(uid)
    print(f"User {uid}: population={pop:,}")
    print(f"  Rations stockpile: {status['rations_stockpile']:,}")
    print(f"  Distribution cap:  {status['distribution_cap']:,}")
    print(f"  Coverage:        {status['coverage_percent']}%")
    print(f"  Unserved pop:    {status['uncovered_population']:,}")
    print(f"  Suggested DCs:   {status['distribution_centers_suggested']}")
    print(f"  Food score:      {score:.3f}")
    if status["stockpile_bottleneck"]:
        print("  => Stockpile bottleneck: build distribution_centers or more retail.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
