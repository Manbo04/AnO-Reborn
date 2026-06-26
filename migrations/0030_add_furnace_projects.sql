-- Add Integrated Steelmaking and Electric Arc Furnace to tech_dictionary

INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
VALUES ('integrated_steelmaking', 'Integrated Steelmaking', 'industry', 100000, NULL, 'resource_production', 36.0, 'Boosts Steel Mills production by 36% nationwide. Iron and Coal usages are increased to create more Steel.')
ON CONFLICT (name) DO NOTHING;

INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
VALUES ('electric_arc_furnace', 'Electric Arc Furnace', 'industry', 120000, NULL, 'resource_production', 25.0, 'A modern steelmaking method that consumes 50% less raw iron and coal, but uses immense amounts of electricity (2 energy per mill).')
ON CONFLICT (name) DO NOTHING;
