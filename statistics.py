from flask import render_template
from helpers import login_required
from database import get_request_cursor, cache_response, get_coalition_members_table

# NOTE: 'app' is NOT imported at module level to avoid circular imports


@login_required
@cache_response(ttl_seconds=120)  # Cache statistics for 2 minutes
def statistics():
    """Display market statistics and nation stats"""

    with get_request_cursor(read_only=True) as db:
        # Get market statistics for different resources
        resources = [
            "rations",
            "oil",
            "coal",
            "uranium",
            "steel",
            "aluminium",
            "lumber",
            "components",
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
                SELECT
                    u.id,
                    ROUND(
                        COALESCE(p.provinces_count, 0) * 300
                        + COALESCE(m.soldiers, 0) * 0.02
                        + COALESCE(m.artillery, 0) * 1.6
                        + COALESCE(m.tanks, 0) * 0.8
                        + COALESCE(m.fighters, 0) * 3.5
                        + COALESCE(m.bombers, 0) * 2.5
                        + COALESCE(m.apaches, 0) * 3.2
                        + COALESCE(m.submarines, 0) * 4.5
                        + COALESCE(m.destroyers, 0) * 3
                        + COALESCE(m.cruisers, 0) * 5.5
                        + COALESCE(m.icbms, 0) * 250
                        + COALESCE(m.nukes, 0) * 500
                        + COALESCE(m.spies, 0) * 25
                        + COALESCE(p.city_count, 0) * 10
                        + COALESCE(p.total_land, 0) * 10
                        + COALESCE(r.total_resources, 0) * 0.001
                        + COALESCE(s.gold, 0) * 0.00001
                    )::bigint AS influence
                FROM users u
                LEFT JOIN stats s ON s.id = u.id
                LEFT JOIN (
                    SELECT
                        userid AS user_id,
                        COUNT(id) AS provinces_count,
                        COALESCE(SUM(citycount), 0) AS city_count,
                        COALESCE(SUM(land), 0) AS total_land
                    FROM provinces
                    GROUP BY userid
                ) p ON p.user_id = u.id
                LEFT JOIN (
                    SELECT
                        um.user_id,
                        SUM(CASE WHEN ud.name='soldiers' THEN um.quantity ELSE 0 END) AS soldiers,
                        SUM(CASE WHEN ud.name='artillery' THEN um.quantity ELSE 0 END) AS artillery,
                        SUM(CASE WHEN ud.name='tanks' THEN um.quantity ELSE 0 END) AS tanks,
                        SUM(CASE WHEN ud.name='fighters' THEN um.quantity ELSE 0 END) AS fighters,
                        SUM(CASE WHEN ud.name='bombers' THEN um.quantity ELSE 0 END) AS bombers,
                        SUM(CASE WHEN ud.name='apaches' THEN um.quantity ELSE 0 END) AS apaches,
                        SUM(CASE WHEN ud.name='submarines' THEN um.quantity ELSE 0 END) AS submarines,
                        SUM(CASE WHEN ud.name='destroyers' THEN um.quantity ELSE 0 END) AS destroyers,
                        SUM(CASE WHEN ud.name='cruisers' THEN um.quantity ELSE 0 END) AS cruisers,
                        SUM(CASE WHEN ud.name='icbms' THEN um.quantity ELSE 0 END) AS icbms,
                        SUM(CASE WHEN ud.name='nukes' THEN um.quantity ELSE 0 END) AS nukes,
                        SUM(CASE WHEN ud.name='spies' THEN um.quantity ELSE 0 END) AS spies
                    FROM user_military um
                    JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
                    GROUP BY um.user_id
                ) m ON m.user_id = u.id
                LEFT JOIN (
                    SELECT user_id, COALESCE(SUM(quantity), 0) AS total_resources
                    FROM user_economy
                    GROUP BY user_id
                ) r ON r.user_id = u.id
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


@login_required
@cache_response(ttl_seconds=300)  # Cache rankings for 5 minutes
def rankings():
    """Display the top leaderboards for nations and alliances."""
    with get_request_cursor(read_only=True) as db:
        # Top 15 by Population
        db.execute(
            """
            SELECT u.id, u.username, COALESCE(SUM(p.population), 0) as total_pop
            FROM users u
            JOIN provinces p ON u.id = p.userid
            WHERE u.is_verified = TRUE
            GROUP BY u.id, u.username
            ORDER BY total_pop DESC
            LIMIT 15
            """
        )
        top_population = db.fetchall()

        # Top 15 by Military Size (Total quantity of all units)
        db.execute(
            """
            SELECT u.id, u.username, COALESCE(SUM(um.quantity), 0) as army_size
            FROM users u
            JOIN user_military um ON u.id = um.user_id
            WHERE u.is_verified = TRUE
            GROUP BY u.id, u.username
            ORDER BY army_size DESC
            LIMIT 15
            """
        )
        top_military = db.fetchall()
        
        # Top 15 by Wealth (Money)
        db.execute(
            """
            SELECT u.id, u.username, COALESCE(s.gold, 0) as total_money
            FROM users u
            JOIN stats s ON u.id = s.id
            WHERE u.is_verified = TRUE
            ORDER BY total_money DESC
            LIMIT 15
            """
        )
        top_wealth = db.fetchall()
        
        # Top 15 Alliances by Influence (Sum of member populations)
        members_tbl = get_coalition_members_table() or "coalitions_legacy"
        db.execute(
            f"""
            SELECT c.id, c.name, COALESCE(SUM(p.population), 0) as total_pop
            FROM colNames c
            JOIN {members_tbl} m ON c.id = m.colid
            JOIN provinces p ON m.userid = p.userid
            GROUP BY c.id, c.name
            ORDER BY total_pop DESC
            LIMIT 15
            """
        )
        top_alliances = db.fetchall()

    return render_template(
        "rankings.html",
        top_population=top_population,
        top_military=top_military,
        top_wealth=top_wealth,
        top_alliances=top_alliances,
    )


def register_statistics_routes(app_instance):
    """Register all statistics routes with the Flask app instance"""
    app_instance.add_url_rule("/statistics", "statistics", statistics)
    app_instance.add_url_rule("/rankings", "rankings", rankings)
