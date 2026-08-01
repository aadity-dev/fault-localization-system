# backend/app/seed.py
def seed_database():
    if poles_table_is_empty():
        load_csv_into_db("data/pole_registry.csv")
        load_csv_into_db("data/dt_registry.csv")