from app import app
from database import get_request_cursor

with app.app_context():
    with get_request_cursor() as db:
        db.execute("""
        INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
        VALUES ('integrated_steelmaking', 'Integrated Steelmaking', 'industry', 100000, NULL, 'resource_production', 36.0, 'Boosts Steel Mills production by 36% nationwide. Iron and Coal usages are increased to create more Steel.')
        ON CONFLICT (name) DO NOTHING;
        """)

        db.execute("""
        INSERT INTO tech_dictionary (name, display_name, category, research_cost, prerequisite_tech_id, effect_type, effect_value, description)
        VALUES ('electric_arc_furnace', 'Electric Arc Furnace', 'industry', 120000, NULL, 'resource_production', 25.0, 'A modern steelmaking method that consumes less raw iron and coal, but uses immense amounts of electricity.')
        ON CONFLICT (name) DO NOTHING;
        """)
        print("Added tech projects to database!")
