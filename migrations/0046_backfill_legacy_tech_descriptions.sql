-- Backfill tech_dictionary.description for the 18 legacy techs (better_engineering
-- through nuclear_testing_facility) that were migrated from the old upgrades system
-- without one. The "All Technologies" dropdown on /upgrades only ever showed
-- name + cost for these because it selects `description` from this table, and
-- it was NULL. Text below is copied verbatim from the existing hardcoded
-- descriptions already shown to players in the Economic/Military tech cards
-- on the same page, so the dropdown now matches what's already live.

UPDATE tech_dictionary SET description = 'Reworking of existing nuclear reactors and regulation of future nuclear reactors results in +6 energy produced per reactor.' WHERE name = 'better_engineering' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'With research into optimized construction methods and rebuilding of existing structures, upkeep costs for all existing and future industry infrastructure is decreased by 20%.' WHERE name = 'cheaper_materials' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Outdated malls are replaced with fulfillment centers, delivering goods to consumers. Consequently, upkeep for malls is decreased by 30%.' WHERE name = 'online_shopping' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Government regulation and implementation of new building standards, green energy quotas, and energy use results in retail producing 25% less pollution.' WHERE name = 'government_regulation' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Implementation of a national health institution allows for organization and effective distribution and communication, increasing each hospital''s happiness increase by 30%.' WHERE name = 'national_health_institution' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Re-creation of existing and future monorails into high speed rail increases productivity increase by 20%.' WHERE name = 'high_speed_rail' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'The implementation of automation and advanced technologies into conventional farming increases farm output by 50%.' WHERE name = 'advanced_machinery' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Research and development into explosives allows for more effective bauxite harvesting, increasing production by 45%.' WHERE name = 'stronger_explosives' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Use of propaganda in media, news, and through devices allows for easy recruitment of soldiers, bringing costs down by 35%.' WHERE name = 'widespread_propaganda' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Increased funding and construction of new operative bases allows for the ability to recruit and maintain more spies by a factor of 40%.' WHERE name = 'increased_funding' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Research and development into technologies allows for cheaper and quicker production of components, decreasing resources needed to make components by 25%.' WHERE name = 'automation_integration' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Heavy subsidisation of the steel industry allows for investments into large scale projects, decreasing upkeep and resources to make steel by 30%.' WHERE name = 'larger_forges' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Looting teams will acquire military supplies from annexed establishments, increasing war supplies production by 10%.' WHERE name = 'looting_teams' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Organized supply lines gives annexed citizens jobs producing resources for your war economy, further increasing war supplies production by 15%.' WHERE name = 'organized_supply_lines' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Large storehouses allows for greater storage of war supplies, increasing max supplies by 25%.' WHERE name = 'large_storehouses' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Ballistic missile silos provides countries with the ability to develop and deploy ballistic missiles.' WHERE name = 'ballistic_missile_silo' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Inter-continental ballistic missile silos allows countries to develop and deploy inter-continental ballistic missiles.' WHERE name = 'icbm_silo' AND (description IS NULL OR description = '');
UPDATE tech_dictionary SET description = 'Nuclear testing facilities gives countries the ability to create nuclear warheads and establish nuclear reactors.' WHERE name = 'nuclear_testing_facility' AND (description IS NULL OR description = '');
