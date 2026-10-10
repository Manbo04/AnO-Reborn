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
    # Hourly economy ticks: at most once per ~55 min, same as the hourly-gated
    # ticks below. These used to be 65-100s, which only stopped back-to-back
    # duplicates -- the global_tick watchdog or a deploy-boot nudge firing
    # 20-30 min after the scheduled run sailed through, so building upkeep was
    # billed (and production paid out) up to 6x in one hour (slotherer,
    # 2026-10-05: 24h upkeep in revenue history ~1.7x hourly x 24).
    "tax_income": int(os.getenv("TAX_INCOME_MIN_INTERVAL", "3300")),
    "population_growth": int(os.getenv("POP_GROWTH_MIN_INTERVAL", "3300")),
    "generate_province_revenue": int(os.getenv("PROV_REV_MIN_INTERVAL", "3300")),
    "produce_unit_stockpiles": int(os.getenv("UNIT_PRODUCTION_MIN_INTERVAL", "3300")),
    "execute_trade_agreements": int(os.getenv("TRADE_AGR_MIN_INTERVAL", "65")),
    "global_tick": int(os.getenv("GLOBAL_TICK_MIN_INTERVAL", "540")),
    # Military maintenance is deducted inside global_tick but must run at most
    # once per hour to match hourly production — otherwise upkeep is charged 6x
    # (global_tick fires every 10 min) and armies starve their own nations.
    "military_maintenance": int(os.getenv("MILITARY_MAINT_MIN_INTERVAL", "3300")),
    # War supply regen (see maintenance.py global_tick) is also hourly-gated,
    # same reasoning as military_maintenance above.
    "war_supply_regen": int(os.getenv("WAR_SUPPLY_REGEN_MIN_INTERVAL", "3300")),
    # Disasters are meant to fire at most once an hour per nation -- same
    # hourly-safety reasoning as military_maintenance/war_supply_regen.
    "natural_disasters": int(os.getenv("NATURAL_DISASTERS_MIN_INTERVAL", "3300")),
    # Loan interest is meant to be garnished at most once an hour per nation --
    # same hourly-safety reasoning as the other hourly-gated ticks above.
    "loan_interest": int(os.getenv("LOAN_INTEREST_MIN_INTERVAL", "3300")),
    # Bonds market interest/escrow/maturity settlement is meant to run at
    # most once a day per bond (Kurai's spec: interest deducted "on a daily
    # basis") -- generous buffer under 24h so scheduler drift can't skip a
    # whole day.
    "bond_tick": int(os.getenv("BOND_TICK_MIN_INTERVAL", "82800")),
    "assembly_tick": int(os.getenv("ASSEMBLY_TICK_MIN_INTERVAL", "300")),
    "war_auto_expiry": int(os.getenv("WAR_AUTO_EXPIRY_MIN_INTERVAL", "3300")),
}

# Ticks that must run AT MOST ONCE PER CALENDAR PERIOD (UTC). These are gated
# on the period a run claimed (task_runs.last_period), not on time since the
# last run: an elapsed-time window skipped a whole hour whenever a run was
# delayed (2-hour tax skip, 2026-10-03) and let late nudges/deploys bill an
# hour twice (upkeep up to 6x, 2026-10-05). See common.claim_tick_period().
TASK_PERIODS = {
    "tax_income": "hour",
    "generate_province_revenue": "hour",
    "population_growth": "hour",
    "produce_unit_stockpiles": "hour",
    "military_maintenance": "hour",
    "war_supply_regen": "hour",
    "natural_disasters": "hour",
    "loan_interest": "hour",
    "bond_tick": "day",
    # Value-moving jobs gated via common.run_once_per_period():
    "war_reparation_tax": "day",
    "manpower_increase": "hour",  # scheduled every 4h; hour gate stops duplicates
    "war_auto_expiry": "hour",
}

CELERY_BEAT_SCHEDULE = {
    "war_auto_expiry": {
        "task": "tasks.task_war_auto_expiry",
        "schedule": get_crontab_env("WAR_AUTO_EXPIRY_CRON", crontab(minute="50")),
    },
    "check_achievements": {
        "task": "tasks.task_check_achievements",
        "schedule": get_crontab_env("ACHIEVEMENTS_CRON", crontab(minute="*/30")),
    },

    "tax_income": {
        "task": "tasks.task_tax_income",
        "schedule": get_crontab_env("TAX_INCOME_CRON", crontab(minute="0")),
    },
    "generate_province_revenue": {
        "task": "tasks.task_generate_province_revenue",
        "schedule": get_crontab_env("PROV_REV_CRON", crontab(minute="25")),
    },
    "produce_unit_stockpiles": {
        "task": "tasks.task_produce_unit_stockpiles",
        "schedule": get_crontab_env("UNIT_PRODUCTION_CRON", crontab(minute="35")),
    },
    "population_growth": {
        "task": "tasks.task_population_growth",
        "schedule": get_crontab_env("POP_GROWTH_CRON", crontab(minute="45")),
    },
    "natural_disasters": {
        "task": "tasks.task_natural_disasters",
        "schedule": get_crontab_env("NATURAL_DISASTERS_CRON", crontab(minute="15")),
    },
    "loan_interest": {
        "task": "tasks.task_loan_interest",
        "schedule": get_crontab_env("LOAN_INTEREST_CRON", crontab(minute="40")),
    },
    "bond_tick": {
        "task": "tasks.task_bond_tick",
        "schedule": get_crontab_env("BOND_TICK_CRON", crontab(minute="50", hour="4")),
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
    # Recurring coalition bank trades (migration 0086): each trade keeps its
    # own schedule; this just picks up whatever is due.
    "recurring_bank_trades": {
        "task": "tasks.task_recurring_bank_trades",
        "schedule": get_crontab_env("RECURRING_BANK_TRADES_CRON", crontab(minute="7,22,37,52")),
    },
    # Automatic market orders (migration 0104): hourly, off the :00 rush.
    "market_auto_orders": {
        "task": "tasks.task_market_auto_orders",
        "schedule": get_crontab_env("MARKET_AUTO_ORDERS_CRON", crontab(minute="13")),
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
    "backup_database": {
        "task": "tasks.task_backup_database",
        "schedule": get_crontab_env("BACKUP_CRON", crontab(minute="10", hour="3")),
    },
    # Dormant until FEATURE_PATREON_GEMS=true -- see app_core/patreon/service.py.
        "assembly_tick": {
        "task": "tasks.task_assembly_tick",
        "schedule": get_crontab_env("ASSEMBLY_TICK_CRON", crontab(minute="*/5")),
    },
    "patreon_gem_grant": {
        "task": "tasks.task_patreon_gem_grant",
        "schedule": get_crontab_env(
            "PATREON_GEM_GRANT_CRON", crontab(minute="0", hour="12", day_of_month="1")
        ),
    },
}
