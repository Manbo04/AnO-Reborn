"""Celery beat schedule and task timing thresholds (extracted from tasks.py)."""
from __future__ import annotations

import os

from celery.schedules import crontab


def get_crontab_env(var: str, default):
    val = os.getenv(var)
    if val:
        return crontab(minute=val)
    return default


TASK_RUN_THRESHOLDS = {
    "tax_income": int(os.getenv("TAX_INCOME_MIN_INTERVAL", "65")),
    "population_growth": int(os.getenv("POP_GROWTH_MIN_INTERVAL", "100")),
    "generate_province_revenue": int(os.getenv("PROV_REV_MIN_INTERVAL", "100")),
    "execute_trade_agreements": int(os.getenv("TRADE_AGR_MIN_INTERVAL", "65")),
    "global_tick": int(os.getenv("GLOBAL_TICK_MIN_INTERVAL", "540")),
    # Military maintenance is deducted inside global_tick but must run at most
    # once per hour to match hourly production — otherwise upkeep is charged 6x
    # (global_tick fires every 10 min) and armies starve their own nations.
    "military_maintenance": int(os.getenv("MILITARY_MAINT_MIN_INTERVAL", "3300")),
    # War supply regen (see maintenance.py global_tick) is also hourly-gated,
    # same reasoning as military_maintenance above.
    "war_supply_regen": int(os.getenv("WAR_SUPPLY_REGEN_MIN_INTERVAL", "3300")),
}

CELERY_BEAT_SCHEDULE = {
    "tax_income": {
        "task": "tasks.task_tax_income",
        "schedule": get_crontab_env("TAX_INCOME_CRON", crontab(minute="0")),
    },
    "generate_province_revenue": {
        "task": "tasks.task_generate_province_revenue",
        "schedule": get_crontab_env("PROV_REV_CRON", crontab(minute="25")),
    },
    "population_growth": {
        "task": "tasks.task_population_growth",
        "schedule": get_crontab_env("POP_GROWTH_CRON", crontab(minute="45")),
    },
    "war_reparation_tax": {
        "task": "tasks.task_war_reparation_tax",
        "schedule": get_crontab_env("WAR_REP_CRON", crontab(minute="0", hour="0")),
    },
    "manpower_increase": {
        "task": "tasks.task_manpower_increase",
        "schedule": get_crontab_env("MANPOWER_CRON", crontab(minute="5", hour="*/4")),
    },
    "backfill_missing_resources": {
        "task": "tasks.task_backfill_missing_resources",
        "schedule": get_crontab_env("BACKFILL_CRON", crontab(minute="15", hour="1")),
    },
    "cleanup_orphan_user_rows": {
        "task": "tasks.task_cleanup_orphan_user_rows",
        "schedule": get_crontab_env("ORPHAN_CLEANUP_CRON", crontab(minute="10", hour="1")),
    },
    "refresh_bot_offers": {
        "task": "tasks.task_refresh_bot_offers",
        "schedule": get_crontab_env("BOT_OFFERS_CRON", crontab(minute="*/5")),
    },
    "execute_trade_agreements": {
        "task": "tasks.task_execute_trade_agreements",
        "schedule": get_crontab_env("TRADE_AGR_CRON", crontab(minute="*/15")),
    },
    "global_tick": {
        "task": "tasks.task_global_tick",
        "schedule": get_crontab_env("GLOBAL_TICK_CRON", crontab(minute="*/10")),
    },
    "cleanup_old_spyinfo": {
        "task": "tasks.task_cleanup_old_spyinfo",
        "schedule": get_crontab_env("SPYINFO_CLEANUP_CRON", crontab(minute="30", hour="2")),
    },
    "economy_snapshot": {
        "task": "tasks.task_economy_snapshot",
        "schedule": get_crontab_env("ECONOMY_SNAPSHOT_CRON", crontab(minute="0", hour="*/1")),
    },
    "ai_agent": {
        "task": "tasks.task_ai_agent",
        "schedule": get_crontab_env("AI_AGENT_CRON", crontab(minute="30", hour="*/1")),
    },
    "update_war_supplies": {
        "task": "tasks.task_update_war_supplies",
        "schedule": get_crontab_env("WAR_SUPPLIES_CRON", crontab(minute="55")),
    },
    # Dormant until FEATURE_PATREON_GEMS=true -- see app_core/patreon/service.py.
    "patreon_gem_grant": {
        "task": "tasks.task_patreon_gem_grant",
        "schedule": get_crontab_env(
            "PATREON_GEM_GRANT_CRON", crontab(minute="0", hour="12", day_of_month="1")
        ),
    },
}
