"""One-time setup: create tables in Neon and load the synthetic CSV data."""
import csv
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()  # reads DATABASE_URL from .env
DB_URL = os.getenv("DATABASE_URL")

# Parent tables first, because of foreign keys (vehicles need customers, etc.)
TABLES = ["customers", "vehicles", "policies", "past_claims", "policy_rules", "repair_prices"]


def load_csv(cur, table):
    """Read data/claims/<table>.csv and insert every row into the table."""
    with open(f"data/claims/{table}.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"

    for row in rows:
        # Empty cells (e.g. no add-ons) become NULL in the database
        values = [row[c] if row[c] != "" else None for c in columns]
        cur.execute(sql, values)
    print(f"{table}: {len(rows)} rows loaded")


def main():
    if not DB_URL:
        print("DATABASE_URL is empty. Paste your Neon connection string into .env and save it.")
        return

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    with open("scripts/schema.sql", encoding="utf-8") as f:
        cur.execute(f.read())
    print("Tables created")

    for table in TABLES:
        load_csv(cur, table)

    conn.commit()  # save everything in one go

    # Quick check: show the demo policy with its customer and car
    cur.execute("""
        SELECT p.policy_number, c.full_name, v.make, v.model, p.policy_type, p.status, p.idv, p.addons
        FROM policies p
        JOIN customers c ON c.customer_id = p.customer_id
        JOIN vehicles v  ON v.vehicle_id  = p.vehicle_id
        WHERE p.policy_number = 'SSM-2026-00001'
    """)
    print("Check:", cur.fetchone())

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
