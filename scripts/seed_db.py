import os
from app.db import supabase

def seed_events():
    events = [
        {"event_name": "Easter Holiday", "start_date": "2026-04-03", "end_date": "2026-04-06", "region_scope": "national", "affected_categories": ["confectionery", "beverages", "poultry"], "demand_multiplier": 1.4},
        {"event_name": "Eid al-Fitr", "start_date": "2026-03-20", "end_date": "2026-03-21", "region_scope": "national", "affected_categories": ["rice", "oil", "meat"], "demand_multiplier": 1.5},
        {"event_name": "Homowo Festival", "start_date": "2026-08-01", "end_date": "2026-08-31", "region_scope": "Greater Accra", "affected_categories": ["maize", "fish", "drinks"], "demand_multiplier": 1.3},
        {"event_name": "Back to School (Term 2)", "start_date": "2026-05-01", "end_date": "2026-05-10", "region_scope": "national", "affected_categories": ["stationary", "detergents", "cereal"], "demand_multiplier": 1.6},
    ]
    
    for event in events:
        supabase.table("events_calendar").upsert(event, on_conflict="event_name").execute()
    print("Events seeded successfully.")

def seed_cities():
    cities = [
        {"city_name": "Accra", "region": "Greater Accra", "population_segment": "High-Density Urban", "key_cultural_factors": ["multicultural", "tech-savvy", "high-convenience"]},
        {"city_name": "Kumasi", "region": "Ashanti", "population_segment": "Traditional Urban", "key_cultural_factors": ["traditional", "market-centric", "brand-loyal"]},
        {"city_name": "Tamale", "region": "Northern", "population_segment": "Regional Hub", "key_cultural_factors": ["religious", "wholesale-oriented", "seasonal-sensitive"]},
    ]
    
    for city in cities:
        supabase.table("city_profiles").upsert(city, on_conflict="city_name").execute()
    print("Cities seeded successfully.")

if __name__ == "__main__":
    try:
        seed_events()
        seed_cities()
    except Exception as e:
        print(f"Error seeding data: {e}")
