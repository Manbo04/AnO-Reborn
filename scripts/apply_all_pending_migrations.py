#!/usr/bin/env python3
"""Apply SQL migrations idempotently (production maintenance).

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_all_pending_migrations.py
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_all_pending_migrations.py --dry-run
"""


import argparse
import re
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Order matters; 0001-0010 assumed applied on long-lived prod DBs.
MIGRATION_FILES = [
    "0011_add_users_last_active.sql",
    "0012_add_join_number.sql",
    "0013_add_demographics_education_schema.sql",
    "0015_add_hotpath_indexes.sql",
    "0016_add_market_offer_hotpath_indexes.sql",
    "0017_add_performance_indexes.sql",
    "0018_cleanup_indexes_add_spyinfo.sql",
    "0019_fix_maintenance_costs.sql",
    "0020_enforce_population_demographics_sync.sql",
    "0021_coalition_members_and_discord_compat.sql",
    "0022_discord_bot.sql",
    "0023_discord_guild_panels.sql",
    "0024_nextjs_compat_views.sql",
    "0025_tech_tree_prerequisites.sql",
    "0026_fix_building_costs.sql",
    "0027_deprecate_distribution_centers.sql",
    "0028_add_world_map_nodes.sql",
    "0029_optimize_queries.sql",
    "0030_tutorial_rewards.sql",
    "0030_world_map_tiers.sql",
    "0031_advertisements.sql",
    "0032_poll_votes.sql",
    "0033_optimize_schema.sql",
    "0034_add_users_recovery_key.sql",
    "0035_add_provinces_image_data.sql",
    "0036_referrals.sql",
    "0030_add_furnace_projects.sql",
    "0039_add_food_banks.sql",
    "0040_rebalance_naval_special_costs.sql",
    "0041_discord_analytics_panel.sql",
    "0042_coalition_invites.sql",
    "0043_planes_missiles_use_aluminium.sql",
    "0044_military_stat_rebalance.sql",
    "0045_add_login_events.sql",
    "0048_add_store_gems_cosmetics.sql",
    "0049_seed_store_catalog.sql",
    "0050_fix_coalition_messages_fk.sql",
    "0051_nukes_require_uranium.sql",
    "0052_add_patreon_gems.sql",
    "0053_seed_patreon_tiers.sql",
    "0054_seed_patreon_tier_elite.sql",
    "0055_seed_patreon_tier_high_council.sql",
    "0056_widen_users_description.sql",
    "0057_add_global_chat.sql",
    "0058_add_devlog_and_discussions.sql",
    "0059_coalition_members_joined_at.sql",
    "0060_add_login_verifications.sql",
    "0061_add_store_cosmetic_types.sql",
    "0062_seed_store_cosmetic_catalog.sql",
    "0063_add_bmc_gem_purchases.sql",
    "0064_seed_bmc_gem_package_ids.sql",
    "0065_reactivate_distribution_centers.sql",
    "0066_drone_missile_carrier_units.sql",
    "0067_login_verifications_delivered.sql",
    "0068_add_users_session_epoch.sql",
    "0069_add_user_loans.sql",
    "0070_add_totp_2fa.sql",
    "0071_add_bounties_and_world_events.sql",
    "0072_buff_aircraft_carrier_attack.sql",
    "0073_nation_customization_fields.sql",
    "0074_seed_title_conqueror_of_worlds.sql",
    "0075_add_tutorial_step.sql",
    "0076_add_market_embargoes.sql",
    "0077_add_ads_image_data.sql",
    "0078_seed_molten_forge_background.sql",
    "0079_add_national_currency.sql",
    "0080_add_bonds_market.sql",
    "0081_add_war_last_attack_resolved_at.sql",
    "0082_coalition_bank_trades_and_bond_insurance.sql",
    "0083_add_currency_unions.sql",
    "0084_add_sam_battery.sql",
    "0085_spy_op_types_and_counter_intel.sql",
    "0086_coalition_recurring_trades_etc.sql",
    "0087_add_nation_revenue_history.sql",
    "0089_nuclear_strikes.sql",
    "0091_currency_market.sql",
    "0093.sql",
    "0094.sql",
    "0095_achievements.sql",
    "0096_cg_chains.sql",
    "0097_spyinfo_sam_batteries.sql",
    "0098_player_analytics.sql",
    "0099_backfill_discord_id.sql",
    "0100_add_news_is_read.sql",
    "0101_reimburse_24h_revenue.sql",
    "0102_personal_bank_accounts.sql",
    "0103_personal_bank_balance_from_log.sql",
    # Shipped 2026-10-04 but never added here; 0104/0106 were applied by hand,
    # 0105 never ran (spyinfo.iron_domes missing -> spy reports 500).
    "0104_iron_dome.sql",
    "0104_market_rework.sql",
    "0105_spyinfo_iron_domes.sql",
    "0106_population_growth_freezes.sql",
]

# Files that predate tracking (applied long ago or by hand) and must never be
# re-run automatically. Frozen: do not add to this set.
PRE_TRACKING_FILES = {
    "0001_add_province_delete_audit.sql",
    "0002_EXECUTION_LOG.txt",
    "0002_normalize_economy_military.sql",
    "0003_normalize_diplomacy_market.sql",
    "0004_normalize_infrastructure_tech.sql",
    "0005_finalize_normalized_cleanup.sql",
    "0006_add_game_tick_logs.sql",
    "0007_seed_unit_dictionary.sql",
    "0008_add_unique_dictionary_names.sql",
    "0009_add_stats_manpower.sql",
    "0010_add_stats_default_defense.sql",
    "0014_rebalance_unit_upkeep_costs.sql",
    "0037_add_province_coordinates.sql",
    "0038_game_map.sql",
    "0046_backfill_legacy_tech_descriptions.sql",
    "0047_add_chat_and_direct_messages.sql",
    "010_economy_rebalance.py",
    "011_sanitize_duplicates.py",
    "012_add_province_id_to_user_buildings.py",
    "016_add_coalition_tax_rate.sql",
}

# NEW migrations: name them YYYYMMDD_HHMM_short_name.sql (UTC). They are picked
# up automatically, in name order, after MIGRATION_FILES -- no list to edit, and
# two sessions can no longer grab the same number (0030 x3, 0104 x2 happened).
NEW_MIGRATION_RE = re.compile(r"^\d{8}_\d{4}_[a-z0-9_]+\.sql$")


def discover_new_migrations() -> list:
    return sorted(
        f.name
        for f in (ROOT / "migrations").iterdir()
        if NEW_MIGRATION_RE.match(f.name)
    )


def check_names() -> list:
    """Return problems with migration file naming (used by CI)."""
    problems = []
    known = set(MIGRATION_FILES) | PRE_TRACKING_FILES
    for f in sorted((ROOT / "migrations").iterdir()):
        name = f.name
        if name.startswith("._") or name in known or NEW_MIGRATION_RE.match(name):
            continue
        problems.append(
            f"migrations/{name}: new migrations must be named "
            "YYYYMMDD_HHMM_short_name.sql (UTC time, lowercase)"
        )
    return problems


def _ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name VARCHAR(128) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _already_applied(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (name,))
    return cur.fetchone() is not None


def _mark_applied(cur, name: str) -> None:
    cur.execute(
        """
        INSERT INTO schema_migrations (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """,
        (name,),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any migration fails (CI); production boot stays lenient",
    )
    parser.add_argument(
        "--check-names", action="store_true", help="only validate migration file names"
    )
    args = parser.parse_args()

    if args.check_names:
        problems = check_names()
        for p in problems:
            print("ERROR", p)
        sys.exit(1 if problems else 0)

    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    if not args.dry_run:
        _ensure_migration_table(cur)

    failed = []
    for name in MIGRATION_FILES + discover_new_migrations():
        path = ROOT / "migrations" / name
        if not path.exists():
            print(f"SKIP missing {name}")
            continue
        if not args.dry_run and _already_applied(cur, name):
            print(f"SKIP already applied {name}")
            continue
        sql = path.read_text()
        print(f"{'[dry-run] ' if args.dry_run else ''}Applying {name}...")
        if not args.dry_run:
            try:
                cur.execute(sql)
                _mark_applied(cur, name)
            except Exception as exc:
                print(f"  WARN {name}: {exc}")
                failed.append(name)
                conn.rollback()
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass

    if not args.dry_run:
        from database import ensure_schema_compat

        ensure_schema_compat()
        print("Ran ensure_schema_compat()")

    cur.close()
    conn.close()
    if failed:
        print(f"FAILED migrations: {', '.join(failed)}")
        if args.strict:
            sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
