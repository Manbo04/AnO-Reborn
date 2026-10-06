-- Game catalog rows (resources, buildings, units, techs, store items) from production.
-- No player data. Loaded after db/schema.sql in CI.

SET session_replication_role = replica;
--
-- PostgreSQL database dump
--


-- Dumped from database version 17.11 (Debian 17.11-1.pgdg13+2)
-- Dumped by pg_dump version 17.11 (Debian 17.11-0+deb13u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: tech_dictionary; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.tech_dictionary VALUES (1, 'basic_agriculture', 'Basic Agriculture', 'agriculture', 5000, NULL, 'resource_production', 10.00, 'Fundamental farming techniques increasing food production', true, '2026-03-02 23:32:27.156348+00');
INSERT INTO public.tech_dictionary VALUES (2, 'mining_techniques', 'Mining Techniques', 'industry', 6000, NULL, 'resource_production', 10.00, 'Basic resource extraction methods', true, '2026-03-02 23:32:27.156348+00');
INSERT INTO public.tech_dictionary VALUES (3, 'military_doctrine', 'Military Doctrine', 'military', 8000, NULL, 'military_boost', 5.00, 'Organized military training and tactics', true, '2026-03-02 23:32:27.156348+00');
INSERT INTO public.tech_dictionary VALUES (4, 'industrialization', 'Industrialization', 'industry', 15000, 2, 'resource_production', 20.00, 'Advanced manufacturing and mass production techniques', true, '2026-03-02 23:32:27.363281+00');
INSERT INTO public.tech_dictionary VALUES (5, 'advanced_farming', 'Advanced Farming', 'agriculture', 12000, 1, 'resource_production', 15.00, 'Improved irrigation and crop rotation methods', true, '2026-03-02 23:32:27.498324+00');
INSERT INTO public.tech_dictionary VALUES (6, 'scientific_method', 'Scientific Method', 'science', 25000, 4, 'research_speed', 25.00, 'Systematic approach to research and experimentation', true, '2026-03-02 23:32:27.652693+00');
INSERT INTO public.tech_dictionary VALUES (7, 'steel_production', 'Steel Production', 'industry', 20000, 4, 'resource_production', 30.00, 'Bessemer process and advanced metallurgy', true, '2026-03-02 23:32:27.84272+00');
INSERT INTO public.tech_dictionary VALUES (8, 'nuclear_physics', 'Nuclear Physics', 'science', 50000, 6, 'military_boost', 50.00, 'Atomic theory and nuclear energy harnessing', true, '2026-03-02 23:32:27.979437+00');
INSERT INTO public.tech_dictionary VALUES (27, 'integrated_steelmaking', 'Integrated Steelmaking', 'industry', 100000, NULL, 'resource_production', 36.00, 'Boosts Steel Mills production by 36% nationwide. Iron and Coal usages are increased to create more Steel.', true, '2026-06-26 13:34:58.86093+00');
INSERT INTO public.tech_dictionary VALUES (28, 'electric_arc_furnace', 'Electric Arc Furnace', 'industry', 120000, NULL, 'resource_production', 25.00, 'A modern steelmaking method that consumes 50% less raw iron and coal, but uses immense amounts of electricity (2 energy per mill).', true, '2026-06-26 13:34:58.86093+00');
INSERT INTO public.tech_dictionary VALUES (9, 'better_engineering', 'Better Engineering', 'industry', 10000, NULL, NULL, NULL, 'Reworking of existing nuclear reactors and regulation of future nuclear reactors results in +6 energy produced per reactor.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (10, 'cheaper_materials', 'Cheaper Materials', 'industry', 8000, NULL, NULL, NULL, 'With research into optimized construction methods and rebuilding of existing structures, upkeep costs for all existing and future industry infrastructure is decreased by 20%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (11, 'online_shopping', 'Online Shopping', 'infrastructure', 12000, NULL, NULL, NULL, 'Outdated malls are replaced with fulfillment centers, delivering goods to consumers. Consequently, upkeep for malls is decreased by 30%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (12, 'government_regulation', 'Government Regulation', 'diplomacy', 15000, NULL, NULL, NULL, 'Government regulation and implementation of new building standards, green energy quotas, and energy use results in retail producing 25% less pollution.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (13, 'national_health_institution', 'National Health Institution', 'science', 20000, NULL, NULL, NULL, 'Implementation of a national health institution allows for organization and effective distribution and communication, increasing each hospital''s happiness increase by 30%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (14, 'high_speed_rail', 'High Speed Rail', 'infrastructure', 25000, NULL, NULL, NULL, 'Re-creation of existing and future monorails into high speed rail increases productivity increase by 20%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (15, 'advanced_machinery', 'Advanced Machinery', 'industry', 18000, NULL, NULL, NULL, 'The implementation of automation and advanced technologies into conventional farming increases farm output by 50%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (16, 'stronger_explosives', 'Stronger Explosives', 'military', 15000, NULL, NULL, NULL, 'Research and development into explosives allows for more effective bauxite harvesting, increasing production by 45%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (17, 'widespread_propaganda', 'Widespread Propaganda', 'diplomacy', 10000, 12, NULL, NULL, 'Use of propaganda in media, news, and through devices allows for easy recruitment of soldiers, bringing costs down by 35%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (18, 'increased_funding', 'Increased Funding', 'science', 12000, NULL, NULL, NULL, 'Increased funding and construction of new operative bases allows for the ability to recruit and maintain more spies by a factor of 40%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (19, 'automation_integration', 'Automation Integration', 'industry', 30000, NULL, NULL, NULL, 'Research and development into technologies allows for cheaper and quicker production of components, decreasing resources needed to make components by 25%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (20, 'larger_forges', 'Larger Forges', 'industry', 14000, NULL, NULL, NULL, 'Heavy subsidisation of the steel industry allows for investments into large scale projects, decreasing upkeep and resources to make steel by 30%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (21, 'looting_teams', 'Looting Teams', 'military', 8000, 22, NULL, NULL, 'Looting teams will acquire military supplies from annexed establishments, increasing war supplies production by 10%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (22, 'organized_supply_lines', 'Organized Supply Lines', 'military', 16000, NULL, NULL, NULL, 'Organized supply lines gives annexed citizens jobs producing resources for your war economy, further increasing war supplies production by 15%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (23, 'large_storehouses', 'Large Storehouses', 'infrastructure', 11000, NULL, NULL, NULL, 'Large storehouses allows for greater storage of war supplies, increasing max supplies by 25%.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (24, 'ballistic_missile_silo', 'Ballistic Missile Silo', 'military', 40000, 26, NULL, NULL, 'Ballistic missile silos provides countries with the ability to develop and deploy ballistic missiles.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (25, 'icbm_silo', 'ICBM Silo', 'military', 50000, 24, NULL, NULL, 'Inter-continental ballistic missile silos allows countries to develop and deploy inter-continental ballistic missiles.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (26, 'nuclear_testing_facility', 'Nuclear Testing Facility', 'military', 60000, 9, NULL, NULL, 'Nuclear testing facilities gives countries the ability to create nuclear warheads and establish nuclear reactors.', true, '2026-03-03 00:07:46.905044+00');
INSERT INTO public.tech_dictionary VALUES (29, 'star_wars_project', 'Star Wars Project', 'military', 1200000, NULL, 'iron_dome_bonus', 25.00, 'Strategic Defense Initiative. Iron Domes detect and shoot down 25% more incoming missiles, drones and nukes. Prohibitively expensive, just like the real one.', true, '2026-10-04 09:29:50.416907+00');


--
-- Data for Name: building_dictionary; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.building_dictionary VALUES (37, 'silos', 'Silos', 'military', 1080000, 'unit_capacity', 1.00, 340000, NULL, 'Store and launch ballistic missiles and nuclear weapons.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (43, 'lead_mines', 'Lead Mines', 'resource_production', 45000, 'resource_production', 19.00, 7200, NULL, 'Mine lead used in ammunition production.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (45, 'wind_farms', 'Wind Farms', 'energy', 4000000, 'energy_production', 2.00, 8000, NULL, NULL, true, '2026-07-02 08:32:28.482398+00');
INSERT INTO public.building_dictionary VALUES (46, 'geothermal_plants', 'Geothermal Plants', 'energy', 12000000, 'energy_production', 5.00, 20000, NULL, NULL, true, '2026-07-02 08:32:28.482398+00');
INSERT INTO public.building_dictionary VALUES (48, 'drone_sites', 'Drone Site', 'military', 15000000, 'unit_production', 10.00, 5000, NULL, 'Manufactures kamikaze drones over time into a stockpile (10/site) you can activate into your military.', true, '2026-09-04 23:53:34.878107+00');
INSERT INTO public.building_dictionary VALUES (49, 'missile_batteries', 'Missile Battery', 'military', 120000000, 'unit_production', 5.00, 40000, NULL, 'Manufactures cruise missiles over time into a stockpile (5/battery) you can activate into your military.', true, '2026-09-04 23:53:34.878107+00');
INSERT INTO public.building_dictionary VALUES (50, 'railways', 'Railways', 'civic', 62500000, 'resource_production', 8.00, 67500, NULL, 'Regional rail network boosting productivity.', true, '2026-09-28 14:36:32.891379+00');
INSERT INTO public.building_dictionary VALUES (51, 'metros', 'Metros', 'civic', 150000000, 'resource_production', 12.00, 150000, NULL, 'Urban metro system significantly boosting productivity.', true, '2026-09-28 14:36:32.891379+00');
INSERT INTO public.building_dictionary VALUES (52, 'firewatch_towers', 'Firewatch Towers', 'civic', 15000, 'resource_production', 0.00, 1000, NULL, 'Fire lookout towers reducing wildfire disaster risk.', true, '2026-09-28 14:36:32.891379+00');
INSERT INTO public.building_dictionary VALUES (53, 'levees', 'Levees', 'civic', 75000, 'resource_production', 0.00, 3000, NULL, 'Flood barriers reducing flood and monsoon disaster risk.', true, '2026-09-28 14:36:32.891379+00');
INSERT INTO public.building_dictionary VALUES (54, 'seismic_reinforcements', 'Seismic Reinforcements', 'civic', 150000, 'resource_production', 0.00, 5000, NULL, 'Earthquake-resistant infrastructure reducing rockslide disaster risk.', true, '2026-09-28 14:36:32.891379+00');
INSERT INTO public.building_dictionary VALUES (1, 'farms', 'Farms', 'resource_production', 1050000, 'resource_production', 12.00, 50, NULL, 'Agricultural facilities producing rations for population', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (2, 'pumpjacks', 'Oil Pumpjacks', 'resource_production', 2100000, 'resource_production', 24.00, 150, NULL, 'Extract crude oil from underground reserves', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (3, 'coal_mines', 'Coal Mines', 'resource_production', 2450000, 'resource_production', 31.00, 100, NULL, 'Extract coal for energy and industrial use', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (40, 'bauxite_mines', 'Bauxite Mines', 'resource_production', 2250000, 'resource_production', 20.00, 8000, NULL, 'Mine raw bauxite for aluminium production.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (41, 'copper_mines', 'Copper Mines', 'resource_production', 1950000, 'resource_production', 25.00, 5000, NULL, 'Extract copper ore used in components and ammunition.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (42, 'uranium_mines', 'Uranium Mines', 'resource_production', 3850000, 'resource_production', 12.00, 45000, NULL, 'Mine radioactive uranium for nuclear power.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (39, 'iron_mines', 'Iron Mines', 'resource_production', 2650000, 'resource_production', 23.00, 11000, NULL, 'Extract iron ore from underground deposits.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (38, 'lumber_mills', 'Lumber Mills', 'resource_production', 1550000, 'resource_production', 35.00, 7500, NULL, 'Harvest and process timber into lumber.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (25, 'component_factories', 'Component Factories', 'resource_production', 11200000, 'resource_production', 5.00, 50000, NULL, 'Produce military components from copper, steel, and aluminium', true, '2026-03-05 06:33:55.860445+00');
INSERT INTO public.building_dictionary VALUES (4, 'steel_mills', 'Steel Mills', 'resource_production', 8400000, 'resource_production', 12.00, 200, NULL, 'Process iron ore into steel for construction', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (26, 'ammunition_factories', 'Ammunition Factories', 'resource_production', 7000000, 'resource_production', 12.00, 15000, NULL, 'Produce ammunition from copper and lead', true, '2026-03-05 06:33:55.860445+00');
INSERT INTO public.building_dictionary VALUES (24, 'aluminium_refineries', 'Aluminium Refineries', 'resource_production', 7700000, 'resource_production', 16.00, 42000, NULL, 'Refine bauxite into aluminium for aircraft production', true, '2026-03-05 06:33:55.860445+00');
INSERT INTO public.building_dictionary VALUES (23, 'oil_refineries', 'Oil Refineries', 'resource_production', 6300000, 'resource_production', 11.00, 35000, NULL, 'Refine oil into gasoline for military vehicles and aircraft', true, '2026-03-05 06:33:55.860445+00');
INSERT INTO public.building_dictionary VALUES (31, 'hydro_dams', 'Hydro Dams', 'energy', 120000, 'energy_production', 6.00, 24000, NULL, 'Large-scale hydroelectric power generation.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (32, 'gas_stations', 'Gas Stations', 'commerce', 60000, 'resource_production', 12.00, 20000, NULL, 'Retail fuel stations that also distribute consumer goods.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (33, 'farmers_markets', 'Farmers Markets', 'commerce', 110000, 'resource_production', 16.00, 80000, NULL, 'Local food distribution and rations availability.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (55, 'silver_mines', 'Silver Mines', 'resource_production', 4000000, 'resource_production', 60.00, 12000, NULL, 'Extracts silver from mineral veins.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (6, 'oil_burners', 'Oil Power Plants', 'energy', 3150000, 'energy_production', 600.00, 400, NULL, 'Generate electricity by burning oil', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (56, 'diamond_mines', 'Diamond Mines', 'resource_production', 6000000, 'resource_production', 30.00, 25000, NULL, 'Mines diamonds from deep kimberlite pipes.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (57, 'bullion_mines', 'Bullion Mines', 'resource_production', 5000000, 'resource_production', 40.00, 18000, NULL, 'Mines and casts precious metal bullion.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (58, 'fisheries', 'Fisheries', 'resource_production', 800000, 'resource_production', 160.00, 1800, NULL, 'Aquaculture and coastal fisheries producing food rations.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (59, 'workshops', 'Workshops', 'commerce', 3000000, 'resource_production', 4.00, 12000, NULL, 'Artisan workshops crafting consumer goods from steel.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (60, 'jewelry_stores', 'Jewelry Stores', 'commerce', 45000000, 'resource_production', 36.00, 60000, NULL, 'High-end jewelry stores crafting luxury consumer goods from silver, diamonds, and bullion.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (61, 'automotive_plants', 'Automotive Plants', 'commerce', 350000000, 'resource_production', 160.00, 180000, NULL, 'Large-scale automotive manufacturing plants producing high volumes of consumer goods.', true, '2026-09-28 18:55:40.083038+00');
INSERT INTO public.building_dictionary VALUES (7, 'nuclear_reactors', 'Nuclear Reactors', 'energy', 105000000, 'energy_production', 2000.00, 1000, NULL, 'Advanced nuclear power generation', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (30, 'solar_fields', 'Solar Fields', 'energy', 5600000, 'energy_production', 3.00, 13000, NULL, 'Clean energy from sunlight. No fuel required.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (11, 'general_stores', 'General Stores', 'commerce', 10500000, 'tax_income', 500.00, 80, NULL, 'Retail establishments generating tax revenue', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (12, 'malls', 'Shopping Malls', 'commerce', 157500000, 'tax_income', 2000.00, 350, NULL, 'Large commercial centers with high tax yield', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (13, 'banks', 'Banks', 'commerce', 84000000, 'tax_income', 3000.00, 500, NULL, 'Financial institutions generating significant revenue', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (34, 'city_parks', 'City Parks', 'civic', 22000, 'happiness', 5.00, 25000, NULL, 'Green spaces that increase happiness and reduce pollution.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (35, 'monorails', 'Monorails', 'civic', 600000, 'resource_production', 16.00, 270000, NULL, 'High-speed urban transit boosting productivity.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (36, 'admin_buildings', 'Administrative Buildings', 'military', 135000, 'military_boost', 1.00, 90000, NULL, 'Enable spy recruitment and intelligence operations.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (47, 'food_banks', 'Food Banks', 'infrastructure', 250000, 'population_growth', 250000.00, 2500, NULL, 'Cheap distribution building to distribute rations to the populace.', true, '2026-08-02 19:22:03.977839+00');
INSERT INTO public.building_dictionary VALUES (44, 'distribution_centers', 'Distribution Centers', 'commerce', 45000, 'resource_production', 8.00, 15000, NULL, 'Large-scale logistics hubs that distribute rations and consumer goods to 400,000 citizens each.', true, '2026-03-05 16:48:31.350125+00');
INSERT INTO public.building_dictionary VALUES (5, 'coal_burners', 'Coal Power Plants', 'energy', 1750000, 'energy_production', 500.00, 300, NULL, 'Generate electricity by burning coal', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (17, 'industrial_district', 'Industrial District', 'resource_production', 196000000, 'resource_production', 50.00, 400, NULL, 'Advanced manufacturing hub producing consumer goods and components', true, '2026-03-05 02:10:55.498345+00');
INSERT INTO public.building_dictionary VALUES (8, 'hospitals', 'Hospitals', 'civic', 21000000, 'population_growth', 5.00, 200, NULL, 'Medical facilities improving population health and growth', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (10, 'libraries', 'Libraries', 'civic', 7000000, 'happiness', 3.00, 100, NULL, 'Cultural centers improving citizen happiness', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (9, 'universities', 'Universities', 'civic', 28000000, 'research_speed', 10.00, 300, NULL, 'Higher education institutions accelerating research', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (18, 'primary_school', 'Primary School', 'civic', 2800000, 'population_growth', 3.00, 150, NULL, 'Elementary education facility establishing baseline education', true, '2026-03-05 02:10:55.498345+00');
INSERT INTO public.building_dictionary VALUES (19, 'high_school', 'High School', 'civic', 8400000, 'research_speed', 7.00, 250, NULL, 'Secondary education institution advancing student knowledge', true, '2026-03-05 02:10:55.498345+00');
INSERT INTO public.building_dictionary VALUES (14, 'army_bases', 'Army Bases', 'military', 5600000, 'unit_capacity', 1000.00, 400, NULL, 'Military installations increasing ground unit capacity', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (16, 'harbours', 'Harbours', 'military', 12600000, 'unit_capacity', 300.00, 550, NULL, 'Naval ports increasing fleet capacity', true, '2026-03-02 23:32:27.006427+00');
INSERT INTO public.building_dictionary VALUES (15, 'aerodomes', 'Aerodromes', 'military', 15400000, 'unit_capacity', 500.00, 600, NULL, 'Air force bases increasing aircraft capacity', true, '2026-03-02 23:32:27.006427+00');


--
-- Data for Name: cosmetics; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.cosmetics VALUES (1, 'sunset-horizon', 'Sunset Horizon', 'background', 150, 'bg-sunset-horizon', NULL, true, 0, '2026-08-27 18:26:22.211127+00', NULL);
INSERT INTO public.cosmetics VALUES (2, 'emerald-canopy', 'Emerald Canopy', 'background', 250, 'bg-emerald-canopy', NULL, true, 1, '2026-08-27 18:26:22.211127+00', NULL);
INSERT INTO public.cosmetics VALUES (3, 'aurora-borealis', 'Aurora Borealis', 'background', 500, 'bg-aurora-borealis', NULL, true, 2, '2026-08-27 18:26:22.211127+00', NULL);
INSERT INTO public.cosmetics VALUES (4, 'midnight-nebula', 'Midnight Nebula', 'background', 400, 'bg-midnight-nebula', NULL, true, 3, '2026-08-27 18:26:22.211127+00', NULL);
INSERT INTO public.cosmetics VALUES (5, 'neon-circuit', 'Neon Circuit', 'background', 600, 'bg-neon-circuit', NULL, true, 4, '2026-08-27 18:26:22.211127+00', NULL);
INSERT INTO public.cosmetics VALUES (6, 'royal-amethyst', 'Royal Amethyst', 'background', 900, 'bg-royal-amethyst', NULL, true, 5, '2026-08-27 18:26:22.211127+00', NULL);
INSERT INTO public.cosmetics VALUES (14, 'crimson-wasteland', 'Crimson Wasteland', 'background', 200, 'bg-crimson-wasteland', NULL, true, 6, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (15, 'golden-savanna', 'Golden Savanna', 'background', 200, 'bg-golden-savanna', NULL, true, 7, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (16, 'arctic-frost', 'Arctic Frost', 'background', 350, 'bg-arctic-frost', NULL, true, 8, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (17, 'volcanic-ember', 'Volcanic Ember', 'background', 450, 'bg-volcanic-ember', NULL, true, 9, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (18, 'deep-ocean-trench', 'Deep Ocean Trench', 'background', 550, 'bg-deep-ocean-trench', NULL, true, 10, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (19, 'cherry-blossom-dusk', 'Cherry Blossom Dusk', 'background', 700, 'bg-cherry-blossom-dusk', NULL, true, 11, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (20, 'name-crimson-blaze', 'Crimson Blaze', 'name_color', 120, NULL, NULL, true, 0, '2026-09-03 06:30:37.91722+00', '#e63946');
INSERT INTO public.cosmetics VALUES (21, 'name-sunflower-gold', 'Sunflower Gold', 'name_color', 120, NULL, NULL, true, 1, '2026-09-03 06:30:37.91722+00', '#f2a900');
INSERT INTO public.cosmetics VALUES (22, 'name-emerald-green', 'Emerald Green', 'name_color', 120, NULL, NULL, true, 2, '2026-09-03 06:30:37.91722+00', '#2ea043');
INSERT INTO public.cosmetics VALUES (23, 'name-sky-cyan', 'Sky Cyan', 'name_color', 150, NULL, NULL, true, 3, '2026-09-03 06:30:37.91722+00', '#00b4d8');
INSERT INTO public.cosmetics VALUES (24, 'name-royal-purple', 'Royal Purple', 'name_color', 150, NULL, NULL, true, 4, '2026-09-03 06:30:37.91722+00', '#8e44ad');
INSERT INTO public.cosmetics VALUES (25, 'name-hot-pink', 'Hot Pink', 'name_color', 180, NULL, NULL, true, 5, '2026-09-03 06:30:37.91722+00', '#ff4d94');
INSERT INTO public.cosmetics VALUES (26, 'name-tangerine', 'Tangerine', 'name_color', 180, NULL, NULL, true, 6, '2026-09-03 06:30:37.91722+00', '#ff8c42');
INSERT INTO public.cosmetics VALUES (27, 'name-deep-rose', 'Deep Rose', 'name_color', 220, NULL, NULL, true, 7, '2026-09-03 06:30:37.91722+00', '#d6336c');
INSERT INTO public.cosmetics VALUES (28, 'badge-rising-star', 'Rising Star', 'badge', 150, NULL, NULL, true, 0, '2026-09-03 06:30:37.91722+00', 'stars');
INSERT INTO public.cosmetics VALUES (29, 'badge-iron-shield', 'Iron Shield', 'badge', 180, NULL, NULL, true, 1, '2026-09-03 06:30:37.91722+00', 'shield');
INSERT INTO public.cosmetics VALUES (30, 'badge-diplomat', 'Diplomat', 'badge', 180, NULL, NULL, true, 2, '2026-09-03 06:30:37.91722+00', 'handshake');
INSERT INTO public.cosmetics VALUES (31, 'badge-veteran-commander', 'Veteran Commander', 'badge', 220, NULL, NULL, true, 3, '2026-09-03 06:30:37.91722+00', 'military_tech');
INSERT INTO public.cosmetics VALUES (32, 'badge-warmonger', 'Warmonger', 'badge', 220, NULL, NULL, true, 4, '2026-09-03 06:30:37.91722+00', 'local_fire_department');
INSERT INTO public.cosmetics VALUES (33, 'badge-elite-council', 'Elite Council', 'badge', 280, NULL, NULL, true, 5, '2026-09-03 06:30:37.91722+00', 'workspace_premium');
INSERT INTO public.cosmetics VALUES (34, 'badge-champion', 'Champion', 'badge', 320, NULL, NULL, true, 6, '2026-09-03 06:30:37.91722+00', 'emoji_events');
INSERT INTO public.cosmetics VALUES (35, 'badge-verified-legend', 'Verified Legend', 'badge', 400, NULL, NULL, true, 7, '2026-09-03 06:30:37.91722+00', 'verified');
INSERT INTO public.cosmetics VALUES (36, 'title-the-benevolent', 'The Benevolent', 'title', 150, NULL, NULL, true, 0, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (37, 'title-the-diplomat', 'The Diplomat', 'title', 150, NULL, NULL, true, 1, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (38, 'title-the-unyielding', 'The Unyielding', 'title', 180, NULL, NULL, true, 2, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (39, 'title-iron-fist', 'Iron Fist', 'title', 180, NULL, NULL, true, 3, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (40, 'title-warlord', 'Warlord', 'title', 200, NULL, NULL, true, 4, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (41, 'title-the-visionary', 'The Visionary', 'title', 200, NULL, NULL, true, 5, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (42, 'title-architect-of-empires', 'Architect of Empires', 'title', 250, NULL, NULL, true, 6, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (43, 'title-conqueror', 'Conqueror', 'title', 280, NULL, NULL, true, 7, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (44, 'border-golden-crest', 'Golden Crest', 'country_border', 250, 'border-golden-crest', NULL, true, 0, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (45, 'border-obsidian-frame', 'Obsidian Frame', 'country_border', 250, 'border-obsidian-frame', NULL, true, 1, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (46, 'border-emerald-laurel', 'Emerald Laurel', 'country_border', 300, 'border-emerald-laurel', NULL, true, 2, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (47, 'border-royal-crimson', 'Royal Crimson Trim', 'country_border', 300, 'border-royal-crimson', NULL, true, 3, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (48, 'border-frostbound-edge', 'Frostbound Edge', 'country_border', 350, 'border-frostbound-edge', NULL, true, 4, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (49, 'border-molten-core', 'Molten Core Rim', 'country_border', 400, 'border-molten-core', NULL, true, 5, '2026-09-03 06:30:37.91722+00', NULL);
INSERT INTO public.cosmetics VALUES (50, 'title-conqueror-of-worlds', 'Conqueror of Worlds', 'title', 320, NULL, NULL, true, 8, '2026-09-08 08:15:45.486536+00', NULL);
INSERT INTO public.cosmetics VALUES (51, 'molten-forge', 'Molten Forge', 'background', 650, 'bg-molten-forge', NULL, true, 12, '2026-09-16 11:57:32.268695+00', NULL);


--
-- Data for Name: gem_packages; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.gem_packages VALUES (1, 'Starter Pack', 300, 299, 'usd', NULL, true, 0, '2026-08-27 18:26:22.211127+00', 572730, 300);
INSERT INTO public.gem_packages VALUES (2, 'Popular Pack', 550, 499, 'usd', NULL, true, 1, '2026-08-27 18:26:22.211127+00', 572731, 500);
INSERT INTO public.gem_packages VALUES (3, 'Value Pack', 1200, 999, 'usd', NULL, true, 2, '2026-08-27 18:26:22.211127+00', 572732, 1000);
INSERT INTO public.gem_packages VALUES (4, 'Mega Pack', 2800, 1999, 'usd', NULL, true, 3, '2026-08-27 18:26:22.211127+00', 572733, 2000);


--
-- Data for Name: patreon_tiers; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.patreon_tiers VALUES (1, 'Just to show your love!', 600, true, '2026-08-30 08:45:37.486207+00');
INSERT INTO public.patreon_tiers VALUES (2, 'Order''s Elite', 1000, true, '2026-08-30 08:53:46.431067+00');
INSERT INTO public.patreon_tiers VALUES (3, 'The High Council', 2500, true, '2026-08-30 08:59:12.29107+00');
INSERT INTO public.patreon_tiers VALUES (4, 'Supreme Sovereign', 5000, true, '2026-09-02 19:14:39.03177+00');


--
-- Data for Name: resource_dictionary; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.resource_dictionary VALUES (1, 'rations', 'Rations', 'Food resources for population sustenance', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (2, 'oil', 'Oil', 'Raw oil for fuel and production', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (3, 'coal', 'Coal', 'Raw coal for energy', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (4, 'uranium', 'Uranium', 'Raw uranium for advanced weapons', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (5, 'bauxite', 'Bauxite', 'Raw ore for aluminium production', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (6, 'iron', 'Iron', 'Raw iron ore', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (7, 'lead', 'Lead', 'Raw lead for ammunition', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (8, 'copper', 'Copper', 'Raw copper for components', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (9, 'lumber', 'Lumber', 'Wood for construction', false, true, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (10, 'components', 'Components', 'Manufactured military components', true, false, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (11, 'steel', 'Steel', 'Refined steel for construction and military', true, false, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (12, 'consumer_goods', 'Consumer Goods', 'Goods for civilian population', true, false, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (13, 'aluminium', 'Aluminium', 'Refined aluminium for aircraft', true, false, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (14, 'gasoline', 'Gasoline', 'Refined fuel for vehicles and aircraft', true, false, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (15, 'ammunition', 'Ammunition', 'Manufactured ammunition for military', true, false, '2026-03-02 22:52:35.442786+00', true);
INSERT INTO public.resource_dictionary VALUES (31, 'silver', 'Silver', 'Precious metal mined from mineral veins, used in jewelry and luxury goods.', false, true, '2026-09-28 18:55:40.083038+00', true);
INSERT INTO public.resource_dictionary VALUES (32, 'diamonds', 'Diamonds', 'Precious gemstones mined from deep kimberlite pipes, used in jewelry and luxury goods.', false, true, '2026-09-28 18:55:40.083038+00', true);
INSERT INTO public.resource_dictionary VALUES (33, 'bullion', 'Bullion', 'Refined gold bullion mined and cast into bars, highly prized for trade and jewelry.', false, true, '2026-09-28 18:55:40.083038+00', true);


--
-- Data for Name: unit_dictionary; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.unit_dictionary VALUES (37, 'aircraft_carriers', 'Aircraft Carriers', 'naval', 40.00, 3.50, 14, 60, 12, 0, 60000, 400000, 20000, 'Naval capital ship. Extends the reach of your air wing -- each carrier raises your fighter/bomber capacity.', true, '2026-09-04 23:53:34.878107+00', 200000, 0);
INSERT INTO public.unit_dictionary VALUES (38, 'sam_batteries', 'SAM Batteries', 'strategic', 0.00, 5.00, 14, 15, 3, 0, 4000, 15000, 0, 'Surface-to-Air Missile battery. Automatically intercepts incoming Kamikaze Drones and Cruise Missiles.', true, '2026-09-27 11:52:18.755705+00', 5000, 0);
INSERT INTO public.unit_dictionary VALUES (39, 'counter_intel_agents', 'Counter-Intelligence Agents', 'espionage', 0.00, 0.00, 1, 2, 1, 200, 1500, 0, 0, 'Internal security force. Intercepts incoming enemy spy operations before they happen, capturing some of the enemy spies.', true, '2026-09-27 11:52:18.779812+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (9, 'spies', 'Spies', 'espionage', 0.50, 0.50, 10, 1, 0, 100, 2000, 0, 0, 'Intelligence and espionage unit', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (1, 'soldiers', 'Soldiers', 'infantry', 1.00, 1.50, 1, 1, 0, 500, 0, 0, 0, 'Basic infantry unit for ground combat', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (2, 'tanks', 'Tanks', 'vehicle', 3.00, 2.50, 14, 2, 0, 0, 5000, 50000, 2000, 'Armored ground vehicle for heavy combat', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (3, 'artillery', 'Artillery', 'vehicle', 2.50, 1.00, 14, 1, 0, 0, 3000, 30000, 1000, 'Long-range ground weapon system', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (10, 'icbms', 'ICBMs', 'strategic', 5.00, 0.00, 14, 5, 0, 0, 50000, 0, 15000, 'Intercontinental ballistic missile', true, '2026-03-02 22:52:35.577716+00', 80000, 0);
INSERT INTO public.unit_dictionary VALUES (4, 'fighters', 'Fighters', 'naval', 35.00, 25.00, 14, 3, 0, 0, 10000, 0, 5000, 'Jet fighter aircraft', true, '2026-03-02 22:52:35.577716+00', 20000, 0);
INSERT INTO public.unit_dictionary VALUES (5, 'bombers', 'Bombers', 'naval', 50.00, 10.00, 14, 3, 0, 0, 15000, 0, 8000, 'Heavy bomber aircraft', true, '2026-03-02 22:52:35.577716+00', 25000, 0);
INSERT INTO public.unit_dictionary VALUES (31, 'apaches', 'Apache Helicopters', 'naval', 15.00, 10.00, 14, 3, 4, 0, 8000, 0, 3000, 'Attack helicopter with strong offensive capabilities', true, '2026-03-03 01:29:30.319054+00', 15000, 0);
INSERT INTO public.unit_dictionary VALUES (6, 'destroyers', 'Destroyers', 'naval', 40.00, 55.00, 14, 3, 0, 0, 15000, 120000, 4000, 'Fast naval warship', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (7, 'cruisers', 'Cruisers', 'naval', 55.00, 65.00, 14, 5, 0, 0, 25000, 200000, 6000, 'Medium naval warship', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (8, 'submarines', 'Submarines', 'naval', 50.00, 20.00, 14, 2, 0, 0, 20000, 150000, 5000, 'Stealth underwater naval unit', true, '2026-03-02 22:52:35.577716+00', 0, 0);
INSERT INTO public.unit_dictionary VALUES (11, 'nukes', 'Nuclear Warheads', 'strategic', 10.00, 0.00, NULL, 0, 0, 0, 100000, 0, 25000, 'Nuclear deterrent weapon', true, '2026-03-02 22:52:35.577716+00', 120000, 20000);
INSERT INTO public.unit_dictionary VALUES (35, 'kamikaze_drones', 'Kamikaze Drones', 'strategic', 1.50, 0.00, 14, 5, 0, 0, 400, 0, 0, 'Cheap expendable loitering munition. Weak alone -- meant to be launched in swarms at enemy buildings.', true, '2026-09-04 23:53:34.878107+00', 800, 0);
INSERT INTO public.unit_dictionary VALUES (36, 'cruise_missiles', 'Cruise Missiles', 'strategic', 4.00, 0.00, 14, 20, 0, 0, 8000, 5000, 0, 'Precision-guided missile. Pricier and slower to produce than drones, but a guaranteed hit.', true, '2026-09-04 23:53:34.878107+00', 12000, 0);


--
-- Name: building_dictionary_building_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.building_dictionary_building_id_seq', 61, true);


--
-- Name: cosmetics_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.cosmetics_id_seq', 51, true);


--
-- Name: gem_packages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.gem_packages_id_seq', 4, true);


--
-- Name: patreon_tiers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patreon_tiers_id_seq', 4, true);


--
-- Name: resource_dictionary_resource_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.resource_dictionary_resource_id_seq', 33, true);


--
-- Name: tech_dictionary_tech_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tech_dictionary_tech_id_seq', 30, true);


--
-- Name: unit_dictionary_unit_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.unit_dictionary_unit_id_seq', 39, true);


--
-- PostgreSQL database dump complete
--



-- Migrations already applied in production (so CI only runs NEW ones).
INSERT INTO public.schema_migrations VALUES ('0011_add_users_last_active.sql', '2026-06-03 07:33:23.788585+00');
INSERT INTO public.schema_migrations VALUES ('0012_add_join_number.sql', '2026-06-03 07:33:23.806475+00');
INSERT INTO public.schema_migrations VALUES ('0013_add_demographics_education_schema.sql', '2026-06-03 07:33:23.826719+00');
INSERT INTO public.schema_migrations VALUES ('0015_add_hotpath_indexes.sql', '2026-06-03 07:33:23.847596+00');
INSERT INTO public.schema_migrations VALUES ('0017_add_performance_indexes.sql', '2026-06-03 07:33:23.959518+00');
INSERT INTO public.schema_migrations VALUES ('0018_cleanup_indexes_add_spyinfo.sql', '2026-06-03 07:33:23.998307+00');
INSERT INTO public.schema_migrations VALUES ('0019_fix_maintenance_costs.sql', '2026-06-03 07:33:24.022888+00');
INSERT INTO public.schema_migrations VALUES ('0020_enforce_population_demographics_sync.sql', '2026-06-03 07:33:24.073103+00');
INSERT INTO public.schema_migrations VALUES ('0021_coalition_members_and_discord_compat.sql', '2026-06-03 07:33:24.096958+00');
INSERT INTO public.schema_migrations VALUES ('0022_discord_bot.sql', '2026-06-03 07:33:24.149586+00');
INSERT INTO public.schema_migrations VALUES ('0023_discord_guild_panels.sql', '2026-06-03 07:33:24.202881+00');
INSERT INTO public.schema_migrations VALUES ('0025_tech_tree_prerequisites.sql', '2026-06-03 16:25:16.491415+00');
INSERT INTO public.schema_migrations VALUES ('0026_fix_building_costs.sql', '2026-06-04 11:26:25.792687+00');
INSERT INTO public.schema_migrations VALUES ('0027_deprecate_distribution_centers.sql', '2026-06-04 11:26:26.060796+00');
INSERT INTO public.schema_migrations VALUES ('0028_add_world_map_nodes.sql', '2026-06-26 13:34:58.692358+00');
INSERT INTO public.schema_migrations VALUES ('0029_optimize_queries.sql', '2026-06-26 13:34:58.71166+00');
INSERT INTO public.schema_migrations VALUES ('0030_tutorial_rewards.sql', '2026-06-26 13:34:58.728672+00');
INSERT INTO public.schema_migrations VALUES ('0030_world_map_tiers.sql', '2026-06-26 13:34:58.745167+00');
INSERT INTO public.schema_migrations VALUES ('0031_advertisements.sql', '2026-06-26 13:34:58.764564+00');
INSERT INTO public.schema_migrations VALUES ('0032_poll_votes.sql', '2026-06-26 13:34:58.780628+00');
INSERT INTO public.schema_migrations VALUES ('0034_add_users_recovery_key.sql', '2026-06-26 13:34:58.813108+00');
INSERT INTO public.schema_migrations VALUES ('0035_add_provinces_image_data.sql', '2026-06-26 13:34:58.829381+00');
INSERT INTO public.schema_migrations VALUES ('0036_referrals.sql', '2026-06-26 13:34:58.849472+00');
INSERT INTO public.schema_migrations VALUES ('0030_add_furnace_projects.sql', '2026-06-26 13:34:58.87123+00');
INSERT INTO public.schema_migrations VALUES ('0024_nextjs_compat_views.sql', '2026-07-01 11:51:26.400259+00');
INSERT INTO public.schema_migrations VALUES ('0039_add_food_banks.sql', '2026-08-02 19:22:03.985902+00');
INSERT INTO public.schema_migrations VALUES ('0040_rebalance_naval_special_costs.sql', '2026-08-15 12:18:10.668144+00');
INSERT INTO public.schema_migrations VALUES ('0041_discord_analytics_panel.sql', '2026-08-15 12:32:21.906019+00');
INSERT INTO public.schema_migrations VALUES ('0042_coalition_invites.sql', '2026-08-15 18:45:33.802592+00');
INSERT INTO public.schema_migrations VALUES ('0043_planes_missiles_use_aluminium.sql', '2026-08-16 21:35:54.773421+00');
INSERT INTO public.schema_migrations VALUES ('0044_military_stat_rebalance.sql', '2026-08-19 20:09:49.437609+00');
INSERT INTO public.schema_migrations VALUES ('0045_add_login_events.sql', '2026-08-23 20:39:54.529175+00');
INSERT INTO public.schema_migrations VALUES ('0050_fix_coalition_messages_fk.sql', '2026-08-27 13:39:01.48477+00');
INSERT INTO public.schema_migrations VALUES ('0048_add_store_gems_cosmetics.sql', '2026-08-27 18:27:34.461706+00');
INSERT INTO public.schema_migrations VALUES ('0049_seed_store_catalog.sql', '2026-08-27 18:27:34.461706+00');
INSERT INTO public.schema_migrations VALUES ('0051_nukes_require_uranium.sql', '2026-08-28 07:26:40.034176+00');
INSERT INTO public.schema_migrations VALUES ('0052_add_patreon_gems.sql', '2026-08-29 15:32:41.091551+00');
INSERT INTO public.schema_migrations VALUES ('0053_seed_patreon_tiers.sql', '2026-08-30 08:45:41.291005+00');
INSERT INTO public.schema_migrations VALUES ('0054_seed_patreon_tier_elite.sql', '2026-08-30 08:54:13.156556+00');
INSERT INTO public.schema_migrations VALUES ('0055_seed_patreon_tier_high_council.sql', '2026-08-30 08:59:13.282299+00');
INSERT INTO public.schema_migrations VALUES ('0056_widen_users_description.sql', '2026-08-31 06:47:18.097476+00');
INSERT INTO public.schema_migrations VALUES ('0057_add_global_chat.sql', '2026-08-31 16:20:26.182103+00');
INSERT INTO public.schema_migrations VALUES ('0058_add_devlog_and_discussions.sql', '2026-08-31 17:00:45.970829+00');
INSERT INTO public.schema_migrations VALUES ('0059_coalition_members_joined_at.sql', '2026-09-01 08:33:07.756597+00');
INSERT INTO public.schema_migrations VALUES ('0060_add_login_verifications.sql', '2026-09-03 06:13:32.483199+00');
INSERT INTO public.schema_migrations VALUES ('0061_add_store_cosmetic_types.sql', '2026-09-03 06:29:42.951229+00');
INSERT INTO public.schema_migrations VALUES ('0062_seed_store_cosmetic_catalog.sql', '2026-09-03 06:30:37.981915+00');
INSERT INTO public.schema_migrations VALUES ('0016_add_market_offer_hotpath_indexes.sql', '2026-09-04 05:05:02.51789+00');
INSERT INTO public.schema_migrations VALUES ('0033_optimize_schema.sql', '2026-09-04 05:05:02.641011+00');
INSERT INTO public.schema_migrations VALUES ('0063_add_bmc_gem_purchases.sql', '2026-09-04 15:10:12.743259+00');
INSERT INTO public.schema_migrations VALUES ('0064_seed_bmc_gem_package_ids.sql', '2026-09-04 15:10:12.763552+00');
INSERT INTO public.schema_migrations VALUES ('0065_reactivate_distribution_centers.sql', '2026-09-04 22:59:23.316347+00');
INSERT INTO public.schema_migrations VALUES ('0066_drone_missile_carrier_units.sql', '2026-09-04 23:53:34.900767+00');
INSERT INTO public.schema_migrations VALUES ('0067_login_verifications_delivered.sql', '2026-09-05 14:17:11.819901+00');
INSERT INTO public.schema_migrations VALUES ('0068_add_users_session_epoch.sql', '2026-09-05 14:17:11.842266+00');
INSERT INTO public.schema_migrations VALUES ('0069_add_user_loans.sql', '2026-09-06 21:37:47.100739+00');
INSERT INTO public.schema_migrations VALUES ('0070_add_totp_2fa.sql', '2026-09-06 22:27:34.182022+00');
INSERT INTO public.schema_migrations VALUES ('0072_buff_aircraft_carrier_attack.sql', '2026-09-07 20:48:03.794994+00');
INSERT INTO public.schema_migrations VALUES ('0071_add_bounties_and_world_events.sql', '2026-09-08 07:19:37.869481+00');
INSERT INTO public.schema_migrations VALUES ('0073_nation_customization_fields.sql', '2026-09-08 07:26:29.959961+00');
INSERT INTO public.schema_migrations VALUES ('0074_seed_title_conqueror_of_worlds.sql', '2026-09-08 08:15:45.543994+00');
INSERT INTO public.schema_migrations VALUES ('0075_add_tutorial_step.sql', '2026-09-09 06:07:26.161908+00');
INSERT INTO public.schema_migrations VALUES ('0076_add_market_embargoes.sql', '2026-09-10 00:13:47.846123+00');
INSERT INTO public.schema_migrations VALUES ('0077_add_ads_image_data.sql', '2026-09-15 10:56:34.041625+00');
INSERT INTO public.schema_migrations VALUES ('0078_seed_molten_forge_background.sql', '2026-09-16 11:57:32.275119+00');
INSERT INTO public.schema_migrations VALUES ('0079_add_national_currency.sql', '2026-09-22 13:08:25.431315+00');
INSERT INTO public.schema_migrations VALUES ('0080_add_bonds_market.sql', '2026-09-22 13:11:24.683824+00');
INSERT INTO public.schema_migrations VALUES ('0081_add_war_last_attack_resolved_at.sql', '2026-09-23 07:08:16.320004+00');
INSERT INTO public.schema_migrations VALUES ('0082_coalition_bank_trades_and_bond_insurance.sql', '2026-09-26 21:07:27.011032+00');
INSERT INTO public.schema_migrations VALUES ('0083_add_currency_unions.sql', '2026-09-27 10:34:11.449466+00');
INSERT INTO public.schema_migrations VALUES ('0084_add_sam_battery.sql', '2026-09-27 11:52:18.764887+00');
INSERT INTO public.schema_migrations VALUES ('0085_spy_op_types_and_counter_intel.sql', '2026-09-27 11:52:18.789719+00');
INSERT INTO public.schema_migrations VALUES ('0086_coalition_recurring_trades_etc.sql', '2026-09-28 09:00:55.031119+00');
INSERT INTO public.schema_migrations VALUES ('0087_add_nation_revenue_history.sql', '2026-09-28 09:08:14.138571+00');
INSERT INTO public.schema_migrations VALUES ('0089_nuclear_strikes.sql', '2026-09-28 09:08:14.161652+00');
INSERT INTO public.schema_migrations VALUES ('0091_currency_market.sql', '2026-09-28 09:08:14.187315+00');
INSERT INTO public.schema_migrations VALUES ('0093.sql', '2026-09-28 14:36:32.880174+00');
INSERT INTO public.schema_migrations VALUES ('0094.sql', '2026-09-28 14:36:32.902097+00');
INSERT INTO public.schema_migrations VALUES ('0095_achievements.sql', '2026-09-28 14:36:32.923434+00');
INSERT INTO public.schema_migrations VALUES ('0096_cg_chains.sql', '2026-09-28 18:55:40.109467+00');
INSERT INTO public.schema_migrations VALUES ('0097_spyinfo_sam_batteries.sql', '2026-10-02 09:14:14.227321+00');
INSERT INTO public.schema_migrations VALUES ('0098_player_analytics.sql', '2026-10-02 09:14:14.250013+00');
INSERT INTO public.schema_migrations VALUES ('0099_backfill_discord_id.sql', '2026-10-02 09:14:14.271098+00');
INSERT INTO public.schema_migrations VALUES ('0100_add_news_is_read.sql', '2026-10-03 01:23:40.954081+00');
INSERT INTO public.schema_migrations VALUES ('0101_reimburse_24h_revenue.sql', '2026-10-03 08:29:43.699989+00');
INSERT INTO public.schema_migrations VALUES ('0102_personal_bank_accounts.sql', '2026-10-03 09:19:47.775791+00');
INSERT INTO public.schema_migrations VALUES ('0103_personal_bank_balance_from_log.sql', '2026-10-03 20:44:55.187491+00');
INSERT INTO public.schema_migrations VALUES ('0104_iron_dome.sql', '2026-10-06 09:48:42.000883+00');
INSERT INTO public.schema_migrations VALUES ('0104_market_rework.sql', '2026-10-06 09:48:42.020183+00');
INSERT INTO public.schema_migrations VALUES ('0105_spyinfo_iron_domes.sql', '2026-10-06 09:48:42.037791+00');
INSERT INTO public.schema_migrations VALUES ('0106_population_growth_freezes.sql', '2026-10-06 09:48:42.054441+00');

SET session_replication_role = DEFAULT;
