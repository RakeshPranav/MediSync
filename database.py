import os
import sqlite3

DB_FOLDER = "database"
DB_PATH = os.path.join(DB_FOLDER, "inventory.db")


def get_connection():
    """Autocommit mode: inventory.py controls transactions explicitly."""
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL COLLATE NOCASE,
    product_type TEXT NOT NULL
        CHECK(product_type IN ('Medicine', 'IV Fluid', 'Test Kit')),
    storage_condition TEXT NOT NULL
        CHECK(storage_condition IN ('Ambient', '2-8C')),
    quantity INTEGER NOT NULL CHECK(quantity >= 0),
    expiry_date TEXT NOT NULL,                 -- ISO format YYYY-MM-DD
    status TEXT NOT NULL DEFAULT 'Pending QC'
        CHECK(status IN ('Pending QC', 'Released', 'Quarantined', 'Rejected')),
    current_temp REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_name TEXT NOT NULL UNIQUE,
    min_shelf_life_months INTEGER NOT NULL DEFAULT 6
        CHECK(min_shelf_life_months >= 1)
);

CREATE TABLE IF NOT EXISTS temperature_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    temperature REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    is_excursion INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS dispatches (
    dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id INTEGER NOT NULL,
    dispatch_date TEXT NOT NULL,
    FOREIGN KEY(hospital_id) REFERENCES hospitals(hospital_id)
);

CREATE TABLE IF NOT EXISTS dispatch_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dispatch_id INTEGER NOT NULL,
    batch_id TEXT NOT NULL,
    quantity_shipped INTEGER NOT NULL CHECK(quantity_shipped > 0),
    FOREIGN KEY(dispatch_id) REFERENCES dispatches(dispatch_id),
    FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS quality_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    decision TEXT NOT NULL
        CHECK(decision IN ('Auto-Quarantined', 'Approved', 'Rejected')),
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_batches_product
    ON batches(product_name, expiry_date);
CREATE INDEX IF NOT EXISTS idx_templogs_batch
    ON temperature_logs(batch_id, recorded_at);
"""


def create_tables(verbose=True):
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
    if verbose:
        print("Database and tables created successfully!")


def reset_db():
    """Delete the DB file and rebuild it. Close Streamlit first on Windows."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    create_tables(verbose=False)


if __name__ == "__main__":
    create_tables()