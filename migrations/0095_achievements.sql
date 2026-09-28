CREATE TABLE IF NOT EXISTS achievements (
    key VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(64) NOT NULL,
    tier VARCHAR(64) NOT NULL,
    icon VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS user_achievements (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key VARCHAR(64) NOT NULL REFERENCES achievements(key) ON DELETE CASCADE,
    unlocked_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
    UNIQUE(user_id, key)
);

CREATE INDEX IF NOT EXISTS user_achievements_user_id_idx ON user_achievements(user_id);

INSERT INTO achievements (key, name, description, category, tier, icon) VALUES
-- Economy
('eco_mall_1', 'Consumer Culture', 'Build your first Shopping Mall.', 'economy', 'bronze', 'fa-shopping-bag'),
('eco_cg_all', 'Self-Sufficient', 'Build at least one of every Consumer Goods building.', 'economy', 'silver', 'fa-industry'),
('eco_treasury_1b', 'Billionaire Club', 'Reach 1,000,000,000 in your national treasury.', 'economy', 'silver', 'fa-money-bill-wave'),
('eco_treasury_100b', 'Hundred Billionaire', 'Reach 100,000,000,000 in your national treasury.', 'economy', 'gold', 'fa-money-bill-alt'),
('eco_treasury_1t', 'Trillionaire', 'Reach 1,000,000,000,000 in your national treasury.', 'economy', 'platinum', 'fa-gem'),
('eco_bond_issued', 'Debt Market', 'Issue your first national bond.', 'economy', 'bronze', 'fa-file-invoice-dollar'),
('eco_bond_funded', 'Funded Future', 'Have a national bond fully funded by investors.', 'economy', 'silver', 'fa-hand-holding-usd'),
('eco_currency_minted', 'Sovereign Wealth', 'Mint your own national currency.', 'economy', 'silver', 'fa-coins'),
-- Population
('pop_1m', 'A Modest Republic', 'Reach a population of 1,000,000 citizens.', 'population', 'bronze', 'fa-users'),
('pop_100m', 'Thronging Masses', 'Reach a population of 100,000,000 citizens.', 'population', 'silver', 'fa-city'),
('pop_1b', 'Billion Strong', 'Reach a population of 1,000,000,000 citizens.', 'population', 'gold', 'fa-globe-americas'),
-- Expansion
('exp_prov_5', 'Regional Power', 'Expand your nation to 5 provinces.', 'expansion', 'bronze', 'fa-map-marked-alt'),
('exp_prov_20', 'Continental Power', 'Expand your nation to 20 provinces.', 'expansion', 'silver', 'fa-map'),
('exp_prov_50', 'Superpower', 'Expand your nation to 50 provinces.', 'expansion', 'gold', 'fa-globe'),
('exp_cities_1000', 'Urban Sprawl', 'Reach a total of 1,000 cities across all provinces.', 'expansion', 'silver', 'fa-building'),
-- Military
('mil_war_won', 'First Blood', 'Win your first war against another nation.', 'military', 'bronze', 'fa-fighter-jet'),
('mil_spy_op', 'Cloak and Dagger', 'Successfully execute your first espionage operation.', 'military', 'bronze', 'fa-user-secret'),
('mil_carrier', 'Force Projection', 'Construct and deploy an Aircraft Carrier.', 'military', 'silver', 'fa-ship'),
-- Diplomacy
('dip_coalition', 'Better Together', 'Join or create a coalition.', 'diplomacy', 'bronze', 'fa-handshake'),
('dip_treaty', 'Pen is Mightier', 'Sign a treaty with another nation.', 'diplomacy', 'bronze', 'fa-file-signature'),
-- Fun
('fun_nuke', 'I Am Become Death', 'Launch a nuclear strike.', 'fun', 'gold', 'fa-radiation'),
('fun_debt', 'Bailout Needed', 'Reach negative treasury.', 'fun', 'bronze', 'fa-chart-line-down')
ON CONFLICT (key) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    tier = EXCLUDED.tier,
    icon = EXCLUDED.icon;
