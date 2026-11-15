-- Nuke rework, phase 1 (flag nuke_rework, ships OFF). See docs/design/NUKE_REWORK.md.
-- Nuclear Weapons Facility manufactures nukes into the existing unit stockpile at
-- 1 per 72h per facility (fractional progress kept in user_nuke_progress).
BEGIN;

INSERT INTO building_dictionary (name, display_name, category, base_cost, effect_type, effect_value, maintenance_cost, description)
VALUES (
    'nuclear_weapons_facility', 'Nuclear Weapons Facility', 'military', 500000000, 'unit_production', 1, 500000,
    'Manufactures nuclear missiles into a stockpile (one per facility every 72 hours, up to your silo capacity). Activate them on the Military page.'
)
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS user_nuke_progress (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    progress NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (progress >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_nuke_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    auto_missile BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('nuke_rework', FALSE, 100,
        'Nukes are manufactured by the Nuclear Weapons Facility into a stockpile (capacity = silos) and activated for gold; direct purchase of nukes closes. Do not turn on until the Military page shows the facility stockpile.',
        'Turn off if nukes cannot be obtained or the production tick errors. Stockpiled nukes stay owned.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
