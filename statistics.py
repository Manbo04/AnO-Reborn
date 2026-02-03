from flask import render_template
from helpers import login_required
from database import get_db_cursor, cache_response

# NOTE: 'app' is NOT imported at module level to avoid circular imports


@login_required
@cache_response(ttl_seconds=120)  # Cache statistics for 2 minutes
def statistics():
    """Display market statistics and nation stats"""

    with get_db_cursor() as db:
        # Get market statistics for different resources
        resources = [
            "rations",
            "oil",
            "coal",
            "uranium",
            "steel",
            "aluminium",
            "lumber",
        ]

        market_stats = {}

        # OPTIMIZATION: Fetch all resource stats in ONE query instead of 21 queries
        db.execute(
            """
            SELECT resource,
                   ROUND(AVG(price)) as avg_price,
                   MAX(price) as max_price,
                   MIN(price) as min_price
            FROM offers
            WHERE type = 'sell' AND resource IN %s
            GROUP BY resource
            """,
            (tuple(resources),),
        )

        # Initialize all resources with default values
        for resource in resources:
            market_stats[resource] = {"avg": 0, "max": 0, "min": 0}

        # Populate with actual data
        for row in db.fetchall():
            resource, avg_price, max_price, min_price = row
            market_stats[resource] = {
                "avg": int(avg_price) if avg_price else 0,
                "max": max_price if max_price else 0,
                "min": min_price if min_price else 0,
            }

        # Get some basic nation statistics
        db.execute(
            """
            SELECT COUNT(*) as total_nations,
                   AVG(influence) as avg_influence,
                   MAX(influence) as max_influence
            FROM (
                SELECT users.id,
                       CASE
                           WHEN SUM(provinces.population) IS NULL THEN 0
                           ELSE SUM(provinces.population)
                       END as influence
                FROM users
                LEFT JOIN provinces ON users.id = provinces.userid
                GROUP BY users.id
            ) as nation_stats
        """
        )
        nation_stats = db.fetchone()
        total_nations = nation_stats[0] if nation_stats[0] else 0
        avg_influence = round(nation_stats[1]) if nation_stats[1] else 0
        max_influence = nation_stats[2] if nation_stats[2] else 0

    return render_template(
        "statistics.html",
        market_stats=market_stats,
        total_nations=total_nations,
        avg_influence=avg_influence,
        max_influence=max_influence,
    )


def register_statistics_routes(app_instance):
    """Register all statistics routes with the Flask app instance"""
    app_instance.add_url_rule("/statistics", "statistics", statistics)
