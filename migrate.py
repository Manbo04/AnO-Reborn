from dotenv import load_dotenv
load_dotenv()
from app import app
from database import get_db_cursor

with app.app_context():
    with get_db_cursor() as db:
        try:
            db.execute("ALTER TABLE provinces ADD COLUMN wind_farms INTEGER DEFAULT 0;")
            print("Added wind_farms column to provinces table.")
        except Exception as e:
            print("wind_farms already exists or error:", e)
            
        try:
            db.execute("ALTER TABLE provinces ADD COLUMN geothermal_plants INTEGER DEFAULT 0;")
            print("Added geothermal_plants column to provinces table.")
        except Exception as e:
            print("geothermal_plants already exists or error:", e)

        # Also add to building_dictionary if needed for Economy 2.0
        try:
            db.execute("INSERT INTO building_dictionary (name, display_name, base_cost, is_active) VALUES ('wind_farms', 'Wind Farms', 4000000, true) ON CONFLICT (name) DO NOTHING;")
            db.execute("INSERT INTO building_dictionary (name, display_name, base_cost, is_active) VALUES ('geothermal_plants', 'Geothermal Plants', 12000000, true) ON CONFLICT (name) DO NOTHING;")
            print("Added wind_farms and geothermal_plants to building_dictionary.")
        except Exception as e:
            print("building_dictionary insert error:", e)

print("Migration done.")
