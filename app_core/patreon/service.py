"""Monthly Patreon -> Gems bonus.

Fetches active patrons from the Patreon API, matches each to an AnO
account via users.discord_id, and idempotently credits Gems for whatever
tier they're entitled to (per the admin-managed patreon_tiers table).

Dormant by default: FEATURE_PATREON_GEMS defaults false, and run() also
no-ops if PATREON_ACCESS_TOKEN/PATREON_CAMPAIGN_ID aren't set or
patreon_tiers is empty. Flip FEATURE_PATREON_GEMS=true only once the tier
table is seeded with real gem amounts and the API path has been verified
against the live campaign (see client.py docstring -- untested as of this
writing).
"""
import logging
import os
from datetime import datetime, timezone

from database import get_db_cursor

from . import client, repositories

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


FEATURE_PATREON_GEMS = _env_flag("FEATURE_PATREON_GEMS", "false")


def _empty_summary() -> dict:
    return {
        "granted": 0,
        "gems_total": 0,
        "no_discord_link": 0,
        "unmatched_tier": 0,
        "no_ano_account": 0,
        "already_granted": 0,
        "errors": 0,
    }


def run(period: str = None) -> dict:
    """Grants this month's Gems bonus to linked, active patrons.

    Safe to call more than once for the same period (task retry, manual
    re-run) -- each grant is individually idempotent. Never raises for
    "nothing to do" conditions (feature off, not configured, no tiers, API
    failure); a per-member error is logged and skipped rather than aborting
    the whole run.
    """
    summary = _empty_summary()

    if not FEATURE_PATREON_GEMS:
        logger.info("[patreon_gems] FEATURE_PATREON_GEMS is off, skipping")
        return summary
    if not client.is_configured():
        logger.warning(
            "[patreon_gems] PATREON_ACCESS_TOKEN/PATREON_CAMPAIGN_ID not set, skipping"
        )
        return summary

    period = period or datetime.now(timezone.utc).strftime("%Y-%m")

    with get_db_cursor(read_only=True) as db:
        tiers = {title: gems for title, gems in repositories.get_active_tiers(db)}
    if not tiers:
        logger.warning("[patreon_gems] no active rows in patreon_tiers, skipping")
        return summary

    members = client.fetch_active_members()
    if members is None:
        logger.error("[patreon_gems] Patreon API fetch failed, skipping this run entirely")
        return summary

    # A patron can appear once per entitled tier if they're stacked on
    # multiple -- keep only the highest-value matching tier per patron.
    best_by_member = {}
    for m in members:
        gems = tiers.get(m["tier_title"])
        if gems is None:
            summary["unmatched_tier"] += 1
            continue
        current = best_by_member.get(m["member_id"])
        if current is None or gems > current["gems"]:
            best_by_member[m["member_id"]] = {**m, "gems": gems}

    for m in best_by_member.values():
        if not m["discord_id"]:
            summary["no_discord_link"] += 1
            continue
        try:
            with get_db_cursor() as db:
                user_id = repositories.get_user_id_by_discord_id(db, m["discord_id"])
                if user_id is None:
                    summary["no_ano_account"] += 1
                    continue
                credited = repositories.grant_monthly_gems(
                    db, user_id, m["member_id"], m["tier_title"], period, m["gems"]
                )
        except Exception:
            logger.exception(
                "[patreon_gems] failed to grant member_id=%s", m["member_id"]
            )
            summary["errors"] += 1
            continue

        if credited:
            summary["granted"] += 1
            summary["gems_total"] += m["gems"]
        else:
            summary["already_granted"] += 1

    logger.info("[patreon_gems] period=%s %s", period, summary)
    return summary
