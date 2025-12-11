from flask import request, render_template, session
from helpers import login_required
from database import get_db_cursor
from app import app

@app.route("/statistics")
@login_required
def statistics():
    """Display market statistics and nation stats"""

    with get_db_cursor() as db:
        # Get market statistics for different resources
        resources = ['rations', 'oil', 'coal', 'uranium', 'steel', 'aluminium', 'lumber']

        market_stats = {}

        for resource in resources:
            # Get average price
            db.execute("""
                SELECT AVG(price) as avg_price
                FROM offers
                WHERE resource = %s AND type = 'sell'
            """, (resource,))
            avg_result = db.fetchone()
            avg_price = round(avg_result[0]) if avg_result[0] else 0

            # Get highest price
            db.execute("""
                SELECT MAX(price) as max_price
                FROM offers
                WHERE resource = %s AND type = 'sell'
            """, (resource,))
            max_result = db.fetchone()
            max_price = max_result[0] if max_result[0] else 0

            # Get lowest price
            db.execute("""
                SELECT MIN(price) as min_price
                FROM offers
                WHERE resource = %s AND type = 'sell'
            """, (resource,))
            min_result = db.fetchone()
            min_price = min_result[0] if min_result[0] else 0

            market_stats[resource] = {
                'avg': avg_price,
                'max': max_price,
                'min': min_price
            }

        # Get some basic nation statistics
        db.execute("""
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
        """)
        nation_stats = db.fetchone()
        total_nations = nation_stats[0] if nation_stats[0] else 0
        avg_influence = round(nation_stats[1]) if nation_stats[1] else 0
        max_influence = nation_stats[2] if nation_stats[2] else 0

    return render_template("statistics.html",
                         market_stats=market_stats,
                         total_nations=total_nations,
                         avg_influence=avg_influence,
                         max_influence=max_influence)