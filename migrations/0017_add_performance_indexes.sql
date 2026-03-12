-- Migration 0017: Additional performance indexes for frequently queried tables

-- admin_user_controls is queried on EVERY request via before_request hook
CREATE INDEX IF NOT EXISTS idx_admin_user_controls_user_id ON admin_user_controls(user_id);

-- spyinfo queried by spyer on intelligence page, and by (spyer, spyee) on spy results
CREATE INDEX IF NOT EXISTS idx_spyinfo_spyer ON spyinfo(spyer);
CREATE INDEX IF NOT EXISTS idx_spyinfo_spyee ON spyinfo(spyee);
CREATE INDEX IF NOT EXISTS idx_spyinfo_date ON spyinfo(date);

-- news table queried by destination_id on every country page load
CREATE INDEX IF NOT EXISTS idx_news_destination_id ON news(destination_id);

-- revenue table queried by user_id on country page
CREATE INDEX IF NOT EXISTS idx_revenue_user_id ON revenue(user_id);

-- user_economy is hot-path: queried by (user_id, resource_id) constantly
CREATE INDEX IF NOT EXISTS idx_user_economy_user_resource ON user_economy(user_id, resource_id);

-- user_buildings queried by (user_id, province_id) on every province page
CREATE INDEX IF NOT EXISTS idx_user_buildings_user_province ON user_buildings(user_id, province_id);

-- user_military queried by (user_id, unit_id) for military operations
CREATE INDEX IF NOT EXISTS idx_user_military_user_unit ON user_military(user_id, unit_id);

-- coalitions_legacy queried by colid and userid frequently
CREATE INDEX IF NOT EXISTS idx_coalitions_legacy_colid ON coalitions_legacy(colid);
CREATE INDEX IF NOT EXISTS idx_coalitions_legacy_userid ON coalitions_legacy(userid);

-- treaties queried by col2_id and status
CREATE INDEX IF NOT EXISTS idx_treaties_col2_status ON treaties(col2_id, status);
CREATE INDEX IF NOT EXISTS idx_treaties_col1_id ON treaties(col1_id);

-- col_applications queried by colId
CREATE INDEX IF NOT EXISTS idx_col_applications_colid ON col_applications(colId);

-- requests table queried by colId
CREATE INDEX IF NOT EXISTS idx_requests_colid ON requests(colId);

-- stats table queried by id (should already be PK, but ensure)
CREATE INDEX IF NOT EXISTS idx_stats_id ON stats(id);

-- building_dictionary and resource_dictionary name lookups
CREATE INDEX IF NOT EXISTS idx_building_dictionary_name ON building_dictionary(name);
CREATE INDEX IF NOT EXISTS idx_resource_dictionary_name ON resource_dictionary(name);

-- unit_dictionary name lookups
CREATE INDEX IF NOT EXISTS idx_unit_dictionary_name ON unit_dictionary(name);

-- users last_active for coalition member display sorting
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active);

ANALYZE admin_user_controls;
ANALYZE spyinfo;
ANALYZE news;
ANALYZE revenue;
ANALYZE user_economy;
ANALYZE user_buildings;
ANALYZE user_military;
ANALYZE coalitions_legacy;
ANALYZE treaties;
ANALYZE building_dictionary;
ANALYZE resource_dictionary;
ANALYZE unit_dictionary;
