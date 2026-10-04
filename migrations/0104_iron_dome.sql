BEGIN;

-- Migration 0104: Iron Dome province air defense + Star Wars Project tech.
-- Iron Domes are bought per province and only protect that province.
-- Requested by Unknown Identity in #military-recommendations (2026-10-04).

CREATE TABLE IF NOT EXISTS province_iron_domes (
    province_id INTEGER PRIMARY KEY REFERENCES provinces(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0)
);

INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
SELECT 'star_wars_project', 'Star Wars Project', 'military',
       GREATEST(1000000, (SELECT COALESCE(MAX(research_cost), 0) * 10 FROM tech_dictionary WHERE name <> 'star_wars_project')),
       NULL, 'iron_dome_bonus', 25.0,
       'Strategic Defense Initiative. Iron Domes detect and shoot down 25% more incoming missiles, drones and nukes. Prohibitively expensive, just like the real one.'
ON CONFLICT (name) DO NOTHING;

COMMIT;
