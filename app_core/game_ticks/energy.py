from celery import Celery
import psycopg2
import os
import time
import logging
from dotenv import load_dotenv
from attack_scripts import Economy
import math
from celery.schedules import crontab
import variables
import redis

logger = logging.getLogger(__name__)

load_dotenv()
import config  # Parse Railway environment variables  # noqa: E402

# Toggle noisy per-building revenue logs (default off in production)
VERBOSE_REVENUE_LOGS = os.getenv("VERBOSE_REVENUE_LOGS") == "1"

from app_core.celery_schedule import CELERY_BEAT_SCHEDULE, TASK_RUN_THRESHOLDS

# Mapping from normalized building names to produced resource names.
# Used by the global tick economy engine.
# NOTE: BUILDING_PRODUCTION_RESOURCE_MAP was removed.  These buildings are
# now handled exclusively by generate_province_revenue() (hourly) which
# enforces energy, gold upkeep, and input-resource checks.  Having them
# here too caused DOUBLE production and free resources (steel mills
# produced steel without consuming coal/iron, etc.).
BUILDING_PRODUCTION_RESOURCE_MAP = {}


redis_url = config.get_redis_url()
celery = Celery("app", broker=redis_url)
celery.conf.update(
    broker_url=redis_url, result_backend=redis_url, CELERY_BROKER_URL=redis_url
)

celery.conf.update(
    timezone="UTC",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule=CELERY_BEAT_SCHEDULE,
)


# Centralized helper for last_run threshold check



# Returns energy production and consumption from a certain province
def energy_info(province_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        production = 0
        consumption = 0

        consumers = variables.ENERGY_CONSUMERS
        producers = variables.ENERGY_UNITS

        infra = variables.NEW_INFRA

        # Fetch building quantities from user_buildings for THIS province
        db.execute(
            """
            SELECT bd.name, ub.quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.province_id = %s AND bd.name IN %s
            """,
            (province_id, tuple(consumers + producers)),
        )
        rows = db.fetchall()
        result_dict = {row[0]: row[1] for row in rows} if rows else {}
        result = tuple(result_dict.get(name, 0) for name in consumers + producers)

        if not result:
            return 0, 0

        # Calculate consumption from first N fields
        consumption = sum(result[: len(consumers)])

        # Calculate production from remaining fields
        for idx, producer in enumerate(producers):
            producer_count = result[len(consumers) + idx]
            production += producer_count * infra[producer]["plus"]["energy"]

        return consumption, production




# Returns an energy score for a user, from -1 to -1.6
# -1 = Enough or more than enough energy
# -1.6 = No energy at all
def energy_stats(user_id):
    from database import get_db_cursor

    with get_db_cursor() as db:
        # Get all province IDs in one query
        db.execute("SELECT id FROM provinces WHERE userId=%s", (user_id,))
        provinces = db.fetchall()

        total_energy_consumption = 0
        total_energy_production = 0

        for province_id in provinces:
            province_id = province_id[0]

            consumption, production = energy_info(province_id)
            total_energy_consumption += consumption
            total_energy_production += production

    if total_energy_consumption == 0:
        total_energy_consumption = 1

    tcp = (
        total_energy_production / total_energy_consumption
    ) - 1  # Normalizes the score to 0.
    if tcp > 0:
        tcp = 0

    score = -1 + (tcp * variables.NO_ENERGY_TAX_MULTIPLIER)

    return score


