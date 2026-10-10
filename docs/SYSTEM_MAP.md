# AnO system map (generated -- do not edit by hand)

Rebuilt from the code by `scripts/generate_system_map.py`; CI fails if it is stale.
Intent and game rules live in `docs/GAME_RULES.md`; this file says **where** things are.

## 1. Background jobs (Celery beat)

Gate: **per hour/day** = runs at most once per UTC period (`task_runs.last_period`,
claimed before work -- see `app_core/game_ticks/common.py::claim_tick_period`);
**min interval** = skips if `task_runs.last_run` is more recent than that.

| beat entry | task | schedule (UTC) | gate |
|---|---|---|---|
| ai_agent | `tasks.task_ai_agent` | `30 */1 * * *` | none (must be idempotent) |
| assembly_tick | `tasks.task_assembly_tick` | `*/5 * * * *` | min interval 300s |
| backfill_missing_resources | `tasks.task_backfill_missing_resources` | `15 1 * * *` | none (must be idempotent) |
| backup_database | `tasks.task_backup_database` | `10 3 * * *` | none (must be idempotent) |
| bond_tick | `tasks.task_bond_tick` | `50 4 * * *` | per day |
| check_achievements | `tasks.task_check_achievements` | `*/30 * * * *` | none (must be idempotent) |
| cleanup_old_spyinfo | `tasks.task_cleanup_old_spyinfo` | `30 2 * * *` | none (must be idempotent) |
| cleanup_orphan_user_rows | `tasks.task_cleanup_orphan_user_rows` | `10 1 * * *` | none (must be idempotent) |
| economy_snapshot | `tasks.task_economy_snapshot` | `0 */1 * * *` | none (must be idempotent) |
| execute_trade_agreements | `tasks.task_execute_trade_agreements` | `*/15 * * * *` | min interval 65s |
| generate_province_revenue | `tasks.task_generate_province_revenue` | `25 * * * *` | per hour |
| global_tick | `tasks.task_global_tick` | `*/10 * * * *` | min interval 540s |
| loan_interest | `tasks.task_loan_interest` | `40 * * * *` | per hour |
| manpower_increase | `tasks.task_manpower_increase` | `5 */4 * * *` | per hour |
| market_auto_orders | `tasks.task_market_auto_orders` | `13 * * * *` | none (must be idempotent) |
| natural_disasters | `tasks.task_natural_disasters` | `15 * * * *` | per hour |
| patreon_gem_grant | `tasks.task_patreon_gem_grant` | `0 12 * 1 *` | none (must be idempotent) |
| population_growth | `tasks.task_population_growth` | `45 * * * *` | per hour |
| produce_unit_stockpiles | `tasks.task_produce_unit_stockpiles` | `35 * * * *` | per hour |
| recurring_bank_trades | `tasks.task_recurring_bank_trades` | `7,22,37,52 * * * *` | none (must be idempotent) |
| tax_income | `tasks.task_tax_income` | `0 * * * *` | per hour |
| war_reparation_tax | `tasks.task_war_reparation_tax` | `0 0 * * *` | per day |

Sub-steps gated inside `global_tick` (per hour): `military_maintenance`, `war_supply_regen`

## 2. Tables: who writes, who reads

From every SQL statement in app code (scripts/tests excluded). Dynamic table
names (f-strings) are not attributed. **Bold** = holds player money/assets:
every writer listed there can create or destroy value.

| table | written by | read only by |
|---|---|---|
| achievements | -- | `app_core/game_ticks/achievements.py`<br>`countries.py` |
| admin_actions | `app_core/admin/repositories.py` | -- |
| admin_user_controls | `app.py`<br>`app_core/admin/repositories.py` | -- |
| advertisements | `app_core/ads/repositories.py` | `app_core/ads/helpers.py` |
| assembly_effects | `app_core/game_ticks/assembly_tick.py` | `app_core/currency/services.py`<br>`app_core/game_ticks/market_auto_orders.py`<br>`app_core/market/routes.py` |
| assembly_proposals | `app_core/game_engine/routes.py`<br>`app_core/game_ticks/assembly_tick.py` | -- |
| assembly_votes | `app_core/game_engine/routes.py` | `app_core/game_ticks/assembly_tick.py` |
| bmc_gem_purchases | `app_core/store/repositories.py` | -- |
| bonds | `app_core/bonds/repositories.py`<br>`app_core/game_ticks/bond_tick.py` | `app_core/coalition_bank/services.py`<br>`app_core/currency_market/repositories.py` |
| bounties | `app_core/bounties/repositories.py` | -- |
| building_dictionary | `migrate.py` | `action_loop.py`<br>`ai_agent.py`<br>`app_core/economy/building_purchase.py`<br>`app_core/economy/consumer_goods.py`<br>`app_core/economy/province_energy.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/game_ticks/energy.py`<br>`app_core/game_ticks/food.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/game_ticks/unit_production.py`<br>`app_core/military/repositories.py`<br>`app_core/onboarding/service.py`<br>`app_core/tutorial/tour.py`<br>`countries.py`<br>`province.py`<br>`services/country_service.py`<br>`services/province_service.py`<br>`wars/routes.py`<br>`wars/service.py` |
| coalition_bond_insurance | `app_core/coalition_bank/services.py` | `app_core/game_ticks/bond_tick.py` |
| coalition_invites | `app_core/coalitions/routes.py` | -- |
| coalition_messages | `app_core/chat/repositories.py` | `app_core/main/routes.py` |
| coalitions_legacy | -- | `app_core/admin/repositories.py`<br>`app_core/world_map/repositories.py` |
| col_applications | -- | `app_core/coalitions/routes.py` |
| col_bank_contributions | `app_core/coalitions/routes.py` | -- |
| col_bank_recurring_trade_runs | `app_core/game_ticks/recurring_bank_trades.py` | `app_core/coalition_bank/services.py`<br>`bot_api.py` |
| col_bank_recurring_trades | `app_core/coalition_bank/services.py`<br>`app_core/game_ticks/recurring_bank_trades.py` | `bot_api.py` |
| col_bank_trades | `app_core/coalition_bank/services.py` | `bot_api.py` |
| col_bank_transactions | `app_core/coalition_bank/services.py`<br>`app_core/coalitions/routes.py` | `bot_api.py` |
| col_role_names | `app_core/coalitions/routes.py` | -- |
| colbanks | `app_core/admin/repositories.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/coalitions/routes.py`<br>`app_core/game_ticks/bond_tick.py`<br>`app_core/game_ticks/recurring_bank_trades.py`<br>`repositories/country_repository.py` | -- |
| colbanksrequests | `app_core/coalitions/routes.py`<br>`repositories/country_repository.py` | -- |
| colnames | `app_core/coalitions/routes.py`<br>`database.py`<br>`repositories/country_repository.py` | `app.py`<br>`app_core/admin/repositories.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/coalitions/repositories.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/main/routes.py`<br>`app_core/market/repositories.py`<br>`app_core/social_cards/routes.py`<br>`app_core/world_map/repositories.py`<br>`bot_api.py`<br>`countries.py`<br>`province.py`<br>`services/country_service.py`<br>`statistics.py` |
| cosmetics | -- | `app_core/chat/repositories.py`<br>`app_core/social_cards/routes.py`<br>`app_core/store/repositories.py`<br>`services/country_service.py`<br>`statistics.py` |
| **currency_holdings** | `app_core/currency/repositories.py` | `app_core/currency_market/repositories.py` |
| currency_market_offers | `app_core/currency_market/repositories.py` | `app_core/market/repositories.py` |
| currency_market_trades | `app_core/currency_market/repositories.py` | -- |
| currency_union_applications | `app_core/currency_unions/repositories.py` | -- |
| currency_union_members | `app_core/currency_unions/repositories.py` | `app_core/market/fees.py` |
| currency_unions | `app_core/currency_unions/repositories.py` | -- |
| devlog_entries | `app_core/community/repositories.py` | -- |
| direct_messages | `app_core/chat/repositories.py` | `app_core/main/routes.py` |
| discord_bad_words | `discord_bot/moderation_store.py` | -- |
| discord_custom_commands | `discord_bot/customcommands_store.py` | -- |
| discord_giveaways | `discord_bot/engagement_store.py` | -- |
| discord_guild_settings | `discord_bot/guild_store.py` | -- |
| discord_level_config | `discord_bot/engagement_store.py` | -- |
| discord_level_roles | `discord_bot/engagement_store.py` | -- |
| discord_link_codes | `bot_api.py` | -- |
| discord_logging_config | `discord_bot/logging_store.py` | -- |
| discord_moderation_config | `discord_bot/moderation_store.py` | -- |
| discord_panel_messages | `discord_bot/guild_store.py` | -- |
| discord_reaction_roles | `discord_bot/engagement_store.py` | -- |
| discord_role_aliases | `discord_bot/guild_store.py` | -- |
| discord_starboard_config | `discord_bot/starboard_store.py` | -- |
| discord_starboard_posts | `discord_bot/starboard_store.py` | -- |
| discord_suggestions | `discord_bot/suggestions_store.py` | -- |
| discord_suggestions_config | `discord_bot/suggestions_store.py` | -- |
| discord_ticket_config | `discord_bot/tickets_store.py` | -- |
| discord_tickets | `discord_bot/tickets_store.py` | -- |
| discord_user_xp | `discord_bot/engagement_store.py` | -- |
| discord_welcome_config | `discord_bot/engagement_store.py` | -- |
| forum_replies | `app_core/community/repositories.py` | -- |
| forum_threads | `app_core/community/repositories.py` | -- |
| game_economy_snapshots | `app_core/admin/repositories.py` | -- |
| game_tick_logs | `app_core/game_ticks/maintenance.py` | -- |
| gem_packages | -- | `app_core/store/repositories.py` |
| gem_purchases | `app_core/store/repositories.py` | -- |
| global_chat_messages | `app_core/chat/repositories.py` | `app_core/main/routes.py` |
| identity_diagnostic_log | `app_core/identity_diagnostics.py` | `app_core/admin/routes.py` |
| interactive_events | `app_core/events/routes.py`<br>`app_core/game_ticks/maintenance.py` | `services/country_service.py` |
| keys | `affo/create_db.py`<br>`init_db_railway.py` | -- |
| login_events | `database.py` | `login_verification.py` |
| login_verifications | `login_verification.py` | -- |
| map_combat_log | `app_core/game_map/routes.py` | -- |
| map_unit_deployments | `app_core/game_map/routes.py` | -- |
| market_auto_order_log | `app_core/game_ticks/market_auto_orders.py` | -- |
| market_auto_orders | `app_core/game_ticks/market_auto_orders.py`<br>`app_core/market/auto_orders.py` | `app_core/market/auto_order_routes.py` |
| market_embargoes | `app_core/market/repositories.py` | -- |
| market_fills | `app_core/market/repositories.py` | -- |
| market_preferences | `app_core/market/repositories.py` | -- |
| military | `app_core/game_map/routes.py`<br>`app_core/world_map/repositories.py` | -- |
| nation_revenue_history | `app_core/game_ticks/revenue_history.py` | -- |
| nation_treaties | `app_core/treaties/repositories.py` | `app_core/intelligence/repositories.py`<br>`app_core/onboarding/service.py`<br>`services/country_service.py`<br>`wars/routes.py` |
| national_currency_conversions | `app_core/currency/repositories.py` | -- |
| news | `app_core/admin/services.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/coalitions/repositories.py`<br>`app_core/coalitions/routes.py`<br>`app_core/currency_unions/repositories.py`<br>`app_core/game_ticks/assembly_tick.py`<br>`app_core/game_ticks/bond_tick.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/main/routes.py`<br>`app_core/market/repositories.py`<br>`bot_api.py`<br>`countries.py`<br>`repositories/country_repository.py`<br>`wars/nuclear.py`<br>`wars/routes.py` | `app.py`<br>`app_core/admin/repositories.py`<br>`services/country_service.py` |
| nodes | `app_core/world_map/repositories.py` | -- |
| nuclear_strikes | `wars/nuclear.py` | -- |
| offers | `app_core/game_ticks/market_auto_orders.py`<br>`app_core/market/repositories.py`<br>`countries.py`<br>`repositories/country_repository.py` | `app_core/admin/repositories.py`<br>`app_core/market/auto_orders.py`<br>`services/country_service.py`<br>`statistics.py` |
| patreon_gem_grants | `app_core/patreon/repositories.py` | -- |
| patreon_tiers | -- | `app_core/patreon/repositories.py` |
| peace | `countries.py`<br>`repositories/country_repository.py`<br>`wars/routes.py` | -- |
| policies | `app_core/game_ticks/maintenance.py`<br>`app_core/policies/repositories.py`<br>`countries.py`<br>`login.py`<br>`repositories/country_repository.py`<br>`signup.py` | `app_core/economy/building_purchase.py`<br>`app_core/game_ticks/food.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py`<br>`province.py` |
| poll_votes | `app_core/game_engine/routes.py` | -- |
| population_growth_freezes | `wars/aftermath.py` | `app_core/game_ticks/population.py` |
| province_iron_domes | `app_core/military/iron_dome.py` | `app_core/game_ticks/maintenance.py`<br>`app_core/intelligence/services.py` |
| provinces | `app.py`<br>`app_core/admin/repositories.py`<br>`app_core/game_map/routes.py`<br>`app_core/game_ticks/common.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/onboarding/customization.py`<br>`countries.py`<br>`discord_bot/commands/admin_cmds.py`<br>`init_db_railway.py`<br>`province.py`<br>`repositories/country_repository.py`<br>`wars/aftermath.py`<br>`wars/nuclear.py`<br>`wars/service.py` | `action_loop.py`<br>`ai_agent.py`<br>`app_core/bonds/repositories.py`<br>`app_core/coalitions/routes.py`<br>`app_core/currency_unions/repositories.py`<br>`app_core/economy/building_purchase.py`<br>`app_core/economy/province_energy.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/energy.py`<br>`app_core/game_ticks/food.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/intelligence/services.py`<br>`app_core/loans/repositories.py`<br>`app_core/main/routes.py`<br>`app_core/military/iron_dome.py`<br>`app_core/onboarding/service.py`<br>`app_core/social_cards/routes.py`<br>`app_core/tutorial/tour.py`<br>`app_core/world_map/routes.py`<br>`bot_api.py`<br>`check_counts.py`<br>`repositories/province_repository.py`<br>`services/country_service.py`<br>`statistics.py`<br>`tasks.py`<br>`wars/routes.py`<br>`wars/supply.py` |
| purchase_audit | `app_core/economy/building_purchase.py`<br>`province.py` | -- |
| referral_active_days | `app_core/referrals/service.py`<br>`repositories/country_repository.py` | -- |
| referral_milestone_payouts | `app_core/referrals/service.py`<br>`repositories/country_repository.py` | -- |
| reparation_tax | `countries.py`<br>`repositories/country_repository.py` | -- |
| requests | `app_core/coalitions/routes.py`<br>`countries.py`<br>`repositories/country_repository.py` | -- |
| reset_codes | `change.py`<br>`login_verification.py` | -- |
| resource_dictionary | -- | `action_loop.py`<br>`ai_agent.py`<br>`app.py`<br>`app_core/admin/repositories.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/coalitions/routes.py`<br>`app_core/economy/building_purchase.py`<br>`app_core/events/routes.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/game_ticks/food.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/game_ticks/unit_production.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/market/repositories.py`<br>`app_core/market/services.py`<br>`app_core/military/repositories.py`<br>`app_core/trade_agreements/repositories.py`<br>`bot_api.py`<br>`countries.py`<br>`db_check.py`<br>`province.py`<br>`services/country_service.py`<br>`signup.py`<br>`units.py`<br>`wars/routes.py` |
| revenue | `action_loop.py`<br>`app_core/military/repositories.py`<br>`province.py` | `services/country_service.py` |
| signup_attempts | `app_core/auth/google_auth.py`<br>`signup.py` | `app_core/admin/repositories.py` |
| site_visits | `app_core/analytics/service.py` | -- |
| spyinfo | `app_core/intelligence/repositories.py`<br>`countries.py`<br>`repositories/country_repository.py`<br>`tasks.py` | `wars/routes.py` |
| **stats** | `action_loop.py`<br>`app_core/admin/repositories.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/coalitions/routes.py`<br>`app_core/currency/repositories.py`<br>`app_core/economy/building_purchase.py`<br>`app_core/events/routes.py`<br>`app_core/game_ticks/bond_tick.py`<br>`app_core/game_ticks/loan_interest.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/loans/repositories.py`<br>`app_core/market/repositories.py`<br>`app_core/market/services.py`<br>`app_core/military/repositories.py`<br>`app_core/patreon/repositories.py`<br>`app_core/referrals/service.py`<br>`app_core/store/repositories.py`<br>`app_core/tutorial/routes.py`<br>`app_core/world_map/repositories.py`<br>`bot_api.py`<br>`countries.py`<br>`province.py`<br>`repositories/country_repository.py`<br>`signup.py`<br>`wars/routes.py` | `ai_agent.py`<br>`app.py`<br>`app_core/bonds/repositories.py`<br>`app_core/chat/repositories.py`<br>`app_core/currency_market/repositories.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_map/routes.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/onboarding/service.py`<br>`app_core/social_cards/routes.py`<br>`app_core/trade_agreements/repositories.py`<br>`app_core/tutorial/tour.py`<br>`services/country_service.py`<br>`statistics.py`<br>`tasks.py` |
| task_cursors | `app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py` | -- |
| task_metrics | `helpers.py` | -- |
| task_runs | `app_core/game_ticks/bond_tick.py`<br>`app_core/game_ticks/common.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/game_ticks/loan_interest.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/game_ticks/unit_production.py` | `app_core/system/routes.py` |
| tech_dictionary | `add_projects.py` | `action_loop.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/main/routes.py`<br>`app_core/military/iron_dome.py`<br>`app_core/upgrades/repositories.py`<br>`countries.py`<br>`province.py`<br>`services/country_service.py`<br>`wars/routes.py` |
| totp_backup_codes | `app_core/auth/totp.py` | -- |
| trade_agreements | `app_core/trade_agreements/repositories.py` | `app_core/game_ticks/maintenance.py` |
| trade_events | `helpers.py` | -- |
| trades | `app_core/market/repositories.py`<br>`countries.py`<br>`repositories/country_repository.py` | `app_core/admin/repositories.py` |
| treaties | `app_core/coalitions/routes.py` | -- |
| unit_dictionary | -- | `ai_agent.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/unit_production.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/military/repositories.py`<br>`app_core/tutorial/tour.py`<br>`bot_api.py`<br>`countries.py`<br>`services/country_service.py`<br>`signup.py`<br>`statistics.py`<br>`units.py`<br>`wars/aftermath.py`<br>`wars/nuclear.py`<br>`wars/routes.py` |
| user_achievements | -- | `app_core/game_ticks/achievements.py`<br>`countries.py` |
| user_active_days | `app_core/analytics/service.py` | -- |
| **user_buildings** | `action_loop.py`<br>`app_core/economy/building_purchase.py`<br>`countries.py`<br>`province.py`<br>`repositories/country_repository.py`<br>`wars/nuclear.py`<br>`wars/service.py` | `ai_agent.py`<br>`app_core/economy/consumer_goods.py`<br>`app_core/economy/province_energy.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/game_ticks/energy.py`<br>`app_core/game_ticks/food.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/game_ticks/unit_production.py`<br>`app_core/military/repositories.py`<br>`app_core/onboarding/service.py`<br>`app_core/tutorial/tour.py`<br>`services/country_service.py`<br>`services/province_service.py`<br>`wars/routes.py` |
| user_cosmetics | `app_core/store/repositories.py` | -- |
| **user_economy** | `action_loop.py`<br>`app_core/admin/repositories.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/coalitions/routes.py`<br>`app_core/economy/building_purchase.py`<br>`app_core/events/routes.py`<br>`app_core/game_ticks/disasters.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/market/repositories.py`<br>`app_core/market/services.py`<br>`countries.py`<br>`province.py`<br>`repositories/country_repository.py`<br>`signup.py`<br>`wars/routes.py` | `ai_agent.py`<br>`app.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_ticks/food.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/game_ticks/unit_production.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/military/repositories.py`<br>`app_core/trade_agreements/repositories.py`<br>`bot_api.py`<br>`db_check.py`<br>`services/country_service.py`<br>`statistics.py`<br>`units.py` |
| user_loans | `app_core/game_ticks/loan_interest.py`<br>`app_core/loans/repositories.py` | -- |
| **user_military** | `app_core/game_ticks/maintenance.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/military/repositories.py`<br>`countries.py`<br>`repositories/country_repository.py`<br>`signup.py`<br>`units.py`<br>`wars/aftermath.py`<br>`wars/nuclear.py`<br>`wars/routes.py` | `ai_agent.py`<br>`app_core/tutorial/tour.py`<br>`bot_api.py`<br>`services/country_service.py`<br>`statistics.py` |
| user_tech | `action_loop.py`<br>`countries.py`<br>`repositories/country_repository.py`<br>`wars/routes.py` | `app_core/game_engine/routes.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/revenue.py`<br>`app_core/main/routes.py`<br>`app_core/military/iron_dome.py`<br>`app_core/upgrades/repositories.py`<br>`province.py`<br>`services/country_service.py` |
| user_unit_stockpile | `app_core/military/repositories.py` | `app_core/game_ticks/unit_production.py` |
| users | `app.py`<br>`app_core/analytics/service.py`<br>`app_core/auth/email_auth.py`<br>`app_core/auth/google_auth.py`<br>`app_core/auth/totp.py`<br>`app_core/coalitions/routes.py`<br>`app_core/onboarding/customization.py`<br>`app_core/referrals/service.py`<br>`change.py`<br>`countries.py`<br>`database.py`<br>`login.py`<br>`repositories/country_repository.py`<br>`signup.py` | `admin_reset_password.py`<br>`app_core/admin/repositories.py`<br>`app_core/auth/routes.py`<br>`app_core/bonds/repositories.py`<br>`app_core/bounties/repositories.py`<br>`app_core/chat/repositories.py`<br>`app_core/chat/routes.py`<br>`app_core/coalition_bank/services.py`<br>`app_core/community/repositories.py`<br>`app_core/currency/repositories.py`<br>`app_core/currency_market/repositories.py`<br>`app_core/currency_unions/repositories.py`<br>`app_core/currency_unions/services.py`<br>`app_core/game_engine/routes.py`<br>`app_core/game_map/routes.py`<br>`app_core/game_ticks/bond_tick.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/game_ticks/population.py`<br>`app_core/game_ticks/taxes.py`<br>`app_core/identity_diagnostics.py`<br>`app_core/intelligence/repositories.py`<br>`app_core/main/routes.py`<br>`app_core/market/repositories.py`<br>`app_core/onboarding/service.py`<br>`app_core/patreon/repositories.py`<br>`app_core/social_cards/routes.py`<br>`app_core/store/repositories.py`<br>`app_core/trade_agreements/repositories.py`<br>`app_core/treaties/repositories.py`<br>`app_core/tutorial/tour.py`<br>`app_core/world_affairs/repositories.py`<br>`app_core/world_map/routes.py`<br>`bot_api.py`<br>`check_counts.py`<br>`check_tokens.py`<br>`db_check.py`<br>`email_utils.py`<br>`helpers.py`<br>`login_verification.py`<br>`province.py`<br>`services/country_service.py`<br>`statistics.py`<br>`tasks.py`<br>`wars/nuclear.py`<br>`wars/routes.py` |
| war_events | `helpers.py` | -- |
| wars | `app_core/game_ticks/taxes.py`<br>`countries.py`<br>`repositories/country_repository.py`<br>`units.py`<br>`wars/routes.py`<br>`wars/supply.py` | `app_core/admin/repositories.py`<br>`app_core/game_ticks/maintenance.py`<br>`app_core/main/routes.py`<br>`bot_api.py`<br>`province.py`<br>`services/country_service.py`<br>`wars/nuclear.py` |
| world_events | `app_core/world_affairs/repositories.py` | -- |

Tables no static query touches (dynamic SQL, scripts, or dead): `coalition_members`, `coalitions_normalized`, `discord_mod_cases`, `global_market`, `map_objects`, `marches`, `node_battles`, `node_yields`, `player_reimbursements`, `proinfra`, `repairs`, `resources`, `schema_migrations`, `upgrades`, `wars_normalized`

## 3. Routes

| URL | methods | handler |
|---|---|---|
| `/` | GET,POST | `app_core.main.routes:index` |
| `/<way>/<units>/<province_id>` | POST | `province:province_sell_buy` |
| `/_admin/ai_agent` | POST | `app_core.admin.routes:admin_ai_agent` |
| `/_admin/ai_logs` | GET | `app_core.admin.routes:admin_ai_logs_route` |
| `/_admin/db_diagnostics` | GET | `app_core.admin.routes:db_diagnostics` |
| `/_admin/trigger_tasks` | GET | `app_core.admin.routes:trigger_tasks` |
| `/accept_bank_request/<bankId>` | POST | `app_core.coalitions.routes:accept_bank_request` |
| `/accept_trade/<trade_id>` | POST | `app_core.market.routes:accept_trade` |
| `/accept_treaty/<offer_id>` | POST | `app_core.coalitions.routes:accept_treaty` |
| `/account` | GET | `app_core.auth.routes:account` |
| `/account/2fa/confirm` | POST | `app_core.auth.routes:twofa_confirm` |
| `/account/2fa/disable` | POST | `app_core.auth.routes:twofa_disable` |
| `/account/2fa/setup` | GET | `app_core.auth.routes:twofa_setup` |
| `/account/request_password_reset` | POST | `change:account_request_password_reset` |
| `/account/reveal_email` | POST | `app_core.auth.routes:reveal_email` |
| `/add/<uId>` | POST | `app_core.coalitions.routes:adding` |
| `/adjust_personal_bank/<coalition_id>` | POST | `app_core.coalitions.routes:adjust_personal_bank` |
| `/admin/ads` | GET,POST | `app_core.ads.routes:admin_ads` |
| `/admin/analytics` | GET | `app_core.analytics.routes:admin_analytics` |
| `/admin/command-center` | GET | `app_core.admin.routes:admin_command_center` |
| `/admin/command-center/add-provinces` | POST | `app_core.admin.routes:admin_add_provinces` |
| `/admin/command-center/add-resource` | POST | `app_core.admin.routes:admin_add_resource` |
| `/admin/command-center/ban-user` | POST | `app_core.admin.routes:admin_ban_user` |
| `/admin/command-center/economy` | GET | `app_core.admin.routes:admin_economy_dashboard` |
| `/admin/command-center/economy/api` | GET | `app_core.admin.routes:admin_economy_api` |
| `/admin/command-center/economy/snapshot` | POST | `app_core.admin.routes:admin_trigger_snapshot` |
| `/admin/command-center/identity-diagnostics` | GET | `app_core.admin.routes:admin_identity_diagnostics` |
| `/admin/command-center/kick-user` | POST | `app_core.admin.routes:admin_kick_user` |
| `/admin/command-center/unban-user` | POST | `app_core.admin.routes:admin_unban_user` |
| `/admin/command-center/view-as` | POST | `app_core.admin.routes:admin_view_as` |
| `/admin/debug/exploits` | GET,POST | `app_core.admin.routes:debug_exploits` |
| `/admin/debug/leviathan` | GET | `app_core.admin.routes:debug_leviathan` |
| `/admin/debug_wealth` | GET | `app_core.admin.routes:admin_debug_wealth` |
| `/admin/live-feed` | GET | `app_core.admin.routes:admin_live_feed` |
| `/admin/migrate_treaties` | GET | `app_core.admin.routes:admin_migrate_treaties` |
| `/admin/view-as/exit` | POST | `app_core.admin.routes:admin_view_as_exit` |
| `/ads` | GET,POST | `app_core.ads.routes:upload_ad` |
| `/ads/image/<int:ad_id>` | GET | `app_core.ads.routes:serve_ad_image` |
| `/api/admin/run_migration` | GET | `app_core.world_map.routes:run_migration_backdoor` |
| `/api/bot/coalition_bank_summary` | GET | `bot_api:bot_coalition_bank_summary` |
| `/api/bot/devlog` | POST | `bot_api:bot_post_devlog` |
| `/api/bot/embed_version` | GET | `bot_api:bot_embed_version` |
| `/api/bot/health` | GET | `bot_api:bot_health` |
| `/api/bot/heuristics/sync` | POST | `bot_api:bot_heuristics_sync` |
| `/api/bot/me` | GET | `bot_api:bot_me` |
| `/api/bot/me_embed` | GET | `bot_api:bot_me_embed` |
| `/api/bot/nation` | GET | `bot_api:bot_nation` |
| `/api/bot/nation_embed` | GET | `bot_api:bot_nation_embed` |
| `/api/bot/register` | POST | `bot_api:bot_register` |
| `/api/bot/resources` | GET | `bot_api:bot_resources` |
| `/api/bot/staff/nation` | GET | `bot_api:bot_staff_nation` |
| `/api/bot/wars` | GET | `bot_api:bot_wars` |
| `/api/bot/world_stats` | GET | `bot_api:bot_world_stats` |
| `/api/economy/status` | GET | `app_core.system.routes:economy_status` |
| `/api/events/<int:event_id>/respond` | POST | `app_core.events.routes:respond_event` |
| `/api/game_map/attack` | POST | `app_core.game_map.routes:game_map_attack` |
| `/api/game_map/data` | GET | `app_core.game_map.routes:game_map_data` |
| `/api/game_map/deploy` | POST | `app_core.game_map.routes:game_map_deploy` |
| `/api/game_map/move` | POST | `app_core.game_map.routes:game_map_move` |
| `/api/game_map/retreat` | POST | `app_core.game_map.routes:game_map_retreat` |
| `/api/global_events` | GET | `province:get_global_events` |
| `/api/news/clear_all` | POST | `app_core.main.routes:api_news_clear_all` |
| `/api/news/mark_read` | POST | `app_core.main.routes:api_news_mark_read` |
| `/api/notifications` | GET | `app_core.main.routes:api_notifications` |
| `/api/onboarding/status` | GET | `app_core.onboarding.routes:onboarding_status` |
| `/api/province/<int:pId>/layout` | GET | `province:province_layout_api` |
| `/api/province/<int:pId>/quick_build` | POST | `province:province_quick_build_api` |
| `/api/province/<int:pId>/slot/<slot_id>` | GET | `province:province_slot_api` |
| `/api/province_map/nodes` | GET | `app_core.world_map.routes:get_province_map_nodes` |
| `/api/quick_search` | GET | `app_core.main.routes:api_quick_search` |
| `/api/referrals/stats` | GET | `app_core.referrals.routes:referral_stats` |
| `/api/tour/dismiss` | POST | `app_core.tutorial.routes:tour_dismiss` |
| `/api/tour/state` | GET | `app_core.tutorial.routes:tour_state` |
| `/api/tour/visit` | POST | `app_core.tutorial.routes:tour_visit` |
| `/api/tutorial/claim` | POST | `app_core.tutorial.routes:claim_tutorial_reward` |
| `/api/tutorial/progress` | GET | `app_core.tutorial.routes:tutorial_progress` |
| `/api/world_map/nodes` | GET | `app_core.world_map.routes:get_nodes` |
| `/api/world_map/nodes/<int:node_id>/attack` | POST | `app_core.world_map.routes:declare_siege` |
| `/assembly` | GET,POST | `app_core.game_engine.routes:assembly` |
| `/assembly/propose` | GET,POST | `app_core.game_engine.routes:assembly_propose` |
| `/assembly/vote/<int:proposal_id>` | POST | `app_core.game_engine.routes:assembly_vote` |
| `/bonds` | GET | `app_core.bonds.routes:view_bonds` |
| `/bonds/<int:bond_id>/cancel` | POST | `app_core.bonds.routes:cancel_bond_route` |
| `/bonds/<int:bond_id>/edit` | POST | `app_core.bonds.routes:edit_bond_route` |
| `/bonds/<int:bond_id>/fund` | POST | `app_core.bonds.routes:fund_bond_route` |
| `/bonds/create` | POST | `app_core.bonds.routes:create_bond_route` |
| `/bounties` | GET | `app_core.bounties.routes:view_bounties` |
| `/bounties/cancel/<int:bounty_id>` | POST | `app_core.bounties.routes:cancel_bounty_route` |
| `/bounties/place` | POST | `app_core.bounties.routes:place_bounty_route` |
| `/break_treaty/<offer_id>` | POST | `app_core.coalitions.routes:break_treaty` |
| `/build_structure` | POST | `province:build_structure_action` |
| `/businesses` | GET | `app_core.game_engine.routes:businesses` |
| `/buy_offer/<offer_id>` | POST | `app_core.market.routes:buy_market_offer` |
| `/callback` | GET | `signup:callback` |
| `/change` | POST | `change:change` |
| `/coalition/<coalition_id>` | GET | `app_core.coalitions.routes:coalition` |
| `/coalition/<int:coalition_id>/bank-trades` | GET | `app_core.coalition_bank.routes:bank_trades` |
| `/coalition/<int:coalition_id>/bank-trades/propose` | POST | `app_core.coalition_bank.routes:propose_bank_trade` |
| `/coalition/<int:coalition_id>/bank-trades/recurring` | POST | `app_core.coalition_bank.routes:propose_recurring_bank_trade` |
| `/coalition/<int:coalition_id>/bank_log` | GET | `app_core.coalitions.routes:bank_log` |
| `/coalition/<int:coalition_id>/bank_log.csv` | GET | `app_core.coalitions.routes:bank_log_csv` |
| `/coalition/<int:coalition_id>/bond-insurance` | GET | `app_core.coalition_bank.routes:bond_insurance` |
| `/coalition/<int:coalition_id>/bond-insurance/set` | POST | `app_core.coalition_bank.routes:set_bond_insurance` |
| `/coalition/<int:coalition_id>/chat/messages` | GET | `app_core.chat.routes:coalition_chat_history` |
| `/coalition/<int:coalition_id>/embargo` | POST | `app_core.coalitions.routes:embargo_coalition` |
| `/coalition/<int:coalition_id>/lift_embargo` | POST | `app_core.coalitions.routes:lift_coalition_embargo` |
| `/coalition/<int:coalition_id>/member/<int:member_id>/revenue` | GET | `app_core.coalitions.routes:member_revenue` |
| `/coalition/<int:coalition_id>/role_names` | POST | `app_core.coalitions.routes:update_role_names` |
| `/coalition/<int:coalition_id>/settings` | POST | `app_core.coalitions.routes:update_coalition_settings` |
| `/coalition/bank-trades/<int:trade_id>/accept` | POST | `app_core.coalition_bank.routes:accept_bank_trade` |
| `/coalition/bank-trades/<int:trade_id>/cancel` | POST | `app_core.coalition_bank.routes:cancel_bank_trade` |
| `/coalition/bank-trades/<int:trade_id>/decline` | POST | `app_core.coalition_bank.routes:decline_bank_trade` |
| `/coalition/bank-trades/recurring/<int:rec_id>/<action>` | POST | `app_core.coalition_bank.routes:resolve_recurring_bank_trade` |
| `/coalition/build-sharing` | POST | `app_core.coalitions.routes:toggle_build_sharing` |
| `/coalition_invite/<invite_id>/accept` | POST | `app_core.coalitions.routes:accept_coalition_invite` |
| `/coalition_invite/<invite_id>/reject` | POST | `app_core.coalitions.routes:reject_coalition_invite` |
| `/coalition_invite/<invite_id>/revoke` | POST | `app_core.coalitions.routes:revoke_coalition_invite` |
| `/coalition_invites` | GET | `app_core.coalitions.routes:view_coalition_invites` |
| `/coalitions` | GET | `app_core.coalitions.routes:coalitions` |
| `/confirm_login/<token>` | GET | `login_verification:confirm_login` |
| `/countries` | GET | `countries:countries` |
| `/country` | GET | `app_core.game_engine.routes:country_redirect` |
| `/country/id=<cId>` | GET | `countries:country` |
| `/createprovince` | GET,POST | `province:createprovince` |
| `/cruise_missile_strike` | POST | `wars.routes:cruise_missile_strike` |
| `/currency/mint` | POST | `app_core.currency.routes:mint_currency_route` |
| `/currency/redeem` | POST | `app_core.currency.routes:redeem_currency_route` |
| `/currency_market` | GET | `app_core.currency_market.routes:currency_market` |
| `/currency_market/accept/<int:offer_id>` | POST | `app_core.currency_market.routes:accept_offer` |
| `/currency_market/cancel/<int:offer_id>` | POST | `app_core.currency_market.routes:cancel_offer` |
| `/currency_market/offer` | POST | `app_core.currency_market.routes:create_offer` |
| `/currency_unions` | GET | `app_core.currency_unions.routes:view_unions` |
| `/currency_unions/<int:union_id>/applications/<int:applicant_id>/<decision>` | POST | `app_core.currency_unions.routes:decide_route` |
| `/currency_unions/<int:union_id>/apply` | POST | `app_core.currency_unions.routes:apply_route` |
| `/currency_unions/<int:union_id>/kick/<int:member_id>` | POST | `app_core.currency_unions.routes:kick_route` |
| `/currency_unions/<int:union_id>/withdraw` | POST | `app_core.currency_unions.routes:withdraw_route` |
| `/currency_unions/create` | POST | `app_core.currency_unions.routes:create_union_route` |
| `/currency_unions/leave` | POST | `app_core.currency_unions.routes:leave_route` |
| `/declare_war` | POST | `wars.routes:declare_war` |
| `/decline_trade/<trade_id>` | POST | `app_core.market.routes:decline_trade_endpoint` |
| `/decline_treaty/<offer_id>` | POST | `app_core.coalitions.routes:decline_treaty` |
| `/defense` | GET,POST | `wars.routes:defense` |
| `/delete_coalition/<coalition_id>` | POST | `app_core.coalitions.routes:delete_coalition` |
| `/delete_news/<int:id>` | POST | `countries:delete_news` |
| `/delete_offer/<offer_id>` | POST | `app_core.market.routes:delete_offer_endpoint` |
| `/delete_own_account` | POST | `countries:delete_own_account` |
| `/deploy-info` | GET | `app_core.system.routes:deploy_info` |
| `/deposit_into_bank/<coalition_id>` | POST | `app_core.coalitions.routes:deposit_into_bank` |
| `/devlog` | GET,POST | `app_core.community.routes:devlog` |
| `/discord` | GET,POST | `signup:discord` |
| `/discord_login/` | GET | `login:discord_login` |
| `/discord_reset_password_page` | GET,POST | `change:discord_reset_password_page` |
| `/discord_signup` | GET,POST | `signup:discord_register` |
| `/discussions` | GET,POST | `app_core.community.routes:discussions` |
| `/discussions/<int:thread_id>` | GET,POST | `app_core.community.routes:thread_detail` |
| `/discussions/<int:thread_id>/delete` | POST | `app_core.community.routes:delete_thread` |
| `/discussions/reply/<int:reply_id>/delete` | POST | `app_core.community.routes:delete_reply` |
| `/dns_troubleshoot` | GET | `app_core.main.routes:dns_troubleshoot` |
| `/drone_strike` | POST | `wars.routes:drone_strike` |
| `/embargo/<target_id>` | POST | `app_core.market.routes:embargo_nation` |
| `/embargo/<target_id>/remove` | POST | `app_core.market.routes:remove_embargo_endpoint` |
| `/establish_coalition` | GET,POST | `app_core.coalitions.routes:establish_coalition` |
| `/find_targets` | GET,POST | `wars.routes:find_targets` |
| `/flag/<flag_type>/<int:flag_id>` | GET | `app_core.main.routes:serve_flag` |
| `/forgot_password` | GET | `app_core.auth.routes:forget_password` |
| `/game_map` | GET | `app_core.game_map.routes:game_map_view` |
| `/game_map/<path:token>` | GET | `app_core.game_map.routes:game_map_auth` |
| `/generate_discord_link_code` | POST | `change:generate_discord_link_code` |
| `/generate_recovery_key` | POST | `change:generate_recovery_key` |
| `/give_position` | POST | `app_core.coalitions.routes:give_position` |
| `/global_chat/messages` | GET | `app_core.chat.routes:global_chat_history` |
| `/google7c77c4ff4f7be650.html` | GET | `app_core.main.routes:google_search_console_verify` |
| `/google_signup` | GET,POST | `app_core.auth.google_auth:google_signup_route` |
| `/health` | GET | `app_core.system.routes:health` |
| `/intelligence` | GET | `app_core.intelligence.routes:intelligence` |
| `/join/<coalition_id>` | POST | `app_core.coalitions.routes:join_col` |
| `/leave/<coalition_id>` | POST | `app_core.coalitions.routes:leave_col` |
| `/loans` | GET | `app_core.loans.routes:view_loans` |
| `/loans/quote` | GET | `app_core.loans.routes:loan_quote_route` |
| `/loans/repay` | POST | `app_core.loans.routes:repay_loan_route` |
| `/loans/take` | POST | `app_core.loans.routes:take_loan_route` |
| `/login` | GET,POST | `login:login` |
| `/login/` | GET,POST | `login:login` |
| `/login/2fa` | GET,POST | `login:login_2fa` |
| `/login/email` | POST | `app_core.auth.email_auth:login_email` |
| `/login/google` | GET | `app_core.auth.google_auth:google_login_route` |
| `/login/google/callback` | GET | `app_core.auth.google_auth:google_callback_route` |
| `/logout` | GET | `app_core.auth.routes:logout` |
| `/lore_map` | GET | `app_core.world_map.routes:lore_map` |
| `/market` | GET | `app_core.market.routes:market` |
| `/market/auto_orders` | GET | `app_core.market.auto_order_routes:auto_orders` |
| `/market/auto_orders` | POST | `app_core.market.auto_order_routes:save_auto_order` |
| `/market/auto_orders/<int:rule_id>/delete` | POST | `app_core.market.auto_order_routes:delete_auto_order` |
| `/market/auto_orders/<int:rule_id>/toggle` | POST | `app_core.market.auto_order_routes:toggle_auto_order` |
| `/market/preferences` | POST | `app_core.market.routes:market_preferences` |
| `/marketoffer/` | GET,POST | `app_core.market.routes:marketoffer` |
| `/mass_purchase` | GET | `app_core.game_engine.routes:mass_purchase` |
| `/mass_purchase/buy` | POST | `province:mass_purchase_buy` |
| `/mass_purchase/preview` | POST | `province:mass_purchase_preview` |
| `/mechanics` | GET | `app_core.main.routes:mechanics` |
| `/mechanics/biomes` | GET | `app_core.main.routes:mechanics_biomes` |
| `/mechanics/consumer_goods` | GET | `app_core.main.routes:mechanics_consumer_goods` |
| `/mechanics/rations` | GET | `app_core.main.routes:mechanics_rations` |
| `/mechanics/resources` | GET | `app_core.main.routes:mechanics_resources` |
| `/mechanics/revenue` | GET | `app_core.main.routes:mechanics_revenue` |
| `/mechanics/war` | GET | `app_core.main.routes:mechanics_war` |
| `/media/banner/<int:ad_id>` | GET | `app_core.ads.routes:serve_ad_image` |
| `/messages` | GET | `app_core.chat.routes:messages_inbox` |
| `/messages/<int:other_user_id>` | GET | `app_core.chat.routes:messages_thread` |
| `/military` | GET,POST | `app_core.military.routes:military` |
| `/military/<way>/<units>` | POST | `app_core.military.routes:military_sell_buy` |
| `/military/activate/<units>` | POST | `app_core.military.routes:military_activate` |
| `/my_coalition` | GET | `app_core.coalitions.routes:my_coalition` |
| `/my_country` | GET | `countries:my_country` |
| `/my_offers` | GET | `app_core.market.routes:my_offers` |
| `/nation/<nation_id>/invite` | POST | `app_core.coalitions.routes:send_coalition_invite` |
| `/nuclear_strike` | POST | `wars.routes:nuclear_strike` |
| `/nuclear_strike/<int:war_id>` | GET | `wars.routes:nuclear_strike_plan` |
| `/nuclear_strike/<int:war_id>/launch` | POST | `wars.routes:nuclear_strike_launch` |
| `/nuclear_strike/<int:war_id>/review` | POST | `wars.routes:nuclear_strike_review` |
| `/offer_treaty` | POST | `app_core.coalitions.routes:offer_treaty` |
| `/outgoing_invites` | GET | `app_core.coalitions.routes:view_outgoing_invites` |
| `/peace_offers` | GET,POST | `wars.routes:peace_offers` |
| `/policies/update` | POST | `app_core.policies.routes:policies` |
| `/post_offer/<offer_type>` | POST | `app_core.market.routes:post_offer` |
| `/post_trade_offer/<offer_type>/<offeree_id>` | POST | `app_core.market.routes:post_trade_offer` |
| `/privacy` | GET | `app_core.main.routes:privacy_policy` |
| `/province-image/<int:pId>` | GET | `province:serve_province_image` |
| `/province/<int:pId>/delete` | POST | `province:delete_province` |
| `/province/<int:pId>/flag` | POST | `province:upload_province_flag` |
| `/province/<int:pId>/image` | POST | `province:update_province_image` |
| `/province/<int:pId>/iron_dome` | POST | `province:province_iron_dome` |
| `/province/<int:pId>/rename` | POST | `province:rename_province` |
| `/province/<int:pId>/set-capital` | POST | `province:set_capital_province` |
| `/province/<pId>` | GET | `province:province` |
| `/provinces` | GET | `province:provinces` |
| `/rankings` | GET | `statistics:rankings` |
| `/ready` | GET | `app_core.system.routes:ready` |
| `/recruitments` | GET | `app_core.game_engine.routes:recruitments` |
| `/register/email` | POST | `app_core.auth.email_auth:register_email` |
| `/remove/<uId>` | POST | `app_core.coalitions.routes:removing_requests` |
| `/remove_bank_request/<bankId>` | POST | `app_core.coalitions.routes:remove_bank_request` |
| `/request_from_bank/<coalition_id>` | POST | `app_core.coalitions.routes:request_from_bank` |
| `/request_password_reset` | POST | `change:request_password_reset` |
| `/resend_verification` | POST | `signup:resend_verification` |
| `/reset_account` | POST | `countries:reset_account` |
| `/reset_password/<code>` | GET,POST | `change:reset_password` |
| `/reset_password_recovery_key` | POST | `change:reset_password_recovery_key` |
| `/robots.txt` | GET | `app_core.main.routes:robots` |
| `/save_recovery_key` | GET | `signup:save_recovery_key` |
| `/sell_offer/<offer_id>` | POST | `app_core.market.routes:sell_market_offer` |
| `/send_peace_offer/<int:war_id>/<int:enemy_id>` | POST | `wars.routes:send_peace_offer` |
| `/set_tax_rate/<coalition_id>` | POST | `app_core.coalitions.routes:set_tax_rate` |
| `/signup` | GET,POST | `signup:signup` |
| `/sitemap.xml` | GET | `app_core.main.routes:sitemap` |
| `/social-card/coalition/<int:coalition_id>.gif` | GET | `app_core.social_cards.routes:coalition_card` |
| `/social-card/country/<int:cid>.gif` | GET | `app_core.social_cards.routes:country_card` |
| `/social-card/province/<int:province_id>.gif` | GET | `app_core.social_cards.routes:province_card` |
| `/spyAmount` | GET,POST | `app_core.intelligence.routes:spyAmount` |
| `/spyResult` | GET,POST | `app_core.intelligence.routes:spyResult` |
| `/start_research` | POST | `app_core.upgrades.routes:start_research_action` |
| `/statistics` | GET | `statistics:statistics` |
| `/store` | GET | `app_core.store.routes:store` |
| `/store/bmc/webhook` | POST | `app_core.store.routes:bmc_webhook` |
| `/store/cosmetics/buy/<int:cosmetic_id>` | POST | `app_core.store.routes:buy_cosmetic` |
| `/store/cosmetics/equip/<int:cosmetic_id>` | POST | `app_core.store.routes:equip_cosmetic` |
| `/store/cosmetics/unequip/<cosmetic_type>` | POST | `app_core.store.routes:unequip_cosmetic` |
| `/store/gems/checkout/<int:gem_package_id>` | POST | `app_core.store.routes:gems_checkout` |
| `/store/stripe/webhook` | POST | `app_core.store.routes:stripe_webhook` |
| `/strategic_airstrike` | POST | `wars.routes:strategic_airstrike` |
| `/terms` | GET | `app_core.main.routes:terms_of_service` |
| `/trade-agreements` | GET | `app_core.trade_agreements.routes:trade_agreements` |
| `/trade-agreements/<int:agreement_id>/accept` | POST | `app_core.trade_agreements.routes:accept_trade_agreement` |
| `/trade-agreements/<int:agreement_id>/cancel` | POST | `app_core.trade_agreements.routes:cancel_trade_agreement` |
| `/trade-agreements/<int:agreement_id>/reject` | POST | `app_core.trade_agreements.routes:reject_trade_agreement` |
| `/trade-agreements/<int:agreement_id>/resume` | POST | `app_core.trade_agreements.routes:resume_trade_agreement` |
| `/trade-agreements/create` | POST | `app_core.trade_agreements.routes:create_trade_agreement` |
| `/trade-agreements/partners` | GET | `app_core.trade_agreements.routes:search_trade_partners` |
| `/transfer/<transferee>` | POST | `app_core.market.routes:transfer` |
| `/treaties` | GET | `app_core.treaties.routes:view_treaties` |
| `/treaties/accept/<int:treaty_id>` | POST | `app_core.treaties.routes:accept_treaty` |
| `/treaties/cancel/<int:treaty_id>` | POST | `app_core.treaties.routes:cancel_treaty` |
| `/treaties/offer` | POST | `app_core.treaties.routes:offer_treaty` |
| `/treaties/reject/<int:treaty_id>` | POST | `app_core.treaties.routes:reject_treaty` |
| `/tutorial` | GET | `app_core.main.routes:tutorial` |
| `/update_col_info/<coalition_id>` | POST | `app_core.coalitions.routes:update_col_info` |
| `/update_country_info` | POST | `countries:update_info` |
| `/upgrades` | GET | `app_core.upgrades.routes:upgrades` |
| `/upgrades_sb/<ttype>/<thing>` | POST | `app_core.upgrades.routes:upgrade_sell_buy` |
| `/verification_pending` | GET | `signup:verification_pending` |
| `/verify` | GET | `signup:verify_email` |
| `/war` | GET | `app_core.game_engine.routes:war` |
| `/war/<int:war_id>` | GET | `wars.routes:war_with_id` |
| `/war/<int:war_id>/repeat_attack` | POST | `wars.routes:repeat_attack` |
| `/warResult` | GET | `wars.routes:warResult` |
| `/waramount` | GET,POST | `wars.routes:warAmount` |
| `/warchoose/<int:war_id>` | GET,POST | `wars.routes:warChoose` |
| `/warresult` | GET | `app_core.game_engine.routes:warresult_deprecated` |
| `/wars` | GET,POST | `wars.routes:wars` |
| `/wars/<int:war_id>/join_ally` | POST | `wars.routes:join_war_as_ally` |
| `/wartarget` | GET,POST | `wars.routes:warTarget` |
| `/withdraw_from_bank/<coalition_id>` | POST | `app_core.coalitions.routes:withdraw_from_bank` |
| `/withdraw_personal_from_bank/<coalition_id>` | POST | `app_core.coalitions.routes:withdraw_personal_from_bank` |
| `/world_affairs` | GET | `app_core.world_affairs.routes:view_world_affairs` |
| `/world_map` | GET | `app_core.world_map.routes:world_map_view` |
