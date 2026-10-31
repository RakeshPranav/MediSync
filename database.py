
import sqlite3
import os

# Database location
DB_FOLDER = "database"
DB_PATH = os.path.join(DB_FOLDER, "inventory.db")


def get_connection():
    os.makedirs(DB_FOLDER, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Medical batches
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS batches (
        batch_id TEXT PRIMARY KEY,
        product_name TEXT NOT NULL,
        product_type TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK(quantity >= 0),
        expiry_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Released'
            CHECK(status IN ('Released', 'Quarantined', 'Rejected')),
        current_temp REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Hospital customers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospitals (
        hospital_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_name TEXT NOT NULL,
        min_shelf_life_months INTEGER NOT NULL DEFAULT 6
    )
    """)

    # 3. Temperature history
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS temperature_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        temperature REAL NOT NULL,
        recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
    )
    """)

    # 4. Dispatch records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dispatches (
        dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER NOT NULL,
        dispatch_date TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(hospital_id) REFERENCES hospitals(hospital_id)
    )
    """)

    # 5. Individual batches in each dispatch
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dispatch_items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dispatch_id INTEGER NOT NULL,
        batch_id TEXT NOT NULL,
        quantity_shipped INTEGER NOT NULL CHECK(quantity_shipped > 0),
        FOREIGN KEY(dispatch_id) REFERENCES dispatches(dispatch_id),
        FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
    )
    """)

    # 6. Quality inspection records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quality_records (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        decision TEXT NOT NULL,
        reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
    )
    """)

    conn.commit()
    conn.close()

    print("Database and tables created successfully!")


if __name__ == "__main__":
    create_tables()

