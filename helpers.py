# FULLY MIGRATED

import os
from flask import redirect, render_template, session, request
from functools import wraps, lru_cache
from dotenv import load_dotenv
from datetime import date
from database import get_db_cursor, query_cache

load_dotenv()


def get_date():
    today = date.today()
    return today.strftime("%Y-%m-%d")


def get_flagname(user_id):
    # Check cache first
    cache_key = f"flag_{user_id}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    # Query if not cached
    with get_db_cursor() as db:
        db.execute("SELECT flag FROM users WHERE id=(%s)", (user_id,))
        flag_name = db.fetchone()[0]

        if flag_name == None:
            flag_name = "default_flag.jpg"

        # Cache the result
        query_cache.set(cache_key, flag_name)
        return flag_name


def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        import logging

        logger = logging.getLogger(__name__)
        if not session.get("user_id", None):
            logger.debug(
                f"login_required: session user_id={session.get('user_id', None)} path={getattr(request, 'path', None)}"
            )
            logger.debug("login_required: user_id missing, redirecting to /login")
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


# Check for neccessary values without them user can't access a page
# example: can't access /warchoose or /waramount without enemy_id
def check_required(func):
    @wraps(func)
    def check_session(*args, **kwargs):
        if not session.get("enemy_id", None):
            return redirect("/wars")
        return func(*args, **kwargs)

    return check_session


def error(code, message):
    # Return the proper HTTP status code along with the error template to
    # ensure external clients receive the correct status for assertion checks
    return render_template("error.html", code=code, message=message), code


def get_influence(country_id):
    # Check cache first
    cache_key = f"influence_{country_id}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    cId = country_id

    with get_db_cursor() as db:
        # OPTIMIZED: Single query instead of 6 separate queries
        db.execute(
            """
            SELECT
                COALESCE(m.soldiers, 0) as soldiers,
                COALESCE(m.artillery, 0) as artillery,
                COALESCE(m.tanks, 0) as tanks,
                COALESCE(m.fighters, 0) as fighters,
                COALESCE(m.bombers, 0) as bombers,
                COALESCE(m.apaches, 0) as apaches,
                COALESCE(m.submarines, 0) as submarines,
                COALESCE(m.destroyers, 0) as destroyers,
                COALESCE(m.cruisers, 0) as cruisers,
                COALESCE(m.ICBMs, 0) as icbms,
                COALESCE(m.nukes, 0) as nukes,
                COALESCE(m.spies, 0) as spies,
                COALESCE(s.gold, 0) as gold,
                COALESCE(prov.city_count, 0) as city_count,
                COALESCE(prov.province_count, 0) as province_count,
                COALESCE(prov.total_land, 0) as total_land,
                COALESCE(r.total_resources, 0) as total_resources
            FROM users u
            LEFT JOIN military m ON u.id = m.id
            LEFT JOIN stats s ON u.id = s.id
            LEFT JOIN (
                SELECT userId,
                       SUM(cityCount) as city_count,
                       COUNT(id) as province_count,
                       SUM(land) as total_land
                FROM provinces
                GROUP BY userId
            ) prov ON u.id = prov.userId
            LEFT JOIN (
                SELECT id,
                       (oil + rations + coal + uranium + bauxite + iron + lead + copper + lumber + components + steel + consumer_goods + aluminium + gasoline + ammunition) as total_resources
                FROM resources
            ) r ON u.id = r.id
            WHERE u.id = %s
            """,
            (cId,),
        )
        result = db.fetchone()

        if not result:
            query_cache.set(cache_key, 0)
            return 0

        (
            soldiers,
            artillery,
            tanks,
            fighters,
            bombers,
            apaches,
            submarines,
            destroyers,
            cruisers,
            icbms,
            nukes,
            spies,
            gold,
            city_count,
            province_count,
            total_land,
            total_resources,
        ) = result

        # Calculate influence scores
        soldiers_score = soldiers * 0.02
        artillery_score = artillery * 1.6
        tanks_score = tanks * 0.8
        fighters_score = fighters * 3.5
        bombers_score = bombers * 2.5
        apaches_score = apaches * 3.2
        submarines_score = submarines * 4.5
        destroyers_score = destroyers * 3
        cruisers_score = cruisers * 5.5
        icbms_score = icbms * 250
        nukes_score = nukes * 500
        spies_score = spies * 25
        money_score = gold * 0.00001
        cities_score = city_count * 10
        provinces_score = province_count * 300
        land_score = total_land * 10
        resources_score = total_resources * 0.001

    """
    (# of provinces * 300)+(# of soldiers * 0.02)+(# of artillery*1.6)+(# of tanks*0.8)
    +(# of fighters* 3.5)+(# of bombers *2.5)+(# of apaches *3.2)+(# of subs * 4.5)+
    (# of destroyers *3.0)+(# of cruisers *5.5) + (# of ICBMS*250)+(# of Nukes * 500)
    + (# of spies*25) + (# of total cities * 10) + (# of total land * 10)+
    (total number of rss *0.001)+(total amount of money*0.00001)
    """

    influence = (
        provinces_score
        + soldiers_score
        + artillery_score
        + tanks_score
        + fighters_score
        + bombers_score
        + apaches_score
        + submarines_score
        + destroyers_score
        + cruisers_score
        + icbms_score
        + nukes_score
        + spies_score
        + cities_score
        + land_score
        + resources_score
        + money_score
    )

    influence = round(influence)

    # Cache the result
    query_cache.set(cache_key, influence)

    return influence


def get_bulk_influence(user_ids):
    """
    Calculate influence for multiple users in a single query.
    Returns a dict mapping user_id -> influence score.
    Much faster than calling get_influence() in a loop.
    """
    if not user_ids:
        return {}

    # Check cache first for all users
    results = {}
    uncached_ids = []
    for uid in user_ids:
        cache_key = f"influence_{uid}"
        cached = query_cache.get(cache_key)
        if cached is not None:
            results[uid] = cached
        else:
            uncached_ids.append(uid)

    if not uncached_ids:
        return results

    with get_db_cursor() as db:
        # Bulk query for all uncached users at once
        db.execute(
            """
            SELECT
                u.id,
                COALESCE(m.soldiers, 0) as soldiers,
                COALESCE(m.artillery, 0) as artillery,
                COALESCE(m.tanks, 0) as tanks,
                COALESCE(m.fighters, 0) as fighters,
                COALESCE(m.bombers, 0) as bombers,
                COALESCE(m.apaches, 0) as apaches,
                COALESCE(m.submarines, 0) as submarines,
                COALESCE(m.destroyers, 0) as destroyers,
                COALESCE(m.cruisers, 0) as cruisers,
                COALESCE(m.ICBMs, 0) as icbms,
                COALESCE(m.nukes, 0) as nukes,
                COALESCE(m.spies, 0) as spies,
                COALESCE(s.gold, 0) as gold,
                COALESCE(prov.city_count, 0) as city_count,
                COALESCE(prov.province_count, 0) as province_count,
                COALESCE(prov.total_land, 0) as total_land,
                COALESCE(r.total_resources, 0) as total_resources
            FROM users u
            LEFT JOIN military m ON u.id = m.id
            LEFT JOIN stats s ON u.id = s.id
            LEFT JOIN (
                SELECT userId,
                       SUM(cityCount) as city_count,
                       COUNT(id) as province_count,
                       SUM(land) as total_land
                FROM provinces
                GROUP BY userId
            ) prov ON u.id = prov.userId
            LEFT JOIN (
                SELECT id,
                       (oil + rations + coal + uranium + bauxite + iron + lead + copper + lumber + components + steel + consumer_goods + aluminium + gasoline + ammunition) as total_resources
                FROM resources
            ) r ON u.id = r.id
            WHERE u.id = ANY(%s)
            """,
            (uncached_ids,),
        )
        rows = db.fetchall()

        for row in rows:
            (
                user_id,
                soldiers,
                artillery,
                tanks,
                fighters,
                bombers,
                apaches,
                submarines,
                destroyers,
                cruisers,
                icbms,
                nukes,
                spies,
                gold,
                city_count,
                province_count,
                total_land,
                total_resources,
            ) = row

            # Calculate influence
            influence = round(
                province_count * 300
                + soldiers * 0.02
                + artillery * 1.6
                + tanks * 0.8
                + fighters * 3.5
                + bombers * 2.5
                + apaches * 3.2
                + submarines * 4.5
                + destroyers * 3
                + cruisers * 5.5
                + icbms * 250
                + nukes * 500
                + spies * 25
                + city_count * 10
                + total_land * 10
                + total_resources * 0.001
                + gold * 0.00001
            )

            results[user_id] = influence
            query_cache.set(f"influence_{user_id}", influence)

    return results


def get_coalition_influence(coalition_id):
    with get_db_cursor() as db:
        total_influence = 0

        try:
            db.execute(
                "SELECT userId FROM coalitions WHERE colId=(%s)", (coalition_id,)
            )
            members = db.fetchall()
        except:
            return 0

        for member in members:
            member_influence = get_influence(member[0])
            total_influence += member_influence

        return total_influence
