import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import supabase

def fix_constraints():
    print("Applying missing unique constraints to events_calendar...")
    # Using raw SQL via Supabase isn't directly supported in the client for DDL 
    # unless an RPC is set up. We will use a 'Delete + Insert' strategy for seeding instead.
    pass

def seed_events():
    events = [
        # --- Public Holidays 2026 ---
        {"event_name": "New Year's Day", "start_date": "2026-01-01", "end_date": "2026-01-01", "region_scope": "national", "affected_categories": ["beverages", "snacks", "alcohol"], "demand_multiplier": 1.5},
        {"event_name": "Independence Day", "start_date": "2026-03-06", "end_date": "2026-03-06", "region_scope": "national", "affected_categories": ["apparel", "beverages", "flags"], "demand_multiplier": 1.3},
        {"event_name": "Eid al-Fitr", "start_date": "2026-03-20", "end_date": "2026-03-21", "region_scope": "national", "affected_categories": ["rice", "oil", "meat", "confectionery"], "demand_multiplier": 1.7},
        {"event_name": "Easter Weekend", "start_date": "2026-04-03", "end_date": "2026-04-06", "region_scope": "national", "affected_categories": ["fish", "poultry", "beverages", "family-packs"], "demand_multiplier": 1.6},
        {"event_name": "Eid al-Adha", "start_date": "2026-05-27", "end_date": "2026-05-28", "region_scope": "national", "affected_categories": ["livestock", "rice", "seasonings"], "demand_multiplier": 1.8},
        {"event_name": "Farmers Day", "start_date": "2026-12-04", "end_date": "2026-12-04", "region_scope": "national", "affected_categories": ["canned-foods", "beverages"], "demand_multiplier": 1.2},
        {"event_name": "Christmas Season", "start_date": "2026-12-20", "end_date": "2026-12-31", "region_scope": "national", "affected_categories": ["gifts", "electronics", "beverages", "alcohol", "meat"], "demand_multiplier": 2.2},

        # --- Major Traditional Festivals ---
        {"event_name": "Aboakyer Festival", "start_date": "2026-05-02", "end_date": "2026-05-04", "region_scope": "Central", "affected_categories": ["tourism-retail", "beverages", "apparel"], "demand_multiplier": 1.4},
        {"event_name": "Homowo Festival", "start_date": "2026-08-15", "end_date": "2026-08-30", "region_scope": "Greater Accra", "affected_categories": ["maize", "palm-oil", "fish", "drinks"], "demand_multiplier": 1.5},
        {"event_name": "Hogbetsotso Festival", "start_date": "2026-11-07", "end_date": "2026-11-08", "region_scope": "Volta", "affected_categories": ["textiles", "beverages", "local-food"], "demand_multiplier": 1.4},

        # --- Commercial/Seasonal ---
        {"event_name": "Back to School (Term 1)", "start_date": "2026-01-05", "end_date": "2026-01-15", "region_scope": "national", "affected_categories": ["stationery", "detergents", "dairy", "cereal"], "demand_multiplier": 1.8},
        {"event_name": "Back to School (Term 2)", "start_date": "2026-05-01", "end_date": "2026-05-10", "region_scope": "national", "affected_categories": ["stationery", "dairy", "detergents"], "demand_multiplier": 1.6},
        {"event_name": "Black Friday Week", "start_date": "2026-11-23", "end_date": "2026-11-30", "region_scope": "national", "affected_categories": ["electronics", "appliances", "fashion"], "demand_multiplier": 2.5},
    ]
    
    # Strategy: Delete existing and re-insert to avoid constraint issues
    print("Clearing existing events...")
    supabase.table("events_calendar").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    
    print(f"Inserting {len(events)} events...")
    supabase.table("events_calendar").insert(events).execute()
    print("Events seeded successfully.")

def seed_cities():
    cities = [
        {"city_name": "Accra", "region": "Greater Accra", "population_segment": "Cosmopolitan Urban", "key_cultural_factors": ["multicultural", "e-commerce-heavy", "high-convenience"]},
        {"city_name": "Kumasi", "region": "Ashanti", "population_segment": "Trading Middle Class", "key_cultural_factors": ["traditional", "brand-loyal", "market-centric"]},
        {"city_name": "Tamale", "region": "Northern", "population_segment": "Regional Hub", "key_cultural_factors": ["religious-influenced", "wholesale-oriented", "livestock-hub"]},
        {"city_name": "Takoradi", "region": "Western", "population_segment": "Industrial Oil-City", "key_cultural_factors": ["high-purchasing-power", "nightlife-centric", "international-brands"]},
        {"city_name": "Tema", "region": "Greater Accra", "population_segment": "Blue-Collar Industrial", "key_cultural_factors": ["grocery-heavy", "worker-commute-patterns"]},
        {"city_name": "Cape Coast", "region": "Central", "population_segment": "Student/Tourist Hub", "key_cultural_factors": ["educational-spikes", "tourism-impacted"]},
        {"city_name": "Sunyani", "region": "Bono", "population_segment": "Agrarian Urban", "key_cultural_factors": ["food-basket", "stable-demand"]},
        {"city_name": "Koforidua", "region": "Eastern", "population_segment": "Commercial/Traders", "key_cultural_factors": ["commuter-retail", "strong-weekly-markets"]},
    ]
    
    # Strategy: Delete existing and re-insert
    print("Clearing existing city profiles...")
    supabase.table("city_profiles").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    
    print(f"Inserting {len(cities)} city profiles...")
    supabase.table("city_profiles").insert(cities).execute()
    print("Cities seeded successfully.")

if __name__ == "__main__":
    try:
        seed_events()
        seed_cities()
    except Exception as e:
        print(f"Error seeding data: {e}")
