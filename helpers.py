# FULLY MIGRATED

from datetime import date
from functools import wraps
from typing import Callable, TypeVar, Any
from typing import ParamSpec

from dotenv import load_dotenv
from flask import redirect, render_template, request, session

from database import get_db_cursor, query_cache

# Generic parameterization for decorator typing
P = ParamSpec("P")
R = TypeVar("R")

load_dotenv()


def get_date() -> str:
    """Return today's date as YYYY-MM-DD."""
    today = date.today()
    return today.strftime("%Y-%m-%d")


def get_flagname(user_id: int) -> str:
    """Return the cached flag name for a user, populating the cache if needed."""
    cache_key = f"flag_{user_id}"
    cached = query_cache.get(cache_key)
    # Ensure the cached value is a string before returning it to satisfy type checks
    if isinstance(cached, str):
        return cached

    with get_db_cursor() as db:
        db.execute("SELECT flag FROM users WHERE id=(%s)", (user_id,))
        row = db.fetchone()
        flag_name = row[0] if row else None

        if flag_name is None:
            flag_name = "default_flag.jpg"

        query_cache.set(cache_key, flag_name)
        return flag_name


def login_required(f: Callable[P, R]) -> Callable[P, Any]:
    """Decorator that redirects unauthenticated users to /login.

    This is typed with ParamSpec so that the decorated function preserves
    the original callable signature for static type checkers.
    """

    @wraps(f)
    def decorated_function(*args: P.args, **kwargs: P.kwargs) -> Any:
        import logging

        logger = logging.getLogger(__name__)
        if not session.get("user_id", None):
            logger.debug(
                "login_required: session user_id=%s path=%s",
                session.get("user_id", None),
                getattr(request, "path", None),
            )
            logger.debug("login_required: user_id missing, redirecting to /login")
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


# Check for necessary values without them user can't access a page
def check_required(func: Callable[P, R]) -> Callable[P, Any]:
    @wraps(func)
    def check_session(*args: P.args, **kwargs: P.kwargs) -> Any:
        if not session.get("enemy_id", None):
            return redirect("/wars")
        return func(*args, **kwargs)

    return check_session


def error(code: int, message: str) -> tuple[Any, int]:
    """Return the error template and HTTP status code."""
    return render_template("error.html", code=code, message=message), code


def get_influence(country_id: int) -> int:
    """Compute and cache an influence score for a country."""
    cache_key = f"influence_{country_id}"
    cached = query_cache.get(cache_key)
    # Only accept cached integers to satisfy the declared return type
    if isinstance(cached, int):
        return cached

    cId = country_id

    with get_db_cursor() as db:
        try:
            db.execute(
                (
                    "SELECT soldiers, artillery, tanks, fighters, bombers, apaches, "
                    "submarines, destroyers, cruisers, ICBMs, nukes, spies "
                    "FROM military WHERE id=%s"
                ),
                (cId,),
            )
            military = db.fetchall()[0]

            soldiers_score = military[0] * 0.02
            artillery_score = military[1] * 1.6
            tanks_score = military[2] * 0.8
            fighters_score = military[3] * 3.5
            bombers_score = military[4] * 2.5
            apaches_score = military[5] * 3.2
            submarines_score = military[6] * 4.5
            destroyers_score = military[7] * 3
            cruisers_score = military[8] * 5.5
            icbms_score = military[9] * 250
            nukes_score = military[10] * 500
            spies_score = military[11] * 25
        except Exception:
            tanks_score = 0
            soldiers_score = 0
            artillery_score = 0
            bombers_score = 0
            fighters_score = 0
            apaches_score = 0
            destroyers_score = 0
            cruisers_score = 0
            submarines_score = 0
            spies_score = 0
            icbms_score = 0
            nukes_score = 0
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Couldn't get military data for user id: {cId}")

        try:
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
            money_score = int(db.fetchone()[0]) * 0.00001
        except Exception:
            money_score = 0

        try:
            db.execute("SELECT SUM(cityCount) FROM provinces WHERE userId=(%s)", (cId,))
            cities_score = int(db.fetchone()[0]) * 10
        except Exception:
            cities_score = 0

        try:
            db.execute("SELECT COUNT(id) FROM provinces WHERE userId=(%s)", (cId,))
            provinces_score = int(db.fetchone()[0]) * 300
        except Exception:
            provinces_score = 0

        try:
            db.execute("SELECT SUM(land) FROM provinces WHERE userId=%s", (cId,))
            land_score = db.fetchone()[0] * 10
        except Exception:
            land_score = 0

        try:
            db.execute(
                (
                    "SELECT oil + rations + coal + uranium + bauxite + iron + lead + "
                    "copper + lumber + components + steel, consumer_goods + "
                    "aluminium + gasoline + ammunition FROM resources "
                    "WHERE id=%s"
                ),
                (cId,),
            )
            resources_score = db.fetchone()[0] * 0.001
        except Exception:
            resources_score = 0

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

    query_cache.set(cache_key, influence)
    return influence


def get_coalition_influence(coalition_id: int) -> int:
    with get_db_cursor() as db:
        total_influence = 0

        try:
            db.execute(
                "SELECT userId FROM coalitions WHERE colId=(%s)", (coalition_id,)
            )
            members = db.fetchall()
        except Exception:
            return 0

        for member in members:
            # fetched rows are untyped; coerce the user id to int for typing
            member_id = int(member[0])
            member_influence = get_influence(member_id)
            total_influence += member_influence

        return int(total_influence)
