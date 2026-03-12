-- Migration 0015: Add hot-path indexes for task and page latency reduction

-- Provinces is queried heavily by user in countries/tasks/population flows
CREATE INDEX IF NOT EXISTS idx_provinces_userid ON provinces(userId);
CREATE INDEX IF NOT EXISTS idx_provinces_userid_id ON provinces(userId, id);

-- Revenue task resolves per-province building state in user_buildings
CREATE INDEX IF NOT EXISTS idx_user_buildings_province_id ON user_buildings(province_id);

-- Tax/revenue/task flows frequently read policies by user_id
CREATE INDEX IF NOT EXISTS idx_policies_user_id ON policies(user_id);

-- Upgrade preload in hourly revenue task filters unlocked tech by user
CREATE INDEX IF NOT EXISTS idx_user_tech_user_unlocked ON user_tech(user_id, is_unlocked);
